"""
╔══════════════════════════════════════════════════════════════╗
║       TARS — Browser Engine v2: CDP (Chrome DevTools)        ║
╠══════════════════════════════════════════════════════════════╣
║  Direct websocket to Chrome. No cliclick. No screen coords.  ║
║  No multi-monitor bugs. Clicks by selector/text via CDP.     ║
║                                                              ║
║  How it works:                                               ║
║    1. Chrome runs with --remote-debugging-port=9222          ║
║    2. We connect via websocket (CDP protocol)                ║
║    3. Find elements with Runtime.evaluate (JS)               ║
║    4. Click with Input.dispatchMouseEvent (viewport coords)  ║
║    5. Type with Input.insertText (native input pipeline)     ║
║    6. Navigate with Page.navigate                            ║
║                                                              ║
║  Clicks dispatch real browser input events — passes bot      ║
║  detection the same way a real mouse click would.            ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import time
import os
import base64
import tempfile
import random
import threading
import urllib.parse

from hands.cdp import CDP, CDP_PORT

import logging
logger = logging.getLogger("TARS")


# ═══════════════════════════════════════════════════════
#  Module State — Singleton CDP Connection
# ═══════════════════════════════════════════════════════

_cdp = None
_browser_lock = threading.RLock()  # Serializes all browser operations across agents (RLock: reentrant so act_fill_form→act_fill doesn't deadlock)


def _with_browser_lock(func):
    """Decorator that serializes browser operations.
    
    Prevents concurrent agents from interleaving CDP commands
    (e.g., one agent navigating while another reads the page).
    """
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _browser_lock:
            return func(*args, **kwargs)
    return wrapper


def _ensure():
    """Ensure we have a live CDP connection. Called before every action.
    
    If the connection dropped (Chrome crash, WS timeout), creates a fresh
    CDP instance instead of reusing the dead one.
    """
    global _cdp
    if _cdp and _cdp.connected:
        _auto_handle_dialogs()
        return
    # Connection dead or never created — always start fresh
    _cdp = CDP()
    _cdp.ensure_connected()


def _auto_handle_dialogs():
    """Auto-dismiss any JavaScript alert/confirm/prompt that's blocking."""
    for ev in _cdp.drain_events("Page.javascriptDialogOpening"):
        msg = ev.get("message", "")
        try:
            _cdp.send("Page.handleJavaScriptDialog", {"accept": True})
            logger.info(f"    🔔 Auto-accepted dialog: {msg[:80]}")
        except Exception:
            pass


_consecutive_timeouts = 0  # Track repeated CDP timeouts

def _js(code):
    """Execute JavaScript in the active tab. Returns string result.
    
    On CDP timeout: navigates to about:blank to unstick the browser.
    After 3+ consecutive timeouts: forces full CDP reconnect.
    """
    global _cdp, _consecutive_timeouts
    _ensure()
    try:
        r = _cdp.send("Runtime.evaluate", {
            "expression": code,
            "returnByValue": True,
            "awaitPromise": False,
        })
        _consecutive_timeouts = 0  # Reset on success
        if r.get("exceptionDetails"):
            exc = r["exceptionDetails"]
            text = exc.get("text", "")
            # Try to get the actual error message
            if "exception" in exc:
                text = exc["exception"].get("description", text)
            return f"JS_ERROR: {text}"
        val = r.get("result", {}).get("value")
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)
    except TimeoutError as e:
        _consecutive_timeouts += 1
        logger.warning(f"    ⚠️ CDP timeout #{_consecutive_timeouts}: {str(e)[:80]}")
        # Try to unstick the browser by navigating to a blank page
        try:
            if _consecutive_timeouts >= 3:
                # Force full reconnect after 3+ consecutive timeouts
                logger.warning(f"    🔄 Forcing CDP reconnect after {_consecutive_timeouts} consecutive timeouts")
                if _cdp:
                    try:
                        _cdp.connected = False
                    except Exception:
                        pass
                    _cdp = None
                _cdp = CDP()
                _cdp.ensure_connected()
                # Navigate to blank page to start clean
                _cdp.send("Page.navigate", {"url": "about:blank"})
                time.sleep(1)
                _consecutive_timeouts = 0
            else:
                # Try navigating to about:blank to unstick
                _cdp.send("Page.navigate", {"url": "about:blank"}, timeout=10)
                time.sleep(1)
        except Exception:
            pass
        return f"JS_ERROR: CDP timeout after 30s: {str(e)[:60]}"
    except Exception as e:
        _consecutive_timeouts += 1
        if _consecutive_timeouts >= 3:
            # Force reconnect on repeated failures
            logger.warning(f"    🔄 Forcing CDP reconnect after {_consecutive_timeouts} consecutive errors")
            if _cdp:
                try:
                    _cdp.connected = False
                except Exception:
                    pass
                _cdp = None
            _consecutive_timeouts = 0
        return f"JS_ERROR: {e}"


def _reset_page(navigate=False):
    """Reset internal state between agent deployments.
    
    Args:
        navigate: If True, also navigate to about:blank. Default False
                  to preserve page state for multi-step browser flows
                  (e.g. agent #1 reaches birthday page, agent #2 continues).
    """
    global _consecutive_timeouts, _last_page_state
    _consecutive_timeouts = 0
    _last_page_state = None  # Clear page diff cache
    try:
        _ensure()
        if navigate:
            _cdp.send("Page.navigate", {"url": "about:blank"}, timeout=10)
            time.sleep(0.5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  CDP Input Helpers — Real browser events
# ═══════════════════════════════════════════════════════

def _bezier_point(t, p0, p1, p2, p3):
    """Calculate a point on a cubic Bezier curve at parameter t."""
    u = 1 - t
    return (u*u*u*p0 + 3*u*u*t*p1 + 3*u*t*t*p2 + t*t*t*p3)


def _human_mouse_move(target_x, target_y, steps=None):
    """Move mouse to target using a Bezier curve (human-like arc).

    Instead of teleporting directly to the click point, this traces
    a natural curved path that mimics human hand movement. Anti-bot
    systems track mouse movement patterns.
    """
    # Get current (or random starting) position
    start_x = target_x + random.randint(-200, 200)
    start_y = target_y + random.randint(-150, 150)

    # Generate control points for a natural-looking curve
    mid_x = (start_x + target_x) / 2 + random.randint(-80, 80)
    mid_y = (start_y + target_y) / 2 + random.randint(-60, 60)
    cp1_x = start_x + (mid_x - start_x) * 0.4 + random.randint(-30, 30)
    cp1_y = start_y + (mid_y - start_y) * 0.4 + random.randint(-20, 20)
    cp2_x = target_x + (mid_x - target_x) * 0.4 + random.randint(-20, 20)
    cp2_y = target_y + (mid_y - target_y) * 0.4 + random.randint(-15, 15)

    if steps is None:
        steps = random.randint(8, 16)

    for i in range(steps + 1):
        t = i / steps
        # Ease-in-out timing (slow at start and end, fast in middle)
        t = t * t * (3 - 2 * t)
        x = int(_bezier_point(t, start_x, cp1_x, cp2_x, target_x))
        y = int(_bezier_point(t, start_y, cp1_y, cp2_y, target_y))
        _cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
        })
        time.sleep(random.uniform(0.008, 0.025))


def _cdp_click_at(x, y):
    """Dispatch a real mouse click at viewport coordinates via CDP.

    Includes:
    - Bezier curve mouse movement (natural arc path)
    - Micro-randomization of position (±3px jitter)
    - Variable timing between press and release
    - Occasional micro-movements during hold
    """
    # Small random offset to avoid exact-center bot pattern
    jitter_x = x + random.randint(-3, 3)
    jitter_y = y + random.randint(-3, 3)

    # Human-like mouse movement to target (Bezier curve)
    try:
        _human_mouse_move(jitter_x, jitter_y)
    except Exception:
        # Fallback: simple direct move
        _cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": jitter_x, "y": jitter_y
        })

    time.sleep(random.uniform(0.02, 0.08))
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": jitter_x, "y": jitter_y,
        "button": "left", "clickCount": 1,
    })
    # Human hold time — variable, occasionally longer (hesitation)
    hold_time = random.uniform(0.04, 0.12)
    if random.random() < 0.15:
        hold_time += random.uniform(0.05, 0.15)
    time.sleep(hold_time)
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": jitter_x, "y": jitter_y,
        "button": "left", "clickCount": 1,
    })
    time.sleep(random.uniform(0.1, 0.2))


def _cdp_type_text(text):
    """Type text via CDP's native input pipeline. Triggers all events."""
    _cdp.send("Input.insertText", {"text": text})
    time.sleep(0.05)


def _cdp_type_human(text, min_delay=0.03, max_delay=0.12):
    """Type text character-by-character with random delays.

    Sends individual keyDown/keyUp/char events per character,
    mimicking real human typing. Critical for React-based sites
    (Instagram, etc.) that track individual key events and detect
    instant Input.insertText as bot behavior.

    Features:
    - Variable speed (faster for common chars, slower for special chars)
    - Occasional pauses (thinking/hesitation)
    - Speed variation within the same word
    - Burst typing patterns (fast-slow-fast)
    Average speed: ~60-90 WPM (human-like).
    """
    # Simulate typing speed variation — faster in the middle of words
    word_position = 0
    for i, ch in enumerate(text):
        # Send char event (works for all printable characters)
        _cdp.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": ch,
            "text": ch,
            "unmodifiedText": ch,
        })
        time.sleep(0.01)
        _cdp.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": ch,
        })

        # Variable delay based on character type
        if ch == ' ':
            # Space between words — slightly longer pause
            delay = random.uniform(0.08, 0.2)
            word_position = 0
        elif ch in '@._-':
            # Special chars — slightly slower
            delay = random.uniform(0.06, 0.18)
        elif word_position < 2:
            # Start of word — slower
            delay = random.uniform(min_delay + 0.02, max_delay + 0.02)
        else:
            # Mid-word — faster (muscle memory)
            delay = random.uniform(min_delay, max_delay * 0.8)

        # Occasional longer pause (thinking/hesitation) — ~6% chance
        if random.random() < 0.06:
            delay += random.uniform(0.2, 0.5)

        # Occasional burst (fast typing) — ~10% chance
        if random.random() < 0.10:
            delay = random.uniform(0.015, 0.04)

        word_position += 1
        time.sleep(delay)


import re as _re

