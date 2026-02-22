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
DEPENDENT_TOOLS = {"verify_result", "send_imessage", "send_imessage_file", "wait_for_reply", "checkpoint"}
# Tools safe to run in parallel
PARALLEL_SAFE = {"think", "scan_environment", "recall_memory", "run_quick_command",
                 "quick_read_file", "web_search", "save_memory"}

# ── Progress / ack message blocker ──────────────────────────
# If the LLM calls send_imessage with one of these, suppress it.
# The prompt says ZERO progress messages but LLMs sometimes ignore it.
_PROGRESS_PATTERNS = [
    r"^(on it|got it|sure|working on it|let me|i.ll|i will|looking into|checking|gimme|give me)[\s.!]*",
    r"^(searching|processing|analyzing|scanning|running|fetching|pulling|gathering)[\s.!]",
    r"^(one sec|one moment|hold on|hang on|just a (sec|moment|minute))[\s.!]*",
    r"^(almost done|still working|making progress|nearly there)[\s.!]*",
    r"^(i.m (going to|about to|starting|now|currently))[\s]",
    r"^(let me (check|look|search|find|get|pull|grab|see))[\s]",
]
_PROGRESS_RE = [re.compile(p, re.IGNORECASE) for p in _PROGRESS_PATTERNS]


def _is_progress_message(text: str) -> bool:
    """Return True if the message is a progress/ack update that should be suppressed."""
    text = text.strip()
    # Very short messages that are just acks
    if len(text) < 60:
        for pat in _PROGRESS_RE:
            if pat.match(text):
                return True
    return False


