"""
╔══════════════════════════════════════════════════════════════╗
║      TARS Brain — Phase 34: Meta-Cognitive Monitoring        ║
╠══════════════════════════════════════════════════════════════╣
║  Real-time self-awareness layer that monitors the brain's    ║
║  own thinking process. Detects:                              ║
║    - Looping (same tool called 3+ times with similar args)   ║
║    - Token waste (high usage with no progress)               ║
║    - Declining confidence                                    ║
║    - Stuck patterns (repeated failures)                      ║
║                                                              ║
║  Injects meta-prompts to course-correct the brain before     ║
║  it wastes more resources or gets truly stuck.               ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ToolCallRecord:
    """Record of a single tool call for pattern detection."""
    name: str
    args_hash: str       # Hash of the input args for dedup
    timestamp: float
    success: bool = True
    duration: float = 0.0


@dataclass
class MetaCognitiveState:
    """Snapshot of the brain's cognitive health."""
    is_looping: bool = False
    loop_tool: str = ""
    loop_count: int = 0
    is_stalled: bool = False
    stall_reason: str = ""
    confidence_trend: str = "stable"  # rising, falling, stable
    avg_confidence: float = 75.0
    token_efficiency: float = 1.0     # progress per token (higher = better)
    recommendation: str = ""
    # Phase 38: Preventive intelligence fields
    deployments_used: int = 0
    deployments_budget: int = 15
    phase: str = "planning"
    tool_diversity: float = 1.0       # 0-1 tool variety score
    progress_score: float = 1.0       # 0-1 success rate
    strategic_advice: str = ""


