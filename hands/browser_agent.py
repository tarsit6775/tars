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
    act_fill_form, act_full_page_scan, act_smart_wait,
    act_upload_file, act_handle_oauth_popup,
)
from hands.account_manager import read_verification_code, manage_account

import logging
logger = logging.getLogger("TARS")


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
        "name": "new_tab",
        "description": "Open a new tab, optionally with a URL.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to open in the new tab (optional)"}}, "required": []}
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
        "name": "fill_form",
        "description": "Fill multiple form fields at once — like a human filling out a whole form. MUCH faster than typing one field at a time. Use after look() shows multiple empty fields. Pass a list of {selector, value} pairs.",
        "input_schema": {"type": "object", "properties": {
            "fields": {
                "type": "array",
                "description": "List of fields to fill. Each item: {selector: CSS selector from look(), value: text to type, type: 'text' or 'select'}",
                "items": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector from look() output"},
                        "value": {"type": "string", "description": "Value to type or option to select"},
                        "type": {"type": "string", "enum": ["text", "select"], "default": "text"}
                    },
                    "required": ["selector", "value"]
                }
            }
        }, "required": ["fields"]}
    },
    {
        "name": "read_otp",
        "description": "Read a verification/OTP code from Mac Mail. Use when the page asks for an email confirmation code, verification code, or OTP. Polls Mail.app for recent messages and extracts the numeric code. Returns the code ready to type into the field.",
        "input_schema": {"type": "object", "properties": {
            "from_sender": {"type": "string", "description": "Filter by sender email, e.g. 'security@mail.instagram.com'. Optional."},
            "subject_contains": {"type": "string", "description": "Filter by subject keyword, e.g. 'Instagram', 'verification'. Optional."},
            "timeout": {"type": "integer", "description": "Max seconds to wait for the email (default 60)", "default": 60}
        }}
    },
    {
        "name": "full_scan",
        "description": "Scan the ENTIRE page by auto-scrolling top to bottom. Collects ALL fields, buttons, and links across the full page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "smart_wait",
        "description": "Smart wait that detects page changes (navigation, DOM updates, network idle). Better than fixed-time wait().",
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "What to wait for: 'page_change', 'network_idle', 'dom_stable'", "default": "page_change"},
            "timeout": {"type": "integer", "description": "Max seconds to wait", "default": 10}
        }}
    },
    {
        "name": "upload_file",
        "description": "Upload a file to a file input element. Use for profile photos, documents, attachments.",
        "input_schema": {"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS selector for the file input (e.g., 'input[type=file]')"},
            "file_path": {"type": "string", "description": "Absolute path to the file to upload"}
        }, "required": ["selector", "file_path"]}
    },
    {
        "name": "oauth_popup",
        "description": "Handle OAuth login popups (Google, GitHub, etc.). Call to switch to popup window. Use provider='return' to switch back.",
        "input_schema": {"type": "object", "properties": {
            "provider": {"type": "string", "description": "OAuth provider name or 'return' to switch back", "default": ""}
        }}
    },
    {
        "name": "generate_totp",
        "description": "Generate a TOTP 2FA code for a service. Use when a site asks for a 2FA/MFA/authenticator code.",
        "input_schema": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Service name to look up the TOTP secret"},
            "totp_secret": {"type": "string", "description": "Direct TOTP secret (base32 string) if not stored"}
        }}
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

## Core Operating Principle: OODA Loop
Every step follows this cycle:
1. **OBSERVE** → `look` at the page. Read the PAGE ASSESSMENT header.
2. **ORIENT** → What type of page is this? Am I done? What's blocking me?
3. **DECIDE** → What is the best next action?
4. **ACT** → Execute it.

## ABSOLUTE RULE: ONE TOOL CALL PER STEP
You MUST call exactly ONE tool per response. Never batch multiple tools.
The cycle is: look → (one action) → look → (one action) → ...

## CRITICAL: USE EXACT VALUES FROM YOUR TASK
Your task contains specific emails, passwords, names, and URLs. Use EXACTLY those values.
NEVER substitute your own values.

## CRITICAL: ONLY USE SELECTORS FROM `look` OUTPUT
NEVER guess selector names. Use EXACTLY what `look` showed you.

