"""
TARS Dev Agent v2: Full-Autonomous VS Code Agent Mode Orchestrator

Architecture:
  - Claude Opus 4 in VS Code Agent Mode = the developer
  - TARS Dev Agent = the orchestrator / supervisor / remote control
  - iMessage = the user interface

PRD-to-Production Flow:
  1. User sends PRD or task description via iMessage
  2. TARS scans the project for context
  3. TARS crafts a detailed prompt and fires Agent Mode
  4. YOLO mode auto-approves all tool calls (no buttons to press)
  5. TARS polls chat session files to read Agent Mode's progress
  6. When Agent Mode finishes, TARS reads the output + git diff
  7. TARS sends summary to user, asks if more work needed
  8. If yes, TARS fires follow-up prompt -> cycle repeats
  9. If stuck, TARS sends Cmd+Enter via AppleScript to unstick

Key Settings (auto-configured in VS Code):
  chat.tools.global.autoApprove = true     (YOLO mode - no buttons)
  chat.editing.autoAcceptDelay = 10        (auto-accept file edits)
  chat.agent.maxRequests = 100             (long sessions)
"""

import os
import json
import subprocess
import time as _time
import glob
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.agent_tools import (
    TOOL_RUN_COMMAND, TOOL_READ_FILE,
    TOOL_LIST_DIR, TOOL_SEARCH_FILES, TOOL_GIT,
    TOOL_DONE, TOOL_STUCK,
)
from hands.terminal import run_terminal
from hands.file_manager import read_file, list_directory


# -------------------------------------------
#  Constants
# -------------------------------------------

VSCODE_SETTINGS_PATH = os.path.expanduser(
    "~/Library/Application Support/Code/User/settings.json"
)
VSCODE_STORAGE_PATH = os.path.expanduser(
    "~/Library/Application Support/Code/User/workspaceStorage"
)


# -------------------------------------------
#  VS Code CLI -- auto-discover
# -------------------------------------------

def _find_vscode_cli():
    """Find the VS Code CLI binary, even under AppTranslocation."""
    # 1. Check PATH
    result = subprocess.run(["which", "code"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # 2. Standard install location
    standard = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
    if os.path.exists(standard):
        return standard

    # 3. AppTranslocation (macOS moves apps here on first launch)
    try:
        result = subprocess.run(
            ["find", "/private/var/folders", "-name", "code",
             "-path", "*/Visual Studio Code.app/*/bin/*"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            if line.endswith("/bin/code") and os.path.isfile(line):
                return line
    except Exception:
        pass

    # 4. Homebrew
    brew_path = "/usr/local/bin/code"
    if os.path.exists(brew_path):
        return brew_path

    return None


def _ensure_yolo_mode():
    """Ensure VS Code has YOLO mode enabled for full autonomy."""
    try:
        if os.path.exists(VSCODE_SETTINGS_PATH):
            with open(VSCODE_SETTINGS_PATH) as f:
                settings = json.load(f)
        else:
            settings = {}

        changed = False
        needed = {
            "chat.tools.global.autoApprove": True,
            "chat.editing.autoAcceptDelay": 10,
            "chat.agent.maxRequests": 100,
        }
        for key, val in needed.items():
            if settings.get(key) != val:
                settings[key] = val
                changed = True

        if changed:
            with open(VSCODE_SETTINGS_PATH, "w") as f:
                json.dump(settings, f, indent=4)
            print("    [Dev Agent] Enabled YOLO mode in VS Code settings")
    except Exception as e:
        print(f"    [Dev Agent] Warning: Could not update VS Code settings: {e}")


VSCODE_CLI = _find_vscode_cli()
_ensure_yolo_mode()


# -------------------------------------------
#  Tool Definitions
# -------------------------------------------

TOOL_ASK_USER = {
    "name": "ask_user",
    "description": (
        "Send a question to the user via iMessage and WAIT for their reply. "
        "Use for decisions, approval, or clarification. Be concise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to send. Be concise, use numbered options.",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds to wait for reply (default 300)",
                "default": 300,
            },
        },
        "required": ["message"],
    },
}

TOOL_NOTIFY_USER = {
    "name": "notify_user",
    "description": (
        "Send a one-way status update via iMessage. No wait for reply. "
        "Use for progress updates and completion notifications."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Status message to send (keep brief)",
            },
        },
        "required": ["message"],
    },
}

