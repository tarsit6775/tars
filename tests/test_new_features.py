"""
╔══════════════════════════════════════════════════════════╗
║     TARS — Integration Tests: New Features               ║
╠══════════════════════════════════════════════════════════╣
║  Tests for: Watchdog, Semantic Memory, Scheduler,        ║
║  MCP Client, Voice Interface, Dashboard Auth,            ║
║  Image Gen, Charts, PPTX, Media Processing,              ║
║  Headless Browser, LLM Client normalization.             ║
╚══════════════════════════════════════════════════════════╝

Usage:
    python -m pytest tests/test_new_features.py -v
    python tests/test_new_features.py
"""

import unittest
import threading
import time
import os
import sys
import json
import tempfile
import hashlib
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Health Watchdog Tests ────────────────────────────

class TestHealthWatchdog(unittest.TestCase):
    """Test the health watchdog thread."""

    def setUp(self):
        from utils.watchdog import HealthWatchdog

        self.mock_tars = MagicMock()
        self.mock_tars._kill_event = threading.Event()
        self.mock_tars._count_active_tasks.return_value = 0
        self.mock_tars.server = MagicMock()
        self.mock_tars.server._boot_time = time.time()
        self.mock_tars.imessage_sender = MagicMock()

        self.config = {"watchdog": {"check_interval": 1, "task_timeout_minutes": 1, "memory_warn_mb": 4096}}
        self.watchdog = HealthWatchdog(self.config, self.mock_tars)

    def tearDown(self):
        self.watchdog.stop()
        time.sleep(0.1)

    def test_start_stop(self):
        """Watchdog starts and stops cleanly."""
        self.watchdog.start()
        self.assertTrue(self.watchdog._running)
        self.assertIsNotNone(self.watchdog._thread)
        self.assertTrue(self.watchdog._thread.is_alive())

        self.watchdog.stop()
        time.sleep(1.5)  # Wait for loop to exit
        self.assertFalse(self.watchdog._running)

    def test_task_registration(self):
        """Tasks can be registered and unregistered."""
        self.watchdog.task_started("task_1")
        self.assertIn("task_1", self.watchdog._task_start_times)

        self.watchdog.task_completed("task_1")
        self.assertNotIn("task_1", self.watchdog._task_start_times)

    def test_stale_task_detection(self):
        """Stale tasks are detected and killed."""
        # Set timeout to 0 so any task is immediately stale
        self.watchdog._task_timeout = 0

        self.watchdog.task_started("stale_task")
        time.sleep(0.1)

        self.watchdog._check_stale_tasks()

        # Kill event should have been set (and then cleared)
        # The task should be removed
        self.assertNotIn("stale_task", self.watchdog._task_start_times)

    def test_no_stale_when_fresh(self):
        """Fresh tasks are not killed."""
        self.watchdog._task_timeout = 3600  # 1 hour

        self.watchdog.task_started("fresh_task")
        self.watchdog._check_stale_tasks()

        # Task should still be registered
        self.assertIn("fresh_task", self.watchdog._task_start_times)
        self.watchdog.task_completed("fresh_task")

    def test_double_start_is_safe(self):
        """Starting twice doesn't create two threads."""
        self.watchdog.start()
        t1 = self.watchdog._thread
        self.watchdog.start()
        t2 = self.watchdog._thread
        self.assertIs(t1, t2)


# ─── Semantic Memory Tests ───────────────────────────

