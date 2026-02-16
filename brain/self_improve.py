"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Self-Improvement Engine                          ║
╠══════════════════════════════════════════════════════════════╣
║  Post-task review, pattern learning, and strategy evolution. ║
║  Makes TARS smarter with every task it completes.            ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional

from memory.agent_memory import AgentMemory


class SelfImproveEngine:
    """Learns from every task to make TARS smarter over time.
    
    After each task completes (success or failure), this engine:
    1. Records the outcome in agent memory
    2. Analyzes patterns across tasks
    3. Generates strategy recommendations
    4. Builds a knowledge base of what works
    """

    def __init__(self, agent_memory: AgentMemory, llm_client=None, model: str = None):
        self.memory = agent_memory
        self.llm_client = llm_client
        self.model = model
        self._session_log = []  # This session's tasks

    def record_task_outcome(self, agent_name: str, task: str,
                            result: Dict, escalation_history: list = None):
        """Record the outcome of an agent task execution.
        
        Args:
            agent_name: Which agent ran the task
            task: What the task was
            result: {success, content, steps, stuck, stuck_reason}
            escalation_history: List of escalation attempts if any
        """
        entry = {
            "agent": agent_name,
            "task": task,
            "success": result.get("success", False),
            "steps": result.get("steps", 0),
            "timestamp": time.time(),
            "escalation_history": escalation_history or [],
        }

        if result.get("success"):
            self.memory.record_success(
                agent_name=agent_name,
                task=task,
                summary=result.get("content", ""),
                steps=result.get("steps", 0),
            )
            entry["outcome"] = "success"
        else:
            reason = result.get("stuck_reason", result.get("content", "unknown"))
            self.memory.record_failure(
                agent_name=agent_name,
                task=task,
                reason=reason,
                steps=result.get("steps", 0),
            )
            entry["outcome"] = "failure"
            entry["failure_reason"] = reason

        self._session_log.append(entry)

    def get_pre_task_advice(self, agent_name: str, task: str) -> Optional[str]:
        """Get advice for an agent before it starts a task.
        
        Checks memory for similar past failures and successes
        to provide guidance.
        """
        context = self.memory.get_context(agent_name)
        if not context:
            return None

        return context

    def get_session_summary(self) -> str:
        """Get a summary of this session's performance."""
        if not self._session_log:
            return "No tasks completed this session."

        total = len(self._session_log)
        successes = sum(1 for e in self._session_log if e["outcome"] == "success")
        failures = total - successes
        avg_steps = sum(e["steps"] for e in self._session_log) / max(total, 1)

        escalated = sum(1 for e in self._session_log if e.get("escalation_history"))

        lines = [
            f"📊 Session Summary",
            f"   Tasks: {total} total, {successes} ✅, {failures} ❌",
            f"   Avg steps: {avg_steps:.1f}",
            f"   Escalated: {escalated}",
            "",
        ]

        # Per-agent breakdown
        agents_used = set(e["agent"] for e in self._session_log)
        for agent in sorted(agents_used):
            agent_tasks = [e for e in self._session_log if e["agent"] == agent]
            agent_success = sum(1 for e in agent_tasks if e["outcome"] == "success")
            lines.append(f"   {agent}: {agent_success}/{len(agent_tasks)} success")

        # Common failure patterns
        failures_list = [e for e in self._session_log if e["outcome"] == "failure"]
        if failures_list:
            lines.append("")
            lines.append("   ⚠️ Failures:")
            for f in failures_list[-5:]:
                reason = f.get("failure_reason", "unknown")[:80]
                lines.append(f"     - [{f['agent']}] {reason}")

        return "\n".join(lines)

    def get_all_agent_stats(self) -> Dict:
        """Get statistics for all agents (for dashboard)."""
        return self.memory.get_all_stats()

    def run_post_task_review(self, agent_name: str, task: str,
                             result: Dict) -> Optional[str]:
        """Run an LLM-powered post-task review to extract learnings.
        
        This is a synchronous deep analysis — only run for significant
        failures or complex successes. Saves learnings to memory.
        """
        if not self.llm_client or not self.model:
            return None

        # Only review failures or tasks that took many steps
        if result.get("success") and result.get("steps", 0) < 15:
            return None

        review_prompt = f"""Analyze this agent task execution and extract learnings:

Agent: {agent_name}
Task: {task}
Success: {result.get('success')}
Steps taken: {result.get('steps', 0)}
{'Stuck reason: ' + result.get('stuck_reason', '') if not result.get('success') else ''}
Result: {str(result.get('content', ''))[:500]}

Provide a brief (2-3 sentence) analysis:
1. What went well or wrong?
2. What should be done differently next time?

Keep it concise and actionable."""

        try:
            response = self.llm_client.create(
                model=self.model,
                max_tokens=300,
                system="You are a concise task reviewer. Analyze agent outcomes and provide actionable learnings.",
                tools=[],
                messages=[{"role": "user", "content": review_prompt}],
            )

            review = ""
            if hasattr(response, "content"):
                for block in response.content:
                    if hasattr(block, "text"):
                        review += block.text
            elif isinstance(response, dict):
                # OpenAI-compatible format
                choices = response.get("choices", [])
                if choices:
                    review = choices[0].get("message", {}).get("content", "")

            if review:
                # Save the learning to memory for future reference
                self.memory.record_success(
                    agent_name=agent_name,
                    task=f"[POST-REVIEW] {task}",
                    summary=review,
                    steps=0,
                )

            return review if review else None

        except Exception:
            return None

    def clear_session(self):
        """Clear the session log (memory persists)."""
        self._session_log.clear()
