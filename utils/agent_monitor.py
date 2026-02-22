"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Agent Monitor: Real-Time Multi-Agent Tracking    ║
╠══════════════════════════════════════════════════════════════╣
║  Tracks all agents in real-time. Called directly by the       ║
║  executor when agent states change.                          ║
╚══════════════════════════════════════════════════════════════╝
"""

import time


class AgentMonitor:
    """Tracks the state of all agents in real-time."""

    AGENTS = ["browser", "coder", "system", "research", "file", "dev", "screen"]

    def __init__(self):
        self._states = {}
        for agent in self.AGENTS:
            self._states[agent] = {
                "status": "idle",       # idle, working, done, stuck, escalated
                "task": None,
                "step": 0,
                "max_steps": 40,
                "started_at": None,
                "completed_at": None,
                "result": None,
                "attempt": 0,
            }

    def on_started(self, agent, task="", attempt=1):
        """Call when an agent starts a task."""
        if agent in self._states:
            self._states[agent].update({
                "status": "working",
                "task": task,
                "step": 0,
                "started_at": time.time(),
                "completed_at": None,
                "result": None,
                "attempt": attempt,
            })

    def on_step(self, agent, step=0):
        """Call when an agent takes a step."""
        if agent in self._states:
            self._states[agent]["step"] = step

    def on_completed(self, agent, success=False, steps=0):
        """Call when an agent finishes."""
        if agent in self._states:
            self._states[agent].update({
                "status": "done" if success else "stuck",
                "completed_at": time.time(),
                "step": steps,
                "result": "success" if success else "failed",
            })

    def on_stuck(self, agent):
        """Call when an agent gets stuck."""
        if agent in self._states:
            self._states[agent]["status"] = "stuck"

    def on_escalated(self, agent):
        """Call when an agent task is escalated."""
        if agent in self._states:
            self._states[agent]["status"] = "escalated"

    def get_status(self, agent=None):
        """Get status of one or all agents."""
        if agent:
            return self._states.get(agent, {"status": "unknown"})
        return dict(self._states)

    def get_active_agents(self):
        """Get list of currently active agents."""
        return [name for name, state in self._states.items() if state["status"] == "working"]

    def get_dashboard_data(self):
        """Get formatted data for the dashboard."""
        agents = []
        for name in self.AGENTS:
            state = self._states[name]
            duration = None
            if state["started_at"]:
                end = state["completed_at"] or time.time()
                duration = round(end - state["started_at"], 1)

            agents.append({
                "name": name,
                "emoji": {"browser": "🌐", "coder": "💻", "system": "⚙️", "research": "🔍", "file": "📁", "dev": "🛠️", "screen": "🖥️"}.get(name, "🤖"),
                "status": state["status"],
                "task": (state["task"] or "")[:100],
                "step": state["step"],
                "max_steps": state["max_steps"],
                "duration": duration,
                "attempt": state["attempt"],
            })

        return {"agents": agents, "active_count": len(self.get_active_agents())}

    def reset(self, agent=None):
        """Reset state of one or all agents to idle."""
        targets = [agent] if agent else self.AGENTS
        for name in targets:
            if name in self._states:
                self._states[name] = {
                    "status": "idle",
                    "task": None,
                    "step": 0,
                    "max_steps": 40,
                    "started_at": None,
                    "completed_at": None,
                    "result": None,
                    "attempt": 0,
                }


# Global singleton
agent_monitor = AgentMonitor()
