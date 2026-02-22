"""
╔══════════════════════════════════════════╗
║       TARS — Dashboard Server            ║
╚══════════════════════════════════════════╝

WebSocket server for real-time events +
HTTP server to serve the dashboard UI.
Runs on localhost:8420
"""

import asyncio
import json
import os
import threading
import time
import mimetypes
import secrets
from http.server import HTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs
import websockets

from utils.event_bus import event_bus
from utils.agent_monitor import agent_monitor

# Prefer built Vite output (dashboard/dist/), fall back to dashboard/ root
_base = os.path.dirname(os.path.abspath(__file__))
_dist = os.path.join(_base, "dashboard", "dist")
DASHBOARD_DIR = _dist if os.path.isdir(_dist) else os.path.join(_base, "dashboard")
WS_PORT = 8421
HTTP_PORT = 8420


class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    """Serve dashboard static files + /api/health endpoint."""

    # Class-level reference so the handler can reach the server instance
    _server_ref = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_GET(self):
        """Handle GET — serve /api/health or fall through to static files."""
        if self.path == "/api/health":
            self._handle_health()
            return

        # Auth check — require valid token via query param or cookie
        if not self._check_auth():
            self.send_response(401)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>401 Unauthorized</h2><p>Add <code>?token=YOUR_TOKEN</code> to the URL. Check the TARS console for the token.</p>")
            return

        # If token is in query param, set it as a cookie so future requests work
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if "token" in qs:
            # Redirect to clean URL after setting cookie
            self.send_response(302)
            self.send_header("Set-Cookie", f"tars_token={qs['token'][0]}; Path=/; HttpOnly; SameSite=Strict")
            clean_path = parsed.path or "/"
            self.send_header("Location", clean_path)
            self.end_headers()
            return

        super().do_GET()

    def _check_auth(self):
        """Validate session token from query param or cookie."""
        expected = TARSServer._session_token
        if not expected:
            return True  # No token configured — allow all

        # Check query param
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("token", [None])[0] == expected:
            return True

        # Check cookie
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            cookies = SimpleCookie()
            try:
                cookies.load(cookie_header)
                if cookies.get("tars_token") and cookies["tars_token"].value == expected:
                    return True
            except Exception:
                pass

        return False

    def _handle_health(self):
        """Return JSON health status: uptime, agents, queue, memory."""
        import resource
        try:
            uptime = 0
            if DashboardHTTPHandler._server_ref:
                uptime = time.time() - DashboardHTTPHandler._server_ref._boot_time
            agents = agent_monitor.get_dashboard_data()
            stats = event_bus.get_stats()

            # Queue depth (if tars instance available)
            queue_depth = 0
            last_msg_time = None
            if DashboardHTTPHandler._server_ref and DashboardHTTPHandler._server_ref.tars:
                tars = DashboardHTTPHandler._server_ref.tars
                queue_depth = tars._task_queue.qsize()
                brain = getattr(tars, 'brain', None)
                if brain:
                    last_msg_time = getattr(brain, '_last_message_time', None)

            # Memory usage (RSS in MB)
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS returns bytes, Linux returns KB
            rss_mb = rss_kb / (1024 * 1024) if rss_kb > 1_000_000 else rss_kb / 1024

            health = {
                "status": "healthy",
                "uptime_seconds": round(uptime, 1),
                "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
                "queue_depth": queue_depth,
                "last_message_time": last_msg_time,
                "memory_rss_mb": round(rss_mb, 1),
                "agents": agents,
                "api_stats": stats,
            }

            payload = json.dumps(health, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            err = json.dumps({"status": "error", "message": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)


class TARSServer:
    """Runs the dashboard HTTP server + WebSocket server."""

    _session_token = None  # Set on first start, printed to console

    def __init__(self, memory_manager=None, tars_instance=None):
        self.memory = memory_manager
        self.tars = tars_instance
        self._ws_loop = None
        self._thread = None
        self._boot_time = time.time()  # Reset on each restart for accurate uptime

        # Generate a random session token for localhost auth
        # This prevents other users on the same Mac from accessing the dashboard
        if TARSServer._session_token is None:
            TARSServer._session_token = secrets.token_urlsafe(24)

    def start(self):
        """Start both servers in a background thread."""
        DashboardHTTPHandler._server_ref = self  # Wire the server ref for /api/health
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        # Print the session token so the user can access the dashboard
        print(f"\n  🔑 Dashboard token: \033[33m{TARSServer._session_token}\033[0m")
        print(f"  🌐 Open: \033[36mhttp://localhost:{HTTP_PORT}?token={TARSServer._session_token}\033[0m\n")

        # Write token to a known file so CLI tools (test runners, scripts) can auto-connect
        try:
            token_path = os.path.join(os.path.dirname(__file__), ".dashboard_token")
            with open(token_path, "w") as f:
                f.write(TARSServer._session_token)
        except Exception:
            pass

    def _run(self):
        """Run the async event loop for WebSocket + HTTP."""
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        event_bus.set_loop(self._ws_loop)

        # Start HTTP server in a sub-thread
        http_thread = threading.Thread(target=self._run_http, daemon=True)
        http_thread.start()

        # Start WebSocket server
        self._ws_loop.run_until_complete(self._run_ws())

    def _run_http(self):
        """Run HTTP server for dashboard static files."""
        server = HTTPServer(("127.0.0.1", HTTP_PORT), DashboardHTTPHandler)
        server.serve_forever()

    async def _run_ws(self):
        """Run WebSocket server for real-time events."""
        async def handler(websocket, path=None):
            # Auth check — require token in query param or first message
            # WebSocket URL: ws://localhost:8421?token=xxx
            # websockets v15: use websocket.request.path
            # websockets v10-11 (legacy): use websocket.path
            request_path = ''
            if hasattr(websocket, 'request') and hasattr(websocket.request, 'path'):
                request_path = websocket.request.path or ''
            elif hasattr(websocket, 'path'):
                request_path = websocket.path or ''
            parsed = urlparse(request_path)
            qs = parse_qs(parsed.query)
            token = qs.get("token", [None])[0]

            # Also check cookies from the HTTP upgrade request
            if not token:
                cookies_header = ''
                if hasattr(websocket, 'request_headers'):
                    cookies_header = websocket.request_headers.get('Cookie', '')
                elif hasattr(websocket, 'request') and hasattr(websocket.request, 'headers'):
                    cookies_header = str(websocket.request.headers.get('Cookie', ''))
                if cookies_header:
                    cookies = SimpleCookie()
                    try:
                        cookies.load(cookies_header)
                        if cookies.get("tars_token"):
                            token = cookies["tars_token"].value
                    except Exception:
                        pass

            expected = TARSServer._session_token
            if expected and token != expected:
                await websocket.close(4001, "Unauthorized — invalid session token")
                return

            # Send recent history to new client (cap at 100 to avoid blocking on slow connections)
            history = event_bus.get_history()
            for event in history[-100:]:
                try:
                    await websocket.send(json.dumps(event))
                except Exception:
                    return

            # Subscribe for new events
            event_bus.subscribe(websocket.send)
            try:
                async for message in websocket:
                    await self._handle_ws_message(message, websocket)
            except websockets.exceptions.ConnectionClosed:
                pass
            finally:
                event_bus.unsubscribe(websocket.send)

        async with websockets.serve(handler, "127.0.0.1", WS_PORT):
            await asyncio.Future()  # Run forever

    async def _handle_ws_message(self, message, websocket):
        """Handle incoming WebSocket messages from the dashboard."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "get_stats":
                stats = event_bus.get_stats()
                await websocket.send(json.dumps({"type": "stats", "data": stats}))

            elif msg_type == "get_memory":
                if self.memory:
                    mem_data = {
                        "context": self.memory._read(self.memory.context_file),
                        "preferences": self.memory._read(self.memory.preferences_file),
                        "active_project": self.memory.get_active_project(),
                    }
                    await websocket.send(json.dumps({"type": "memory_data", "data": mem_data}))

            elif msg_type == "save_memory":
                if self.memory:
                    field = data.get("field", "")
                    content = data.get("content", "")
                    if field == "context":
                        self.memory.update_context(content)
                    elif field == "preferences":
                        self.memory.update_preferences(content)
                    await websocket.send(json.dumps({"type": "memory_saved", "data": {"field": field}}))

            elif msg_type == "send_task":
                task = data.get("task", "")
                if task and self.tars:
                    # Check if connection is from localhost (tunnel) — skip passphrase
                    remote = websocket.remote_address if hasattr(websocket, 'remote_address') else None
                    is_local = remote and remote[0] in ("127.0.0.1", "::1", "localhost")
                    if not is_local:
                        # Remote connections require passphrase
                        expected = (self.tars.config.get("relay", {}).get("passphrase") or "").strip()
                        if not expected:
                            await websocket.send(json.dumps({"type": "error", "data": {"message": "Rejected: relay passphrase not configured"}}))
                            return
                        if data.get("passphrase") != expected:
                            await websocket.send(json.dumps({"type": "error", "data": {"message": "Unauthorized: invalid passphrase"}}))
                            return
                    event_bus.emit("task_received", {"task": task, "source": "dashboard"})
                    # Process in a thread so we don't block
                    threading.Thread(target=self.tars._process_task, args=(task,), daemon=True).start()

            elif msg_type == "send_message":
                # Dashboard chat message — mirror of iMessage.
                # Push into the reader's dashboard queue so the main loop
                # picks it up via wait_for_reply() — exactly like an iMessage.
                # The main loop then feeds it through the message parser.
                # This single-path design prevents double-processing.
                message = data.get("message", "")
                if message and self.tars:
                    # Remote connections require passphrase (same gate as send_task)
                    remote = websocket.remote_address if hasattr(websocket, 'remote_address') else None
                    is_local = remote and remote[0] in ("127.0.0.1", "::1", "localhost")
                    if not is_local:
                        expected = (self.tars.config.get("relay", {}).get("passphrase") or "").strip()
                        if not expected:
                            await websocket.send(json.dumps({"type": "error", "data": {"message": "Rejected: relay passphrase not configured"}}))
                            return
                        if data.get("passphrase") != expected:
                            await websocket.send(json.dumps({"type": "error", "data": {"message": "Unauthorized: invalid passphrase"}}))
                            return

                    # Emit event so dashboard sees it as an incoming user message
                    event_bus.emit("imessage_received", {"message": message, "source": "dashboard"})

                    # Push into the reader's dashboard queue (for wait_for_reply)
                    self.tars.imessage_reader.push_dashboard_message(message)

            elif msg_type == "get_agents":
                agent_data = agent_monitor.get_dashboard_data()
                await websocket.send(json.dumps({"type": "agent_status", "data": agent_data}))

            elif msg_type == "kill":
                if not self.tars:
                    await websocket.send(json.dumps({"type": "error", "data": {"message": "TARS instance not available"}}))
                    return
                # Require passphrase for kill from dashboard
                expected = (self.tars.config.get("relay", {}).get("passphrase") or "").strip()
                if not expected:
                    await websocket.send(json.dumps({"type": "error", "data": {"message": "Rejected: relay passphrase not configured"}}))
                    return
                if data.get("passphrase") != expected:
                    await websocket.send(json.dumps({"type": "error", "data": {"message": "Unauthorized: invalid passphrase"}}))
                    return
                event_bus.emit("kill_switch", {"source": "dashboard"})
                if self.tars:
                    self.tars._kill_event.set()
                    self.tars.running = False

            elif msg_type == "update_config":
                key = data.get("key", "")
                value = data.get("value")
                # Whitelist: only allow safe config mutations
                MUTABLE_KEYS = {
                    "agent.humor_level", "imessage.rate_limit",
                    "imessage.max_message_length", "safety.max_retries",
                }
                if self.tars and key and key in MUTABLE_KEYS:
                    keys = key.split(".")
                    cfg = self.tars.config
                    for k in keys[:-1]:
                        cfg = cfg[k]
                    cfg[keys[-1]] = value
                    event_bus.emit("config_updated", {"key": key, "value": value})
                elif key not in MUTABLE_KEYS:
                    await websocket.send(json.dumps({"type": "error", "data": {"message": f"Config key '{key}' is not mutable from dashboard"}}))

        except Exception as e:
            # Sanitize: don't leak internal errors to remote connections
            remote = websocket.remote_address if hasattr(websocket, 'remote_address') else None
            is_local = remote and remote[0] in ("127.0.0.1", "::1", "localhost")
            err_msg = str(e) if is_local else "Internal server error"
            await websocket.send(json.dumps({"type": "error", "data": {"message": err_msg}}))
