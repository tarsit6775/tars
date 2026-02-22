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


# ─────────────────────────────────────────────
#  Email Agent Tools (hands/email.py backend)
# ─────────────────────────────────────────────

TOOL_EMAIL_READ_INBOX = {
    "name": "email_read_inbox",
    "description": "Read latest N emails from inbox. Returns sender, subject, date, read/unread status for each.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to read (default 10)", "default": 10}
        }
    }
}

TOOL_EMAIL_READ_MESSAGE = {
    "name": "email_read_message",
    "description": "Read full email content by index (1 = newest). Returns from, to, cc, subject, date, body, and attachments list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_SEND = {
    "name": "email_send",
    "description": "Send an email. Supports plain text, HTML, CC/BCC, multiple recipients, and file attachments.\n\nExamples:\n  email_send(to='bob@gmail.com', subject='Hello', body='Hi Bob!')\n  email_send(to=['alice@gmail.com','bob@gmail.com'], subject='Report', body='<h1>Report</h1>', html=true, attachment_paths=['/Users/abdullah/report.xlsx'])",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "description": "Recipient(s) — single email string or array of emails",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            },
            "subject": {"type": "string", "description": "Email subject line"},
            "body": {"type": "string", "description": "Email body (plain text or HTML if html=true)"},
            "cc": {
                "description": "CC recipient(s)",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            },
            "bcc": {
                "description": "BCC recipient(s)",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            },
            "attachment_paths": {
                "description": "File path(s) to attach",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            },
            "html": {"type": "boolean", "description": "Send as HTML email (default: false)", "default": False},
            "from_address": {"type": "string", "description": "Sender address (default: tarsitgroup@outlook.com)"}
        },
        "required": ["to", "subject", "body"]
    }
}

TOOL_EMAIL_REPLY = {
    "name": "email_reply",
    "description": "Reply to an email by index. Optionally reply-all.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index to reply to (1 = newest)", "default": 1},
            "body": {"type": "string", "description": "Reply text"},
            "reply_all": {"type": "boolean", "description": "Reply to all recipients (default: false)", "default": False},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        },
        "required": ["body"]
    }
}

TOOL_EMAIL_FORWARD = {
    "name": "email_forward",
    "description": "Forward an email by index to a new recipient.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index to forward (1 = newest)", "default": 1},
            "to": {"type": "string", "description": "Recipient email address"},
            "body": {"type": "string", "description": "Additional text to add above the forwarded content"},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        },
        "required": ["to"]
    }
}

TOOL_EMAIL_SEARCH = {
    "name": "email_search",
    "description": "Advanced email search with multiple filters (AND-combined). Pass only the filters you need.\n\nExamples:\n  email_search(sender='john@company.com')\n  email_search(keyword='invoice', unread_only=true)\n  email_search(subject='report', flagged_only=true)",
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search keyword (matches subject and sender)"},
            "sender": {"type": "string", "description": "Filter by sender (partial match)"},
            "subject": {"type": "string", "description": "Filter by subject (partial match)"},
            "unread_only": {"type": "boolean", "description": "Only show unread emails", "default": False},
            "flagged_only": {"type": "boolean", "description": "Only show flagged emails", "default": False},
            "has_attachments": {"type": "boolean", "description": "Only show emails with attachments", "default": False},
            "mailbox": {"type": "string", "description": "Mailbox to search (default: inbox)", "default": "inbox"},
            "max_results": {"type": "integer", "description": "Max results (default: 20)", "default": 20}
        }
    }
}

TOOL_EMAIL_UNREAD_COUNT = {
    "name": "email_unread_count",
    "description": "Get the count of unread emails in inbox.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_MARK_READ = {
    "name": "email_mark_read",
    "description": "Mark an email as read.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_MARK_UNREAD = {
    "name": "email_mark_unread",
    "description": "Mark an email as unread.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_FLAG = {
    "name": "email_flag",
    "description": "Flag or unflag an email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "flagged": {"type": "boolean", "description": "True to flag, false to unflag", "default": True},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_DELETE = {
    "name": "email_delete",
    "description": "Delete an email (move to Trash).",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_ARCHIVE = {
    "name": "email_archive",
    "description": "Archive an email (move to Archive folder).",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_MOVE = {
    "name": "email_move",
    "description": "Move an email to a different mailbox/folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "from_mailbox": {"type": "string", "description": "Source mailbox (default: inbox)", "default": "inbox"},
            "to_mailbox": {"type": "string", "description": "Destination mailbox name"},
            "account": {"type": "string", "description": "Account name (optional, for cross-account moves)"}
        },
        "required": ["to_mailbox"]
    }
}

TOOL_EMAIL_LIST_FOLDERS = {
    "name": "email_list_folders",
    "description": "List all mailboxes/folders across all email accounts.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_DOWNLOAD_ATTACHMENTS = {
    "name": "email_download_attachments",
    "description": "Download all attachments from an email to disk.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Message index (1 = newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox (default: inbox)", "default": "inbox"},
            "save_dir": {"type": "string", "description": "Save directory (default: ~/Downloads/tars_attachments/)"}
        }
    }
}

TOOL_EMAIL_SAVE_DRAFT = {
    "name": "email_save_draft",
    "description": "Save an email as a draft (don't send yet).",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string", "description": "Subject line"},
            "body": {"type": "string", "description": "Email body"},
            "cc": {
                "description": "CC recipient(s)",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}}
                ]
            },
            "html": {"type": "boolean", "description": "Save as HTML draft", "default": False}
        },
        "required": ["to", "subject", "body"]
    }
}

TOOL_EMAIL_LIST_DRAFTS = {
    "name": "email_list_drafts",
    "description": "List emails saved in the Drafts mailbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Max drafts to list (default 10)", "default": 10}
        }
    }
}

TOOL_EMAIL_VERIFY_SENT = {
    "name": "email_verify_sent",
    "description": "Verify an email was actually sent by checking the Sent folder. Use after sending important emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Subject of the email to verify"},
            "to": {"type": "string", "description": "Recipient address (optional, narrows search)"}
        },
        "required": ["subject"]
    }
}

TOOL_EMAIL_TEMPLATE_SAVE = {
    "name": "email_template_save",
    "description": "Save a reusable email template. Use {{variable}} placeholders for dynamic content.\n\nExample:\n  email_template_save(name='weekly_report', subject='Weekly Report — {{date}}', body='Hi {{name}},\\n\\nHere is the weekly report...')",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Template name (used to reference it later)"},
            "subject": {"type": "string", "description": "Subject template (supports {{var}} placeholders)"},
            "body": {"type": "string", "description": "Body template (supports {{var}} placeholders)"},
            "html": {"type": "boolean", "description": "Is this an HTML template?", "default": False}
        },
        "required": ["name", "subject", "body"]
    }
}

TOOL_EMAIL_TEMPLATE_LIST = {
    "name": "email_template_list",
    "description": "List all saved email templates.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_TEMPLATE_SEND = {
    "name": "email_template_send",
    "description": "Send an email using a saved template. Pass variables dict for placeholder substitution.\n\nExample:\n  email_template_send(name='weekly_report', to='boss@company.com', variables={'date': 'March 1', 'name': 'John'})",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Template name"},
            "to": {"type": "string", "description": "Recipient email"},
            "variables": {"type": "object", "description": "Key-value pairs for placeholder substitution"}
        },
        "required": ["name", "to"]
    }
}

TOOL_EMAIL_FOLLOWUP = {
    "name": "email_followup",
    "description": "Track an email for follow-up. TARS will check if a reply was received before the deadline.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Subject of the sent email"},
            "to": {"type": "string", "description": "Recipient who should reply"},
            "deadline_hours": {"type": "integer", "description": "Hours to wait for reply (default 48)", "default": 48},
            "reminder_text": {"type": "string", "description": "Custom reminder text"}
        },
        "required": ["subject", "to"]
    }
}

