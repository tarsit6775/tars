"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Browser Agent: Autonomous Browser Brain          ║
╠══════════════════════════════════════════════════════════════╣
║  A sub-agent with its own LLM loop that controls Chrome      ║
║  via CDP (Chrome DevTools Protocol) — direct websocket.      ║
║                                                              ║
║  No cliclick. No screen coordinates. No monitor bugs.        ║
║  Clicks by selector/text. Types via native input pipeline.   ║
║  Works on any screen setup, any window position.             ║
║                                                              ║
║  Sends iMessage progress updates so user sees what's         ║
║  happening in real time.                                     ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import time

from agents.base_agent import _send_progress
from hands.browser import (
    act_goto, act_google, act_read_page, act_read_url,
    act_inspect_page, act_fill, act_click, act_select_option,
    act_press_key, act_scroll, act_get_tabs, act_switch_tab,
    act_close_tab, act_new_tab, act_back, act_forward,
    act_refresh, act_wait, act_wait_for_text, act_run_js,
    act_screenshot, act_handle_dialog, _detect_challenge,
    _activate_chrome, web_search,
    act_press_and_hold, act_solve_captcha,
)


# ─────────────────────────────────────────────
#  Tool Definitions — Simple, Human-Like
# ─────────────────────────────────────────────

BROWSER_TOOLS = [
    {
        "name": "look",
        "description": "Look at the current page. Shows all visible fields, buttons, dropdowns, links, and checkboxes with their selectors. ALWAYS do this first before interacting with any page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "goto",
        "description": "Navigate to a URL.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    },
    {
        "name": "click",
        "description": "Physically click on something. Pass either the visible text of a button/link (e.g. 'Next', 'Sign in') or a CSS selector (e.g. '#submit', '.btn'). Uses real mouse click.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string", "description": "Button/link text like 'Next' or CSS selector like '#myBtn'"}}, "required": ["target"]}
    },
    {
        "name": "type",
        "description": "Click on a field and type text into it physically. Like a human: clicks the field, clears it, types the value.",
        "input_schema": {"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector of the field from 'look' output, e.g. '#firstName', '[name=email]'"}, "text": {"type": "string", "description": "The text to type"}}, "required": ["selector", "text"]}
    },
    {
        "name": "select",
        "description": "Select an option from ANY dropdown (standard or custom/Material). Clicks the dropdown to open it, then clicks the option. Works with all frameworks.",
        "input_schema": {"type": "object", "properties": {"dropdown": {"type": "string", "description": "The dropdown label text (e.g. 'Month', 'Gender') or CSS selector (e.g. '#month')"}, "option": {"type": "string", "description": "The option text to select (e.g. 'June', 'Male')"}}, "required": ["dropdown", "option"]}
    },
    {
        "name": "key",
        "description": "Press a keyboard key: enter, tab, escape, up, down, left, right, space, backspace, etc.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    },
    {
        "name": "scroll",
        "description": "Scroll the page: up, down, top, bottom.",
        "input_schema": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down", "top", "bottom"], "default": "down"}}}
    },
    {
        "name": "read",
        "description": "Read all visible text on the page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "url",
        "description": "Get the current page URL and title.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "wait",
        "description": "Wait N seconds for page to load or transition.",
        "input_schema": {"type": "object", "properties": {"seconds": {"type": "integer", "default": 2}}}
    },
    {
        "name": "wait_for",
        "description": "Wait for specific text to appear on the page (up to 10s).",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    },
    {
        "name": "tabs",
        "description": "List all open browser tabs.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "switch_tab",
        "description": "Switch to a specific tab by number.",
        "input_schema": {"type": "object", "properties": {"number": {"type": "integer"}}, "required": ["number"]}
    },
    {
        "name": "close_tab",
        "description": "Close the current tab.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "back",
        "description": "Go back to the previous page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "forward",
        "description": "Go forward.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "refresh",
        "description": "Reload the current page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "screenshot",
        "description": "Take a screenshot of the screen for visual inspection.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "js",
        "description": "Run custom JavaScript for reading page info. READ-ONLY — never use this to click or modify the page. Use 'return' to get values.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
    },
    {
        "name": "hold",
        "description": "Press and hold an element for N seconds. For CAPTCHA 'press and hold' buttons. Use target='captcha' to auto-detect the CAPTCHA button position.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string", "description": "Element text, CSS selector, or 'captcha' for auto-detect", "default": "captcha"}, "duration": {"type": "integer", "description": "Seconds to hold (default 10)", "default": 10}}, "required": ["target"]}
    },
    {
        "name": "solve_captcha",
        "description": "Auto-detect and solve CAPTCHA on the current page. Handles 'press and hold' CAPTCHAs automatically. Call this when you see 'Press and hold' or 'prove you're human' text.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "done",
        "description": "Task is complete. Provide a summary of what was accomplished.",
        "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
    },
    {
        "name": "stuck",
        "description": "Cannot complete the task after trying multiple approaches. Explain why.",
        "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}
    },
]


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

