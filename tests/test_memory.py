"""
╔══════════════════════════════════════════╗
║     TARS — Test Suite: Memory Manager     ║
╚══════════════════════════════════════════╝

Tests memory persistence, dedup, file cap, history rotation,
recall search, and edge cases.
"""

import unittest
import tempfile
import shutil
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from memory.memory_manager import MemoryManager


def _make_config(base_dir):
    """Build a minimal config dict pointing at temp dirs."""
    return {
        "memory": {
            "context_file": os.path.join("memory", "context.md"),
            "preferences_file": os.path.join("memory", "preferences.md"),
            "history_file": os.path.join("memory", "history.jsonl"),
            "projects_dir": os.path.join("memory", "projects"),
            "max_history_context": 10,
        }
    }


class TestMemoryInit(unittest.TestCase):
    """Test initial file creation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_context_file_created(self):
        self.assertTrue(os.path.exists(self.mm.context_file))

    def test_preferences_file_created(self):
        self.assertTrue(os.path.exists(self.mm.preferences_file))

    def test_history_file_created(self):
        self.assertTrue(os.path.exists(self.mm.history_file))

    def test_default_context_content(self):
        ctx = self.mm._read(self.mm.context_file)
        self.assertIn("Current Context", ctx)

    def test_default_preferences_content(self):
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertIn("Preferences", prefs)


class TestSaveAndRecall(unittest.TestCase):
    """Test save (upsert) and recall (search)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_preference(self):
        result = self.mm.save("preference", "editor", "vscode")
        self.assertTrue(result["success"])
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertIn("**editor**: vscode", prefs)

    def test_save_context(self):
        result = self.mm.save("context", "current_task", "building website")
        self.assertTrue(result["success"])
        ctx = self.mm._read(self.mm.context_file)
        self.assertIn("**current_task**: building website", ctx)

    def test_save_project(self):
        self.mm.save("project", "mysite", "A cool website project")
        project_file = os.path.join(self.mm.projects_dir, "mysite.md")
        self.assertTrue(os.path.exists(project_file))
        content = self.mm._read(project_file)
        self.assertIn("A cool website project", content)

    def test_upsert_replaces_existing_key(self):
        """Save same key twice — should update, not duplicate."""
        self.mm.save("preference", "theme", "dark")
        self.mm.save("preference", "theme", "light")
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertEqual(prefs.count("**theme**:"), 1, "Key should appear exactly once")
        self.assertIn("**theme**: light", prefs)
        self.assertNotIn("dark", prefs)

    def test_upsert_different_keys_coexist(self):
        self.mm.save("preference", "theme", "dark")
        self.mm.save("preference", "editor", "vim")
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertIn("**theme**: dark", prefs)
        self.assertIn("**editor**: vim", prefs)

    def test_recall_finds_saved_preference(self):
        self.mm.save("preference", "editor", "vscode")
        result = self.mm.recall("editor")
        self.assertTrue(result["success"])
        self.assertIn("vscode", result["content"])

    def test_recall_finds_context(self):
        self.mm.save("context", "project_name", "tars_v3")
        result = self.mm.recall("project_name")
        self.assertTrue(result["success"])
        self.assertIn("tars_v3", result["content"])

    def test_recall_no_match(self):
        result = self.mm.recall("xyznonexistent123")
        self.assertTrue(result["success"])
        self.assertIn("No memories found", result["content"])

    def test_recall_token_matching(self):
        """Even partial token matches should return results."""
        self.mm.save("preference", "color_scheme", "monokai pro dark")
        result = self.mm.recall("monokai dark")
        self.assertTrue(result["success"])
        self.assertIn("monokai pro dark", result["content"])