TOOL_EMAIL_CHECK_FOLLOWUPS = {
    "name": "email_check_followups",
    "description": "Check for overdue follow-ups — emails that haven't received a reply past their deadline.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_CONTACT_LOOKUP = {
    "name": "email_contact_lookup",
    "description": "Look up an email address by contact name from macOS Contacts app.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Contact name to search for"}
        },
        "required": ["name"]
    }
}

TOOL_EMAIL_STATS = {
    "name": "email_stats",
    "description": "Get email statistics: unread count, inbox total, sent today, drafts count.",
    "input_schema": {"type": "object", "properties": {}}
}

# ── Auto-Rules ──
TOOL_EMAIL_ADD_RULE = {
    "name": "email_add_rule",
    "description": "Add a persistent auto-rule for incoming emails. Conditions: sender_contains, sender_is, subject_contains, subject_is, body_contains. Actions: move_to, flag, mark_read, delete, archive, forward_to, auto_reply, notify.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Human-readable rule name, e.g. 'Archive newsletters'"},
            "conditions": {
                "type": "object",
                "description": "Dict of conditions (AND logic). Keys: sender_contains, sender_is, subject_contains, subject_is, body_contains",
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "Action type: move_to, flag, mark_read, mark_unread, delete, archive, forward_to, auto_reply, notify"},
                        "value": {"type": "string", "description": "Action value (e.g. folder name for move_to, email for forward_to, reply text for auto_reply)"},
                    },
                    "required": ["action"],
                },
                "description": "List of actions to execute when conditions match",
            },
            "enabled": {"type": "boolean", "description": "Whether rule is active (default true)"},
        },
        "required": ["name", "conditions", "actions"],
    }
}

TOOL_EMAIL_LIST_RULES = {
    "name": "email_list_rules",
    "description": "List all email auto-rules with their conditions, actions, and hit counts.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_DELETE_RULE = {
    "name": "email_delete_rule",
    "description": "Delete an email auto-rule by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "The rule ID to delete"},
        },
        "required": ["rule_id"],
    }
}

TOOL_EMAIL_TOGGLE_RULE = {
    "name": "email_toggle_rule",
    "description": "Enable or disable an email auto-rule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "The rule ID to toggle"},
            "enabled": {"type": "boolean", "description": "True to enable, false to disable. Omit to toggle."},
        },
        "required": ["rule_id"],
    }
}

TOOL_EMAIL_RUN_RULES = {
    "name": "email_run_rules",
    "description": "Manually run all auto-rules against the top N inbox messages. Useful for applying rules to existing emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of inbox messages to process (default 20)"},
        },
    }
}

# ── Summarization & Threads ──
TOOL_EMAIL_SUMMARIZE = {
    "name": "email_summarize",
    "description": "Generate a structured inbox summary: grouped by priority (urgent/regular/newsletters), top senders, unread counts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to summarize (default 20)"},
        },
    }
}

TOOL_EMAIL_THREAD = {
    "name": "email_thread",
    "description": "Get all emails in a conversation thread by subject or message index. Groups related Re:/Fwd: emails chronologically.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {
                "oneOf": [
                    {"type": "string", "description": "Subject to search for"},
                    {"type": "integer", "description": "Message index to get thread for"},
                ],
            },
            "max_messages": {"type": "integer", "description": "Max messages to return (default 20)"},
        },
        "required": ["subject_or_index"],
    }
}

# ── Scheduling ──
TOOL_EMAIL_SCHEDULE = {
    "name": "email_schedule",
    "description": "Schedule an email to be sent at a specific time. The inbox monitor sends it automatically when the time arrives.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body"},
            "send_at": {
                "oneOf": [
                    {"type": "string", "description": "ISO timestamp (e.g. '2026-02-21T09:00:00')"},
                    {"type": "integer", "description": "Minutes from now (e.g. 60 = 1 hour)"},
                ],
                "description": "When to send: ISO timestamp or minutes from now",
            },
            "cc": {"type": "string", "description": "CC recipients"},
            "bcc": {"type": "string", "description": "BCC recipients"},
            "attachment_paths": {"type": "string", "description": "File path to attach"},
            "html": {"type": "boolean", "description": "Send as HTML"},
        },
        "required": ["to", "subject", "body", "send_at"],
    }
}

TOOL_EMAIL_LIST_SCHEDULED = {
    "name": "email_list_scheduled",
    "description": "List all pending scheduled emails with their send times.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_CANCEL_SCHEDULED = {
    "name": "email_cancel_scheduled",
    "description": "Cancel a scheduled email by its ID before it sends.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scheduled_id": {"type": "string", "description": "The scheduled email ID to cancel"},
        },
        "required": ["scheduled_id"],
    }
}

# ── Batch Operations ──
TOOL_EMAIL_BATCH_READ = {
    "name": "email_batch_mark_read",
    "description": "Mark multiple emails as read at once. Pass a list of indices, or set all_unread=true to mark everything.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of message indices to mark read"},
            "all_unread": {"type": "boolean", "description": "Mark ALL unread emails as read"},
            "mailbox": {"type": "string", "description": "Mailbox (default inbox)"},
        },
    }
}

TOOL_EMAIL_BATCH_DELETE = {
    "name": "email_batch_delete",
    "description": "Delete multiple emails at once. Pass indices list, or sender to delete all from a specific sender.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of message indices to delete"},
            "sender": {"type": "string", "description": "Delete all emails from this sender"},
            "mailbox": {"type": "string", "description": "Mailbox (default inbox)"},
        },
    }
}

TOOL_EMAIL_BATCH_MOVE = {
    "name": "email_batch_move",
    "description": "Move multiple emails to a folder at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of message indices to move"},
            "to_mailbox": {"type": "string", "description": "Destination folder"},
            "from_mailbox": {"type": "string", "description": "Source folder (default inbox)"},
        },
        "required": ["indices", "to_mailbox"],
    }
}

TOOL_EMAIL_BATCH_FORWARD = {
    "name": "email_batch_forward",
    "description": "Forward multiple emails to someone at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of message indices to forward"},
            "to": {"type": "string", "description": "Forward destination email address"},
            "body": {"type": "string", "description": "Optional message to include"},
            "mailbox": {"type": "string", "description": "Mailbox (default inbox)"},
        },
        "required": ["indices", "to"],
    }
}

# ─────────────────────────────────────────────
#  Phase 4: Smart Compose / Quick Replies
# ─────────────────────────────────────────────

TOOL_EMAIL_LIST_QUICK_REPLIES = {
    "name": "email_list_quick_replies",
    "description": "List all available quick reply templates (acknowledge, confirm_meeting, decline_meeting, will_review, follow_up, thank_you, out_of_office, request_info) plus any saved custom templates.",
    "input_schema": {
        "type": "object",
        "properties": {},
    }
}

TOOL_EMAIL_SEND_QUICK_REPLY = {
    "name": "email_send_quick_reply",
    "description": "Send a quick reply to an email using a predefined template. Types: acknowledge, confirm_meeting, decline_meeting, will_review, follow_up, thank_you, out_of_office, request_info. Can also use 'template:<name>' for custom saved templates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_index": {"type": "integer", "description": "Index of the email to reply to"},
            "reply_type": {"type": "string", "description": "Quick reply type (e.g. 'acknowledge', 'confirm_meeting', 'template:my_template')"},
            "mailbox": {"type": "string", "description": "Mailbox (default inbox)"},
            "custom_note": {"type": "string", "description": "Optional text appended after the template body"},
        },
        "required": ["message_index", "reply_type"],
    }
}

TOOL_EMAIL_SUGGEST_REPLIES = {
    "name": "email_suggest_replies",
    "description": "Analyze an email and suggest appropriate quick reply types based on its content. Returns suggested reply types with reasons.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message_index": {"type": "integer", "description": "Index of the email to analyze"},
            "mailbox": {"type": "string", "description": "Mailbox (default inbox)"},
        },
        "required": ["message_index"],
    }
}

# ── Phase 5: Categorization & Contact Management ──

TOOL_EMAIL_CATEGORIZE = {
    "name": "email_categorize",
    "description": "Auto-categorize inbox emails into priority/meeting/regular/newsletter/notification with confidence scores and tags.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to categorize (default 20)"},
        },
    }
}