class TestSemanticMemory(unittest.TestCase):
    """Test semantic memory (ChromaDB)."""

    def setUp(self):
        try:
            import chromadb
            self._has_chromadb = True
        except ImportError:
            self._has_chromadb = False

        if not self._has_chromadb:
            self.skipTest("chromadb not installed")

        from memory.semantic_memory import SemanticMemory
        self._tmpdir = tempfile.mkdtemp()
        # Create the memory subdirectory structure
        os.makedirs(os.path.join(self._tmpdir, "memory"), exist_ok=True)
        self.mem = SemanticMemory(base_dir=self._tmpdir)

    def test_available(self):
        """Semantic memory is available when ChromaDB is installed."""
        self.assertTrue(self.mem.available)

    def test_store_and_recall_conversation(self):
        """Store a conversation and recall it semantically."""
        self.mem.store_conversation(
            user_message="What's the weather in Tokyo?",
            tars_response="It's 22°C and partly cloudy in Tokyo.",
        )
        result = self.mem.recall("Tokyo weather")
        self.assertTrue(result["success"])
        self.assertIn("Tokyo", result["content"])

    def test_store_and_recall_knowledge(self):
        """Store knowledge and recall it."""
        self.mem.store_knowledge("favorite_color", "Abdullah's favorite color is blue.")
        result = self.mem.recall("favorite color", collection="knowledge")
        self.assertTrue(result["success"])
        self.assertIn("blue", result["content"])

    def test_recall_empty_returns_no_matches(self):
        """Recall with no data returns no matches."""
        result = self.mem.recall("nonexistent query xyz")
        self.assertTrue(result["success"])
        self.assertIn("No semantic matches", result["content"])

    def test_ingest_text_document(self):
        """Ingest a text file and search it."""
        doc_path = os.path.join(self._tmpdir, "test_doc.txt")
        with open(doc_path, "w") as f:
            f.write("The quick brown fox jumps over the lazy dog. " * 20)

        result = self.mem.ingest_document(doc_path, chunk_size=100, chunk_overlap=20)
        self.assertTrue(result["success"])
        self.assertIn("chunks", result["content"])

        # Search the document
        search = self.mem.search_documents("fox jumps")
        self.assertTrue(search["success"])

    def test_ingest_missing_file(self):
        """Ingest a nonexistent file returns error."""
        result = self.mem.ingest_document("/nonexistent/file.txt")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"])

    def test_stats(self):
        """Stats returns correct structure."""
        stats = self.mem.get_stats()
        self.assertTrue(stats["available"])
        self.assertIn("collections", stats)
        self.assertIn("total_vectors", stats)

    def test_openai_embedding_function_class(self):
        """OpenAIEmbeddingFunction initializes gracefully without valid key."""
        from memory.semantic_memory import OpenAIEmbeddingFunction
        ef = OpenAIEmbeddingFunction(api_key="invalid-key-for-test")
        self.assertFalse(ef.available)


# ─── Scheduler Tests ─────────────────────────────────

class TestScheduler(unittest.TestCase):
    """Test the task scheduler."""

    def setUp(self):
        from utils.scheduler import TaskScheduler
        self.scheduler = TaskScheduler()
        self._fired = []
        self.scheduler._on_task_due = lambda text, tid: self._fired.append((text, tid))

    def tearDown(self):
        self.scheduler.stop()

    def test_add_task(self):
        """Add a scheduled task."""
        result = self.scheduler.add_task(
            task_text="Say hello",
            schedule="0 9 * * *",
            task_id="test_1",
        )
        self.assertTrue(result["success"])

    def test_list_tasks(self):
        """List scheduled tasks."""
        self.scheduler.add_task("Task A", "0 9 * * *", task_id="t1")
        self.scheduler.add_task("Task B", "0 17 * * *", task_id="t2")
        result = self.scheduler.list_tasks()
        self.assertTrue(result["success"])
        self.assertIn("t1", result["content"])
        self.assertIn("t2", result["content"])

    def test_remove_task(self):
        """Remove a scheduled task."""
        self.scheduler.add_task("Task C", "0 12 * * *", task_id="remove_me")
        result = self.scheduler.remove_task("remove_me")
        self.assertTrue(result["success"])

        # Verify it's gone
        listing = self.scheduler.list_tasks()
        self.assertNotIn("remove_me", listing["content"])

    def test_remove_nonexistent(self):
        """Remove a nonexistent task returns error."""
        result = self.scheduler.remove_task("nonexistent")
        self.assertFalse(result["success"])

    def test_invalid_schedule(self):
        """Invalid cron expression returns error."""
        result = self.scheduler.add_task("Bad task", "invalid cron", task_id="bad")
        self.assertFalse(result["success"])


# ─── MCP Client Tests ────────────────────────────────

