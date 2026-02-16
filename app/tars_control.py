#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║         TARS Control — macOS Menu Bar App            ║
╠══════════════════════════════════════════════════════╣
║  One-click control panel for TARS automation.        ║
║  Lives in your menu bar. Manages:                    ║
║    • Tunnel connection to Railway cloud              ║
║    • Local TARS automation (browser, iMessage, etc)  ║
║    • Start / Stop / Kill from your menu bar          ║
║    • Opens Railway dashboard in browser              ║
║    • Auto-validates environment on launch            ║
╚══════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import signal
import subprocess
import threading
import webbrowser
import logging
import rumps

# ── Default Environment Setup Config ──
# What happens when TARS starts — optimized for iMessage workflow
DEFAULT_SETUP = {
    "ensure_running": ["Messages", "Google Chrome", "Mail"],
    "close_distracting": ["Music", "Spotify", "TV", "News", "Podcasts", "Photos", "FaceTime", "Photo Booth"],
    "volume": 30,
    "do_not_disturb": True,
    "dark_mode": True,
    "notify_ready": True,
}

LOG_FILE = os.path.expanduser("~/Library/Logs/TARSControl.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tars_control")

# ── Paths ──────────────────────────────────────────
# When running as a .app bundle, resources are in Contents/Resources
if getattr(sys, '_MEIPASS', None):
    BUNDLE_DIR = sys._MEIPASS
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

# TARS project directory — one level up from app/
TARS_DIR = os.environ.get("TARS_DIR", os.path.dirname(BUNDLE_DIR))

# Validate TARS_DIR has the expected structure
if not os.path.isfile(os.path.join(TARS_DIR, "tars.py")):
    # Try parent of parent (when inside .app bundle)
    alt = os.path.dirname(os.path.dirname(BUNDLE_DIR))
    if os.path.isfile(os.path.join(alt, "tars.py")):
        TARS_DIR = alt

VENV_PYTHON = os.path.join(TARS_DIR, "venv", "bin", "python")
TUNNEL_SCRIPT = os.path.join(TARS_DIR, "tunnel.py")
CONFIG_FILE = os.path.join(TARS_DIR, "config.yaml")


