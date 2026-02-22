"""
╔══════════════════════════════════════════════════════════════╗
║       TARS — Environment Manager (macOS Workspace Setup)     ║
╠══════════════════════════════════════════════════════════════╣
║  Autonomous workspace management on startup:                 ║
║    • Detect & assign screens (TARS / User / Dev)             ║
║    • Close clutter apps, open essentials                     ║
║    • Arrange windows to assigned screens                     ║
║    • Enable Do Not Disturb                                   ║
║    • Clipboard save/restore guard                            ║
║    • Focus-steal prevention                                  ║
║    • Chrome profile isolation on TARS screen                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import subprocess
import time
import json
import os
import logging

from utils.event_bus import event_bus

log = logging.getLogger("tars.environment")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Core helpers (copied pattern from mac_control.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _run_applescript(script, timeout=30):
    """Run an AppleScript and return structured result."""
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
#  1. SCREEN DETECTION & ASSIGNMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_displays():
    """Detect all connected displays with positions and sizes.

    Returns list of dicts sorted by x position (leftmost first):
    [{"name": "C27F398", "id": 3, "x": -1920, "y": 0, "width": 1920, "height": 1080, "main": False}, ...]
    """
    # Get display names and IDs from System Events
    name_script = '''
    tell application "System Events"
        set displayCount to (count of desktops)
        set info to ""
        repeat with i from 1 to displayCount
            set d to desktop i
            set dName to name of d
            set dId to id of d
            set info to info & dName & "|" & dId & linefeed
        end repeat
        return info
    end tell
    '''
    name_result = _run_applescript(name_script)

    # Get screen bounds from system_profiler + window positions
    # Parse display info from system_profiler
    # Note: "Main Display: Yes" appears AFTER "Resolution:" in output,
    # so we must collect ALL attributes per display before recording.
    profiler = _run_cmd(["system_profiler", "SPDisplaysDataType"])
    displays_raw = []
    if profiler["success"]:
        lines = profiler["content"].split("\n")
        # First pass: split into per-display sections
        sections = []  # [{"name": ..., "lines": [...]}, ...]
        current_section = None
        skip_names = {"Graphics/Displays", "Displays"}
        for line in lines:
            stripped = line.strip()
            if stripped.endswith(":") and "Resolution" not in stripped and "UI Looks" not in stripped:
                candidate = stripped.rstrip(":")
                if candidate not in skip_names and "Apple" not in candidate and "Chipset" not in candidate:
                    # New display section
                    current_section = {"name": candidate, "lines": []}
                    sections.append(current_section)
                    continue
            if current_section is not None:
                current_section["lines"].append(stripped)

        # Second pass: extract attributes from each section
        for sec in sections:
            width, height, is_main = 0, 0, False
            for attr in sec["lines"]:
                if "Main Display: Yes" in attr:
                    is_main = True
                if "Resolution:" in attr:
                    res_part = attr.split(":")[-1].strip().split("(")[0].strip()
                    wh = res_part.split(" x ")
                    if len(wh) == 2:
                        try:
                            width, height = int(wh[0].strip()), int(wh[1].strip())
                        except ValueError:
                            pass
            if width > 0 and height > 0:
                displays_raw.append({"name": sec["name"], "width": width, "height": height, "main": is_main})

    # Get actual screen positions by probing window coordinates
    # The Finder desktop bounds give us the total spanning rect
    bounds_result = _run_applescript('tell application "Finder" to get bounds of window of desktop')
    total_x1, total_y1, total_x2, total_y2 = 0, 0, 3840, 1080
    if bounds_result["success"]:
        try:
            parts = [int(p.strip()) for p in bounds_result["content"].split(",")]
            total_x1, total_y1, total_x2, total_y2 = parts
        except (ValueError, IndexError):
            pass

    # Assign positions: main display is at x=0, others are offset
    displays = []
    if len(displays_raw) == 1:
        d = displays_raw[0]
        displays.append({**d, "x": 0, "y": 0, "id": 1, "role": "main"})
    elif len(displays_raw) >= 2:
        # Find main display
        main_idx = next((i for i, d in enumerate(displays_raw) if d["main"]), 0)

        # Main is at x=0. Non-main displays fill the remaining space.
        # total bounds tell us the full span
        # e.g., total_x1=-1920 means a screen is 1920px to the left of main
        remaining_x = total_x1  # Start from leftmost edge
        idx = 0
        for i, d in enumerate(displays_raw):
            if d["main"]:
                displays.append({**d, "x": 0, "y": 0, "id": i + 1})
            else:
                # Calculate position relative to total bounds
                if remaining_x < 0:
                    displays.append({**d, "x": remaining_x, "y": 0, "id": i + 1})
                    remaining_x += d["width"]
                else:
                    # Display is to the right of main
                    right_x = total_x2 - d["width"]
                    displays.append({**d, "x": right_x, "y": 0, "id": i + 1})
                idx += 1

    # Sort by x position (leftmost first)
    displays.sort(key=lambda d: d["x"])

    # Merge names from System Events if available
    if name_result["success"]:
        se_displays = []
        for line in name_result["content"].strip().split("\n"):
            if "|" in line:
                parts = line.strip().split("|")
                se_displays.append({"name": parts[0], "id": int(parts[1])})
        # Match by name
        for se in se_displays:
            for d in displays:
                if d["name"] == se["name"]:
                    d["id"] = se["id"]

    return displays


def assign_screens(displays, config=None):
    """Assign roles to screens based on config and position.

    Roles: 'tars' (TARS browser/dashboard), 'user' (your stuff), 'dev' (VS Code/shared)

    Default assignment (left external = TARS):
    - 3 screens: left=tars, center=dev, right=user
    - 2 screens: left=tars, right=dev (user shares dev screen)
    - 1 screen: everything on one screen
    """
    tars_screen_pref = "left"  # Default
    if config:
        tars_screen_pref = config.get("environment", {}).get("tars_screen", "left")

    n = len(displays)
    if n == 0:
        return {}

    if n == 1:
        displays[0]["role"] = "all"
        return {
            "tars": displays[0],
            "dev": displays[0],
            "user": displays[0],
        }

    if n == 2:
        if tars_screen_pref == "left":
            displays[0]["role"] = "tars"
            displays[1]["role"] = "dev"
        else:
            displays[0]["role"] = "dev"
            displays[1]["role"] = "tars"
        return {
            "tars": next(d for d in displays if d["role"] == "tars"),
            "dev": next(d for d in displays if d["role"] == "dev"),
            "user": next(d for d in displays if d["role"] == "dev"),  # Share with dev
        }

    # 3+ screens
    if tars_screen_pref == "left":
        displays[0]["role"] = "tars"
        displays[-1]["role"] = "user"
        # Middle screen(s) = dev
        for d in displays[1:-1]:
            d["role"] = "dev"
        return {
            "tars": displays[0],
            "dev": displays[1],
            "user": displays[-1],
        }
    else:
        displays[-1]["role"] = "tars"
        displays[0]["role"] = "user"
        for d in displays[1:-1]:
            d["role"] = "dev"
        return {
            "tars": displays[-1],
            "dev": displays[1] if n > 2 else displays[0],
            "user": displays[0],
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2. APP MANAGEMENT (close clutter, open essentials)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Apps that TARS does NOT need — close on startup
CLUTTER_APPS = [
    "System Settings", "System Preferences",
    "App Store", "Preview", "TextEdit", "Notes",
    "Calculator", "Photo Booth", "Stickies",
    "FaceTime", "Maps", "News", "Stocks",
    "Home", "TV", "Music", "Podcasts", "Books",
    "Reminders",  # TARS uses AppleScript directly, not the GUI
]

# Apps that TARS needs running
ESSENTIAL_APPS = [
    "Messages",   # iMessage read/write
    "Mail",       # Email monitoring
]

# Apps to leave alone (never close, never open)
PROTECTED_APPS = [
    "Finder",     # macOS requires it
    "Code",       # VS Code — dev uses it, TARS uses it for code changes
    "Terminal",   # User might have terminals open
    "iTerm2",     # Alternative terminal
    "Activity Monitor",
    "Disk Utility",
    "Console",
]


def close_clutter(extra_close=None):
    """Close unnecessary apps that could interfere or cause confusion.

    Returns list of actions taken.
    """
    actions = []
    to_close = CLUTTER_APPS + (extra_close or [])

    # Get running apps first
    result = _run_applescript(
        'tell application "System Events" to get name of every process whose background only is false'
    )
    if not result["success"]:
        return [{"action": "detect_apps", "success": False, "detail": result["content"]}]

    running = [a.strip() for a in result["content"].split(",")]

    for app in to_close:
        if app in running and app not in PROTECTED_APPS:
            r = _run_applescript(f'tell application "{app}" to quit')
            actions.append({
                "action": "close",
                "app": app,
                "success": r["success"],
                "detail": r.get("content", ""),
            })

    # Close all Finder windows (but keep Finder running)
    r = _run_applescript('tell application "Finder" to close every window')
    actions.append({
        "action": "close_finder_windows",
        "app": "Finder",
        "success": r["success"],
        "detail": "Closed all Finder windows",
    })

    return actions


def open_essentials(extra_open=None):
    """Open apps that TARS needs to function.

    Opens them hidden (no focus steal) where possible.
    Returns list of actions taken.
    """
    actions = []
    to_open = ESSENTIAL_APPS + (extra_open or [])

    # Get running apps
    result = _run_applescript(
        'tell application "System Events" to get name of every process whose background only is false'
    )
    running = []
    if result["success"]:
        running = [a.strip() for a in result["content"].split(",")]

    for app in to_open:
        if app not in running:
            # Open hidden — launch without activating
            r = _run_applescript(f'''
            tell application "{app}" to launch
            delay 1
            tell application "System Events" to set visible of process "{app}" to false
            ''')
            actions.append({
                "action": "open_hidden",
                "app": app,
                "success": r["success"],
                "detail": f"Launched {app} (hidden)",
            })
        else:
            # Already running — just hide it
            _run_applescript(f'tell application "System Events" to set visible of process "{app}" to false')
            actions.append({
                "action": "already_running",
                "app": app,
                "success": True,
                "detail": f"{app} already running (hidden)",
            })

    return actions


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3. WINDOW ARRANGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def arrange_windows(screen_map):
    """Move app windows to their assigned screens.

    screen_map: dict from assign_screens() with 'tars', 'dev', 'user' keys.
    """
    actions = []
    tars_screen = screen_map.get("tars", {})
    dev_screen = screen_map.get("dev", {})

    # Window placement rules:
    # - Chrome (TARS profile) → TARS screen, fullscreen
    # - Dashboard browser → TARS screen (if we open it)
    # - VS Code → Dev screen, fullscreen
    # - Messages → Dev screen, hidden
    # - Mail → Dev screen, hidden
    # - Microsoft Outlook → Dev screen (if running)

    placements = {
        "Google Chrome": {"screen": tars_screen, "maximize": True},
        "Code":          {"screen": dev_screen, "maximize": True},
    }

    for app_name, cfg in placements.items():
        screen = cfg["screen"]
        if not screen:
            continue

        sx = screen.get("x", 0)
        sy = screen.get("y", 0)
        sw = screen.get("width", 1920)
        sh = screen.get("height", 1080)
        menu_bar = 25  # macOS menu bar height

        if cfg.get("maximize"):
            # Move and resize to fill the screen
            script = f'''
            tell application "System Events"
                try
                    tell process "{app_name}"
                        set position of first window to {{{sx}, {sy + menu_bar}}}
                        set size of first window to {{{sw}, {sh - menu_bar}}}
                    end tell
                end try
            end tell
            '''
        else:
            script = f'''
            tell application "System Events"
                try
                    tell process "{app_name}"
                        set position of first window to {{{sx}, {sy + menu_bar}}}
                    end tell
                end try
            end tell
            '''

        r = _run_applescript(script)
        actions.append({
            "action": "arrange",
            "app": app_name,
            "screen": screen.get("name", "?"),
            "position": f"({sx}, {sy + menu_bar})",
            "success": r["success"],
        })

    return actions


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  4. DO NOT DISTURB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def enable_dnd():
    """Enable Do Not Disturb / Focus mode to prevent notification popups.

    Uses macOS Focus mode via shortcuts. Falls back to notification center.
    """
    # Try using the `shortcuts` CLI (macOS 12+) to toggle DND
    result = _run_cmd(["shortcuts", "run", "Do Not Disturb"])
    if result["success"]:
        return {"success": True, "content": "Do Not Disturb enabled via Shortcuts"}

    # Fallback: use AppleScript to toggle via Control Center
    # This clicks the DND button in the menu bar
    script = '''
    tell application "System Events"
        try
            -- Open Control Center
            tell process "ControlCenter"
                click menu bar item "Focus" of menu bar 1
                delay 0.5
                -- Click "Do Not Disturb" if not already on
                click button "Do Not Disturb" of group 1 of window "Control Center"
            end tell
            return "Do Not Disturb toggled"
        on error errMsg
            return "DND toggle failed: " & errMsg
        end try
    end tell
    '''
    result = _run_applescript(script)
    return result


def disable_dnd():
    """Disable Do Not Disturb / Focus mode."""
    result = _run_cmd(["shortcuts", "run", "Do Not Disturb Off"])
    if result["success"]:
        return {"success": True, "content": "Do Not Disturb disabled"}
    return {"success": False, "error": True, "content": "Could not disable DND"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  5. CLIPBOARD GUARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_saved_clipboard = None


def clipboard_save():
    """Save current clipboard contents before TARS operations."""
    global _saved_clipboard
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
        _saved_clipboard = result.stdout  # Keep as bytes to preserve encoding
        return {"success": True, "content": f"Clipboard saved ({len(_saved_clipboard)} bytes)"}
    except Exception as e:
        _saved_clipboard = None
        return {"success": False, "error": True, "content": f"Clipboard save failed: {e}"}


def clipboard_restore():
    """Restore clipboard contents after TARS operations."""
    global _saved_clipboard
    if _saved_clipboard is None:
        return {"success": True, "content": "No clipboard to restore"}
    try:
        subprocess.run(["pbcopy"], input=_saved_clipboard, capture_output=True, timeout=5)
        content_len = len(_saved_clipboard)
        _saved_clipboard = None
        return {"success": True, "content": f"Clipboard restored ({content_len} bytes)"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Clipboard restore failed: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  6. FOCUS GUARD (prevent focus stealing)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_previous_frontmost = None


def focus_save():
    """Record which app is currently frontmost (before TARS steals focus)."""
    global _previous_frontmost
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    result = _run_applescript(script)
    if result["success"]:
        _previous_frontmost = result["content"]
        return {"success": True, "content": f"Saved focus: {_previous_frontmost}"}
    return result


def focus_restore():
    """Restore focus to the app that was frontmost before TARS activated something."""
    global _previous_frontmost
    if not _previous_frontmost:
        return {"success": True, "content": "No previous focus to restore"}

    app = _previous_frontmost
    _previous_frontmost = None

    # Use System Events to bring it to front without the jarring activate animation
    script = f'''
    tell application "System Events"
        set frontmost of process "{app}" to true
    end tell
    '''
    result = _run_applescript(script)
    if result["success"]:
        result["content"] = f"Focus restored to {app}"
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  7. CHROME MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def launch_tars_chrome(screen=None, port=9222):
    """Launch Chrome with TARS profile and CDP, positioned on the TARS screen.

    If Chrome Canary is available, prefer it for complete isolation.
    Otherwise uses regular Chrome with the TARS-specific profile.
    """
    # Check available Chrome variants
    canary_path = "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if os.path.exists(canary_path):
        browser_path = canary_path
        browser_name = "Google Chrome Canary"
        data_dir = os.path.join(os.path.expanduser("~"), ".tars_canary_profile")
    else:
        browser_path = chrome_path
        browser_name = "Google Chrome"
        data_dir = os.path.join(os.path.expanduser("~"), ".tars_chrome_profile")

    os.makedirs(data_dir, exist_ok=True)

    # Check if already running with debug port
    try:
        import urllib.request
        url = f"http://localhost:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as r:
            version_info = json.loads(r.read())
            log.info(f"  Chrome CDP already running: {version_info.get('Browser', '?')}")
            # Just move the window to the right screen
            if screen:
                _move_chrome_to_screen(browser_name, screen)
            return {"success": True, "content": f"Chrome CDP already running on :{port}", "browser": browser_name}
    except Exception:
        pass

    # Kill any existing Chrome that doesn't have debug port
    # (only if using regular Chrome, not Canary)
    if browser_name == "Google Chrome":
        _run_applescript(f'tell application "{browser_name}" to quit')
        time.sleep(2)

    # Launch with CDP
    cmd = [
        browser_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={data_dir}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    # Position Chrome window on TARS screen at launch
    if screen:
        x = screen.get("x", 0)
        y = screen.get("y", 0)
        w = screen.get("width", 1920)
        h = screen.get("height", 1080) - 25
        cmd.extend([f"--window-position={x},{y + 25}", f"--window-size={w},{h}"])

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info(f"  Launched {browser_name} with CDP on :{port}")

    # Wait for CDP to be ready
    for i in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            url = f"http://localhost:{port}/json/version"
            with urllib.request.urlopen(url, timeout=2):
                break
        except Exception:
            continue

    # Move to TARS screen after launch
    if screen:
        time.sleep(1)
        _move_chrome_to_screen(browser_name, screen)

    return {"success": True, "content": f"Launched {browser_name} on TARS screen", "browser": browser_name}


def _move_chrome_to_screen(browser_name, screen):
    """Move Chrome window to the specified screen, maximized."""
    sx = screen.get("x", 0)
    sy = screen.get("y", 0)
    sw = screen.get("width", 1920)
    sh = screen.get("height", 1080)
    menu_bar = 25

    script = f'''
    tell application "System Events"
        try
            tell process "{browser_name}"
                set position of first window to {{{sx}, {sy + menu_bar}}}
                set size of first window to {{{sw}, {sh - menu_bar}}}
            end tell
        end try
    end tell
    '''
    _run_applescript(script)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  8. PORT CLEANUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_ports_free(ports=None):
    """Make sure TARS ports (8420, 8421) are available.

    Kills anything blocking them EXCEPT our own process tree
    (so TARS doesn't kill its own server).
    """
    if ports is None:
        ports = [8420, 8421]

    my_pid = str(os.getpid())
    # Also protect parent PID (in case we're called from a child thread)
    my_ppid = str(os.getppid())
    protected = {my_pid, my_ppid}

    actions = []
    for port in ports:
        result = _run_cmd(["lsof", "-ti", f":{port}"])
        if result["success"] and result["content"].strip():
            pids = result["content"].strip().split("\n")
            for pid in pids:
                pid = pid.strip()
                if pid in protected:
                    log.debug(f"  Port {port}: PID {pid} is our own process — skipping")
                    continue
                _run_cmd(["kill", "-9", pid])
                actions.append(f"Killed PID {pid} on port {port}")

    if actions:
        time.sleep(1)  # Let ports release
    return actions


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  9. SYSTEM CHECKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def verify_services():
    """Verify critical services are available.

    Returns dict with status of each service.
    """
    checks = {}

    # Wi-Fi connected (auto-detect interface — en0 or en1)
    wifi_interface = "en0"
    iface_detect = _run_cmd(["networksetup", "-listallhardwareports"])
    if iface_detect["success"]:
        lines_iface = iface_detect["content"].split("\n")
        for j, ln in enumerate(lines_iface):
            if "Wi-Fi" in ln and j + 1 < len(lines_iface):
                dev_line = lines_iface[j + 1]
                if "Device:" in dev_line:
                    wifi_interface = dev_line.split("Device:")[-1].strip()
                    break
    wifi = _run_cmd(["/usr/sbin/networksetup", "-getairportnetwork", wifi_interface])
    wifi_ok = wifi["success"] and "not associated" not in wifi["content"].lower()
    wifi_detail = wifi.get("content", "unknown")

    # If Wi-Fi is off, check if we have internet via Ethernet
    if not wifi_ok:
        net_check = _run_cmd(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3", "https://www.google.com"])
        if net_check["success"] and net_check["content"].strip() in ("200", "301", "302"):
            wifi_ok = True
            wifi_detail = "Connected via Ethernet"

    checks["network"] = {
        "ok": wifi_ok,
        "detail": wifi_detail,
    }

    # Disk space (warn if < 5GB)
    disk = _run_cmd(["df", "-h", "/"])
    checks["disk"] = {"ok": True, "detail": "OK"}
    if disk["success"]:
        lines = disk["content"].split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                avail = parts[3]
                checks["disk"]["detail"] = f"{avail} free"
                # Parse available space
                try:
                    num = float(avail.rstrip("GgMmTt"))
                    unit = avail[-2:].upper() if len(avail) > 1 else "G"
                    if "M" in unit or (num < 5 and "G" in unit):
                        checks["disk"]["ok"] = False
                        checks["disk"]["detail"] = f"LOW DISK: {avail} free"
                except ValueError:
                    pass

    # Chrome CDP port
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:9222/json/version", timeout=2) as r:
            version = json.loads(r.read())
            checks["chrome_cdp"] = {"ok": True, "detail": version.get("Browser", "Chrome")}
    except Exception:
        checks["chrome_cdp"] = {"ok": False, "detail": "CDP not available (will launch on first browser task)"}

    # Accessibility permissions
    ax_check = _run_applescript('''
    tell application "System Events"
        try
            get name of first process whose frontmost is true
            return "granted"
        on error
            return "denied"
        end try
    end tell
    ''')
    checks["accessibility"] = {
        "ok": ax_check["success"] and "granted" in ax_check.get("content", ""),
        "detail": "Accessibility permissions " + ("granted" if ax_check["success"] else "DENIED — enable in System Settings > Privacy"),
    }

    return checks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MASTER: setup_environment()
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def setup_environment(config=None):
    """Full autonomous environment setup on TARS startup.

    This is the main entry point — called once during tars.py run().

    Steps:
    1. Detect displays and assign roles
    2. Close clutter apps
    3. Open essential apps (hidden)
    4. Clean up ports
    5. Launch Chrome with CDP on TARS screen
    6. Arrange windows to assigned screens
    7. Enable Do Not Disturb
    8. Verify services
    9. Set volume to low

    Returns a report dict with all actions taken.
    """
    report = {"steps": [], "screens": {}, "services": {}}

    # ── Step 1: Detect displays ──
    log.info("  🖥️  Detecting displays...")
    displays = detect_displays()
    screen_map = assign_screens(displays, config)
    report["screens"] = {
        "count": len(displays),
        "displays": displays,
        "assignments": {k: v.get("name", "?") for k, v in screen_map.items()},
    }
    event_bus.emit("environment_setup", {
        "step": "displays",
        "detail": f"{len(displays)} displays detected",
        "assignments": report["screens"]["assignments"],
    })

    if len(displays) >= 2:
        tars_name = screen_map.get("tars", {}).get("name", "?")
        dev_name = screen_map.get("dev", {}).get("name", "?")
        log.info(f"     ├─ TARS screen: {tars_name} (left)")
        log.info(f"     └─ Dev screen: {dev_name} (main)")
    else:
        log.info(f"     └─ Single screen mode")

    report["steps"].append({"step": "displays", "ok": True, "detail": f"{len(displays)} displays"})

    # ── Step 2: Close clutter ──
    log.info("  🧹 Closing clutter apps...")
    close_actions = close_clutter()
    closed = [a["app"] for a in close_actions if a["success"] and a["action"] == "close"]
    if closed:
        log.info(f"     └─ Closed: {', '.join(closed)}")
    else:
        log.info(f"     └─ No clutter to close")
    report["steps"].append({"step": "close_clutter", "ok": True, "detail": f"Closed {len(closed)} apps", "closed": closed})
    event_bus.emit("environment_setup", {"step": "close_clutter", "detail": f"Closed {len(closed)} apps"})

    # ── Step 3: Open essentials ──
    log.info("  📱 Opening essential apps (hidden)...")
    open_actions = open_essentials()
    opened = [a["app"] for a in open_actions if a["success"]]
    log.info(f"     └─ Ready: {', '.join(opened)}")
    report["steps"].append({"step": "open_essentials", "ok": True, "detail": f"{', '.join(opened)}"})
    event_bus.emit("environment_setup", {"step": "open_essentials", "detail": f"Ready: {', '.join(opened)}"})

    # ── Step 4: Clean up ports ──
    port_actions = ensure_ports_free()
    if port_actions:
        log.info(f"  🔌 Freed ports: {', '.join(port_actions)}")
        report["steps"].append({"step": "ports", "ok": True, "detail": f"Freed {len(port_actions)} blocked ports"})
    else:
        report["steps"].append({"step": "ports", "ok": True, "detail": "Ports clear"})

    # ── Step 5: Launch Chrome on TARS screen ──
    tars_screen = screen_map.get("tars")
    log.info("  🌐 Launching Chrome with CDP on TARS screen...")
    chrome_result = launch_tars_chrome(screen=tars_screen)
    log.info(f"     └─ {chrome_result.get('content', '?')}")
    report["steps"].append({"step": "chrome", "ok": chrome_result["success"], "detail": chrome_result.get("content", "")})
    event_bus.emit("environment_setup", {"step": "chrome", "detail": chrome_result.get("content", "")})

    # ── Step 6: Arrange windows ──
    log.info("  📐 Arranging windows...")
    arrange_actions = arrange_windows(screen_map)
    arranged = [f"{a['app']}→{a['screen']}" for a in arrange_actions if a["success"]]
    if arranged:
        log.info(f"     └─ {', '.join(arranged)}")
    report["steps"].append({"step": "arrange", "ok": True, "detail": f"Arranged {len(arranged)} windows"})

    # ── Step 7: Do Not Disturb ──
    dnd_enabled = config.get("environment", {}).get("dnd", True) if config else True
    if dnd_enabled:
        log.info("  🔕 Enabling Do Not Disturb...")
        dnd_result = enable_dnd()
        log.info(f"     └─ {dnd_result.get('content', '?')}")
        report["steps"].append({"step": "dnd", "ok": dnd_result.get("success", False), "detail": dnd_result.get("content", "")})
    else:
        report["steps"].append({"step": "dnd", "ok": True, "detail": "Disabled in config"})

    # ── Step 8: Verify services ──
    log.info("  ✅ Verifying services...")
    services = verify_services()
    report["services"] = services
    all_ok = all(s["ok"] for s in services.values())
    for svc, info in services.items():
        icon = "✅" if info["ok"] else "⚠️"
        log.info(f"     {icon} {svc}: {info['detail']}")
    report["steps"].append({"step": "verify", "ok": all_ok, "detail": f"{sum(1 for s in services.values() if s['ok'])}/{len(services)} checks passed"})

    # ── Step 9: Set volume low ──
    target_volume = 15
    if config:
        target_volume = config.get("environment", {}).get("volume", 15)
    _run_applescript(f"set volume output volume {target_volume}")
    log.info(f"  🔊 Volume set to {target_volume}%")
    report["steps"].append({"step": "volume", "ok": True, "detail": f"Volume → {target_volume}%"})

    # ── Done ──
    total_steps = len(report["steps"])
    ok_steps = sum(1 for s in report["steps"] if s["ok"])
    log.info(f"\n  🏁 Environment ready — {ok_steps}/{total_steps} steps passed")

    event_bus.emit("environment_setup", {
        "step": "complete",
        "detail": f"{ok_steps}/{total_steps} steps passed",
        "screens": report["screens"],
        "services": {k: v["ok"] for k, v in services.items()},
    })

    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SHUTDOWN: cleanup_environment()
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cleanup_environment():
    """Cleanup on TARS shutdown.

    - Restore clipboard if saved
    - Restore focus
    - Disable DND
    - Restore volume
    """
    clipboard_restore()
    focus_restore()
    disable_dnd()
    # Restore volume to a reasonable level
    _run_applescript("set volume output volume 50")
    log.info("  🧹 Environment cleaned up")
