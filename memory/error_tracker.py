"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Error Tracker + Fix Registry                     ║
╠══════════════════════════════════════════════════════════════╣
║  Persistent log of every error TARS encounters, paired with  ║
║  known fixes. Over time, TARS auto-heals from past lessons.  ║
║                                                              ║
║  Flow:                                                       ║
║    1. Error happens → tracker.record_error(...)              ║
║    2. If a fix is known → return it immediately              ║
║    3. If fix is found later → tracker.record_fix(...)        ║
║    4. Next time same error → auto-apply the fix              ║
║                                                              ║
║  "Every error is a lesson. The second time is a choice."     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import time
import traceback
import threading
from datetime import datetime
from typing import Dict, Optional, List

from utils.event_bus import event_bus

import logging
logger = logging.getLogger("TARS")


# ─── Constants ──────────────────────────────────────
TARS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER_DB = os.path.join(TARS_ROOT, "memory", "error_tracker.json")
MAX_ENTRIES = 200
MAX_FIXES_PER_ERROR = 5


# ─── Fix Hint Patterns ─────────────────────────────
# Pattern-matched guidance so the dev agent knows what kind of fix is needed.
# Each entry: (regex_on_error, hint_text, likely_files)
_FIX_HINT_PATTERNS = [
    # Missing / wrong tool params
    (r"KeyError:\s*['\"](\w+)['\"]",
     "A required parameter '{0}' is missing from the tool call. "
     "Check brain/tools.py schema — the param may need a default, or the brain prompt "
     "needs to specify it. Also check executor.py dispatch for the tool.",
     ["brain/tools.py", "executor.py"]),

    (r"Unknown tool:\s*(\w+)",
     "The brain hallucinated tool '{0}' which doesn't exist. "
     "Either add it (schema in brain/tools.py, handler in executor.py) or "
     "update brain/prompts.py to stop the LLM from inventing tools.",
     ["brain/tools.py", "executor.py", "brain/prompts.py"]),

    # AppleScript failures
    (r"osascript.*error|AppleScript|NSAppleScript",
     "AppleScript execution failed. Common causes: unescaped quotes/backslashes, "
     "Unicode characters, or the target app (Mail, Messages) not running. "
     "Check string escaping in the AppleScript template.",
     ["hands/mac_control.py", "voice/imessage_send.py"]),

    # Browser agent stuck
    (r"Agent stuck:.*form|page|element|click|type",
     "Browser agent couldn't interact with a page element. "
     "Possible causes: wrong CSS selector, element not visible, page didn't load, "
     "or anti-bot detection. Check browser.py action functions and the agent's "
     "system prompt for better selectors/wait strategies.",
     ["hands/browser.py", "agents/browser_agent.py", "hands/browser_agent.py"]),

    # LLM API errors
    (r"rate.?limit|429|resource_exhausted|quota",
     "LLM API rate limit hit. The failover system should handle this. "
     "If recurring: increase backoff delays in brain/planner.py _retry_with_backoff(), "
     "or switch the agent_llm to a different provider in config.yaml.",
     ["brain/planner.py", "brain/llm_client.py"]),

    (r"API key.*expired|PERMISSION_DENIED|leaked|invalid.*key",
     "API key is invalid/revoked. Rotate the key in config.yaml for the affected "
     "provider. Check brain/llm_client.py for which provider is failing.",
     ["brain/llm_client.py"]),

    # File/path errors
    (r"FileNotFoundError|No such file|ENOENT",
     "A file path doesn't exist. Check if the path is hardcoded vs dynamic. "
     "May need os.path.exists() guard or os.makedirs() for the parent directory.",
     ["hands/file_manager.py"]),

    (r"PermissionError|Permission denied|EACCES",
     "Permission denied on a file or system resource. On macOS, check if the app "
     "has Full Disk Access in System Preferences → Privacy & Security.",
     []),

    # Email errors
    (r"mail.*error|SMTP|email.*fail|outbox.*stuck",
     "Email sending failed. Check hands/email.py for Mail.app AppleScript issues, "
     "SMTP config, or Exchange/IMAP delays. For attachments, the compose window "
     "needs visible:true and a delay before send.",
     ["hands/email.py", "hands/mac_control.py"]),

    # Tool return format
    (r"'(success|content|error)'.*(missing|KeyError|NoneType)",
     "A tool handler isn't returning the standard {{success, content}} dict. "
     "Every handler in hands/*, voice/*, memory/* MUST return "
     "{{'success': True/False, 'content': str}}. Check the handler.",
     ["executor.py"]),

    # Agent loop / stuck patterns
    (r"Agent.*FAILED after \d+ steps|max.*steps|loop.*detect",
     "Agent hit the step limit or was caught in a loop. "
     "Check agents/base_agent.py for loop detection thresholds and "
     "the agent's system prompt for better termination instructions.",
     ["agents/base_agent.py"]),

    # JSON / parsing errors
    (r"JSONDecodeError|json\.loads|Expecting value",
     "JSON parsing failed on an API response or file. The data may be HTML "
     "(error page), truncated, or malformed. Add try/except around json.loads() "
     "and handle the raw text gracefully.",
     []),

    # Connection / network errors
    (r"ConnectionError|ConnectionRefused|timeout|timed out|URLError",
     "Network request failed. Could be transient (retry) or the service is down. "
     "Add retry logic with exponential backoff if not already present.",
     []),

    # Import / module errors
    (r"ImportError|ModuleNotFoundError|No module named",
     "Missing Python module. Either add it to requirements.txt and pip install, "
     "or fix the import path. TARS uses absolute imports from repo root.",
     ["requirements.txt"]),
]


