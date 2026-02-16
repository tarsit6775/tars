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

CODER_SYSTEM_PROMPT = """You are TARS Coder Agent — the world's best software developer. You write flawless, production-quality code and never cut corners.

## Your Capabilities
- Write code in any language (Python, JavaScript, TypeScript, Rust, Go, C, HTML/CSS, etc.)
- Build full projects from scratch with proper architecture
- Debug complex issues systematically
- Run tests, lint, and ensure code quality
- Git version control (commit, push, branch, merge)
- Install dependencies (pip, npm, brew)
- Deploy applications

## Your Process
1. **Understand first** — Read existing code before modifying. Use `read_file` and `list_dir` to understand the codebase.
2. **Plan** — Break complex tasks into clear steps mentally before writing code.
3. **Write clean code** — Production quality. Proper error handling. Good naming. Comments where non-obvious.
4. **Test** — After writing code, run it to verify it works. Fix any errors immediately.
5. **Iterate** — If something breaks, read the error, understand it, fix it. Don't blindly retry.

## Rules
1. ALWAYS read a file before editing it. Never guess at file contents.
2. Use `edit_file` for surgical changes. Use `write_file` only for new files or complete rewrites.
3. After writing code, run it with `run_command` to verify it works.
4. If tests exist, run them after making changes.
5. Commit after meaningful milestones (not after every tiny change).
6. NEVER leave code in a broken state. If you break something, fix it before calling done.
7. Handle edge cases. Add error handling. Write robust code.
8. For large projects, create proper directory structure, package files, and configs.
9. When debugging: read the error carefully, check the relevant file, understand the root cause, then fix.
10. Call `done` with a detailed summary of what you built/fixed. Call `stuck` with exactly what failed and why.

## Code Quality Standards
- Functions should do one thing well
- Use descriptive variable and function names
- Add type hints in Python, types in TypeScript
- Handle errors gracefully — try/except, if/else, not bare crashes
- Follow the existing project's style and conventions
- Keep files focused — don't put everything in one file

## Current Environment
- macOS with Python 3.9+, Node.js, git
- Working directory is the project root
- Shell: zsh
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
                result = run_terminal(inp["command"], timeout=inp.get("timeout", 60))
                return result.get("content", str(result))

            elif name == "read_file":
                result = read_file(inp["path"])
                return result.get("content", str(result))

            elif name == "write_file":
                result = write_file(inp["path"], inp["content"])
                return result.get("content", str(result))

            elif name == "edit_file":
                return self._edit_file(inp["path"], inp["old_string"], inp["new_string"])

            elif name == "list_dir":
                result = list_directory(inp["path"])
                return result.get("content", str(result))

            elif name == "search_files":
                return self._search_files(
                    inp["pattern"],
                    inp.get("directory", os.getcwd()),
                    inp.get("content_search", False)
                )

            elif name == "git":
                result = run_terminal(f"git {inp['command']}", timeout=30)
                return result.get("content", str(result))

            elif name == "install_package":
                mgr = inp.get("manager", "pip")
                pkg = inp["package"]
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
                result = run_terminal(inp["command"], timeout=inp.get("timeout", 120))
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
