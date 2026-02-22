"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Screen Agent: Vision-Driven Mac Control          ║
╠══════════════════════════════════════════════════════════════╣
║  Controls the Mac like a human — SEES the screen through     ║
║  screenshots, CLICKS on what it sees, TYPES with keyboard.   ║
║                                                              ║
║  Uses screenshots + Vision LLM (Gemini) to understand UI.   ║
║  Uses native macOS input (cliclick/System Events) to act.    ║
║  Works on ANY app — Chrome, Safari, Finder, Settings, etc.   ║
║                                                              ║
║  No DOM parsing. No CSS selectors. No CDP.                   ║
║  Pure visual control — exactly like a human at the screen.   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import re
import time
import json
import base64
import logging
import tempfile
import subprocess

from agents.base_agent import BaseAgent
from agents.agent_tools import TOOL_DONE, TOOL_STUCK
from hands import mac_control

logger = logging.getLogger("TARS")


# ─────────────────────────────────────────────
#  Screen Utilities
# ─────────────────────────────────────────────


def _get_focused_display():
    """Get the display number and x-offset of the display containing the frontmost window.

    On multi-monitor setups, screencapture -x captures only the main display.
    If the frontmost app is on a secondary display, we need -D <n> to capture it.

    Returns (display_number, x_offset) where:
        - display_number: 1-based display number for screencapture -D, or None for default
        - x_offset: the x coordinate offset of the display in the virtual screen space
    """
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get position of first window of (first process whose frontmost is true)'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(", ")
            x = int(parts[0])
            # Main display is at x=0. Secondary display to the left has x < 0.
            # screencapture -D 1 = main, -D 2 = next, etc.
            if x < 0:
                # Determine the display origin — try to get exact offset from NSScreen
                try:
                    from AppKit import NSScreen
                    for screen in NSScreen.screens():
                        frame = screen.frame()
                        sx = int(frame.origin.x)
                        if sx < 0 and x >= sx and x < sx + int(frame.size.width):
                            return 2, sx
                except ImportError:
                    pass
                # Fallback: assume display is 1920 wide, offset is -1920
                return 2, -1920
    except Exception:
        pass
    return None, 0  # Use default (main display), no offset

def _get_screen_size():
    """
    Get screen size in points (the coordinate system macOS uses for mouse events).
    Returns (width, height) in screen points.
    """
    try:
        from AppKit import NSScreen
        frame = NSScreen.mainScreen().frame()
        return int(frame.size.width), int(frame.size.height)
    except ImportError:
        pass

    # Fallback: AppleScript
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to get bounds of window of desktop'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = [int(p.strip()) for p in result.stdout.strip().split(",")]
            return parts[2], parts[3]
    except Exception:
        pass

    return 1440, 900  # Safe default for MacBook Pro


def _get_retina_scale():
    """Get the Retina scale factor (usually 2.0 on Retina, 1.0 on non-Retina)."""
    try:
        from AppKit import NSScreen
        return int(NSScreen.mainScreen().backingScaleFactor())
    except ImportError:
        pass
    # Heuristic: check screenshot resolution vs screen size
    return 2  # Most modern Macs are Retina


