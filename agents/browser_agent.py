"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Browser Agent: Autonomous Web Expert             ║
╠══════════════════════════════════════════════════════════════╣
║  Controls Google Chrome using PHYSICAL mouse + keyboard.     ║
║  JS is READ-ONLY (inspect page, find elements).              ║
║  All actions = real mouse clicks + real keyboard typing.     ║
║  Dynamic coordinate mapping — works at any window size.      ║
║                                                              ║
║  21 human-like tools. Own LLM loop.                          ║
║  Inherits from BaseAgent.                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import logging
from urllib.parse import urlparse

from agents.base_agent import BaseAgent
from agents.agent_tools import TOOL_DONE, TOOL_STUCK

from hands.browser import (
    act_goto, act_google, act_read_page, act_read_url,
    act_inspect_page, act_fill, act_click, act_select_option,
    act_press_key, act_scroll, act_get_tabs, act_switch_tab,
    act_close_tab, act_new_tab, act_back, act_forward,
    act_refresh, act_wait, act_wait_for_text, act_run_js,
    act_screenshot, act_handle_dialog, _activate_chrome,
    act_press_and_hold, act_solve_captcha, act_smart_wait,
    _last_page_classification, _capture_page_state, _compute_page_diff,
    act_fill_form, act_full_page_scan,
    act_upload_file, act_handle_oauth_popup,
)
from hands.account_manager import read_verification_code, manage_account
from memory.site_knowledge import site_knowledge

logger = logging.getLogger("TARS")


# ─────────────────────────────────────────────
#  Browser-Specific Tool Definitions
# ─────────────────────────────────────────────

