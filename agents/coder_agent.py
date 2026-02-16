"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Coder Agent: The Developer                       ║
╠══════════════════════════════════════════════════════════════╣
║  Expert at writing code, building projects, debugging,       ║
║  testing, git, and deployments. Own LLM loop.                ║
║                                                              ║
║  Tools: run_command, read_file, write_file, edit_file,       ║
║         list_dir, search_files, git, install_package,        ║
║         run_tests, done, stuck                               ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import subprocess
import shutil

from agents.base_agent import BaseAgent
from agents.agent_tools import (
    TOOL_RUN_COMMAND, TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_EDIT_FILE,
    TOOL_LIST_DIR, TOOL_SEARCH_FILES, TOOL_GIT, TOOL_INSTALL_PACKAGE,
    TOOL_RUN_TESTS, TOOL_DONE, TOOL_STUCK,
)
from hands.terminal import run_terminal
from hands.file_manager import read_file, write_file, list_directory


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

CODER_SYSTEM_PROMPT = """You are TARS Coder Agent — an expert software developer. You write flawless code and verify everything works.

## CRITICAL RULES (read these FIRST)

### File Paths
- ALWAYS use absolute paths starting with / (e.g., /Users/abdullah/Desktop/script.py)
- NEVER use ~ in file paths — it does NOT expand in Python open() or write_file
- If the task says "save to ~/Desktop/foo.py", YOU must use "/Users/abdullah/Desktop/foo.py"

### File Names — USE EXACTLY WHAT WAS ASKED
- If task says "create parallel_test_2_colors.py" → write to THAT EXACT filename
- NEVER rename files to something "better" — use the EXACT name from the task
- Wrong: task says "parallel_test_2_colors.py" → you write "color_palette.py" ← WRONG
- Right: task says "parallel_test_2_colors.py" → you write "parallel_test_2_colors.py" ← RIGHT

### Code Must Work — MANDATORY verify
- After writing ANY script, you MUST run it with run_command to verify zero errors
- If run_command shows a SyntaxError or any error, FIX IT before calling done()
- NEVER call done() without verifying the code actually runs
- Python: run with `python3 /absolute/path/to/script.py`

### Python Syntax — Common Mistakes to AVOID
- Match every opening ( { [ with its closing ) } ]
- f-strings: use f"text {variable}" — never nest f"...{f'...'}" (use a temp variable)
- Multi-line strings: use triple quotes, not concatenation with +
- Indentation: use 4 spaces consistently, never mix tabs and spaces
- Dictionary/list literals: ensure trailing commas don't cause issues
- Print formatting: prefer f-strings over .format() or % for clarity

## Your Process
1. **Read the task carefully** — note exact filenames, paths, and requirements
2. **Plan** — break the task into steps mentally
3. **Write code** — clean, production-quality, with error handling
4. **VERIFY** — run the script with run_command. If errors, fix and re-run
5. **Done** — only call done() after successful verification

## Tools
- `write_file` — write a new file (provide FULL content, absolute path)
- `read_file` — read existing file before editing
- `edit_file` — surgical string replacement (read first!)
- `run_command` — run shell commands, test scripts
- `list_dir` — explore directories
- `search_files` — find files by name or content
- `git` — version control
- `install_package` — pip/npm/brew install
- `run_tests` — run test suites

## Code Quality
- Functions do one thing well
- Descriptive variable names
- Error handling (try/except)
- Comments for non-obvious logic
- Type hints in Python

## Environment
- macOS, Python 3.9+, Node.js, git, zsh
- Home directory: /Users/abdullah
- Desktop: /Users/abdullah/Desktop
"""


