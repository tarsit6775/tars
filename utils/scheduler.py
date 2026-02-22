"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Task Scheduler (Proactive Agent)             ║
╠══════════════════════════════════════════════════════════╣
║  Cron-like scheduler for autonomous recurring tasks:     ║
║    • "Check my email every morning at 9 AM"             ║
║    • "Track NVDA stock price every hour"                ║
║    • "Summarize daily news at 7 PM"                     ║
║  Persists tasks to memory/scheduled_tasks.json          ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger("TARS")

TASKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory", "scheduled_tasks.json")


class TaskScheduler:
    """Cron-style task scheduler for TARS.
    
    Tasks are stored as:
        {
            "id": "task_1",
            "task": "Check my email and summarize unread",
            "cron": "0 9 * * *",      # minute hour day month weekday
            "enabled": true,
            "created": "2025-01-01T09:00:00",
            "last_run": null,
            "run_count": 0
        }
    
    Supports simplified cron:
        - "0 9 * * *"     → Every day at 9:00 AM
        - "*/30 * * * *"  → Every 30 minutes
        - "0 */2 * * *"   → Every 2 hours
        - "0 9 * * 1"     → Every Monday at 9 AM
        - "0 9,18 * * *"  → At 9 AM and 6 PM daily
    
    Also supports natural language shortcuts:
        - "every 30 minutes"
        - "every hour"
        - "daily at 9am"
        - "every monday at 9am"
    """

    def __init__(self, on_task_due=None):
        """
        Args:
            on_task_due: Callback(task_text: str, task_id: str) called when a task is due.
        """
        self._on_task_due = on_task_due
        self._tasks = []
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._load_tasks()

    def start(self):
        """Start the scheduler background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="tars-scheduler")
        self._thread.start()
        task_count = len([t for t in self._tasks if t.get("enabled", True)])
        logger.info(f"  ⏰ Task scheduler started ({task_count} active tasks)")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    # ─── Task Management ─────────────────────────────

    def add_task(self, task_text, schedule, task_id=None):
        """Add a scheduled task.
        
        Args:
            task_text: What TARS should do (e.g. "Check my email and summarize")
            schedule: Cron string or natural language (e.g. "0 9 * * *" or "daily at 9am")
            task_id: Optional custom ID
            
        Returns:
            Standard tool result dict
        """
        cron = self._parse_schedule(schedule)
        if not cron:
            return {"success": False, "error": True, "content": f"Invalid schedule: '{schedule}'. Use cron (0 9 * * *) or natural language (daily at 9am)."}

        with self._lock:
            if not task_id:
                task_id = f"sched_{int(time.time())}_{len(self._tasks)}"

            # Deduplicate: remove any existing task with the same ID
            self._tasks = [t for t in self._tasks if t["id"] != task_id]

            task = {
                "id": task_id,
                "task": task_text,
                "cron": cron,
                "schedule_raw": schedule,
                "enabled": True,
                "created": datetime.now().isoformat(),
                "last_run": None,
                "run_count": 0,
            }
            self._tasks.append(task)
            self._save_tasks()

        next_run = self._next_run_time(cron)
        logger.info(f"  ⏰ Scheduled: '{task_text[:60]}' ({cron}) — next: {next_run}")
        return {
            "success": True,
            "content": f"Scheduled task '{task_text[:80]}' with schedule '{schedule}' (cron: {cron}). Next run: {next_run}. Task ID: {task_id}"
        }

    def remove_task(self, task_id):
        """Remove a scheduled task by ID."""
        with self._lock:
            before = len(self._tasks)
            self._tasks = [t for t in self._tasks if t["id"] != task_id]
            if len(self._tasks) < before:
                self._save_tasks()
                return {"success": True, "content": f"Removed scheduled task: {task_id}"}
            return {"success": False, "error": True, "content": f"Task not found: {task_id}"}

    def list_tasks(self):
        """List all scheduled tasks."""
        with self._lock:
            if not self._tasks:
                return {"success": True, "content": "No scheduled tasks."}

            lines = ["## Scheduled Tasks\n"]
            for t in self._tasks:
                status = "✅" if t.get("enabled", True) else "⏸️"
                last = t.get("last_run", "never")
                if last and last != "never":
                    try:
                        last = datetime.fromisoformat(last).strftime("%b %d %I:%M %p")
                    except Exception:
                        pass
                next_run = self._next_run_time(t["cron"])
                lines.append(
                    f"{status} **{t['id']}**: {t['task'][:60]}\n"
                    f"   Schedule: `{t.get('schedule_raw', t['cron'])}` | "
                    f"Last: {last} | Next: {next_run} | Runs: {t.get('run_count', 0)}"
                )

            return {"success": True, "content": "\n".join(lines)}

    def toggle_task(self, task_id, enabled=None):
        """Enable or disable a scheduled task."""
        with self._lock:
            for t in self._tasks:
                if t["id"] == task_id:
                    t["enabled"] = enabled if enabled is not None else not t.get("enabled", True)
                    self._save_tasks()
                    state = "enabled" if t["enabled"] else "disabled"
                    return {"success": True, "content": f"Task {task_id} {state}."}
            return {"success": False, "error": True, "content": f"Task not found: {task_id}"}

    # ─── Scheduler Loop ──────────────────────────────

    def _scheduler_loop(self):
        """Check every 30 seconds if any task is due."""
        while self._running:
            try:
                now = datetime.now()
                with self._lock:
                    due_tasks = []
                    for task in self._tasks:
                        if not task.get("enabled", True):
                            continue
                        if self._is_due(task, now):
                            due_tasks.append(task)

                for task in due_tasks:
                    logger.info(f"  ⏰ Task due: {task['task'][:60]}")
                    with self._lock:
                        task["last_run"] = now.isoformat()
                        task["run_count"] = task.get("run_count", 0) + 1
                        self._save_tasks()

                    # Dispatch to TARS
                    if self._on_task_due:
                        try:
                            self._on_task_due(task["task"], task["id"])
                        except Exception as e:
                            logger.error(f"  ⏰ Scheduled task error: {e}")

            except Exception as e:
                logger.error(f"  ⏰ Scheduler error: {e}")

            # Check every 30 seconds
            for _ in range(30):
                if not self._running:
                    break
                time.sleep(1)

    def _is_due(self, task, now):
        """Check if a task should run at the current time."""
        cron = task.get("cron", "")
        last_run = task.get("last_run")

        # Don't run more than once per minute
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                if (now - last_dt).total_seconds() < 55:
                    return False
            except Exception:
                pass

        return self._cron_matches(cron, now)

    # ─── Cron Parser ─────────────────────────────────

    @staticmethod
    def _cron_matches(cron, dt):
        """Check if a datetime matches a cron expression.
        
        Format: minute hour day_of_month month day_of_week
        Supports: *, */N, N, N,M
        """
        parts = cron.split()
        if len(parts) != 5:
            return False

        fields = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]  # 0=Sunday

        for field_val, pattern in zip(fields, parts):
            if pattern == "*":
                continue
            if pattern.startswith("*/"):
                try:
                    step = int(pattern[2:])
                    if field_val % step != 0:
                        return False
                except ValueError:
                    return False
            elif "," in pattern:
                values = [int(v) for v in pattern.split(",") if v.isdigit()]
                if field_val not in values:
                    return False
            else:
                try:
                    if field_val != int(pattern):
                        return False
                except ValueError:
                    return False

        return True

    @staticmethod
    def _parse_schedule(schedule):
        """Parse a schedule string into a cron expression.
        
        Accepts both cron and natural language:
            "0 9 * * *"           → "0 9 * * *"
            "every 30 minutes"    → "*/30 * * * *"
            "every hour"          → "0 */1 * * *"
            "daily at 9am"        → "0 9 * * *"
            "daily at 9:30am"     → "30 9 * * *"
            "every monday at 9am" → "0 9 * * 1"
            "weekdays at 8am"     → "0 8 * * 1,2,3,4,5"
        """
        s = schedule.strip().lower()

        # Already cron format?
        parts = s.split()
        if len(parts) == 5 and all(
            p == "*" or p.startswith("*/") or p.replace(",", "").isdigit()
            for p in parts
        ):
            return s

        import re

        # "every N minutes"
        m = re.match(r"every\s+(\d+)\s+min", s)
        if m:
            return f"*/{m.group(1)} * * * *"

        # "every hour" / "hourly"
        if "every hour" in s or s == "hourly":
            return "0 */1 * * *"

        # "every N hours"
        m = re.match(r"every\s+(\d+)\s+hour", s)
        if m:
            return f"0 */{m.group(1)} * * *"

        # Parse time component
        def _parse_time(text):
            """Extract hour:minute from text like '9am', '9:30pm', '14:00'."""
            t = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', text)
            if t:
                h, m_val = int(t.group(1)), int(t.group(2))
                if t.group(3) == "pm" and h < 12:
                    h += 12
                elif t.group(3) == "am" and h == 12:
                    h = 0
                return h, m_val

            t = re.search(r'(\d{1,2})\s*(am|pm)', text)
            if t:
                h = int(t.group(1))
                if t.group(2) == "pm" and h < 12:
                    h += 12
                elif t.group(2) == "am" and h == 12:
                    h = 0
                return h, 0

            return None, None

        hour, minute = _parse_time(s)

        # Day names
        day_map = {
            "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
            "thursday": 4, "friday": 5, "saturday": 6,
            "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
        }

        # "every <day> at <time>"
        for day_name, day_num in day_map.items():
            if day_name in s:
                if hour is not None:
                    return f"{minute or 0} {hour} * * {day_num}"
                return f"0 9 * * {day_num}"  # default 9 AM

        # "weekdays at <time>"
        if "weekday" in s:
            if hour is not None:
                return f"{minute or 0} {hour} * * 1,2,3,4,5"
            return "0 9 * * 1,2,3,4,5"

        # "daily at <time>" or "every day at <time>"
        if "daily" in s or "every day" in s:
            if hour is not None:
                return f"{minute or 0} {hour} * * *"
            return "0 9 * * *"

        # Just a time → assume daily
        if hour is not None:
            return f"{minute or 0} {hour} * * *"

        return None

    @staticmethod
    def _next_run_time(cron):
        """Calculate the next run time for a cron expression (approximate)."""
        try:
            parts = cron.split()
            if len(parts) != 5:
                return "unknown"

            now = datetime.now()

            # Simple approximation for common patterns
            minute_part, hour_part = parts[0], parts[1]

            if minute_part.startswith("*/"):
                step = int(minute_part[2:])
                next_min = ((now.minute // step) + 1) * step
                if next_min >= 60:
                    return (now + timedelta(hours=1)).replace(minute=0, second=0).strftime("%I:%M %p")
                return now.replace(minute=next_min, second=0).strftime("%I:%M %p")

            if hour_part.startswith("*/"):
                step = int(hour_part[2:])
                next_hour = ((now.hour // step) + 1) * step
                if next_hour >= 24:
                    return "Tomorrow"
                return now.replace(hour=next_hour, minute=int(minute_part) if minute_part != "*" else 0, second=0).strftime("%I:%M %p")

            if minute_part != "*" and hour_part != "*":
                target = now.replace(hour=int(hour_part), minute=int(minute_part), second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                if target.date() == now.date():
                    return target.strftime("Today %I:%M %p")
                return target.strftime("Tomorrow %I:%M %p")

            return "~" + now.replace(second=0).strftime("%I:%M %p")
        except Exception:
            return "unknown"

    # ─── Persistence ─────────────────────────────────

    def _load_tasks(self):
        """Load tasks from disk."""
        try:
            if os.path.exists(TASKS_FILE):
                with open(TASKS_FILE, "r") as f:
                    self._tasks = json.load(f)
        except Exception as e:
            logger.warning(f"  ⏰ Could not load scheduled tasks: {e}")
            self._tasks = []

    def _save_tasks(self):
        """Save tasks to disk."""
        try:
            os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
            with open(TASKS_FILE, "w") as f:
                json.dump(self._tasks, f, indent=2)
        except Exception as e:
            logger.warning(f"  ⏰ Could not save scheduled tasks: {e}")


# Singleton
task_scheduler = TaskScheduler()
