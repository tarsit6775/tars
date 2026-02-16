"""
TARS Brain v5: Autonomous Mind with MetaCognition

Phases 1-14: v4 foundations (intent, threads, memory, tools)
Phases 15-34: v5 enhancements (metacognition, decision cache,
semantic compaction, multi-query recall, task decomposition,
confidence gating, dynamic tool pruning, error patterns,
cross-session continuity, structured reflection, reasoning trace)
"""

import os
import re
import time
import json
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from brain.llm_client import LLMClient, _parse_failed_tool_call
from brain.prompts import build_system_prompt, RECOVERY_PROMPT
from brain.tools import TARS_TOOLS, get_tools_for_intent
from brain.intent import IntentClassifier, Intent
from brain.threads import ThreadManager
from brain.metacognition import MetaCognitionMonitor
from brain.decision_cache import DecisionCache
from utils.event_bus import event_bus
from memory.error_tracker import error_tracker

logger = logging.getLogger("TARS")

# Tools that depend on previous results — must run sequentially
DEPENDENT_TOOLS = {"verify_result", "send_imessage", "wait_for_reply", "checkpoint"}
# Tools safe to run in parallel
PARALLEL_SAFE = {"think", "scan_environment", "recall_memory", "run_quick_command",
                 "quick_read_file", "web_search", "save_memory"}


