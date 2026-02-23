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
import queue
import subprocess
import json
from collections import deque

import logging
logger = logging.getLogger("TARS")


class IMessageReader:
    def __init__(self, config):
        self.phone = config["imessage"]["owner_phone"]
        self.poll_interval = config["imessage"]["poll_interval"]
        self.db_path = os.path.expanduser("~/Library/Messages/chat.db")
        # Track whether Python sqlite3 has FDA (Full Disk Access)
        self._use_cli = False
        self._last_message_rowid = self._get_latest_rowid()
        # Idempotent dedup — bounded set of recently processed ROWIDs
        self._seen_rowids = deque(maxlen=1000)
        # Dashboard reply queue — messages from the web dashboard chat
        # are pushed here so wait_for_reply picks them up just like iMessages
        self._dashboard_queue = queue.Queue()

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

    def _cli_query(self, sql):
        """Run a SQL query via /usr/bin/sqlite3 CLI (bypasses FDA restrictions).
        
        The system sqlite3 binary inherits Terminal.app's Full Disk Access,
        while Python's sqlite3 module runs under the Python.app binary which
        may not have FDA. Returns list of rows (each row is a list of strings).
        """
        try:
            result = subprocess.run(
                ["/usr/bin/sqlite3", "-separator", "|||", self.db_path, sql],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return []
            rows = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    rows.append(line.split("|||"))
            return rows
        except Exception:
            return []

    def _get_latest_rowid(self):
        """Get the ROWID of the most recent message."""
        # Try Python sqlite3 first
        try:
            with self._get_db_connection() as conn:
                cursor = conn.execute("SELECT MAX(ROWID) FROM message")
                row = cursor.fetchone()
                return row[0] if row[0] else 0
        except Exception:
            pass
        # Fall back to CLI
        self._use_cli = True
        rows = self._cli_query("SELECT MAX(ROWID) FROM message;")
        if rows and rows[0][0]:
            try:
                return int(rows[0][0])
            except (ValueError, IndexError):
                pass
        return 0

    def _get_new_messages(self):
        """Check for new messages from the owner's phone number since last check."""
        if self._use_cli:
            return self._get_new_messages_cli()
        try:
            return self._get_new_messages_python()
        except Exception as e:
            if "unable to open database" in str(e):
                logger.info("  🔄 Switching to CLI sqlite3 (FDA workaround)")
                self._use_cli = True
                return self._get_new_messages_cli()
            logger.warning(f"  ⚠️ Error reading chat.db: {e}")
            return []

    def _get_new_messages_python(self):
        """Read new messages using Python's sqlite3 module."""
        with self._get_db_connection() as conn:
            # Sanity check: if DB was vacuumed/reset, max ROWID may be lower
            # than our watermark — reset to avoid missing all messages.
            cursor = conn.execute("SELECT MAX(ROWID) FROM message")
            db_max = cursor.fetchone()[0] or 0
            if db_max > 0 and db_max < self._last_message_rowid - 1000:
                logger.warning(f"  ⚠️ chat.db ROWID reset detected (db max: {db_max}, watermark: {self._last_message_rowid}). Resetting.")
                self._last_message_rowid = max(0, db_max - 10)

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
                LIMIT 50
            """, (self._last_message_rowid, self.phone))

            messages = []
            for row in cursor.fetchall():
                rowid, text, is_from_me, date, attr_body = row
                body = (text or "").strip()
                if not body and attr_body:
                    body = self._extract_text_from_attributed_body(attr_body) or ""
                if not body:
                    continue
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

    def _get_new_messages_cli(self):
        """Read new messages using /usr/bin/sqlite3 CLI (FDA workaround).
        
        Note: attributedBody (BLOB) cannot be read via CLI, so we only
        get the text column. On macOS Sequoia+ where text is NULL, we
        use a secondary hex query + Python parsing as fallback.
        """
        sql = f"""
            SELECT m.ROWID, m.text, m.date
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.ROWID > {self._last_message_rowid}
              AND h.id = '{self.phone}'
              AND m.is_from_me = 0
              AND m.associated_message_type = 0
            ORDER BY m.ROWID ASC
            LIMIT 50;
        """
        rows = self._cli_query(sql)
        messages = []
        for row in rows:
            try:
                rowid = int(row[0])
                text = row[1] if len(row) > 1 else ""
                date = row[2] if len(row) > 2 else ""

                body = (text or "").strip()

                # If text column is empty (macOS Sequoia+), try attributedBody via hex
                if not body:
                    body = self._read_attributed_body_cli(rowid)

                if not body:
                    continue
                if rowid in self._seen_rowids:
                    continue
                self._seen_rowids.append(rowid)
                messages.append({
                    "rowid": rowid,
                    "text": body,
                    "date": date,
                })
                self._last_message_rowid = max(self._last_message_rowid, rowid)
            except (ValueError, IndexError):
                continue
        return messages

    def _read_attributed_body_cli(self, rowid):
        """Read attributedBody blob for a specific message via CLI hex dump."""
        sql = f"SELECT hex(attributedBody) FROM message WHERE ROWID = {rowid};"
        rows = self._cli_query(sql)
        if not rows or not rows[0][0]:
            return None
        try:
            blob = bytes.fromhex(rows[0][0])
            return self._extract_text_from_attributed_body(blob)
        except Exception:
            return None

    def push_dashboard_message(self, text):
        """Push a message from the dashboard chat into the reply queue.
        
        This lets the web dashboard act as a full iMessage replacement.
        Messages pushed here are picked up by wait_for_reply() on the
        next poll cycle — exactly like an incoming iMessage.
        """
        self._dashboard_queue.put(text)
        logger.info(f"  🌐 Dashboard message queued: {text[:80]}")

    def _drain_dashboard_queue(self):
        """Drain all pending dashboard messages (non-blocking)."""
        messages = []
        while True:
            try:
                msg = self._dashboard_queue.get_nowait()
                messages.append(msg)
            except queue.Empty:
                break
        return messages

    def wait_for_reply(self, timeout=300):
        """
        Block and poll until a new message arrives from the owner.
        Checks BOTH iMessage (chat.db) AND the dashboard chat queue.
        
        Returns the message text, or error dict if timed out.
        
        NOTE: We do NOT reset _last_message_rowid here. If a message arrived
        between our last check and now, we WANT to catch it — resetting would
        permanently skip it.
        """
        logger.info(f"  📱 Waiting for reply (iMessage + dashboard, timeout: {timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            # ── Check dashboard queue first (instant) ──
            dashboard_msgs = self._drain_dashboard_queue()
            if dashboard_msgs:
                reply = "\n".join(dashboard_msgs)
                logger.info(f"  🌐 Reply from dashboard ({len(dashboard_msgs)} msg(s)): {reply[:80]}")
                return {"success": True, "content": reply, "source": "dashboard"}

            # ── Check iMessage (chat.db) ──
            messages = self._get_new_messages()
            if messages:
                # Concatenate all messages so none are lost when multiple
                # arrive during a single poll interval
                reply = "\n".join(m["text"] for m in messages)
                logger.debug(f"  📱 Received reply ({len(messages)} msg(s)): {reply[:80]}...")
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
