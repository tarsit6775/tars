"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Inter-Agent Communication Hub                    ║
╠══════════════════════════════════════════════════════════════╣
║  Message passing between agents via the orchestrator brain.  ║
║  Brain is the central hub — no direct agent-to-agent comms.  ║
║                                                              ║
║  v2: Structured scratchpad — agents can share typed data     ║
║  (selectors, URLs, extracted facts) not just strings.        ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentMessage:
    """A message passed between agents via the brain."""
    from_agent: str
    to_agent: str
    content: str
    msg_type: str = "info"       # info, request, result, handoff, scratchpad
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ScratchpadEntry:
    """A typed structured data entry on the shared scratchpad."""
    key: str                     # e.g., "login_selectors", "search_results"
    data_type: str               # selectors, urls, facts, credentials, code, error
    value: Any                   # The actual data (dict, list, str, etc.)
    source_agent: str            # Who wrote it
    timestamp: float = field(default_factory=time.time)


class AgentComms:
    """Central communication hub for inter-agent messaging.
    
    All communication flows through the brain (orchestrator):
      Agent A → Brain → Agent B
    
    v2: Includes a structured scratchpad where agents can read/write
    typed data (selectors, URLs, extracted facts, error context) so
    downstream agents don't have to re-discover information.
    """

    def __init__(self):
        self._messages: List[AgentMessage] = []
        self._handoff_context: Dict[str, str] = {}  # agent → context from prev agent
        self._scratchpad: Dict[str, ScratchpadEntry] = {}  # key → entry
        self._scratchpad_lock = threading.Lock()

    def send(self, from_agent: str, to_agent: str, content: str,
             msg_type: str = "info", metadata: Dict = None) -> AgentMessage:
        """Record a message from one agent to another."""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            msg_type=msg_type,
            metadata=metadata or {},
        )
        self._messages.append(msg)
        return msg

    # ─── Structured Scratchpad ───────────────────────

    def write_scratchpad(self, key: str, value: Any, data_type: str,
                         source_agent: str) -> None:
        """Write structured data to the shared scratchpad.
        
        Examples:
            write_scratchpad("login_selectors", {"email": "#email", "password": "#pass"},
                             "selectors", "browser")
            write_scratchpad("search_results", ["url1", "url2"], "urls", "research")
            write_scratchpad("api_key", "sk-...", "credentials", "coder")
        """
        entry = ScratchpadEntry(
            key=key,
            data_type=data_type,
            value=value,
            source_agent=source_agent,
        )
        with self._scratchpad_lock:
            self._scratchpad[key] = entry

        self.send(source_agent, "scratchpad", str(value)[:200],
                  msg_type="scratchpad", metadata={"key": key, "data_type": data_type})

    def read_scratchpad(self, key: str) -> Optional[Any]:
        """Read a value from the scratchpad by key. Returns None if not found."""
        with self._scratchpad_lock:
            entry = self._scratchpad.get(key)
            return entry.value if entry else None

    def read_scratchpad_by_type(self, data_type: str) -> Dict[str, Any]:
        """Read all scratchpad entries of a given type.
        
        Returns dict of {key: value} for all entries matching the type.
        """
        with self._scratchpad_lock:
            return {
                k: v.value for k, v in self._scratchpad.items()
                if v.data_type == data_type
            }

    def get_scratchpad_summary(self) -> str:
        """Get a human-readable summary of all scratchpad entries."""
        with self._scratchpad_lock:
            if not self._scratchpad:
                return ""
            lines = ["## Shared Scratchpad"]
            for key, entry in self._scratchpad.items():
                age = int(time.time() - entry.timestamp)
                val_preview = str(entry.value)[:150]
                lines.append(f"  [{entry.data_type}] {key} (by {entry.source_agent}, {age}s ago): {val_preview}")
            return "\n".join(lines)

    # ─── Handoff ─────────────────────────────────────

    def handoff(self, from_agent: str, to_agent: str, context: str,
                task: str = "") -> str:
        """Create a handoff context when one agent passes work to another.
        
        v2: Also includes any relevant scratchpad data in the handoff.
        """
        # Include scratchpad summary if there's data
        scratchpad_info = self.get_scratchpad_summary()
        
        handoff_text = (
            f"=== HANDOFF FROM {from_agent.upper()} AGENT ===\n"
            f"Previous agent ({from_agent}) worked on this task and provides context:\n"
            f"{context}\n"
            f"{'Task for you: ' + task if task else ''}\n"
        )
        
        if scratchpad_info:
            handoff_text += f"\n{scratchpad_info}\n"
        
        handoff_text += "=== END HANDOFF ==="

        self._handoff_context[to_agent] = handoff_text

        self.send(
            from_agent=from_agent,
            to_agent=to_agent,
            content=context,
            msg_type="handoff",
            metadata={"task": task},
        )

        return handoff_text

    def get_handoff_context(self, agent_name: str) -> Optional[str]:
        """Get any handoff context waiting for an agent, then clear it.
        
        v2: Always includes scratchpad summary if available.
        """
        ctx = self._handoff_context.pop(agent_name, None)
        
        # Even without an explicit handoff, include scratchpad if populated
        if not ctx:
            scratchpad_info = self.get_scratchpad_summary()
            return scratchpad_info if scratchpad_info else None
        
        return ctx

    def get_messages(self, agent: str = None, msg_type: str = None,
                     limit: int = 20) -> List[AgentMessage]:
        """Get recent messages, optionally filtered."""
        msgs = self._messages
        if agent:
            msgs = [m for m in msgs if m.from_agent == agent or m.to_agent == agent]
        if msg_type:
            msgs = [m for m in msgs if m.msg_type == msg_type]
        return msgs[-limit:]

    def get_conversation_log(self) -> str:
        """Get a formatted log of all agent communications."""
        if not self._messages:
            return "No inter-agent communications yet."

        lines = ["=== Agent Communication Log ==="]
        for msg in self._messages[-30:]:  # Last 30 messages
            ts = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
            lines.append(f"[{ts}] {msg.from_agent} → {msg.to_agent} ({msg.msg_type}): {msg.content[:200]}")
        return "\n".join(lines)

    def clear(self):
        """Clear all messages, handoff context, and scratchpad."""
        self._messages.clear()
        self._handoff_context.clear()
        with self._scratchpad_lock:
            self._scratchpad.clear()


# Global singleton
agent_comms = AgentComms()
