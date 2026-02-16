"""
╔══════════════════════════════════════════╗
║       TARS — Hands: Terminal Runner      ║
╚══════════════════════════════════════════╝

Runs shell commands and captures output.
"""

import subprocess
import os
from utils.safety import is_destructive


def run_terminal(command, timeout=60, cwd=None):
    """Run a shell command and return the output."""
    # Safety: block destructive commands
    if is_destructive(command):
        return {
            "success": False,
            "error": True,
            "content": f"⛔ BLOCKED: Destructive command detected: {command}\nIf you really need this, ask Abdullah for confirmation via send_imessage.",
        }
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.getcwd(),
            env={**os.environ, "TERM": "dumb"},  # Prevent color codes
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"

        # Truncate very long output
        if len(output) > 10000:
            output = output[:5000] + "\n\n... [output truncated] ...\n\n" + output[-3000:]

        return {
            "success": result.returncode == 0,
            "content": output.strip() or "(no output)",
            "exit_code": result.returncode,
            "error": result.returncode != 0,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": True,
            "content": f"Command timed out after {timeout}s: {command}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": True,
            "content": f"Failed to run command: {e}",
        }
