"""
╔══════════════════════════════════════════════════════════╗
║           TARS — Health Watchdog Thread                   ║
╠══════════════════════════════════════════════════════════╣
║  Monitors active task threads and system health.          ║
║  Force-stops stale tasks that exceed timeout.            ║
║  Reports health status to dashboard via event bus.       ║
╚══════════════════════════════════════════════════════════╝
"""

import logging
import threading
import time
import os
import resource
from datetime import datetime

from utils.event_bus import event_bus

logger = logging.getLogger("tars.watchdog")


class HealthWatchdog:
    """Monitors TARS health and force-kills stale tasks.
    
    Checks every `check_interval` seconds:
        1. Stale tasks — threads running longer than `task_timeout_minutes`
        2. Memory usage — warns if RSS exceeds threshold
        3. Heartbeat — emits periodic health events for the dashboard
    
    Stale task recovery:
        - Sets the kill_event to stop the brain's LLM loop
        - Waits briefly, then clears the kill_event so new tasks work
        - Notifies the user via iMessage
    """

    def __init__(self, config, tars_instance):
        self._config = config
        self._tars = tars_instance
        self._running = False
        self._thread = None

        # Config
        watchdog_cfg = config.get("watchdog", {})
        self._check_interval = watchdog_cfg.get("check_interval", 60)  # seconds
        self._task_timeout = watchdog_cfg.get("task_timeout_minutes", 30) * 60  # → seconds
        self._memory_warn_mb = watchdog_cfg.get("memory_warn_mb", 1024)  # 1GB default

        # Track when each task started {task_id: start_time}
        self._task_start_times = {}
        self._task_lock = threading.Lock()

    def start(self):
        """Start the watchdog background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="tars-watchdog", daemon=True)
        self._thread.start()
        logger.info(f"  🐕 Watchdog started (check every {self._check_interval}s, task timeout {self._task_timeout // 60}m)")

    def stop(self):
        """Stop the watchdog thread."""
        self._running = False

    def task_started(self, task_id):
        """Register a task as started."""
        with self._task_lock:
            self._task_start_times[task_id] = time.time()

    def task_completed(self, task_id):
        """Register a task as completed."""
        with self._task_lock:
            self._task_start_times.pop(task_id, None)

    def _loop(self):
        """Main watchdog loop."""
        while self._running:
            try:
                self._check_stale_tasks()
                self._check_memory()
                self._emit_heartbeat()
            except Exception as e:
                logger.warning(f"  🐕 Watchdog error: {e}")

            # Sleep in small increments so we can stop quickly
            for _ in range(self._check_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _check_stale_tasks(self):
        """Check for tasks that have exceeded the timeout."""
        now = time.time()
        stale_tasks = []

        with self._task_lock:
            for task_id, start_time in list(self._task_start_times.items()):
                elapsed = now - start_time
                if elapsed > self._task_timeout:
                    stale_tasks.append((task_id, elapsed))

        if not stale_tasks:
            return

        for task_id, elapsed in stale_tasks:
            minutes = int(elapsed // 60)
            logger.warning(f"  🐕 STALE TASK: {task_id} running for {minutes}m (timeout: {self._task_timeout // 60}m)")
            event_bus.emit("watchdog_stale_task", {
                "task_id": task_id,
                "elapsed_minutes": minutes,
                "action": "force_kill",
            })

        # Force-kill: set the kill event to break the brain's LLM loop
        self._tars._kill_event.set()
        logger.warning(f"  🐕 Kill event SET — stopping {len(stale_tasks)} stale task(s)")

        # Wait for tasks to notice the kill event
        time.sleep(5)

        # Clear the kill event so new tasks can proceed
        self._tars._kill_event.clear()
        logger.info(f"  🐕 Kill event cleared — ready for new tasks")

        # Clean up stale entries
        with self._task_lock:
            for task_id, _ in stale_tasks:
                self._task_start_times.pop(task_id, None)

        # Notify user
        try:
            stale_names = ", ".join(t[0] for t in stale_tasks)
            self._tars.imessage_sender.send(
                f"🐕 Watchdog: Force-stopped stale task(s) ({stale_names}) "
                f"after {self._task_timeout // 60} minutes. "
                f"Ready for new commands."
            )
        except Exception:
            pass

    def _check_memory(self):
        """Check RSS memory usage and warn if too high."""
        try:
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS returns bytes, Linux returns KB
            rss_mb = rss_kb / (1024 * 1024) if rss_kb > 1_000_000 else rss_kb / 1024

            if rss_mb > self._memory_warn_mb:
                logger.warning(f"  🐕 High memory usage: {rss_mb:.0f} MB (threshold: {self._memory_warn_mb} MB)")
                event_bus.emit("watchdog_memory_warning", {
                    "rss_mb": round(rss_mb, 1),
                    "threshold_mb": self._memory_warn_mb,
                })
        except Exception:
            pass

    def _emit_heartbeat(self):
        """Emit a periodic health heartbeat for the dashboard."""
        try:
            active_tasks = self._tars._count_active_tasks()
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss_kb / (1024 * 1024) if rss_kb > 1_000_000 else rss_kb / 1024

            event_bus.emit("watchdog_heartbeat", {
                "timestamp": datetime.now().isoformat(),
                "active_tasks": active_tasks,
                "memory_mb": round(rss_mb, 1),
                "uptime_seconds": round(time.time() - self._tars.server._boot_time, 1),
            })
        except Exception:
            pass
