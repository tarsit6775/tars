"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Agent Memory: Per-Agent Learning                 ║
╠══════════════════════════════════════════════════════════════╣
║  Each agent accumulates knowledge over time:                 ║
║    - Success patterns (what worked)                          ║
║    - Failure patterns (what didn't)                          ║
║    - User preferences                                        ║
║    - Project context                                         ║
║                                                              ║
║  Memory is injected into agent system prompts so they        ║
║  get smarter over time.                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
from datetime import datetime


class AgentMemory:
    """Persistent memory for agent learning patterns."""

    def __init__(self, base_dir):
        self.memory_dir = os.path.join(base_dir, "memory", "agents")
        os.makedirs(self.memory_dir, exist_ok=True)

    def _agent_file(self, agent_name):
        """Get memory file path for an agent."""
        safe_name = agent_name.lower().replace(" ", "_")
        return os.path.join(self.memory_dir, f"{safe_name}.json")

    def _load(self, agent_name):
        """Load agent memory from disk."""
        path = self._agent_file(agent_name)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "success_patterns": [],
            "failure_patterns": [],
            "stats": {"total_tasks": 0, "successes": 0, "failures": 0, "total_steps": 0},
        }

    def _save(self, agent_name, data):
        """Save agent memory to disk."""
        path = self._agent_file(agent_name)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def record_success(self, agent_name, task, summary, steps):
        """Record a successful task completion."""
        data = self._load(agent_name)
        data["stats"]["total_tasks"] += 1
        data["stats"]["successes"] += 1
        data["stats"]["total_steps"] += steps

        # Keep last 20 success patterns
        data["success_patterns"].append({
            "task": task[:200],
            "summary": summary[:300],
            "steps": steps,
            "timestamp": datetime.now().isoformat(),
        })
        data["success_patterns"] = data["success_patterns"][-20:]

        self._save(agent_name, data)

    def record_failure(self, agent_name, task, reason, steps):
        """Record a failed task."""
        data = self._load(agent_name)
        data["stats"]["total_tasks"] += 1
        data["stats"]["failures"] += 1
        data["stats"]["total_steps"] += steps

        # Keep last 20 failure patterns
        data["failure_patterns"].append({
            "task": task[:200],
            "reason": reason[:300],
            "steps": steps,
            "timestamp": datetime.now().isoformat(),
        })
        data["failure_patterns"] = data["failure_patterns"][-20:]

        self._save(agent_name, data)

    def get_context(self, agent_name, max_patterns=5):
        """Get memory context to inject into agent system prompt."""
        data = self._load(agent_name)
        parts = []

        stats = data["stats"]
        if stats["total_tasks"] > 0:
            rate = (stats["successes"] / stats["total_tasks"]) * 100
            avg_steps = stats["total_steps"] / stats["total_tasks"]
            parts.append(
                f"Track record: {stats['successes']}/{stats['total_tasks']} tasks succeeded ({rate:.0f}%), "
                f"avg {avg_steps:.1f} steps per task."
            )

        # Recent failure patterns (so agent can avoid repeating mistakes)
        failures = data["failure_patterns"][-max_patterns:]
        if failures:
            parts.append("\nCommon failure patterns to avoid:")
            for f in failures:
                parts.append(f"  - Task '{f['task'][:80]}' failed: {f['reason'][:120]}")

        # Recent success patterns (so agent knows what works)
        successes = data["success_patterns"][-max_patterns:]
        if successes:
            parts.append("\nRecent successful approaches:")
            for s in successes:
                parts.append(f"  - '{s['task'][:80]}' in {s['steps']} steps")

        return "\n".join(parts) if parts else ""

    def get_all_stats(self):
        """Get stats for all agents."""
        stats = {}
        if not os.path.exists(self.memory_dir):
            return stats

        for filename in os.listdir(self.memory_dir):
            if filename.endswith(".json"):
                agent_name = filename[:-5].replace("_", " ").title()
                data = self._load(agent_name)
                stats[agent_name] = data["stats"]

        return stats