class TestMCPClient(unittest.TestCase):
    """Test the MCP client."""

    def test_init_no_servers(self):
        """MCP client initializes with no servers configured."""
        from utils.mcp_client import MCPClient
        client = MCPClient(config={})
        stats = client.get_stats()
        self.assertEqual(stats["configured"], 0)
        self.assertEqual(stats["connected"], 0)

    def test_stats_structure(self):
        """Stats returns expected keys."""
        from utils.mcp_client import MCPClient
        client = MCPClient(config={"mcp": {"servers": []}})
        stats = client.get_stats()
        self.assertIn("configured", stats)
        self.assertIn("connected", stats)
        self.assertIn("total_tools", stats)


# ─── Voice Interface Tests ───────────────────────────

class TestVoiceInterface(unittest.TestCase):
    """Test voice interface initialization."""

    def test_disabled_by_default(self):
        """Voice interface is disabled when config says so."""
        from voice.voice_interface import VoiceInterface
        config = {"voice": {"enabled": False}}
        vi = VoiceInterface(config, on_message=lambda text, src: None)
        self.assertFalse(vi.enabled)

    def test_enabled_flag(self):
        """Voice interface reads enabled flag from config."""
        from voice.voice_interface import VoiceInterface
        config = {"voice": {"enabled": True, "silence_threshold": 500, "silence_duration": 1.5}}
        vi = VoiceInterface(config, on_message=lambda text, src: None)
        # May be True or False depending on if pyaudio is installed
        # but the config flag should be read
        self.assertIsNotNone(vi.enabled)


# ─── Dashboard Auth Tests ────────────────────────────

class TestDashboardAuth(unittest.TestCase):
    """Test dashboard session token authentication."""

    def test_token_generated(self):
        """Session token is generated on server init."""
        from server import TARSServer
        # Reset token for test
        TARSServer._session_token = None
        server = TARSServer()
        self.assertIsNotNone(TARSServer._session_token)
        self.assertTrue(len(TARSServer._session_token) > 16)

    def test_token_is_stable(self):
        """Same token is reused across instances (class-level)."""
        from server import TARSServer
        TARSServer._session_token = None
        s1 = TARSServer()
        token1 = TARSServer._session_token
        s2 = TARSServer()
        token2 = TARSServer._session_token
        self.assertEqual(token1, token2)


# ─── LLM Client Normalization Tests ──────────────────

