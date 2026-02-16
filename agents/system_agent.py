"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — System Agent: Full Mac Controller                ║
╠══════════════════════════════════════════════════════════════╣
║  Expert at COMPLETE macOS automation — apps, windows, mail,  ║
║  notes, calendar, reminders, contacts, clipboard, keychain,  ║
║  audio, display, Finder, Spotlight, OCR, accessibility,      ║
║  and system controls.                                        ║
║                                                              ║
║  Own LLM loop. Inherits from BaseAgent.                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import subprocess

from agents.base_agent import BaseAgent
from agents.agent_tools import (
    TOOL_OPEN_APP, TOOL_TYPE_TEXT, TOOL_KEY_PRESS, TOOL_CLICK,
    TOOL_SCREENSHOT, TOOL_FRONTMOST_APP, TOOL_APPLESCRIPT,
    TOOL_RUN_COMMAND, TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_LIST_DIR,
    TOOL_DONE, TOOL_STUCK,
    # Advanced Mac Control
    TOOL_QUIT_APP, TOOL_HIDE_APP, TOOL_GET_RUNNING_APPS,
    TOOL_RIGHT_CLICK, TOOL_DRAG,
    TOOL_GET_WINDOWS, TOOL_MOVE_WINDOW, TOOL_RESIZE_WINDOW,
    TOOL_TILE_WINDOW, TOOL_MINIMIZE_WINDOW, TOOL_CLOSE_WINDOW, TOOL_FULLSCREEN_WINDOW,
    TOOL_SET_VOLUME, TOOL_GET_VOLUME, TOOL_TOGGLE_MUTE,
    TOOL_CLIPBOARD_READ, TOOL_CLIPBOARD_WRITE,
    TOOL_NOTIFY, TOOL_SPOTLIGHT_SEARCH,
    TOOL_FINDER_REVEAL, TOOL_FINDER_TAG,
    TOOL_MAIL_READ, TOOL_MAIL_SEARCH, TOOL_MAIL_SEND, TOOL_MAIL_UNREAD,
    TOOL_NOTES_LIST, TOOL_NOTES_READ, TOOL_NOTES_CREATE, TOOL_NOTES_SEARCH,
    TOOL_CALENDAR_EVENTS, TOOL_CALENDAR_CREATE,
    TOOL_REMINDERS_LIST, TOOL_REMINDERS_CREATE, TOOL_REMINDERS_COMPLETE,
    TOOL_CONTACTS_SEARCH, TOOL_CONTACTS_GET,
    TOOL_SET_DARK_MODE, TOOL_OPEN_URL, TOOL_WIFI_TOGGLE, TOOL_LOCK_SCREEN,
    TOOL_GET_BATTERY, TOOL_OCR_SCREEN, TOOL_GET_UI_ELEMENTS,
    TOOL_GET_ENVIRONMENT, TOOL_PREPARE_ENVIRONMENT,
    TOOL_SIRI_SHORTCUT, TOOL_KEYCHAIN_STORE, TOOL_KEYCHAIN_READ,
)
from hands import mac_control as mac
from hands.terminal import run_terminal
from hands.file_manager import read_file, write_file, list_directory


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

