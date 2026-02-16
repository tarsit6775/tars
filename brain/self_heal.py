"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Self-Healing Engine                              ║
╠══════════════════════════════════════════════════════════════╣
║  Monitors failures, proposes code fixes to itself, asks      ║
║  Abdullah for approval, and deploys dev agent to fix TARS.   ║
║                                                              ║
║  "I found a weakness in myself. Want me to fix it?"          ║
╚══════════════════════════════════════════════════════════════╝

Flow:
  1. Brain/agents hit recurring failures → self_heal.record_failure()
  2. Engine detects patterns (same error 2+ times, agent stuck, etc.)
  3. Generates a healing proposal: what to change and why
  4. Asks Abdullah via iMessage: "I want to improve myself. Approve?"
  5. If approved → deploys dev agent on TARS's own codebase
  6. After changes → runs test_systems.py to verify nothing broke
  7. Records the healing event for future reference
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Optional, List

from utils.event_bus import event_bus

# TARS's own codebase root
TARS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class HealingProposal:
    """A proposed self-modification."""

    def __init__(self, trigger: str, diagnosis: str, prescription: str,
                 target_files: List[str], severity: str = "improvement",
                 category: str = "general"):
        self.id = f"heal_{int(time.time())}_{id(self) % 1000}"
        self.trigger = trigger            # What caused this (error message, pattern)
        self.diagnosis = diagnosis          # Why it's happening
        self.prescription = prescription    # What to change (natural language PRD)
        self.target_files = target_files    # Which files to modify
        self.severity = severity            # "critical", "improvement", "optimization"
        self.category = category            # "bug_fix", "new_capability", "performance", "reliability"
        self.status = "proposed"            # proposed → approved → healing → healed / rejected
        self.created_at = datetime.now().isoformat()
        self.approved_at = None
        self.healed_at = None
        self.result = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "diagnosis": self.diagnosis,
            "prescription": self.prescription,
            "target_files": self.target_files,
            "severity": self.severity,
            "category": self.category,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "healed_at": self.healed_at,
            "result": self.result,
        }

    def to_imessage(self) -> str:
        """Format for iMessage approval request."""
        emoji = {"critical": "🔴", "improvement": "🟡", "optimization": "🟢"}.get(self.severity, "🔵")
        return (
            f"{emoji} TARS Self-Healing Proposal\n\n"
            f"🔍 Issue: {self.trigger[:200]}\n\n"
            f"🧠 Diagnosis: {self.diagnosis[:300]}\n\n"
            f"💊 Proposed Fix: {self.prescription[:400]}\n\n"
            f"📁 Files: {', '.join(self.target_files[:5])}\n\n"
            f"Reply 'yes' to approve, 'no' to skip."
        )


