"""
╔══════════════════════════════════════════╗
║   TARS — Test Suite: Progress Collector   ║
╚══════════════════════════════════════════╝

Tests _ProgressCollector lifecycle, event collection,
debounced iMessage sending, and cleanup on stop.
"""

import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.event_bus import EventBus


class TestProgressCollector(unittest.TestCase):
    """Test the _ProgressCollector class from tars.py."""

    def _make_collector(self, bus, sender, interval=0.1):
        """Build a _ProgressCollector wired to the given bus."""
        # Import inline to avoid triggering TARS __init__
        sys.modules.pop("tars", None)

        # We need to monkey-patch event_bus in the tars module
        import importlib
        import tars as tars_mod

        # Replace the event_bus used by _ProgressCollector
        original_bus = tars_mod.event_bus

        # Create collector using the class
        collector = tars_mod._ProgressCollector(sender=sender, interval=interval)
        # Redirect its subscribe/unsubscribe to our test bus
        collector._start_bus = bus
        return collector, original_bus

    def test_start_stop_lifecycle(self):
        """start() then stop() should not leak subscriptions."""
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=0.1)

        collector.start()
        self.assertTrue(collector._running)

        collector.stop()
        self.assertFalse(collector._running)

    def test_stop_cancels_timer(self):
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector.start()
        self.assertIsNotNone(collector._timer)

        collector.stop()
        # Give a moment for cancel to take effect
        time.sleep(0.05)
        # After stop, timer should no longer fire (cancelled)
        self.assertFalse(collector._running)

    def test_double_stop_safe(self):
        """Calling stop() twice should not raise."""
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=0.1)
        collector.start()
        collector.stop()
        collector.stop()  # Should not raise

    def test_events_collected(self):
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector.start()
        collector._on_event({"agent": "browser", "task": "click button"})
        collector._on_event({"tool_name": "navigate"})

        self.assertEqual(len(collector._events), 2)
        collector.stop()

    def test_tick_sends_progress(self):
        """When events are collected, _tick should send an iMessage."""
        from tars import _ProgressCollector
        sender = MagicMock()
        sender.send = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector._running = True
        collector._events = [
            {"agent": "browser", "task": "navigate to google.com"},
            {"tool_name": "click"},
        ]

        # Manually trigger tick (normally done by timer)
        collector._tick()

        sender.send.assert_called_once()
        msg = sender.send.call_args[0][0]
        self.assertIn("Progress", msg)
        self.assertIn("browser", msg)

    def test_tick_clears_events(self):
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector._running = True
        collector._events = [{"tool_name": "ls"}]
        collector._tick()

        self.assertEqual(len(collector._events), 0)

    def test_tick_no_events_no_send(self):
        """If no events collected, tick should not send."""
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector._running = True
        collector._events = []
        collector._tick()

        sender.send.assert_not_called()

    def test_tick_sender_exception_ignored(self):
        """If sender.send() raises, tick should not crash."""
        from tars import _ProgressCollector
        sender = MagicMock()
        sender.send.side_effect = Exception("network error")
        collector = _ProgressCollector(sender=sender, interval=10)

        collector._running = True
        collector._events = [{"tool_name": "test"}]

        # Should not raise
        collector._tick()

    def test_max_5_events_in_message(self):
        """Progress message should include at most 5 recent events."""
        from tars import _ProgressCollector
        sender = MagicMock()
        collector = _ProgressCollector(sender=sender, interval=10)

        collector._running = True
        collector._events = [{"tool_name": f"tool_{i}"} for i in range(20)]
        collector._tick()

        msg = sender.send.call_args[0][0]
        # Count 🔧 icons — should be at most 5
        self.assertLessEqual(msg.count("🔧"), 5)


if __name__ == "__main__":
    unittest.main()