def _fix_selector(selector):
    """Fix CSS selectors that LLMs break by stripping escape characters.

    Common issue: getSel() outputs '#fieldWrapper-\\:r1\\:' but the LLM
    passes '#fieldWrapper-:r1:' which is invalid CSS (colons = pseudo-class).
    This converts broken '#' selectors to safe '[id="..."]' attribute selectors.
    Also handles selectors the LLM may have mangled in other ways.
    """
    if not selector or not isinstance(selector, str):
        return selector

    selector = selector.strip()

    # Already an attribute selector — safe as-is
    if selector.startswith("["):
        return selector

    # ID selector with special CSS chars that need escaping
    if selector.startswith("#"):
        raw_id = selector[1:]
        # Check if the ID contains chars that are special in CSS selectors
        # (colons, dots, brackets, etc.) — these break querySelector
        if _re.search(r'[:.#\[\]()~>+,\s]', raw_id):
            return f'[id="{raw_id}"]'

    return selector


def _cdp_key(key, code, key_code=0, modifiers=0):
    """Press and release a single key via CDP."""
    params = {
        "type": "keyDown",
        "key": key,
        "code": code,
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
        "modifiers": modifiers,
    }
    _cdp.send("Input.dispatchKeyEvent", params)
    time.sleep(0.02)
    params["type"] = "keyUp"
    _cdp.send("Input.dispatchKeyEvent", params)
    time.sleep(0.02)


# Key name → (CDP key, CDP code, virtual key code)
KEY_MAP = {
    "enter":     ("Enter",      "Enter",      13),
    "return":    ("Enter",      "Enter",      13),
    "tab":       ("Tab",        "Tab",         9),
    "escape":    ("Escape",     "Escape",     27),
    "esc":       ("Escape",     "Escape",     27),
    "space":     (" ",          "Space",      32),
    "backspace": ("Backspace",  "Backspace",   8),
    "delete":    ("Delete",     "Delete",     46),
    "up":        ("ArrowUp",    "ArrowUp",    38),
    "down":      ("ArrowDown",  "ArrowDown",  40),
    "left":      ("ArrowLeft",  "ArrowLeft",  37),
    "right":     ("ArrowRight", "ArrowRight", 39),
    "home":      ("Home",       "Home",       36),
    "end":       ("End",        "End",        35),
    "pageup":    ("PageUp",     "PageUp",     33),
    "pagedown":  ("PageDown",   "PageDown",   34),
}


def _find_element_coords(target):
    """Find an element by visible text OR CSS selector. Returns (x, y) or None.

    If target starts with # . [ → CSS selector
    Otherwise → search by visible text (exact > case-insensitive > substring)
    Automatically scrolls element into view if needed.
    """
    # CSS selector detection: # for IDs, . for classes, [ for attribute selectors
    # But [Next] is NOT a CSS selector — it's bracket-wrapped text.
    # Real CSS attribute selectors always contain = (e.g. [name="email"])
    is_css = len(target) > 0 and (
        target[0] in ("#", ".") or 
        (target[0] == "[" and "=" in target)
    )

    if is_css:
        # CSS selector path — fix broken selectors from LLMs
        target = _fix_selector(target)
        safe_sel = target.replace("\\", "\\\\").replace("'", "\\'")
        raw = _js(f"""
            (function() {{
                var el = document.querySelector('{safe_sel}');
                if (!el) return '';
                el.scrollIntoView({{block: 'center', behavior: 'instant'}});
                var r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return '';
                return JSON.stringify({{
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    tag: el.tagName,
                    text: (el.innerText||el.value||'').trim().substring(0,50)
                }});
            }})()
        """)
    else:
        # Text search path
        safe_text = target.replace("\\", "\\\\").replace("'", "\\'")
        raw = _js(f"""
            (function() {{
                var target = '{safe_text}';
                var targetLower = target.toLowerCase();
                var selectors = 'button, a, [role=button], input[type=submit], input[type=button], span, div, label, li, p, [role=tab], [role=menuitem], [role=option], [role=link], h1, h2, h3, h4, td, th';
                var els = document.querySelectorAll(selectors);
                var best = null;
                var bestScore = 999;

                for (var i = 0; i < els.length; i++) {{
                    var el = els[i];
                    var r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    // Skip invisible
                    var s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;

                    var t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();

                    // Score: 0=exact, 1=case-insensitive, 2=contains (shorter preferred)
                    if (t === target && bestScore > 0) {{
                        best = el; bestScore = 0;
                    }} else if (t.toLowerCase() === targetLower && bestScore > 1) {{
                        best = el; bestScore = 1;
                    }} else if (t.toLowerCase().indexOf(targetLower) !== -1 && t.length < 200 && bestScore > 2) {{
                        best = el; bestScore = 2;
                    }}
                    if (bestScore === 0) break;
                }}

                if (!best) return '';
                best.scrollIntoView({{block: 'center', behavior: 'instant'}});
                // Re-read rect after scroll
                var r2 = best.getBoundingClientRect();
                return JSON.stringify({{
                    x: Math.round(r2.x + r2.width/2),
                    y: Math.round(r2.y + r2.height/2),
                    tag: best.tagName,
                    text: (best.innerText||best.value||'').trim().substring(0,50)
                }});
            }})()
        """)

    if not raw or raw.startswith("JS_ERROR"):
        return None

    try:
        data = json.loads(raw)
        return (data["x"], data["y"])
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
#  Navigation
# ═══════════════════════════════════════════════════════

def act_goto(url):
    """Navigate to a URL."""
    _ensure()
    # Drain old load events
    _cdp.drain_events("Page.loadEventFired")
    _cdp.drain_events("Page.frameStoppedLoading")

    try:
        _cdp.send("Page.navigate", {"url": url})
    except Exception as e:
        return f"ERROR: Navigation failed: {e}"

    # Wait for page to load
    _wait_for_load(15)
    time.sleep(0.5)
    title = _js("document.title") or ""
    return f"Opened {url} — {title}"


def act_back():
    """Go back in browser history."""
    _ensure()
    _js("history.back()")
    time.sleep(1.5)
    _wait_for_load(10)
    title = _js("document.title") or ""
    return f"Back → {title}"


def act_forward():
    """Go forward in browser history."""
    _ensure()
    _js("history.forward()")
    time.sleep(1.5)
    _wait_for_load(10)
    title = _js("document.title") or ""
    return f"Forward → {title}"


def act_refresh():
    """Reload the current page."""
    _ensure()
    _cdp.drain_events("Page.loadEventFired")
    _cdp.send("Page.reload")
    _wait_for_load(15)
    time.sleep(0.5)
    title = _js("document.title") or ""
    return f"Refreshed → {title}"


def _wait_for_load(timeout=10):
    """Wait for page to finish loading via CDP events + readyState check."""
    # First try CDP events
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _cdp.drain_events("Page.loadEventFired"):
            time.sleep(0.3)
            return True
        if _cdp.drain_events("Page.frameStoppedLoading"):
            time.sleep(0.3)
            return True
        # Also check readyState as fallback
        state = _js("document.readyState")
        if state in ("complete", "interactive"):
            time.sleep(0.3)
            return True
        time.sleep(0.1)
    return False


# ═══════════════════════════════════════════════════════
#  Page Diffing — Track what changed between looks
# ═══════════════════════════════════════════════════════

_last_page_state = {}  # {url, title, field_count, button_count, text_hash, errors}


def _capture_page_state():
    """Capture a lightweight page state snapshot for diffing."""
    try:
        raw = _js(r"""(function() {
            var fields = document.querySelectorAll('input:not([type=hidden]), textarea, select');
            var visFields = 0;
            for (var i = 0; i < fields.length; i++) {
                var r = fields[i].getBoundingClientRect();
                if (r.width > 0 && r.height > 0) visFields++;
            }
            var buttons = document.querySelectorAll('button, [role=button], input[type=submit]');
            var visButtons = 0;
            for (var j = 0; j < buttons.length; j++) {
                var rb = buttons[j].getBoundingClientRect();
                if (rb.width > 0 && rb.height > 0) visButtons++;
            }
            var text = (document.body ? document.body.innerText : '').substring(0, 3000);
            var hash = 0;
            for (var k = 0; k < text.length; k++) {
                hash = ((hash << 5) - hash + text.charCodeAt(k)) | 0;
            }
            var errs = [];
            document.querySelectorAll('[role=alert], .error, .field-error, .form-error').forEach(function(el) {
                var s = window.getComputedStyle(el);
                if (s.display !== 'none' && s.visibility !== 'hidden') {
                    var t = el.innerText.trim();
                    if (t && t.length > 2 && t.length < 200) errs.push(t);
                }
            });
            return JSON.stringify({
                url: location.href,
                title: document.title || '',
                fields: visFields,
                buttons: visButtons,
                textHash: hash,
                errors: errs.slice(0, 5),
                scrollY: Math.round(window.scrollY)
            });
        })()""")
        if raw and not raw.startswith("JS_ERROR"):
            return json.loads(raw)
    except Exception:
        pass
    return {}


def _compute_page_diff(old_state, new_state):
    """Compute what changed between two page states. Returns human-readable diff."""
    if not old_state or not new_state:
        return ""
    changes = []
    if old_state.get("url") != new_state.get("url"):
        changes.append(f"🔀 URL changed: {new_state.get('url', '?')}")
    if old_state.get("title") != new_state.get("title"):
        changes.append(f"📄 Title changed: {new_state.get('title', '?')}")
    old_f, new_f = old_state.get("fields", 0), new_state.get("fields", 0)
    if old_f != new_f:
        changes.append(f"📝 Fields: {old_f} → {new_f}")
    old_b, new_b = old_state.get("buttons", 0), new_state.get("buttons", 0)
    if old_b != new_b:
        changes.append(f"🔘 Buttons: {old_b} → {new_b}")
    if old_state.get("textHash") != new_state.get("textHash"):
        changes.append("📝 Page content changed")
    old_errs = set(old_state.get("errors", []))
    new_errs = set(new_state.get("errors", []))
    appeared = new_errs - old_errs
    if appeared:
        changes.append(f"⚠️ New errors: {' | '.join(list(appeared)[:3])}")
    if not changes:
        changes.append("No visible changes detected")
    return " • ".join(changes)


# ═══════════════════════════════════════════════════════
#  Form Intelligence — Auto-detect form structure
# ═══════════════════════════════════════════════════════