## 🔍 GOOGLE-FIRST NAVIGATION (CRITICAL — avoids CAPTCHAs and bot detection)
**NEVER use `goto` to navigate directly to a signup, login, or service URL.**
Direct URL navigation is a major bot signal — sites throw CAPTCHAs, block the session, or redirect endlessly.

**ALWAYS search Google first to reach a website:**
1. `goto("https://www.google.com/search?q=DoorDash+developer+portal+sign+up")` — search Google
2. `look` — see the search results
3. `click` the official result link
4. Now you're on the site with a natural Google referrer — sites trust this traffic

**Why:** Real humans Google things. Direct URL entry is a bot pattern. Searching Google sets proper Referer headers, bypasses CAPTCHAs, and finds the correct page even if URLs changed.

- ✅ `goto("https://www.google.com/search?q=Stripe+developer+signup")` → click result
- ❌ `goto("https://dashboard.stripe.com/register")` — bot pattern, triggers CAPTCHA

**Exception:** Already ON a site and navigating within it (clicking links, buttons) — that's fine.

## EFFICIENCY: USE fill_form FOR FORMS (CRITICAL)
When `look` shows a form with multiple empty fields, use `fill_form` to fill ALL fields at once:
```
fill_form(fields=[
  {selector: '#email', value: 'user@example.com'},
  {selector: '#name', value: 'John Doe'},
  {selector: '#password', value: 'SecurePass123!'}
])
```
This is 3x faster than calling `type` on each field separately.
A signup flow should take 8-12 steps, NOT 30-40.

## Step-by-Step Workflow
1. `look` → read PAGE ASSESSMENT + all fields/buttons on the page
2. `fill_form` with ALL empty fields from look output (or `type` for single field)
3. Check the tool result — all fields filled?
4. `click` the submit/next button
5. `wait` 2-3 seconds after state-changing clicks
6. `look` again → see the updated page
7. If new page: repeat from step 2
8. Check for 🚨 FORM ERRORS — fix and retry

## Account Creation & Developer Portals
When creating accounts on developer portals:
1. **Google it first** → `goto("https://www.google.com/search?q=SERVICE+developer+signup")` → `look` → click official result
2. `look` at the signup page → see the form
3. `fill_form` ALL visible fields (email, name, password, company)
4. Click submit → handle email verification with `read_otp`
5. After login, navigate to API/Developer section (Dashboard, API Keys, Apps)
6. Create an app if needed → copy API keys
7. Report ALL credentials in done() summary
- ⚠️ NEVER `goto` directly to signup/login URLs — always search Google first

## Goal Check (EVERY Step)
- "Is my goal ALREADY achieved?" → done() with evidence
- "Am I already logged in?" → done()
- "Is something blocking me?" → Dismiss overlay, solve CAPTCHA first

