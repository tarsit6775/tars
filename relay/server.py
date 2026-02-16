"""
TARS Cloud Relay Server — Full Control Edition
Deployed to Railway. Bridges the cloud-hosted dashboard
to the TARS agent running on a Mac via WebSocket tunneling.

Architecture:
  [Browser Dashboard] <--wss--> [This Relay] <--wss--> [Mac TARS Agent Tunnel]

Endpoints:
  GET  /              -> Serves the built React dashboard
  GET  /ws            -> Dashboard WebSocket (browser clients)
  GET  /tunnel        -> Mac agent tunnel WebSocket (authenticated)
  POST /api/auth      -> Login with passphrase, get JWT
  GET  /api/health    -> Health check with full status
  GET  /api/status    -> Full TARS status (process, system, tunnel)
  POST /api/command   -> Send a command to TARS (start/stop/kill/task)
"""

import os
import json
import time
import asyncio
import hashlib
import hmac
import logging
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.websockets import WebSocketState

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("relay")

# ── Config ──────────────────────────────────────────
RELAY_TOKEN = os.environ.get("TARS_RELAY_TOKEN", "tars-default-token-change-me")
PASSPHRASE = os.environ.get("TARS_PASSPHRASE", "interstellar")
JWT_SECRET = os.environ.get("TARS_JWT_SECRET", RELAY_TOKEN + "-jwt")
PORT = int(os.environ.get("PORT", 8420))
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TARS Relay", docs_url=None, redoc_url=None)