class CoderAgent(BaseAgent):
    """Autonomous coding agent — writes, debugs, tests, and deploys code."""

    @property
    def agent_name(self):
        return "Coder Agent"

    @property
    def agent_emoji(self):
        return "💻"

    @property
    def system_prompt(self):
        return CODER_SYSTEM_PROMPT

    @property
    def tools(self):
        return [
            TOOL_RUN_COMMAND, TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_EDIT_FILE,
            TOOL_LIST_DIR, TOOL_SEARCH_FILES, TOOL_GIT, TOOL_INSTALL_PACKAGE,
            TOOL_RUN_TESTS, TOOL_DONE, TOOL_STUCK,
        ]

    def _dispatch(self, name, inp):
        """Route coder tool calls to actual handlers."""
        try:
            if name == "run_command":
                cmd = inp.get("command", "")
                if not cmd:
                    return "ERROR: Missing 'command' parameter. Provide the shell command to run."
                result = run_terminal(cmd, timeout=inp.get("timeout", 60))
                return result.get("content", str(result))

            elif name == "read_file":
                path = inp.get("path", "")
                if not path:
                    return "ERROR: Missing 'path' parameter. Provide the absolute file path."
                result = read_file(path)
                return result.get("content", str(result))

            elif name == "write_file":
                path = inp.get("path", "")
                content = inp.get("content", "")
                if not path:
                    return "ERROR: Missing 'path' parameter. Use an ABSOLUTE path like /Users/abdullah/Desktop/script.py"
                if not content:
                    return "ERROR: Missing 'content' parameter. Provide the full file content to write."
                result = write_file(path, content)
                msg = result.get("content", str(result))
                # Auto syntax-check Python files after writing
                expanded = os.path.expanduser(path)
                if result.get("success") and expanded.endswith(".py"):
                    check = run_terminal(
                        f"python3 -c \"import py_compile; py_compile.compile('{expanded}', doraise=True)\"",
                        timeout=10,
                    )
                    check_out = check.get("content", "")
                    if not check.get("success") or "Error" in check_out or "SyntaxError" in check_out:
                        msg += f"\n\n⚠️ SYNTAX ERROR DETECTED — fix this before calling done():\n{check_out}"
                    else:
                        msg += "\n✅ Syntax check passed."
                return msg

            elif name == "edit_file":
                path = inp.get("path", "")
                old_str = inp.get("old_string", "")
                new_str = inp.get("new_string", "")
                if not path:
                    return "ERROR: Missing 'path' parameter."
                if not old_str:
                    return "ERROR: Missing 'old_string' parameter. Use read_file first, then provide exact text to replace."
                result = self._edit_file(path, old_str, new_str)
                # Auto syntax-check Python files after editing
                expanded = os.path.expanduser(path)
                if "✅ Edited" in result and expanded.endswith(".py"):
                    check = run_terminal(
                        f"python3 -c \"import py_compile; py_compile.compile('{expanded}', doraise=True)\"",
                        timeout=10,
                    )
                    check_out = check.get("content", "")
                    if not check.get("success") or "Error" in check_out or "SyntaxError" in check_out:
                        result += f"\n\n⚠️ SYNTAX ERROR after edit — fix this before calling done():\n{check_out}"
                    else:
                        result += "\n✅ Syntax OK after edit."
                return result

            elif name == "list_dir":
                path = inp.get("path", "")
                if not path:
                    return "ERROR: Missing 'path' parameter."
                result = list_directory(path)
                return result.get("content", str(result))

            elif name == "search_files":
                pattern = inp.get("pattern", "")
                if not pattern:
                    return "ERROR: Missing 'pattern' parameter."
                return self._search_files(
                    pattern,
                    inp.get("directory", os.getcwd()),
                    inp.get("content_search", False)
                )

            elif name == "git":
                git_cmd = inp.get("command", "")
                if not git_cmd:
                    return "ERROR: Missing 'command' parameter. Example: 'status', 'add .', 'commit -m \"msg\"'"
                result = run_terminal(f"git {git_cmd}", timeout=30)
                return result.get("content", str(result))

            elif name == "install_package":
                mgr = inp.get("manager", "pip")
                pkg = inp.get("package", "")
                if not pkg:
                    return "ERROR: Missing 'package' parameter."
                cmd_map = {
                    "pip": f"pip install {pkg}",
                    "pip3": f"pip3 install {pkg}",
                    "npm": f"npm install {pkg}",
                    "brew": f"brew install {pkg}",
                }
                cmd = cmd_map.get(mgr, f"pip install {pkg}")
                result = run_terminal(cmd, timeout=120)
                return result.get("content", str(result))

            elif name == "run_tests":
                test_cmd = inp.get("command", "")
                if not test_cmd:
                    return "ERROR: Missing 'command' parameter. Example: 'pytest', 'python3 -m unittest'"
                result = run_terminal(test_cmd, timeout=inp.get("timeout", 120))
                return result.get("content", str(result))

            return f"Unknown coder tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _edit_file(self, path, old_string, new_string):
        """Surgical string replacement in a file."""
        try:
            path = os.path.expanduser(path)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_string not in content:
                return f"ERROR: old_string not found in {path}. Use read_file to see current contents."

            count = content.count(old_string)
            if count > 1:
                return f"ERROR: old_string found {count} times in {path}. Make it more specific (include surrounding lines)."

            new_content = content.replace(old_string, new_string, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"✅ Edited {path} — replaced {len(old_string)} chars with {len(new_string)} chars"
        except FileNotFoundError:
            return f"ERROR: File not found: {path}"
        except Exception as e:
            return f"ERROR editing file: {e}"

    def _search_files(self, pattern, directory, content_search):
        """Search files by name or content."""
        try:
            directory = os.path.expanduser(directory)
            if content_search:
                # Grep for content
                result = run_terminal(
                    f"grep -rn --include='*.py' --include='*.js' --include='*.ts' --include='*.html' --include='*.css' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.md' --include='*.txt' '{pattern}' '{directory}' 2>/dev/null | head -50",
                    timeout=15
                )
                return result.get("content", "(no results)")
            else:
                # Find by filename pattern
                result = run_terminal(
                    f"find '{directory}' -name '{pattern}' -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/venv/*' 2>/dev/null | head -50",
                    timeout=15
                )
                return result.get("content", "(no results)")
        except Exception as e:
            return f"ERROR searching: {e}"
