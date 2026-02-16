"""
╔══════════════════════════════════════════╗
║      TARS — Memory Manager               ║
╚══════════════════════════════════════════╝

Persistent memory: context, preferences, project notes, history.
"""

import os
import json
from datetime import datetime


class MemoryManager:
    def __init__(self, config, base_dir):
        self.base_dir = base_dir
        self.context_file = os.path.join(base_dir, config["memory"]["context_file"])
        self.preferences_file = os.path.join(base_dir, config["memory"]["preferences_file"])
        self.history_file = os.path.join(base_dir, config["memory"]["history_file"])
        self.projects_dir = os.path.join(base_dir, config["memory"]["projects_dir"])
        self.max_history_context = config["memory"]["max_history_context"]

        # Ensure directories exist
        os.makedirs(os.path.dirname(self.context_file), exist_ok=True)
        os.makedirs(self.projects_dir, exist_ok=True)

        # Create default files if they don't exist
        self._init_files()

    def _init_files(self):
        if not os.path.exists(self.context_file):
            self._write(self.context_file, "# TARS — Current Context\n\n_No active task._\n")
        if not os.path.exists(self.preferences_file):
            self._write(self.preferences_file, "# TARS — Abdullah's Preferences\n\n_Learning..._\n")
        if not os.path.exists(self.history_file):
            self._write(self.history_file, "")

    def _write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _read(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    # ─── Context ─────────────────────────────────────

    def get_context_summary(self):
        """Get full memory context for the system prompt."""
        parts = []

        # Current context
        ctx = self._read(self.context_file)
        if ctx.strip():
            parts.append(f"### Current Context\n{ctx}")

        # Preferences
        prefs = self._read(self.preferences_file)
        if prefs.strip():
            parts.append(f"### Preferences\n{prefs}")

        # Recent history
        history = self._get_recent_history(10)
        if history:
            parts.append(f"### Recent Actions\n{history}")

        return "\n\n".join(parts) if parts else "_No memory yet._"

    def get_active_project(self):
        """Get the name of the active project from context."""
        ctx = self._read(self.context_file)
        for line in ctx.split("\n"):
            if "project" in line.lower() and ":" in line:
                return line.split(":", 1)[1].strip()
        return "None"

    def update_context(self, content):
        """Update the current context file."""
        self._write(self.context_file, content)

    # ─── Preferences ─────────────────────────────────

    def get_preferences(self):
        return self._read(self.preferences_file)

    def update_preferences(self, content):
        self._write(self.preferences_file, content)

    # ─── History ─────────────────────────────────────

    def log_action(self, action, input_data, result):
        """Append an action to the history log. Auto-rotates at 10MB."""
        # Rotate if file is too large
        try:
            if os.path.exists(self.history_file) and os.path.getsize(self.history_file) > 10_000_000:
                import time as _t
                archive = self.history_file + f".{int(_t.time())}.bak"
                os.rename(self.history_file, archive)
        except Exception:
            pass

        entry = {
            "ts": datetime.now().isoformat(),
            "action": action,
            "input": str(input_data)[:500],
            "result": str(result)[:500],
            "success": result.get("success", False) if isinstance(result, dict) else True,
        }
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _get_recent_history(self, n=10):
        """Get the last N actions from history."""
        try:
            with open(self.history_file, "r") as f:
                lines = f.readlines()
            recent = lines[-n:] if len(lines) > n else lines
            summaries = []
            for line in recent:
                try:
                    entry = json.loads(line)
                    status = "✅" if entry.get("success") else "❌"
                    summaries.append(f"{status} {entry['action']}: {entry['input'][:80]}")
                except json.JSONDecodeError:
                    continue
            return "\n".join(summaries)
        except FileNotFoundError:
            return ""

    # ─── Save/Recall (for Claude tool calls) ─────────

    def save(self, category, key, value):
        """Save a memory entry. Uses key-based dedup (updates existing, not appends)."""
        if category == "preference":
            self._upsert_entry(self.preferences_file, key, value, "# TARS — Abdullah's Preferences\n")
        elif category == "project":
            project_file = os.path.join(self.projects_dir, f"{key}.md")
            self._write(project_file, f"# Project: {key}\n\n{value}\n")
        elif category == "context":
            self._upsert_entry(self.context_file, key, value, "# TARS — Current Context\n")
        elif category == "note":
            self.log_action("note", key, {"success": True, "content": value})
        elif category == "credential":
            cred_file = os.path.join(self.base_dir, "memory", "credentials.md")
            self._upsert_entry(cred_file, key, value, "# Saved Credentials\n")
        elif category == "learned":
            learned_file = os.path.join(self.base_dir, "memory", "learned.md")
            self._upsert_entry(learned_file, key, value, "# Learned Patterns\n")

        return {"success": True, "content": f"Saved to {category}: {key}"}

    def _upsert_entry(self, filepath, key, value, default_header=""):
        """Update existing key in a markdown file, or append if new.
        
        Prevents unbounded growth by:
          1. Replacing existing **key**: ... lines (dedup)
          2. Capping total file size at 50KB
        """
        import re
        
        existing = self._read(filepath) if os.path.exists(filepath) else default_header
        
        # Pattern: - **key**: ...  (match the entire line)
        pattern = re.compile(r'^- \*\*' + re.escape(key) + r'\*\*:.*$', re.MULTILINE)
        new_line = f"- **{key}**: {value}"
        
        if pattern.search(existing):
            # Update in place
            updated = pattern.sub(new_line, existing)
        else:
            # Append
            updated = existing.rstrip() + f"\n{new_line}"
        
        # Cap file size at 50KB — trim oldest entries if exceeded
        if len(updated.encode('utf-8')) > 50_000:
            lines = updated.split('\n')
            # Keep header (first 2 lines) + last entries that fit
            header = '\n'.join(lines[:2])
            body_lines = lines[2:]
            # Remove oldest entries (from the front) until under limit
            while body_lines and len(('\n'.join([header] + body_lines)).encode('utf-8')) > 50_000:
                body_lines.pop(0)
            updated = header + '\n' + '\n'.join(body_lines)
        
        self._write(filepath, updated)

    def recall(self, query):
        """Search memory for relevant information. Uses token matching."""
        results = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        def _matches(text):
            """Check if query or any query token matches text."""
            text_lower = text.lower()
            if query_lower in text_lower:
                return True
            # Token match: at least half of query tokens found
            matches = sum(1 for t in query_tokens if t in text_lower)
            return matches >= max(1, len(query_tokens) // 2)

        # Search context
        ctx = self._read(self.context_file)
        if _matches(ctx):
            results.append(f"[Context] {ctx[:500]}")

        # Search preferences
        prefs = self._read(self.preferences_file)
        if _matches(prefs):
            results.append(f"[Preferences] {prefs[:500]}")

        # Search project files
        if os.path.exists(self.projects_dir):
            for fname in os.listdir(self.projects_dir):
                content = self._read(os.path.join(self.projects_dir, fname))
                if _matches(content):
                    results.append(f"[Project: {fname}] {content[:500]}")

        # Search credentials
        cred_file = os.path.join(self.base_dir, "memory", "credentials.md")
        if os.path.exists(cred_file):
            creds = self._read(cred_file)
            if _matches(creds):
                results.append(f"[Credentials] {creds[:500]}")

        # Search learned patterns
        learned_file = os.path.join(self.base_dir, "memory", "learned.md")
        if os.path.exists(learned_file):
            learned = self._read(learned_file)
            if _matches(learned):
                results.append(f"[Learned] {learned[:500]}")

        # Search recent history
        try:
            with open(self.history_file, "r") as f:
                for line in f:
                    if _matches(line):
                        results.append(f"[History] {line.strip()[:200]}")
        except FileNotFoundError:
            pass

        if results:
            return {"success": True, "content": "\n\n".join(results[:10])}
        else:
            return {"success": True, "content": f"No memories found matching '{query}'"}