# ── Simple JWT ──────────────────────────────────────
def create_token(payload: dict, expires_hours: int = 24) -> str:
    payload["exp"] = (datetime.utcnow() + timedelta(hours=expires_hours)).timestamp()
    data = json.dumps(payload, sort_keys=True).encode()
    sig = hmac.new(JWT_SECRET.encode(), data, hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(data).decode() + "." + sig

def verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        data = base64.urlsafe_b64decode(parts[0])
        expected_sig = hmac.new(JWT_SECRET.encode(), data, hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(parts[1], expected_sig):
            return None
        payload = json.loads(data)
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            return None
        return payload
    except Exception:
        return None

def verify_api_token(request: Request) -> dict:
    """Verify JWT from Authorization header for REST endpoints."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        payload = verify_token(token)
        if payload:
            return payload
    # Also check query param
    token = request.query_params.get("token", "")
    if token:
        payload = verify_token(token)
        if payload:
            return payload
    raise HTTPException(status_code=401, detail="Unauthorized")


# ── State ───────────────────────────────────────────
class RelayState:
    def __init__(self):
        self.dashboard_clients: List[WebSocket] = []
        self.tunnel: Optional[WebSocket] = None
        self.tunnel_connected_at: Optional[float] = None
        self.event_history: List[dict] = []
        self.max_history = 500
        self.lock = asyncio.Lock()
        self.start_time = time.time()
        # TARS process state (reported by tunnel)
        self.tars_process: Dict = {
            "running": False,
            "pid": None,
            "started_at": None,
            "status": "stopped",  # stopped, starting, running, error
            "last_task": None,
            "uptime": 0,
        }
        # Output log (last N lines from TARS stdout/stderr)
        self.output_log: List[dict] = []
        self.max_output_log = 500
        # Pending command responses
        self._pending_commands: Dict[str, asyncio.Future] = {}

    async def add_dashboard(self, ws: WebSocket):
        async with self.lock:
            self.dashboard_clients.append(ws)
            logger.info(f"Dashboard client connected ({len(self.dashboard_clients)} total)")

    async def remove_dashboard(self, ws: WebSocket):
        async with self.lock:
            if ws in self.dashboard_clients:
                self.dashboard_clients.remove(ws)
                logger.info(f"Dashboard client disconnected ({len(self.dashboard_clients)} total)")

    async def broadcast_to_dashboards(self, message: str):
        async with self.lock:
            dead = []
            for ws in self.dashboard_clients:
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.dashboard_clients.remove(ws)

    def add_event(self, event: dict):
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history = self.event_history[-self.max_history:]

    def add_output(self, line: dict):
        self.output_log.append(line)
        if len(self.output_log) > self.max_output_log:
            self.output_log = self.output_log[-self.max_output_log:]

    async def send_to_tunnel(self, message: str) -> bool:
        if self.tunnel and self.tunnel.client_state == WebSocketState.CONNECTED:
            try:
                await self.tunnel.send_text(message)
                return True
            except Exception:
                self.tunnel = None
                return False
        return False

    async def send_command_to_tunnel(self, command: dict, timeout: float = 10.0) -> dict:
        """Send a command to tunnel and wait for response."""
        import uuid
        cmd_id = str(uuid.uuid4())[:8]
        command["cmd_id"] = cmd_id
        msg = json.dumps(command)

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_commands[cmd_id] = future

        sent = await self.send_to_tunnel(msg)
        if not sent:
            self._pending_commands.pop(cmd_id, None)
            return {"error": "Tunnel not connected", "success": False}

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_commands.pop(cmd_id, None)
            return {"error": "Command timed out", "success": False}

    def resolve_command(self, cmd_id: str, result: dict):
        """Resolve a pending command future."""
        future = self._pending_commands.pop(cmd_id, None)
        if future and not future.done():
            future.set_result(result)


state = RelayState()


# ── Auth Endpoint ───────────────────────────────────
@app.post("/api/auth")
async def auth(request: Request):
    body = await request.json()
    passphrase = body.get("passphrase", "")
    if passphrase == PASSPHRASE:
        token = create_token({"sub": "dashboard", "iat": time.time()})
        return JSONResponse({"token": token})
    raise HTTPException(status_code=401, detail="Invalid passphrase")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "tunnel_connected": state.tunnel is not None,
        "tunnel_uptime": (time.time() - state.tunnel_connected_at) if state.tunnel_connected_at and state.tunnel else 0,
        "dashboard_clients": len(state.dashboard_clients),
        "events_buffered": len(state.event_history),
        "relay_uptime": time.time() - state.start_time,
        "tars_process": state.tars_process,
    }


@app.get("/api/status")
async def full_status():
    """Full TARS system status — requires auth in production."""
    return {
        "relay": {
            "uptime": time.time() - state.start_time,
            "events_buffered": len(state.event_history),
            "output_lines": len(state.output_log),
        },
        "tunnel": {
            "connected": state.tunnel is not None,
            "connected_at": state.tunnel_connected_at,
            "uptime": (time.time() - state.tunnel_connected_at) if state.tunnel_connected_at and state.tunnel else 0,
        },
        "tars": state.tars_process,
        "dashboard": {
            "clients": len(state.dashboard_clients),
        },
    }


@app.post("/api/command")
async def send_command(request: Request):
    """Send a control command to the Mac agent via tunnel."""
    # Auth check
    auth_header = request.headers.get("Authorization", "")
    token_param = request.query_params.get("token", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else token_param

    if RELAY_TOKEN != "tars-default-token-change-me":
        if not token or not verify_token(token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    cmd_type = body.get("command", "")

    if cmd_type not in ("start_tars", "stop_tars", "kill_tars", "restart_tars", "get_process_status", "send_task", "send_message"):
        raise HTTPException(status_code=400, detail=f"Unknown command: {cmd_type}")

    if not state.tunnel:
        raise HTTPException(status_code=503, detail="Mac agent tunnel not connected")

    result = await state.send_command_to_tunnel({
        "type": "control_command",
        "command": cmd_type,
        "data": body.get("data", {}),
    })
    return JSONResponse(result)


@app.get("/api/output")
async def get_output(lines: int = 100):
    """Get recent TARS console output."""
    return {"output": state.output_log[-lines:]}


# ── Dashboard WebSocket ────────────────────────────
@app.websocket("/ws")
async def dashboard_ws(ws: WebSocket):
    # Auth check via query param
    token = ws.query_params.get("token", "")
    # In local dev mode (no TARS_RELAY_TOKEN env set), skip auth
    if RELAY_TOKEN != "tars-default-token-change-me":
        if not token or not verify_token(token):
            await ws.close(code=4001, reason="Unauthorized")
            return

    await ws.accept()
    await state.add_dashboard(ws)

    # Send event history
    for event in state.event_history:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            break

    # Send tunnel status
    tunnel_status = {
        "type": "tunnel_status",
        "timestamp": datetime.utcnow().isoformat(),
        "ts_unix": time.time(),
        "data": {"connected": state.tunnel is not None},
    }
    try:
        await ws.send_text(json.dumps(tunnel_status))
    except Exception:
        pass

    # Send TARS process status
    process_status = {
        "type": "tars_process_status",
        "timestamp": datetime.utcnow().isoformat(),
        "ts_unix": time.time(),
        "data": state.tars_process,
    }
    try:
        await ws.send_text(json.dumps(process_status))
    except Exception:
        pass

    # Send recent output
    if state.output_log:
        output_event = {
            "type": "tars_output_batch",
            "timestamp": datetime.utcnow().isoformat(),
            "ts_unix": time.time(),
            "data": {"lines": state.output_log[-200:]},
        }
        try:
            await ws.send_text(json.dumps(output_event))
        except Exception:
            pass

    try:
        while True:
            message = await ws.receive_text()

            if message == "ping":
                await ws.send_text("pong")
                continue

            # Parse the message to handle control commands specially
            try:
                msg_data = json.loads(message)
                msg_type = msg_data.get("type", "")

                # Control commands that need responses
                if msg_type == "control_command":
                    result = await state.send_command_to_tunnel(msg_data)
                    await ws.send_text(json.dumps({
                        "type": "command_response",
                        "timestamp": datetime.utcnow().isoformat(),
                        "ts_unix": time.time(),
                        "data": result,
                    }))
                    continue

                # Request process status
                if msg_type == "get_process_status":
                    await ws.send_text(json.dumps({
                        "type": "tars_process_status",
                        "timestamp": datetime.utcnow().isoformat(),
                        "ts_unix": time.time(),
                        "data": state.tars_process,
                    }))
                    continue

                # Request output log
                if msg_type == "get_output":
                    lines = msg_data.get("lines", 200)
                    await ws.send_text(json.dumps({
                        "type": "tars_output_batch",
                        "timestamp": datetime.utcnow().isoformat(),
                        "ts_unix": time.time(),
                        "data": {"lines": state.output_log[-lines:]},
                    }))
                    continue

            except json.JSONDecodeError:
                pass

            # Forward commands from dashboard to the Mac tunnel
            forwarded = await state.send_to_tunnel(message)
            if not forwarded:
                # No tunnel -- send error back
                err = {
                    "type": "error",
                    "timestamp": datetime.utcnow().isoformat(),
                    "ts_unix": time.time(),
                    "data": {"message": "Mac agent not connected. Start the tunnel on your Mac."},
                }
                await ws.send_text(json.dumps(err))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Dashboard WS error: {e}")
    finally:
        await state.remove_dashboard(ws)


# ── Tunnel WebSocket (Mac Agent) ───────────────────
@app.websocket("/tunnel")
async def tunnel_ws(ws: WebSocket):
    # Authenticate the tunnel connection
    token = ws.query_params.get("token", "")
    if token != RELAY_TOKEN:
        await ws.close(code=4001, reason="Invalid tunnel token")
        return

    await ws.accept()
    state.tunnel = ws
    state.tunnel_connected_at = time.time()
    logger.info("Mac tunnel connected")

    # Notify dashboards
    event = {
        "type": "tunnel_status",
        "timestamp": datetime.utcnow().isoformat(),
        "ts_unix": time.time(),
        "data": {"connected": True},
    }
    await state.broadcast_to_dashboards(json.dumps(event))

    try:
        while True:
            message = await ws.receive_text()

            if message == "ping":
                await ws.send_text("pong")
                continue

            # Parse and handle different message types from tunnel
            try:
                event_data = json.loads(message)
                msg_type = event_data.get("type", "")

                # Command response from tunnel
                if msg_type == "command_response":
                    cmd_id = event_data.get("cmd_id", "")
                    if cmd_id:
                        state.resolve_command(cmd_id, event_data.get("data", {}))
                    continue

                # TARS process status update
                if msg_type == "tars_process_status":
                    state.tars_process = event_data.get("data", state.tars_process)
                    await state.broadcast_to_dashboards(message)
                    continue

                # TARS console output
                if msg_type == "tars_output":
                    line = event_data.get("data", {})
                    state.add_output(line)
                    await state.broadcast_to_dashboards(message)
                    continue

                # Regular event — store and broadcast
                state.add_event(event_data)

            except json.JSONDecodeError:
                pass

            await state.broadcast_to_dashboards(message)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Tunnel WS error: {e}")
    finally:
        state.tunnel = None
        state.tars_process["running"] = False
        state.tars_process["status"] = "unknown"
        logger.info("Mac tunnel disconnected")
        # Notify dashboards
        event = {
            "type": "tunnel_status",
            "timestamp": datetime.utcnow().isoformat(),
            "ts_unix": time.time(),
            "data": {"connected": False},
        }
        await state.broadcast_to_dashboards(json.dumps(event))
        # Also send process status
        proc_event = {
            "type": "tars_process_status",
            "timestamp": datetime.utcnow().isoformat(),
            "ts_unix": time.time(),
            "data": state.tars_process,
        }
        await state.broadcast_to_dashboards(json.dumps(proc_event))


# ── Serve Static Dashboard ─────────────────────────
# Mount static files if the dist directory exists
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Try to serve the file directly
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Fallback to index.html for SPA routing
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def no_dashboard():
        return JSONResponse({
            "status": "relay running",
            "dashboard": "not built yet -- run `npm run build` in dashboard/ and copy dist/ to relay/static/",
            "tunnel_connected": state.tunnel is not None,
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
