"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Base Agent: Foundation for All Specialists       ║
╠══════════════════════════════════════════════════════════════╣
║  Every agent (Browser, Coder, System, Research) inherits     ║
║  from this. Provides:                                        ║
║    - Own LLM loop with tool calling                          ║
║    - done / stuck terminal states                            ║
║    - Escalation reporting back to orchestrator               ║
║    - iMessage progress updates                               ║
║    - Step tracking & safety limits                           ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import logging
import re
import time
import subprocess
from abc import ABC, abstractmethod
from utils.event_bus import event_bus

logger = logging.getLogger("TARS")
from utils.agent_monitor import agent_monitor


# ─────────────────────────────────────────────
#  Parse <function>name{...}</function> or <function(name>{...}</function> tags from text
#  Groq Llama uses both formats depending on the run:
#    Format A: <function>done{"summary": "..."}</function>
#    Format B: <function(done>{"summary": "..."}</function>
# ─────────────────────────────────────────────

_FUNCTION_TAG_RE = re.compile(
    r'<function[>(](\w+)>?\s*(\{.*?\})\s*</function>',
    re.DOTALL,
)


def _parse_function_tags(text):
    """
    Parse <function>name{"key":"val"}</function> from agent text output.
    
    Groq Llama sometimes emits tool calls as text instead of proper tool_use.
    Returns list of (name, args_dict) tuples, or empty list if none found.
    """
    results = []
    for m in _FUNCTION_TAG_RE.finditer(text):
        name = m.group(1)
        args_raw = m.group(2)
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            # Llama sometimes escapes single quotes (\') which breaks JSON
            try:
                args = json.loads(args_raw.replace("\\'", "'").replace("\\\\", "\\"))
            except json.JSONDecodeError:
                continue
        results.append((name, args))
    return results


# ─────────────────────────────────────────────
#  iMessage progress helper
# ─────────────────────────────────────────────

def _send_progress(phone, message):
    """Send a short iMessage progress update (bypasses rate limit)."""
    if not phone:
        return
    # Use argv to avoid AppleScript injection — message never enters eval context
    script = f'''
    on run argv
        set msg to item 1 of argv
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{phone}" of targetService
            send msg to targetBuddy
        end tell
    end run
    '''
    try:
        subprocess.run(["osascript", "-e", script, message],
                       capture_output=True, text=True, timeout=10)
    except Exception:
        pass


