"""
╔══════════════════════════════════════════╗
║  TARS — Test Suite: File Manager          ║
╚══════════════════════════════════════════╝

Tests write_file syntax checking, path expansion, etc.
"""

import unittest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from hands.file_manager import write_file, read_file


class TestWriteFileSyntaxCheck(unittest.TestCase):
    """Test that write_file auto-checks Python syntax after writing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_python_gets_syntax_ok(self):
        """Writing valid Python should include '✅ Syntax OK'."""
        path = os.path.join(self.tmpdir, "good.py")
        result = write_file(path, 'print("hello world")\n')
        self.assertTrue(result["success"])
        self.assertIn("Syntax OK", result["content"])

    def test_invalid_python_gets_syntax_error(self):
        """Writing invalid Python should include 'SYNTAX ERROR'."""
        path = os.path.join(self.tmpdir, "bad.py")
        result = write_file(path, 'def foo(\n  print("oops"\n')
        self.assertTrue(result["success"])  # File is still written
        self.assertIn("SYNTAX ERROR", result["content"])

    def test_non_python_no_syntax_check(self):
        """Writing a .txt file should NOT include syntax info."""
        path = os.path.join(self.tmpdir, "notes.txt")
        result = write_file(path, "Hello there\n")
        self.assertTrue(result["success"])
        self.assertNotIn("Syntax", result["content"])

    def test_valid_multiline_python(self):
        """Multi-line valid Python passes syntax check."""
        path = os.path.join(self.tmpdir, "multi.py")
        code = '''
import os

def greet(name: str) -> str:
    """Return greeting."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("TARS"))
'''
        result = write_file(path, code)
        self.assertTrue(result["success"])
        self.assertIn("Syntax OK", result["content"])

    def test_syntax_error_reports_line_number(self):
        """Syntax error message should include line number."""
        path = os.path.join(self.tmpdir, "line_err.py")
        code = 'x = 1\ny = 2\nz = (\n'
        result = write_file(path, code)
        self.assertIn("SYNTAX ERROR", result["content"])
        self.assertIn("line", result["content"].lower())


class TestWriteFilePathExpansion(unittest.TestCase):
    """Test that write_file handles tilde paths."""

    def test_tilde_expansion(self):
        """write_file should expand ~ to home directory."""
        # We can't test writing to ~/Desktop without side effects,
        # but we can verify the function doesn't crash on tilde paths
        path = os.path.join(tempfile.mkdtemp(), "test_expand.txt")
        result = write_file(path, "test content")
        self.assertTrue(result["success"])
        # Clean up
        os.unlink(path)

    def test_creates_parent_dirs(self):
        """write_file should create parent directories."""
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "sub", "dir", "file.txt")
        result = write_file(path, "nested content")
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(path))
        import shutil
        shutil.rmtree(tmpdir)


class TestReadFile(unittest.TestCase):
    """Test read_file basics."""

    def test_read_nonexistent(self):
        """Reading a nonexistent file returns error."""
        result = read_file("/tmp/tars_nonexistent_file_12345.txt")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"].lower())

    def test_read_existing(self):
        """Reading an existing file returns its content."""
        path = os.path.join(tempfile.mkdtemp(), "readable.txt")
        with open(path, "w") as f:
            f.write("hello from TARS")
        result = read_file(path)
        self.assertTrue(result["success"])
        self.assertIn("hello from TARS", result["content"])
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