class ErrorEntry:
    """A recorded error with optional fix."""

    def __init__(self, signature: str, context: str, raw_error: str,
                 tool: str = "", agent: str = "", details: str = "",
                 source_file: str = "", params: dict = None,
                 traceback_str: str = "", fix_hint: str = "",
                 fix_hint_files: list = None):
        self.signature = signature
        self.context = context
        self.raw_error = raw_error[:500]
        self.tool = tool
        self.agent = agent
        self.details = details[:300]
        self.source_file = source_file      # Which file/handler raised the error
        self.traceback_str = traceback_str[:1000]  # Stack trace for exact code location
        self.fix_hint = fix_hint[:500]       # Pattern-matched guidance for the dev agent
        self.fix_hint_files = fix_hint_files or []  # Likely files to edit
        self.sample_params = []             # Last 3 tool inputs that caused this error
        self.count = 1
        self.first_seen = datetime.now().isoformat()
        self.last_seen = datetime.now().isoformat()
        self.fixes = []          # [{fix, applied_at, success, source}]
        self.auto_fixable = False  # True once a fix has succeeded
        self.fixed_count = 0     # Times auto-fix was applied
        if params:
            self.sample_params.append(params)

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "context": self.context,
            "raw_error": self.raw_error,
            "tool": self.tool,
            "agent": self.agent,
            "details": self.details,
            "source_file": self.source_file,
            "traceback": self.traceback_str,
            "fix_hint": self.fix_hint,
            "fix_hint_files": self.fix_hint_files,
            "sample_params": self.sample_params[-3:],  # Keep last 3 samples
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "fixes": self.fixes,
            "auto_fixable": self.auto_fixable,
            "fixed_count": self.fixed_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ErrorEntry":
        entry = cls(
            signature=d["signature"],
            context=d["context"],
            raw_error=d.get("raw_error", ""),
            tool=d.get("tool", ""),
            agent=d.get("agent", ""),
            details=d.get("details", ""),
            source_file=d.get("source_file", ""),
            traceback_str=d.get("traceback", ""),
            fix_hint=d.get("fix_hint", ""),
            fix_hint_files=d.get("fix_hint_files", []),
        )
        entry.sample_params = d.get("sample_params", [])
        entry.count = d.get("count", 1)
        entry.first_seen = d.get("first_seen", datetime.now().isoformat())
        entry.last_seen = d.get("last_seen", datetime.now().isoformat())
        entry.fixes = d.get("fixes", [])
        entry.auto_fixable = d.get("auto_fixable", False)
        entry.fixed_count = d.get("fixed_count", 0)
        return entry


