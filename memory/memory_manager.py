"""
╔══════════════════════════════════════════╗
║      TARS — Memory Manager               ║
╚══════════════════════════════════════════╝

Persistent memory: context, preferences, project notes, history.
Hybrid: flat-file keyword search + ChromaDB semantic search.
"""

import os
import json
import threading
from datetime import datetime

# Lazy import — created in __init__ if chromadb available
_semantic = None

# Lock for thread-safe history file appends
_history_lock = threading.Lock()


class MemoryManager:
    def __init__(self, config, base_dir):
        global _semantic
        self.base_dir = base_dir
        self.context_file = os.path.join(base_dir, config["memory"]["context_file"])
        self.preferences_file = os.path.join(base_dir, config["memory"]["preferences_file"])
        self.history_file = os.path.join(base_dir, config["memory"]["history_file"])
        self.projects_dir = os.path.join(base_dir, config["memory"]["projects_dir"])
        self.max_history_context = config["memory"]["max_history_context"]

        # Ensure directories exist
        os.makedirs(os.path.dirname(self.context_file), exist_ok=True)
        os.makedirs(self.projects_dir, exist_ok=True)

        # Initialize semantic memory (ChromaDB) — graceful if unavailable
        try:
            from memory.semantic_memory import SemanticMemory
            _semantic = SemanticMemory(base_dir=base_dir, config=config)
            self.semantic = _semantic
        except Exception:
            self.semantic = None

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
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)  # Atomic on POSIX

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
        """Append an action to the history log. Auto-rotates at 10MB. Thread-safe."""
        with _history_lock:
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
            try:
                with open(self.history_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass  # Don't crash on history write failure

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
        """Save a memory entry. Uses key-based dedup (updates existing, not appends).
        Also stores in semantic memory (ChromaDB) for vector search."""
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

        # Mirror to semantic memory for vector search
        if self.semantic and self.semantic.available:
            self.semantic.store_knowledge(key, f"[{category}] {value}", category=category)

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
        """Search memory for relevant information. Hybrid: keyword + semantic search."""
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

        # ── Semantic search (ChromaDB) — augments keyword results ──
        if self.semantic and self.semantic.available:
            semantic_result = self.semantic.recall(query, n_results=5)
            if semantic_result.get("success") and "No semantic matches" not in semantic_result.get("content", ""):
                results.append(f"\n── Semantic Memory ──\n{semantic_result['content']}")

        if results:
            return {"success": True, "content": "\n\n".join(results[:10])}
        else:
            return {"success": True, "content": f"No memories found matching '{query}'"}

    # ─── List All Memories ───────────────────────────

    def list_all(self, category=None):
        """List all stored memories, optionally filtered by category.
        
        Returns a clean, categorized breakdown of everything TARS remembers.
        """
        sections = []

        def _parse_entries(filepath, label):
            """Extract - **key**: value entries from a markdown file."""
            import re
            content = self._read(filepath)
            if not content or content.strip() in ("", "_Learning..._", "_No active task._"):
                return None
            entries = re.findall(r'^- \*\*(.+?)\*\*:\s*(.+)$', content, re.MULTILINE)
            if not entries:
                return None
            lines = [f"  • {key}: {value}" for key, value in entries]
            return f"📂 {label} ({len(entries)} entries)\n" + "\n".join(lines)

        cats = {
            "preference": (self.preferences_file, "Preferences"),
            "credential": (os.path.join(self.base_dir, "memory", "credentials.md"), "Credentials"),
            "learned": (os.path.join(self.base_dir, "memory", "learned.md"), "Learned Patterns"),
            "context": (self.context_file, "Context"),
        }

        # If filtering by category
        if category and category in cats:
            filepath, label = cats[category]
            block = _parse_entries(filepath, label)
            if block:
                return {"success": True, "content": block}
            return {"success": True, "content": f"No {label.lower()} memories stored."}

        # Projects (special — one file per project)
        if category is None or category == "project":
            if os.path.exists(self.projects_dir):
                project_files = [f for f in os.listdir(self.projects_dir) if f.endswith(".md") and f != ".gitkeep"]
                if project_files:
                    plines = []
                    for pf in project_files:
                        content = self._read(os.path.join(self.projects_dir, pf))
                        preview = content.replace("\n", " ").strip()[:120]
                        plines.append(f"  • {pf[:-3]}: {preview}")
                    sections.append(f"📂 Projects ({len(project_files)} entries)\n" + "\n".join(plines))
            if category == "project":
                return {"success": True, "content": sections[0] if sections else "No project memories stored."}

        # All categories
        if category is None:
            for cat_key, (filepath, label) in cats.items():
                if os.path.exists(filepath):
                    block = _parse_entries(filepath, label)
                    if block:
                        sections.append(block)

        # History summary
        if category is None or category == "history":
            try:
                with open(self.history_file, "r") as f:
                    lines = f.readlines()
                total = len(lines)
                if total > 0:
                    successes = sum(1 for l in lines if '"success": true' in l.lower())
                    sections.append(f"📂 Action History ({total} entries, {successes} successful)")
                if category == "history":
                    return {"success": True, "content": sections[-1] if sections else "No action history."}
            except FileNotFoundError:
                if category == "history":
                    return {"success": True, "content": "No action history."}

        # Agent memories
        if category is None or category == "agent":
            agents_dir = os.path.join(self.base_dir, "memory", "agents")
            if os.path.exists(agents_dir):
                agent_lines = []
                for af in sorted(os.listdir(agents_dir)):
                    if not af.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(agents_dir, af)) as f:
                            data = json.load(f)
                        stats = data.get("stats", {})
                        total = stats.get("total_tasks", 0)
                        success = stats.get("successes", 0)
                        if total > 0:
                            agent_lines.append(f"  • {af[:-5]}: {success}/{total} tasks succeeded")
                    except Exception:
                        continue
                if agent_lines:
                    sections.append(f"📂 Agent Learning ({len(agent_lines)} agents)\n" + "\n".join(agent_lines))
            if category == "agent":
                return {"success": True, "content": sections[-1] if sections else "No agent memories."}

        if sections:
            header = f"🧠 TARS Memory — {len(sections)} categories\n{'─' * 40}"
            return {"success": True, "content": header + "\n\n" + "\n\n".join(sections)}
        else:
            return {"success": True, "content": "Memory is empty. I'm a blank slate."}

    # ─── Delete Memory ───────────────────────────────

    def delete(self, category, key=None):
        """Delete a specific memory entry or an entire category.
        
        Args:
            category: Which category to delete from (preference, credential, learned, context, project, history, agent, all)
            key: Optional specific key to delete. If None, deletes the entire category.
        
        Returns:
            Standard tool result dict
        """
        import re

        def _delete_entry(filepath, key, default_header=""):
            """Remove a specific - **key**: ... entry from a markdown file."""
            if not os.path.exists(filepath):
                return False
            content = self._read(filepath)
            pattern = re.compile(r'^- \*\*' + re.escape(key) + r'\*\*:.*\n?', re.MULTILINE)
            if not pattern.search(content):
                return False
            updated = pattern.sub('', content)
            self._write(filepath, updated)
            return True

        def _clear_file(filepath, default_content=""):
            """Clear a file to its default state."""
            if os.path.exists(filepath):
                self._write(filepath, default_content)
                return True
            return False

        cats_files = {
            "preference": (self.preferences_file, "# TARS — Abdullah's Preferences\n\n_Learning..._\n"),
            "credential": (os.path.join(self.base_dir, "memory", "credentials.md"), "# Saved Credentials\n"),
            "learned": (os.path.join(self.base_dir, "memory", "learned.md"), "# Learned Patterns\n"),
            "context": (self.context_file, "# TARS — Current Context\n\n_No active task._\n"),
        }

        # Delete everything
        if category == "all":
            count = 0
            for cat_key, (filepath, default) in cats_files.items():
                if _clear_file(filepath, default):
                    count += 1
            # Clear history
            if _clear_file(self.history_file, ""):
                count += 1
            # Clear projects
            if os.path.exists(self.projects_dir):
                for pf in os.listdir(self.projects_dir):
                    if pf.endswith(".md") and pf != ".gitkeep":
                        os.remove(os.path.join(self.projects_dir, pf))
                        count += 1
            # Clear agent memories
            agents_dir = os.path.join(self.base_dir, "memory", "agents")
            if os.path.exists(agents_dir):
                for af in os.listdir(agents_dir):
                    if af.endswith(".json"):
                        os.remove(os.path.join(agents_dir, af))
                        count += 1
            # Clear semantic memory
            if self.semantic and self.semantic.available:
                try:
                    self.semantic.clear_all()
                except Exception:
                    pass
            return {"success": True, "content": f"🧹 Wiped all memory ({count} files cleared). Starting fresh."}

        # Delete specific key from a category
        if key and category in cats_files:
            filepath, _ = cats_files[category]
            if _delete_entry(filepath, key):
                # Also remove from semantic memory
                if self.semantic and self.semantic.available:
                    try:
                        import hashlib
                        doc_id = hashlib.md5(f"knowledge:{key}".encode()).hexdigest()
                        self.semantic._collections["knowledge"].delete(ids=[doc_id])
                    except Exception:
                        pass
                return {"success": True, "content": f"🗑️ Deleted '{key}' from {category}."}
            return {"success": False, "error": True, "content": f"Key '{key}' not found in {category}."}

        # Delete a project
        if category == "project":
            if key:
                pf = os.path.join(self.projects_dir, f"{key}.md")
                if os.path.exists(pf):
                    os.remove(pf)
                    return {"success": True, "content": f"🗑️ Deleted project '{key}'."}
                return {"success": False, "error": True, "content": f"Project '{key}' not found."}
            # Clear all projects
            count = 0
            for pf in os.listdir(self.projects_dir):
                if pf.endswith(".md") and pf != ".gitkeep":
                    os.remove(os.path.join(self.projects_dir, pf))
                    count += 1
            return {"success": True, "content": f"🗑️ Cleared all projects ({count} deleted)."}

        # Delete agent memory
        if category == "agent":
            agents_dir = os.path.join(self.base_dir, "memory", "agents")
            if key:
                af = os.path.join(agents_dir, f"{key.lower().replace(' ', '_')}.json")
                if os.path.exists(af):
                    os.remove(af)
                    return {"success": True, "content": f"🗑️ Cleared {key} agent memory."}
                return {"success": False, "error": True, "content": f"Agent '{key}' memory not found."}
            # Clear all agent memories
            count = 0
            for af in os.listdir(agents_dir):
                if af.endswith(".json"):
                    os.remove(os.path.join(agents_dir, af))
                    count += 1
            return {"success": True, "content": f"🗑️ Cleared all agent memories ({count} agents reset)."}

        # Delete history
        if category == "history":
            if _clear_file(self.history_file, ""):
                return {"success": True, "content": "🗑️ Action history cleared."}
            return {"success": True, "content": "History already empty."}

        # Clear entire category (no specific key)
        if category in cats_files and key is None:
            filepath, default = cats_files[category]
            _clear_file(filepath, default)
            return {"success": True, "content": f"🗑️ Cleared all {category} memories."}

        return {"success": False, "error": True, "content": f"Unknown category: {category}. Use: preference, credential, learned, context, project, history, agent, or all."}
