"""
╔══════════════════════════════════════════╗
║     TARS — Test Suite: Base Agent         ║
╚══════════════════════════════════════════╝

Tests for base_agent.py utilities:
  - _parse_function_tags (Groq text→tool parsing)
  - Text-only loop detection behavior
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.base_agent import _parse_function_tags


class TestParseFunctionTags(unittest.TestCase):
    """Test parsing <function>name{...}</function> tags from agent text."""

    def test_parse_done_tag(self):
        text = '<function>done{"summary": "Task completed successfully."}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")
        self.assertEqual(result[0][1]["summary"], "Task completed successfully.")

    def test_parse_stuck_tag(self):
        text = '<function>stuck{"reason": "Cannot access the website."}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "stuck")
        self.assertEqual(result[0][1]["reason"], "Cannot access the website.")

    def test_parse_done_with_surrounding_text(self):
        text = (
            'Here are the results I found. '
            '<function>done{"summary": "Found 5 countries with populations."}</function> '
            'Hope that helps!'
        )
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")
        self.assertIn("5 countries", result[0][1]["summary"])

    def test_parse_no_tags(self):
        text = "Just some regular text with no function tags."
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 0)

    def test_parse_invalid_json(self):
        text = '<function>done{not valid json}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 0)

    def test_parse_multiple_tags(self):
        text = (
            '<function>note{"key": "pop", "value": "1.4B"}</function> '
            '<function>done{"summary": "All done"}</function>'
        )
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "note")
        self.assertEqual(result[1][0], "done")

    def test_parse_multiline_json(self):
        text = '<function>done{"summary": "Found data:\\n1. India\\n2. China"}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")

    def test_parse_with_spaces_around_json(self):
        text = '<function>done {"summary": "Completed"} </function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")

    def test_parse_real_groq_output(self):
        """Test with actual Groq Llama output pattern seen in production."""
        text = (
            '<function>done{"summary": "Here are 5 interesting space facts from '
            '2025 or 2026: \\n1. New Interstellar Comet: In 2025, a new interstellar '
            'comet was discovered."}</function>'
        )
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")
        self.assertIn("space facts", result[0][1]["summary"])

    def test_empty_string(self):
        result = _parse_function_tags("")
        self.assertEqual(len(result), 0)

    def test_partial_tag_not_parsed(self):
        text = '<function>done{"summary": "test"}'  # Missing closing tag
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 0)

    # ── Tests for <function(name>{...}</function> format (Groq variant) ──

    def test_parse_parenthesis_done_tag(self):
        """Groq Llama sometimes uses <function(done> instead of <function>done."""
        text = '<function(done>{"summary": "Task completed successfully."}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")
        self.assertEqual(result[0][1]["summary"], "Task completed successfully.")

    def test_parse_parenthesis_stuck_tag(self):
        text = '<function(stuck>{"reason": "Cannot find element."}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "stuck")
        self.assertEqual(result[0][1]["reason"], "Cannot find element.")

    def test_parse_parenthesis_write_file_tag(self):
        """Groq also uses parenthesis format for other tools."""
        text = '<function(write_file>{"content": "hello world", "path": "/tmp/test.py"}</function>'
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "write_file")
        self.assertEqual(result[0][1]["content"], "hello world")

    def test_parse_parenthesis_with_surrounding_text(self):
        text = (
            'I will now complete the task. '
            '<function(done>{"summary": "Created the script and ran it."}</function>'
        )
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "done")

    def test_parse_mixed_formats(self):
        """Both formats in same output (unlikely but should work)."""
        text = (
            '<function>note{"key": "test"}</function> '
            '<function(done>{"summary": "All done"}</function>'
        )
        result = _parse_function_tags(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "note")
        self.assertEqual(result[1][0], "done")


if __name__ == "__main__":
    unittest.main()