class ErrorTracker:
    """Persistent error tracker with fix registry.

    Records every error, deduplicates by signature, and maintains a registry
    of known fixes. When the same error recurs and a fix is known, it returns
    the fix so the caller can auto-apply.
    """

    def __init__(self):
        self._entries: Dict[str, ErrorEntry] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load()

    # ═══════════════════════════════════════════════════
    #  PUBLIC API
    # ═══════════════════════════════════════════════════

    def record_error(self, error: str, context: str = "", tool: str = "",
                     agent: str = "", details: str = "",
                     source_file: str = "", params: dict = None,
                     tb: str = "") -> Optional[dict]:
        """Record an error occurrence.

        Args:
            error:       The error message (will be normalized for dedup).
            context:     Where it happened (tool name, "task_processing", etc.).
            tool:        The specific tool that failed.
            agent:       The agent type if an agent was involved.
            details:     Human-readable context (what was the task/input).
            source_file: Which source file raised the error (e.g. "executor.py").
            params:      The actual tool input params (stored as sample for debugging).
            tb:          Explicit traceback string. If empty, auto-captures the
                         current exception traceback (if called from an except block).

        Returns:
            dict with fix info if a known fix exists, None otherwise.
            {"has_fix": True, "fix": "...", "confidence": 0.9, "source": "..."}
        """
        sig = self._normalize(error)
        key = f"{context}:{sig}" if context else sig

        # Auto-capture traceback if we're inside an except block and none provided
        if not tb:
            import sys
            exc_info = sys.exc_info()
            if exc_info[2] is not None:
                tb = "".join(traceback.format_exception(*exc_info))[-1000:]

        # Auto-match fix hints from patterns
        hint, hint_files = self._match_fix_hint(error)

        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.count += 1
                entry.last_seen = datetime.now().isoformat()
                # Update details if we have more info now
                if details and len(details) > len(entry.details):
                    entry.details = details[:300]
                # Update source_file if newly provided
                if source_file and not entry.source_file:
                    entry.source_file = source_file
                # Update traceback if we have a better one
                if tb and (not entry.traceback_str or len(tb) > len(entry.traceback_str)):
                    entry.traceback_str = tb[:1000]
                # Update fix hint if newly matched
                if hint and not entry.fix_hint:
                    entry.fix_hint = hint
                    entry.fix_hint_files = hint_files
                # Store sample params (keep last 3 for pattern analysis)
                if params:
                    entry.sample_params.append(params)
                    entry.sample_params = entry.sample_params[-3:]
            else:
                entry = ErrorEntry(
                    signature=sig,
                    context=context,
                    raw_error=error,
                    tool=tool,
                    agent=agent,
                    details=details,
                    source_file=source_file,
                    params=params,
                    traceback_str=tb,
                    fix_hint=hint,
                    fix_hint_files=hint_files,
                )
                self._entries[key] = entry

            self._dirty = True

            # Emit event for dashboard
            event_bus.emit("error_tracked", {
                "signature": sig,
                "context": context,
                "tool": tool,
                "count": entry.count,
                "has_fix": entry.auto_fixable,
            })

            # Auto-save every 10 new errors
            total = sum(e.count for e in self._entries.values())
            if total % 10 == 0:
                self._save()

            # Check if we have a known fix
            if entry.auto_fixable and entry.fixes:
                best_fix = self._get_best_fix(entry)
                if best_fix:
                    entry.fixed_count += 1
                    return {
                        "has_fix": True,
                        "fix": best_fix["fix"],
                        "confidence": best_fix.get("confidence", 0.8),
                        "source": best_fix.get("source", "learned"),
                        "times_applied": entry.fixed_count,
                    }

        return None

    def record_fix(self, error: str, fix: str, context: str = "",
                   source: str = "manual", success: bool = True,
                   confidence: float = 0.8) -> bool:
        """Record a fix for a known error.

        Args:
            error: The error string (will be normalized to match)
            fix: Description of the fix (natural language or code action)
            context: Tool/agent context
            source: "manual", "self_heal", "user", "auto"
            success: Whether this fix actually worked
            confidence: 0.0-1.0 how reliable this fix is

        Returns:
            True if recorded successfully
        """
        sig = self._normalize(error)
        key = f"{context}:{sig}" if context else sig

        with self._lock:
            if key not in self._entries:
                # Create entry for the error if it doesn't exist yet
                self._entries[key] = ErrorEntry(
                    signature=sig,
                    context=context,
                    raw_error=error[:500],
                )

            entry = self._entries[key]
            fix_record = {
                "fix": fix[:500],
                "source": source,
                "success": success,
                "confidence": confidence,
                "applied_at": datetime.now().isoformat(),
            }
            entry.fixes.append(fix_record)

            # Keep only the most recent fixes
            if len(entry.fixes) > MAX_FIXES_PER_ERROR:
                entry.fixes = entry.fixes[-MAX_FIXES_PER_ERROR:]

            # Mark as auto-fixable if at least one successful fix
            if success and confidence >= 0.7:
                entry.auto_fixable = True

            self._dirty = True
            self._save()

            event_bus.emit("fix_recorded", {
                "signature": sig,
                "context": context,
                "fix": fix[:200],
                "source": source,
                "auto_fixable": entry.auto_fixable,
            })

            return True

    def mark_fix_failed(self, error: str, context: str = ""):
        """Mark the latest fix for an error as failed (it didn't actually work)."""
        sig = self._normalize(error)
        key = f"{context}:{sig}" if context else sig

        with self._lock:
            entry = self._entries.get(key)
            if entry and entry.fixes:
                entry.fixes[-1]["success"] = False
                entry.fixes[-1]["confidence"] = max(0, entry.fixes[-1]["confidence"] - 0.3)

                # If all fixes have failed, no longer auto-fixable
                if not any(f["success"] for f in entry.fixes):
                    entry.auto_fixable = False

                self._dirty = True
                self._save()

    def get_known_fix(self, error: str, context: str = "") -> Optional[dict]:
        """Check if we have a known fix for an error without recording it.

        Returns:
            {"fix": "...", "confidence": 0.9, "source": "..."} or None
        """
        sig = self._normalize(error)
        key = f"{context}:{sig}" if context else sig

        with self._lock:
            entry = self._entries.get(key)
            if entry and entry.auto_fixable and entry.fixes:
                return self._get_best_fix(entry)
        return None

    def get_top_errors(self, n: int = 10) -> List[dict]:
        """Get the N most frequent errors (for dashboard/diagnostics)."""
        with self._lock:
            sorted_entries = sorted(
                self._entries.values(),
                key=lambda e: e.count,
                reverse=True,
            )
            return [e.to_dict() for e in sorted_entries[:n]]

    def get_unfixed_errors(self, min_count: int = 2) -> List[dict]:
        """Get errors that keep recurring but have no fix yet."""
        with self._lock:
            unfixed = [
                e.to_dict() for e in self._entries.values()
                if not e.auto_fixable and e.count >= min_count
            ]
            unfixed.sort(key=lambda e: e["count"], reverse=True)
            return unfixed

    def get_auto_fixable(self) -> List[dict]:
        """Get all errors that have known auto-fixes."""
        with self._lock:
            return [
                e.to_dict() for e in self._entries.values()
                if e.auto_fixable
            ]

    def get_stats(self) -> dict:
        """Get tracker statistics for dashboard."""
        with self._lock:
            total_errors = len(self._entries)
            total_occurrences = sum(e.count for e in self._entries.values())
            fixable = sum(1 for e in self._entries.values() if e.auto_fixable)
            unfixed = sum(1 for e in self._entries.values() if not e.auto_fixable and e.count >= 2)
            total_fixes_applied = sum(e.fixed_count for e in self._entries.values())

            return {
                "unique_errors": total_errors,
                "total_occurrences": total_occurrences,
                "auto_fixable": fixable,
                "unfixed_recurring": unfixed,
                "total_fixes_applied": total_fixes_applied,
                "fix_rate": f"{(fixable / max(total_errors, 1)) * 100:.0f}%",
            }

    def get_error_report(self) -> str:
        """Generate a human-readable error report with actionable info."""
        stats = self.get_stats()
        lines = [
            "╔══════════════════════════════════════════╗",
            "║         TARS Error Tracker Report        ║",
            "╚══════════════════════════════════════════╝",
            "",
            f"  Unique errors:      {stats['unique_errors']}",
            f"  Total occurrences:  {stats['total_occurrences']}",
            f"  Auto-fixable:       {stats['auto_fixable']}",
            f"  Unfixed recurring:  {stats['unfixed_recurring']}",
            f"  Fixes applied:      {stats['total_fixes_applied']}",
            f"  Fix rate:           {stats['fix_rate']}",
            "",
        ]

        # Top unfixed errors — with full actionable detail
        unfixed = self.get_unfixed_errors(10)
        if unfixed:
            lines.append("  🔴 Top Unfixed Errors (need fixing):")
            lines.append("  " + "─" * 50)
            for i, e in enumerate(unfixed, 1):
                lines.append(f"  {i}. [{e['count']}x] {e['context'] or 'unknown'}:{e['tool'] or ''}")
                lines.append(f"     Error:  {e['signature'][:120]}")
                if e.get('source_file'):
                    lines.append(f"     Source: {e['source_file']}")
                if e.get('agent'):
                    lines.append(f"     Agent:  {e['agent']}")
                if e.get('details'):
                    lines.append(f"     Detail: {e['details'][:150]}")
                if e.get('sample_params'):
                    last = e['sample_params'][-1]
                    # Show params concisely
                    param_str = json.dumps(last, default=str)[:200]
                    lines.append(f"     Params: {param_str}")
                lines.append(f"     When:   {e['first_seen'][:10]} → {e['last_seen'][:10]}")
                lines.append("")
            lines.append("")

        # Auto-fixable errors
        fixable = self.get_auto_fixable()
        if fixable:
            lines.append("  🟢 Auto-Fixable Errors:")
            lines.append("  " + "─" * 50)
            for e in fixable:
                fix = e["fixes"][-1] if e["fixes"] else {}
                lines.append(
                    f"    [{e['count']}x] {e['context']}: {e['signature'][:60]}"
                    f"\n           → Fix: {fix.get('fix', '?')[:80]}"
                )
            lines.append("")

        # Error hotspots — which source files generate the most errors
        with self._lock:
            file_counts = {}
            for entry in self._entries.values():
                sf = entry.source_file or "unknown"
                file_counts[sf] = file_counts.get(sf, 0) + entry.count
        if file_counts:
            sorted_files = sorted(file_counts.items(), key=lambda x: -x[1])[:5]
            lines.append("  📍 Error Hotspots (by source file):")
            lines.append("  " + "─" * 50)
            for f, c in sorted_files:
                lines.append(f"    {c:>4}x  {f}")
            lines.append("")

        return "\n".join(lines)

    def generate_dev_prompt(self, max_errors: int = 15) -> str:
        """Generate a complete dev-agent-ready prompt from the error tracker.

        This is the core method: hand this entire output to the dev agent
        and it will know exactly what's broken, where, and how to fix it.

        Returns a structured prompt with:
        1. Project rules (what NOT to do)
        2. Each error with full context, traceback, fix hint, and sample params
        3. Prioritized by frequency × severity
        4. Previously attempted fixes (what didn't work)
        """
        lines = []

        # ── Header ──
        lines.append("# TARS Error Tracker — Dev Agent Fix Prompt")
        lines.append("")
        lines.append("You are fixing bugs in TARS, an autonomous macOS agent.")
        lines.append("Below are real errors from production runs, ordered by priority.")
        lines.append("Fix them surgically — minimal changes, preserve all imports and signatures.")
        lines.append("")

        # ── Project Rules (anti-patterns / lessons learned) ──
        lines.append("## Rules (MUST follow)")
        lines.append("")
        lines.append("1. **Tool return format**: Every handler in hands/*, voice/*, memory/* MUST return `{\"success\": True/False, \"content\": str}`. No extra keys, no different shapes.")
        lines.append("2. **Absolute imports only**: `from brain.planner import TARSBrain` — never `from . import`.")
        lines.append("3. **Never raise from handlers**: Always `try/except → return {\"success\": False, ...}`. The executor depends on this.")
        lines.append("4. **4-space indentation everywhere**. No tabs. No mixing.")
        lines.append("5. **Don't rewrite entire files** — surgical edits only.")
        lines.append("6. **Don't rename existing functions/params** — other files depend on them.")
        lines.append("7. **Event bus**: `from utils.event_bus import event_bus` — emit events for dashboard visibility.")
        lines.append("8. **Config access**: `config[\"section\"][\"key\"]` for required, `config.get(\"section\", {}).get(\"key\", default)` for optional.")
        lines.append("9. **AppleScript strings**: Escape backslashes, quotes, and Unicode before passing to osascript.")
        lines.append("10. **Browser agent**: Page elements use aria-label and title attributes, not just label/name/id.")
        lines.append("11. **Agent `run()` returns** its own shape (`final_response`, `steps`, `stuck`, etc.) — NOT the standard `{success, content}` dict. The executor wraps it.")
        lines.append("12. After making changes, run: `python3 test_systems.py`")
        lines.append("")

        # ── Collect and prioritize errors ──
        with self._lock:
            entries = list(self._entries.values())

        # Score: count * severity_multiplier
        def _score(e):
            mult = 1.0
            if e.count >= 5:
                mult = 2.0
            elif e.count >= 3:
                mult = 1.5
            # Boost if it has a traceback (real crash vs agent message)
            if e.traceback_str:
                mult *= 1.3
            # Boost unfixed recurring
            if not e.auto_fixable and e.count >= 2:
                mult *= 1.5
            return e.count * mult

        entries.sort(key=_score, reverse=True)
        entries = entries[:max_errors]

        if not entries:
            lines.append("## No errors recorded — system is clean! 🎉")
            return "\n".join(lines)

        # ── Error Entries ──
        lines.append(f"## Errors to Fix ({len(entries)} prioritized)")
        lines.append("")

        for i, e in enumerate(entries, 1):
            status = "🟢 HAS FIX" if e.auto_fixable else "🔴 NEEDS FIX"
            lines.append(f"### Error {i}: {status} — {e.context or 'unknown'}:{e.tool or ''} [{e.count}x]")
            lines.append("")

            # What happened
            lines.append(f"**Error message**: `{e.raw_error[:300]}`")
            lines.append("")

            # Where it happened
            where_parts = []
            if e.source_file:
                where_parts.append(f"Source file: `{e.source_file}`")
            if e.tool:
                where_parts.append(f"Tool: `{e.tool}`")
            if e.agent:
                where_parts.append(f"Agent: `{e.agent}`")
            if e.context and e.context != e.tool:
                where_parts.append(f"Context: `{e.context}`")
            if where_parts:
                lines.append(f"**Where**: {' | '.join(where_parts)}")
                lines.append("")

            # Human-readable detail
            if e.details:
                lines.append(f"**What was happening**: {e.details}")
                lines.append("")

            # Stack trace — the gold for the dev agent
            if e.traceback_str:
                lines.append("**Stack trace**:")
                lines.append("```")
                lines.append(e.traceback_str.strip())
                lines.append("```")
                lines.append("")

            # Sample params — what input triggered it
            if e.sample_params:
                lines.append("**Sample input that caused this**:")
                lines.append("```json")
                try:
                    lines.append(json.dumps(e.sample_params[-1], indent=2, default=str)[:500])
                except Exception:
                    lines.append(str(e.sample_params[-1])[:500])
                lines.append("```")
                lines.append("")

            # Fix hint — pattern-matched guidance
            if e.fix_hint:
                lines.append(f"**Fix hint**: {e.fix_hint}")
                if e.fix_hint_files:
                    lines.append(f"**Likely files to edit**: {', '.join(f'`{f}`' for f in e.fix_hint_files)}")
                lines.append("")

            # Previous fix attempts — what didn't work
            if e.fixes:
                lines.append("**Previous fix attempts**:")
                for fix in e.fixes[-3:]:
                    status_icon = "✅" if fix.get("success") else "❌"
                    lines.append(f"  - {status_icon} [{fix.get('source', '?')}] {fix.get('fix', '?')[:200]}")
                lines.append("")

            # Frequency info
            lines.append(f"**Frequency**: {e.count}x between {e.first_seen[:10]} and {e.last_seen[:10]}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # ── Summary Section ──
        stats = self.get_stats()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total unique errors: {stats['unique_errors']}")
        lines.append(f"- Total occurrences: {stats['total_occurrences']}")
        lines.append(f"- Auto-fixable: {stats['auto_fixable']}")
        lines.append(f"- Unfixed recurring: {stats['unfixed_recurring']}")
        lines.append(f"- Current fix rate: {stats['fix_rate']}")
        lines.append("")

        # ── Error Hotspots ──
        file_counts = {}
        for entry in entries:
            sf = entry.source_file or "unknown"
            file_counts[sf] = file_counts.get(sf, 0) + entry.count
        if file_counts:
            sorted_files = sorted(file_counts.items(), key=lambda x: -x[1])[:8]
            lines.append("## Error Hotspots (files generating the most errors)")
            lines.append("")
            for f, c in sorted_files:
                lines.append(f"- `{f}`: {c}x")
            lines.append("")

        return "\n".join(lines)

    def deduplicate(self) -> int:
        """Merge entries with the same normalized signature.

        Over time, entries accumulate with slightly different keys
        (e.g., different step counts, recovery levels, or old normalization).
        This method re-normalizes all keys and merges duplicates.

        Returns:
            Number of entries removed by merging.
        """
        with self._lock:
            # Re-normalize all keys
            new_entries: Dict[str, ErrorEntry] = {}
            merged_count = 0

            for old_key, entry in self._entries.items():
                # Re-normalize the raw error with current normalization logic
                new_sig = self._normalize(entry.raw_error)
                new_key = f"{entry.context}:{new_sig}" if entry.context else new_sig

                if new_key in new_entries:
                    # Merge into existing entry
                    existing = new_entries[new_key]
                    existing.count += entry.count
                    existing.fixed_count += entry.fixed_count
                    # Keep the most recent last_seen
                    if entry.last_seen > existing.last_seen:
                        existing.last_seen = entry.last_seen
                    # Keep the earliest first_seen
                    if entry.first_seen < existing.first_seen:
                        existing.first_seen = entry.first_seen
                    # Merge fixes (deduplicate by applied_at)
                    seen_fixes = {f.get("applied_at", ""): f for f in existing.fixes}
                    for fix in entry.fixes:
                        at = fix.get("applied_at", "")
                        if at not in seen_fixes:
                            existing.fixes.append(fix)
                    # Keep auto_fixable if either had it
                    if entry.auto_fixable:
                        existing.auto_fixable = True
                    # Keep longer details
                    if len(entry.details) > len(existing.details):
                        existing.details = entry.details
                    # Keep longer raw_error
                    if len(entry.raw_error) > len(existing.raw_error):
                        existing.raw_error = entry.raw_error
                    # Merge sample params
                    existing.sample_params.extend(entry.sample_params)
                    existing.sample_params = existing.sample_params[-3:]
                    # Keep traceback if we have one
                    if entry.traceback_str and not existing.traceback_str:
                        existing.traceback_str = entry.traceback_str
                    # Keep fix hints
                    if entry.fix_hint and not existing.fix_hint:
                        existing.fix_hint = entry.fix_hint
                        existing.fix_hint_files = entry.fix_hint_files
                    # Update signature to the new normalized one
                    existing.signature = new_sig
                    merged_count += 1
                else:
                    # Update signature to the new normalized one
                    entry.signature = new_sig
                    new_entries[new_key] = entry

            if merged_count > 0:
                self._entries = new_entries
                self._dirty = True
                self._save()
                logger.info(f"  🧹 Error tracker dedup: merged {merged_count} entries, {len(self._entries)} unique remain")

            return merged_count

    def purge_noise(self, patterns: list = None) -> int:
        """Remove non-actionable entries that aren't real bugs.

        Args:
            patterns: List of regex patterns matching noise entries to remove.
                      If None, uses built-in noise patterns.

        Returns:
            Number of entries removed.
        """
        if patterns is None:
            patterns = [
                r"No reply received within \d+s",     # User didn't respond — not a bug
                r"wait_for_reply.*timeout",            # Same
                r"Task cancelled by user",             # User choice
                r"STOP|HALT|ABORT",                    # Kill switch — intentional
            ]

        removed = 0
        with self._lock:
            keys_to_remove = []
            for key, entry in self._entries.items():
                for pattern in patterns:
                    if re.search(pattern, entry.raw_error, re.IGNORECASE):
                        keys_to_remove.append(key)
                        break
            for key in keys_to_remove:
                del self._entries[key]
                removed += 1

            if removed > 0:
                self._dirty = True
                self._save()
                logger.info(f"  🧹 Purged {removed} noise entries from error tracker")

        return removed

    def record_bulk_fixes(self, fixes: list) -> int:
        """Record fixes for multiple errors at once.

        Args:
            fixes: List of dicts with keys:
                - error_pattern: regex matching the error signature
                - context: optional context filter
                - fix: description of the fix
                - source: "code_change", "manual", etc.

        Returns:
            Number of entries that got fixes recorded.
        """
        fixed = 0
        with self._lock:
            for fix_spec in fixes:
                pattern = fix_spec.get("error_pattern", "")
                ctx_filter = fix_spec.get("context", "")
                fix_text = fix_spec.get("fix", "")
                source = fix_spec.get("source", "code_change")

                if not pattern or not fix_text:
                    continue

                for key, entry in self._entries.items():
                    # Match by context if specified
                    if ctx_filter and entry.context != ctx_filter:
                        continue
                    # Match by pattern
                    if re.search(pattern, entry.raw_error, re.IGNORECASE) or \
                       re.search(pattern, entry.signature, re.IGNORECASE):
                        # Don't add duplicate fixes
                        existing_fix_texts = [f.get("fix", "") for f in entry.fixes]
                        if fix_text not in existing_fix_texts:
                            entry.fixes.append({
                                "fix": fix_text[:500],
                                "source": source,
                                "success": True,
                                "confidence": 0.9,
                                "applied_at": datetime.now().isoformat(),
                            })
                            entry.auto_fixable = True
                            fixed += 1

            if fixed > 0:
                self._dirty = True
                self._save()
                logger.info(f"  🩹 Recorded fixes for {fixed} error entries")

        return fixed

    def save(self):
        """Force save to disk."""
        self._save()

    # ═══════════════════════════════════════════════════
    #  INTERNAL HELPERS
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _match_fix_hint(error: str) -> tuple:
        """Match error against known patterns and return (hint, likely_files).

        Returns:
            (hint_text, [file1, file2, ...]) or ("", [])
        """
        for pattern, hint_template, files in _FIX_HINT_PATTERNS:
            m = re.search(pattern, error, re.IGNORECASE)
            if m:
                # Fill in any capture groups into the hint template
                try:
                    hint = hint_template.format(*m.groups()) if m.groups() else hint_template
                except (IndexError, KeyError):
                    hint = hint_template
                return hint[:500], files
        return "", []

    @staticmethod
    def _normalize(error: str) -> str:
        """Normalize error string for deduplication.

        Strips:
        - Recovery guidance ("## Recovery: LEVEL ...", "PREVIOUS FAILED ATTEMPTS")
        - Agent FAILED preamble ("❌ browser agent FAILED after N steps.\nReason: ")
        - File paths, long numbers, hex addresses, emails, long strings
        - Budget nudges ("⚡ BUDGET ALERT")
        """
        # Strip recovery ladder text that makes dedup impossible
        for marker in ["\n\n## Recovery:", "\n\n## ⚠️ PREVIOUS", "\n\n⚡ BUDGET",
                       "\n\n⚡ Budget:", "\nDO NOT repeat"]:
            idx = error.find(marker)
            if idx > 0:
                error = error[:idx]

        # Strip "❌ <agent> agent FAILED after N steps.\nReason: " prefix
        error = re.sub(
            r"^❌\s*\w+\s+agent\s+FAILED\s+after\s+\d+\s+steps\.\s*\n?Reason:\s*",
            "", error
        )

        # Standard normalizations
        sig = re.sub(r"/[\w/\-.]+", "<PATH>", error)
        sig = re.sub(r"\b\d{4,}\b", "<NUM>", sig)
        sig = re.sub(r"0x[0-9a-fA-F]+", "<HEX>", sig)
        sig = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "<EMAIL>", sig)
        sig = re.sub(r"'[^']{30,}'", "'<LONG_STR>'", sig)
        # Strip trailing whitespace and limit length
        return sig[:200].strip()

    @staticmethod
    def _get_best_fix(entry: ErrorEntry) -> Optional[dict]:
        """Get the most reliable fix for an entry."""
        successful = [f for f in entry.fixes if f.get("success")]
        if not successful:
            return None
        # Sort by confidence, then recency
        successful.sort(key=lambda f: (f.get("confidence", 0), f.get("applied_at", "")), reverse=True)
        return successful[0]

    def _load(self):
        """Load tracker from disk."""
        try:
            if os.path.exists(TRACKER_DB):
                with open(TRACKER_DB, "r") as f:
                    data = json.load(f)
                for key, entry_dict in data.items():
                    self._entries[key] = ErrorEntry.from_dict(entry_dict)

                # Retroactively apply fix hints to old entries that don't have them
                for entry in self._entries.values():
                    if not entry.fix_hint and entry.raw_error:
                        hint, files = self._match_fix_hint(entry.raw_error)
                        if hint:
                            entry.fix_hint = hint
                            entry.fix_hint_files = files
                            self._dirty = True

                logger.info(f"  📋 Error tracker: {len(self._entries)} patterns loaded, "
                      f"{sum(1 for e in self._entries.values() if e.auto_fixable)} auto-fixable")

                # Auto-deduplicate on load (merges old entries with bad normalization)
                merged = self.deduplicate()
                if merged:
                    logger.info(f"  🧹 Deduped {merged} entries on load → {len(self._entries)} unique")
        except Exception as e:
            logger.warning(f"  ⚠️ Error tracker load failed: {e}")
            self._entries = {}

    def _save(self):
        """Persist tracker to disk."""
        if not self._dirty:
            return
        try:
            # Prune oldest low-count entries if over limit
            if len(self._entries) > MAX_ENTRIES:
                sorted_keys = sorted(
                    self._entries.keys(),
                    key=lambda k: (
                        self._entries[k].auto_fixable,  # Keep fixable ones
                        self._entries[k].count,
                    ),
                )
                for k in sorted_keys[:len(self._entries) - MAX_ENTRIES]:
                    del self._entries[k]

            os.makedirs(os.path.dirname(TRACKER_DB), exist_ok=True)
            data = {k: v.to_dict() for k, v in self._entries.items()}
            tmp = TRACKER_DB + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, TRACKER_DB)  # Atomic on POSIX
            self._dirty = False
        except Exception as e:
            logger.warning(f"  ⚠️ Error tracker save failed: {e}")


# ─── Singleton ──────────────────────────────────────
error_tracker = ErrorTracker()
