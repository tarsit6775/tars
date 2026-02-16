"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Hands: Mac Controller (Full macOS Control)       ║
╠══════════════════════════════════════════════════════════════╣
║  Complete macOS automation engine. Controls:                 ║
║    • Apps — open, quit, hide, activate, frontmost            ║
║    • Keyboard — type text, press keys, shortcuts             ║
║    • Mouse — click, double-click, right-click, drag          ║
║    • Windows — move, resize, minimize, fullscreen, tile      ║
║    • Audio — volume, mute, play/pause                        ║
║    • Display — brightness, dark mode                         ║
║    • Clipboard — read/write text                             ║
║    • Notifications — send native macOS notifications         ║
║    • Finder — tags, reveal, Quick Look, open with            ║
║    • Spotlight — search files by content, type, date         ║
║    • Mail — read, send, search email                         ║
║    • Notes — create, read, search notes                      ║
║    • Calendar — create, read events                          ║
║    • Reminders — create, list, complete                      ║
║    • Contacts — search, read contact info                    ║
║    • Keychain — secure credential storage                    ║
║    • System — Wi-Fi, sleep, lock, screenshot                 ║
║    • OCR — screen text extraction via Vision framework       ║
║    • Accessibility — UI element tree reading                 ║
║    • Environment — snapshot, prepare, diff                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import subprocess
import time
import json
import os
import tempfile
import logging

log = logging.getLogger("tars.mac_control")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Core: AppleScript Runners
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _run_applescript(script, timeout=30):
    """Run an AppleScript and return structured result."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return {"success": True, "content": result.stdout.strip()}
        else:
            return {"success": False, "error": True, "content": f"AppleScript error: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": True, "content": f"AppleScript timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error: {e}"}


def _run_applescript_stdin(script, timeout=30):
    """Run AppleScript via stdin to avoid shell escaping issues."""
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return {"success": True, "content": result.stdout.strip()}
        else:
            return {"success": False, "error": True, "content": f"AppleScript error: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": True, "content": f"AppleScript timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error: {e}"}


def _run_cmd(cmd, timeout=30):
    """Run a shell command and return structured result."""
    try:
        result = subprocess.run(
            cmd if isinstance(cmd, list) else cmd.split(),
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return {"success": True, "content": result.stdout.strip()}
        else:
            return {"success": False, "error": True, "content": result.stderr.strip() or f"Exit code {result.returncode}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1. APP CONTROL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def open_app(app_name):
    """Open/activate a macOS application by name."""
    script = f'tell application "{app_name}" to activate'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Opened {app_name}"
        time.sleep(1)
    return result


def quit_app(app_name, force=False):
    """Quit a macOS application. Use force=True for unresponsive apps."""
    if force:
        result = _run_cmd(["pkill", "-9", "-f", app_name])
        if result["success"]:
            result["content"] = f"Force-killed {app_name}"
    else:
        script = f'tell application "{app_name}" to quit'
        result = _run_applescript(script)
        if result["success"]:
            result["content"] = f"Quit {app_name}"
    return result


def hide_app(app_name):
    """Hide a macOS application."""
    script = f'tell application "System Events" to set visible of process "{app_name}" to false'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Hidden {app_name}"
    return result


def get_frontmost_app():
    """Get the name of the frontmost application."""
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    return _run_applescript(script)


def get_running_apps():
    """Get list of all running visible applications."""
    script = 'tell application "System Events" to get name of every process whose background only is false'
    result = _run_applescript(script)
    if result["success"]:
        apps = [a.strip() for a in result["content"].split(",")]
        result["content"] = json.dumps(apps)
        result["apps"] = apps
    return result


def app_is_running(app_name):
    """Check if a specific app is running."""
    script = f'''
    tell application "System Events"
        return (name of every process) contains "{app_name}"
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["running"] = result["content"].lower() == "true"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2. KEYBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def type_text(text):
    """Type text into the frontmost application using System Events."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Typed {len(text)} characters"
    return result


