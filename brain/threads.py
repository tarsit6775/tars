"""
╔══════════════════════════════════════════════════════════════╗
║      TARS Brain v4 — Phase 3: Conversation Threading         ║
╠══════════════════════════════════════════════════════════════╣
║  Tracks conversation threads so follow-ups find context.     ║
║                                                              ║
║  Problem: "search flights to NYC" → (result) → "did it      ║
║  work?" → TARS doesn't know what "it" refers to.            ║
║                                                              ║
║  Solution: Messages are grouped into threads by topic.       ║
║  Follow-ups attach to the active thread. New topics start    ║
║  new threads. The Brain gets thread context injected into    ║
║  its prompt so it always knows what "it" refers to.          ║
║                                                              ║
║  Also provides:                                              ║
║    - Decision Journal: every Brain decision is logged         ║
║    - Task Decomposition: complex tasks → tracked subtasks    ║
║    - Confidence scoring infrastructure                        ║
║                                                              ║
║  Thread lifecycle:                                           ║
║    new message → route_message() → Thread                    ║
║    TARS responds → record_response()                         ║
║    Thread idle >10min → becomes stale                        ║
║    Max 20 threads in memory, oldest pruned                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import uuid
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


# ─── Data Classes ────────────────────────────────────

@dataclass
class ThreadMessage:
    """A single message in a thread."""
    role: str           # "user" or "tars"
    text: str
    timestamp: float
    intent_type: str = ""
    confidence: float = 0.0


@dataclass
class Decision:
    """A logged Brain decision with reasoning."""
    action: str         # What was decided (e.g., "deploy_dev_agent")
    reasoning: str      # Why (e.g., "Multi-file code change requires VS Code Agent Mode")
    confidence: float   # 0-100
    timestamp: float = 0.0
    outcome: str = ""   # Filled after execution: "success", "failed", "pending"


@dataclass
class Subtask:
    """A subtask in a task decomposition."""
    id: int
    description: str
    status: str = "pending"     # pending, in_progress, completed, failed, skipped
    agent: str = ""             # Which agent handles this
    result: str = ""            # Execution result summary
    depends_on: List[int] = field(default_factory=list)  # Subtask IDs this depends on


@dataclass
class Thread:
    """A conversation thread with full context."""
    id: str
    created_at: float
    last_activity: float
    topic: str                  # Short description of what this thread is about
    messages: List[ThreadMessage] = field(default_factory=list)
    active_task: Optional[str] = None     # Current task being worked on
    task_status: str = "idle"             # idle, working, waiting_user, completed, failed
    subtasks: List[Subtask] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    escalation_count: int = 0             # How many times we've escalated to user
    metadata: Dict = field(default_factory=dict)  # Flexible storage

    @property
    def is_stale(self) -> bool:
        """Thread is stale if no activity for 10 minutes."""
        return (time.time() - self.last_activity) > 600

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.created_at) / 60

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_messages(self) -> List[ThreadMessage]:
        return [m for m in self.messages if m.role == "user"]

    @property
    def tars_messages(self) -> List[ThreadMessage]:
        return [m for m in self.messages if m.role == "tars"]

    @property
    def last_user_message(self) -> Optional[ThreadMessage]:
        user_msgs = self.user_messages
        return user_msgs[-1] if user_msgs else None

    @property
    def last_tars_message(self) -> Optional[ThreadMessage]:
        tars_msgs = self.tars_messages
        return tars_msgs[-1] if tars_msgs else None

    @property
    def pending_subtasks(self) -> List[Subtask]:
        return [s for s in self.subtasks if s.status in ("pending", "in_progress")]

    @property
    def completed_subtasks(self) -> List[Subtask]:
        return [s for s in self.subtasks if s.status == "completed"]

    @property
    def summary(self) -> str:
        """Compact summary for context injection."""
        msg_count = self.message_count
        last_msg = self.messages[-1].text[:80] if self.messages else "empty"
        status = f" [{self.task_status}]" if self.active_task else ""
        subtask_info = ""
        if self.subtasks:
            done = len(self.completed_subtasks)
            total = len(self.subtasks)
            subtask_info = f" ({done}/{total} subtasks)"
        return f"Thread '{self.topic}'{status}{subtask_info} ({msg_count} msgs) — last: {last_msg}"

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "topic": self.topic,
            "task_status": self.task_status,
            "active_task": self.active_task,
            "message_count": self.message_count,
            "escalation_count": self.escalation_count,
            "messages": [
                {"role": m.role, "text": m.text[:200], "intent": m.intent_type}
                for m in self.messages[-10:]  # Last 10 only
            ],
            "subtasks": [
                {"id": s.id, "desc": s.description[:100], "status": s.status}
                for s in self.subtasks
            ],
            "decisions": [
                {"action": d.action, "confidence": d.confidence, "outcome": d.outcome}
                for d in self.decisions[-5:]  # Last 5 only
            ],
        }


# ─── Thread Manager ─────────────────────────────────

class ThreadManager:
    """
    Manages conversation threads for the Brain.
    
    Rules:
    - New topic → new thread
    - Follow-up → attaches to most recent active thread
    - Correction → modifies the active thread's context
    - After 10 min inactivity → thread becomes stale (but not deleted)
    - Acknowledgments → attach to active thread
    - Emergency → always active thread if exists, else new
    
    Provides:
    - Decision journaling: every Brain decision is logged with reasoning
    - Task decomposition: complex tasks broken into tracked subtasks
    - Thread-aware context for the Brain prompt
    """

    MAX_THREADS = 20        # Keep last 20 threads in memory
    STALE_TIMEOUT = 600     # 10 minutes

    def __init__(self, persistence_dir: Optional[str] = None):
        self._threads: Dict[str, Thread] = {}
        self._active_thread_id: Optional[str] = None
        self._thread_order: List[str] = []  # Most recent first
        self._persistence_dir = persistence_dir

        # Load persisted threads if available
        if persistence_dir:
            self._load_threads()

    # ═══════════════════════════════════════════════════
    #  Properties
    # ═══════════════════════════════════════════════════

    @property
    def active_thread(self) -> Optional[Thread]:
        """Get the currently active thread (None if stale or doesn't exist)."""
        if self._active_thread_id and self._active_thread_id in self._threads:
            thread = self._threads[self._active_thread_id]
            if not thread.is_stale:
                return thread
        return None

    @property
    def has_active_thread(self) -> bool:
        return self.active_thread is not None

    @property
    def all_threads(self) -> List[Thread]:
        """All threads in recency order."""
        return [self._threads[tid] for tid in self._thread_order if tid in self._threads]

    @property
    def recent_threads(self) -> List[Thread]:
        """Last 5 threads for context."""
        return self.all_threads[:5]

    # ═══════════════════════════════════════════════════
    #  Thread Lifecycle
    # ═══════════════════════════════════════════════════

    def create_thread(self, topic: str, first_message: str,
                      intent_type: str = "", confidence: float = 0.0) -> Thread:
        """Create a new conversation thread."""
        thread_id = str(uuid.uuid4())[:8]
        now = time.time()

        thread = Thread(
            id=thread_id,
            created_at=now,
            last_activity=now,
            topic=topic[:80],
        )
        thread.messages.append(ThreadMessage(
            role="user",
            text=first_message,
            timestamp=now,
            intent_type=intent_type,
            confidence=confidence,
        ))

        self._threads[thread_id] = thread
        self._thread_order.insert(0, thread_id)
        self._active_thread_id = thread_id

        # Prune old threads
        self._prune()
        self._persist()

        return thread

    def add_message(self, thread_id: str, role: str, text: str,
                    intent_type: str = "", confidence: float = 0.0) -> Thread:
        """Add a message to an existing thread."""
        thread = self._threads.get(thread_id)
        if not thread:
            return self.create_thread("continued", text, intent_type, confidence)

        thread.messages.append(ThreadMessage(
            role=role,
            text=text,
            timestamp=time.time(),
            intent_type=intent_type,
            confidence=confidence,
        ))
        thread.last_activity = time.time()

        # Move to front of order
        if thread_id in self._thread_order:
            self._thread_order.remove(thread_id)
        self._thread_order.insert(0, thread_id)
        self._active_thread_id = thread_id

        self._persist()
        return thread

    # ═══════════════════════════════════════════════════
    #  Message Routing
    # ═══════════════════════════════════════════════════

    def route_message(self, text: str, intent_type: str,
                      confidence: float = 0.0) -> Thread:
        """
        Route a message to the right thread based on intent.
        
        This is the main entry point for incoming messages.
        The intent classifier has already determined what type
        of message this is.
        """
        active = self.active_thread

        # Follow-ups, corrections, acknowledgments → active thread
        if intent_type in ("FOLLOW_UP", "CORRECTION", "ACKNOWLEDGMENT") and active:
            return self.add_message(active.id, "user", text, intent_type, confidence)

        # Emergency → active thread if exists, else new
        if intent_type == "EMERGENCY":
            if active:
                return self.add_message(active.id, "user", text, intent_type, confidence)
            return self.create_thread("🚨 Emergency", text, intent_type, confidence)

        # Task → always new thread (clean context)
        if intent_type == "TASK":
            topic = self._extract_topic(text)
            return self.create_thread(topic, text, intent_type, confidence)

        # Quick question → new thread (but could reuse if same topic)
        if intent_type == "QUICK_QUESTION":
            topic = self._extract_topic(text)
            return self.create_thread(f"Q: {topic}", text, intent_type, confidence)

        # Conversation → reuse active thread if fresh, else new
        if active and not active.is_stale:
            return self.add_message(active.id, "user", text, intent_type, confidence)

        topic = self._extract_topic(text)
        return self.create_thread(f"Chat: {topic}", text, intent_type, confidence)

    def record_response(self, text: str):
        """Record TARS's response in the active thread."""
        active = self.active_thread
        if active:
            self.add_message(active.id, "tars", text[:500])

    # ═══════════════════════════════════════════════════
    #  Task Management
    # ═══════════════════════════════════════════════════

    def set_task(self, task: str, status: str = "working"):
        """Set/update the active task in the current thread."""
        active = self.active_thread
        if active:
            active.active_task = task[:200]
            active.task_status = status
            self._persist()

    def set_task_status(self, status: str):
        """Update task status: idle, working, waiting_user, completed, failed."""
        active = self.active_thread
        if active:
            active.task_status = status
            self._persist()

    def add_subtasks(self, subtasks: List[dict]):
        """
        Add subtasks to the current thread's task decomposition.
        
        Each subtask dict: {"description": str, "agent": str, "depends_on": [int]}
        """
        active = self.active_thread
        if not active:
            return

        for i, st in enumerate(subtasks):
            active.subtasks.append(Subtask(
                id=len(active.subtasks) + 1,
                description=st.get("description", ""),
                agent=st.get("agent", ""),
                depends_on=st.get("depends_on", []),
            ))
        self._persist()

    def update_subtask(self, subtask_id: int, status: str, result: str = ""):
        """Update a subtask's status and result."""
        active = self.active_thread
        if not active:
            return

        for st in active.subtasks:
            if st.id == subtask_id:
                st.status = status
                if result:
                    st.result = result[:300]
                break
        self._persist()

    def get_next_subtask(self) -> Optional[Subtask]:
        """Get the next pending subtask whose dependencies are met."""
        active = self.active_thread
        if not active:
            return None

        completed_ids = {s.id for s in active.subtasks if s.status == "completed"}
        for st in active.subtasks:
            if st.status == "pending":
                deps_met = all(d in completed_ids for d in st.depends_on)
                if deps_met:
                    return st
        return None

    # ═══════════════════════════════════════════════════
    #  Decision Journal
    # ═══════════════════════════════════════════════════

    def log_decision(self, action: str, reasoning: str,
                     confidence: float) -> Decision:
        """
        Log a Brain decision with reasoning.
        
        Every significant decision is recorded:
        - Which agent to deploy
        - What approach to take
        - Whether to escalate to user
        
        This creates an auditable trail and helps the Brain
        learn from past decisions.
        """
        decision = Decision(
            action=action,
            reasoning=reasoning,
            confidence=confidence,
            timestamp=time.time(),
        )

        active = self.active_thread
        if active:
            active.decisions.append(decision)
            # Keep last 20 decisions per thread
            if len(active.decisions) > 20:
                active.decisions = active.decisions[-20:]
            self._persist()

        return decision

    def update_decision_outcome(self, outcome: str):
        """Update the most recent decision with its outcome."""
        active = self.active_thread
        if active and active.decisions:
            active.decisions[-1].outcome = outcome
            self._persist()

    def record_escalation(self):
        """Record that we escalated to the user."""
        active = self.active_thread
        if active:
            active.escalation_count += 1

    # ═══════════════════════════════════════════════════
    #  Context for Brain
    # ═══════════════════════════════════════════════════

    def get_context_for_brain(self) -> str:
        """
        Build a context string for injection into the Brain's system prompt.
        
        Includes:
        - Active thread: full recent history, task status, subtasks, decisions
        - Decision quality metrics (success rate, common patterns)
        - Recent threads: brief summaries for cross-reference
        - Topic drift detection
        
        This is the thread-awareness that makes "did it work?" answerable.
        """
        parts = []
        active = self.active_thread

        if active:
            parts.append("## Active Conversation Thread")
            parts.append(f"Topic: {active.topic}")
            parts.append(f"Status: {active.task_status}")
            parts.append(f"Duration: {active.age_minutes:.0f} min")

            if active.active_task:
                parts.append(f"Current task: {active.active_task}")

            if active.escalation_count > 0:
                parts.append(f"Escalations to user: {active.escalation_count}")

            # Recent messages (last 15 for full context)
            recent = active.messages[-15:]
            if recent:
                parts.append("\nRecent messages:")
                for msg in recent:
                    prefix = "👤 Abdullah" if msg.role == "user" else "🤖 TARS"
                    text = msg.text[:250]
                    parts.append(f"  {prefix}: {text}")

            # Subtask progress
            if active.subtasks:
                parts.append("\nTask decomposition:")
                for st in active.subtasks:
                    icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅",
                            "failed": "❌", "skipped": "⏭️"}.get(st.status, "•")
                    parts.append(f"  {icon} [{st.id}] {st.description[:100]} ({st.status})")
                    if st.result:
                        parts.append(f"       → {st.result[:150]}")

            # Recent decisions with quality metrics
            if active.decisions:
                total_d = len(active.decisions)
                outcomes = [d.outcome for d in active.decisions if d.outcome]
                successes = sum(1 for o in outcomes if o in ("success", "completed", "done"))
                failures = sum(1 for o in outcomes if o in ("failed", "error"))
                if outcomes:
                    parts.append(f"\nDecision track record: {successes}✅ {failures}❌ of {len(outcomes)} evaluated")

                parts.append(f"Recent decisions:")
                for d in active.decisions[-5:]:
                    outcome = f" → {d.outcome}" if d.outcome else ""
                    parts.append(f"  → {d.action} (confidence: {d.confidence:.0f}/100){outcome}")
                    if d.reasoning:
                        parts.append(f"    Reasoning: {d.reasoning[:150]}")

        # Brief summaries of other recent threads
        other_threads = [t for t in self.recent_threads
                         if t.id != (active.id if active else None)]
        if other_threads:
            parts.append("\n## Recent Threads (for cross-reference)")
            for t in other_threads[:3]:
                stale = " [stale]" if t.is_stale else ""
                parts.append(f"  - {t.summary}{stale}")

        return "\n".join(parts) if parts else ""

    def get_decision_quality(self) -> dict:
        """
        Get decision quality metrics across recent threads.
        Helps metacognition understand brain decision-making quality.
        """
        all_decisions = []
        for thread in self.recent_threads[:5]:
            all_decisions.extend(thread.decisions)

        if not all_decisions:
            return {"total": 0, "success_rate": 0.0}

        evaluated = [d for d in all_decisions if d.outcome]
        successes = sum(1 for d in evaluated if d.outcome in ("success", "completed", "done"))
        failures = sum(1 for d in evaluated if d.outcome in ("failed", "error"))

        # Average confidence of successful vs failed decisions
        success_conf = [d.confidence for d in evaluated if d.outcome in ("success", "completed", "done")]
        failure_conf = [d.confidence for d in evaluated if d.outcome in ("failed", "error")]

        return {
            "total": len(all_decisions),
            "evaluated": len(evaluated),
            "successes": successes,
            "failures": failures,
            "success_rate": (successes / max(len(evaluated), 1)) * 100,
            "avg_success_confidence": sum(success_conf) / max(len(success_conf), 1),
            "avg_failure_confidence": sum(failure_conf) / max(len(failure_conf), 1),
        }

    def get_thread_stats(self) -> dict:
        """Get thread statistics for dashboard/monitoring."""
        active = self.active_thread
        return {
            "total_threads": len(self._threads),
            "active_thread_id": self._active_thread_id,
            "active_topic": active.topic if active else None,
            "active_status": active.task_status if active else "idle",
            "active_messages": active.message_count if active else 0,
            "active_subtasks": len(active.subtasks) if active else 0,
            "active_decisions": len(active.decisions) if active else 0,
            "threads": [t.to_dict() for t in self.recent_threads[:5]],
        }

    # ═══════════════════════════════════════════════════
    #  Internal Helpers
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _extract_topic(text: str) -> str:
        """
        Extract a short, meaningful topic from a message for thread naming.
        Uses domain-aware keyword extraction instead of just first 50 chars.
        """
        import re
        clean = text.strip()

        # Remove common prefixes
        clean = re.sub(
            r"^(hey |hi |yo |can you |could you |please |i need you to |i want you to |"
            r"i need |i want |go ahead and |let's |let me |help me )",
            "", clean.lower(),
        ).strip()

        # Try to extract a meaningful topic via action + object
        # e.g. "search flights to NYC" → "Search flights to NYC"
        action_match = re.match(
            r"(search|find|create|build|make|send|email|book|order|deploy|"
            r"install|setup|fix|debug|check|update|download|research|track|"
            r"schedule|remind|generate|monitor|organize|write|delete|move|"
            r"compare|analyze|run|test|configure)\s+(.{5,50})",
            clean, re.IGNORECASE
        )
        if action_match:
            topic = f"{action_match.group(1)} {action_match.group(2)}"
            # Break at word boundary if too long
            if len(topic) > 50:
                topic = topic[:50].rsplit(" ", 1)[0]
            return topic[:1].upper() + topic[1:]

        # Look for quoted targets
        quoted = re.findall(r'"([^"]{3,40})"', clean)
        if quoted:
            return quoted[0][:1].upper() + quoted[0][1:]

        # Fall back to first 50 chars, break at word boundary
        if len(clean) > 50:
            clean = clean[:50].rsplit(" ", 1)[0]

        # Capitalize first letter
        return clean[:1].upper() + clean[1:] if clean else "Untitled"

    def _prune(self):
        """Remove oldest threads beyond MAX_THREADS."""
        while len(self._thread_order) > self.MAX_THREADS:
            old_id = self._thread_order.pop()
            self._threads.pop(old_id, None)

    def _persist(self):
        """Save thread state to disk for crash recovery."""
        if not self._persistence_dir:
            return

        try:
            path = Path(self._persistence_dir) / "threads.json"
            path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "active_thread_id": self._active_thread_id,
                "thread_order": self._thread_order[:10],  # Persist last 10
                "threads": {
                    tid: self._threads[tid].to_dict()
                    for tid in self._thread_order[:10]
                    if tid in self._threads
                },
            }
            path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass  # Non-critical — don't crash on persistence failure

    def _load_threads(self):
        """Load persisted thread state. Non-critical — failure is OK."""
        if not self._persistence_dir:
            return

        try:
            path = Path(self._persistence_dir) / "threads.json"
            if not path.exists():
                return

            data = json.loads(path.read_text())
            self._active_thread_id = data.get("active_thread_id")
            self._thread_order = data.get("thread_order", [])

            # Reconstruct threads (partial — messages are truncated)
            for tid, tdata in data.get("threads", {}).items():
                thread = Thread(
                    id=tid,
                    created_at=tdata.get("created_at", 0),
                    last_activity=tdata.get("last_activity", 0),
                    topic=tdata.get("topic", "restored"),
                    task_status=tdata.get("task_status", "idle"),
                    active_task=tdata.get("active_task"),
                    escalation_count=tdata.get("escalation_count", 0),
                )
                for mdata in tdata.get("messages", []):
                    thread.messages.append(ThreadMessage(
                        role=mdata.get("role", "user"),
                        text=mdata.get("text", ""),
                        timestamp=tdata.get("last_activity", 0),
                        intent_type=mdata.get("intent", ""),
                    ))
                self._threads[tid] = thread

        except Exception:
            pass  # Non-critical