def _take_screenshot_for_vision():
    """
    Take a screenshot optimized for vision LLM consumption.

    The image is resized to match screen POINT coordinates, so the LLM's
    coordinate output maps directly to screen click coordinates.
    No conversion needed — what the LLM sees IS where to click.

    Returns dict with:
        - image_base64: base64-encoded JPEG image
        - screen_width: screen width in points
        - screen_height: screen height in points
        - display_x_offset: x offset for coordinate mapping (0 for main display)
        - error: set if something went wrong
    """
    screen_w, screen_h = _get_screen_size()

    # 1. Capture screenshot at native resolution
    #    Detect which display has the focused app and capture THAT display
    ts = int(time.time() * 1000)
    png_path = os.path.join(tempfile.gettempdir(), f"tars_screen_{ts}.png")
    try:
        cmd = ["screencapture", "-x"]
        display_num, display_x_offset = _get_focused_display()
        if display_num:
            cmd.extend(["-D", str(display_num)])
        cmd.append(png_path)
        subprocess.run(cmd, timeout=10, capture_output=True)
    except Exception as e:
        return {"error": f"Screenshot failed: {e}"}

    if not os.path.exists(png_path):
        return {"error": "Screenshot file not created"}

    # 2. Resize to screen point dimensions + convert to JPEG for smaller size
    #    This makes the image coordinate system match screen coordinates exactly.
    jpg_path = png_path.replace(".png", ".jpg")
    try:
        subprocess.run([
            "sips",
            "--resampleWidth", str(screen_w),
            "--setProperty", "format", "jpeg",
            "--setProperty", "formatOptions", "80",
            png_path,
            "--out", jpg_path,
        ], capture_output=True, timeout=10)
    except Exception:
        # Fallback: use PNG as-is
        jpg_path = png_path

    # 3. Encode as base64 for LLM
    target = jpg_path if os.path.exists(jpg_path) else png_path
    with open(target, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    # 4. Get actual output dimensions for reference
    img_w, img_h = screen_w, screen_h
    try:
        result = subprocess.run(
            ["sips", "--getProperty", "pixelWidth", "--getProperty", "pixelHeight", target],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "pixelWidth" in line:
                    img_w = int(line.split(":")[-1].strip())
                elif "pixelHeight" in line:
                    img_h = int(line.split(":")[-1].strip())
    except Exception:
        pass

    # 5. Cleanup temp files
    for p in [png_path, jpg_path]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    return {
        "image_base64": image_b64,
        "screen_width": screen_w,
        "screen_height": screen_h,
        "image_width": img_w,
        "image_height": img_h,
        "display_x_offset": display_x_offset if display_num else 0,
        "mime_type": "image/jpeg",
    }


def _scroll_screen(direction="down", amount=3):
    """Scroll using native scroll wheel events."""
    try:
        from Quartz import (
            CGEventCreateScrollWheelEvent,
            CGEventPost,
            kCGScrollEventUnitLine,
            kCGHIDEventTap,
        )
        # Negative = scroll down, positive = scroll up
        delta = -amount if direction == "down" else amount
        event = CGEventCreateScrollWheelEvent(
            None, kCGScrollEventUnitLine, 1, delta
        )
        CGEventPost(kCGHIDEventTap, event)
        return f"Scrolled {direction} {amount} lines"
    except ImportError:
        # Fallback: keyboard-based scroll
        key = "pagedown" if direction == "down" else "pageup"
        mac_control.key_press(key)
        return f"Scrolled {direction} (keyboard fallback)"


# ─────────────────────────────────────────────
#  Screen Agent Tool Definitions
# ─────────────────────────────────────────────

SCREEN_TOOLS = [
    {
        "name": "screenshot",
        "description": (
            "Take a screenshot of the entire screen. You will SEE the actual screen as an image. "
            "The image coordinate system matches screen coordinates — when you see a button at position "
            "(x, y) in the image, click at those exact coordinates. "
            "ALWAYS do this first and after every action to verify what happened."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "click",
        "description": (
            "Click at screen coordinates (x, y). Look at the screenshot to determine where to click. "
            "Aim for the CENTER of buttons, links, and fields — not the edges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate (pixels from left edge)"},
                "y": {"type": "integer", "description": "Y coordinate (pixels from top edge)"},
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "double_click",
        "description": "Double-click at screen coordinates. Use for selecting words or opening files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "right_click",
        "description": "Right-click at screen coordinates. Opens context menus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "type_text",
        "description": (
            "Type text using the keyboard, character by character like a human. "
            "IMPORTANT: Click on a text field FIRST to focus it, then call type_text. "
            "To replace existing text: click the field, then key('command+a'), then type_text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "key",
        "description": (
            "Press a keyboard key or shortcut. "
            "Examples: 'return', 'tab', 'escape', 'space', 'backspace', 'delete', "
            "'up', 'down', 'left', 'right', "
            "'command+a' (select all), 'command+c' (copy), 'command+v' (paste), "
            "'command+z' (undo), 'command+s' (save), 'command+w' (close window), "
            "'command+q' (quit app), 'command+space' (Spotlight), 'command+tab' (switch app)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Key name or combo like 'command+a'"},
            },
            "required": ["keys"]
        }
    },
    {
        "name": "scroll",
        "description": "Scroll the screen at the current mouse position. Use to reveal content below/above the viewport.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                "amount": {"type": "integer", "description": "Lines to scroll (1-10, default 3)", "default": 3},
            }
        }
    },
    {
        "name": "move_mouse",
        "description": "Move mouse to coordinates without clicking. Useful for hovering over menus/tooltips.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "drag",
        "description": "Drag from one point to another. For drag-and-drop, slider adjustment, text selection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_x": {"type": "integer"}, "start_y": {"type": "integer"},
                "end_x": {"type": "integer"}, "end_y": {"type": "integer"},
            },
            "required": ["start_x", "start_y", "end_x", "end_y"]
        }
    },
    {
        "name": "wait",
        "description": "Wait for N seconds. Use after clicking buttons, submitting forms, or opening apps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "default": 2},
            }
        }
    },
    {
        "name": "open_app",
        "description": "Open a macOS application by name. Brings it to the foreground.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "App name: 'Google Chrome', 'Safari', 'Finder', 'System Settings', etc."},
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "read_screen",
        "description": (
            "OCR the screen — extract all visible text as a string. "
            "Use when you need to find specific text, read small/unclear text, "
            "or verify content that's hard to read from the screenshot image."
        ),
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "clipboard_read",
        "description": "Read the current clipboard contents. Use after Command+C to check what was copied.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "clipboard_write",
        "description": "Write text to the clipboard. Use before Command+V to paste specific text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to put on the clipboard"},
            },
            "required": ["text"]
        }
    },
    TOOL_DONE,
    TOOL_STUCK,
]


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