TOOL_EMAIL_CONTACT_ADD = {
    "name": "email_contact_add",
    "description": "Add or update a contact in the TARS contacts database. If email already exists, updates name/tags/notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Contact name"},
            "email": {"type": "string", "description": "Contact email address"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags (e.g. ['vip', 'client', 'team'])"},
            "notes": {"type": "string", "description": "Notes about this contact"},
        },
        "required": ["name", "email"],
    }
}

TOOL_EMAIL_CONTACT_LIST = {
    "name": "email_contact_list",
    "description": "List all TARS-managed contacts, optionally filtered by tag.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tag": {"type": "string", "description": "Filter by tag (e.g. 'vip', 'client')"},
        },
    }
}

TOOL_EMAIL_CONTACT_SEARCH = {
    "name": "email_contact_search",
    "description": "Search contacts by name, email, tag, or notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }
}

TOOL_EMAIL_CONTACT_DELETE = {
    "name": "email_contact_delete",
    "description": "Delete a contact from the TARS contacts database by ID or email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "Contact ID"},
            "email": {"type": "string", "description": "Contact email (alternative to contact_id)"},
        },
    }
}

TOOL_EMAIL_AUTO_LEARN_CONTACTS = {
    "name": "email_auto_learn_contacts",
    "description": "Scan recent inbox to auto-discover contacts from email senders. Adds new senders to the contacts database with auto-learned tags.",
    "input_schema": {"type": "object", "properties": {}}
}

# ── Phase 6: Snooze / Priority / Digest ──

TOOL_EMAIL_SNOOZE = {
    "name": "email_snooze",
    "description": "Snooze an email — mark read now, resurface later by marking unread. Supports: '2h', '30m', '1d', 'tomorrow', 'monday', 'tonight', 'next_week', or ISO timestamp.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index, 1=newest"},
            "snooze_until": {"type": "string", "description": "When to resurface: '2h', '30m', '1d', 'tomorrow', 'monday', 'tonight', 'next_week', or ISO timestamp"},
            "mailbox": {"type": "string", "description": "Source mailbox", "default": "inbox"}
        },
        "required": ["index", "snooze_until"]
    }
}

TOOL_EMAIL_LIST_SNOOZED = {
    "name": "email_list_snoozed",
    "description": "List all snoozed emails with their resurface times.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_CANCEL_SNOOZE = {
    "name": "email_cancel_snooze",
    "description": "Cancel a snooze and immediately resurface the email (mark unread).",
    "input_schema": {
        "type": "object",
        "properties": {
            "snooze_id": {"type": "string", "description": "Snooze entry ID to cancel"}
        },
        "required": ["snooze_id"]
    }
}

TOOL_EMAIL_PRIORITY_INBOX = {
    "name": "email_priority_inbox",
    "description": "Get inbox sorted by 0-100 priority score. Factors: urgency keywords, sender reputation, recency, unread status, thread depth, category.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to score", "default": 20}
        }
    }
}

TOOL_EMAIL_SENDER_PROFILE = {
    "name": "email_sender_profile",
    "description": "Get detailed profile for a sender: message counts, frequency, relationship.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Sender name or email to look up"}
        },
        "required": ["query"]
    }
}

TOOL_EMAIL_DIGEST = {
    "name": "email_digest",
    "description": "Generate daily email briefing: stats overview, top priority emails, category breakdown, overdue follow-ups, snoozed emails resurfacing today.",
    "input_schema": {"type": "object", "properties": {}}
}
# ── Phase 7: OOO ──

TOOL_EMAIL_SET_OOO = {
    "name": "set_ooo",
    "description": "Set an out-of-office auto-reply for a date range. TARS will auto-reply to new emails during the period and auto-disable when the period ends.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date: ISO 'YYYY-MM-DD', 'today', or 'tomorrow'"},
            "end_date": {"type": "string", "description": "End date: ISO 'YYYY-MM-DD'"},
            "message": {"type": "string", "description": "Auto-reply message body"},
            "exceptions": {"type": "array", "items": {"type": "string"}, "description": "Email addresses/domains to NOT auto-reply to (optional)"}
        },
        "required": ["start_date", "end_date", "message"]
    }
}

TOOL_EMAIL_CANCEL_OOO = {
    "name": "cancel_ooo",
    "description": "Cancel the current out-of-office auto-reply.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_OOO_STATUS = {
    "name": "ooo_status",
    "description": "Check if out-of-office is active and get details (dates, message, reply count).",
    "input_schema": {"type": "object", "properties": {}}
}

# ── Phase 7: Analytics ──

TOOL_EMAIL_ANALYTICS = {
    "name": "email_analytics",
    "description": "Get comprehensive email analytics: volume stats, top communicators, follow-up rates, snooze stats, rule automation, OOO status, and email health score.",
    "input_schema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["day", "week", "month"], "description": "Analytics time period", "default": "week"}
        }
    }
}

TOOL_EMAIL_HEALTH = {
    "name": "email_health",
    "description": "Get email health score (0-100) with contributing factors: inbox zero progress, follow-up completion, snooze usage, rule automation, contact coverage. Includes letter grade.",
    "input_schema": {"type": "object", "properties": {}}
}

# ═══════════════════════════════════════════════════
#  PHASE 8: Inbox Zero + Attachments + Contact Intelligence
# ═══════════════════════════════════════════════════

TOOL_EMAIL_CLEAN_SWEEP = {
    "name": "clean_sweep",
    "description": "Bulk archive old low-priority emails to reach inbox zero. Preview with dry_run=true first. Targets newsletters, notifications, and promotional emails older than N days.",
    "input_schema": {
        "type": "object",
        "properties": {
            "older_than_days": {"type": "integer", "description": "Archive emails older than N days (default: 7)", "default": 7},
            "categories": {"type": "array", "items": {"type": "string"}, "description": "Categories to sweep: newsletter, notification, promotional. Default: all low-priority."},
            "dry_run": {"type": "boolean", "description": "True=preview only (default), False=actually archive", "default": True}
        }
    }
}

TOOL_EMAIL_AUTO_TRIAGE = {
    "name": "auto_triage",
    "description": "Auto-categorize latest inbox emails into priority/action_needed/FYI/archive_candidate with suggested next actions for each.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to triage (default: 20)", "default": 20}
        }
    }
}

TOOL_EMAIL_INBOX_ZERO_STATUS = {
    "name": "inbox_zero_status",
    "description": "Get current inbox zero progress: total email count, trend vs yesterday, streak (consecutive days at zero or declining), category breakdown.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_SMART_UNSUBSCRIBE = {
    "name": "smart_unsubscribe",
    "description": "Detect if an email is a newsletter/marketing and extract the unsubscribe link. Shows sender pattern and frequency.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index to check (1=newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox to look in (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_BUILD_ATTACHMENT_INDEX = {
    "name": "build_attachment_index",
    "description": "Scan inbox emails and build/update an index of all attachments (filename, size, sender, date, message index).",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to scan (default: 50)", "default": 50},
            "mailbox": {"type": "string", "description": "Mailbox to scan (default: inbox)", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_SEARCH_ATTACHMENTS = {
    "name": "search_attachments",
    "description": "Search the attachment index by filename, sender, or file type. Returns matching attachments with email context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Filename pattern to search for"},
            "sender": {"type": "string", "description": "Filter by sender email/name"},
            "file_type": {"type": "string", "description": "File type filter: pdf, xlsx, jpg, png, doc, zip, etc."},
            "max_results": {"type": "integer", "description": "Max results (default: 20)", "default": 20}
        }
    }
}

TOOL_EMAIL_ATTACHMENT_SUMMARY = {
    "name": "attachment_summary",
    "description": "Summary of email attachments: total count, total size, breakdown by file type, top senders with attachments.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to analyze (default: 50)", "default": 50}
        }
    }
}