_FORM_ANALYSIS_JS = r"""(function() {
    var forms = document.querySelectorAll('form');
    var result = { forms: [], standalone_fields: [] };

    function isVis(el) {
        if (!el) return false;
        var s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        var r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    function fieldInfo(el) {
        var type = el.type || el.tagName.toLowerCase();
        var name = el.name || '';
        var label = '';
        if (el.id) {
            var lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (lbl) label = lbl.innerText.trim();
        }
        if (!label) label = el.getAttribute('aria-label') || el.placeholder || el.title || name;
        var val = el.value || '';
        var req = el.required || el.getAttribute('aria-required') === 'true';
        return { type: type, name: name, label: label.substring(0, 50), filled: val.length > 0, required: req };
    }

    forms.forEach(function(form) {
        if (!isVis(form)) return;
        var fields = [];
        form.querySelectorAll('input:not([type=hidden]):not([type=submit]), textarea, select').forEach(function(f) {
            if (isVis(f)) fields.push(fieldInfo(f));
        });
        var action = form.action || '';
        var method = form.method || 'get';
        var submitBtn = form.querySelector('button[type=submit], input[type=submit], button:not([type])');
        var submitText = submitBtn ? (submitBtn.innerText || submitBtn.value || 'Submit').trim() : '';
        if (fields.length > 0) {
            result.forms.push({
                fields: fields,
                action: action.substring(0, 100),
                method: method,
                submit_text: submitText.substring(0, 40),
                field_count: fields.length,
                filled_count: fields.filter(function(f) { return f.filled; }).length
            });
        }
    });

    // Standalone fields not in any form
    document.querySelectorAll('input:not([type=hidden]):not([type=submit]), textarea, select').forEach(function(el) {
        if (!isVis(el)) return;
        if (el.closest('form')) return;
        result.standalone_fields.push(fieldInfo(el));
    });

    return JSON.stringify(result);
})()"""


def _analyze_forms():
    """Analyze all forms on the page. Returns form structure with fill state."""
    try:
        raw = _js(_FORM_ANALYSIS_JS)
        if raw and not raw.startswith("JS_ERROR"):
            return json.loads(raw)
    except Exception:
        pass
    return {"forms": [], "standalone_fields": []}


def _format_form_intelligence(form_data):
    """Format form analysis into agent-readable text."""
    if not form_data:
        return ""
    parts = []
    forms = form_data.get("forms", [])
    for i, form in enumerate(forms):
        fc = form.get("field_count", 0)
        filled = form.get("filled_count", 0)
        submit = form.get("submit_text", "Submit")
        parts.append(f"📋 Form {i+1}: {filled}/{fc} fields filled, submit='{submit}'")
        for f in form.get("fields", []):
            status = "✅" if f.get("filled") else ("⭕" if f.get("required") else "○")
            parts.append(f"  {status} {f.get('label', '?')} ({f.get('type', '?')})")
    standalone = form_data.get("standalone_fields", [])
    if standalone:
        parts.append(f"📋 Standalone fields: {len(standalone)}")
        for f in standalone[:5]:
            status = "✅" if f.get("filled") else "○"
            parts.append(f"  {status} {f.get('label', '?')} ({f.get('type', '?')})")
    return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════
#  Smart Wait — Adaptive waiting based on page load state
# ═══════════════════════════════════════════════════════

def act_smart_wait(reason="page_change", timeout=10):
    """Intelligently wait for the page to stabilize after an action.

    Monitors DOM mutations, network activity, and readyState.
    Returns early when stable rather than waiting a fixed duration.
    """
    _ensure()
    start = time.time()
    timeout = min(int(timeout), 30)

    # Capture initial state
    initial_url = _js("location.href") or ""
    initial_hash = _js("""(function() {
        var t = (document.body ? document.body.innerText : '').substring(0, 2000);
        var h = 0; for (var i = 0; i < t.length; i++) h = ((h << 5) - h + t.charCodeAt(i)) | 0;
        return '' + h;
    })()""")

    # Wait for readyState first
    for _ in range(timeout * 4):
        state = _js("document.readyState")
        if state == "complete":
            break
        time.sleep(0.25)

    # Check if URL changed (navigation)
    current_url = _js("location.href") or ""
    if current_url != initial_url:
        time.sleep(0.5)  # Small extra wait for new page
        elapsed = round(time.time() - start, 1)
        return f"Page navigated to {current_url} ({elapsed}s)"

    # Wait for content to stabilize (DOM stops changing)
    stable_count = 0
    last_hash = initial_hash
    for _ in range(timeout * 2):
        time.sleep(0.5)
        current_hash = _js("""(function() {
            var t = (document.body ? document.body.innerText : '').substring(0, 2000);
            var h = 0; for (var i = 0; i < t.length; i++) h = ((h << 5) - h + t.charCodeAt(i)) | 0;
            return '' + h;
        })()""")
        if current_hash == last_hash:
            stable_count += 1
            if stable_count >= 2:
                elapsed = round(time.time() - start, 1)
                return f"Page stabilized ({elapsed}s)"
        else:
            stable_count = 0
        last_hash = current_hash
        if time.time() - start > timeout:
            break

    elapsed = round(time.time() - start, 1)
    return f"Waited {elapsed}s (timeout — page may still be loading)"


# ═══════════════════════════════════════════════════════
#  Anti-Detection — Human behavior simulation
# ═══════════════════════════════════════════════════════

def _human_mouse_move(target_x, target_y, steps=None):
    """Move mouse along a curved path to target coordinates.

    Instead of teleporting, generates a Bezier-like curve with
    random control points for natural mouse movement.
    """
    # Get current mouse position (or use random start near target)
    start_x = target_x + random.randint(-200, 200)
    start_y = target_y + random.randint(-100, 100)

    if steps is None:
        distance = ((target_x - start_x)**2 + (target_y - start_y)**2) ** 0.5
        steps = max(5, min(20, int(distance / 50)))

    # Bezier control point for curve
    ctrl_x = (start_x + target_x) / 2 + random.randint(-50, 50)
    ctrl_y = (start_y + target_y) / 2 + random.randint(-30, 30)

    for i in range(steps + 1):
        t = i / steps
        # Quadratic Bezier
        x = (1-t)**2 * start_x + 2*(1-t)*t * ctrl_x + t**2 * target_x
        y = (1-t)**2 * start_y + 2*(1-t)*t * ctrl_y + t**2 * target_y
        # Add micro-jitter
        x += random.uniform(-1, 1)
        y += random.uniform(-1, 1)
        _cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": int(x), "y": int(y)
        })
        time.sleep(random.uniform(0.005, 0.025))


def _human_pre_click(x, y):
    """Human-like approach before clicking: move mouse, brief hover."""
    try:
        _human_mouse_move(x, y)
        time.sleep(random.uniform(0.1, 0.3))  # Hover time before click
    except Exception:
        pass  # Fall back to direct click if movement fails


# ═══════════════════════════════════════════════════════
#  Page Classification — OODA Support
# ═══════════════════════════════════════════════════════

_last_page_classification = {}

_CLASSIFY_PAGE_JS = r"""(function() {
    var url = location.href;
    var title = document.title || '';
    var bodyText = (document.body ? document.body.innerText : '').substring(0, 5000);

    function isVis(el) {
        if (!el) return false;
        var s = window.getComputedStyle(el);
        if (s.display==='none' || s.visibility==='hidden' || s.opacity==='0') return false;
        var r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    var allInputs = Array.from(document.querySelectorAll('input:not([type=hidden])')).filter(isVis);
    var passwordFields = allInputs.filter(function(e) { return e.type === 'password'; });
    var emailFields = allInputs.filter(function(e) {
        var a = (e.type+' '+(e.name||'')+' '+(e.placeholder||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase();
        return /email|phone|username|login|user.?name/.test(a);
    });
    var codeFields = allInputs.filter(function(e) {
        var a = ((e.name||'')+' '+(e.placeholder||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.autocomplete||'')).toLowerCase();
        return /code|otp|pin|verification|one-time/.test(a) || (e.inputMode === 'numeric' && e.maxLength && e.maxLength <= 8);
    });
    var selects = Array.from(document.querySelectorAll('select')).filter(isVis);
    var dateSelects = selects.filter(function(s) {
        var l = ((s.getAttribute('aria-label')||'')+(s.title||'')).toLowerCase();
        return /month|day|year|birth|date/.test(l);
    });

    var type = 'content_page';
    var confidence = 50;

    if (codeFields.length > 0 || /enter.{0,20}(code|pin|otp)|confirmation code|verify your|we sent.{0,30}code|check your (email|phone)/i.test(bodyText.substring(0, 3000))) {
        type = 'verification_code'; confidence = 90;
    } else if (document.querySelector('iframe[src*=captcha], iframe[src*=recaptcha], iframe[src*=hcaptcha], [class*=captcha], #captcha') || /press and hold|i.m not a robot|verify you.re human|prove you.re human|security check/i.test(bodyText.substring(0,3000))) {
        type = 'captcha_challenge'; confidence = 85;
    } else if (dateSelects.length >= 2) {
        type = 'birthday_form'; confidence = 85;
    } else if (passwordFields.length > 0 && emailFields.length > 0 && allInputs.length <= 4) {
        type = 'login_form'; confidence = 80;
    } else if (passwordFields.length > 0 && allInputs.length > 3) {
        type = 'signup_form'; confidence = 75;
    } else if (/thank you|success|account.{0,20}created|welcome back|you.re all set|registration complete/i.test(bodyText.substring(0,2000)) && allInputs.length <= 1) {
        type = 'confirmation_page'; confidence = 70;
    } else if (/settings|preferences|account settings|edit profile/i.test(title) && allInputs.length > 2) {
        type = 'settings_page'; confidence = 65;
    } else if (/404|not found|page doesn.t exist|something went wrong|error occurred/i.test(title + ' ' + bodyText.substring(0,500))) {
        type = 'error_page'; confidence = 75;
    }

    var loggedInEls = document.querySelectorAll('[aria-label*="rofile" i], [href*="/logout" i], [href*="signout" i], [data-testid*="avatar"], [data-testid*="profile"]');
    var loggedIn = loggedInEls.length >= 1;
    var loggedInAs = '';
    if (loggedIn) {
        var pLink = document.querySelector('a[href*="/profile" i], a[href$="/me" i], [data-testid*="profile-link"]');
        if (pLink) loggedInAs = (pLink.getAttribute('href') || '').split('/').filter(Boolean).pop() || '';
        if (!loggedInAs) { var nav = document.querySelector('nav, header'); if (nav) { var m = (nav.innerText||'').match(/@(\w{2,30})/); if (m) loggedInAs = m[1]; } }
    }
    if (loggedIn && type === 'content_page') { type = 'logged_in_dashboard'; confidence = 70; }

    var overlays = [];
    var cookieEls = document.querySelectorAll('[class*=cookie i], [id*=cookie i], [class*=consent i], [id*=consent i], [aria-label*=cookie i]');
    for (var i = 0; i < cookieEls.length; i++) { if (isVis(cookieEls[i])) { overlays.push('cookie_consent'); break; } }
    if (/turn on notifications|enable notifications|allow notifications/i.test(bodyText.substring(0,3000))) overlays.push('notification_prompt');
    if (/download the app|get the app|open in app/i.test(bodyText.substring(0,2000))) overlays.push('app_banner');
    var modals = document.querySelectorAll('[role=dialog]:not([aria-hidden=true]), .modal.show, .modal.visible, .modal.open');
    for (var j = 0; j < modals.length; j++) { if (isVis(modals[j]) && overlays.indexOf('cookie_consent')===-1) { overlays.push('modal_dialog'); break; } }

    var hasCaptcha = type === 'captcha_challenge' || document.querySelector('iframe[src*=captcha], iframe[src*=recaptcha], iframe[src*=hcaptcha]') !== null;

    return JSON.stringify({
        type: type, confidence: confidence, url: url, title: title,
        logged_in: loggedIn, logged_in_as: loggedInAs, has_captcha: hasCaptcha,
        overlays: overlays, field_count: allInputs.length,
        password_fields: passwordFields.length,
        button_count: document.querySelectorAll('button:not([disabled]), input[type=submit]:not([disabled]), [role=button]:not([aria-disabled=true])').length,
        select_count: selects.length
    });
})()"""  # noqa: E501


