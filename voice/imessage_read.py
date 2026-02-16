"""
╔══════════════════════════════════════════╗
║      TARS — Voice: iMessage Reader       ║
╚══════════════════════════════════════════╝

Reads incoming iMessages from ~/Library/Messages/chat.db
by polling the SQLite database.

On macOS Sequoia+ the `text` column is often NULL — the actual
message content lives inside the `attributedBody` BLOB
(a typedstream-encoded NSAttributedString).  We extract from
both columns so TARS works on every macOS version.
"""

import sqlite3
import time
import os
import re
from collections import deque


class IMessageReader:
    def __init__(self, config):
        self.phone = config["imessage"]["owner_phone"]
        self.poll_interval = config["imessage"]["poll_interval"]
        self.db_path = os.path.expanduser("~/Library/Messages/chat.db")
        self._last_message_rowid = self._get_latest_rowid()
        # Idempotent dedup — bounded set of recently processed ROWIDs
        self._seen_rowids = deque(maxlen=1000)

    # ── attributedBody parser ────────────────────────────────────
    @staticmethod
    def _extract_text_from_attributed_body(blob):
        """
        Extract plain-text from a typedstream NSAttributedString blob.
        The text sits right after the byte sequence:
            NSString \\x01\\x94\\x84\\x01+  <length> <utf-8 text>
        Length encoding:
            • 1-byte length  if < 0x81
            • 2-byte big-endian length prefixed by 0x81 if ≥ 0x81
        Returns the decoded string or None.
        """
        if not blob:
            return None
        try:
            marker = b"NSString\x01\x94\x84\x01+"
            idx = blob.find(marker)
            if idx < 0:
                return None
            start = idx + len(marker)
            if start >= len(blob):
                return None

            # Read length
            first = blob[start]
            if first < 0x81:
                length = first
                text_start = start + 1
            elif first == 0x81:
                if start + 2 >= len(blob):
                    return None
                length = blob[start + 1]
                text_start = start + 2
            elif first == 0x82:
                if start + 3 >= len(blob):
                    return None
                length = int.from_bytes(blob[start + 1:start + 3], "big")
                text_start = start + 3
            else:
                # Unknown length encoding — fall back to regex
                raw = blob[start:].split(b"\x86\x84")[0]
                return raw.decode("utf-8", errors="replace").strip() or None

            raw = blob[text_start:text_start + length]
            return raw.decode("utf-8", errors="replace").strip() or None
        except Exception:
            return None

    def _get_db_connection(self):
        """Open a read-only connection to chat.db with timeout."""
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)

    def _get_latest_rowid(self):
        """Get the ROWID of the most recent message."""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.execute("SELECT MAX(ROWID) FROM message")
                row = cursor.fetchone()
                return row[0] if row[0] else 0
        except Exception:
            return 0

    def _get_new_messages(self):
        """Check for new messages from the owner's phone number since last check."""
        try:
            with self._get_db_connection() as conn:
                # Fetch both `text` AND `attributedBody` — on modern macOS
                # the text column is empty and content is in the blob.
                cursor = conn.execute("""
                    SELECT m.ROWID, m.text, m.is_from_me, m.date,
                           m.attributedBody
                    FROM message m
                    LEFT JOIN handle h ON m.handle_id = h.ROWID
                    WHERE m.ROWID > ?
                      AND h.id = ?
                      AND m.is_from_me = 0
                      AND m.associated_message_type = 0
                    ORDER BY m.ROWID ASC
                """, (self._last_message_rowid, self.phone))

                messages = []
                for row in cursor.fetchall():
                    rowid, text, is_from_me, date, attr_body = row

                    # Prefer text column, fall back to attributedBody
                    body = (text or "").strip()
                    if not body and attr_body:
                        body = self._extract_text_from_attributed_body(attr_body) or ""

                    if not body:
                        continue  # skip truly empty messages

                    # Idempotent: skip any ROWID we've already processed
                    if rowid in self._seen_rowids:
                        continue
                    self._seen_rowids.append(rowid)
                    messages.append({
                        "rowid": rowid,
                        "text": body,
                        "date": date,
                    })
                    self._last_message_rowid = max(self._last_message_rowid, rowid)

                return messages
        except Exception as e:
            print(f"  ⚠️ Error reading chat.db: {e}")
            return []

    def wait_for_reply(self, timeout=300):
        """
        Block and poll chat.db until a new message arrives from the owner.
        Returns the message text, or None if timed out.
        
        NOTE: We do NOT reset _last_message_rowid here. If a message arrived
        between our last check and now, we WANT to catch it — resetting would
        permanently skip it.
        """
        print(f"  📱 Waiting for iMessage reply (timeout: {timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            messages = self._get_new_messages()
            if messages:
                # Concatenate all messages so none are lost when multiple
                # arrive during a single poll interval
                reply = "\n".join(m["text"] for m in messages)
                print(f"  📱 Received reply ({len(messages)} msg(s)): {reply[:80]}...")
                return {"success": True, "content": reply}

            time.sleep(self.poll_interval)

        return {
            "success": False, "error": True,
            "content": f"No reply received within {timeout}s"
        }

    def check_for_kill(self, kill_words):
        """Check if any recent message contains a kill word."""
        messages = self._get_new_messages()
        for msg in messages:
            for kw in kill_words:
                if kw.lower() in msg["text"].lower():
                    return True, msg["text"]
        return False, None