SCREEN_SYSTEM_PROMPT = """You are TARS Screen Agent — you control a Mac computer exactly like a human would. You SEE the screen through screenshots, and you act using real mouse clicks and keyboard typing.

## How You Work

You are looking at a real macOS screen. Every action you take is a REAL mouse click or keystroke at actual screen coordinates, exactly as if a human were sitting at the computer.

**Your cycle every step:**
1. 📸 **SCREENSHOT** → Take a screenshot to see what's on screen
2. 👁️ **ANALYZE** → What app is open? What buttons, fields, text do you see? Where exactly are they?
3. 🧠 **DECIDE** → What single action will advance my task?
4. 🖱️ **ACT** → Click at the coordinates, type text, or press keys
5. 📸 **VERIFY** → Screenshot again to confirm your action worked

## Coordinate System

The screenshot image matches the screen coordinate system exactly:
- **(0, 0)** is the **top-left corner** of the screen
- **X increases rightward** (left edge = 0, right edge = screen width)
- **Y increases downward** (top edge = 0, bottom edge = screen height)
- The macOS **menu bar** is at the very top (y ≈ 0-25)
- The **Dock** is usually at the bottom

When you see a button at a certain position in the screenshot, use those EXACT coordinates to click it. **Aim for the CENTER of clickable elements.**

## Your Tools

**Vision:**
- `screenshot` — See the screen. Returns an image. Do this FIRST and after every action.
- `read_screen` — OCR all text on screen (when screenshot text is unclear)

**Mouse:**
- `click(x, y)` — Left-click at coordinates. For buttons, links, checkboxes, menu items.
- `double_click(x, y)` — Double-click. For selecting words, opening files/folders.
- `right_click(x, y)` — Right-click. Opens context menus.
- `move_mouse(x, y)` — Hover without clicking. For dropdown menus, tooltips.
- `drag(start_x, start_y, end_x, end_y)` — Click-and-drag. For sliders, selections, file moves.

**Keyboard:**
- `type_text(text)` — Type text character by character. Always click a field first to focus it!
- `key(keys)` — Press key combos: 'return', 'tab', 'escape', 'command+a', 'command+c', 'command+v', 'backspace'

**Clipboard:**
- `clipboard_read` — Read clipboard contents (after Command+C)
- `clipboard_write(text)` — Write to clipboard (before Command+V)

**Other:**
- `scroll(direction, amount)` — Scroll up/down at current position
- `open_app(app_name)` — Launch/activate a macOS app
- `wait(seconds)` — Pause before next action

**Terminal:**
- `done(summary)` — Task complete. Provide evidence of what you accomplished.
- `stuck(reason)` — Can't proceed after genuine effort (10+ steps, 3+ approaches).

## Operating Rules

1. **ALWAYS SCREENSHOT FIRST** — You are completely blind without it. Take one before your first action and after every click/type to verify results.

2. **ONE ACTION AT A TIME** — Click ONE button, then screenshot. Type ONE field, then screenshot. Never batch 5 actions without checking between them.

3. **AIM FOR ELEMENT CENTERS** — When clicking a button that's 100px wide, click the center, not the edge. This prevents misclicks.

4. **CLICK BEFORE TYPING** — Text fields must be focused (clicked) before you can type into them. Always click the field first.

5. **CLEAR BEFORE REPLACING** — To replace text in a field: click it → key('command+a') → type_text('new text'). Don't just type and hope.

6. **WAIT AFTER ACTIONS** — After clicking buttons, submitting forms, or opening apps, wait 1-3 seconds for the UI to update before taking the next screenshot.

7. **READ WHAT YOU SEE** — If an error message appears, read it. If a dialog pops up, read it. React to what the screen shows.

8. **USE KEYBOARD SHORTCUTS** — They're faster and more reliable than clicking:
   - Tab → move between form fields
   - Return → submit/confirm
   - Escape → dismiss dialogs
   - Command+A → select all text in a field
   - Command+C/V → copy/paste

9. **SCROLL TO FIND** — If you don't see what you're looking for, scroll down. Forms often extend below the visible area.

10. **ADAPT TO WHAT YOU SEE** — Every screen is different. Don't assume layout. Look and react.

## Web Form Tips
- Click each input field before typing into it
- Use Tab to move between fields efficiently
- After filling a form, scroll down to check for more fields or a submit button
- Watch for inline error messages after clicking away from a field
- After submitting, wait 2-3s then screenshot to check the result

## macOS Tips
- Menu bar is at the top of screen (y ≈ 10-20)
- Click menu bar items to open menus, then click menu options
- Dock is at the bottom — click app icons to open/switch apps
- Command+Space opens Spotlight search (type to find anything)
- Command+Tab shows app switcher
- Red/yellow/green dots at top-left of windows = close/minimize/fullscreen

## Multiple Monitors
If the screen seems larger than expected, you may be on a multi-monitor setup. Focus on the primary display area.

## Important: You Are Not a Browser Agent
You don't have DOM access, CSS selectors, or JavaScript. You see PIXELS on a screen and control a MOUSE and KEYBOARD. Think visually — identify elements by their appearance and position, not by code."""


