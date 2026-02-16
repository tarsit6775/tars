"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — File Agent: The File Manager                     ║
╠══════════════════════════════════════════════════════════════╣
║  Expert at file organization, bulk operations, finding       ║
║  things, compressing, cleaning up. Own LLM loop.             ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import shutil
import subprocess

from agents.base_agent import BaseAgent
from agents.agent_tools import (
    TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_LIST_DIR, TOOL_SEARCH_FILES,
    TOOL_MOVE, TOOL_COPY, TOOL_DELETE, TOOL_TREE, TOOL_DISK_USAGE,
    TOOL_COMPRESS, TOOL_EXTRACT_ARCHIVE, TOOL_RUN_COMMAND,
    TOOL_DONE, TOOL_STUCK,
)
from hands.terminal import run_terminal
from hands.file_manager import read_file, write_file, move_file, delete_file, list_directory


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

FILE_AGENT_PROMPT = """You are TARS File Agent — the world's best file management specialist. You organize, find, move, compress, and clean up files and directories with precision and efficiency.

## Your Capabilities
- Read and write files
- List directory contents
- Search for files by name pattern or content
- Move and rename files/directories
- Copy files/directories
- Delete files (carefully)
- Show directory tree structure
- Check disk usage
- Compress files into zip/tar archives
- Extract archives
- Run shell commands for advanced operations

## Your Process
1. **Understand** — List directories and understand the current structure before making changes
2. **Plan** — For bulk operations, list what will be affected before acting
3. **Execute** — Perform the operations carefully
4. **Verify** — Check the result (list_dir, tree) to confirm success

## Rules
1. ALWAYS list/read before modifying — understand the current state first
2. For bulk deletes, list what will be deleted and confirm the scope
3. Use `tree` to get an overview before reorganizing
4. Prefer `move` over copy+delete
5. Use `search_files` to find things instead of manually listing every directory
6. For large-scale operations, use `run_command` with find/xargs for efficiency
7. Never delete system files or hidden config files unless explicitly asked
8. When organizing, follow common conventions (src/, docs/, tests/, etc.)
9. Call `done` with a summary of all changes made
10. Call `stuck` if permissions prevent operations or paths don't exist
"""


class FileAgent(BaseAgent):
    """Autonomous file management agent — organizes, finds, and manages files."""

    @property
    def agent_name(self):
        return "File Agent"

    @property
    def agent_emoji(self):
        return "📁"

    @property
    def system_prompt(self):
        return FILE_AGENT_PROMPT

    @property
    def tools(self):
        return [
            TOOL_READ_FILE, TOOL_WRITE_FILE, TOOL_LIST_DIR, TOOL_SEARCH_FILES,
            TOOL_MOVE, TOOL_COPY, TOOL_DELETE, TOOL_TREE, TOOL_DISK_USAGE,
            TOOL_COMPRESS, TOOL_EXTRACT_ARCHIVE, TOOL_RUN_COMMAND,
            TOOL_DONE, TOOL_STUCK,
        ]

    def _dispatch(self, name, inp):
        """Route file management tool calls."""
        try:
            if name == "read_file":
                result = read_file(inp["path"])
                return result.get("content", str(result))

            elif name == "write_file":
                result = write_file(inp["path"], inp["content"])
                return result.get("content", str(result))

            elif name == "list_dir":
                result = list_directory(inp["path"])
                return result.get("content", str(result))

            elif name == "search_files":
                return self._search_files(
                    inp["pattern"],
                    inp.get("directory", os.getcwd()),
                    inp.get("content_search", False)
                )

            elif name == "move":
                result = move_file(inp["source"], inp["destination"])
                return result.get("content", str(result))

            elif name == "copy":
                return self._copy(inp["source"], inp["destination"])

            elif name == "delete":
                result = delete_file(inp["path"], inp.get("recursive", False))
                return result.get("content", str(result))

            elif name == "tree":
                return self._tree(inp["path"], inp.get("depth", 3))

            elif name == "disk_usage":
                return self._disk_usage(inp["path"])

            elif name == "compress":
                return self._compress(inp["paths"], inp["output"])

            elif name == "extract_archive":
                return self._extract_archive(inp["archive"], inp["destination"])

            elif name == "run_command":
                result = run_terminal(inp["command"], timeout=inp.get("timeout", 60))
                return result.get("content", str(result))

            return f"Unknown file tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _search_files(self, pattern, directory, content_search):
        """Search files by name or content."""
        try:
            directory = os.path.expanduser(directory)
            if content_search:
                result = run_terminal(
                    f"grep -rn '{pattern}' '{directory}' --include='*' 2>/dev/null | head -50",
                    timeout=15
                )
            else:
                result = run_terminal(
                    f"find '{directory}' -name '{pattern}' -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/venv/*' 2>/dev/null | head -50",
                    timeout=15
                )
            return result.get("content", "(no results)")
        except Exception as e:
            return f"ERROR searching: {e}"

    def _copy(self, source, destination):
        """Copy file or directory."""
        try:
            src = os.path.expanduser(source)
            dst = os.path.expanduser(destination)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return f"Copied {source} → {destination}"
        except Exception as e:
            return f"ERROR copying: {e}"

    def _tree(self, path, depth):
        """Show directory tree."""
        result = run_terminal(
            f"find '{os.path.expanduser(path)}' -maxdepth {depth} -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/venv/*' | head -100 | sed 's|[^/]*/|  |g'",
            timeout=10
        )
        return result.get("content", "(empty)")

    def _disk_usage(self, path):
        """Get disk usage."""
        result = run_terminal(f"du -sh '{os.path.expanduser(path)}' 2>/dev/null", timeout=10)
        return result.get("content", "unknown")

    def _compress(self, paths, output):
        """Compress files into archive."""
        try:
            paths_str = " ".join(f"'{os.path.expanduser(p)}'" for p in paths)
            output = os.path.expanduser(output)
            if output.endswith(".zip"):
                cmd = f"zip -r '{output}' {paths_str}"
            elif output.endswith(".tar.gz") or output.endswith(".tgz"):
                cmd = f"tar -czf '{output}' {paths_str}"
            else:
                cmd = f"tar -cf '{output}' {paths_str}"
            result = run_terminal(cmd, timeout=120)
            if result.get("success"):
                return f"✅ Compressed to {output}"
            return result.get("content", "Compression failed")
        except Exception as e:
            return f"ERROR compressing: {e}"

    def _extract_archive(self, archive, destination):
        """Extract an archive."""
        try:
            archive = os.path.expanduser(archive)
            destination = os.path.expanduser(destination)
            os.makedirs(destination, exist_ok=True)
            if archive.endswith(".zip"):
                cmd = f"unzip -o '{archive}' -d '{destination}'"
            elif archive.endswith(".tar.gz") or archive.endswith(".tgz"):
                cmd = f"tar -xzf '{archive}' -C '{destination}'"
            elif archive.endswith(".tar"):
                cmd = f"tar -xf '{archive}' -C '{destination}'"
            else:
                return f"Unknown archive format: {archive}"
            result = run_terminal(cmd, timeout=120)
            if result.get("success"):
                return f"✅ Extracted {archive} to {destination}"
            return result.get("content", "Extraction failed")
        except Exception as e:
            return f"ERROR extracting: {e}"
