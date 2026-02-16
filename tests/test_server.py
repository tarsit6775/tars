"""
╔══════════════════════════════════════════╗
║   TARS — Test Suite: Server Auth & WS     ║
╚══════════════════════════════════════════╝

Tests server passphrase enforcement, empty passphrase
rejection, config mutation whitelist, and health endpoint.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server import TARSServer


def _run_async(coro):
    """Run an async function synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _call(server, data, ws):
    """Call _handle_ws_message with the correct (message, websocket) signature."""
    return _run_async(server._handle_ws_message(json.dumps(data), ws))


class TestPassphraseAuth(unittest.TestCase):
    """Test the empty-passphrase auth bypass fix."""

    def _make_server_with_passphrase(self, passphrase):
        server = TARSServer.__new__(TARSServer)
        server.memory = None
        mock_tars = MagicMock()
        mock_tars.config = {"relay": {"passphrase": passphrase}}
        mock_tars._kill_event = MagicMock()
        server.tars = mock_tars
        return server

    def test_empty_passphrase_rejects_send_task(self):
        """Empty passphrase should REJECT tasks, not bypass auth."""
        server = self._make_server_with_passphrase("")
        ws = AsyncMock()

        data = {"type": "send_task", "task": "do something", "passphrase": "anything"}
        _call(server, data, ws)

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("not configured", sent["data"]["message"])

    def test_none_passphrase_rejects(self):
        """None passphrase should also reject."""
        server = self._make_server_with_passphrase(None)
        ws = AsyncMock()

        data = {"type": "send_task", "task": "do something"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("not configured", sent["data"]["message"])

    def test_whitespace_passphrase_rejects(self):
        """Whitespace-only passphrase should reject."""
        server = self._make_server_with_passphrase("   ")
        ws = AsyncMock()

        data = {"type": "send_task", "task": "do something"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("not configured", sent["data"]["message"])

    def test_valid_passphrase_accepted(self):
        """Correct passphrase should be accepted."""
        server = self._make_server_with_passphrase("interstellar")
        ws = AsyncMock()

        # Patch event_bus and thread to prevent side effects
        with patch("server.event_bus"), patch("server.threading"):
            data = {"type": "send_task", "task": "build a website", "passphrase": "interstellar"}
            _call(server, data, ws)

        # If accepted, no error was sent (task was processed)
        if ws.send.called:
            sent = json.loads(ws.send.call_args[0][0])
            self.assertNotEqual(sent.get("type"), "error")

    def test_wrong_passphrase_rejected(self):
        """Wrong passphrase should return unauthorized."""
        server = self._make_server_with_passphrase("interstellar")
        ws = AsyncMock()

        data = {"type": "send_task", "task": "build a website", "passphrase": "wrong"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("Unauthorized", sent["data"]["message"])

    def test_empty_passphrase_rejects_kill(self):
        """Kill with empty passphrase should be rejected too."""
        server = self._make_server_with_passphrase("")
        ws = AsyncMock()

        data = {"type": "kill"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("not configured", sent["data"]["message"])

    def test_kill_wrong_passphrase(self):
        server = self._make_server_with_passphrase("secret123")
        ws = AsyncMock()

        data = {"type": "kill", "passphrase": "wrong"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertIn("Unauthorized", sent["data"]["message"])


class TestConfigMutation(unittest.TestCase):
    """Test config update whitelist enforcement."""

    def _make_server(self):
        server = TARSServer.__new__(TARSServer)
        server.memory = None
        mock_tars = MagicMock()
        mock_tars.config = {
            "agent": {"humor_level": 75},
            "imessage": {"rate_limit": 2, "max_message_length": 1600},
            "safety": {"max_retries": 3},
            "relay": {"passphrase": "secret"},
        }
        server.tars = mock_tars
        return server

    def test_mutable_key_accepted(self):
        server = self._make_server()
        ws = AsyncMock()

        with patch("server.event_bus"):
            data = {"type": "update_config", "key": "agent.humor_level", "value": 50}
            _call(server, data, ws)

        self.assertEqual(server.tars.config["agent"]["humor_level"], 50)

    def test_immutable_key_rejected(self):
        server = self._make_server()
        ws = AsyncMock()

        data = {"type": "update_config", "key": "relay.passphrase", "value": "hacked"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "error")
        self.assertIn("not mutable", sent["data"]["message"])
        # Verify passphrase was NOT changed
        self.assertEqual(server.tars.config["relay"]["passphrase"], "secret")


class TestGetStats(unittest.TestCase):
    """Test get_stats WS message handler."""

    def test_get_stats_returns_stats(self):
        server = TARSServer.__new__(TARSServer)
        server.memory = None
        server.tars = None
        ws = AsyncMock()

        with patch("server.event_bus") as mock_bus:
            mock_bus.get_stats.return_value = {"total_events": 42}
            data = {"type": "get_stats"}
            _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "stats")
        self.assertEqual(sent["data"]["total_events"], 42)


class TestGetMemory(unittest.TestCase):
    """Test get_memory WS message handler."""

    def test_get_memory_returns_data(self):
        server = TARSServer.__new__(TARSServer)
        server.tars = None
        mock_memory = MagicMock()
        mock_memory._read.side_effect = lambda f: "content"
        mock_memory.get_active_project.return_value = "tars"
        server.memory = mock_memory
        ws = AsyncMock()

        data = {"type": "get_memory"}
        _call(server, data, ws)

        sent = json.loads(ws.send.call_args[0][0])
        self.assertEqual(sent["type"], "memory_data")
        self.assertIn("context", sent["data"])
        self.assertEqual(sent["data"]["active_project"], "tars")


if __name__ == "__main__":
    unittest.main()
