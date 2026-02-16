"""
╔══════════════════════════════════════════╗
║      TARS — Hands: File Manager          ║
╚══════════════════════════════════════════╝

Read, write, move, delete files and directories.
"""

import os
import shutil


def read_file(file_path):
    """Read a file's contents."""
    try:
        path = os.path.expanduser(file_path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Truncate very large files
        if len(content) > 50000:
            content = content[:25000] + "\n\n... [file truncated] ...\n\n" + content[-15000:]

        return {"success": True, "content": content}
    except FileNotFoundError:
        return {"success": False, "error": True, "content": f"File not found: {file_path}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error reading file: {e}"}


def write_file(file_path, content):
    """Write content to a file, creating directories as needed."""
    try:
        path = os.path.expanduser(file_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "content": f"Written {len(content)} chars to {file_path}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error writing file: {e}"}


def move_file(source, destination):
    """Move or rename a file/directory."""
    try:
        src = os.path.expanduser(source)
        dst = os.path.expanduser(destination)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        return {"success": True, "content": f"Moved {source} → {destination}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error moving: {e}"}


def delete_file(file_path, recursive=False):
    """Delete a file or directory."""
    try:
        path = os.path.expanduser(file_path)
        if os.path.isdir(path):
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
        else:
            os.remove(path)
        return {"success": True, "content": f"Deleted {file_path}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error deleting: {e}"}


def list_directory(dir_path):
    """List directory contents."""
    try:
        path = os.path.expanduser(dir_path)
        entries = []
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                entries.append(f"📁 {entry}/")
            else:
                size = os.path.getsize(full)
                entries.append(f"📄 {entry} ({_human_size(size)})")
        return {"success": True, "content": "\n".join(entries) if entries else "(empty directory)"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error listing: {e}"}


def _human_size(size):
    """Convert bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