TOOL_EMAIL_LIST_SAVED_ATTACHMENTS = {
    "name": "list_saved_attachments",
    "description": "List previously downloaded/saved attachments in TARS storage. Filter by folder or file type.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Subfolder to list (optional)"},
            "file_type": {"type": "string", "description": "File type filter: pdf, xlsx, jpg, etc. (optional)"}
        }
    }
}

TOOL_EMAIL_SCORE_RELATIONSHIPS = {
    "name": "score_relationships",
    "description": "Score all contacts by relationship strength (0-100) based on communication frequency, recency, reciprocity, and thread depth.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_DETECT_VIPS = {
    "name": "detect_vips",
    "description": "Auto-detect VIP contacts whose relationship score exceeds the threshold. Tags them as VIP in contacts database.",
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "description": "Score threshold for VIP detection (default: 70)", "default": 70}
        }
    }
}

TOOL_EMAIL_RELATIONSHIP_REPORT = {
    "name": "relationship_report",
    "description": "Detailed relationship report for a specific contact: message counts, frequency, reciprocity ratio, thread depth, last interaction, relationship strength score.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_query": {"type": "string", "description": "Contact name or email to report on"}
        },
        "required": ["contact_query"]
    }
}

TOOL_EMAIL_COMMUNICATION_GRAPH = {
    "name": "communication_graph",
    "description": "Top N communication partners ranked by relationship score with metrics (sent/received counts, last contact, reciprocity).",
    "input_schema": {
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "Number of top contacts to show (default: 15)", "default": 15}
        }
    }
}

TOOL_EMAIL_DECAY_CONTACTS = {
    "name": "decay_contacts",
    "description": "Decay stale contacts that haven't been active for N days. Reduces their priority/VIP status and returns list of decayed contacts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "inactive_days": {"type": "integer", "description": "Days of inactivity before decay (default: 90)", "default": 90}
        }
    }
}

# ── Phase 9: Security & Trust ──
TOOL_EMAIL_SCAN_SECURITY = {
    "name": "scan_email_security",
    "description": "Full security scan on an email: phishing score (0-100), suspicious link analysis, sender trust assessment, risk level (low/medium/high/critical).",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_CHECK_SENDER_TRUST = {
    "name": "check_sender_trust",
    "description": "Check sender trust score (0-100) based on contacts, communication history, domain reputation, trust/block lists.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sender_email": {"type": "string", "description": "Sender email to check"}
        },
        "required": ["sender_email"]
    }
}

TOOL_EMAIL_SCAN_LINKS = {
    "name": "scan_links",
    "description": "Extract and analyze all URLs in an email. Detects shortened URLs, IP-based links, typosquat domains, non-HTTPS links.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_SECURITY_REPORT = {
    "name": "security_report",
    "description": "Inbox-wide security report: scan latest N emails for threats. Returns risk distribution and flagged emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to scan", "default": 20}
        }
    }
}

TOOL_EMAIL_ADD_TRUSTED = {
    "name": "add_trusted_sender",
    "description": "Add an email address or @domain to the trusted senders list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "email_or_domain": {"type": "string", "description": "Email address or @domain to trust"},
            "reason": {"type": "string", "description": "Reason for trusting", "default": ""}
        },
        "required": ["email_or_domain"]
    }
}

TOOL_EMAIL_ADD_BLOCKED = {
    "name": "add_blocked_sender",
    "description": "Add an email address or @domain to the blocked senders list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "email_or_domain": {"type": "string", "description": "Email address or @domain to block"},
            "reason": {"type": "string", "description": "Reason for blocking", "default": ""}
        },
        "required": ["email_or_domain"]
    }
}

TOOL_EMAIL_LIST_TRUSTED = {
    "name": "list_trusted_senders",
    "description": "List all trusted senders and domains.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_LIST_BLOCKED = {
    "name": "list_blocked_senders",
    "description": "List all blocked senders and domains.",
    "input_schema": {"type": "object", "properties": {}}
}

# ── Phase 9: Action Items & Meetings ──
TOOL_EMAIL_EXTRACT_ACTIONS = {
    "name": "extract_action_items",
    "description": "Parse an email for action items: tasks, deadlines, requests. Saves them for tracking.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_EXTRACT_MEETING = {
    "name": "extract_meeting_details",
    "description": "Parse an email for meeting details: date/time, platform (Zoom/Teams/Meet/WebEx), link, location, attendees, agenda.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_SCAN_INBOX_ACTIONS = {
    "name": "scan_inbox_actions",
    "description": "Batch-scan latest emails for all action items and meetings. Returns counts and summaries.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to scan", "default": 20}
        }
    }
}

TOOL_EMAIL_CREATE_REMINDER = {
    "name": "create_reminder",
    "description": "Create a macOS Reminder from an extracted action item or email task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Reminder title"},
            "due_date": {"type": "string", "description": "Due date (e.g. 'March 15, 2026')"},
            "notes": {"type": "string", "description": "Additional notes", "default": ""},
            "source_email_subject": {"type": "string", "description": "Source email subject for context", "default": ""}
        },
        "required": ["title"]
    }
}

TOOL_EMAIL_CREATE_CALENDAR = {
    "name": "create_calendar_event",
    "description": "Create a Calendar.app event from extracted meeting details.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event title"},
            "start_datetime": {"type": "string", "description": "Start date/time (e.g. 'March 15, 2026 2:00 PM')"},
            "end_datetime": {"type": "string", "description": "End date/time"},
            "location": {"type": "string", "description": "Event location", "default": ""},
            "notes": {"type": "string", "description": "Event notes", "default": ""}
        },
        "required": ["title", "start_datetime"]
    }
}

TOOL_EMAIL_LIST_ACTIONS = {
    "name": "list_actions",
    "description": "List all extracted action items from emails. Filter by status: all, pending, completed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "Filter: all/pending/completed", "default": "all"}
        }
    }
}

TOOL_EMAIL_COMPLETE_ACTION = {
    "name": "complete_action",
    "description": "Mark an extracted action item as completed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action_id": {"type": "string", "description": "Action item ID (e.g. 'act_123')"}
        },
        "required": ["action_id"]
    }
}

TOOL_EMAIL_ACTION_SUMMARY = {
    "name": "action_summary",
    "description": "Dashboard summary of action items: pending count, completed count, urgent items, latest pending.",
    "input_schema": {"type": "object", "properties": {}}
}

# ── Phase 9: Workflow Chains ──
TOOL_EMAIL_CREATE_WORKFLOW = {
    "name": "create_workflow",
    "description": "Create a multi-step email workflow chain with trigger conditions and action steps.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_name": {"type": "string", "description": "Workflow name"},
            "trigger": {"type": "object", "description": "Trigger conditions: from_contains, subject_contains, from_vip, category, is_unread"},
            "steps": {"type": "array", "description": "Action steps: [{action, params, condition}]", "items": {"type": "object"}},
            "enabled": {"type": "boolean", "description": "Whether workflow is active", "default": True}
        },
        "required": ["workflow_name", "trigger", "steps"]
    }
}

TOOL_EMAIL_LIST_WORKFLOWS = {
    "name": "list_workflows",
    "description": "List all email workflows with trigger summaries and run counts.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_GET_WORKFLOW = {
    "name": "get_workflow",
    "description": "Get full workflow definition by ID: trigger, steps, run count, status.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Workflow ID"}
        },
        "required": ["workflow_id"]
    }
}

TOOL_EMAIL_DELETE_WORKFLOW = {
    "name": "delete_workflow",
    "description": "Delete a workflow by ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Workflow ID"}
        },
        "required": ["workflow_id"]
    }
}

TOOL_EMAIL_TOGGLE_WORKFLOW = {
    "name": "toggle_workflow",
    "description": "Enable or disable a workflow.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Workflow ID"},
            "enabled": {"type": "boolean", "description": "True=enable, False=disable"}
        },
        "required": ["workflow_id"]
    }
}

TOOL_EMAIL_RUN_WORKFLOW = {
    "name": "run_workflow",
    "description": "Manually trigger a workflow against a specific email. Executes all steps in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Workflow ID"},
            "index": {"type": "integer", "description": "Email index to run against", "default": 1},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": ["workflow_id"]
    }
}