class SelfHealEngine:
    """Monitors TARS for weaknesses and proposes/applies fixes to itself.

    Three trigger sources:
    1. Recurring error patterns (same error 2+ times)
    2. Agent failure spirals (3+ consecutive failures on same task type)
    3. Metacognition alerts (brain detects it's stuck/looping)

    All modifications require user approval via iMessage before execution.
    """

    # Minimum failures before proposing a heal
    FAILURE_THRESHOLD = 2
    # Cooldown between proposals (seconds) — don't spam
    PROPOSAL_COOLDOWN = 300
    # Max pending proposals
    MAX_PENDING = 5

    def __init__(self):
        self._failure_log = []           # [{error, context, timestamp, tool, agent}]
        self._proposals = []             # [HealingProposal]
        self._healing_history = []       # Completed heals
        self._last_proposal_time = 0
        self._lock = threading.Lock()
        self._pending_approval = None    # Current proposal awaiting iMessage reply
        self._heal_log_path = os.path.join(TARS_ROOT, "memory", "healing_log.json")
        self._load_history()

        # Known healing recipes — patterns we KNOW how to fix
        self._recipes = {
            "tool_not_found": {
                "diagnosis": "Brain is calling a tool name that doesn't exist in the dispatch table",
                "prescription": "Add the missing tool mapping to executor.py _dispatch() method",
                "target_files": ["executor.py", "brain/tools.py"],
                "category": "bug_fix",
            },
            "api_rate_limit": {
                "diagnosis": "LLM API is rate-limiting too frequently, degrading performance",
                "prescription": "Add exponential backoff with jitter, or add a new fallback provider",
                "target_files": ["brain/llm_client.py", "brain/planner.py"],
                "category": "reliability",
            },
            "agent_timeout": {
                "diagnosis": "Agents are consistently timing out — tasks may be too complex for single deployments",
                "prescription": "Increase timeout or add automatic task splitting in the agent",
                "target_files": ["executor.py"],
                "category": "performance",
            },
            "import_error": {
                "diagnosis": "Missing Python module preventing startup or tool execution",
                "prescription": "Add the missing package to requirements.txt and install it",
                "target_files": ["requirements.txt"],
                "category": "bug_fix",
            },
            "conversation_bleed": {
                "diagnosis": "Tasks are bleeding context into each other because conversation history is shared",
                "prescription": "Implement per-task conversation isolation in the brain's process() method",
                "target_files": ["brain/planner.py"],
                "category": "reliability",
            },
        }

    def record_failure(self, error: str, context: str = "", tool: str = "",
                       agent: str = "", details: str = ""):
        """Record a failure for pattern analysis.

        Called from:
        - planner.py when tool calls fail
        - executor.py when agents crash/timeout
        - brain._record_brain_outcome() on task failure
        """
        with self._lock:
            self._failure_log.append({
                "error": error[:500],
                "context": context[:200],
                "tool": tool,
                "agent": agent,
                "details": details[:300],
                "timestamp": time.time(),
            })

            # Keep only last 100 failures
            if len(self._failure_log) > 100:
                self._failure_log = self._failure_log[-100:]

        # Analyze for patterns
        proposal = self._analyze_failures()
        if proposal:
            self._proposals.append(proposal)
            event_bus.emit("self_heal_proposal", proposal.to_dict())
            return proposal

        return None

    def _analyze_failures(self) -> Optional[HealingProposal]:
        """Analyze failure log for recurring patterns that warrant self-healing."""
        now = time.time()

        # Cooldown check
        if now - self._last_proposal_time < self.PROPOSAL_COOLDOWN:
            return None

        # Too many pending
        pending = [p for p in self._proposals if p.status == "proposed"]
        if len(pending) >= self.MAX_PENDING:
            return None

        recent = [f for f in self._failure_log if now - f["timestamp"] < 3600]  # Last hour
        if len(recent) < self.FAILURE_THRESHOLD:
            return None

        # ── Pattern 1: Same error message repeating ──
        error_counts = {}
        for f in recent:
            # Normalize error for grouping
            key = self._normalize_error(f["error"])
            if key not in error_counts:
                error_counts[key] = {"count": 0, "entries": []}
            error_counts[key]["count"] += 1
            error_counts[key]["entries"].append(f)

        for key, data in error_counts.items():
            if data["count"] >= self.FAILURE_THRESHOLD:
                # Check if we already proposed this
                if self._already_proposed(key):
                    continue

                proposal = self._create_proposal_from_error(key, data["entries"])
                if proposal:
                    self._last_proposal_time = now
                    return proposal

        # ── Pattern 2: Same agent type failing repeatedly ──
        agent_failures = {}
        for f in recent:
            if f.get("agent"):
                agent = f["agent"]
                if agent not in agent_failures:
                    agent_failures[agent] = 0
                agent_failures[agent] += 1

        for agent, count in agent_failures.items():
            if count >= 3 and not self._already_proposed(f"agent_{agent}_spiral"):
                self._last_proposal_time = now
                return HealingProposal(
                    trigger=f"{agent} agent failed {count} times in the last hour",
                    diagnosis=f"The {agent} agent is consistently failing. Common causes: incorrect tool definitions, missing capabilities, or environment issues.",
                    prescription=(
                        f"Analyze the {agent} agent's failure patterns and improve its reliability. "
                        f"Review agents/{agent}_agent.py for error handling gaps, add retry logic, "
                        f"and update the agent's tool set if needed. Run test_systems.py after changes."
                    ),
                    target_files=[f"agents/{agent}_agent.py", "executor.py"],
                    severity="improvement",
                    category="reliability",
                )

        # ── Pattern 3: Tool dispatch failures ──
        tool_errors = [f for f in recent if "Unknown tool" in f.get("error", "")]
        if len(tool_errors) >= 2:
            tools = set(f.get("tool", "unknown") for f in tool_errors)
            if not self._already_proposed("missing_tools"):
                self._last_proposal_time = now
                return HealingProposal(
                    trigger=f"Unknown tool errors: {', '.join(tools)}",
                    diagnosis="Brain is calling tools that don't exist in the executor dispatch table",
                    prescription=(
                        f"Add dispatch entries for tools: {', '.join(tools)}. "
                        f"Check brain/tools.py for the tool schemas and add corresponding "
                        f"handlers in executor.py _dispatch() method."
                    ),
                    target_files=["executor.py", "brain/tools.py"],
                    severity="critical",
                    category="bug_fix",
                )

        return None

    def _create_proposal_from_error(self, error_key: str,
                                     entries: list) -> Optional[HealingProposal]:
        """Create a healing proposal from a recurring error pattern."""
        sample = entries[0]
        count = len(entries)

        # Check known recipes first
        for recipe_key, recipe in self._recipes.items():
            if recipe_key in error_key.lower():
                return HealingProposal(
                    trigger=f"Recurring error ({count}x): {sample['error'][:200]}",
                    diagnosis=recipe["diagnosis"],
                    prescription=recipe["prescription"],
                    target_files=recipe["target_files"],
                    severity="critical" if count >= 4 else "improvement",
                    category=recipe["category"],
                )

        # Generic proposal for unknown patterns
        context = sample.get("context", "unknown context")
        return HealingProposal(
            trigger=f"Recurring error ({count}x): {sample['error'][:200]}",
            diagnosis=f"Error keeps happening in {context}. Needs investigation.",
            prescription=(
                f"Investigate and fix the recurring error: {sample['error'][:300]}. "
                f"Context: {context}. "
                f"Check error handling, add retries if transient, or fix the root cause. "
                f"Run test_systems.py and test_brain_fixes.py after changes."
            ),
            target_files=self._guess_target_files(sample),
            severity="improvement",
            category="bug_fix",
        )

    def request_healing(self, imessage_sender, imessage_reader,
                        proposal: Optional[HealingProposal] = None) -> Optional[HealingProposal]:
        """Ask Abdullah for permission to self-heal.

        If no proposal given, picks the highest-severity pending one.
        Sends iMessage, waits for reply.
        Returns the proposal if approved, None if rejected.
        """
        if proposal is None:
            # Pick highest severity pending proposal
            pending = [p for p in self._proposals if p.status == "proposed"]
            if not pending:
                return None
            severity_order = {"critical": 0, "improvement": 1, "optimization": 2}
            pending.sort(key=lambda p: severity_order.get(p.severity, 99))
            proposal = pending[0]

        # Send approval request
        try:
            imessage_sender.send(proposal.to_imessage())
            event_bus.emit("self_heal_approval_requested", proposal.to_dict())

            # Wait for reply (5 min timeout)
            reply = imessage_reader.wait_for_reply(timeout=300)
            if reply.get("success"):
                answer = reply["content"].strip().lower()
                if answer in ("yes", "y", "approve", "do it", "go", "go ahead", "yep", "yeah"):
                    proposal.status = "approved"
                    proposal.approved_at = datetime.now().isoformat()
                    event_bus.emit("self_heal_approved", proposal.to_dict())
                    return proposal
                else:
                    proposal.status = "rejected"
                    event_bus.emit("self_heal_rejected", proposal.to_dict())
                    return None
            else:
                # Timeout — don't heal without explicit approval
                proposal.status = "rejected"
                return None
        except Exception as e:
            print(f"  ⚠️ Self-heal approval error: {e}")
            return None

    def execute_healing(self, proposal: HealingProposal, executor) -> dict:
        """Execute an approved healing proposal by deploying the dev agent.

        This is where TARS modifies its own code.
        """
        proposal.status = "healing"
        event_bus.emit("self_heal_started", proposal.to_dict())

        # Build the dev agent prompt — very specific about TARS self-modification
        prompt = self._build_healing_prompt(proposal)

        try:
            # Deploy dev agent on TARS's own codebase
            result = executor.execute("deploy_dev_agent", {"task": prompt})

            if result.get("success"):
                proposal.status = "healed"
                proposal.healed_at = datetime.now().isoformat()
                proposal.result = "success"
                self._healing_history.append(proposal.to_dict())
                self._save_history()
                event_bus.emit("self_heal_completed", proposal.to_dict())
            else:
                proposal.status = "failed"
                proposal.result = result.get("content", "Unknown failure")[:500]
                self._healing_history.append(proposal.to_dict())
                self._save_history()
                event_bus.emit("self_heal_failed", proposal.to_dict())

            return result

        except Exception as e:
            proposal.status = "failed"
            proposal.result = str(e)
            self._healing_history.append(proposal.to_dict())
            self._save_history()
            return {"success": False, "content": f"Self-healing error: {e}"}

    def propose_capability(self, description: str, reason: str) -> HealingProposal:
        """Brain can proactively propose a new capability.

        Called when the brain realizes it can't do something and wants
        to add the capability to itself.
        """
        proposal = HealingProposal(
            trigger=f"Capability gap: {description[:200]}",
            diagnosis=f"TARS cannot currently do this: {reason[:300]}",
            prescription=(
                f"Add new capability to TARS: {description}. "
                f"This may involve adding a new tool to brain/tools.py, "
                f"a new handler in executor.py, or a new agent in agents/. "
                f"Follow the existing patterns (tool schema → dispatch → handler). "
                f"Run test_systems.py after changes."
            ),
            target_files=["brain/tools.py", "executor.py"],
            severity="improvement",
            category="new_capability",
        )
        self._proposals.append(proposal)
        event_bus.emit("self_heal_proposal", proposal.to_dict())
        return proposal

    def get_pending_proposals(self) -> List[dict]:
        """Get all pending proposals (for dashboard)."""
        return [p.to_dict() for p in self._proposals if p.status == "proposed"]

    def get_healing_history(self) -> List[dict]:
        """Get history of completed heals."""
        return list(self._healing_history)

    def get_stats(self) -> dict:
        """Get self-healing stats for dashboard."""
        return {
            "total_failures_recorded": len(self._failure_log),
            "proposals_total": len(self._proposals),
            "proposals_pending": len([p for p in self._proposals if p.status == "proposed"]),
            "proposals_approved": len([p for p in self._proposals if p.status == "approved"]),
            "heals_completed": len([h for h in self._healing_history if h.get("status") == "healed"]),
            "heals_failed": len([h for h in self._healing_history if h.get("status") == "failed"]),
        }

    # ═══════════════════════════════════════════════════
    #  INTERNAL HELPERS
    # ═══════════════════════════════════════════════════

    def _build_healing_prompt(self, proposal: HealingProposal) -> str:
        """Build a detailed prompt for the dev agent to modify TARS's code."""
        return (
            f"## TARS Self-Healing: Modify TARS's Own Code\n\n"
            f"**IMPORTANT**: You are modifying TARS itself — the autonomous agent codebase. "
            f"Be extremely careful. Follow the copilot-instructions.md rules.\n\n"
            f"**Project Path**: {TARS_ROOT}\n\n"
            f"**Issue**: {proposal.trigger}\n\n"
            f"**Diagnosis**: {proposal.diagnosis}\n\n"
            f"**What to do**: {proposal.prescription}\n\n"
            f"**Target Files**: {', '.join(proposal.target_files)}\n\n"
            f"**Rules**:\n"
            f"1. Make MINIMAL surgical changes — don't rewrite entire files\n"
            f"2. Preserve all existing imports and function signatures\n"
            f"3. Follow the project's patterns (tool return format, event_bus, etc.)\n"
            f"4. After changes, run: python3 test_systems.py\n"
            f"5. If tests pass, commit with message: 'self-heal: {proposal.category} - {proposal.trigger[:60]}'\n"
            f"6. Do NOT modify config.yaml or any files with API keys\n"
        )

    @staticmethod
    def _normalize_error(error: str) -> str:
        """Normalize error string for pattern matching."""
        import re
        s = re.sub(r"/[\w/\-.]+", "<PATH>", error)
        s = re.sub(r"\b\d{4,}\b", "<NUM>", s)
        s = re.sub(r"0x[0-9a-fA-F]+", "<HEX>", s)
        return s[:200].lower()

    def _already_proposed(self, key: str) -> bool:
        """Check if we already have a pending/recent proposal for this pattern."""
        for p in self._proposals:
            if p.status in ("proposed", "approved", "healing"):
                if key in p.trigger.lower() or key in p.diagnosis.lower():
                    return True
        # Also check recent history (last 24h)
        cutoff = (datetime.now().timestamp() - 86400)
        for h in self._healing_history:
            created = h.get("created_at", "")
            try:
                created_ts = datetime.fromisoformat(created).timestamp()
                if created_ts > cutoff:
                    if key in h.get("trigger", "").lower():
                        return True
            except (ValueError, TypeError):
                pass
        return False

    @staticmethod
    def _guess_target_files(failure: dict) -> List[str]:
        """Guess which files need modification based on failure context."""
        files = []
        context = failure.get("context", "")
        tool = failure.get("tool", "")
        agent = failure.get("agent", "")

        if agent:
            files.append(f"agents/{agent}_agent.py")
        if tool:
            files.append("executor.py")
        if "brain" in context.lower() or "planner" in context.lower():
            files.append("brain/planner.py")
        if "tool" in context.lower():
            files.append("brain/tools.py")

        return files or ["brain/planner.py"]

    def _load_history(self):
        """Load healing history from disk."""
        try:
            if os.path.exists(self._heal_log_path):
                with open(self._heal_log_path, "r") as f:
                    self._healing_history = json.load(f)
                print(f"  🩹 Loaded {len(self._healing_history)} healing records")
        except Exception:
            self._healing_history = []

    def _save_history(self):
        """Persist healing history to disk."""
        try:
            os.makedirs(os.path.dirname(self._heal_log_path), exist_ok=True)
            # Keep last 50 records
            if len(self._healing_history) > 50:
                self._healing_history = self._healing_history[-50:]
            with open(self._heal_log_path, "w") as f:
                json.dump(self._healing_history, f, indent=2)
        except Exception as e:
            print(f"  ⚠️ Failed to save healing history: {e}")