def _classify_page_internal():
    """Classify the current page type and state (no lock — call from within locked functions).

    Returns dict with: type, confidence, url, title, logged_in, logged_in_as,
    has_captcha, overlays, field_count, password_fields, button_count, select_count.
    """
    raw = _js(_CLASSIFY_PAGE_JS)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {
            "type": "unknown", "confidence": 0, "url": "", "title": "",
            "logged_in": False, "logged_in_as": "", "has_captcha": False,
            "overlays": [], "field_count": 0, "password_fields": 0,
            "button_count": 0, "select_count": 0,
        }


def _format_page_assessment(cls):
    """Format classification dict into a human-readable assessment header."""
    if not cls or cls.get("type") == "unknown":
        return ""

    lines = ["═══ PAGE ASSESSMENT ═══"]

    # Page type
    page_type = cls.get("type", "unknown").upper().replace("_", " ")
    lines.append(f"Type: {page_type} (confidence: {cls.get('confidence', 0)}%)")

    # Domain
    url = cls.get("url", "")
    if url:
        try:
            from urllib.parse import urlparse as _up
            domain = _up(url).netloc
            if domain:
                lines.append(f"Site: {domain}")
        except Exception:
            pass

    # Login state
    if cls.get("logged_in"):
        user = cls.get("logged_in_as", "")
        lines.append(f"Logged In: YES" + (f" (as {user})" if user else ""))
    else:
        lines.append("Logged In: No")

    # CAPTCHA warning
    if cls.get("has_captcha"):
        lines.append("⚠️ CAPTCHA: Detected — call solve_captcha() or hold()")

    # Overlay warnings
    overlays = cls.get("overlays", [])
    if overlays:
        lines.append(f"⚠️ Overlays: {', '.join(overlays)} — dismiss before interacting")

    # Element summary
    fields = cls.get("field_count", 0)
    buttons = cls.get("button_count", 0)
    selects = cls.get("select_count", 0)
    lines.append(f"Elements: {fields} fields, {buttons} buttons, {selects} dropdowns")

    lines.append("═══════════════════════")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
#  Page Reading
# ═══════════════════════════════════════════════════════

def act_inspect_page():
    """Get a structured view of all visible interactive elements.

    Returns a PAGE ASSESSMENT header (type, login state, overlays, CAPTCHA)
    followed by all visible fields, buttons, dropdowns, links, errors,
    and checkboxes — everything the agent needs for OODA-based decisions.
    """
    global _last_page_classification
    _ensure()

    # ── Phase 1: Classify the page for quick orientation ──
    try:
        cls = _classify_page_internal()
        _last_page_classification = cls
    except Exception:
        cls = {}
        _last_page_classification = {}
    assessment_header = _format_page_assessment(cls)
    raw = _js("""
        (function() {
            function isVis(el) {
                if (!el) return false;
                var s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                var r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }

            function getLabel(el) {
                if (el.id) {
                    var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (l) return l.innerText.trim();
                }
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                if (el.getAttribute('title')) return el.getAttribute('title');
                if (el.placeholder) return el.placeholder;
                if (el.name) return el.name;
                // Check parent label
                var parent = el.closest('label');
                if (parent) return parent.innerText.trim().substring(0, 40);
                return '';
            }

            function getSel(el) {
                if (el.id) {
                    // Use attribute selector for IDs with special CSS chars (colons, dots, brackets)
                    // CSS.escape adds backslashes that LLMs strip, breaking querySelector
                    if (/[:.\\[\\]()#~>+,]/.test(el.id)) return '[id="' + el.id + '"]';
                    return '#' + el.id;
                }
                if (el.name) return '[name="' + el.name + '"]';
                if (el.getAttribute('aria-label')) return '[aria-label="' + el.getAttribute('aria-label') + '"]';
                if (el.placeholder) return '[placeholder="' + el.placeholder + '"]';
                if (el.type && el.type !== 'text') return el.tagName.toLowerCase() + '[type="' + el.type + '"]';
                // Fallback: nth-of-type
                var parent = el.parentElement;
                if (parent) {
                    var siblings = parent.querySelectorAll(el.tagName);
                    for (var i = 0; i < siblings.length; i++) {
                        if (siblings[i] === el) return el.tagName.toLowerCase() + ':nth-of-type(' + (i+1) + ')';
                    }
                }
                return el.tagName.toLowerCase();
            }

            var out = [];
            out.push('PAGE: ' + document.title);
            out.push('URL: ' + location.href);
            out.push('');

            // ── Input Fields ──
            var fields = [];
            document.querySelectorAll('input, textarea, [contenteditable="true"], [role="textbox"]').forEach(function(el) {
                if (!isVis(el)) return;
                var type = el.type || el.tagName.toLowerCase();
                if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'reset') return;
                if (type === 'checkbox' || type === 'radio') return; // handled separately
                var label = getLabel(el);
                var sel = getSel(el);
                var val = el.value || el.textContent || '';
                val = val.substring(0, 40);
                fields.push({label: label, sel: sel, type: type, val: val});
            });
            if (fields.length) {
                out.push('FIELDS:');
                fields.forEach(function(f) {
                    var valStr = f.val ? ' = "' + f.val + '"' : '';
                    out.push('  ' + (f.label || f.sel) + ' → ' + f.sel + ' (' + f.type + ')' + valStr);
                });
                out.push('');
            }

            // ── Inline Field Errors (near inputs) ──
            var fieldErrors = [];
            var positiveWords = ['is valid', 'is available', 'looks good', 'accepted', 'confirmed', 'strong password'];
            document.querySelectorAll('[role=alert], [aria-live=assertive], [aria-live=polite], .error, .field-error, .form-error, .validation-error, .invalid-feedback, span[class*=coreSpriteInputError], [data-testid*=error], [id*=error-message]').forEach(function(el) {
                if (!isVis(el)) return;
                var t = el.innerText.trim();
                if (t && t.length > 2 && t.length < 200 && fieldErrors.indexOf(t) === -1) {
                    // Filter out positive validation messages (not actual errors)
                    var lower = t.toLowerCase();
                    var isPositive = positiveWords.some(function(pw) { return lower.indexOf(pw) !== -1; });
                    if (!isPositive) fieldErrors.push(t);
                }
            });
            if (fieldErrors.length) {
                out.push('🚨 FORM ERRORS:');
                fieldErrors.forEach(function(e) { out.push('  ❌ ' + e); });
                out.push('');
            }

            // ── Dropdowns ──
            var drops = [];
            document.querySelectorAll('select').forEach(function(el) {
                if (!isVis(el) && !(el.parentElement && isVis(el.parentElement))) return;
                var label = getLabel(el);
                var sel = getSel(el);
                var cur = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.trim() : '';
                var opts = Array.from(el.options).map(function(o) { return o.text.trim(); })
                    .filter(function(t) { return t && t !== ''; }).slice(0, 15);
                drops.push({label: label || sel, sel: sel, cur: cur, opts: opts});
            });
            if (drops.length) {
                out.push('DROPDOWNS:');
                drops.forEach(function(d) {
                    out.push('  ' + d.label + ' → ' + d.sel + ' (current: ' + d.cur + ') options: ' + d.opts.join(', '));
                });
                out.push('');
            }

            // ── Custom Dropdowns (role=listbox, role=combobox) ──
            var customs = [];
            document.querySelectorAll('[role=listbox], [role=combobox]').forEach(function(el) {
                if (!isVis(el)) return;
                var label = el.getAttribute('aria-label') || '';
                if (!label) {
                    var lbl = el.getAttribute('aria-labelledby');
                    if (lbl) {
                        lbl.split(' ').forEach(function(id) {
                            var e = document.getElementById(id);
                            if (e) label += e.innerText.trim() + ' ';
                        });
                    }
                }
                if (!label) label = el.id || 'custom-dropdown';
                customs.push({label: label.trim(), text: el.innerText.trim().substring(0, 40)});
            });
            if (customs.length) {
                out.push('CUSTOM DROPDOWNS:');
                customs.forEach(function(c) {
                    out.push('  ' + c.label + ' (showing: ' + c.text + ')');
                });
                out.push('');
            }

            // ── Checkboxes & Radio Buttons ──
            var checks = [];
            document.querySelectorAll('input[type=checkbox], input[type=radio], [role=checkbox], [role=radio], [role=switch]').forEach(function(el) {
                if (!isVis(el)) return;
                var label = getLabel(el);
                if (!label) {
                    var lbl = el.closest('label');
                    label = lbl ? lbl.innerText.trim().substring(0, 60) : (el.name || el.id || '?');
                }
                var sel = getSel(el);
                var checked = el.checked || el.getAttribute('aria-checked') === 'true';
                var type = el.type || el.getAttribute('role') || 'checkbox';
                var icon = type === 'radio' ? (checked ? '●' : '○') : (checked ? '☑' : '☐');
                checks.push({icon: icon, label: label, sel: sel});
            });
            if (checks.length) {
                out.push('CHECKBOXES:');
                checks.forEach(function(c) {
                    out.push('  ' + c.icon + ' ' + c.label + ' → ' + c.sel);
                });
                out.push('');
            }

            // ── Buttons (with selectors for unambiguous clicking) ──
            var btns = [];
            document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]').forEach(function(el) {
                if (!isVis(el)) return;
                var text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                if (text && text.length < 80) {
                    var sel = getSel(el);
                    btns.push({text: text, sel: sel});
                }
            });
            if (btns.length) {
                out.push('BUTTONS:');
                btns.forEach(function(b) {
                    out.push('  [' + b.text + '] → ' + b.sel);
                });
                out.push('');
            }

            // ── Links (first 30 visible) ──
            var links = [];
            document.querySelectorAll('a[href]').forEach(function(a) {
                if (links.length >= 30 || !isVis(a)) return;
                var text = a.innerText.trim();
                if (text && text.length > 0 && text.length < 80) {
                    links.push(text.substring(0, 60));
                }
            });
            if (links.length) {
                out.push('LINKS:');
                links.forEach(function(l) { out.push('  [' + l + ']'); });
                out.push('');
            }

            // ── Error/Alert Messages ──
            var errors = [];
            var positiveWords2 = ['is valid', 'is available', 'looks good', 'accepted', 'confirmed', 'strong password'];
            document.querySelectorAll('[role=alert], .error, .alert, .warning, [aria-live=assertive], [aria-live=polite], .field-error, .form-error, .validation-error, .invalid-feedback, .help-block, [id*=error], [class*=error], [class*=Error]').forEach(function(el) {
                if (!isVis(el)) return;
                var text = el.innerText.trim();
                if (text && text.length > 2 && text.length < 200 && errors.indexOf(text) === -1) {
                    var lower = text.toLowerCase();
                    var isPositive = positiveWords2.some(function(pw) { return lower.indexOf(pw) !== -1; });
                    if (!isPositive) errors.push(text);
                }
            });
            if (errors.length) {
                out.push('⚠️ ERRORS/ALERTS ON PAGE:');
                errors.forEach(function(e) { out.push('  ' + e); });
                out.push('');
            }

            // ── iframes (note them) ──
            var iframes = document.querySelectorAll('iframe');
            var visIframes = [];
            iframes.forEach(function(f) { if (isVis(f)) visIframes.push(f); });
            if (visIframes.length) {
                out.push('IFRAMES: ' + visIframes.length + ' embedded frame(s)');
                visIframes.forEach(function(f) {
                    var src = f.src || '(no src)';
                    out.push('  ' + src.substring(0, 80));
                });
                out.push('');
            }

            return out.join('\\n');
        })()
    """)
    detail = raw or "Could not inspect page — try act_goto first"

    # ── Phase 3: Page diff — what changed since last look? ──
    global _last_page_state
    diff_section = ""
    try:
        new_state = _capture_page_state()
        if _last_page_state:
            diff_text = _compute_page_diff(_last_page_state, new_state)
            if diff_text and "No visible changes" not in diff_text:
                diff_section = f"\n═══ CHANGES SINCE LAST LOOK ═══\n{diff_text}\n═══════════════════════════════\n\n"
        _last_page_state = new_state
    except Exception:
        pass

    # ── Phase 4: Form intelligence — fill progress ──
    form_section = ""
    try:
        form_data = _analyze_forms()
        form_text = _format_form_intelligence(form_data)
        if form_text:
            form_section = f"\n═══ FORM PROGRESS ═══\n{form_text}\n═════════════════════\n\n"
    except Exception:
        pass

    return assessment_header + diff_section + form_section + detail