def load_config():
    """Load config.yaml from TARS directory."""
    try:
        import yaml
        with open(CONFIG_FILE, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def get_python():
    """Get the best Python executable."""
    if os.path.isfile(VENV_PYTHON):
        return VENV_PYTHON
    return sys.executable


class TARSControlApp(rumps.App):
    """macOS menu bar app for controlling TARS."""

    def __init__(self):
        super().__init__(
            "TARS",
            title="🤖",
            quit_button=None,  # We'll add our own
        )
        log.info("TARS Control starting — TARS_DIR=%s", TARS_DIR)

        self.config = load_config()
        self.relay_url = self.config.get("relay", {}).get("url", "")
        self.dashboard_url = self.relay_url.replace("wss://", "https://").replace("/tunnel", "") if self.relay_url else ""

        # State
        self._tunnel_proc = None
        self._tunnel_output = []
        self._health_data = {}
        self._monitor_thread = None
        self._auth_token = None
        self._auth_expiry = 0

        # ── Validate environment on startup ──
        self._env_ok = self._validate_environment()

        # Build menu
        self.status_item = rumps.MenuItem("⚪ Disconnected", callback=None)
        self.status_item.set_callback(None)

        self.tunnel_item = rumps.MenuItem("▶ Start Tunnel", callback=self.toggle_tunnel)
        self.tars_item = rumps.MenuItem("▶ Start TARS", callback=self.toggle_tars)
        self.tars_item.set_callback(None)  # Disabled until tunnel is up

        self.dashboard_item = rumps.MenuItem("🌐 Open Dashboard", callback=self.open_dashboard)
        self.kill_item = rumps.MenuItem("🛑 Kill Switch", callback=self.kill_switch)
        self.kill_item.set_callback(None)  # Disabled until TARS running

        self.logs_item = rumps.MenuItem("📋 View Logs", callback=self.view_logs)
        self.health_item = rumps.MenuItem("💓 Health: checking...", callback=self.check_health)

        self.auto_connect_item = rumps.MenuItem("🔄 Auto-Connect on Launch")
        self.auto_connect_item.state = self.config.get("app", {}).get("auto_connect", False)

        self.auto_setup_item = rumps.MenuItem("🧹 Auto-Setup on Start", callback=self.toggle_auto_setup)
        self.auto_setup_item.state = self.config.get("app", {}).get("auto_setup", True)

        self.prepare_item = rumps.MenuItem("🛠 Prepare Mac Now", callback=self.prepare_mac_now)
        self.env_status_item = rumps.MenuItem("📊 Environment: unknown", callback=self.show_environment)

        # Load setup config (user can override in config.yaml under 'app.setup')
        app_cfg = self.config.get("app", {})
        self._setup = {**DEFAULT_SETUP, **app_cfg.get("setup", {})}
        self._last_setup_report = ""

        self.menu = [
            self.status_item,
            self.env_status_item,
            None,  # separator
            self.tunnel_item,
            self.tars_item,
            self.kill_item,
            None,
            self.prepare_item,
            self.dashboard_item,
            self.health_item,
            self.logs_item,
            None,
            self.auto_connect_item,
            self.auto_setup_item,
            rumps.MenuItem("⚙ Settings", callback=self.open_settings),
            rumps.MenuItem("📁 Open TARS Folder", callback=self.open_folder),
            rumps.MenuItem("📄 View App Logs", callback=self.view_app_logs),
            None,
            rumps.MenuItem("Quit TARS Control", callback=self.quit_app),
        ]

        # Start health monitor
        self._start_health_monitor()

        # Auto-connect if enabled
        if self._env_ok and self.auto_connect_item.state:
            log.info("Auto-connect enabled, starting tunnel...")
            threading.Timer(1.0, lambda: self._start_tunnel()).start()

        # Initial environment check (non-blocking)
        threading.Timer(2.0, self._update_env_status).start()

    # ─── Environment Validation ────────────────────────

    def _validate_environment(self):
        """Validate that TARS is properly set up."""
        issues = []

        if not os.path.isfile(os.path.join(TARS_DIR, "tars.py")):
            issues.append("tars.py not found")
        if not os.path.isfile(TUNNEL_SCRIPT):
            issues.append("tunnel.py not found")
        if not os.path.isfile(CONFIG_FILE):
            issues.append("config.yaml not found")
        if not os.path.isfile(VENV_PYTHON):
            issues.append("Python venv not found")
        if not self.relay_url:
            issues.append("No relay URL in config.yaml")

        if issues:
            log.warning("Environment issues: %s", ", ".join(issues))
            rumps.notification(
                "TARS Control",
                "Setup Issue",
                "Missing: " + ", ".join(issues) + "\nCheck TARS folder: " + TARS_DIR,
            )
            return False

        log.info("Environment validated OK")
        return True

    # ─── Environment Auto-Setup ─────────────────────────

    def toggle_auto_setup(self, sender):
        """Toggle auto-setup on TARS start."""
        sender.state = not sender.state
        log.info("Auto-setup on start: %s", "ON" if sender.state else "OFF")

    def prepare_mac_now(self, sender):
        """Manually prepare the Mac environment."""
        threading.Thread(target=self._setup_environment, args=(True,), daemon=True).start()

    def show_environment(self, sender):
        """Show current environment status."""
        threading.Thread(target=self._show_env_detail, daemon=True).start()

    def _show_env_detail(self):
        """Gather and display environment info."""
        try:
            info = []
            # Running apps
            r = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process whose background only is false'],
                capture_output=True, text=True, timeout=10
            )
            apps = [a.strip() for a in r.stdout.strip().split(",")] if r.returncode == 0 else []
            info.append(f"Running Apps ({len(apps)}):")
            for a in sorted(apps):
                marker = "✅" if a in self._setup.get("ensure_running", []) else "  "
                info.append(f"  {marker} {a}")

            # Volume
            r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                             capture_output=True, text=True, timeout=5)
            vol = r.stdout.strip() if r.returncode == 0 else "?"
            info.append(f"\nVolume: {vol}%")

            # Dark mode
            r = subprocess.run(["osascript", "-e",
                              'tell application "System Events" to tell appearance preferences to get dark mode'],
                             capture_output=True, text=True, timeout=5)
            dm = r.stdout.strip() if r.returncode == 0 else "?"
            info.append(f"Dark Mode: {dm}")

            # Battery
            r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
            batt = r.stdout.strip().split("\n")[-1].strip() if r.returncode == 0 else "?"
            info.append(f"Battery: {batt}")

            # Messages running?
            msgs_running = "Messages" in apps
            info.append(f"\niMessage Ready: {'✅ Yes' if msgs_running else '❌ No — Messages not running'}")

            # Chrome running?
            chrome_running = "Google Chrome" in apps
            info.append(f"Chrome Ready: {'✅ Yes' if chrome_running else '❌ No'}")

            if self._last_setup_report:
                info.append(f"\nLast Setup:\n{self._last_setup_report}")

            rumps.alert("TARS — Mac Environment", "\n".join(info))
        except Exception as e:
            rumps.alert("Environment Check Error", str(e))

    def _update_env_status(self):
        """Quick env status update for the menu item."""
        try:
            r = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process whose background only is false'],
                capture_output=True, text=True, timeout=10
            )
            apps = [a.strip() for a in r.stdout.strip().split(",")] if r.returncode == 0 else []
            needed = self._setup.get("ensure_running", [])
            ready = all(app in apps for app in needed)
            msgs = "Messages" in apps
            if ready and msgs:
                self.env_status_item.title = f"📊 Environment: ✅ Ready ({len(apps)} apps)"
            elif msgs:
                missing = [a for a in needed if a not in apps]
                self.env_status_item.title = f"📊 Environment: ⚠️ Missing {', '.join(missing)}"
            else:
                self.env_status_item.title = "📊 Environment: ❌ Messages not running"
        except Exception:
            self.env_status_item.title = "📊 Environment: ?"

    def _setup_environment(self, manual=False):
        """
        Prepare the Mac for TARS operation.
        Called automatically when TARS starts (if auto_setup enabled),
        or manually via the menu item.

        Steps:
          1. Ensure critical apps are running (Messages, Chrome, Mail)
          2. Close distracting apps (Music, Spotify, etc.)
          3. Set volume to a low level (don't blast notifications)
          4. Enable dark mode (TARS aesthetic)
          5. Send a notification when ready
        """
        log.info("Setting up environment (manual=%s)...", manual)
        actions = []
        setup = self._setup

        # ── Step 1: Ensure critical apps are running ──
        ensure = setup.get("ensure_running", [])
        if ensure:
            try:
                r = subprocess.run(
                    ["osascript", "-e",
                     'tell application "System Events" to get name of every process whose background only is false'],
                    capture_output=True, text=True, timeout=10
                )
                running = [a.strip() for a in r.stdout.strip().split(",")] if r.returncode == 0 else []
            except Exception:
                running = []

            for app in ensure:
                if app not in running:
                    try:
                        subprocess.run(
                            ["osascript", "-e", f'tell application "{app}" to activate'],
                            capture_output=True, timeout=10
                        )
                        actions.append(f"✅ Opened {app}")
                        log.info("Opened %s", app)
                        time.sleep(1)  # Give app time to launch
                    except Exception as e:
                        actions.append(f"❌ Failed to open {app}: {e}")
                        log.error("Failed to open %s: %s", app, e)
                else:
                    actions.append(f"✅ {app} already running")

        # ── Step 2: Close distracting apps ──
        close_apps = setup.get("close_distracting", [])
        if close_apps:
            for app in close_apps:
                try:
                    r = subprocess.run(
                        ["osascript", "-e",
                         f'tell application "System Events" to (name of every process) contains "{app}"'],
                        capture_output=True, text=True, timeout=5
                    )
                    if r.returncode == 0 and r.stdout.strip().lower() == "true":
                        subprocess.run(
                            ["osascript", "-e", f'tell application "{app}" to quit'],
                            capture_output=True, timeout=10
                        )
                        actions.append(f"🚫 Closed {app}")
                        log.info("Closed distracting app: %s", app)
                except Exception:
                    pass  # App wasn't running, that's fine

        # ── Step 3: Set volume ──
        target_vol = setup.get("volume")
        if target_vol is not None:
            try:
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {target_vol}"],
                    capture_output=True, timeout=5
                )
                actions.append(f"🔊 Volume → {target_vol}%")
            except Exception as e:
                actions.append(f"❌ Volume: {e}")

        # ── Step 4: Dark mode ──
        if setup.get("dark_mode") is not None:
            try:
                val = "true" if setup["dark_mode"] else "false"
                subprocess.run(
                    ["osascript", "-e",
                     f'tell application "System Events" to tell appearance preferences to set dark mode to {val}'],
                    capture_output=True, timeout=5
                )
                actions.append(f"🌙 Dark mode → {'on' if setup['dark_mode'] else 'off'}")
            except Exception:
                pass

        # ── Step 5: Focus — hide non-essential windows ──
        try:
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to set visible of every process whose name is not "Finder" and name is not "Messages" and name is not "Google Chrome" to false'],
                capture_output=True, timeout=10
            )
            actions.append("👁 Hidden non-essential windows")
        except Exception:
            pass

        # ── Step 6: Bring Messages to front ──
        try:
            subprocess.run(
                ["osascript", "-e", 'tell application "Messages" to activate'],
                capture_output=True, timeout=5
            )
            actions.append("💬 Messages → front")
        except Exception:
            pass

        # ── Report ──
        report = "\n".join(actions) if actions else "No changes needed"
        self._last_setup_report = report
        log.info("Environment setup complete: %s", report.replace("\n", " | "))

        # Update env status
        self._update_env_status()

        # Notify
        if setup.get("notify_ready", True):
            rumps.notification(
                "TARS Control",
                "✅ Mac Ready for TARS" if manual else "✅ Environment Prepared",
                f"{len([a for a in actions if a.startswith('✅')])} apps ready, volume {setup.get('volume', '?')}%"
            )

        return actions

    # ─── Tunnel Control ────────────────────────────────

    def toggle_tunnel(self, sender):
        """Start or stop the tunnel."""
        if self._tunnel_proc and self._tunnel_proc.poll() is None:
            self._stop_tunnel()
        else:
            self._start_tunnel()

    def _start_tunnel(self):
        """Launch tunnel.py as a subprocess."""
        if not os.path.isfile(TUNNEL_SCRIPT):
            rumps.notification("TARS Control", "Error", f"tunnel.py not found at {TUNNEL_SCRIPT}")
            return

        if not self.relay_url:
            rumps.notification("TARS Control", "Error", "No relay URL configured in config.yaml")
            return

        python = get_python()
        try:
            self._tunnel_proc = subprocess.Popen(
                [python, TUNNEL_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=TARS_DIR,
                bufsize=1,
                universal_newlines=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            # Reader thread for tunnel output
            t = threading.Thread(target=self._read_tunnel_output, daemon=True)
            t.start()

            self.tunnel_item.title = "⏹ Stop Tunnel"
            self.tars_item.set_callback(self.toggle_tars)
            self._update_status("tunnel_connected")

            rumps.notification("TARS Control", "Tunnel Started",
                             f"Connected to {self.relay_url.split('//')[1].split('/')[0]}")

        except Exception as e:
            rumps.notification("TARS Control", "Tunnel Error", str(e))

    def _stop_tunnel(self):
        """Stop the tunnel subprocess."""
        if self._tunnel_proc:
            try:
                self._tunnel_proc.terminate()
                try:
                    self._tunnel_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._tunnel_proc.kill()
            except Exception:
                pass
            self._tunnel_proc = None

        self.tunnel_item.title = "▶ Start Tunnel"
        self.tars_item.title = "▶ Start TARS"
        self.tars_item.set_callback(None)
        self.kill_item.set_callback(None)
        self._update_status("disconnected")

        rumps.notification("TARS Control", "Tunnel Stopped", "Disconnected from cloud relay")

    def _read_tunnel_output(self):
        """Read tunnel subprocess output in a background thread."""
        try:
            for line in self._tunnel_proc.stdout:
                line = line.rstrip('\n')
                if line:
                    self._tunnel_output.append(line)
                    # Keep last 500 lines
                    if len(self._tunnel_output) > 500:
                        self._tunnel_output = self._tunnel_output[-500:]
                    # Update status based on output
                    if "Tunnel established" in line:
                        self._update_status("tunnel_connected")
                    elif "Reconnecting" in line:
                        self._update_status("reconnecting")
                    elif "Tunnel error" in line:
                        self._update_status("tunnel_error")
        except Exception:
            pass
        finally:
            # Tunnel died
            if self._tunnel_proc and self._tunnel_proc.poll() is not None:
                self._update_status("disconnected")
                self.tunnel_item.title = "▶ Start Tunnel"
                self.tars_item.set_callback(None)
                self.kill_item.set_callback(None)
                self._tunnel_proc = None

    # ─── TARS Control (via Railway API) ─────────────────

    def toggle_tars(self, sender):
        """Start or stop TARS via the cloud relay API."""
        if self._is_tars_running():
            self._send_command("stop_tars")
            self.tars_item.title = "▶ Start TARS"
            self.kill_item.set_callback(None)
            rumps.notification("TARS Control", "TARS Stopping", "Sending stop command...")
        else:
            # ── Auto-setup before starting TARS ──
            if self.auto_setup_item.state:
                rumps.notification("TARS Control", "Preparing Mac...", "Setting up environment for TARS")
                threading.Thread(
                    target=self._start_tars_with_setup,
                    daemon=True
                ).start()
            else:
                self._send_start_tars()

    def _start_tars_with_setup(self):
        """Run environment setup, then start TARS."""
        try:
            self._setup_environment(manual=False)
            time.sleep(1)  # Brief pause after setup
        except Exception as e:
            log.error("Setup error (continuing anyway): %s", e)
        self._send_start_tars()

    def _send_start_tars(self):
        """Send the start command to TARS."""
        self._send_command("start_tars")
        self.tars_item.title = "⏹ Stop TARS"
        self.kill_item.set_callback(self.kill_switch)
        self._update_status("tars_running")
        rumps.notification("TARS Control", "TARS Starting", "Launching TARS automation...")

    def kill_switch(self, sender):
        """Emergency kill switch."""
        if rumps.alert(
            "Kill Switch",
            "This will immediately kill all TARS processes.\nAre you sure?",
            ok="KILL",
            cancel="Cancel"
        ) == 1:
            self._send_command("kill_tars")
            self.tars_item.title = "▶ Start TARS"
            self.kill_item.set_callback(None)
            self._update_status("tunnel_connected")
            rumps.notification("TARS Control", "🛑 KILLED", "All TARS processes terminated")

    def _send_command(self, command, data=None):
        """Send a control command to TARS via the Railway relay API."""
        if not self.dashboard_url:
            return

        import urllib.request

        try:
            # Get auth token
            token = self._get_auth_token()
            if not token:
                return

            payload = json.dumps({
                "command": command,
                "data": data or {},
            }).encode()

            req = urllib.request.Request(
                f"{self.dashboard_url}/api/command",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            rumps.notification("TARS Control", "Command Error", str(e)[:80])
            return None

    def _get_auth_token(self):
        """Get a JWT token from the relay (cached)."""
        if not self.dashboard_url:
            return None

        # Return cached token if still valid
        if self._auth_token and time.time() < self._auth_expiry:
            return self._auth_token

        import urllib.request

        passphrase = self.config.get("relay", {}).get("passphrase", "")
        try:
            payload = json.dumps({"passphrase": passphrase}).encode()
            req = urllib.request.Request(
                f"{self.dashboard_url}/api/auth",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._auth_token = json.loads(resp.read()).get("token")
                self._auth_expiry = time.time() + 3500  # ~1 hour
                return self._auth_token
        except Exception:
            return None

    def _is_tars_running(self):
        """Check if TARS is running based on last health data."""
        proc = self._health_data.get("tars_process", {})
        return proc.get("running", False)

    # ─── Health Monitor ─────────────────────────────────

    def _start_health_monitor(self):
        """Start background health check thread."""
        self._monitor_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._monitor_thread.start()

    def _health_loop(self):
        """Check health every 10 seconds."""
        while True:
            try:
                self._check_health_internal()
            except Exception:
                pass
            time.sleep(10)

    def _check_health_internal(self):
        """Fetch health from Railway relay."""
        if not self.dashboard_url:
            return

        import urllib.request

        try:
            req = urllib.request.Request(f"{self.dashboard_url}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._health_data = json.loads(resp.read())

            # Update UI based on health
            tunnel_ok = self._health_data.get("tunnel_connected", False)
            tars_running = self._health_data.get("tars_process", {}).get("running", False)

            if tars_running:
                self._update_status("tars_running")
                self.tars_item.title = "⏹ Stop TARS"
                self.kill_item.set_callback(self.kill_switch)
            elif tunnel_ok:
                self._update_status("tunnel_connected")
                self.tars_item.title = "▶ Start TARS"
                self.kill_item.set_callback(None)
            else:
                if not (self._tunnel_proc and self._tunnel_proc.poll() is None):
                    self._update_status("disconnected")

            # Update health display
            uptime = self._health_data.get("relay_uptime", 0)
            h, m = int(uptime // 3600), int((uptime % 3600) // 60)
            clients = self._health_data.get("dashboard_clients", 0)
            self.health_item.title = f"💓 Relay: {h}h{m}m  |  Viewers: {clients}"

        except Exception:
            self.health_item.title = "💓 Health: offline"

    def check_health(self, sender):
        """Manual health check."""
        threading.Thread(target=self._check_health_internal, daemon=True).start()
        rumps.notification("TARS Control", "Health Check", "Refreshing status...")

    # ─── Status Updates ─────────────────────────────────

    def _update_status(self, state):
        """Update the menu bar icon and status text."""
        states = {
            "disconnected":     ("🤖", "⚪ Disconnected"),
            "tunnel_connected": ("🟡", "🟡 Tunnel Connected — TARS Idle"),
            "tars_running":     ("🟢", "🟢 TARS Running"),
            "reconnecting":     ("🟠", "🟠 Reconnecting..."),
            "tunnel_error":     ("🔴", "🔴 Tunnel Error"),
        }
        icon, status = states.get(state, ("🤖", f"⚪ {state}"))
        self.title = icon
        self.status_item.title = status

    # ─── Menu Actions ────────────────────────────────────

    def open_dashboard(self, sender):
        """Open the Railway dashboard in the default browser."""
        if self.dashboard_url:
            webbrowser.open(self.dashboard_url)
        else:
            rumps.notification("TARS Control", "No Dashboard", "Configure relay.url in config.yaml")

    def view_logs(self, sender):
        """Show recent tunnel logs in a window."""
        if self._tunnel_output:
            recent = "\n".join(self._tunnel_output[-30:])
        else:
            recent = "No tunnel output yet. Start the tunnel first."

        rumps.alert("TARS Tunnel Logs (last 30 lines)", recent)

    def open_settings(self, sender):
        """Open config.yaml in the default editor."""
        subprocess.Popen(["open", CONFIG_FILE])

    def open_folder(self, sender):
        """Open the TARS project folder in Finder."""
        subprocess.Popen(["open", TARS_DIR])

    def view_app_logs(self, sender):
        """Open TARSControl.log in Console app."""
        subprocess.Popen(["open", "-a", "Console", LOG_FILE])

    def quit_app(self, sender):
        """Quit the app, stopping tunnel if running."""
        log.info("TARS Control quitting")
        if self._tunnel_proc and self._tunnel_proc.poll() is None:
            self._stop_tunnel()
        rumps.quit_application()


if __name__ == "__main__":
    TARSControlApp().run()