class MetaCognitionMonitor:
    """
    Monitors the brain's thinking loop in real-time.
    
    Called after every tool execution. Maintains a sliding window
    of recent tool calls and analyzes patterns to detect:
    
    1. LOOPING: Same tool called 3+ times with similar arguments
       → Inject: "You're looping. Try a completely different approach."
    
    2. STALLING: Many tool calls but no verify_result or send_imessage
       → Inject: "You've taken N steps without verifying or reporting. Check progress."
    
    3. CONFIDENCE DECLINE: Parsed confidence scores trending downward
       → Inject: "Your confidence is declining. Consider asking Abdullah."
    
    4. TOKEN WASTE: High token count with no deployments or results
       → Inject: "You're burning tokens on thinking without acting."
    
    5. FAILURE SPIRAL: 3+ consecutive failures across tools
       → Inject: "Multiple consecutive failures. STOP and reassess."
    """

    # Thresholds
    LOOP_THRESHOLD = 3          # Same tool+args this many times = looping
    STALL_THRESHOLD = 10        # Steps without verify/report = stalling
    CONFIDENCE_WINDOW = 5       # Last N confidence scores for trend
    FAILURE_SPIRAL_THRESHOLD = 3  # Consecutive failures
    MAX_THINKING_WITHOUT_ACTION = 5  # Max consecutive think() calls

    def __init__(self):
        self._tool_history: deque = deque(maxlen=50)  # Last 50 tool calls
        self._confidence_history: deque = deque(maxlen=20)
        self._consecutive_failures = 0
        self._steps_since_verify = 0
        self._steps_since_report = 0
        self._consecutive_thinks = 0
        self._total_steps = 0
        self._start_time = time.time()
        self._last_state = MetaCognitiveState()
        # Phase 38: Preventive intelligence
        self._deployments = []               # Track agent deployments
        self._max_deployments = 15           # Budget (set by planner via set_budget)
        self._max_tool_loops = 50            # Budget (set by planner via set_budget)
        self._tool_name_counter = Counter()  # Cumulative tool usage counts
        self._phase = "planning"             # Current phase
        self._phase_steps = Counter()        # Steps spent in each phase
        self._unique_tools_used = set()      # Distinct tools used this task
        self._successful_results = 0         # Count of successful tool calls
        self._total_token_estimate = 0       # Running token estimate

    def reset(self):
        """Reset for a new task."""
        self._tool_history.clear()
        self._confidence_history.clear()
        self._consecutive_failures = 0
        self._steps_since_verify = 0
        self._steps_since_report = 0
        self._consecutive_thinks = 0
        self._total_steps = 0
        self._start_time = time.time()
        self._last_state = MetaCognitiveState()
        # Phase 38: Reset preventive intelligence
        self._deployments.clear()
        self._tool_name_counter.clear()
        self._phase = "planning"
        self._phase_steps.clear()
        self._unique_tools_used.clear()
        self._successful_results = 0
        self._total_token_estimate = 0

    def record_tool_call(self, tool_name: str, tool_input: dict,
                         success: bool, duration: float = 0.0):
        """Record a tool call and update all tracking state."""
        # Hash the args for dedup detection
        args_hash = self._hash_args(tool_name, tool_input)

        record = ToolCallRecord(
            name=tool_name,
            args_hash=args_hash,
            timestamp=time.time(),
            success=success,
            duration=duration,
        )
        self._tool_history.append(record)
        self._total_steps += 1

        # Track consecutive patterns
        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        if tool_name == "think":
            self._consecutive_thinks += 1
        else:
            self._consecutive_thinks = 0

        if tool_name in ("verify_result",):
            self._steps_since_verify = 0
        else:
            self._steps_since_verify += 1

        if tool_name in ("send_imessage",):
            self._steps_since_report = 0
        else:
            self._steps_since_report += 1

        # Phase 38: Track diversity, success, and phase
        self._unique_tools_used.add(tool_name)
        self._tool_name_counter[tool_name] += 1
        if success:
            self._successful_results += 1
        self._phase_steps[self._phase] += 1

        # Auto-detect phase transitions from tool usage
        if tool_name in ("generate_report", "generate_presentation"):
            self._update_phase("compilation")
        elif tool_name in ("send_imessage", "send_imessage_file", "mac_mail"):
            self._update_phase("delivery")
        elif tool_name.startswith("deploy_"):
            agent = tool_name.replace("deploy_", "")
            if agent in ("research_agent",):
                self._update_phase("research")
            else:
                self._update_phase("action")

    def record_confidence(self, score: float):
        """Record a confidence score from the brain's thinking."""
        self._confidence_history.append((time.time(), score))

    def set_budget(self, max_deployments: int = 15, max_tool_loops: int = 50):
        """Set task budget limits for awareness tracking."""
        self._max_deployments = max_deployments
        self._max_tool_loops = max_tool_loops

    def record_deployment(self, agent_type: str, task: str = ""):
        """Record an agent deployment for budget tracking."""
        self._deployments.append({
            "agent": agent_type,
            "task": task[:200],
            "timestamp": time.time(),
        })

    def _update_phase(self, new_phase: str):
        """Track phase transitions for awareness."""
        if self._phase != new_phase:
            self._phase = new_phase

    def record_token_estimate(self, tokens: int):
        """Track estimated token usage for budget awareness."""
        self._total_token_estimate += tokens

    def analyze(self) -> MetaCognitiveState:
        """
        Analyze current cognitive state and return recommendations.
        
        Called after each tool execution in the thinking loop.
        Returns a MetaCognitiveState with any warnings.
        """
        state = MetaCognitiveState()

        # ── Check 1: Looping Detection ──
        loop_info = self._detect_loop()
        if loop_info:
            state.is_looping = True
            state.loop_tool = loop_info[0]
            state.loop_count = loop_info[1]
            state.recommendation = (
                f"⚠️ META-COGNITION: You've called `{loop_info[0]}` {loop_info[1]} times "
                f"with similar arguments. You are LOOPING. STOP this approach entirely. "
                f"Try a COMPLETELY DIFFERENT strategy — different tool, different method, "
                f"or ask Abdullah for help."
            )

        # ── Check 2: Stalling Detection ──
        elif self._steps_since_verify > self.STALL_THRESHOLD and self._has_deployments():
            state.is_stalled = True
            state.stall_reason = "no_verification"
            state.recommendation = (
                f"⚠️ META-COGNITION: You've taken {self._steps_since_verify} steps "
                f"without verifying results. Use `verify_result` to check if your "
                f"agents' work actually succeeded before continuing."
            )

        # ── Check 3: Failure Spiral ──
        elif self._consecutive_failures >= self.FAILURE_SPIRAL_THRESHOLD:
            state.is_stalled = True
            state.stall_reason = "failure_spiral"
            state.recommendation = (
                f"⚠️ META-COGNITION: {self._consecutive_failures} consecutive failures. "
                f"You're in a failure spiral. STOP and completely reassess your approach. "
                f"Consider: 1) Different tool/agent, 2) Simpler approach, 3) Ask Abdullah."
            )

        # ── Check 4: Overthinking (too many think() without action) ──
        elif self._consecutive_thinks >= self.MAX_THINKING_WITHOUT_ACTION:
            state.is_stalled = True
            state.stall_reason = "overthinking"
            state.recommendation = (
                f"⚠️ META-COGNITION: You've called think() {self._consecutive_thinks} "
                f"times in a row without taking any action. STOP THINKING and ACT. "
                f"Deploy an agent, run a command, or respond to Abdullah."
            )

        # ── Check 5: No reporting on long tasks ──
        elif self._steps_since_report > 15 and self._total_steps > 15:
            state.recommendation = (
                f"⚠️ META-COGNITION: {self._steps_since_report} steps without "
                f"updating Abdullah. Send a progress update via send_imessage."
            )

        # ── Check 6: Deployment budget crisis ──
        elif (len(self._deployments) >= self._max_deployments - 1
              and self._phase in ("planning", "research")):
            state.recommendation = (
                f"🚨 META-COGNITION: You've used {len(self._deployments)}/{self._max_deployments} "
                f"deployments and you're still in the {self._phase} phase. STOP deploying agents. "
                f"Use what you have — move to compilation and delivery NOW. "
                f"Use generate_report and send_imessage with the data you've collected."
            )

        # ── Check 7: Phase imbalance (stuck in research too long) ──
        elif (self._phase == "research"
              and self._phase_steps.get("research", 0) > 15
              and self._phase_steps.get("compilation", 0) == 0):
            state.recommendation = (
                f"⚠️ META-COGNITION: {self._phase_steps['research']} steps in research "
                f"with zero compilation/delivery. You have enough data — MOVE FORWARD. "
                f"Compile what you have into a report and deliver it."
            )

        # ── Check 8: Low tool diversity (stuck using one tool) ──
        elif self._total_steps > 8 and len(self._unique_tools_used) <= 2:
            top = self._tool_name_counter.most_common(1)
            top_name = top[0][0] if top else "unknown"
            state.recommendation = (
                f"⚠️ META-COGNITION: {self._total_steps} steps using only "
                f"{len(self._unique_tools_used)} distinct tools (mostly `{top_name}`). "
                f"Consider a different approach — you may be stuck in a rut."
            )

        # ── Populate Phase 38 fields ──
        state.deployments_used = len(self._deployments)
        state.deployments_budget = self._max_deployments
        state.phase = self._phase
        if self._total_steps > 0:
            state.tool_diversity = min(1.0, len(self._unique_tools_used) / max(1, self._total_steps) * 3)
            state.progress_score = self._successful_results / max(1, self._total_steps)

        # ── Confidence Trend ──
        state.confidence_trend = self._confidence_trend()
        state.avg_confidence = self._avg_confidence()

        if state.confidence_trend == "falling" and state.avg_confidence < 50:
            if not state.recommendation:
                state.recommendation = (
                    f"⚠️ META-COGNITION: Your confidence is declining "
                    f"(avg: {state.avg_confidence:.0f}%). Consider asking Abdullah "
                    f"for guidance before proceeding."
                )

        self._last_state = state
        return state

    def get_injection(self) -> Optional[str]:
        """
        Get a meta-cognitive injection for the prompt, if needed.
        
        Returns None if everything is fine, or a warning string
        to inject into the next LLM prompt.
        """
        state = self.analyze()
        return state.recommendation if state.recommendation else None

    def get_strategic_advice(self) -> Optional[str]:
        """
        Proactive strategy guidance — not just problem warnings.
        
        Unlike get_injection() which only fires when something is wrong,
        this provides forward-looking advice. Injected periodically.
        """
        advice = []
        deploys_used = len(self._deployments)
        deploys_left = self._max_deployments - deploys_used
        loops_left = self._max_tool_loops - self._total_steps

        # Budget awareness
        if deploys_used > 0 and deploys_left <= 3:
            advice.append(
                f"📊 {deploys_left} deployments left — prefer direct tools over agents."
            )

        if loops_left <= 10 and self._total_steps > 5:
            advice.append(
                f"⏳ {loops_left} steps remaining — wrap up and deliver."
            )

        # Phase coaching
        if self._phase == "research" and deploys_used >= (self._max_deployments // 2):
            advice.append(
                f"📋 {deploys_used}/{self._max_deployments} deploys used in research. "
                f"Move to compilation — generate_report with data you have."
            )

        if (self._phase == "compilation"
                and self._phase_steps.get("compilation", 0) > 3
                and self._phase_steps.get("delivery", 0) == 0):
            advice.append("📬 Report ready — deliver it (send_imessage, mac_mail).")

        # Success rate coaching
        if self._total_steps > 5:
            rate = self._successful_results / max(1, self._total_steps)
            if rate < 0.4:
                advice.append(
                    f"⚠️ {rate:.0%} success rate — try simpler approaches."
                )

        # Same-agent over-deployment
        if deploys_used >= 2:
            agent_counts = Counter(d["agent"] for d in self._deployments)
            top_agent, top_count = agent_counts.most_common(1)[0]
            if top_count >= 3:
                advice.append(
                    f"🔄 {top_count}x {top_agent} — consider a different agent or direct tools."
                )

        return "\n".join(advice) if advice else None

    # ─── Internal Helpers ────────────────────────────

    def _hash_args(self, tool_name: str, tool_input: dict) -> str:
        """Create a fuzzy hash of tool args for dedup detection."""
        # For agent deployments, hash the first 100 chars of the task
        if tool_name.startswith("deploy_"):
            task = str(tool_input.get("task", ""))[:100].lower()
            return f"{tool_name}:{hash(task)}"
        # For commands, hash the command itself
        if tool_name == "run_quick_command":
            cmd = str(tool_input.get("command", "")).lower()
            return f"{tool_name}:{hash(cmd)}"
        # For everything else, hash the full input
        return f"{tool_name}:{hash(str(sorted(tool_input.items())))}"

    def _detect_loop(self) -> Optional[Tuple[str, int]]:
        """Detect if the brain is calling the same tool repeatedly."""
        if len(self._tool_history) < self.LOOP_THRESHOLD:
            return None

        # Check last N calls for the same tool+args
        recent = list(self._tool_history)[-10:]
        hash_counts = Counter(r.args_hash for r in recent)

        for args_hash, count in hash_counts.most_common(1):
            if count >= self.LOOP_THRESHOLD:
                # Find the tool name
                tool_name = next(r.name for r in recent if r.args_hash == args_hash)
                return (tool_name, count)

        # Also check for same tool name (even with different args)
        name_counts = Counter(r.name for r in recent)
        for name, count in name_counts.most_common(1):
            # More lenient for tools that legitimately run in parallel with diverse args
            if name in ("think",):
                continue  # think is never a loop
            elif name in ("web_search", "quick_read_file", "recall_memory"):
                # These tools are often called in parallel with DIFFERENT queries —
                # only flag if args are also similar (already caught above).
                # Name-only threshold is very high to avoid false positives.
                threshold = 8
            elif name in ("scan_environment",):
                threshold = 6
            elif name == "send_imessage":
                # iMessage loops are critical — catch them faster
                threshold = 4
            elif name.startswith("deploy_"):
                # Agent deployments for different sub-tasks are normal —
                # a 5-task batch legitimately deploys 4-5 agents.
                # Only flag at high counts.
                threshold = 6
            elif name in ("run_quick_command",):
                # Parallel execution of different commands is normal for multi-task batches
                threshold = 6
            elif name == "verify_result":
                # Verifying multiple files/results is normal after parallel work
                threshold = 6
            else:
                threshold = self.LOOP_THRESHOLD + 1  # default: 4
            if count >= threshold:
                return (name, count)

        return None

    def _has_deployments(self) -> bool:
        """Check if any agent deployments happened."""
        return any(r.name.startswith("deploy_") for r in self._tool_history)

    def _confidence_trend(self) -> str:
        """Analyze confidence score trend."""
        scores = [s for _, s in self._confidence_history]
        if len(scores) < 3:
            return "stable"

        recent = scores[-3:]
        older = scores[-6:-3] if len(scores) >= 6 else scores[:3]

        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)

        if avg_recent < avg_older - 10:
            return "falling"
        elif avg_recent > avg_older + 10:
            return "rising"
        return "stable"

    def _avg_confidence(self) -> float:
        """Get average recent confidence."""
        scores = [s for _, s in self._confidence_history]
        if not scores:
            return 75.0
        recent = scores[-self.CONFIDENCE_WINDOW:]
        return sum(recent) / len(recent)

    def get_stats(self) -> dict:
        """Get stats for dashboard."""
        return {
            "total_steps": self._total_steps,
            "consecutive_failures": self._consecutive_failures,
            "steps_since_verify": self._steps_since_verify,
            "steps_since_report": self._steps_since_report,
            "is_looping": self._last_state.is_looping,
            "is_stalled": self._last_state.is_stalled,
            "confidence_trend": self._last_state.confidence_trend,
            "avg_confidence": self._last_state.avg_confidence,
            "elapsed_seconds": time.time() - self._start_time,
            # Phase 38: Preventive intelligence
            "deployments_used": len(self._deployments),
            "deployments_budget": self._max_deployments,
            "phase": self._phase,
            "tool_diversity": self._last_state.tool_diversity,
            "progress_score": self._last_state.progress_score,
            "unique_tools": len(self._unique_tools_used),
            "success_rate": self._successful_results / max(1, self._total_steps),
            "token_estimate": self._total_token_estimate,
        }