def act_read_page():
    """Read all visible text on the page."""
    _ensure()
    text = _js("document.body ? document.body.innerText.substring(0, 12000) : ''")
    return text or "(empty page)"


def act_read_url():
    """Get current URL and title."""
    _ensure()
    url = _js("location.href") or ""
    title = _js("document.title") or ""
    return f"URL: {url}\nTitle: {title}"


# ═══════════════════════════════════════════════════════
#  Click — by text or CSS selector, via real CDP mouse
# ═══════════════════════════════════════════════════════

def act_click(target):
    """Click an element by visible text OR CSS selector.

    Uses CDP Input.dispatchMouseEvent — a REAL browser click at viewport
    coordinates. No screen coordinates, no cliclick, no monitor issues.
    Automatically scrolls element into view first.
    After clicking, reports any state changes (URL change, errors, new content).
    """
    _ensure()
    
    # Strip surrounding brackets if LLM passed "[Next]" instead of "Next"
    clean_target = target.strip()
    if clean_target.startswith("[") and clean_target.endswith("]") and not "=" in clean_target:
        clean_target = clean_target[1:-1]
    
    coords = _find_element_coords(clean_target)
    if not coords:
        # Fallback: try original target if cleaning changed it
        if clean_target != target.strip():
            coords = _find_element_coords(target.strip())
        if not coords:
            return f"ERROR: No visible element with text: {target}"

    # Capture state before click
    url_before = _js("location.href") or ""

    x, y = coords

    # Human-like mouse approach (anti-detection)
    _human_pre_click(x, y)

    _cdp_click_at(x, y)
    time.sleep(0.5)

    # Check what changed after click
    url_after = _js("location.href") or ""
    
    # Detect inline errors/validation messages that appeared
    errors = _js("""
        (function() {
            var msgs = [];
            var positiveWords = ['is valid', 'is available', 'looks good', 'accepted', 'confirmed', 'strong password'];
            document.querySelectorAll('[role=alert], [aria-live=assertive], [aria-live=polite], .error, .alert, .field-error, .form-error, .validation-error, .invalid-feedback, [id*=error], [class*=error], [class*=Error], [class*=sAlert], [data-testid*=error], span[class*=coreSpriteInputError]').forEach(function(el) {
                var s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return;
                var r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                var t = el.innerText.trim();
                if (t && t.length > 2 && t.length < 200 && msgs.indexOf(t) === -1) {
                    var lower = t.toLowerCase();
                    var isPositive = positiveWords.some(function(pw) { return lower.indexOf(pw) !== -1; });
                    if (!isPositive) msgs.push(t);
                }
            });
            return msgs.join(' | ');
        })()
    """)

    result = f"Clicked '{target}' at ({x}, {y})"
    
    # Auto-wait for submit/navigation buttons — SPA transitions take 1-3s
    # This saves the agent from wasting a step calling wait() separately
    submit_keywords = ["sign up", "submit", "next", "continue", "create", "register",
                        "log in", "login", "sign in", "confirm", "verify", "send", "save"]
    if any(kw in clean_target.lower() for kw in submit_keywords):
        time.sleep(1.5)  # Extra wait for form submissions
        # Re-check URL and errors after the extra wait
        url_after = _js("location.href") or ""
        errors = _js("""
            (function() {
                var msgs = [];
                var positiveWords = ['is valid', 'is available', 'looks good', 'accepted', 'confirmed', 'strong password'];
                document.querySelectorAll('[role=alert], [aria-live=assertive], .error, .field-error, .form-error, .validation-error, .invalid-feedback, [data-testid*=error], span[class*=coreSpriteInputError]').forEach(function(el) {
                    var s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden') return;
                    var r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return;
                    var t = el.innerText.trim();
                    if (t && t.length > 2 && t.length < 200 && msgs.indexOf(t) === -1) {
                        var lower = t.toLowerCase();
                        var isPositive = positiveWords.some(function(pw) { return lower.indexOf(pw) !== -1; });
                        if (!isPositive) msgs.push(t);
                    }
                });
                return msgs.join(' | ');
            })()
        """) or ""
    
    if url_before != url_after:
        result += f" → navigated to {url_after}"
    if errors:
        result += f" ⚠️ Page errors: {errors[:300]}"
    
    return result


# ═══════════════════════════════════════════════════════
#  Type — click field + clear + type via CDP input
# ═══════════════════════════════════════════════════════

def act_fill(selector, value):
    """Click on a field, clear it, and type a value character-by-character.

    Uses CDP mouse click to focus, then human-like keypress events to type.
    Verifies the value was accepted after typing.
    Works with React, Vue, Angular, vanilla HTML — everything.
    """
    _ensure()

    # Normalize selector — fix IDs with special CSS chars that LLMs break
    selector = _fix_selector(selector)

    # Find the element
    safe_sel = selector.replace("\\", "\\\\").replace("'", "\\'")
    raw = _js(f"""
        (function() {{
            var el = document.querySelector('{safe_sel}');
            if (!el) return '';
            el.scrollIntoView({{block: 'center', behavior: 'instant'}});
            var r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) return '';
            return JSON.stringify({{
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2)
            }});
        }})()
    """)

    if not raw or raw.startswith("JS_ERROR"):
        return f"ERROR: No visible field for: {selector}"

    try:
        pos = json.loads(raw)
    except Exception:
        return f"ERROR: Bad position data for: {selector}"

    # Click to focus
    _cdp_click_at(pos["x"], pos["y"])
    time.sleep(0.2)

    # Clear field: select all with Ctrl+A then delete
    _js(f"""
        (function() {{
            var el = document.querySelector('{safe_sel}');
            if (el) {{
                el.focus();
                if (el.select) el.select();
                else if (el.setSelectionRange) el.setSelectionRange(0, el.value.length);
            }}
        }})()
    """)
    time.sleep(0.05)
    
    # Select all via keyboard (Cmd+A on Mac) + delete
    _cdp_key("a", "KeyA", 65, modifiers=4)  # 4 = Meta (Cmd on Mac)
    time.sleep(0.05)
    _cdp_key("Backspace", "Backspace", 8)
    time.sleep(0.1)
    
    # Double-check: if field still has value, force-clear via React-safe setter
    remaining = _js(f"document.querySelector('{safe_sel}') ? document.querySelector('{safe_sel}').value : ''")
    if remaining and remaining.strip():
        _js(f"""
            (function() {{
                var el = document.querySelector('{safe_sel}');
                if (el) {{
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                    if (nativeInputValueSetter && nativeInputValueSetter.set) {{
                        nativeInputValueSetter.set.call(el, '');
                    }} else {{
                        el.value = '';
                    }}
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    el.focus();
                }}
            }})()
        """)
        time.sleep(0.1)

    # Type character-by-character with human-like delays
    # This triggers proper keyDown/keyUp events that React tracks
    _cdp_type_human(value)
    time.sleep(0.15)

    # Fire input/change events as backup for frameworks
    _js(f"""
        (function() {{
            var el = document.querySelector('{safe_sel}');
            if (el) {{
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.dispatchEvent(new Event('blur', {{bubbles: true}}));
            }}
        }})()
    """)
    time.sleep(0.1)

    # Verify the value was accepted
    actual = _js(f"document.querySelector('{safe_sel}') ? document.querySelector('{safe_sel}').value : ''")
    if actual and value in actual:
        return f"Typed '{value}' into {selector} ✓"
    elif actual:
        return f"Typed into {selector} (field shows: '{actual[:40]}') — may need verification"
    else:
        return f"Typed '{value}' into {selector}"


# ═══════════════════════════════════════════════════════
#  Fill Form — batch fill multiple fields in one call
# ═══════════════════════════════════════════════════════

def act_fill_form(fields):
    """Fill multiple form fields at once — like a human filling out a form.

    Takes a list of {selector, value} pairs and fills them all in sequence.
    Much more efficient than calling type() one field at a time.
    Also handles dropdowns when type='select' is specified.

    Args:
        fields: List of dicts with keys:
            - selector (str): CSS selector of the field
            - value (str): Value to type or select
            - type (str, optional): 'text' (default) or 'select' (for dropdowns)

    Returns:
        Summary of all fill results.
    """
    if not fields or not isinstance(fields, list):
        return "ERROR: fill_form requires a list of {selector, value} field dicts"

    results = []
    filled = 0
    failed = 0

    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            results.append(f"  ❌ Field {i+1}: invalid format (expected {{selector, value}})")
            failed += 1
            continue

        selector = field.get("selector", "")
        value = field.get("value", "")
        field_type = field.get("type", "text")

        if not selector or not value:
            results.append(f"  ❌ Field {i+1}: missing selector or value")
            failed += 1
            continue

        try:
            if field_type == "select":
                result = act_select_option(selector, value)
            else:
                result = act_fill(selector, value)

            if "ERROR" in str(result):
                results.append(f"  ❌ {selector}: {result}")
                failed += 1
            else:
                results.append(f"  ✅ {selector} = '{value}'")
                filled += 1
        except Exception as e:
            results.append(f"  ❌ {selector}: {e}")
            failed += 1

        # Brief pause between fields (human-like)
        time.sleep(0.3)

    summary = f"Form fill: {filled}/{len(fields)} fields filled"
    if failed:
        summary += f" ({failed} failed)"
    summary += "\n" + "\n".join(results)
    return summary


