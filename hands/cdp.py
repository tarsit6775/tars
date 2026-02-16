"""
╔══════════════════════════════════════════════════════════════╗
║       TARS — Chrome DevTools Protocol (CDP) Connection       ║
╠══════════════════════════════════════════════════════════════╣
║  Raw websocket connection to Chrome.                         ║
║  Zero external dependencies beyond websocket-client.         ║
║  Handles: launch, connect, send/receive, events, tabs.       ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import threading
import time
import subprocess
import urllib.request
import websocket
import os

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_PORT = 9222


class CDP:
    """Chrome DevTools Protocol connection over WebSocket."""

    def __init__(self, port=CDP_PORT):
        self.port = port
        self._ws = None
        self._next_id = 0
        self._responses = {}          # msg_id → response dict
        self._event_queues = {}        # method → [params, ...]
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._running = False
        self._chrome_proc = None

    # ─── Connection ────────────────────────────────────

    def ensure_connected(self):
        """Ensure we have a live CDP connection. Launch Chrome if needed."""
        if self.connected:
            return

        # Try connecting to existing Chrome with debug port
        tabs = self._list_targets()
        if tabs:
            page = self._pick_page(tabs)
            if page:
                try:
                    self._connect_ws(page["webSocketDebuggerUrl"])
                    return
                except (TimeoutError, RuntimeError) as e:
                    # Tab might be stuck (e.g., on a heavy travel site)
                    # Try creating a fresh tab instead
                    print(f"    ⚠️ Existing tab unresponsive ({e}), creating fresh tab...")
                    self.close()
                    fresh = self._create_fresh_tab()
                    if fresh:
                        self._connect_ws(fresh["webSocketDebuggerUrl"])
                        return

        # No Chrome with debug port — launch it
        self._launch_chrome()
        for _ in range(40):  # Wait up to 20s
            time.sleep(0.5)
            tabs = self._list_targets()
            if tabs:
                page = self._pick_page(tabs)
                if page:
                    self._connect_ws(page["webSocketDebuggerUrl"])
                    return

        raise RuntimeError("Cannot connect to Chrome. Is it installed?")

    def _connect_ws(self, ws_url):
        """Connect websocket to a specific tab."""
        self.close()

        self._ws = websocket.WebSocket()
        self._ws.connect(ws_url, timeout=10)
        self._ws.settimeout(0.05)
        self._running = True

        # Background listener thread
        t = threading.Thread(target=self._recv_loop, daemon=True)
        t.start()

        # Enable needed CDP domains
        self.send("Page.enable")
        self.send("Runtime.enable")

    def _list_targets(self):
        """Get list of browser targets from Chrome's HTTP endpoint."""
        try:
            url = f"http://localhost:{self.port}/json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def _create_fresh_tab(self):
        """Create a new blank tab via CDP HTTP API. Returns target dict or None."""
        try:
            url = f"http://localhost:{self.port}/json/new?about:blank"
            req = urllib.request.Request(url, method='PUT')
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())
        except Exception:
            try:
                # Some Chrome versions use GET for /json/new
                url = f"http://localhost:{self.port}/json/new?about:blank"
                with urllib.request.urlopen(url, timeout=5) as r:
                    return json.loads(r.read())
            except Exception:
                return None

    def _pick_page(self, tabs):
        """Pick the best page target from target list.
        
        Priority: blank/simple tabs > any page tab > any ws target.
        Avoids picking tabs on heavy travel sites that might be stuck loading.
        """
        page_tabs = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        
        # Prefer blank/new tabs (least likely to be stuck)
        for t in page_tabs:
            url = t.get("url", "")
            if "about:blank" in url or "chrome://newtab" in url or "chrome-untrusted:" in url:
                return t
        
        # Then prefer any simple page over heavy travel sites
        heavy_sites = ("google.com/travel", "kayak.com", "skyscanner.com", "booking.com", "expedia.com")
        for t in page_tabs:
            url = t.get("url", "")
            if not any(h in url for h in heavy_sites):
                return t
        
        # Fall back to any page tab
        if page_tabs:
            return page_tabs[0]
        
        # Last resort: anything with a ws URL
        for t in tabs:
            if t.get("webSocketDebuggerUrl"):
                return t
        return None

    def _launch_chrome(self):
        """Launch Chrome with remote debugging enabled."""
        # Chrome requires --user-data-dir for remote debugging
        data_dir = os.path.join(os.path.expanduser("~"), ".tars_chrome_profile")
        os.makedirs(data_dir, exist_ok=True)

        # Check if Chrome already running without debug port — restart it
        try:
            existing = subprocess.run(
                ["pgrep", "-f", "Google Chrome"],
                capture_output=True, text=True, timeout=3
            )
            if existing.stdout.strip():
                # Chrome is running — try to quit gracefully and relaunch
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to quit'],
                    capture_output=True, timeout=5
                )
                time.sleep(3)
        except Exception:
            pass

        self._chrome_proc = subprocess.Popen(
            [
                CHROME_PATH,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={data_dir}",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ─── Send / Receive ────────────────────────────────

    def send(self, method, params=None, timeout=30):
        """Send a CDP command and wait for the response."""
        if not self._ws or not self._running:
            raise RuntimeError("Not connected to Chrome")

        with self._send_lock:
            self._next_id += 1
            mid = self._next_id

        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params

        with self._send_lock:
            self._ws.send(json.dumps(msg))

        # Wait for response
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if mid in self._responses:
                    resp = self._responses.pop(mid)
                    if "error" in resp:
                        err = resp["error"]
                        raise RuntimeError(
                            f"CDP {method}: {err.get('message', str(err))}"
                        )
                    return resp.get("result", {})
            time.sleep(0.02)

        raise TimeoutError(f"CDP timeout after {timeout}s: {method}")

    def _recv_loop(self):
        """Background thread: read websocket messages."""
        while self._running and self._ws:
            try:
                raw = self._ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                if "id" in msg:
                    # Response to a command we sent
                    with self._lock:
                        self._responses[msg["id"]] = msg
                elif "method" in msg:
                    # Unsolicited event
                    with self._lock:
                        method = msg["method"]
                        if method not in self._event_queues:
                            self._event_queues[method] = []
                        self._event_queues[method].append(msg.get("params", {}))
                        # Cap buffer size
                        if len(self._event_queues[method]) > 100:
                            self._event_queues[method] = self._event_queues[method][-50:]
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException:
                break
            except Exception:
                break
        # Clean up dead connection so _ensure() re-connects next call
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ─── Events ────────────────────────────────────────

    def drain_events(self, method):
        """Get and clear all buffered events of a given type."""
        with self._lock:
            return self._event_queues.pop(method, [])

    def wait_event(self, method, timeout=10):
        """Wait for a specific CDP event to fire. Returns params or None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                q = self._event_queues.get(method, [])
                if q:
                    return q.pop(0)
            time.sleep(0.05)
        return None

    # ─── Tab Management ────────────────────────────────

    def get_tabs(self):
        """Get all open browser tabs as list of dicts."""
        tabs = self._list_targets() or []
        return [
            {
                "id": t.get("id", ""),
                "title": t.get("title", ""),
                "url": t.get("url", ""),
                "ws_url": t.get("webSocketDebuggerUrl", ""),
            }
            for t in tabs
            if t.get("type") == "page"
        ]

    def switch_to_tab(self, tab_id):
        """Switch CDP connection to a different tab by its ID."""
        tabs = self._list_targets() or []
        target = None
        for t in tabs:
            if t.get("id") == tab_id:
                target = t
                break

        if not target or not target.get("webSocketDebuggerUrl"):
            raise RuntimeError(f"Tab not found: {tab_id}")

        # Activate the tab via HTTP endpoint
        try:
            urllib.request.urlopen(
                f"http://localhost:{self.port}/json/activate/{tab_id}", timeout=3
            )
        except Exception:
            pass

        self._connect_ws(target["webSocketDebuggerUrl"])

    def new_tab(self, url="about:blank"):
        """Create a new tab and connect to it. Returns tab info."""
        try:
            encoded = urllib.parse.quote(url, safe=":/?&=#")
            req_url = f"http://localhost:{self.port}/json/new?{encoded}"
            with urllib.request.urlopen(req_url, timeout=5) as r:
                tab = json.loads(r.read())
            ws_url = tab.get("webSocketDebuggerUrl", "")
            if ws_url:
                self._connect_ws(ws_url)
            return tab
        except Exception as e:
            raise RuntimeError(f"Failed to create tab: {e}")

    def close_tab(self, tab_id):
        """Close a tab by its ID."""
        try:
            urllib.request.urlopen(
                f"http://localhost:{self.port}/json/close/{tab_id}", timeout=3
            )
        except Exception:
            pass

    # ─── Properties ────────────────────────────────────

    @property
    def connected(self):
        return self._running and self._ws is not None

    def close(self):
        """Close the websocket connection (does NOT quit Chrome)."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        with self._lock:
            self._responses.clear()
            self._event_queues.clear()
