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

    def __init__(self, llm_client, model, max_steps=40, phone=None, update_every=3, kill_event=None):
        self.client = llm_client
        self.model = model
        self.max_steps = max_steps
        self.phone = phone
        self.update_every = update_every
        self._kill_event = kill_event  # Shared threading.Event — set when kill word received

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

            # LLM call with retry for transient Groq errors
            response = None
            last_err = None
            for _api_try in range(3):
                try:
                    response = self.client.create(
                        model=self.model,
                        max_tokens=4096,
                        system=self.system_prompt,
                        tools=self.tools,
                        messages=messages,
                    )
                    break
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    # Groq tool_use_failed is transient — retry
                    if "tool_use_failed" in err_str or "rate_limit" in err_str.lower():
                        import time as _t
                        _t.sleep(1.0 * (_api_try + 1))
                        logger.warning(f"    ⟳ Retrying LLM call ({_api_try + 2}/3)...")
                        continue
                    break  # Non-transient error, stop retrying

            if response is None:
                err = f"API error: {last_err}"
                logger.warning(f"  ❌ {err}")
                self._notify(f"❌ {self.agent_name} API error: {str(last_err)[:200]}")
                return {
                    "success": False,
                    "content": err,
                    "steps": step,
                    "stuck": True,
                    "stuck_reason": f"LLM API call failed: {last_err}",
                }

            assistant_content = response.content
            tool_results = []

            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    logger.debug(f"    💭 {block.text[:200]}")

                elif block.type == "tool_use":
                    name = block.name
                    inp = block.input
                    tid = block.id

                    # ── Terminal tool: done ──
                    if name == "done":
                        summary = inp.get("summary", "Done.")

                        # Anti-hallucination: require minimum real tool usage
                        real_tool_steps = step - 1  # subtract this done call
                        min_steps = 2
                        vague_summaries = [
                            "done", "done.", "completed", "completed.",
                            "task completed", "task completed.",
                            "task is complete", "task is complete.",
                        ]
                        is_vague = (
                            summary.strip().lower() in vague_summaries
                            or len(summary.strip()) < 15
                        )

                        if real_tool_steps < min_steps and is_vague:
                            # Reject — force agent to actually do work
                            logger.warning(f"  ⚠️ [{self.agent_name}] Rejected premature done (only {real_tool_steps} real steps, vague summary)")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": (
                                    f"REJECTED: You called done() without actually completing the task. "
                                    f"You have only used {real_tool_steps} tool(s). You MUST use your tools to "
                                    f"actually perform the task — do not just claim it is done. "
                                    f"Start by using your tools to take real action on the task, "
                                    f"then call done() with a SPECIFIC summary of what you actually did "
                                    f"(include details like URLs visited, fields filled, results seen)."
                                ),
                            })
                            continue

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
                        logger.warning(f"  ❌ [{self.agent_name}] Stuck: {reason[:200]}")
                        self._notify(f"⚠️ {self.agent_name} stuck: {reason[:500]}")
                        self._on_stuck(reason)
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
                    result_str = str(result)[:8000]
                    logger.debug(f"      → {result_str[:200]}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "content": result_str,
                    })

                    # Callback
                    self._on_step(step, name, result_str)

                    # Periodic progress update
                    if step % self.update_every == 0:
                        short = result_str[:200] + ("..." if len(result_str) > 200 else "")
                        self._notify(f"{self.agent_emoji} Step {step}: {name}\n→ {short}")

            # No tool calls — check for text-only loop or <function> tags
            if not tool_results:
                if response.stop_reason == "end_turn":
                    texts = [b.text for b in assistant_content if b.type == "text"]
                    txt = " ".join(texts).strip()
                    if txt:
                        logger.warning(f"  ⚠️ [{self.agent_name}] Text-only: {txt[:200]}")

                        # ── Parse <function>name{...}</function> tags from text ──
                        parsed_calls = _parse_function_tags(txt)
                        _rejected_premature = False
                        if parsed_calls:
                            for fn_name, fn_args in parsed_calls:
                                # Handle done() from text
                                if fn_name == "done":
                                    summary = fn_args.get("summary", "Done.")

                                    # Anti-hallucination: same check as proper tool_use done()
                                    real_tool_steps = step - 1
                                    vague_summaries = [
                                        "done", "done.", "completed", "completed.",
                                        "task completed", "task completed.",
                                        "task is complete", "task is complete.",
                                    ]
                                    is_vague = (
                                        summary.strip().lower() in vague_summaries
                                        or len(summary.strip()) < 15
                                    )
                                    if real_tool_steps < 2 and is_vague:
                                        logger.warning(f"  ⚠️ [{self.agent_name}] Rejected premature done from text (only {real_tool_steps} real steps)")
                                        messages.append({"role": "assistant", "content": assistant_content})
                                        messages.append({
                                            "role": "user",
                                            "content": (
                                                f"REJECTED: You called done() without actually completing the task. "
                                                f"You have only used {real_tool_steps} tool(s). Use your tools to "
                                                f"actually perform the task first, then call done() with specifics."
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
                                if fn_name == "stuck":
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

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({
                        "role": "user",
                        "content": "Use a tool to take action. If you're done, call done(summary). If stuck, call stuck(reason)."
                    })
                    continue

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

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
