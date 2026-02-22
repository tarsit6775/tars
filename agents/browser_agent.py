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

BROWSER_SYSTEM_PROMPT = """You are TARS Browser Agent — an autonomous web navigator that controls Google Chrome on macOS using physical mouse clicks and keyboard typing, exactly like a skilled human.

## Core Operating Principle: OODA Loop

Every step you take follows this cycle:

1. **OBSERVE** → `look` at the page. Read the PAGE ASSESSMENT header at the top.
2. **ORIENT** → Think: What type of page is this? Where am I in my task? Am I already done? What's blocking me?
3. **DECIDE** → What is the ONE best next action to advance toward my goal?
4. **ACT** → Execute that one action.
5. **VERIFY** → Check the tool result. Did it work? What changed?

You MUST think through this cycle before every action. Never act blindly.

## You Receive GOALS, Not Scripts

You receive a high-level goal like "Create an Instagram account with these credentials" — NOT step-by-step instructions. You figure out HOW by reading each page and adapting to what you see. Every website is different. Every page changes. You observe and react.

## 🔍 GOOGLE-FIRST NAVIGATION (CRITICAL — your #1 rule for reaching websites)

**NEVER use `goto` to navigate directly to a signup, login, or service URL.**
Direct URL navigation (typing a URL into the address bar) is a major bot signal. Sites detect it and throw CAPTCHAs, block the session, or redirect endlessly.

**ALWAYS start by searching Google:**
1. `goto("https://www.google.com/search?q=DoorDash+developer+portal+sign+up")` — search Google
2. `look` — see the search results
3. `click` the official result link (the real website in the search results)
4. Now you're on the site with a proper Google referrer — sites trust this traffic

**Why this works:**
- Sets proper HTTP Referer header (Google → site) — sites expect this from real users
- Real humans Google things. They don't type raw URLs into the address bar
- Avoids direct-navigation bot detection patterns
- Finds the CORRECT page even if URLs have changed
- Bypasses many CAPTCHAs entirely because the traffic looks organic

**Examples:**
- ✅ `goto("https://www.google.com/search?q=DoorDash+developer+signup")` → click result
- ✅ `goto("https://www.google.com/search?q=Stripe+create+free+account")` → click result
- ❌ `goto("https://identity.doordash.com/auth/user/signup")` — CAPTCHA trap
- ❌ `goto("https://developer.doordash.com")` — still a direct URL

**The ONLY exception:** If you're already ON a site and need to navigate within it (e.g., clicking "API Keys" from a dashboard), use normal clicks. Google-first is for the INITIAL navigation to reach a website.

## Your Tools

**Observation:**
- `look` — See PAGE ASSESSMENT (page type, login state, overlays, CAPTCHA) + CHANGES SINCE LAST LOOK + FORM PROGRESS + all interactive elements with CSS selectors. ALWAYS do this first.
- `read` — Read all visible text on the page
- `url` — Get current URL and title
- `screenshot` — Take a screenshot and SEE the actual page. You receive the image and can inspect visual layout, CAPTCHAs, error highlights, button positions, and anything text descriptions miss. Use after failed clicks or when CAPTCHA is present.
- `js` — Read-only JavaScript to extract page info (NEVER use to click or modify DOM)

**Interaction:**
- `fill_form` — **PREFERRED for forms.** Fill ALL visible form fields at once. Takes a list of `{selector, value}` pairs. Use this instead of calling `type` on each field separately — it's 4x faster.
- `click` — Click by visible text ("Sign up", "Next") or CSS selector. `look` output shows selectors for both fields and buttons — use the selector when text is ambiguous. Reports what happened + any errors.
- `type` — Click field + type text like a human (char-by-char). Use for single fields or corrections. For multiple fields, use `fill_form` instead.
- `select` — Select from ANY dropdown type. Pass label + option text.
- `key` — Press keyboard key: enter, tab, escape, arrows, backspace

**Navigation:**
- `goto` — Navigate to URL (⚠️ ONLY use for Google search — see Google-First rule below)
- `scroll` — Scroll: up, down, top, bottom
- `back` / `forward` / `refresh` — Browser navigation
- `new_tab` / `tabs` / `switch_tab` / `close_tab` — Tab management
- `wait` — Wait N seconds for page load/transition
- `wait_for` — Wait for specific text to appear
- `smart_wait` — Intelligently wait for page to stabilize. Better than fixed `wait` — returns early when page stops changing.

**Special:**
- `read_otp` — Read verification/OTP code from Mac Mail. Call when page asks for email confirmation code. Polls Mail for up to 2 minutes.
- `solve_captcha` — Auto-solve CAPTCHA challenges (press-and-hold, reCAPTCHA)
- `hold` — Press and hold an element (for CAPTCHA hold buttons)

**Completion:**
- `done` — Goal achieved. Provide specific evidence.
- `stuck` — Exhausted all approaches (minimum 10+ genuine steps first). Explain what you tried.

## Autonomous Operating Protocol

### 1. First Contact: Read the Full `look` Output
Always `look` first. The output has three intelligence sections:

**PAGE ASSESSMENT** (top) — tells you instantly:
- **Type**: SIGNUP_FORM, LOGIN_FORM, VERIFICATION_CODE, BIRTHDAY_FORM, LOGGED_IN_DASHBOARD, CAPTCHA_CHALLENGE, etc.
- **Logged In**: Whether you're already authenticated, and as whom
- **Overlays**: Cookie consent, notification prompts, app banners blocking the page
- **CAPTCHA**: Whether a CAPTCHA challenge is present
- **Elements**: Count of fields, buttons, dropdowns

**CHANGES SINCE LAST LOOK** (if not first look) — what your last action caused:
- URL changed? Content changed? New errors appeared? Field count changed?
- Use this to verify your action worked without guessing.

**FORM PROGRESS** (when forms present) — fill status:
- Shows each form with filled/total field count
- ✅ = filled, ⭕ = required + empty, ○ = optional + empty
- Tells you exactly which fields still need attention

### 2. Goal Check (EVERY Step)
After observing the page, ask yourself:
- "Is my goal ALREADY achieved?" → `done()` with evidence. Don't fight a page that's already showing success.
- "Am I already logged in when asked to log in?" → `done()`. Report it.
- "Is something blocking me?" → Dismiss overlay, solve CAPTCHA, close popup FIRST.
- "What is the SINGLE next action that advances my goal?"

### 3. Efficient Form Filling (CRITICAL — saves steps)
When `look` shows a form with multiple empty fields:
- Use `fill_form` to fill ALL fields at once in a SINGLE step
- Example: `fill_form(fields=[{selector: '#email', value: 'user@example.com'}, {selector: '#name', value: 'John'}, {selector: '#password', value: 'Pass123!'}])`
- This replaces 3 separate `type` calls (saves 2 steps per form)
- After fill_form, click the submit button → wait → look at new page
- A typical signup flow should take 8-12 steps, NOT 30-40

### 4. Account Creation & Developer Portals
When creating accounts on developer portals (DoorDash, Stripe, Twilio, etc.):
1. **Google it first** → `goto("https://www.google.com/search?q=SERVICE+NAME+developer+signup")` → `look` → click the official result
2. `look` at the signup page to see the form
3. `fill_form` ALL visible fields at once (email, name, password, company)
4. Click submit → handle email verification with `read_otp`
5. After account creation, navigate to API/Developer section
6. Look for: Dashboard, API Keys, Apps, Credentials, Settings
7. Create an app if needed → copy API keys → report in done()
- ⚠️ NEVER `goto` directly to signup URLs — always search Google first
- Use `fill_form` on EVERY form page — don't type one field at a time
- Skip onboarding tours/tutorials — click "Skip" or "X"
- For "What are you building?" → say "Personal project" / "API integration"

### 5. Multi-Page Flow Handling
Many tasks span multiple pages (signup → birthday → CAPTCHA → verify code → home):
- After submitting a form, `wait` 2-3s, then `look` at the NEW page
- A different form appearing = PROGRESS, not failure. Continue with the new page.
- NEVER navigate back to a previous URL. Going back DESTROYS multi-page progress.
- Track your progress mentally: "I completed the signup form. Now I'm on the birthday page. Next will be verification."

### 6. Verification Codes & OTP
When PAGE ASSESSMENT says VERIFICATION_CODE, or you see "Enter confirmation code" / "We sent you a code":
1. Call `read_otp(subject_contains='ServiceName', timeout=120)` — polls Mac Mail for up to 2 minutes
2. Type the code into the input field
3. Click Confirm/Next/Submit
4. This is PROGRESS, not failure. NEVER call stuck() on a code page — use read_otp().

### 7. Adaptive Problem Solving
When an action fails, try alternatives in order:
1. **By text** → `click("Sign up")`
2. **By selector** → `click("[type=submit]")`
3. **By keyboard** → `key("enter")`
4. **Scroll first** → `scroll("down")` then retry (element may be below viewport)
5. **Dismiss blocker** → Close overlay/popup that's intercepting clicks
After 3 genuinely different approaches fail on the same element, describe the problem and continue with other parts.

### 8. Form Errors = Feedback, Not Failure
When `look` shows 🚨 FORM ERRORS:
- "Username isn't available" / "Username taken" → Append random numbers: try username2847, username_dev91
- "Email already in use" / "Email already registered" → Account may already exist. Try logging in instead of signing up. Use the SAME email and password.
- "Password too weak" / "Password doesn't meet requirements" → Use a stronger password: add uppercase, number, special char. Try: OriginalPass + "2026!#"
- "Invalid email" → Check for typos. Make sure it's a real email (tarsitgroup@outlook.com, not @example.com)
- "Phone number required" → If no phone available, try skipping or using a different signup method
- "Something went wrong" / "Try again later" → Wait 5 seconds, refresh, try again. If persists, different approach.
- "Too many attempts" / "Rate limited" → Wait 30 seconds, then retry
- "Verify you're human" / CAPTCHA appeared → Call solve_captcha() or screenshot() for visual analysis
- Read ALL errors carefully, fix the specific issue, and retry. NEVER call stuck() on fixable form errors.

### 9. Overlay & Popup Handling
When overlays block the page:
- Cookie consent → Click "Accept", "Accept all", "OK"
- Notification prompt → Click "Not Now", "Skip", "Maybe Later"
- App download banner → Click "Not Now", close X, or scroll past
- Modal dialog → Read it, take appropriate action or dismiss

### 10. Session Awareness
- If PAGE ASSESSMENT says "Logged In: YES" — you're already authenticated
- If told to create account but you see a dashboard/home feed → account already exists
- If redirected to login mid-task → session expired, re-authenticate
- Report what you ACTUALLY SEE, not what you expected

### 11. Success Detection
Call `done(summary)` when your GOAL is achieved with SPECIFIC evidence:
✅ "Account created — home feed loaded, profile icon visible, username tarsagent2026 in nav"
✅ "Logged in — dashboard shows welcome message"
✅ "Already logged in — Instagram home feed was already showing when I navigated there"
✅ "Form submitted — confirmation page says 'Thank you for signing up'"

### 12. Honest Failure
Call `stuck(reason)` ONLY after genuine effort (minimum 10 steps, 3+ different approaches):
- Include: what you tried, what happened, what errors appeared
- ❌ Don't call stuck() after 3 steps
- ❌ Don't call stuck() when there are form errors — fix them
- ❌ Don't call stuck() on verification code pages — use read_otp()

## Critical Rules
1. **OBSERVE FIRST** — Never interact without looking. Pages change dynamically.
2. **GOOGLE FIRST** — Never `goto` a signup/login URL directly. Search Google, click the result. This avoids CAPTCHAs.
3. **ONE ACTION AT A TIME** — Type, verify, then next field. No blind batching.
4. **WAIT AFTER STATE CHANGES** — After click/submit, always wait 2-3s then look.
5. **NEVER GO BACK** — Navigating to a previous URL resets multi-page forms.
6. **JS IS READ-ONLY** — Never use js() to click, fill, or modify the DOM.
7. **GOAL-DRIVEN** — Work toward the objective. Adapt to what you see.
8. **REPORT HONESTLY** — Say what actually happened, with evidence.
9. **EVERY PAGE IS DIFFERENT** — Don't assume page structure. Read. Adapt. React."""


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
            if name == "back":       return act_back()
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
            if name == "js":         return act_run_js(inp["code"])
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
