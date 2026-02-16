"""
╔══════════════════════════════════════════╗
║     TARS — Test Suite: CDP Connection     ║
╚══════════════════════════════════════════╝

Tests CDP WebSocket connection, recv loop cleanup,
thread leak fix, send/receive, and tab management.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import threading
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from hands.cdp import CDP


class TestCDPRecvLoopCleanup(unittest.TestCase):
    """Test that _recv_loop properly cleans up on crash."""

    def test_recv_loop_exception_cleans_up_ws(self):
        """When _recv_loop hits an exception, it should set _ws to None."""
        cdp = CDP()
        mock_ws = MagicMock()
        mock_ws.recv.side_effect = Exception("connection lost")
        cdp._ws = mock_ws
        cdp._running = True

        # Run the recv loop — it should break and clean up
        cdp._recv_loop()

        self.assertFalse(cdp._running)
        self.assertIsNone(cdp._ws)
        mock_ws.close.assert_called_once()

    def test_recv_loop_connection_closed_cleans_up(self):
        """WebSocketConnectionClosedException should clean up too."""
        import websocket as ws_mod
        cdp = CDP()
        mock_ws = MagicMock()
        mock_ws.recv.side_effect = ws_mod.WebSocketConnectionClosedException()
        cdp._ws = mock_ws
        cdp._running = True

        cdp._recv_loop()

        self.assertFalse(cdp._running)
        self.assertIsNone(cdp._ws)

    def test_recv_loop_close_exception_ignored(self):
        """If ws.close() itself throws, it should be silently ignored."""
        cdp = CDP()
        mock_ws = MagicMock()
        mock_ws.recv.side_effect = Exception("boom")
        mock_ws.close.side_effect = Exception("close also failed")
        cdp._ws = mock_ws
        cdp._running = True

        # Should not raise
        cdp._recv_loop()
        self.assertIsNone(cdp._ws)


class TestCDPRecvLoopRouting(unittest.TestCase):
    """Test that _recv_loop correctly routes responses and events."""

    def test_command_response_stored(self):
        """Responses with 'id' should go into _responses."""
        cdp = CDP()
        mock_ws = MagicMock()
        response_json = json.dumps({"id": 42, "result": {"data": "hello"}})
        mock_ws.recv.side_effect = [response_json, Exception("done")]
        cdp._ws = mock_ws
        cdp._running = True

        cdp._recv_loop()

        self.assertIn(42, cdp._responses)
        self.assertEqual(cdp._responses[42]["result"]["data"], "hello")

    def test_event_stored_in_queue(self):
        """Events with 'method' should go into _event_queues."""
        cdp = CDP()
        mock_ws = MagicMock()
        event_json = json.dumps({"method": "Page.loadEventFired", "params": {"ts": 123}})
        mock_ws.recv.side_effect = [event_json, Exception("done")]
        cdp._ws = mock_ws
        cdp._running = True

        cdp._recv_loop()

        self.assertIn("Page.loadEventFired", cdp._event_queues)
        self.assertEqual(cdp._event_queues["Page.loadEventFired"][0]["ts"], 123)

    def test_event_queue_capped_at_100(self):
        """Event queues should be trimmed when over 100 entries."""
        cdp = CDP()
        mock_ws = MagicMock()
        events = [json.dumps({"method": "Network.data", "params": {"i": i}}) for i in range(120)]
        events.append(None)  # empty recv to trigger continue then we break

        side_effects = []
        for e in events[:120]:
            side_effects.append(e)
        side_effects.append(Exception("done"))
        mock_ws.recv.side_effect = side_effects
        cdp._ws = mock_ws
        cdp._running = True

        cdp._recv_loop()

        q = cdp._event_queues.get("Network.data", [])
        self.assertLessEqual(len(q), 100)

    def test_timeout_exception_continues(self):
        """WebSocketTimeoutException should just continue the loop."""
        import websocket as ws_mod
        cdp = CDP()
        mock_ws = MagicMock()
        mock_ws.recv.side_effect = [
            ws_mod.WebSocketTimeoutException(),
            json.dumps({"id": 1, "result": {}}),
            Exception("done"),
        ]
        cdp._ws = mock_ws
        cdp._running = True

        cdp._recv_loop()

        # The timeout was skipped, and the next message was processed
        self.assertIn(1, cdp._responses)


class TestCDPSend(unittest.TestCase):
    """Test the send method."""

    def test_send_returns_result(self):
        cdp = CDP()
        mock_ws = MagicMock()
        cdp._ws = mock_ws
        cdp._running = True

        # Pre-populate response
        cdp._responses[1] = {"id": 1, "result": {"frameId": "abc"}}

        result = cdp.send("Page.navigate", {"url": "http://example.com"}, timeout=1)
        self.assertEqual(result["frameId"], "abc")

    def test_send_raises_on_error(self):
        cdp = CDP()
        mock_ws = MagicMock()
        cdp._ws = mock_ws
        cdp._running = True

        cdp._responses[1] = {"id": 1, "error": {"message": "target closed"}}

        with self.assertRaises(RuntimeError) as ctx:
            cdp.send("Page.navigate", timeout=1)
        self.assertIn("target closed", str(ctx.exception))

    def test_send_timeout(self):
        cdp = CDP()
        mock_ws = MagicMock()
        cdp._ws = mock_ws
        cdp._running = True
        # No response populated — should timeout
        with self.assertRaises(TimeoutError):
            cdp.send("Page.navigate", timeout=0.1)

    def test_send_not_connected_raises(self):
        cdp = CDP()
        with self.assertRaises(RuntimeError):
            cdp.send("Page.navigate")


class TestCDPClose(unittest.TestCase):
    """Test close() cleanup."""

    def test_close_resets_state(self):
        cdp = CDP()
        mock_ws = MagicMock()
        cdp._ws = mock_ws
        cdp._running = True
        cdp._responses = {1: {}, 2: {}}
        cdp._event_queues = {"Page.loadEventFired": [{}]}

        cdp.close()

        self.assertFalse(cdp._running)
        self.assertIsNone(cdp._ws)
        self.assertEqual(cdp._responses, {})
        self.assertEqual(cdp._event_queues, {})
        mock_ws.close.assert_called_once()

    def test_close_handles_ws_exception(self):
        cdp = CDP()
        mock_ws = MagicMock()
        mock_ws.close.side_effect = Exception("already closed")
        cdp._ws = mock_ws
        cdp._running = True

        # Should not raise
        cdp.close()
        self.assertIsNone(cdp._ws)

    def test_connected_property(self):
        cdp = CDP()
        self.assertFalse(cdp.connected)
        cdp._running = True
        cdp._ws = MagicMock()
        self.assertTrue(cdp.connected)


class TestCDPDrainEvents(unittest.TestCase):
    """Test event drain and wait."""

    def test_drain_returns_and_clears(self):
        cdp = CDP()
        cdp._event_queues["Page.loadEventFired"] = [{"ts": 1}, {"ts": 2}]

        events = cdp.drain_events("Page.loadEventFired")
        self.assertEqual(len(events), 2)
        self.assertNotIn("Page.loadEventFired", cdp._event_queues)

    def test_drain_missing_key(self):
        cdp = CDP()
        events = cdp.drain_events("nonexistent")
        self.assertEqual(events, [])

    def test_wait_event_returns_first(self):
        cdp = CDP()
        cdp._event_queues["evt"] = [{"a": 1}, {"a": 2}]
        result = cdp.wait_event("evt", timeout=0.1)
        self.assertEqual(result["a"], 1)
        self.assertEqual(len(cdp._event_queues["evt"]), 1)

    def test_wait_event_timeout(self):
        cdp = CDP()
        result = cdp.wait_event("nothing", timeout=0.1)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
