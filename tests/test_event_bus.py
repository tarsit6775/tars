"""
╔══════════════════════════════════════════╗
║     TARS — Test Suite: Event Bus          ║
╚══════════════════════════════════════════╝

Tests event emission, sync subscribers, stats tracking,
history bounded deque, and thread safety.
"""

import unittest
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.event_bus import EventBus


class TestEventEmission(unittest.TestCase):
    """Test basic event emission and sync subscribers."""

    def setUp(self):
        self.bus = EventBus(max_history=100)

    def test_emit_stores_in_history(self):
        self.bus.emit("test_event", {"key": "value"})
        history = self.bus.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["type"], "test_event")
        self.assertEqual(history[0]["data"]["key"], "value")

    def test_emit_increments_total_events(self):
        self.bus.emit("a")
        self.bus.emit("b")
        self.bus.emit("c")
        self.assertEqual(self.bus._stats["total_events"], 3)

    def test_history_bounded(self):
        bus = EventBus(max_history=5)
        for i in range(20):
            bus.emit(f"event_{i}")
        history = bus.get_history()
        self.assertEqual(len(history), 5)
        # Oldest events should be gone, newest present
        self.assertEqual(history[0]["type"], "event_15")
        self.assertEqual(history[-1]["type"], "event_19")

    def test_sync_subscriber_called(self):
        received = []
        self.bus.subscribe_sync("test_event", lambda data: received.append(data))
        self.bus.emit("test_event", {"msg": "hello"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["msg"], "hello")

    def test_sync_subscriber_only_for_matching_type(self):
        received = []
        self.bus.subscribe_sync("type_a", lambda data: received.append(data))
        self.bus.emit("type_b", {"msg": "wrong"})
        self.assertEqual(len(received), 0)

    def test_unsubscribe_sync(self):
        received = []
        cb = lambda data: received.append(data)
        self.bus.subscribe_sync("test", cb)
        self.bus.emit("test", {"x": 1})
        self.bus.unsubscribe_sync("test", cb)
        self.bus.emit("test", {"x": 2})
        self.assertEqual(len(received), 1)  # Only the first event

    def test_multiple_sync_subscribers(self):
        results_a = []
        results_b = []
        self.bus.subscribe_sync("evt", lambda d: results_a.append(d))
        self.bus.subscribe_sync("evt", lambda d: results_b.append(d))
        self.bus.emit("evt", {"v": 42})
        self.assertEqual(len(results_a), 1)
        self.assertEqual(len(results_b), 1)

    def test_sync_subscriber_exception_does_not_crash(self):
        """A failing subscriber should not prevent other subscribers or crash emit."""
        def bad_callback(data):
            raise ValueError("boom")

        received = []
        self.bus.subscribe_sync("evt", bad_callback)
        self.bus.subscribe_sync("evt", lambda d: received.append(d))
        self.bus.emit("evt", {"x": 1})
        # The good subscriber should still run
        self.assertEqual(len(received), 1)

    def test_emit_with_no_data(self):
        self.bus.emit("empty_event")
        history = self.bus.get_history()
        self.assertEqual(history[0]["data"], {})


class TestStats(unittest.TestCase):
    """Test statistics tracking."""

    def setUp(self):
        self.bus = EventBus()

    def test_tool_result_success(self):
        self.bus.emit("tool_result", {"success": True, "tool_name": "ls"})
        self.assertEqual(self.bus._stats["actions_success"], 1)
        self.assertEqual(self.bus._stats["tool_usage"]["ls"], 1)

    def test_tool_result_failure(self):
        self.bus.emit("tool_result", {"success": False, "tool_name": "rm"})
        self.assertEqual(self.bus._stats["actions_failed"], 1)

    def test_api_call_tokens(self):
        self.bus.emit("api_call", {
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "gemini-2.5-flash",
        })
        self.assertEqual(self.bus._stats["total_tokens_in"], 100)
        self.assertEqual(self.bus._stats["total_tokens_out"], 50)
        self.assertEqual(self.bus._stats["total_cost"], 0.0)  # Gemini is free

    def test_api_call_paid_model_costs(self):
        self.bus.emit("api_call", {
            "tokens_in": 1000,
            "tokens_out": 500,
            "model": "claude-3-sonnet",
        })
        self.assertGreater(self.bus._stats["total_cost"], 0)

    def test_model_usage_counted(self):
        self.bus.emit("api_call", {"tokens_in": 10, "tokens_out": 5, "model": "llama-3.3-70b"})
        self.bus.emit("api_call", {"tokens_in": 10, "tokens_out": 5, "model": "llama-3.3-70b"})
        self.assertEqual(self.bus._stats["model_usage"]["llama-3.3-70b"], 2)

    def test_get_stats_includes_uptime(self):
        stats = self.bus.get_stats()
        self.assertIn("uptime_seconds", stats)
        self.assertGreaterEqual(stats["uptime_seconds"], 0)


class TestThreadSafety(unittest.TestCase):
    """Test concurrent event emission from multiple threads."""

    def test_concurrent_emit(self):
        bus = EventBus(max_history=10000)
        errors = []

        def emitter(n):
            try:
                for i in range(100):
                    bus.emit(f"thread_{n}", {"i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emitter, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(bus._stats["total_events"], 1000)

    def test_concurrent_subscribe_unsubscribe(self):
        bus = EventBus()
        errors = []

        def sub_unsub(n):
            try:
                cb = lambda d: None
                for _ in range(50):
                    bus.subscribe_sync(f"type_{n}", cb)
                    bus.emit(f"type_{n}", {"x": 1})
                    bus.unsubscribe_sync(f"type_{n}", cb)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=sub_unsub, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
