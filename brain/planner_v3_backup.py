"""
╔══════════════════════════════════════════════════════════════╗
║       TARS — Brain: Autonomous LLM Planner                   ║
╠══════════════════════════════════════════════════════════════╣
║  v3: Full Autonomy Architecture (10-Phase)                   ║
║    - Dual-provider: Brain=Gemini, Agents=Groq               ║
║    - Auto-compaction prevents context overflow               ║
║    - Environmental scan → Think → Deploy → Verify loop       ║
║    - Smart recovery ladder on failures                       ║
║    - Self-reflection after task completion                    ║
║                                                              ║
║  Supports: Groq, Together, Anthropic, OpenRouter,            ║
║  Gemini, DeepSeek, or any OpenAI-compatible endpoint.        ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from brain.llm_client import LLMClient, _parse_failed_tool_call
from brain.prompts import TARS_SYSTEM_PROMPT, RECOVERY_PROMPT
from brain.tools import TARS_TOOLS
from utils.event_bus import event_bus

# Tools that depend on previous results — must run sequentially
DEPENDENT_TOOLS = {"verify_result", "send_imessage", "wait_for_reply", "checkpoint"}
# Tools safe to run in parallel
PARALLEL_SAFE = {"think", "scan_environment", "recall_memory", "run_quick_command", "quick_read_file"}


class TARSBrain:
    def __init__(self, config, tool_executor, memory_manager):
        self.config = config
        
        # ── Dual-provider setup ──
        # Brain LLM: smart model for planning/reasoning (Gemini, Claude, etc.)
        # Agent LLM: fast model for sub-agent execution (Groq, etc.)
        brain_cfg = config.get("brain_llm")
        llm_cfg = config["llm"]
        
        if brain_cfg and brain_cfg.get("api_key"):
            # Dual-provider mode: separate brain + agent models
            self.client = LLMClient(
                provider=brain_cfg["provider"],
                api_key=brain_cfg["api_key"],
                base_url=brain_cfg.get("base_url"),
            )
            self.brain_model = brain_cfg["model"]
            print(f"  🧠 Brain: {brain_cfg['provider']}/{self.brain_model}")
        else:
            # Fallback: single provider for everything
            self.client = LLMClient(
                provider=llm_cfg["provider"],
                api_key=llm_cfg["api_key"],
                base_url=llm_cfg.get("base_url"),
            )
            self.brain_model = llm_cfg["heavy_model"]
            print(f"  🧠 Brain: {llm_cfg['provider']}/{self.brain_model} (single-provider mode)")

        # ── Provider failover setup ──
        # When the primary brain hits rate limits, failover to this provider
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

        # Keep legacy references for executor compatibility
        self.heavy_model = llm_cfg.get("heavy_model", llm_cfg.get("model", ""))
        self.fast_model = llm_cfg.get("fast_model", self.heavy_model)
        
        self.tool_executor = tool_executor
        self.memory = memory_manager
        self.conversation_history = []
        self.max_retries = config["safety"]["max_retries"]
        
        # Context management — token-aware compaction
        self.max_history_messages = 80      # Hard cap (safety net)
        self.compaction_token_threshold = 80000  # Compact when est. tokens exceed this
        self._compacted_summary = ""        # Compressed old context
        self.max_tool_loops = 50            # Max tool call loops per think() call
        self._tool_loop_count = 0           # Track current loop count
        
        # Conversation memory — TARS remembers across messages
        self._last_message_time = 0         # Timestamp of last user message
        self._conversation_timeout = 600    # 10 min — after this, soft-reset context
        self._message_count = 0             # Messages in current conversation

    def _get_system_prompt(self):
        """Build the system prompt with current context."""
        import os
        memory_context = self.memory.get_context_summary()
        
        # Include compacted context if we have it
        extra_context = ""
        if self._compacted_summary:
            extra_context = f"\n\n## Previous Context (compacted)\n{self._compacted_summary}"
        
        # Include session performance summary if available
        if hasattr(self.tool_executor, 'self_improve'):
            session_summary = self.tool_executor.self_improve.get_session_summary()
            if session_summary and "No tasks" not in session_summary:
                extra_context += f"\n\n{session_summary}"
        
        base_prompt = TARS_SYSTEM_PROMPT.format(
            humor_level=self.config["agent"]["humor_level"],
            cwd=os.getcwd(),
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            active_project=self.memory.get_active_project(),
            memory_context=memory_context,
            max_deploys=8,
        )
        return base_prompt + extra_context

    @staticmethod
    def _estimate_tokens(messages):
        """Estimate token count for a message list.
        
        Uses the ~4 chars/token heuristic (accurate within ±15% for English).
        Much faster than calling tiktoken, zero dependencies.
        """
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
        estimated token usage exceeds the threshold.
        
        Keeps the last 20 messages intact, summarizes the rest.
        This prevents context overflow while preserving key decisions.
        
        Triggers on EITHER:
          - Estimated tokens > compaction_token_threshold (primary)
          - Message count > max_history_messages (hard safety cap)
        """
        est_tokens = self._estimate_tokens(self.conversation_history)
        msg_count = len(self.conversation_history)
        
        if est_tokens < self.compaction_token_threshold and msg_count < self.max_history_messages:
            return
            
        # Split: old messages to compact vs recent to keep
        keep_count = 20
        old_messages = self.conversation_history[:-keep_count]
        recent = self.conversation_history[-keep_count:]
        
        # Build a compact summary of what happened
        summary_parts = []
        for msg in old_messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "user" and isinstance(content, str):
                summary_parts.append(f"User: {content[:200]}")
            elif role == "user" and isinstance(content, list):
                # Tool results
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
        
        self._compacted_summary = "\n".join(summary_parts[-30:])  # Keep last 30 entries
        # Cap total size — keep first 500 chars (task context) + tail (recent results)
        if len(self._compacted_summary) > 4000:
            head = self._compacted_summary[:500]
            tail = self._compacted_summary[-(4000 - 500 - 20):]  # leave room for separator
            self._compacted_summary = head + "\n... (compacted) ...\n" + tail
        self.conversation_history = recent
        
        print(f"  📦 Compacted history: {len(old_messages)} msgs (~{est_tokens} tokens) → summary, keeping {len(recent)} recent")

    def think(self, user_message, use_heavy=None):
        """
        Send a message to the brain LLM and process the response.
        Handles tool calls in a loop until the LLM gives a final text response.
        Streams events to the dashboard in real-time.
        
        v3: Supports up to 50 tool loops for complex multi-step autonomous tasks.
        The brain will: think → scan → deploy → verify → adapt → repeat.
        
        v4: Conversation memory — TARS remembers across messages.
        Messages within 10 min are part of the same conversation.
        After 10 min idle, context is soft-reset (compacted, not wiped).
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
            # Soft-reset: compact everything into summary, don't wipe
            print(f"  💭 Conversation gap: {int(time_since_last)}s — soft-resetting context")
            self._force_compact()
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Compact history if needed (prevents context overflow)
        self._compact_history()

        retry_count = 0
        self._tool_loop_count = 0

        while True:
            # Safety: kill switch — stop thinking immediately
            kill_event = getattr(self.tool_executor, '_kill_event', None)
            if kill_event and kill_event.is_set():
                return "🛑 Kill switch activated — stopping all work."

            # Safety: prevent infinite tool loops
            self._tool_loop_count += 1
            if self._tool_loop_count > self.max_tool_loops:
                event_bus.emit("error", {"message": f"Brain hit max tool loops ({self.max_tool_loops})"})
                return f"⚠️ Reached maximum {self.max_tool_loops} tool call loops. Task may be partially complete. Sending status update."

            call_start = time.time()

            try:
                # Use streaming for real-time dashboard updates
                with self.client.stream(
                    model=model,
                    max_tokens=8192,
                    system=self._get_system_prompt(),
                    tools=TARS_TOOLS,
                    messages=self.conversation_history,
                ) as stream:
                    for event in stream:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                chunk = event.delta.text
                                event_bus.emit("thinking", {
                                    "text": chunk,
                                    "model": model,
                                })

                    # Get the final message
                    response = stream.get_final_message()

                call_duration = time.time() - call_start

                # Emit API stats
                usage = response.usage
                event_bus.emit("api_call", {
                    "model": model,
                    "tokens_in": usage.input_tokens,
                    "tokens_out": usage.output_tokens,
                    "duration": call_duration,
                })

            except Exception as e:
                error_str = str(e)
                error_type = type(e).__name__
                print(f"  ⚠️ Brain streaming error ({error_type}): {error_str[:200]}")

                # ── Non-retryable: API key / permission errors ──
                if "API key expired" in error_str or "PERMISSION_DENIED" in error_str:
                    event_bus.emit("error", {"message": f"API key error: {error_str[:200]}"})
                    self._emergency_notify(error_str)
                    return f"❌ LLM API error: {e}"

                # ── Groq tool_use_failed: try to recover the malformed call ──
                if "tool_use_failed" in error_str:
                    recovered = _parse_failed_tool_call(e)
                    if recovered:
                        response = recovered
                        call_duration = time.time() - call_start
                        event_bus.emit("api_call", {
                            "model": model, "tokens_in": 0,
                            "tokens_out": 0, "duration": call_duration,
                        })
                        print(f"  🔧 Brain: Recovered malformed tool call")
                        # Skip the retry loop below — we have a valid response
                        pass  # fall through to "Process response" section
                    else:
                        # tool_use_failed but couldn't parse — fall through to retry
                        error_str = str(e)  # keep for retry logic
                        response = None
                else:
                    response = None

                # ── Retryable errors: rate limit, 5xx, transient ──
                if response is None:
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
                        is_rate_limit = any(m in error_str.lower() for m in ("rate_limit", "rate limit", "429", "resource_exhausted"))

                        # ── Strategy 1: Provider failover (instant, no wait) ──
                        if is_rate_limit and self._fallback_client and not self._using_fallback:
                            self._using_fallback = True
                            self.client = self._fallback_client
                            model = self._fallback_model
                            self.brain_model = model
                            print(f"  🔄 FAILOVER: Switching brain to {model} (rate limited on primary)")
                            event_bus.emit("status_change", {"status": "online", "label": f"FAILOVER → {model}"})
                            try:
                                response = self.client.create(
                                    model=model,
                                    max_tokens=8192,
                                    system=self._get_system_prompt(),
                                    tools=TARS_TOOLS,
                                    messages=self.conversation_history,
                                )
                                call_duration = time.time() - call_start
                                event_bus.emit("api_call", {
                                    "model": model,
                                    "tokens_in": response.usage.input_tokens,
                                    "tokens_out": response.usage.output_tokens,
                                    "duration": call_duration,
                                })
                                print(f"  ✅ Fallback provider succeeded: {model}")
                            except Exception as fb_e:
                                print(f"  ⚠️ Fallback also failed: {fb_e}")
                                # Both providers down — fall through to retry loop
                                response = None

                        # ── Strategy 2: Retry with backoff (same or fallback provider) ──
                        if response is None:
                            max_api_retries = 5
                            for api_attempt in range(1, max_api_retries + 1):
                                import random as _rand
                                if is_rate_limit:
                                    base, cap = 3.0, 90.0
                                else:
                                    base, cap = 1.0, 30.0
                                delay = min(cap, base * (2 ** api_attempt)) * _rand.uniform(0.5, 1.0)
                                print(f"  ⏳ Retry {api_attempt}/{max_api_retries} in {delay:.1f}s ({error_type})")
                                event_bus.emit("status_change", {"status": "waiting", "label": f"RATE LIMITED — retry in {int(delay)}s"})
                                time.sleep(delay)

                                try:
                                    response = self.client.create(
                                        model=model,
                                        max_tokens=8192,
                                        system=self._get_system_prompt(),
                                        tools=TARS_TOOLS,
                                        messages=self.conversation_history,
                                    )
                                    call_duration = time.time() - call_start
                                    event_bus.emit("api_call", {
                                        "model": model,
                                        "tokens_in": response.usage.input_tokens,
                                        "tokens_out": response.usage.output_tokens,
                                        "duration": call_duration,
                                    })
                                    print(f"  ✅ Retry {api_attempt} succeeded")
                                    event_bus.emit("status_change", {"status": "online", "label": "THINKING"})
                                    break
                                except Exception as retry_e:
                                    error_str = str(retry_e)
                                    error_type = type(retry_e).__name__
                                    print(f"  ⚠️ Retry {api_attempt} failed: {error_str[:150]}")

                                    # Mid-retry failover: if primary is still rate limited, try fallback
                                    if api_attempt == 2 and self._fallback_client and not self._using_fallback:
                                        self._using_fallback = True
                                        self.client = self._fallback_client
                                        model = self._fallback_model
                                        self.brain_model = model
                                        print(f"  🔄 FAILOVER (mid-retry): Switching to {model}")
                                        event_bus.emit("status_change", {"status": "online", "label": f"FAILOVER → {model}"})

                                    if api_attempt == max_api_retries:
                                        event_bus.emit("error", {"message": f"LLM API error after {max_api_retries} retries: {retry_e}"})
                                        self._emergency_notify(str(retry_e))
                                        return f"❌ LLM API error after {max_api_retries} retries: {retry_e}"
                    else:
                        # Non-retryable, non-key error — try one non-streaming fallback
                        print(f"  🔧 Brain: Trying non-streaming fallback...")
                        try:
                            response = self.client.create(
                                model=model,
                                max_tokens=8192,
                                system=self._get_system_prompt(),
                                tools=TARS_TOOLS,
                                messages=self.conversation_history,
                            )
                            call_duration = time.time() - call_start
                            event_bus.emit("api_call", {
                                "model": model,
                                "tokens_in": response.usage.input_tokens,
                                "tokens_out": response.usage.output_tokens,
                                "duration": call_duration,
                            })
                            print(f"  🔧 Brain: Non-streaming fallback succeeded")
                        except Exception as e2:
                            event_bus.emit("error", {"message": f"LLM API error: {e2}"})
                            self._emergency_notify(str(e2))
                            return f"❌ LLM API error: {e2}"

            # Process response
            assistant_content = response.content
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_content
            })

            # Check if LLM wants to use tools
            if response.stop_reason == "tool_use":
                tool_calls = [b for b in assistant_content if b.type == "tool_use"]
                tool_results = []

                # ── Parallel execution for independent tool calls ──
                if len(tool_calls) > 1 and all(tc.name in PARALLEL_SAFE for tc in tool_calls):
                    # All safe to parallelize — these are read-only tools
                    print(f"  ⚡ Parallel execution: {', '.join(tc.name for tc in tool_calls)}")
                    with ThreadPoolExecutor(max_workers=min(len(tool_calls), 4)) as pool:
                        futures = {}
                        start_times = {}
                        for block in tool_calls:
                            event_bus.emit("tool_called", {"tool_name": block.name, "tool_input": block.input})
                            print(f"  🔧 Executing (parallel): {block.name}({block.input})")
                            start_times[block.id] = time.time()
                            future = pool.submit(self.tool_executor.execute, block.name, block.input)
                            futures[future] = block

                        for future in as_completed(futures):
                            block = futures[future]
                            exec_duration = time.time() - start_times[block.id]
                            result = future.result()

                            event_bus.emit("tool_result", {
                                "tool_name": block.name,
                                "content": result.get("content", str(result))[:500],
                                "success": result.get("success", not result.get("error")),
                                "duration": exec_duration,
                            })

                            if result.get("error"):
                                retry_count += 1
                                if retry_count >= self.max_retries:
                                    result["content"] = (
                                        result.get("content", "") +
                                        f"\n\n⚠️ This has failed {retry_count} times. "
                                        "Consider asking Abdullah for help via send_imessage."
                                    )

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result.get("content", str(result)),
                            })
                else:
                    # Sequential execution (default — for dependent or mixed tools)
                    for block in tool_calls:
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        # Emit tool call event
                        event_bus.emit("tool_called", {
                            "tool_name": tool_name,
                            "tool_input": tool_input,
                        })

                        # Execute the tool
                        print(f"  🔧 Executing: {tool_name}({tool_input})")
                        exec_start = time.time()
                        result = self.tool_executor.execute(tool_name, tool_input)
                        exec_duration = time.time() - exec_start

                        # Emit tool result event
                        event_bus.emit("tool_result", {
                            "tool_name": tool_name,
                            "content": result.get("content", str(result))[:500],
                            "success": result.get("success", not result.get("error")),
                            "duration": exec_duration,
                        })

                        # Emit iMessage events for the dashboard
                        if tool_name == "send_imessage":
                            event_bus.emit("imessage_sent", {
                                "message": tool_input.get("message", "")
                            })
                        elif tool_name == "wait_for_reply" and result.get("success"):
                            event_bus.emit("imessage_received", {
                                "message": result.get("content", "")
                            })

                        # Check for failure and retry logic
                        if result.get("error"):
                            retry_count += 1
                            if retry_count >= self.max_retries:
                                result["content"] = (
                                    result.get("content", "") +
                                    f"\n\n⚠️ This has failed {retry_count} times. "
                                    "Consider asking Abdullah for help via send_imessage."
                                )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result.get("content", str(result)),
                        })

                # Add tool results back to conversation
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })

                # Compact if conversation is getting long
                self._compact_history()

                # New thinking block for next iteration
                event_bus.emit("thinking_start", {"model": model})

                # Continue the loop — LLM will process tool results
                continue

            else:
                # LLM gave a final text response — extract it
                final_text = ""
                for block in assistant_content:
                    if hasattr(block, "text"):
                        final_text += block.text

                # Phase 10: Self-reflection — log what worked for learning
                if self._tool_loop_count > 3:  # Only reflect on non-trivial tasks
                    event_bus.emit("self_reflection", {
                        "loops": self._tool_loop_count,
                        "response": final_text[:300],
                    })

                self._tool_loop_count = 0
                event_bus.emit("task_completed", {"response": final_text[:300]})
                return final_text

    def _force_compact(self):
        """Force-compact all history into a summary. Used on conversation timeout."""
        if not self.conversation_history:
            return

    def _emergency_notify(self, error_str):
        """Last-resort: try to send an iMessage when the brain crashes.
        
        Scans conversation history for the last useful result and includes it,
        so the user gets *something* even when the LLM API fails.
        """
        try:
            # Find any useful content from this conversation
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
                notify_msg = "❌ My API key was revoked. Need a new one in config.yaml before I can work."
            elif "rate limit" in error_str.lower() or "429" in error_str:
                notify_msg = "⏳ Rate limited. Send your request again in about a minute."
            else:
                notify_msg = "⚠️ Ran into a technical issue. Try sending your request again."

            self.tool_executor.execute("send_imessage", {"message": notify_msg})
        except Exception:
            pass  # Absolute last resort — don't crash the crash handler
        
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
        print(f"  📦 Force-compacted conversation into summary ({len(summary_parts)} entries)")

    def reset_conversation(self, hard=False):
        """
        Reset conversation state.
        
        soft (default): Compact history into summary — TARS still remembers key context.
        hard: Full wipe — for debugging or explicit user request.
        """
        if hard:
            self.conversation_history = []
            self._compacted_summary = ""
            self._message_count = 0
        else:
            self._force_compact()
        event_bus.emit("status_change", {"status": "online", "label": "READY"})