BROWSER_AGENT_PROMPT = """You are TARS Browser Agent — you control Google Chrome via CDP (Chrome DevTools Protocol).

## ABSOLUTE RULE: ONE TOOL CALL PER STEP
You MUST call exactly ONE tool per response. Never batch multiple tools.
The cycle is: look → (one action) → look → (one action) → ...

## CRITICAL RULE: USE THE EXACT VALUES FROM YOUR TASK
Your task contains specific emails, passwords, names, and URLs. Use EXACTLY those values.
NEVER substitute your own values. If the task says "type tarsmacbot2026@outlook.com", type exactly that.

## CRITICAL RULE: ONLY USE SELECTORS FROM `look` OUTPUT
NEVER guess selector names. Use EXACTLY what `look` showed you.
Modern pages use generated IDs like #floatingLabelInput4 — you MUST read `look` first.

## Step-by-Step Workflow
1. `look` → see what fields/buttons are on the page
2. ONE action: `type` into a field, or `click` a button, or `select` a dropdown
3. `wait` 2 seconds
4. `look` again → see the updated page
5. Repeat

## Clicking Buttons
- Use the button's visible TEXT without brackets: click(target="Next") ✅
- NOT click(target="[Next]") ❌
- NOT click(target="#idBtn_Next") ❌ (don't guess IDs)

## Dropdowns
If `look` shows a CUSTOM DROPDOWN like "Email domain options (showing: @hotmail.com)":
- Use `select(dropdown="Email domain options", option="@outlook.com")` to change it

## Example: Filling a Microsoft signup form
Step 1: look() → sees Email field #floatingLabelInput4
Step 2: type(selector="#floatingLabelInput4", text="tarsmacbot2026@outlook.com")
Step 3: click(target="Next")
Step 4: wait(seconds=2)
Step 5: look() → sees Password field #floatingLabelInput13
Step 6: type(selector="#floatingLabelInput13", text="MyPassword123!")
Step 7: click(target="Next")
...and so on, ONE tool per step.

## CAPTCHA Handling
If the page says "Press and hold the button" or "prove you're human":
- Call `solve_captcha()` — it auto-detects the CAPTCHA type and solves it.
- After solving, call `wait(seconds=3)` then `look` to see the new page.
- If it says "Loading..." after solving, wait a few more seconds.

## RULES
1. ONE tool call per response. No exceptions.
2. ONLY use selectors from `look`. Never guess.
3. Use EXACTLY the values from your task instructions.
4. Click buttons by TEXT ("Next"), never with brackets ("[Next]") or guessed IDs.
5. If `look` shows CUSTOM DROPDOWNS, use `select` to pick from them.
6. If ⚠️ ERRORS appear in `look`, read them and adapt.
7. NEVER call `done` unless the page clearly shows success (welcome, inbox, confirmation).
8. If stuck after 3+ retries on the same step, call `stuck` honestly.
9. `js` is READ-ONLY. Never use it to click or modify.
10. If you see a CAPTCHA / "prove you're human", call `solve_captcha()` immediately.
"""


# ─────────────────────────────────────────────
#  Browser Agent Class
# ─────────────────────────────────────────────

