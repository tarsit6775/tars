"""
╔══════════════════════════════════════════╗
║       TARS — Event Bus                   ║
╚══════════════════════════════════════════╝

Central event system. Every action, thought,
and message flows through here to the dashboard.
"""

import json
import time
import asyncio
import threading
from datetime import datetime
from collections import deque


class EventBus:
    """Central event bus — all TARS events flow through here."""

    def __init__(self, max_history=500):
        self.subscribers = []          # WebSocket clients (async)
        self._sub_lock = threading.Lock()  # Thread-safe subscriber management
        self._sync_subs = {}           # event_type → [callable] for sync listeners
        self._sync_lock = threading.Lock()
        self.history = deque(maxlen=max_history)  # Recent events for new clients
        self._loop = None
        self._stats = {
            "total_events": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost": 0.0,
            "actions_success": 0,
            "actions_failed": 0,
            "start_time": time.time(),
            "tool_usage": {},
            "model_usage": {},
        }

    def set_loop(self, loop):
        self._loop = loop

    @property
    def stats(self):
        return self._stats

    def emit(self, event_type, data=None):
        """Emit an event to all subscribers and history."""
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "ts_unix": time.time(),
            "data": data or {},
        }

        # Update stats
        self._stats["total_events"] += 1
        self._update_stats(event_type, data or {})

        # Store in history
        self.history.append(event)

        # Send to all WebSocket subscribers (thread-safe)
        message = json.dumps(event)
        dead = []
        with self._sub_lock:
            for ws_send in self.subscribers:
                try:
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(ws_send(message), self._loop)
                except Exception:
                    dead.append(ws_send)
            for d in dead:
                self.subscribers.remove(d)

        # Notify synchronous listeners (for in-process progress tracking)
        with self._sync_lock:
            for cb in self._sync_subs.get(event_type, []):
                try:
                    cb(data or {})
                except Exception:
                    pass

    def _update_stats(self, event_type, data):
        """Update running statistics."""
        if event_type == "tool_result":
            if data.get("success"):
                self._stats["actions_success"] += 1
            else:
                self._stats["actions_failed"] += 1
            tool = data.get("tool_name", "unknown")
            self._stats["tool_usage"][tool] = self._stats["tool_usage"].get(tool, 0) + 1

        elif event_type == "api_call":
            tokens_in = data.get("tokens_in", 0)
            tokens_out = data.get("tokens_out", 0)
            model = data.get("model", "unknown")
            self._stats["total_tokens_in"] += tokens_in
            self._stats["total_tokens_out"] += tokens_out
            self._stats["model_usage"][model] = self._stats["model_usage"].get(model, 0) + 1

            # Estimate cost (most providers are free or near-free)
            model_lower = model.lower()
            if "gemini" in model_lower or "llama" in model_lower:
                cost = 0.0  # Gemini Flash and Groq Llama are free
            elif "haiku" in model_lower:
                cost = (tokens_in * 0.80 + tokens_out * 4.00) / 1_000_000
            elif "claude" in model_lower or "sonnet" in model_lower or "opus" in model_lower:
                cost = (tokens_in * 3.00 + tokens_out * 15.00) / 1_000_000
            elif "gpt-4" in model_lower:
                cost = (tokens_in * 10.00 + tokens_out * 30.00) / 1_000_000
            else:
                cost = 0.0  # Default free for unknown models
            self._stats["total_cost"] += cost

    def subscribe(self, ws_send):
        """Add a WebSocket client."""
        with self._sub_lock:
            self.subscribers.append(ws_send)

    def unsubscribe(self, ws_send):
        """Remove a WebSocket client."""
        with self._sub_lock:
            if ws_send in self.subscribers:
                self.subscribers.remove(ws_send)

    def subscribe_sync(self, event_type, callback):
        """Subscribe a synchronous callback to a specific event type.
        
        Used by in-process listeners (e.g., progress streaming to iMessage).
        The callback receives the event data dict and runs on the emitting thread.
        """
        with self._sync_lock:
            self._sync_subs.setdefault(event_type, []).append(callback)

    def unsubscribe_sync(self, event_type, callback):
        """Remove a synchronous callback."""
        with self._sync_lock:
            listeners = self._sync_subs.get(event_type, [])
            if callback in listeners:
                listeners.remove(callback)

    def get_history(self):
        """Get all stored events for new clients."""
        return list(self.history)

    def get_stats(self):
        """Get current stats snapshot."""
        stats = dict(self._stats)
        stats["uptime_seconds"] = time.time() - stats["start_time"]
        return stats


# Singleton
event_bus = EventBus()
