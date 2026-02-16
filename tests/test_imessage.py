"""
╔══════════════════════════════════════════╗
║     TARS — Test Suite: iMessage           ║
╚══════════════════════════════════════════╝

Tests iMessage reader (dedup, multi-msg, kill detect)
and sender (rate limit, retry, truncation).
Uses mocking — does NOT touch real chat.db.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reader_config():
    return {
        "imessage": {
            "owner_phone": "+10000000000",
            "poll_interval": 0.05,
        }
    }


def _sender_config():
    return {
        "imessage": {
            "owner_phone": "+10000000000",
            "rate_limit": 0,  # No rate limit in tests
            "max_message_length": 200,
        }
    }


class TestIMessageReaderDedup(unittest.TestCase):
    """Test idempotent dedup — same ROWID never processed twice."""

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    @patch("voice.imessage_read.IMessageReader._get_db_connection")
    def test_same_rowid_skipped(self, mock_conn, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())

        # Simulate: two polls return the same ROWID
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1, "hello", 0, 12345)]
        mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=mock_cursor)))
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        msgs1 = reader._get_new_messages()
        msgs2 = reader._get_new_messages()

        self.assertEqual(len(msgs1), 1)
        self.assertEqual(len(msgs2), 0, "Same ROWID should be deduped on second poll")

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_dedup_bounded(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        # Fill the dedup deque
        for i in range(1100):
            reader._seen_rowids.append(i)
        self.assertLessEqual(len(reader._seen_rowids), 1000)


class TestIMessageReaderMultiMsg(unittest.TestCase):
    """Test that multiple messages arriving in one poll are all returned."""

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_wait_for_reply_concatenates(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())

        # Mock _get_new_messages to return 3 messages
        reader._get_new_messages = MagicMock(return_value=[
            {"rowid": 1, "text": "part one", "date": 1},
            {"rowid": 2, "text": "part two", "date": 2},
            {"rowid": 3, "text": "part three", "date": 3},
        ])

        result = reader.wait_for_reply(timeout=1)
        self.assertTrue(result["success"])
        self.assertIn("part one", result["content"])
        self.assertIn("part two", result["content"])
        self.assertIn("part three", result["content"])

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_wait_for_reply_timeout(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        reader._get_new_messages = MagicMock(return_value=[])

        result = reader.wait_for_reply(timeout=0.1)
        self.assertFalse(result["success"])
        self.assertIn("No reply", result["content"])


class TestIMessageReaderKillDetect(unittest.TestCase):
    """Test kill word detection."""

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_kill_word_detected(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        reader._get_new_messages = MagicMock(return_value=[
            {"rowid": 99, "text": "TARS STOP NOW", "date": 1},
        ])
        found, msg = reader.check_for_kill(["stop"])
        self.assertTrue(found)
        self.assertIn("STOP", msg)

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_kill_word_case_insensitive(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        reader._get_new_messages = MagicMock(return_value=[
            {"rowid": 99, "text": "abort mission", "date": 1},
        ])
        found, _ = reader.check_for_kill(["ABORT"])
        self.assertTrue(found)

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_no_kill_word(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        reader._get_new_messages = MagicMock(return_value=[
            {"rowid": 99, "text": "build me a website", "date": 1},
        ])
        found, _ = reader.check_for_kill(["stop", "abort", "kill"])
        self.assertFalse(found)

    @patch("voice.imessage_read.IMessageReader._get_latest_rowid", return_value=0)
    def test_no_messages_no_kill(self, mock_rowid):
        from voice.imessage_read import IMessageReader
        reader = IMessageReader(_reader_config())
        reader._get_new_messages = MagicMock(return_value=[])
        found, _ = reader.check_for_kill(["stop"])
        self.assertFalse(found)


class TestIMessageSender(unittest.TestCase):
    """Test iMessage sender: retry, truncation, rate limiting."""

    @patch("voice.imessage_send.subprocess.run")
    def test_send_success(self, mock_run):
        from voice.imessage_send import IMessageSender
        mock_run.return_value = MagicMock(returncode=0)
        sender = IMessageSender(_sender_config())
        result = sender.send("hello")
        self.assertTrue(result["success"])

    @patch("voice.imessage_send.subprocess.run")
    def test_send_retries_on_failure(self, mock_run):
        """Sender should retry up to 3 times on failure."""
        from voice.imessage_send import IMessageSender
        # Fail first 2, succeed on 3rd
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="busy"),
            MagicMock(returncode=1, stderr="busy"),
            MagicMock(returncode=0),
        ]
        sender = IMessageSender(_sender_config())
        result = sender.send("hello")
        self.assertTrue(result["success"])
        self.assertEqual(mock_run.call_count, 3)

    @patch("voice.imessage_send.subprocess.run")
    def test_send_all_retries_fail(self, mock_run):
        """After 3 failed attempts, return failure."""
        from voice.imessage_send import IMessageSender
        mock_run.return_value = MagicMock(returncode=1, stderr="error msg")
        sender = IMessageSender(_sender_config())
        result = sender.send("hello")
        self.assertFalse(result["success"])
        self.assertIn("3 attempts", result["content"])
        self.assertEqual(mock_run.call_count, 3)

    @patch("voice.imessage_send.subprocess.run")
    def test_send_exception_retries(self, mock_run):
        """Exceptions should trigger retries too."""
        from voice.imessage_send import IMessageSender
        mock_run.side_effect = [
            TimeoutError("osascript hung"),
            MagicMock(returncode=0),
        ]
        sender = IMessageSender(_sender_config())
        result = sender.send("hello")
        self.assertTrue(result["success"])

    @patch("voice.imessage_send.subprocess.run")
    def test_truncation(self, mock_run):
        from voice.imessage_send import IMessageSender
        mock_run.return_value = MagicMock(returncode=0)
        sender = IMessageSender(_sender_config())
        long_msg = "x" * 500
        sender.send(long_msg)
        # The actual message passed to osascript should be truncated
        call_args = mock_run.call_args[0][0]
        actual_msg = call_args[-1]  # last arg is the message
        self.assertLessEqual(len(actual_msg), 200)
        self.assertIn("truncated", actual_msg)

    @patch("voice.imessage_send.subprocess.run")
    def test_rate_limit(self, mock_run):
        from voice.imessage_send import IMessageSender
        config = _sender_config()
        config["imessage"]["rate_limit"] = 0.1  # 100ms rate limit
        mock_run.return_value = MagicMock(returncode=0)
        sender = IMessageSender(config)

        start = time.time()
        sender.send("msg1")
        sender.send("msg2")
        elapsed = time.time() - start

        # Second send should have waited ~100ms
        self.assertGreaterEqual(elapsed, 0.08)


class TestIMessageSenderSecurity(unittest.TestCase):
    """Test that message content is injection-safe."""

    @patch("voice.imessage_send.subprocess.run")
    def test_message_not_in_script(self, mock_run):
        """Message content should be passed via argv, not embedded in script."""
        from voice.imessage_send import IMessageSender
        mock_run.return_value = MagicMock(returncode=0)
        sender = IMessageSender(_sender_config())

        evil_msg = '"; tell application "Finder" to delete every file; "'
        sender.send(evil_msg)

        call_args = mock_run.call_args[0][0]
        # Message should be the last argument, separate from the script
        script = call_args[2]  # -e script
        self.assertNotIn(evil_msg, script, "Message must not be in AppleScript code")
        self.assertEqual(call_args[-1], evil_msg, "Message should be passed as argv")


if __name__ == "__main__":
    unittest.main()
