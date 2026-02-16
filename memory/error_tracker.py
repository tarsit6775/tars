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


class ErrorEntry:
    """A recorded error with optional fix."""

    def __init__(self, signature: str, context: str, raw_error: str,
                 tool: str = "", agent: str = "", details: str = ""):
        self.signature = signature
        self.context = context
        self.raw_error = raw_error[:500]
        self.tool = tool
        self.agent = agent
        self.details = details[:300]
        self.count = 1
        self.first_seen = datetime.now().isoformat()
        self.last_seen = datetime.now().isoformat()
        self.fixes = []          # [{fix, applied_at, success, source}]
        self.auto_fixable = False  # True once a fix has succeeded
        self.fixed_count = 0     # Times auto-fix was applied

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "context": self.context,
            "raw_error": self.raw_error,
            "tool": self.tool,
            "agent": self.agent,
            "details": self.details,
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
        )
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
                     agent: str = "", details: str = "") -> Optional[dict]:
        """Record an error occurrence.

        Returns:
            dict with fix info if a known fix exists, None otherwise.
            {"has_fix": True, "fix": "...", "confidence": 0.9, "source": "..."}
        """
        sig = self._normalize(error)
        key = f"{context}:{sig}" if context else sig

        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                entry.count += 1
                entry.last_seen = datetime.now().isoformat()
                # Update details if we have more info now
                if details and len(details) > len(entry.details):
                    entry.details = details[:300]
            else:
                entry = ErrorEntry(
                    signature=sig,
                    context=context,
                    raw_error=error,
                    tool=tool,
                    agent=agent,
                    details=details,
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
        """Generate a human-readable error report."""
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

        # Top unfixed errors
        unfixed = self.get_unfixed_errors(5)
        if unfixed:
            lines.append("  🔴 Top Unfixed Errors:")
            for e in unfixed:
                lines.append(f"    [{e['count']}x] {e['context']}: {e['signature'][:80]}")
            lines.append("")

        # Auto-fixable errors
        fixable = self.get_auto_fixable()
        if fixable:
            lines.append("  🟢 Auto-Fixable Errors:")
            for e in fixable:
                fix = e["fixes"][-1] if e["fixes"] else {}
                lines.append(
                    f"    [{e['count']}x] {e['context']}: {e['signature'][:60]}"
                    f"  → Fix: {fix.get('fix', '?')[:60]}"
                )
            lines.append("")

        return "\n".join(lines)

    def save(self):
        """Force save to disk."""
        self._save()

    # ═══════════════════════════════════════════════════
    #  INTERNAL HELPERS
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _normalize(error: str) -> str:
        """Normalize error string for deduplication."""
        sig = re.sub(r"/[\w/\-.]+", "<PATH>", error)
        sig = re.sub(r"\b\d{4,}\b", "<NUM>", sig)
        sig = re.sub(r"0x[0-9a-fA-F]+", "<HEX>", sig)
        sig = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "<EMAIL>", sig)
        sig = re.sub(r"'[^']{30,}'", "'<LONG_STR>'", sig)
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
                logger.info(f"  📋 Error tracker: {len(self._entries)} patterns loaded, "
                      f"{sum(1 for e in self._entries.values() if e.auto_fixable)} auto-fixable")
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
            with open(TRACKER_DB, "w") as f:
                json.dump(data, f, indent=2)
            self._dirty = False
        except Exception as e:
            logger.warning(f"  ⚠️ Error tracker save failed: {e}")


# ─── Singleton ──────────────────────────────────────
error_tracker = ErrorTracker()