class _TaskContext:
    """Per-task conversation context — enables true brain parallelism.
    
    Each concurrent task gets its own conversation history, metacognition
    monitor, reasoning trace, and loop counters. This avoids the old
    design where all tasks shared a single conversation_history under
    a global lock (serializing all parallel work).
    """

    def __init__(self, compacted_summary=""):
        self.conversation_history = []
        self.tool_loop_count = 0
        self.metacog_loop_count = 0
        self.reasoning_trace = []
        self.brain_sent_imessage = False
        self.applied_fixes = {}
        self.metacognition = MetaCognitionMonitor()
        self.compacted_summary = compacted_summary


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

        # Thread safety: per-task conversation histories for true parallelism.
        # _lock only protects shared mutable state (compacted summary, message count).
        # Each task gets its own _TaskContext via _task_contexts dict.
        self._lock = threading.Lock()

        # Per-task context storage — keyed by thread id (threading.get_ident())
        self._task_contexts = {}  # {thread_id: _TaskContext}
        self._task_contexts_lock = threading.Lock()

        # Shared state (protected by _lock)
        self.conversation_history = []  # Legacy — only used by external accessors
        self.max_history_messages = 80
        self.compaction_token_threshold = 80000
        self._compacted_summary = ""
        self.max_tool_loops = 50
        self._brain_sent_imessage = False  # Track if brain already notified user

        # Phase 28: Reasoning Trace (per-task, but last one kept for accessors)
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
        9. Create per-task context
        10. Think via LLM loop
        11. Structured reflection (Phase 27)
        12. Record response in thread
        13. Proactive anticipation (Phase 29)
        14. Save session state (Phase 33)
        """
        # Per-task context: each task gets its own conversation history
        # and metacognition so multiple tasks can think concurrently.
        # Only shared state (message_count, compacted_summary) needs the lock.
        with self._lock:
            compacted = self._compacted_summary
            # Reset the shared sent-flag so this task's response gets delivered.
            # Each task tracks its own flag via ctx.brain_sent_imessage.
            self._brain_sent_imessage = False
        ctx = _TaskContext(compacted_summary=compacted)
        tid = threading.get_ident()
        with self._task_contexts_lock:
            self._task_contexts[tid] = ctx
        try:
            return self._process_inner(batch_or_text, ctx)
        finally:
            with self._task_contexts_lock:
                self._task_contexts.pop(tid, None)
            # Preserve the last task's trace and sent-flag for external accessors
            with self._lock:
                self._reasoning_trace = ctx.reasoning_trace
                if ctx.brain_sent_imessage:
                    self._brain_sent_imessage = True

    def _process_inner(self, batch_or_text, ctx) -> str:
        """Inner process logic — each task has its own _TaskContext."""
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
            cache_context = self.decision_cache.lookup_with_context(
                intent.type, domain_hints, text,
                complexity=getattr(intent, 'complexity', 'simple'),
            )
            cached = cache_context.get("cached_strategy")
            if cached:
                logger.info(f"  💾 Decision cache hit (reliability {cached.reliability:.0f}%)")
                event_bus.emit("decision_cache_hit", {"task": text[:100], "reliability": cached.reliability})
            anti = cache_context.get("anti_patterns", [])
            if anti:
                logger.info(f"  ⚠️ Anti-patterns found: {len(anti)}")

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

        # ── Step 9: Reset metacognition on task context (Phase 34) ──
        ctx.metacognition.reset()

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
            ctx=ctx,
        )

        # ── Step 11: Structured reflection (Phase 27) ──
        if ctx.tool_loop_count > 3:
            self._structured_reflection(text, response, intent, ctx)

        # ── Step 12: Record response in thread ──
        self.threads.record_response(response[:500])

        # ── Step 13: Record brain-level task outcome for self-improvement ──
        self._record_brain_outcome(text, response, intent, ctx)

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
                    cached_decision=None, ctx=None) -> str:
        """
        Core LLM thinking loop — v5 with metacognition + reasoning trace.
        Each call gets its own _TaskContext for true parallelism.
        """
        if ctx is None:
            ctx = _TaskContext()
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
        with self._lock:
            time_since_last = now - self._last_message_time if self._last_message_time else float("inf")
            self._last_message_time = now
            self._message_count += 1
            compacted = self._compacted_summary

        if time_since_last > self._conversation_timeout and compacted:
            gap_display = "∞" if (time_since_last == float("inf") or time_since_last > 1e15) else int(time_since_last)
            logger.info(f"  💭 Conversation gap: {gap_display}s — starting fresh context")

        # ── Inject cached decision hint ──
        hint = ""
        if cached_decision:
            hint = f"\n\n[Decision cache: Previously succeeded with strategy: {cached_decision.strategy}. Tools: {', '.join(cached_decision.tool_sequence[:5])}]"
        if error_warning:
            hint += f"\n\n[Error pattern warning: {error_warning}]"

        # ── Add user message to per-task history ──
        # Cap message length to prevent a single huge paste from blowing context
        msg_content = (user_message + hint)[:8000]
        ctx.conversation_history.append({
            "role": "user",
            "content": msg_content,
        })

        # ── Compact if needed ──
        self._compact_history(ctx)

        # Phase 38: Configure metacognition budget awareness
        ctx.metacognition.set_budget(
            max_deployments=self.tool_executor.max_deployments,
            max_tool_loops=self.max_tool_loops,
        )

        # ── Build system prompt ──
        system_prompt = self._build_system_prompt(
            intent, thread_context, memory_context,
            subtask_plan=subtask_plan,
            compacted_summary=ctx.compacted_summary,
            ctx=ctx,
        )

        # ── LLM thinking loop ──
        retry_count = 0
        ctx.tool_loop_count = 0

        while True:
            # Safety: kill switch
            kill_event = getattr(self.tool_executor, '_kill_event', None)
            if kill_event and kill_event.is_set():
                return "🛑 Kill switch activated — stopping all work."

            # Safety: max tool loops
            ctx.tool_loop_count += 1
            if ctx.tool_loop_count > self.max_tool_loops:
                event_bus.emit("error", {"message": f"Brain hit max tool loops ({self.max_tool_loops})"})
                return f"⚠️ Reached maximum {self.max_tool_loops} tool call loops. Task may be partially complete."

            # Phase 34: MetaCognition check every iteration
            metacog = ctx.metacognition.analyze()
            injection = ctx.metacognition.get_injection()

            # Phase 38: Strategic advice every 5 steps (proactive, not reactive)
            if not injection and ctx.tool_loop_count % 5 == 0 and ctx.tool_loop_count > 0:
                advice = ctx.metacognition.get_strategic_advice()
                if advice:
                    injection = f"\U0001f4cb STRATEGIC AWARENESS:\n{advice}"

            if injection:
                ctx.conversation_history.append({
                    "role": "user",
                    "content": injection,
                })
                ctx.reasoning_trace.append({
                    "step": ctx.tool_loop_count,
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
                    ctx.metacog_loop_count += 1
                    # send_imessage loops are critical — break immediately
                    if metacog.loop_tool in ("send_imessage", "send_imessage_file"):
                        logger.warning(f"  🛑 Force-breaking: send_imessage loop detected ({metacog.loop_count} calls)")
                        event_bus.emit("error", {"message": "Force-break: send_imessage loop"})
                        return "⚠️ I detected I was stuck in a messaging loop and stopped. The task may be partially complete."
                    # Other tools: allow 3 consecutive metacognition warnings before force-break
                    if ctx.metacog_loop_count >= 3:
                        logger.warning(f"  🛑 Force-breaking: metacognition detected {ctx.metacog_loop_count} consecutive loops")
                        event_bus.emit("error", {"message": "Force-break: sustained tool loop detected"})
                        return "⚠️ I detected I was stuck in a loop and stopped. The task may be partially complete."
                else:
                    ctx.metacog_loop_count = 0

            # ── Call LLM (with error handling + failover) ──
            response, model = self._call_llm(system_prompt, model, tools=tools, ctx=ctx)
            if response is None:
                return "❌ LLM API error — could not get a response after retries."

            # ── Process response ──
            assistant_content = response.content
            ctx.conversation_history.append({
                "role": "assistant",
                "content": assistant_content,
            })

            if response.stop_reason == "tool_use":
                # ── Extract and execute tool calls ──
                tool_calls = [b for b in assistant_content if b.type == "tool_use"]

                # Phase 28: Log reasoning trace
                ctx.reasoning_trace.append({
                    "step": ctx.tool_loop_count,
                    "type": "tool_calls",
                    "tools": [tc.name for tc in tool_calls],
                })

                tool_results = self._execute_tool_calls(tool_calls, retry_count, intent, thread, ctx)

                # Add tool results to conversation
                ctx.conversation_history.append({
                    "role": "user",
                    "content": tool_results,
                })

                # Compact if growing
                self._compact_history(ctx)

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
                # Exception: if the brain already sent an iMessage, the task is done.
                if ctx.tool_loop_count > 1 and len(final_text.strip()) < 10:
                    if ctx.brain_sent_imessage:
                        logger.info("  ✅ Empty response after send_imessage — task is done.")
                        final_text = final_text.strip() or "✅ Message sent."
                    elif retry_count < 2:
                        retry_count += 1
                        logger.warning(f"  ⚠️ Empty response after {ctx.tool_loop_count} tool loops — re-prompting LLM (retry {retry_count}/2)")
                        ctx.conversation_history.append({
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
                ctx.reasoning_trace.append({
                    "step": ctx.tool_loop_count,
                    "type": "final_response",
                    "length": len(final_text),
                })

                if ctx.tool_loop_count > 3:
                    event_bus.emit("self_reflection", {
                        "loops": ctx.tool_loop_count,
                        "response": final_text[:300],
                    })

                # Phase 39: Reasoning quality gate — validate before returning
                quality = self._check_response_quality(final_text, intent, ctx)
                if quality.get("needs_retry") and retry_count < 2:
                    retry_count += 1
                    logger.warning(f"  ⚠️ Quality gate: {quality['reason']} — re-prompting (retry {retry_count}/2)")
                    ctx.conversation_history.append({
                        "role": "user",
                        "content": quality["nudge"],
                    })
                    event_bus.emit("quality_gate", {
                        "passed": False,
                        "reason": quality["reason"],
                    })
                    event_bus.emit("thinking_start", {"model": model})
                    continue

                event_bus.emit("task_completed", {"response": final_text[:300]})
                return final_text

    # ═══════════════════════════════════════════════════
    #  LLM CALL (with error handling, retry, failover)
    # ═══════════════════════════════════════════════════

    def _call_llm(self, system_prompt, model, tools=None, ctx=None):
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
        if ctx is None:
            ctx = _TaskContext()
        messages = ctx.conversation_history
        call_start = time.time()

        try:
            # ── Debug: log message count and last message ──
            hist_len = len(messages)
            if hist_len > 0:
                last_msg = messages[-1]
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
                messages=messages,
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

            # Phase 38: Track token usage for budget awareness
            if ctx and hasattr(response, 'usage'):
                ctx.metacognition.record_token_estimate(
                    response.usage.input_tokens + response.usage.output_tokens
                )

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

                # Phase 24: Record LLM error for pattern tracking
                error_tracker.record_error(
                    error=f"LLM {error_type}: {error_str[:300]}",
                    context="llm_call",
                    tool="llm_call",
                    source_file="brain/planner.py",
                    details=f"model={model}, retryable={'rate_limit' if is_rate_limit else error_type}",
                )

                # ── Strategy 1: Provider failover (instant) ──
                if is_rate_limit and self._fallback_client and not self._using_fallback:
                    result, new_model = self._failover_to_fallback(system_prompt, tools=tools, messages=messages)
                    if result is not None:
                        return result, new_model

                # ── Strategy 2: Retry with backoff ──
                result = self._retry_with_backoff(
                    system_prompt, model, is_rate_limit, error_type, tools=tools, messages=messages
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
                        messages=messages,
                    )
                    call_duration = time.time() - call_start
                    self._emit_api_stats(model, response, call_duration)
                    logger.info(f"  🔧 Brain: Non-streaming fallback succeeded")
                    return response, model
                except Exception as e2:
                    error_tracker.record_error(
                        error=f"LLM non-streaming fallback: {type(e2).__name__}: {e2}",
                        context="llm_call",
                        tool="llm_call",
                        source_file="brain/planner.py",
                        details=f"model={model}, both streaming and non-streaming failed",
                    )
                    event_bus.emit("error", {"message": f"LLM API error: {e2}"})
                    self._emergency_notify(str(e2))

            return None, model

    def _failover_to_fallback(self, system_prompt, tools=None, messages=None):
        """Switch to fallback LLM provider."""
        if tools is None:
            tools = TARS_TOOLS
        if messages is None:
            messages = []
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
                messages=messages,
            )
            self._emit_api_stats(model, response, 0)
            logger.info(f"  ✅ Fallback provider succeeded: {model}")
            return response, model
        except Exception as fb_e:
            self._degradation_level = 2
            logger.warning(f"  ⚠️ Fallback also failed: {fb_e}")
            return None, model

    def _retry_with_backoff(self, system_prompt, model, is_rate_limit, error_type, tools=None, messages=None):
        """Retry LLM call with exponential backoff."""
        import random as _rand
        if tools is None:
            tools = TARS_TOOLS
        if messages is None:
            messages = []
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
                    messages=messages,
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

    def _execute_tool_calls(self, tool_calls, retry_count, intent, thread, ctx=None):
        """
        Execute a batch of tool calls — v5 with metacognition + error patterns.

        Supports parallel execution for independent tools.
        Records to metacognition, decision cache, and reasoning trace.
        """
        if ctx is None:
            ctx = _TaskContext()
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
                    ctx.metacognition.record_tool_call(
                        block.name, block.input,
                        result.get("success", False), exec_duration
                    )

                    # Phase 35: Track failures in error tracker (parallel path)
                    # Skip deploy_* tools — executor._deploy_agent() already records those
                    if not result.get("success") and not block.name.startswith("deploy_"):
                        error_content = result.get("content", "unknown error")
                        error_tracker.record_error(
                            error=error_content,
                            context=block.name,
                            tool=block.name,
                            source_file="brain/planner.py",
                            details=self._format_error_details(block.name, block.input, error_content),
                            params=self.tool_executor._safe_params(block.input) if hasattr(self.tool_executor, '_safe_params') else {},
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

                # ── Progress message blocker ──
                # If the brain calls send_imessage with a progress/ack update,
                # suppress it and tell the LLM to stop doing that.
                if tool_name == "send_imessage" and _is_progress_message(tool_input.get("message", "")):
                    logger.info(f"  🚫 Blocked progress message: {tool_input.get('message', '')[:80]}")
                    result = {
                        "success": True,
                        "content": (
                            "⚠️ BLOCKED: That was a progress/status update. "
                            "Abdullah does NOT want progress messages — only FINAL results. "
                            "Continue working silently and send ONE message when the task is DONE."
                        ),
                    }
                    exec_duration = 0.0
                else:
                    exec_start = time.time()
                    result = self.tool_executor.execute(tool_name, tool_input)
                    exec_duration = time.time() - exec_start

                self._emit_tool_result(block, result, exec_duration)

                # Phase 34: Record in metacognition
                success = result.get("success", not result.get("error", False))
                ctx.metacognition.record_tool_call(tool_name, tool_input, success, exec_duration)

                # Phase 38: Parse confidence from think() results
                if tool_name == "think" and success:
                    self._parse_and_record_confidence(result.get("content", ""), ctx)

                # Phase 38: Track deployments for budget awareness
                if success and tool_name.startswith("deploy_"):
                    ctx.metacognition.record_deployment(
                        agent_type=tool_name.replace("deploy_", ""),
                        task=str(tool_input.get("task", ""))[:200],
                    )

                # Track if brain sent an iMessage (so _run_task doesn't double-send)
                if tool_name in ("send_imessage", "send_imessage_file") and success:
                    ctx.brain_sent_imessage = True

                # Phase 24: Record error pattern on failure
                if not success:
                    error_content = result.get("content", "unknown error")
                    # Feed to self-healing engine for pattern detection
                    self._record_self_heal_failure(
                        tool_name, error_content, str(tool_input)[:200],
                    )
                    # Phase 35: Error tracker — skip deploy_* (executor already records)
                    fix_info = None
                    if not tool_name.startswith("deploy_"):
                        fix_info = error_tracker.record_error(
                            error=error_content,
                            context=tool_name,
                            tool=tool_name,
                            source_file="brain/planner.py",
                            details=self._format_error_details(tool_name, tool_input, error_content),
                            params=self.tool_executor._safe_params(tool_input) if hasattr(self.tool_executor, '_safe_params') else {},
                        )
                    if fix_info and fix_info.get("has_fix"):
                        # Check if this same error recurred after a fix was already suggested
                        fix_key = f"{tool_name}:{error_content[:100]}"
                        if fix_key in ctx.applied_fixes:
                            # Fix was already suggested but error recurred — mark it as failed
                            logger.warning(f"🩹 Auto-fix failed — same error recurred: {error_content[:80]}")
                            error_tracker.mark_fix_failed(
                                error=error_content,
                                context=tool_name,
                            )
                            del ctx.applied_fixes[fix_key]
                        else:
                            # First time suggesting this fix — track it
                            ctx.applied_fixes[fix_key] = fix_info["fix"][:200]
                            logger.info(f"🩹 Known fix available: {fix_info['fix'][:80]}")
                            event_bus.emit("auto_fix_available", {
                                "tool": tool_name,
                                "fix": fix_info["fix"][:200],
                                "confidence": fix_info.get("confidence", 0),
                                "times_applied": fix_info.get("times_applied", 0),
                            })


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
    #  REASONING QUALITY GATE (Phase 39)
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _check_response_quality(response: str, intent, ctx) -> dict:
        """
        Validate the brain's final response before returning.
        
        Catches:
        - Task responses that forgot to send iMessage
        - Empty/apology responses when tools succeeded
        - Responses that don't address the user's question
        - Brain giving up too early
        
        Returns:
            {"needs_retry": bool, "reason": str, "nudge": str}
        """
        text = response.strip()
        text_lower = text.lower()

        # Skip quality checks for conversation/acknowledgment
        if intent and intent.type in ("CONVERSATION", "ACKNOWLEDGMENT"):
            return {"needs_retry": False}

        # Check 1: Task completed but no iMessage sent
        # If the brain did real work (3+ tool loops) but never sent an iMessage,
        # it probably forgot to deliver the result to Abdullah.
        if (intent and intent.is_actionable
                and ctx.tool_loop_count >= 3
                and not ctx.brain_sent_imessage):
            # Check if the response is an internal summary (not user-facing)
            has_result_keywords = any(w in text_lower for w in [
                "done", "completed", "finished", "created", "sent", "found",
                "here's", "result", "success", "ready", "built", "deployed",
            ])
            if has_result_keywords:
                return {
                    "needs_retry": True,
                    "reason": "completed_task_no_imessage",
                    "nudge": (
                        "You completed the task but FORGOT to send the result to Abdullah "
                        "via send_imessage. The user NEVER sees your text responses — "
                        "only iMessages reach them. Send the result NOW."
                    ),
                }

        # Check 2: Apology/giving-up when tools had successes
        apology_patterns = [
            "i apologize", "i'm sorry", "unfortunately", "i wasn't able",
            "i couldn't", "i can't", "unable to", "not possible",
            "i failed to", "i was unable",
        ]
        has_apology = any(p in text_lower for p in apology_patterns)
        if has_apology and ctx.tool_loop_count >= 2:
            # Check if any tools actually succeeded
            successful_tools = sum(
                1 for step in ctx.reasoning_trace
                if step.get("type") == "tool_calls"
            )
            if successful_tools >= 2:
                return {
                    "needs_retry": True,
                    "reason": "apologizing_despite_progress",
                    "nudge": (
                        "You said you couldn't do it, but you actually made progress — "
                        f"you successfully used tools in {successful_tools} steps. "
                        "Review what you've gathered and compile a useful response. "
                        "Don't give up — use what you have."
                    ),
                }

        # Check 3: Very short response for a complex task
        if (intent and intent.is_actionable
                and getattr(intent, 'complexity', 'simple') in ('moderate', 'complex')
                and len(text) < 30
                and ctx.tool_loop_count < 3
                and not ctx.brain_sent_imessage):
            return {
                "needs_retry": True,
                "reason": "too_shallow_for_complexity",
                "nudge": (
                    f"This is a {getattr(intent, 'complexity', 'moderate')} task but you responded "
                    "with a very short answer and barely used any tools. "
                    "Think deeper — use the appropriate tools to actually accomplish the task."
                ),
            }

        return {"needs_retry": False}

    # ═══════════════════════════════════════════════════
    #  SYSTEM PROMPT BUILDER (Phase 5)
    # ═══════════════════════════════════════════════════

    def _build_system_prompt(self, intent, thread_context="", memory_context="",
                             subtask_plan="", compacted_summary=None, ctx=None):
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

        # Use provided compacted_summary (per-task), fall back to shared
        summary = compacted_summary if compacted_summary is not None else self._compacted_summary

        # Build metacognition context for system prompt injection
        metacog_context = ""
        if ctx:
            stats = ctx.metacognition.get_stats()
            if stats.get("total_steps", 0) > 0:
                parts = []
                phase = stats.get("phase", "planning")
                parts.append(f"Phase: {phase}")
                deploys = stats.get("deployments_used", 0)
                deploy_budget = stats.get("deployments_budget", 15)
                if deploys > 0:
                    parts.append(f"Deployments: {deploys}/{deploy_budget}")
                diversity = stats.get("tool_diversity", 1.0)
                if diversity < 0.5:
                    parts.append(f"Tool diversity: LOW ({diversity:.0%}) — try different tools")
                progress = stats.get("progress_score", 0.0)
                if progress > 0:
                    parts.append(f"Progress: {progress:.0%}")
                advice = stats.get("strategic_advice", "")
                if advice:
                    parts.append(f"Advice: {advice}")
                metacog_context = " | ".join(parts)

        # Build anti-pattern warnings from decision cache
        anti_warning = ""
        if intent and hasattr(intent, 'domain_hints') and intent.domain_hints:
            anti = self.decision_cache.get_anti_patterns(
                intent.type, intent.domain_hints,
                intent.detail or ""
            )
            if anti:
                anti_warning = "\n\n⚠️ KNOWN ANTI-PATTERNS (avoid these):\n" + "\n".join(
                    f"  ❌ {a}" for a in anti[:3]
                )
        if anti_warning:
            if metacog_context:
                metacog_context += anti_warning
            else:
                metacog_context = anti_warning

        return build_system_prompt(
            humor_level=self.config["agent"]["humor_level"],
            cwd=os.getcwd(),
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            active_project=self.memory.get_active_project(),
            memory_context=full_memory_context,
            max_deploys=self.tool_executor.max_deployments,
            intent_type=intent.type if intent else "",
            intent_detail=intent.detail if intent else "",
            domain_hints=intent.domain_hints if intent else [],
            thread_context=thread_context,
            compacted_summary=summary,
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
        Phase 19+: Smart multi-query memory recall.

        Generates targeted queries from multiple angles:
        1. Direct text (first 100 chars)
        2. Extracted entities (proper nouns, quoted strings)
        3. Domain-specific keywords (preferences, procedures)
        4. Action + object patterns
        5. Entity-specific queries from intent classifier
        """
        queries = [text[:100]]

        # Use entities from intent classifier if available
        if intent and hasattr(intent, 'entities') and intent.entities:
            for entity in intent.entities[:3]:
                if len(entity) > 2:
                    queries.append(entity)

        # Domain-specific memory queries
        if intent and hasattr(intent, 'domain_hints'):
            domain_query_map = {
                "flights": ["flight preferences", "airlines", "travel"],
                "email": ["email preferences", "contacts", "email signature"],
                "dev": ["coding preferences", "tech stack", "repositories"],
                "accounts": ["account credentials", "passwords", "login"],
                "reports": ["report format", "report preferences"],
                "scheduling": ["calendar", "schedule preferences"],
            }
            for domain in (intent.domain_hints or []):
                for dq in domain_query_map.get(domain, []):
                    queries.append(dq)

        # Extract potential entity names (capitalized words)
        words = text.split()
        entities = [w for w in words if w[0:1].isupper() and len(w) > 2]
        if entities:
            queries.append(" ".join(entities[:5]))

        # Extract quoted strings as exact recall targets
        import re as _re
        quoted = _re.findall(r'"([^"]+)"', text)
        queries.extend(quoted[:2])

        # Extract action + object pattern
        action_words = {"find", "search", "create", "build", "fix", "update",
                        "check", "get", "send", "write", "read", "install",
                        "deploy", "run", "test", "debug", "setup", "configure",
                        "book", "order", "schedule", "remind", "track", "monitor"}
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
            q_lower = q.lower().strip()
            if q_lower in seen or len(q_lower) < 3:
                continue
            seen.add(q_lower)
            try:
                result = self.memory.recall(q)
                if result.get("success") and result.get("content"):
                    content = result["content"]
                    if len(content) > 20 and content != "No memories found.":
                        # Avoid duplicate content
                        if not any(content[:50] in r for r in results):
                            results.append(content)
            except Exception:
                pass

            # Cap at 4 results to avoid overwhelming context
            if len(results) >= 4:
                break

        if not results:
            return ""

        # Merge and cap
        merged = "\n---\n".join(results)
        return merged[:1500]

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

    def _compact_history(self, ctx=None):
        """
        Token-aware compaction: compress old conversation history when
        estimated token usage exceeds threshold.
        
        Keeps last 20 messages intact, summarizes the rest.
        Operates on per-task context if provided.
        """
        history = ctx.conversation_history if ctx else self.conversation_history
        est_tokens = self._estimate_tokens(history)
        msg_count = len(history)

        if est_tokens < self.compaction_token_threshold and msg_count < self.max_history_messages:
            return

        keep_count = 20
        old_messages = history[:-keep_count]
        recent = history[-keep_count:]

        # Build compact summary with smart prioritization
        high_priority = []   # Errors, decisions, deployments — always kept
        medium_priority = [] # Tool calls, user messages
        low_priority = []    # Search results, verbose data

        for i, msg in enumerate(old_messages):
            role = msg["role"]
            content = msg["content"]

            if role == "user" and isinstance(content, str):
                # First user message (original task) gets full preservation
                if i == 0:
                    high_priority.append(f"ORIGINAL TASK: {content[:500]}")
                elif content.startswith("\u26a0\ufe0f META-COGNITION") or content.startswith("\U0001f4cb STRATEGIC"):
                    high_priority.append(f"Alert: {content[:200]}")
                else:
                    medium_priority.append(f"User: {content[:150]}")
            elif role == "user" and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result_text = str(item.get("content", ""))
                        t_name = item.get("tool_name", "")
                        if "error" in result_text.lower() or "failed" in result_text.lower():
                            high_priority.append(f"\u274c {t_name}: {result_text[:300]}")
                        elif t_name.startswith("deploy_") or t_name in ("generate_report", "send_imessage"):
                            high_priority.append(f"\u2705 {t_name}: {result_text[:250]}")
                        elif t_name in ("web_search", "recall_memory", "scan_environment"):
                            low_priority.append(f"{t_name}: {result_text[:100]}")
                        else:
                            medium_priority.append(f"{t_name}: {result_text[:150]}")
            elif role == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "type"):
                            if block.type == "text" and block.text:
                                medium_priority.append(f"TARS: {block.text[:200]}")
                            elif block.type == "tool_use":
                                if block.name.startswith("deploy_") or block.name in ("send_imessage", "generate_report"):
                                    high_priority.append(f"Called: {block.name}({str(block.input)[:150]})")
                                else:
                                    medium_priority.append(f"Called: {block.name}({str(block.input)[:80]})")
                elif isinstance(content, str):
                    medium_priority.append(f"TARS: {content[:200]}")

        # Assemble: all high priority + capped medium + capped low
        summary_parts = list(high_priority)
        budget = 30 - len(summary_parts)
        summary_parts.extend(medium_priority[-max(budget // 2, 5):])
        budget = 30 - len(summary_parts)
        if budget > 0:
            summary_parts.extend(low_priority[-budget:])

        compacted = "\n".join(summary_parts[:30])
        if len(compacted) > 4000:
            head = compacted[:500]
            tail = compacted[-(4000 - 500 - 20):]
            compacted = head + "\n... (compacted) ...\n" + tail

        if ctx:
            ctx.compacted_summary = compacted
            ctx.conversation_history = recent
        else:
            self._compacted_summary = compacted
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
            # Get the current task's conversation history
            tid = threading.get_ident()
            with self._task_contexts_lock:
                ctx = self._task_contexts.get(tid)
            history = ctx.conversation_history if ctx else self.conversation_history
            partial = ""
            for msg in reversed(history):
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
        
        Uses keyword heuristics + domain analysis (no LLM call).
        Detects: numbered lists, sequential markers, multi-domain tasks,
        implicit research→compile→deliver pipelines, and intent subtasks.
        """
        subtasks = []

        # Strategy 0: Use intent classifier's multi-task detection
        if intent and hasattr(intent, 'subtasks') and intent.subtasks:
            subtasks = intent.subtasks[:8]

        # Strategy 1: Explicit numbered lists
        if not subtasks:
            lines = text.split("\n")
            numbered = [l.strip() for l in lines if re.match(r"^\d+[\.\)]\s", l.strip())]
            if numbered:
                subtasks = numbered[:8]

        # Strategy 2: Sequential markers ("then", "also", "after that")
        if not subtasks:
            parts = re.split(r"\b(?:then|and then|after that|also|next)\b", text, flags=re.IGNORECASE)
            if len(parts) > 1:
                subtasks = [p.strip() for p in parts if len(p.strip()) > 10][:6]

        # Strategy 3: Multi-domain detection (implicit pipeline)
        if not subtasks and intent and intent.domain_hints and len(intent.domain_hints) >= 2:
            domain_tasks = {
                "research": "Research and gather data",
                "flights": "Search for flight options",
                "email": "Send results via email",
                "dev": "Implement the code changes",
                "browser": "Complete the web task",
                "files": "Organize the files",
                "system": "Configure the system",
                "accounts": "Handle account setup/login",
                "reports": "Generate the report/document",
                "scheduling": "Set up the schedule/reminder",
                "memory": "Store/recall relevant information",
                "media": "Handle media playback/control",
            }
            for d in intent.domain_hints:
                if d in domain_tasks:
                    subtasks.append(domain_tasks[d])
            if subtasks:
                subtasks.append("Deliver results to Abdullah via iMessage")

        # Strategy 4: Implicit pipeline (research\u2192report\u2192deliver pattern)
        if not subtasks:
            text_lower = text.lower()
            phases = []
            if any(w in text_lower for w in ("find", "search", "get", "look up",
                    "research", "check", "analyze", "compare")):
                phases.append("Gather data and research")
            if any(w in text_lower for w in ("report", "excel", "pdf", "spreadsheet",
                    "chart", "summary", "compile", "presentation")):
                phases.append("Compile findings into report/document")
            if any(w in text_lower for w in ("email", "send", "mail", "notify", "share")):
                phases.append("Deliver via email")
            if len(phases) >= 2:
                subtasks = phases
                subtasks.append("Confirm completion to Abdullah via iMessage")

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

        # Complexity-aware budget allocation
        max_deploys = self.tool_executor.max_deployments
        complexity = getattr(intent, 'complexity', 'simple')
        if complexity == "complex":
            plan += f"\n⚠️ COMPLEX TASK — Budget: {max_deploys} deployments. "
            plan += "Plan carefully. BATCH related items. Don't spend >50% on data gathering.\n"
        elif len(subtasks) > 2:
            plan += f"\nBudget: {max_deploys} deployments. "
            plan += f"Allocate ~{max_deploys // len(subtasks)} per phase. "
            plan += "Batch related items into single deployments.\n"

        # Urgency annotation
        urgency = getattr(intent, 'urgency', 0.0)
        if urgency >= 0.7:
            plan += "🔴 HIGH URGENCY — prioritize speed over perfection.\n"
        elif urgency >= 0.4:
            plan += "🟡 MODERATE URGENCY — balance speed and quality.\n"

        event_bus.emit("task_decomposed", {"subtasks": subtasks, "complexity": complexity})
        return plan

    # ═══════════════════════════════════════════════════
    #  STRUCTURED REFLECTION (Phase 27)
    # ═══════════════════════════════════════════════════

    def _structured_reflection(self, task, response, intent, ctx=None):
        """
        Post-task structured reflection — learns from what just happened.
        """
        try:
            mc = ctx.metacognition if ctx else self.metacognition
            metacog_stats = mc.get_stats()
            total_steps = metacog_stats.get("total_steps", 0)
            total_failures = metacog_stats.get("consecutive_failures", 0)
            loop_count = ctx.tool_loop_count if ctx else 0
            trace = ctx.reasoning_trace if ctx else self._reasoning_trace
            reflection = {
                "task": task[:200],
                "loops": loop_count,
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
            elif loop_count > 15:
                reflection["quality"] = "slow"
                event_bus.emit("reflection", {
                    "quality": "slow",
                    "reason": f"Took {loop_count} loops",
                    "task": task[:100],
                })
            else:
                reflection["quality"] = "good"

            # Record full task strategy in decision cache (not per-tool)
            tool_sequence = []
            for t in trace:
                if t.get("type") == "tool_calls":
                    tool_sequence.extend(t.get("tools", []))

            if tool_sequence:
                domain = intent.domain_hints[0] if (intent and intent.domain_hints) else "general"
                # Deduplicate consecutive same-tools for cleaner sequences
                deduped = []
                for t in tool_sequence:
                    if not deduped or deduped[-1] != t:
                        deduped.append(t)
                # Build a meaningful strategy description
                phases = []
                if any(t.startswith("deploy_") for t in deduped):
                    agents = list(dict.fromkeys(t for t in deduped if t.startswith("deploy_")))
                    phases.append(f"agents: {', '.join(agents)}")
                if "generate_report" in deduped:
                    phases.append("compiled report")
                if "send_imessage" in deduped or "mac_mail" in deduped:
                    phases.append("delivered results")
                strategy = f"{' → '.join(phases) if phases else 'direct'} in {loop_count} steps"
                generalized = self.decision_cache.generalize_pattern(task, intent.domain_hints or [])

                if reflection["quality"] != "poor":
                    self.decision_cache.record_success(
                        intent_type=intent.type if intent else "TASK",
                        domain=domain,
                        pattern=generalized if len(generalized) > 10 else task[:200],
                        tool_sequence=deduped[:20],
                        strategy=strategy,
                        steps=loop_count,
                        complexity=getattr(intent, 'complexity', 'simple'),
                    )
                else:
                    self.decision_cache.record_failure(
                        intent_type=intent.type if intent else "TASK",
                        domain=domain,
                        pattern=generalized if len(generalized) > 10 else task[:200],
                        failed_strategy=strategy,
                    )

        except Exception as e:
            logger.warning(f"  ⚠️ Reflection error: {e}")

    def _record_brain_outcome(self, task, response, intent, ctx=None):
        """
        Record brain-level task outcome to SelfImproveEngine.

        This closes the self-improvement loop: agent-level outcomes are
        recorded by executor._deploy_agent(), but brain-level orchestration
        outcomes were never tracked. Now they are.
        """
        try:
            if not hasattr(self.tool_executor, 'self_improve'):
                return

            mc = ctx.metacognition if ctx else self.metacognition
            metacog_stats = mc.get_stats()
            loop_count = ctx.tool_loop_count if ctx else 0
            success = (
                not response.startswith("❌") and
                not response.startswith("⚠️") and
                metacog_stats.get("consecutive_failures", 0) < 3
            )

            result = {
                "success": success,
                "content": response[:500],
                "steps": loop_count,
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
        After completing a task, analyze what happened and save
        follow-up hints for the next interaction.
        """
        try:
            trace_tools = set()
            for t in self._reasoning_trace:
                if t.get("type") == "tool_calls":
                    trace_tools.update(t.get("tools", []))

            hints = []

            # Code changes → suggest testing
            code_tools = {"run_quick_command", "deploy_coder_agent", "deploy_file_agent", "deploy_dev_agent"}
            if trace_tools & code_tools:
                hints.append("Code was modified — verification/testing recommended")

            # Deployment → suggest health check
            if any("deploy" in t for t in trace_tools):
                if "deploy" in task.lower() or "deploy" in response.lower():
                    hints.append("Deployment detected — health check recommended")

            # Report generated → follow-up on action items
            if "generate_report" in trace_tools:
                hints.append("Report was generated — follow up on action items")

            # Email sent → suggest follow-up tracking
            if "mac_mail" in trace_tools and "send" in task.lower():
                hints.append("Email sent — consider setting a follow-up reminder")

            # Account created → verify login
            if "manage_account" in trace_tools or "deploy_browser_agent" in trace_tools:
                if any(w in task.lower() for w in ("signup", "sign up", "create account", "register")):
                    hints.append("Account created — verify login works")

            # Save hints for next interaction context
            if hints:
                try:
                    self.memory.save({
                        "category": "context",
                        "key": "proactive_hints",
                        "value": " | ".join(hints[:3]),
                    })
                except Exception:
                    pass

                for hint in hints:
                    event_bus.emit("proactive_hint", {
                        "hint": hint,
                        "task": task[:100],
                    })

        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    #  ERROR PATTERN DATABASE (Phase 24) — Consolidated
    #  Uses memory/error_tracker.py singleton (single source of truth)
    # ═══════════════════════════════════════════════════

    def _record_error_pattern(self, context, error_str, details=""):
        """Record an error pattern via the consolidated error_tracker.

        NOTE: Most call sites now call error_tracker.record_error() directly
        with richer fields. This wrapper exists for backward compatibility.
        """
        error_tracker.record_error(
            error=error_str[:500],
            context=context,
            tool=context,
            source_file="brain/planner.py",
            details=details[:200],
        )

    @staticmethod
    def _format_error_details(tool_name, tool_input, error_content):
        """Build a human-readable detail string for the error tracker.

        Instead of raw str(tool_input), produce something actionable like:
        'web_search query="stock price NVDA" → 403 Forbidden'
        """
        parts = [tool_name]
        if isinstance(tool_input, dict):
            # Pick the most useful params to show
            for key in ("query", "task", "command", "url", "file_path",
                        "recipient", "to", "subject", "path", "search_query"):
                if key in tool_input:
                    val = str(tool_input[key])[:100]
                    parts.append(f'{key}="{val}"')
                    break
        # Add error summary
        err_short = error_content.split("\n")[0][:120] if error_content else ""
        parts.append(f"→ {err_short}")
        return " ".join(parts)[:300]

    @staticmethod
    def _parse_and_record_confidence(text: str, ctx):
        """Parse confidence scores from think() output and feed to metacognition."""
        match = re.search(r'(?:confidence|conf)[:\s]+(\d{1,3})\s*%?', text, re.IGNORECASE)
        if match:
            score = float(match.group(1))
            if 0 <= score <= 100:
                ctx.metacognition.record_confidence(score)

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
