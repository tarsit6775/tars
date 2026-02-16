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

    def record_confidence(self, score: float):
        """Record a confidence score from the brain's thinking."""
        self._confidence_history.append((time.time(), score))

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
            # More lenient for think/scan (those are expected to repeat)
            threshold = 6 if name in ("think", "scan_environment") else self.LOOP_THRESHOLD + 1
            if count >= threshold and name not in ("think",):
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
        }