TOOL_VSCODE_AGENT = {
    "name": "vscode_agent",
    "description": (
        "Fire Claude Opus 4 in VS Code Agent Mode to do the actual coding work. "
        "This is your PRIMARY tool. Claude Opus 4 handles all code reading, editing, "
        "terminal commands, testing, and debugging. You orchestrate, it executes.\n\n"
        "YOLO mode is enabled -- Agent Mode auto-approves all tool calls, no buttons "
        "to press. It will run until done or until it hits max requests.\n\n"
        "The prompt should be detailed and specific. Include:\n"
        "- What to do (the task / PRD)\n"
        "- Which project/directory to work in\n"
        "- Any constraints or preferences from the user\n"
        "- Context about what was already done (if continuing)\n"
        "- Testing requirements (run tests after, etc.)\n\n"
        "This opens a new Agent Mode chat session in VS Code. The command returns "
        "immediately. Use wait_and_report to poll for completion and get results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "The prompt to send to Claude Opus 4 Agent Mode. Be detailed. "
                    "For PRDs, include the full requirements. For tasks, include "
                    "file paths, expected behavior, user constraints."
                ),
            },
            "project_path": {
                "type": "string",
                "description": "Absolute path to the project root to open in VS Code.",
            },
            "add_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional file paths to add as context.",
            },
        },
        "required": ["prompt"],
    },
}

TOOL_WAIT_AND_REPORT = {
    "name": "wait_and_report",
    "description": (
        "Poll VS Code Agent Mode until it finishes, then report what it did. "
        "This is your SECOND most important tool. Use after vscode_agent.\n\n"
        "It works by:\n"
        "1. Polling CPU usage + file activity every poll_interval seconds\n"
        "2. Reading the chat session file to see Agent Mode's output\n"
        "3. Checking git diff for actual code changes\n"
        "4. If Agent Mode appears stuck, optionally sends Cmd+Enter to unstick\n"
        "5. Returns a comprehensive report when Agent Mode finishes\n\n"
        "Set max_wait based on task complexity:\n"
        "- Simple fix: 120s\n"
        "- Feature implementation: 300s\n"
        "- Full PRD / multi-file project: 600-900s"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Absolute path to the project to monitor.",
            },
            "max_wait": {
                "type": "integer",
                "description": "Maximum seconds to wait (default 300).",
                "default": 300,
            },
            "poll_interval": {
                "type": "integer",
                "description": "Seconds between status checks (default 15).",
                "default": 15,
            },
            "auto_unstick": {
                "type": "boolean",
                "description": "If Agent Mode seems stuck, send Cmd+Enter to continue (default true).",
                "default": True,
            },
        },
        "required": ["project_path"],
    },
}

TOOL_READ_CHAT_OUTPUT = {
    "name": "read_chat_output",
    "description": (
        "Read what VS Code Agent Mode said in its most recent chat session. "
        "Returns the last N messages from the chat, including Agent Mode's "
        "thinking, tool invocations, and text responses.\n\n"
        "Use this to understand WHAT Agent Mode did and WHY, so you can "
        "craft better follow-up prompts or summarize for the user."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "last_n_requests": {
                "type": "integer",
                "description": "How many recent request/response pairs to read (default 3).",
                "default": 3,
            },
        },
        "required": [],
    },
}

TOOL_CONTINUE_SESSION = {
    "name": "continue_session",
    "description": (
        "Send a follow-up prompt to VS Code Agent Mode to continue work. "
        "Use after wait_and_report reveals issues, or after user feedback.\n\n"
        "The follow-up prompt should reference what was already done and "
        "what needs to change or be added next."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Follow-up prompt. Reference what was done, what to do next.",
            },
            "project_path": {
                "type": "string",
                "description": "Project root path.",
            },
            "add_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional files to add as context.",
            },
        },
        "required": ["prompt"],
    },
}

TOOL_PRESS_BUTTON = {
    "name": "press_button",
    "description": (
        "Send keyboard shortcut to VS Code to press a button or confirm an action. "
        "Use when Agent Mode is stuck waiting for confirmation despite YOLO mode.\n\n"
        "Actions:\n"
        "- 'continue': Cmd+Enter (accept/allow tool, accept edits)\n"
        "- 'skip': Cmd+Alt+Enter (skip a tool call)\n"
        "- 'accept_all': Cmd+Alt+Y (accept all file edits)\n"
        "- 'accept_one': Cmd+Y (accept single edit)\n"
        "- 'new_chat': Cmd+Shift+N (start new chat session)"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["continue", "skip", "accept_all", "accept_one", "new_chat"],
                "description": "Which button/action to trigger.",
            },
            "repeat": {
                "type": "integer",
                "description": "How many times to press (default 1). Use >1 to spam continue.",
                "default": 1,
            },
        },
        "required": ["action"],
    },
}