class BaseAgent(ABC):
    """
    Base class for all TARS specialist agents.

    Subclasses must implement:
      - agent_name       (str)  — Human-readable name like "Browser Agent"
      - agent_emoji       (str)  — Emoji for logs like "🌐"
      - system_prompt     (str)  — The agent's system prompt
      - tools            (list) — Tool definitions (Anthropic schema)
      - _dispatch(name, inp) → str  — Route tool calls to handlers
    """

    def __init__(self, llm_client, model, max_steps=40, phone=None, update_every=3, kill_event=None,
                 fallback_client=None, fallback_model=None):
        self.client = llm_client
        self.model = model
        self.max_steps = max_steps
        self.phone = phone
        self.update_every = update_every
        self._kill_event = kill_event  # Shared threading.Event — set when kill word received
        # Automatic LLM failover: when primary provider dies (spend limit, quota, etc.)
        self._fallback_client = fallback_client
        self._fallback_model = fallback_model
        self._using_fallback = False
        # Session learning scratchpad — persists within this agent's lifetime
        # Records what worked, what failed, and patterns discovered during this session
        self._session_scratchpad = {
            "attempts": [],          # List of {action, result, worked: bool}
            "discovered_selectors": {},  # selector_name → working CSS selector
            "page_patterns": [],     # Observed page patterns (e.g., "form has 3 pages")
            "failed_approaches": [], # Approaches that didn't work (don't retry)
            "working_approaches": [],# Approaches that worked (reuse)
        }

    # ── Abstract properties/methods subclasses must implement ──

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name: 'Browser Agent', 'Coder Agent', etc."""
        ...

    @property
    @abstractmethod
    def agent_emoji(self) -> str:
        """Emoji for logs: '🌐', '💻', '⚙️', '🔍'"""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The agent's specialized system prompt."""
        ...

    @property
    @abstractmethod
    def tools(self) -> list:
        """Tool definitions list (Anthropic tool_use schema)."""
        ...

    @abstractmethod
    def _dispatch(self, name: str, inp: dict) -> str:
        """Route a tool call to the actual handler. Return result as string."""
        ...

    # ── Session Learning — within-session memory ──

    def _record_attempt(self, action, result_str, worked):
        """Record an action attempt for session learning."""
        entry = {
            "action": str(action)[:100],
            "result": str(result_str)[:150],
            "worked": worked,
        }
        self._session_scratchpad["attempts"].append(entry)
        # Keep last 20 attempts
        if len(self._session_scratchpad["attempts"]) > 20:
            self._session_scratchpad["attempts"] = self._session_scratchpad["attempts"][-20:]

        if worked:
            self._session_scratchpad["working_approaches"].append(entry["action"])
        else:
            self._session_scratchpad["failed_approaches"].append(entry["action"])

    def _record_selector(self, name, selector):
        """Remember a working CSS selector for reuse."""
        self._session_scratchpad["discovered_selectors"][name] = selector

    def _record_pattern(self, pattern):
        """Record an observed page pattern."""
        if pattern not in self._session_scratchpad["page_patterns"]:
            self._session_scratchpad["page_patterns"].append(pattern)
            if len(self._session_scratchpad["page_patterns"]) > 10:
                self._session_scratchpad["page_patterns"] = self._session_scratchpad["page_patterns"][-10:]

    def _get_session_context(self):
        """Build a context string from session learnings to inject into the LLM."""
        parts = []
        sp = self._session_scratchpad

        failed = sp.get("failed_approaches", [])
        if failed:
            parts.append("## ❌ Failed approaches (don't retry these):")
            for f in failed[-5:]:
                parts.append(f"  - {f}")

        working = sp.get("working_approaches", [])
        if working:
            parts.append("## ✅ Working approaches (reuse these):")
            for w in working[-5:]:
                parts.append(f"  - {w}")

        selectors = sp.get("discovered_selectors", {})
        if selectors:
            parts.append("## 🎯 Known selectors:")
            for name, sel in list(selectors.items())[-10:]:
                parts.append(f"  - {name}: {sel}")

        patterns = sp.get("page_patterns", [])
        if patterns:
            parts.append("## 📋 Page patterns observed:")
            for p in patterns[-5:]:
                parts.append(f"  - {p}")

        return "\n".join(parts) if parts else ""

    # ── Optional hooks subclasses can override ──

    def _on_start(self, task: str):
        """Called before the agent loop starts. Override for setup (e.g., activate Chrome)."""
        pass

    def _on_step(self, step: int, tool_name: str, tool_result: str):
        """Called after each tool execution. Override for per-step logic."""
        pass

    def _on_done(self, summary: str):
        """Called when agent calls done(). Override for cleanup."""
        pass

    def _on_stuck(self, reason: str):
        """Called when agent calls stuck(). Override for cleanup."""
        pass

    @property
    def _loop_detection_window(self) -> int:
        """How many step-patterns to check for repetition. Override for agents with naturally repetitive patterns (e.g. browser: click→wait→look)."""
        return 3

    @property
    def _loop_detection_repeats(self) -> int:
        """How many full cycles of the same pattern before triggering. Override for browser-like agents."""
        return 3

    def _collect_notes_for_summary(self):
        """Extract saved notes from agent for force-stop summaries.
        
        Works with ResearchAgent's _notes dict and _get_notes() method.
        Returns formatted string of all collected notes, or empty string.
        """
        # Try _get_notes() method first (ResearchAgent has this)
        if hasattr(self, '_get_notes') and callable(self._get_notes):
            try:
                notes = self._get_notes()
                if notes and "No notes yet" not in notes:
                    return notes
            except Exception:
                pass

        # Fallback: read _notes dict directly
        if hasattr(self, '_notes') and self._notes:
            if isinstance(self._notes, dict):
                lines = []
                for key, val in list(self._notes.items())[:20]:
                    if isinstance(val, dict):
                        lines.append(f"- **{key}**: {val.get('value', str(val))[:300]}")
                    else:
                        lines.append(f"- {key}: {str(val)[:300]}")
                return "## Collected Notes\n" + "\n".join(lines)
            elif isinstance(self._notes, list):
                return "## Collected Notes\n" + "\n".join(f"- {n}" for n in self._notes[-15:])

        return ""

    # ── Core agent loop ──

    def _notify(self, msg):
        """Send iMessage progress if phone is configured."""
        _send_progress(self.phone, msg)

    def run(self, task, context=None):
        """
        Execute a task autonomously using the agent's LLM loop.

        Args:
            task: The task description
            context: Optional extra context from the orchestrator brain
                     (e.g., previous agent results, brain guidance on stuck)

        Returns:
            dict with keys:
                success (bool)  — Whether the agent completed the task
                content (str)   — Summary or error message
                steps   (int)   — How many steps were taken
                stuck   (bool)  — Whether the agent got stuck (for escalation)
                stuck_reason (str) — Why it got stuck (if stuck=True)
        """
        logger.info(f"  {self.agent_emoji} {self.agent_name}: {task[:80]}...")
        self._notify(f"{self.agent_emoji} {self.agent_name} starting: {task[:300]}")

        # Let subclass do setup
        self._on_start(task)

        # Build initial message with optional context
        user_content = f"Complete this task:\n\n{task}"
        if context:
            user_content += f"\n\n## Additional Context from Brain\n{context}"

        messages = [{"role": "user", "content": user_content}]

        # Text-only loop detection
        _last_text_hash = None
        _text_repeat_count = 0
        _TEXT_REPEAT_LIMIT = 3  # Force-stop after 3 identical text-only outputs
        _real_tool_dispatches = 0  # Count ACTUAL tool executions (not steps)

        # Tool-call loop detection: track tool names per step to detect cyclic repetition
        _tool_pattern_history = []  # List of tuples: tool names called per step
        _TOOL_LOOP_WINDOW = self._loop_detection_window
        _TOOL_LOOP_REPEATS = self._loop_detection_repeats
        _loop_nudge_sent = False  # Only inject one nudge

        # Dispatch budget: hard cap on total tool dispatches to prevent runaway agents
        _MAX_DISPATCHES = 40  # After this, inject wrap-up nudge
        _MAX_DISPATCHES_HARD = 55  # After this, force-stop
        _dispatch_nudge_sent = False

        # end_turn streak detection: model sends end_turn with no content repeatedly
        # instead of calling done(). After 3 consecutive, auto-call done().
        _end_turn_streak = 0
        _END_TURN_AUTO_DONE = 3  # Auto-done after this many consecutive end_turns

        # Parallel tool cap: limit how many tool_use blocks we execute per step
        # Prevents agent from batching 12-16 calls and burning through dispatch budget
        _MAX_PARALLEL_TOOLS = 6

        # Browser observation-only loop detection: track consecutive observe-only steps
        # (look, scroll, read without any click/type/fill_form action)
        _observe_only_streak = 0
        _OBSERVE_STREAK_LIMIT = 6  # After 6 consecutive observe-only steps, nudge
        _observe_nudge_sent = False

        for step in range(1, self.max_steps + 1):
            logger.debug(f"  🧠 [{self.agent_name}] Step {step}/{self.max_steps}...")
            agent_key = self.agent_name.lower().split()[0]
            event_bus.emit("agent_step", {"agent": agent_key, "step": step})
            agent_monitor.on_step(agent_key, step)

            # ── Kill switch check — abort immediately ──
            if self._kill_event and self._kill_event.is_set():
                msg = f"{self.agent_name} killed by user at step {step}."
                logger.warning(f"  \U0001f6d1 {msg}")
                return {
                    "success": False,
                    "content": msg,
                    "steps": step,
                    "stuck": False,
                    "stuck_reason": "Killed by user",
                }

            # ── Context window management ──
            # After many steps, trim old tool results to prevent context overflow.
            # Keep the first message (task), last 6 messages (recent context), and
            # truncate tool result contents in the middle to summaries.
            _MAX_MESSAGES_BEFORE_TRIM = 20  # ~10 steps × 2 messages each
            if len(messages) > _MAX_MESSAGES_BEFORE_TRIM:
                # Keep first message (original task) and last 6 (3 recent steps)
                # Truncate tool results in the middle, but PRESERVE note results
                for i in range(1, len(messages) - 6):
                    msg = messages[i]
                    if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                        # This is a tool_results list — truncate each result's content
                        for tr in msg["content"]:
                            if isinstance(tr, dict) and tr.get("type") == "tool_result":
                                content = tr.get("content", "")
                                if isinstance(content, str) and len(content) > 500:
                                    # Preserve note results (they contain the agent's findings)
                                    is_note = ("VERIFIED" in content or "HIGH" in content
                                               or "MEDIUM" in content or "NOTE" in content
                                               or "notes |" in content)
                                    if is_note:
                                        continue  # Don't truncate note results
                                    tr["content"] = content[:500] + "... [truncated — data already processed]"

            # ── Inject session learnings at key intervals ──
            # After enough attempts, remind the agent what it's learned
            if step in (8, 15, 25) and _real_tool_dispatches >= 4:
                session_ctx = self._get_session_context()
                if session_ctx:
                    messages.append({"role": "user", "content": f"## 📝 Session Learnings (what you've discovered so far)\n{session_ctx}"})

            # LLM call with retry for transient Groq errors
            response = None
            last_err = None
            # ALWAYS force tool_choice=required for Groq/Llama
            # With "auto", Llama alternates between tool_use and text-only, wasting steps.
            # With "required", it must pick a tool each step — including done() when finished.
            # This is safe because done() and stuck() are in the tool list.
            force_tool = "required"
            logger.info(f"  🔧 [{self.agent_name}] tool_choice={force_tool}, step={step}, dispatches={_real_tool_dispatches}")

            # Try primary client first, then fallback if primary fails hard
            _clients_to_try = [(self.client, self.model, "primary")]
            if self._fallback_client and self._fallback_model:
                _clients_to_try.append((self._fallback_client, self._fallback_model, "fallback"))
            # If already using fallback (switched earlier in this run), put fallback first
            if self._using_fallback:
                _clients_to_try = [(self._fallback_client, self._fallback_model, "fallback")]

            for _cli, _mdl, _label in _clients_to_try:
                response = None
                last_err = None
                for _api_try in range(3):
                    try:
                        response = _cli.create(
                            model=_mdl,
                            max_tokens=4096,
                            system=self.system_prompt,
                            tools=self.tools,
                            messages=messages,
                            tool_choice=force_tool,
                        )
                        break
                    except Exception as e:
                        last_err = e
                        err_str = str(e).lower()
                        # Transient errors — retry with same client
                        if "tool_use_failed" in err_str or "rate_limit" in err_str:
                            import time as _t
                            _t.sleep(1.0 * (_api_try + 1))
                            logger.warning(f"    ⟳ Retrying LLM call ({_api_try + 2}/3) [{_label}]...")
                            continue
                        # Non-transient: spend limit, quota, billing, permission — try fallback
                        _fatal_markers = ("spend_limit", "spend limit", "spend alert",
                                          "quota", "billing", "blocked", "suspended",
                                          "api key expired", "permission_denied",
                                          "insufficient_quota", "account")
                        if any(m in err_str for m in _fatal_markers):
                            logger.warning(f"  💀 [{self.agent_name}] {_label} provider dead: {str(last_err)[:150]}")
                            break  # Break retry loop, fall through to next client
                        break  # Other non-transient error, stop retrying

                if response is not None:
                    # If we succeeded on fallback, remember for remaining steps
                    if _label == "fallback" and not self._using_fallback:
                        self._using_fallback = True
                        logger.info(f"  🔄 [{self.agent_name}] Switched to fallback provider for remaining steps")
                        event_bus.emit("agent_failover", {
                            "agent": self.agent_name,
                            "reason": str(last_err)[:200] if last_err else "primary failed",
                        })
                    break  # Got a response, proceed

            if response is None:
                err = f"API error: {last_err}"
                logger.warning(f"  ❌ {err}")
                self._notify(f"❌ {self.agent_name} API error: {str(last_err)[:200]}")
                # Record agent API failure for pattern learning
                try:
                    from memory.error_tracker import error_tracker
                    error_tracker.record_error(
                        error=f"Agent LLM API failed: {last_err}",
                        context=f"agent_{self.agent_name}",
                        tool="llm_call",
                        agent=self.agent_name,
                        source_file="agents/base_agent.py",
                        details=f"All LLM providers failed at step {step}",
                        params={"agent": self.agent_name, "step": step, "task": task[:200]},
                    )
                except Exception:
                    pass  # Don't let tracker errors crash the agent
                return {
                    "success": False,
                    "content": err,
                    "steps": step,
                    "stuck": True,
                    "stuck_reason": f"LLM API call failed: {last_err}",
                }

            assistant_content = response.content
            tool_results = []

            # Diagnostic: log response shape
            block_types = [b.type for b in assistant_content]
            tool_names = [b.name for b in assistant_content if b.type == "tool_use"]
            logger.info(f"  📨 [{self.agent_name}] Response: stop={response.stop_reason}, blocks={block_types}, tools={tool_names}")

            _tool_use_count_this_step = 0
            _skipped_tools = []
            
            # Pre-scan: if the last tool is a verification tool (look/read/url),
            # prioritize it by reducing cap by 1 so it always fits within budget.
            # This prevents the agent's verification step from being skipped.
            _verification_tools = {"look", "read", "url", "screenshot"}
            _effective_cap = _MAX_PARALLEL_TOOLS
            _tool_blocks = [b for b in assistant_content if b.type == "tool_use"]
            if len(_tool_blocks) > _MAX_PARALLEL_TOOLS:
                # Check if last tool is a verification tool
                last_tool = _tool_blocks[-1].name if _tool_blocks else ""
                if last_tool in _verification_tools:
                    # We'll skip earlier non-essential tools to keep the verify step
                    _effective_cap = _MAX_PARALLEL_TOOLS - 1  # Reserve 1 slot for verification
                    
            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    logger.debug(f"    💭 {block.text[:200]}")

                elif block.type == "tool_use":
                    is_verify = block.name in _verification_tools
                    is_terminal = block.name in ("done", "stuck")
                    
                    # Cap parallel tool calls per step
                    # But always allow: terminal tools (done/stuck) and the final verification tool
                    if not is_terminal and not is_verify and _tool_use_count_this_step >= _effective_cap:
                        _skipped_tools.append(block.name)
                        # Still need to return a tool_result for the API
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "SKIPPED: Too many parallel tool calls this step. This call was not executed. Reduce parallel calls — use at most 4-5 tools per step.",
                        })
                        continue
                    # Hard cap: even verification tools can't exceed total budget
                    if not is_terminal and _tool_use_count_this_step >= _MAX_PARALLEL_TOOLS + 1:
                        _skipped_tools.append(block.name)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "SKIPPED: Exceeded max parallel tool calls.",
                        })
                        continue
                    name = block.name
                    inp = block.input
                    tid = block.id

                    # ── Terminal tool: done ──
                    if name == "done":
                        summary = inp.get("summary", "Done.")

                        # Anti-hallucination: require minimum real tool usage
                        min_dispatches = 2
                        vague_summaries = [
                            "done", "done.", "completed", "completed.",
                            "task completed", "task completed.",
                            "task is complete", "task is complete.",
                        ]
                        is_vague = (
                            summary.strip().lower() in vague_summaries
                            or len(summary.strip()) < 15
                        )

                        # Reject if: zero real tools used, OR (few tools AND vague summary)
                        if _real_tool_dispatches == 0 or (_real_tool_dispatches < min_dispatches and is_vague):
                            # Reject — force agent to actually do work
                            logger.warning(f"  ⚠️ [{self.agent_name}] Rejected premature done (only {_real_tool_dispatches} real tool calls, vague summary)")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": (
                                    f"REJECTED: You called done() without actually completing the task. "
                                    f"You have only dispatched {_real_tool_dispatches} real tool(s). You MUST use your tools to "
                                    f"actually perform the task — do not just claim it is done. "
                                    f"Start by using your tools (web_search, wiki_search, etc.) to take real action, "
                                    f"then call done() with a SPECIFIC summary of what you actually found "
                                    f"(include details like URLs visited, data points found, facts verified)."
                                ),
                            })
                            continue

                        # Self-verification for browser agents: check if the summary
                        # actually indicates task completion, not just page loading
                        is_browser = "browser" in self.agent_name.lower()
                        if is_browser and _real_tool_dispatches >= 3:
                            summary_lower = summary.lower()
                            # Check for false success claims
                            failure_signals = [
                                "could not", "couldn't", "unable to", "failed to",
                                "not found", "doesn't exist", "does not exist",
                                "error occurred", "page not loading",
                                "still on the same page", "no progress",
                            ]
                            has_failure = any(sig in summary_lower for sig in failure_signals)

                            # Require evidence of actual completion
                            evidence_signals = [
                                "account created", "signed up", "logged in",
                                "dashboard", "welcome", "profile", "home page",
                                "api key", "credentials", "successfully",
                                "confirmed", "verified", "registered",
                                "already logged in", "already exists",
                                "copied", "saved", "downloaded", "extracted",
                                "form submitted", "submitted successfully",
                            ]
                            has_evidence = any(sig in summary_lower for sig in evidence_signals)

                            if has_failure and not has_evidence:
                                # This is actually a failure report — convert to stuck
                                logger.info(f"  🔄 [{self.agent_name}] done() contains failure signals — converting to result")
                                # Still allow it through, but flag it
                                self._on_done(summary)
                                return {
                                    "success": False,
                                    "content": summary,
                                    "steps": step,
                                    "stuck": True,
                                    "stuck_reason": summary[:300],
                                }
                            # Fall through to normal done() success path below

                        logger.info(f"  ✅ [{self.agent_name}] Done: {summary[:200]}")
                        self._notify(f"✅ {self.agent_name} done: {summary[:500]}")
                        self._on_done(summary)
                        return {
                            "success": True,
                            "content": summary,
                            "steps": step,
                            "stuck": False,
                            "stuck_reason": None,
                        }

                    # ── Terminal tool: stuck ──
                    if name == "stuck":
                        reason = inp.get("reason", "Unknown reason.")

                        # OTP/confirmation guard: if the agent mentions email/code/confirmation,
                        # it's on a verification page — redirect to read_otp instead of giving up
                        reason_lower = reason.lower()
                        otp_keywords = [
                            "sent you an email", "confirmation code", "verification code",
                            "enter the code", "enter code", "check your email",
                            "we sent", "code was sent", "confirm your",
                            "email with a link", "security code",
                        ]
                        has_otp_context = any(kw in reason_lower for kw in otp_keywords)
                        is_browser = "browser" in self.agent_name.lower()

                        if has_otp_context and is_browser and step < 35:
                            logger.info(f"  🔄 [{self.agent_name}] Rejected stuck() — OTP/confirmation context detected. Redirecting to read_otp.")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": (
                                    "REJECTED: You are on a verification/confirmation code page — this is PROGRESS, not stuck! "
                                    "The page says an email was sent. You MUST call read_otp(subject_contains='Instagram', timeout=90) "
                                    "to retrieve the code from Mac Mail. Then type the code into the input field and click Confirm/Next. "
                                    "Do NOT call stuck() when you see a confirmation code page — USE read_otp() to get the code."
                                ),
                            })
                            continue

                        logger.warning(f"  ❌ [{self.agent_name}] Stuck: {reason[:200]}")
                        self._notify(f"⚠️ {self.agent_name} stuck: {reason[:500]}")
                        self._on_stuck(reason)
                        # Record agent stuck for pattern learning
                        try:
                            from memory.error_tracker import error_tracker
                            error_tracker.record_error(
                                error=f"Agent stuck: {reason}",
                                context=f"agent_{self.agent_name}",
                                tool="stuck",
                                agent=self.agent_name,
                                source_file="agents/base_agent.py",
                                details=f"Agent called stuck() at step {step}",
                                params={"agent": self.agent_name, "step": step, "task": task[:200], "reason": reason[:300]},
                            )
                        except Exception:
                            pass
                        return {
                            "success": False,
                            "content": f"Stuck: {reason}",
                            "steps": step,
                            "stuck": True,
                            "stuck_reason": reason,
                        }

                    # ── Regular tool: dispatch ──
                    inp_short = json.dumps(inp)[:120]
                    logger.debug(f"    🔧 {name}({inp_short})")
                    result = self._dispatch(name, inp)
                    _real_tool_dispatches += 1
                    _tool_use_count_this_step += 1

                    # Handle screenshot results with vision data
                    if isinstance(result, dict) and result.get("_screenshot"):
                        # Build a tool result with both text and image for vision models
                        # LLM client will pick up _image_base64 and convert to inline image
                        result_str = result.get("text", "Screenshot captured")
                        tool_result_entry = {
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": result_str,
                        }
                        # Attach image data — LLM client will convert for vision-capable models
                        img_b64 = result.get("image_base64", "")
                        if img_b64:
                            tool_result_entry["_image_base64"] = img_b64
                            tool_result_entry["_image_mime"] = "image/jpeg"
                        tool_results.append(tool_result_entry)
                        logger.debug(f"      → {result_str[:200]} [+screenshot image]")
                    else:
                        result_str = str(result)[:8000]
                        logger.debug(f"      → {result_str[:200]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": result_str,
                        })

                    # Callback
                    self._on_step(step, name, str(result)[:8000] if not isinstance(result, dict) else result.get("text", str(result))[:8000])

                    # Session learning: track what worked and what failed
                    is_error = isinstance(result_str, str) and ("ERROR" in result_str or "FAILED" in result_str)
                    self._record_attempt(f"{name}({inp_short})", result_str[:100], not is_error)

                    # Periodic progress update
                    if step % self.update_every == 0:
                        short = result_str[:200] + ("..." if len(result_str) > 200 else "")
                        self._notify(f"{self.agent_emoji} Step {step}: {name}\n→ {short}")

            # Log skipped tools
            if _skipped_tools:
                logger.info(f"  ⚡ [{self.agent_name}] Capped parallel tools: executed {_tool_use_count_this_step}, skipped {len(_skipped_tools)} ({', '.join(_skipped_tools[:5])})")

            # ── Dispatch budget check ──
            if _real_tool_dispatches >= _MAX_DISPATCHES_HARD:
                logger.warning(f"  🛑 [{self.agent_name}] Hard dispatch limit ({_MAX_DISPATCHES_HARD}) reached. Force-stopping.")
                notes_content = self._collect_notes_for_summary()
                force_summary = (
                    f"Research completed ({_real_tool_dispatches} tool calls across {step} steps). "
                    f"Dispatch budget exhausted — force-stopped."
                )
                if notes_content:
                    force_summary += f"\n\n{notes_content}"
                return {
                    "success": True,
                    "content": force_summary,
                    "steps": step,
                    "stuck": False,
                    "stuck_reason": None,
                }

            if _real_tool_dispatches >= _MAX_DISPATCHES and not _dispatch_nudge_sent:
                _dispatch_nudge_sent = True
                logger.warning(f"  ⚠️ [{self.agent_name}] Dispatch budget warning ({_real_tool_dispatches}/{_MAX_DISPATCHES_HARD}). Injecting wrap-up nudge.")
                if tool_results:
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                messages.append({"role": "user", "content": (
                    f"⚠️ DISPATCH BUDGET: You have used {_real_tool_dispatches} of {_MAX_DISPATCHES_HARD} max tool calls. "
                    f"You MUST call done(summary) NOW with a detailed summary of everything you found. "
                    f"Include ALL specific data points, numbers, and facts. Do NOT make any more search calls."
                )})
                continue

            # ── Browser observation-only streak detection ──
            # If the agent is doing nothing but look/scroll/read for many consecutive
            # steps without any action (click/type/fill_form/goto), it's aimlessly
            # exploring. Nudge it to take action or call done().
            if "browser" in self.agent_name.lower() and tool_names:
                _observe_tools = {"look", "scroll", "read", "screenshot", "url"}
                _action_tools_used = [t for t in tool_names if t not in _observe_tools]
                if _action_tools_used:
                    _observe_only_streak = 0  # Reset: agent took an action
                else:
                    _observe_only_streak += 1

                if _observe_only_streak >= _OBSERVE_STREAK_LIMIT and not _observe_nudge_sent:
                    _observe_nudge_sent = True
                    logger.warning(f"  ⚠️ [{self.agent_name}] {_observe_only_streak} consecutive observe-only steps (no clicks/typing). Nudging.")
                    if tool_results:
                        messages.append({"role": "assistant", "content": assistant_content})
                        messages.append({"role": "user", "content": tool_results})
                    messages.append({"role": "user", "content": (
                        f"⚠️ OBSERVATION LOOP: You have spent {_observe_only_streak} consecutive steps only looking/scrolling "
                        f"without taking any action (click, type, fill_form). You MUST either:\n"
                        f"1. TAKE ACTION — click a button, fill a form, navigate somewhere specific\n"
                        f"2. CONCLUDE — if what you need isn't on this page, call done() with what you found\n"
                        f"3. TRY A DIFFERENT URL — if this page doesn't have what you need, use goto() to try a different page\n"
                        f"Do NOT keep scrolling and looking at the same page. Make a DECISION now."
                    )})
                    continue

            # ── Tool-call loop detection ──
            # Track the set of tool names called this step
            step_tools = tuple(sorted(tool_names))  # tool_names set from diagnostic logging above
            if step_tools:
                _tool_pattern_history.append(step_tools)

            # Check for cyclic repetition (e.g. stock_quote→finance_search→web_search repeated 3x)
            if len(_tool_pattern_history) >= _TOOL_LOOP_WINDOW * _TOOL_LOOP_REPEATS:
                window = _tool_pattern_history[-_TOOL_LOOP_WINDOW:]
                # Check if this window has appeared before
                cycle_count = 0
                for i in range(len(_tool_pattern_history) - _TOOL_LOOP_WINDOW, -1, -_TOOL_LOOP_WINDOW):
                    if i < 0:
                        break
                    past_window = _tool_pattern_history[i:i + _TOOL_LOOP_WINDOW]
                    if past_window == window:
                        cycle_count += 1
                    else:
                        break

                if cycle_count >= _TOOL_LOOP_REPEATS - 1:
                    if _loop_nudge_sent:
                        # Already nudged once and still looping — force-stop with best-effort summary
                        logger.warning(f"  🛑 [{self.agent_name}] Tool loop persists after nudge. Force-stopping at step {step}.")
                        notes_content = self._collect_notes_for_summary()
                        force_summary = (
                            f"Research completed ({_real_tool_dispatches} tool calls across {step} steps). "
                            f"Agent was force-stopped due to tool loop detection. "
                            f"Data was gathered but agent failed to compile a summary."
                        )
                        if notes_content:
                            force_summary += f"\n\n{notes_content}"
                        return {
                            "success": True,
                            "content": force_summary,
                            "steps": step,
                            "stuck": False,
                            "stuck_reason": None,
                        }

                    logger.warning(f"  🔄 [{self.agent_name}] Tool loop detected! Same {_TOOL_LOOP_WINDOW}-step pattern repeated {cycle_count + 1}x. Injecting wrap-up nudge.")
                    _loop_nudge_sent = True
                    _tool_pattern_history.clear()  # Reset so force-stop triggers after just 1 more cycle
                    _TOOL_LOOP_REPEATS = 2  # Lower threshold for force-stop after nudge
                    # Append tool results collected so far, then inject nudge
                    if tool_results:
                        messages.append({"role": "assistant", "content": assistant_content})
                        messages.append({"role": "user", "content": tool_results})
                    # Browser agents should try different approaches, not wrap up
                    if "browser" in self.agent_name.lower():
                        messages.append({"role": "user", "content": (
                            f"⚠️ LOOP DETECTED: You are repeating the same actions in a cycle ({_real_tool_dispatches} tool calls). "
                            f"Your current approach is NOT working. You MUST try something DIFFERENT:\n"
                            f"- If a button click does nothing: scroll('down') first — the button may need to be visible, or try a different button text\n"
                            f"- If you're stuck on a form: look() to check for error messages you missed\n"
                            f"- If you need a verification code: call read_otp(subject_contains='...') to get it from email\n"
                            f"- NEVER navigate back to the starting URL — you will lose all progress\n"
                            f"- If truly stuck after trying all alternatives: call stuck() with details"
                        )})
                    else:
                        messages.append({"role": "user", "content": (
                            "⚠️ IMPORTANT: You are repeating the same tools in a loop. You have already gathered "
                            f"sufficient data ({_real_tool_dispatches} tool calls completed). "
                            "STOP gathering more data and call done(summary) NOW with a detailed summary of "
                            "everything you found. Include specific numbers, facts, and data points in your summary."
                        )})
                    continue

            # No tool calls — check for text-only loop or <function> tags
            if not tool_results:

                if response.stop_reason == "end_turn":
                    _end_turn_streak += 1
                    texts = [b.text for b in assistant_content if b.type == "text"]
                    txt = " ".join(texts).strip()

                    # ── end_turn streak auto-done ──
                    # Model keeps sending end_turn (no content, no tools) instead of
                    # calling done(). After N consecutive end_turns with real work done,
                    # auto-complete — the agent clearly thinks it's finished.
                    if _end_turn_streak >= _END_TURN_AUTO_DONE and _real_tool_dispatches >= 8:
                        auto_summary = txt if txt else f"Task completed ({_real_tool_dispatches} actions taken). Agent signaled completion {_end_turn_streak} times."
                        logger.info(f"  ✅ [{self.agent_name}] Auto-done (end_turn streak ×{_end_turn_streak} after {_real_tool_dispatches} dispatches)")
                        self._notify(f"✅ {self.agent_name} done (auto): {auto_summary[:500]}")
                        self._on_done(auto_summary)
                        return {
                            "success": True,
                            "content": auto_summary[:3000],
                            "steps": step,
                            "stuck": False,
                            "stuck_reason": None,
                        }
                    if txt:
                        logger.warning(f"  ⚠️ [{self.agent_name}] Text-only: {txt[:200]}")

                        # ── Parse <function>name{...}</function> tags from text ──
                        parsed_calls = _parse_function_tags(txt)
                        _rejected_premature = False
                        _parsed_tool_results = []
                        if parsed_calls:
                            for fn_name, fn_args in parsed_calls:
                                # Handle done() from text
                                if fn_name == "done":
                                    summary = fn_args.get("summary", "Done.")

                                    # Anti-hallucination: same check as proper tool_use done()
                                    min_dispatches = 2
                                    vague_summaries = [
                                        "done", "done.", "completed", "completed.",
                                        "task completed", "task completed.",
                                        "task is complete", "task is complete.",
                                    ]
                                    is_vague = (
                                        summary.strip().lower() in vague_summaries
                                        or len(summary.strip()) < 15
                                    )
                                    if _real_tool_dispatches == 0 or (_real_tool_dispatches < min_dispatches and is_vague):
                                        logger.warning(f"  ⚠️ [{self.agent_name}] Rejected premature done from text (only {_real_tool_dispatches} real tool calls)")
                                        messages.append({"role": "assistant", "content": assistant_content})
                                        messages.append({
                                            "role": "user",
                                            "content": (
                                                f"REJECTED: You called done() without actually completing the task. "
                                                f"You have dispatched {_real_tool_dispatches} real tool(s) but need at least {min_dispatches}. "
                                                f"You MUST call your tools (web_search, wiki_search, stock_quote, etc.) to "
                                                f"gather real data BEFORE calling done(). Do NOT answer from memory. "
                                                f"Start by calling web_search or wiki_search now."
                                            ),
                                        })
                                        _rejected_premature = True
                                        break  # break out of parsed_calls loop

                                    logger.info(f"  ✅ [{self.agent_name}] Done (parsed from text): {summary[:200]}")
                                    self._notify(f"✅ {self.agent_name} done: {summary[:500]}")
                                    self._on_done(summary)
                                    return {
                                        "success": True,
                                        "content": summary,
                                        "steps": step,
                                        "stuck": False,
                                        "stuck_reason": None,
                                    }
                                # Handle stuck() from text
                                elif fn_name == "stuck":
                                    reason = fn_args.get("reason", "Unknown reason.")
                                    logger.warning(f"  ❌ [{self.agent_name}] Stuck (parsed from text): {reason[:200]}")
                                    self._notify(f"⚠️ {self.agent_name} stuck: {reason[:500]}")
                                    self._on_stuck(reason)
                                    return {
                                        "success": False,
                                        "content": f"Stuck: {reason}",
                                        "steps": step,
                                        "stuck": True,
                                        "stuck_reason": reason,
                                    }
                                # Handle regular tools from text (web_search, note, etc.)
                                else:
                                    logger.info(f"    🔧 [{self.agent_name}] Dispatching from text: {fn_name}({json.dumps(fn_args)[:100]})")
                                    try:
                                        result = self._dispatch(fn_name, fn_args)
                                        result_str = str(result)[:8000]
                                        _real_tool_dispatches += 1
                                        _parsed_tool_results.append(f"Tool {fn_name} result: {result_str}")
                                        logger.debug(f"      → {result_str[:200]}")
                                    except Exception as e:
                                        _parsed_tool_results.append(f"Tool {fn_name} error: {e}")
                                        logger.warning(f"    ❌ Text-parsed tool {fn_name} failed: {e}")

                        # If we dispatched tools from text, feed results back
                        if _parsed_tool_results:
                            messages.append({"role": "assistant", "content": assistant_content})
                            messages.append({
                                "role": "user",
                                "content": "Tool results from your previous request:\n\n" + "\n\n".join(_parsed_tool_results) + "\n\nContinue working on the task. Use your tools to gather more data, then call done(summary) when finished.",
                            })
                            continue

                        # If premature done was rejected, continue to next step
                        if _rejected_premature:
                            continue

                        # ── Text-only loop detection ──
                        txt_hash = hash(txt[:500])
                        if txt_hash == _last_text_hash:
                            _text_repeat_count += 1
                        else:
                            _text_repeat_count = 1
                            _last_text_hash = txt_hash

                        if _text_repeat_count >= _TEXT_REPEAT_LIMIT:
                            msg = (
                                f"{self.agent_name} stuck in text-only loop "
                                f"(same output {_text_repeat_count}x). Force-stopping."
                            )
                            logger.warning(f"  🔄 {msg}")
                            self._notify(f"⚠️ {msg}")
                            # Return best-effort: use the repeated text as content
                            return {
                                "success": True,
                                "content": txt[:2000],
                                "steps": step,
                                "stuck": False,
                                "stuck_reason": None,
                            }

                        # ── Auto-done: text-only response that IS the conclusion ──
                        # If the agent has done real work (10+ dispatches) and emits
                        # a substantive text response (not just chatter), treat it as done().
                        # This prevents wasting 2+ more steps after the agent already answered.
                        _conclusion_signals = [
                            "does not have", "doesn't have", "no direct",
                            "not possible", "cannot", "can't", "unable to",
                            "no way to", "not available", "is not supported",
                            "i found that", "i've found", "here is what",
                            "here's what", "the result", "in summary",
                            "in conclusion", "to summarize", "my findings",
                            "the page does not", "there is no",
                            "unfortunately", "i was unable", "i could not",
                            "completed the", "successfully", "here are the",
                            "i have completed", "task is done",
                        ]
                        txt_lower = txt.lower()
                        has_conclusion = any(sig in txt_lower for sig in _conclusion_signals)
                        is_substantive = len(txt) >= 80  # Not a short fragment

                        if has_conclusion and is_substantive and _real_tool_dispatches >= 8:
                            logger.info(f"  ✅ [{self.agent_name}] Auto-done (text conclusion after {_real_tool_dispatches} dispatches): {txt[:200]}")
                            self._notify(f"✅ {self.agent_name} done: {txt[:500]}")
                            self._on_done(txt)
                            return {
                                "success": True,
                                "content": txt[:3000],
                                "steps": step,
                                "stuck": False,
                                "stuck_reason": None,
                            }

                    messages.append({"role": "assistant", "content": assistant_content})
                    if _end_turn_streak >= 2 and _real_tool_dispatches >= 5:
                        # Model has tried to stop multiple times — strongly nudge done()
                        messages.append({
                            "role": "user",
                            "content": (
                                f"You have tried to end your turn {_end_turn_streak} times. "
                                "If you have completed the task, you MUST call the done() tool "
                                "with a summary of what you accomplished. Example: done(summary=\"Created repo and configured settings\"). "
                                "If you are stuck, call stuck(reason). Do NOT just end your turn — call done() or stuck()."
                            ),
                        })
                    else:
                        messages.append({
                            "role": "user",
                            "content": (
                                "You MUST use a tool now. If you have finished the task or determined "
                                "it cannot be completed, call done(summary) with your findings. "
                                "If stuck, call stuck(reason). Otherwise, call your next tool."
                            ),
                        })
                    continue

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})
            _end_turn_streak = 0  # Reset — model used tools successfully

        # Max steps exhausted
        msg = f"{self.agent_name} reached {self.max_steps} steps without finishing. Task may be partially complete."
        logger.warning(f"  ⏱️ {msg}")
        self._notify(f"⏱️ {msg}")
        return {
            "success": False,
            "content": msg,
            "steps": self.max_steps,
            "stuck": True,
            "stuck_reason": f"Reached max {self.max_steps} steps",
        }
