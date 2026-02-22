"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Site Knowledge: Persistent Web Memory            ║
╠══════════════════════════════════════════════════════════════╣
║  Every time the browser agent visits a page, it learns:      ║
║    - Page structure (fields, buttons, dropdowns)             ║
║    - Which selectors work and which fail                     ║
║    - Multi-page flows (signup → birthday → captcha → verify) ║
║    - Error → fix patterns per site                           ║
║    - Session/login state detection rules                     ║
║    - Overlay dismissal actions per site                      ║
║                                                              ║
║  Knowledge is injected into the browser agent before each    ║
║  task, making it smarter with every interaction.             ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger("TARS")

KNOWLEDGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "site_knowledge.json")
MAX_ENTRIES_PER_SECTION = 50
MAX_DOMAINS = 100


class SiteKnowledge:
    """Persistent per-domain knowledge base — learns how websites work."""

    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        """Load knowledge from disk."""
        if os.path.exists(KNOWLEDGE_FILE):
            try:
                with open(KNOWLEDGE_FILE, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}

    def _save(self):
        """Save knowledge to disk."""
        try:
            os.makedirs(os.path.dirname(KNOWLEDGE_FILE), exist_ok=True)
            # Prune if too many domains
            if len(self._data) > MAX_DOMAINS:
                # Remove least-visited domains
                sorted_domains = sorted(
                    self._data.items(),
                    key=lambda x: x[1].get("visit_count", 0),
                )
                for domain, _ in sorted_domains[:len(self._data) - MAX_DOMAINS]:
                    del self._data[domain]
            with open(KNOWLEDGE_FILE, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
        except IOError as e:
            logger.warning(f"Failed to save site knowledge: {e}")

    def _get_domain(self, url_or_domain):
        """Extract domain from URL or return as-is."""
        if "://" in url_or_domain:
            parsed = urlparse(url_or_domain)
            return parsed.netloc or url_or_domain
        return url_or_domain

    def _ensure_domain(self, domain):
        """Ensure domain entry exists."""
        if domain not in self._data:
            self._data[domain] = {
                "pages": {},
                "selectors": {},
                "flows": {},
                "errors": {},
                "login_indicators": {},
                "overlay_dismissals": {},
                "first_seen": datetime.now().isoformat(),
                "visit_count": 0,
            }
        self._data[domain]["visit_count"] = self._data[domain].get("visit_count", 0) + 1

    # ═══════════════════════════════════════════
    #  Page Learning
    # ═══════════════════════════════════════════

    def learn_page(self, url, page_type, fields=None, buttons=None, notes=None):
        """Record page structure from a look() inspection.

        Args:
            url: Full URL or path
            page_type: "signup_form", "login_form", "verification_code", etc.
            fields: List of field descriptions
            buttons: List of button labels
            notes: Free-text observations
        """
        domain = self._get_domain(url)
        path = urlparse(url).path if "://" in url else url
        self._ensure_domain(domain)

        self._data[domain]["pages"][path] = {
            "type": page_type,
            "fields": (fields or [])[:20],
            "buttons": (buttons or [])[:15],
            "notes": (notes or "")[:300],
            "last_seen": datetime.now().isoformat(),
        }
        # Prune old pages
        pages = self._data[domain]["pages"]
        if len(pages) > MAX_ENTRIES_PER_SECTION:
            oldest = sorted(pages.items(), key=lambda x: x[1].get("last_seen", ""))
            for key, _ in oldest[:len(pages) - MAX_ENTRIES_PER_SECTION]:
                del pages[key]
        self._save()

    def get_page(self, url):
        """Get known page structure."""
        domain = self._get_domain(url)
        path = urlparse(url).path if "://" in url else url
        if domain in self._data:
            return self._data[domain]["pages"].get(path)
        return None

    # ═══════════════════════════════════════════
    #  Selector Learning
    # ═══════════════════════════════════════════

    def learn_selector(self, domain, element_name, selector, worked=True):
        """Track which selectors work for which elements on a domain.

        Args:
            domain: URL or domain name
            element_name: Human description like "email field", "sign up button"
            selector: CSS selector or text used
            worked: Whether it succeeded
        """
        domain = self._get_domain(domain)
        self._ensure_domain(domain)

        key = element_name.lower().strip()[:80]
        if key not in self._data[domain]["selectors"]:
            self._data[domain]["selectors"][key] = {}

        sel_data = self._data[domain]["selectors"][key]
        if selector not in sel_data:
            sel_data[selector] = {"successes": 0, "failures": 0}

        if worked:
            sel_data[selector]["successes"] += 1
        else:
            sel_data[selector]["failures"] += 1

        # Prune low-value selectors (>5 failures, 0 successes)
        to_remove = [s for s, d in sel_data.items() if d["failures"] > 5 and d["successes"] == 0]
        for s in to_remove:
            del sel_data[s]

        self._save()

    def get_best_selector(self, domain, element_name):
        """Get the most reliable selector for an element on a domain."""
        domain = self._get_domain(domain)
        key = element_name.lower().strip()[:80]

        if domain not in self._data:
            return None
        selectors = self._data[domain].get("selectors", {}).get(key, {})
        if not selectors:
            return None

        # Sort by success rate, then by total successes
        ranked = sorted(
            selectors.items(),
            key=lambda x: (
                x[1]["successes"] / max(x[1]["successes"] + x[1]["failures"], 1),
                x[1]["successes"],
            ),
            reverse=True,
        )
        return ranked[0][0] if ranked else None

    def get_all_selectors(self, domain):
        """Get all known selectors for a domain."""
        domain = self._get_domain(domain)
        if domain not in self._data:
            return {}
        return self._data[domain].get("selectors", {})

    # ═══════════════════════════════════════════
    #  Flow Learning
    # ═══════════════════════════════════════════

    def learn_flow(self, domain, flow_name, steps, success=True):
        """Record a multi-page flow sequence.

        Args:
            domain: URL or domain name
            flow_name: "signup", "login", "checkout", etc.
            steps: List of step descriptions or page types visited
            success: Whether the flow completed successfully
        """
        domain = self._get_domain(domain)
        self._ensure_domain(domain)

        flow_key = flow_name.lower().strip()
        if flow_key not in self._data[domain]["flows"]:
            self._data[domain]["flows"][flow_key] = []

        self._data[domain]["flows"][flow_key].append({
            "steps": steps[:20],
            "success": success,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 5 recordings per flow
        self._data[domain]["flows"][flow_key] = self._data[domain]["flows"][flow_key][-5:]
        self._save()

    def get_flow(self, domain, flow_name):
        """Get the most recent successful flow for a domain.

        Returns list of steps, or None if no successful flow found.
        """
        domain = self._get_domain(domain)
        flow_key = flow_name.lower().strip()

        if domain not in self._data:
            return None
        flows = self._data[domain].get("flows", {}).get(flow_key, [])
        # Return the most recent successful flow
        for flow in reversed(flows):
            if flow.get("success"):
                return flow["steps"]
        # Fallback: return latest even if failed
        return flows[-1]["steps"] if flows else None

    # ═══════════════════════════════════════════
    #  Error → Fix Learning
    # ═══════════════════════════════════════════

    def learn_error_fix(self, domain, error_pattern, fix, page=None):
        """Record an error→fix pattern for a domain.

        Args:
            domain: URL or domain name
            error_pattern: The error text or description
            fix: What fixed it
            page: Optional page path where it occurred
        """
        domain = self._get_domain(domain)
        self._ensure_domain(domain)

        error_key = error_pattern[:100].lower().strip()
        self._data[domain]["errors"][error_key] = {
            "fix": fix[:300],
            "page": page,
            "times_used": self._data[domain]["errors"].get(error_key, {}).get("times_used", 0) + 1,
            "last_used": datetime.now().isoformat(),
        }
        # Prune old errors
        errors = self._data[domain]["errors"]
        if len(errors) > MAX_ENTRIES_PER_SECTION:
            oldest = sorted(errors.items(), key=lambda x: x[1].get("last_used", ""))
            for key, _ in oldest[:len(errors) - MAX_ENTRIES_PER_SECTION]:
                del errors[key]
        self._save()

    def get_error_fix(self, domain, error):
        """Get a known fix for an error on a domain."""
        domain = self._get_domain(domain)
        if domain not in self._data:
            return None

        error_lower = error[:200].lower().strip()
        errors = self._data[domain].get("errors", {})

        # Check for matching patterns
        for pattern, fix_data in errors.items():
            if pattern in error_lower or error_lower in pattern:
                fix_data["times_used"] = fix_data.get("times_used", 0) + 1
                self._save()
                return fix_data["fix"]
        return None

    # ═══════════════════════════════════════════
    #  Login/Session Detection
    # ═══════════════════════════════════════════

    def learn_login_indicator(self, domain, indicator_type, indicator_value):
        """Record how to detect login state on a domain.

        indicator_type: "url_pattern", "element_present", "title_pattern"
        """
        domain = self._get_domain(domain)
        self._ensure_domain(domain)
        self._data[domain]["login_indicators"][indicator_type] = indicator_value
        self._save()

    def get_login_indicators(self, domain):
        """Get known login detection rules for a domain."""
        domain = self._get_domain(domain)
        if domain in self._data:
            return self._data[domain].get("login_indicators", {})
        return {}

    # ═══════════════════════════════════════════
    #  Overlay Dismissal Memory
    # ═══════════════════════════════════════════

    def learn_overlay_dismissal(self, domain, overlay_type, dismiss_action):
        """Record how to dismiss overlays on a domain.

        overlay_type: "cookie_consent", "notification_prompt", "app_banner", "popup"
        dismiss_action: The action that worked, e.g. "click('Accept all')"
        """
        domain = self._get_domain(domain)
        self._ensure_domain(domain)
        self._data[domain]["overlay_dismissals"][overlay_type] = {
            "action": dismiss_action[:200],
            "last_used": datetime.now().isoformat(),
        }
        self._save()

    def get_overlay_dismissals(self, domain):
        """Get known overlay dismissal actions for a domain."""
        domain = self._get_domain(domain)
        if domain in self._data:
            return self._data[domain].get("overlay_dismissals", {})
        return {}

    # ═══════════════════════════════════════════
    #  Context Generation (for Agent Injection)
    # ═══════════════════════════════════════════

    def get_site_context(self, url):
        """Get a concise knowledge summary for a domain, suitable for agent prompt injection.

        Returns a formatted string with everything we know about the domain,
        or empty string if we have no knowledge.
        """
        domain = self._get_domain(url)
        if domain not in self._data:
            return ""

        data = self._data[domain]
        parts = [f"\n🧠 SITE MEMORY for {domain} ({data.get('visit_count', 0)} previous visits):"]

        # Known page types
        pages = data.get("pages", {})
        if pages:
            parts.append("  Known pages:")
            for path, info in list(pages.items())[:8]:
                parts.append(f"    {path} → {info.get('type', 'unknown')}")

        # Known successful flows
        flows = data.get("flows", {})
        if flows:
            parts.append("  Known flows:")
            for name, recordings in flows.items():
                # Find most recent successful recording
                for rec in reversed(recordings):
                    if rec.get("success"):
                        steps_str = " → ".join(rec["steps"][:8])
                        parts.append(f"    ✅ {name}: {steps_str}")
                        break

        # Known error fixes (critical for avoiding repeated mistakes)
        errors = data.get("errors", {})
        if errors:
            parts.append("  ⚠️ Known pitfalls (learn from past mistakes):")
            for err, fix_data in list(errors.items())[:5]:
                parts.append(f"    \"{err[:60]}\" → Fix: {fix_data['fix'][:80]}")

        # Overlay dismissal actions
        overlays = data.get("overlay_dismissals", {})
        if overlays:
            parts.append("  Overlay handling:")
            for otype, odata in overlays.items():
                parts.append(f"    {otype}: {odata['action']}")

        # Login indicators
        indicators = data.get("login_indicators", {})
        if indicators:
            parts.append("  Login detection:")
            for itype, ival in indicators.items():
                parts.append(f"    {itype}: {ival}")

        # Best-known selectors
        selectors = data.get("selectors", {})
        if selectors:
            best = []
            for elem, sels in selectors.items():
                ranked = sorted(
                    sels.items(),
                    key=lambda x: x[1].get("successes", 0),
                    reverse=True,
                )
                if ranked and ranked[0][1].get("successes", 0) > 0:
                    best.append(f"    {elem}: use {ranked[0][0]} ({ranked[0][1]['successes']} successes)")
            if best:
                parts.append("  Best selectors:")
                parts.extend(best[:8])

        return "\n".join(parts) if len(parts) > 1 else ""

    # ═══════════════════════════════════════════
    #  Stats
    # ═══════════════════════════════════════════

    def get_stats(self):
        """Get summary statistics."""
        return {
            "domains_known": len(self._data),
            "total_pages": sum(len(d.get("pages", {})) for d in self._data.values()),
            "total_flows": sum(len(d.get("flows", {})) for d in self._data.values()),
            "total_selectors": sum(len(d.get("selectors", {})) for d in self._data.values()),
            "total_error_fixes": sum(len(d.get("errors", {})) for d in self._data.values()),
        }


# ═══════════════════════════════════════════
#  Singleton
# ═══════════════════════════════════════════
site_knowledge = SiteKnowledge()