TOOL_EMAIL_WORKFLOW_TEMPLATES = {
    "name": "workflow_templates",
    "description": "List built-in workflow templates: vip_urgent, newsletter_cleanup, team_forward, followup_escalation, auto_categorize_act.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_CREATE_FROM_TEMPLATE = {
    "name": "create_from_template",
    "description": "Create a workflow from a built-in template with optional parameter overrides.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_name": {"type": "string", "description": "Template name: vip_urgent, newsletter_cleanup, team_forward, followup_escalation, auto_categorize_act"},
            "template_params": {"type": "object", "description": "Optional parameter overrides for the template"}
        },
        "required": ["template_name"]
    }
}

TOOL_EMAIL_WORKFLOW_HISTORY = {
    "name": "workflow_history",
    "description": "Get workflow execution history: step results, timestamps, success rates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Filter by workflow ID (optional)"},
            "limit": {"type": "integer", "description": "Max entries to return", "default": 20}
        }
    }
}

# ═══════════════════════════════════════
#  Phase 10: Smart Compose & Writing Assistance
# ═══════════════════════════════════════

TOOL_EMAIL_SMART_COMPOSE = {
    "name": "smart_compose",
    "description": "AI-compose an email from a natural language prompt. Specify tone (formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic) and style (concise/detailed/bullet_points/executive_summary/action_oriented). Optionally provide context_email for reply context and recipient for personalization.",
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "What to write, e.g. 'apologize for delayed shipment, offer 20% discount'"},
            "tone": {"type": "string", "description": "Writing tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic", "default": "formal"},
            "style": {"type": "string", "description": "Writing style: concise/detailed/bullet_points/executive_summary/action_oriented", "default": "concise"},
            "context_email": {"type": "string", "description": "Previous email text for context (optional)"},
            "recipient": {"type": "string", "description": "Recipient name/email for personalization (optional)"}
        },
        "required": ["prompt"]
    }
}

TOOL_EMAIL_REWRITE = {
    "name": "rewrite_email",
    "description": "AI-rewrite existing email text in a new tone and/or style. Preserves meaning while transforming voice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Email text to rewrite"},
            "tone": {"type": "string", "description": "Target tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic", "default": "formal"},
            "style": {"type": "string", "description": "Target style: concise/detailed/bullet_points/executive_summary/action_oriented"}
        },
        "required": ["text"]
    }
}

TOOL_EMAIL_ADJUST_TONE = {
    "name": "adjust_tone",
    "description": "Change just the tone of existing email text without altering content or structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Email text to adjust"},
            "tone": {"type": "string", "description": "Target tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic"}
        },
        "required": ["text", "tone"]
    }
}

TOOL_EMAIL_SUGGEST_SUBJECTS = {
    "name": "suggest_subject_lines",
    "description": "Generate 5 subject line options from email body text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Email body text to generate subjects for"}
        },
        "required": ["text"]
    }
}

TOOL_EMAIL_PROOFREAD = {
    "name": "proofread_email",
    "description": "Proofread email text for grammar, spelling, clarity, and professionalism. Returns corrected text and list of issues found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Email text to proofread"}
        },
        "required": ["text"]
    }
}

TOOL_EMAIL_COMPOSE_REPLY_DRAFT = {
    "name": "compose_reply_draft",
    "description": "Read an email by index, then AI-draft a reply based on instructions. Returns the drafted reply text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index to reply to (1=newest)"},
            "instructions": {"type": "string", "description": "Instructions for the reply, e.g. 'politely decline, suggest next quarter'"},
            "tone": {"type": "string", "description": "Reply tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic", "default": "formal"},
            "mailbox": {"type": "string", "description": "Mailbox to read from", "default": "inbox"}
        },
        "required": ["index", "instructions"]
    }
}

# ═══════════════════════════════════════
#  Phase 10: Email Delegation & Task Assignment
# ═══════════════════════════════════════

TOOL_EMAIL_DELEGATE = {
    "name": "delegate_email",
    "description": "Delegate an email task to someone. Tracks the delegation with status, deadline, and instructions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index to delegate (1=newest)"},
            "delegate_to": {"type": "string", "description": "Person to delegate to (name or email)"},
            "instructions": {"type": "string", "description": "Instructions for the delegate"},
            "deadline_hours": {"type": "integer", "description": "Deadline in hours from now", "default": 24},
            "mailbox": {"type": "string", "description": "Mailbox to read from", "default": "inbox"}
        },
        "required": ["index", "delegate_to"]
    }
}

TOOL_EMAIL_LIST_DELEGATIONS = {
    "name": "list_delegations",
    "description": "List all email delegations. Optionally filter by status: pending, in_progress, completed, cancelled.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "Filter by status: pending/in_progress/completed/cancelled (optional)"}
        }
    }
}

TOOL_EMAIL_UPDATE_DELEGATION = {
    "name": "update_delegation",
    "description": "Update a delegation's status and/or notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "delegation_id": {"type": "string", "description": "Delegation ID"},
            "status": {"type": "string", "description": "New status: pending/in_progress/completed/cancelled"},
            "notes": {"type": "string", "description": "Update notes"}
        },
        "required": ["delegation_id"]
    }
}

TOOL_EMAIL_COMPLETE_DELEGATION = {
    "name": "complete_delegation",
    "description": "Mark a delegation as completed with an outcome description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "delegation_id": {"type": "string", "description": "Delegation ID"},
            "outcome": {"type": "string", "description": "Completion outcome/result"}
        },
        "required": ["delegation_id"]
    }
}

TOOL_EMAIL_CANCEL_DELEGATION = {
    "name": "cancel_delegation",
    "description": "Cancel a delegation with a reason.",
    "input_schema": {
        "type": "object",
        "properties": {
            "delegation_id": {"type": "string", "description": "Delegation ID"},
            "reason": {"type": "string", "description": "Cancellation reason"}
        },
        "required": ["delegation_id"]
    }
}

TOOL_EMAIL_DELEGATION_DASHBOARD = {
    "name": "delegation_dashboard",
    "description": "Get an overview of all delegations: totals, by status, overdue count, average completion time.",
    "input_schema": {"type": "object", "properties": {}}
}

TOOL_EMAIL_NUDGE_DELEGATION = {
    "name": "nudge_delegation",
    "description": "Send a reminder/nudge for an overdue or pending delegation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "delegation_id": {"type": "string", "description": "Delegation ID to nudge"}
        },
        "required": ["delegation_id"]
    }
}

# ═══════════════════════════════════════
#  Phase 10: Contextual Search & Email Memory
# ═══════════════════════════════════════

TOOL_EMAIL_CONTEXTUAL_SEARCH = {
    "name": "contextual_search",
    "description": "Natural language email search. Parses queries like 'emails from John about the project last week' into structured filters (sender, subject, date range, keywords).",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "max_results": {"type": "integer", "description": "Max results to return", "default": 20}
        },
        "required": ["query"]
    }
}

TOOL_EMAIL_BUILD_SEARCH_INDEX = {
    "name": "build_search_index",
    "description": "Rebuild the email search index from current inbox. Indexes subject, sender, date, and content keywords.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to index", "default": 100}
        }
    }
}

TOOL_EMAIL_CONVERSATION_RECALL = {
    "name": "conversation_recall",
    "description": "Recall full email conversation history with a specific contact. Optionally include an AI-generated summary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_query": {"type": "string", "description": "Contact name or email to recall conversations with"},
            "summarize": {"type": "boolean", "description": "Include AI-generated conversation summary", "default": False},
            "max_results": {"type": "integer", "description": "Max emails to retrieve", "default": 20}
        },
        "required": ["contact_query"]
    }
}

TOOL_EMAIL_SEARCH_DATE_RANGE = {
    "name": "search_by_date_range",
    "description": "Search emails within a specific date range, optionally filtered by keyword.",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD or 'today', 'yesterday', 'last_week')"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD or 'today')"},
            "keyword": {"type": "string", "description": "Optional keyword filter"},
            "max_results": {"type": "integer", "description": "Max results", "default": 20}
        },
        "required": ["start_date", "end_date"]
    }
}

