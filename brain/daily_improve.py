"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Daily Self-Improvement Scheduler                 ║
╠══════════════════════════════════════════════════════════════╣
║  Every day at midnight (configurable), TARS:                 ║
║    1. Analyzes the day's errors, failures, and performance   ║
║    2. Generates improvement proposals (error fixes, new      ║
║       capabilities, performance optimizations)               ║
║    3. Sends a summary to Abdullah via iMessage               ║
║    4. If approved, deploys dev agent to implement changes    ║
║    5. Runs tests, commits, and pushes to GitHub              ║
║                                                              ║
║  "Every night I get a little smarter."                       ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from utils.event_bus import event_bus
from memory.error_tracker import error_tracker

logger = logging.getLogger("TARS")

TARS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DailyImprover:
    """Scheduled daily self-improvement cycle.

    At a configurable hour (default 00:00), this engine:
    1. Collects the day's error patterns, agent stats, and healing history
    2. Generates a prioritized list of improvement proposals
    3. Sends a concise iMessage summary asking for approval
    4. If approved, deploys dev agent with a detailed improvement PRD
    5. After changes, runs tests, commits, and pushes to GitHub

    The cycle is non-blocking — runs in its own background thread.
    """

    def __init__(self, config, self_heal_engine, self_improve_engine,
                 imessage_sender, imessage_reader, executor):
        self.config = config
        self.self_heal = self_heal_engine
        self.self_improve = self_improve_engine
        self.imessage_sender = imessage_sender
        self.imessage_reader = imessage_reader
        self.executor = executor

        # Schedule config
        improvement_cfg = config.get("daily_improvement", {})
        self._hour = improvement_cfg.get("hour", 0)          # 0 = midnight
        self._minute = improvement_cfg.get("minute", 0)
        self._enabled = improvement_cfg.get("enabled", True)
        self._auto_push = improvement_cfg.get("auto_push", True)
        self._git_remote = improvement_cfg.get("git_remote", "origin")
        self._git_branch = improvement_cfg.get("git_branch", "main")

        # State
        self._thread = None
        self._stop_event = threading.Event()
        self._last_run_date = None
        self._state_path = os.path.join(TARS_ROOT, "memory", "daily_improve_state.json")
        self._load_state()

    def start(self):
        """Start the daily improvement scheduler in a background thread."""
        if not self._enabled:
            logger.info("📅 Daily improvement disabled in config")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="DailyImprover",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"📅 Daily improvement scheduled at {self._hour:02d}:{self._minute:02d}")

    def stop(self):
        """Stop the scheduler."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def run_now(self):
        """Trigger a daily improvement cycle immediately (for testing/manual use)."""
        threading.Thread(
            target=self._run_improvement_cycle,
            name="DailyImprover-Manual",
            daemon=True,
        ).start()

    # ═══════════════════════════════════════════════════
    #  SCHEDULER
    # ═══════════════════════════════════════════════════

    def _scheduler_loop(self):
        """Background loop that waits for the scheduled hour, then runs."""
        while not self._stop_event.is_set():
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # Already ran today?
            if self._last_run_date == today_str:
                self._sleep_until_next_run(now)
                continue

            # Is it time?
            if now.hour == self._hour and now.minute >= self._minute:
                logger.info("🌙 Daily improvement cycle starting...")
                self._last_run_date = today_str
                self._save_state()

                try:
                    self._run_improvement_cycle()
                except Exception as e:
                    logger.error(f"Daily improvement cycle failed: {e}")
                    event_bus.emit("daily_improve_error", {"error": str(e)})

            # Sleep 30 seconds between checks (lightweight)
            self._stop_event.wait(30)

    def _sleep_until_next_run(self, now):
        """Sleep until close to the next scheduled run time."""
        target = now.replace(hour=self._hour, minute=self._minute, second=0)
        if target <= now:
            target += timedelta(days=1)
        sleep_secs = min((target - now).total_seconds(), 300)  # Wake up at least every 5 min
        self._stop_event.wait(sleep_secs)

    # ═══════════════════════════════════════════════════
    #  IMPROVEMENT CYCLE
    # ═══════════════════════════════════════════════════

    def _run_improvement_cycle(self):
        """The main daily improvement cycle."""
        event_bus.emit("daily_improve_started", {
            "timestamp": datetime.now().isoformat(),
        })

        # Step 1: Collect daily intelligence
        report = self._collect_daily_report()

        if not report["has_improvements"]:
            logger.info("🌙 Daily check: nothing to improve today")
            event_bus.emit("daily_improve_skipped", {"reason": "no improvements needed"})
            return

        # Step 2: Send summary to user via iMessage
        message = self._format_daily_message(report)
        try:
            self.imessage_sender.send(message)
            logger.info("📱 Daily improvement proposal sent via iMessage")
        except Exception as e:
            logger.warning(f"Failed to send daily improvement iMessage: {e}")
            event_bus.emit("daily_improve_error", {"error": f"iMessage send failed: {e}"})
            return

        # Step 3: Wait for approval (10 min timeout at midnight)
        try:
            reply = self.imessage_reader.wait_for_reply(timeout=600)
            if not reply.get("success"):
                logger.info("🌙 Daily improvement: no reply (timeout) — skipping")
                event_bus.emit("daily_improve_skipped", {"reason": "no reply"})
                return

            answer = reply["content"].strip().lower()
            approved = answer in (
                "yes", "y", "approve", "do it", "go",
                "go ahead", "yep", "yeah", "sure", "ok",
            )

            if not approved:
                logger.info(f"🌙 Daily improvement: user declined ({answer})")
                event_bus.emit("daily_improve_rejected", {"reply": answer})
                return
        except Exception as e:
            logger.warning(f"Daily improvement approval error: {e}")
            return

        # Step 4: Deploy dev agent with improvement PRD
        logger.info("🔧 Daily improvement: deploying dev agent...")
        event_bus.emit("daily_improve_executing", {
            "proposals": report["proposal_count"],
        })

        prd = self._build_improvement_prd(report)

        try:
            result = self.executor.execute("deploy_dev_agent", {"task": prd})

            if result.get("success"):
                logger.info("✅ Daily improvement: dev agent completed successfully")

                # Step 5: Git commit + push
                if self._auto_push:
                    self._git_commit_and_push(report)

                # Notify user
                try:
                    self.imessage_sender.send(
                        "✅ Daily improvement complete!\n\n"
                        f"Changes: {report['proposal_count']} improvements applied.\n"
                        f"Tests: passed ✅\n"
                        f"Git: {'pushed to ' + self._git_branch if self._auto_push else 'committed locally'}"
                    )
                except Exception:
                    pass

                event_bus.emit("daily_improve_completed", {
                    "proposals": report["proposal_count"],
                    "result": "success",
                })
            else:
                logger.warning(f"Daily improvement: dev agent failed — {result.get('content', '?')[:200]}")
                try:
                    self.imessage_sender.send(
                        f"⚠️ Daily improvement partially failed:\n{result.get('content', 'Unknown error')[:300]}\n\n"
                        f"I'll try again tomorrow."
                    )
                except Exception:
                    pass
                event_bus.emit("daily_improve_failed", {
                    "error": result.get("content", "")[:200],
                })

        except Exception as e:
            logger.error(f"Daily improvement execution error: {e}")
            event_bus.emit("daily_improve_failed", {"error": str(e)})

    # ═══════════════════════════════════════════════════
    #  INTELLIGENCE COLLECTION
    # ═══════════════════════════════════════════════════

    def _collect_daily_report(self) -> dict:
        """Collect all signals about what can be improved."""
        report = {
            "has_improvements": False,
            "proposal_count": 0,
            "error_fixes": [],
            "unfixed_errors": [],
            "agent_improvements": [],
            "pending_heals": [],
            "session_stats": None,
        }

        # 1. Unfixed recurring errors from error_tracker
        try:
            unfixed = error_tracker.get_unfixed_errors()
            for err in unfixed[:5]:  # Top 5
                if err.get("count", 0) >= 2:
                    report["unfixed_errors"].append({
                        "error": err.get("error", "")[:200],
                        "context": err.get("context", ""),
                        "count": err.get("count", 0),
                    })
        except Exception:
            pass

        # 2. Top errors that DO have fixes (verify they're actually working)
        try:
            top = error_tracker.get_top_errors(10)
            for err in top:
                if err.get("has_fix") and err.get("count", 0) >= 3:
                    report["error_fixes"].append({
                        "error": err.get("error", "")[:150],
                        "fix": err.get("fix", "")[:150],
                        "count": err.get("count", 0),
                    })
        except Exception:
            pass

        # 3. Pending self-heal proposals that weren't addressed
        try:
            pending = self.self_heal.get_pending_proposals()
            for p in pending[:3]:
                report["pending_heals"].append({
                    "trigger": p.get("trigger", "")[:200],
                    "prescription": p.get("prescription", "")[:200],
                    "severity": p.get("severity", "improvement"),
                })
        except Exception:
            pass

        # 4. Session performance summary
        try:
            report["session_stats"] = self.self_improve.get_session_summary()
        except Exception:
            pass

        # 5. Agent performance stats
        try:
            all_stats = self.self_improve.get_all_agent_stats()
            for agent_name, stats in all_stats.items():
                fail_rate = stats.get("failure_rate", 0)
                if fail_rate > 0.3:  # >30% failure rate
                    report["agent_improvements"].append({
                        "agent": agent_name,
                        "failure_rate": f"{fail_rate:.0%}",
                        "total_tasks": stats.get("total_tasks", 0),
                        "common_failure": stats.get("common_failure", "unknown"),
                    })
        except Exception:
            pass

        # Determine if there's anything to improve
        total = (
            len(report["unfixed_errors"])
            + len(report["pending_heals"])
            + len(report["agent_improvements"])
        )
        report["has_improvements"] = total > 0
        report["proposal_count"] = total

        return report

    # ═══════════════════════════════════════════════════
    #  MESSAGE FORMATTING
    # ═══════════════════════════════════════════════════

    def _format_daily_message(self, report: dict) -> str:
        """Format the daily improvement summary for iMessage."""
        lines = [
            "🌙 TARS Daily Self-Improvement Report",
            f"📅 {datetime.now().strftime('%B %d, %Y')}",
            "",
        ]

        if report["unfixed_errors"]:
            lines.append(f"🔴 Unfixed Errors ({len(report['unfixed_errors'])}):")
            for e in report["unfixed_errors"]:
                lines.append(f"  • {e['error'][:100]} ({e['count']}x)")
            lines.append("")

        if report["pending_heals"]:
            lines.append(f"🩹 Pending Fixes ({len(report['pending_heals'])}):")
            for h in report["pending_heals"]:
                sev = {"critical": "🔴", "improvement": "🟡", "optimization": "🟢"}.get(h["severity"], "🔵")
                lines.append(f"  {sev} {h['trigger'][:80]}")
            lines.append("")

        if report["agent_improvements"]:
            lines.append(f"📊 Agents Needing Help ({len(report['agent_improvements'])}):")
            for a in report["agent_improvements"]:
                lines.append(f"  • {a['agent']}: {a['failure_rate']} fail rate ({a['total_tasks']} tasks)")
            lines.append("")

        if report["session_stats"]:
            lines.append(report["session_stats"])
            lines.append("")

        lines.append(f"📋 Total improvements: {report['proposal_count']}")
        lines.append("")
        lines.append("Reply 'yes' to approve all improvements, 'no' to skip.")

        return "\n".join(lines)

    def _build_improvement_prd(self, report: dict) -> str:
        """Build a detailed PRD for the dev agent to implement improvements."""
        sections = [
            "## TARS Daily Self-Improvement — Automated Code Changes\n",
            f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
            f"**Project Path**: {TARS_ROOT}\n",
            "**IMPORTANT**: You are modifying TARS itself. Follow copilot-instructions.md rules.\n",
            "---\n",
        ]

        task_num = 1

        # Unfixed errors → add fixes
        for err in report.get("unfixed_errors", []):
            sections.append(
                f"### Task {task_num}: Fix recurring error in {err['context']}\n"
                f"**Error** ({err['count']}x): {err['error'][:300]}\n"
                f"**Action**: Find the root cause in the relevant handler and fix it. "
                f"Add error handling if needed. Record the fix in error_tracker.\n"
            )
            task_num += 1

        # Pending heals → implement
        for heal in report.get("pending_heals", []):
            sections.append(
                f"### Task {task_num}: {heal['trigger'][:100]}\n"
                f"**Fix**: {heal['prescription'][:400]}\n"
            )
            task_num += 1

        # Agent improvements → optimize
        for agent in report.get("agent_improvements", []):
            sections.append(
                f"### Task {task_num}: Improve {agent['agent']} agent reliability\n"
                f"**Problem**: {agent['failure_rate']} failure rate over {agent['total_tasks']} tasks. "
                f"Common failure: {agent.get('common_failure', 'unknown')}\n"
                f"**Action**: Review agents/{agent['agent']}_agent.py, improve error handling, "
                f"add retries for transient failures, and update prompts if needed.\n"
            )
            task_num += 1

        # Standard rules
        sections.append(
            "---\n"
            "## Rules\n"
            "1. Make MINIMAL surgical changes — don't rewrite entire files\n"
            "2. Preserve all existing imports and function signatures\n"
            "3. Follow project patterns (tool return format, event_bus, logger)\n"
            "4. After ALL changes, run: python3 test_systems.py\n"
            "5. If tests pass, commit with: git commit -am 'daily-improve: "
            f"{datetime.now().strftime('%Y-%m-%d')} — {task_num - 1} improvements'\n"
            "6. Do NOT modify config.yaml or any files with API keys\n"
        )

        return "\n".join(sections)

    # ═══════════════════════════════════════════════════
    #  GIT OPERATIONS
    # ═══════════════════════════════════════════════════

    def _git_commit_and_push(self, report: dict):
        """Commit and push improvements to GitHub."""
        import subprocess

        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            commit_msg = (
                f"daily-improve: {date_str} — "
                f"{report['proposal_count']} improvements"
            )

            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=TARS_ROOT, capture_output=True, timeout=30,
            )

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=TARS_ROOT, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                if "nothing to commit" in result.stdout:
                    logger.info("🌙 Git: nothing new to commit")
                    return
                logger.warning(f"Git commit failed: {result.stderr[:200]}")
                return

            logger.info(f"📦 Git committed: {commit_msg}")

            # Push
            push_result = subprocess.run(
                ["git", "push", self._git_remote, self._git_branch],
                cwd=TARS_ROOT, capture_output=True, text=True, timeout=60,
            )

            if push_result.returncode == 0:
                logger.info(f"🚀 Git pushed to {self._git_remote}/{self._git_branch}")
                event_bus.emit("daily_improve_pushed", {
                    "commit": commit_msg,
                    "remote": self._git_remote,
                    "branch": self._git_branch,
                })
            else:
                logger.warning(f"Git push failed: {push_result.stderr[:200]}")

        except Exception as e:
            logger.warning(f"Git operations failed: {e}")

    # ═══════════════════════════════════════════════════
    #  STATE PERSISTENCE
    # ═══════════════════════════════════════════════════

    def _load_state(self):
        """Load last run date from disk."""
        try:
            if os.path.exists(self._state_path):
                with open(self._state_path, "r") as f:
                    state = json.load(f)
                self._last_run_date = state.get("last_run_date")
        except Exception:
            self._last_run_date = None

    def _save_state(self):
        """Persist last run date to disk."""
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump({
                    "last_run_date": self._last_run_date,
                    "last_run_time": datetime.now().isoformat(),
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save daily improve state: {e}")