BROWSER_TOOLS = [
    {
        "name": "look",
        "description": "Observe the current page. Returns a PAGE ASSESSMENT (page type, login state, overlays, CAPTCHA) followed by all visible fields, buttons, dropdowns, links, errors, and checkboxes. ALWAYS do this first on any new or changed page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "goto",
        "description": "Navigate to a URL.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    },
    {
        "name": "click",
        "description": "Physically click on something. Pass visible text of a button/link ('Next', 'Sign in') or a CSS selector ('#submit', '.btn'). Uses real mouse click.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string", "description": "Button/link text or CSS selector"}}, "required": ["target"]}
    },
    {
        "name": "type",
        "description": "Click on a field and type text physically. Like a human: clicks the field, clears it, types the value.",
        "input_schema": {"type": "object", "properties": {"selector": {"type": "string", "description": "CSS selector of field, e.g. '#firstName'"}, "text": {"type": "string", "description": "Text to type"}}, "required": ["selector", "text"]}
    },
    {
        "name": "select",
        "description": "Select an option from ANY dropdown (standard or custom/Material). Clicks dropdown to open, then clicks option.",
        "input_schema": {"type": "object", "properties": {"dropdown": {"type": "string", "description": "Dropdown label text or CSS selector"}, "option": {"type": "string", "description": "Option text to select"}}, "required": ["dropdown", "option"]}
    },
    {
        "name": "key",
        "description": "Press a keyboard key: enter, tab, escape, up, down, left, right, space, backspace.",
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
        "name": "smart_wait",
        "description": "Intelligently wait for page to stabilize after an action. Monitors DOM changes, network activity, and readyState. Returns early when stable. Better than fixed wait times.",
        "input_schema": {"type": "object", "properties": {"timeout": {"type": "integer", "description": "Max seconds to wait (default 10)"}}}
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
    # back and forward REMOVED — agents abuse them, destroying multi-page progress.
    # If absolutely needed, use goto() to navigate to a specific URL instead.
    {
        "name": "refresh",
        "description": "Reload the current page.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "screenshot",
        "description": "Take a screenshot of the page. The image is sent to you for visual inspection — you can SEE the page layout, buttons, CAPTCHAs, error messages, and visual state. Use this when look() text description isn't enough, or to verify visual elements like CAPTCHAs, images, or layout.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "js",
        "description": "Run custom JavaScript for reading page info. READ-ONLY — never use to click or modify the DOM. Use 'return' to get values.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
    },
    {
        "name": "new_tab",
        "description": "Open a new tab, optionally with a URL.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to open in the new tab (optional)"}}, "required": []}
    },
    {
        "name": "hold",
        "description": "Press and hold an element for N seconds. For CAPTCHA 'press and hold' buttons. Use target='captcha' to auto-detect.",
        "input_schema": {"type": "object", "properties": {"target": {"type": "string", "description": "Element text, CSS selector, or 'captcha' for auto-detect", "default": "captcha"}, "duration": {"type": "integer", "description": "Seconds to hold (default 10)", "default": 10}}, "required": ["target"]}
    },
    {
        "name": "solve_captcha",
        "description": "Auto-detect and solve CAPTCHA on the current page. Handles 'press and hold' CAPTCHAs automatically. Call when you see 'Press and hold', 'prove you're human', or a CAPTCHA challenge.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "fill_form",
        "description": "Fill multiple form fields at once — like a human filling out a whole form. MUCH faster than typing one field at a time. Use after look() shows multiple empty fields. Pass a list of {selector, value} pairs. Can also handle dropdowns with type='select'.",
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
        "description": "Read a verification/OTP code from Mac Mail. Use this when the page asks for an email confirmation code, verification code, or OTP. Polls Mail.app for recent messages and extracts the numeric code. Returns the code ready to type into the field.",
        "input_schema": {"type": "object", "properties": {
            "from_sender": {"type": "string", "description": "Filter by sender email, e.g. 'security@mail.instagram.com'. Optional."},
            "subject_contains": {"type": "string", "description": "Filter by subject keyword, e.g. 'Instagram', 'verification'. Optional."},
            "timeout": {"type": "integer", "description": "Max seconds to wait for the email (default 60)", "default": 60}
        }}
    },
    {
        "name": "full_scan",
        "description": "Scan the ENTIRE page by auto-scrolling top to bottom. Collects ALL fields, buttons, and links across the full page — not just the current viewport. Use when you suspect important elements are below the fold, or on long pages where look() only shows partial content.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "upload_file",
        "description": "Upload a file to a file input element on the page. Use for profile photos, documents, attachments. Finds the <input type='file'> and sets the file via CDP.",
        "input_schema": {"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS selector for the file input (e.g., 'input[type=file]', '#avatar-upload'). If unsure, use 'input[type=file]'."},
            "file_path": {"type": "string", "description": "Absolute path to the file to upload (e.g., '/tmp/profile.jpg')"}
        }, "required": ["selector", "file_path"]}
    },
    {
        "name": "oauth_popup",
        "description": "Handle OAuth login popups (Google Sign-In, GitHub OAuth, etc.). When a site opens a popup for third-party auth, call this to switch to the popup window. After logging in, call with provider='return' to switch back to the main window.",
        "input_schema": {"type": "object", "properties": {
            "provider": {"type": "string", "description": "OAuth provider name ('google', 'github', 'facebook') or 'return' to switch back to main window after auth.", "default": ""}
        }}
    },
    {
        "name": "generate_totp",
        "description": "Generate a TOTP 2FA code for a service. Use when a site asks for a 2FA/MFA/authenticator code during login. Reads the stored TOTP secret and generates the current 6-digit code.",
        "input_schema": {"type": "object", "properties": {
            "service": {"type": "string", "description": "Service name to look up the TOTP secret (e.g., 'github', 'aws')"},
            "totp_secret": {"type": "string", "description": "Direct TOTP secret (base32 string) if not stored. Use this when setting up 2FA for the first time."}
        }}
    },
    TOOL_DONE,
    TOOL_STUCK,
]


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