TOOL_EMAIL_FIND_RELATED = {
    "name": "find_related_emails",
    "description": "Find emails related to a given email by matching subject, sender, and content keywords.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index to find related emails for (1=newest)"},
            "max_results": {"type": "integer", "description": "Max related emails to return", "default": 10},
            "mailbox": {"type": "string", "description": "Mailbox to search", "default": "inbox"}
        },
        "required": ["index"]
    }
}

# ── Phase 11A: Sentiment Analysis ──

TOOL_EMAIL_ANALYZE_SENTIMENT = {
    "name": "analyze_sentiment",
    "description": "Analyze the sentiment/tone of a single email. Returns score (-100 to +100), label (positive/negative/neutral), and detected keywords.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)"},
            "mailbox": {"type": "string", "description": "Mailbox to read from", "default": "inbox"}
        },
        "required": ["index"]
    }
}

TOOL_EMAIL_BATCH_SENTIMENT = {
    "name": "batch_sentiment",
    "description": "Analyze sentiment across multiple inbox emails at once. Returns stats: average score, positive/neutral/negative counts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to analyze", "default": 20},
            "mailbox": {"type": "string", "description": "Mailbox", "default": "inbox"}
        }
    }
}

TOOL_EMAIL_SENDER_SENTIMENT = {
    "name": "sender_sentiment",
    "description": "Get sentiment history and trends for a specific sender. Shows average score, trend direction, and recent analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sender_email": {"type": "string", "description": "Sender email address to look up"}
        },
        "required": ["sender_email"]
    }
}

TOOL_EMAIL_SENTIMENT_ALERTS = {
    "name": "sentiment_alerts",
    "description": "Flag emails with negative sentiment below a threshold score. Scans recent inbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "description": "Score threshold (emails below this are flagged)", "default": -20}
        }
    }
}

TOOL_EMAIL_SENTIMENT_REPORT = {
    "name": "sentiment_report",
    "description": "Sentiment analytics over a period. Shows average score, positive/negative breakdown, top negative senders, overall mood.",
    "input_schema": {
        "type": "object",
        "properties": {
            "period": {"type": "string", "description": "Time period: day, week, month", "default": "week"}
        }
    }
}

# ── Phase 11B: Smart Folders ──

TOOL_EMAIL_CREATE_SMART_FOLDER = {
    "name": "create_smart_folder",
    "description": "Create a dynamic smart folder with saved search criteria. The folder auto-executes its search when opened.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Folder name"},
            "criteria": {"type": "object", "description": "Search criteria: {from_contains, subject_contains, keyword, has_attachment, is_unread, is_flagged, exclude_from}"},
            "pinned": {"type": "boolean", "description": "Pin for quick access", "default": False}
        },
        "required": ["name", "criteria"]
    }
}

TOOL_EMAIL_LIST_SMART_FOLDERS = {
    "name": "list_smart_folders",
    "description": "List all smart folders with their criteria and access stats.",
    "input_schema": {
        "type": "object",
        "properties": {}
    }
}

TOOL_EMAIL_GET_SMART_FOLDER = {
    "name": "get_smart_folder",
    "description": "Execute a smart folder's saved search and return matching emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "description": "Smart folder ID"},
            "max_results": {"type": "integer", "description": "Max results to return", "default": 20}
        },
        "required": ["folder_id"]
    }
}

TOOL_EMAIL_UPDATE_SMART_FOLDER = {
    "name": "update_smart_folder",
    "description": "Update a smart folder's name or search criteria.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "description": "Smart folder ID"},
            "name": {"type": "string", "description": "New folder name (optional)"},
            "criteria": {"type": "object", "description": "New search criteria (optional)"}
        },
        "required": ["folder_id"]
    }
}

TOOL_EMAIL_DELETE_SMART_FOLDER = {
    "name": "delete_smart_folder",
    "description": "Delete a smart folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "description": "Smart folder ID to delete"}
        },
        "required": ["folder_id"]
    }
}

TOOL_EMAIL_PIN_SMART_FOLDER = {
    "name": "pin_smart_folder",
    "description": "Pin or unpin a smart folder for quick access.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_id": {"type": "string", "description": "Smart folder ID"},
            "pinned": {"type": "boolean", "description": "True to pin, False to unpin", "default": True}
        },
        "required": ["folder_id"]
    }
}

# ── Phase 11C: Thread Summarization ──

TOOL_EMAIL_SUMMARIZE_THREAD = {
    "name": "summarize_thread",
    "description": "AI-powered summary of an email thread. Returns key points, current status, and pending items.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject string or email index"},
            "max_messages": {"type": "integer", "description": "Max thread messages to include", "default": 20}
        },
        "required": ["subject_or_index"]
    }
}

TOOL_EMAIL_THREAD_DECISIONS = {
    "name": "thread_decisions",
    "description": "Extract key decisions made in an email thread. Lists what was decided, by whom, and when.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject string or email index"},
            "max_messages": {"type": "integer", "description": "Max thread messages", "default": 20}
        },
        "required": ["subject_or_index"]
    }
}

TOOL_EMAIL_THREAD_PARTICIPANTS = {
    "name": "thread_participants",
    "description": "Analyze who said what in a thread. Shows message counts, word counts, and participation breakdown per person.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject string or email index"},
            "max_messages": {"type": "integer", "description": "Max thread messages", "default": 20}
        },
        "required": ["subject_or_index"]
    }
}

TOOL_EMAIL_THREAD_TIMELINE = {
    "name": "thread_timeline",
    "description": "Generate a chronological timeline of events/messages in an email thread.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject string or email index"},
            "max_messages": {"type": "integer", "description": "Max thread messages", "default": 20}
        },
        "required": ["subject_or_index"]
    }
}

TOOL_EMAIL_PREPARE_FORWARD_SUMMARY = {
    "name": "prepare_forward_summary",
    "description": "Generate a TL;DR summary suitable for forwarding an email thread. Includes context, key points, status, and action needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject string or email index"},
            "recipient": {"type": "string", "description": "Who the thread will be forwarded to (for context)"},
            "max_messages": {"type": "integer", "description": "Max thread messages", "default": 20}
        },
        "required": ["subject_or_index"]
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 12A: EMAIL LABELS & TAGS
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_ADD_LABEL = {
    "name": "add_label",
    "description": "Add a custom label/tag to an email. Labels persist across sessions for organizing emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index, 1=newest", "default": 1},
            "label": {"type": "string", "description": "Label name (e.g. 'urgent', 'project-x', 'followup')"},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": ["label"]
    }
}

TOOL_EMAIL_REMOVE_LABEL = {
    "name": "remove_label",
    "description": "Remove a label from an email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index, 1=newest", "default": 1},
            "label": {"type": "string", "description": "Label name to remove"},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": ["label"]
    }
}

TOOL_EMAIL_LIST_LABELS = {
    "name": "list_labels",
    "description": "List all labels with email counts.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_GET_LABELED = {
    "name": "get_labeled_emails",
    "description": "Get all emails with a specific label.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Label to filter by"},
            "max_results": {"type": "integer", "description": "Max results", "default": 20}
        },
        "required": ["label"]
    }
}

TOOL_EMAIL_BULK_LABEL = {
    "name": "bulk_label",
    "description": "Apply a label to multiple emails at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of email indices"},
            "label": {"type": "string", "description": "Label to apply"},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": ["indices", "label"]
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 12B: NEWSLETTER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_DETECT_NEWSLETTERS = {
    "name": "detect_newsletters",
    "description": "Scan inbox for newsletter/subscription emails. Identifies sources and frequency.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to scan", "default": 30},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": []
    }
}

TOOL_EMAIL_NEWSLETTER_DIGEST = {
    "name": "newsletter_digest",
    "description": "Generate a digest of recent newsletters with previews.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to check", "default": 20},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"}
        },
        "required": []
    }
}