## Clicking Buttons
- Use the button's visible TEXT: click(target="Next") ✅
- NOT click(target="[Next]") ❌ (don't guess IDs)

## Multi-Page Forms
Signup forms are often MULTI-PAGE:
  Page 1: Email/name/password → fill_form + click "Sign up"
  Page 2: Birthday/profile → fill_form + click "Next"
  Page 3: CAPTCHA → solve_captcha()
  Page 4: Verification code → read_otp() to get code from email!
After submit, seeing NEW FIELDS = the form advanced. Fill them. DON'T call stuck.

## Verification / Confirmation Code
When the page asks for a code:
  1. Call `read_otp(subject_contains='ServiceName')` — polls Mail for up to 120s
  2. Type the code into the input field
  3. Click confirm
  ⚠️ DO NOT navigate away from the code page!
  ⚠️ DO NOT call stuck() on a code page — use read_otp.

## NEVER GO BACK TO A PREVIOUS URL
Going back DESTROYS multi-page form progress.

## CAPTCHA Handling
Call `solve_captcha()` when you see CAPTCHA challenges.

## Form Errors = Feedback, Not Failure
When you see form errors, apply these recovery playbooks:
- "Username taken" / "Username isn't available" → Append random digits (e.g. tarsdev847) and re-type
- "Email already in use" / "Already registered" → Switch to LOGIN flow with the same credentials
- "Password too weak" / "Password doesn't meet requirements" → Use stronger password: TarsAgent2026!#
- "Invalid email" → Check for typos, use tarsitgroup@outlook.com (NOT @example.com)
- "Too many attempts" / "Try again later" → wait(30), then refresh() and retry
- "Something went wrong" → wait(5), refresh(), try again
- "Verify you're human" / CAPTCHA → call solve_captcha()
- "Session expired" → refresh() and restart the form
NEVER call stuck() on fixable form errors.

## RULES
1. ONE tool call per response.
2. ONLY use selectors from `look`.
3. Use EXACTLY the values from your task.
4. Use `fill_form` for multi-field forms — NOT individual `type` calls.
5. Fix FORM ERRORS — don't call stuck.
6. NEVER call done unless page clearly shows success.
7. NEVER call stuck after just 3-4 steps. Try 3+ different approaches.
8. `js` is READ-ONLY.
9. Multi-page forms: new fields = PROGRESS.
10. Report what you ACTUALLY SEE, not what you expected.
11. A typical account creation should take 8-15 steps, not 40.
12. GOOGLE FIRST — never `goto` a signup/login URL. Search Google, click the result.
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
            if name == "new_tab":   return act_new_tab(inp.get("url", ""))
            if name == "close_tab":  return act_close_tab()
            if name == "back":       return act_back()
            if name == "forward":    return act_forward()
            if name == "refresh":    return act_refresh()
            if name == "screenshot": return act_screenshot()
            if name == "js":         return act_run_js(inp["code"])
            if name == "fill_form":  return act_fill_form(inp.get("fields", []))
            if name == "full_scan":  return act_full_page_scan()
            if name == "smart_wait": return act_smart_wait(inp.get("reason", "page_change"), inp.get("timeout", 10))
            if name == "upload_file": return act_upload_file(inp["selector"], inp["file_path"])
            if name == "oauth_popup": return act_handle_oauth_popup(inp.get("provider", ""))
            if name == "generate_totp":
                result = manage_account({"action": "generate_totp", "service": inp.get("service", ""), "totp_secret": inp.get("totp_secret", "")})
                return result.get("content", str(result))
            if name == "hold":       return act_press_and_hold(inp.get("target", "captcha"), inp.get("duration", 10))
            if name == "solve_captcha": return act_solve_captcha()
            if name == "read_otp":
                timeout = max(inp.get("timeout", 90), 90)  # Minimum 90s — emails can take time
                result = read_verification_code(
                    from_sender=inp.get("from_sender"),
                    subject_contains=inp.get("subject_contains"),
                    timeout=timeout,
                )
                if result.get("code"):
                    return f"✅ Verification code: {result['code']} — Type this into the code field now."
                if result.get("raw_email"):
                    return f"Found emails but no clear code. Email content:\n{result['raw_email'][:500]}\n\nLook for a code manually in the text above."
                return result.get("content", "No verification code found after waiting. Check if the email was sent to the correct address.")
            return f"Unknown tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _notify(self, msg):
        """Send iMessage progress if phone configured."""
        if self.phone:
            _send_progress(self.phone, msg)

    def run(self, task, context=None):
        """Execute a browser task autonomously. Returns result dict."""
        logger.info(f"  🌐 Browser Agent: {task[:80]}...")
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
            logger.debug(f"  🧠 [Browser Agent] Step {step}/{self.max_steps}...")

            # ── Kill switch check — abort immediately ──
            if self._kill_event and self._kill_event.is_set():
                msg = f"Browser Agent killed by user at step {step}."
                logger.warning(f"  🛑 {msg}")
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
                logger.warning(f"  ❌ {err}")
                self._notify(f"❌ {err[:200]}")
                return {"success": False, "content": err, "steps": step, "stuck": True, "stuck_reason": err}

            assistant_content = response.content
            tool_results = []
            tools_this_step = 0
            MAX_TOOLS_PER_STEP = 1  # STRICT: exactly ONE tool call per step

            for block in assistant_content:
                if block.type == "text" and block.text.strip():
                    logger.debug(f"    💭 {block.text[:150]}")

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
                            logger.warning(f"  ⚠️ Rejecting 'done' — {total_errors}/{total_actions} actions failed")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: You cannot claim success — {total_errors} of {total_actions} actions returned errors. Call 'look' to see the current page state, then try a different approach. If truly stuck, call 'stuck' instead.",
                            })
                            continue
                        # Guard 2: reject if 'done' called too early (< 4 actions)
                        if total_actions < 4:
                            logger.warning(f"  ⚠️ Rejecting 'done' — only {total_actions} actions taken, too few")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: Only {total_actions} actions taken — that's too few to have completed a signup/login. Call 'look' to verify the page shows a success/welcome state before calling done.",
                            })
                            continue
                        # Guard 3: verify by checking the current page
                        verify = act_inspect_page()
                        verify_lower = verify.lower()
                        # Only block done() if the page clearly looks like an INCOMPLETE signup/login form
                        # Check FIELDS section specifically — "password" in a settings page is fine
                        fields_section = ""
                        for line in verify.split("\n"):
                            if line.startswith("FIELDS:"):
                                fields_section = verify_lower[verify_lower.index("fields:"):]
                                # Only get up to next section
                                for end_marker in ["buttons:", "links:", "dropdowns:", "checkboxes:", "errors:", "iframes:"]:
                                    if end_marker in fields_section[8:]:
                                        fields_section = fields_section[:fields_section.index(end_marker, 8)]
                                        break
                                break
                        # Signals that the page is still an unfilled signup/login FORM
                        form_signals = ["sign up", "create account", "create your", "register", "get started", "create a", "join now"]
                        captcha_signals = ["prove you're human", "press and hold", "captcha", "verify you are human"]
                        # Signals that OTP/verification is still pending — NOT done yet
                        otp_signals = ["confirmation code", "enter the code", "enter code", "verification code", "we sent a code", "check your email"]
                        # Signals the task succeeded
                        success_signals = ["welcome", "inbox", "dashboard", "account created", "you're all set", "successfully", "feed", "home", "profile"]
                        # Check for form errors — those always mean NOT done
                        has_form_errors = "🚨 form errors:" in verify_lower
                        # Only consider it a fail if signup keywords are in buttons/page title AND no success signals
                        has_form_signal = any(s in verify_lower for s in form_signals)
                        has_captcha = any(s in verify_lower for s in captcha_signals)
                        has_otp_pending = any(s in verify_lower for s in otp_signals)
                        has_success = any(s in verify_lower for s in success_signals)
                        # Reject: form still showing signup buttons + no success indicators
                        if (has_form_signal or has_captcha or has_form_errors) and not has_success:
                            logger.warning(f"  ⚠️ Rejecting 'done' — page still shows signup/form fields")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: Page still shows signup/login form. Current page:\n{verify[:1500]}\n\nYou are NOT done yet. Continue filling the form or call 'stuck'.",
                            })
                            continue
                        # Reject: OTP/verification code page — not done until code is entered
                        if has_otp_pending and not has_success:
                            logger.warning(f"  ⚠️ Rejecting 'done' — page still needs verification code")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tid,
                                "content": f"REJECTED: Page is asking for a verification/confirmation code. You are NOT done yet. Call read_otp(subject_contains='...') to get the code from Mac Mail, type it into the field, then submit.\n\nCurrent page:\n{verify[:1500]}",
                            })
                            continue
                        logger.info(f"  ✅ Done: {summary[:150]}")
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
                        logger.warning(f"  ❌ [Browser Agent] Stuck: {reason[:150]}")
                        self._notify(f"❌ Stuck: {reason[:500]}")
                        return {"success": False, "stuck": True, "stuck_reason": reason, "content": f"Browser agent stuck: {reason}", "steps": step}

                    # Execute
                    inp_short = json.dumps(inp)[:100]
                    logger.debug(f"    🔧 {name}({inp_short})")
                    result = self._dispatch(name, inp)
                    result_str = str(result)[:4000]
                    logger.debug(f"      → {result_str[:150]}")
                    
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
                        logger.warning(f"  ⚠️ Loop detected: {name} repeated {repeat_count}x")

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
                        logger.warning(f"  ⚠️ Text-only: {txt[:150]}")
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": "Use a tool. If done, call done(). If stuck, call stuck()."})
                    continue

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        # Max steps hit
        msg = f"Reached {self.max_steps} steps. Task may be partially complete."
        logger.info(f"  ⏱️ {msg}")
        self._notify(f"⏱️ {msg}")
        return {"success": False, "content": msg, "steps": self.max_steps, "stuck": True, "stuck_reason": f"Hit max steps ({self.max_steps})"}