class BrowserAgent:
    def __init__(self, llm_client, model, max_steps=40, phone=None, kill_event=None):
        self.client = llm_client
        self.model = model
        self.max_steps = max_steps
        self.phone = phone
        self.update_every = 3  # iMessage update every N steps
        self._kill_event = kill_event  # Shared threading.Event — set when kill word received

    def _dispatch(self, name, inp):
        """Route tool calls to browser functions."""
        try:
            if name == "look":       return act_inspect_page()
            if name == "goto":       return act_goto(inp["url"])
            if name == "click":      return act_click(inp["target"])
            if name == "type":       return act_fill(inp["selector"], inp["text"])
            if name == "select":     return act_select_option(inp["dropdown"], inp["option"])
            if name == "key":        return act_press_key(inp["name"])
            if name == "scroll":     return act_scroll(inp.get("direction", "down"))
            if name == "read":       return act_read_page()
            if name == "url":        return act_read_url()
            if name == "wait":       return act_wait(inp.get("seconds", 2))
            if name == "wait_for":   return act_wait_for_text(inp["text"])
            if name == "tabs":       return act_get_tabs()
            if name == "switch_tab": return act_switch_tab(inp["number"])
            if name == "close_tab":  return act_close_tab()
            if name == "back":       return act_back()
            if name == "forward":    return act_forward()
            if name == "refresh":    return act_refresh()
            if name == "screenshot": return act_screenshot()
            if name == "js":         return act_run_js(inp["code"])
            if name == "hold":       return act_press_and_hold(inp.get("target", "captcha"), inp.get("duration", 10))
            if name == "solve_captcha": return act_solve_captcha()
            return f"Unknown tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _notify(self, msg):
        """Send iMessage progress if phone configured."""
        if self.phone:
            _send_progress(self.phone, msg)

    def run(self, task, context=None):
        """Execute a browser task autonomously. Returns result dict."""
        print(f"  🌐 Browser Agent: {task[:80]}...")
        self._notify(f"🌐 Starting: {task[:300]}")

        # Make sure Chrome is active
        _activate_chrome()

        # Build initial user message with optional escalation context
        user_msg = f"Complete this task:\n\n{task}"
        if context:
            user_msg += f"\n\n## Additional guidance\n{context}"
        messages = [{"role": "user", "content": user_msg}]
        
        # Track success/error metrics to catch hallucinated success
        total_actions = 0
        total_errors = 0
        
        # ── Loop detection: track recent actions to prevent repetition ──
        recent_actions = []  # list of (name, args_hash) tuples
        LOOP_THRESHOLD = 3  # same action 3 times = force intervention

        # ── Auto-look on first step: always start by seeing the page ──
        auto_look_needed = True
        # Track actions that should trigger auto-wait + auto-look
        NAVIGATION_ACTIONS = {"goto", "click", "key", "select", "solve_captcha", "hold"}

        for step in range(1, self.max_steps + 1):
            print(f"  🧠 [Browser Agent] Step {step}/{self.max_steps}...")

            # ── Kill switch check — abort immediately ──
            if self._kill_event and self._kill_event.is_set():
                msg = f"Browser Agent killed by user at step {step}."
                print(f"  🛑 {msg}")
                self._notify(f"🛑 {msg}")
                return {"success": False, "content": msg, "steps": step, "stuck": True, "stuck_reason": "Kill switch activated"}

            # ── Auto-look: inject page state before first LLM call ──
            if auto_look_needed:
                auto_look_needed = False
                page_state = act_inspect_page()
                if page_state:
                    # Prepend page state so the LLM knows what it's working with
                    if len(messages) == 1:
                        messages[0]["content"] += f"\n\n## Current page state (auto-look):\n{page_state[:3000]}"
                    else:
                        messages.append({"role": "user", "content": f"Here is the current page state:\n{page_state[:3000]}"})

            try:
                response = self.client.create(
                    model=self.model,
                    max_tokens=2048,
                    system=BROWSER_AGENT_PROMPT,
                    tools=BROWSER_TOOLS,
                    messages=messages,
                )
            except Exception as e:
                err = f"API error: {e}"
                print(f"  ❌ {err}")
                self._notify(f"❌ {err[:200]}")
                return {"success": False, "content": err, "steps": step, "stuck": True, "stuck_reason": err}

            assistant_content = response.content
            tool_results = []
            tools_this_step = 0
            MAX_TOOLS_PER_STEP = 1  # STRICT: exactly ONE tool call per step

            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    print(f"    💭 {block.text[:150]}")

                elif block.type == "tool_use":
                    name = block.name
                    inp = block.input
                    tid = block.id
                    
                    # Limit tool calls per step to prevent batching hallucinations
                    tools_this_step += 1
                    if tools_this_step > MAX_TOOLS_PER_STEP:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": "SKIPPED: Only ONE tool call per step. Your previous tool in this step was executed. Now look at the result and decide your NEXT single action.",
                        })
                        continue

                    # Terminal tools
                    if name == "done":
                        summary = inp.get("summary", "Done.")
                        # Guard 1: reject if error rate too high
                        if total_actions > 2 and total_errors >= total_actions * 0.5:
                            print(f"  ⚠️ Rejecting 'done' — {total_errors}/{total_actions} actions failed")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: You cannot claim success — {total_errors} of {total_actions} actions returned errors. Call 'look' to see the current page state, then try a different approach. If truly stuck, call 'stuck' instead.",
                            })
                            continue
                        # Guard 2: reject if 'done' called too early (< 4 actions)
                        if total_actions < 4:
                            print(f"  ⚠️ Rejecting 'done' — only {total_actions} actions taken, too few")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: Only {total_actions} actions taken — that's too few to have completed a signup/login. Call 'look' to verify the page shows a success/welcome state before calling done.",
                            })
                            continue
                        # Guard 3: verify by checking the current page
                        verify = act_inspect_page()
                        verify_lower = verify.lower()
                        fail_signals = ["signup", "sign up", "create account", "create your", "enter your", "password", "username", "create a", "register", "get started", "floatinglabel", "prove you're human", "press and hold", "captcha"]
                        success_signals = ["welcome", "inbox", "dashboard", "account created", "you're all set", "verify your email", "confirmation", "successfully"]
                        has_fail = any(s in verify_lower for s in fail_signals)
                        has_success = any(s in verify_lower for s in success_signals)
                        if has_fail and not has_success:
                            print(f"  ⚠️ Rejecting 'done' — page still shows signup/form fields")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: Page still shows signup/login form. Current page:\n{verify[:1500]}\n\nYou are NOT done yet. Continue filling the form or call 'stuck'.",
                            })
                            continue
                        print(f"  ✅ Done: {summary[:150]}")
                        self._notify(f"✅ Done: {summary[:500]}")
                        return {"success": True, "content": summary, "steps": step}

                    if name == "stuck":
                        reason = inp.get("reason", "").strip()
                        # If reason is empty (malformed Groq call), grab page context
                        if not reason or reason == "Unknown." or len(reason) < 5:
                            page_ctx = act_inspect_page()
                            page_title = ""
                            for line in page_ctx.split("\n"):
                                if line.startswith("PAGE:"):
                                    page_title = line[5:].strip()
                                    break
                            reason = f"Stuck on page: {page_title}. Page state: {page_ctx[:500]}"
                        print(f"  ❌ [Browser Agent] Stuck: {reason[:150]}")
                        self._notify(f"❌ Stuck: {reason[:500]}")
                        return {"success": False, "stuck": True, "stuck_reason": reason, "content": f"Browser agent stuck: {reason}", "steps": step}

                    # Execute
                    inp_short = json.dumps(inp)[:100]
                    print(f"    🔧 {name}({inp_short})")
                    result = self._dispatch(name, inp)
                    result_str = str(result)[:4000]
                    print(f"      → {result_str[:150]}")
                    
                    # Track error rate
                    total_actions += 1
                    if result_str.startswith("ERROR"):
                        total_errors += 1
                        # If a type/click failed, show the agent what's ACTUALLY on the page
                        if name in ("type", "click") and "No visible" in result_str:
                            current_page = act_inspect_page()
                            result_str += f"\n\nHere is what is ACTUALLY on the page right now:\n{current_page[:2000]}\n\nUse ONLY the selectors shown above."

                    # ── Loop detection: same action repeated too many times ──
                    action_sig = f"{name}:{json.dumps(inp, sort_keys=True)}"
                    recent_actions.append(action_sig)
                    # Count how many times this exact action appears in last 6 actions
                    recent_window = recent_actions[-6:]
                    repeat_count = recent_window.count(action_sig)
                    if repeat_count >= LOOP_THRESHOLD:
                        result_str += f"\n\n⚠️ WARNING: You have tried this EXACT same action {repeat_count} times. It is NOT working. You MUST try a completely different approach, or call 'stuck' if you cannot proceed."
                        print(f"  ⚠️ Loop detected: {name} repeated {repeat_count}x")

                    # ── Auto-wait after navigation actions ──
                    # If the action triggers a page change, wait for it to load
                    if name in NAVIGATION_ACTIONS and not result_str.startswith("ERROR"):
                        time.sleep(1.5)  # Brief wait for page transition
                        # Auto-inject fresh page state so LLM sees the new page
                        fresh_page = act_inspect_page()
                        if fresh_page:
                            result_str += f"\n\n## Page after action (auto-look):\n{fresh_page[:2500]}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "content": result_str,
                    })

                    # iMessage update every N steps
                    if step % self.update_every == 0:
                        short = result_str[:200] + ("..." if len(result_str) > 200 else "")
                        self._notify(f"🌐 Step {step}: {name}\n→ {short}")

            # No tool calls = prompt to act
            if not tool_results:
                if response.stop_reason == "end_turn":
                    texts = [b.text for b in assistant_content if b.type == "text"]
                    txt = " ".join(texts).strip()
                    if txt:
                        print(f"  ⚠️ Text-only: {txt[:150]}")
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": "Use a tool. If done, call done(). If stuck, call stuck()."})
                    continue

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        # Max steps hit
        msg = f"Reached {self.max_steps} steps. Task may be partially complete."
        print(f"  ⏱️ {msg}")
        self._notify(f"⏱️ {msg}")
        return {"success": False, "content": msg, "steps": self.max_steps, "stuck": True, "stuck_reason": f"Hit max steps ({self.max_steps})"}
