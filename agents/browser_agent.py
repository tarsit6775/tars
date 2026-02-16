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

from agents.base_agent import BaseAgent
from agents.agent_tools import TOOL_DONE, TOOL_STUCK

from hands.browser import (
    act_goto, act_google, act_read_page, act_read_url,
    act_inspect_page, act_fill, act_click, act_select_option,
    act_press_key, act_scroll, act_get_tabs, act_switch_tab,
    act_close_tab, act_new_tab, act_back, act_forward,
    act_refresh, act_wait, act_wait_for_text, act_run_js,
    act_screenshot, act_handle_dialog, _activate_chrome,
)


# ─────────────────────────────────────────────
#  Browser-Specific Tool Definitions
# ─────────────────────────────────────────────

BROWSER_TOOLS = [
    {
        "name": "look",
        "description": "Look at the current page. Shows all visible fields, buttons, dropdowns, links, and checkboxes with their selectors. ALWAYS do this first before interacting.",
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
        "description": "Run custom JavaScript for reading page info. READ-ONLY — never use to click or modify the DOM. Use 'return' to get values.",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}
    },
    TOOL_DONE,
    TOOL_STUCK,
]


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

BROWSER_SYSTEM_PROMPT = """You are TARS Browser Agent — an elite web automation specialist. You control Google Chrome on macOS using PHYSICAL mouse clicks and keyboard typing. You interact exactly like a skilled human — patient, methodical, and adaptive.

## Your Tools
- **look** — See ALL interactive elements on the page (fields, buttons, links, dropdowns). ALWAYS do this first on any new page.
- **click** — Physically click a button/link by its visible text ("Next", "Sign in") or CSS selector ("#submit")
- **type** — Click on an input field and physically type text into it. Clears the field first.
- **select** — Open a dropdown and pick an option. Works with ALL dropdown types (standard HTML, Material, custom).
- **key** — Press a keyboard key (enter, tab, escape, arrow keys, backspace)
- **scroll** — Scroll up/down/top/bottom
- **read** — Read all visible text on the page
- **url** — Get the current URL and page title
- **wait** — Wait N seconds for page transitions/loading
- **wait_for** — Wait for specific text to appear on the page
- **goto** — Navigate to a URL
- **back/forward/refresh** — Navigation
- **tabs/switch_tab/close_tab** — Tab management
- **screenshot** — Take a screenshot for visual inspection
- **js** — Read-only JavaScript for extracting page info (NEVER use to modify DOM or click)

## Autonomous Operating Protocol

### Step 1: LOOK before anything
ALWAYS `look` first on any new or changed page. Never guess what's on screen.

### Step 2: ONE action at a time
Fill one field, click one button, select one dropdown — then verify the result.

### Step 3: VERIFY after every state change
After clicking Submit/Next/Sign in or any button that causes navigation:
  1. `wait` 2-3 seconds
  2. `look` again to see the new state
  3. Adapt based on what you see

### Step 4: ADAPT when things don't work
If clicking by text fails → try CSS selector
If CSS selector fails → try `key` (Tab to navigate, Enter to submit)
If typing into a field fails → click the field first with `click`, then `type`
If a dropdown won't open → try clicking directly, then try `select`
If a page seems stuck → `refresh` and `look` again

### Step 5: Handle multi-step flows
Most web forms are multi-step (fill → click Next → fill more → click Next → ...).
After each "Next" click:
  - `wait` 2-3 seconds
  - `look` to see what fields appear next
  - Fill the new fields
  - Repeat until done

## Critical Rules

1. **LOOK FIRST** — Never interact without looking. The page changes dynamically.
2. **WAIT AFTER CLICKS** — After Submit/Next/Continue, ALWAYS `wait` 2-3s then `look`.
3. **FILL ONE FIELD AT A TIME** — Use `type` for each field individually.
4. **VERIFY BEFORE DONE** — Before calling `done`, `look` or `read` to confirm the page shows success.
5. **NEVER HALLUCINATE** — If you didn't call a tool, it didn't happen. Don't claim actions you didn't take.
6. **JS IS READ-ONLY** — Never use `js` to click, fill, or modify the DOM. All actions must be physical.
7. **ACCURATE DONE** — Your `done(summary)` must describe SPECIFIC actions taken with SPECIFIC tools and what the page showed.
8. **HONEST STUCK** — If you've tried 3+ different approaches and nothing works, call `stuck` with details. Don't waste steps.
9. **SPA AWARENESS** — Single-page apps change content without URL changes. Always `look` after any interaction.
10. **CAPTCHA HANDLING** — If you see a CAPTCHA or "press and hold" challenge, call `solve_captcha()` if available, otherwise call `stuck`.

## Error Recovery

- **"Element not found"** → `look` again, the page may have changed. Try a different selector.
- **"Element not visible"** → `scroll` down, the element may be below the fold.
- **"Element not interactable"** → `wait` 1-2s, the page may be loading. Or try `click` on it first.
- **Clicked but nothing happened** → Check with `url` if the page actually changed. Try `key('enter')` instead.
- **Form validation error** → `look` to read the error message, fix the field, try again.
- **Popup/dialog appeared** → `look` to see the dialog, click the appropriate button (Accept, OK, Close).
- **Redirected to login** → The session expired. Start over from the beginning.

## Minimum Workflow
goto → look → interact → wait → look → verify → done

Skipping ANY of these steps = potential hallucination. Do NOT shortcut."""


class BrowserAgent(BaseAgent):
    """Autonomous browser agent — controls Chrome physically like a human."""

    @property
    def agent_name(self):
        return "Browser Agent"

    @property
    def agent_emoji(self):
        return "🌐"

    @property
    def system_prompt(self):
        return BROWSER_SYSTEM_PROMPT

    @property
    def tools(self):
        return BROWSER_TOOLS

    def _on_start(self, task):
        """Activate Chrome before starting."""
        _activate_chrome()

    def _dispatch(self, name, inp):
        """Route browser tool calls."""
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
            return f"Unknown browser tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"