TOOL_PROJECT_SCAN = {
    "name": "project_scan",
    "description": (
        "Quick scan of a project: structure, tech stack, git state. "
        "Use to get context before crafting a good prompt for vscode_agent."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the project root",
            },
        },
        "required": ["path"],
    },
}

TOOL_OPEN_PROJECT = {
    "name": "open_project",
    "description": (
        "Open a project folder in VS Code. Use before vscode_agent if "
        "the project is not already open."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the project folder or file.",
            },
            "new_window": {
                "type": "boolean",
                "description": "Open in new window (default false).",
                "default": False,
            },
        },
        "required": ["path"],
    },
}


# -------------------------------------------
#  System Prompt
# -------------------------------------------

DEV_SYSTEM_PROMPT = """You are TARS Dev Agent v2 -- a fully autonomous VS Code Agent Mode orchestrator.

You do NOT write code yourself. Claude Opus 4 in VS Code Agent Mode is your developer. YOLO mode is enabled -- it auto-approves everything. You are the supervisor.

## Architecture
- Claude Opus 4 (VS Code Agent Mode) = writes code, runs terminal, runs tests
- You (TARS Dev Agent) = crafts prompts, monitors progress, reads output, relays to user
- iMessage = your communication channel with the user
- YOLO mode = no approval buttons, fully autonomous execution

## PRD-to-Production Workflow

### Phase 1: Understand the Task
- Read the PRD or task description carefully
- Use project_scan to understand the existing codebase
- If anything is unclear, ask_user for clarification
- notify_user that you're starting work

### Phase 2: Launch Agent Mode
- Craft a DETAILED, SPECIFIC prompt (this is your most important job)
- Include: full PRD/requirements, project context, tech stack, constraints
- Include: "After implementation, run all tests and fix any failures"
- Include: "Commit your changes with a descriptive message when done"
- Fire vscode_agent with the prompt

### Phase 3: Monitor and Read Output
- Use wait_and_report to poll until Agent Mode finishes
- Use read_chat_output to understand WHAT it did and WHY
- If stuck, press_button with 'continue' to unstick
- Check git diff for actual changes

### Phase 4: Evaluate and Iterate
- Read the chat output -- did it complete everything?
- Check for errors, missing features, test failures
- If incomplete, use continue_session with specific follow-up
- Repeat wait_and_report after each follow-up
- Keep iterating until the task is FULLY DONE

### Phase 5: Report and Finalize
- Summarize what was built/changed (files, features, tests)
- notify_user with the summary
- ask_user if they want any changes
- If yes, continue_session with their feedback
- If done, confirm completion

## Prompt Crafting Tips (CRITICAL -- quality determines everything)
- Start with the big picture: "Build a REST API for user management"
- Then specifics: "Using Express.js, TypeScript, PostgreSQL"
- Then constraints: "Follow existing patterns in src/routes/"
- Then testing: "Write Jest tests, ensure all pass"
- Then cleanup: "Run eslint --fix, commit with descriptive message"
- For PRDs: Include the ENTIRE PRD text in the prompt

## Rules
1. NEVER write code yourself -- always use vscode_agent or continue_session
2. ALWAYS wait_and_report after launching -- never assume success
3. ALWAYS read_chat_output to understand what happened
4. Keep iterating until the task is FULLY complete
5. Notify the user of progress at each major milestone
6. If Agent Mode fails 3 times on the same issue, ask_user for guidance
"""