SYSTEM_AGENT_PROMPT = """You are TARS System Agent — the world's most powerful macOS automation specialist. You have FULL CONTROL of the Mac — every app, every setting, every pixel.

## Your Capabilities (60+ tools)

### Apps & Windows
- Open, quit, hide any app. Get running apps list.
- Move, resize, tile (left/right/top/bottom/center/fullscreen), minimize, close windows.
- Get UI element tree of any app via Accessibility API.

### Input
- Type text, press any keyboard shortcut (Cmd+S, F5, media keys, etc.)
- Click, double-click, right-click, drag at any screen coordinate.

### Native Apps
- **Mail** — read inbox, search, send emails via Mail.app
- **Notes** — list, read, create, search Apple Notes
- **Calendar** — view events, create events
- **Reminders** — list, create, complete reminders
- **Contacts** — search, get full contact details

### System
- Volume (set/get/mute), dark mode toggle, brightness
- Wi-Fi toggle, battery status, disk space
- Lock screen, run Siri Shortcuts
- Clipboard read/write, native notifications
- Spotlight file search (mdfind)
- Finder: reveal files, add tags
- Keychain: store/read credentials securely

### Vision
- Screenshot any area of the screen
- OCR: extract text from screen/images via Apple Vision
- UI element tree: read buttons, fields, labels of any app

### Environment
- Full Mac snapshot (apps, volume, WiFi, battery, clipboard, etc.)
- Prepare environment (close/open apps, set volume, dark mode)

## Your Process
1. **Check state** — Use `frontmost_app`, `screenshot`, or `get_environment` to understand context
2. **Act precisely** — Use the right tool for each action
3. **Verify** — After each action, check the result (screenshot, frontmost_app, etc.)
4. **Adapt** — If something doesn't work, try alternatives (AppleScript, keyboard shortcut, etc.)

## Common Shortcuts
- Cmd+Space → Spotlight | Cmd+Tab → Switch apps | Cmd+Q → Quit
- Cmd+W → Close window | Cmd+N → New | Cmd+, → Preferences
- Cmd+Shift+. → Show hidden files | Ctrl+Cmd+Q → Lock screen

## Rules
1. Always check what app is active before typing/clicking
2. Wait after opening apps (they need time to launch)
3. Use AppleScript for complex automation
4. For email/notes/calendar, use the dedicated tools (faster + more reliable than GUI)
5. For file management, prefer shell commands over Finder GUI
6. NEVER run destructive commands without the task explicitly requiring it
7. Call `done` with a clear summary. Call `stuck` with what you tried.

## CRITICAL ANTI-HALLUCINATION RULES
- You can ONLY do things through your tools. If you didn't call a tool, it didn't happen.
- NEVER claim you completed a web task — you are NOT a browser agent.
- If a task requires browsing the web, call `stuck` immediately.
- Your `done(summary)` must describe SPECIFIC actions with SPECIFIC tools.
- NEVER fabricate results. If you can't do it, call `stuck`.
"""


