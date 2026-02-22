"""
╔══════════════════════════════════════════════════════════════╗
║      TARS Brain — Phase 26: Decision Tree Caching            ║
╠══════════════════════════════════════════════════════════════╣
║  Caches successful decision patterns so the brain can        ║
║  recognize and reuse proven strategies without re-reasoning  ║
║  from scratch every time.                                    ║
║                                                              ║
║  A "decision tree" is: intent → plan → tool sequence         ║
║  Cached entries include domain, entity patterns, and the     ║
║  full tool sequence that worked.                             ║
║                                                              ║
║  Cache entries are invalidated after failures or after       ║
║  30 days of non-use.                                         ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import os
import time
import re
from typing import Dict, List, Optional
from pathlib import Path


class DecisionEntry:
    """A cached decision pattern."""

    def __init__(self, intent_type: str, domain: str, pattern: str,
                 tool_sequence: List[str], strategy: str,
                 success_count: int = 1, failure_count: int = 0,
                 last_used: float = 0.0, created: float = 0.0,
                 anti_patterns: List[str] = None,
                 avg_steps: float = 0.0, best_steps: int = 0,
                 complexity: str = "simple"):
        self.intent_type = intent_type
        self.domain = domain
        self.pattern = pattern           # Generalized pattern like "search flights {origin} to {dest}"
        self.tool_sequence = tool_sequence  # ["think", "search_flights_report", "send_imessage"]
        self.strategy = strategy         # Natural language description of the approach
        self.success_count = success_count
        self.failure_count = failure_count
        self.last_used = last_used or time.time()
        self.created = created or time.time()
        self.anti_patterns = anti_patterns or []  # List of strategies that FAILED for this pattern
        self.avg_steps = avg_steps       # Average tool-loop steps to complete
        self.best_steps = best_steps     # Fewest steps ever achieved
        self.complexity = complexity      # simple/moderate/complex from intent classifier

    @property
    def reliability(self) -> float:
        """Success rate as a percentage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100

    @property
    def is_stale(self) -> bool:
        """Stale if not used in 30 days."""
        return (time.time() - self.last_used) > (30 * 86400)

    @property
    def is_reliable(self) -> bool:
        """Reliable if 70%+ success rate with 2+ uses."""
        return self.reliability >= 70 and (self.success_count + self.failure_count) >= 2

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type,
            "domain": self.domain,
            "pattern": self.pattern,
            "tool_sequence": self.tool_sequence,
            "strategy": self.strategy,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_used": self.last_used,
            "created": self.created,
            "anti_patterns": self.anti_patterns,
            "avg_steps": self.avg_steps,
            "best_steps": self.best_steps,
            "complexity": self.complexity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionEntry":
        # Handle legacy entries without new fields
        return cls(
            intent_type=d.get("intent_type", ""),
            domain=d.get("domain", ""),
            pattern=d.get("pattern", ""),
            tool_sequence=d.get("tool_sequence", []),
            strategy=d.get("strategy", ""),
            success_count=d.get("success_count", 1),
            failure_count=d.get("failure_count", 0),
            last_used=d.get("last_used", 0.0),
            created=d.get("created", 0.0),
            anti_patterns=d.get("anti_patterns", []),
            avg_steps=d.get("avg_steps", 0.0),
            best_steps=d.get("best_steps", 0),
            complexity=d.get("complexity", "simple"),
        )