class DevAgent(BaseAgent):
    """Full-autonomous VS Code Agent Mode orchestrator."""

    def __init__(self, llm_client, model, max_steps=60, phone=None,
                 update_every=5, kill_event=None,
                 imessage_sender=None, imessage_reader=None):
        super().__init__(
            llm_client=llm_client,
            model=model,
            max_steps=max_steps,
            phone=phone,
            update_every=update_every,
            kill_event=kill_event,
        )
        self._imessage_sender = imessage_sender
        self._imessage_reader = imessage_reader
        self._session_start = datetime.now()
        self._project_cache = {}
        self._snapshots = {}
        self._vscode_cli = VSCODE_CLI
        self._agent_launches = 0
        self._launch_timestamps = []
        self._stuck_count = 0

    # ---- Identity ----

    @property
    def agent_name(self):
        return "Dev Agent"

    @property
    def agent_emoji(self):
        return "\U0001f6e0\ufe0f"

    @property
    def system_prompt(self):
        cli_status = (
            f"VS Code CLI: {self._vscode_cli}"
            if self._vscode_cli
            else "WARNING: VS Code CLI not found! Install via: VS Code > Cmd+Shift+P > Shell Command: Install 'code' in PATH"
        )
        return DEV_SYSTEM_PROMPT + f"\n\n## Environment\n- {cli_status}\n- YOLO mode: enabled\n- macOS, Python 3.9+, zsh\n"

    @property
    def tools(self):
        return [
            TOOL_VSCODE_AGENT,
            TOOL_WAIT_AND_REPORT,
            TOOL_READ_CHAT_OUTPUT,
            TOOL_CONTINUE_SESSION,
            TOOL_PRESS_BUTTON,
            TOOL_OPEN_PROJECT,
            TOOL_PROJECT_SCAN,
            TOOL_ASK_USER,
            TOOL_NOTIFY_USER,
            TOOL_RUN_COMMAND,
            TOOL_READ_FILE,
            TOOL_LIST_DIR,
            TOOL_SEARCH_FILES,
            TOOL_GIT,
            TOOL_DONE,
            TOOL_STUCK,
        ]

    # ===== Tool Dispatch =====

    def _dispatch(self, name, inp):
        try:
            if name == "vscode_agent":
                return self._vscode_agent(
                    inp["prompt"],
                    inp.get("project_path"),
                    inp.get("add_files"),
                )

            elif name == "wait_and_report":
                return self._wait_and_report(
                    inp["project_path"],
                    inp.get("max_wait", 300),
                    inp.get("poll_interval", 15),
                    inp.get("auto_unstick", True),
                )

            elif name == "read_chat_output":
                return self._read_chat_output(
                    inp.get("last_n_requests", 3),
                )

            elif name == "continue_session":
                return self._vscode_agent(
                    inp["prompt"],
                    inp.get("project_path"),
                    inp.get("add_files"),
                )

            elif name == "press_button":
                return self._press_button(
                    inp["action"],
                    inp.get("repeat", 1),
                )

            elif name == "open_project":
                return self._open_project(
                    inp["path"],
                    inp.get("new_window", False),
                )

            elif name == "project_scan":
                return self._project_scan(inp["path"])

            elif name == "ask_user":
                return self._ask_user(
                    inp["message"],
                    inp.get("timeout", 300),
                )

            elif name == "notify_user":
                return self._notify_user(inp["message"])

            elif name == "run_command":
                result = run_terminal(
                    inp["command"],
                    timeout=inp.get("timeout", 60),
                )
                return result.get("content", str(result))

            elif name == "read_file":
                result = read_file(inp["path"])
                return result.get("content", str(result))

            elif name == "list_dir":
                result = list_directory(inp["path"])
                return result.get("content", str(result))

            elif name == "search_files":
                return self._search_files(
                    inp["pattern"],
                    inp.get("directory", os.getcwd()),
                    inp.get("content_search", False),
                )

            elif name == "git":
                cmd_str = inp["command"]
                result = run_terminal(f"git {cmd_str}", timeout=30)
                return result.get("content", str(result))

            return f"Unknown tool: {name}"
        except Exception as e:
            return f"ERROR [{name}]: {e}"

    # ===== VS Code Agent Mode =====

    def _vscode_agent(self, prompt, project_path=None, add_files=None):
        """Launch Claude Opus 4 in VS Code Agent Mode."""
        if not self._vscode_cli:
            return (
                "ERROR: VS Code CLI not found. Cannot launch Agent Mode.\n"
                "Fix: VS Code > Cmd+Shift+P > Shell Command: Install 'code' in PATH"
            )

        # Build the command
        cmd = [self._vscode_cli, "chat", "-m", "agent"]

        # Add context files
        if add_files:
            for f in add_files:
                if os.path.exists(f):
                    cmd.extend(["-a", f])

        # Reuse existing window
        cmd.append("-r")

        # The prompt itself
        cmd.append(prompt)

        # Open the project first if specified
        if project_path:
            self._snapshots[project_path] = self._take_snapshot(project_path)
            try:
                subprocess.run(
                    [self._vscode_cli, project_path, "-r"],
                    capture_output=True, text=True, timeout=10,
                )
                _time.sleep(2)
            except Exception:
                pass

        self._agent_launches += 1
        self._launch_timestamps.append(_time.time())
        launch_num = self._agent_launches
        self._stuck_count = 0
        print(f"    [Dev Agent] Launching Agent Mode #{launch_num}: {prompt[:120]}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_path if project_path else None,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                return f"ERROR launching Agent Mode (exit {result.returncode}): {stderr}"

            parts = [
                f"Agent Mode launched (session #{launch_num}).",
                f"Prompt: {prompt[:300]}",
            ]
            if project_path:
                parts.append(f"Project: {project_path}")
            parts.append("")
            parts.append("YOLO mode is ON -- all tools auto-approved.")
            parts.append("Use wait_and_report to poll for completion.")
            return "\n".join(parts)

        except subprocess.TimeoutExpired:
            return (
                f"Agent Mode launch sent (session #{launch_num}). "
                "CLI timed out but Agent Mode is likely working. "
                "Use wait_and_report to poll for completion."
            )
        except Exception as e:
            return f"ERROR: {e}"

    # ===== Wait and Report (Smart Polling) =====

    def _wait_and_report(self, project_path, max_wait=300, poll_interval=15, auto_unstick=True):
        """Poll until Agent Mode finishes, then report changes."""
        project_path = os.path.expanduser(project_path)
        if not os.path.isdir(project_path):
            return f"ERROR: Not a directory: {project_path}"

        start_time = _time.time()
        idle_count = 0
        last_file_count = 0
        unstick_attempts = 0

        print(f"    [Dev Agent] Polling Agent Mode (max {max_wait}s, every {poll_interval}s)...")

        while (_time.time() - start_time) < max_wait:
            _time.sleep(poll_interval)
            elapsed = int(_time.time() - start_time)

            # Check VS Code CPU activity
            is_active = self._is_vscode_active()

            # Check file modification activity
            recently_modified = self._count_recent_files(project_path, minutes=1)

            if is_active or recently_modified > last_file_count:
                idle_count = 0
                last_file_count = recently_modified
                print(f"    [Dev Agent] {elapsed}s: Agent Mode ACTIVE (CPU active, {recently_modified} files changed)")
            else:
                idle_count += 1
                print(f"    [Dev Agent] {elapsed}s: Agent Mode IDLE ({idle_count} consecutive)")

                # If idle for 3+ consecutive polls, it's probably done
                if idle_count >= 3:
                    print(f"    [Dev Agent] Agent Mode appears FINISHED after {elapsed}s")
                    break

                # If idle for 2 polls and auto_unstick, try pressing continue
                if idle_count == 2 and auto_unstick and unstick_attempts < 3:
                    unstick_attempts += 1
                    self._stuck_count += 1
                    print(f"    [Dev Agent] Trying to unstick (attempt {unstick_attempts})...")
                    self._press_button("continue", 1)

        total_time = int(_time.time() - start_time)

        # Now gather the report
        sections = [f"## Agent Mode Report (ran for {total_time}s)\n"]

        # Git diff
        sections.append(self._get_git_report(project_path))

        # File snapshot comparison
        sections.append(self._get_file_change_report(project_path))

        # Chat output summary
        chat_summary = self._read_chat_output(last_n_requests=2)
        if chat_summary and "No chat session" not in chat_summary:
            sections.append(f"### Agent Mode Output\n{chat_summary}\n")

        # Status
        if idle_count >= 3:
            sections.append("\nStatus: Agent Mode FINISHED (idle detected)")
        elif (_time.time() - start_time) >= max_wait:
            sections.append("\nStatus: TIMEOUT -- Agent Mode may still be running. Use wait_and_report again or check_status.")
        if unstick_attempts > 0:
            sections.append(f"Unstick attempts: {unstick_attempts}")

        return "\n".join(sections)

    def _is_vscode_active(self):
        """Check if VS Code is actively using CPU."""
        try:
            r = run_terminal(
                "ps aux | grep 'Code Helper (Renderer)' | grep -v grep | awk '{print $3}'",
                timeout=5,
            )
            cpu_vals = r.get("content", "").strip()
            if cpu_vals:
                total = sum(float(v) for v in cpu_vals.splitlines() if v.strip())
                return total > 10
        except Exception:
            pass
        return False

    def _count_recent_files(self, project_path, minutes=1):
        """Count files modified in the last N minutes."""
        try:
            r = run_terminal(
                f"find '{project_path}' -type f -mmin -{minutes} "
                f"-not -path '*/.git/*' -not -path '*/node_modules/*' "
                f"-not -path '*/venv/*' -not -path '*/__pycache__/*' "
                f"2>/dev/null | wc -l",
                timeout=5,
            )
            count_str = r.get("content", "0").strip()
            return int(count_str)
        except Exception:
            return 0

    def _get_git_report(self, project_path):
        """Get git diff report for the project."""
        sections = []
        try:
            r = run_terminal(
                f"cd '{project_path}' && git diff --stat 2>/dev/null",
                timeout=10,
            )
            diff_stat = r.get("content", "").strip()
            if diff_stat:
                sections.append(f"### Git Diff (unstaged)\n```\n{diff_stat}\n```")

            r = run_terminal(
                f"cd '{project_path}' && git diff --cached --stat 2>/dev/null",
                timeout=10,
            )
            cached = r.get("content", "").strip()
            if cached:
                sections.append(f"### Git Diff (staged)\n```\n{cached}\n```")

            r = run_terminal(
                f"cd '{project_path}' && git ls-files --others --exclude-standard 2>/dev/null | head -20",
                timeout=10,
            )
            untracked = r.get("content", "").strip()
            if untracked:
                sections.append(f"### New Files\n```\n{untracked}\n```")

            r = run_terminal(
                f"cd '{project_path}' && git log --oneline -5 --since='30 minutes ago' 2>/dev/null",
                timeout=5,
            )
            recent = r.get("content", "").strip()
            if recent:
                sections.append(f"### Recent Commits\n```\n{recent}\n```")

            r = run_terminal(
                f"cd '{project_path}' && git diff 2>/dev/null | head -300",
                timeout=10,
            )
            diff_content = r.get("content", "").strip()
            if diff_content:
                sections.append(f"### Diff Detail (first 300 lines)\n```diff\n{diff_content}\n```")
        except Exception as e:
            sections.append(f"### Git\nError: {e}")

        return "\n".join(sections) if sections else "### Git\nNo git changes detected."

    def _get_file_change_report(self, project_path):
        """Compare file snapshots to detect changes."""
        baseline = self._snapshots.get(project_path)
        if not baseline:
            return ""

        current = self._take_snapshot(project_path)
        modified = []
        new_files = []
        deleted = []

        for fpath, info in current.items():
            if fpath in baseline:
                if info["mtime"] != baseline[fpath]["mtime"]:
                    modified.append(os.path.relpath(fpath, project_path))
            else:
                new_files.append(os.path.relpath(fpath, project_path))

        for fpath in baseline:
            if fpath not in current:
                deleted.append(os.path.relpath(fpath, project_path))

        self._snapshots[project_path] = current

        if not (modified or new_files or deleted):
            return ""

        lines = ["### File Changes"]
        if modified:
            lines.append(f"Modified ({len(modified)}): {', '.join(modified[:20])}")
        if new_files:
            lines.append(f"New ({len(new_files)}): {', '.join(new_files[:20])}")
        if deleted:
            lines.append(f"Deleted ({len(deleted)}): {', '.join(deleted[:10])}")
        return "\n".join(lines)

    # ===== Chat Session Reader =====

    def _read_chat_output(self, last_n_requests=3):
        """Read the most recent VS Code Agent Mode chat session output."""
        try:
            # Find all chat session files
            sessions = glob.glob(
                os.path.join(VSCODE_STORAGE_PATH, "*/chatSessions/*.json")
            )
            if not sessions:
                return "No chat session files found."

            # Sort by modification time, most recent first
            sessions.sort(key=os.path.getmtime, reverse=True)

            # Find the session modified after our last launch
            target = sessions[0]
            if self._launch_timestamps:
                last_launch = self._launch_timestamps[-1]
                for s in sessions:
                    if os.path.getmtime(s) >= last_launch:
                        target = s
                        break

            with open(target) as f:
                data = json.load(f)

            requests = data.get("requests", [])
            if not requests:
                return "Chat session has no requests."

            # Get last N requests
            recent = requests[-last_n_requests:]
            output_parts = []

            for req in recent:
                # User message
                msg = req.get("message", {})
                msg_text = ""
                if isinstance(msg, dict):
                    msg_text = msg.get("text", "")
                if msg_text:
                    output_parts.append(f"**User**: {msg_text[:300]}")

                # Agent response
                response = req.get("response", [])
                if isinstance(response, list):
                    resp_texts = []
                    tool_calls = []
                    for part in response:
                        if not isinstance(part, dict):
                            continue
                        kind = part.get("kind", "")
                        value = part.get("value", "")

                        if kind == "thinking" and value:
                            resp_texts.append(f"(thinking: {str(value)[:150]})")
                        elif kind == "prepareToolInvocation":
                            tool_name = part.get("toolName", "unknown")
                            tool_calls.append(tool_name)
                        elif kind == "toolInvocation":
                            tool_name = part.get("toolName", "unknown")
                            tool_calls.append(tool_name)
                        elif isinstance(value, str) and value.strip():
                            resp_texts.append(value[:500])

                    if tool_calls:
                        output_parts.append(f"**Tools used**: {', '.join(tool_calls)}")
                    if resp_texts:
                        combined = "\n".join(resp_texts)
                        output_parts.append(f"**Agent**: {combined[:800]}")

                # Result status
                result = req.get("result", None)
                if result:
                    output_parts.append(f"**Result**: {result}")

                output_parts.append("---")

            # Session metadata
            has_pending = data.get("hasPendingEdits", False)
            if has_pending:
                output_parts.append("WARNING: Session has pending edits that need acceptance!")

            return "\n".join(output_parts) if output_parts else "No readable output in chat session."

        except Exception as e:
            return f"Error reading chat session: {e}"

    # ===== Button Presser (AppleScript) =====

    def _press_button(self, action, repeat=1):
        """Send keyboard shortcuts to VS Code via AppleScript."""
        # Map actions to AppleScript keystrokes
        key_map = {
            "continue": 'keystroke return using {command down}',
            "skip": 'keystroke return using {command down, option down}',
            "accept_all": 'keystroke "y" using {command down, option down}',
            "accept_one": 'keystroke "y" using {command down}',
            "new_chat": 'keystroke "n" using {command down, shift down}',
        }

        keystroke = key_map.get(action)
        if not keystroke:
            return f"Unknown action: {action}"

        results = []
        for i in range(repeat):
            try:
                script = (
                    'tell application "System Events"\n'
                    '    tell process "Electron"\n'
                    '        set frontmost to true\n'
                    '        delay 0.3\n'
                    f'        {keystroke}\n'
                    '    end tell\n'
                    'end tell'
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    results.append(f"Press {i+1}: OK")
                else:
                    results.append(f"Press {i+1}: Error - {result.stderr.strip()}")
                if repeat > 1:
                    _time.sleep(1)
            except Exception as e:
                results.append(f"Press {i+1}: Error - {e}")

        action_desc = {
            "continue": "Cmd+Enter (accept/continue)",
            "skip": "Cmd+Alt+Enter (skip)",
            "accept_all": "Cmd+Alt+Y (accept all edits)",
            "accept_one": "Cmd+Y (accept edit)",
            "new_chat": "Cmd+Shift+N (new chat)",
        }
        return f"Sent {action_desc.get(action, action)} x{repeat}: {'; '.join(results)}"

    # ===== Snapshot =====

    def _take_snapshot(self, project_path):
        """Capture file mtimes for change detection."""
        snapshot = {}
        skip_dirs = {
            ".git", "node_modules", "venv", "__pycache__",
            ".next", "dist", "build", ".tox", ".mypy_cache",
        }
        try:
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        st = os.stat(fpath)
                        snapshot[fpath] = {
                            "mtime": st.st_mtime,
                            "size": st.st_size,
                        }
                    except OSError:
                        pass
        except Exception:
            pass
        return snapshot

    # ===== VS Code Project =====

    def _open_project(self, path, new_window=False):
        """Open a project folder in VS Code."""
        if not self._vscode_cli:
            return "ERROR: VS Code CLI not found."
        path = os.path.expanduser(path)
        flag = "-n" if new_window else "-r"
        cmd = [self._vscode_cli, path, flag]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return f"Opened {path} in VS Code."
            return f"ERROR: {result.stderr.strip()}"
        except Exception as e:
            return f"ERROR: {e}"

    # ===== iMessage =====

    def _ask_user(self, message, timeout=300):
        """Send question via iMessage, wait for reply."""
        if not self._imessage_sender or not self._imessage_reader:
            return "ERROR: iMessage not configured for this session."

        tagged = f"Dev Agent:\n{message}"
        try:
            self._imessage_sender.send(tagged)
        except Exception as e:
            return f"ERROR sending iMessage: {e}"

        print(f"    [Dev Agent] Asked user: {message[:100]}...")

        try:
            reply = self._imessage_reader.wait_for_reply(timeout=timeout)
            if reply.get("success"):
                user_reply = reply["content"]
                print(f"    [Dev Agent] User replied: {user_reply[:100]}...")
                return f"User replied: {user_reply}"
            return f"No reply received within {timeout}s."
        except Exception as e:
            return f"ERROR waiting for reply: {e}"

    def _notify_user(self, message):
        """Send one-way status update via iMessage."""
        if not self._imessage_sender:
            return "ERROR: iMessage not configured for this session."

        tagged = f"Dev Agent:\n{message}"
        try:
            self._imessage_sender.send(tagged)
            print(f"    [Dev Agent] Notified user: {message[:100]}...")
            return "Notification sent."
        except Exception as e:
            return f"ERROR sending notification: {e}"

    # ===== Project Intelligence =====

    def _project_scan(self, path):
        """Quick project scan: structure, tech stack, git state."""
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return f"ERROR: Not a directory: {path}"

        if path in self._project_cache:
            return self._project_cache[path]

        sections = [f"## Project: {path}\n"]

        # Detect tech stack
        stack = []
        stack_map = {
            "package.json": "Node.js",
            "tsconfig.json": "TypeScript",
            "requirements.txt": "Python (pip)",
            "pyproject.toml": "Python (pyproject)",
            "setup.py": "Python (setup.py)",
            "Cargo.toml": "Rust",
            "go.mod": "Go",
            "Gemfile": "Ruby",
            "next.config.js": "Next.js",
            "next.config.mjs": "Next.js",
            "next.config.ts": "Next.js",
            "vite.config.ts": "Vite",
            "vite.config.js": "Vite",
            "Dockerfile": "Docker",
            "docker-compose.yml": "Docker Compose",
            "docker-compose.yaml": "Docker Compose",
            "tailwind.config.js": "Tailwind CSS",
            "tailwind.config.ts": "Tailwind CSS",
            "Podfile": "CocoaPods",
        }
        for filename, tech in stack_map.items():
            if os.path.exists(os.path.join(path, filename)):
                if tech not in stack:
                    stack.append(tech)
        if stack:
            sections.append(f"Stack: {', '.join(stack)}\n")

        # Directory tree
        try:
            r = run_terminal(
                f"find '{path}' -maxdepth 3 "
                f"-not -path '*/node_modules/*' -not -path '*/.git/*' "
                f"-not -path '*/venv/*' -not -path '*/__pycache__/*' "
                f"| head -80",
                timeout=10,
            )
            tree = r.get("content", "")
            if tree:
                sections.append(f"### Structure\n```\n{tree}\n```\n")
        except Exception:
            pass

        # Recent git history
        try:
            r = run_terminal(
                f"cd '{path}' && git log --oneline -5 2>/dev/null",
                timeout=5,
            )
            log = r.get("content", "").strip()
            if log:
                sections.append(f"### Recent Commits\n```\n{log}\n```\n")

            r = run_terminal(
                f"cd '{path}' && git status --short 2>/dev/null | head -20",
                timeout=5,
            )
            status = r.get("content", "").strip()
            if status:
                sections.append(f"### Git Status\n```\n{status}\n```\n")
        except Exception:
            pass

        # File count
        try:
            r = run_terminal(
                f"find '{path}' -type f "
                f"-not -path '*/.git/*' -not -path '*/node_modules/*' "
                f"-not -path '*/venv/*' 2>/dev/null | wc -l",
                timeout=5,
            )
            count = r.get("content", "").strip()
            sections.append(f"Total files: {count}\n")
        except Exception:
            pass

        scan = "\n".join(sections)
        self._project_cache[path] = scan
        return scan

    def _search_files(self, pattern, directory, content_search):
        """Search for files by name or content."""
        try:
            directory = os.path.expanduser(directory)
            if content_search:
                r = run_terminal(
                    f"grep -rn "
                    f"--include='*.py' --include='*.js' --include='*.ts' "
                    f"--include='*.tsx' --include='*.jsx' --include='*.html' "
                    f"--include='*.css' --include='*.json' --include='*.yaml' "
                    f"'{pattern}' '{directory}' 2>/dev/null | head -30",
                    timeout=15,
                )
                return r.get("content", "(no results)")
            else:
                r = run_terminal(
                    f"find '{directory}' -name '{pattern}' "
                    f"-not -path '*/node_modules/*' -not -path '*/.git/*' "
                    f"-not -path '*/venv/*' "
                    f"2>/dev/null | head -30",
                    timeout=15,
                )
                return r.get("content", "(no results)")
        except Exception as e:
            return f"ERROR: {e}"