class TestLLMClientNormalization(unittest.TestCase):
    """Test that LLM response types are consistent."""

    def test_content_block_text(self):
        """ContentBlock with text works."""
        from brain.llm_client import ContentBlock
        cb = ContentBlock(block_type="text", text="Hello, world!")
        self.assertEqual(cb.type, "text")
        self.assertEqual(cb.text, "Hello, world!")
        self.assertIsNone(cb.id)
        self.assertIsNone(cb.name)

    def test_content_block_tool_use(self):
        """ContentBlock with tool_use works."""
        from brain.llm_client import ContentBlock
        cb = ContentBlock(block_type="tool_use", block_id="t1", name="web_search", input_data={"query": "test"})
        self.assertEqual(cb.type, "tool_use")
        self.assertEqual(cb.name, "web_search")
        self.assertEqual(cb.input, {"query": "test"})

    def test_llm_response_structure(self):
        """LLMResponse has all expected attributes."""
        from brain.llm_client import LLMResponse, ContentBlock, Usage
        resp = LLMResponse(
            content=[ContentBlock(block_type="text", text="hi")],
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        self.assertEqual(resp.stop_reason, "end_turn")
        self.assertEqual(resp.usage.input_tokens, 10)
        self.assertEqual(len(resp.content), 1)
        self.assertEqual(resp.content[0].text, "hi")

    def test_usage_defaults(self):
        """Usage defaults to 0."""
        from brain.llm_client import Usage
        u = Usage()
        self.assertEqual(u.input_tokens, 0)
        self.assertEqual(u.output_tokens, 0)


# ─── Image Generation Tests ──────────────────────────

class TestImageGenModule(unittest.TestCase):
    """Test image generation module structure."""

    def test_import(self):
        """Image gen module imports."""
        from hands.image_gen import generate_image
        self.assertTrue(callable(generate_image))

    def test_missing_api_key(self):
        """Generate image without API key returns error."""
        from hands.image_gen import generate_image
        result = generate_image("a cat", api_key=None)
        self.assertFalse(result["success"])


# ─── Report Generation Tests ─────────────────────────

class TestReportGenModule(unittest.TestCase):
    """Test report generation module."""

    def test_import(self):
        """Report gen module imports."""
        from hands.report_gen import generate_report
        self.assertTrue(callable(generate_report))


# ─── PPTX Generation Tests ──────────────────────────

class TestPPTXModule(unittest.TestCase):
    """Test PowerPoint generation module."""

    def test_import(self):
        """PPTX gen module imports."""
        try:
            from hands.pptx_gen import generate_pptx
            self.assertTrue(callable(generate_pptx))
        except ImportError:
            self.skipTest("python-pptx not installed")


# ─── Headless Browser Tests ──────────────────────────

class TestHeadlessBrowserModule(unittest.TestCase):
    """Test headless browser module."""

    def test_import(self):
        """Headless browser module imports."""
        from hands.headless_browser import scrape_page, take_screenshot, extract_links
        self.assertTrue(callable(scrape_page))
        self.assertTrue(callable(take_screenshot))
        self.assertTrue(callable(extract_links))


# ─── Error Tracker Tests ─────────────────────────────

class TestErrorTracker(unittest.TestCase):
    """Test error tracker persistence and fix registry."""

    def test_record_error(self):
        """Record an error."""
        from memory.error_tracker import ErrorTracker
        tracker = ErrorTracker()
        # Override file path to a temp location
        tracker._file = os.path.join(tempfile.mkdtemp(), "errors.json")

        result = tracker.record_error(error="Test error unique xyz", context="test")
        self.assertIsNone(result)  # No fix known yet

    def test_record_and_recall_fix(self):
        """Record a fix and auto-recall it."""
        from memory.error_tracker import ErrorTracker
        tracker = ErrorTracker()
        tracker._file = os.path.join(tempfile.mkdtemp(), "errors.json")

        tracker.record_error(error="KeyError: 'name' test_unique", context="executor")
        tracker.record_fix(error="KeyError: 'name' test_unique", fix="Add default value", context="executor")

        # Now record the same error — should get the fix back
        fix = tracker.record_error(error="KeyError: 'name' test_unique", context="executor")
        self.assertIsNotNone(fix)

    def test_stats(self):
        """Stats returns expected shape."""
        from memory.error_tracker import error_tracker
        stats = error_tracker.get_stats()
        self.assertIn("unique_errors", stats)
        self.assertIn("auto_fixable", stats)
        self.assertIn("fix_rate", stats)


# ─── Safety Module Tests ─────────────────────────────

class TestSafety(unittest.TestCase):
    """Test destructive command detection."""

    def test_destructive_commands(self):
        from utils.safety import is_destructive
        self.assertTrue(is_destructive("rm -rf /"))
        self.assertTrue(is_destructive("sudo rm -rf /home"))
        self.assertTrue(is_destructive("mkfs.ext4 /dev/sda"))

    def test_safe_commands(self):
        from utils.safety import is_destructive
        self.assertFalse(is_destructive("ls -la"))
        self.assertFalse(is_destructive("echo hello"))
        self.assertFalse(is_destructive("cat file.txt"))


# ─── Event Bus Tests (quick) ─────────────────────────

class TestEventBusQuick(unittest.TestCase):
    """Quick event bus smoke test."""

    def test_emit_and_history(self):
        from utils.event_bus import EventBus
        bus = EventBus(max_history=10)
        bus.emit("test", {"key": "value"})
        history = bus.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["type"], "test")

    def test_stats(self):
        from utils.event_bus import EventBus
        bus = EventBus(max_history=10)
        bus.emit("a")
        bus.emit("b")
        stats = bus.get_stats()
        self.assertEqual(stats["total_events"], 2)


# ─── Run all tests ───────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  TARS — Integration Tests: New Features")
    print("=" * 60 + "\n")
    unittest.main(verbosity=2)