TOOL_EMAIL_NEWSLETTER_STATS = {
    "name": "newsletter_stats",
    "description": "Stats on newsletter volume, top sources, and preferences.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_NEWSLETTER_PREFS = {
    "name": "newsletter_preferences",
    "description": "Set preference per newsletter sender: keep, archive, or unsubscribe.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sender": {"type": "string", "description": "Newsletter sender email or name"},
            "pref_action": {"type": "string", "description": "Action: keep, archive, or unsubscribe", "enum": ["keep", "archive", "unsubscribe"]}
        },
        "required": ["sender", "pref_action"]
    }
}

TOOL_EMAIL_APPLY_NEWSLETTER_PREFS = {
    "name": "apply_newsletter_preferences",
    "description": "Apply saved newsletter preferences to inbox. Use dry_run=true for preview.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to process", "default": 30},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"},
            "dry_run": {"type": "boolean", "description": "Preview without applying", "default": True}
        },
        "required": []
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 12C: AUTO-RESPONDER
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_CREATE_AUTO_RESPONSE = {
    "name": "create_auto_response",
    "description": "Create a conditional auto-response rule. Replies automatically when conditions match.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Rule name"},
            "conditions": {"type": "object", "description": "Match conditions: {from_contains, subject_contains, body_contains, mailbox}"},
            "response_body": {"type": "string", "description": "Auto-reply text"},
            "response_subject": {"type": "string", "description": "Custom reply subject (optional)"},
            "enabled": {"type": "boolean", "description": "Enable rule", "default": True},
            "max_replies": {"type": "integer", "description": "Max auto-replies per sender per day", "default": 1}
        },
        "required": ["name", "conditions", "response_body"]
    }
}

TOOL_EMAIL_LIST_AUTO_RESPONSES = {
    "name": "list_auto_responses",
    "description": "List all auto-response rules with status and stats.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_UPDATE_AUTO_RESPONSE = {
    "name": "update_auto_response",
    "description": "Update an auto-response rule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "Auto-response rule ID"},
            "name": {"type": "string", "description": "New name"},
            "conditions": {"type": "object", "description": "New conditions"},
            "response_body": {"type": "string", "description": "New response text"},
            "max_replies": {"type": "integer", "description": "New max replies per sender per day"}
        },
        "required": ["rule_id"]
    }
}

TOOL_EMAIL_DELETE_AUTO_RESPONSE = {
    "name": "delete_auto_response",
    "description": "Delete an auto-response rule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "Auto-response rule ID"}
        },
        "required": ["rule_id"]
    }
}

TOOL_EMAIL_TOGGLE_AUTO_RESPONSE = {
    "name": "toggle_auto_response",
    "description": "Enable or disable an auto-response rule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rule_id": {"type": "string", "description": "Auto-response rule ID"},
            "enabled": {"type": "boolean", "description": "True to enable, false to disable"}
        },
        "required": ["rule_id"]
    }
}

TOOL_EMAIL_AUTO_RESPONSE_HISTORY = {
    "name": "auto_response_history",
    "description": "View history of sent auto-responses.",
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max history entries", "default": 20}
        },
        "required": []
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 13A: EMAIL SIGNATURES
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_CREATE_SIGNATURE = {
    "name": "create_signature",
    "description": "Create a reusable email signature.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Signature name"},
            "body": {"type": "string", "description": "Signature body text"},
            "is_html": {"type": "boolean", "description": "Whether body is HTML", "default": False}
        },
        "required": ["name", "body"]
    }
}

TOOL_EMAIL_LIST_SIGNATURES = {
    "name": "list_signatures",
    "description": "List all saved email signatures.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_UPDATE_SIGNATURE = {
    "name": "update_signature",
    "description": "Update an existing email signature.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sig_id": {"type": "string", "description": "Signature ID"},
            "name": {"type": "string", "description": "New name"},
            "body": {"type": "string", "description": "New body text"},
            "is_html": {"type": "boolean", "description": "Whether body is HTML"}
        },
        "required": ["sig_id"]
    }
}

TOOL_EMAIL_DELETE_SIGNATURE = {
    "name": "delete_signature",
    "description": "Delete an email signature.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sig_id": {"type": "string", "description": "Signature ID"}
        },
        "required": ["sig_id"]
    }
}

TOOL_EMAIL_SET_DEFAULT_SIGNATURE = {
    "name": "set_default_signature",
    "description": "Set a signature as the default.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sig_id": {"type": "string", "description": "Signature ID"}
        },
        "required": ["sig_id"]
    }
}

TOOL_EMAIL_GET_SIGNATURE = {
    "name": "get_signature",
    "description": "Get a specific signature by ID, or the default.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sig_id": {"type": "string", "description": "Signature ID (omit for default)"}
        },
        "required": []
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 13B: EMAIL ALIASES / IDENTITIES
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_ADD_ALIAS = {
    "name": "add_alias",
    "description": "Add a sender alias/identity.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alias_email": {"type": "string", "description": "Alias email address"},
            "display_name": {"type": "string", "description": "Display name"},
            "sig_id": {"type": "string", "description": "Linked signature ID (optional)"}
        },
        "required": ["alias_email"]
    }
}

TOOL_EMAIL_LIST_ALIASES = {
    "name": "list_aliases",
    "description": "List all sender aliases/identities.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_UPDATE_ALIAS = {
    "name": "update_alias",
    "description": "Update a sender alias.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alias_id": {"type": "string", "description": "Alias ID"},
            "alias_email": {"type": "string", "description": "New email"},
            "display_name": {"type": "string", "description": "New display name"},
            "sig_id": {"type": "string", "description": "New signature ID"}
        },
        "required": ["alias_id"]
    }
}

TOOL_EMAIL_DELETE_ALIAS = {
    "name": "delete_alias",
    "description": "Delete a sender alias.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alias_id": {"type": "string", "description": "Alias ID"}
        },
        "required": ["alias_id"]
    }
}

TOOL_EMAIL_SET_DEFAULT_ALIAS = {
    "name": "set_default_alias",
    "description": "Set a sender alias as the default.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alias_id": {"type": "string", "description": "Alias ID"}
        },
        "required": ["alias_id"]
    }
}

# ═══════════════════════════════════════════════════════════════════
#  PHASE 13C: EMAIL EXPORT / ARCHIVAL
# ═══════════════════════════════════════════════════════════════════

TOOL_EMAIL_EXPORT_EMAILS = {
    "name": "export_emails",
    "description": "Export recent emails to a JSON or text file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to export", "default": 10},
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"},
            "export_format": {"type": "string", "description": "Export format: json or txt", "enum": ["json", "txt"]}
        },
        "required": []
    }
}

TOOL_EMAIL_EXPORT_THREAD = {
    "name": "export_thread",
    "description": "Export a full email thread to a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_or_index": {"type": "string", "description": "Thread subject or email index"},
            "export_format": {"type": "string", "description": "Export format: json or txt", "enum": ["json", "txt"]}
        },
        "required": ["subject_or_index"]
    }
}

TOOL_EMAIL_BACKUP_MAILBOX = {
    "name": "backup_mailbox",
    "description": "Create a full backup of a mailbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mailbox": {"type": "string", "description": "Mailbox name", "default": "inbox"},
            "max_emails": {"type": "integer", "description": "Max emails to back up", "default": 100}
        },
        "required": []
    }
}

TOOL_EMAIL_LIST_BACKUPS = {
    "name": "list_backups",
    "description": "List all email exports and backups.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_SEARCH_EXPORTS = {
    "name": "search_exports",
    "description": "Search through exported/backed-up emails by keyword.",
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Keyword to search for"}
        },
        "required": ["keyword"]
    }
}

TOOL_EMAIL_EXPORT_STATS = {
    "name": "export_stats",
    "description": "Stats on email exports and backups.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

# ── Phase 14: Email Templates ──

TOOL_EMAIL_CREATE_TEMPLATE = {
    "name": "create_template",
    "description": "Create a reusable email template with {{variable}} placeholders.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Template name"},
            "subject_template": {"type": "string", "description": "Subject with {{var}} placeholders"},
            "body_template": {"type": "string", "description": "Body with {{var}} placeholders"},
            "category": {"type": "string", "description": "Template category", "default": "general"}
        },
        "required": ["name", "body_template"]
    }
}

