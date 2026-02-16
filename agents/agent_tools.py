"""
╔══════════════════════════════════════════════════════════════╗
║     TARS — Shared Agent Tool Definitions                     ║
╠══════════════════════════════════════════════════════════════╣
║  Common tool schemas reused across multiple agents.          ║
║  Single source of truth — no duplication.                    ║
╚══════════════════════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────────
#  Terminal Tools (done + stuck are auto-added by BaseAgent)
# ─────────────────────────────────────────────

TOOL_DONE = {
    "name": "done",
    "description": "Task is complete. Provide a detailed summary of what was accomplished, including specifics (files created, commands run, results found, etc).",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Detailed summary of accomplishments"
            }
        },
        "required": ["summary"]
    }
}

TOOL_STUCK = {
    "name": "stuck",
    "description": "Cannot complete the task after trying multiple approaches. Explain exactly what you tried and why each approach failed. The orchestrator brain will analyze this and either retry with guidance, reroute to a different agent, or ask the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Detailed explanation: what you tried, why each approach failed, what info is missing"
            }
        },
        "required": ["reason"]
    }
}


# ─────────────────────────────────────────────
#  File Tools (shared by Coder, System, File agents)
# ─────────────────────────────────────────────

TOOL_READ_FILE = {
    "name": "read_file",
    "description": "Read the full contents of a file. Use absolute paths.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file"}
        },
        "required": ["path"]
    }
}

TOOL_WRITE_FILE = {
    "name": "write_file",
    "description": "Write content to a file. Creates parent directories automatically. Overwrites if file exists.\n\nCRITICAL: Use ABSOLUTE paths starting with / (e.g. /Users/abdullah/Desktop/script.py). NEVER use ~ (tilde does NOT expand). Use the EXACT filename from the task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "ABSOLUTE path starting with / — e.g. /Users/abdullah/Desktop/script.py — NEVER use ~"},
            "content": {"type": "string", "description": "Full file content to write"}
        },
        "required": ["path", "content"]
    }
}

TOOL_EDIT_FILE = {
    "name": "edit_file",
    "description": "Surgically edit a file by replacing an exact string with new content. Use read_file first to see the current content. The old_string must match EXACTLY (whitespace, indentation, everything).",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file"},
            "old_string": {"type": "string", "description": "Exact text to find and replace (must be unique in file)"},
            "new_string": {"type": "string", "description": "Replacement text"}
        },
        "required": ["path", "old_string", "new_string"]
    }
}

TOOL_LIST_DIR = {
    "name": "list_dir",
    "description": "List contents of a directory with file sizes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to directory"}
        },
        "required": ["path"]
    }
}


# ─────────────────────────────────────────────
#  Terminal / Shell Tools
# ─────────────────────────────────────────────

TOOL_RUN_COMMAND = {
    "name": "run_command",
    "description": "Run a shell command (bash/zsh) and get the output. Use for: installing packages, running scripts, git, building, any CLI task. For long commands, set a higher timeout.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)", "default": 60}
        },
        "required": ["command"]
    }
}

TOOL_SEARCH_FILES = {
    "name": "search_files",
    "description": "Search for files by name pattern (glob) or search file contents (grep). Returns matching file paths and, for content searches, the matching lines.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern — filename glob (e.g. '*.py', '*.ts') or text to grep for"},
            "directory": {"type": "string", "description": "Directory to search in (default: current dir)"},
            "content_search": {"type": "boolean", "description": "If true, search inside file contents (grep). If false, search filenames.", "default": False}
        },
        "required": ["pattern"]
    }
}


# ─────────────────────────────────────────────
#  Git Tools
# ─────────────────────────────────────────────

TOOL_GIT = {
    "name": "git",
    "description": "Run a git command. Examples: 'status', 'add .', 'commit -m \"msg\"', 'push', 'pull', 'log --oneline -10', 'diff', 'branch', 'checkout -b feature'. Do NOT include 'git' prefix — just the subcommand.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Git subcommand (without 'git' prefix)"}
        },
        "required": ["command"]
    }
}


# ─────────────────────────────────────────────
#  Package Management
# ─────────────────────────────────────────────

TOOL_INSTALL_PACKAGE = {
    "name": "install_package",
    "description": "Install a package using the appropriate package manager.",
    "input_schema": {
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "Package name to install"},
            "manager": {"type": "string", "enum": ["pip", "npm", "brew", "pip3"], "description": "Package manager", "default": "pip"}
        },
        "required": ["package"]
    }
}


# ─────────────────────────────────────────────
#  Test Runner
# ─────────────────────────────────────────────

TOOL_RUN_TESTS = {
    "name": "run_tests",
    "description": "Run tests for the project. Provide the test command (e.g., 'pytest', 'npm test', 'python -m unittest').",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Test command to run"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)", "default": 120}
        },
        "required": ["command"]
    }
}


# ─────────────────────────────────────────────
#  Mac Control Tools
# ─────────────────────────────────────────────

TOOL_OPEN_APP = {
    "name": "open_app",
    "description": "Open a macOS application by name. Examples: 'Safari', 'Terminal', 'Visual Studio Code', 'Finder', 'Spotify'",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name"}
        },
        "required": ["app_name"]
    }
}

TOOL_TYPE_TEXT = {
    "name": "type_text",
    "description": "Type text into the currently active/frontmost application window using physical keyboard.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to type"}
        },
        "required": ["text"]
    }
}

TOOL_KEY_PRESS = {
    "name": "key_press",
    "description": "Press a keyboard shortcut. Format: 'command+s', 'command+shift+p', 'return', 'tab', 'escape'. Use modifier names: command/cmd, control/ctrl, option/alt, shift.",
    "input_schema": {
        "type": "object",
        "properties": {
            "keys": {"type": "string", "description": "Key combination (e.g., 'command+s', 'return')"}
        },
        "required": ["keys"]
    }
}

TOOL_CLICK = {
    "name": "click",
    "description": "Click at a specific screen coordinate using physical mouse.",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X screen coordinate"},
            "y": {"type": "integer", "description": "Y screen coordinate"},
            "double_click": {"type": "boolean", "description": "Double-click", "default": False}
        },
        "required": ["x", "y"]
    }
}

TOOL_SCREENSHOT = {
    "name": "screenshot",
    "description": "Take a screenshot of the entire screen. Returns the saved file path.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_FRONTMOST_APP = {
    "name": "frontmost_app",
    "description": "Get the name of the currently active/frontmost application.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_APPLESCRIPT = {
    "name": "applescript",
    "description": "Run raw AppleScript code for advanced macOS automation. Use for things like: controlling System Preferences, managing windows, interacting with apps that have AppleScript dictionaries.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "AppleScript code to execute"}
        },
        "required": ["code"]
    }
}


# ─────────────────────────────────────────────
#  Research / Web Tools
# ─────────────────────────────────────────────

TOOL_WEB_SEARCH = {
    "name": "web_search",
    "description": "Quick Google search. Returns search result snippets. For simple fact lookups.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}

TOOL_BROWSE = {
    "name": "browse",
    "description": "Open a URL in the browser and read the full page text. For reading articles, documentation, product pages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit and read"}
        },
        "required": ["url"]
    }
}

TOOL_EXTRACT = {
    "name": "extract",
    "description": "Open a URL and extract specific information by answering a question about the page content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to visit"},
            "question": {"type": "string", "description": "What specific info to extract from the page"}
        },
        "required": ["url", "question"]
    }
}


# ─────────────────────────────────────────────
#  Research Note Tools
# ─────────────────────────────────────────────

TOOL_NOTE = {
    "name": "note",
    "description": "Save a research finding to your working notes. Use to collect facts as you research.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Short label for this finding"},
            "value": {"type": "string", "description": "The finding/fact to save"}
        },
        "required": ["key", "value"]
    }
}

TOOL_NOTES = {
    "name": "notes",
    "description": "Review all your collected research notes so far.",
    "input_schema": {"type": "object", "properties": {}}
}


# ─────────────────────────────────────────────
#  File Management Tools
# ─────────────────────────────────────────────

TOOL_MOVE = {
    "name": "move",
    "description": "Move or rename a file or directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"}
        },
        "required": ["source", "destination"]
    }
}

TOOL_COPY = {
    "name": "copy",
    "description": "Copy a file or directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"}
        },
        "required": ["source", "destination"]
    }
}

TOOL_DELETE = {
    "name": "delete",
    "description": "Delete a file or directory. Use carefully.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to delete"},
            "recursive": {"type": "boolean", "description": "Delete directory recursively", "default": False}
        },
        "required": ["path"]
    }
}

TOOL_TREE = {
    "name": "tree",
    "description": "Show directory tree structure with depth limit.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path"},
            "depth": {"type": "integer", "description": "Max depth (default 3)", "default": 3}
        },
        "required": ["path"]
    }
}

TOOL_DISK_USAGE = {
    "name": "disk_usage",
    "description": "Get disk usage / size of a file or directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to check"}
        },
        "required": ["path"]
    }
}

TOOL_COMPRESS = {
    "name": "compress",
    "description": "Compress files/directories into a zip or tar.gz archive.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file/directory paths to compress"
            },
            "output": {"type": "string", "description": "Output archive path (e.g., 'backup.zip', 'project.tar.gz')"}
        },
        "required": ["paths", "output"]
    }
}

TOOL_EXTRACT_ARCHIVE = {
    "name": "extract_archive",
    "description": "Extract a zip, tar, or tar.gz archive.",
    "input_schema": {
        "type": "object",
        "properties": {
            "archive": {"type": "string", "description": "Path to archive file"},
            "destination": {"type": "string", "description": "Directory to extract into"}
        },
        "required": ["archive", "destination"]
    }
}


# ─────────────────────────────────────────────
#  Advanced Mac Control Tools (Full macOS Control)
# ─────────────────────────────────────────────

TOOL_QUIT_APP = {
    "name": "quit_app",
    "description": "Quit a macOS application. Set force=true for unresponsive apps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name"},
            "force": {"type": "boolean", "description": "Force-kill (pkill -9)", "default": False}
        },
        "required": ["app_name"]
    }
}

TOOL_HIDE_APP = {
    "name": "hide_app",
    "description": "Hide a macOS application (keeps it running but invisible).",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "Application name"}
        },
        "required": ["app_name"]
    }
}

TOOL_GET_RUNNING_APPS = {
    "name": "get_running_apps",
    "description": "Get a list of all running visible macOS applications.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_RIGHT_CLICK = {
    "name": "right_click",
    "description": "Right-click (context menu) at screen coordinates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"}
        },
        "required": ["x", "y"]
    }
}

TOOL_DRAG = {
    "name": "drag",
    "description": "Drag from one point to another on screen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "x1": {"type": "integer", "description": "Start X"},
            "y1": {"type": "integer", "description": "Start Y"},
            "x2": {"type": "integer", "description": "End X"},
            "y2": {"type": "integer", "description": "End Y"}
        },
        "required": ["x1", "y1", "x2", "y2"]
    }
}

TOOL_GET_WINDOWS = {
    "name": "get_windows",
    "description": "Get all windows of an app (or frontmost app). Shows name, position, size.",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "App name (optional, defaults to frontmost)"}
        }
    }
}

TOOL_MOVE_WINDOW = {
    "name": "move_window",
    "description": "Move frontmost window to a screen position.",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X position"},
            "y": {"type": "integer", "description": "Y position"},
            "app_name": {"type": "string", "description": "App name (optional)"}
        },
        "required": ["x", "y"]
    }
}

TOOL_RESIZE_WINDOW = {
    "name": "resize_window",
    "description": "Resize frontmost window to specific dimensions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "width": {"type": "integer", "description": "Width in pixels"},
            "height": {"type": "integer", "description": "Height in pixels"},
            "app_name": {"type": "string", "description": "App name (optional)"}
        },
        "required": ["width", "height"]
    }
}

TOOL_TILE_WINDOW = {
    "name": "tile_window",
    "description": "Tile the frontmost window. Positions: left, right, top, bottom, fullscreen, center.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position": {"type": "string", "enum": ["left", "right", "top", "bottom", "fullscreen", "center"], "description": "Tile position"}
        },
        "required": ["position"]
    }
}

TOOL_MINIMIZE_WINDOW = {
    "name": "minimize_window",
    "description": "Minimize the frontmost window.",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "App name (optional)"}
        }
    }
}

TOOL_CLOSE_WINDOW = {
    "name": "close_window",
    "description": "Close the frontmost window.",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "App name (optional)"}
        }
    }
}

TOOL_FULLSCREEN_WINDOW = {
    "name": "fullscreen_window",
    "description": "Toggle fullscreen for the frontmost window.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_SET_VOLUME = {
    "name": "set_volume",
    "description": "Set the system output volume (0-100).",
    "input_schema": {
        "type": "object",
        "properties": {
            "level": {"type": "integer", "description": "Volume level 0-100"}
        },
        "required": ["level"]
    }
}

TOOL_GET_VOLUME = {
    "name": "get_volume",
    "description": "Get the current system output volume.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_TOGGLE_MUTE = {
    "name": "toggle_mute",
    "description": "Toggle mute/unmute for system audio.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_CLIPBOARD_READ = {
    "name": "clipboard_read",
    "description": "Read text from the macOS clipboard (pbpaste).",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_CLIPBOARD_WRITE = {
    "name": "clipboard_write",
    "description": "Write text to the macOS clipboard (pbcopy).",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to copy to clipboard"}
        },
        "required": ["text"]
    }
}

TOOL_NOTIFY = {
    "name": "notify",
    "description": "Send a native macOS notification banner.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Notification message"},
            "title": {"type": "string", "description": "Title (default: TARS)", "default": "TARS"},
            "subtitle": {"type": "string", "description": "Subtitle (optional)"}
        },
        "required": ["message"]
    }
}

TOOL_SPOTLIGHT_SEARCH = {
    "name": "spotlight_search",
    "description": "Search files via macOS Spotlight (mdfind). Search by content, type, date. Examples: 'meeting notes', 'kind:pdf', 'date:today'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Spotlight search query"},
            "folder": {"type": "string", "description": "Restrict to folder (optional)"},
            "max_results": {"type": "integer", "description": "Max results (default 20)", "default": 20}
        },
        "required": ["query"]
    }
}

TOOL_FINDER_REVEAL = {
    "name": "finder_reveal",
    "description": "Reveal a file in Finder (highlights it).",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to reveal"}
        },
        "required": ["path"]
    }
}

TOOL_FINDER_TAG = {
    "name": "finder_tag",
    "description": "Add a Finder tag (color label) to a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "tag_name": {"type": "string", "description": "Tag name (e.g., Red, Blue, Important)"}
        },
        "required": ["path", "tag_name"]
    }
}

TOOL_MAIL_READ = {
    "name": "mail_read",
    "description": "Read emails from Mail.app inbox. Returns sender, subject, date.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to read (default 5)", "default": 5},
            "index": {"type": "integer", "description": "Read a specific email by index (1=newest)"}
        }
    }
}

TOOL_MAIL_SEARCH = {
    "name": "mail_search",
    "description": "Search emails by keyword (searches subject and sender).",
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search keyword"}
        },
        "required": ["keyword"]
    }
}

TOOL_MAIL_SEND = {
    "name": "mail_send",
    "description": "Send an email via Mail.app.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body text"}
        },
        "required": ["to", "subject", "body"]
    }
}

TOOL_MAIL_UNREAD = {
    "name": "mail_unread",
    "description": "Get the count of unread emails in inbox.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_NOTES_LIST = {
    "name": "notes_list",
    "description": "List all Apple Notes with modification dates.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_NOTES_READ = {
    "name": "notes_read",
    "description": "Read an Apple Note by its exact name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "note_name": {"type": "string", "description": "Exact name of the note"}
        },
        "required": ["note_name"]
    }
}

TOOL_NOTES_CREATE = {
    "name": "notes_create",
    "description": "Create a new Apple Note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Note title"},
            "body": {"type": "string", "description": "Note content"},
            "folder": {"type": "string", "description": "Notes folder (default: Notes)", "default": "Notes"}
        },
        "required": ["title", "body"]
    }
}

TOOL_NOTES_SEARCH = {
    "name": "notes_search",
    "description": "Search Apple Notes by title keyword.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    }
}

TOOL_CALENDAR_EVENTS = {
    "name": "calendar_events",
    "description": "Get upcoming calendar events for the next N days.",
    "input_schema": {
        "type": "object",
        "properties": {
            "calendar_name": {"type": "string", "description": "Calendar name (optional — all if omitted)"},
            "days_ahead": {"type": "integer", "description": "Days ahead to look (default 7)", "default": 7}
        }
    }
}

TOOL_CALENDAR_CREATE = {
    "name": "calendar_create",
    "description": "Create a calendar event. Dates like 'March 1, 2026 2:00 PM'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event title"},
            "start_date": {"type": "string", "description": "Start date (e.g., 'March 1, 2026 2:00 PM')"},
            "end_date": {"type": "string", "description": "End date"},
            "calendar_name": {"type": "string", "description": "Calendar name (default: Calendar)", "default": "Calendar"}
        },
        "required": ["title", "start_date", "end_date"]
    }
}

TOOL_REMINDERS_LIST = {
    "name": "reminders_list",
    "description": "List reminders. Without list_name, shows all lists with item counts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "list_name": {"type": "string", "description": "Specific list name (optional)"}
        }
    }
}

TOOL_REMINDERS_CREATE = {
    "name": "reminders_create",
    "description": "Create a new reminder in Apple Reminders.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Reminder title"},
            "list_name": {"type": "string", "description": "List name (default: Reminders)", "default": "Reminders"},
            "due_date": {"type": "string", "description": "Due date (optional, e.g., 'March 1, 2026')"},
            "notes": {"type": "string", "description": "Notes (optional)"}
        },
        "required": ["title"]
    }
}

TOOL_REMINDERS_COMPLETE = {
    "name": "reminders_complete",
    "description": "Mark a reminder as completed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Exact reminder title"},
            "list_name": {"type": "string", "description": "List name (default: Reminders)", "default": "Reminders"}
        },
        "required": ["title"]
    }
}

TOOL_CONTACTS_SEARCH = {
    "name": "contacts_search",
    "description": "Search macOS Contacts by name. Returns name, email, phone.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Name to search"}
        },
        "required": ["query"]
    }
}

TOOL_CONTACTS_GET = {
    "name": "contacts_get",
    "description": "Get full details of a contact by exact name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Exact contact name"}
        },
        "required": ["name"]
    }
}

TOOL_SET_DARK_MODE = {
    "name": "set_dark_mode",
    "description": "Enable or disable macOS dark mode.",
    "input_schema": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "description": "true=dark, false=light"}
        },
        "required": ["enabled"]
    }
}

TOOL_OPEN_URL = {
    "name": "open_url",
    "description": "Open a URL in the default browser.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open"}
        },
        "required": ["url"]
    }
}

TOOL_WIFI_TOGGLE = {
    "name": "wifi_toggle",
    "description": "Turn Wi-Fi on or off.",
    "input_schema": {
        "type": "object",
        "properties": {
            "on": {"type": "boolean", "description": "true=on, false=off"}
        },
        "required": ["on"]
    }
}

TOOL_LOCK_SCREEN = {
    "name": "lock_screen",
    "description": "Lock the Mac screen.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_GET_BATTERY = {
    "name": "get_battery",
    "description": "Get Mac battery status and percentage.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_OCR_SCREEN = {
    "name": "ocr_screen",
    "description": "Take a screenshot and OCR it — returns all text visible on screen. Optionally specify a region (x,y,w,h).",
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Region X (optional)"},
            "y": {"type": "integer", "description": "Region Y (optional)"},
            "w": {"type": "integer", "description": "Region width (optional)"},
            "h": {"type": "integer", "description": "Region height (optional)"}
        }
    }
}

TOOL_GET_UI_ELEMENTS = {
    "name": "get_ui_elements",
    "description": "Read the UI element tree of any app via macOS Accessibility API. Returns buttons, text fields, labels, etc. with their roles and identifiers. Powerful for automating apps without screenshots.",
    "input_schema": {
        "type": "object",
        "properties": {
            "app_name": {"type": "string", "description": "App name (optional, defaults to frontmost)"},
            "max_depth": {"type": "integer", "description": "Max UI tree depth (default 3)", "default": 3}
        }
    }
}

TOOL_GET_ENVIRONMENT = {
    "name": "get_environment",
    "description": "Get a complete Mac environment snapshot: running apps, volume, dark mode, Wi-Fi, battery, disk space, screen size, clipboard.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_PREPARE_ENVIRONMENT = {
    "name": "prepare_environment",
    "description": "Prepare Mac for TARS operation — close distracting apps, open needed ones, set volume, dark mode.",
    "input_schema": {
        "type": "object",
        "properties": {
            "close_apps": {"type": "array", "items": {"type": "string"}, "description": "Apps to close"},
            "open_apps": {"type": "array", "items": {"type": "string"}, "description": "Apps to open"},
            "volume": {"type": "integer", "description": "Volume level 0-100"},
            "dark_mode": {"type": "boolean", "description": "Enable dark mode"}
        }
    }
}

TOOL_SIRI_SHORTCUT = {
    "name": "siri_shortcut",
    "description": "Run a Siri Shortcut by name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "shortcut_name": {"type": "string", "description": "Name of the Siri Shortcut"},
            "input_text": {"type": "string", "description": "Input text to pass (optional)"}
        },
        "required": ["shortcut_name"]
    }
}

TOOL_KEYCHAIN_STORE = {
    "name": "keychain_store",
    "description": "Store a credential securely in macOS Keychain.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name"},
            "account": {"type": "string", "description": "Account name"},
            "password": {"type": "string", "description": "Password/secret to store"}
        },
        "required": ["service", "account", "password"]
    }
}

TOOL_KEYCHAIN_READ = {
    "name": "keychain_read",
    "description": "Read a credential from macOS Keychain.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name"},
            "account": {"type": "string", "description": "Account name"}
        },
        "required": ["service", "account"]
    }
}