# ═══════════════════════════════════════════════════════
#  Select — handle both native <select> and custom dropdowns
# ═══════════════════════════════════════════════════════

def act_select_option(dropdown_text_or_selector, option_text):
    """Select an option from ANY dropdown — native <select> or custom.

    For native <select>: sets value via JS + dispatches change event.
    For custom dropdowns: clicks to open, finds option, clicks it.
    """
    _ensure()

    # Normalize selector — fix IDs with special CSS chars that LLMs break
    if dropdown_text_or_selector.startswith(("#", ".", "[")):
        dropdown_text_or_selector = _fix_selector(dropdown_text_or_selector)

    safe_dd = dropdown_text_or_selector.replace("\\", "\\\\").replace("'", "\\'")
    safe_opt = option_text.replace("\\", "\\\\").replace("'", "\\'")

    # Try native <select> first
    is_css = len(dropdown_text_or_selector) > 0 and dropdown_text_or_selector[0] in ("#", ".", "[")
    native_result = _js(f"""
        (function() {{
            var sel = null;
            if ({'true' if is_css else 'false'}) {{
                sel = document.querySelector('{safe_dd}');
            }} else {{
                // Find select by label text
                var labels = document.querySelectorAll('label');
                for (var i = 0; i < labels.length; i++) {{
                    if (labels[i].innerText.trim().toLowerCase().indexOf('{safe_dd}'.toLowerCase()) !== -1) {{
                        var forId = labels[i].getAttribute('for');
                        if (forId) sel = document.getElementById(forId);
                        if (!sel) sel = labels[i].querySelector('select');
                        if (sel) break;
                    }}
                }}
                // Try finding select by aria-label or title attribute
                if (!sel) {{
                    document.querySelectorAll('select').forEach(function(s) {{
                        var ariaLabel = (s.getAttribute('aria-label') || '').toLowerCase();
                        var title = (s.getAttribute('title') || '').toLowerCase();
                        var searchTerm = '{safe_dd}'.toLowerCase();
                        if (ariaLabel === searchTerm || ariaLabel.indexOf(searchTerm) !== -1) sel = s;
                        if (!sel && (title === searchTerm || title.indexOf(searchTerm) !== -1)) sel = s;
                    }});
                }}
                // Also try finding select by name/id containing the text
                if (!sel) {{
                    document.querySelectorAll('select').forEach(function(s) {{
                        if (s.name && s.name.toLowerCase().indexOf('{safe_dd}'.toLowerCase()) !== -1) sel = s;
                        if (s.id && s.id.toLowerCase().indexOf('{safe_dd}'.toLowerCase()) !== -1) sel = s;
                    }});
                }}
                // Last resort: try placeholder text in first option
                if (!sel) {{
                    document.querySelectorAll('select').forEach(function(s) {{
                        if (s.options && s.options[0]) {{
                            var firstOpt = s.options[0].text.trim().toLowerCase();
                            if (firstOpt === '{safe_dd}'.toLowerCase() || firstOpt.indexOf('{safe_dd}'.toLowerCase()) !== -1) sel = s;
                        }}
                    }});
                }}
            }}
            if (!sel || sel.tagName !== 'SELECT') return '';

            // Found native select — pick the option
            for (var i = 0; i < sel.options.length; i++) {{
                if (sel.options[i].text.trim() === '{safe_opt}' ||
                    sel.options[i].text.trim().toLowerCase() === '{safe_opt}'.toLowerCase() ||
                    sel.options[i].value === '{safe_opt}') {{
                    sel.selectedIndex = i;
                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                    sel.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return 'native:' + sel.options[i].text.trim();
                }}
            }}
            // List available options for debugging
            var opts = Array.from(sel.options).map(function(o) {{ return o.text.trim(); }}).join(', ');
            return 'options:' + opts;
        }})()
    """)

    if native_result.startswith("native:"):
        return f"Selected '{native_result[7:]}' from dropdown"

    if native_result.startswith("options:"):
        return f"ERROR: Option '{option_text}' not found. Available: {native_result[8:]}"

    # Not a native select — try clicking to open custom dropdown, then click option
    coords = _find_element_coords(dropdown_text_or_selector)
    if not coords:
        return f"ERROR: Dropdown not found: {dropdown_text_or_selector}"

    _cdp_click_at(coords[0], coords[1])
    time.sleep(0.8)  # Wait for dropdown to open

    # Now find and click the option
    opt_coords = _find_element_coords(option_text)
    if not opt_coords:
        return f"ERROR: Option '{option_text}' not found after opening dropdown"

    _cdp_click_at(opt_coords[0], opt_coords[1])
    time.sleep(0.3)

    return f"Selected '{option_text}'"


# Alias for backward compatibility
act_select_custom = act_select_option


# ═══════════════════════════════════════════════════════
#  Keyboard
# ═══════════════════════════════════════════════════════

def act_press_key(key_name):
    """Press a keyboard key: enter, tab, escape, up, down, etc."""
    _ensure()
    key_lower = key_name.lower().strip()

    if key_lower in KEY_MAP:
        key, code, vk = KEY_MAP[key_lower]
        _cdp_key(key, code, vk)
        return f"Pressed {key_name}"

    # Single character key
    if len(key_name) == 1:
        char = key_name
        code = f"Key{char.upper()}" if char.isalpha() else ""
        vk = ord(char.upper()) if char.isalpha() else ord(char)
        _cdp_key(char, code, vk)
        return f"Pressed '{key_name}'"

    return f"ERROR: Unknown key: {key_name}"


# ═══════════════════════════════════════════════════════
#  Scrolling
# ═══════════════════════════════════════════════════════

def act_scroll(direction="down"):
    """Scroll the page: up, down, top, bottom."""
    _ensure()
    if direction == "down":
        _js("window.scrollBy(0, window.innerHeight * 0.8)")
    elif direction == "up":
        _js("window.scrollBy(0, -window.innerHeight * 0.8)")
    elif direction == "top":
        _js("window.scrollTo(0, 0)")
    elif direction == "bottom":
        _js("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(0.3)
    return f"Scrolled {direction}"


# ═══════════════════════════════════════════════════════
#  Waiting
# ═══════════════════════════════════════════════════════

def act_wait(seconds=2):
    """Wait for N seconds."""
    time.sleep(int(seconds))
    return f"Waited {seconds}s"


def act_wait_for_text(text, timeout=10):
    """Wait for specific text to appear on the page."""
    _ensure()
    safe = text.replace("\\", "\\\\").replace("'", "\\'")
    for _ in range(int(timeout) * 4):
        found = _js(f"document.body && document.body.innerText.indexOf('{safe}') !== -1 ? 'yes' : 'no'")
        if found == "yes":
            return f"Text '{text}' found on page"
        time.sleep(0.25)
    return f"Text '{text}' NOT found after {timeout}s"


# ═══════════════════════════════════════════════════════
#  Tab Management
# ═══════════════════════════════════════════════════════

def act_get_tabs():
    """List all open browser tabs."""
    _ensure()
    tabs = _cdp.get_tabs()
    if not tabs:
        return "No tabs"
    lines = []
    for i, t in enumerate(tabs, 1):
        lines.append(f"{i}. {t['title'][:60]} ({t['url'][:60]})")
    return "\n".join(lines)


def act_switch_tab(tab_number):
    """Switch to a tab by its number (1-indexed)."""
    _ensure()
    tabs = _cdp.get_tabs()
    idx = int(tab_number) - 1
    if idx < 0 or idx >= len(tabs):
        return f"ERROR: Tab {tab_number} does not exist (have {len(tabs)} tabs)"

    tab = tabs[idx]
    _cdp.switch_to_tab(tab["id"])
    time.sleep(0.5)
    return f"Switched to tab {tab_number}: {tab['title'][:60]}"


def act_close_tab():
    """Close the current tab and switch to the next one."""
    _ensure()
    tabs = _cdp.get_tabs()
    if not tabs:
        return "No tabs to close"

    # Find current tab (first one since we're connected to it)
    current_id = tabs[0]["id"] if tabs else None
    if current_id:
        _cdp.close_tab(current_id)
        time.sleep(0.5)
        # Reconnect to remaining tab
        remaining = _cdp.get_tabs()
        if remaining:
            _cdp.switch_to_tab(remaining[0]["id"])
            return f"Closed tab. Now on: {remaining[0]['title'][:60]}"

    return "Tab closed"


def act_new_tab(url=""):
    """Open a new tab, optionally with a URL."""
    _ensure()
    if url:
        _cdp.new_tab(url)
        time.sleep(1.5)
        _wait_for_load(10)
        title = _js("document.title") or ""
        return f"New tab: {url} — {title}"
    else:
        _cdp.new_tab("about:blank")
        time.sleep(0.5)
        return "New empty tab opened"


# ═══════════════════════════════════════════════════════
#  Screenshot
# ═══════════════════════════════════════════════════════

def act_screenshot():
    """Capture a screenshot of the page via CDP.
    
    Returns the base64 image data so vision-capable LLMs can actually
    SEE the page. Also saves to disk as backup.
    Returns a dict with 'image_base64' key when vision is available,
    plus a text description for non-vision models.
    """
    _ensure()
    try:
        result = _cdp.send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 70,
        })
        data = result.get("data", "")
        if data:
            path = os.path.join(
                tempfile.gettempdir(),
                f"tars_screenshot_{int(time.time())}.jpg"
            )
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            
            # Return structured data: base64 for vision models + text fallback
            # The agent dispatch layer will pass the image to the LLM if supported
            url = _js("location.href") or "unknown"
            title = _js("document.title") or "unknown"
            return {
                "_screenshot": True,
                "image_base64": data,
                "image_path": path,
                "text": f"Screenshot captured of '{title}' ({url}). Saved to {path}",
            }
        return "ERROR: Empty screenshot data"
    except Exception as e:
        return f"ERROR: Screenshot failed: {e}"


# ═══════════════════════════════════════════════════════
#  JavaScript (read-only for agent)
# ═══════════════════════════════════════════════════════

def act_run_js(code):
    """Run custom JavaScript. READ-ONLY — for getting page info."""
    _ensure()
    return _js(code)


