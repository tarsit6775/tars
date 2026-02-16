#!/usr/bin/env python3
"""
TARS Tunnel — Full Control Edition
Connects the local Mac to the cloud relay, manages the TARS process,
and streams everything to the dashboard in real-time.

Features:
  - Start/stop/kill TARS process remotely from dashboard
  - Stream TARS stdout/stderr to cloud in real-time
  - Forward events from event_bus to relay
  - Receive and execute commands from dashboard
  - Auto-reconnect with exponential backoff

Usage:
    python tunnel.py                           # Uses config.yaml relay settings
    python tunnel.py wss://your-app.railway.app/tunnel
"""

import os
import sys
import json
import time
import asyncio
import signal
import subprocess
import threading
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils.event_bus import event_bus


def load_config():
    config_path = os.path.join(BASE_DIR, "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


class TARSProcessManager:
    """Manages the tars.py process — both spawned and externally-started.

    Detects any running tars.py process on the system and "adopts" it,
    so the dashboard/tunnel always shows the real status. Start/stop/kill
    work regardless of how TARS was launched (tunnel, terminal, menu bar).
    """

    def __init__(self, base_dir: str, on_output=None, on_status_change=None):
        self.base_dir = base_dir
        self.process: subprocess.Popen = None  # Only set if WE spawned it
        self._adopted_pid: int = None  # PID of externally-started TARS
        self.on_output = on_output  # callback(stream, text)
        self.on_status_change = on_status_change  # callback(status_dict)
        self._reader_threads = []
        self._started_at = None
        self._scan_lock = threading.Lock()

        # Start a background thread to continuously scan for external TARS
        self._scanner_running = True
        self._scanner = threading.Thread(target=self._scan_loop, daemon=True)
        self._scanner.start()

    # ── Process Detection ──────────────────────────────

    def _find_external_tars_pid(self) -> int:
        """Find a running tars.py process that we didn't spawn."""
        try:
            # pgrep for any process with tars.py in its command line
            r = subprocess.run(
                ["pgrep", "-f", "tars\\.py"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                return None

            my_pid = os.getpid()
            our_child = self.process.pid if self.process and self.process.poll() is None else None
            parent_pid = os.getppid()

            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    pid = int(line)
                except ValueError:
                    continue
                if pid in (my_pid, our_child, parent_pid):
                    continue
                # Verify it's actually tars.py (not tunnel.py, tars_control.py, etc.)
                try:
                    cmd_r = subprocess.run(
                        ["ps", "-ww", "-p", str(pid), "-o", "command="],
                        capture_output=True, text=True, timeout=3,
                    )
                    cmd_line = cmd_r.stdout.strip()
                    if ("tars.py" in cmd_line
                            and "tunnel" not in cmd_line.lower()
                            and "tars_control" not in cmd_line.lower()
                            and "pgrep" not in cmd_line.lower()):
                        return pid
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if a PID is still running."""
        if pid is None:
            return False
        try:
            os.kill(pid, 0)  # signal 0 = just check
            return True
        except (OSError, ProcessLookupError):
            return False

    def _scan_loop(self):
        """Background scanner: detect external TARS processes appearing/disappearing."""
        while self._scanner_running:
            try:
                self._scan_once()
            except Exception:
                pass
            time.sleep(3)  # Check every 3 seconds

    def _scan_once(self):
        """Single scan cycle — detect or release adopted processes."""
        with self._scan_lock:
            # If we spawned TARS and it's still running, nothing to scan
            if self.process and self.process.poll() is None:
                return

            # If we have an adopted PID, check if it's still alive
            if self._adopted_pid:
                if not self._is_pid_alive(self._adopted_pid):
                    old_pid = self._adopted_pid
                    self._adopted_pid = None
                    self._started_at = None
                    self._emit_output("system", f"TARS process (PID {old_pid}) exited")
                    self._notify_status("stopped")
                return

            # No tracked TARS — scan for an external one
            ext_pid = self._find_external_tars_pid()
            if ext_pid:
                self._adopted_pid = ext_pid
                self._started_at = self._started_at or time.time()
                self._emit_output("system", f"Detected running TARS (PID {ext_pid}) — adopted")
                self._notify_status("running")

    # ── Properties ──────────────────────────────────────

    @property
    def is_running(self) -> bool:
        # Our spawned process
        if self.process is not None and self.process.poll() is None:
            return True
        # Externally adopted process
        if self._adopted_pid and self._is_pid_alive(self._adopted_pid):
            return True
        return False

    @property
    def pid(self):
        if self.process and self.process.poll() is None:
            return self.process.pid
        if self._adopted_pid and self._is_pid_alive(self._adopted_pid):
            return self._adopted_pid
        return None

    def get_status(self) -> dict:
        running = self.is_running
        mode = "unknown"
        if running:
            if self.process and self.process.poll() is None:
                mode = "managed"  # We spawned it
            else:
                mode = "adopted"  # External process we detected
        return {
            "running": running,
            "pid": self.pid,
            "started_at": self._started_at,
            "status": "running" if running else "stopped",
            "mode": mode,
            "uptime": (time.time() - self._started_at) if self._started_at and running else 0,
        }

    # ── Start ───────────────────────────────────────────

    def start(self, task: str = None) -> dict:
        """Start tars.py as a subprocess."""
        if self.is_running:
            return {"success": False, "error": "TARS is already running", "pid": self.pid}

        try:
            # Find python in the venv
            venv_python = os.path.join(self.base_dir, "venv", "bin", "python")
            if not os.path.exists(venv_python):
                venv_python = sys.executable  # fallback to current python

            cmd = [venv_python, os.path.join(self.base_dir, "tars.py")]
            if task:
                cmd.append(task)

            self._emit_output("system", f"Starting TARS: {' '.join(cmd)}")
            self._notify_status("starting")

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.base_dir,
                bufsize=1,
                universal_newlines=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            self._started_at = time.time()
            self._adopted_pid = None  # Clear any adopted PID

            # Start reader threads for stdout and stderr
            self._reader_threads = []
            for stream_name, pipe in [("stdout", self.process.stdout), ("stderr", self.process.stderr)]:
                t = threading.Thread(target=self._read_stream, args=(stream_name, pipe), daemon=True)
                t.start()
                self._reader_threads.append(t)

            # Monitor thread for process exit
            t = threading.Thread(target=self._monitor_process, daemon=True)
            t.start()
            self._reader_threads.append(t)

            self._notify_status("running")
            self._emit_output("system", f"TARS started (PID {self.process.pid})")

            return {"success": True, "pid": self.process.pid}

        except Exception as e:
            self._notify_status("error")
            self._emit_output("system", f"Failed to start TARS: {e}")
            return {"success": False, "error": str(e)}

    # ── Stop ────────────────────────────────────────────

    def stop(self) -> dict:
        """Gracefully stop TARS (SIGTERM). Works for both spawned and adopted."""
        if not self.is_running:
            return {"success": False, "error": "TARS is not running"}

        target_pid = self.pid
        self._emit_output("system", f"Stopping TARS (PID {target_pid})...")
        self._notify_status("stopping")

        try:
            # If it's our subprocess, use Popen methods
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._emit_output("system", "TARS didn't stop gracefully, killing...")
                    self.process.kill()
                    self.process.wait(timeout=5)
            else:
                # Adopted process — send SIGTERM directly
                os.kill(target_pid, signal.SIGTERM)
                # Wait for it to die
                for _ in range(20):  # 10 seconds
                    time.sleep(0.5)
                    if not self._is_pid_alive(target_pid):
                        break
                else:
                    # Still alive — force kill
                    self._emit_output("system", "TARS didn't stop gracefully, killing...")
                    os.kill(target_pid, signal.SIGKILL)
                    time.sleep(1)

            self._started_at = None
            self._adopted_pid = None
            self._notify_status("stopped")
            self._emit_output("system", f"TARS stopped (was PID {target_pid})")
            return {"success": True}

        except Exception as e:
            self._emit_output("system", f"Error stopping TARS: {e}")
            return {"success": False, "error": str(e)}

    # ── Kill ────────────────────────────────────────────

    def kill(self) -> dict:
        """Force kill TARS (SIGKILL). Works for both spawned and adopted."""
        if not self.is_running:
            return {"success": False, "error": "TARS is not running"}

        target_pid = self.pid
        self._emit_output("system", f"KILLING TARS (PID {target_pid})!")
        self._notify_status("killed")

        try:
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            else:
                os.kill(target_pid, signal.SIGKILL)
                time.sleep(1)

            self._started_at = None
            self._adopted_pid = None
            self._notify_status("stopped")
            self._emit_output("system", f"TARS killed (was PID {target_pid})")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Restart ─────────────────────────────────────────

    def restart(self, task: str = None) -> dict:
        """Restart TARS."""
        self._emit_output("system", "Restarting TARS...")
        if self.is_running:
            result = self.stop()
            if not result.get("success"):
                self.kill()
            time.sleep(1)
        return self.start(task=task)

    # ── Internal Helpers ────────────────────────────────

    def _read_stream(self, stream_name: str, pipe):
        """Read a subprocess output stream line by line."""
        try:
            for line in pipe:
                line = line.rstrip('\n')
                if line:
                    self._emit_output(stream_name, line)
        except Exception:
            pass

    def _monitor_process(self):
        """Monitor the subprocess and report when it exits."""
        if self.process:
            returncode = self.process.wait()
            self._started_at = None
            self._emit_output("system", f"TARS process exited with code {returncode}")
            self._notify_status("stopped")

    def _emit_output(self, stream: str, text: str):
        """Send output to the callback."""
        if self.on_output:
            self.on_output(stream, text)

    def _notify_status(self, status: str):
        """Send status change to the callback."""
        if self.on_status_change:
            self.on_status_change(self.get_status() | {"status": status})


class TARSTunnel:
    def __init__(self, relay_url: str, token: str):
        self.relay_url = relay_url
        self.token = token
        self.ws = None
        self.running = True
        self.reconnect_delay = 1
        self.max_reconnect_delay = 30

        # Process manager
        self.process_mgr = TARSProcessManager(
            BASE_DIR,
            on_output=self._on_process_output,
            on_status_change=self._on_process_status_change,
        )

        # Queue for outbound messages
        self._send_queue: asyncio.Queue = None
        self._loop = None

    def _on_process_output(self, stream: str, text: str):
        """Called from reader threads when TARS outputs a line."""
        msg = {
            "type": "tars_output",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ts_unix": time.time(),
            "data": {"stream": stream, "text": text, "ts": time.time()},
        }
        self._enqueue(msg)

    def _on_process_status_change(self, status: dict):
        """Called when TARS process status changes."""
        msg = {
            "type": "tars_process_status",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ts_unix": time.time(),
            "data": status,
        }
        self._enqueue(msg)

    def _enqueue(self, msg: dict):
        """Thread-safe enqueue for the async send loop."""
        if self._send_queue and self._loop:
            try:
                self._loop.call_soon_threadsafe(self._send_queue.put_nowait, msg)
            except Exception:
                pass

    async def connect(self):
        """Connect to the relay and maintain the connection."""
        try:
            import websockets
        except ImportError:
            print("  [!] Install websockets: pip install websockets")
            sys.exit(1)

        self._loop = asyncio.get_event_loop()

        while self.running:
            try:
                url = f"{self.relay_url}?token={self.token}"
                print(f"  [>] Connecting to relay: {self.relay_url}")

                async with websockets.connect(url, ping_interval=15, ping_timeout=10) as ws:
                    self.ws = ws
                    self.reconnect_delay = 1
                    print(f"  [+] Tunnel established")

                    # Create send queue
                    self._send_queue = asyncio.Queue()

                    # Subscribe to local event_bus and forward events
                    def on_event_sync(event_type, data):
                        event = {
                            "type": event_type,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "ts_unix": time.time(),
                            "data": data or {},
                        }
                        self._enqueue(event)

                    # Patch event_bus.emit to also forward events
                    original_emit = event_bus.emit

                    def patched_emit(event_type, data=None):
                        original_emit(event_type, data)
                        on_event_sync(event_type, data)

                    event_bus.emit = patched_emit

                    # Send initial process status
                    self._on_process_status_change(self.process_mgr.get_status())

                    # Three concurrent tasks: send events, receive commands, status heartbeat
                    send_task = asyncio.create_task(self._send_loop(ws))
                    recv_task = asyncio.create_task(self._recv_loop(ws))
                    heartbeat_task = asyncio.create_task(self._status_heartbeat())

                    done, pending = await asyncio.wait(
                        [send_task, recv_task, heartbeat_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()

                    # Restore original emit
                    event_bus.emit = original_emit

            except Exception as e:
                print(f"  [!] Tunnel error: {e}")

            if self.running:
                print(f"  [~] Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def _send_loop(self, ws):
        """Forward queued messages to the relay."""
        while True:
            msg = await self._send_queue.get()
            try:
                await ws.send(json.dumps(msg))
            except Exception:
                return

    async def _recv_loop(self, ws):
        """Receive commands from the relay (from dashboard) and handle them."""
        async for message in ws:
            if message == "pong":
                continue
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")
                cmd_id = data.get("cmd_id", "")

                # ── Control commands (start/stop/kill TARS) ──
                if msg_type == "control_command":
                    command = data.get("command", "")
                    cmd_data = data.get("data", {})
                    result = self._handle_control_command(command, cmd_data)

                    # Send response back to relay
                    response = {
                        "type": "command_response",
                        "cmd_id": cmd_id,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "ts_unix": time.time(),
                        "data": result,
                    }
                    self._enqueue(response)
                    continue

                # ── Legacy message types ──
                if msg_type == "send_task":
                    task = data.get("task", "")
                    if task:
                        # If TARS is running, forward to local WS
                        if self.process_mgr.is_running:
                            await self._forward_to_local(message)
                            event_bus.emit("task_received", {"task": task, "source": "dashboard"})
                        else:
                            # Start TARS with this task
                            self.process_mgr.start(task=task)

                elif msg_type == "kill":
                    if self.process_mgr.is_running:
                        self.process_mgr.kill()
                    event_bus.emit("kill_switch", {"source": "dashboard"})

                elif msg_type in ("get_stats", "get_memory", "save_memory", "update_config"):
                    await self._forward_to_local(message)

            except json.JSONDecodeError:
                pass

    def _handle_control_command(self, command: str, data: dict) -> dict:
        """Handle a control command from the dashboard."""
        if command == "start_tars":
            task = data.get("task")
            return self.process_mgr.start(task=task)

        elif command == "stop_tars":
            return self.process_mgr.stop()

        elif command == "kill_tars":
            return self.process_mgr.kill()

        elif command == "restart_tars":
            task = data.get("task")
            return self.process_mgr.restart(task=task)

        elif command == "get_process_status":
            return {"success": True, **self.process_mgr.get_status()}

        elif command == "send_task":
            task = data.get("task", "")
            if not task:
                return {"success": False, "error": "No task provided"}
            if self.process_mgr.is_running:
                # Forward to running TARS
                asyncio.run_coroutine_threadsafe(
                    self._forward_to_local(json.dumps({"type": "send_task", "task": task})),
                    self._loop,
                )
                return {"success": True, "message": "Task sent to running TARS"}
            else:
                # Start TARS with this task
                return self.process_mgr.start(task=task)

        return {"success": False, "error": f"Unknown command: {command}"}

    async def _status_heartbeat(self):
        """Periodically send process status to the relay."""
        while True:
            await asyncio.sleep(5)
            self._on_process_status_change(self.process_mgr.get_status())

    async def _forward_to_local(self, message: str):
        """Forward a command to the local TARS WebSocket server."""
        try:
            import websockets
            async with websockets.connect("ws://localhost:8421") as local_ws:
                await local_ws.send(message)
                response = await asyncio.wait_for(local_ws.recv(), timeout=5)
                # Forward response back through tunnel
                if self.ws:
                    await self.ws.send(response)
        except Exception:
            pass

    def stop(self):
        """Stop the tunnel (and TARS if running)."""
        self.running = False
        if self.process_mgr.is_running:
            self.process_mgr.stop()


def main():
    config = load_config()

    # Get relay URL from CLI arg or config
    if len(sys.argv) > 1:
        relay_url = sys.argv[1]
    else:
        relay_url = config.get("relay", {}).get("url", "")
        if not relay_url:
            print("  [!] No relay URL configured.")
            print("  Usage: python tunnel.py wss://your-app.railway.app/tunnel")
            print("  Or add relay.url to config.yaml")
            sys.exit(1)

    token = config.get("relay", {}).get("token", "tars-default-token-change-me")

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║     TARS TUNNEL — Full Control       ║")
    print("  ╠══════════════════════════════════════╣")
    print(f"  ║  Relay: {relay_url[:30]:<30}║")
    print("  ║  Process Manager: Ready              ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    tunnel = TARSTunnel(relay_url, token)

    def shutdown(*args):
        print("\n  [x] Tunnel shutting down...")
        tunnel.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    asyncio.run(tunnel.connect())


if __name__ == "__main__":
    main()
