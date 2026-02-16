"""
╔══════════════════════════════════════════════════════════════╗
║       TARS — Brain v4: Autonomous LLM Planner                ║
╠══════════════════════════════════════════════════════════════╣
║  v4: The Brain That Thinks                                   ║
║                                                              ║
║  Architecture:                                               ║
║    Phase 1 — Message Stream Parser (back-to-back msgs)       ║
║    Phase 2 — Intent Classifier (zero LLM tokens)             ║
║    Phase 3 — Conversation Threading (context continuity)     ║
║    Phase 4 — Brain/Hands Separation (think vs do)            ║
║    Phase 5 — Modular System Prompt (domain injection)        ║
║    Phase 6 — Live Knowledge Access (web search)              ║
║    Phase 7 — Task Decomposition (DAG subtasks)               ║
║    Phase 8 — Smart Escalation (5 strategies before asking)   ║
║    Phase 9 — Contextual Memory (auto-recall)                 ║
║    Phase 13 — Decision Journal (every decision logged)       ║
║    Phase 14 — Confidence Scoring (0-100 on decisions)        ║
║                                                              ║
║  Flow:                                                       ║
║    message → classify intent → route to thread →             ║
║    auto-recall memory → build focused prompt →               ║
║    think (LLM loop) → execute tools → verify → report        ║
║                                                              ║
║  The Brain ONLY thinks and decides.                          ║
║  The Executor ONLY executes.                                 ║
║  Clean separation. No mixed concerns.                        ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from brain.llm_client import LLMClient, _parse_failed_tool_call
from brain.prompts import build_system_prompt, RECOVERY_PROMPT
from brain.tools import TARS_TOOLS
from brain.intent import IntentClassifier, Intent
from brain.threads import ThreadManager
from utils.event_bus import event_bus

# Tools that depend on previous results — must run sequentially
DEPENDENT_TOOLS = {"verify_result", "send_imessage", "wait_for_reply", "checkpoint"}
# Tools safe to run in parallel
PARALLEL_SAFE = {"think", "scan_environment", "recall_memory", "run_quick_command", "quick_read_file", "web_search"}


class TARSBrain:
    """
    The Brain — TARS's thinking engine.
    
    Responsibilities:
    - Understand what the user wants (intent classification)
    - Track conversation context (threading)
    - Decide what to do (LLM reasoning)
    - Route decisions to the Executor (tool calls)
    - Verify results and adapt
    - Escalate intelligently when stuck
    
    NOT responsible for:
    - Executing tools (that's the Executor)
    - Retrying agent deployments (that's the Executor)
    - Managing LLM API errors (extracted to _call_llm helper)
    """

    def __init__(self, config, tool_executor, memory_manager):
        self.config = config
        
        # ── Dual-provider LLM setup ──
        brain_cfg = config.get("brain_llm")
        llm_cfg = config["llm"]
        
        if brain_cfg and brain_cfg.get("api_key"):
            self.client = LLMClient(
                provider=brain_cfg["provider"],
                api_key=brain_cfg["api_key"],
                base_url=brain_cfg.get("base_url"),
            )
            self.brain_model = brain_cfg["model"]
            print(f"  🧠 Brain: {brain_cfg['provider']}/{self.brain_model}")
        else:
            self.client = LLMClient(
                provider=llm_cfg["provider"],
                api_key=llm_cfg["api_key"],
                base_url=llm_cfg.get("base_url"),
            )
            self.brain_model = llm_cfg["heavy_model"]
            print(f"  🧠 Brain: {llm_cfg['provider']}/{self.brain_model} (single-provider)")

        # ── Provider failover ──
        self._primary_client = self.client
        self._primary_model = self.brain_model
        self._fallback_client = None
        self._fallback_model = None
        self._using_fallback = False

        fb_cfg = config.get("fallback_llm")
        if fb_cfg and fb_cfg.get("api_key"):
            self._fallback_client = LLMClient(
                provider=fb_cfg["provider"],
                api_key=fb_cfg["api_key"],
                base_url=fb_cfg.get("base_url"),
            )
            self._fallback_model = fb_cfg["model"]
            print(f"  🔄 Fallback: {fb_cfg['provider']}/{self._fallback_model}")

        # Legacy references for executor compatibility
        self.heavy_model = llm_cfg.get("heavy_model", llm_cfg.get("model", ""))
        self.fast_model = llm_cfg.get("fast_model", self.heavy_model)
        
        self.tool_executor = tool_executor
        self.memory = memory_manager
        self.max_retries = config["safety"]["max_retries"]

        # ── Phase 2: Intent Classifier ──
        self.intent_classifier = IntentClassifier()

        # ── Phase 3: Conversation Threading ──
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        thread_dir = os.path.join(base_dir, "memory", "threads")
        self.threads = ThreadManager(persistence_dir=thread_dir)
        
        # ── Conversation history (LLM-level) ──
        self.conversation_history = []
        self.max_history_messages = 80
        self.compaction_token_threshold = 80000
        self._compacted_summary = ""
        self.max_tool_loops = 50
        self._tool_loop_count = 0

        # ── Conversation continuity ──
        self._last_message_time = 0
        self._conversation_timeout = 600  # 10 min
        self._message_count = 0

    # ═══════════════════════════════════════════════════
    #  MAIN ENTRY POINT — process()
    # ═══════════════════════════════════════════════════

    def process(self, batch_or_text) -> str:
        """
        Main entry point for the Brain v4.
        
        Accepts either:
        - A MessageBatch (from the message stream parser)
        - A raw string (backward compatibility)
        
        Flow:
        1. Normalize input
        2. Classify intent (Phase 2)
        3. Route to thread (Phase 3)
        4. Auto-recall memory (Phase 9)
        5. Build focused prompt (Phase 5)
        6. Think via LLM loop (Phase 4)
        7. Record response in thread (Phase 3)
        8. Return final response
        """
        # ── Step 1: Normalize input ──
        from brain.message_parser import MessageBatch
        if isinstance(batch_or_text, MessageBatch):
            text = batch_or_text.merged_text
            batch_type = batch_or_text.batch_type
        else:
            text = str(batch_or_text)
            batch_type = "single"

        # ── Step 2: Classify intent (Phase 2 — zero LLM tokens) ──
        intent = self.intent_classifier.classify(
            text,
            has_active_thread=self.threads.has_active_thread,
            batch_type=batch_type,
        )
        print(f"  🎯 Intent: {intent}")

        # ── Step 3: Route to thread (Phase 3) ──
        thread = self.threads.route_message(text, intent.type, intent.confidence)
        print(f"  📎 Thread: {thread.topic} ({thread.id})")

        # ── Step 4: Auto-recall memory (Phase 9) ──
        memory_context = ""
        if intent.needs_memory:
            memory_context = self._auto_recall(text)

        # ── Step 5: Build thread context ──
        thread_context = self.threads.get_context_for_brain()

        # ── Step 6: Think (LLM loop) ──
        response = self._think_loop(
            user_message=text,
            intent=intent,
            thread=thread,
            memory_context=memory_context,
            thread_context=thread_context,
        )

        # ── Step 7: Record response in thread ──
        self.threads.record_response(response[:500])

        return response

    def think(self, user_message, use_heavy=None):
        """
        Backward-compatible entry point.
        
        The old tars.py calls brain.think(task). This delegates
        to the new process() method.
        """
        return self.process(user_message)

    # ═══════════════════════════════════════════════════
    #  CORE THINKING LOOP
    # ═══════════════════════════════════════════════════

    def _think_loop(self, user_message, intent, thread,
                    memory_context="", thread_context="") -> str:
        """
        The core LLM thinking loop.
        
        Refactored from v3's monolithic think() method:
        - LLM error handling extracted to _call_llm()
        - Tool execution extracted to _execute_tool_calls()
        - Prompt building uses the new modular system
        
        Still supports:
        - Streaming with event bus
        - Tool call loops (up to max_tool_loops)
        - Context compaction
        - Kill switch
        - Provider failover
        """
        # ── Restore primary provider if we failed over previously ──
        if self._using_fallback and self._primary_client:
            self._using_fallback = False
            self.client = self._primary_client
            self.brain_model = self._primary_model
            print(f"  🔄 Restored primary brain: {self._primary_model}")

        model = self.brain_model
        event_bus.emit("thinking_start", {"model": model})

        # ── Conversation continuity ──
        now = time.time()
        time_since_last = now - self._last_message_time if self._last_message_time else float("inf")
        self._last_message_time = now
        self._message_count += 1

        if time_since_last > self._conversation_timeout and self.conversation_history:
            print(f"  💭 Conversation gap: {int(time_since_last)}s — soft-resetting context")
            self._force_compact()

        # ── Add user message to LLM history ──
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        # ── Compact if needed ──
        self._compact_history()

        # ── Build system prompt (Phase 5 — modular) ──
        system_prompt = self._build_system_prompt(intent, thread_context, memory_context)

        # ── LLM thinking loop ──
        retry_count = 0
        self._tool_loop_count = 0

        while True:
            # Safety: kill switch
            kill_event = getattr(self.tool_executor, '_kill_event', None)
            if kill_event and kill_event.is_set():
                return "🛑 Kill switch activated — stopping all work."

            # Safety: max tool loops
            self._tool_loop_count += 1
            if self._tool_loop_count > self.max_tool_loops:
                event_bus.emit("error", {"message": f"Brain hit max tool loops ({self.max_tool_loops})"})
                return f"⚠️ Reached maximum {self.max_tool_loops} tool call loops. Task may be partially complete."

            # ── Call LLM (with error handling + failover) ──
            response, model = self._call_llm(system_prompt, model)
            if response is None:
                return "❌ LLM API error — could not get a response after retries."

            # ── Process response ──
            assistant_content = response.content
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_content,
            })

            if response.stop_reason == "tool_use":
                # ── Extract and execute tool calls ──
                tool_calls = [b for b in assistant_content if b.type == "tool_use"]
                tool_results = self._execute_tool_calls(tool_calls, retry_count, intent, thread)

                # Add tool results to conversation
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                # Compact if growing
                self._compact_history()

                # Continue the loop — LLM processes tool results next
                event_bus.emit("thinking_start", {"model": model})
                continue

            else:
                # ── Final text response — extract it ──
                final_text = ""
                for block in assistant_content:
                    if hasattr(block, "text"):
                        final_text += block.text

                # Phase 13: Self-reflection for non-trivial tasks
                if self._tool_loop_count > 3:
                    event_bus.emit("self_reflection", {
                        "loops": self._tool_loop_count,
                        "response": final_text[:300],
                    })

                self._tool_loop_count = 0
                event_bus.emit("task_completed", {"response": final_text[:300]})
                return final_text

    # ═══════════════════════════════════════════════════
    #  LLM CALL (with error handling, retry, failover)
    # ═══════════════════════════════════════════════════

    def _call_llm(self, system_prompt, model):
        """
        Make a streaming LLM call with full error handling.
        
        Handles:
        - Rate limits → failover to fallback provider → retry with backoff
        - Transient errors (5xx, timeout) → retry with backoff
        - Malformed tool calls (Groq/Llama) → parse and recover
        - Non-retryable errors (API key revoked) → fail fast
        
        Returns:
            (response, model_used) or (None, model) on unrecoverable failure
        """
        call_start = time.time()

        try:
            # ── Try streaming first (for real-time dashboard) ──
            with self.client.stream(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                tools=TARS_TOOLS,
                messages=self.conversation_history,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            event_bus.emit("thinking", {
                                "text": event.delta.text,
                                "model": model,
                            })
                response = stream.get_final_message()

            call_duration = time.time() - call_start
            self._emit_api_stats(model, response, call_duration)
            return response, model

        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__
            print(f"  ⚠️ Brain LLM error ({error_type}): {error_str[:200]}")

            # ── Non-retryable: API key / permission errors ──
            if "API key expired" in error_str or "PERMISSION_DENIED" in error_str:
                event_bus.emit("error", {"message": f"API key error: {error_str[:200]}"})
                self._emergency_notify(error_str)
                return None, model

            # ── Groq tool_use_failed: recover malformed call ──
            if "tool_use_failed" in error_str:
                recovered = _parse_failed_tool_call(e)
                if recovered:
                    print(f"  🔧 Brain: Recovered malformed tool call")
                    call_duration = time.time() - call_start
                    self._emit_api_stats(model, recovered, call_duration)
                    return recovered, model

            # ── Retryable errors: rate limit, 5xx, transient ──
            _retryable_markers = (
                "rate_limit", "rate limit", "429",
                "500", "502", "503", "529",
                "overloaded", "capacity", "resource_exhausted",
                "connection", "timeout", "timed out",
                "service unavailable", "internal server error",
                "tool_use_failed",
            )
            is_retryable = any(m in error_str.lower() for m in _retryable_markers)

            if is_retryable:
                is_rate_limit = any(m in error_str.lower() for m in (
                    "rate_limit", "rate limit", "429", "resource_exhausted"
                ))

                # ── Strategy 1: Provider failover (instant) ──
                if is_rate_limit and self._fallback_client and not self._using_fallback:
                    result, new_model = self._failover_to_fallback(system_prompt)
                    if result is not None:
                        return result, new_model

                # ── Strategy 2: Retry with backoff ──
                result = self._retry_with_backoff(
                    system_prompt, model, is_rate_limit, error_type
                )
                if result is not None:
                    return result, model

            else:
                # ── Non-retryable, non-key error: try non-streaming ──
                print(f"  🔧 Brain: Trying non-streaming fallback...")
                try:
                    response = self.client.create(
                        model=model,
                        max_tokens=8192,
                        system=system_prompt,
                        tools=TARS_TOOLS,
                        messages=self.conversation_history,
                    )
                    call_duration = time.time() - call_start
                    self._emit_api_stats(model, response, call_duration)
                    print(f"  🔧 Brain: Non-streaming fallback succeeded")
                    return response, model
                except Exception as e2:
                    event_bus.emit("error", {"message": f"LLM API error: {e2}"})
                    self._emergency_notify(str(e2))

            return None, model

    def _failover_to_fallback(self, system_prompt):
        """Switch to fallback LLM provider."""
        self._using_fallback = True
        self.client = self._fallback_client
        model = self._fallback_model
        self.brain_model = model
        print(f"  🔄 FAILOVER: Switching brain to {model}")
        event_bus.emit("status_change", {"status": "online", "label": f"FAILOVER → {model}"})

        try:
            response = self.client.create(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                tools=TARS_TOOLS,
                messages=self.conversation_history,
            )
            call_duration = time.time()
            self._emit_api_stats(model, response, 0)
            print(f"  ✅ Fallback provider succeeded: {model}")
            return response, model
        except Exception as fb_e:
            print(f"  ⚠️ Fallback also failed: {fb_e}")
            return None, model

    def _retry_with_backoff(self, system_prompt, model, is_rate_limit, error_type):
        """Retry LLM call with exponential backoff."""
        import random as _rand
        max_api_retries = 5

        for attempt in range(1, max_api_retries + 1):
            if is_rate_limit:
                base, cap = 3.0, 90.0
            else:
                base, cap = 1.0, 30.0
            delay = min(cap, base * (2 ** attempt)) * _rand.uniform(0.5, 1.0)

            print(f"  ⏳ Retry {attempt}/{max_api_retries} in {delay:.1f}s ({error_type})")
            event_bus.emit("status_change", {
                "status": "waiting",
                "label": f"RATE LIMITED — retry in {int(delay)}s"
            })
            time.sleep(delay)

            try:
                response = self.client.create(
                    model=model,
                    max_tokens=8192,
                    system=system_prompt,
                    tools=TARS_TOOLS,
                    messages=self.conversation_history,
                )
                self._emit_api_stats(model, response, 0)
                print(f"  ✅ Retry {attempt} succeeded")
                event_bus.emit("status_change", {"status": "online", "label": "THINKING"})
                return response
            except Exception as retry_e:
                error_str = str(retry_e)
                print(f"  ⚠️ Retry {attempt} failed: {error_str[:150]}")

                # Mid-retry failover
                if attempt == 2 and self._fallback_client and not self._using_fallback:
                    self._using_fallback = True
                    self.client = self._fallback_client
                    model = self._fallback_model
                    self.brain_model = model
                    print(f"  🔄 FAILOVER (mid-retry): Switching to {model}")

                if attempt == max_api_retries:
                    event_bus.emit("error", {
                        "message": f"LLM API error after {max_api_retries} retries: {retry_e}"
                    })
                    self._emergency_notify(str(retry_e))
                    return None

        return None

    # ═══════════════════════════════════════════════════
    #  TOOL EXECUTION
    # ═══════════════════════════════════════════════════

    def _execute_tool_calls(self, tool_calls, retry_count, intent, thread):
        """
        Execute a batch of tool calls from the LLM response.
        
        Supports parallel execution for independent tools.
        Logs decisions to the thread journal.
        Emits events for the dashboard.
        """
        tool_results = []

        # ── Parallel execution for independent tools ──
        if len(tool_calls) > 1 and all(tc.name in PARALLEL_SAFE for tc in tool_calls):
            print(f"  ⚡ Parallel execution: {', '.join(tc.name for tc in tool_calls)}")
            with ThreadPoolExecutor(max_workers=min(len(tool_calls), 4)) as pool:
                futures = {}
                start_times = {}
                for block in tool_calls:
                    self._emit_tool_start(block)
                    start_times[block.id] = time.time()
                    future = pool.submit(self.tool_executor.execute, block.name, block.input)
                    futures[future] = block

                for future in as_completed(futures):
                    block = futures[future]
                    exec_duration = time.time() - start_times[block.id]
                    result = future.result()
                    self._emit_tool_result(block, result, exec_duration)
                    result = self._enrich_failure(result, retry_count)
                    tool_results.append(self._format_tool_result(block, result))
        else:
            # ── Sequential execution ──
            for block in tool_calls:
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                self._emit_tool_start(block)

                # Phase 13: Log decision
                self.threads.log_decision(
                    action=tool_name,
                    reasoning=f"Called with: {str(tool_input)[:150]}",
                    confidence=intent.confidence * 100 if intent else 70,
                )

                # Execute
                print(f"  🔧 Executing: {tool_name}({tool_input})")
                exec_start = time.time()
                result = self.tool_executor.execute(tool_name, tool_input)
                exec_duration = time.time() - exec_start

                self._emit_tool_result(block, result, exec_duration)

                # Phase 13: Update decision outcome
                outcome = "success" if result.get("success") else "failed"
                self.threads.update_decision_outcome(outcome)

                # Enrich failures with retry guidance
                result = self._enrich_failure(result, retry_count)
                if result.get("error"):
                    retry_count += 1

                tool_results.append(self._format_tool_result(block, result))

        return tool_results

    def _emit_tool_start(self, block):
        """Emit tool call event for dashboard."""
        event_bus.emit("tool_called", {
            "tool_name": block.name,
            "tool_input": block.input,
        })

    def _emit_tool_result(self, block, result, duration):
        """Emit tool result event for dashboard."""
        event_bus.emit("tool_result", {
            "tool_name": block.name,
            "content": result.get("content", str(result))[:500],
            "success": result.get("success", not result.get("error")),
            "duration": duration,
        })
        # iMessage-specific events
        if block.name == "send_imessage":
            event_bus.emit("imessage_sent", {"message": block.input.get("message", "")})
        elif block.name == "wait_for_reply" and result.get("success"):
            event_bus.emit("imessage_received", {"message": result.get("content", "")})

    def _enrich_failure(self, result, retry_count):
        """Add escalation guidance to failed results."""
        if result.get("error"):
            if retry_count >= self.max_retries:
                result["content"] = (
                    result.get("content", "") +
                    f"\n\n⚠️ This has failed {retry_count} times. "
                    "Consider asking Abdullah for help via send_imessage — but "
                    "include WHAT you tried and WHY each attempt failed."
                )
        return result

    @staticmethod
    def _format_tool_result(block, result):
        """Format a tool result for the LLM conversation."""
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result.get("content", str(result)),
        }

    def _emit_api_stats(self, model, response, duration):
        """Emit API call stats for dashboard."""
        if response and hasattr(response, 'usage'):
            event_bus.emit("api_call", {
                "model": model,
                "tokens_in": response.usage.input_tokens,
                "tokens_out": response.usage.output_tokens,
                "duration": duration,
            })

    # ═══════════════════════════════════════════════════
    #  SYSTEM PROMPT BUILDER (Phase 5)
    # ═══════════════════════════════════════════════════

    def _build_system_prompt(self, intent, thread_context="", memory_context=""):
        """
        Build the system prompt using the modular prompt system.
        
        Injects:
        - Only relevant domain knowledge (based on intent)
        - Thread context (conversation continuity)
        - Auto-recalled memory
        - Compacted old context
        - Session performance summary
        """
        # Get session summary from self-improvement engine
        session_summary = ""
        if hasattr(self.tool_executor, 'self_improve'):
            session_summary = self.tool_executor.self_improve.get_session_summary()

        # Get memory context from memory manager
        full_memory_context = self.memory.get_context_summary()
        if memory_context:
            full_memory_context = f"{full_memory_context}\n\n## Auto-recalled for this message\n{memory_context}"

        return build_system_prompt(
            humor_level=self.config["agent"]["humor_level"],
            cwd=os.getcwd(),
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            active_project=self.memory.get_active_project(),
            memory_context=full_memory_context,
            max_deploys=8,
            intent_type=intent.type if intent else "",
            intent_detail=intent.detail if intent else "",
            domain_hints=intent.domain_hints if intent else [],
            thread_context=thread_context,
            compacted_summary=self._compacted_summary,
            session_summary=session_summary,
        )

    # ═══════════════════════════════════════════════════
    #  AUTO MEMORY RECALL (Phase 9)
    # ═══════════════════════════════════════════════════

    def _auto_recall(self, text: str) -> str:
        """
        Automatically recall relevant memories before thinking.
        
        Phase 9: Contextual Memory Injection.
        Instead of the Brain having to explicitly call recall_memory,
        we automatically search memory based on the message content
        and inject relevant results into the prompt.
        """
        try:
            # Extract key terms for memory search
            # Use first 100 chars as search query
            query = text[:100]
            result = self.memory.recall(query)
            
            if result.get("success") and result.get("content"):
                content = result["content"]
                # Only inject if we found something meaningful
                if len(content) > 20 and content != "No memories found.":
                    return content[:800]  # Cap at 800 chars
        except Exception:
            pass
        
        return ""

    # ═══════════════════════════════════════════════════
    #  CONTEXT MANAGEMENT
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _estimate_tokens(messages):
        """Estimate token count (~4 chars/token heuristic)."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        total_chars += len(str(item.get("content", "")))
                    elif hasattr(item, "text"):
                        total_chars += len(item.text or "")
                    elif hasattr(item, "input"):
                        total_chars += len(str(item.input or ""))
        return total_chars // 4

    def _compact_history(self):
        """
        Token-aware compaction: compress old conversation history when
        estimated token usage exceeds threshold.
        
        Keeps last 20 messages intact, summarizes the rest.
        """
        est_tokens = self._estimate_tokens(self.conversation_history)
        msg_count = len(self.conversation_history)

        if est_tokens < self.compaction_token_threshold and msg_count < self.max_history_messages:
            return

        keep_count = 20
        old_messages = self.conversation_history[:-keep_count]
        recent = self.conversation_history[-keep_count:]

        # Build compact summary
        summary_parts = []
        for msg in old_messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user" and isinstance(content, str):
                summary_parts.append(f"User: {content[:200]}")
            elif role == "user" and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result_preview = str(item.get("content", ""))[:150]
                        summary_parts.append(f"Tool result: {result_preview}")
            elif role == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "type"):
                            if block.type == "text" and block.text:
                                summary_parts.append(f"TARS: {block.text[:200]}")
                            elif block.type == "tool_use":
                                args_preview = str(block.input)[:100]
                                summary_parts.append(f"TARS called: {block.name}({args_preview})")
                elif isinstance(content, str):
                    summary_parts.append(f"TARS: {content[:200]}")

        self._compacted_summary = "\n".join(summary_parts[-30:])
        if len(self._compacted_summary) > 4000:
            head = self._compacted_summary[:500]
            tail = self._compacted_summary[-(4000 - 500 - 20):]
            self._compacted_summary = head + "\n... (compacted) ...\n" + tail

        self.conversation_history = recent
        print(f"  📦 Compacted: {len(old_messages)} msgs (~{est_tokens} tokens) → summary, keeping {len(recent)}")

    def _force_compact(self):
        """Force-compact all history into summary. Used on conversation timeout."""
        if not self.conversation_history:
            return

        summary_parts = []
        for msg in self.conversation_history:
            role = msg["role"]
            content = msg["content"]

            if role == "user" and isinstance(content, str):
                summary_parts.append(f"User: {content[:200]}")
            elif role == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "type"):
                            if block.type == "text" and block.text:
                                summary_parts.append(f"TARS: {block.text[:200]}")
                            elif block.type == "tool_use":
                                args_preview = str(block.input)[:100]
                                summary_parts.append(f"TARS called: {block.name}({args_preview})")
                elif isinstance(content, str):
                    summary_parts.append(f"TARS: {content[:200]}")

        self._compacted_summary = "\n".join(summary_parts[-40:])
        if len(self._compacted_summary) > 4000:
            head = self._compacted_summary[:500]
            tail = self._compacted_summary[-(4000 - 500 - 20):]
            self._compacted_summary = head + "\n... (compacted) ...\n" + tail

        self.conversation_history = []
        print(f"  📦 Force-compacted conversation ({len(summary_parts)} entries)")

    # ═══════════════════════════════════════════════════
    #  EMERGENCY & RECOVERY
    # ═══════════════════════════════════════════════════

    def _emergency_notify(self, error_str):
        """Last-resort: try to send iMessage when the brain crashes."""
        try:
            partial = ""
            for msg in reversed(self.conversation_history):
                content = msg.get("content", "")
                if msg["role"] == "user" and isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            c = str(item.get("content", ""))
                            if len(c) > 50 and not c.startswith("ERROR") and "✅" in c:
                                partial = c[:500]
                                break
                if partial:
                    break

            if partial:
                notify_msg = f"⚠️ Hit a technical snag, but here's what I found so far:\n\n{partial}"
            elif "leaked" in error_str.lower() or "permission_denied" in error_str.lower():
                notify_msg = "❌ My API key was revoked. Need a new one in config.yaml."
            elif "rate limit" in error_str.lower() or "429" in error_str:
                notify_msg = "⏳ Rate limited. Try again in about a minute."
            else:
                notify_msg = "⚠️ Ran into a technical issue. Try sending your request again."

            self.tool_executor.execute("send_imessage", {"message": notify_msg})
        except Exception:
            pass

    def reset_conversation(self, hard=False):
        """
        Reset conversation state.
        
        soft (default): Compact history — TARS still remembers key context.
        hard: Full wipe — for debugging or explicit user request.
        """
        if hard:
            self.conversation_history = []
            self._compacted_summary = ""
            self._message_count = 0
        else:
            self._force_compact()
        event_bus.emit("status_change", {"status": "online", "label": "READY"})

    # ═══════════════════════════════════════════════════
    #  PUBLIC ACCESSORS (for tars.py, dashboard, etc.)
    # ═══════════════════════════════════════════════════

    def get_thread_stats(self) -> dict:
        """Get thread statistics for the dashboard."""
        return self.threads.get_thread_stats()

    @property
    def active_thread(self):
        """Get the active thread (for external access)."""
        return self.threads.active_thread