class TARSBrain:
    """Brain v5 — thinking engine with metacognition, decision cache,
    semantic compaction, error patterns, cross-session continuity."""

    def __init__(self, config, tool_executor, memory_manager):
        self.config = config
        brain_cfg = config.get("brain_llm")
        llm_cfg = config["llm"]

        if brain_cfg and brain_cfg.get("api_key"):
            self.client = LLMClient(
                provider=brain_cfg["provider"],
                api_key=brain_cfg["api_key"],
                base_url=brain_cfg.get("base_url"),
            )
            self.brain_model = brain_cfg["model"]
            logger.info(f"  🧠 Brain: {brain_cfg['provider']}/{self.brain_model}")
        else:
            self.client = LLMClient(
                provider=llm_cfg["provider"],
                api_key=llm_cfg["api_key"],
                base_url=llm_cfg.get("base_url"),
            )
            self.brain_model = llm_cfg["heavy_model"]
            logger.info(f"  🧠 Brain: {llm_cfg['provider']}/{self.brain_model} (single-provider)")

        # Phase 31: Graceful degradation chain
        self._primary_client = self.client
        self._primary_model = self.brain_model
        self._fallback_client = None
        self._fallback_model = None
        self._using_fallback = False
        self._degradation_level = 0  # 0=primary, 1=fallback, 2+=emergency

        fb_cfg = config.get("fallback_llm")
        if fb_cfg and fb_cfg.get("api_key"):
            self._fallback_client = LLMClient(
                provider=fb_cfg["provider"],
                api_key=fb_cfg["api_key"],
                base_url=fb_cfg.get("base_url"),
            )
            self._fallback_model = fb_cfg["model"]
            logger.info(f"  🔄 Fallback: {fb_cfg['provider']}/{self._fallback_model}")

        self.heavy_model = llm_cfg.get("heavy_model", llm_cfg.get("model", ""))
        self.fast_model = llm_cfg.get("fast_model", self.heavy_model)
        self.tool_executor = tool_executor
        self.memory = memory_manager
        self.max_retries = config["safety"]["max_retries"]

        self.intent_classifier = IntentClassifier()

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        thread_dir = os.path.join(base_dir, "memory", "threads")
        self.threads = ThreadManager(persistence_dir=thread_dir)

        # Phase 34: MetaCognition Monitor
        self.metacognition = MetaCognitionMonitor()

        # Phase 26: Decision Cache
        self.decision_cache = DecisionCache(base_dir=base_dir)

        # Thread safety: parallel tasks share this brain instance.
        # The lock serializes process() calls so conversation_history
        # and metacognition state don't get corrupted.
        self._lock = threading.Lock()

        self.conversation_history = []
        self.max_history_messages = 80
        self.compaction_token_threshold = 80000
        self._compacted_summary = ""
        self.max_tool_loops = 50
        self._tool_loop_count = 0
        self._metacog_loop_count = 0  # Consecutive metacognition loop detections
        self._brain_sent_imessage = False  # Track if brain already notified user

        # Phase 28: Reasoning Trace
        self._reasoning_trace = []

        self._last_message_time = 0
        self._conversation_timeout = 600
        self._message_count = 0

        # Phase 33: Cross-Session Continuity
        self._session_state_path = os.path.join(base_dir, "memory", "session_state.json")
        self._restore_session_state()

    # ═══════════════════════════════════════════════════
    #  MAIN ENTRY POINT — process()
    # ═══════════════════════════════════════════════════

    def process(self, batch_or_text) -> str:
        """
        Main entry point — Brain v5.

        Flow:
        1. Normalize input
        2. Classify intent
        3. Route to thread
        4. Decision cache lookup (Phase 26)
        5. Multi-query memory recall (Phase 19)
        6. Task decomposition (Phase 17)
        7. Dynamic tool pruning (Phase 22)
        8. Build thread context
        9. Reset metacognition (Phase 34)
        10. Think via LLM loop
        11. Structured reflection (Phase 27)
        12. Record response in thread
        13. Proactive anticipation (Phase 29)
        14. Save session state (Phase 33)
        """
        # Thread safety: serialize brain access for parallel tasks.
        # Without this, two tasks could corrupt conversation_history,
        # metacognition state, and reasoning trace simultaneously.
        with self._lock:
            return self._process_inner(batch_or_text)

    def _process_inner(self, batch_or_text) -> str:
        """Inner process logic — called under self._lock."""
        # ── Step 1: Normalize input ──
        from brain.message_parser import MessageBatch
        if isinstance(batch_or_text, MessageBatch):
            text = batch_or_text.merged_text
            batch_type = batch_or_text.batch_type
        else:
            text = str(batch_or_text)
            batch_type = "single"

        # ── Step 2: Classify intent ──
        intent = self.intent_classifier.classify(
            text,
            has_active_thread=self.threads.has_active_thread,
            batch_type=batch_type,
        )
        logger.info(f"  🎯 Intent: {intent}")

        # ── Step 3: Route to thread ──
        thread = self.threads.route_message(text, intent.type, intent.confidence)
        logger.info(f"  📎 Thread: {thread.topic} ({thread.id})")

        # ── Step 4: Decision cache lookup (Phase 26) ──
        cached = None
        domain_hints = intent.domain_hints if intent and hasattr(intent, 'domain_hints') else []
        if domain_hints:
            cached = self.decision_cache.lookup(intent.type, domain_hints, text)
            if cached:
                logger.info(f"  💾 Decision cache hit (reliability {cached.reliability:.0f}%)")
                event_bus.emit("decision_cache_hit", {"task": text[:100], "reliability": cached.reliability})

        # ── Step 5: Multi-query memory recall (Phase 19) ──
        memory_context = ""
        if intent.needs_memory:
            memory_context = self._auto_recall_multi(text, intent)

        # ── Step 6: Task decomposition (Phase 17) ──
        subtask_plan = ""
        if intent.type == "TASK" and len(text) > 60:
            subtask_plan = self._decompose_task(text, intent)

        # ── Step 7: Dynamic tool pruning (Phase 22) ──
        active_tools = get_tools_for_intent(intent)
        if len(active_tools) < len(TARS_TOOLS):
            logger.info(f"  🔧 Pruned tools: {len(TARS_TOOLS)} → {len(active_tools)}")

        # ── Step 8: Build thread context ──
        thread_context = self.threads.get_context_for_brain()

        # ── Step 9: Reset metacognition (Phase 34) ──
        self.metacognition.reset()
        self._metacog_loop_count = 0
        self._brain_sent_imessage = False
        self._reasoning_trace = []

        # ── Step 10: Think (LLM loop) ──
        # Inject error warning if we have patterns for this kind of task
        error_warning = self._get_error_warning(text)

        response = self._think_loop(
            user_message=text,
            intent=intent,
            thread=thread,
            memory_context=memory_context,
            thread_context=thread_context,
            subtask_plan=subtask_plan,
            tools=active_tools,
            error_warning=error_warning,
            cached_decision=cached,
        )

        # ── Step 11: Structured reflection (Phase 27) ──
        if self._tool_loop_count > 3:
            self._structured_reflection(text, response, intent)

        # ── Step 12: Record response in thread ──
        self.threads.record_response(response[:500])

        # ── Step 13: Record brain-level task outcome for self-improvement ──
        self._record_brain_outcome(text, response, intent)

        # ── Step 14: Proactive anticipation (Phase 29) ──
        self._proactive_check(text, response, intent)

        # ── Step 15: Save session state (Phase 33) ──
        self._save_session_state()

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
                    memory_context="", thread_context="",
                    subtask_plan="", tools=None, error_warning="",
                    cached_decision=None) -> str:
        """
        Core LLM thinking loop — v5 with metacognition + reasoning trace.
        """
        if tools is None:
            tools = TARS_TOOLS

        # ── Restore primary provider if we failed over previously ──
        if self._using_fallback and self._primary_client:
            self._using_fallback = False
            self.client = self._primary_client
            self.brain_model = self._primary_model
            self._degradation_level = 0
            logger.info(f"  🔄 Restored primary brain: {self._primary_model}")

        model = self.brain_model
        event_bus.emit("thinking_start", {"model": model})

        # ── Conversation continuity ──
        now = time.time()
        time_since_last = now - self._last_message_time if self._last_message_time else float("inf")
        self._last_message_time = now
        self._message_count += 1

        if time_since_last > self._conversation_timeout and self.conversation_history:
            logger.info(f"  💭 Conversation gap: {int(time_since_last)}s — soft-resetting context")
            self._force_compact()

        # ── Inject cached decision hint ──
        hint = ""
        if cached_decision:
            hint = f"\n\n[Decision cache: Previously succeeded with strategy: {cached_decision.strategy}. Tools: {', '.join(cached_decision.tool_sequence[:5])}]"
        if error_warning:
            hint += f"\n\n[Error pattern warning: {error_warning}]"

        # ── Add user message to LLM history ──
        self.conversation_history.append({
            "role": "user",
            "content": user_message + hint,
        })

        # ── Compact if needed ──
        self._compact_history()

        # ── Build system prompt ──
        system_prompt = self._build_system_prompt(
            intent, thread_context, memory_context,
            subtask_plan=subtask_plan,
        )

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

            # Phase 34: MetaCognition check every iteration
            metacog = self.metacognition.analyze()
            injection = self.metacognition.get_injection()
            if injection:
                self.conversation_history.append({
                    "role": "user",
                    "content": injection,
                })
                self._reasoning_trace.append({
                    "step": self._tool_loop_count,
                    "type": "metacognition",
                    "alert": metacog.recommendation or "",
                })
                event_bus.emit("metacognition_alert", {
                    "is_looping": metacog.is_looping,
                    "is_stalled": metacog.is_stalled,
                    "recommendation": metacog.recommendation,
                })

                # Force-break if metacognition detects sustained looping
                if metacog.is_looping:
                    self._metacog_loop_count += 1
                    # send_imessage loops are critical — break immediately
                    if metacog.loop_tool == "send_imessage":
                        logger.warning(f"  🛑 Force-breaking: send_imessage loop detected ({metacog.loop_count} calls)")
                        event_bus.emit("error", {"message": "Force-break: send_imessage loop"})
                        return "⚠️ I detected I was stuck in a messaging loop and stopped. The task may be partially complete."
                    # Other tools: allow 3 consecutive metacognition warnings before force-break
                    if self._metacog_loop_count >= 3:
                        logger.warning(f"  🛑 Force-breaking: metacognition detected {self._metacog_loop_count} consecutive loops")
                        event_bus.emit("error", {"message": "Force-break: sustained tool loop detected"})
                        return "⚠️ I detected I was stuck in a loop and stopped. The task may be partially complete."
                else:
                    self._metacog_loop_count = 0

            # ── Call LLM (with error handling + failover) ──
            response, model = self._call_llm(system_prompt, model, tools=tools)
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

                # Phase 28: Log reasoning trace
                self._reasoning_trace.append({
                    "step": self._tool_loop_count,
                    "type": "tool_calls",
                    "tools": [tc.name for tc in tool_calls],
                })

                tool_results = self._execute_tool_calls(tool_calls, retry_count, intent, thread)

                # Add tool results to conversation
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                # Compact if growing
                self._compact_history()

                # Continue — LLM processes tool results next
                event_bus.emit("thinking_start", {"model": model})
                continue

            else:
                # ── Final text response ──
                final_text = ""
                for block in assistant_content:
                    if hasattr(block, "text"):
                        final_text += block.text

                # ── Gemini empty-response recovery ──
                # If the LLM returned an empty/very short response after tool calls,
                # it likely "gave up" mid-task. Re-prompt it to continue.
                if self._tool_loop_count > 1 and len(final_text.strip()) < 10:
                    if retry_count < 2:
                        retry_count += 1
                        logger.warning(f"  ⚠️ Empty response after {self._tool_loop_count} tool loops — re-prompting LLM (retry {retry_count}/2)")
                        self.conversation_history.append({
                            "role": "user",
                            "content": (
                                "You returned an empty response but the task is not complete yet. "
                                "Review what you've done so far and continue with the remaining steps. "
                                "Use the appropriate tools to finish the task."
                            ),
                        })
                        event_bus.emit("thinking_start", {"model": model})
                        continue

                # Phase 28: Log final reasoning
                self._reasoning_trace.append({
                    "step": self._tool_loop_count,
                    "type": "final_response",
                    "length": len(final_text),
                })

                if self._tool_loop_count > 3:
                    event_bus.emit("self_reflection", {
                        "loops": self._tool_loop_count,
                        "response": final_text[:300],
                    })

                event_bus.emit("task_completed", {"response": final_text[:300]})
                return final_text

    # ═══════════════════════════════════════════════════
    #  LLM CALL (with error handling, retry, failover)
    # ═══════════════════════════════════════════════════

    def _call_llm(self, system_prompt, model, tools=None):
        """
        Make a streaming LLM call with full error handling.
        
        Handles:
        - Rate limits → failover to fallback provider → retry with backoff
        - Transient errors (5xx, timeout) → retry with backoff
        - Malformed tool calls (Groq/Llama) → parse and recover
        - Non-retryable errors (API key revoked) → fail fast
        - Phase 24: Error pattern recording
        - Phase 31: Degradation level tracking
        
        Returns:
            (response, model_used) or (None, model) on unrecoverable failure
        """
        if tools is None:
            tools = TARS_TOOLS
        call_start = time.time()

        try:
            # ── Debug: log message count and last message ──
            hist_len = len(self.conversation_history)
            if hist_len > 0:
                last_msg = self.conversation_history[-1]
                last_role = last_msg.get("role", "?")
                last_content = last_msg.get("content", "")
                if isinstance(last_content, str):
                    content_preview = last_content[:100]
                elif isinstance(last_content, list):
                    content_preview = f"[{len(last_content)} blocks]"
                else:
                    content_preview = str(type(last_content))
                logger.debug(f"  📡 LLM call: {hist_len} messages, last={last_role}: {content_preview}")

            # ── Try streaming first (for real-time dashboard) ──
            with self.client.stream(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                tools=tools,
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
            logger.warning(f"  ⚠️ Brain LLM error ({error_type}): {error_str[:200]}")

            # ── API key / permission errors → try fallback before giving up ──
            if "API key expired" in error_str or "PERMISSION_DENIED" in error_str or "leaked" in error_str.lower():
                event_bus.emit("error", {"message": f"API key error: {error_str[:200]}"})
                # Try fallback provider before giving up
                if self._fallback_client and not self._using_fallback:
                    logger.warning(f"  🔄 Primary API key revoked — failing over to fallback provider")
                    result, new_model = self._failover_to_fallback(system_prompt, tools=tools)
                    if result is not None:
                        return result, new_model
                self._emergency_notify(error_str)
                return None, model

            # ── Groq tool_use_failed: recover malformed call ──
            if "tool_use_failed" in error_str:
                recovered = _parse_failed_tool_call(e)
                if recovered:
                    logger.info(f"  🔧 Brain: Recovered malformed tool call")
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

                # Phase 24: Record error pattern
                self._record_error_pattern("llm_call", error_str, model)

                # ── Strategy 1: Provider failover (instant) ──
                if is_rate_limit and self._fallback_client and not self._using_fallback:
                    result, new_model = self._failover_to_fallback(system_prompt, tools=tools)
                    if result is not None:
                        return result, new_model

                # ── Strategy 2: Retry with backoff ──
                result = self._retry_with_backoff(
                    system_prompt, model, is_rate_limit, error_type, tools=tools
                )
                if result is not None:
                    return result, model

            else:
                # ── Non-retryable, non-key error: try non-streaming ──
                logger.info(f"  🔧 Brain: Trying non-streaming fallback...")
                try:
                    response = self.client.create(
                        model=model,
                        max_tokens=8192,
                        system=system_prompt,
                        tools=tools,
                        messages=self.conversation_history,
                    )
                    call_duration = time.time() - call_start
                    self._emit_api_stats(model, response, call_duration)
                    logger.info(f"  🔧 Brain: Non-streaming fallback succeeded")
                    return response, model
                except Exception as e2:
                    self._record_error_pattern("llm_call", str(e2), model)
                    event_bus.emit("error", {"message": f"LLM API error: {e2}"})
                    self._emergency_notify(str(e2))

            return None, model

    def _failover_to_fallback(self, system_prompt, tools=None):
        """Switch to fallback LLM provider."""
        if tools is None:
            tools = TARS_TOOLS
        self._using_fallback = True
        self._degradation_level = 1
        self.client = self._fallback_client
        model = self._fallback_model
        self.brain_model = model
        logger.warning(f"  🔄 FAILOVER: Switching brain to {model} (degradation={self._degradation_level})")
        event_bus.emit("status_change", {"status": "online", "label": f"FAILOVER → {model}"})

        try:
            response = self.client.create(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                tools=tools,
                messages=self.conversation_history,
            )
            self._emit_api_stats(model, response, 0)
            logger.info(f"  ✅ Fallback provider succeeded: {model}")
            return response, model
        except Exception as fb_e:
            self._degradation_level = 2
            logger.warning(f"  ⚠️ Fallback also failed: {fb_e}")
            return None, model

    def _retry_with_backoff(self, system_prompt, model, is_rate_limit, error_type, tools=None):
        """Retry LLM call with exponential backoff."""
        import random as _rand
        if tools is None:
            tools = TARS_TOOLS
        max_api_retries = 5

        for attempt in range(1, max_api_retries + 1):
            if is_rate_limit:
                base, cap = 3.0, 90.0
            else:
                base, cap = 1.0, 30.0
            delay = min(cap, base * (2 ** attempt)) * _rand.uniform(0.5, 1.0)

            logger.info(f"  ⏳ Retry {attempt}/{max_api_retries} in {delay:.1f}s ({error_type})")
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
                    tools=tools,
                    messages=self.conversation_history,
                )
                self._emit_api_stats(model, response, 0)
                logger.info(f"  ✅ Retry {attempt} succeeded")
                event_bus.emit("status_change", {"status": "online", "label": "THINKING"})
                return response
            except Exception as retry_e:
                error_str = str(retry_e)
                logger.warning(f"  ⚠️ Retry {attempt} failed: {error_str[:150]}")

                # Mid-retry failover
                if attempt == 2 and self._fallback_client and not self._using_fallback:
                    self._using_fallback = True
                    self._degradation_level = 1
                    self.client = self._fallback_client
                    model = self._fallback_model
                    self.brain_model = model
                    logger.warning(f"  🔄 FAILOVER (mid-retry): Switching to {model}")

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
        Execute a batch of tool calls — v5 with metacognition + error patterns.

        Supports parallel execution for independent tools.
        Records to metacognition, decision cache, and reasoning trace.
        """
        tool_results = []

        # ── Parallel execution for independent tools ──
        if len(tool_calls) > 1 and all(tc.name in PARALLEL_SAFE for tc in tool_calls):
            logger.debug(f"  ⚡ Parallel execution: {', '.join(tc.name for tc in tool_calls)}")
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

                    # Phase 34: Record in metacognition
                    self.metacognition.record_tool_call(
                        block.name, block.input,
                        result.get("success", False), exec_duration
                    )

                    result = self._enrich_failure(result, retry_count)
                    tool_results.append(self._format_tool_result(block, result))
        else:
            # ── Sequential execution ──
            for block in tool_calls:
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                self._emit_tool_start(block)

                # Log decision in thread
                self.threads.log_decision(
                    action=tool_name,
                    reasoning=f"Called with: {str(tool_input)[:150]}",
                    confidence=intent.confidence * 100 if intent else 70,
                )

                # Execute
                logger.info(f"  🔧 Executing: {tool_name}({tool_input})")
                exec_start = time.time()
                result = self.tool_executor.execute(tool_name, tool_input)
                exec_duration = time.time() - exec_start

                self._emit_tool_result(block, result, exec_duration)

                # Phase 34: Record in metacognition
                success = result.get("success", not result.get("error", False))
                self.metacognition.record_tool_call(tool_name, tool_input, success, exec_duration)

                # Track if brain sent an iMessage (so _run_task doesn't double-send)
                if tool_name == "send_imessage" and success:
                    self._brain_sent_imessage = True

                # Phase 24: Record error pattern on failure
                if not success:
                    error_content = result.get("content", "unknown error")
                    self._record_error_pattern(
                        tool_name,
                        error_content,
                        str(tool_input)[:200],
                    )
                    # Feed to self-healing engine for pattern detection
                    self._record_self_heal_failure(
                        tool_name, error_content, str(tool_input)[:200],
                    )
                    # Phase 35: Error tracker — check for known auto-fixes
                    fix_info = error_tracker.record_error(
                        error=error_content,
                        context=tool_name,
                        tool=tool_name,
                        details=str(tool_input)[:200],
                    )
                    if fix_info and fix_info.get("has_fix"):
                        logger.info(f"  🩹 Known fix available: {fix_info['fix'][:80]}")
                        event_bus.emit("auto_fix_available", {
                            "tool": tool_name,
                            "fix": fix_info["fix"][:200],
                            "confidence": fix_info.get("confidence", 0),
                            "times_applied": fix_info.get("times_applied", 0),
                        })

                # Phase 26: Record in decision cache on success
                if success and tool_name not in ("think", "scan_environment"):
                    domain = intent.domain_hints[0] if (intent and intent.domain_hints) else "general"
                    self.decision_cache.record_success(
                        intent_type=intent.type if intent else "TASK",
                        domain=domain,
                        pattern=tool_name,
                        tool_sequence=[tool_name],
                        strategy=f"{tool_name} with {str(tool_input)[:100]}",
                    )

                # Update decision outcome
                outcome = "success" if success else "failed"
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
            "tool_name": block.name,
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

    def _build_system_prompt(self, intent, thread_context="", memory_context="",
                             subtask_plan=""):
        """
        Build the system prompt — v5 with subtask plan + metacog injection.
        """
        # Get session summary from self-improvement engine
        session_summary = ""
        if hasattr(self.tool_executor, 'self_improve'):
            session_summary = self.tool_executor.self_improve.get_session_summary()

        # Get memory context from memory manager
        full_memory_context = self.memory.get_context_summary()
        if memory_context:
            full_memory_context = f"{full_memory_context}\n\n## Auto-recalled for this message\n{memory_context}"

        # Phase 34: Metacognition context
        metacog_context = self.metacognition.get_injection() or ""

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
            subtask_plan=subtask_plan,
            metacog_context=metacog_context,
        )

    # ═══════════════════════════════════════════════════
    #  AUTO MEMORY RECALL (Phase 9)
    # ═══════════════════════════════════════════════════

    def _auto_recall(self, text: str) -> str:
        """Legacy single-query recall — delegates to multi-query version."""
        return self._auto_recall_multi(text)

    def _auto_recall_multi(self, text: str, intent=None) -> str:
        """
        Phase 19: Multi-query memory recall.

        Instead of a single search, generates 2-3 queries from different
        angles to catch more relevant memories.
        """
        queries = [text[:100]]

        # Extract potential entity names (capitalized words)
        words = text.split()
        entities = [w for w in words if w[0:1].isupper() and len(w) > 2]
        if entities:
            queries.append(" ".join(entities[:5]))

        # Extract action + object pattern
        action_words = {"find", "search", "create", "build", "fix", "update",
                        "check", "get", "send", "write", "read", "install",
                        "deploy", "run", "test", "debug", "setup", "configure"}
        for w in words:
            if w.lower() in action_words:
                idx = words.index(w)
                context_slice = " ".join(words[max(0, idx-1):min(len(words), idx+4)])
                if context_slice not in queries:
                    queries.append(context_slice)
                break

        # Deduplicate and search
        seen = set()
        results = []
        for q in queries:
            if q in seen or len(q) < 5:
                continue
            seen.add(q)
            try:
                result = self.memory.recall(q)
                if result.get("success") and result.get("content"):
                    content = result["content"]
                    if len(content) > 20 and content != "No memories found.":
                        results.append(content)
            except Exception:
                pass

        if not results:
            return ""

        # Merge and cap
        merged = "\n---\n".join(results)
        return merged[:1200]

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
        logger.info(f"  📦 Compacted: {len(old_messages)} msgs (~{est_tokens} tokens) → summary, keeping {len(recent)}")

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
        logger.info(f"  📦 Force-compacted conversation ({len(summary_parts)} entries)")

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
            self._reasoning_trace = []
            self.metacognition.reset()
        else:
            self._force_compact()
        event_bus.emit("status_change", {"status": "online", "label": "READY"})

    # ═══════════════════════════════════════════════════
    #  PUBLIC ACCESSORS (for tars.py, dashboard, etc.)
    # ═══════════════════════════════════════════════════

    def get_thread_stats(self) -> dict:
        """Get thread statistics for the dashboard."""
        stats = self.threads.get_thread_stats()
        metacog_stats = self.metacognition.get_stats()
        stats["metacognition"] = {
            "total_tool_calls": metacog_stats.get("total_steps", 0),
            "total_failures": metacog_stats.get("consecutive_failures", 0),
            "is_looping": metacog_stats.get("is_looping", False),
            "is_stalled": metacog_stats.get("is_stalled", False),
            "confidence_trend": metacog_stats.get("confidence_trend", "stable"),
        }
        stats["decision_cache_size"] = len(self.decision_cache._entries)
        stats["error_patterns"] = error_tracker.get_stats().get("unique_errors", 0)
        stats["degradation_level"] = self._degradation_level
        return stats

    @property
    def active_thread(self):
        """Get the active thread (for external access)."""
        return self.threads.active_thread

    def get_reasoning_trace(self) -> list:
        """Get the reasoning trace for the current/last task."""
        return list(self._reasoning_trace)

    def get_error_pattern_stats(self) -> dict:
        """Get summary of recorded error patterns via error_tracker."""
        stats = error_tracker.get_stats()
        top_errors = error_tracker.get_top_errors(20)
        return {
            "total_patterns": stats.get("unique_errors", 0),
            "fix_rate": stats.get("fix_rate", "0%"),
            "patterns": {
                err.get("context", "unknown"): {
                    "count": err.get("count", 0),
                    "last_seen": err.get("last_seen", ""),
                    "context": err.get("context", "")[:100],
                    "has_fix": err.get("has_fix", False),
                }
                for err in top_errors
            },
        }

    # ═══════════════════════════════════════════════════
    #  TASK DECOMPOSITION (Phase 17)
    # ═══════════════════════════════════════════════════

    def _decompose_task(self, text, intent):
        """
        Break a complex task into subtasks for the thread journal.
        
        Uses keyword heuristics (no LLM call) to identify sub-steps.
        Returns a subtask plan string for prompt injection.
        """
        subtasks = []

        # Detect multi-step indicators
        lines = text.split("\n")
        numbered = [l.strip() for l in lines if re.match(r"^\d+[\.\)]\s", l.strip())]
        if numbered:
            subtasks = numbered[:8]
        else:
            # Detect "and" / "then" / "also" splits
            parts = re.split(r"\b(?:then|and then|after that|also|next)\b", text, flags=re.IGNORECASE)
            if len(parts) > 1:
                subtasks = [p.strip() for p in parts if len(p.strip()) > 10][:6]

        if not subtasks:
            return ""

        # Record subtasks in thread
        subtask_dicts = [
            {"description": st[:200], "agent": "auto", "depends_on": []}
            for st in subtasks
        ]
        self.threads.add_subtasks(subtask_dicts)

        plan = "## Task Breakdown\n"
        for i, st in enumerate(subtasks, 1):
            plan += f"{i}. {st[:200]}\n"
        plan += "\nWork through these steps in order. Report progress after each.\n"

        event_bus.emit("task_decomposed", {"subtasks": subtasks})
        return plan

    # ═══════════════════════════════════════════════════
    #  STRUCTURED REFLECTION (Phase 27)
    # ═══════════════════════════════════════════════════

    def _structured_reflection(self, task, response, intent):
        """
        Post-task structured reflection — learns from what just happened.
        """
        try:
            metacog_stats = self.metacognition.get_stats()
            total_steps = metacog_stats.get("total_steps", 0)
            total_failures = metacog_stats.get("consecutive_failures", 0)
            reflection = {
                "task": task[:200],
                "loops": self._tool_loop_count,
                "total_tool_calls": total_steps,
                "failures": total_failures,
                "is_looping": metacog_stats.get("is_looping", False),
                "intent": intent.type if intent else "unknown",
                "response_length": len(response),
                "timestamp": datetime.now().isoformat(),
            }

            # Determine efficiency
            if total_failures > total_steps * 0.5:
                reflection["quality"] = "poor"
                event_bus.emit("reflection", {
                    "quality": "poor",
                    "reason": "High failure rate",
                    "task": task[:100],
                })
            elif self._tool_loop_count > 15:
                reflection["quality"] = "slow"
                event_bus.emit("reflection", {
                    "quality": "slow",
                    "reason": f"Took {self._tool_loop_count} loops",
                    "task": task[:100],
                })
            else:
                reflection["quality"] = "good"

            # Record successful pattern in decision cache
            if reflection["quality"] != "poor":
                tool_sequence = []
                for t in self._reasoning_trace:
                    if t.get("type") == "tool_calls":
                        tool_sequence.extend(t.get("tools", []))
                if tool_sequence:
                    domain = intent.domain_hints[0] if (intent and intent.domain_hints) else "general"
                    self.decision_cache.record_success(
                        intent_type=intent.type if intent else "TASK",
                        domain=domain,
                        pattern=task[:200],
                        tool_sequence=tool_sequence[:20],
                        strategy=f"Completed in {self._tool_loop_count} loops",
                    )

        except Exception as e:
            logger.warning(f"  ⚠️ Reflection error: {e}")

    def _record_brain_outcome(self, task, response, intent):
        """
        Record brain-level task outcome to SelfImproveEngine.

        This closes the self-improvement loop: agent-level outcomes are
        recorded by executor._deploy_agent(), but brain-level orchestration
        outcomes were never tracked. Now they are.
        """
        try:
            if not hasattr(self.tool_executor, 'self_improve'):
                return

            metacog_stats = self.metacognition.get_stats()
            success = (
                not response.startswith("❌") and
                not response.startswith("⚠️") and
                metacog_stats.get("consecutive_failures", 0) < 3
            )

            result = {
                "success": success,
                "content": response[:500],
                "steps": self._tool_loop_count,
                "stuck": metacog_stats.get("is_stalled", False),
                "stuck_reason": metacog_stats.get("stall_reason", "") if metacog_stats.get("is_stalled") else "",
            }

            self.tool_executor.self_improve.record_task_outcome(
                agent_name="brain",
                task=task[:200],
                result=result,
            )
        except Exception as e:
            logger.warning(f"  ⚠️ Brain outcome recording error: {e}")

    def _record_self_heal_failure(self, tool_name, error_content, details=""):
        """Feed tool failures into the self-healing engine for pattern detection.

        The self-heal engine (owned by tars.py) analyzes recurring failures
        and can propose code modifications to fix them.
        """
        try:
            # Access self-heal engine through tars instance if available
            # The executor has a _self_heal instance created on first propose_self_heal call
            if hasattr(self.tool_executor, '_self_heal'):
                self.tool_executor._self_heal.record_failure(
                    error=error_content[:500],
                    context=f"tool_execution:{tool_name}",
                    tool=tool_name,
                    details=details,
                )
        except Exception:
            pass  # Self-heal is optional — never crash the brain

    # ═══════════════════════════════════════════════════
    #  PROACTIVE ANTICIPATION (Phase 29)
    # ═══════════════════════════════════════════════════

    def _proactive_check(self, task, response, intent):
        """
        After completing a task, check if there's an obvious follow-up
        and prepare context for it.
        """
        try:
            # If task involved code changes, anticipate testing
            code_tools = {"run_quick_command", "deploy_coder_agent", "deploy_file_agent"}
            trace_tools = set()
            for t in self._reasoning_trace:
                if t.get("type") == "tool_calls":
                    trace_tools.update(t.get("tools", []))

            if trace_tools & code_tools:
                event_bus.emit("proactive_hint", {
                    "hint": "Code was modified — consider testing/verification",
                    "tools_used": list(trace_tools & code_tools),
                })

            # If deployment happened, anticipate health check
            if "deploy" in task.lower() or "deploy" in response.lower():
                event_bus.emit("proactive_hint", {
                    "hint": "Deployment detected — health check recommended",
                })

        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    #  ERROR PATTERN DATABASE (Phase 24) — Consolidated
    #  Uses memory/error_tracker.py singleton (single source of truth)
    # ═══════════════════════════════════════════════════

    def _record_error_pattern(self, context, error_str, details=""):
        """Record an error pattern via the consolidated error_tracker."""
        error_tracker.record_error(
            error=error_str[:500],
            context=context,
            tool=context,
            details=details[:200],
        )

    def _get_error_warning(self, task_text):
        """Check error_tracker for known issues relevant to this task."""
        try:
            top_errors = error_tracker.get_top_errors(10)
            if not top_errors:
                return ""
            warnings = []
            task_lower = task_text.lower()
            for err in top_errors:
                ctx = err.get("context", "").lower()
                count = err.get("count", 0)
                if count >= 2 and (ctx in task_lower or any(
                    w in task_lower for w in ctx.split("_") if len(w) > 3
                )):
                    has_fix = "✅ fix known" if err.get("has_fix") else "❌ no fix"
                    warnings.append(
                        f"⚠️ Previously failed {count}x on '{ctx}': "
                        f"{err.get('error', '')[:100]} [{has_fix}]"
                    )
            return "\n".join(warnings[:3]) if warnings else ""
        except Exception:
            return ""

    # ═══════════════════════════════════════════════════
    #  CROSS-SESSION CONTINUITY (Phase 33)
    # ═══════════════════════════════════════════════════

    def _save_session_state(self):
        """Save lightweight session state for continuity across restarts."""
        try:
            state = {
                "last_active": datetime.now().isoformat(),
                "message_count": self._message_count,
                "compacted_summary": self._compacted_summary[:2000],
                "degradation_level": self._degradation_level,
                "active_thread_id": (
                    self.threads.active_thread.id
                    if self.threads.active_thread else None
                ),
            }
            os.makedirs(os.path.dirname(self._session_state_path), exist_ok=True)
            with open(self._session_state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"  ⚠️ Failed to save session state: {e}")

    def _restore_session_state(self):
        """Restore session state from previous run."""
        try:
            if os.path.exists(self._session_state_path):
                with open(self._session_state_path, "r") as f:
                    state = json.load(f)

                last_active = state.get("last_active", "")
                if last_active:
                    logger.info(f"  📋 Restoring session (last active: {last_active})")

                self._compacted_summary = state.get("compacted_summary", "")
                self._message_count = state.get("message_count", 0)

                # If we were degraded, start fresh
                if state.get("degradation_level", 0) > 0:
                    logger.warning(f"  ⚠️ Previous session was degraded — starting fresh")
        except Exception:
            pass