# ═══════════════════════════════════════════════════════
#  File Upload via CDP
# ═══════════════════════════════════════════════════════

@_with_browser_lock
def act_upload_file(selector, file_path):
    """Upload a file to an <input type='file'> element.

    Uses CDP DOM.setFileInputFiles — the standard way to programmatically
    set files on file input elements. Works for profile photos, documents,
    resumes, attachments, etc.

    Args:
        selector: CSS selector for the file input (e.g., 'input[type=file]', '#avatar-upload')
        file_path: Absolute path to the file on disk
    """
    _ensure()
    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        return f"ERROR: File not found: {file_path}"

    try:
        # Enable DOM domain
        _cdp.send("DOM.enable", {})

        # Get the document root
        doc = _cdp.send("DOM.getDocument", {"depth": 0})
        root_id = doc["root"]["nodeId"]

        # Find the file input element
        result = _cdp.send("DOM.querySelector", {
            "nodeId": root_id,
            "selector": selector,
        })
        node_id = result.get("nodeId", 0)

        if not node_id:
            # Try common file input selectors as fallback
            for fallback in ["input[type='file']", "input[type=file]", "[accept]"]:
                result = _cdp.send("DOM.querySelector", {
                    "nodeId": root_id,
                    "selector": fallback,
                })
                node_id = result.get("nodeId", 0)
                if node_id:
                    break

        if not node_id:
            return f"ERROR: No file input found with selector '{selector}'. Look at the page for the correct file upload element."

        # Set the file on the input
        _cdp.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [file_path],
        })

        filename = os.path.basename(file_path)
        time.sleep(1)

        # Check if an upload preview appeared
        preview = _js("""
            (() => {
                const imgs = document.querySelectorAll('img[src*="blob:"], img[src*="data:"], .preview, .upload-preview, [class*="avatar"], [class*="thumbnail"]');
                return imgs.length > 0 ? 'preview visible' : 'no preview detected';
            })()
        """)

        return f"✅ Uploaded '{filename}' to {selector}. {preview}. If the form needs you to confirm/save, click the submit button."

    except Exception as e:
        return f"ERROR uploading file: {e}"


# ═══════════════════════════════════════════════════════
#  OAuth Popup Handling
# ═══════════════════════════════════════════════════════

@_with_browser_lock
def act_handle_oauth_popup(provider=""):
    """Detect and switch to an OAuth popup window (Google, GitHub, etc.).

    When a site opens "Sign in with Google/GitHub/etc.", it opens a popup.
    This function finds that popup, switches to it so the agent can interact,
    and returns info about the popup page.

    After authenticating in the popup, call this again with provider='return'
    to switch back to the original window.
    """
    _ensure()
    try:
        tabs = _cdp.get_tabs()
        if not tabs:
            return "ERROR: No tabs found"

        if provider.lower() == "return":
            # Switch back to the first (main) tab
            if len(tabs) >= 1:
                _cdp.switch_to_tab(tabs[0]["id"])
                time.sleep(1)
                title = _js("document.title") or ""
                return f"✅ Switched back to main window: {title}"
            return "ERROR: No main window to return to"

        # Find OAuth popup — look for known OAuth URLs
        oauth_patterns = [
            "accounts.google.com", "github.com/login/oauth",
            "appleid.apple.com", "facebook.com/login",
            "login.microsoftonline.com", "twitter.com/i/oauth",
            "id.twitch.tv", "discord.com/oauth",
        ]

        current_tab = tabs[0]["id"] if tabs else None
        popup_tab = None

        for tab in tabs[1:]:  # Skip the first (main) tab
            url = tab.get("url", "").lower()
            title = tab.get("title", "").lower()
            # Match by known OAuth patterns or by provider name
            if any(p in url for p in oauth_patterns):
                popup_tab = tab
                break
            if provider and provider.lower() in url:
                popup_tab = tab
                break
            # Generic: any non-main tab opened recently is likely the popup
            if not popup_tab and tab["id"] != current_tab:
                popup_tab = tab

        if popup_tab:
            _cdp.switch_to_tab(popup_tab["id"])
            time.sleep(1)
            title = _js("document.title") or ""
            url = _js("location.href") or ""
            return f"✅ Switched to OAuth popup: {title} ({url}). Now use look() to see the login form and authenticate."
        else:
            return "No OAuth popup detected. The popup may not have opened yet — try clicking the OAuth button first, then wait 2 seconds before calling this again."

    except Exception as e:
        return f"ERROR handling OAuth popup: {e}"


# ═══════════════════════════════════════════════════════
#  Google Search Helper
# ═══════════════════════════════════════════════════════

def act_google(query):
    """Quick Google search: navigate and return results."""
    encoded = urllib.parse.quote_plus(query)
    act_goto(f"https://www.google.com/search?q={encoded}")
    time.sleep(1)
    text = act_read_page()
    return f"Google results for '{query}':\n\n{text[:6000]}"


# ═══════════════════════════════════════════════════════
#  Dialog Handling
# ═══════════════════════════════════════════════════════

def act_handle_dialog(action="accept"):
    """Handle a browser alert/confirm/prompt dialog."""
    _ensure()
    accept = action.lower() != "dismiss"
    try:
        _cdp.send("Page.handleJavaScriptDialog", {"accept": accept})
        return f"Dialog {'accepted' if accept else 'dismissed'}"
    except Exception:
        return "No dialog to handle"


# ═══════════════════════════════════════════════════════
#  Press and Hold — for CAPTCHA buttons
# ═══════════════════════════════════════════════════════

def act_press_and_hold(target, duration=10):
    """Press and hold an element (or coordinates) for N seconds.

    For CAPTCHA 'press and hold' buttons. Dispatches real CDP mouse
    events with human-like micro-jitter during the hold.

    target: CSS selector, text, or 'iframe:hsprotect' for auto-detect.
    duration: seconds to hold (default 10).
    """
    _ensure()
    duration = int(duration)
    if duration < 1:
        duration = 1
    if duration > 30:
        duration = 30

    x, y = None, None

    # Auto-detect CAPTCHA iframe position
    if target.lower() in ('captcha', 'iframe:hsprotect', 'hold_button', 'press_and_hold'):
        iframe_pos = _js("""
            (function() {
                var iframe = document.querySelector('iframe[src*="hsprotect"]');
                if (!iframe) {
                    // Fallback: any iframe near "press and hold" text
                    var iframes = document.querySelectorAll('iframe');
                    for (var i = 0; i < iframes.length; i++) {
                        var r = iframes[i].getBoundingClientRect();
                        if (r.width > 100 && r.height > 30 && r.width < 500 && r.height < 200) {
                            iframe = iframes[i];
                            break;
                        }
                    }
                }
                if (!iframe) return '';
                var r = iframe.getBoundingClientRect();
                return JSON.stringify({
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2)
                });
            })()
        """)
        if iframe_pos and not iframe_pos.startswith("JS_ERROR"):
            try:
                pos = json.loads(iframe_pos)
                x, y = pos["x"], pos["y"]
            except Exception:
                pass
    else:
        # Try as selector/text
        coords = _find_element_coords(target)
        if coords:
            x, y = coords

    if x is None or y is None:
        return "ERROR: Could not find element to press and hold"

    # Move mouse to position first (like a human approaching)
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": x, "y": y
    })
    time.sleep(0.3)

    # Mouse down
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })

    # Hold with human-like micro-jitter
    steps = duration * 4  # 4 movements per second
    for i in range(steps):
        time.sleep(0.25)
        jx = x + (i % 3) - 1   # -1, 0, +1 pixel jitter
        jy = y + ((i + 1) % 3) - 1
        _cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": jx, "y": jy,
            "button": "left",
        })

    # Release
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })

    time.sleep(2)
    title = _js("document.title") or ""
    return f"Held at ({x}, {y}) for {duration}s — page: {title}"


