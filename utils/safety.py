"""
╔══════════════════════════════════════════╗
║       TARS — Utilities: Safety           ║
╚══════════════════════════════════════════╝

Guardrails, destructive action detection, kill switch.
"""

import re

# Patterns that indicate destructive actions
DESTRUCTIVE_PATTERNS = [
    # File destruction
    r"rm\s+(-[rRf]+|--recursive|--force)",
    r"rmdir",
    r":\s*>\s*/",                      # truncate files
    r"mv\s+.*/dev/null",
    # Git force operations
    r"git\s+push\s+.*--force",
    r"git\s+push\s+-f",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-[dfx]+",
    # Database destruction
    r"DROP\s+(TABLE|DATABASE|INDEX)",
    r"DELETE\s+FROM",
    r"TRUNCATE\s+TABLE",
    # Disk / system
    r"mkfs\.",
    r"dd\s+if=",
    r"format\s+",
    r"diskutil\s+(erase|partition|unmount)",
    r">/dev/",
    r"chmod\s+(000|777)",
    # Privilege escalation
    r"sudo\s+rm",
    r"sudo\s+dd",
    r"sudo\s+mkfs",
    r"sudo\s+reboot",
    r"sudo\s+shutdown",
    r"sudo\s+halt",
    # System control
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bhalt\b",
    r"launchctl\s+(unload|remove)",
    r"killall\s+",
    r"pkill\s+-9\s+",
    # Remote code execution
    r"curl\s+.*\|\s*(bash|sh|zsh)",
    r"wget\s+.*\|\s*(bash|sh|zsh)",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"python.*-c.*import\s+os.*system",
    # Fork bombs / resource exhaustion  
    r":\(\)\{\s*:\|",                    # bash fork bomb
    # Additional dangerous patterns
    r"find\s+.*-delete",
    r"find\s+.*-exec\s+rm",
    r"xargs\s+rm",
    r"perl\s+-e\s+.*unlink",
    r"python.*-c.*os\.(remove|unlink|rmdir|rmtree)",
    r"`[^`]*rm\s",                       # backtick substitution with rm
    r"\$\([^)]*rm\s",                    # $() substitution with rm
    r"crontab\s+-r",                     # remove all cron jobs
    r"networksetup\s+-setdnsservers",    # DNS hijack
    # Shell chaining to bypass prefix checks
    r";\s*(rm|curl|wget|dd|mkfs|shutdown|reboot)",   # semicolon chaining
    r"\|\s*(bash|sh|zsh|python)",        # pipe-to-shell (generic)
    r"base64\s+.*-[dD].*\|\s*(bash|sh)", # base64 decode to shell
    r"python.*-c.*subprocess",           # python subprocess injection
    r"mv\s+.*~/Library/LaunchAgents",    # persistence via LaunchAgents
    r"osascript\s+-e.*do\s+shell\s+script", # AppleScript shell escape
    r"defaults\s+write.*LSUIElement",    # hide app from dock (stealth)
]


def is_destructive(command):
    """Check if a shell command looks destructive."""
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def is_path_allowed(path, allowed_paths):
    """Check if a file path is within allowed paths. Empty = all allowed."""
    if not allowed_paths:
        return True
    import os
    path = os.path.abspath(os.path.expanduser(path))
    for allowed in allowed_paths:
        allowed = os.path.abspath(os.path.expanduser(allowed))
        if path.startswith(allowed):
            return True
    return False
