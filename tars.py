#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║                 ████████╗ █████╗ ██████╗ ███████╗        ║
║                 ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝        ║
║                    ██║   ███████║██████╔╝███████╗        ║
║                    ██║   ██╔══██║██╔══██╗╚════██║        ║
║                    ██║   ██║  ██║██║  ██║███████║        ║
║                    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝        ║
║                                                          ║
║          Autonomous Mac Agent — Your Workflow             ║
║                    Never Stops                           ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝

Usage:
    python tars.py                    # Start TARS, waits for iMessage
    python tars.py "build a website"  # Start with a task
"""

import os
import sys
import yaml
import time
import logging
import queue
import signal
import threading
from datetime import datetime

# Set working directory to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from brain.planner import TARSBrain
from brain.message_parser import MessageStreamParser, MessageBatch
from brain.self_heal import SelfHealEngine
from brain.daily_improve import DailyImprover
from executor import ToolExecutor
from voice.imessage_send import IMessageSender
from voice.imessage_read import IMessageReader
from memory.memory_manager import MemoryManager
from memory.agent_memory import AgentMemory
from memory.error_tracker import error_tracker
from utils.logger import setup_logger
from utils.event_bus import event_bus
from utils.agent_monitor import agent_monitor
from server import TARSServer
from hands import mac_control as mac

logger = logging.getLogger("TARS")


# ─── Banner ──────────────────────────────────────────

BANNER = """
\033[36m
  ████████╗ █████╗ ██████╗ ███████╗
  ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝
     ██║   ███████║██████╔╝███████╗
     ██║   ██╔══██║██╔══██╗╚════██║
     ██║   ██║  ██║██║  ██║███████║
     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
\033[0m
  \033[90mAutonomous Mac Agent — v5.0 Brain\033[0m
  \033[90m"Parallel Tasks + Self-Healing"\033[0m
  \033[90mDashboard: http://localhost:8420\033[0m
"""


def load_config():
    """Load configuration from config.yaml with env var overrides.
    
    API keys can be set via environment variables:
      TARS_BRAIN_API_KEY  →  brain_llm.api_key
      TARS_AGENT_API_KEY  →  agent_llm.api_key + llm.api_key
    """
    config_path = os.path.join(BASE_DIR, "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Env var overrides for API keys (so they never need to be in yaml)
    if os.environ.get("TARS_BRAIN_API_KEY"):
        config.setdefault("brain_llm", {})["api_key"] = os.environ["TARS_BRAIN_API_KEY"]
    if os.environ.get("TARS_AGENT_API_KEY"):
        config.setdefault("agent_llm", {})["api_key"] = os.environ["TARS_AGENT_API_KEY"]
        config.setdefault("llm", {})["api_key"] = os.environ["TARS_AGENT_API_KEY"]
    
    return config


class TARS:
    def __init__(self):
        print(BANNER)

        # Load config
        self.config = load_config()
        logger.info("  ⚙️  Config loaded")

        # Validate API keys — both brain and agent
        provider_urls = {
            "groq": "https://console.groq.com/keys",
            "together": "https://api.together.xyz/settings/api-keys",
            "anthropic": "https://console.anthropic.com/settings/keys",
            "openrouter": "https://openrouter.ai/keys",
            "openai": "https://platform.openai.com/api-keys",
            "gemini": "https://aistudio.google.com/apikey",
        }

        # Validate brain LLM key
        brain_cfg = self.config.get("brain_llm", {})
        brain_key = brain_cfg.get("api_key", "")
        brain_provider = brain_cfg.get("provider", "")
        if brain_key and not brain_key.startswith("YOUR_"):
            logger.info(f"  🧠 Brain LLM: {brain_provider}/{brain_cfg.get('model', '?')}")
        elif brain_provider:
            url = provider_urls.get(brain_provider, "your provider's dashboard")
            logger.error(f"\n  ❌ ERROR: Brain API key missing or invalid")
            logger.error(f"  → Set brain_llm.api_key in config.yaml")
            logger.error(f"  → Or: export TARS_BRAIN_API_KEY=your_key")
            logger.error(f"  → Get a key at: {url}\n")
            sys.exit(1)

        # Validate agent LLM key  
        llm_cfg = self.config["llm"]
        api_key = llm_cfg["api_key"]
        provider = llm_cfg["provider"]
        if not api_key or api_key.startswith("YOUR_"):
            url = provider_urls.get(provider, "your provider's dashboard")
            logger.error(f"\n  ❌ ERROR: Set your {provider} API key in config.yaml")
            logger.error(f"  → Open config.yaml and set llm.api_key")
            logger.error(f"  → Or: export TARS_AGENT_API_KEY=your_key")
            logger.error(f"  → Get a key at: {url}\n")
            sys.exit(1)
        logger.info(f"  🤖 Agent LLM: {provider}")

        # Initialize components
        self.logger = setup_logger(self.config, BASE_DIR)
        logger.info("  📝 Logger ready")

        self.memory = MemoryManager(self.config, BASE_DIR)
        logger.info("  🧠 Memory loaded")

        self.agent_memory = AgentMemory(BASE_DIR)
        logger.info("  🧬 Agent memory loaded")

        self.imessage_sender = IMessageSender(self.config)
        self.imessage_reader = IMessageReader(self.config)
        logger.info("  📱 iMessage bridge ready")

        # Must init before executor/brain so they can reference these
        self.running = True
        self.kill_words = self.config["safety"]["kill_words"]
        self._kill_event = threading.Event()  # Shared kill signal — stops running agents
        self._task_queue = queue.Queue()  # Thread-safe task queue
        self._progress_interval = self.config.get("imessage", {}).get("progress_interval", 30)  # Seconds between progress updates

        self.executor = ToolExecutor(
            self.config, self.imessage_sender, self.imessage_reader, self.memory, self.logger,
            kill_event=self._kill_event,
        )
        logger.info("  🔧 Orchestrator executor ready")
        logger.info(f"     ├─ 🌐 Browser Agent")
        logger.info(f"     ├─ 💻 Coder Agent")
        logger.info(f"     ├─ ⚙️  System Agent")
        logger.info(f"     ├─ 🔍 Research Agent")
        logger.info(f"     └─ 📁 File Agent")

        self.brain = TARSBrain(self.config, self.executor, self.memory)
        logger.info("  🤖 Orchestrator brain online")

        # Self-Healing Engine — monitors failures, proposes code fixes
        self.self_heal = SelfHealEngine()
        logger.info("  🩹 Self-healing engine ready")

        # Daily Self-Improvement — scheduled nightly improvement cycle
        self.daily_improver = DailyImprover(
            config=self.config,
            self_heal_engine=self.self_heal,
            self_improve_engine=self.executor.self_improve,
            imessage_sender=self.imessage_sender,
            imessage_reader=self.imessage_reader,
            executor=self.executor,
        )
        self.daily_improver.start()
        logger.info("  📅 Daily self-improvement scheduler active")

        # Error Tracker — persistent error log with fix registry
        tracker_stats = error_tracker.get_stats()
        logger.info(f"  📋 Error tracker: {tracker_stats['unique_errors']} patterns, "
              f"{tracker_stats['auto_fixable']} auto-fixable")

        # Parallel task processing config
        self._max_parallel_tasks = self.config.get("agent", {}).get("max_parallel_tasks", 3)
        self._active_tasks = {}  # {task_id: threading.Thread}
        self._active_tasks_lock = threading.Lock()
        self._task_counter = 0
        logger.info(f"  ⚡ Parallel task pool (max {self._max_parallel_tasks} concurrent)")

        # Phase 1: Message Stream Parser
        # Accumulates back-to-back messages (3s window) and merges intelligently
        self.message_parser = MessageStreamParser(
            on_batch_ready=self._on_batch_ready
        )
        logger.info("  📨 Message stream parser ready (3s merge window)")

        self.monitor = agent_monitor
        logger.info("  📊 Agent monitor active")

        # Start dashboard server
        self.server = TARSServer(memory_manager=self.memory, tars_instance=self)
        self.server.start()
        logger.info("  🖥️  Dashboard live at \033[36mhttp://localhost:8420\033[0m")

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *args):
        """Graceful shutdown — stops agents, drains queue, then exits."""
        logger.info("\n\n  🛑 TARS shutting down...")

        # Flush any pending messages in the stream parser
        if hasattr(self, 'message_parser'):
            self.message_parser.force_flush()

        # Stop daily improver
        if hasattr(self, 'daily_improver'):
            self.daily_improver.stop()

        # Signal all running agents to stop
        self._kill_event.set()
        self.running = False

        # Wait for current task to finish (up to 10s)
        try:
            self._task_queue.join()  # blocks until task_done() called
        except Exception:
            pass

        # Print session summary from self-improvement engine
        if hasattr(self.executor, 'self_improve'):
            summary = self.executor.self_improve.get_session_summary()
            if summary:
                logger.info(f"\n{summary}\n")

        self.memory.update_context(
            f"# TARS — Last Session\n\nShutdown at {datetime.now().isoformat()}\n"
        )
        sys.exit(0)

    def run(self, initial_task=None):
        """Main agent loop."""
        logger.info(f"\n  {'─' * 50}")
        logger.info(f"  🟢 TARS is online — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"  {'─' * 50}\n")

        event_bus.emit("status_change", {"status": "online", "label": "ONLINE"})

        # ── Environment snapshot on startup ──
        logger.info("  🌍 Taking environment snapshot...")
        try:
            snapshot = mac.get_environment_snapshot()
            if snapshot.get("success"):
                self._last_snapshot = snapshot.get("snapshot", {})
                self.memory.save("context", "startup_environment", snapshot.get("content", ""))
                apps = snapshot.get("snapshot", {}).get("running_apps", [])
                logger.info(f"  ✅ Snapshot: {len(apps)} apps running, volume {snapshot.get('snapshot', {}).get('volume', '?')}%")
            else:
                self._last_snapshot = {}
                logger.warning("  ⚠️ Snapshot partial — continuing")
        except Exception as e:
            self._last_snapshot = {}
            logger.warning(f"  ⚠️ Snapshot skipped: {e}")

        # Start flight price tracker scheduler (background)
        try:
            from hands.flight_search import start_price_tracker_scheduler
            start_price_tracker_scheduler(check_interval_minutes=30)
            logger.info("  ✈️  Flight price tracker scheduler started (every 30min)")
        except Exception as e:
            logger.warning(f"  ⚠️  Price tracker scheduler skipped: {e}")

        # Start task worker thread (processes queue serially)
        worker = threading.Thread(target=self._task_worker, daemon=True)
        worker.start()

        # Dashboard URL (don't auto-open — it interferes with Chrome browser tools)
        logger.info(f"  🌐 Open dashboard: http://localhost:8420\n")

        # Notify owner that TARS is online and ready
        try:
            self.imessage_sender.send("✅ TARS is online and all systems are functional. Ready for commands.")
            logger.info("  📱 Startup notification sent via iMessage")
        except Exception as e:
            logger.warning(f"  ⚠️ Could not send startup iMessage: {e}")

        if initial_task:
            # Start with a task from command line
            logger.info(f"  📋 Initial task: {initial_task}\n")
            self._process_task(initial_task)
        else:
            # No task — wait for messages (conversation-ready)
            logger.info("  📱 Listening for messages...\n")

        # Main loop — keep working forever
        # Messages are fed through the stream parser which:
        #   1. Accumulates back-to-back messages (3s window)
        #   2. Detects corrections ("actually make it Tokyo")
        #   3. Detects additions ("also track the price")
        #   4. Merges intelligently into a single batch
        #   5. Calls _on_batch_ready() which queues for the brain
        while self.running:
            try:
                # Wait for a new message via iMessage
                conv_msgs = self.brain._message_count
                conv_ctx = len(self.brain.conversation_history)
                active = self.brain.threads.active_thread
                thread_info = f", thread: {active.topic[:30]}" if active else ""
                logger.debug(f"  ⏳ Waiting for message... (msgs: {conv_msgs}, ctx: {conv_ctx}{thread_info})")
                reply = self.imessage_reader.wait_for_reply(timeout=3600)  # 1 hour timeout

                if reply.get("success"):
                    task = reply["content"]
                    event_bus.emit("imessage_received", {"message": task})

                    # Check kill switch — stops all running agents
                    if any(kw.lower() in task.lower() for kw in self.kill_words):
                        logger.info(f"  🛑 Kill command received: {task}")
                        self._kill_event.set()
                        event_bus.emit("kill_switch", {"source": "imessage"})
                        try:
                            self.imessage_sender.send("🛑 Kill switch activated — all agents stopped.")
                        except Exception:
                            pass
                        time.sleep(1)
                        self._kill_event.clear()
                        continue

                    # Feed through the message stream parser (Phase 1)
                    # Parser accumulates for 3s, merges back-to-back messages,
                    # then calls _on_batch_ready() which queues for the brain
                    self.message_parser.ingest(task)
                else:
                    # Timed out — just keep waiting silently
                    logger.debug("  💤 Still waiting...")

            except KeyboardInterrupt:
                self._shutdown()
            except Exception as e:
                self.logger.error(f"Loop error: {e}")
                logger.warning(f"  ⚠️ Error: {e} — continuing...")
                time.sleep(5)

    def _on_batch_ready(self, batch):
        """
        Called by the MessageStreamParser when a batch of messages is ready.
        
        Phase 1: Back-to-back messages have been accumulated and merged.
        The batch knows if it's a correction, addition, or new task.
        
        Queue it for the task worker to process.
        """
        if batch.batch_type == "multi_task" and batch.individual_tasks:
            # Multiple independent tasks — queue each separately
            logger.info(f"  📨 Received {len(batch.individual_tasks)} separate tasks")
            for task_text in batch.individual_tasks:
                single_batch = MessageBatch(
                    messages=batch.messages,
                    merged_text=task_text,
                    batch_type="single",
                    timestamp=batch.timestamp,
                )
                self._task_queue.put(single_batch)
        else:
            # Single task or merged batch
            info = f"({batch.batch_type})" if batch.batch_type != "single" else ""
            logger.info(f"  📨 Batch ready {info}: {batch.merged_text[:100]}")
            self._task_queue.put(batch)

    def _process_task(self, task):
        """
        Legacy entry point — wraps a string into a batch.
        Used for initial_task from command line.
        """
        batch = MessageBatch(
            messages=[],
            merged_text=task,
            batch_type="single",
            timestamp=time.time(),
        )
        self._task_queue.put(batch)

    def _task_worker(self):
        """Background worker that dispatches tasks from the queue to parallel threads."""
        while self.running:
            try:
                item = self._task_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                # Wait if at max capacity
                while self._count_active_tasks() >= self._max_parallel_tasks:
                    time.sleep(0.5)
                    if not self.running:
                        break

                # Handle both MessageBatch (new) and raw strings (legacy)
                if isinstance(item, MessageBatch):
                    task_text = item.merged_text
                    batch = item
                else:
                    task_text = str(item)
                    batch = None

                # Assign task ID
                self._task_counter += 1
                task_id = f"task_{self._task_counter}"

                # Launch in a new thread
                t = threading.Thread(
                    target=self._run_task,
                    args=(task_id, task_text, batch),
                    name=f"tars-{task_id}",
                    daemon=True,
                )
                with self._active_tasks_lock:
                    self._active_tasks[task_id] = t
                t.start()

                active = self._count_active_tasks()
                logger.info(f"  ⚡ Spawned {task_id} (active: {active}/{self._max_parallel_tasks})")
                event_bus.emit("parallel_task_started", {
                    "task_id": task_id,
                    "task": task_text[:100],
                    "active_count": active,
                })

            except Exception as e:
                self.logger.error(f"Task dispatch error: {e}")
            finally:
                self._task_queue.task_done()

    def _count_active_tasks(self) -> int:
        """Count currently running task threads."""
        with self._active_tasks_lock:
            # Clean up finished threads
            finished = [tid for tid, t in self._active_tasks.items() if not t.is_alive()]
            for tid in finished:
                del self._active_tasks[tid]
            return len(self._active_tasks)

    def _run_task(self, task_id, task_text, batch):
        """Execute a single task in its own thread.

        Each task gets its own progress collector and isolated execution.
        The brain handles thread routing internally.
        """
        try:
            logger.info(f"\n  {'═' * 50}")
            batch_info = f" [{batch.batch_type}]" if batch and batch.batch_type != "single" else ""
            logger.info(f"  📨 [{task_id}] Message{batch_info}: {task_text[:120]}")
            logger.info(f"  {'═' * 50}\n")

            self.logger.info(f"[{task_id}] New message: {task_text}")
            event_bus.emit("task_received", {"task": task_text, "source": "agent", "task_id": task_id})
            event_bus.emit("status_change", {"status": "working", "label": f"WORKING ({self._count_active_tasks()})" })

            # Set reply routing — dashboard messages get dashboard replies
            task_source = batch.source if batch else "imessage"
            self.executor.set_reply_source(task_source)

            # Reset deployment tracker (fresh agent budget)
            self.executor.reset_task_tracker()

            # Streaming progress: debounced updates to iMessage
            progress_collector = _ProgressCollector(
                sender=self.imessage_sender,
                interval=self._progress_interval,
            )
            progress_collector.start()

            # Send to brain
            try:
                if batch:
                    response = self.brain.process(batch)
                else:
                    response = self.brain.think(task_text)
            finally:
                progress_collector.stop()

            # Log the result
            self.logger.info(f"[{task_id}] Cycle complete. Response: {response[:200]}")

            # Send the brain's final response to the user
            # BUT only if the brain didn't already send messages during its tool loop
            if response and not response.startswith("🛑") and not self.brain._brain_sent_imessage:
                try:
                    self.executor.send_reply(response[:1500])
                except Exception as e:
                    self.logger.warning(f"[{task_id}] Failed to send response: {e}")

            # Safety net: if brain returned an error, notify user
            if response and (response.startswith("❌") or response.startswith("⚠️")):
                self.logger.warning(f"[{task_id}] Brain returned error: {response[:200]}")
                self._handle_task_error(task_id, task_text, response)

            # Check for self-healing opportunities on failure
            if response and (response.startswith("❌") or response.startswith("⚠️")):
                self._check_self_heal(task_id, task_text, response)

            event_bus.emit("parallel_task_completed", {
                "task_id": task_id,
                "task": task_text[:100],
                "success": not (response and response.startswith("❌")),
                "active_count": self._count_active_tasks() - 1,
            })

            logger.info(f"\n  {'─' * 50}")
            logger.info(f"  ✅ [{task_id}] Cycle complete")
            logger.info(f"  {'─' * 50}\n")

        except Exception as e:
            self.logger.error(f"[{task_id}] Task error: {e}")
            logger.warning(f"  ⚠️ [{task_id}] Task error: {e}")
            try:
                self.executor.send_reply(f"⚠️ Something went wrong with a task. Error: {str(e)[:200]}. Send your request again.")
            except Exception:
                pass

            # Record failure for self-healing
            self.self_heal.record_failure(
                error=str(e),
                context="task_processing",
                details=task_text[:200],
            )
            # Record in error tracker for pattern learning
            error_tracker.record_error(
                error=str(e),
                context="task_processing",
                details=task_text[:200],
            )

        finally:
            # Update status — check if other tasks are still running
            remaining = self._count_active_tasks() - 1  # -1 for this finishing thread
            if remaining <= 0:
                event_bus.emit("status_change", {"status": "online", "label": "ONLINE"})
            else:
                event_bus.emit("status_change", {"status": "working", "label": f"WORKING ({remaining})"})

    def _handle_task_error(self, task_id, task_text, response):
        """Handle error responses — notify user if brain didn't already."""
        try:
            already_notified = any(m in response.lower() for m in (
                "rate limit", "429", "retries",
                "api key", "permission_denied", "leaked",
            ))
            if not already_notified:
                if "Failed to call a function" in response:
                    self.imessage_sender.send("⚠️ Had a formatting hiccup with my response. Can you repeat your request? I'll get it right this time.")
                else:
                    self.imessage_sender.send(f"⚠️ Ran into an issue: {response[:300]}")
        except Exception:
            pass

    def _check_self_heal(self, task_id, task_text, response):
        """Check if a task failure should trigger self-healing."""
        proposal = self.self_heal.record_failure(
            error=response[:500],
            context="brain_response",
            tool="brain",
            details=task_text[:200],
        )
        if proposal:
            logger.info(f"  🩹 [{task_id}] Self-healing proposal: {proposal.trigger[:80]}")
            # Ask Abdullah for permission
            approved = self.self_heal.request_healing(
                self.imessage_sender,
                self.imessage_reader,
                proposal,
            )
            if approved:
                logger.info(f"  🩹 [{task_id}] Self-healing APPROVED — deploying dev agent")
                result = self.self_heal.execute_healing(approved, self.executor)
                heal_status = "✅ healed" if result.get("success") else "❌ failed"
                logger.info(f"  🩹 [{task_id}] Self-healing {heal_status}")
                try:
                    if result.get("success"):
                        self.imessage_sender.send("🩹 Self-healing complete! I've patched myself. The fix will take effect on next task.")
                    else:
                        self.imessage_sender.send(f"🩹 Self-healing attempt didn't work: {result.get('content', 'unknown')[:200]}")
                except Exception:
                    pass


class _ProgressCollector:
    """Collects agent/tool events and sends debounced progress updates to iMessage.
    
    Subscribes to event_bus for 'agent_started', 'agent_completed', 'tool_called'
    events. Every `interval` seconds, if there's new activity, sends a compact
    progress update via iMessage so the user knows what TARS is doing.
    
    Also sends periodic heartbeats during long operations so the user
    never thinks TARS silently died.
    """

    def __init__(self, sender, interval=30):
        self._sender = sender
        self._interval = interval
        self._events = []
        self._lock = threading.Lock()
        self._timer = None
        self._running = False
        self._ticks_without_event = 0
        self._last_agent = None
        self._start_time = None

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._ticks_without_event = 0
        event_bus.subscribe_sync("agent_started", self._on_agent_start)
        event_bus.subscribe_sync("agent_completed", self._on_event)
        event_bus.subscribe_sync("tool_called", self._on_event)
        self._schedule_tick()

    def stop(self):
        self._running = False
        event_bus.unsubscribe_sync("agent_started", self._on_agent_start)
        event_bus.unsubscribe_sync("agent_completed", self._on_event)
        event_bus.unsubscribe_sync("tool_called", self._on_event)
        if self._timer:
            self._timer.cancel()

    def _on_agent_start(self, data):
        with self._lock:
            self._events.append(data)
            self._last_agent = data.get("agent", "agent")

    def _on_event(self, data):
        with self._lock:
            self._events.append(data)

    def _schedule_tick(self):
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self):
        if not self._running:
            return
        with self._lock:
            events = self._events[:]
            self._events.clear()

        if events:
            self._ticks_without_event = 0
            # Build a compact progress summary
            parts = []
            for ev in events[-5:]:  # Last 5 events max
                if "agent" in ev and "task" in ev:
                    parts.append(f"🚀 {ev['agent']}: {ev['task'][:60]}")
                elif "agent" in ev and "success" in ev:
                    status = "✅" if ev["success"] else "❌"
                    parts.append(f"{status} {ev['agent']} done ({ev.get('steps', '?')} steps)")
                elif "tool_name" in ev:
                    parts.append(f"🔧 {ev['tool_name']}")

            if parts:
                msg = "⏳ Progress:\n" + "\n".join(parts)
                try:
                    self._sender.send(msg)
                except Exception:
                    pass
        else:
            # No events — send heartbeat so user knows we're alive
            self._ticks_without_event += 1
            elapsed = int(time.time() - self._start_time) if self._start_time else 0
            # Send heartbeat every 60s of silence (every 2 ticks at 30s interval)
            if self._ticks_without_event >= 2 and elapsed > 45:
                self._ticks_without_event = 0
                agent_label = self._last_agent or "task"
                minutes = elapsed // 60
                try:
                    self._sender.send(f"⏳ Still working on it... ({agent_label}, {minutes}m elapsed)")
                except Exception:
                    pass

        self._schedule_tick()


# ─── Entry Point ─────────────────────────────────────

def _run_with_auto_restart():
    """Run TARS with automatic crash recovery.
    
    If TARS crashes for any reason, waits 5 seconds and restarts.
    Sends an iMessage notification about the crash and recovery.
    Max 10 restarts to prevent infinite crash loops.
    """
    max_restarts = 10
    restart_count = 0

    while restart_count < max_restarts:
        try:
            tars = TARS()
            if len(sys.argv) > 1:
                task = " ".join(sys.argv[1:])
                tars.run(initial_task=task)
            else:
                tars.run()
            break  # Clean exit — don't restart
        except KeyboardInterrupt:
            logger.info("\n  🛑 TARS stopped by user.")
            break
        except SystemExit:
            break
        except Exception as e:
            restart_count += 1
            import traceback
            logger.error(f"\n  💥 TARS CRASHED: {e}")
            traceback.print_exc()
            logger.error(f"  🔄 Auto-restart {restart_count}/{max_restarts} in 5s...\n")

            # Try to notify owner about the crash
            try:
                from voice.imessage_send import IMessageSender
                import yaml
                with open("config.yaml") as f:
                    cfg = yaml.safe_load(f)
                sender = IMessageSender(cfg)
                sender.send(f"⚠️ TARS crashed: {str(e)[:150]}. Auto-restarting ({restart_count}/{max_restarts})...")
            except Exception:
                pass

            time.sleep(5)

    if restart_count >= max_restarts:
        logger.error(f"\n  🛑 TARS hit max restarts ({max_restarts}). Stopping.")
        try:
            from voice.imessage_send import IMessageSender
            import yaml
            with open("config.yaml") as f:
                cfg = yaml.safe_load(f)
            sender = IMessageSender(cfg)
            sender.send(f"🛑 TARS has stopped after {max_restarts} crashes. Manual intervention needed.")
        except Exception:
            pass


if __name__ == "__main__":
    _run_with_auto_restart()