def act_full_page_scan():
    """Auto-scroll the entire page and collect ALL interactive elements.

    Unlike look() which only sees the current viewport, this function:
    1. Scrolls to top
    2. Captures elements at each viewport position
    3. Scrolls down and repeats until bottom
    4. Deduplicates and returns a comprehensive element map

    Use this for long pages where important buttons/forms may be below the fold.
    Returns the page assessment + all elements found across the full page.
    """
    _ensure()

    # Get page dimensions
    dims = _js("""
        JSON.stringify({
            scrollHeight: document.documentElement.scrollHeight,
            clientHeight: document.documentElement.clientHeight,
            scrollTop: window.scrollY
        })
    """)
    try:
        dims = json.loads(dims)
    except Exception:
        # Fallback: just do a regular look()
        return act_inspect_page()

    scroll_height = dims.get("scrollHeight", 0)
    client_height = dims.get("clientHeight", 0)

    # If page fits in viewport, just do normal inspect
    if scroll_height <= client_height + 100:
        return act_inspect_page()

    # Scroll to top first
    _js("window.scrollTo(0, 0)")
    time.sleep(0.3)

    all_fields = []
    all_buttons = []
    all_links = []
    all_errors = []
    seen_selectors = set()
    page_sections = []

    # Scan the page in viewport-sized chunks
    max_scrolls = min(int(scroll_height / max(client_height * 0.7, 1)) + 1, 15)

    for i in range(max_scrolls):
        # Extract elements at current scroll position
        chunk = _js("""
            (function() {
                function isVis(el) {
                    if (!el) return false;
                    var s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                    var r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && r.top < window.innerHeight && r.bottom > 0;
                }
                function getLabel(el) {
                    if (el.id) { var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return l.innerText.trim(); }
                    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
                    if (el.getAttribute('title')) return el.getAttribute('title');
                    if (el.placeholder) return el.placeholder;
                    if (el.name) return el.name;
                    var parent = el.closest('label');
                    if (parent) return parent.innerText.trim().substring(0, 40);
                    return '';
                }
                function getSel(el) {
                    if (el.id) {
                        if (/[:.\\[\\]()#~>+,]/.test(el.id)) return '[id="' + el.id + '"]';
                        return '#' + el.id;
                    }
                    if (el.name) return '[name="' + el.name + '"]';
                    if (el.getAttribute('aria-label')) return '[aria-label="' + el.getAttribute('aria-label') + '"]';
                    if (el.placeholder) return '[placeholder="' + el.placeholder + '"]';
                    return el.tagName.toLowerCase();
                }
                var fields = [], buttons = [], links = [], errors = [];
                document.querySelectorAll('input, textarea, [contenteditable="true"]').forEach(function(el) {
                    if (!isVis(el)) return;
                    var type = el.type || 'text';
                    if (type === 'hidden' || type === 'submit' || type === 'button') return;
                    fields.push({label: getLabel(el), sel: getSel(el), type: type, val: (el.value || '').substring(0, 30)});
                });
                document.querySelectorAll('button, input[type=submit], [role=button]').forEach(function(el) {
                    if (!isVis(el)) return;
                    var text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                    if (text && text.length < 80) buttons.push({text: text, sel: getSel(el)});
                });
                document.querySelectorAll('a[href]').forEach(function(a) {
                    if (!isVis(a)) return;
                    var text = a.innerText.trim();
                    if (text && text.length > 0 && text.length < 80) links.push(text.substring(0, 60));
                });
                document.querySelectorAll('[role=alert], .error, .alert, .warning').forEach(function(el) {
                    if (!isVis(el)) return;
                    var text = el.innerText.trim();
                    if (text && text.length > 2 && text.length < 200) errors.push(text);
                });
                // Get visible headings for section context
                var headings = [];
                document.querySelectorAll('h1, h2, h3').forEach(function(h) {
                    if (isVis(h)) headings.push(h.innerText.trim().substring(0, 60));
                });
                return JSON.stringify({fields: fields, buttons: buttons, links: links, errors: errors, headings: headings, scrollY: window.scrollY});
            })()
        """)

        try:
            data = json.loads(chunk)
        except Exception:
            data = {}

        # Deduplicate by selector
        for f in data.get("fields", []):
            if f["sel"] not in seen_selectors:
                seen_selectors.add(f["sel"])
                all_fields.append(f)
        for b in data.get("buttons", []):
            if b["sel"] not in seen_selectors:
                seen_selectors.add(b["sel"])
                all_buttons.append(b)
        for e in data.get("errors", []):
            if e not in all_errors:
                all_errors.append(e)
        for l in data.get("links", []):
            if l not in all_links:
                all_links.append(l)
        headings = data.get("headings", [])
        if headings:
            page_sections.extend(headings)

        # Scroll down by 70% of viewport
        current_scroll = data.get("scrollY", 0)
        _js(f"window.scrollBy(0, {int(client_height * 0.7)})")
        time.sleep(0.4)

        # Check if we've reached the bottom
        new_scroll = _js("window.scrollY")
        try:
            if float(new_scroll) <= current_scroll:
                break  # Didn't scroll further — at bottom
        except (ValueError, TypeError):
            break

    # Scroll back to top
    _js("window.scrollTo(0, 0)")
    time.sleep(0.2)

    # Build output
    out = []
    title = _js("document.title") or ""
    url = _js("location.href") or ""
    out.append(f"=== FULL PAGE SCAN ===")
    out.append(f"PAGE: {title}")
    out.append(f"URL: {url}")
    out.append(f"Page height: {scroll_height}px ({max_scrolls} sections scanned)")
    if page_sections:
        out.append(f"Sections: {' → '.join(dict.fromkeys(page_sections))}")
    out.append("")

    if all_fields:
        out.append(f"FIELDS ({len(all_fields)}):")
        for f in all_fields:
            val = f' = "{f["val"]}"' if f.get("val") else ""
            out.append(f'  {f["label"] or f["sel"]} → {f["sel"]} ({f["type"]}){val}')
        out.append("")

    if all_errors:
        out.append("🚨 ERRORS:")
        for e in all_errors:
            out.append(f"  ❌ {e}")
        out.append("")

    if all_buttons:
        out.append(f"BUTTONS ({len(all_buttons)}):")
        for b in all_buttons:
            out.append(f'  [{b["text"]}] → {b["sel"]}')
        out.append("")

    if all_links:
        out.append(f"LINKS ({len(all_links)}):")
        for l in all_links[:40]:
            out.append(f"  [{l}]")
        out.append("")

    return "\n".join(out)


def act_solve_captcha():
    """Auto-detect and solve CAPTCHA on the current page.

    Solving strategy (escalating):
    1. Press-and-hold CAPTCHAs → direct hold interaction
    2. reCAPTCHA/Turnstile/hCaptcha checkbox → click the checkbox iframe
    3. Vision LLM analysis → screenshot + Gemini vision for complex CAPTCHAs

    Returns result string describing what happened.
    """
    _ensure()

    # Check if this is a press-and-hold CAPTCHA
    page_text = _js("document.body ? document.body.innerText.substring(0, 2000) : ''")
    lower = (page_text or "").lower()

    if "press and hold" in lower or "press & hold" in lower:
        # Find the CAPTCHA iframe or button
        result = act_press_and_hold("captcha", duration=10)
        if "ERROR" in result:
            # Fallback: try pressing at any visible interactive iframe
            result = act_press_and_hold("captcha", duration=12)
        if "ERROR" not in result:
            time.sleep(3)
            new_title = _js("document.title") or ""
            new_text = _js("document.body ? document.body.innerText.substring(0, 500) : ''")
            if "press and hold" not in (new_text or "").lower():
                return f"CAPTCHA solved! Page now: {new_title}"
            else:
                return "CAPTCHA press-and-hold attempted but page still shows challenge. May need retry."
        return result

    # Strategy 2: Try clicking reCAPTCHA/Turnstile/hCaptcha checkbox
    try:
        from hands.captcha_solver import solve_recaptcha_checkbox
        checkbox_result = solve_recaptcha_checkbox(None)
        if checkbox_result:
            time.sleep(3)
            # Check if challenge appeared (image grid) or if it's solved
            new_text = _js("document.body ? document.body.innerText.substring(0, 1000) : ''") or ""
            challenge = _detect_challenge()
            if not challenge:
                return f"CAPTCHA solved! {checkbox_result}"
            # Checkbox clicked but image challenge appeared — use vision
            logger.info("[CAPTCHA] Checkbox clicked but challenge appeared — trying vision analysis")
    except Exception as e:
        logger.debug(f"[CAPTCHA] Checkbox approach failed: {e}")

    # Strategy 3: Vision LLM analysis
    try:
        from hands.captcha_solver import analyze_captcha_screenshot, solve_with_vision

        # Take screenshot for vision analysis
        screenshot_result = act_screenshot()
        screenshot_b64 = None
        if isinstance(screenshot_result, dict):
            screenshot_b64 = screenshot_result.get("image_base64")

        if screenshot_b64:
            analysis = analyze_captcha_screenshot(screenshot_b64)
            if analysis.get("captcha_found"):
                captcha_type = analysis.get("type", "unknown")
                action = analysis.get("action", "none")
                details = analysis.get("details", {})

                # Handle text CAPTCHAs directly
                if captcha_type == "text_captcha" and isinstance(details, dict) and details.get("text_to_type"):
                    return f"✅ CAPTCHA text recognized by vision: '{details['text_to_type']}' — type this into the CAPTCHA input field now."

                # Handle math CAPTCHAs directly
                if captcha_type == "math_captcha" and isinstance(details, dict) and details.get("text_to_type"):
                    return f"✅ CAPTCHA answer: '{details['text_to_type']}' — type this into the CAPTCHA input field now."

                # Handle image grid challenges
                if captcha_type == "recaptcha_image":
                    challenge_text = details.get("challenge_text", "") if isinstance(details, dict) else ""
                    tiles = details.get("tiles_to_click", []) if isinstance(details, dict) else []
                    return (
                        f"🖼️ reCAPTCHA image challenge detected: '{challenge_text}'\n"
                        f"Vision suggests tiles: {tiles} (1=top-left, 9=bottom-right)\n"
                        f"Take a screenshot() to see the grid, click each suggested tile by position, then click 'Verify'.\n"
                        f"If wrong, new images will appear — take another screenshot and retry."
                    )

                # Generic CAPTCHA guidance
                desc = details.get("description", str(details)) if isinstance(details, dict) else str(details)
                return f"CAPTCHA detected: {captcha_type} ({action}). {desc}. Consider using Screen Agent for complex visual CAPTCHAs."
            else:
                return "Vision analysis found no CAPTCHA in the screenshot. The page may have loaded past it."
    except ImportError:
        logger.debug("[CAPTCHA] Vision solver not available")
    except Exception as e:
        logger.warning(f"[CAPTCHA] Vision analysis failed: {e}")

    # Check for other CAPTCHA types (fallback)
    challenge = _detect_challenge()
    if challenge:
        return f"Detected challenge: {challenge}. Try: 1) screenshot() to see it, 2) solve_captcha() again after a few seconds, 3) If persistent, the Screen Agent handles CAPTCHAs better."

    return "No CAPTCHA detected on this page."


# ═══════════════════════════════════════════════════════
#  CAPTCHA/Challenge Detection
# ═══════════════════════════════════════════════════════

def _detect_challenge():
    """Detect if the page is blocked by a CAPTCHA or verification challenge."""
    _ensure()
    text = _js("""
        (function() {
            var body = document.body ? document.body.innerText : '';
            var lower = body.toLowerCase();
            var title = document.title.toLowerCase();

            if (title.indexOf('unusual traffic') !== -1) return 'Blocked: unusual traffic';
            if (title.indexOf('captcha') !== -1) return 'Blocked: CAPTCHA page';
            if (lower.indexOf('press and hold') !== -1) return 'press_and_hold';
            if (title.indexOf('prove you') !== -1) return 'press_and_hold';

            if (body.length < 1500) {
                if (lower.indexOf('verify you are human') !== -1) return 'Blocked: human verification';
                if (lower.indexOf('unusual traffic') !== -1) return 'Blocked: traffic challenge';
                if (lower.indexOf('are you a robot') !== -1) return 'Blocked: robot check';
                if (lower.indexOf('complete the security check') !== -1) return 'Blocked: security check';
            }

            var visible = document.querySelector('.g-recaptcha, #recaptcha, [data-sitekey]');
            if (visible) {
                var r = visible.getBoundingClientRect();
                if (r.width > 50 && r.height > 50) return 'Visible CAPTCHA widget';
            }

            return '';
        })()
    """)
    return text if text else None


# ═══════════════════════════════════════════════════════
#  Chrome Activation (compatibility shim)
# ═══════════════════════════════════════════════════════

def _activate_chrome():
    """Ensure Chrome is running and CDP is connected.
    With CDP, Chrome doesn't need to be in the foreground.
    """
    _ensure()


# ═══════════════════════════════════════════════════════
#  Web Search (used by research agent & executor)
# ═══════════════════════════════════════════════════════

def web_search(query):
    """Search Google and return results dict."""
    try:
        text = act_google(query)
        return {"success": True, "content": text}
    except Exception as e:
        return {"success": False, "content": f"Search failed: {e}"}


# ═══════════════════════════════════════════════════════
#  Apply browser lock to ALL public act_* functions
#  Prevents concurrent agents from interleaving CDP ops
# ═══════════════════════════════════════════════════════

def _apply_browser_locks():
    """Wrap all act_* functions with _browser_lock at module init."""
    import sys
    _mod = sys.modules[__name__]
    for name in dir(_mod):
        if name.startswith("act_"):
            fn = getattr(_mod, name)
            if callable(fn):
                setattr(_mod, name, _with_browser_lock(fn))

_apply_browser_locks()