class SystemAgent(BaseAgent):
    """Autonomous system agent — controls macOS with 60+ tools."""

    @property
    def agent_name(self):
        return "System Agent"

    @property
    def agent_emoji(self):
        return "⚙️"

    @property
    def system_prompt(self):
        return SYSTEM_AGENT_PROMPT

    @property
    def tools(self):
        return [
            # Core
            TOOL_OPEN_APP, TOOL_TYPE_TEXT, TOOL_KEY_PRESS, TOOL_CLICK,
            TOOL_SCREENSHOT, TOOL_FRONTMOST_APP, TOOL_APPLESCRIPT,
            TOOL_RUN_COMMAND, TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_LIST_DIR,
            TOOL_DONE, TOOL_STUCK,
            # Advanced Mac
            TOOL_QUIT_APP, TOOL_HIDE_APP, TOOL_GET_RUNNING_APPS,
            TOOL_RIGHT_CLICK, TOOL_DRAG,
            TOOL_GET_WINDOWS, TOOL_MOVE_WINDOW, TOOL_RESIZE_WINDOW,
            TOOL_TILE_WINDOW, TOOL_MINIMIZE_WINDOW, TOOL_CLOSE_WINDOW, TOOL_FULLSCREEN_WINDOW,
            TOOL_SET_VOLUME, TOOL_GET_VOLUME, TOOL_TOGGLE_MUTE,
            TOOL_CLIPBOARD_READ, TOOL_CLIPBOARD_WRITE,
            TOOL_NOTIFY, TOOL_SPOTLIGHT_SEARCH,
            TOOL_FINDER_REVEAL, TOOL_FINDER_TAG,
            TOOL_MAIL_READ, TOOL_MAIL_SEARCH, TOOL_MAIL_SEND, TOOL_MAIL_UNREAD,
            TOOL_NOTES_LIST, TOOL_NOTES_READ, TOOL_NOTES_CREATE, TOOL_NOTES_SEARCH,
            TOOL_CALENDAR_EVENTS, TOOL_CALENDAR_CREATE,
            TOOL_REMINDERS_LIST, TOOL_REMINDERS_CREATE, TOOL_REMINDERS_COMPLETE,
            TOOL_CONTACTS_SEARCH, TOOL_CONTACTS_GET,
            TOOL_SET_DARK_MODE, TOOL_OPEN_URL, TOOL_WIFI_TOGGLE, TOOL_LOCK_SCREEN,
            TOOL_GET_BATTERY, TOOL_OCR_SCREEN, TOOL_GET_UI_ELEMENTS,
            TOOL_GET_ENVIRONMENT, TOOL_PREPARE_ENVIRONMENT,
            TOOL_SIRI_SHORTCUT, TOOL_KEYCHAIN_STORE, TOOL_KEYCHAIN_READ,
        ]

    def _dispatch(self, name, inp):
        """Route system tool calls to mac_control functions."""
        try:
            # ── Core Tools ──
            if name == "open_app":
                return self._r(mac.open_app(inp["app_name"]))
            elif name == "type_text":
                return self._r(mac.type_text(inp["text"]))
            elif name == "key_press":
                return self._r(mac.key_press(inp["keys"]))
            elif name == "click":
                return self._r(mac.click(inp["x"], inp["y"], inp.get("double_click", False)))
            elif name == "screenshot":
                return self._r(mac.take_screenshot())
            elif name == "frontmost_app":
                return self._r(mac.get_frontmost_app())
            elif name == "applescript":
                return self._run_applescript(inp["code"])

            # ── App Control ──
            elif name == "quit_app":
                return self._r(mac.quit_app(inp["app_name"], inp.get("force", False)))
            elif name == "hide_app":
                return self._r(mac.hide_app(inp["app_name"]))
            elif name == "get_running_apps":
                return self._r(mac.get_running_apps())

            # ── Mouse ──
            elif name == "right_click":
                return self._r(mac.right_click(inp["x"], inp["y"]))
            elif name == "drag":
                return self._r(mac.drag(inp["x1"], inp["y1"], inp["x2"], inp["y2"]))

            # ── Window Management ──
            elif name == "get_windows":
                return self._r(mac.get_windows(inp.get("app_name")))
            elif name == "move_window":
                return self._r(mac.move_window(inp["x"], inp["y"], inp.get("app_name")))
            elif name == "resize_window":
                return self._r(mac.resize_window(inp["width"], inp["height"], inp.get("app_name")))
            elif name == "tile_window":
                return self._r(mac.tile_window(inp["position"]))
            elif name == "minimize_window":
                return self._r(mac.minimize_window(inp.get("app_name")))
            elif name == "close_window":
                return self._r(mac.close_window(inp.get("app_name")))
            elif name == "fullscreen_window":
                return self._r(mac.fullscreen_window())

            # ── Audio ──
            elif name == "set_volume":
                return self._r(mac.set_volume(inp["level"]))
            elif name == "get_volume":
                return self._r(mac.get_volume())
            elif name == "toggle_mute":
                return self._r(mac.toggle_mute())

            # ── Clipboard ──
            elif name == "clipboard_read":
                return self._r(mac.clipboard_read())
            elif name == "clipboard_write":
                return self._r(mac.clipboard_write(inp["text"]))

            # ── Notifications ──
            elif name == "notify":
                return self._r(mac.notify(inp["message"], inp.get("title", "TARS"), inp.get("subtitle", "")))

            # ── Spotlight ──
            elif name == "spotlight_search":
                return self._r(mac.spotlight_search(inp["query"], inp.get("folder"), inp.get("max_results", 20)))

            # ── Finder ──
            elif name == "finder_reveal":
                return self._r(mac.finder_reveal(inp["path"]))
            elif name == "finder_tag":
                return self._r(mac.finder_tag(inp["path"], inp["tag_name"]))

            # ── Mail ──
            elif name == "mail_read":
                if inp.get("index"):
                    return self._r(mac.mail_read_message(inp["index"]))
                return self._r(mac.mail_read_inbox(inp.get("count", 5)))
            elif name == "mail_search":
                return self._r(mac.mail_search(inp["keyword"]))
            elif name == "mail_send":
                return self._r(mac.mail_send(inp["to"], inp["subject"], inp["body"]))
            elif name == "mail_unread":
                return self._r(mac.mail_unread_count())

            # ── Notes ──
            elif name == "notes_list":
                return self._r(mac.notes_list())
            elif name == "notes_read":
                return self._r(mac.notes_read(inp["note_name"]))
            elif name == "notes_create":
                return self._r(mac.notes_create(inp["title"], inp["body"], inp.get("folder", "Notes")))
            elif name == "notes_search":
                return self._r(mac.notes_search(inp["query"]))

            # ── Calendar ──
            elif name == "calendar_events":
                return self._r(mac.calendar_events(inp.get("calendar_name"), inp.get("days_ahead", 7)))
            elif name == "calendar_create":
                return self._r(mac.calendar_create_event(inp["title"], inp["start_date"], inp["end_date"], inp.get("calendar_name", "Calendar")))

            # ── Reminders ──
            elif name == "reminders_list":
                return self._r(mac.reminders_list(inp.get("list_name")))
            elif name == "reminders_create":
                return self._r(mac.reminders_create(inp["title"], inp.get("list_name", "Reminders"), inp.get("due_date"), inp.get("notes")))
            elif name == "reminders_complete":
                return self._r(mac.reminders_complete(inp["title"], inp.get("list_name", "Reminders")))

            # ── Contacts ──
            elif name == "contacts_search":
                return self._r(mac.contacts_search(inp["query"]))
            elif name == "contacts_get":
                return self._r(mac.contacts_get(inp["name"]))

            # ── System Controls ──
            elif name == "set_dark_mode":
                return self._r(mac.set_dark_mode(inp["enabled"]))
            elif name == "open_url":
                return self._r(mac.open_url(inp["url"]))
            elif name == "wifi_toggle":
                return self._r(mac.wifi_toggle(inp["on"]))
            elif name == "lock_screen":
                return self._r(mac.lock_screen())
            elif name == "get_battery":
                return self._r(mac.get_battery())

            # ── OCR & Accessibility ──
            elif name == "ocr_screen":
                region = None
                if inp.get("x") is not None and inp.get("y") is not None and inp.get("w") and inp.get("h"):
                    region = (inp["x"], inp["y"], inp["w"], inp["h"])
                return self._r(mac.ocr_screen(region))
            elif name == "get_ui_elements":
                return self._r(mac.get_ui_elements(inp.get("app_name"), inp.get("max_depth", 3)))

            # ── Environment ──
            elif name == "get_environment":
                return self._r(mac.get_environment_snapshot())
            elif name == "prepare_environment":
                return self._r(mac.prepare_environment(
                    close_apps=inp.get("close_apps"),
                    open_apps=inp.get("open_apps"),
                    volume=inp.get("volume"),
                    dark_mode=inp.get("dark_mode"),
                ))

            # ── Siri & Keychain ──
            elif name == "siri_shortcut":
                return self._r(mac.run_siri_shortcut(inp["shortcut_name"], inp.get("input_text")))
            elif name == "keychain_store":
                return self._r(mac.keychain_store(inp["service"], inp["account"], inp["password"]))
            elif name == "keychain_read":
                return self._r(mac.keychain_read(inp["service"], inp["account"]))

            # ── File & Terminal (unchanged) ──
            elif name == "run_command":
                result = run_terminal(inp["command"], timeout=inp.get("timeout", 60))
                return result.get("content", str(result))
            elif name == "read_file":
                result = read_file(inp["path"])
                return result.get("content", str(result))
            elif name == "write_file":
                result = write_file(inp["path"], inp["content"])
                return result.get("content", str(result))
            elif name == "list_dir":
                result = list_directory(inp["path"])
                return result.get("content", str(result))

            return f"Unknown system tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _r(self, result):
        """Extract content from a mac_control result dict."""
        if isinstance(result, dict):
            return result.get("content", str(result))
        return str(result)

    def _run_applescript(self, code):
        """Run raw AppleScript and return output."""
        try:
            result = subprocess.run(
                ["osascript", "-e", code],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip() or "(no output — script ran successfully)"
            else:
                return f"AppleScript error: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return "AppleScript timed out after 30s"
        except Exception as e:
            return f"AppleScript error: {e}"
