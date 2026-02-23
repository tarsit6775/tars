"""
╔══════════════════════════════════════════╗
║      TARS — Voice: iMessage Sender       ║
╚══════════════════════════════════════════╝

Sends iMessages to Abdullah via AppleScript.

Features:
  - Smart splitting: long messages split at sentence boundaries
    (never truncated with "...")
  - File attachments: send images, PDFs, reports via iMessage
  - Minimal rate limit: 1.5s between sends (just enough to prevent
    Messages.app from choking, not enough to feel slow)
"""

import os
import re
import sqlite3
import subprocess
import time
import logging

logger = logging.getLogger("TARS")

# Path to the Messages database — used for delivery verification.
_CHAT_DB = os.path.expanduser("~/Library/Messages/chat.db")

# Minimum gap between sends — prevents Messages.app from dropping
# messages when they arrive too fast, but keeps conversation snappy.
_MIN_SEND_GAP = 1.5  # seconds


class IMessageSender:
    def __init__(self, config):
        self.phone = config["imessage"]["owner_phone"]
        self.max_length = config["imessage"].get("max_message_length", 1600)
        self.phone_to_email = config.get("imessage", {}).get("owner_email", "tarsitgroup@outlook.com")
        self._last_sent_time = 0

    # ── Primary: send a text message ──────────────────────

    def send(self, message):
        """Send an iMessage. Long messages are split into multiple parts.

        Returns the standard tool result dict.  If the message exceeds
        max_length it is split at the nearest sentence boundary and each
        chunk is sent as a separate iMessage (with a tiny gap so they
        arrive in order).
        """
        if not message or not message.strip():
            return {"success": True, "content": "Empty message — skipped."}

        # Split into chunks if too long
        chunks = self._split_message(message)

        last_result = None
        for i, chunk in enumerate(chunks):
            # Rate limit — short gap between consecutive sends
            self._wait_rate_limit()
            last_result = self._send_raw(chunk)
            if not last_result.get("success"):
                return last_result  # Abort on first failure

        sent_label = f"{len(chunks)} parts" if len(chunks) > 1 else "1 message"
        return {"success": True, "content": f"iMessage sent ({sent_label}) to {self.phone}"}

    # ── File / attachment sending ─────────────────────────

    def send_file(self, file_path, caption=None):
        """Send a file (image, PDF, report, etc.) via iMessage.

        Uses the Finder-copy → Messages-paste approach which goes through
        the UI send pipeline (same as drag-and-drop).  The old AppleScript
        `send POSIX file` scripting bridge is broken on macOS 26 — it
        creates messages with transfer_state=6 (iCloud upload failure)
        even though iCloud works fine for UI-initiated sends.

        After sending, verifies delivery via chat.db.  If the attachment
        is stuck, falls back to email delivery.

        Args:
            file_path: Absolute path to the file to send.
            caption:   Optional text message sent right before the file.

        Returns the standard tool result dict.
        """
        file_path = os.path.expanduser(file_path)
        if not os.path.isfile(file_path):
            return {"success": False, "error": True,
                    "content": f"File not found: {file_path}"}

        # Send caption first (if provided)
        if caption:
            self._wait_rate_limit()
            cap_result = self._send_raw(caption)
            if not cap_result.get("success"):
                return cap_result

        self._wait_rate_limit()
        fname = os.path.basename(file_path)

        # ── Primary: Finder-copy → Messages-paste ──
        # This simulates drag-and-drop which uses the working UI pipeline.
        result = self._send_file_via_paste(file_path)

        if result.get("success"):
            # Verify delivery via chat.db
            delivered = self._verify_file_delivery(file_path)
            if delivered:
                logger.info(f"  📎 File delivered via iMessage: {fname}")
                return {"success": True,
                        "content": f"File '{fname}' sent via iMessage to {self.phone}"}

            # Paste worked but delivery still stuck — email fallback
            logger.warning(f"  ⚠️ iMessage attachment stuck, falling back to email")
            return self._email_fallback(file_path, fname, caption)

        # Paste failed — try legacy AppleScript send as fallback
        logger.warning(f"  ⚠️ Paste method failed, trying AppleScript send")
        legacy = self._send_file_via_applescript(file_path)
        if legacy.get("success"):
            delivered = self._verify_file_delivery(file_path)
            if delivered:
                logger.info(f"  📎 File delivered via iMessage (legacy): {fname}")
                return {"success": True,
                        "content": f"File '{fname}' sent via iMessage to {self.phone}"}

            logger.warning(f"  ⚠️ iMessage attachment stuck, falling back to email")
            return self._email_fallback(file_path, fname, caption)

        return {"success": False, "error": True,
                "content": f"iMessage file send failed: {legacy.get('content', 'unknown')}"}

    def _send_file_via_paste(self, file_path):
        """Send file by copying in Finder and pasting into Messages compose field.

        This uses the same pipeline as manual drag-and-drop, which works
        even when the AppleScript scripting bridge is broken.
        """
        # Guard clipboard and focus — restore after we're done
        from hands.environment import clipboard_save, clipboard_restore, focus_save, focus_restore
        clipboard_save()
        focus_save()

        try:
            return self._send_file_via_paste_inner(file_path)
        finally:
            clipboard_restore()
            focus_restore()

    def _send_file_via_paste_inner(self, file_path):
        """Inner paste logic (wrapped by clipboard/focus guards)."""
        # Ensure the conversation is open before pasting
        self._ensure_conversation_open()

        script = f'''
        -- Step 1: Select and copy the file in Finder
        tell application "Finder"
            activate
            set theFile to POSIX file "{file_path}" as alias
            select theFile
            delay 0.3
        end tell

        tell application "System Events"
            tell process "Finder"
                keystroke "c" using command down
            end tell
        end tell

        delay 0.5

        -- Step 2: Switch to Messages and paste into compose field
        tell application "Messages"
            activate
        end tell

        delay 1

        -- Step 3: Paste (file appears as inline attachment) and send
        tell application "System Events"
            tell process "Messages"
                keystroke "v" using command down
                delay 2
                key code 36
            end tell
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=30
            )
            self._last_sent_time = time.time()

            if result.returncode == 0:
                return {"success": True, "content": "File pasted and sent"}
            else:
                return {"success": False, "error": True,
                        "content": result.stderr.strip()}
        except Exception as e:
            return {"success": False, "error": True, "content": str(e)}

    def _send_file_via_applescript(self, file_path):
        """Legacy: send file via AppleScript 'send POSIX file' command.

        This is the old approach that breaks on macOS 26 with iCloud
        transfer_state=6.  Kept as fallback in case paste fails.
        """
        script = f'''
        on run argv
            set filePath to POSIX file (item 1 of argv)
            tell application "Messages"
                set targetService to 1st account whose service type = iMessage
                set targetBuddy to participant "{self.phone}" of targetService
                send filePath to targetBuddy
            end tell
        end run
        '''

        last_err = None
        for attempt in range(2):
            try:
                result = subprocess.run(
                    ["osascript", "-e", script, file_path],
                    capture_output=True, text=True, timeout=30
                )
                self._last_sent_time = time.time()
                if result.returncode == 0:
                    return {"success": True, "content": "Sent via AppleScript"}
                else:
                    last_err = result.stderr.strip()
            except Exception as e:
                last_err = str(e)
            if attempt < 1:
                time.sleep(1)

        return {"success": False, "error": True,
                "content": f"AppleScript send failed: {last_err}"}

    def _ensure_conversation_open(self):
        """Make sure the Messages app has the right conversation open."""
        script = f'''
        tell application "Messages"
            activate
        end tell
        delay 0.5
        -- Click on the correct conversation if needed
        tell application "System Events"
            tell process "Messages"
                -- Use Cmd+N then type the contact, or just make sure window is frontmost
                set frontmost to true
            end tell
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=10)
        except Exception:
            pass

    # ── Delivery verification & fallback ─────────────────

    def _verify_file_delivery(self, file_path, timeout=8):
        """Check chat.db to see if the latest outgoing attachment delivered.

        Messages.app uploads attachments to iCloud before marking them
        as sent.  transfer_state meanings:
          5 = sent/delivered
          6 = failed / stuck (iCloud upload error)

        Returns True if delivered, False if stuck/failed.
        """
        fname = os.path.basename(file_path)
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                with sqlite3.connect(_CHAT_DB) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.execute(
                        """
                        SELECT a.transfer_state, m.is_sent, m.is_delivered
                        FROM message m
                        JOIN message_attachment_join maj ON m.rowid = maj.message_id
                        JOIN attachment a ON maj.attachment_id = a.rowid
                        WHERE m.is_from_me = 1
                        ORDER BY m.date DESC
                        LIMIT 1
                        """
                    )
                    row = cur.fetchone()

                if row:
                    state = row["transfer_state"]
                    if state == 5:
                        return True   # delivered
                    if state == 6:
                        return False  # stuck / iCloud error
                    # Still in-progress (state < 5), keep waiting
            except Exception:
                pass

            time.sleep(1.5)

        return False  # timed out — assume stuck

    def _email_fallback(self, file_path, fname, caption=None):
        """Send the file via email when iMessage attachment delivery fails.

        Returns the standard tool result dict.
        """
        try:
            from hands.mac_control import mail_send
        except ImportError:
            return {"success": False, "error": True,
                    "content": f"iMessage attachment stuck (iCloud sync issue). "
                               f"Email fallback unavailable — mail_send not found."}

        subject = f"TARS File: {fname}"
        body = caption or f"Attached: {fname}"
        body += "\n\n(Sent via email — iMessage attachment delivery is temporarily unavailable due to iCloud sync.)"

        try:
            email_result = mail_send(
                to_address=self.phone_to_email,
                subject=subject,
                body=body,
                attachment_path=file_path,
            )

            if email_result.get("success"):
                # Notify via text iMessage that file was emailed
                self._wait_rate_limit()
                self._send_raw(f"📎 Sent '{fname}' to your email instead — iMessage attachments are temporarily down (iCloud sync issue).")
                return {"success": True,
                        "content": f"iMessage attachment stuck (iCloud). File '{fname}' sent via email as fallback."}
            else:
                return {"success": False, "error": True,
                        "content": f"iMessage attachment stuck AND email fallback failed: {email_result.get('content', 'unknown')}"}
        except Exception as e:
            return {"success": False, "error": True,
                    "content": f"iMessage attachment stuck AND email fallback error: {e}"}

    # ── Internals ─────────────────────────────────────────

    def _wait_rate_limit(self):
        """Sleep just long enough to respect the minimum send gap."""
        elapsed = time.time() - self._last_sent_time
        if elapsed < _MIN_SEND_GAP:
            time.sleep(_MIN_SEND_GAP - elapsed)

    def _send_raw(self, text):
        """Send a single text chunk via AppleScript. No splitting, no rate logic."""
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
                    ["osascript", "-e", script, text],
                    capture_output=True, text=True, timeout=15
                )
                self._last_sent_time = time.time()

                if result.returncode == 0:
                    return {"success": True, "content": f"iMessage sent to {self.phone}"}
                else:
                    last_err = result.stderr.strip()
            except Exception as e:
                last_err = str(e)

            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))

        return {"success": False, "error": True,
                "content": f"iMessage failed after 3 attempts: {last_err}"}

    def _split_message(self, message):
        """Split a message into chunks that fit within max_length.

        Strategy:
          1. If it fits → return as-is.
          2. Split at paragraph boundaries (double newline).
          3. Within a paragraph, split at sentence boundaries (. ! ?).
          4. Last resort: hard-split at max_length.

        Returns a list of strings, each ≤ max_length.
        """
        message = message.strip()
        if len(message) <= self.max_length:
            return [message]

        chunks = []
        # First try splitting by paragraphs
        paragraphs = re.split(r'\n\s*\n', message)

        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Would adding this paragraph exceed the limit?
            candidate = f"{current}\n\n{para}" if current else para
            if len(candidate) <= self.max_length:
                current = candidate
            else:
                # Flush current chunk
                if current:
                    chunks.append(current.strip())
                    current = ""

                # Does this paragraph alone fit?
                if len(para) <= self.max_length:
                    current = para
                else:
                    # Split the paragraph at sentence boundaries
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    for sent in sentences:
                        candidate = f"{current} {sent}" if current else sent
                        if len(candidate) <= self.max_length:
                            current = candidate
                        else:
                            if current:
                                chunks.append(current.strip())
                            # If single sentence > max_length, hard-split
                            if len(sent) > self.max_length:
                                while sent:
                                    chunks.append(sent[:self.max_length])
                                    sent = sent[self.max_length:]
                                current = ""
                            else:
                                current = sent

        if current.strip():
            chunks.append(current.strip())

        return chunks if chunks else [message[:self.max_length]]