class DecisionCache:
    """
    Persistent cache of successful decision patterns.
    
    Usage:
        cache = DecisionCache(base_dir)
        
        # Before thinking: check for cached strategy
        cached = cache.lookup("TASK", ["flights"], "search flights SLC to NYC")
        if cached:
            # Inject cached.strategy into the prompt
            
        # After successful task: record the decision
        cache.record_success("TASK", "flights", 
                           "search flights from {origin} to {dest}",
                           ["think", "search_flights_report", "send_imessage"],
                           "Use search_flights_report for specific-date flight requests")
        
        # After failure: mark the pattern as less reliable
        cache.record_failure("TASK", "flights", "search flights from {origin} to {dest}")
    """

    MAX_ENTRIES = 200
    CACHE_FILE = "decision_cache.json"

    def __init__(self, base_dir: str):
        self._cache_dir = os.path.join(base_dir, "memory")
        self._cache_file = os.path.join(self._cache_dir, self.CACHE_FILE)
        self._entries: Dict[str, DecisionEntry] = {}
        self._load()

    def _load(self):
        """Load cache from disk."""
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r") as f:
                    data = json.load(f)
                for key, entry_dict in data.items():
                    self._entries[key] = DecisionEntry.from_dict(entry_dict)
                # Prune stale entries on load
                self._prune()
            except (json.JSONDecodeError, IOError, TypeError):
                self._entries = {}

    def _save(self):
        """Save cache to disk."""
        os.makedirs(self._cache_dir, exist_ok=True)
        data = {k: v.to_dict() for k, v in self._entries.items()}
        try:
            with open(self._cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass

    def _prune(self):
        """Remove stale and low-reliability entries."""
        to_remove = []
        for key, entry in self._entries.items():
            if entry.is_stale:
                to_remove.append(key)
            elif entry.failure_count > 5 and entry.reliability < 30:
                to_remove.append(key)
        for key in to_remove:
            del self._entries[key]

        # Cap total entries
        if len(self._entries) > self.MAX_ENTRIES:
            # Remove least recently used
            sorted_entries = sorted(self._entries.items(), key=lambda x: x[1].last_used)
            for key, _ in sorted_entries[:len(self._entries) - self.MAX_ENTRIES]:
                del self._entries[key]

    def _make_key(self, intent_type: str, domain: str, pattern: str) -> str:
        """Create a cache key from intent, domain, and pattern."""
        return f"{intent_type}:{domain}:{pattern}".lower()

    def lookup(self, intent_type: str, domains: List[str],
               message: str) -> Optional[DecisionEntry]:
        """
        Look up a cached decision strategy for a message.
        
        Searches by intent type + domain, then checks if the message
        matches any cached pattern.
        
        Returns the best matching reliable entry, or None.
        """
        if not domains:
            return None

        candidates = []
        for key, entry in self._entries.items():
            if entry.intent_type != intent_type:
                continue
            if entry.domain not in domains:
                continue
            if not entry.is_reliable:
                continue
            if entry.is_stale:
                continue
            # Check if the message loosely matches the pattern
            if self._fuzzy_match(message, entry.pattern):
                candidates.append(entry)

        if not candidates:
            return None

        # Return highest reliability, then most recent
        candidates.sort(key=lambda e: (e.reliability, e.last_used), reverse=True)
        best = candidates[0]
        best.last_used = time.time()
        self._save()
        return best

    def record_success(self, intent_type: str, domain: str, pattern: str,
                       tool_sequence: List[str], strategy: str,
                       steps: int = 0, complexity: str = "simple"):
        """Record a successful decision pattern with performance tracking."""
        key = self._make_key(intent_type, domain, pattern)

        if key in self._entries:
            entry = self._entries[key]
            entry.success_count += 1
            entry.last_used = time.time()
            entry.tool_sequence = tool_sequence  # Update with latest
            entry.strategy = strategy
            entry.complexity = complexity
            # Track step performance (rolling average)
            if steps > 0:
                if entry.avg_steps > 0:
                    entry.avg_steps = (entry.avg_steps * 0.7) + (steps * 0.3)
                else:
                    entry.avg_steps = float(steps)
                if entry.best_steps == 0 or steps < entry.best_steps:
                    entry.best_steps = steps
        else:
            self._entries[key] = DecisionEntry(
                intent_type=intent_type,
                domain=domain,
                pattern=pattern,
                tool_sequence=tool_sequence,
                strategy=strategy,
                avg_steps=float(steps) if steps else 0.0,
                best_steps=steps,
                complexity=complexity,
            )

        self._prune()
        self._save()

    def record_failure(self, intent_type: str, domain: str, pattern: str,
                       failed_strategy: str = ""):
        """Record a failure for a pattern (lowers reliability) + track anti-pattern."""
        key = self._make_key(intent_type, domain, pattern)
        if key in self._entries:
            entry = self._entries[key]
            entry.failure_count += 1
            if failed_strategy and failed_strategy not in entry.anti_patterns:
                entry.anti_patterns.append(failed_strategy)
                # Cap anti-patterns at 5
                if len(entry.anti_patterns) > 5:
                    entry.anti_patterns = entry.anti_patterns[-5:]
            self._save()
        else:
            # Record even unknown pattern failures as anti-patterns
            if failed_strategy:
                self._entries[key] = DecisionEntry(
                    intent_type=intent_type,
                    domain=domain,
                    pattern=pattern,
                    tool_sequence=[],
                    strategy="",
                    success_count=0,
                    failure_count=1,
                    anti_patterns=[failed_strategy],
                )
                self._save()

    def get_anti_patterns(self, intent_type: str, domains: List[str],
                          message: str) -> List[str]:
        """
        Get known anti-patterns (what NOT to do) for a message type.
        Helps the brain avoid repeating past mistakes.
        """
        anti = []
        for entry in self._entries.values():
            if entry.intent_type != intent_type:
                continue
            if entry.domain not in domains:
                continue
            if not entry.anti_patterns:
                continue
            if self._fuzzy_match(message, entry.pattern):
                anti.extend(entry.anti_patterns)
        # Deduplicate
        seen = set()
        unique = []
        for a in anti:
            if a.lower() not in seen:
                seen.add(a.lower())
                unique.append(a)
        return unique[:5]

    def get_domain_insights(self, domain: str) -> dict:
        """
        Get learning insights for a domain — what works, what doesn't, performance.
        Useful for metacognition and prompt enrichment.
        """
        entries = [e for e in self._entries.values() if e.domain == domain]
        if not entries:
            return {}

        reliable = [e for e in entries if e.is_reliable]
        total_success = sum(e.success_count for e in entries)
        total_failure = sum(e.failure_count for e in entries)
        all_anti = []
        for e in entries:
            all_anti.extend(e.anti_patterns)

        best_strategies = sorted(reliable, key=lambda e: e.reliability, reverse=True)[:3]

        return {
            "domain": domain,
            "total_patterns": len(entries),
            "reliable_patterns": len(reliable),
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": (total_success / max(total_success + total_failure, 1)) * 100,
            "best_strategies": [
                {"pattern": s.pattern, "strategy": s.strategy,
                 "reliability": s.reliability, "avg_steps": s.avg_steps}
                for s in best_strategies
            ],
            "common_anti_patterns": list(set(all_anti))[:5],
        }

    def get_all_patterns(self) -> List[dict]:
        """Get all cached patterns (for dashboard/debugging)."""
        return [
            {**e.to_dict(), "key": k, "reliability": e.reliability}
            for k, e in self._entries.items()
        ]

    @staticmethod
    def _fuzzy_match(message: str, pattern: str) -> bool:
        """Check if a message loosely matches a cached pattern."""
        msg_lower = message.lower()
        pat_lower = pattern.lower()

        # Remove placeholder tokens like {origin}, {dest}, etc.
        pat_clean = re.sub(r'\{[^}]+\}', '', pat_lower).strip()
        pat_words = [w for w in pat_clean.split() if len(w) > 2]

        if not pat_words:
            return False

        # Check if at least 60% of pattern words appear in the message
        matches = sum(1 for w in pat_words if w in msg_lower)
        return (matches / len(pat_words)) >= 0.6

    @staticmethod
    def generalize_pattern(message: str, domains: List[str]) -> str:
        """
        Generalize a specific message into a reusable pattern.
        
        "search flights from SLC to NYC on March 15" 
          → "search flights from {origin} to {dest} on {date}"
        "buy 50 shares of NVDA at $182"
          → "buy {amount} shares of {ticker} at {price}"
        """
        pattern = message

        # Replace common entities with placeholders
        # Email addresses (before URLs to avoid conflicts)
        pattern = re.sub(r'\S+@\S+\.\S+', '{email}', pattern)

        # URLs
        pattern = re.sub(r'https?://\S+', '{url}', pattern)

        # File paths
        pattern = re.sub(r'(?:~/|/[\w.-]+/|\./)[\w./-]+', '{path}', pattern)

        # Dates — named months
        pattern = re.sub(
            r'\b(?:january|february|march|april|may|june|july|august|'
            r'september|october|november|december)\s+\d{1,2}(?:\s*,?\s*\d{4})?\b',
            '{date}', pattern, flags=re.IGNORECASE
        )
        # Dates — ISO format
        pattern = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '{date}', pattern)
        # Dates — US format
        pattern = re.sub(r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b', '{date}', pattern)
        # Relative dates
        pattern = re.sub(
            r'\b(today|tomorrow|tonight|yesterday|next week|next month|this weekend)\b',
            '{date}', pattern, flags=re.IGNORECASE
        )

        # Dollar amounts
        pattern = re.sub(r'\$[\d,]+(?:\.\d{2})?', '{price}', pattern)

        # Airport codes (3 uppercase letters — only in flight context)
        if "flights" in domains or "travel" in domains:
            pattern = re.sub(r'\b[A-Z]{3}\b', '{airport}', pattern)

        # Stock tickers (all caps 1-5 letters — only in research/finance context)
        if "research" in domains:
            pattern = re.sub(r'\b[A-Z]{1,5}\b(?=\s|$|,)', '{ticker}', pattern)

        # Phone numbers
        pattern = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '{phone}', pattern)

        # Plain numbers (amounts, counts, IDs) — do this last
        pattern = re.sub(r'\b\d{2,}\b', '{number}', pattern)

        # Lowercase for consistency
        pattern = pattern.lower()

        # Keep it to first 80 chars
        if len(pattern) > 80:
            pattern = pattern[:80]

        return pattern.strip()

    # ═══════════════════════════════════════════════════
    #  Lookup Enhancement
    # ═══════════════════════════════════════════════════

    def lookup_with_context(self, intent_type: str, domains: List[str],
                            message: str, complexity: str = "simple") -> dict:
        """
        Enhanced lookup that returns strategy + anti-patterns + insights.
        Gives the brain a complete picture of what worked and what didn't.
        """
        best = self.lookup(intent_type, domains, message)
        anti = self.get_anti_patterns(intent_type, domains, message)

        # Get domain insights for the primary domain
        primary_domain = domains[0] if domains else ""
        insights = self.get_domain_insights(primary_domain) if primary_domain else {}

        return {
            "cached_strategy": best,
            "anti_patterns": anti,
            "domain_insights": insights,
        }