TOOL_EMAIL_LIST_TEMPLATES = {
    "name": "list_templates",
    "description": "List all email templates (optional category filter).",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Filter by category"}
        },
        "required": []
    }
}

TOOL_EMAIL_GET_TEMPLATE = {
    "name": "get_template",
    "description": "Get a specific email template by ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_id": {"type": "string", "description": "Template ID"}
        },
        "required": ["template_id"]
    }
}

TOOL_EMAIL_UPDATE_TEMPLATE = {
    "name": "update_template",
    "description": "Update an email template.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_id": {"type": "string", "description": "Template ID"},
            "name": {"type": "string", "description": "New name"},
            "subject_template": {"type": "string", "description": "New subject template"},
            "body_template": {"type": "string", "description": "New body template"},
            "category": {"type": "string", "description": "New category"}
        },
        "required": ["template_id"]
    }
}

TOOL_EMAIL_DELETE_TEMPLATE = {
    "name": "delete_template",
    "description": "Delete an email template.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_id": {"type": "string", "description": "Template ID"}
        },
        "required": ["template_id"]
    }
}

TOOL_EMAIL_USE_TEMPLATE = {
    "name": "use_template",
    "description": "Render a template with variable substitutions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "template_id": {"type": "string", "description": "Template ID"},
            "variables": {"type": "object", "description": "Variable substitutions {key: value}"}
        },
        "required": ["template_id"]
    }
}

# ── Phase 15: Email Drafts ──

TOOL_EMAIL_SAVE_DRAFT_MANAGED = {
    "name": "save_draft",
    "description": "Save an email as a draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient"},
            "subject": {"type": "string", "description": "Subject"},
            "body": {"type": "string", "description": "Body"},
            "cc": {"type": "string", "description": "CC"},
            "bcc": {"type": "string", "description": "BCC"}
        },
        "required": []
    }
}

TOOL_EMAIL_LIST_DRAFTS_MANAGED = {
    "name": "list_drafts_managed",
    "description": "List all saved email drafts.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_GET_DRAFT = {
    "name": "get_draft",
    "description": "Get a specific draft by ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string", "description": "Draft ID"}
        },
        "required": ["draft_id"]
    }
}

TOOL_EMAIL_UPDATE_DRAFT = {
    "name": "update_draft",
    "description": "Update a saved draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string", "description": "Draft ID"},
            "to": {"type": "string", "description": "Recipient"},
            "subject": {"type": "string", "description": "Subject"},
            "body": {"type": "string", "description": "Body"},
            "cc": {"type": "string", "description": "CC"},
            "bcc": {"type": "string", "description": "BCC"}
        },
        "required": ["draft_id"]
    }
}

TOOL_EMAIL_DELETE_DRAFT_MANAGED = {
    "name": "delete_draft",
    "description": "Delete a saved draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_id": {"type": "string", "description": "Draft ID"}
        },
        "required": ["draft_id"]
    }
}

# ── Phase 16: Folder Management ──

TOOL_EMAIL_CREATE_MAIL_FOLDER = {
    "name": "create_mail_folder",
    "description": "Create a new mailbox folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_name": {"type": "string", "description": "Folder name"},
            "parent": {"type": "string", "description": "Parent folder (optional)"}
        },
        "required": ["folder_name"]
    }
}

TOOL_EMAIL_LIST_MAIL_FOLDERS = {
    "name": "list_mail_folders",
    "description": "List all mailbox folders.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_RENAME_MAIL_FOLDER = {
    "name": "rename_mail_folder",
    "description": "Rename a mailbox folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_name": {"type": "string", "description": "Current folder name"},
            "new_name": {"type": "string", "description": "New folder name"}
        },
        "required": ["folder_name", "new_name"]
    }
}

TOOL_EMAIL_DELETE_MAIL_FOLDER = {
    "name": "delete_mail_folder",
    "description": "Delete a mailbox folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_name": {"type": "string", "description": "Folder name to delete"}
        },
        "required": ["folder_name"]
    }
}

TOOL_EMAIL_MOVE_TO_FOLDER = {
    "name": "move_to_folder",
    "description": "Move an email to a specific folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)"},
            "folder_name": {"type": "string", "description": "Target folder name"}
        },
        "required": ["folder_name"]
    }
}

TOOL_EMAIL_GET_FOLDER_STATS = {
    "name": "get_folder_stats",
    "description": "Get email count per folder.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

# ── Phase 17: Email Tracking ──

TOOL_EMAIL_TRACK_EMAIL = {
    "name": "track_email",
    "description": "Track a sent email for reply status.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Email subject"},
            "recipient": {"type": "string", "description": "Recipient email"},
            "sent_at": {"type": "string", "description": "When sent (ISO)"}
        },
        "required": ["subject"]
    }
}

TOOL_EMAIL_LIST_TRACKED = {
    "name": "list_tracked_emails",
    "description": "List all tracked emails.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_GET_TRACKING_STATUS = {
    "name": "get_tracking_status",
    "description": "Get tracking details for a specific email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tracking_id": {"type": "string", "description": "Tracking ID"}
        },
        "required": ["tracking_id"]
    }
}

TOOL_EMAIL_TRACKING_REPORT = {
    "name": "tracking_report",
    "description": "Generate tracking summary report.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_UNTRACK = {
    "name": "untrack_email",
    "description": "Stop tracking an email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tracking_id": {"type": "string", "description": "Tracking ID"}
        },
        "required": ["tracking_id"]
    }
}

# ── Phase 18: Extended Batch Operations ──

TOOL_EMAIL_BATCH_ARCHIVE = {
    "name": "batch_archive",
    "description": "Archive multiple emails at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "Email indices to archive"}
        },
        "required": ["indices"]
    }
}

TOOL_EMAIL_BATCH_REPLY = {
    "name": "batch_reply",
    "description": "Send the same reply to multiple emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indices": {"type": "array", "items": {"type": "integer"}, "description": "Email indices to reply to"},
            "body": {"type": "string", "description": "Reply body text"}
        },
        "required": ["indices", "body"]
    }
}

# ── Phase 19: Calendar Integration ──

TOOL_EMAIL_TO_EVENT = {
    "name": "email_to_event",
    "description": "Create a calendar event from an email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Email index (1=newest)", "default": 1},
            "calendar_name": {"type": "string", "description": "Calendar name (optional)"}
        },
        "required": []
    }
}

TOOL_EMAIL_LIST_EMAIL_EVENTS = {
    "name": "list_email_events",
    "description": "List all calendar events created from emails.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_UPCOMING_FROM_EMAIL = {
    "name": "upcoming_from_email",
    "description": "Show upcoming events created from emails.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Days to look back", "default": 7}
        },
        "required": []
    }
}

TOOL_EMAIL_MEETING_CONFLICTS = {
    "name": "meeting_conflicts",
    "description": "Check for meeting conflicts on a date.",
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "Date YYYY-MM-DD"}
        },
        "required": []
    }
}

TOOL_EMAIL_SYNC_CALENDAR = {
    "name": "sync_email_calendar",
    "description": "Email calendar sync summary.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

# ── Phase 20: Dashboard & Reporting ──

TOOL_EMAIL_DASHBOARD = {
    "name": "email_dashboard",
    "description": "Comprehensive email dashboard overview.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_WEEKLY_REPORT = {
    "name": "weekly_report",
    "description": "Weekly email activity summary.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_MONTHLY_REPORT = {
    "name": "monthly_report",
    "description": "Monthly email activity summary.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_PRODUCTIVITY_SCORE = {
    "name": "productivity_score",
    "description": "Email productivity rating 0-100.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

TOOL_EMAIL_TRENDS = {
    "name": "email_trends",
    "description": "Email trend analysis over time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Number of days to analyze", "default": 30}
        },
        "required": []
    }
}