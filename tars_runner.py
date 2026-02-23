#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  TARS Service Runner — 24/7 Background Service               ║
╠══════════════════════════════════════════════════════════════╣
║  Called by launchd or run standalone in Terminal.app.          ║
║                                                              ║
║  Features:                                                   ║
║   • Auto-restarts TARS on crash (10s cooldown)               ║
║   • Auto-reloads when .py files change                       ║
║   • Prevents Mac from sleeping (caffeinate)                  ║
║   • Proper signal handling for graceful shutdown             ║
║                                                              ║
║  Usage:                                                      ║
║    .venv/bin/python tars_runner.py                            ║
║    .venv/bin/python tars_runner.py --no-reload               ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import signal
import subprocess
import hashlib
import threading
import resource
from pathlib import Path
from datetime import datetime

TARS_DIR = Path(__file__).parent.resolve()
PYTHON = str(TARS_DIR / ".venv" / "bin" / "python")
TARS_SCRIPT = str(TARS_DIR / "tars.py")

# Use /tmp for launchd-spawned logs (~/Downloads is sandboxed on macOS)
# The runner writes its own log + TARS subprocess logs
LOG_DIR = Path("/tmp/tars-logs")
SERVICE_LOG = LOG_DIR / "tars-service.log"
TARS_STDOUT = LOG_DIR / "tars-stdout.log"
TARS_STDERR = LOG_DIR / "tars-stderr.log"

# Globals
tars_process = None
watcher_thread = None
shutting_down = False
auto_reload = "--no-reload" not in sys.argv
_tars_log_fh = None
_tars_err_fh = None


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(SERVICE_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def free_ports():
    """Kill anything on ports 8420/8421."""
    try:
        result = subprocess.run(
            "lsof -ti:8420 -ti:8421 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        pids = result.stdout.strip()
        if pids:
            log(f"   Freeing ports 8420/8421 (PIDs: {pids.replace(chr(10), ', ')})")
            subprocess.run(f"echo '{pids}' | xargs kill -9 2>/dev/null", shell=True)
            time.sleep(1)
    except Exception:
        pass


def start_tars():
    """Start TARS as a subprocess with caffeinate."""
    global tars_process, _tars_log_fh, _tars_err_fh
    free_ports()
    log("🚀 Starting TARS...")

    # Close previous log handles to avoid FD leak on restart
    for fh in (_tars_log_fh, _tars_err_fh):
        try:
            if fh:
                fh.close()
        except Exception:
            pass

    _tars_log_fh = open(TARS_STDOUT, "a")
    _tars_err_fh = open(TARS_STDERR, "a")

    tars_process = subprocess.Popen(
        ["/usr/bin/caffeinate", "-s", PYTHON, TARS_SCRIPT],
        cwd=str(TARS_DIR),
        stdout=_tars_log_fh,
        stderr=_tars_err_fh,
        env={**os.environ, "HOME": str(Path.home()), "LANG": "en_US.UTF-8"},
    )
    log(f"   PID: {tars_process.pid}")


def stop_tars():
    """Gracefully stop TARS."""
    global tars_process
    if tars_process and tars_process.poll() is None:
        log("   Sending SIGTERM to TARS...")
        tars_process.terminate()
        try:
            tars_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log("   Force-killing TARS...")
            tars_process.kill()
            tars_process.wait()
        tars_process = None


def restart_tars():
    """Stop and restart TARS."""
    log("🔄 Restarting TARS...")
    stop_tars()
    time.sleep(2)
    start_tars()


def get_code_hash():
    """Hash all .py files (excluding venv, tests, cache) to detect changes."""
    hasher = hashlib.md5()
    try:
        py_files = sorted(
            p for p in TARS_DIR.rglob("*.py")
            if not any(skip in p.parts for skip in (".venv", "venv", "__pycache__", "tests", "node_modules"))
            and p.name != "tars_runner.py"
            and p.name != "send_task.py"
        )
        for pf in py_files:
            try:
                stat = pf.stat()
                hasher.update(f"{pf}:{stat.st_mtime}:{stat.st_size}".encode())
            except Exception:
                pass
    except Exception:
        pass
    return hasher.hexdigest()


def file_watcher():
    """Watch .py files for changes and trigger restart."""
    global shutting_down
    log("👁️  File watcher active (auto-reload on .py changes)")
    last_hash = get_code_hash()

    while not shutting_down:
        time.sleep(5)
        if shutting_down:
            break
        current_hash = get_code_hash()
        if current_hash != last_hash:
            log("📝 Code change detected — reloading TARS...")
            last_hash = current_hash
            restart_tars()
            # Wait a bit after restart to let things settle
            time.sleep(10)
            last_hash = get_code_hash()


def handle_signal(signum, frame):
    """Handle shutdown signals."""
    global shutting_down
    sig_name = signal.Signals(signum).name
    log(f"🛑 Received {sig_name} — shutting down...")
    shutting_down = True
    stop_tars()
    free_ports()
    log("✅ Service stopped.")
    sys.exit(0)


def main():
    global watcher_thread

    # Ensure we're in the TARS directory (tars.py expects CWD to be repo root)
    os.chdir(str(TARS_DIR))

    # Raise file descriptor limit (macOS default 256 is too low for 24/7 agent)
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
        log(f"   FD limit: {soft} → {min(4096, hard)}")
    except Exception:
        pass

    LOG_DIR.mkdir(exist_ok=True)

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGHUP, handle_signal)

    log("═══════════════════════════════════════════")
    log("  TARS Service Runner")
    log(f"  Dir:    {TARS_DIR}")
    log(f"  Python: {PYTHON}")
    log(f"  Reload: {auto_reload}")
    log("═══════════════════════════════════════════")

    # Start TARS
    start_tars()

    # Start file watcher
    if auto_reload:
        watcher_thread = threading.Thread(target=file_watcher, daemon=True)
        watcher_thread.start()

    # Main loop: monitor TARS and restart on crash
    while not shutting_down:
        if tars_process and tars_process.poll() is not None:
            exit_code = tars_process.returncode
            if exit_code == 0:
                log(f"⚠️  TARS exited cleanly (code 0). Restarting in 10s...")
            else:
                log(f"💥 TARS crashed (exit code: {exit_code}). Restarting in 10s...")
            time.sleep(10)
            if not shutting_down:
                start_tars()
        time.sleep(3)


if __name__ == "__main__":
    main()