BROWSER_SYSTEM_PROMPT = """You are TARS Browser Agent — an autonomous web navigator controlling Chrome on macOS with physical mouse clicks and keyboard typing.

## DECISION FRAMEWORK (use this EVERY step)

After EVERY action, follow this exact decision process:

1. **READ** the tool result carefully. What happened? Did the URL change? Any errors?
2. **MATCH** — Look at the elements on the page. Which ONE element matches your goal?
3. **ACT** — Interact with THAT specific element. One action per step.
4. **VERIFY** — Call look() to confirm the action worked.

## ABSOLUTE RULES (violations waste steps)

1. **look() FIRST** — Always look() before doing anything on a new/changed page.
2. **GOOGLE-FIRST** — Never goto() a website directly. Always search Google first, then click the result.
3. **ONE ELEMENT PER STEP** — Identify the ONE element that advances your goal, interact with it.
4. **NEVER GO BACK** — Do NOT use back(). Going back destroys multi-page progress. If you're on the wrong page, click a link/button to navigate FORWARD.
5. **fill_form FOR FORMS** — When look() shows 2+ empty fields, use fill_form to fill ALL at once. Never type fields one by one.
6. **OAUTH POPUPS** — After clicking "Continue with Google/GitHub", call oauth_popup() to switch to the popup window. After authenticating, call oauth_popup(provider='return') to switch back.
7. **JS IS READ-ONLY** — Never use js() to click, fill, or modify DOM elements. Use click() and type() for interactions.
8. **FORM ERRORS ≠ STUCK** — Read the error message, fix the issue, retry. Never call stuck() on fixable errors.
9. **VERIFICATION CODES** — When you see "Enter code" or "Confirmation code", call read_otp(). Never call stuck() on code pages.
10. **DONE WITH EVIDENCE** — When calling done(), include specific evidence: what you see on screen, URLs, usernames, extracted data.

## HOW TO IDENTIFY THE RIGHT ELEMENT

When look() returns many buttons/fields, use this priority:
1. **Text match** — Find elements whose text contains keywords from your goal (e.g., "API Keys", "Create token", "Sign up")
2. **Primary actions** — Buttons labeled "Submit", "Create", "Continue", "Next", "Sign in" are usually the right choice
3. **Form fields** — Empty required fields (⭕) should be filled before clicking submit
4. **Sidebar/nav** — Settings pages often have sidebar navigation. Look for the menu item matching your goal.

## YOUR TOOLS

**Observe:** look, read, url, screenshot, js (read-only)
**Interact:** fill_form (preferred for forms), click, type, select, key
**Navigate:** goto (Google searches only), scroll, refresh, new_tab, tabs, switch_tab, close_tab
**Wait:** wait, wait_for, smart_wait
**Special:** read_otp, solve_captcha, hold, oauth_popup, generate_totp, full_scan, upload_file
**Finish:** done (with evidence), stuck (after 10+ genuine attempts)

## GOOGLE-FIRST NAVIGATION

ALWAYS search Google to reach a website:
1. `goto("https://www.google.com/search?q=SITE+NAME+developer+signup")`
2. `look()` → find the official result
3. `click("Official Result Text")` → you're on the site with proper referrer

NEVER goto("https://example.com/signup") directly — triggers CAPTCHAs.
Exception: navigating WITHIN a site you're already on (clicking sidebar links, etc.)

## FORM FILLING WORKFLOW

1. look() → see FIELDS section with selectors and empty/filled status
2. fill_form(fields=[{selector: '#email', value: 'user@example.com'}, {selector: '#password', value: 'Pass123!'}])
3. click("Submit") or click("[type=submit]")
4. wait(2) → look() → handle new page

## MULTI-PAGE FLOWS

Many tasks span multiple pages (signup → birthday → CAPTCHA → verify → dashboard):
- After submitting, wait 2s then look() at the NEW page
- A new form = PROGRESS, not failure. Continue.
- Track mentally: "Completed signup. Now on birthday page. Next: verification."
- NEVER navigate to a previous URL. Progress is irreversible.

## OAUTH LOGIN (Google/GitHub)

1. look() → find "Continue with Google" button
2. click("Continue with Google")
3. wait(3) → oauth_popup(provider='google') → switches to popup
4. look() → see Google account selection
5. click("tarsitsales@gmail.com") or fill credentials
6. wait(3) → oauth_popup(provider='return') → back to main site
7. look() → confirm login success"""