def key_press(keys):
    """
    Press a keyboard shortcut.
    Format: 'command+s', 'command+shift+p', 'return', 'tab', 'f5', etc.
    """
    parts = keys.lower().split("+")
    key = parts[-1].strip()
    modifiers = [p.strip() for p in parts[:-1]] if len(parts) > 1 else []

    special_keys = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "delete": 51, "escape": 53, "esc": 53,
        "up": 126, "down": 125, "left": 123, "right": 124,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118,
        "f5": 96, "f6": 97, "f7": 98, "f8": 100,
        "f9": 101, "f10": 109, "f11": 103, "f12": 111,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "volumeup": 72, "volumedown": 73, "mute": 74,
        "brightnessup": 144, "brightnessdown": 145,
        "playpause": 16,
    }

    modifier_map = {
        "command": "command down", "cmd": "command down",
        "control": "control down", "ctrl": "control down",
        "option": "option down", "alt": "option down",
        "shift": "shift down",
    }

    modifier_str = ", ".join(modifier_map.get(m, f"{m} down") for m in modifiers)

    if key in special_keys:
        code = special_keys[key]
        if modifier_str:
            script = f'tell application "System Events" to key code {code} using {{{modifier_str}}}'
        else:
            script = f'tell application "System Events" to key code {code}'
    else:
        if modifier_str:
            script = f'tell application "System Events" to keystroke "{key}" using {{{modifier_str}}}'
        else:
            script = f'tell application "System Events" to keystroke "{key}"'

    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Pressed {keys}"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3. MOUSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def click(x, y, double_click=False):
    """Click at screen coordinates. Uses cliclick if available."""
    try:
        flag = "dc" if double_click else "c"
        result = subprocess.run(
            ["cliclick", f"{flag}:{x},{y}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return {"success": True, "content": f"Clicked at ({x}, {y})"}
    except FileNotFoundError:
        pass

    click_cmd = "click" if not double_click else "double click"
    script = f'tell application "System Events" to {click_cmd} at {{{x}, {y}}}'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Clicked at ({x}, {y})"
    return result


def right_click(x, y):
    """Right-click at screen coordinates."""
    try:
        result = subprocess.run(
            ["cliclick", f"rc:{x},{y}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return {"success": True, "content": f"Right-clicked at ({x}, {y})"}
    except FileNotFoundError:
        pass
    script = f'''
    tell application "System Events"
        key down control
        click at {{{x}, {y}}}
        key up control
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Right-clicked at ({x}, {y})"
    return result


def drag(x1, y1, x2, y2, duration=0.5):
    """Drag from one point to another."""
    try:
        result = subprocess.run(
            ["cliclick", f"dd:{x1},{y1}", f"du:{x2},{y2}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "content": f"Dragged from ({x1},{y1}) to ({x2},{y2})"}
    except FileNotFoundError:
        pass
    try:
        from Quartz import (
            CGEventCreateMouseEvent, CGEventPost,
            kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventLeftMouseDragged,
            kCGHIDEventTap, CGPointMake,
        )
        steps = 20
        dx = (x2 - x1) / steps
        dy = (y2 - y1) / steps
        down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, CGPointMake(x1, y1), 0)
        CGEventPost(kCGHIDEventTap, down)
        for i in range(steps):
            pt = CGPointMake(x1 + dx * (i + 1), y1 + dy * (i + 1))
            drag_ev = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, pt, 0)
            CGEventPost(kCGHIDEventTap, drag_ev)
            time.sleep(duration / steps)
        up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, CGPointMake(x2, y2), 0)
        CGEventPost(kCGHIDEventTap, up)
        return {"success": True, "content": f"Dragged from ({x1},{y1}) to ({x2},{y2})"}
    except ImportError:
        return {"success": False, "error": True, "content": "Drag requires cliclick or pyobjc-framework-Quartz"}


def mouse_move(x, y):
    """Move mouse to coordinates without clicking."""
    try:
        result = subprocess.run(["cliclick", f"m:{x},{y}"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return {"success": True, "content": f"Mouse moved to ({x}, {y})"}
    except FileNotFoundError:
        pass
    return {"success": False, "error": True, "content": "mouse_move requires cliclick"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  4. WINDOW MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_windows(app_name=None):
    """Get all windows of an app (or frontmost app)."""
    if app_name:
        target = f'process "{app_name}"'
    else:
        target = '(first process whose frontmost is true)'
    script = f'''
    tell application "System Events"
        set proc to {target}
        set winInfo to ""
        repeat with w in windows of proc
            set winInfo to winInfo & (name of w) & " | pos:" & (position of w as string) & " | size:" & (size of w as string) & linefeed
        end repeat
        return winInfo
    end tell
    '''
    return _run_applescript(script)


def move_window(x, y, app_name=None):
    """Move frontmost window to position."""
    target = f'process "{app_name}"' if app_name else '(first process whose frontmost is true)'
    script = f'tell application "System Events" to set position of first window of {target} to {{{x}, {y}}}'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Moved window to ({x}, {y})"
    return result


def resize_window(width, height, app_name=None):
    """Resize frontmost window."""
    target = f'process "{app_name}"' if app_name else '(first process whose frontmost is true)'
    script = f'tell application "System Events" to set size of first window of {target} to {{{width}, {height}}}'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Resized window to {width}x{height}"
    return result


def tile_window(position="left"):
    """Tile frontmost window. position: left, right, top, bottom, fullscreen, center."""
    script = 'tell application "Finder" to get bounds of window of desktop'
    bounds = _run_applescript(script)
    if not bounds["success"]:
        sw, sh = 1920, 1080
    else:
        parts = bounds["content"].split(", ")
        sw, sh = int(parts[2]), int(parts[3])
    mb = 25
    layouts = {
        "left":       (0, mb, sw // 2, sh - mb),
        "right":      (sw // 2, mb, sw // 2, sh - mb),
        "top":        (0, mb, sw, (sh - mb) // 2),
        "bottom":     (0, mb + (sh - mb) // 2, sw, (sh - mb) // 2),
        "fullscreen": (0, mb, sw, sh - mb),
        "center":     (sw // 4, sh // 4, sw // 2, sh // 2),
    }
    if position not in layouts:
        return {"success": False, "error": True, "content": f"Unknown: {position}. Use: {', '.join(layouts.keys())}"}
    x, y, w, h = layouts[position]
    script = f'''
    tell application "System Events"
        tell (first process whose frontmost is true)
            set position of first window to {{{x}, {y}}}
            set size of first window to {{{w}, {h}}}
        end tell
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Window tiled {position} ({w}x{h})"
    return result


def minimize_window(app_name=None):
    """Minimize frontmost window."""
    target = f'process "{app_name}"' if app_name else '(first process whose frontmost is true)'
    script = f'tell application "System Events" to set miniaturized of first window of {target} to true'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = "Window minimized"
    return result


def close_window(app_name=None):
    """Close frontmost window."""
    target = f'process "{app_name}"' if app_name else '(first process whose frontmost is true)'
    script = f'''
    tell application "System Events"
        click (first button whose subrole is "AXCloseButton") of first window of {target}
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = "Window closed"
    return result


def fullscreen_window():
    """Toggle fullscreen for frontmost window."""
    script = '''
    tell application "System Events"
        tell (first process whose frontmost is true)
            set value of attribute "AXFullScreen" of first window to (not (value of attribute "AXFullScreen" of first window))
        end tell
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = "Toggled fullscreen"
    return result


def close_all_windows():
    """Close all windows of the frontmost app."""
    script = '''
    tell application "System Events"
        set frontApp to name of first process whose frontmost is true
    end tell
    tell application frontApp to close every window
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = "All windows closed"
    return result


def hide_all_apps():
    """Hide all applications except Finder."""
    script = 'tell application "System Events" to set visible of every process whose name is not "Finder" to false'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = "All apps hidden"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  5. AUDIO & VOLUME
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def set_volume(level):
    """Set output volume (0-100)."""
    level = max(0, min(100, int(level)))
    result = _run_applescript(f'set volume output volume {level}')
    if result["success"]:
        result["content"] = f"Volume set to {level}%"
    return result


def get_volume():
    """Get current output volume."""
    return _run_applescript('output volume of (get volume settings)')


def toggle_mute():
    """Toggle mute state."""
    script = '''
    set currentMute to output muted of (get volume settings)
    set volume output muted (not currentMute)
    if currentMute then
        return "Unmuted"
    else
        return "Muted"
    end if
    '''
    return _run_applescript(script)


def play_pause():
    """Toggle play/pause for media."""
    return key_press("playpause")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  6. DISPLAY & APPEARANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def set_dark_mode(enabled=True):
    """Enable or disable dark mode."""
    val = "true" if enabled else "false"
    script = f'tell application "System Events" to tell appearance preferences to set dark mode to {val}'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Dark mode {'enabled' if enabled else 'disabled'}"
    return result


def get_dark_mode():
    """Check if dark mode is on."""
    return _run_applescript('tell application "System Events" to tell appearance preferences to get dark mode')


def adjust_brightness(direction="up"):
    """Adjust brightness up or down."""
    return key_press("brightnessup" if direction == "up" else "brightnessdown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  7. CLIPBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def clipboard_read():
    """Read text from the clipboard."""
    result = _run_cmd(["pbpaste"])
    if result["success"]:
        result["content"] = result["content"] or "(clipboard is empty)"
    return result


def clipboard_write(text):
    """Write text to the clipboard."""
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), capture_output=True, timeout=5)
        return {"success": True, "content": f"Copied {len(text)} chars to clipboard"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Clipboard write failed: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  8. NOTIFICATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def notify(message, title="TARS", subtitle="", sound="Ping"):
    """Send a native macOS notification."""
    script = f'display notification "{message}" with title "{title}"'
    if subtitle:
        script += f' subtitle "{subtitle}"'
    script += f' sound name "{sound}"'
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Notification: {title} — {message}"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  9. SPOTLIGHT / FILE SEARCH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def spotlight_search(query, folder=None, max_results=20):
    """Search files via Spotlight (mdfind).
    Examples: "meeting notes", "kind:pdf", "date:today kind:document"
    """
    cmd = ["mdfind"]
    if folder:
        cmd += ["-onlyin", os.path.expanduser(folder)]
    cmd.append(query)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        files = [f for f in result.stdout.strip().split("\n") if f][:max_results]
        if files:
            formatted = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(files))
            return {"success": True, "content": f"Found {len(files)} results:\n{formatted}", "files": files}
        return {"success": True, "content": "No results found", "files": []}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Search error: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  10. SCREENSHOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def take_screenshot(region=None):
    """Take a screenshot. region=(x,y,w,h) or None for full screen."""
    path = os.path.join(tempfile.gettempdir(), f"tars_screenshot_{int(time.time())}.png")
    cmd = ["screencapture", "-x"]
    if region:
        cmd.extend(["-R", f"{region[0]},{region[1]},{region[2]},{region[3]}"])
    cmd.append(path)
    try:
        subprocess.run(cmd, timeout=10)
        if os.path.exists(path):
            size = os.path.getsize(path)
            return {"success": True, "content": f"Screenshot saved: {path} ({size:,} bytes)", "path": path}
        return {"success": False, "error": True, "content": "Screenshot not created"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Screenshot failed: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  11. FINDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def finder_reveal(path):
    """Reveal a file in Finder."""
    result = _run_cmd(["open", "-R", os.path.expanduser(path)])
    if result["success"]:
        result["content"] = f"Revealed in Finder: {path}"
    return result


def finder_open_with(path, app_name):
    """Open a file with a specific app."""
    result = _run_cmd(["open", "-a", app_name, os.path.expanduser(path)])
    if result["success"]:
        result["content"] = f"Opened {path} with {app_name}"
    return result


def finder_tag(path, tag_name):
    """Add a Finder tag to a file."""
    path = os.path.expanduser(path)
    script = f'''
    tell application "Finder"
        set theFile to POSIX file "{path}" as alias
        set current tags to tags of theFile
        set tags of theFile to current tags & {{"{tag_name}"}}
    end tell
    '''
    result = _run_applescript_stdin(script)
    if result["success"]:
        result["content"] = f"Tagged {os.path.basename(path)} with '{tag_name}'"
    return result


def finder_get_selection():
    """Get the currently selected files in Finder."""
    script = '''
    tell application "Finder"
        set theSelection to selection as alias list
        set paths to ""
        repeat with f in theSelection
            set paths to paths & POSIX path of f & linefeed
        end repeat
        return paths
    end tell
    '''
    return _run_applescript(script)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  12. MAIL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def mail_unread_count():
    """Get unread email count."""
    return _run_applescript('tell application "Mail" to get unread count of inbox')


def mail_read_inbox(count=5):
    """Read latest emails from inbox."""
    script = f'''
    tell application "Mail"
        set msgs to messages 1 thru {count} of inbox
        set output to ""
        repeat with m in msgs
            set output to output & "FROM: " & (sender of m) & linefeed
            set output to output & "SUBJECT: " & (subject of m) & linefeed
            set output to output & "DATE: " & (date received of m as string) & linefeed
            set output to output & "---" & linefeed
        end repeat
        return output
    end tell
    '''
    return _run_applescript(script, timeout=60)


def mail_read_message(index=1):
    """Read full email by index (1 = newest)."""
    script = f'''
    tell application "Mail"
        set m to message {index} of inbox
        set output to "FROM: " & (sender of m) & linefeed
        set output to output & "TO: " & (address of to recipient 1 of m) & linefeed
        set output to output & "SUBJECT: " & (subject of m) & linefeed
        set output to output & "DATE: " & (date received of m as string) & linefeed
        set output to output & linefeed & (content of m)
        return output
    end tell
    '''
    return _run_applescript(script, timeout=60)


def mail_search(keyword, mailbox="inbox"):
    """Search emails by keyword."""
    script = f'''
    tell application "Mail"
        set found to messages of {mailbox} whose subject contains "{keyword}" or sender contains "{keyword}"
        set output to ""
        set maxResults to 10
        set counter to 0
        repeat with m in found
            if counter >= maxResults then exit repeat
            set output to output & "FROM: " & (sender of m) & " | SUBJECT: " & (subject of m) & " | DATE: " & (date received of m as string) & linefeed
            set counter to counter + 1
        end repeat
        if output is "" then return "No emails matching: {keyword}"
        return output
    end tell
    '''
    return _run_applescript(script, timeout=60)


def mail_send(to_address, subject, body, attachment_path=None, from_address="tarsitgroup@outlook.com"):
    """Send an email via Mail.app with optional attachment.
    
    Args:
        to_address: Recipient email
        subject: Email subject
        body: Email body text
        attachment_path: Optional absolute path to a file to attach
        from_address: Sender account (default: tarsitgroup@outlook.com)
    """
    # Escape special characters for AppleScript
    safe_subject = subject.replace('\\', '\\\\').replace('"', '\\"')
    safe_body = body.replace('\\', '\\\\').replace('"', '\\"')
    
    if attachment_path:
        # Expand ~ and resolve path
        attachment_path = os.path.expanduser(attachment_path)
        if not os.path.isfile(attachment_path):
            return {"success": False, "error": True, "content": f"Attachment not found: {attachment_path}"}
        # Convert to POSIX file for AppleScript
        script = f'''
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
            tell msg
                make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
                set senderAddr to "{from_address}"
                -- Attach the file
                set theAttachment to POSIX file "{attachment_path}"
                make new attachment with properties {{file name:theAttachment}} at after last paragraph
            end tell
            send msg
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
            tell msg
                make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
            end tell
            send msg
        end tell
        '''
    result = _run_applescript_stdin(script, timeout=60)
    if result["success"]:
        att_info = f" (with attachment: {os.path.basename(attachment_path)})" if attachment_path else ""
        result["content"] = f"Email sent to {to_address}: {subject}{att_info}"
    return result


def mail_verify_sent(subject, to_address=None):
    """Check the Sent mailbox to verify an email was actually sent.
    
    Automatically discovers the correct account and sent mailbox name.
    
    Args:
        subject: Subject line to search for
        to_address: Optional recipient to match
    """
    safe_subject = subject.replace('"', '\\"')
    
    # Try all common sent folder names across all accounts
    sent_names = ["Sent Items", "Sent Messages", "Sent", "Sent Mail"]
    
    # First discover account names
    acct_result = _run_applescript('tell application "Mail" to get name of every account')
    accounts = []
    if acct_result["success"]:
        accounts = [a.strip() for a in acct_result["content"].split(",")]
    if not accounts:
        accounts = ["Exchange", "Outlook", "iCloud"]  # Fallback guesses
    
    for acct in accounts:
        for sent_name in sent_names:
            script = f'''
            tell application "Mail"
                try
                    set sentMsgs to messages of mailbox "{sent_name}" of account "{acct}"
                    set output to ""
                    set found to false
                    set counter to 0
                    repeat with m in sentMsgs
                        if counter >= 20 then exit repeat
                        if subject of m contains "{safe_subject}" then
                            set output to output & "FOUND — Subject: " & (subject of m) & " | To: " & (address of to recipient 1 of m) & " | Date: " & (date sent of m as string) & linefeed
                            set found to true
                        end if
                        set counter to counter + 1
                    end repeat
                    if not found then return "NOT_FOUND"
                    return output
                on error
                    return "NOT_FOUND"
                end try
            end tell
            '''
            result = _run_applescript_stdin(script, timeout=30)
            if result["success"] and "NOT_FOUND" not in result.get("content", ""):
                return result
    
    return {"success": False, "error": True, 
            "content": f"No sent email matching '{safe_subject}' found in any account"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  13. NOTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def notes_list():
    """List all notes."""
    script = '''
    tell application "Notes"
        set noteList to ""
        repeat with n in notes
            set noteList to noteList & (name of n) & " | " & (modification date of n as string) & linefeed
        end repeat
        return noteList
    end tell
    '''
    return _run_applescript(script, timeout=30)


def notes_read(note_name):
    """Read a note by name."""
    script = f'''
    tell application "Notes"
        set matchingNotes to notes whose name is "{note_name}"
        if (count of matchingNotes) > 0 then
            return body of item 1 of matchingNotes
        else
            return "Note not found: {note_name}"
        end if
    end tell
    '''
    return _run_applescript(script, timeout=30)


def notes_create(title, body, folder="Notes"):
    """Create a new note."""
    script = f'''
    tell application "Notes"
        tell folder "{folder}"
            make new note with properties {{name:"{title}", body:"{body}"}}
        end tell
        return "Created note: {title}"
    end tell
    '''
    return _run_applescript_stdin(script, timeout=30)


def notes_search(query):
    """Search notes by title or content."""
    script = f'''
    tell application "Notes"
        set found to notes whose name contains "{query}"
        set output to ""
        set counter to 0
        repeat with n in found
            if counter >= 10 then exit repeat
            set output to output & (name of n) & " | " & (modification date of n as string) & linefeed
            set counter to counter + 1
        end repeat
        if output is "" then return "No notes matching: {query}"
        return output
    end tell
    '''
    return _run_applescript(script, timeout=30)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  14. CALENDAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calendar_list():
    """List all calendars."""
    return _run_applescript('tell application "Calendar" to get name of every calendar')


def calendar_events(calendar_name=None, days_ahead=7):
    """Get upcoming events."""
    cal_filter = f'calendar "{calendar_name}"' if calendar_name else "every calendar"
    script = f'''
    tell application "Calendar"
        set today to current date
        set endDate to today + {days_ahead} * days
        set output to ""
        set eventList to every event of {cal_filter} whose start date >= today and start date <= endDate
        repeat with e in eventList
            set output to output & (summary of e) & " | " & (start date of e as string) & " to " & (end date of e as string) & linefeed
        end repeat
        if output is "" then return "No events in the next {days_ahead} days"
        return output
    end tell
    '''
    return _run_applescript(script, timeout=30)


def calendar_create_event(title, start_date, end_date, calendar_name="Calendar"):
    """Create a calendar event. Dates like 'March 1, 2026 2:00 PM'."""
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_name}"
            make new event with properties {{summary:"{title}", start date:date "{start_date}", end date:date "{end_date}"}}
        end tell
        return "Event created: {title}"
    end tell
    '''
    return _run_applescript_stdin(script, timeout=30)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  15. REMINDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def reminders_list(list_name=None):
    """List reminders. If no list_name, shows all lists with counts."""
    if list_name:
        script = f'''
        tell application "Reminders"
            set output to ""
            repeat with r in reminders of list "{list_name}"
                if completed of r is false then
                    set output to output & (name of r)
                    try
                        set output to output & " | due: " & (due date of r as string)
                    end try
                    set output to output & linefeed
                end if
            end repeat
            if output is "" then return "No incomplete reminders in {list_name}"
            return output
        end tell
        '''
    else:
        script = '''
        tell application "Reminders"
            set output to ""
            repeat with l in lists
                set count_ to count of (reminders of l whose completed is false)
                set output to output & (name of l) & " (" & count_ & " items)" & linefeed
            end repeat
            return output
        end tell
        '''
    return _run_applescript(script, timeout=30)


def reminders_create(title, list_name="Reminders", due_date=None, notes=None):
    """Create a new reminder."""
    props = f'name:"{title}"'
    if due_date:
        props += f', due date:date "{due_date}"'
    if notes:
        props += f', body:"{notes}"'
    script = f'''
    tell application "Reminders"
        tell list "{list_name}"
            make new reminder with properties {{{props}}}
        end tell
        return "Reminder created: {title}"
    end tell
    '''
    return _run_applescript_stdin(script, timeout=30)


def reminders_complete(title, list_name="Reminders"):
    """Mark a reminder as complete."""
    script = f'''
    tell application "Reminders"
        set matching to reminders of list "{list_name}" whose name is "{title}"
        if (count of matching) > 0 then
            set completed of item 1 of matching to true
            return "Completed: {title}"
        else
            return "Reminder not found: {title}"
        end if
    end tell
    '''
    return _run_applescript(script, timeout=30)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  16. CONTACTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def contacts_search(query):
    """Search contacts by name."""
    script = f'''
    tell application "Contacts"
        set found to every person whose name contains "{query}"
        set output to ""
        repeat with p in found
            set output to output & (name of p)
            try
                set output to output & " | " & (value of first email of p)
            end try
            try
                set output to output & " | " & (value of first phone of p)
            end try
            set output to output & linefeed
        end repeat
        if output is "" then return "No contacts matching: {query}"
        return output
    end tell
    '''
    return _run_applescript(script, timeout=30)


def contacts_get(name):
    """Get full details of a contact."""
    script = f'''
    tell application "Contacts"
        set found to every person whose name is "{name}"
        if (count of found) = 0 then return "Contact not found: {name}"
        set p to item 1 of found
        set output to "Name: " & (name of p) & linefeed
        try
            set output to output & "Company: " & (organization of p) & linefeed
        end try
        repeat with e in emails of p
            set output to output & "Email: " & (value of e) & " (" & (label of e) & ")" & linefeed
        end repeat
        repeat with ph in phones of p
            set output to output & "Phone: " & (value of ph) & " (" & (label of ph) & ")" & linefeed
        end repeat
        try
            set output to output & "Birthday: " & (birth date of p as string) & linefeed
        end try
        try
            set output to output & "Notes: " & (note of p) & linefeed
        end try
        return output
    end tell
    '''
    return _run_applescript(script, timeout=30)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  17. KEYCHAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def keychain_store(service, account, password):
    """Store a credential in macOS Keychain."""
    subprocess.run(["security", "delete-generic-password", "-s", service, "-a", account], capture_output=True)
    result = subprocess.run(
        ["security", "add-generic-password", "-s", service, "-a", account, "-w", password, "-U"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return {"success": True, "content": f"Stored credential: {service}/{account}"}
    return {"success": False, "error": True, "content": f"Keychain error: {result.stderr.strip()}"}


def keychain_read(service, account):
    """Read a credential from macOS Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return {"success": True, "content": result.stdout.strip()}
    return {"success": False, "error": True, "content": f"Not found: {service}/{account}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  18. SYSTEM CONTROLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def wifi_toggle(on=True):
    """Toggle Wi-Fi on or off."""
    try:
        r = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True, timeout=5)
        iface = "en0"
        for i, line in enumerate(r.stdout.split("\n")):
            if "Wi-Fi" in line:
                for j in range(i + 1, min(i + 3, len(r.stdout.split("\n")))):
                    if "Device:" in r.stdout.split("\n")[j]:
                        iface = r.stdout.split("\n")[j].split("Device:")[1].strip()
                        break
                break
    except Exception:
        iface = "en0"
    state = "on" if on else "off"
    result = _run_cmd(["networksetup", "-setairportpower", iface, state])
    if result["success"]:
        result["content"] = f"Wi-Fi turned {state}"
    return result


def get_wifi_network():
    """Get current Wi-Fi network name."""
    # Try common interface names
    for iface in ["en0", "en1"]:
        result = _run_cmd(["networksetup", "-getairportnetwork", iface])
        if result["success"] and "not associated" not in result["content"].lower() and "Error" not in result["content"]:
            return result
    return _run_cmd(["networksetup", "-getairportnetwork", "en0"])


def lock_screen():
    """Lock the screen."""
    result = _run_cmd([
        "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"
    ])
    if result["success"]:
        result["content"] = "Screen locked"
    return result


def sleep_mac():
    """Put the Mac to sleep."""
    result = _run_cmd(["pmset", "sleepnow"])
    if result["success"]:
        result["content"] = "Mac going to sleep"
    return result


def get_battery():
    """Get battery status."""
    return _run_cmd(["pmset", "-g", "batt"])


def get_disk_space():
    """Get disk space usage."""
    return _run_cmd(["df", "-h", "/"])


def run_siri_shortcut(shortcut_name, input_text=None):
    """Run a Siri Shortcut by name."""
    cmd = ["shortcuts", "run", shortcut_name]
    if input_text:
        cmd.extend(["-i", input_text])
    result = _run_cmd(cmd)
    if result["success"]:
        result["content"] = f"Ran shortcut: {shortcut_name}"
    return result


def open_url(url):
    """Open a URL in the default browser."""
    result = _run_cmd(["open", url])
    if result["success"]:
        result["content"] = f"Opened: {url}"
    return result


def open_file(path, app_name=None):
    """Open a file with default or specific app."""
    path = os.path.expanduser(path)
    cmd = ["open"]
    if app_name:
        cmd.extend(["-a", app_name])
    cmd.append(path)
    result = _run_cmd(cmd)
    if result["success"]:
        result["content"] = f"Opened {path}" + (f" with {app_name}" if app_name else "")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  19. SCREEN OCR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ocr_screen(region=None):
    """Screenshot + OCR. Returns text on screen."""
    ss = take_screenshot(region=region)
    if not ss["success"]:
        return ss
    return ocr_image(ss["path"])


def ocr_image(image_path):
    """OCR an image using Apple Vision framework."""
    try:
        import Vision
        import Quartz
        from Foundation import NSURL

        url = NSURL.fileURLWithPath_(image_path)
        source = Quartz.CGImageSourceCreateWithURL(url, None)
        if not source:
            return {"success": False, "error": True, "content": f"Cannot read image: {image_path}"}
        image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
        if not image:
            return {"success": False, "error": True, "content": "Cannot decode image"}
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(1)
        request.setUsesLanguageCorrection_(True)
        success, error = handler.performRequests_error_([request], None)
        if not success:
            return {"success": False, "error": True, "content": f"OCR failed: {error}"}
        texts = []
        for obs in request.results():
            texts.append(obs.topCandidates_(1)[0].string())
        return {"success": True, "content": "\n".join(texts) or "(no text detected)", "text_count": len(texts)}
    except ImportError:
        return {"success": False, "error": True, "content": "OCR needs: pip install pyobjc-framework-Vision pyobjc-framework-Quartz"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"OCR error: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  20. ACCESSIBILITY (UI Element Tree)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_ui_elements(app_name=None, max_depth=3):
    """Read UI element tree of any app via Accessibility API."""
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            AXUIElementCopyAttributeNames,
            kAXErrorSuccess,
        )
        from AppKit import NSWorkspace

        ws = NSWorkspace.sharedWorkspace()
        target_pid = None
        if app_name:
            for app in ws.runningApplications():
                if app.localizedName() == app_name:
                    target_pid = app.processIdentifier()
                    break
            if not target_pid:
                return {"success": False, "error": True, "content": f"App not found: {app_name}"}
        else:
            app = ws.frontmostApplication()
            target_pid = app.processIdentifier()
            app_name = app.localizedName()

        root = AXUIElementCreateApplication(target_pid)
        tree = _read_ax_element(root, max_depth, AXUIElementCopyAttributeValue, AXUIElementCopyAttributeNames, kAXErrorSuccess)
        formatted = _format_ax_tree(tree)
        return {"success": True, "content": f"UI Tree for {app_name}:\n{formatted}", "tree": tree}
    except ImportError:
        return {"success": False, "error": True, "content": "Needs: pip install pyobjc-framework-ApplicationServices"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Accessibility error: {e}"}


def _read_ax_element(element, depth, copy_value, copy_names, ok, level=0):
    if depth <= 0:
        return None
    try:
        err, names = copy_names(element, None)
        if err != ok:
            return None
    except Exception:
        return None
    info = {}
    for attr in ["AXRole", "AXTitle", "AXValue", "AXDescription", "AXRoleDescription", "AXEnabled", "AXIdentifier"]:
        if attr in names:
            try:
                err, val = copy_value(element, attr, None)
                if err == ok and val is not None:
                    info[attr] = str(val)[:200]
            except Exception:
                pass
    if "AXChildren" in names and depth > 1:
        try:
            err, children = copy_value(element, "AXChildren", None)
            if err == ok and children:
                child_list = [c for c in (_read_ax_element(c, depth - 1, copy_value, copy_names, ok, level + 1) for c in children[:50]) if c]
                if child_list:
                    info["children"] = child_list
        except Exception:
            pass
    return info if info else None


def _format_ax_tree(node, indent=0):
    if not node:
        return ""
    prefix = "  " * indent
    parts = [node.get("AXRole", "?")]
    if node.get("AXTitle"):
        parts.append(f'"{node["AXTitle"]}"')
    if node.get("AXValue") and node.get("AXValue") != node.get("AXTitle"):
        parts.append(f'val="{node["AXValue"][:50]}"')
    if node.get("AXRoleDescription"):
        parts.append(f'({node["AXRoleDescription"]})')
    if node.get("AXIdentifier"):
        parts.append(f'[{node["AXIdentifier"]}]')
    line = f"{prefix}• {' '.join(parts)}\n"
    for child in node.get("children", []):
        line += _format_ax_tree(child, indent + 1)
    return line


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  21. ENVIRONMENT ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_environment_snapshot():
    """Complete Mac environment snapshot."""
    snapshot = {}
    r = get_frontmost_app()
    snapshot["frontmost_app"] = r.get("content", "unknown")
    r = get_running_apps()
    snapshot["running_apps"] = r.get("apps", [])
    r = get_volume()
    snapshot["volume"] = r.get("content", "unknown")
    r = get_dark_mode()
    snapshot["dark_mode"] = r.get("content", "unknown")
    r = clipboard_read()
    snapshot["clipboard_preview"] = r.get("content", "")[:200]
    r = get_battery()
    snapshot["battery"] = r.get("content", "unknown")
    r = get_disk_space()
    snapshot["disk"] = r.get("content", "unknown")
    r = get_wifi_network()
    snapshot["wifi"] = r.get("content", "unknown")
    r = _run_applescript('tell application "Finder" to get bounds of window of desktop')
    snapshot["screen_bounds"] = r.get("content", "unknown")

    apps_str = ", ".join(snapshot["running_apps"][:15]) if snapshot["running_apps"] else "none"
    summary = f"""## Mac Environment Snapshot
- **Frontmost App:** {snapshot['frontmost_app']}
- **Running Apps:** {apps_str}
- **Volume:** {snapshot['volume']}%
- **Dark Mode:** {snapshot['dark_mode']}
- **Wi-Fi:** {snapshot['wifi']}
- **Battery:** {snapshot['battery']}
- **Disk:** {snapshot['disk']}
- **Screen:** {snapshot['screen_bounds']}
- **Clipboard:** {snapshot['clipboard_preview'][:100]}
"""
    return {"success": True, "content": summary, "snapshot": snapshot}


def prepare_environment(close_apps=None, open_apps=None, volume=None, dark_mode=None):
    """Prepare Mac for TARS operation."""
    actions = []
    if close_apps:
        for app in close_apps:
            r = quit_app(app)
            actions.append(f"{'✅' if r['success'] else '❌'} Close {app}")
    if volume is not None:
        r = set_volume(volume)
        actions.append(f"{'✅' if r['success'] else '❌'} Volume → {volume}%")
    if dark_mode is not None:
        r = set_dark_mode(dark_mode)
        actions.append(f"{'✅' if r['success'] else '❌'} Dark mode → {'on' if dark_mode else 'off'}")
    if open_apps:
        for app in open_apps:
            r = open_app(app)
            actions.append(f"{'✅' if r['success'] else '❌'} Open {app}")
    return {"success": True, "content": "Environment prepared:\n" + "\n".join(actions) if actions else "No actions"}


def get_session_diff(last_snapshot):
    """Compare current env to a previous snapshot. Returns changes."""
    current = get_environment_snapshot()
    if not current["success"]:
        return current
    curr = current.get("snapshot", {})
    changes = []
    curr_apps = set(curr.get("running_apps", []))
    last_apps = set(last_snapshot.get("running_apps", []))
    new_apps = curr_apps - last_apps
    closed_apps = last_apps - curr_apps
    if new_apps:
        changes.append(f"📱 New apps: {', '.join(new_apps)}")
    if closed_apps:
        changes.append(f"📴 Apps closed: {', '.join(closed_apps)}")
    if curr.get("frontmost_app") != last_snapshot.get("frontmost_app"):
        changes.append(f"🔝 Active: {last_snapshot.get('frontmost_app')} → {curr.get('frontmost_app')}")
    if curr.get("volume") != last_snapshot.get("volume"):
        changes.append(f"🔊 Volume: {last_snapshot.get('volume')} → {curr.get('volume')}")
    if curr.get("dark_mode") != last_snapshot.get("dark_mode"):
        changes.append(f"🌙 Dark mode: {last_snapshot.get('dark_mode')} → {curr.get('dark_mode')}")
    summary = "## Session Changes\n" + "\n".join(changes) if changes else "## Session Changes\nNo changes"
    return {"success": True, "content": summary, "changes": changes, "current_snapshot": curr}