class TestMemoryFileCap(unittest.TestCase):
    """Test the 50KB file size cap."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_stays_under_50kb(self):
        """Writing many entries should never exceed 50KB."""
        for i in range(500):
            self.mm.save("preference", f"key_{i}", "x" * 100)

        size = os.path.getsize(self.mm.preferences_file)
        self.assertLessEqual(size, 50_000, f"File is {size} bytes, should be ≤ 50KB")

    def test_oldest_entries_trimmed(self):
        """When cap is hit, oldest entries should be removed first."""
        # Use longer values so we actually exceed 50KB
        for i in range(200):
            self.mm.save("preference", f"bigkey_{i}", "x" * 300)

        prefs = self.mm._read(self.mm.preferences_file)
        # The latest keys should be present
        self.assertIn("bigkey_199", prefs)
        # Very old keys should be trimmed
        self.assertNotIn("bigkey_0", prefs)


class TestHistoryLog(unittest.TestCase):
    """Test action history logging and rotation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_action_creates_entry(self):
        self.mm.log_action("test_action", "input data", {"success": True, "content": "done"})
        with open(self.mm.history_file) as f:
            lines = f.readlines()
        self.assertGreaterEqual(len(lines), 1)
        entry = json.loads(lines[-1])
        self.assertEqual(entry["action"], "test_action")
        self.assertTrue(entry["success"])

    def test_log_action_truncates_long_input(self):
        long_input = "x" * 10000
        self.mm.log_action("test", long_input, {"success": True})
        with open(self.mm.history_file) as f:
            entry = json.loads(f.readlines()[-1])
        self.assertLessEqual(len(entry["input"]), 500)

    def test_recent_history(self):
        for i in range(20):
            self.mm.log_action(f"action_{i}", f"input_{i}", {"success": i % 2 == 0})
        history = self.mm._get_recent_history(5)
        lines = history.strip().split("\n")
        self.assertEqual(len(lines), 5)

    def test_history_handles_missing_file(self):
        os.remove(self.mm.history_file)
        result = self.mm._get_recent_history()
        self.assertEqual(result, "")


class TestContextSummary(unittest.TestCase):
    """Test the get_context_summary method."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_summary_includes_context(self):
        self.mm.update_context("# Active: Building TARS")
        summary = self.mm.get_context_summary()
        self.assertIn("Building TARS", summary)

    def test_summary_includes_preferences(self):
        self.mm.update_preferences("# Prefs\n- Dark mode")
        summary = self.mm.get_context_summary()
        self.assertIn("Dark mode", summary)

    def test_summary_includes_recent_history(self):
        self.mm.log_action("deploy", "website", {"success": True})
        summary = self.mm.get_context_summary()
        self.assertIn("deploy", summary)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and robustness tests."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mm = MemoryManager(_make_config(self.tmp), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_empty_key(self):
        result = self.mm.save("preference", "", "value")
        self.assertTrue(result["success"])

    def test_save_empty_value(self):
        result = self.mm.save("preference", "key", "")
        self.assertTrue(result["success"])

    def test_save_unicode_content(self):
        result = self.mm.save("preference", "emoji", "🚀🔥💎")
        self.assertTrue(result["success"])
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertIn("🚀🔥💎", prefs)

    def test_save_multiline_value(self):
        result = self.mm.save("preference", "notes", "line1\nline2\nline3")
        self.assertTrue(result["success"])

    def test_save_special_regex_chars_in_key(self):
        """Keys with regex special chars should not break upsert."""
        result = self.mm.save("preference", "key.with[special](chars)", "safe")
        self.assertTrue(result["success"])
        prefs = self.mm._read(self.mm.preferences_file)
        self.assertIn("safe", prefs)

    def test_save_credential(self):
        result = self.mm.save("credential", "github_token", "ghp_fake123")
        self.assertTrue(result["success"])
        cred_file = os.path.join(self.tmp, "memory", "credentials.md")
        self.assertTrue(os.path.exists(cred_file))

    def test_save_learned_pattern(self):
        result = self.mm.save("learned", "retry_on_503", "retry 3 times with backoff")
        self.assertTrue(result["success"])

    def test_save_note_goes_to_history(self):
        self.mm.save("note", "reminder", "check logs at 5pm")
        with open(self.mm.history_file) as f:
            content = f.read()
        self.assertIn("note", content)

    def test_concurrent_read_write(self):
        """Simulate concurrent access (basic thread safety)."""
        import threading
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    self.mm.save("preference", f"thread_{n}_key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent write errors: {errors}")

    def test_corrupted_history_line(self):
        """Corrupt JSON in history should not crash _get_recent_history."""
        with open(self.mm.history_file, "a") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"ts": "t", "action": "ok", "input": "i", "result": "r", "success": True}) + "\n")
        history = self.mm._get_recent_history()
        self.assertIn("ok", history)


if __name__ == "__main__":
    unittest.main()