# ─────────────────────────────────────────────
#  Screen Agent Class
# ─────────────────────────────────────────────

class ScreenAgent(BaseAgent):
    """
    Vision-driven Mac control agent.

    Instead of parsing DOM elements or using CSS selectors, this agent:
    1. Takes screenshots → sends to vision LLM (Gemini)
    2. LLM analyzes what's on screen visually
    3. LLM decides where to click/type based on what it SEES
    4. Uses native macOS mouse/keyboard (cliclick, System Events) to act

    This is like Anthropic Computer Use — pure visual control.
    Works on ANY application, not just Chrome.
    Uses real OS-level input events that are indistinguishable from human input.
    """

    @property
    def agent_name(self):
        return "Screen Agent"

    @property
    def agent_emoji(self):
        return "🖥️"

    @property
    def _loop_detection_window(self):
        # screenshot→click→screenshot→click is normal workflow
        return 4

    @property
    def _loop_detection_repeats(self):
        return 4

    @property
    def system_prompt(self):
        return SCREEN_SYSTEM_PROMPT

    @property
    def tools(self):
        return SCREEN_TOOLS

    def _on_start(self, task):
        """Setup before agent loop starts."""
        self._task = task
        self._action_count = 0
        self._screenshots_taken = 0
        self._display_x_offset = 0  # Offset for multi-display coordinate mapping
        self._target_app = None  # Track which app we're controlling

        # Auto-detect and activate the target app from task text
        task_lower = task.lower()
        app_targets = [
            ("chrome", "Google Chrome"),
            ("browser", "Google Chrome"),
            ("http://", "Google Chrome"),
            ("https://", "Google Chrome"),
            ("safari", "Safari"),
            ("finder", "Finder"),
            ("system settings", "System Settings"),
            ("system preferences", "System Preferences"),
            ("terminal", "Terminal"),
            ("mail", "Mail"),
            ("notes", "Notes"),
            ("messages", "Messages"),
            ("calendar", "Calendar"),
            ("photos", "Photos"),
            ("music", "Music"),
            ("maps", "Maps"),
        ]
        for keyword, app_name in app_targets:
            if keyword in task_lower:
                logger.info(f"  🖥️ [ScreenAgent] Activating {app_name}")
                mac_control.open_app(app_name)
                self._target_app = app_name
                time.sleep(1.0)
                break

        # If task contains a URL, open it in Chrome
        urls = re.findall(r'https?://[^\s,)"\'>]+', task)
        if urls:
            url = urls[0]
            logger.info(f"  🖥️ [ScreenAgent] Opening URL: {url}")
            self._target_app = self._target_app or "Google Chrome"
            try:
                subprocess.run(["open", url], timeout=5, capture_output=True)
                time.sleep(2.0)
            except Exception:
                pass

    def _ensure_focus(self):
        """Ensure the target app is frontmost before typing/key presses.

        Without this, keystrokes go to whatever window has focus — which can be
        VS Code, Finder, etc. if macOS shifted focus between steps.
        """
        if not self._target_app:
            return
        try:
            frontmost = mac_control.get_frontmost_app()
            current = frontmost.get("content", "") if frontmost.get("success") else ""
            if self._target_app.lower() not in current.lower():
                logger.info(f"  🖥️ [ScreenAgent] Focus lost → re-activating {self._target_app}")
                mac_control.open_app(self._target_app)
                time.sleep(0.3)
        except Exception:
            pass  # Don't let focus check failure block the actual action

    def _dispatch(self, name, inp):
        """Route screen agent tool calls to macOS native handlers."""
        try:
            if name == "screenshot":
                self._screenshots_taken += 1
                result = _take_screenshot_for_vision()
                if result.get("error"):
                    return f"ERROR: {result['error']}"
                # Store display offset for coordinate mapping on next click/type
                self._display_x_offset = result.get("display_x_offset", 0)
                # Return in the format base_agent.py expects for vision images
                return {
                    "_screenshot": True,
                    "image_base64": result["image_base64"],
                    "text": (
                        f"Screenshot #{self._screenshots_taken}. "
                        f"Screen size: {result['screen_width']}×{result['screen_height']} points. "
                        f"The coordinates in this image map directly to screen click coordinates. "
                        f"Analyze the image to see what's on screen and decide your next action."
                    ),
                }

            # ── Coordinate mapping helper ──
            # On multi-display setups, the LLM sees image coordinates (0, 0) to (W, H)
            # but actual clicks need absolute screen coordinates which may be offset.
            # E.g., secondary display at x=-1920: image (500, 300) → screen (-1420, 300)
            def _map_coords(x, y):
                sw, sh = _get_screen_size()
                # Clamp to display bounds first
                x = max(0, min(x, sw - 1))
                y = max(0, min(y, sh - 1))
                # Apply display offset for absolute screen coordinates
                return x + self._display_x_offset, y

            if name == "click":
                x, y = _map_coords(int(inp["x"]), int(inp["y"]))
                self._action_count += 1
                result = mac_control.click(x, y)
                time.sleep(0.3)
                return result.get("content", f"Clicked at ({x}, {y})")

            if name == "double_click":
                x, y = _map_coords(int(inp["x"]), int(inp["y"]))
                self._action_count += 1
                result = mac_control.click(x, y, double_click=True)
                time.sleep(0.3)
                return result.get("content", f"Double-clicked at ({x}, {y})")

            if name == "right_click":
                x, y = _map_coords(int(inp["x"]), int(inp["y"]))
                self._action_count += 1
                result = mac_control.right_click(x, y)
                time.sleep(0.3)
                return result.get("content", f"Right-clicked at ({x}, {y})")

            if name == "type_text":
                text = inp["text"]
                self._action_count += 1
                # FOCUS GUARD: Re-activate target app before typing
                # Prevents typing into VS Code/Finder when focus shifts between steps
                self._ensure_focus()
                result = mac_control.type_text(text)
                time.sleep(0.2)
                return result.get("content", f"Typed {len(text)} characters")

            if name == "key":
                keys = inp["keys"]
                self._action_count += 1
                # FOCUS GUARD: Re-activate target app before key press
                self._ensure_focus()
                result = mac_control.key_press(keys)
                time.sleep(0.2)
                return result.get("content", f"Pressed: {keys}")

            if name == "scroll":
                direction = inp.get("direction", "down")
                amount = inp.get("amount", 3)
                result = _scroll_screen(direction, amount)
                time.sleep(0.3)
                return result

            if name == "move_mouse":
                x, y = _map_coords(int(inp["x"]), int(inp["y"]))
                result = mac_control.mouse_move(x, y)
                time.sleep(0.2)
                return result.get("content", f"Mouse moved to ({x}, {y})")

            if name == "drag":
                sx, sy = _map_coords(int(inp["start_x"]), int(inp["start_y"]))
                ex, ey = _map_coords(int(inp["end_x"]), int(inp["end_y"]))
                result = mac_control.drag(sx, sy, ex, ey
                )
                time.sleep(0.3)
                return result.get("content", "Dragged")

            if name == "wait":
                secs = inp.get("seconds", 2)
                time.sleep(secs)
                return f"Waited {secs} seconds"

            if name == "open_app":
                app_name = inp["app_name"]
                result = mac_control.open_app(app_name)
                # Update target app so focus guard tracks the new app
                self._target_app = app_name
                time.sleep(1.5)
                return result.get("content", f"Opened {app_name}")

            if name == "read_screen":
                result = mac_control.ocr_screen()
                return result.get("content", "No text detected on screen")

            if name == "clipboard_read":
                result = mac_control.clipboard_read()
                return result.get("content", "Clipboard empty")

            if name == "clipboard_write":
                text = inp["text"]
                result = mac_control.clipboard_write(text)
                return result.get("content", f"Wrote to clipboard: {text[:50]}")

            return f"Unknown screen tool: {name}"

        except Exception as e:
            return f"ERROR: {e}"
