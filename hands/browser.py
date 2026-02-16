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
import threading
import urllib.parse

from hands.cdp import CDP, CDP_PORT


# ═══════════════════════════════════════════════════════
#  Module State — Singleton CDP Connection
# ═══════════════════════════════════════════════════════

_cdp = None
_browser_lock = threading.Lock()  # Serializes all browser operations across agents


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
            print(f"    🔔 Auto-accepted dialog: {msg[:80]}")
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
        print(f"    ⚠️ CDP timeout #{_consecutive_timeouts}: {str(e)[:80]}")
        # Try to unstick the browser by navigating to a blank page
        try:
            if _consecutive_timeouts >= 3:
                # Force full reconnect after 3+ consecutive timeouts
                print(f"    🔄 Forcing CDP reconnect after {_consecutive_timeouts} consecutive timeouts")
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
            print(f"    🔄 Forcing CDP reconnect after {_consecutive_timeouts} consecutive errors")
            if _cdp:
                try:
                    _cdp.connected = False
                except Exception:
                    pass
                _cdp = None
            _consecutive_timeouts = 0
        return f"JS_ERROR: {e}"


def _reset_page():
    """Navigate to about:blank and clear state. Call between agent deployments."""
    global _consecutive_timeouts
    _consecutive_timeouts = 0
    try:
        _ensure()
        _cdp.send("Page.navigate", {"url": "about:blank"}, timeout=10)
        time.sleep(0.5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  CDP Input Helpers — Real browser events
# ═══════════════════════════════════════════════════════

def _cdp_click_at(x, y):
    """Dispatch a real mouse click at viewport coordinates via CDP."""
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": x, "y": y
    })
    time.sleep(0.02)
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })
    time.sleep(0.02)
    _cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1,
    })
    time.sleep(0.15)


def _cdp_type_text(text):
    """Type text via CDP's native input pipeline. Triggers all events."""
    _cdp.send("Input.insertText", {"text": text})
    time.sleep(0.05)


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
        # CSS selector path
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
#  Page Reading
# ═══════════════════════════════════════════════════════

def act_inspect_page():
    """Get a structured view of all visible interactive elements.

    Returns formatted text showing: fields, buttons, dropdowns, links,
    checkboxes — everything the agent needs to understand the page.
    """
    _ensure()
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
                if (el.placeholder) return el.placeholder;
                if (el.name) return el.name;
                // Check parent label
                var parent = el.closest('label');
                if (parent) return parent.innerText.trim().substring(0, 40);
                return '';
            }

            function getSel(el) {
                if (el.id) return '#' + CSS.escape(el.id);
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

            // ── Buttons ──
            var btns = [];
            document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]').forEach(function(el) {
                if (!isVis(el)) return;
                var text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                if (text && text.length < 80) btns.push(text);
            });
            if (btns.length) {
                out.push('BUTTONS:');
                btns.forEach(function(b) { out.push('  [' + b + ']'); });
                out.push('');
            }

            // ── Links (first 15 visible) ──
            var links = [];
            document.querySelectorAll('a[href]').forEach(function(a) {
                if (links.length >= 15 || !isVis(a)) return;
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
            document.querySelectorAll('[role=alert], .error, .alert, .warning, [aria-live=assertive], [aria-live=polite], .field-error, .form-error, .validation-error, .invalid-feedback, .help-block, [id*=error], [class*=error], [class*=Error]').forEach(function(el) {
                if (!isVis(el)) return;
                var text = el.innerText.trim();
                if (text && text.length > 2 && text.length < 200 && errors.indexOf(text) === -1) {
                    errors.push(text);
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
    return raw or "Could not inspect page — try act_goto first"


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

    x, y = coords
    _cdp_click_at(x, y)
    time.sleep(0.3)

    return f"Clicked '{target}' at ({x}, {y})"


# ═══════════════════════════════════════════════════════
#  Type — click field + clear + type via CDP input
# ═══════════════════════════════════════════════════════

def act_fill(selector, value):
    """Click on a field, clear it, and type a value.

    Uses CDP mouse click to focus, then native input events to type.
    Works with React, Vue, Angular, vanilla HTML — everything.
    """
    _ensure()

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
    time.sleep(0.15)

    # Clear field using JS + triple-click + delete (robust approach)
    # First, try JS-based clearing (select all text)
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
    
    # Delete the selected text via CDP key event
    _cdp_key("Backspace", "Backspace", 8)
    time.sleep(0.05)
    
    # Double-check: if field still has value, force-clear via JS and re-focus
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
                    el.focus();
                }}
            }})()
        """)
        time.sleep(0.05)

    # Type the new value via CDP insert
    _cdp_type_text(value)
    time.sleep(0.1)

    # Fire input/change events as backup for frameworks
    _js(f"""
        (function() {{
            var el = document.querySelector('{safe_sel}');
            if (el) {{
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }})()
    """)

    return f"Filled {selector} with '{value}'"


# ═══════════════════════════════════════════════════════
#  Select — handle both native <select> and custom dropdowns
# ═══════════════════════════════════════════════════════

def act_select_option(dropdown_text_or_selector, option_text):
    """Select an option from ANY dropdown — native <select> or custom.

    For native <select>: sets value via JS + dispatches change event.
    For custom dropdowns: clicks to open, finds option, clicks it.
    """
    _ensure()

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
                // Also try finding select by name/id containing the text
                if (!sel) {{
                    document.querySelectorAll('select').forEach(function(s) {{
                        if (s.name && s.name.toLowerCase().indexOf('{safe_dd}'.toLowerCase()) !== -1) sel = s;
                        if (s.id && s.id.toLowerCase().indexOf('{safe_dd}'.toLowerCase()) !== -1) sel = s;
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
    """Capture a screenshot of the page via CDP."""
    _ensure()
    try:
        result = _cdp.send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 80,
        })
        data = result.get("data", "")
        if data:
            path = os.path.join(
                tempfile.gettempdir(),
                f"tars_screenshot_{int(time.time())}.jpg"
            )
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            return f"Screenshot saved: {path}"
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


def act_solve_captcha():
    """Auto-detect and solve CAPTCHA on the current page.

    Currently handles:
    - 'Press and hold' CAPTCHAs (hsprotect / Microsoft)
    - Standard hold-button CAPTCHAs

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

    # Check for other CAPTCHA types
    challenge = _detect_challenge()
    if challenge:
        return f"Detected challenge: {challenge} — cannot auto-solve this type yet."

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
