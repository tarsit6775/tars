"""
╔══════════════════════════════════════════╗
║      TARS — Voice: iMessage Sender       ║
╚══════════════════════════════════════════╝

Sends iMessages to Abdullah via AppleScript.
"""

import subprocess
import time


class IMessageSender:
    def __init__(self, config):
        self.phone = config["imessage"]["owner_phone"]
        self.rate_limit = config["imessage"]["rate_limit"]
        self.max_length = config["imessage"]["max_message_length"]
        self._last_sent_time = 0

    def send(self, message):
        """Send an iMessage. Respects rate limiting."""
        # Rate limit
        now = time.time()
        elapsed = now - self._last_sent_time
        if elapsed < self.rate_limit:
            wait = self.rate_limit - elapsed
            time.sleep(wait)

        # Truncate if needed
        if len(message) > self.max_length:
            message = message[:self.max_length - 20] + "\n\n... (truncated)"

        # Use stdin pipe to avoid AppleScript injection — message content never
        # enters the AppleScript string evaluation context.
        script = f'''
        on run argv
            set msg to item 1 of argv
            tell application "Messages"
                set targetService to 1st account whose service type = iMessage
                set targetBuddy to participant "{self.phone}" of targetService
                send msg to targetBuddy
            end tell
        end run
        '''

        last_err = None
        for attempt in range(3):
            try:
                result = subprocess.run(
                    ["osascript", "-e", script, message],
                    capture_output=True, text=True, timeout=15
                )
                self._last_sent_time = time.time()

                if result.returncode == 0:
                    return {"success": True, "content": f"iMessage sent to {self.phone}"}
                else:
                    last_err = result.stderr.strip()
            except Exception as e:
                last_err = str(e)

            # Backoff before retry (0.5s, 1.5s)
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))

        return {"success": False, "error": True, "content": f"iMessage failed after 3 attempts: {last_err}"}