class BrowserAgent(BaseAgent):
    """Autonomous browser agent — controls Chrome physically like a human."""

    @property
    def agent_name(self):
        return "Browser Agent"

    @property
    def agent_emoji(self):
        return "🌐"

    @property
    def _loop_detection_window(self):
        # Browser agents naturally repeat click→wait→look patterns.
        # Use a wider window so normal navigation isn't falsely flagged.
        return 4

    @property
    def _loop_detection_repeats(self):
        # Require more repetitions before flagging — browser workflows are repetitive.
        return 4

    @property
    def system_prompt(self):
        """Dynamic prompt: base OODA prompt + injected site knowledge."""
        base = BROWSER_SYSTEM_PROMPT
        if hasattr(self, '_site_context') and self._site_context:
            base += f"\n\n{self._site_context}"
        return base

    @property
    def tools(self):
        return BROWSER_TOOLS

    def _on_start(self, task):
        """Activate Chrome + load site knowledge + init tracking."""
        _activate_chrome()
        self._visited_urls = []  # Track navigation to prevent backtracking
        self._past_first_page = False  # Set True after first successful form submission
        self._current_domain = ""  # Track current site for learning
        self._flow_steps = []  # Track page transitions for flow recording
        self._site_context = ""  # Site knowledge injected into prompt
        self._task = task  # Remember the original task
        self._action_log = []  # Track all actions for self-evaluation
        self._tab_id = None  # Tab this agent operates on (multi-tab support)

        # Extract domain from any URLs in the task
        urls = re.findall(r'https?://[^\s,)\"\']+'  , task)
        if urls:
            domain = urlparse(urls[0]).netloc
            self._current_domain = domain
            # Load site knowledge — agent gets smarter with each visit
            ctx = site_knowledge.get_site_context(urls[0])
            if ctx:
                self._site_context = ctx
                logger.info(f"[BrowserAgent] Loaded site knowledge for {domain}")

    def run(self, task, context=None):
        """Run with post-task site knowledge learning."""
        result = super().run(task, context)
        self._learn_from_result(task, result)
        return result

    def _learn_from_result(self, task, result):
        """Record what we learned to site knowledge after task completion."""
        domain = getattr(self, '_current_domain', '')
        if not domain:
            return
        try:
            if result.get("success"):
                # Record successful flow
                flow_steps = getattr(self, '_flow_steps', [])
                if flow_steps:
                    flow_name = "task"
                    task_lower = task.lower()
                    if any(k in task_lower for k in ["signup", "sign up", "create account", "register"]):
                        flow_name = "signup"
                    elif any(k in task_lower for k in ["login", "log in", "sign in"]):
                        flow_name = "login"
                    elif any(k in task_lower for k in ["search", "find", "look for"]):
                        flow_name = "search"
                    site_knowledge.learn_flow(domain, flow_name, flow_steps, success=True)
                    logger.info(f"[BrowserAgent] Saved successful {flow_name} flow for {domain} ({len(flow_steps)} steps)")
            else:
                # Record failure for analysis
                content = result.get("content", "")[:200]
                flow_steps = getattr(self, '_flow_steps', [])
                if flow_steps:
                    site_knowledge.learn_flow(domain, "failed_attempt", flow_steps, success=False)
                if content:
                    site_knowledge.learn_error_fix(domain, content, "pending investigation")

            # Self-evaluation: score the outcome
            self._self_evaluate(task, result)
        except Exception as e:
            logger.warning(f"[BrowserAgent] Failed to save learning: {e}")

    def _self_evaluate(self, task, result):
        """Rate own performance for continuous improvement."""
        try:
            steps = result.get("steps", 0)
            success = result.get("success", False)
            content = result.get("content", "")

            # Confidence scoring
            confidence = 0.5  # Base
            if success:
                confidence += 0.3
                if steps <= 10:
                    confidence += 0.15  # Efficient
                elif steps >= 30:
                    confidence -= 0.1  # Inefficient
            else:
                confidence -= 0.2
                if "stuck" in content.lower():
                    confidence -= 0.1

            # Log self-evaluation
            domain = getattr(self, '_current_domain', 'unknown')
            logger.info(
                f"[BrowserAgent] Self-eval: domain={domain} "
                f"success={success} steps={steps} confidence={confidence:.2f}"
            )

            # Emit for dashboard
            from utils.event_bus import event_bus
            event_bus.emit("browser_self_eval", {
                "domain": domain,
                "success": success,
                "steps": steps,
                "confidence": round(confidence, 2),
                "task_summary": task[:100],
            })
        except Exception:
            pass  # Self-eval failures are non-critical

    def get_state_checkpoint(self):
        """Export current agent state for persistence/handoff."""
        return {
            "domain": getattr(self, '_current_domain', ''),
            "visited_urls": getattr(self, '_visited_urls', []),
            "past_first_page": getattr(self, '_past_first_page', False),
            "flow_steps": getattr(self, '_flow_steps', []),
            "task": getattr(self, '_task', ''),
        }

    def restore_state_checkpoint(self, checkpoint):
        """Restore agent state from a previous checkpoint."""
        if not checkpoint:
            return
        self._current_domain = checkpoint.get("domain", "")
        self._visited_urls = checkpoint.get("visited_urls", [])
        self._past_first_page = checkpoint.get("past_first_page", False)
        self._flow_steps = checkpoint.get("flow_steps", [])
        # Load site knowledge for restored domain
        if self._current_domain:
            from urllib.parse import urlparse as _up
            visited = checkpoint.get("visited_urls", [])
            if visited:
                ctx = site_knowledge.get_site_context(visited[-1])
                if ctx:
                    self._site_context = ctx

    # ── Error recovery playbooks ──────────────────────────────────
    _FORM_ERROR_PLAYBOOKS = {
        # pattern (lowercase) → recovery guidance injected after look/click
        "username isn't available": "🔧 RECOVERY: Try a different username — append random digits (e.g. tarsdev{rand}) and re-type the field.",
        "username taken": "🔧 RECOVERY: Try a different username — append random digits (e.g. tarsdev{rand}) and re-type the field.",
        "username already": "🔧 RECOVERY: Try a different username — append random digits (e.g. tarsdev{rand}) and re-type the field.",
        "email already": "🔧 RECOVERY: This email has an account. Try LOGGING IN instead of signing up. Navigate to the login page and use the same email + password.",
        "email is already": "🔧 RECOVERY: This email has an account. Try LOGGING IN instead of signing up. Navigate to the login page and use the same email + password.",
        "already registered": "🔧 RECOVERY: Account exists. Switch to LOGIN flow with the same credentials.",
        "already in use": "🔧 RECOVERY: Account exists for this email. Switch to LOGIN flow.",
        "password too weak": "🔧 RECOVERY: Make password stronger. Clear the field and type a new password with uppercase + lowercase + number + special char (e.g. TarsAgent2026!#).",
        "password doesn't meet": "🔧 RECOVERY: Password doesn't meet requirements. Try: TarsAgent2026!# (has upper, lower, digit, special).",
        "password must": "🔧 RECOVERY: Read the password requirements carefully. Generate a password that satisfies ALL listed rules.",
        "too many attempts": "🔧 RECOVERY: Rate limited. Call wait(seconds=30), then refresh() the page and try again.",
        "try again later": "🔧 RECOVERY: Temporary block. Call wait(seconds=15), then refresh() and retry.",
        "something went wrong": "🔧 RECOVERY: Generic error. Call wait(seconds=5), then refresh() the page. If it persists, try a different approach.",
        "invalid email": "🔧 RECOVERY: Check for typos in the email field. Use tarsitgroup@outlook.com or tarsitsales@gmail.com (NOT @example.com).",
        "phone number required": "🔧 RECOVERY: No phone available. Look for a 'Skip' button, or try a different signup method (Google/GitHub OAuth).",
        "verify you're human": "🔧 RECOVERY: CAPTCHA detected. Call solve_captcha() to attempt automated solving.",
        "captcha": "🔧 RECOVERY: CAPTCHA detected. Call solve_captcha() to attempt automated solving.",
        "session expired": "🔧 RECOVERY: Session timed out. Call refresh() to reload the page, then restart the form from the beginning.",
        "session has expired": "🔧 RECOVERY: Session timed out. Call refresh() to reload the page, then restart the form from the beginning.",
        "please log in again": "🔧 RECOVERY: Session lost. Navigate to the login page and re-authenticate.",
    }

    def _check_form_error_recovery(self, result_text):
        """Check tool result for form errors and append recovery playbook guidance."""
        if not isinstance(result_text, str):
            return result_text
        result_lower = result_text.lower()
        import random
        recoveries = []
        for pattern, guidance in self._FORM_ERROR_PLAYBOOKS.items():
            if pattern in result_lower:
                # Inject random digits for username suggestions
                g = guidance.replace("{rand}", str(random.randint(100, 9999)))
                recoveries.append(g)
        if recoveries:
            # Deduplicate (some patterns overlap)
            seen = set()
            unique = []
            for r in recoveries:
                key = r[:40]
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return result_text + "\n\n" + "\n".join(unique)
        return result_text

    def _dispatch(self, name, inp):
        """Route browser tool calls with OODA intelligence."""
        try:
            if name == "look":
                result = act_inspect_page()
                # Auto-learn from page classification
                try:
                    cls = _last_page_classification
                    if cls and cls.get("url"):
                        url = cls["url"]
                        domain = urlparse(url).netloc
                        if domain:
                            self._current_domain = domain
                        # Track flow transitions (page type changes)
                        page_type = cls.get("type", "unknown")
                        path = urlparse(url).path
                        step_key = f"{page_type}:{path}"
                        if not self._flow_steps or self._flow_steps[-1] != step_key:
                            self._flow_steps.append(step_key)
                        # Learn page structure
                        site_knowledge.learn_page(
                            url, page_type,
                            notes=f"fields={cls.get('field_count',0)} buttons={cls.get('button_count',0)}"
                        )
                except Exception:
                    pass  # Learning failures should never break the tool
                # Check for form errors and inject recovery guidance
                result = self._check_form_error_recovery(result)
                return result
            if name == "goto":
                url = inp["url"]
                # Anti-backtrack guard: if agent already progressed past signup form,
                # block navigation back to the signup URL (which would reset the page)
                if self._past_first_page:
                    for visited in self._visited_urls[:3]:  # Check first few URLs
                        if visited and url.rstrip("/") == visited.rstrip("/"):
                            return (
                                "⛔ BLOCKED: You already visited this URL earlier and progressed past it. "
                                "Navigating back will RESET your progress and lose the current page. "
                                "Instead, use look() to see what's currently on the page and continue from here. "
                                "If you need to read email, use read_otp(). Do NOT go back to the signup URL."
                            )
                result = act_goto(url)
                self._visited_urls.append(url)
                return result
            if name == "click":
                result = act_click(inp["target"])
                # Detect form submission — mark that we've progressed past first page
                target_lower = inp["target"].lower()
                if any(kw in target_lower for kw in ["sign up", "submit", "next", "continue", "create", "register"]):
                    self._past_first_page = True
                # Auto-detect OAuth popup after clicking OAuth-related buttons
                oauth_triggers = ["continue with google", "sign in with google", "continue with github",
                                  "sign in with github", "continue with microsoft", "sign in with apple",
                                  "continue with facebook", "log in with google", "google", "github"]
                if any(kw in target_lower for kw in oauth_triggers):
                    import time as _t
                    _t.sleep(2)  # Wait for popup to open
                    try:
                        from hands.browser import _cdp
                        tabs = _cdp.get_tabs() if _cdp else []
                        if len(tabs) > 1:
                            result = str(result) + (
                                "\n\n🔔 POPUP DETECTED: A new window/tab opened (likely OAuth login). "
                                "Call oauth_popup(provider='google') to switch to it, then look() to see the login form."
                            )
                    except Exception:
                        pass
                # Multi-strategy retry: if click failed, try alternative selectors
                if isinstance(result, str) and "ERROR" in result:
                    target = inp["target"]
                    # Strategy 2: Try as text if was selector, or vice versa
                    retry_result = None
                    if target.startswith(("#", ".", "[")):
                        # Was CSS selector — try by partial text match
                        retry_result = act_click(target.strip("#.[]").split("=")[-1].strip("'\""))
                    else:
                        # Was text — try common CSS patterns
                        for sel in [f"[aria-label*='{target}']", f"button:has-text('{target}')"]:
                            retry_result = act_click(sel)
                            if not (isinstance(retry_result, str) and "ERROR" in retry_result):
                                break
                    if retry_result and not (isinstance(retry_result, str) and "ERROR" in retry_result):
                        result = retry_result + " (auto-retry succeeded)"
                    # Learn selector failure for site knowledge
                    try:
                        if self._current_domain:
                            site_knowledge.learn_selector(
                                self._current_domain, target, "click_failed",
                                success=False
                            )
                    except Exception:
                        pass
                return self._check_form_error_recovery(result)
            if name == "type":
                result = act_fill(inp["selector"], inp["text"])
                # Multi-strategy retry: if field not found, try alt selectors
                if isinstance(result, str) and "ERROR" in result:
                    selector = inp["selector"]
                    # Strategy 2: Try by aria-label or placeholder
                    for alt in [
                        f"[aria-label*='{selector.strip('#.[]')}']",
                        f"[placeholder*='{selector.strip('#.[]')}']",
                        f"[name*='{selector.strip('#.[]')}']",
                    ]:
                        retry_result = act_fill(alt, inp["text"])
                        if not (isinstance(retry_result, str) and "ERROR" in retry_result):
                            result = retry_result + " (auto-retry with alt selector)"
                            break
                return self._check_form_error_recovery(result)
            if name == "fill_form":  return self._check_form_error_recovery(act_fill_form(inp.get("fields", [])))
            if name == "full_scan":  return act_full_page_scan()
            if name == "upload_file": return act_upload_file(inp["selector"], inp["file_path"])
            if name == "oauth_popup": return act_handle_oauth_popup(inp.get("provider", ""))
            if name == "generate_totp":
                result = manage_account({"action": "generate_totp", "service": inp.get("service", ""), "totp_secret": inp.get("totp_secret", "")})
                return result.get("content", str(result))
            if name == "select":     return act_select_option(inp["dropdown"], inp["option"])
            if name == "key":        return act_press_key(inp["name"])
            if name == "scroll":     return act_scroll(inp.get("direction", "down"))
            if name == "read":       return act_read_page()
            if name == "url":        return act_read_url()
            if name == "wait":       return act_wait(inp.get("seconds", 2))
            if name == "wait_for":   return act_wait_for_text(inp["text"])
            if name == "smart_wait": return act_smart_wait(inp.get("reason", "page_change"), inp.get("timeout", 10))
            if name == "tabs":       return act_get_tabs()
            if name == "switch_tab": return act_switch_tab(inp["number"])
            if name == "close_tab":  return act_close_tab()
            if name == "back":
                return (
                    "⛔ BLOCKED: back() is disabled — going back destroys multi-page progress. "
                    "Instead, use look() to see what's on the current page and work FORWARD. "
                    "If you need a specific page, use goto() with the URL."
                )
            if name == "forward":    return act_forward()
            if name == "refresh":    return act_refresh()
            if name == "screenshot":
                result = act_screenshot()
                # Handle vision-capable screenshot: extract image for LLM
                if isinstance(result, dict) and result.get("_screenshot"):
                    # Store base64 data for injection into tool_result as image
                    # The base_agent will pick this up and send it to the LLM
                    self._last_screenshot_b64 = result.get("image_base64", "")
                    return result  # Return full dict — base_agent handles it
                return result
            if name == "js":
                # Guard: block DOM-modifying JS — agent should use click/type instead
                code_lower = inp["code"].lower()
                write_patterns = [".click(", ".submit(", ".value=", ".value =",
                                  "innerhtml", "innertext=", "innertext =",
                                  "dispatchevent", "setattribute", "removeattribute",
                                  ".focus(", ".blur(", "appendchild", "removechild",
                                  "createelement", "classlist.", "style."]
                if any(p in code_lower for p in write_patterns):
                    return (
                        "⛔ BLOCKED: JS is READ-ONLY. Your code appears to modify the DOM. "
                        "Use click() to click elements, type() to fill fields, fill_form() for forms. "
                        "JS should only be used to READ page data (e.g., 'return document.title')."
                    )
                return act_run_js(inp["code"])
            if name == "new_tab":   return act_new_tab(inp.get("url", ""))
            if name == "hold":      return act_press_and_hold(inp.get("target", "captcha"), inp.get("duration", 10))
            if name == "solve_captcha": return act_solve_captcha()
            if name == "read_otp" or name == "manage_account":
                # Handle both read_otp AND manage_account('read_otp') — brain sometimes
                # tells the agent to call manage_account instead of read_otp directly
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
            return f"Unknown browser tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"
