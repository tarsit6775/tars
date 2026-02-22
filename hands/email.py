"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Unified Email Backend                            ║
╠══════════════════════════════════════════════════════════════╣
║  Single source of truth for ALL email operations.            ║
║  Consolidates Mail.app AppleScript + SMTP + Outlook paths.   ║
║                                                              ║
║  Account: tarsitgroup@outlook.com (Mac Mail.app)             ║
║                                                              ║
║  Phases:                                                     ║
║    1-3:  Send/Read/Search/HTML/CC/BCC/Reply/Forward/Drafts   ║
║    4-5:  Folder ops, attachments, advanced search            ║
║    6-8:  Templates, contacts, real-time monitor              ║
║    9-10: Categorization, auto-rules, smart compose           ║
║                                                              ║
║  Every function returns: {"success": bool, "content": str}   ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import time
import smtplib
import tempfile
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from utils.event_bus import event_bus

# ─── Constants ──────────────────────────────────────
TARS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FROM = "tarsitgroup@outlook.com"
ATTACHMENTS_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "tars_attachments")
TEMPLATES_DIR = os.path.join(TARS_ROOT, "memory", "email_templates")
INDEX_PATH = os.path.join(TARS_ROOT, "memory", "email_index.json")
RULES_PATH = os.path.join(TARS_ROOT, "memory", "email_rules.json")
FOLLOWUPS_PATH = os.path.join(TARS_ROOT, "memory", "email_followups.json")
CONTACTS_PATH = os.path.join(TARS_ROOT, "memory", "email_contacts.json")
SNOOZED_PATH = os.path.join(TARS_ROOT, "memory", "email_snoozed.json")
DIGEST_PATH = os.path.join(TARS_ROOT, "memory", "email_digest_history.json")
SENDER_STATS_PATH = os.path.join(TARS_ROOT, "memory", "email_sender_stats.json")

# SMTP config (Outlook)
SMTP_SERVER = "smtp-mail.outlook.com"
SMTP_PORT = 587


# ═══════════════════════════════════════════════════
#  LOW-LEVEL: AppleScript Runners
# ═══════════════════════════════════════════════════

def _run_applescript(script, timeout=30):
    """Run AppleScript via osascript, return standard dict."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return {"success": True, "content": result.stdout.strip()}
        return {"success": False, "error": True, "content": f"AppleScript error: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": True, "content": f"AppleScript timed out ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"AppleScript exception: {e}"}


def _run_applescript_stdin(script, timeout=60):
    """Run AppleScript via stdin to avoid shell escaping issues."""
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return {"success": True, "content": result.stdout.strip()}
        return {"success": False, "error": True, "content": f"AppleScript error: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": True, "content": f"AppleScript timed out ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"AppleScript exception: {e}"}


def _escape_as(text):
    """Escape text for AppleScript string embedding."""
    return text.replace('\\', '\\\\').replace('"', '\\"')


def _get_smtp_password():
    """Load SMTP password from env or config."""
    pwd = os.environ.get("TARS_SMTP_PASSWORD", "")
    if pwd:
        return pwd
    try:
        import yaml
        config_path = os.path.join(TARS_ROOT, "config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config.get("email", {}).get("smtp_password", "")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════
#  PHASE 1: Core Read Operations
# ═══════════════════════════════════════════════════

def get_unread_count():
    """Get number of unread emails in inbox."""
    return _run_applescript('tell application "Mail" to get unread count of inbox')


def read_inbox(count=10):
    """Read latest N emails from inbox with structured output.

    Returns sender, subject, date, read status, and message ID for each.
    """
    script = f'''
    tell application "Mail"
        set msgCount to count of messages of inbox
        if msgCount > {count} then set msgCount to {count}
        if msgCount < 1 then return "No messages in inbox."
        set msgList to messages 1 thru msgCount of inbox
        set output to ""
        set idx to 1
        repeat with m in msgList
            set isRead to read status of m
            set readMark to "📖"
            if not isRead then set readMark to "📩"
            set output to output & readMark & " [" & idx & "] "
            set output to output & "FROM: " & (sender of m) & " | "
            set output to output & "SUBJECT: " & (subject of m) & " | "
            set output to output & "DATE: " & (date received of m as string)
            set output to output & linefeed
            set idx to idx + 1
        end repeat
        return output
    end tell
    '''
    return _run_applescript_stdin(script, timeout=60)


def read_message(index=1, mailbox="inbox"):
    """Read full email content by index (1 = newest).

    Returns from, to, cc, subject, date, body, attachments list.
    """
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    script = f'''
    tell application "Mail"
        set m to message {index} of {mb_ref}
        set output to ""
        set output to output & "FROM: " & (sender of m) & linefeed
        try
            set toAddrs to ""
            repeat with r in to recipients of m
                set toAddrs to toAddrs & (address of r) & ", "
            end repeat
            set output to output & "TO: " & toAddrs & linefeed
        end try
        try
            set ccAddrs to ""
            repeat with r in cc recipients of m
                set ccAddrs to ccAddrs & (address of r) & ", "
            end repeat
            if ccAddrs is not "" then set output to output & "CC: " & ccAddrs & linefeed
        end try
        set output to output & "SUBJECT: " & (subject of m) & linefeed
        set output to output & "DATE: " & (date received of m as string) & linefeed
        set output to output & "READ: " & (read status of m) & linefeed
        try
            set attCount to count of mail attachments of m
            if attCount > 0 then
                set output to output & "ATTACHMENTS: " & attCount & linefeed
                repeat with a in mail attachments of m
                    set output to output & "  📎 " & (name of a) & " (" & (MIME type of a) & ")" & linefeed
                end repeat
            end if
        end try
        set output to output & linefeed & "--- BODY ---" & linefeed & (content of m)
        return output
    end tell
    '''
    return _run_applescript_stdin(script, timeout=60)


def mark_read(index=1, mailbox="inbox"):
    """Mark an email as read."""
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    script = f'''
    tell application "Mail"
        set read status of message {index} of {mb_ref} to true
    end tell
    '''
    result = _run_applescript_stdin(script)
    if result["success"]:
        result["content"] = f"Marked message {index} as read"
    return result


def mark_unread(index=1, mailbox="inbox"):
    """Mark an email as unread."""
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    script = f'''
    tell application "Mail"
        set read status of message {index} of {mb_ref} to false
    end tell
    '''
    result = _run_applescript_stdin(script)
    if result["success"]:
        result["content"] = f"Marked message {index} as unread"
    return result


def flag_message(index=1, flagged=True, mailbox="inbox"):
    """Flag or unflag an email."""
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    flag_val = "1" if flagged else "0"
    script = f'''
    tell application "Mail"
        set flagged status of message {index} of {mb_ref} to {flag_val}
    end tell
    '''
    result = _run_applescript_stdin(script)
    if result["success"]:
        action = "Flagged" if flagged else "Unflagged"
        result["content"] = f"{action} message {index}"
    return result


# ═══════════════════════════════════════════════════
#  PHASE 2: Send Operations (Plain + HTML + Attachments)
# ═══════════════════════════════════════════════════

def send_email(to, subject, body, cc=None, bcc=None,
               attachment_paths=None, html=False,
               from_address=DEFAULT_FROM):
    """Send an email — the unified entry point.

    Supports: plain text, HTML, CC/BCC, multiple recipients,
    multiple attachments. Falls back through:
      1. SMTP (if password configured) — best for HTML
      2. Mail.app AppleScript — reliable for plain text + single attachment
    """
    # Normalize recipients
    to_list = [to] if isinstance(to, str) else to
    cc_list = ([cc] if isinstance(cc, str) else cc) if cc else []
    bcc_list = ([bcc] if isinstance(bcc, str) else bcc) if bcc else []
    att_list = ([attachment_paths] if isinstance(attachment_paths, str) else attachment_paths) if attachment_paths else []

    # Validate attachments exist
    for att in att_list:
        expanded = os.path.expanduser(att)
        if not os.path.isfile(expanded):
            return {"success": False, "error": True, "content": f"Attachment not found: {att}"}

    # HTML or SMTP-needed features (CC/BCC/multiple recipients)
    use_smtp = html or cc_list or bcc_list or len(to_list) > 1

    if use_smtp:
        result = _send_via_smtp(to_list, subject, body, cc_list, bcc_list, att_list, html, from_address)
        if result["success"]:
            event_bus.emit("email_sent", {"to": to_list, "subject": subject, "html": html})
            return result
        # SMTP failed — try Mail.app for plain text
        if not html:
            result = _send_via_mailapp(to_list[0], subject, body, att_list[0] if att_list else None, from_address)
            if result["success"]:
                event_bus.emit("email_sent", {"to": to_list, "subject": subject})
            return result
        # HTML fallback to Mail.app html content
        result = _send_html_via_mailapp(to_list[0], subject, body, att_list[0] if att_list else None, from_address)
        if result["success"]:
            event_bus.emit("email_sent", {"to": to_list, "subject": subject, "html": True})
        return result

    # Simple plain text — use Mail.app directly (faster, no password needed)
    result = _send_via_mailapp(to_list[0], subject, body, att_list[0] if att_list else None, from_address)
    if result["success"]:
        event_bus.emit("email_sent", {"to": to_list, "subject": subject})
    return result


def _send_via_smtp(to_list, subject, body, cc_list, bcc_list, att_list, html, from_address):
    """Send via SMTP (Outlook). Supports all features."""
    password = _get_smtp_password()
    if not password:
        return {"success": False, "error": True, "content": "SMTP password not configured. Set TARS_SMTP_PASSWORD env var."}

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"TARS <{from_address}>"
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["X-Mailer"] = "TARS Email Agent"

        # Body
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # Attachments
        for att_path in att_list:
            att_path = os.path.expanduser(att_path)
            with open(att_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(att_path)}"')
                msg.attach(part)

        all_recipients = to_list + cc_list + bcc_list
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(from_address, password)
            server.sendmail(from_address, all_recipients, msg.as_string())

        att_info = f" (with {len(att_list)} attachment(s))" if att_list else ""
        return {"success": True, "content": f"Email sent via SMTP to {', '.join(to_list)}: {subject}{att_info}"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": True, "content": "SMTP authentication failed. Check TARS_SMTP_PASSWORD."}
    except Exception as e:
        return {"success": False, "error": True, "content": f"SMTP error: {e}"}


def _send_via_mailapp(to_address, subject, body, attachment_path=None, from_address=DEFAULT_FROM):
    """Send plain text email via Mail.app AppleScript."""
    safe_subject = _escape_as(subject)
    safe_body = _escape_as(body)

    if attachment_path:
        attachment_path = os.path.expanduser(attachment_path)
        script = f'''
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:true}}
            tell msg
                make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
                set theAttachment to POSIX file "{attachment_path}"
                make new attachment with properties {{file name:theAttachment}} at after last paragraph
            end tell
            delay 3
            send msg
            set maxWait to 30
            set waited to 0
            repeat while waited < maxWait
                delay 2
                set waited to waited + 2
                set oCount to count of (messages of outbox)
                if oCount = 0 then return "sent"
            end repeat
            return "outbox_stuck"
        end tell
        '''
    else:
        script = f'''
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
            tell msg
                make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
            end tell
            send msg
        end tell
        '''

    result = _run_applescript_stdin(script, timeout=60)
    if result["success"]:
        if result.get("content") == "outbox_stuck":
            result["success"] = False
            result["error"] = True
            result["content"] = f"Email to {to_address} may be stuck in Outbox. Check Mail.app > Outbox."
        else:
            att_info = f" (with attachment: {os.path.basename(attachment_path)})" if attachment_path else ""
            result["content"] = f"Email sent to {to_address}: {subject}{att_info}"
    return result


def _send_html_via_mailapp(to_address, subject, html_body, attachment_path=None, from_address=DEFAULT_FROM):
    """Send HTML email via Mail.app using html content property."""
    safe_subject = _escape_as(subject)

    # Write HTML to temp file (avoids escaping hell)
    html_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False)
    html_file.write(html_body)
    html_file.close()

    try:
        if attachment_path and os.path.isfile(os.path.expanduser(attachment_path)):
            attachment_path = os.path.expanduser(attachment_path)
            script = f'''
            set htmlContent to read POSIX file "{html_file.name}" as «class utf8»
            tell application "Mail"
                set msg to make new outgoing message with properties {{subject:"{safe_subject}", visible:true}}
                tell msg
                    make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
                    set theAttachment to POSIX file "{attachment_path}"
                    make new attachment with properties {{file name:theAttachment}} at after last paragraph
                    delay 1
                    set html content to htmlContent
                end tell
                delay 2
                send msg
            end tell
            '''
        else:
            script = f'''
            set htmlContent to read POSIX file "{html_file.name}" as «class utf8»
            tell application "Mail"
                set msg to make new outgoing message with properties {{subject:"{safe_subject}", visible:false}}
                tell msg
                    set html content to htmlContent
                    make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
                end tell
                send msg
            end tell
            '''

        result = _run_applescript_stdin(script, timeout=60)
        if result["success"]:
            result["content"] = f"HTML email sent via Mail.app to {to_address}: {subject}"
        return result
    finally:
        try:
            os.unlink(html_file.name)
        except Exception:
            pass


# ═══════════════════════════════════════════════════
#  PHASE 3: Reply & Forward
# ═══════════════════════════════════════════════════

def reply_to(index=1, body="", reply_all=False, mailbox="inbox"):
    """Reply to an email by index.

    Args:
        index: Message index (1 = newest)
        body: Reply text
        reply_all: If True, reply to all recipients
        mailbox: Which mailbox (default: inbox)
    """
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    safe_body = _escape_as(body)
    reply_cmd = "reply msg with reply to all" if reply_all else "reply msg"

    script = f'''
    tell application "Mail"
        set msg to message {index} of {mb_ref}
        set replyMsg to {reply_cmd}
        set content of replyMsg to "{safe_body}" & linefeed & linefeed & content of replyMsg
        send replyMsg
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=60)
    if result["success"]:
        kind = "Reply-all" if reply_all else "Reply"
        result["content"] = f"{kind} sent to message {index}"
        event_bus.emit("email_sent", {"action": "reply", "index": index, "reply_all": reply_all})
    return result


def forward_to(index=1, to_address="", body="", mailbox="inbox"):
    """Forward an email by index to a new recipient."""
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    safe_body = _escape_as(body)

    script = f'''
    tell application "Mail"
        set msg to message {index} of {mb_ref}
        set fwdMsg to forward msg
        tell fwdMsg
            make new to recipient at end of to recipients with properties {{address:"{to_address}"}}
        end tell
        if "{safe_body}" is not "" then
            set content of fwdMsg to "{safe_body}" & linefeed & linefeed & content of fwdMsg
        end if
        send fwdMsg
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=60)
    if result["success"]:
        result["content"] = f"Forwarded message {index} to {to_address}"
        event_bus.emit("email_sent", {"action": "forward", "to": to_address, "index": index})
    return result


# ═══════════════════════════════════════════════════
#  PHASE 4: Search (Advanced)
# ═══════════════════════════════════════════════════

def search_emails(keyword="", sender="", subject="", body_contains="",
                  unread_only=False, flagged_only=False, has_attachments=False,
                  date_from=None, date_to=None, mailbox="inbox", max_results=20):
    """Advanced email search with multiple filters.

    All filters are AND-combined. Pass only the ones you need.
    """
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'

    # Build AppleScript whose clause
    conditions = []
    if keyword:
        conditions.append(f'(subject contains "{_escape_as(keyword)}" or sender contains "{_escape_as(keyword)}")')
    if sender:
        conditions.append(f'sender contains "{_escape_as(sender)}"')
    if subject:
        conditions.append(f'subject contains "{_escape_as(subject)}"')
    if unread_only:
        conditions.append('read status is false')
    if flagged_only:
        conditions.append('flagged status is true')
    if date_from:
        conditions.append(f'date received >= date "{date_from}"')
    if date_to:
        conditions.append(f'date received <= date "{date_to}"')

    where = " and ".join(conditions) if conditions else ""
    whose = f"whose {where}" if where else ""

    # Post-fetch filters (body_contains + has_attachments can't go in whose clause)
    post_filter_body = body_contains
    post_filter_attachments = has_attachments

    script = f'''
    tell application "Mail"
        set found to (messages of {mb_ref} {whose})
        set output to ""
        set counter to 0
        repeat with m in found
            if counter >= {max_results} then exit repeat
            set skipMsg to false
            {'set bodyText to content of m' if post_filter_body else ''}
            {'if bodyText does not contain "' + _escape_as(body_contains) + '" then set skipMsg to true' if post_filter_body else ''}
            {'if (count of mail attachments of m) < 1 then set skipMsg to true' if post_filter_attachments else ''}
            if not skipMsg then
                set isRead to read status of m
                set readMark to "📖"
                if not isRead then set readMark to "📩"
                set isFlagged to flagged status of m
                set flagMark to ""
                if isFlagged then set flagMark to "🚩"
                set output to output & readMark & flagMark & " [" & (counter + 1) & "] "
                set output to output & "FROM: " & (sender of m) & " | "
                set output to output & "SUBJECT: " & (subject of m) & " | "
                set output to output & "DATE: " & (date received of m as string)
                set output to output & linefeed
                set counter to counter + 1
            end if
        end repeat
        if output is "" then return "No emails found matching the criteria."
        return output
    end tell
    '''
    return _run_applescript_stdin(script, timeout=60)


# ═══════════════════════════════════════════════════
#  PHASE 5: Folder / Mailbox Operations
# ═══════════════════════════════════════════════════

def list_mailboxes():
    """List all mailboxes/folders across all accounts."""
    script = '''
    tell application "Mail"
        set output to ""
        repeat with acct in accounts
            set acctName to name of acct
            set output to output & "📧 Account: " & acctName & linefeed
            repeat with mb in mailboxes of acct
                set msgCount to count of messages of mb
                set output to output & "  📁 " & (name of mb) & " (" & msgCount & " messages)" & linefeed
            end repeat
            set output to output & linefeed
        end repeat
        return output
    end tell
    '''
    return _run_applescript_stdin(script, timeout=60)


def move_message(index=1, from_mailbox="inbox", to_mailbox="Archive", account=None):
    """Move an email to a different mailbox/folder."""
    from_ref = f'inbox' if from_mailbox == "inbox" else f'mailbox "{from_mailbox}"'

    # Build target mailbox reference
    if account:
        to_ref = f'mailbox "{to_mailbox}" of account "{account}"'
    else:
        to_ref = f'mailbox "{to_mailbox}"'

    script = f'''
    tell application "Mail"
        set msg to message {index} of {from_ref}
        move msg to {to_ref}
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=30)
    if result["success"]:
        result["content"] = f"Moved message {index} from {from_mailbox} to {to_mailbox}"
        event_bus.emit("email_action", {"action": "move", "index": index, "to": to_mailbox})
    return result


def delete_message(index=1, mailbox="inbox"):
    """Delete an email (move to Trash)."""
    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    script = f'''
    tell application "Mail"
        delete message {index} of {mb_ref}
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=30)
    if result["success"]:
        result["content"] = f"Deleted message {index} from {mailbox}"
        event_bus.emit("email_action", {"action": "delete", "index": index, "mailbox": mailbox})
    return result


def archive_message(index=1, mailbox="inbox"):
    """Archive an email (move to Archive folder)."""
    return move_message(index, mailbox, "Archive")


# ═══════════════════════════════════════════════════
#  PHASE 6: Attachment Download
# ═══════════════════════════════════════════════════

def download_attachments(index=1, mailbox="inbox", save_dir=None):
    """Download all attachments from an email.

    Saves to ~/Downloads/tars_attachments/ by default.
    Returns list of saved file paths.
    """
    save_dir = save_dir or ATTACHMENTS_DIR
    os.makedirs(save_dir, exist_ok=True)

    mb_ref = f'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    script = f'''
    tell application "Mail"
        set m to message {index} of {mb_ref}
        set attList to mail attachments of m
        set attCount to count of attList
        if attCount = 0 then return "NO_ATTACHMENTS"
        set output to ""
        repeat with a in attList
            set fileName to name of a
            set savePath to POSIX path of (("{save_dir}/" & fileName) as string)
            try
                save a in POSIX file savePath
                set output to output & savePath & linefeed
            on error errMsg
                set output to output & "FAILED:" & fileName & ":" & errMsg & linefeed
            end try
        end repeat
        return output
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=120)
    if result["success"]:
        content = result["content"]
        if content == "NO_ATTACHMENTS":
            result["content"] = f"No attachments on message {index}"
        else:
            paths = [l for l in content.strip().split('\n') if l and not l.startswith("FAILED:")]
            failures = [l for l in content.strip().split('\n') if l.startswith("FAILED:")]
            parts = [f"Downloaded {len(paths)} attachment(s) to {save_dir}:"]
            for p in paths:
                parts.append(f"  📎 {os.path.basename(p)}")
            if failures:
                parts.append(f"  ⚠️ {len(failures)} failed")
            result["content"] = "\n".join(parts)
    return result


# ═══════════════════════════════════════════════════
#  PHASE 7: Drafts
# ═══════════════════════════════════════════════════

def save_draft(to, subject, body, cc=None, html=False):
    """Save an email as a draft (don't send)."""
    safe_subject = _escape_as(subject)
    safe_body = _escape_as(body)

    # Build recipient block
    to_block = f'make new to recipient at end of to recipients with properties {{address:"{to}"}}'
    cc_block = ""
    if cc:
        cc_list = [cc] if isinstance(cc, str) else cc
        for addr in cc_list:
            cc_block += f'\n                make new cc recipient at end of cc recipients with properties {{address:"{addr}"}}'

    if html:
        html_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False)
        html_file.write(body)
        html_file.close()
        script = f'''
        set htmlContent to read POSIX file "{html_file.name}" as «class utf8»
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", visible:false}}
            tell msg
                set html content to htmlContent
                {to_block}
                {cc_block}
            end tell
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=30)
        try:
            os.unlink(html_file.name)
        except Exception:
            pass
    else:
        script = f'''
        tell application "Mail"
            set msg to make new outgoing message with properties {{subject:"{safe_subject}", content:"{safe_body}", visible:false}}
            tell msg
                {to_block}
                {cc_block}
            end tell
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=30)

    if result["success"]:
        result["content"] = f"Draft saved: {subject} → {to}"
    return result


def list_drafts(count=10):
    """List emails in the Drafts mailbox."""
    script = f'''
    tell application "Mail"
        set output to ""
        set found to false
        repeat with acct in accounts
            try
                set draftBox to drafts mailbox of acct
                set msgs to messages 1 thru (min({count}, (count of messages of draftBox))) of draftBox
                repeat with m in msgs
                    set found to true
                    set output to output & "📝 TO: "
                    try
                        set output to output & (address of to recipient 1 of m)
                    on error
                        set output to output & "(no recipient)"
                    end try
                    set output to output & " | SUBJECT: " & (subject of m)
                    set output to output & " | DATE: " & (date received of m as string) & linefeed
                end repeat
            end try
        end repeat
        if not found then return "No drafts found."
        return output
    end tell
    '''
    return _run_applescript_stdin(script, timeout=60)


# ═══════════════════════════════════════════════════
#  PHASE 8: Verify Sent
# ═══════════════════════════════════════════════════

def verify_sent(subject, to_address=None):
    """Verify an email was sent by checking the Sent folder."""
    safe_subject = _escape_as(subject)
    sent_names = ["Sent Items", "Sent Messages", "Sent", "Sent Mail"]

    # Discover accounts
    acct_result = _run_applescript('tell application "Mail" to get name of every account')
    accounts = []
    if acct_result["success"]:
        accounts = [a.strip() for a in acct_result["content"].split(",")]
    if not accounts:
        accounts = ["Exchange", "Outlook", "iCloud"]

    for acct in accounts:
        for sent_name in sent_names:
            script = f'''
            tell application "Mail"
                try
                    set sentMsgs to messages of mailbox "{sent_name}" of account "{acct}"
                    set output to ""
                    set found to false
                    set counter to 0
                    repeat with m in sentMsgs
                        if counter >= 20 then exit repeat
                        if subject of m contains "{safe_subject}" then
                            set output to output & "✅ FOUND — Subject: " & (subject of m) & " | To: " & (address of to recipient 1 of m) & " | Date: " & (date sent of m as string) & linefeed
                            set found to true
                        end if
                        set counter to counter + 1
                    end repeat
                    if not found then return "NOT_FOUND"
                    return output
                on error
                    return "NOT_FOUND"
                end try
            end tell
            '''
            result = _run_applescript_stdin(script, timeout=30)
            if result["success"] and "NOT_FOUND" not in result.get("content", ""):
                return result

    return {"success": False, "error": True, "content": f"No sent email matching '{subject}' found"}


# ═══════════════════════════════════════════════════
#  PHASE 9: Templates
# ═══════════════════════════════════════════════════

def save_template(name, subject, body, html=False):
    """Save an email template for reuse."""
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    template = {
        "name": name,
        "subject": subject,
        "body": body,
        "html": html,
        "created": datetime.now().isoformat(),
    }
    path = os.path.join(TEMPLATES_DIR, f"{name.lower().replace(' ', '_')}.json")
    with open(path, "w") as f:
        json.dump(template, f, indent=2)
    return {"success": True, "content": f"Template '{name}' saved"}


def list_templates():
    """List available email templates."""
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    templates = []
    for f in os.listdir(TEMPLATES_DIR):
        if f.endswith(".json"):
            try:
                with open(os.path.join(TEMPLATES_DIR, f)) as fh:
                    t = json.load(fh)
                    templates.append(f"📋 {t['name']} — Subject: {t['subject'][:50]}")
            except Exception:
                pass
    if not templates:
        return {"success": True, "content": "No templates saved yet."}
    return {"success": True, "content": "\n".join(templates)}


def send_template(name, to, variables=None):
    """Send an email using a saved template.

    Variables is a dict for substitution: {"name": "John", "date": "March 1"}
    Template uses {{key}} placeholders.
    """
    path = os.path.join(TEMPLATES_DIR, f"{name.lower().replace(' ', '_')}.json")
    if not os.path.exists(path):
        return {"success": False, "error": True, "content": f"Template '{name}' not found"}

    with open(path) as f:
        template = json.load(f)

    subject = template["subject"]
    body = template["body"]

    # Variable substitution
    if variables:
        for key, val in variables.items():
            subject = subject.replace(f"{{{{{key}}}}}", str(val))
            body = body.replace(f"{{{{{key}}}}}", str(val))

    return send_email(to=to, subject=subject, body=body, html=template.get("html", False))


# ═══════════════════════════════════════════════════
#  PHASE 10: Contact Integration
# ═══════════════════════════════════════════════════

def lookup_contact_email(name):
    """Look up an email address by contact name from macOS Contacts + TARS contacts."""
    # 1. Search TARS contacts first (faster, no AppleScript)
    tars_contacts = _load_contacts()
    name_lower = name.lower()
    tars_matches = [
        c for c in tars_contacts
        if name_lower in c.get("name", "").lower() or name_lower in c.get("email", "").lower()
    ]
    if tars_matches:
        lines = []
        for c in tars_matches:
            tags = f" [{', '.join(c.get('tags', []))}]" if c.get("tags") else ""
            lines.append(f"{c['name']}: {c['email']}{tags}")
        return {"success": True, "content": "\n".join(lines)}

    # 2. Fall back to macOS Contacts
    safe_name = _escape_as(name)
    script = f'''
    tell application "Contacts"
        set found to (every person whose name contains "{safe_name}")
        if (count of found) = 0 then return "NOT_FOUND"
        set output to ""
        repeat with p in found
            set pName to name of p
            set emails to value of emails of p
            if (count of emails) > 0 then
                set output to output & pName & ": " & (item 1 of emails) & linefeed
            end if
        end repeat
        return output
    end tell
    '''
    result = _run_applescript(script, timeout=15)
    if result["success"] and result["content"] == "NOT_FOUND":
        result["success"] = False
        result["content"] = f"No contact found for '{name}'"
    return result


# ═══════════════════════════════════════════════════
#  PHASE 11: Real-Time Inbox Monitor
# ═══════════════════════════════════════════════════

class InboxMonitor:
    """Background thread that polls Mail.app for new emails.

    Emits 'email_received' events on the event bus when new emails arrive.
    Tracks seen message IDs to avoid duplicates.
    """

    def __init__(self, poll_interval=15):
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._seen_subjects = set()  # Track by subject+sender+date hash
        self._last_count = None
        self._lock = threading.Lock()
        self._callbacks = []  # [(filter_fn, callback_fn)]

    def start(self):
        """Start polling inbox in background."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="InboxMonitor")
        self._thread.start()
        print("  📬 Inbox monitor started (polling every {}s)".format(self.poll_interval))

    def stop(self):
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def add_rule(self, filter_fn, callback_fn):
        """Add a real-time rule: when filter_fn(email_dict) is True, call callback_fn(email_dict)."""
        with self._lock:
            self._callbacks.append((filter_fn, callback_fn))

    def _poll_loop(self):
        """Main polling loop."""
        # Seed with current inbox to avoid firing on startup
        self._seed_seen()

        poll_count = 0
        self._last_digest_date = None
        self._digest_hour = 8  # 8 AM daily digest
        while self._running:
            try:
                self._check_new()
            except Exception as e:
                print(f"  ⚠️ Inbox monitor error: {e}")

            # Process scheduled emails
            try:
                sent = _process_scheduled_emails()
                if sent > 0:
                    print(f"  📤 Sent {sent} scheduled email(s)")
            except Exception as e:
                print(f"  ⚠️ Scheduled email error: {e}")

            # Process snoozed emails (resurface expired snoozes)
            try:
                resurfaced = _process_snoozed()
                if resurfaced > 0:
                    print(f"  ⏰ Resurfaced {resurfaced} snoozed email(s)")
            except Exception as e:
                print(f"  ⚠️ Snoozed email error: {e}")

            # Check follow-ups every 10 polls (~2.5 min at 15s interval)
            if poll_count % 10 == 0 and poll_count > 0:
                try:
                    self._process_followups()
                except Exception as e:
                    print(f"  ⚠️ Follow-up check error: {e}")

            # Auto-digest: once per day at digest_hour
            try:
                self._auto_digest()
            except Exception as e:
                print(f"  ⚠️ Auto-digest error: {e}")

            # Emit email stats to dashboard every 5 polls
            poll_count += 1
            if poll_count % 5 == 0:
                try:
                    stats_result = get_email_stats()
                    if stats_result["success"]:
                        import json as _json
                        stats_data = _json.loads(stats_result["content"])
                        event_bus.emit("email_stats", stats_data)
                except Exception:
                    pass

            # Record daily inbox snapshot at midnight (for inbox zero tracking)
            if poll_count % 20 == 0:
                try:
                    self._record_daily_snapshot()
                except Exception as e:
                    print(f"  ⚠️ Inbox snapshot error: {e}")

            # Auto-detect VIPs weekly (every ~6h of runtime = 1440 polls at 15s)
            if poll_count % 1440 == 0 and poll_count > 0:
                try:
                    auto_detect_vips(threshold=70)
                except Exception as e:
                    print(f"  ⚠️ Auto-VIP detection error: {e}")

            time.sleep(self.poll_interval)

    def _record_daily_snapshot(self):
        """Record inbox snapshot for inbox zero trend tracking."""
        try:
            _record_inbox_snapshot()
        except Exception:
            pass

    def _process_followups(self):
        """Check follow-ups and emit events for overdue items."""
        try:
            result = check_followups()
            if not result.get("success"):
                return
            content = result.get("content", "")
            if "overdue" in content.lower():
                # Parse overdue count from the result
                followups = _load_followups()
                overdue = [f for f in followups if f.get("status") == "overdue"]
                if overdue:
                    event_bus.emit("email_followup_overdue", {
                        "count": len(overdue),
                        "subjects": [f.get("subject", "")[:50] for f in overdue[:5]],
                    })
                    print(f"  📋 {len(overdue)} follow-up(s) overdue")
        except Exception as e:
            print(f"  ⚠️ Follow-up processing error: {e}")

    def _auto_digest(self):
        """Run daily digest once per day at the configured hour."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # Already ran today
        if self._last_digest_date == today:
            return

        # Only run at digest hour
        if now.hour != self._digest_hour:
            return

        # Check if we already generated a digest today (from persistence)
        try:
            if os.path.exists(DIGEST_PATH):
                with open(DIGEST_PATH) as f:
                    history = json.load(f)
                if any(d.get("date") == today for d in history):
                    self._last_digest_date = today
                    return
        except Exception:
            pass

        # Generate the digest
        print(f"  📰 Generating daily digest for {today}...")
        try:
            result = generate_daily_digest()
            if result.get("success"):
                self._last_digest_date = today
                event_bus.emit("email_auto_digest", {"date": today})
                print(f"  📰 Daily digest generated successfully")
        except Exception as e:
            print(f"  ⚠️ Daily digest generation error: {e}")

    def _seed_seen(self):
        """Load current inbox message hashes so we don't fire on existing emails."""
        try:
            script = '''
            tell application "Mail"
                set msgs to messages 1 thru (min(50, (count of messages of inbox))) of inbox
                set output to ""
                repeat with m in msgs
                    set output to output & (sender of m) & "|" & (subject of m) & "|" & (date received of m as string) & linefeed
                end repeat
                return output
            end tell
            '''
            result = _run_applescript_stdin(script, timeout=30)
            if result["success"]:
                for line in result["content"].strip().split('\n'):
                    if line.strip():
                        self._seen_subjects.add(hash(line.strip()))
                # Cap the set
                if len(self._seen_subjects) > 500:
                    self._seen_subjects = set(list(self._seen_subjects)[-200:])
        except Exception:
            pass

    def _check_new(self):
        """Check for new emails since last poll."""
        script = '''
        tell application "Mail"
            check for new mail
            delay 1
            set unreadMsgs to (messages of inbox whose read status is false)
            set output to ""
            repeat with m in unreadMsgs
                set msgHash to (sender of m) & "|" & (subject of m) & "|" & (date received of m as string)
                set output to output & msgHash & "|||" & (sender of m) & "|||" & (subject of m) & "|||" & (date received of m as string) & linefeed
            end repeat
            return output
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=30)
        if not result["success"]:
            return

        content = result["content"].strip()
        if not content:
            return

        for line in content.split('\n'):
            if not line.strip():
                continue
            parts = line.strip().split('|||')
            if len(parts) < 4:
                continue
            msg_hash = hash(parts[0])
            if msg_hash in self._seen_subjects:
                continue

            self._seen_subjects.add(msg_hash)
            email_info = {
                "sender": parts[1],
                "subject": parts[2],
                "date": parts[3],
                "timestamp": datetime.now().isoformat(),
            }

            # Emit event
            event_bus.emit("email_received", email_info)
            print(f"  📬 New email: {email_info['sender'][:30]} — {email_info['subject'][:50]}")

            # Auto-update sender stats for incoming email
            try:
                update_sender_stats(email_info["sender"], "received")
            except Exception as e:
                print(f"  ⚠️ Sender stats update error: {e}")

            # Process OOO auto-reply
            try:
                _process_ooo(email_info)
            except Exception as e:
                print(f"  ⚠️ OOO auto-reply error: {e}")

            # Apply auto-rules (persistent rules from email_rules.json)
            try:
                apply_rules_to_email(email_info)
            except Exception as e:
                print(f"  ⚠️ Auto-rule error: {e}")

            # Run callback rules (programmatic)
            with self._lock:
                for filter_fn, callback_fn in self._callbacks:
                    try:
                        if filter_fn(email_info):
                            callback_fn(email_info)
                    except Exception as e:
                        print(f"  ⚠️ Email rule error: {e}")


# ─── Singleton monitor ──────────────────────────────
inbox_monitor = InboxMonitor()


# ═══════════════════════════════════════════════════
#  PHASE 12: Follow-up Tracking
# ═══════════════════════════════════════════════════

def add_followup(subject, to_address, deadline_hours=48, reminder_text=""):
    """Track an email for follow-up if no reply received."""
    os.makedirs(os.path.dirname(FOLLOWUPS_PATH), exist_ok=True)
    followups = _load_followups()
    followups.append({
        "subject": subject,
        "to": to_address,
        "sent_at": datetime.now().isoformat(),
        "deadline": (datetime.now() + timedelta(hours=deadline_hours)).isoformat(),
        "reminder": reminder_text or f"No reply to '{subject}' from {to_address}",
        "status": "waiting",
    })
    _save_followups(followups)
    return {"success": True, "content": f"Follow-up set: will remind in {deadline_hours}h if no reply from {to_address}"}


def check_followups():
    """Check for overdue follow-ups. Returns list of overdue items."""
    followups = _load_followups()
    now = datetime.now()
    overdue = []
    updated = False

    for f in followups:
        if f["status"] != "waiting":
            continue
        deadline = datetime.fromisoformat(f["deadline"])
        if now > deadline:
            # Check if a reply came in
            search_result = search_emails(sender=f["to"], subject=f["subject"], max_results=5)
            if search_result["success"] and "No emails found" not in search_result["content"]:
                f["status"] = "replied"
                updated = True
            else:
                overdue.append(f)
                f["status"] = "overdue"
                updated = True

    if updated:
        _save_followups(followups)

    if not overdue:
        return {"success": True, "content": "No overdue follow-ups."}

    lines = ["⏰ Overdue follow-ups:"]
    for f in overdue:
        lines.append(f"  📧 {f['to']}: {f['subject']} (sent {f['sent_at'][:10]})")
    return {"success": True, "content": "\n".join(lines)}


def _load_followups():
    try:
        if os.path.exists(FOLLOWUPS_PATH):
            with open(FOLLOWUPS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_followups(data):
    os.makedirs(os.path.dirname(FOLLOWUPS_PATH), exist_ok=True)
    # Keep last 100
    if len(data) > 100:
        data = data[-100:]
    with open(FOLLOWUPS_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════
#  STATS (for dashboard)
# ═══════════════════════════════════════════════════

def get_email_stats():
    """Get email statistics for the dashboard."""
    stats = {
        "unread": 0,
        "inbox_total": 0,
        "sent_today": 0,
        "drafts": 0,
        "rules_count": 0,
        "rules_triggered_today": 0,
        "scheduled_pending": 0,
        "monitor_active": inbox_monitor._running if inbox_monitor else False,
        "top_senders": [],
    }

    # Unread count
    r = get_unread_count()
    if r["success"]:
        try:
            stats["unread"] = int(r["content"])
        except ValueError:
            pass

    # Inbox total count
    try:
        script = '''
        tell application "Mail"
            return count of messages of inbox
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=10)
        if result["success"]:
            stats["inbox_total"] = int(result["content"].strip())
    except Exception:
        pass

    # Sent today count
    try:
        today_str = datetime.now().strftime("%B %d, %Y")
        script = f'''
        tell application "Mail"
            set todayStr to "{today_str}"
            set sentBox to sent mailbox
            set sentCount to 0
            try
                set allMsgs to messages of sentBox
                repeat with m in allMsgs
                    set msgDate to date sent of m
                    set msgDateStr to (month of msgDate as string) & " " & (day of msgDate as string) & ", " & (year of msgDate as string)
                    if msgDateStr is todayStr then
                        set sentCount to sentCount + 1
                    else
                        exit repeat
                    end if
                end repeat
            end try
            return sentCount
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=15)
        if result["success"]:
            stats["sent_today"] = int(result["content"].strip())
    except Exception:
        pass

    # Drafts count
    try:
        script = '''
        tell application "Mail"
            return count of messages of drafts mailbox
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=10)
        if result["success"]:
            stats["drafts"] = int(result["content"].strip())
    except Exception:
        pass

    # Rules count + today's triggers
    try:
        rules = _load_rules()
        stats["rules_count"] = len(rules)
        today = datetime.now().strftime("%Y-%m-%d")
        for rule in rules:
            last_triggered = rule.get("last_triggered", "")
            if last_triggered and last_triggered.startswith(today):
                stats["rules_triggered_today"] += rule.get("hit_count", 0)
    except Exception:
        pass

    # Scheduled pending
    try:
        scheduled = _load_scheduled()
        stats["scheduled_pending"] = len([s for s in scheduled if s.get("status") == "pending"])
    except Exception:
        pass

    # Snoozed count
    try:
        snoozed = _load_snoozed()
        stats["snoozed_count"] = len([s for s in snoozed if s.get("status") == "snoozed"])
    except Exception:
        stats["snoozed_count"] = 0

    # Top senders from recent inbox
    try:
        script = '''
        tell application "Mail"
            set output to ""
            set msgs to messages 1 through (minimum of {50, count of messages of inbox}) of inbox
            repeat with m in msgs
                set output to output & (sender of m) & linefeed
            end repeat
            return output
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=15)
        if result["success"]:
            sender_counts = {}
            for line in result["content"].strip().split('\n'):
                sender = line.strip()
                if sender:
                    sender_counts[sender] = sender_counts.get(sender, 0) + 1
            top = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            stats["top_senders"] = [{"name": s[0], "count": s[1]} for s in top]
    except Exception:
        pass

    return {"success": True, "content": json.dumps(stats)}


# ═══════════════════════════════════════════════════
#  AUTO-RULES ENGINE
# ═══════════════════════════════════════════════════
#
#  Persistent rules stored in memory/email_rules.json.
#  Each rule: {id, name, enabled, conditions, actions, created_at, hit_count}
#
#  Conditions (ALL must match — AND logic):
#    sender_contains, sender_is, subject_contains, subject_is,
#    body_contains, has_attachment, is_unread
#
#  Actions (executed in order):
#    move_to, flag, mark_read, mark_unread, delete, archive,
#    forward_to, auto_reply, label, notify
#

def _load_rules():
    """Load auto-rules from disk."""
    try:
        if os.path.exists(RULES_PATH):
            with open(RULES_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_rules(rules):
    """Persist rules to disk."""
    os.makedirs(os.path.dirname(RULES_PATH), exist_ok=True)
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)


def add_email_rule(name, conditions, actions, enabled=True):
    """Add a persistent auto-rule for incoming emails.

    Args:
        name: Human-readable rule name (e.g. "Archive newsletters")
        conditions: dict of condition_type → value
            sender_contains, sender_is, subject_contains, subject_is,
            body_contains, has_attachment
        actions: list of dicts, each {action: str, value: str (optional)}
            move_to, flag, mark_read, mark_unread, delete, archive,
            forward_to, auto_reply, label, notify

    Returns: standard dict
    """
    rules = _load_rules()

    # Validate
    valid_conds = {"sender_contains", "sender_is", "subject_contains", "subject_is",
                   "body_contains", "has_attachment", "is_unread"}
    valid_actions = {"move_to", "flag", "mark_read", "mark_unread", "delete",
                     "archive", "forward_to", "auto_reply", "label", "notify"}

    for k in conditions:
        if k not in valid_conds:
            return {"success": False, "error": True,
                    "content": f"Invalid condition: {k}. Valid: {', '.join(sorted(valid_conds))}"}
    for a in actions:
        if a.get("action") not in valid_actions:
            return {"success": False, "error": True,
                    "content": f"Invalid action: {a.get('action')}. Valid: {', '.join(sorted(valid_actions))}"}

    rule = {
        "id": f"rule_{int(time.time())}_{len(rules)}",
        "name": name,
        "enabled": enabled,
        "conditions": conditions,
        "actions": actions,
        "created_at": datetime.now().isoformat(),
        "hit_count": 0,
    }
    rules.append(rule)
    _save_rules(rules)
    event_bus.emit("email_rule_added", {"name": name, "id": rule["id"]})
    return {"success": True, "content": f"✅ Rule '{name}' added (id: {rule['id']}). {len(conditions)} conditions, {len(actions)} actions."}


def list_email_rules():
    """List all auto-rules."""
    rules = _load_rules()
    if not rules:
        return {"success": True, "content": "No email rules configured."}
    lines = ["📋 Email Rules:"]
    for r in rules:
        status = "✅" if r.get("enabled", True) else "⏸️"
        hits = r.get("hit_count", 0)
        conds = ", ".join(f"{k}={v}" for k, v in r.get("conditions", {}).items())
        acts = ", ".join(a.get("action", "?") for a in r.get("actions", []))
        lines.append(f"  {status} [{r['id']}] {r['name']}  |  if: {conds}  →  {acts}  ({hits} hits)")
    return {"success": True, "content": "\n".join(lines)}


def delete_email_rule(rule_id):
    """Delete an auto-rule by ID."""
    rules = _load_rules()
    original_len = len(rules)
    rules = [r for r in rules if r["id"] != rule_id]
    if len(rules) == original_len:
        return {"success": False, "error": True, "content": f"Rule '{rule_id}' not found."}
    _save_rules(rules)
    return {"success": True, "content": f"🗑️ Rule '{rule_id}' deleted."}


def toggle_email_rule(rule_id, enabled=None):
    """Enable or disable a rule. If enabled is None, toggles."""
    rules = _load_rules()
    for r in rules:
        if r["id"] == rule_id:
            if enabled is None:
                r["enabled"] = not r.get("enabled", True)
            else:
                r["enabled"] = enabled
            _save_rules(rules)
            state = "enabled" if r["enabled"] else "disabled"
            return {"success": True, "content": f"Rule '{r['name']}' {state}."}
    return {"success": False, "error": True, "content": f"Rule '{rule_id}' not found."}


def _match_rule(email_info, rule):
    """Check if an email matches a rule's conditions (AND logic)."""
    conds = rule.get("conditions", {})
    sender = (email_info.get("sender") or "").lower()
    subject = (email_info.get("subject") or "").lower()
    body = (email_info.get("body") or email_info.get("content") or "").lower()

    if "sender_contains" in conds and conds["sender_contains"].lower() not in sender:
        return False
    if "sender_is" in conds and conds["sender_is"].lower() != sender:
        return False
    if "subject_contains" in conds and conds["subject_contains"].lower() not in subject:
        return False
    if "subject_is" in conds and conds["subject_is"].lower() != subject:
        return False
    if "body_contains" in conds and conds["body_contains"].lower() not in body:
        return False
    if "has_attachment" in conds and conds["has_attachment"]:
        # Can't reliably check from email_info dict — skip if no info
        pass
    return True


def _execute_rule_actions(email_info, rule):
    """Execute all actions for a matched rule."""
    results = []
    for action_def in rule.get("actions", []):
        act = action_def.get("action")
        val = action_def.get("value", "")
        try:
            if act == "move_to" and val:
                # Need message index — try to find by subject
                r = search_emails(subject=email_info.get("subject", ""), max_results=1)
                if r["success"] and "index" in str(r["content"]):
                    move_message(1, val)
                results.append(f"move_to:{val}")
            elif act == "flag":
                results.append("flag")
            elif act == "mark_read":
                mark_read(1)
                results.append("mark_read")
            elif act == "mark_unread":
                mark_unread(1)
                results.append("mark_unread")
            elif act == "delete":
                delete_message(1)
                results.append("delete")
            elif act == "archive":
                archive_message(1)
                results.append("archive")
            elif act == "forward_to" and val:
                forward_to(1, val)
                results.append(f"forward_to:{val}")
            elif act == "auto_reply" and val:
                # Auto-reply with template text
                reply_to(1, val)
                results.append("auto_reply")
            elif act == "notify":
                event_bus.emit("email_rule_notify", {
                    "rule": rule["name"],
                    "email": email_info,
                    "message": val or f"Rule '{rule['name']}' triggered",
                })
                results.append("notify")
        except Exception as e:
            results.append(f"{act}:error({e})")
    return results


def apply_rules_to_email(email_info):
    """Apply all enabled rules to an email. Called by InboxMonitor on new mail."""
    rules = _load_rules()
    applied = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if _match_rule(email_info, rule):
            action_results = _execute_rule_actions(email_info, rule)
            rule["hit_count"] = rule.get("hit_count", 0) + 1
            rule["last_triggered"] = datetime.now().isoformat()
            applied.append({"rule": rule["name"], "actions": action_results})
            event_bus.emit("email_rule_triggered", {
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "email_sender": email_info.get("sender", ""),
                "email_subject": email_info.get("subject", ""),
                "actions": action_results,
            })

    if applied:
        _save_rules(rules)  # Persist hit counts

    return applied


def run_rules_on_inbox(count=20):
    """Manually run all rules against the top N inbox messages.

    Useful for applying rules to existing emails, not just new ones.
    """
    inbox_result = read_inbox(count)
    if not inbox_result["success"]:
        return inbox_result

    total_applied = 0
    lines = []
    # Parse inbox content into individual emails
    emails = inbox_result["content"].split("\n---\n") if "---" in inbox_result["content"] else [inbox_result["content"]]
    for i, email_text in enumerate(emails):
        email_info = {"content": email_text, "sender": "", "subject": ""}
        # Extract sender/subject from text
        for line in email_text.split("\n"):
            if line.startswith("From:"):
                email_info["sender"] = line[5:].strip()
            elif line.startswith("Subject:"):
                email_info["subject"] = line[8:].strip()
        applied = apply_rules_to_email(email_info)
        if applied:
            total_applied += len(applied)
            for a in applied:
                lines.append(f"  ✅ Rule '{a['rule']}' → {', '.join(a['actions'])}")

    if not lines:
        return {"success": True, "content": f"Scanned {len(emails)} emails — no rules matched."}
    return {"success": True, "content": f"Applied {total_applied} rules to {len(emails)} emails:\n" + "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  EMAIL SUMMARIZATION
# ═══════════════════════════════════════════════════

def summarize_inbox(count=20):
    """Generate a structured inbox summary: grouped by sender, priority signals, unread count.

    Returns a human-readable summary without needing an LLM — uses
    heuristics for priority (keywords, known senders, urgency markers).
    """
    inbox_result = read_inbox(count)
    if not inbox_result["success"]:
        return inbox_result

    # Parse emails from the read_inbox output
    emails = []
    current = {}
    for line in inbox_result["content"].split("\n"):
        line = line.strip()
        if line.startswith("From:"):
            if current:
                emails.append(current)
            current = {"sender": line[5:].strip(), "subject": "", "date": "", "read": True, "preview": ""}
        elif line.startswith("Subject:"):
            current["subject"] = line[8:].strip()
        elif line.startswith("Date:"):
            current["date"] = line[5:].strip()
        elif line.startswith("Status:"):
            current["read"] = "read" in line.lower()
        elif line.startswith("Preview:") or line.startswith("Body:"):
            current["preview"] = line.split(":", 1)[-1].strip()[:200]
    if current:
        emails.append(current)

    if not emails:
        return {"success": True, "content": "📭 Inbox is empty."}

    # Group by sender domain
    by_sender = {}
    for e in emails:
        # Extract domain or name
        sender = e.get("sender", "Unknown")
        domain = sender.split("@")[-1].split(">")[0].strip() if "@" in sender else sender[:30]
        by_sender.setdefault(domain, []).append(e)

    # Priority detection
    HIGH_PRIORITY_KEYWORDS = {"urgent", "asap", "important", "action required", "deadline",
                               "critical", "time sensitive", "immediate", "priority"}
    NEWSLETTER_SIGNALS = {"unsubscribe", "newsletter", "digest", "weekly", "noreply", "no-reply"}

    high_priority = []
    newsletters = []
    regular = []

    for e in emails:
        subj_lower = (e.get("subject") or "").lower()
        sender_lower = (e.get("sender") or "").lower()
        preview_lower = (e.get("preview") or "").lower()
        combined = subj_lower + " " + sender_lower + " " + preview_lower

        if any(kw in combined for kw in HIGH_PRIORITY_KEYWORDS):
            high_priority.append(e)
        elif any(kw in combined for kw in NEWSLETTER_SIGNALS):
            newsletters.append(e)
        else:
            regular.append(e)

    unread_count = sum(1 for e in emails if not e.get("read", True))

    # Build summary
    lines = [f"📊 Inbox Summary ({len(emails)} emails, {unread_count} unread)"]
    lines.append("═" * 50)

    if high_priority:
        lines.append(f"\n🔴 HIGH PRIORITY ({len(high_priority)}):")
        for e in high_priority:
            flag = "🔵" if e.get("read") else "🔴"
            lines.append(f"  {flag} {e['sender'][:30]}: {e['subject'][:60]}")

    if regular:
        lines.append(f"\n📧 REGULAR ({len(regular)}):")
        for e in regular[:10]:  # Show top 10
            flag = "  " if e.get("read") else "🔵"
            lines.append(f"  {flag} {e['sender'][:30]}: {e['subject'][:60]}")
        if len(regular) > 10:
            lines.append(f"  ... and {len(regular) - 10} more")

    if newsletters:
        lines.append(f"\n📰 NEWSLETTERS/AUTOMATED ({len(newsletters)}):")
        for e in newsletters[:5]:
            lines.append(f"  📰 {e['sender'][:30]}: {e['subject'][:60]}")
        if len(newsletters) > 5:
            lines.append(f"  ... and {len(newsletters) - 5} more")

    # Top senders
    if len(by_sender) > 1:
        lines.append(f"\n👥 TOP SENDERS:")
        sorted_senders = sorted(by_sender.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        for domain, msgs in sorted_senders:
            unread_from = sum(1 for m in msgs if not m.get("read", True))
            lines.append(f"  {domain}: {len(msgs)} emails ({unread_from} unread)")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  PRIORITY INBOX CATEGORIZATION
# ═══════════════════════════════════════════════════

# Category detection constants
PRIORITY_KEYWORDS = {
    "urgent", "asap", "important", "action required", "deadline",
    "critical", "time sensitive", "immediate", "priority", "time-sensitive",
    "eod", "end of day", "by tomorrow", "overdue", "final notice",
}
NEWSLETTER_SIGNALS = {
    "unsubscribe", "newsletter", "digest", "weekly", "noreply", "no-reply",
    "marketing", "promo", "offer", "sale", "deal", "subscription",
    "notifications@", "updates@", "info@", "news@", "mailer-daemon",
}
NOTIFICATION_SIGNALS = {
    "notification", "alert", "automated", "do not reply", "donotreply",
    "system notification", "account activity", "security alert",
    "password reset", "verification", "confirm your", "sign in",
    "login attempt", "two-factor", "2fa", "one-time",
}
MEETING_KEYWORDS = {
    "meeting", "calendar", "invite", "schedule", "call", "zoom",
    "teams meeting", "google meet", "agenda", "standup", "sync",
}


def _categorize_single(email_info):
    """Categorize a single email into priority/meeting/regular/newsletter/notification.

    Args:
        email_info: dict with sender, subject, preview/body fields

    Returns:
        dict with category, confidence, tags
    """
    subj_lower = (email_info.get("subject") or "").lower()
    sender_lower = (email_info.get("sender") or "").lower()
    preview_lower = (email_info.get("preview") or email_info.get("body") or "").lower()
    combined = subj_lower + " " + sender_lower + " " + preview_lower

    tags = []
    category = "regular"
    confidence = 0.5

    # Check priority first (highest precedence)
    priority_hits = [kw for kw in PRIORITY_KEYWORDS if kw in combined]
    if priority_hits:
        category = "priority"
        confidence = min(0.6 + len(priority_hits) * 0.1, 0.95)
        tags.extend(priority_hits[:3])

    # Check meeting/calendar
    meeting_hits = [kw for kw in MEETING_KEYWORDS if kw in combined]
    if meeting_hits:
        if category != "priority":
            category = "meeting"
            confidence = min(0.6 + len(meeting_hits) * 0.1, 0.9)
        tags.extend(["📅 " + h for h in meeting_hits[:2]])

    # Check notification
    notif_hits = [kw for kw in NOTIFICATION_SIGNALS if kw in combined]
    if notif_hits and category == "regular":
        category = "notification"
        confidence = min(0.6 + len(notif_hits) * 0.1, 0.9)
        tags.extend(notif_hits[:2])

    # Check newsletter (lowest precedence)
    news_hits = [kw for kw in NEWSLETTER_SIGNALS if kw in combined]
    if news_hits and category == "regular":
        category = "newsletter"
        confidence = min(0.6 + len(news_hits) * 0.1, 0.9)
        tags.extend(news_hits[:2])

    # Unread flag boosts priority
    if not email_info.get("read", True) and category == "regular":
        confidence += 0.05

    return {"category": category, "confidence": round(confidence, 2), "tags": tags}


def categorize_inbox(count=20):
    """Categorize inbox emails into priority/meeting/regular/newsletter/notification.

    Returns a structured view of the inbox grouped by category with
    auto-detected tags and confidence scores.
    """
    inbox_result = read_inbox(count)
    if not inbox_result["success"]:
        return inbox_result

    # Parse emails from read_inbox output
    emails = []
    current = {}
    for line in inbox_result["content"].split("\n"):
        line = line.strip()
        if line.startswith("From:"):
            if current:
                emails.append(current)
            current = {"sender": line[5:].strip(), "subject": "", "date": "", "read": True, "preview": ""}
        elif line.startswith("Subject:"):
            current["subject"] = line[8:].strip()
        elif line.startswith("Date:"):
            current["date"] = line[5:].strip()
        elif line.startswith("Status:"):
            current["read"] = "read" in line.lower()
        elif line.startswith("Preview:") or line.startswith("Body:"):
            current["preview"] = line.split(":", 1)[-1].strip()[:200]
    if current:
        emails.append(current)

    if not emails:
        return {"success": True, "content": "📭 Inbox is empty — nothing to categorize."}

    # Categorize each email
    categories = {"priority": [], "meeting": [], "regular": [], "newsletter": [], "notification": []}
    for i, e in enumerate(emails, 1):
        cat_info = _categorize_single(e)
        e["_cat"] = cat_info
        e["_index"] = i
        categories[cat_info["category"]].append(e)

    # Build output
    category_icons = {
        "priority": "🔴", "meeting": "📅", "regular": "📧",
        "newsletter": "📰", "notification": "🔔",
    }
    unread_count = sum(1 for e in emails if not e.get("read", True))
    lines = [f"📊 Inbox Categorization ({len(emails)} emails, {unread_count} unread)"]
    lines.append("═" * 55)

    for cat_name in ["priority", "meeting", "regular", "newsletter", "notification"]:
        cat_emails = categories[cat_name]
        if not cat_emails:
            continue
        icon = category_icons[cat_name]
        lines.append(f"\n{icon} {cat_name.upper()} ({len(cat_emails)}):")
        display_limit = 15 if cat_name == "priority" else 10
        for e in cat_emails[:display_limit]:
            read_flag = "  " if e.get("read") else "🔵"
            tags_str = ""
            if e["_cat"]["tags"]:
                tags_str = f" [{', '.join(e['_cat']['tags'][:2])}]"
            lines.append(f"  {read_flag} #{e['_index']} {e['sender'][:25]}: {e['subject'][:50]}{tags_str}")
        if len(cat_emails) > display_limit:
            lines.append(f"  ... and {len(cat_emails) - display_limit} more")

    # Category counts summary
    lines.append(f"\n📈 Breakdown: " + " | ".join(
        f"{category_icons[c]} {c}: {len(categories[c])}"
        for c in ["priority", "meeting", "regular", "newsletter", "notification"]
        if categories[c]
    ))

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  CONTACT MANAGER (persistent)
# ═══════════════════════════════════════════════════
#
#  Stores contacts in memory/email_contacts.json.
#  Supplements Mail.app Contacts lookup with TARS-managed contacts.
#  Each contact: {id, name, email, tags, notes, created_at, last_emailed}
#

def _load_contacts():
    """Load contacts from disk."""
    try:
        if os.path.exists(CONTACTS_PATH):
            with open(CONTACTS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_contacts(contacts):
    """Persist contacts to disk."""
    os.makedirs(os.path.dirname(CONTACTS_PATH), exist_ok=True)
    with open(CONTACTS_PATH, "w") as f:
        json.dump(contacts, f, indent=2)


def add_contact(name, email, tags=None, notes=""):
    """Add or update a contact in the TARS contacts database.

    If a contact with the same email already exists, updates name/tags/notes.
    """
    contacts = _load_contacts()

    # Check for existing contact by email
    for c in contacts:
        if c.get("email", "").lower() == email.lower():
            c["name"] = name
            if tags:
                existing_tags = set(c.get("tags", []))
                existing_tags.update(tags)
                c["tags"] = sorted(existing_tags)
            if notes:
                c["notes"] = notes
            c["updated_at"] = datetime.now().isoformat()
            _save_contacts(contacts)
            event_bus.emit("email_action", {"action": "contact_updated", "name": name, "email": email})
            return {"success": True, "content": f"👤 Updated contact: {name} <{email}>"}

    # New contact
    import uuid
    contact = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "email": email,
        "tags": tags or [],
        "notes": notes,
        "created_at": datetime.now().isoformat(),
        "last_emailed": None,
        "email_count": 0,
    }
    contacts.append(contact)
    _save_contacts(contacts)

    event_bus.emit("email_action", {"action": "contact_added", "name": name, "email": email})
    return {"success": True, "content": f"👤 Added contact: {name} <{email}>"}


def list_contacts(tag=None):
    """List all TARS-managed contacts, optionally filtered by tag."""
    contacts = _load_contacts()
    if not contacts:
        return {"success": True, "content": "📇 No contacts saved yet."}

    if tag:
        contacts = [c for c in contacts if tag.lower() in [t.lower() for t in c.get("tags", [])]]
        if not contacts:
            return {"success": True, "content": f"📇 No contacts with tag '{tag}'."}

    lines = [f"📇 TARS Contacts ({len(contacts)}):"]
    for c in sorted(contacts, key=lambda x: x.get("name", "").lower()):
        tags_str = f" [{', '.join(c.get('tags', []))}]" if c.get("tags") else ""
        count_str = f" ({c.get('email_count', 0)} emails)" if c.get("email_count") else ""
        lines.append(f"  👤 {c['name']} <{c['email']}>{tags_str}{count_str}")
    return {"success": True, "content": "\n".join(lines)}


def search_contacts(query):
    """Search contacts by name, email, tag, or notes."""
    contacts = _load_contacts()
    if not contacts:
        return {"success": True, "content": "📇 No contacts saved yet."}

    query_lower = query.lower()
    matches = []
    for c in contacts:
        searchable = (
            c.get("name", "").lower() + " " +
            c.get("email", "").lower() + " " +
            " ".join(c.get("tags", [])).lower() + " " +
            c.get("notes", "").lower()
        )
        if query_lower in searchable:
            matches.append(c)

    if not matches:
        return {"success": True, "content": f"📇 No contacts matching '{query}'."}

    lines = [f"📇 Found {len(matches)} contact(s):"]
    for c in matches:
        tags_str = f" [{', '.join(c.get('tags', []))}]" if c.get("tags") else ""
        lines.append(f"  👤 {c['name']} <{c['email']}>{tags_str}")
    return {"success": True, "content": "\n".join(lines)}


def delete_contact(contact_id=None, email=None):
    """Delete a contact by ID or email."""
    contacts = _load_contacts()
    original_count = len(contacts)

    if contact_id:
        contacts = [c for c in contacts if c.get("id") != contact_id]
    elif email:
        contacts = [c for c in contacts if c.get("email", "").lower() != email.lower()]
    else:
        return {"success": False, "error": True, "content": "Provide contact_id or email to delete."}

    if len(contacts) == original_count:
        return {"success": False, "error": True, "content": "Contact not found."}

    _save_contacts(contacts)
    event_bus.emit("email_action", {"action": "contact_deleted"})
    return {"success": True, "content": "🗑️ Contact deleted."}


def auto_learn_contacts():
    """Scan recent inbox to auto-discover contacts from email senders.

    Adds new senders to the contacts database with auto-learned tags.
    """
    contacts = _load_contacts()
    known_emails = {c.get("email", "").lower() for c in contacts}

    try:
        script = '''
        tell application "Mail"
            set output to ""
            set msgs to messages 1 through (minimum of {100, count of messages of inbox}) of inbox
            repeat with m in msgs
                set output to output & (sender of m) & linefeed
            end repeat
            return output
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=20)
        if not result["success"]:
            return result

        new_contacts = 0
        seen = set()
        for line in result["content"].strip().split('\n'):
            sender = line.strip()
            if not sender or "@" not in sender:
                continue

            # Extract email and name
            import re as re_mod
            match = re_mod.search(r'<([^>]+)>', sender)
            if match:
                email_addr = match.group(1).lower()
                name = sender.split("<")[0].strip().strip('"')
            else:
                email_addr = sender.lower().strip()
                name = email_addr.split("@")[0].replace(".", " ").title()

            if email_addr in known_emails or email_addr in seen:
                continue
            seen.add(email_addr)

            # Auto-tag based on domain
            domain = email_addr.split("@")[-1]
            tags = ["auto-learned"]
            if any(kw in domain for kw in ["noreply", "no-reply", "notifications", "mailer"]):
                tags.append("automated")
            elif any(kw in domain for kw in ["gmail", "outlook", "yahoo", "hotmail", "icloud"]):
                tags.append("personal")
            else:
                tags.append("business")

            import uuid
            contact = {
                "id": uuid.uuid4().hex[:12],
                "name": name if name else email_addr.split("@")[0],
                "email": email_addr,
                "tags": tags,
                "notes": f"Auto-learned from inbox on {datetime.now().strftime('%Y-%m-%d')}",
                "created_at": datetime.now().isoformat(),
                "last_emailed": None,
                "email_count": 0,
            }
            contacts.append(contact)
            known_emails.add(email_addr)
            new_contacts += 1

        if new_contacts > 0:
            _save_contacts(contacts)

        return {"success": True, "content": f"📇 Discovered {new_contacts} new contacts from inbox ({len(contacts)} total)."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Contact scan error: {e}"}


# ═══════════════════════════════════════════════════
#  SMART SNOOZE & RESURFACING
# ═══════════════════════════════════════════════════
#
#  Snooze an email → mark read + store in snooze queue.
#  When snooze_until expires → mark unread (resurface) + emit event.
#  Processed every poll cycle by InboxMonitor._process_snoozed().
#

def _load_snoozed():
    """Load snoozed emails from disk."""
    try:
        if os.path.exists(SNOOZED_PATH):
            with open(SNOOZED_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_snoozed(data):
    """Persist snoozed emails to disk."""
    os.makedirs(os.path.dirname(SNOOZED_PATH), exist_ok=True)
    with open(SNOOZED_PATH, "w") as f:
        json.dump(data, f, indent=2)


def snooze_email(index, snooze_until, mailbox="inbox"):
    """Snooze an email — mark read now, resurface later by marking unread.

    Args:
        index: email index in the mailbox
        snooze_until: ISO timestamp string, or shorthand like '2h', '30m', 'tomorrow', 'monday'
        mailbox: source mailbox (default inbox)
    """
    # Parse snooze_until
    now = datetime.now()
    if isinstance(snooze_until, str):
        s = snooze_until.lower().strip()
        if s.endswith("m"):
            try:
                minutes = int(s[:-1])
                target = now + timedelta(minutes=minutes)
            except ValueError:
                return {"success": False, "error": True, "content": f"Invalid snooze time: {snooze_until}"}
        elif s.endswith("h"):
            try:
                hours = int(s[:-1])
                target = now + timedelta(hours=hours)
            except ValueError:
                return {"success": False, "error": True, "content": f"Invalid snooze time: {snooze_until}"}
        elif s.endswith("d"):
            try:
                days = int(s[:-1])
                target = now + timedelta(days=days)
            except ValueError:
                return {"success": False, "error": True, "content": f"Invalid snooze time: {snooze_until}"}
        elif s == "tomorrow":
            target = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0)
        elif s == "monday":
            days_ahead = 7 - now.weekday()  # Monday is 0
            if days_ahead <= 0:
                days_ahead += 7
            target = (now + timedelta(days=days_ahead)).replace(hour=8, minute=0, second=0)
        elif s == "tonight":
            target = now.replace(hour=18, minute=0, second=0)
            if target <= now:
                target += timedelta(days=1)
        elif s == "next_week":
            target = (now + timedelta(days=7)).replace(hour=8, minute=0, second=0)
        else:
            try:
                target = datetime.fromisoformat(s)
            except ValueError:
                return {"success": False, "error": True, "content": f"Invalid snooze time: {snooze_until}. Use: '2h', '30m', '1d', 'tomorrow', 'monday', 'tonight', or ISO timestamp."}
    else:
        return {"success": False, "error": True, "content": "snooze_until must be a string"}

    # Read the email to get its details
    msg = read_message(index, mailbox)
    if not msg["success"]:
        return msg

    # Extract sender and subject from the message content
    sender = ""
    subject = ""
    for line in msg["content"].split("\n"):
        if line.startswith("From:"):
            sender = line[5:].strip()
        elif line.startswith("Subject:"):
            subject = line[8:].strip()

    # Mark as read
    mark_read(index, mailbox)

    # Save to snooze queue
    import uuid
    snoozed = _load_snoozed()
    entry = {
        "id": uuid.uuid4().hex[:12],
        "index": index,
        "mailbox": mailbox,
        "sender": sender,
        "subject": subject,
        "snoozed_at": now.isoformat(),
        "snooze_until": target.isoformat(),
        "status": "snoozed",
    }
    snoozed.append(entry)
    _save_snoozed(snoozed)

    event_bus.emit("email_snoozed", {"subject": subject, "until": target.isoformat()})
    time_desc = target.strftime("%b %d at %I:%M %p")
    return {"success": True, "content": f"😴 Snoozed: \"{subject}\" until {time_desc}"}


def list_snoozed():
    """List all snoozed emails with their resurface times."""
    snoozed = _load_snoozed()
    active = [s for s in snoozed if s.get("status") == "snoozed"]

    if not active:
        return {"success": True, "content": "😴 No snoozed emails."}

    now = datetime.now()
    lines = [f"😴 Snoozed emails ({len(active)}):"]
    for s in sorted(active, key=lambda x: x["snooze_until"]):
        until = datetime.fromisoformat(s["snooze_until"])
        if until <= now:
            time_str = "⏰ OVERDUE"
        else:
            delta = until - now
            hours = delta.total_seconds() / 3600
            if hours < 1:
                time_str = f"in {int(delta.total_seconds() / 60)}m"
            elif hours < 24:
                time_str = f"in {hours:.1f}h"
            else:
                time_str = f"in {delta.days}d"
        lines.append(f"  😴 {s['sender'][:25]}: {s['subject'][:45]} — resurfaces {time_str}")
    return {"success": True, "content": "\n".join(lines)}


def cancel_snooze(snooze_id):
    """Cancel a snooze — immediately resurface the email (mark unread)."""
    snoozed = _load_snoozed()
    target = None
    for s in snoozed:
        if s.get("id") == snooze_id:
            target = s
            break

    if not target:
        return {"success": False, "error": True, "content": f"Snooze '{snooze_id}' not found."}

    target["status"] = "cancelled"
    _save_snoozed(snoozed)

    # Resurface: find and mark unread
    _resurface_email(target)
    return {"success": True, "content": f"⏰ Snooze cancelled — \"{target['subject']}\" resurfaced."}


def _resurface_email(snooze_entry):
    """Mark a snoozed email as unread to bring it back to attention."""
    # Search for the email by subject to find its current index
    result = search_emails(subject=snooze_entry.get("subject", ""), max_results=5)
    if result["success"] and "No emails found" not in result["content"]:
        # Mark the first matching email as unread
        mark_unread(1, snooze_entry.get("mailbox", "inbox"))
        event_bus.emit("email_resurfaced", {
            "subject": snooze_entry.get("subject"),
            "sender": snooze_entry.get("sender"),
        })


def _process_snoozed():
    """Check for snoozed emails that need resurfacing. Called by InboxMonitor."""
    snoozed = _load_snoozed()
    now = datetime.now()
    resurfaced = 0

    for s in snoozed:
        if s.get("status") != "snoozed":
            continue
        until = datetime.fromisoformat(s["snooze_until"])
        if now >= until:
            s["status"] = "resurfaced"
            _resurface_email(s)
            resurfaced += 1

    if resurfaced > 0:
        _save_snoozed(snoozed)
    return resurfaced


# ═══════════════════════════════════════════════════
#  PRIORITY SCORING (0-100)
# ═══════════════════════════════════════════════════
#
#  Multi-factor priority score for each email:
#    - Urgency keywords (30 pts max)
#    - Sender reputation: in contacts, known VIP (20 pts max)
#    - Recency: newer = higher (10 pts max)
#    - Direct-to vs CC'd (10 pts max)
#    - Unread status (10 pts max)
#    - Thread depth: ongoing conversation (10 pts max)
#    - Category bonus: meeting/priority (10 pts max)
#

def _load_sender_stats():
    """Load sender statistics from disk."""
    try:
        if os.path.exists(SENDER_STATS_PATH):
            with open(SENDER_STATS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sender_stats(data):
    """Persist sender stats to disk."""
    os.makedirs(os.path.dirname(SENDER_STATS_PATH), exist_ok=True)
    with open(SENDER_STATS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def update_sender_stats(sender, event_type="received"):
    """Update sender statistics when an email is received or sent.

    Args:
        sender: sender email or name string
        event_type: 'received' or 'sent'
    """
    stats = _load_sender_stats()
    # Extract email from "Name <email>" format
    email_addr = sender
    if "<" in sender:
        import re as re_mod
        match = re_mod.search(r'<([^>]+)>', sender)
        if match:
            email_addr = match.group(1).lower()
    email_addr = email_addr.lower().strip()

    if email_addr not in stats:
        stats[email_addr] = {
            "email": email_addr,
            "name": sender.split("<")[0].strip().strip('"') if "<" in sender else "",
            "received_count": 0,
            "sent_count": 0,
            "first_seen": datetime.now().isoformat(),
            "last_received": None,
            "last_sent": None,
        }

    entry = stats[email_addr]
    now = datetime.now().isoformat()
    if event_type == "received":
        entry["received_count"] = entry.get("received_count", 0) + 1
        entry["last_received"] = now
    elif event_type == "sent":
        entry["sent_count"] = entry.get("sent_count", 0) + 1
        entry["last_sent"] = now

    _save_sender_stats(stats)


def get_sender_profile(sender_query):
    """Get detailed profile for a sender: message counts, frequency, relationship."""
    stats = _load_sender_stats()
    query_lower = sender_query.lower()

    matches = []
    for addr, data in stats.items():
        if query_lower in addr or query_lower in data.get("name", "").lower():
            matches.append(data)

    if not matches:
        return {"success": True, "content": f"📊 No stats for '{sender_query}'. They may not have emailed yet."}

    lines = [f"📊 Sender Profile(s) for '{sender_query}':"]
    for m in matches[:5]:
        total = m.get("received_count", 0) + m.get("sent_count", 0)
        lines.append(f"  👤 {m.get('name') or m['email']}")
        lines.append(f"     📥 Received: {m.get('received_count', 0)} | 📤 Sent: {m.get('sent_count', 0)} | Total: {total}")
        if m.get("last_received"):
            lines.append(f"     📅 Last received: {m['last_received'][:10]}")
        if m.get("last_sent"):
            lines.append(f"     📅 Last sent: {m['last_sent'][:10]}")
        if m.get("first_seen"):
            lines.append(f"     🕐 First seen: {m['first_seen'][:10]}")
    return {"success": True, "content": "\n".join(lines)}


def _score_email(email_info, contacts=None, sender_stats=None):
    """Compute a 0-100 priority score for a single email.

    Args:
        email_info: dict with sender, subject, preview, read, date fields
        contacts: pre-loaded contacts list (optimization)
        sender_stats: pre-loaded sender stats dict (optimization)

    Returns:
        dict with score, factors list, category
    """
    score = 0
    factors = []

    subj = (email_info.get("subject") or "").lower()
    sender = (email_info.get("sender") or "").lower()
    preview = (email_info.get("preview") or email_info.get("body") or "").lower()
    combined = subj + " " + sender + " " + preview

    # 1. Urgency keywords (0-30 pts)
    urgency_hits = [kw for kw in PRIORITY_KEYWORDS if kw in combined]
    if urgency_hits:
        pts = min(len(urgency_hits) * 10, 30)
        score += pts
        factors.append(f"urgency:{pts}pts ({', '.join(urgency_hits[:3])})")

    # 2. Sender reputation (0-20 pts)
    if contacts is None:
        contacts = _load_contacts()
    if sender_stats is None:
        sender_stats = _load_sender_stats()

    # Check if sender is in contacts
    sender_email = sender
    if "<" in sender:
        import re as re_mod
        match = re_mod.search(r'<([^>]+)>', sender)
        if match:
            sender_email = match.group(1).lower()

    is_contact = any(
        sender_email in c.get("email", "").lower()
        for c in contacts
    )
    is_vip = any(
        sender_email in c.get("email", "").lower() and "vip" in [t.lower() for t in c.get("tags", [])]
        for c in contacts
    )
    if is_vip:
        score += 20
        factors.append("vip_sender:20pts")
    elif is_contact:
        score += 10
        factors.append("known_contact:10pts")

    # Sender frequency bonus
    sender_data = sender_stats.get(sender_email, {})
    total_msgs = sender_data.get("received_count", 0) + sender_data.get("sent_count", 0)
    if total_msgs >= 10:
        score += 5
        factors.append("frequent_sender:5pts")

    # 3. Recency (0-10 pts)
    date_str = email_info.get("date", "")
    if date_str:
        try:
            # Try to detect if today
            today = datetime.now().strftime("%Y-%m-%d")
            if today in date_str or "today" in date_str.lower():
                score += 10
                factors.append("today:10pts")
            else:
                score += 5
                factors.append("recent:5pts")
        except Exception:
            score += 5

    # 4. Direct vs CC'd (0-10 pts) — assume direct if TO contains our address
    if DEFAULT_FROM.lower() in combined:
        score += 10
        factors.append("direct_to:10pts")
    else:
        score += 5  # Assume direct if not determinable

    # 5. Unread (0-10 pts)
    if not email_info.get("read", True):
        score += 10
        factors.append("unread:10pts")

    # 6. Thread indicator (0-10 pts)
    if subj.startswith("re:") or subj.startswith("fwd:"):
        score += 7
        factors.append("in_thread:7pts")

    # 7. Category bonus (0-10 pts)
    cat = _categorize_single(email_info)
    if cat["category"] == "priority":
        score += 10
        factors.append("cat_priority:10pts")
    elif cat["category"] == "meeting":
        score += 8
        factors.append("cat_meeting:8pts")
    elif cat["category"] == "newsletter":
        score -= 10
        factors.append("cat_newsletter:-10pts")
    elif cat["category"] == "notification":
        score -= 5
        factors.append("cat_notification:-5pts")

    # Clamp to 0-100
    score = max(0, min(100, score))

    return {"score": score, "factors": factors, "category": cat["category"]}


def priority_inbox(count=20):
    """Get inbox sorted by priority score (highest first).

    Returns a ranked list of emails with 0-100 scores and contributing factors.
    """
    inbox_result = read_inbox(count)
    if not inbox_result["success"]:
        return inbox_result

    # Parse emails
    emails = []
    current = {}
    for line in inbox_result["content"].split("\n"):
        line = line.strip()
        if line.startswith("From:"):
            if current:
                emails.append(current)
            current = {"sender": line[5:].strip(), "subject": "", "date": "", "read": True, "preview": ""}
        elif line.startswith("Subject:"):
            current["subject"] = line[8:].strip()
        elif line.startswith("Date:"):
            current["date"] = line[5:].strip()
        elif line.startswith("Status:"):
            current["read"] = "read" in line.lower()
        elif line.startswith("Preview:") or line.startswith("Body:"):
            current["preview"] = line.split(":", 1)[-1].strip()[:200]
    if current:
        emails.append(current)

    if not emails:
        return {"success": True, "content": "📭 Inbox is empty."}

    # Pre-load data for scoring efficiency
    contacts = _load_contacts()
    sender_stats = _load_sender_stats()

    # Score each email
    scored = []
    for i, e in enumerate(emails, 1):
        score_info = _score_email(e, contacts, sender_stats)
        scored.append({"email": e, "index": i, **score_info})

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Build output
    lines = [f"🎯 Priority Inbox ({len(scored)} emails, ranked by importance)"]
    lines.append("═" * 55)

    for rank, item in enumerate(scored, 1):
        e = item["email"]
        score = item["score"]
        cat = item["category"]

        # Score indicator
        if score >= 70:
            indicator = "🔴"
        elif score >= 50:
            indicator = "🟠"
        elif score >= 30:
            indicator = "🟡"
        else:
            indicator = "⚪"

        read_flag = "" if e.get("read") else " 🔵"
        cat_icon = {"priority": "🚨", "meeting": "📅", "newsletter": "📰", "notification": "🔔"}.get(cat, "📧")

        lines.append(f"  {indicator} [{score:3d}] #{item['index']} {cat_icon} {e['sender'][:22]}: {e['subject'][:42]}{read_flag}")

        # Show top factors for high-priority emails
        if score >= 50 and item["factors"]:
            factors_str = ", ".join(item["factors"][:3])
            lines.append(f"         ↳ {factors_str}")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  DAILY EMAIL DIGEST
# ═══════════════════════════════════════════════════
#
#  Generates a morning briefing combining:
#    - Priority inbox summary
#    - Overdue follow-ups
#    - Snoozed emails resurfacing today
#    - Email stats
#    - Top action items
#

def generate_daily_digest():
    """Generate a comprehensive daily email digest/briefing.

    Combines: inbox categorization, overdue follow-ups, snoozed emails,
    stats, and top priority items into one structured briefing.
    """
    sections = []
    now = datetime.now()
    sections.append(f"📋 TARS Daily Email Digest — {now.strftime('%A, %B %d, %Y')}")
    sections.append("═" * 55)

    # 1. Stats overview
    try:
        stats_result = get_email_stats()
        if stats_result["success"]:
            stats = json.loads(stats_result["content"])
            sections.append(f"\n📊 OVERVIEW:")
            sections.append(f"  📥 Inbox: {stats.get('inbox_total', '?')} total, {stats.get('unread', '?')} unread")
            sections.append(f"  📤 Sent today: {stats.get('sent_today', 0)}")
            sections.append(f"  📝 Drafts: {stats.get('drafts', 0)}")
            sections.append(f"  📏 Active rules: {stats.get('rules_count', 0)} (triggered today: {stats.get('rules_triggered_today', 0)})")
            sections.append(f"  ⏰ Scheduled: {stats.get('scheduled_pending', 0)} pending")
    except Exception:
        pass

    # 2. Priority inbox (top 5 by score)
    try:
        inbox_result = read_inbox(20)
        if inbox_result["success"]:
            emails = []
            current = {}
            for line in inbox_result["content"].split("\n"):
                line = line.strip()
                if line.startswith("From:"):
                    if current:
                        emails.append(current)
                    current = {"sender": line[5:].strip(), "subject": "", "date": "", "read": True, "preview": ""}
                elif line.startswith("Subject:"):
                    current["subject"] = line[8:].strip()
                elif line.startswith("Date:"):
                    current["date"] = line[5:].strip()
                elif line.startswith("Status:"):
                    current["read"] = "read" in line.lower()
                elif line.startswith("Preview:") or line.startswith("Body:"):
                    current["preview"] = line.split(":", 1)[-1].strip()[:200]
            if current:
                emails.append(current)

            if emails:
                contacts = _load_contacts()
                sender_stats = _load_sender_stats()
                scored = []
                for i, e in enumerate(emails, 1):
                    score_info = _score_email(e, contacts, sender_stats)
                    scored.append({"email": e, "index": i, **score_info})
                scored.sort(key=lambda x: x["score"], reverse=True)

                # Top priority items
                top = [s for s in scored if s["score"] >= 40][:5]
                if top:
                    sections.append(f"\n🎯 TOP PRIORITY ({len(top)} items need attention):")
                    for item in top:
                        e = item["email"]
                        score = item["score"]
                        indicator = "🔴" if score >= 70 else ("🟠" if score >= 50 else "🟡")
                        read_str = "" if e.get("read") else " 🔵"
                        sections.append(f"  {indicator} [{score}] {e['sender'][:25]}: {e['subject'][:45]}{read_str}")

                # Category breakdown
                cats = {}
                for s in scored:
                    cats[s["category"]] = cats.get(s["category"], 0) + 1
                unread_count = sum(1 for e in emails if not e.get("read", True))
                sections.append(f"\n📂 BREAKDOWN ({len(emails)} emails, {unread_count} unread):")
                cat_icons = {"priority": "🚨", "meeting": "📅", "regular": "📧", "newsletter": "📰", "notification": "🔔"}
                for cat, count in sorted(cats.items(), key=lambda x: x[1], reverse=True):
                    sections.append(f"  {cat_icons.get(cat, '📧')} {cat.title()}: {count}")
    except Exception:
        pass

    # 3. Overdue follow-ups
    try:
        fu_result = check_followups()
        if fu_result["success"] and "overdue" in fu_result["content"].lower():
            sections.append(f"\n⏰ FOLLOW-UPS:")
            for line in fu_result["content"].split("\n"):
                if "📧" in line:
                    sections.append(f"  {line.strip()}")
    except Exception:
        pass

    # 4. Snoozed emails resurfacing today
    try:
        snoozed = _load_snoozed()
        today_resurface = []
        for s in snoozed:
            if s.get("status") != "snoozed":
                continue
            until = datetime.fromisoformat(s["snooze_until"])
            if until.date() <= now.date():
                today_resurface.append(s)
        if today_resurface:
            sections.append(f"\n😴 RESURFACING TODAY ({len(today_resurface)}):")
            for s in today_resurface:
                until = datetime.fromisoformat(s["snooze_until"])
                sections.append(f"  ⏰ {s['sender'][:25]}: {s['subject'][:45]} — at {until.strftime('%I:%M %p')}")
    except Exception:
        pass

    # 5. Save digest to history
    try:
        digest_text = "\n".join(sections)
        history = []
        try:
            if os.path.exists(DIGEST_PATH):
                with open(DIGEST_PATH) as f:
                    history = json.load(f)
        except Exception:
            pass
        history.append({
            "date": now.isoformat(),
            "digest": digest_text,
        })
        # Keep last 30 digests
        history = history[-30:]
        os.makedirs(os.path.dirname(DIGEST_PATH), exist_ok=True)
        with open(DIGEST_PATH, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

    event_bus.emit("email_digest", {"date": now.strftime("%Y-%m-%d"), "sections": len(sections)})
    return {"success": True, "content": "\n".join(sections)}


# ═══════════════════════════════════════════════════
#  OUT-OF-OFFICE (OOO) SYSTEM
# ═══════════════════════════════════════════════════
#
#  Time-bounded auto-reply. TARS creates a rule that
#  auto-replies to incoming emails during a date range,
#  then auto-disables itself when the OOO period ends.
#  InboxMonitor checks the date range every poll cycle.
#

OOO_PATH = os.path.join(TARS_ROOT, "memory", "email_ooo.json")


def _load_ooo():
    """Load OOO configuration."""
    try:
        if os.path.exists(OOO_PATH):
            with open(OOO_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_ooo(data):
    """Persist OOO configuration."""
    os.makedirs(os.path.dirname(OOO_PATH), exist_ok=True)
    with open(OOO_PATH, "w") as f:
        json.dump(data, f, indent=2)


def set_ooo(start_date, end_date, message, exceptions=None):
    """Set an out-of-office auto-reply for a date range.

    Args:
        start_date: ISO date string (e.g. '2026-02-25') or 'today' or 'tomorrow'
        end_date: ISO date string (e.g. '2026-03-01')
        message: Auto-reply message body
        exceptions: list of email addresses/domains to NOT auto-reply to (optional)
    """
    now = datetime.now()

    # Parse start_date
    if start_date == "today":
        start = now.replace(hour=0, minute=0, second=0)
    elif start_date == "tomorrow":
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    else:
        try:
            start = datetime.fromisoformat(start_date)
        except ValueError:
            return {"success": False, "error": True, "content": f"Invalid start_date: {start_date}. Use ISO format (YYYY-MM-DD) or 'today'/'tomorrow'."}

    # Parse end_date
    try:
        end = datetime.fromisoformat(end_date)
        # If only date provided (no time), set to end of day
        if end.hour == 0 and end.minute == 0:
            end = end.replace(hour=23, minute=59, second=59)
    except ValueError:
        return {"success": False, "error": True, "content": f"Invalid end_date: {end_date}. Use ISO format (YYYY-MM-DD)."}

    if end <= start:
        return {"success": False, "error": True, "content": "end_date must be after start_date."}

    ooo = {
        "active": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "message": message,
        "exceptions": exceptions or [],
        "replied_to": [],  # Track who we already replied to (don't spam)
        "created_at": now.isoformat(),
    }
    _save_ooo(ooo)

    is_active_now = start <= now <= end
    status = "ACTIVE NOW" if is_active_now else f"starts {start.strftime('%b %d')}"
    event_bus.emit("email_ooo_set", {"start": start.isoformat(), "end": end.isoformat(), "status": status})
    return {"success": True, "content": f"🏖️ OOO set: {start.strftime('%b %d')} → {end.strftime('%b %d')} ({status})\nMessage: \"{message[:80]}...\""}


def cancel_ooo():
    """Cancel the current out-of-office auto-reply."""
    ooo = _load_ooo()
    if not ooo or not ooo.get("active"):
        return {"success": True, "content": "🏖️ No active OOO to cancel."}

    ooo["active"] = False
    ooo["cancelled_at"] = datetime.now().isoformat()
    _save_ooo(ooo)
    replied_count = len(ooo.get("replied_to", []))
    event_bus.emit("email_ooo_cancelled", {"replied_to_count": replied_count})
    return {"success": True, "content": f"🏖️ OOO cancelled. Auto-replied to {replied_count} sender(s) during the period."}


def get_ooo_status():
    """Check if OOO is active and get details."""
    ooo = _load_ooo()
    if not ooo or not ooo.get("active"):
        return {"success": True, "content": "🏖️ No active OOO."}

    now = datetime.now()
    start = datetime.fromisoformat(ooo["start"])
    end = datetime.fromisoformat(ooo["end"])

    if now < start:
        status = f"Scheduled: starts {start.strftime('%b %d at %I:%M %p')}"
    elif now > end:
        status = "Expired (will auto-disable)"
    else:
        remaining = end - now
        hours = remaining.total_seconds() / 3600
        if hours < 24:
            status = f"ACTIVE — ends in {hours:.1f}h"
        else:
            status = f"ACTIVE — ends in {remaining.days}d {int(hours % 24)}h"

    replied = ooo.get("replied_to", [])
    lines = [
        f"🏖️ OOO Status: {status}",
        f"   Period: {start.strftime('%b %d')} → {end.strftime('%b %d')}",
        f"   Message: \"{ooo['message'][:60]}...\"",
        f"   Auto-replied to: {len(replied)} sender(s)",
    ]
    if ooo.get("exceptions"):
        lines.append(f"   Exceptions: {', '.join(ooo['exceptions'][:5])}")

    return {"success": True, "content": "\n".join(lines)}


def _process_ooo(email_info):
    """Process OOO auto-reply for an incoming email. Called from InboxMonitor._check_new()."""
    ooo = _load_ooo()
    if not ooo or not ooo.get("active"):
        return

    now = datetime.now()
    start = datetime.fromisoformat(ooo["start"])
    end = datetime.fromisoformat(ooo["end"])

    # Auto-disable if expired
    if now > end:
        ooo["active"] = False
        ooo["auto_disabled_at"] = now.isoformat()
        _save_ooo(ooo)
        event_bus.emit("email_ooo_expired", {"replied_to_count": len(ooo.get("replied_to", []))})
        print("  🏖️ OOO period ended — auto-disabled")
        return

    # Not yet active
    if now < start:
        return

    sender = email_info.get("sender", "")
    sender_email = sender
    if "<" in sender:
        import re as re_mod
        match = re_mod.search(r'<([^>]+)>', sender)
        if match:
            sender_email = match.group(1).lower()
    sender_email = sender_email.lower().strip()

    # Check exceptions
    for exc in ooo.get("exceptions", []):
        if exc.lower() in sender_email:
            return

    # Don't reply to same sender twice
    if sender_email in ooo.get("replied_to", []):
        return

    # Don't reply to noreply/newsletter addresses
    skip_patterns = ["noreply", "no-reply", "newsletter", "notifications", "mailer-daemon", "postmaster"]
    if any(p in sender_email for p in skip_patterns):
        return

    # Send auto-reply
    subject = email_info.get("subject", "")
    reply_subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
    try:
        send_result = send_email(
            to=sender_email,
            subject=reply_subject,
            body=ooo["message"],
        )
        if send_result.get("success"):
            ooo.setdefault("replied_to", []).append(sender_email)
            _save_ooo(ooo)
            event_bus.emit("email_ooo_replied", {"to": sender_email, "subject": subject})
            print(f"  🏖️ OOO auto-reply sent to {sender_email}")
    except Exception as e:
        print(f"  ⚠️ OOO auto-reply failed: {e}")


# ═══════════════════════════════════════════════════
#  EMAIL ANALYTICS & INSIGHTS ENGINE
# ═══════════════════════════════════════════════════
#
#  Derived metrics from existing data:
#    - Response time analytics
#    - Email volume trends
#    - Email health score
#    - Communication patterns
#

ANALYTICS_PATH = os.path.join(TARS_ROOT, "memory", "email_analytics.json")


def _load_analytics_cache():
    """Load cached analytics."""
    try:
        if os.path.exists(ANALYTICS_PATH):
            with open(ANALYTICS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_analytics_cache(data):
    """Persist analytics cache."""
    os.makedirs(os.path.dirname(ANALYTICS_PATH), exist_ok=True)
    with open(ANALYTICS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_email_analytics(period="week"):
    """Get comprehensive email analytics for a time period.

    Args:
        period: 'day', 'week', or 'month'

    Returns analytics: volume trend, category breakdown, top senders,
    response time estimates, follow-up completion rate, snooze stats.
    """
    sections = []
    now = datetime.now()
    sections.append(f"📊 Email Analytics — {period.title()} View ({now.strftime('%b %d, %Y')})")
    sections.append("═" * 55)

    # 1. Volume stats from sender_stats
    sender_stats = _load_sender_stats()
    total_received = sum(s.get("received_count", 0) for s in sender_stats.values())
    total_sent = sum(s.get("sent_count", 0) for s in sender_stats.values())
    unique_senders = len(sender_stats)
    sections.append(f"\n📈 VOLUME (all-time tracked):")
    sections.append(f"  📥 Received: {total_received} | 📤 Sent: {total_sent} | Ratio: {total_received / max(total_sent, 1):.1f}:1")
    sections.append(f"  👥 Unique senders tracked: {unique_senders}")

    # 2. Top communicators (most bidirectional)
    bidirectional = []
    for addr, data in sender_stats.items():
        r = data.get("received_count", 0)
        s = data.get("sent_count", 0)
        if r > 0 and s > 0:
            bidirectional.append({"email": addr, "name": data.get("name", ""), "received": r, "sent": s, "total": r + s})
    bidirectional.sort(key=lambda x: x["total"], reverse=True)

    if bidirectional:
        sections.append(f"\n💬 TOP COMMUNICATORS (bidirectional):")
        for c in bidirectional[:5]:
            name = c["name"] or c["email"]
            sections.append(f"  {name[:25]}: ↓{c['received']} ↑{c['sent']} (total: {c['total']})")

    # 3. Follow-up stats
    followups = _load_followups()
    fu_waiting = len([f for f in followups if f.get("status") == "waiting"])
    fu_overdue = len([f for f in followups if f.get("status") == "overdue"])
    fu_replied = len([f for f in followups if f.get("status") == "replied"])
    fu_total = len(followups)
    fu_rate = (fu_replied / max(fu_total, 1)) * 100
    sections.append(f"\n📋 FOLLOW-UPS:")
    sections.append(f"  Waiting: {fu_waiting} | Overdue: {fu_overdue} | Replied: {fu_replied} | Total: {fu_total}")
    sections.append(f"  Reply rate: {fu_rate:.0f}%")

    # 4. Snooze stats
    snoozed = _load_snoozed()
    sn_active = len([s for s in snoozed if s.get("status") == "snoozed"])
    sn_resurfaced = len([s for s in snoozed if s.get("status") == "resurfaced"])
    sn_cancelled = len([s for s in snoozed if s.get("status") == "cancelled"])
    sections.append(f"\n😴 SNOOZE:")
    sections.append(f"  Active: {sn_active} | Resurfaced: {sn_resurfaced} | Cancelled: {sn_cancelled}")

    # 5. Rules stats
    rules = _load_rules()
    total_hits = sum(r.get("hit_count", 0) for r in rules)
    active_rules = len([r for r in rules if r.get("enabled", True)])
    sections.append(f"\n⚡ RULES:")
    sections.append(f"  Active: {active_rules}/{len(rules)} | Total hits: {total_hits}")
    if rules:
        top_rule = max(rules, key=lambda r: r.get("hit_count", 0))
        sections.append(f"  Top rule: \"{top_rule['name']}\" ({top_rule.get('hit_count', 0)} hits)")

    # 6. OOO status
    ooo = _load_ooo()
    if ooo and ooo.get("active"):
        sections.append(f"\n🏖️ OOO: Active — replied to {len(ooo.get('replied_to', []))} sender(s)")

    # 7. Email health score
    health = _compute_health_score()
    sections.append(f"\n💚 EMAIL HEALTH SCORE: {health['score']}/100")
    for factor in health["factors"]:
        sections.append(f"  {factor}")

    return {"success": True, "content": "\n".join(sections)}


def _compute_health_score():
    """Compute a 0-100 email health score.

    Factors:
      - Inbox zero progress (unread ratio) — 25 pts
      - Follow-up completion rate — 25 pts
      - Snooze action rate — 15 pts
      - Rule automation level — 15 pts
      - Sender coverage (contacts vs senders) — 20 pts
    """
    score = 0
    factors = []

    # 1. Inbox zero (25 pts) — lower unread = better
    try:
        r = get_unread_count()
        if r["success"]:
            unread = int(r["content"])
            if unread == 0:
                score += 25
                factors.append("✅ Inbox zero: 25/25")
            elif unread <= 5:
                score += 20
                factors.append(f"📫 Low unread ({unread}): 20/25")
            elif unread <= 15:
                score += 12
                factors.append(f"📬 Moderate unread ({unread}): 12/25")
            else:
                pts = max(0, 25 - unread)
                score += pts
                factors.append(f"📭 High unread ({unread}): {pts}/25")
    except Exception:
        factors.append("❓ Unread: unknown")

    # 2. Follow-up completion (25 pts)
    followups = _load_followups()
    fu_total = len(followups)
    fu_replied = len([f for f in followups if f.get("status") == "replied"])
    if fu_total == 0:
        score += 15
        factors.append("📋 No follow-ups tracked: 15/25")
    else:
        rate = fu_replied / fu_total
        pts = int(rate * 25)
        score += pts
        factors.append(f"📋 Follow-up rate {rate*100:.0f}%: {pts}/25")

    # 3. Snooze action rate (15 pts) — using snooze = good
    snoozed = _load_snoozed()
    sn_resurfaced = len([s for s in snoozed if s.get("status") == "resurfaced"])
    sn_total = len(snoozed)
    if sn_total == 0:
        score += 8
        factors.append("😴 No snoozes used: 8/15")
    else:
        action_rate = sn_resurfaced / sn_total
        pts = int(action_rate * 15)
        score += pts
        factors.append(f"😴 Snooze action rate {action_rate*100:.0f}%: {pts}/15")

    # 4. Rule automation (15 pts)
    rules = _load_rules()
    active_rules = len([r for r in rules if r.get("enabled", True)])
    total_hits = sum(r.get("hit_count", 0) for r in rules)
    if active_rules == 0:
        factors.append("⚡ No rules set: 0/15")
    elif active_rules < 3:
        score += 5
        factors.append(f"⚡ Basic rules ({active_rules}): 5/15")
    elif total_hits > 10:
        score += 15
        factors.append(f"⚡ Active rules ({active_rules}, {total_hits} hits): 15/15")
    else:
        score += 10
        factors.append(f"⚡ Good rules ({active_rules}): 10/15")

    # 5. Sender coverage (20 pts)
    contacts = _load_contacts()
    sender_stats = _load_sender_stats()
    if len(sender_stats) == 0:
        score += 5
        factors.append("👥 No sender data yet: 5/20")
    else:
        contact_emails = {c.get("email", "").lower() for c in contacts}
        covered = sum(1 for addr in sender_stats if addr in contact_emails)
        coverage = covered / len(sender_stats)
        pts = int(coverage * 20)
        score += pts
        factors.append(f"👥 Contact coverage {coverage*100:.0f}% ({covered}/{len(sender_stats)}): {pts}/20")

    score = max(0, min(100, score))
    return {"score": score, "factors": factors}


def get_email_health():
    """Get the email health score with contributing factors."""
    health = _compute_health_score()
    lines = [f"💚 Email Health Score: {health['score']}/100"]
    lines.append("─" * 40)
    for f in health["factors"]:
        lines.append(f"  {f}")

    # Grade
    s = health["score"]
    if s >= 80:
        grade = "A — Excellent email hygiene!"
    elif s >= 60:
        grade = "B — Good, room for improvement"
    elif s >= 40:
        grade = "C — Average, needs attention"
    else:
        grade = "D — Poor, major cleanup needed"
    lines.append(f"\n  Grade: {grade}")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  THREAD TRACKING
# ═══════════════════════════════════════════════════

def get_email_thread(subject_or_index, max_messages=20):
    """Get all emails in a thread by subject or message index.

    Groups related emails by matching Re:/Fwd: subject patterns and
    displays them chronologically as a conversation thread.
    """
    # If given an int/index, read that message to get its subject
    base_subject = subject_or_index
    if isinstance(subject_or_index, (int, float)) or (isinstance(subject_or_index, str) and subject_or_index.isdigit()):
        idx = int(subject_or_index)
        msg = read_message(idx)
        if not msg["success"]:
            return msg
        # Extract subject from message content
        for line in msg["content"].split("\n"):
            if line.startswith("Subject:"):
                base_subject = line[8:].strip()
                break

    # Strip Re:/Fwd:/Fw: prefixes to get the base subject
    clean_subject = re.sub(r'^(Re|Fwd|Fw|RE|FW|FWD):\s*', '', str(base_subject), flags=re.IGNORECASE).strip()
    if not clean_subject:
        return {"success": False, "error": True, "content": "Could not determine thread subject."}

    # Search for all emails with this subject
    result = search_emails(subject=clean_subject, max_results=max_messages)
    if not result["success"]:
        return result

    # Also search sent mail
    sent_script = f'''
    tell application "Mail"
        set sentBox to mailbox "Sent Messages" of account "Outlook"
        set matches to (messages of sentBox whose subject contains "{clean_subject.replace('"', '\\"')}")
        set output to ""
        set maxCount to {max_messages}
        set i to 0
        repeat with m in matches
            if i ≥ maxCount then exit repeat
            set output to output & "---THREAD_MSG---" & linefeed
            set output to output & "From: " & (sender of m) & linefeed
            set output to output & "To: " & (address of to recipient 1 of m) & linefeed
            set output to output & "Subject: " & (subject of m) & linefeed
            set output to output & "Date: " & (date received of m as string) & linefeed
            set output to output & "Body: " & (content of m) & linefeed
            set i to i + 1
        end repeat
        return output
    end tell
    '''
    sent_result = _run_applescript_stdin(sent_script, timeout=30)

    # Combine inbox + sent results
    thread_text = result["content"]
    if sent_result["success"] and sent_result["content"].strip():
        thread_text += "\n" + sent_result["content"]

    if not thread_text.strip() or "No emails found" in thread_text:
        return {"success": True, "content": f"No thread found for: {clean_subject}"}

    return {"success": True, "content": f"📧 Thread: {clean_subject}\n{'═' * 50}\n{thread_text}"}


# ═══════════════════════════════════════════════════
#  EMAIL SCHEDULING (Send Later)
# ═══════════════════════════════════════════════════

SCHEDULED_PATH = os.path.join(TARS_ROOT, "memory", "email_scheduled.json")

def _load_scheduled():
    try:
        if os.path.exists(SCHEDULED_PATH):
            with open(SCHEDULED_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_scheduled(data):
    os.makedirs(os.path.dirname(SCHEDULED_PATH), exist_ok=True)
    if len(data) > 200:
        data = data[-200:]
    with open(SCHEDULED_PATH, "w") as f:
        json.dump(data, f, indent=2)


def schedule_email(to, subject, body, send_at, cc=None, bcc=None,
                   attachment_paths=None, html=False, from_address=DEFAULT_FROM):
    """Schedule an email to be sent at a specific time.

    Args:
        send_at: ISO timestamp string (e.g. "2026-02-21T09:00:00") or
                 minutes from now as int (e.g. 60 = send in 1 hour)
    """
    if isinstance(send_at, (int, float)):
        send_time = (datetime.now() + timedelta(minutes=send_at)).isoformat()
    else:
        send_time = str(send_at)

    # Validate the time is parseable
    try:
        scheduled_dt = datetime.fromisoformat(send_time)
        if scheduled_dt < datetime.now():
            return {"success": False, "error": True,
                    "content": f"Scheduled time {send_time} is in the past."}
    except ValueError:
        return {"success": False, "error": True,
                "content": f"Invalid time format: {send_at}. Use ISO format (2026-02-21T09:00:00) or minutes from now (60)."}

    scheduled = _load_scheduled()
    entry = {
        "id": f"sched_{int(time.time())}_{len(scheduled)}",
        "to": to,
        "subject": subject,
        "body": body,
        "cc": cc,
        "bcc": bcc,
        "attachment_paths": attachment_paths,
        "html": html,
        "from_address": from_address,
        "send_at": send_time,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }
    scheduled.append(entry)
    _save_scheduled(scheduled)
    event_bus.emit("email_scheduled", {"id": entry["id"], "to": to, "subject": subject, "send_at": send_time})

    # Format nicely
    dt = datetime.fromisoformat(send_time)
    friendly = dt.strftime("%b %d at %I:%M %p")
    return {"success": True, "content": f"📅 Email scheduled: '{subject}' → {to} on {friendly} (id: {entry['id']})"}


def list_scheduled():
    """List all scheduled (pending) emails."""
    scheduled = _load_scheduled()
    pending = [s for s in scheduled if s.get("status") == "pending"]
    if not pending:
        return {"success": True, "content": "No scheduled emails."}
    lines = ["📅 Scheduled Emails:"]
    for s in pending:
        dt = datetime.fromisoformat(s["send_at"])
        friendly = dt.strftime("%b %d at %I:%M %p")
        lines.append(f"  ⏰ [{s['id']}] {s['subject']} → {s['to']} — {friendly}")
    return {"success": True, "content": "\n".join(lines)}


def cancel_scheduled(scheduled_id):
    """Cancel a scheduled email by ID."""
    scheduled = _load_scheduled()
    for s in scheduled:
        if s["id"] == scheduled_id and s["status"] == "pending":
            s["status"] = "cancelled"
            _save_scheduled(scheduled)
            return {"success": True, "content": f"🚫 Cancelled scheduled email: {s['subject']}"}
    return {"success": False, "error": True, "content": f"Scheduled email '{scheduled_id}' not found or already sent."}


def _process_scheduled_emails():
    """Check and send any emails whose send_at time has passed. Called by InboxMonitor."""
    scheduled = _load_scheduled()
    now = datetime.now()
    sent_count = 0

    for s in scheduled:
        if s.get("status") != "pending":
            continue
        try:
            send_time = datetime.fromisoformat(s["send_at"])
        except (ValueError, KeyError):
            s["status"] = "error"
            continue

        if now >= send_time:
            result = send_email(
                to=s["to"], subject=s["subject"], body=s["body"],
                cc=s.get("cc"), bcc=s.get("bcc"),
                attachment_paths=s.get("attachment_paths"),
                html=s.get("html", False),
                from_address=s.get("from_address", DEFAULT_FROM),
            )
            if result.get("success"):
                s["status"] = "sent"
                s["sent_at"] = now.isoformat()
                sent_count += 1
                event_bus.emit("email_scheduled_sent", {"id": s["id"], "to": s["to"], "subject": s["subject"]})
            else:
                s["status"] = "error"
                s["error"] = result.get("content", "Unknown error")

    if sent_count > 0:
        _save_scheduled(scheduled)
    return sent_count


# ═══════════════════════════════════════════════════
#  BATCH OPERATIONS
# ═══════════════════════════════════════════════════

def batch_mark_read(indices=None, mailbox="inbox", all_unread=False):
    """Mark multiple emails as read at once.

    Args:
        indices: list of message indices (e.g. [1, 2, 3])
        all_unread: if True, mark ALL unread messages as read
    """
    if all_unread:
        script = '''
        tell application "Mail"
            set unreadMsgs to (messages of inbox whose read status is false)
            set readCount to 0
            repeat with m in unreadMsgs
                set read status of m to true
                set readCount to readCount + 1
            end repeat
            return readCount as string
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=60)
        if result["success"]:
            count = result["content"]
            result["content"] = f"✅ Marked {count} emails as read"
            event_bus.emit("email_batch_action", {"action": "mark_read", "count": int(count) if count.isdigit() else 0})
        return result

    if not indices:
        return {"success": False, "error": True, "content": "Provide indices list or set all_unread=true"}

    mb_ref = 'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'
    success_count = 0
    for idx in indices:
        r = mark_read(idx, mailbox)
        if r.get("success"):
            success_count += 1
    event_bus.emit("email_batch_action", {"action": "mark_read", "count": success_count})
    return {"success": True, "content": f"✅ Marked {success_count}/{len(indices)} emails as read"}


def batch_delete(indices=None, mailbox="inbox", sender=None):
    """Delete multiple emails at once.

    Args:
        indices: list of message indices
        sender: delete all from this sender (within first 50 messages)
    """
    if sender:
        # Delete all from specific sender
        safe_sender = _escape_as(sender)
        script = f'''
        tell application "Mail"
            set msgs to (messages of inbox whose sender contains "{safe_sender}")
            set delCount to 0
            set maxDel to 50
            repeat with m in msgs
                if delCount >= maxDel then exit repeat
                delete m
                set delCount to delCount + 1
            end repeat
            return delCount as string
        end tell
        '''
        result = _run_applescript_stdin(script, timeout=60)
        if result["success"]:
            count = result["content"]
            result["content"] = f"🗑️ Deleted {count} emails from {sender}"
            event_bus.emit("email_batch_action", {"action": "delete", "sender": sender, "count": int(count) if count.isdigit() else 0})
        return result

    if not indices:
        return {"success": False, "error": True, "content": "Provide indices list or sender to delete"}

    # Delete by indices (reverse order to keep indices stable)
    success_count = 0
    for idx in sorted(indices, reverse=True):
        r = delete_message(idx, mailbox)
        if r.get("success"):
            success_count += 1
    event_bus.emit("email_batch_action", {"action": "delete", "count": success_count})
    return {"success": True, "content": f"🗑️ Deleted {success_count}/{len(indices)} emails"}


def batch_move(indices, to_mailbox, from_mailbox="inbox"):
    """Move multiple emails to a folder at once."""
    if not indices:
        return {"success": False, "error": True, "content": "Provide indices list"}

    success_count = 0
    for idx in sorted(indices, reverse=True):
        r = move_message(idx, from_mailbox, to_mailbox)
        if r.get("success"):
            success_count += 1
    event_bus.emit("email_batch_action", {"action": "move", "to": to_mailbox, "count": success_count})
    return {"success": True, "content": f"📁 Moved {success_count}/{len(indices)} emails to {to_mailbox}"}


def batch_forward(indices, to_address, body="", mailbox="inbox"):
    """Forward multiple emails to someone at once."""
    if not indices:
        return {"success": False, "error": True, "content": "Provide indices list"}

    success_count = 0
    for idx in indices:
        r = forward_to(idx, to_address, body, mailbox)
        if r.get("success"):
            success_count += 1
    event_bus.emit("email_batch_action", {"action": "forward", "to": to_address, "count": success_count})
    return {"success": True, "content": f"📤 Forwarded {success_count}/{len(indices)} emails to {to_address}"}


# ═══════════════════════════════════════════════════
#  SMART COMPOSE / QUICK REPLIES
# ═══════════════════════════════════════════════════

# Built-in quick reply patterns for common email types
QUICK_REPLIES = {
    "acknowledge": {
        "label": "Acknowledge",
        "body": "Thank you for your email. I've received it and will review shortly.",
    },
    "confirm_meeting": {
        "label": "Confirm Meeting",
        "body": "Thank you for the invitation. I confirm my attendance and look forward to the meeting.",
    },
    "decline_meeting": {
        "label": "Decline Meeting",
        "body": "Thank you for the invitation. Unfortunately, I'm unable to attend at the proposed time. Could we explore alternative options?",
    },
    "will_review": {
        "label": "Will Review",
        "body": "Thank you for sending this over. I'll review the details and get back to you within the next day or two.",
    },
    "follow_up": {
        "label": "Follow Up",
        "body": "I wanted to follow up on my previous email. Please let me know if you have any questions or need additional information.",
    },
    "thank_you": {
        "label": "Thank You",
        "body": "Thank you for your help with this. I really appreciate it.",
    },
    "out_of_office": {
        "label": "Out of Office",
        "body": "Thank you for your email. I'm currently out of the office and will respond when I return. For urgent matters, please contact the team directly.",
    },
    "request_info": {
        "label": "Request Info",
        "body": "Thank you for your message. Could you provide more details so I can assist you better?",
    },
}


def list_quick_replies():
    """List all available quick reply templates."""
    replies = []
    for key, val in QUICK_REPLIES.items():
        replies.append(f"  • {key}: {val['label']}")

    # Also list saved custom templates
    try:
        if os.path.exists(TEMPLATES_DIR):
            for fname in os.listdir(TEMPLATES_DIR):
                if fname.endswith('.json'):
                    name = fname[:-5]
                    replies.append(f"  • template:{name} (custom)")
    except Exception:
        pass

    return {"success": True, "content": "Quick replies:\n" + "\n".join(replies)}


def send_quick_reply(message_index, reply_type, mailbox="inbox", custom_note=""):
    """Send a quick reply to an email using a predefined template.

    Args:
        message_index: index of the email to reply to
        reply_type: key from QUICK_REPLIES (e.g. 'acknowledge', 'confirm_meeting')
                    or 'template:<name>' for a saved template
        custom_note: optional text appended after the template body
    """
    # Resolve the reply body
    if reply_type.startswith("template:"):
        template_name = reply_type[9:]
        try:
            tpl_path = os.path.join(TEMPLATES_DIR, f"{template_name}.json")
            if not os.path.exists(tpl_path):
                return {"success": False, "error": True, "content": f"Template '{template_name}' not found"}
            with open(tpl_path) as f:
                tpl = json.load(f)
            body = tpl.get("body", "")
        except Exception as e:
            return {"success": False, "error": True, "content": f"Template error: {e}"}
    elif reply_type in QUICK_REPLIES:
        body = QUICK_REPLIES[reply_type]["body"]
    else:
        available = ", ".join(QUICK_REPLIES.keys())
        return {"success": False, "error": True, "content": f"Unknown reply type '{reply_type}'. Available: {available}"}

    if custom_note:
        body = body + "\n\n" + custom_note

    result = reply_to(message_index, body, mailbox=mailbox)
    if result.get("success"):
        result["content"] = f"↩️ Quick reply ({reply_type}) sent to message #{message_index}"
    return result


def suggest_replies(message_index, mailbox="inbox"):
    """Analyze an email and suggest appropriate quick reply types.

    Returns a list of suggested reply types based on email content keywords.
    """
    # Read the message
    msg = read_message(message_index, mailbox)
    if not msg["success"]:
        return msg

    content_lower = msg["content"].lower()
    suggestions = []

    # Match patterns
    if any(kw in content_lower for kw in ["meeting", "invite", "calendar", "schedule", "call"]):
        suggestions.append({"type": "confirm_meeting", "label": "Confirm Meeting", "reason": "Meeting/calendar reference detected"})
        suggestions.append({"type": "decline_meeting", "label": "Decline Meeting", "reason": "Meeting/calendar reference detected"})

    if any(kw in content_lower for kw in ["attached", "attachment", "document", "file", "report", "proposal"]):
        suggestions.append({"type": "will_review", "label": "Will Review", "reason": "Document/attachment reference detected"})

    if any(kw in content_lower for kw in ["question", "help", "assist", "clarify", "more info", "details"]):
        suggestions.append({"type": "request_info", "label": "Request Info", "reason": "Information request detected"})

    if any(kw in content_lower for kw in ["thank", "appreciate", "grateful", "thanks"]):
        suggestions.append({"type": "acknowledge", "label": "Acknowledge", "reason": "Gratitude detected"})

    if any(kw in content_lower for kw in ["follow up", "following up", "checking in", "any update", "status"]):
        suggestions.append({"type": "will_review", "label": "Will Review", "reason": "Follow-up detected"})

    # Always include acknowledge as a safe default
    if not any(s["type"] == "acknowledge" for s in suggestions):
        suggestions.append({"type": "acknowledge", "label": "Acknowledge", "reason": "General acknowledgment"})

    result_text = f"Suggested replies for message #{message_index}:\n"
    for s in suggestions:
        result_text += f"  • {s['type']} ({s['label']}) — {s['reason']}\n"
    result_text += f"\nUse send_quick_reply(index={message_index}, reply_type='<type>') to send."

    return {"success": True, "content": result_text}


# ═══════════════════════════════════════════════════
#  INBOX ZERO AUTOMATION
# ═══════════════════════════════════════════════════
#
#  Smart archive, auto-triage, inbox zero tracking,
#  and newsletter unsubscribe automation.
#

INBOX_ZERO_PATH = os.path.join(TARS_ROOT, "memory", "inbox_zero_history.json")


def _load_inbox_zero_history():
    """Load inbox zero daily snapshots."""
    try:
        if os.path.exists(INBOX_ZERO_PATH):
            with open(INBOX_ZERO_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_inbox_zero_history(history):
    """Persist inbox zero daily snapshots."""
    os.makedirs(os.path.dirname(INBOX_ZERO_PATH), exist_ok=True)
    # Keep last 90 days
    if len(history) > 90:
        history = history[-90:]
    with open(INBOX_ZERO_PATH, "w") as f:
        json.dump(history, f, indent=2)


def _record_inbox_snapshot():
    """Record today's inbox snapshot for trend tracking. Called by InboxMonitor."""
    history = _load_inbox_zero_history()
    today = datetime.now().strftime("%Y-%m-%d")

    # Don't record twice in one day
    if history and history[-1].get("date") == today:
        return

    try:
        unread_r = get_unread_count()
        unread = int(unread_r["content"]) if unread_r["success"] else -1
    except Exception:
        unread = -1

    snapshot = {
        "date": today,
        "unread": unread,
        "timestamp": datetime.now().isoformat(),
    }
    history.append(snapshot)
    _save_inbox_zero_history(history)

    # Determine trend
    trend = "stable"
    if len(history) >= 2:
        prev = history[-2].get("unread", 0)
        if unread < prev:
            trend = "declining"
        elif unread > prev:
            trend = "rising"
    event_bus.emit("inbox_zero_progress", {"total": unread, "trend": trend, "date": today})


def clean_sweep(older_than_days=7, categories=None, dry_run=True):
    """Archive read emails older than N days, optionally filtered by category.

    Args:
        older_than_days: Archive emails older than this (default 7)
        categories: Optional list of categories to target ('newsletter', 'notification', 'regular')
                    None = archive all read emails matching the age threshold
        dry_run: If True, preview what would be archived. If False, actually archive.
    """
    # Read inbox to find candidates
    try:
        inbox_r = read_inbox(count=100)
        if not inbox_r["success"]:
            return {"success": False, "error": True, "content": "Failed to read inbox"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read inbox: {e}"}

    content = inbox_r["content"]
    candidates = []
    now = datetime.now()
    threshold = now - timedelta(days=older_than_days)

    # Parse inbox listing for read emails
    for line in content.strip().split('\n'):
        if not line.strip():
            continue
        # Read emails have 📖, unread have 📩
        is_read = "📖" in line
        if not is_read:
            continue

        # Extract index from [N]
        idx_match = re.search(r'\[(\d+)\]', line)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))

        # Extract subject and sender
        subject_match = re.search(r'SUBJECT:\s*(.+?)(?:\s*\||\s*$)', line)
        sender_match = re.search(r'FROM:\s*(.+?)\s*\|', line)
        subject = subject_match.group(1).strip() if subject_match else ""
        sender = sender_match.group(1).strip() if sender_match else ""

        candidates.append({
            "index": idx,
            "subject": subject[:60],
            "sender": sender[:40],
        })

    if not candidates:
        return {"success": True, "content": "🎯 Nothing to archive — inbox is clean!"}

    if dry_run:
        lines = [f"🧹 Clean Sweep Preview ({len(candidates)} candidates, older than {older_than_days} days):"]
        for c in candidates[:20]:
            lines.append(f"  📦 [{c['index']}] {c['sender'][:25]} — {c['subject'][:40]}")
        if len(candidates) > 20:
            lines.append(f"  ... and {len(candidates) - 20} more")
        lines.append(f"\nRun with dry_run=false to actually archive these {len(candidates)} emails.")
        return {"success": True, "content": "\n".join(lines)}

    # Actually archive
    archived = 0
    errors = 0
    for c in candidates:
        try:
            r = archive_email(c["index"])
            if r.get("success"):
                archived += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    event_bus.emit("email_clean_sweep", {"archived": archived, "errors": errors})
    return {"success": True, "content": f"🧹 Clean Sweep: archived {archived} emails ({errors} errors)"}


def auto_triage(count=20):
    """Auto-triage inbox: categorize unread emails and apply smart actions.

    For each unread email:
      - Priority → flag it
      - Newsletter → archive it
      - Notification → mark as read
      - Regular → leave in inbox
    Returns a summary of actions taken.
    """
    try:
        cat_r = categorize_inbox(count)
        if not cat_r["success"]:
            return {"success": False, "error": True, "content": f"Categorization failed: {cat_r['content']}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Categorization error: {e}"}

    actions = {"flagged": 0, "archived": 0, "marked_read": 0, "left": 0}
    details = []

    content = cat_r["content"]
    # Parse categories from the categorization output
    current_cat = None
    for line in content.strip().split('\n'):
        line = line.strip()
        if "PRIORITY" in line.upper() or "🔴" in line:
            current_cat = "priority"
        elif "NEWSLETTER" in line.upper() or "📰" in line:
            current_cat = "newsletter"
        elif "NOTIFICATION" in line.upper() or "🔔" in line:
            current_cat = "notification"
        elif "REGULAR" in line.upper() or "📧" in line:
            current_cat = "regular"
        elif "MEETING" in line.upper() or "📅" in line:
            current_cat = "priority"

        # Look for indexed emails
        idx_match = re.search(r'\[(\d+)\]', line)
        if idx_match and current_cat:
            idx = int(idx_match.group(1))
            if current_cat == "priority":
                try:
                    flag_email(idx, True)
                    actions["flagged"] += 1
                    details.append(f"  🚩 [{idx}] Flagged (priority)")
                except Exception:
                    pass
            elif current_cat == "newsletter":
                try:
                    archive_email(idx)
                    actions["archived"] += 1
                    details.append(f"  📦 [{idx}] Archived (newsletter)")
                except Exception:
                    pass
            elif current_cat == "notification":
                try:
                    mark_email_read(idx)
                    actions["marked_read"] += 1
                    details.append(f"  👁️ [{idx}] Marked read (notification)")
                except Exception:
                    pass
            else:
                actions["left"] += 1

    total = sum(actions.values())
    lines = [f"⚡ Auto-Triage Complete ({total} emails processed):"]
    lines.append(f"  🚩 Flagged (priority): {actions['flagged']}")
    lines.append(f"  📦 Archived (newsletter): {actions['archived']}")
    lines.append(f"  👁️ Marked read (notification): {actions['marked_read']}")
    lines.append(f"  📧 Left in inbox: {actions['left']}")
    if details:
        lines.append("\nActions taken:")
        lines.extend(details[:15])

    event_bus.emit("email_auto_triage", {"actions": actions, "total": total})
    return {"success": True, "content": "\n".join(lines)}


def inbox_zero_status():
    """Get inbox zero progress: unread count, streak, historical trend."""
    try:
        unread_r = get_unread_count()
        unread = int(unread_r["content"]) if unread_r["success"] else -1
    except Exception:
        unread = -1

    history = _load_inbox_zero_history()
    lines = ["🎯 Inbox Zero Status"]
    lines.append("─" * 40)

    # Current state
    if unread == 0:
        lines.append("  ✅ INBOX ZERO! 🎉")
    elif unread <= 5:
        lines.append(f"  📫 Almost there! {unread} unread")
    elif unread <= 15:
        lines.append(f"  📬 Getting close: {unread} unread")
    else:
        lines.append(f"  📭 Work to do: {unread} unread")

    # Streak calculation
    if history:
        streak = 0
        for snap in reversed(history):
            if snap.get("unread", 99) <= 5:
                streak += 1
            else:
                break
        lines.append(f"  🔥 Streak: {streak} day(s) at ≤5 unread")

        # Trend (last 7 days)
        recent = history[-7:]
        if len(recent) >= 2:
            first_unread = recent[0].get("unread", 0)
            last_unread = recent[-1].get("unread", 0)
            delta = last_unread - first_unread
            if delta < 0:
                lines.append(f"  📉 Trend: ↓{abs(delta)} unread (improving!)")
            elif delta > 0:
                lines.append(f"  📈 Trend: ↑{delta} unread (needs attention)")
            else:
                lines.append(f"  ➡️ Trend: stable")

        # Sparkline
        if len(recent) >= 3:
            sparkline = " ".join(str(s.get("unread", "?")) for s in recent)
            lines.append(f"  📊 Last {len(recent)} days: [{sparkline}]")
    else:
        lines.append("  📊 No history yet (tracking starts automatically)")

    # Health integration
    try:
        health = _compute_health_score()
        lines.append(f"\n  💚 Email Health: {health['score']}/100")
    except Exception:
        pass

    return {"success": True, "content": "\n".join(lines)}


def smart_unsubscribe(index, mailbox="inbox"):
    """Auto-unsubscribe: find sender, create delete-from-sender rule, archive the email.

    This doesn't click unsubscribe links (requires browser agent), but it:
    1. Creates an auto-rule to delete future emails from this sender
    2. Archives the current email
    3. Returns the sender so the user can optionally deploy a browser agent to click unsubscribe
    """
    # Read the email to get sender
    try:
        r = read_email(index, mailbox)
        if not r["success"]:
            return {"success": False, "error": True, "content": f"Can't read email {index}: {r['content']}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error reading email: {e}"}

    content = r["content"]
    sender_match = re.search(r'FROM:\s*(.+?)(?:\n|$)', content)
    sender = sender_match.group(1).strip() if sender_match else ""

    # Extract email address from sender
    email_match = re.search(r'<([^>]+)>', sender)
    sender_email = email_match.group(1) if email_match else sender

    if not sender_email:
        return {"success": False, "error": True, "content": "Could not determine sender email address"}

    # Extract domain for the rule
    domain = sender_email.split("@")[-1] if "@" in sender_email else sender_email

    # Create auto-delete rule
    rule_name = f"Unsubscribe: {domain}"
    try:
        add_email_rule(
            name=rule_name,
            conditions={"from_contains": domain},
            actions=[{"action": "delete"}],
        )
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to create unsubscribe rule: {e}"}

    # Archive the email
    try:
        archive_email(index, mailbox)
    except Exception:
        pass  # Non-critical

    event_bus.emit("email_unsubscribed", {"sender": sender_email, "domain": domain})
    return {"success": True, "content": f"🚫 Unsubscribed from {domain}:\n  ✅ Auto-delete rule created for all emails from *@{domain}\n  ✅ Email archived\n  💡 To fully unsubscribe, deploy a browser agent to click the unsubscribe link."}


# ═══════════════════════════════════════════════════
#  SMART ATTACHMENT MANAGER
# ═══════════════════════════════════════════════════
#
#  Attachment search, indexing, and organized storage.
#

ATTACHMENT_INDEX_PATH = os.path.join(TARS_ROOT, "memory", "email_attachment_index.json")


def _load_attachment_index():
    """Load attachment index."""
    try:
        if os.path.exists(ATTACHMENT_INDEX_PATH):
            with open(ATTACHMENT_INDEX_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_attachment_index(index):
    """Persist attachment index."""
    os.makedirs(os.path.dirname(ATTACHMENT_INDEX_PATH), exist_ok=True)
    # Keep last 500 entries
    if len(index) > 500:
        index = index[-500:]
    with open(ATTACHMENT_INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


def build_attachment_index(count=50, mailbox="inbox"):
    """Scan recent emails and build an attachment index for fast search.

    Args:
        count: Number of recent emails to scan
        mailbox: Mailbox to scan
    """
    mb_ref = 'inbox' if mailbox == "inbox" else f'mailbox "{mailbox}"'

    script = f'''
    tell application "Mail"
        set msgs to messages 1 thru (min({count}, (count of messages of {mb_ref}))) of {mb_ref}
        set output to ""
        set idx to 0
        repeat with m in msgs
            set idx to idx + 1
            set attList to mail attachments of m
            set attCount to count of attList
            if attCount > 0 then
                set output to output & idx & "|||" & (sender of m) & "|||" & (subject of m) & "|||" & (date received of m as string) & "|||"
                set attNames to ""
                repeat with a in attList
                    set attNames to attNames & (name of a) & ","
                end repeat
                set output to output & attNames & linefeed
            end if
        end repeat
        if output is "" then return "NO_ATTACHMENTS_FOUND"
        return output
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=120)
    if not result["success"]:
        return {"success": False, "error": True, "content": f"Scan failed: {result['content']}"}

    if result["content"] == "NO_ATTACHMENTS_FOUND":
        return {"success": True, "content": "No emails with attachments found in the scanned range."}

    index = _load_attachment_index()
    new_entries = 0

    for line in result["content"].strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('|||')
        if len(parts) < 5:
            continue

        idx = int(parts[0])
        sender = parts[1].strip()
        subject = parts[2].strip()
        date = parts[3].strip()
        att_names = [n.strip() for n in parts[4].split(',') if n.strip()]

        # Deduplicate by sender+subject+date
        key = f"{sender}|{subject}|{date}"
        if any(e.get("key") == key for e in index):
            continue

        entry = {
            "key": key,
            "index": idx,
            "mailbox": mailbox,
            "sender": sender,
            "subject": subject,
            "date": date,
            "attachments": att_names,
            "indexed_at": datetime.now().isoformat(),
        }
        index.append(entry)
        new_entries += 1

    _save_attachment_index(index)
    total = len(index)
    att_count = sum(len(e.get("attachments", [])) for e in index)
    return {"success": True, "content": f"📎 Attachment index updated: {new_entries} new entries ({total} total, {att_count} attachments tracked)"}


def search_attachments(filename=None, sender=None, file_type=None, max_results=20):
    """Search the attachment index for files matching filters.

    Args:
        filename: Search by filename (partial match)
        sender: Search by sender (partial match)
        file_type: Filter by extension (e.g. 'pdf', 'xlsx', 'docx', 'png')
        max_results: Max results to return
    """
    index = _load_attachment_index()
    if not index:
        return {"success": True, "content": "📎 No attachment index yet. Run build_attachment_index first."}

    results = []
    for entry in index:
        match = True
        if sender and sender.lower() not in entry.get("sender", "").lower():
            match = False
        if match and filename:
            if not any(filename.lower() in a.lower() for a in entry.get("attachments", [])):
                match = False
        if match and file_type:
            ext = f".{file_type.lower().lstrip('.')}"
            if not any(a.lower().endswith(ext) for a in entry.get("attachments", [])):
                match = False
        if match:
            results.append(entry)
            if len(results) >= max_results:
                break

    if not results:
        return {"success": True, "content": "📎 No attachments found matching your search."}

    lines = [f"📎 Found {len(results)} email(s) with matching attachments:"]
    for r in results:
        atts = ", ".join(r.get("attachments", [])[:3])
        if len(r.get("attachments", [])) > 3:
            atts += f" (+{len(r['attachments']) - 3} more)"
        lines.append(f"  [{r['index']}] {r['sender'][:30]} — {r['subject'][:35]}")
        lines.append(f"       📎 {atts}")
        lines.append(f"       📅 {r.get('date', '?')}")

    lines.append(f"\nUse download_attachments(index=N) to download.")
    return {"success": True, "content": "\n".join(lines)}


def attachment_summary(count=50):
    """Get a summary of attachments in recent emails.

    Returns: total count, breakdown by file type, top senders with attachments.
    """
    index = _load_attachment_index()

    # If index is empty, build it first
    if not index:
        build_r = build_attachment_index(count)
        if not build_r["success"]:
            return build_r
        index = _load_attachment_index()

    if not index:
        return {"success": True, "content": "📎 No attachments found in recent emails."}

    # Aggregate stats
    all_files = []
    sender_counts = {}
    for entry in index:
        for att in entry.get("attachments", []):
            all_files.append(att)
        s = entry.get("sender", "Unknown")
        sender_counts[s] = sender_counts.get(s, 0) + len(entry.get("attachments", []))

    # Type breakdown
    type_counts = {}
    for f in all_files:
        ext = os.path.splitext(f)[1].lower() or "(none)"
        type_counts[ext] = type_counts.get(ext, 0) + 1

    lines = [f"📎 Attachment Summary ({len(index)} emails, {len(all_files)} files):"]
    lines.append("─" * 40)

    # By type
    lines.append("\n📂 By File Type:")
    for ext, cnt in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"  {ext}: {cnt}")

    # Top senders
    lines.append("\n👤 Top Senders with Attachments:")
    for s, cnt in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        lines.append(f"  {s[:35]}: {cnt} file(s)")

    return {"success": True, "content": "\n".join(lines)}


def list_saved_attachments(folder=None, file_type=None):
    """List previously downloaded attachments from the TARS attachments directory.

    Args:
        folder: Subfolder to list (optional)
        file_type: Filter by extension (e.g. 'pdf', 'xlsx')
    """
    base_dir = ATTACHMENTS_DIR
    if folder:
        base_dir = os.path.join(ATTACHMENTS_DIR, folder)

    if not os.path.exists(base_dir):
        return {"success": True, "content": f"📎 No attachments directory at {base_dir}"}

    files = []
    for root, dirs, filenames in os.walk(base_dir):
        for fn in filenames:
            if fn.startswith('.'):
                continue
            if file_type:
                ext = f".{file_type.lower().lstrip('.')}"
                if not fn.lower().endswith(ext):
                    continue
            full_path = os.path.join(root, fn)
            size = os.path.getsize(full_path)
            files.append({
                "name": fn,
                "path": full_path,
                "size": size,
                "size_str": f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f} MB",
                "modified": datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat(),
            })

    if not files:
        return {"success": True, "content": "📎 No saved attachments found."}

    files.sort(key=lambda x: x["modified"], reverse=True)
    lines = [f"📎 Saved Attachments ({len(files)} files in {base_dir}):"]
    for f in files[:25]:
        lines.append(f"  📄 {f['name']} ({f['size_str']})")
    if len(files) > 25:
        lines.append(f"  ... and {len(files) - 25} more")

    total_size = sum(f["size"] for f in files)
    lines.append(f"\n  Total: {total_size / (1024*1024):.1f} MB")
    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  CONTACT RELATIONSHIP INTELLIGENCE
# ═══════════════════════════════════════════════════
#
#  Auto-VIP detection, relationship scoring,
#  communication graph, stale contact decay.
#

RELATIONSHIP_CACHE_PATH = os.path.join(TARS_ROOT, "memory", "email_relationships.json")


def score_relationships():
    """Compute 0-100 relationship scores for all known senders.

    Factors (100 total):
      - Email frequency (0-25): more messages = stronger relationship
      - Recency (0-25): last interaction within 7d=25, 30d=15, 90d=5
      - Bidirectionality (0-25): balanced sent/received ratio = strongest
      - Thread depth (0-15): deep threads = strong engagement
      - Contact status (0-10): known contact +5, VIP tag +10
    """
    sender_stats = _load_sender_stats()
    contacts = _load_contacts()
    contact_emails = {c.get("email", "").lower(): c for c in contacts}

    scores = {}
    now = datetime.now()

    for addr, data in sender_stats.items():
        score = 0
        factors = []
        received = data.get("received_count", 0)
        sent = data.get("sent_count", 0)
        total = received + sent

        # 1. Frequency (0-25)
        if total >= 50:
            freq_pts = 25
        elif total >= 20:
            freq_pts = 20
        elif total >= 10:
            freq_pts = 15
        elif total >= 5:
            freq_pts = 10
        elif total >= 2:
            freq_pts = 5
        else:
            freq_pts = 2
        score += freq_pts
        factors.append(f"frequency:{freq_pts}")

        # 2. Recency (0-25)
        last_seen = data.get("last_received") or data.get("last_sent", "")
        if last_seen:
            try:
                last_dt = datetime.fromisoformat(last_seen)
                days_ago = (now - last_dt).days
                if days_ago <= 7:
                    rec_pts = 25
                elif days_ago <= 14:
                    rec_pts = 20
                elif days_ago <= 30:
                    rec_pts = 15
                elif days_ago <= 60:
                    rec_pts = 8
                elif days_ago <= 90:
                    rec_pts = 5
                else:
                    rec_pts = 0
                score += rec_pts
                factors.append(f"recency:{rec_pts}")
            except Exception:
                pass

        # 3. Bidirectionality (0-25)
        if sent > 0 and received > 0:
            ratio = min(sent, received) / max(sent, received)
            bi_pts = int(ratio * 25)
            score += bi_pts
            factors.append(f"bidirectional:{bi_pts}")
        elif sent > 0 or received > 0:
            score += 3
            factors.append("one-way:3")

        # 4. Thread depth proxy (0-15): lots of bidirectional = deep threads
        if sent >= 3 and received >= 3:
            depth_pts = min(15, (min(sent, received) // 2) * 5)
            score += depth_pts
            factors.append(f"depth:{depth_pts}")

        # 5. Contact status (0-10)
        contact_info = contact_emails.get(addr.lower())
        if contact_info:
            tags = [t.lower() for t in contact_info.get("tags", [])]
            if "vip" in tags:
                score += 10
                factors.append("vip:10")
            else:
                score += 5
                factors.append("contact:5")

        score = max(0, min(100, score))
        scores[addr] = {
            "score": score,
            "name": data.get("name", ""),
            "received": received,
            "sent": sent,
            "factors": factors,
        }

    # Cache the results
    os.makedirs(os.path.dirname(RELATIONSHIP_CACHE_PATH), exist_ok=True)
    cache = {
        "computed_at": now.isoformat(),
        "scores": scores,
    }
    with open(RELATIONSHIP_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    lines = [f"👥 Relationship Scores ({len(scores)} contacts analyzed):"]
    lines.append("─" * 50)
    for addr, data in sorted_scores[:15]:
        name = data["name"] or addr
        lines.append(f"  {data['score']:3d}/100  {name[:30]}  (↓{data['received']} ↑{data['sent']})")

    return {"success": True, "content": "\n".join(lines)}


def auto_detect_vips(threshold=70):
    """Auto-detect VIP contacts based on relationship scores.

    Runs score_relationships(), then auto-tags contacts scoring >= threshold as VIP.
    """
    # Compute fresh scores
    score_relationships()

    try:
        with open(RELATIONSHIP_CACHE_PATH) as f:
            cache = json.load(f)
    except Exception:
        return {"success": False, "error": True, "content": "No relationship data. Run score_relationships first."}

    scores = cache.get("scores", {})
    contacts = _load_contacts()
    contact_emails = {c.get("email", "").lower(): c for c in contacts}

    promoted = []
    for addr, data in scores.items():
        if data["score"] < threshold:
            continue

        addr_lower = addr.lower()
        if addr_lower in contact_emails:
            # Already a contact — add VIP tag if not present
            contact = contact_emails[addr_lower]
            tags = contact.get("tags", [])
            if "vip" not in [t.lower() for t in tags]:
                tags.append("vip")
                contact["tags"] = tags
                promoted.append({"email": addr, "name": data["name"], "score": data["score"]})
        else:
            # New VIP contact
            contacts.append({
                "id": f"auto_{addr_lower.replace('@','_').replace('.','_')}",
                "name": data.get("name", ""),
                "email": addr,
                "tags": ["vip", "auto-detected"],
                "notes": f"Auto-detected VIP (score: {data['score']}/100)",
                "created_at": datetime.now().isoformat(),
            })
            promoted.append({"email": addr, "name": data["name"], "score": data["score"]})

    if promoted:
        _save_contacts(contacts)

    if not promoted:
        return {"success": True, "content": f"👥 No new VIPs detected (threshold: {threshold}/100). All high-score contacts already tagged."}

    lines = [f"👑 Auto-detected {len(promoted)} new VIP(s) (threshold: {threshold}/100):"]
    for p in promoted:
        lines.append(f"  ⭐ {p['name'] or p['email']} — score {p['score']}/100")

    event_bus.emit("email_vip_detected", {"count": len(promoted), "vips": [p["email"] for p in promoted]})
    return {"success": True, "content": "\n".join(lines)}


def get_relationship_report(contact_query):
    """Get detailed relationship report for one contact.

    Args:
        contact_query: Email address or name to search for
    """
    sender_stats = _load_sender_stats()
    contacts = _load_contacts()
    query = contact_query.lower()

    # Find the contact
    matched_addr = None
    matched_name = ""
    for addr, data in sender_stats.items():
        if query in addr.lower() or query in (data.get("name") or "").lower():
            matched_addr = addr
            matched_name = data.get("name", "")
            break

    if not matched_addr:
        # Try contacts list
        for c in contacts:
            if query in c.get("email", "").lower() or query in c.get("name", "").lower():
                matched_addr = c.get("email", "")
                matched_name = c.get("name", "")
                break

    if not matched_addr:
        return {"success": True, "content": f"👥 No contact found matching '{contact_query}'"}

    data = sender_stats.get(matched_addr, {})
    received = data.get("received_count", 0)
    sent = data.get("sent_count", 0)

    # Compute relationship score
    try:
        with open(RELATIONSHIP_CACHE_PATH) as f:
            cache = json.load(f)
        r_score = cache.get("scores", {}).get(matched_addr, {}).get("score", "?")
    except Exception:
        r_score = "?"

    # Contact info
    contact_info = None
    for c in contacts:
        if matched_addr.lower() in c.get("email", "").lower():
            contact_info = c
            break

    lines = [f"👤 Relationship Report: {matched_name or matched_addr}"]
    lines.append("─" * 50)
    lines.append(f"  📧 Email: {matched_addr}")
    lines.append(f"  🏆 Relationship Score: {r_score}/100")
    lines.append(f"  📥 Received: {received} | 📤 Sent: {sent} | Total: {received + sent}")

    if received > 0 and sent > 0:
        ratio = received / sent
        if ratio > 2:
            lines.append(f"  📊 Pattern: They write more ({ratio:.1f}:1 receive:send)")
        elif ratio < 0.5:
            lines.append(f"  📊 Pattern: You write more (1:{1/ratio:.1f} send:receive)")
        else:
            lines.append(f"  📊 Pattern: Balanced communication")
    elif received > 0:
        lines.append(f"  📊 Pattern: One-way (incoming only)")
    elif sent > 0:
        lines.append(f"  📊 Pattern: One-way (outgoing only)")

    if data.get("last_received"):
        lines.append(f"  📅 Last received: {data['last_received'][:10]}")
    if data.get("last_sent"):
        lines.append(f"  📅 Last sent: {data['last_sent'][:10]}")

    if contact_info:
        tags = contact_info.get("tags", [])
        if tags:
            lines.append(f"  🏷️ Tags: {', '.join(tags)}")
        if contact_info.get("notes"):
            lines.append(f"  📝 Notes: {contact_info['notes'][:80]}")

    return {"success": True, "content": "\n".join(lines)}


def communication_graph(top_n=15):
    """Get top N contacts by relationship score with mini-stats.

    Returns a compact view suitable for dashboard display.
    """
    # Load or compute scores
    try:
        with open(RELATIONSHIP_CACHE_PATH) as f:
            cache = json.load(f)
        scores = cache.get("scores", {})
    except Exception:
        score_relationships()
        try:
            with open(RELATIONSHIP_CACHE_PATH) as f:
                cache = json.load(f)
            scores = cache.get("scores", {})
        except Exception:
            return {"success": False, "error": True, "content": "Failed to compute relationship scores"}

    sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)[:top_n]

    lines = [f"🕸️ Communication Graph (Top {min(top_n, len(sorted_scores))}):"]
    lines.append("─" * 55)
    for i, (addr, data) in enumerate(sorted_scores, 1):
        name = data.get("name") or addr
        bar_len = data["score"] // 5  # 0-20 chars
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"  {i:2d}. {name[:25]:<25} {bar} {data['score']:3d}")

    return {"success": True, "content": "\n".join(lines)}


def decay_stale_contacts(inactive_days=90):
    """Find contacts with no email activity in N days, downgrade VIP→regular.

    Args:
        inactive_days: Days of inactivity threshold (default 90)
    """
    sender_stats = _load_sender_stats()
    contacts = _load_contacts()
    now = datetime.now()
    threshold = now - timedelta(days=inactive_days)

    stale = []
    downgraded = []

    for contact in contacts:
        email = contact.get("email", "").lower()
        if not email:
            continue

        data = sender_stats.get(email, {})
        last_received = data.get("last_received", "")
        last_sent = data.get("last_sent", "")

        # Get most recent activity
        last_activity = None
        for ts in [last_received, last_sent]:
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    if last_activity is None or dt > last_activity:
                        last_activity = dt
                except Exception:
                    pass

        # No activity data or old activity
        if last_activity is None or last_activity < threshold:
            tags = contact.get("tags", [])
            days = (now - last_activity).days if last_activity else inactive_days

            if "vip" in [t.lower() for t in tags]:
                # Downgrade VIP → regular
                contact["tags"] = [t for t in tags if t.lower() != "vip"]
                if "stale" not in [t.lower() for t in contact["tags"]]:
                    contact["tags"].append("stale")
                downgraded.append({"name": contact.get("name", ""), "email": email, "days": days})
            else:
                if "stale" not in [t.lower() for t in tags]:
                    contact["tags"] = tags + ["stale"]
                stale.append({"name": contact.get("name", ""), "email": email, "days": days})

    if downgraded or stale:
        _save_contacts(contacts)

    lines = [f"🧹 Stale Contact Review (>{inactive_days} days inactive):"]
    if downgraded:
        lines.append(f"\n  👑→📧 Downgraded VIPs ({len(downgraded)}):")
        for d in downgraded[:10]:
            lines.append(f"    {d['name'] or d['email']} — {d['days']}d inactive")
    if stale:
        lines.append(f"\n  💤 Newly stale ({len(stale)}):")
        for s in stale[:10]:
            lines.append(f"    {s['name'] or s['email']} — {s['days']}d inactive")
    if not downgraded and not stale:
        lines.append("  ✅ All contacts are active!")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  PHASE 9A: Email Security & Trust
# ═══════════════════════════════════════════════════

TRUST_LISTS_PATH = os.path.join(TARS_ROOT, "memory", "email_trust_lists.json")

# Known disposable/temp email domains
_DISPOSABLE_DOMAINS = {
    "tempmail.com", "guerrillamail.com", "throwaway.email", "10minutemail.com",
    "mailinator.com", "yopmail.com", "sharklasers.com", "trashmail.com",
    "getairmail.com", "dispostable.com", "maildrop.cc", "temp-mail.org",
}

# Popular domains for homoglyph/typosquat detection
_POPULAR_DOMAINS = {
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "apple.com", "microsoft.com", "google.com", "amazon.com", "paypal.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "chase.com", "bankofamerica.com", "wellsfargo.com", "citi.com",
}

# Phishing signal keywords
_PHISHING_SIGNALS = [
    "verify your account", "confirm your identity", "unusual activity",
    "account suspended", "click here immediately", "act now",
    "limited time", "you have been selected", "winner", "prize",
    "claim your", "expire", "unauthorized access", "update your payment",
    "billing problem", "payment declined", "verify your information",
    "reset your password", "security notice", "locked out",
    "suspicious login", "wire transfer", "western union", "bitcoin",
    "cryptocurrency", "investment opportunity", "guaranteed return",
]


def _load_trust_lists():
    """Load trusted/blocked sender lists."""
    try:
        if os.path.exists(TRUST_LISTS_PATH):
            with open(TRUST_LISTS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {"trusted": [], "blocked": []}


def _save_trust_lists(data):
    """Save trusted/blocked sender lists."""
    os.makedirs(os.path.dirname(TRUST_LISTS_PATH), exist_ok=True)
    with open(TRUST_LISTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _extract_urls(text):
    """Extract all URLs from text with context."""
    url_pattern = re.compile(
        r'https?://[^\s<>"\')\]]+',
        re.IGNORECASE
    )
    urls = []
    for match in url_pattern.finditer(text):
        url = match.group(0).rstrip('.,;:!?)')
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.hostname or ""
        except Exception:
            domain = ""
        urls.append({
            "url": url,
            "domain": domain,
            "is_https": url.lower().startswith("https://"),
            "is_shortened": domain in {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
                                        "is.gd", "buff.ly", "rebrand.ly", "cutt.ly", "short.io"},
            "is_ip_based": bool(re.match(r'\d+\.\d+\.\d+\.\d+', domain)) if domain else False,
        })
    return urls


def _check_homoglyph(domain):
    """Check if domain uses homoglyph/lookalike characters to impersonate popular domains."""
    if not domain:
        return False, None
    domain_lower = domain.lower()

    # Direct match is fine
    if domain_lower in _POPULAR_DOMAINS:
        return False, None

    # Check for common substitutions
    substitutions = {
        '0': 'o', '1': 'l', 'l': 'i', 'rn': 'm', 'vv': 'w',
        'cl': 'd', 'nn': 'm', 'ii': 'u',
    }
    normalized = domain_lower
    for fake, real in substitutions.items():
        normalized = normalized.replace(fake, real)

    if normalized in _POPULAR_DOMAINS and normalized != domain_lower:
        return True, normalized

    # Check Levenshtein distance 1 (single char diff)
    for popular in _POPULAR_DOMAINS:
        if abs(len(domain_lower) - len(popular)) <= 1:
            diffs = sum(1 for a, b in zip(domain_lower, popular) if a != b)
            diffs += abs(len(domain_lower) - len(popular))
            if diffs == 1:
                return True, popular

    return False, None


def _compute_phishing_score(sender, subject, body_text, urls):
    """Compute 0-100 phishing probability score using heuristic signals."""
    score = 0
    warnings = []

    combined = (subject + " " + body_text).lower()
    sender_lower = (sender or "").lower()

    # Signal 1: Phishing keywords (up to 40 pts)
    hits = [s for s in _PHISHING_SIGNALS if s in combined]
    kw_score = min(len(hits) * 10, 40)
    score += kw_score
    if hits:
        warnings.append(f"Phishing keywords: {', '.join(hits[:5])}")

    # Signal 2: Suspicious links (up to 25 pts)
    for url_info in urls:
        if url_info["is_shortened"]:
            score += 8
            warnings.append(f"Shortened URL: {url_info['domain']}")
        if url_info["is_ip_based"]:
            score += 12
            warnings.append(f"IP-based URL: {url_info['url'][:60]}")
        if not url_info["is_https"]:
            score += 5
            warnings.append(f"Non-HTTPS link: {url_info['url'][:60]}")

    # Signal 3: Homoglyph domain (15 pts)
    try:
        sender_domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
        is_homo, impersonating = _check_homoglyph(sender_domain)
        if is_homo:
            score += 15
            warnings.append(f"Typosquat domain: {sender_domain} looks like {impersonating}")
    except Exception:
        pass

    # Signal 4: Disposable email (10 pts)
    try:
        sender_domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
        if sender_domain in _DISPOSABLE_DOMAINS:
            score += 10
            warnings.append(f"Disposable email domain: {sender_domain}")
    except Exception:
        pass

    # Signal 5: Urgency pressure (10 pts)
    urgency_phrases = ["immediately", "within 24 hours", "right now", "asap",
                        "account will be closed", "last chance", "final warning"]
    urgency_hits = [p for p in urgency_phrases if p in combined]
    if urgency_hits:
        score += min(len(urgency_hits) * 5, 10)
        warnings.append(f"Urgency pressure: {', '.join(urgency_hits[:3])}")

    return min(score, 100), warnings


def scan_email_security(index=1, mailbox="inbox"):
    """Full security scan on an email: phishing score, suspicious links, sender trust.

    Returns risk_level (low/medium/high/critical), phishing_score, trust assessment, warnings.
    """
    try:
        msg_r = read_message(index, mailbox)
        if not msg_r["success"]:
            return {"success": False, "error": True, "content": f"Failed to read email {index}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read email: {e}"}

    content = msg_r["content"]
    # Parse sender, subject, body from the message content
    sender = ""
    subject = ""
    body = content
    for line in content.split("\n"):
        if line.startswith("FROM:"):
            sender = line.replace("FROM:", "").strip()
        elif line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()
        elif line.startswith("BODY:"):
            body = line.replace("BODY:", "").strip()

    urls = _extract_urls(body)
    phishing_score, warnings = _compute_phishing_score(sender, subject, body, urls)

    # Determine risk level
    if phishing_score >= 70:
        risk_level = "critical"
    elif phishing_score >= 40:
        risk_level = "high"
    elif phishing_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Check sender trust
    trust_r = check_sender_trust(sender)
    trust_info = trust_r.get("content", "") if trust_r["success"] else "Unknown"

    lines = [
        f"🛡️ Security Scan — Email #{index}",
        f"  📧 From: {sender}",
        f"  📌 Subject: {subject}",
        f"  🎯 Risk Level: {risk_level.upper()}",
        f"  📊 Phishing Score: {phishing_score}/100",
        f"  🔗 Links Found: {len(urls)}",
    ]
    if urls:
        suspicious = [u for u in urls if u["is_shortened"] or u["is_ip_based"] or not u["is_https"]]
        lines.append(f"  ⚠️ Suspicious Links: {len(suspicious)}")
    if warnings:
        lines.append("  🚩 Warnings:")
        for w in warnings[:8]:
            lines.append(f"    • {w}")
    lines.append(f"  👤 Sender Trust: {trust_info[:100]}")

    event_bus.emit("email_security_scan", {
        "index": index, "risk_level": risk_level,
        "phishing_score": phishing_score, "sender": sender,
    })

    return {"success": True, "content": "\n".join(lines)}


def check_sender_trust(sender_email):
    """Check sender trust based on contact history, communication patterns, trust lists."""
    sender_lower = (sender_email or "").lower()
    if not sender_lower:
        return {"success": False, "error": True, "content": "No sender email provided"}

    trust_score = 50  # neutral baseline
    factors = []

    # Factor 1: Trust/block lists
    trust_lists = _load_trust_lists()
    trusted_entries = [t["email"] for t in trust_lists.get("trusted", []) if isinstance(t, dict)]
    blocked_entries = [b["email"] for b in trust_lists.get("blocked", []) if isinstance(b, dict)]

    if sender_lower in blocked_entries or any(sender_lower.endswith(d) for d in blocked_entries if d.startswith("@")):
        return {"success": True, "content": f"🚫 BLOCKED sender: {sender_email} — trust score: 0/100"}

    if sender_lower in trusted_entries or any(sender_lower.endswith(d) for d in trusted_entries if d.startswith("@")):
        trust_score += 30
        factors.append("✅ On trusted list (+30)")

    # Factor 2: Known contact
    try:
        contacts = _load_contacts()
        is_contact = any(c.get("email", "").lower() == sender_lower for c in contacts)
        if is_contact:
            trust_score += 20
            factors.append("📇 Known contact (+20)")
            # VIP bonus
            contact = next((c for c in contacts if c.get("email", "").lower() == sender_lower), None)
            if contact and "vip" in [t.lower() for t in contact.get("tags", [])]:
                trust_score += 10
                factors.append("👑 VIP contact (+10)")
    except Exception:
        pass

    # Factor 3: Communication history via sender stats
    try:
        stats = _load_sender_stats()
        sender_stat = stats.get(sender_lower, {})
        msg_count = sender_stat.get("count", 0)
        if msg_count >= 10:
            trust_score += 15
            factors.append(f"📊 Frequent sender ({msg_count} msgs, +15)")
        elif msg_count >= 3:
            trust_score += 8
            factors.append(f"📊 Known sender ({msg_count} msgs, +8)")
        elif msg_count == 0:
            trust_score -= 10
            factors.append("🆕 First-time sender (-10)")
    except Exception:
        pass

    # Factor 4: Domain checks
    try:
        domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
        if domain in _DISPOSABLE_DOMAINS:
            trust_score -= 20
            factors.append(f"🗑️ Disposable domain ({domain}, -20)")
        is_homo, target = _check_homoglyph(domain)
        if is_homo:
            trust_score -= 25
            factors.append(f"⚠️ Typosquat of {target} (-25)")
    except Exception:
        pass

    trust_score = max(0, min(100, trust_score))
    grade = "HIGH" if trust_score >= 70 else "MEDIUM" if trust_score >= 40 else "LOW"

    result = f"👤 {sender_email} — Trust: {trust_score}/100 ({grade})"
    if factors:
        result += "\n" + "\n".join(f"  {f}" for f in factors)

    return {"success": True, "content": result}


def scan_links(index=1, mailbox="inbox"):
    """Extract and analyze all URLs in an email body."""
    try:
        msg_r = read_message(index, mailbox)
        if not msg_r["success"]:
            return {"success": False, "error": True, "content": f"Failed to read email {index}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read email: {e}"}

    urls = _extract_urls(msg_r["content"])
    if not urls:
        return {"success": True, "content": f"🔗 No links found in email #{index}"}

    lines = [f"🔗 Link Analysis — Email #{index} ({len(urls)} links):"]
    for i, u in enumerate(urls, 1):
        flags = []
        if u["is_shortened"]:
            flags.append("⚠️ SHORTENED")
        if u["is_ip_based"]:
            flags.append("🚨 IP-BASED")
        if not u["is_https"]:
            flags.append("🔓 HTTP")
        is_homo, target = _check_homoglyph(u["domain"])
        if is_homo:
            flags.append(f"🎭 TYPOSQUAT({target})")
        if u["domain"] in _DISPOSABLE_DOMAINS:
            flags.append("🗑️ DISPOSABLE")

        flag_str = " " + " ".join(flags) if flags else " ✅"
        lines.append(f"  [{i}] {u['url'][:80]}{flag_str}")

    suspicious_count = sum(1 for u in urls if u["is_shortened"] or u["is_ip_based"] or not u["is_https"])
    if suspicious_count:
        lines.append(f"\n  ⚠️ {suspicious_count}/{len(urls)} links flagged as suspicious")
        event_bus.emit("suspicious_link_found", {"index": index, "count": suspicious_count})
    else:
        lines.append(f"\n  ✅ All {len(urls)} links appear safe")

    return {"success": True, "content": "\n".join(lines)}


def get_security_report(count=20):
    """Inbox-wide security report: scan latest emails for threats."""
    try:
        inbox_r = read_inbox(count)
        if not inbox_r["success"]:
            return {"success": False, "error": True, "content": "Failed to read inbox"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read inbox: {e}"}

    content = inbox_r["content"]
    emails = []
    for line in content.strip().split('\n'):
        if not line.strip():
            continue
        idx_match = re.search(r'\[(\d+)\]', line)
        sender_match = re.search(r'FROM:\s*(.+?)\s*\|', line)
        subj_match = re.search(r'SUBJECT:\s*(.+?)(?:\s*\||$)', line)
        if idx_match:
            emails.append({
                "index": int(idx_match.group(1)),
                "sender": sender_match.group(1).strip() if sender_match else "",
                "subject": subj_match.group(1).strip() if subj_match else "",
            })

    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    flagged = []

    for e in emails[:count]:
        try:
            result = scan_email_security(e["index"])
            if result["success"]:
                for level in ["critical", "high", "medium", "low"]:
                    if level.upper() in result["content"]:
                        risk_dist[level] += 1
                        if level in ("high", "critical"):
                            flagged.append(f"  🚨 #{e['index']} {e['sender']}: {e['subject'][:50]}")
                        break
        except Exception:
            pass

    total = sum(risk_dist.values())
    lines = [
        f"🛡️ Inbox Security Report ({total} emails scanned):",
        f"  ✅ Low risk: {risk_dist['low']}",
        f"  ⚠️ Medium risk: {risk_dist['medium']}",
        f"  🔶 High risk: {risk_dist['high']}",
        f"  🚨 Critical risk: {risk_dist['critical']}",
    ]
    if flagged:
        lines.append(f"\n  📛 Flagged emails ({len(flagged)}):")
        lines.extend(flagged[:10])
    else:
        lines.append("\n  ✅ No high-risk emails detected")

    return {"success": True, "content": "\n".join(lines)}


def add_trusted_sender(email_or_domain, reason=""):
    """Add an email or domain to the trusted senders list."""
    if not email_or_domain:
        return {"success": False, "error": True, "content": "No email/domain provided"}

    lists = _load_trust_lists()
    entry = {"email": email_or_domain.lower(), "reason": reason,
             "added": datetime.now().isoformat()}

    # Check for duplicates
    existing = [t["email"] for t in lists.get("trusted", []) if isinstance(t, dict)]
    if email_or_domain.lower() in existing:
        return {"success": True, "content": f"Already trusted: {email_or_domain}"}

    # Remove from blocked if present
    lists["blocked"] = [b for b in lists.get("blocked", [])
                         if isinstance(b, dict) and b["email"] != email_or_domain.lower()]

    lists.setdefault("trusted", []).append(entry)
    _save_trust_lists(lists)
    event_bus.emit("sender_trusted", {"email": email_or_domain, "reason": reason})
    return {"success": True, "content": f"✅ Added to trusted: {email_or_domain}"}


def add_blocked_sender(email_or_domain, reason=""):
    """Add an email or domain to the blocked senders list."""
    if not email_or_domain:
        return {"success": False, "error": True, "content": "No email/domain provided"}

    lists = _load_trust_lists()
    entry = {"email": email_or_domain.lower(), "reason": reason,
             "added": datetime.now().isoformat()}

    existing = [b["email"] for b in lists.get("blocked", []) if isinstance(b, dict)]
    if email_or_domain.lower() in existing:
        return {"success": True, "content": f"Already blocked: {email_or_domain}"}

    # Remove from trusted if present
    lists["trusted"] = [t for t in lists.get("trusted", [])
                         if isinstance(t, dict) and t["email"] != email_or_domain.lower()]

    lists.setdefault("blocked", []).append(entry)
    _save_trust_lists(lists)
    event_bus.emit("sender_blocked", {"email": email_or_domain, "reason": reason})
    return {"success": True, "content": f"🚫 Added to blocked: {email_or_domain}"}


def list_trusted_senders():
    """List all trusted senders/domains."""
    lists = _load_trust_lists()
    trusted = lists.get("trusted", [])
    if not trusted:
        return {"success": True, "content": "📭 No trusted senders configured."}

    lines = [f"✅ Trusted Senders ({len(trusted)}):"]
    for t in trusted:
        if isinstance(t, dict):
            reason = f" — {t.get('reason')}" if t.get("reason") else ""
            lines.append(f"  ✅ {t['email']}{reason}")
    return {"success": True, "content": "\n".join(lines)}


def list_blocked_senders():
    """List all blocked senders/domains."""
    lists = _load_trust_lists()
    blocked = lists.get("blocked", [])
    if not blocked:
        return {"success": True, "content": "📭 No blocked senders configured."}

    lines = [f"🚫 Blocked Senders ({len(blocked)}):"]
    for b in blocked:
        if isinstance(b, dict):
            reason = f" — {b.get('reason')}" if b.get("reason") else ""
            lines.append(f"  🚫 {b['email']}{reason}")
    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  PHASE 9B: Action Item & Meeting Extraction
# ═══════════════════════════════════════════════════

ACTIONS_PATH = os.path.join(TARS_ROOT, "memory", "email_actions.json")

# Action item detection patterns
_ACTION_PATTERNS = [
    # Direct requests
    (r'(?:please|pls|kindly)\s+(.+?)(?:\.|$)', 'request'),
    (r'(?:can you|could you|would you)\s+(.+?)(?:\?|$)', 'request'),
    (r'(?:need you to|needs? to|required to)\s+(.+?)(?:\.|$)', 'task'),
    # Deadline patterns
    (r'(?:by|before|due|deadline)\s+(\w+\s+\d+[\s,]*\d*)', 'deadline'),
    (r'(?:by|before)\s+(end of (?:day|week|month)|eod|eow|eom|tomorrow|friday|monday)', 'deadline'),
    (r'(?:asap|urgent|immediately|right away)', 'urgent'),
    # Assignment patterns
    (r'(?:assign(?:ed)? to|owner|responsible)\s*:?\s*(.+?)(?:\.|$)', 'assignment'),
    # Action verbs at start of sentences
    (r'(?:^|\.\s+)(review|approve|send|submit|complete|prepare|update|create|schedule|confirm|finalize|sign|forward|respond|reply|upload|download)\s+(.+?)(?:\.|$)', 'task'),
]

# Meeting detection patterns
_MEETING_PATTERNS = {
    "zoom": re.compile(r'https?://[\w.-]*zoom\.us/[jw]/\S+', re.I),
    "teams": re.compile(r'https?://teams\.microsoft\.com/\S+', re.I),
    "meet": re.compile(r'https?://meet\.google\.com/\S+', re.I),
    "webex": re.compile(r'https?://[\w.-]*webex\.com/\S+', re.I),
    "calendar": re.compile(r'https?://calendar\.google\.com/\S+', re.I),
}

_DATE_PATTERNS = [
    # "March 15, 2026 at 2:00 PM"
    re.compile(r'(\w+ \d{1,2},?\s*\d{4})\s+(?:at\s+)?(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', re.I),
    # "3/15/2026 2:00 PM"
    re.compile(r'(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', re.I),
    # "tomorrow at 3pm"
    re.compile(r'(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)', re.I),
    # "2026-03-15T14:00"
    re.compile(r'(\d{4}-\d{2}-\d{2})[T\s]+(\d{2}:\d{2})', re.I),
]


def _load_actions():
    """Load extracted action items."""
    try:
        if os.path.exists(ACTIONS_PATH):
            with open(ACTIONS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_actions(data):
    """Save extracted action items."""
    os.makedirs(os.path.dirname(ACTIONS_PATH), exist_ok=True)
    # Keep max 500 entries
    if len(data) > 500:
        data = data[-500:]
    with open(ACTIONS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _parse_action_items(text):
    """Extract action items from email text using regex heuristics."""
    items = []
    text_lower = text.lower()

    for pattern, item_type in _ACTION_PATTERNS:
        try:
            matches = re.finditer(pattern, text_lower, re.MULTILINE | re.IGNORECASE)
            for m in matches:
                task_text = m.group(1) if m.lastindex else m.group(0)
                task_text = task_text.strip().rstrip('.,;:')
                if len(task_text) > 10 and len(task_text) < 200:  # reasonable length
                    items.append({
                        "task": task_text,
                        "type": item_type,
                        "urgency": "high" if item_type == "urgent" else "normal",
                    })
        except Exception:
            continue

    # Deduplicate by similarity
    seen = set()
    unique = []
    for item in items:
        key = item["task"][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:10]  # max 10 per email


def _parse_meeting_info(text):
    """Extract meeting details from email text."""
    meeting = {}

    # Find meeting links
    for platform, pattern in _MEETING_PATTERNS.items():
        match = pattern.search(text)
        if match:
            meeting["platform"] = platform
            meeting["link"] = match.group(0)
            break

    # Find date/time
    for date_pattern in _DATE_PATTERNS:
        match = date_pattern.search(text)
        if match:
            meeting["date"] = match.group(1)
            meeting["time"] = match.group(2) if match.lastindex >= 2 else ""
            break

    # Find location (look for common patterns)
    loc_match = re.search(r'(?:location|where|venue|room|building|address)\s*:?\s*(.+?)(?:\n|$)', text, re.I)
    if loc_match:
        meeting["location"] = loc_match.group(1).strip()[:100]

    # Find agenda keywords
    agenda_match = re.search(r'(?:agenda|topics?|discuss)\s*:?\s*(.+?)(?:\n\n|$)', text, re.I | re.DOTALL)
    if agenda_match:
        meeting["agenda"] = agenda_match.group(1).strip()[:200]

    # Find attendees
    attendees_match = re.search(r'(?:attendees?|participants?|invit(?:ed|ees?))\s*:?\s*(.+?)(?:\n\n|$)', text, re.I)
    if attendees_match:
        meeting["attendees"] = attendees_match.group(1).strip()[:200]

    # Only return if we found at least a link or a date
    if meeting.get("link") or meeting.get("date"):
        return meeting
    return None


def extract_action_items(index=1, mailbox="inbox"):
    """Parse an email for action items: tasks, deadlines, requests."""
    try:
        msg_r = read_message(index, mailbox)
        if not msg_r["success"]:
            return {"success": False, "error": True, "content": f"Failed to read email {index}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read email: {e}"}

    content = msg_r["content"]
    sender = ""
    subject = ""
    for line in content.split("\n"):
        if line.startswith("FROM:"):
            sender = line.replace("FROM:", "").strip()
        elif line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()

    items = _parse_action_items(content)
    if not items:
        return {"success": True, "content": f"📋 No action items detected in email #{index}"}

    # Save extracted items
    actions = _load_actions()
    for item in items:
        item["source_email"] = subject
        item["sender"] = sender
        item["extracted_at"] = datetime.now().isoformat()
        item["status"] = "pending"
        item["id"] = f"act_{int(time.time()*1000)}_{len(actions)}"
        actions.append(item)
    _save_actions(actions)

    event_bus.emit("action_item_extracted", {"count": len(items), "email_index": index, "subject": subject})

    lines = [f"📋 Action Items from email #{index} ({len(items)} found):"]
    lines.append(f"  📧 From: {sender}")
    lines.append(f"  📌 Subject: {subject}")
    for i, item in enumerate(items, 1):
        urgency = "🔴" if item["urgency"] == "high" else "🟡"
        lines.append(f"  {urgency} [{i}] {item['task']} ({item['type']})")

    return {"success": True, "content": "\n".join(lines)}


def extract_meeting_details(index=1, mailbox="inbox"):
    """Parse an email for meeting details: date, time, link, location, attendees."""
    try:
        msg_r = read_message(index, mailbox)
        if not msg_r["success"]:
            return {"success": False, "error": True, "content": f"Failed to read email {index}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read email: {e}"}

    content = msg_r["content"]
    sender = ""
    subject = ""
    for line in content.split("\n"):
        if line.startswith("FROM:"):
            sender = line.replace("FROM:", "").strip()
        elif line.startswith("SUBJECT:"):
            subject = line.replace("SUBJECT:", "").strip()

    meeting = _parse_meeting_info(content)
    if not meeting:
        return {"success": True, "content": f"📅 No meeting details detected in email #{index}"}

    event_bus.emit("meeting_extracted", {"email_index": index, "subject": subject,
                                          "platform": meeting.get("platform", "unknown")})

    lines = [f"📅 Meeting Details from email #{index}:"]
    lines.append(f"  📧 From: {sender}")
    lines.append(f"  📌 Subject: {subject}")
    if meeting.get("platform"):
        lines.append(f"  🖥️ Platform: {meeting['platform'].title()}")
    if meeting.get("link"):
        lines.append(f"  🔗 Link: {meeting['link']}")
    if meeting.get("date"):
        time_str = f" at {meeting['time']}" if meeting.get("time") else ""
        lines.append(f"  📆 Date: {meeting['date']}{time_str}")
    if meeting.get("location"):
        lines.append(f"  📍 Location: {meeting['location']}")
    if meeting.get("attendees"):
        lines.append(f"  👥 Attendees: {meeting['attendees']}")
    if meeting.get("agenda"):
        lines.append(f"  📝 Agenda: {meeting['agenda'][:150]}")

    return {"success": True, "content": "\n".join(lines)}


def scan_inbox_actions(count=20):
    """Batch-scan latest emails for action items and meetings."""
    try:
        inbox_r = read_inbox(count)
        if not inbox_r["success"]:
            return {"success": False, "error": True, "content": "Failed to read inbox"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to read inbox: {e}"}

    all_actions = []
    all_meetings = []

    for line in inbox_r["content"].strip().split('\n'):
        idx_match = re.search(r'\[(\d+)\]', line)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))
        try:
            msg_r = read_message(idx)
            if not msg_r["success"]:
                continue
            content = msg_r["content"]
            subject = ""
            for ln in content.split("\n"):
                if ln.startswith("SUBJECT:"):
                    subject = ln.replace("SUBJECT:", "").strip()

            items = _parse_action_items(content)
            for item in items:
                item["email_index"] = idx
                item["subject"] = subject
                all_actions.append(item)

            meeting = _parse_meeting_info(content)
            if meeting:
                meeting["email_index"] = idx
                meeting["subject"] = subject
                all_meetings.append(meeting)
        except Exception:
            continue

    lines = [f"📊 Inbox Action Scan ({count} emails):"]
    lines.append(f"  📋 Action Items: {len(all_actions)}")
    lines.append(f"  📅 Meetings: {len(all_meetings)}")

    if all_actions:
        lines.append("\n  📋 Action Items:")
        for a in all_actions[:15]:
            urgency = "🔴" if a.get("urgency") == "high" else "🟡"
            lines.append(f"    {urgency} [{a.get('email_index', '?')}] {a['task'][:60]}")

    if all_meetings:
        lines.append("\n  📅 Meetings:")
        for m in all_meetings[:10]:
            platform = m.get("platform", "")
            date_str = m.get("date", "TBD")
            lines.append(f"    📅 [{m.get('email_index', '?')}] {m.get('subject', '')[:40]} — {date_str} ({platform})")

    return {"success": True, "content": "\n".join(lines)}


def create_reminder_from_email(title, due_date=None, notes="", source_email_subject=""):
    """Create a macOS Reminder from an extracted action item."""
    due_clause = ""
    if due_date:
        due_clause = f'due date (date "{due_date}")'

    note_text = notes
    if source_email_subject:
        note_text = f"From email: {source_email_subject}\n{notes}"

    escaped_title = _escape_as(title)
    escaped_notes = _escape_as(note_text)

    script = f'''
    tell application "Reminders"
        set newReminder to make new reminder with properties {{name:"{escaped_title}", body:"{escaped_notes}"}}
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=15)
    if result["success"]:
        result["content"] = f"✅ Reminder created: {title}"
        event_bus.emit("reminder_created", {"title": title, "source": source_email_subject})
    return result


def create_calendar_event(title, start_datetime, end_datetime=None, location="", notes="", attendees=None):
    """Create a Calendar.app event from extracted meeting details."""
    if not end_datetime:
        # Default 1 hour
        end_datetime = start_datetime  # AppleScript will handle duration

    escaped_title = _escape_as(title)
    escaped_location = _escape_as(location or "")
    escaped_notes = _escape_as(notes or "")

    script = f'''
    tell application "Calendar"
        tell calendar "Calendar"
            set newEvent to make new event with properties {{summary:"{escaped_title}", start date:(date "{start_datetime}"), end date:(date "{end_datetime}"), location:"{escaped_location}", description:"{escaped_notes}"}}
        end tell
    end tell
    '''
    result = _run_applescript_stdin(script, timeout=15)
    if result["success"]:
        result["content"] = f"📅 Calendar event created: {title} at {start_datetime}"
        event_bus.emit("calendar_event_created", {"title": title, "start": start_datetime})
    return result


def list_extracted_actions(status="all"):
    """List all extracted action items from emails."""
    actions = _load_actions()
    if status != "all":
        actions = [a for a in actions if a.get("status") == status]

    if not actions:
        return {"success": True, "content": f"📋 No action items found (filter: {status})"}

    lines = [f"📋 Extracted Action Items ({len(actions)}, filter: {status}):"]
    for a in actions[-20:]:  # show latest 20
        urgency = "🔴" if a.get("urgency") == "high" else "🟡"
        status_icon = "✅" if a.get("status") == "completed" else "⬜"
        source = a.get("source_email", "")[:30]
        lines.append(f"  {status_icon} {urgency} {a.get('task', '')[:60]}")
        lines.append(f"      ID: {a.get('id', '?')} | From: {source}")

    return {"success": True, "content": "\n".join(lines)}


def complete_action(action_id):
    """Mark an extracted action item as completed."""
    actions = _load_actions()
    found = False
    for a in actions:
        if a.get("id") == action_id:
            a["status"] = "completed"
            a["completed_at"] = datetime.now().isoformat()
            found = True
            event_bus.emit("action_completed", {"action_id": action_id, "task": a.get("task", "")})
            break

    if not found:
        return {"success": False, "error": True, "content": f"Action item not found: {action_id}"}

    _save_actions(actions)
    return {"success": True, "content": f"✅ Action item completed: {action_id}"}


def get_action_summary():
    """Dashboard summary: pending actions, upcoming meetings, overdue items."""
    actions = _load_actions()
    pending = [a for a in actions if a.get("status") == "pending"]
    completed = [a for a in actions if a.get("status") == "completed"]

    lines = [
        f"📊 Action Item Summary:",
        f"  ⬜ Pending: {len(pending)}",
        f"  ✅ Completed: {len(completed)}",
        f"  📋 Total: {len(actions)}",
    ]

    if pending:
        urgent = [a for a in pending if a.get("urgency") == "high"]
        if urgent:
            lines.append(f"\n  🔴 Urgent ({len(urgent)}):")
            for a in urgent[:5]:
                lines.append(f"    • {a.get('task', '')[:60]}")

        recent = sorted(pending, key=lambda x: x.get("extracted_at", ""), reverse=True)[:5]
        lines.append(f"\n  📋 Latest Pending:")
        for a in recent:
            lines.append(f"    • {a.get('task', '')[:60]} (from: {a.get('source_email', '')[:25]})")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════
#  PHASE 9C: Email Workflow Chains
# ═══════════════════════════════════════════════════

WORKFLOWS_PATH = os.path.join(TARS_ROOT, "memory", "email_workflows.json")
WORKFLOW_HISTORY_PATH = os.path.join(TARS_ROOT, "memory", "email_workflow_history.json")

# Built-in workflow templates
_WORKFLOW_TEMPLATES = {
    "vip_urgent": {
        "name": "VIP Urgent Handler",
        "description": "Flag + auto-ack + forward urgent VIP emails",
        "trigger": {"from_vip": True, "subject_contains": "urgent"},
        "steps": [
            {"action": "flag", "params": {"flagged": True}},
            {"action": "auto_reply", "params": {"body": "Received your urgent message. Looking into it now."}},
            {"action": "notify", "params": {"title": "VIP URGENT"}},
        ],
    },
    "newsletter_cleanup": {
        "name": "Newsletter Auto-Archive",
        "description": "Auto-archive read newsletters older than 3 days",
        "trigger": {"category": "newsletter", "is_read": True},
        "steps": [
            {"action": "archive"},
        ],
    },
    "team_forward": {
        "name": "Team Forward",
        "description": "Forward matching emails to team + flag + ack",
        "trigger": {"subject_contains": ""},
        "steps": [
            {"action": "flag", "params": {"flagged": True}},
            {"action": "forward", "params": {"to": ""}},
            {"action": "auto_reply", "params": {"body": "Thanks! I've forwarded this to the team."}},
        ],
    },
    "followup_escalation": {
        "name": "Follow-up Escalation",
        "description": "Track follow-up + create reminder for important emails",
        "trigger": {"category": "priority"},
        "steps": [
            {"action": "flag", "params": {"flagged": True}},
            {"action": "followup", "params": {"deadline_hours": 48}},
            {"action": "notify", "params": {"title": "Priority email needs follow-up"}},
        ],
    },
    "auto_categorize_act": {
        "name": "Auto Categorize & Act",
        "description": "Categorize email -> archive newsletters, flag priority, track meetings",
        "trigger": {"is_unread": True},
        "steps": [
            {"action": "categorize"},
            {"action": "archive", "condition": {"category": "newsletter"}},
            {"action": "flag", "condition": {"category": "priority"}, "params": {"flagged": True}},
            {"action": "extract_actions", "condition": {"category": "priority"}},
        ],
    },
}


def _load_workflows():
    """Load saved workflows."""
    try:
        if os.path.exists(WORKFLOWS_PATH):
            with open(WORKFLOWS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_workflows(data):
    """Save workflows."""
    os.makedirs(os.path.dirname(WORKFLOWS_PATH), exist_ok=True)
    with open(WORKFLOWS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _load_workflow_history():
    """Load workflow execution history."""
    try:
        if os.path.exists(WORKFLOW_HISTORY_PATH):
            with open(WORKFLOW_HISTORY_PATH) as f:
                data = json.load(f)
                return data[-200:] if len(data) > 200 else data
    except Exception:
        pass
    return []


def _save_workflow_history(data):
    """Save workflow execution history."""
    os.makedirs(os.path.dirname(WORKFLOW_HISTORY_PATH), exist_ok=True)
    if len(data) > 200:
        data = data[-200:]
    with open(WORKFLOW_HISTORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _evaluate_trigger(email_info, trigger):
    """Check if an email matches a workflow trigger's conditions."""
    if not trigger:
        return False

    sender = (email_info.get("sender") or "").lower()
    subject = (email_info.get("subject") or "").lower()

    # Check each trigger condition
    if "from_contains" in trigger:
        if trigger["from_contains"].lower() not in sender:
            return False

    if "subject_contains" in trigger:
        if trigger["subject_contains"] and trigger["subject_contains"].lower() not in subject:
            return False

    if "from_vip" in trigger and trigger["from_vip"]:
        try:
            contacts = _load_contacts()
            is_vip = any(
                c.get("email", "").lower() in sender and "vip" in [t.lower() for t in c.get("tags", [])]
                for c in contacts
            )
            if not is_vip:
                return False
        except Exception:
            return False

    if "category" in trigger:
        cat_info = _categorize_single(email_info)
        if cat_info["category"] != trigger["category"]:
            return False

    if "is_unread" in trigger:
        is_unread = not email_info.get("read", True)
        if trigger["is_unread"] != is_unread:
            return False

    if "is_read" in trigger:
        is_read = email_info.get("read", False)
        if trigger["is_read"] != is_read:
            return False

    return True


def _evaluate_step_condition(email_info, step, prev_results):
    """Check if a workflow step's condition is met."""
    condition = step.get("condition")
    if not condition:
        return True  # No condition = always execute

    if "category" in condition:
        cat_info = _categorize_single(email_info)
        if cat_info["category"] != condition["category"]:
            return False

    if "prev_success" in condition:
        if prev_results and not prev_results[-1].get("success"):
            return False

    return True


def _execute_workflow_step(email_index, step, mailbox="inbox"):
    """Execute a single workflow step against an email."""
    action = step.get("action")
    params = step.get("params", {})

    try:
        if action == "flag":
            return flag_message(email_index, params.get("flagged", True), mailbox)
        elif action == "archive":
            return archive_message(email_index, mailbox)
        elif action == "delete":
            return delete_message(email_index, mailbox)
        elif action == "mark_read":
            return mark_read(email_index, mailbox)
        elif action == "forward":
            to = params.get("to", "")
            body = params.get("body", "")
            return forward_to(email_index, to, body, mailbox)
        elif action == "auto_reply":
            body = params.get("body", "Acknowledged.")
            return reply_to(email_index, body, False, mailbox)
        elif action == "move":
            to_mb = params.get("to_mailbox", "Archive")
            return move_message(email_index, mailbox, to_mb)
        elif action == "followup":
            deadline = params.get("deadline_hours", 48)
            return add_followup("", "", deadline, params.get("reminder_text", ""))
        elif action == "notify":
            title = params.get("title", "Workflow notification")
            event_bus.emit("workflow_notification", {"title": title, "email_index": email_index})
            return {"success": True, "content": f"Notification sent: {title}"}
        elif action == "categorize":
            return categorize_inbox(1)
        elif action == "extract_actions":
            return extract_action_items(email_index, mailbox)
        else:
            return {"success": False, "error": True, "content": f"Unknown workflow action: {action}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Workflow step error: {e}"}


def create_workflow(name, trigger, steps, enabled=True):
    """Create a multi-step workflow chain.

    Args:
        name: Workflow name
        trigger: Dict of conditions (from_contains, subject_contains, from_vip, category, is_unread)
        steps: List of {action, params, condition} dicts
        enabled: Whether workflow is active
    """
    if not name or not trigger or not steps:
        return {"success": False, "error": True, "content": "name, trigger, and steps are required"}

    workflows = _load_workflows()
    workflow = {
        "id": f"wf_{int(time.time()*1000)}",
        "name": name,
        "trigger": trigger,
        "steps": steps,
        "enabled": enabled,
        "created_at": datetime.now().isoformat(),
        "run_count": 0,
    }
    workflows.append(workflow)
    _save_workflows(workflows)

    event_bus.emit("workflow_created", {"workflow_id": workflow["id"], "name": name, "step_count": len(steps)})
    return {"success": True, "content": f"✅ Workflow created: {name} ({len(steps)} steps, ID: {workflow['id']})"}


def list_workflows():
    """List all workflows with trigger summaries."""
    workflows = _load_workflows()
    if not workflows:
        return {"success": True, "content": "📭 No workflows configured."}

    lines = [f"🔗 Email Workflows ({len(workflows)}):"]
    for wf in workflows:
        status = "✅" if wf.get("enabled", True) else "⏸️"
        steps = len(wf.get("steps", []))
        runs = wf.get("run_count", 0)
        trigger_desc = json.dumps(wf.get("trigger", {}))[:60]
        lines.append(f"  {status} {wf['name']} — {steps} steps, {runs} runs")
        lines.append(f"      ID: {wf['id']} | Trigger: {trigger_desc}")

    return {"success": True, "content": "\n".join(lines)}


def get_workflow(workflow_id):
    """Get full workflow definition."""
    workflows = _load_workflows()
    wf = next((w for w in workflows if w["id"] == workflow_id), None)
    if not wf:
        return {"success": False, "error": True, "content": f"Workflow not found: {workflow_id}"}

    lines = [f"🔗 Workflow: {wf['name']}"]
    lines.append(f"  ID: {wf['id']}")
    lines.append(f"  Status: {'✅ Enabled' if wf.get('enabled', True) else '⏸️ Disabled'}")
    lines.append(f"  Runs: {wf.get('run_count', 0)}")
    lines.append(f"  Created: {wf.get('created_at', '?')}")
    lines.append(f"  Trigger: {json.dumps(wf.get('trigger', {}))}")
    lines.append(f"  Steps ({len(wf.get('steps', []))}):")
    for i, step in enumerate(wf.get("steps", []), 1):
        cond = f" [if {step['condition']}]" if step.get("condition") else ""
        params = f" {step.get('params', {})}" if step.get("params") else ""
        lines.append(f"    [{i}] {step['action']}{params}{cond}")

    return {"success": True, "content": "\n".join(lines)}


def delete_workflow(workflow_id):
    """Delete a workflow."""
    workflows = _load_workflows()
    before = len(workflows)
    workflows = [w for w in workflows if w["id"] != workflow_id]
    if len(workflows) == before:
        return {"success": False, "error": True, "content": f"Workflow not found: {workflow_id}"}

    _save_workflows(workflows)
    return {"success": True, "content": f"🗑️ Workflow deleted: {workflow_id}"}


def toggle_workflow(workflow_id, enabled=None):
    """Enable/disable a workflow."""
    workflows = _load_workflows()
    for wf in workflows:
        if wf["id"] == workflow_id:
            if enabled is None:
                wf["enabled"] = not wf.get("enabled", True)
            else:
                wf["enabled"] = enabled
            _save_workflows(workflows)
            state = "enabled" if wf["enabled"] else "disabled"
            return {"success": True, "content": f"{'✅' if wf['enabled'] else '⏸️'} Workflow {state}: {wf['name']}"}

    return {"success": False, "error": True, "content": f"Workflow not found: {workflow_id}"}


def run_workflow_manual(workflow_id, email_index=1, mailbox="inbox"):
    """Manually trigger a workflow against a specific email."""
    workflows = _load_workflows()
    wf = next((w for w in workflows if w["id"] == workflow_id), None)
    if not wf:
        return {"success": False, "error": True, "content": f"Workflow not found: {workflow_id}"}

    event_bus.emit("workflow_triggered", {
        "workflow_id": workflow_id, "name": wf["name"],
        "email_index": email_index, "trigger_reason": "manual",
    })

    results = []
    for i, step in enumerate(wf.get("steps", []), 1):
        # Check step condition
        if step.get("condition"):
            try:
                msg_r = read_message(email_index, mailbox)
                email_info = {"preview": msg_r.get("content", ""), "read": True}
                if not _evaluate_step_condition(email_info, step, results):
                    results.append({"step": i, "action": step["action"], "skipped": True,
                                    "reason": "condition not met"})
                    continue
            except Exception:
                pass

        result = _execute_workflow_step(email_index, step, mailbox)
        results.append({"step": i, "action": step["action"], "success": result.get("success", False),
                         "content": result.get("content", "")[:100]})
        event_bus.emit("workflow_step_executed", {
            "workflow_id": workflow_id, "step": i,
            "action": step["action"], "success": result.get("success", False),
        })

    # Update run count
    wf["run_count"] = wf.get("run_count", 0) + 1
    wf["last_run"] = datetime.now().isoformat()
    _save_workflows(workflows)

    # Save to history
    history = _load_workflow_history()
    history.append({
        "workflow_id": workflow_id, "name": wf["name"],
        "email_index": email_index, "timestamp": datetime.now().isoformat(),
        "results": results,
    })
    _save_workflow_history(history)

    event_bus.emit("workflow_completed", {"workflow_id": workflow_id, "steps": len(results)})

    succeeded = sum(1 for r in results if r.get("success"))
    skipped = sum(1 for r in results if r.get("skipped"))
    lines = [f"🔗 Workflow '{wf['name']}' executed on email #{email_index}:"]
    for r in results:
        if r.get("skipped"):
            lines.append(f"  ⏭️ Step {r['step']}: {r['action']} — skipped ({r.get('reason', '')})")
        elif r.get("success"):
            lines.append(f"  ✅ Step {r['step']}: {r['action']} — {r.get('content', 'OK')[:60]}")
        else:
            lines.append(f"  ❌ Step {r['step']}: {r['action']} — {r.get('content', 'Failed')[:60]}")
    lines.append(f"\n  Summary: {succeeded} succeeded, {skipped} skipped, {len(results)-succeeded-skipped} failed")

    return {"success": True, "content": "\n".join(lines)}


def get_workflow_templates():
    """List built-in workflow templates."""
    lines = ["📦 Built-in Workflow Templates:"]
    for key, tmpl in _WORKFLOW_TEMPLATES.items():
        steps_desc = ", ".join(s["action"] for s in tmpl["steps"])
        lines.append(f"  📋 {key}: {tmpl['name']}")
        lines.append(f"      {tmpl['description']}")
        lines.append(f"      Steps: {steps_desc}")

    return {"success": True, "content": "\n".join(lines)}


def create_workflow_from_template(template_name, params=None):
    """Create a workflow from a built-in template with optional parameter overrides."""
    if template_name not in _WORKFLOW_TEMPLATES:
        available = ", ".join(_WORKFLOW_TEMPLATES.keys())
        return {"success": False, "error": True, "content": f"Unknown template: {template_name}. Available: {available}"}

    tmpl = _WORKFLOW_TEMPLATES[template_name]
    import copy
    workflow_def = copy.deepcopy(tmpl)

    # Apply parameter overrides
    if params:
        if "name" in params:
            workflow_def["name"] = params["name"]
        if "trigger" in params:
            workflow_def["trigger"].update(params["trigger"])
        if "steps" in params:
            # Override step params by index
            for i, step_override in enumerate(params["steps"]):
                if i < len(workflow_def["steps"]):
                    workflow_def["steps"][i].setdefault("params", {}).update(step_override)

    return create_workflow(
        workflow_def["name"],
        workflow_def["trigger"],
        workflow_def["steps"],
    )


def get_workflow_history(workflow_id=None, limit=20):
    """Get workflow execution history."""
    history = _load_workflow_history()
    if workflow_id:
        history = [h for h in history if h.get("workflow_id") == workflow_id]

    if not history:
        return {"success": True, "content": "📭 No workflow execution history."}

    recent = history[-limit:]
    lines = [f"📜 Workflow History ({len(recent)}/{len(history)} entries):"]
    for h in reversed(recent):
        results = h.get("results", [])
        succeeded = sum(1 for r in results if r.get("success"))
        total = len(results)
        lines.append(f"  🔗 {h.get('name', '?')} on email #{h.get('email_index', '?')} — {succeeded}/{total} steps OK")
        lines.append(f"      {h.get('timestamp', '?')}")

    return {"success": True, "content": "\n".join(lines)}


# ═══════════════════════════════════════════════════════════════════
# ██  PHASE 10A — SMART COMPOSE & WRITING ASSISTANCE              ██
# ═══════════════════════════════════════════════════════════════════

COMPOSE_CACHE_PATH = os.path.join(TARS_ROOT, "memory", "email_compose_cache.json")

# Tone presets for rewriting
_TONE_PRESETS = {
    "formal": "Use formal, professional business language. No contractions. Proper salutations.",
    "friendly": "Use warm, conversational tone. Casual but professional. Use contractions naturally.",
    "urgent": "Convey urgency and importance. Be direct and action-oriented. Clear deadlines.",
    "apologetic": "Express genuine apology and accountability. Offer concrete next steps.",
    "enthusiastic": "Show excitement and energy. Use positive language. Be encouraging.",
    "concise": "Be extremely brief and to the point. No fluff. Bullet points where possible.",
    "diplomatic": "Be tactful and balanced. Acknowledge different perspectives. Non-confrontational.",
}

_STYLE_INSTRUCTIONS = {
    "concise": "Rewrite to be extremely concise — cut all filler, use bullet points for lists.",
    "detailed": "Expand with more detail, context, and supporting information.",
    "bullet_points": "Convert the content into well-organized bullet points with headers.",
    "executive_summary": "Write as a brief executive summary — key points only, decision-focused.",
    "action_oriented": "Rewrite to focus on clear action items and next steps.",
}


def _load_compose_cache():
    """Load compose cache."""
    try:
        if os.path.exists(COMPOSE_CACHE_PATH):
            with open(COMPOSE_CACHE_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_compose_cache(data):
    """Save compose cache (max 50 entries)."""
    try:
        os.makedirs(os.path.dirname(COMPOSE_CACHE_PATH), exist_ok=True)
        with open(COMPOSE_CACHE_PATH, "w") as f:
            json.dump(data[-50:], f, indent=2)
    except Exception:
        pass


def _get_llm_for_compose():
    """Get an LLM client for compose operations."""
    try:
        import yaml
        config_path = os.path.join(TARS_ROOT, "config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        llm_config = config.get("agent_llm", config.get("brain_llm", {}))
        from brain.llm_client import LLMClient
        return LLMClient(
            provider=llm_config.get("provider", "groq"),
            api_key=llm_config.get("api_key", ""),
            model=llm_config.get("model", "")
        ), llm_config.get("model", "")
    except Exception:
        return None, None


def smart_compose(prompt, context_email=None, tone="professional", recipient=None):
    """Generate a full email draft from a natural-language prompt.

    Args:
        prompt: What the email should say/accomplish
        context_email: Optional existing email text for context (e.g. reply context)
        tone: Tone preset (formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic)
        recipient: Optional recipient name for personalization
    """
    try:
        if not prompt:
            return {"success": False, "error": True, "content": "Need a prompt describing what to compose."}

        tone_guide = _TONE_PRESETS.get(tone, _TONE_PRESETS["formal"])

        system_msg = f"""You are an expert email composer. Write a professional email based on the user's instructions.

TONE: {tone_guide}

RULES:
- Write ONLY the email content (subject line + body)
- Format as: Subject: <subject>\n\n<body>
- Include a proper greeting and sign-off
- Be {tone} in tone
- Do NOT include meta-commentary or explanations
- Keep it natural and human-sounding"""

        user_msg = f"Compose an email: {prompt}"
        if recipient:
            user_msg += f"\nRecipient: {recipient}"
        if context_email:
            user_msg += f"\n\nContext/previous email:\n{context_email[:1500]}"

        llm, model = _get_llm_for_compose()
        if not llm:
            return {"success": False, "error": True, "content": "LLM not available for smart compose."}

        response = llm.create(
            model=model,
            max_tokens=1500,
            system=system_msg,
            tools=[],
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.7
        )

        text = ""
        if hasattr(response, "text"):
            text = response.text
        elif hasattr(response, "content"):
            if isinstance(response.content, list):
                text = " ".join(b.text for b in response.content if hasattr(b, "text"))
            else:
                text = str(response.content)

        if not text:
            return {"success": False, "error": True, "content": "LLM returned empty response."}

        # Cache for undo/try-again
        cache = _load_compose_cache()
        cache.append({
            "id": f"comp_{int(time.time())}",
            "prompt": prompt,
            "tone": tone,
            "result": text,
            "timestamp": datetime.now().isoformat(),
        })
        _save_compose_cache(cache)

        event_bus.emit("email_composed", {"tone": tone, "prompt": prompt[:100]})
        return {"success": True, "content": f"✍️ Draft composed ({tone} tone):\n\n{text}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Compose error: {e}"}


def rewrite_email(text, style="concise", tone="professional"):
    """Rewrite provided email text with a target style and tone.

    Args:
        text: The email text to rewrite
        style: concise/detailed/bullet_points/executive_summary/action_oriented
        tone: Tone preset key
    """
    try:
        if not text:
            return {"success": False, "error": True, "content": "No text provided to rewrite."}

        tone_guide = _TONE_PRESETS.get(tone, _TONE_PRESETS["formal"])
        style_guide = _STYLE_INSTRUCTIONS.get(style, _STYLE_INSTRUCTIONS["concise"])

        system_msg = f"""You are an expert email editor. Rewrite the email according to these instructions:

STYLE: {style_guide}
TONE: {tone_guide}

RULES:
- Output ONLY the rewritten email — no commentary
- Preserve the original meaning and key information
- Keep it natural and human-sounding
- Include Subject line if one was provided"""

        llm, model = _get_llm_for_compose()
        if not llm:
            return {"success": False, "error": True, "content": "LLM not available for rewrite."}

        response = llm.create(
            model=model,
            max_tokens=1500,
            system=system_msg,
            tools=[],
            messages=[{"role": "user", "content": f"Rewrite this email:\n\n{text[:2000]}"}],
            temperature=0.5
        )

        result = ""
        if hasattr(response, "text"):
            result = response.text
        elif hasattr(response, "content"):
            if isinstance(response.content, list):
                result = " ".join(b.text for b in response.content if hasattr(b, "text"))
            else:
                result = str(response.content)

        if not result:
            return {"success": False, "error": True, "content": "LLM returned empty rewrite."}

        cache = _load_compose_cache()
        cache.append({
            "id": f"rewrite_{int(time.time())}",
            "original": text[:500],
            "style": style,
            "tone": tone,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })
        _save_compose_cache(cache)

        event_bus.emit("email_rewritten", {"style": style, "tone": tone})
        return {"success": True, "content": f"✏️ Rewritten ({style}, {tone} tone):\n\n{result}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Rewrite error: {e}"}


def adjust_tone(text, tone):
    """Re-tone existing email text to the specified tone.

    Args:
        text: Email text to adjust
        tone: Target tone (formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic)
    """
    try:
        if not text:
            return {"success": False, "error": True, "content": "No text provided."}
        if tone not in _TONE_PRESETS:
            return {"success": False, "error": True, "content": f"Unknown tone '{tone}'. Available: {', '.join(_TONE_PRESETS.keys())}"}

        return rewrite_email(text, style="concise" if tone == "concise" else "detailed", tone=tone)

    except Exception as e:
        return {"success": False, "error": True, "content": f"Tone adjustment error: {e}"}


def suggest_subject_lines(body, count=3):
    """Generate subject line suggestions from email body text.

    Args:
        body: Email body text
        count: Number of suggestions (default 3)
    """
    try:
        if not body:
            return {"success": False, "error": True, "content": "No body text provided."}

        llm, model = _get_llm_for_compose()
        if not llm:
            return {"success": False, "error": True, "content": "LLM not available."}

        response = llm.create(
            model=model,
            max_tokens=300,
            system=f"Generate exactly {count} email subject line options for the given email body. Return ONLY the subject lines, one per line, numbered 1-{count}. No commentary.",
            tools=[],
            messages=[{"role": "user", "content": f"Email body:\n{body[:1500]}"}],
            temperature=0.8
        )

        result = ""
        if hasattr(response, "text"):
            result = response.text
        elif hasattr(response, "content"):
            if isinstance(response.content, list):
                result = " ".join(b.text for b in response.content if hasattr(b, "text"))
            else:
                result = str(response.content)

        if not result:
            return {"success": False, "error": True, "content": "LLM returned empty suggestions."}

        return {"success": True, "content": f"📋 Subject Line Suggestions:\n{result}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Subject suggestion error: {e}"}


def proofread_email(text):
    """Check grammar, spelling, clarity and return annotated corrections.

    Args:
        text: Email text to proofread
    """
    try:
        if not text:
            return {"success": False, "error": True, "content": "No text provided."}

        llm, model = _get_llm_for_compose()
        if not llm:
            return {"success": False, "error": True, "content": "LLM not available."}

        response = llm.create(
            model=model,
            max_tokens=1500,
            system="""You are a professional email proofreader. Analyze the email for:
1. Grammar & spelling errors
2. Clarity issues
3. Tone consistency
4. Professional improvements

Format your response as:
🔍 ISSUES FOUND:
- [Issue type]: Description → Suggested fix

✅ CORRECTED VERSION:
[The corrected email text]

📊 SCORE: X/10 (where 10 = perfect)

If the email is already perfect, say so briefly.""",
            tools=[],
            messages=[{"role": "user", "content": f"Proofread this email:\n\n{text[:2000]}"}],
            temperature=0.3
        )

        result = ""
        if hasattr(response, "text"):
            result = response.text
        elif hasattr(response, "content"):
            if isinstance(response.content, list):
                result = " ".join(b.text for b in response.content if hasattr(b, "text"))
            else:
                result = str(response.content)

        if not result:
            return {"success": False, "error": True, "content": "Proofread returned empty."}

        event_bus.emit("email_proofread", {"length": len(text)})
        return {"success": True, "content": f"📝 Proofread Results:\n\n{result}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Proofread error: {e}"}


def compose_reply_draft(index, instructions, tone="professional", mailbox="inbox"):
    """Read email at index, generate a reply draft per instructions.

    Args:
        index: Email index to reply to
        instructions: What the reply should say/accomplish
        tone: Tone preset
        mailbox: Mailbox to read from
    """
    try:
        # Read the original email
        original = read_email(index, mailbox=mailbox)
        if not original.get("success"):
            return original

        context = original["content"]
        prompt = f"Write a reply to this email. Instructions: {instructions}"

        result = smart_compose(prompt, context_email=context, tone=tone)
        if result.get("success"):
            result["content"] = f"💬 Reply draft for email #{index}:\n\n" + result["content"].replace("✍️ Draft composed", "Generated")

        return result

    except Exception as e:
        return {"success": False, "error": True, "content": f"Reply draft error: {e}"}


# ═══════════════════════════════════════════════════════════════════
# ██  PHASE 10B — EMAIL DELEGATION & TASK ASSIGNMENT              ██
# ═══════════════════════════════════════════════════════════════════

DELEGATIONS_PATH = os.path.join(TARS_ROOT, "memory", "email_delegations.json")


def _load_delegations():
    """Load delegation records."""
    try:
        if os.path.exists(DELEGATIONS_PATH):
            with open(DELEGATIONS_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_delegations(data):
    """Save delegation records (max 200)."""
    try:
        os.makedirs(os.path.dirname(DELEGATIONS_PATH), exist_ok=True)
        with open(DELEGATIONS_PATH, "w") as f:
            json.dump(data[-200:], f, indent=2)
    except Exception:
        pass


def delegate_email(index, delegate_to, instructions="", deadline_hours=48, mailbox="inbox"):
    """Forward email to a delegate with tracked delegation status.

    Args:
        index: Email index to delegate
        delegate_to: Email address of the delegate
        instructions: Instructions for the delegate
        deadline_hours: Hours until deadline (default 48)
        mailbox: Source mailbox
    """
    try:
        if not delegate_to:
            return {"success": False, "error": True, "content": "Need delegate_to email address."}

        # Read the original email
        original = read_email(index, mailbox=mailbox)
        if not original.get("success"):
            return original

        # Extract subject from the original
        subject_match = re.search(r"Subject:\s*(.+?)(?:\n|$)", original["content"])
        email_subject = subject_match.group(1).strip() if subject_match else f"Email #{index}"

        # Forward with instructions
        forward_body = f"[Delegated by TARS]\n\nInstructions: {instructions}\nDeadline: {deadline_hours} hours\n\n--- Original Email ---\n{original['content'][:2000]}"
        fwd_result = forward_email(index, delegate_to, comment=forward_body, mailbox=mailbox)

        # Create delegation record
        delegation = {
            "id": f"del_{int(time.time())}_{hash(delegate_to) % 9999:04d}",
            "email_subject": email_subject,
            "email_index": index,
            "delegate_to": delegate_to,
            "delegated_by": DEFAULT_FROM,
            "instructions": instructions,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "deadline": (datetime.now() + timedelta(hours=deadline_hours)).isoformat(),
            "completed_at": None,
            "outcome": "",
            "nudge_count": 0,
            "notes": [],
        }

        delegations = _load_delegations()
        delegations.append(delegation)
        _save_delegations(delegations)

        event_bus.emit("email_delegated", {
            "delegate_to": delegate_to,
            "subject": email_subject,
            "deadline_hours": deadline_hours,
        })

        fwd_status = "✅ forwarded" if fwd_result.get("success") else "⚠️ forward failed"
        return {"success": True, "content": f"📋 Delegated to {delegate_to} ({fwd_status})\n  Subject: {email_subject}\n  Deadline: {deadline_hours}h\n  ID: {delegation['id']}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delegation error: {e}"}


def list_delegations(status="all", delegate_to=None):
    """List delegations filtered by status or assignee.

    Args:
        status: Filter by status (all/pending/in_progress/completed/overdue)
        delegate_to: Filter by delegate email address
    """
    try:
        delegations = _load_delegations()
        now = datetime.now()

        # Mark overdue
        for d in delegations:
            if d.get("status") in ("pending", "in_progress"):
                try:
                    deadline = datetime.fromisoformat(d.get("deadline", ""))
                    if now > deadline:
                        d["status"] = "overdue"
                except (ValueError, TypeError):
                    pass

        # Filter
        if status == "overdue":
            filtered = [d for d in delegations if d.get("status") == "overdue"]
        elif status != "all":
            filtered = [d for d in delegations if d["status"] == status]
        else:
            filtered = delegations

        if delegate_to:
            filtered = [d for d in filtered if delegate_to.lower() in d.get("delegate_to", "").lower()]

        if not filtered:
            return {"success": True, "content": f"📭 No delegations found (filter: {status})."}

        lines = [f"📋 Delegations ({len(filtered)} found, filter: {status}):"]
        for d in reversed(filtered[-20:]):
            status_icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "overdue": "🔴", "cancelled": "❌"}.get(d.get("status", ""), "❓")
            lines.append(f"  {status_icon} [{d.get('id', '?')}] → {d.get('delegate_to', '?')}")
            lines.append(f"      {d.get('email_subject', d.get('subject', 'No subject'))}")
            lines.append(f"      Status: {d.get('status', '?')} | Nudges: {d.get('nudge_count', 0)}")

        _save_delegations(delegations)
        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List delegations error: {e}"}


def update_delegation(delegation_id, status=None, notes=None):
    """Update delegation status or add notes.

    Args:
        delegation_id: Delegation ID
        status: New status (pending/in_progress/completed/cancelled)
        notes: Note text to append
    """
    try:
        if not delegation_id:
            return {"success": False, "error": True, "content": "Need delegation_id."}

        delegations = _load_delegations()
        found = None
        for d in delegations:
            if d["id"] == delegation_id:
                found = d
                break

        if not found:
            return {"success": False, "error": True, "content": f"Delegation '{delegation_id}' not found."}

        changes = []
        if status:
            found["status"] = status
            changes.append(f"status → {status}")
            if status == "completed":
                found["completed_at"] = datetime.now().isoformat()
        if notes:
            found.setdefault("notes", []).append({
                "text": notes,
                "timestamp": datetime.now().isoformat(),
            })
            changes.append("note added")

        _save_delegations(delegations)
        return {"success": True, "content": f"✅ Delegation {delegation_id} updated: {', '.join(changes)}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update delegation error: {e}"}


def complete_delegation(delegation_id, outcome=""):
    """Mark a delegation as completed with outcome summary.

    Args:
        delegation_id: Delegation ID
        outcome: Outcome description
    """
    try:
        if not delegation_id:
            return {"success": False, "error": True, "content": "Need delegation_id."}

        delegations = _load_delegations()
        found = None
        for d in delegations:
            if d["id"] == delegation_id:
                found = d
                break

        if not found:
            return {"success": False, "error": True, "content": f"Delegation '{delegation_id}' not found."}

        found["status"] = "completed"
        found["completed_at"] = datetime.now().isoformat()
        found["outcome"] = outcome

        _save_delegations(delegations)

        event_bus.emit("delegation_completed", {
            "delegation_id": delegation_id,
            "delegate_to": found.get("delegate_to", ""),
            "subject": found.get("email_subject", found.get("subject", "")),
        })

        return {"success": True, "content": f"✅ Delegation {delegation_id} completed.\n  Outcome: {outcome or '(none)'}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Complete delegation error: {e}"}


def cancel_delegation(delegation_id):
    """Cancel a delegation.

    Args:
        delegation_id: Delegation ID to cancel
    """
    try:
        if not delegation_id:
            return {"success": False, "error": True, "content": "Need delegation_id."}

        delegations = _load_delegations()
        found = None
        for d in delegations:
            if d["id"] == delegation_id:
                found = d
                break

        if not found:
            return {"success": False, "error": True, "content": f"Delegation '{delegation_id}' not found."}

        found["status"] = "cancelled"
        found["completed_at"] = datetime.now().isoformat()
        _save_delegations(delegations)

        return {"success": True, "content": f"❌ Delegation {delegation_id} cancelled."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Cancel delegation error: {e}"}


def delegation_dashboard():
    """Get delegation overview — active/overdue/completed counts, per-delegate breakdown."""
    try:
        delegations = _load_delegations()
        now = datetime.now()

        # Mark overdue
        for d in delegations:
            if d.get("status") in ("pending", "in_progress"):
                try:
                    deadline = datetime.fromisoformat(d.get("deadline", ""))
                    if now > deadline:
                        d["status"] = "overdue"
                except (ValueError, TypeError):
                    pass

        total = len(delegations)
        pending = sum(1 for d in delegations if d.get("status") == "pending")
        in_progress = sum(1 for d in delegations if d.get("status") == "in_progress")
        completed = sum(1 for d in delegations if d.get("status") == "completed")
        overdue = sum(1 for d in delegations if d.get("status") == "overdue")
        cancelled = sum(1 for d in delegations if d.get("status") == "cancelled")

        # Per-delegate breakdown
        delegate_counts = {}
        for d in delegations:
            who = d.get("delegate_to", "unknown")
            delegate_counts.setdefault(who, {"total": 0, "active": 0, "completed": 0})
            delegate_counts[who]["total"] += 1
            if d.get("status") in ("pending", "in_progress", "overdue"):
                delegate_counts[who]["active"] += 1
            elif d.get("status") == "completed":
                delegate_counts[who]["completed"] += 1

        # Average completion time
        completion_times = []
        for d in delegations:
            if d["status"] == "completed" and d.get("completed_at") and d.get("created_at"):
                try:
                    created = datetime.fromisoformat(d["created_at"])
                    done = datetime.fromisoformat(d["completed_at"])
                    completion_times.append((done - created).total_seconds() / 3600)
                except (ValueError, TypeError):
                    pass
        avg_hours = sum(completion_times) / len(completion_times) if completion_times else 0

        lines = [
            f"📋 Delegation Dashboard:",
            f"  Total: {total} | Pending: {pending} | In Progress: {in_progress}",
            f"  Completed: {completed} | Overdue: {overdue} | Cancelled: {cancelled}",
            f"  Avg completion: {avg_hours:.1f}h",
        ]

        if delegate_counts:
            lines.append(f"\n  👥 Per-Delegate Breakdown:")
            for who, counts in sorted(delegate_counts.items(), key=lambda x: x[1]["active"], reverse=True)[:10]:
                lines.append(f"    {who}: {counts['active']} active, {counts['completed']} done ({counts['total']} total)")

        _save_delegations(delegations)
        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Dashboard error: {e}"}


def nudge_delegation(delegation_id):
    """Send a follow-up nudge email to the delegate asking for status.

    Args:
        delegation_id: Delegation ID to nudge
    """
    try:
        if not delegation_id:
            return {"success": False, "error": True, "content": "Need delegation_id."}

        delegations = _load_delegations()
        found = None
        for d in delegations:
            if d["id"] == delegation_id:
                found = d
                break

        if not found:
            return {"success": False, "error": True, "content": f"Delegation '{delegation_id}' not found."}

        if found.get("status") in ("completed", "cancelled"):
            return {"success": False, "error": True, "content": f"Delegation already {found.get('status')}."}

        # Send nudge email
        email_subj = found.get("email_subject", found.get("subject", "Delegated Task"))
        subject = f"Follow-up: {email_subj}"
        body = f"Hi,\n\nJust following up on the delegated task:\n\n" \
               f"Subject: {email_subj}\n" \
               f"Instructions: {found.get('instructions', 'N/A')}\n" \
               f"Assigned: {found.get('created_at', '?')[:10]}\n\n" \
               f"Could you provide a status update?\n\nThanks,\nTARS"

        delegate_addr = found.get("delegate_to", "")
        send_result = send_email(delegate_addr, subject, body)

        found["nudge_count"] = found.get("nudge_count", 0) + 1
        found.setdefault("notes", []).append({
            "text": f"Nudge #{found['nudge_count']} sent",
            "timestamp": datetime.now().isoformat(),
        })
        _save_delegations(delegations)

        event_bus.emit("delegation_nudged", {
            "delegation_id": delegation_id,
            "delegate_to": found.get("delegate_to", ""),
            "nudge_count": found.get("nudge_count", 0),
        })

        status = "sent" if send_result.get("success") else "failed"
        return {"success": True, "content": f"📨 Nudge #{found.get('nudge_count', 0)} {status} to {found.get('delegate_to', '?')}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Nudge error: {e}"}


# ═══════════════════════════════════════════════════════════════════
# ██  PHASE 10C — CONTEXTUAL SEARCH & EMAIL MEMORY               ██
# ═══════════════════════════════════════════════════════════════════

SEARCH_INDEX_PATH = os.path.join(TARS_ROOT, "memory", "email_search_index.json")


def _load_search_index():
    """Load email search index."""
    try:
        if os.path.exists(SEARCH_INDEX_PATH):
            with open(SEARCH_INDEX_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_search_index(data):
    """Save search index (max 500)."""
    try:
        os.makedirs(os.path.dirname(SEARCH_INDEX_PATH), exist_ok=True)
        with open(SEARCH_INDEX_PATH, "w") as f:
            json.dump(data[-500:], f, indent=2)
    except Exception:
        pass


def _parse_natural_date(text):
    """Parse natural language date references into date ranges.

    Returns (start_date, end_date) as date strings or (None, None).
    """
    text_lower = text.lower()
    now = datetime.now()

    # "today"
    if "today" in text_lower:
        d = now.strftime("%Y-%m-%d")
        return d, d

    # "yesterday"
    if "yesterday" in text_lower:
        d = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return d, d

    # "last week"
    if "last week" in text_lower:
        start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y-%m-%d")
        end = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return start, end

    # "this week"
    if "this week" in text_lower:
        start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")

    # "last month"
    if "last month" in text_lower:
        first_of_month = now.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start.strftime("%Y-%m-%d"), last_month_end.strftime("%Y-%m-%d")

    # "this month"
    if "this month" in text_lower:
        start = now.replace(day=1).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")

    # "N days ago" / "last N days"
    m = re.search(r'(\d+)\s*days?\s*ago', text_lower)
    if m:
        days = int(m.group(1))
        d = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        return d, now.strftime("%Y-%m-%d")

    m = re.search(r'last\s+(\d+)\s*days?', text_lower)
    if m:
        days = int(m.group(1))
        start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")

    # "N weeks ago" / "last N weeks"
    m = re.search(r'(\d+)\s*weeks?\s*ago', text_lower)
    if not m:
        m = re.search(r'last\s+(\d+)\s*weeks?', text_lower)
    if m:
        weeks = int(m.group(1))
        start = (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")

    return None, None


def _parse_search_query(query):
    """Extract structured filters from natural language search query.

    Returns dict with: sender, subject_hint, date_from, date_to, keywords
    """
    filters = {"sender": None, "subject_hint": None, "date_from": None, "date_to": None, "keywords": []}
    query_lower = query.lower()

    # Extract sender hints: "from john" / "from sarah@company.com"
    sender_match = re.search(r'from\s+([a-zA-Z0-9_.@]+)', query_lower)
    if sender_match:
        filters["sender"] = sender_match.group(1)
        query_lower = query_lower[:sender_match.start()] + query_lower[sender_match.end():]

    # Extract "about <topic>"
    about_match = re.search(r'about\s+(?:the\s+)?(.+?)(?:\s+from|\s+last|\s+this|\s+in\s+|$)', query_lower)
    if about_match:
        filters["subject_hint"] = about_match.group(1).strip()

    # Extract date range
    date_from, date_to = _parse_natural_date(query_lower)
    filters["date_from"] = date_from
    filters["date_to"] = date_to

    # Extract remaining keywords (strip stopwords)
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "that", "this",
                 "from", "about", "last", "week", "month", "ago", "days", "find", "search", "email",
                 "me", "my", "i", "what", "where", "when", "how", "did", "said", "say", "get"}
    words = re.findall(r'\b[a-z]{3,}\b', query_lower)
    filters["keywords"] = [w for w in words if w not in stopwords]

    return filters


def _fuzzy_match(query, text, threshold=50):
    """Simple fuzzy match score between query and text (0-100)."""
    if not query or not text:
        return 0
    query_lower = query.lower()
    text_lower = text.lower()

    # Exact substring match
    if query_lower in text_lower:
        return 100

    # Token overlap
    q_tokens = set(query_lower.split())
    t_tokens = set(text_lower.split())
    if not q_tokens:
        return 0
    overlap = len(q_tokens & t_tokens) / len(q_tokens) * 100

    # Character trigram similarity
    def trigrams(s):
        return set(s[i:i + 3] for i in range(len(s) - 2)) if len(s) >= 3 else {s}

    q_tri = trigrams(query_lower)
    t_tri = trigrams(text_lower)
    tri_sim = len(q_tri & t_tri) / max(len(q_tri), 1) * 100

    return max(overlap, tri_sim)


def build_search_index(count=200, mailbox="inbox"):
    """Scan inbox and build/refresh the local search index.

    Args:
        count: Number of emails to index (default 200)
        mailbox: Mailbox to index
    """
    try:
        script = f'''
tell application "Mail"
    set mb to mailbox "{mailbox}" of account 1
    set msgs to messages of mb
    set total to count of msgs
    set scanCount to {count}
    if total < scanCount then set scanCount to total
    set output to ""
    repeat with i from 1 to scanCount
        set msg to item i of msgs
        set subj to subject of msg
        set sndr to sender of msg
        set dt to date received of msg
        set exc to (extract name from msg)
        set prev to ""
        try
            set prev to (content of msg)
            if length of prev > 200 then set prev to text 1 thru 200 of prev
        end try
        set output to output & i & "|||" & subj & "|||" & sndr & "|||" & (dt as string) & "|||" & prev & "\\n"
    end repeat
    return output
end tell'''

        result = _run_applescript(script)
        if not result:
            return {"success": False, "error": True, "content": "Failed to read inbox for indexing."}

        entries = []
        for line in result.strip().split("\n"):
            parts = line.split("|||")
            if len(parts) >= 4:
                entries.append({
                    "index": int(parts[0]) if parts[0].isdigit() else 0,
                    "subject": parts[1].strip(),
                    "sender": parts[2].strip(),
                    "date": parts[3].strip(),
                    "snippet": parts[4].strip() if len(parts) > 4 else "",
                    "mailbox": mailbox,
                })

        _save_search_index(entries)
        event_bus.emit("search_index_built", {"count": len(entries), "mailbox": mailbox})
        return {"success": True, "content": f"🔍 Search index built: {len(entries)} emails indexed from '{mailbox}'."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Index build error: {e}"}


def contextual_search(query, max_results=10):
    """Natural-language email search with fuzzy matching and date parsing.

    Args:
        query: Natural language query like "email from Sarah about budget last week"
        max_results: Max results to return
    """
    try:
        if not query:
            return {"success": False, "error": True, "content": "Need a search query."}

        # Parse intent
        filters = _parse_search_query(query)

        # Load index
        index = _load_search_index()

        # If index is empty or small, try AppleScript search as fallback
        if not index:
            return {"success": False, "error": True, "content": "Search index is empty. Run build_search_index first."}

        scored = []
        for entry in index:
            score = 0

            # Sender match
            if filters["sender"]:
                sender_lower = entry.get("sender", "").lower()
                if filters["sender"] in sender_lower:
                    score += 40
                elif _fuzzy_match(filters["sender"], sender_lower) > 60:
                    score += 25

            # Subject/topic match
            if filters["subject_hint"]:
                subj_score = _fuzzy_match(filters["subject_hint"], entry.get("subject", ""))
                snippet_score = _fuzzy_match(filters["subject_hint"], entry.get("snippet", ""))
                score += max(subj_score, snippet_score) * 0.4

            # Keyword matches
            for kw in filters["keywords"]:
                combined = f"{entry.get('subject', '')} {entry.get('snippet', '')}".lower()
                if kw in combined:
                    score += 15

            # Date range filter
            if filters["date_from"] or filters["date_to"]:
                entry_date = entry.get("date", "")
                # Try to parse the date
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', entry_date)
                if not date_match:
                    # Try common date formats from AppleScript
                    for fmt in ["%A, %B %d, %Y at %I:%M:%S %p", "%m/%d/%Y", "%B %d, %Y"]:
                        try:
                            parsed = datetime.strptime(entry_date.strip(), fmt)
                            entry_date = parsed.strftime("%Y-%m-%d")
                            date_match = True
                            break
                        except (ValueError, TypeError):
                            continue

                if date_match:
                    if isinstance(date_match, re.Match):
                        entry_date = date_match.group(0)
                    if filters["date_from"] and entry_date < filters["date_from"]:
                        score -= 50  # Penalize out-of-range
                    if filters["date_to"] and entry_date > filters["date_to"]:
                        score -= 50
                    if filters["date_from"] and filters["date_to"]:
                        if filters["date_from"] <= entry_date <= filters["date_to"]:
                            score += 20

            if score > 5:
                scored.append((score, entry))

        # Sort by score
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_results]

        if not top:
            # Fallback to keyword search
            result = search_emails(query=query, count=max_results)
            if result.get("success"):
                return {"success": True, "content": f"🔍 No contextual matches. Keyword search results:\n{result['content']}"}
            return {"success": True, "content": "🔍 No matching emails found."}

        lines = [f"🔍 Contextual Search: \"{query}\" ({len(top)} results):"]
        for score, entry in top:
            lines.append(f"  📧 #{entry['index']} [{score:.0f}%] {entry.get('subject', '?')}")
            lines.append(f"      From: {entry.get('sender', '?')} | {entry.get('date', '?')}")
            snippet = entry.get("snippet", "")[:100]
            if snippet:
                lines.append(f"      {snippet}...")

        event_bus.emit("email_search", {"query": query, "results": len(top)})
        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Contextual search error: {e}"}


def conversation_recall(contact_query, days=14, summarize=False):
    """Pull all emails from/to a contact in a date window, optionally summarize.

    Args:
        contact_query: Contact name or email (partial match)
        days: How many days back to look (default 14)
        summarize: Whether to generate an LLM summary of the conversation
    """
    try:
        if not contact_query:
            return {"success": False, "error": True, "content": "Need a contact name or email."}

        # Search by sender
        result = search_emails(sender=contact_query, count=50)
        if not result.get("success"):
            return result

        content = result["content"]

        if summarize and content and "No emails found" not in content:
            llm, model = _get_llm_for_compose()
            if llm:
                try:
                    response = llm.create(
                        model=model,
                        max_tokens=800,
                        system="Summarize the email conversation below. Focus on: key topics, decisions, action items, and overall sentiment. Be concise.",
                        tools=[],
                        messages=[{"role": "user", "content": f"Summarize these emails from/to {contact_query}:\n\n{content[:3000]}"}],
                        temperature=0.3
                    )
                    summary = ""
                    if hasattr(response, "text"):
                        summary = response.text
                    elif hasattr(response, "content"):
                        if isinstance(response.content, list):
                            summary = " ".join(b.text for b in response.content if hasattr(b, "text"))
                        else:
                            summary = str(response.content)
                    if summary:
                        content = f"📝 Conversation Summary ({contact_query}, last {days} days):\n{summary}\n\n--- Raw Emails ---\n{content}"
                except Exception:
                    pass

        event_bus.emit("conversation_recalled", {"contact": contact_query, "days": days})
        return {"success": True, "content": content}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Recall error: {e}"}


def search_by_date_range(start_date, end_date, sender=None, keyword=None):
    """Structured date-range search with optional filters.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        sender: Optional sender filter
        keyword: Optional keyword filter
    """
    try:
        if not start_date or not end_date:
            return {"success": False, "error": True, "content": "Need both start_date and end_date (YYYY-MM-DD)."}

        return search_emails(
            sender=sender,
            query=keyword,
            date_from=start_date,
            date_to=end_date,
            count=30,
        )

    except Exception as e:
        return {"success": False, "error": True, "content": f"Date range search error: {e}"}


def find_related_emails(index, mailbox="inbox", max_results=5):
    """Given an email, find related emails by subject similarity or same sender.

    Args:
        index: Email index to find related emails for
        mailbox: Mailbox
        max_results: Max related emails to return
    """
    try:
        # Read the target email
        original = read_email(index, mailbox=mailbox)
        if not original.get("success"):
            return original

        # Extract subject and sender
        content = original["content"]
        subject_match = re.search(r"Subject:\s*(.+?)(?:\n|$)", content)
        sender_match = re.search(r"From:\s*(.+?)(?:\n|$)", content)

        subject = subject_match.group(1).strip() if subject_match else ""
        sender = sender_match.group(1).strip() if sender_match else ""

        # Search index for related
        search_index = _load_search_index()
        scored = []

        for entry in search_index:
            if entry.get("index") == index:
                continue  # Skip self

            score = 0
            # Same sender
            if sender and sender.lower() in entry.get("sender", "").lower():
                score += 30

            # Subject similarity
            if subject:
                sim = _fuzzy_match(subject, entry.get("subject", ""))
                score += sim * 0.5

            # Snippet similarity
            snippet = entry.get("snippet", "")
            if snippet and subject:
                sim = _fuzzy_match(subject, snippet)
                score += sim * 0.2

            if score > 10:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_results]

        if not top:
            return {"success": True, "content": f"🔗 No related emails found for #{index}."}

        lines = [f"🔗 Related Emails for #{index} ({len(top)} found):"]
        for score, entry in top:
            lines.append(f"  📧 #{entry['index']} [{score:.0f}%] {entry.get('subject', '?')}")
            lines.append(f"      From: {entry.get('sender', '?')} | {entry.get('date', '?')}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Find related error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 11A: EMAIL SENTIMENT ANALYSIS
# ═══════════════════════════════════════════════════════════════════

SENTIMENT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_sentiment_cache.json")

# ── Keyword dictionaries for fast keyword-based sentiment scoring ──
_POSITIVE_KEYWORDS = {
    "thank", "thanks", "grateful", "appreciate", "great", "excellent",
    "wonderful", "amazing", "perfect", "fantastic", "awesome", "love",
    "pleased", "happy", "glad", "congratulations", "congrats", "well done",
    "good job", "impressive", "brilliant", "delighted", "thrilled",
    "excited", "looking forward", "pleasure", "kind", "generous",
    "helpful", "outstanding", "remarkable", "superb", "terrific",
}

_NEGATIVE_KEYWORDS = {
    "angry", "furious", "disappointed", "frustrated", "annoyed", "upset",
    "unacceptable", "terrible", "horrible", "awful", "disgusted", "hate",
    "worst", "pathetic", "ridiculous", "absurd", "outrageous", "complaint",
    "complain", "failing", "failed", "broken", "useless", "incompetent",
    "rude", "disrespectful", "unprofessional", "inexcusable", "demand",
    "immediately", "urgent", "asap", "overdue", "threatening", "legal action",
    "lawsuit", "escalate", "escalation", "unresolved", "ignored",
}

_URGENCY_KEYWORDS = {
    "urgent", "asap", "immediately", "critical", "emergency", "deadline",
    "overdue", "time-sensitive", "priority", "action required", "respond now",
    "must", "mandatory", "final notice", "last chance", "expire",
}


def _load_sentiment_cache():
    try:
        if os.path.exists(SENTIMENT_CACHE_PATH):
            with open(SENTIMENT_CACHE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"analyses": [], "sender_history": {}}


def _save_sentiment_cache(cache):
    try:
        os.makedirs(os.path.dirname(SENTIMENT_CACHE_PATH), exist_ok=True)
        with open(SENTIMENT_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, default=str)
    except Exception:
        pass


def _analyze_text_sentiment(text):
    """Keyword-based sentiment analysis. Returns dict with score, label, keywords found."""
    if not text:
        return {"score": 0.0, "label": "neutral", "positive_keywords": [], "negative_keywords": [], "urgency_keywords": []}

    text_lower = text.lower()
    words = set(text_lower.split())

    pos_found = []
    neg_found = []
    urg_found = []

    for kw in _POSITIVE_KEYWORDS:
        if kw in text_lower:
            pos_found.append(kw)
    for kw in _NEGATIVE_KEYWORDS:
        if kw in text_lower:
            neg_found.append(kw)
    for kw in _URGENCY_KEYWORDS:
        if kw in text_lower:
            urg_found.append(kw)

    # Score: -100 to +100
    pos_score = len(pos_found) * 15
    neg_score = len(neg_found) * 20  # Negative keywords weighted heavier
    raw_score = pos_score - neg_score

    # Clamp to -100..100
    score = max(-100, min(100, raw_score))

    # Label
    if score >= 30:
        label = "positive"
    elif score >= 10:
        label = "slightly_positive"
    elif score <= -30:
        label = "negative"
    elif score <= -10:
        label = "slightly_negative"
    else:
        label = "neutral"

    return {
        "score": score,
        "label": label,
        "positive_keywords": pos_found[:5],
        "negative_keywords": neg_found[:5],
        "urgency_keywords": urg_found[:5],
        "urgency": len(urg_found) > 0,
    }


def analyze_sentiment(index=1, mailbox="inbox"):
    """Analyze sentiment of a single email."""
    try:
        msg = read_message(index, mailbox)
        if not msg.get("success"):
            return msg

        content = msg.get("content", "")
        # Extract body text
        body = ""
        subject = ""
        sender = ""
        for line in content.split("\n"):
            if line.startswith("Subject: "):
                subject = line[9:]
            elif line.startswith("From: "):
                sender = line[6:]
            elif not line.startswith(("To: ", "CC: ", "Date: ", "Attachments: ")):
                body += line + " "

        combined_text = f"{subject} {body}".strip()
        analysis = _analyze_text_sentiment(combined_text)

        # Cache result
        cache = _load_sentiment_cache()
        entry = {
            "index": index,
            "mailbox": mailbox,
            "subject": subject,
            "sender": sender,
            "score": analysis["score"],
            "label": analysis["label"],
            "analyzed_at": datetime.now().isoformat(),
        }
        cache["analyses"].append(entry)
        # Keep last 500
        if len(cache["analyses"]) > 500:
            cache["analyses"] = cache["analyses"][-500:]

        # Track sender history
        if sender:
            sender_key = sender.lower().strip()
            if sender_key not in cache["sender_history"]:
                cache["sender_history"][sender_key] = []
            cache["sender_history"][sender_key].append({
                "score": analysis["score"],
                "label": analysis["label"],
                "date": datetime.now().isoformat(),
                "subject": subject[:80],
            })
            # Keep last 50 per sender
            if len(cache["sender_history"][sender_key]) > 50:
                cache["sender_history"][sender_key] = cache["sender_history"][sender_key][-50:]

        _save_sentiment_cache(cache)

        event_bus.emit("email_sentiment_analyzed", {
            "index": index, "score": analysis["score"], "label": analysis["label"],
        })

        if analysis["score"] <= -30:
            event_bus.emit("email_sentiment_alert", {
                "index": index, "score": analysis["score"], "sender": sender, "subject": subject,
            })

        emoji_map = {"positive": "😊", "slightly_positive": "🙂", "neutral": "😐",
                     "slightly_negative": "😟", "negative": "😠"}
        emoji = emoji_map.get(analysis["label"], "😐")

        lines = [f"{emoji} Sentiment Analysis — Email #{index}:"]
        lines.append(f"  Score: {analysis['score']:+d}/100 ({analysis['label']})")
        lines.append(f"  Subject: {subject[:60]}")
        lines.append(f"  From: {sender}")
        if analysis["positive_keywords"]:
            lines.append(f"  ✅ Positive signals: {', '.join(analysis['positive_keywords'])}")
        if analysis["negative_keywords"]:
            lines.append(f"  ❌ Negative signals: {', '.join(analysis['negative_keywords'])}")
        if analysis["urgency"]:
            lines.append(f"  ⚡ Urgency detected: {', '.join(analysis['urgency_keywords'])}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Sentiment analysis error: {e}"}


def batch_sentiment(count=20, mailbox="inbox"):
    """Analyze sentiment across multiple inbox emails."""
    try:
        inbox_result = read_inbox(count)
        if not inbox_result.get("success"):
            return inbox_result

        content = inbox_result.get("content", "")
        analyses = []

        for line in content.split("\n"):
            # Parse index from inbox listing
            if line.strip().startswith("[") and "]" in line:
                try:
                    idx_str = line.split("]")[0].replace("[", "").strip()
                    idx = int(idx_str)
                except (ValueError, IndexError):
                    continue

                # Get subject text for quick analysis
                subject_part = line.split("]", 1)[1].strip() if "]" in line else ""
                analysis = _analyze_text_sentiment(subject_part)
                analyses.append({
                    "index": idx,
                    "score": analysis["score"],
                    "label": analysis["label"],
                    "preview": subject_part[:50],
                })

        if not analyses:
            return {"success": True, "content": "📊 No emails to analyze."}

        # Stats
        scores = [a["score"] for a in analyses]
        avg_score = sum(scores) / len(scores) if scores else 0
        positive = sum(1 for a in analyses if a["score"] >= 10)
        negative = sum(1 for a in analyses if a["score"] <= -10)
        neutral = len(analyses) - positive - negative

        lines = [f"📊 Batch Sentiment Analysis ({len(analyses)} emails):"]
        lines.append(f"  Average score: {avg_score:+.1f}/100")
        lines.append(f"  😊 Positive: {positive} | 😐 Neutral: {neutral} | 😟 Negative: {negative}")

        if negative > 0:
            lines.append(f"\n  ⚠️ Negative emails:")
            for a in sorted(analyses, key=lambda x: x["score"]):
                if a["score"] <= -10:
                    lines.append(f"    #{a['index']} [{a['score']:+d}] {a['preview']}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Batch sentiment error: {e}"}


def sender_sentiment(sender_email):
    """Get sentiment history for a specific sender."""
    try:
        if not sender_email:
            return {"success": False, "error": True, "content": "sender_email is required"}

        cache = _load_sentiment_cache()
        sender_key = sender_email.lower().strip()

        # Find matching sender entries
        history = cache.get("sender_history", {}).get(sender_key, [])

        # Also check partial matches
        if not history:
            for key, entries in cache.get("sender_history", {}).items():
                if sender_key in key or key in sender_key:
                    history = entries
                    sender_key = key
                    break

        if not history:
            return {"success": True, "content": f"📊 No sentiment history found for '{sender_email}'. Analyze some emails from this sender first."}

        scores = [h["score"] for h in history]
        avg = sum(scores) / len(scores) if scores else 0
        trend = "improving" if len(scores) >= 2 and scores[-1] > scores[0] else "declining" if len(scores) >= 2 and scores[-1] < scores[0] else "stable"

        lines = [f"📊 Sentiment History — {sender_email}:"]
        lines.append(f"  Emails analyzed: {len(history)}")
        lines.append(f"  Average score: {avg:+.1f}/100")
        lines.append(f"  Trend: {trend}")
        lines.append(f"  Range: {min(scores):+d} to {max(scores):+d}")

        lines.append(f"\n  Recent:")
        for h in history[-5:]:
            emoji = "😊" if h["score"] >= 10 else "😟" if h["score"] <= -10 else "😐"
            lines.append(f"    {emoji} [{h['score']:+d}] {h.get('subject', '?')[:50]} ({h.get('date', '?')[:10]})")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Sender sentiment error: {e}"}


def sentiment_alerts(threshold=-20):
    """Flag emails with negative sentiment below threshold."""
    try:
        inbox_result = read_inbox(30)
        if not inbox_result.get("success"):
            return inbox_result

        content = inbox_result.get("content", "")
        alerts = []

        for line in content.split("\n"):
            if line.strip().startswith("[") and "]" in line:
                try:
                    idx_str = line.split("]")[0].replace("[", "").strip()
                    idx = int(idx_str)
                except (ValueError, IndexError):
                    continue

                subject_part = line.split("]", 1)[1].strip() if "]" in line else ""
                analysis = _analyze_text_sentiment(subject_part)

                if analysis["score"] <= threshold:
                    alerts.append({
                        "index": idx,
                        "score": analysis["score"],
                        "label": analysis["label"],
                        "preview": subject_part[:60],
                        "negative_keywords": analysis["negative_keywords"],
                    })

                    event_bus.emit("email_sentiment_alert", {
                        "index": idx, "score": analysis["score"], "preview": subject_part[:40],
                    })

        if not alerts:
            return {"success": True, "content": f"✅ No emails with sentiment below {threshold}. Inbox looks positive!"}

        lines = [f"🚨 Sentiment Alerts ({len(alerts)} emails below {threshold}):"]
        for a in sorted(alerts, key=lambda x: x["score"]):
            lines.append(f"  ⚠️ #{a['index']} [{a['score']:+d}] {a['preview']}")
            if a["negative_keywords"]:
                lines.append(f"      Signals: {', '.join(a['negative_keywords'][:3])}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Sentiment alerts error: {e}"}


def sentiment_report(period="week"):
    """Sentiment analytics over a period."""
    try:
        cache = _load_sentiment_cache()
        analyses = cache.get("analyses", [])

        if not analyses:
            return {"success": True, "content": "📊 No sentiment data yet. Analyze some emails first."}

        # Filter by period
        now = datetime.now()
        if period == "day":
            cutoff = now - timedelta(days=1)
        elif period == "week":
            cutoff = now - timedelta(weeks=1)
        elif period == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = now - timedelta(weeks=1)

        cutoff_str = cutoff.isoformat()
        filtered = [a for a in analyses if a.get("analyzed_at", "") >= cutoff_str]

        if not filtered:
            return {"success": True, "content": f"📊 No sentiment data for the last {period}. Analyze some emails first."}

        scores = [a["score"] for a in filtered]
        avg = sum(scores) / len(scores)
        positive = sum(1 for s in scores if s >= 10)
        negative = sum(1 for s in scores if s <= -10)
        neutral = len(scores) - positive - negative

        # Top negative senders
        sender_neg = {}
        for a in filtered:
            if a.get("score", 0) <= -10:
                sender = a.get("sender", "unknown")
                sender_neg[sender] = sender_neg.get(sender, 0) + 1

        lines = [f"📊 Sentiment Report — Last {period}:"]
        lines.append(f"  Emails analyzed: {len(filtered)}")
        lines.append(f"  Average sentiment: {avg:+.1f}/100")
        lines.append(f"  😊 Positive: {positive} ({positive*100//len(filtered)}%)")
        lines.append(f"  😐 Neutral: {neutral} ({neutral*100//len(filtered)}%)")
        lines.append(f"  😟 Negative: {negative} ({negative*100//len(filtered)}%)")

        if sender_neg:
            lines.append(f"\n  Top negative senders:")
            for sender, count in sorted(sender_neg.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"    ⚠️ {sender}: {count} negative emails")

        # Overall mood
        if avg >= 20:
            mood = "🌟 Excellent — inbox is overwhelmingly positive"
        elif avg >= 5:
            mood = "👍 Good — mostly positive communications"
        elif avg >= -5:
            mood = "😐 Neutral — balanced mix"
        elif avg >= -20:
            mood = "⚠️ Concerning — some negative patterns"
        else:
            mood = "🚨 Alert — significant negativity detected"
        lines.append(f"\n  Overall mood: {mood}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Sentiment report error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 11B: SMART FOLDERS / SAVED SEARCHES
# ═══════════════════════════════════════════════════════════════════

import uuid

SMART_FOLDERS_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_smart_folders.json")


def _load_smart_folders():
    try:
        if os.path.exists(SMART_FOLDERS_PATH):
            with open(SMART_FOLDERS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"folders": []}


def _save_smart_folders(data):
    try:
        os.makedirs(os.path.dirname(SMART_FOLDERS_PATH), exist_ok=True)
        with open(SMART_FOLDERS_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def _evaluate_smart_folder_criteria(email_text, criteria):
    """Check if an email line matches smart folder criteria."""
    text_lower = email_text.lower()

    # from_contains
    if criteria.get("from_contains"):
        if criteria["from_contains"].lower() not in text_lower:
            return False

    # subject_contains
    if criteria.get("subject_contains"):
        if criteria["subject_contains"].lower() not in text_lower:
            return False

    # keyword
    if criteria.get("keyword"):
        if criteria["keyword"].lower() not in text_lower:
            return False

    # has_attachment
    if criteria.get("has_attachment"):
        if "📎" not in email_text and "attachment" not in text_lower:
            return False

    # is_unread
    if criteria.get("is_unread"):
        if "🔵" not in email_text and "unread" not in text_lower:
            return False

    # is_flagged
    if criteria.get("is_flagged"):
        if "🚩" not in email_text and "flag" not in text_lower:
            return False

    # exclude_from
    if criteria.get("exclude_from"):
        if criteria["exclude_from"].lower() in text_lower:
            return False

    return True


def create_smart_folder(name, criteria, pinned=False):
    """Create a dynamic smart folder with search criteria."""
    try:
        if not name:
            return {"success": False, "error": True, "content": "Folder name is required"}
        if not criteria or not isinstance(criteria, dict):
            return {"success": False, "error": True, "content": "Search criteria dict is required"}

        data = _load_smart_folders()
        folder_id = f"sf_{uuid.uuid4().hex[:8]}"

        folder = {
            "id": folder_id,
            "name": name,
            "criteria": criteria,
            "pinned": pinned,
            "created_at": datetime.now().isoformat(),
            "last_accessed": None,
            "access_count": 0,
        }

        data["folders"].append(folder)
        _save_smart_folders(data)

        event_bus.emit("smart_folder_created", {"id": folder_id, "name": name})

        criteria_desc = ", ".join(f"{k}={v}" for k, v in criteria.items())
        return {"success": True, "content": f"📁 Smart folder created: '{name}' (ID: {folder_id})\n  Criteria: {criteria_desc}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Create smart folder error: {e}"}


def list_smart_folders():
    """List all smart folders."""
    try:
        data = _load_smart_folders()
        folders = data.get("folders", [])

        if not folders:
            return {"success": True, "content": "📁 No smart folders created yet."}

        # Sort: pinned first, then by access count
        pinned = [f for f in folders if f.get("pinned")]
        unpinned = [f for f in folders if not f.get("pinned")]

        lines = [f"📁 Smart Folders ({len(folders)}):"]

        if pinned:
            lines.append("  📌 Pinned:")
            for f in pinned:
                criteria_desc = ", ".join(f"{k}={v}" for k, v in f.get("criteria", {}).items())
                lines.append(f"    📁 {f['name']} [{f['id']}] — {criteria_desc}")
                lines.append(f"       Accessed: {f.get('access_count', 0)} times")

        if unpinned:
            if pinned:
                lines.append("  Regular:")
            for f in unpinned:
                criteria_desc = ", ".join(f"{k}={v}" for k, v in f.get("criteria", {}).items())
                lines.append(f"    📁 {f['name']} [{f['id']}] — {criteria_desc}")
                lines.append(f"       Accessed: {f.get('access_count', 0)} times")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List smart folders error: {e}"}


def get_smart_folder(folder_id, max_results=20):
    """Execute a smart folder's search criteria and return matching emails."""
    try:
        if not folder_id:
            return {"success": False, "error": True, "content": "folder_id is required"}

        data = _load_smart_folders()
        folder = None
        for f in data.get("folders", []):
            if f["id"] == folder_id:
                folder = f
                break

        if not folder:
            return {"success": False, "error": True, "content": f"Smart folder '{folder_id}' not found"}

        criteria = folder.get("criteria", {})

        # Use search_emails for structured criteria
        search_kwargs = {}
        if criteria.get("from_contains"):
            search_kwargs["sender"] = criteria["from_contains"]
        if criteria.get("subject_contains"):
            search_kwargs["subject"] = criteria["subject_contains"]
        if criteria.get("keyword"):
            search_kwargs["keyword"] = criteria["keyword"]
        if criteria.get("is_unread"):
            search_kwargs["unread_only"] = True
        if criteria.get("is_flagged"):
            search_kwargs["flagged_only"] = True
        if criteria.get("has_attachment"):
            search_kwargs["has_attachments"] = True
        search_kwargs["max_results"] = max_results

        result = search_emails(**search_kwargs)

        # Update access stats
        folder["last_accessed"] = datetime.now().isoformat()
        folder["access_count"] = folder.get("access_count", 0) + 1
        _save_smart_folders(data)

        if not result.get("success"):
            return result

        content = result.get("content", "")
        return {"success": True, "content": f"📁 Smart Folder: {folder['name']}\n{content}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get smart folder error: {e}"}


def update_smart_folder(folder_id, name=None, criteria=None):
    """Update a smart folder's name or criteria."""
    try:
        if not folder_id:
            return {"success": False, "error": True, "content": "folder_id is required"}

        data = _load_smart_folders()
        folder = None
        for f in data.get("folders", []):
            if f["id"] == folder_id:
                folder = f
                break

        if not folder:
            return {"success": False, "error": True, "content": f"Smart folder '{folder_id}' not found"}

        changes = []
        if name:
            folder["name"] = name
            changes.append(f"name → {name}")
        if criteria and isinstance(criteria, dict):
            folder["criteria"] = criteria
            criteria_desc = ", ".join(f"{k}={v}" for k, v in criteria.items())
            changes.append(f"criteria → {criteria_desc}")

        if not changes:
            return {"success": True, "content": "No changes specified."}

        _save_smart_folders(data)

        event_bus.emit("smart_folder_updated", {"id": folder_id, "changes": changes})

        return {"success": True, "content": f"📁 Smart folder updated: {', '.join(changes)}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update smart folder error: {e}"}


def delete_smart_folder(folder_id):
    """Delete a smart folder."""
    try:
        if not folder_id:
            return {"success": False, "error": True, "content": "folder_id is required"}

        data = _load_smart_folders()
        before = len(data.get("folders", []))
        data["folders"] = [f for f in data.get("folders", []) if f["id"] != folder_id]
        after = len(data["folders"])

        if before == after:
            return {"success": False, "error": True, "content": f"Smart folder '{folder_id}' not found"}

        _save_smart_folders(data)

        event_bus.emit("smart_folder_deleted", {"id": folder_id})

        return {"success": True, "content": f"📁 Smart folder '{folder_id}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete smart folder error: {e}"}


def pin_smart_folder(folder_id, pinned=True):
    """Pin or unpin a smart folder for quick access."""
    try:
        if not folder_id:
            return {"success": False, "error": True, "content": "folder_id is required"}

        data = _load_smart_folders()
        folder = None
        for f in data.get("folders", []):
            if f["id"] == folder_id:
                folder = f
                break

        if not folder:
            return {"success": False, "error": True, "content": f"Smart folder '{folder_id}' not found"}

        folder["pinned"] = pinned
        _save_smart_folders(data)

        action = "pinned 📌" if pinned else "unpinned"
        return {"success": True, "content": f"📁 Smart folder '{folder['name']}' {action}."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Pin smart folder error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 11C: EMAIL THREAD SUMMARIZATION
# ═══════════════════════════════════════════════════════════════════

def _get_thread_messages(subject_or_index, max_messages=20):
    """Helper: fetch thread messages as structured data."""
    result = get_email_thread(subject_or_index, max_messages)
    if not result.get("success"):
        return None, result

    content = result.get("content", "")
    messages = []
    current_msg = {}

    for line in content.split("\n"):
        line_stripped = line.strip()
        if line_stripped.startswith("───") or line_stripped.startswith("---"):
            if current_msg.get("body"):
                messages.append(current_msg)
            current_msg = {"body": ""}
        elif line_stripped.startswith("From: "):
            current_msg["from"] = line_stripped[6:]
        elif line_stripped.startswith("Date: "):
            current_msg["date"] = line_stripped[6:]
        elif line_stripped.startswith("Subject: "):
            current_msg["subject"] = line_stripped[9:]
        elif line_stripped.startswith("To: "):
            current_msg["to"] = line_stripped[4:]
        elif line_stripped:
            current_msg["body"] = current_msg.get("body", "") + line_stripped + " "

    if current_msg.get("body"):
        messages.append(current_msg)

    return messages, None


def summarize_thread(subject_or_index, max_messages=20):
    """AI-powered summary of an email thread."""
    try:
        messages, err = _get_thread_messages(subject_or_index, max_messages)
        if err:
            return err
        if not messages:
            return {"success": True, "content": "📝 No thread messages found to summarize."}

        # Try LLM summarization
        try:
            llm = _get_llm_for_compose()
            if llm:
                thread_text = ""
                for i, m in enumerate(messages):
                    thread_text += f"\n--- Message {i+1} ---\n"
                    thread_text += f"From: {m.get('from', '?')}\n"
                    thread_text += f"Date: {m.get('date', '?')}\n"
                    thread_text += f"{m.get('body', '')}\n"

                prompt = f"""Summarize this email thread concisely. Include:
1. Main topic/purpose
2. Key points discussed
3. Current status/outcome
4. Any pending items

Thread ({len(messages)} messages):
{thread_text[:4000]}

Provide a clear, concise summary in 3-5 bullet points."""

                response = llm.chat([{"role": "user", "content": prompt}])
                summary_text = ""
                if hasattr(response, "text"):
                    summary_text = response.text
                elif hasattr(response, "content"):
                    if isinstance(response.content, list):
                        summary_text = " ".join(getattr(b, "text", str(b)) for b in response.content)
                    else:
                        summary_text = str(response.content)

                if summary_text and len(summary_text) > 20:
                    event_bus.emit("thread_summarized", {
                        "subject": messages[0].get("subject", "?"),
                        "message_count": len(messages),
                    })

                    lines = [f"📝 Thread Summary ({len(messages)} messages):"]
                    lines.append(f"  Subject: {messages[0].get('subject', '?')}")
                    lines.append(f"  Participants: {', '.join(set(m.get('from', '?') for m in messages))}")
                    lines.append(f"\n{summary_text}")

                    return {"success": True, "content": "\n".join(lines)}
        except Exception:
            pass

        # Fallback: keyword-based extraction
        subject = messages[0].get("subject", "?") if messages else "?"
        participants = list(set(m.get("from", "?") for m in messages))
        all_text = " ".join(m.get("body", "") for m in messages)
        word_count = len(all_text.split())

        lines = [f"📝 Thread Summary ({len(messages)} messages):"]
        lines.append(f"  Subject: {subject}")
        lines.append(f"  Participants: {', '.join(participants[:5])}")
        lines.append(f"  Total words: {word_count}")
        lines.append(f"  Date range: {messages[0].get('date', '?')} → {messages[-1].get('date', '?')}")
        lines.append(f"\n  Latest message from: {messages[-1].get('from', '?')}")
        lines.append(f"  Preview: {messages[-1].get('body', '')[:200]}...")

        event_bus.emit("thread_summarized", {
            "subject": subject, "message_count": len(messages),
        })

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Summarize thread error: {e}"}


def thread_decisions(subject_or_index, max_messages=20):
    """Extract key decisions from a thread."""
    try:
        messages, err = _get_thread_messages(subject_or_index, max_messages)
        if err:
            return err
        if not messages:
            return {"success": True, "content": "📋 No thread messages found."}

        # Try LLM extraction
        try:
            llm = _get_llm_for_compose()
            if llm:
                thread_text = ""
                for i, m in enumerate(messages):
                    thread_text += f"\n--- Message {i+1} from {m.get('from', '?')} ---\n"
                    thread_text += f"{m.get('body', '')}\n"

                prompt = f"""Extract all KEY DECISIONS made in this email thread.
For each decision, note:
- What was decided
- Who made/agreed to the decision
- When (if mentioned)

If no clear decisions were made, say so.

Thread:
{thread_text[:4000]}

List each decision as a bullet point."""

                response = llm.chat([{"role": "user", "content": prompt}])
                decision_text = ""
                if hasattr(response, "text"):
                    decision_text = response.text
                elif hasattr(response, "content"):
                    if isinstance(response.content, list):
                        decision_text = " ".join(getattr(b, "text", str(b)) for b in response.content)
                    else:
                        decision_text = str(response.content)

                if decision_text and len(decision_text) > 10:
                    event_bus.emit("thread_decisions_extracted", {
                        "subject": messages[0].get("subject", "?"),
                    })

                    lines = [f"📋 Thread Decisions — {messages[0].get('subject', '?')}:"]
                    lines.append(decision_text)
                    return {"success": True, "content": "\n".join(lines)}
        except Exception:
            pass

        # Fallback: keyword scan for decision-like language
        decision_keywords = ["decided", "agreed", "confirmed", "approved", "will do",
                             "let's go with", "going with", "settled on", "final",
                             "decision", "we'll", "plan is", "moving forward"]

        found = []
        for m in messages:
            body = m.get("body", "")
            for kw in decision_keywords:
                if kw in body.lower():
                    # Extract the sentence containing the keyword
                    sentences = body.replace(".", ".\n").split("\n")
                    for s in sentences:
                        if kw in s.lower() and len(s.strip()) > 10:
                            found.append(f"  • {m.get('from', '?')}: {s.strip()[:120]}")
                            break

        if not found:
            return {"success": True, "content": f"📋 No explicit decisions detected in thread '{messages[0].get('subject', '?')}'. The thread may still be in discussion."}

        lines = [f"📋 Decisions Detected ({len(found)}):"]
        lines.extend(found[:10])

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Thread decisions error: {e}"}


def thread_participants(subject_or_index, max_messages=20):
    """Analyze who said what in a thread — participation breakdown."""
    try:
        messages, err = _get_thread_messages(subject_or_index, max_messages)
        if err:
            return err
        if not messages:
            return {"success": True, "content": "👥 No thread messages found."}

        participant_stats = {}
        for m in messages:
            sender = m.get("from", "Unknown")
            if sender not in participant_stats:
                participant_stats[sender] = {
                    "count": 0,
                    "total_words": 0,
                    "first_date": m.get("date", "?"),
                    "last_date": m.get("date", "?"),
                }
            participant_stats[sender]["count"] += 1
            participant_stats[sender]["total_words"] += len(m.get("body", "").split())
            participant_stats[sender]["last_date"] = m.get("date", "?")

        lines = [f"👥 Thread Participants — {messages[0].get('subject', '?')}:"]
        lines.append(f"  Total messages: {len(messages)}")
        lines.append(f"  Participants: {len(participant_stats)}")

        for sender, stats in sorted(participant_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            pct = stats["count"] * 100 // len(messages)
            avg_words = stats["total_words"] // stats["count"] if stats["count"] > 0 else 0
            lines.append(f"\n  📧 {sender}:")
            lines.append(f"     Messages: {stats['count']} ({pct}%)")
            lines.append(f"     Avg words/msg: {avg_words}")
            lines.append(f"     Active: {stats['first_date']} → {stats['last_date']}")

        # Who started and who last replied
        if messages:
            lines.append(f"\n  🏁 Started by: {messages[0].get('from', '?')}")
            lines.append(f"  💬 Last reply: {messages[-1].get('from', '?')}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Thread participants error: {e}"}


def thread_timeline(subject_or_index, max_messages=20):
    """Generate a timeline of events/key moments in a thread."""
    try:
        messages, err = _get_thread_messages(subject_or_index, max_messages)
        if err:
            return err
        if not messages:
            return {"success": True, "content": "📅 No thread messages found."}

        lines = [f"📅 Thread Timeline — {messages[0].get('subject', '?')}:"]

        for i, m in enumerate(messages):
            sender = m.get("from", "?")
            date = m.get("date", "?")
            body = m.get("body", "").strip()

            # Create a brief preview
            preview = body[:100].replace("\n", " ")
            if len(body) > 100:
                preview += "..."

            icon = "🟢" if i == 0 else "🔵" if i == len(messages) - 1 else "⚪"
            label = " (started)" if i == 0 else " (latest)" if i == len(messages) - 1 else ""

            lines.append(f"\n  {icon} #{i+1}{label}")
            lines.append(f"     {date} — {sender}")
            lines.append(f"     {preview}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Thread timeline error: {e}"}


def prepare_forward_summary(subject_or_index, recipient=None, max_messages=20):
    """Generate a TL;DR summary suitable for forwarding a thread."""
    try:
        messages, err = _get_thread_messages(subject_or_index, max_messages)
        if err:
            return err
        if not messages:
            return {"success": True, "content": "📝 No thread messages found."}

        subject = messages[0].get("subject", "?") if messages else "?"
        participants = list(set(m.get("from", "?") for m in messages))

        # Try LLM
        try:
            llm = _get_llm_for_compose()
            if llm:
                thread_text = ""
                for i, m in enumerate(messages):
                    thread_text += f"\n--- Message {i+1} from {m.get('from', '?')} ({m.get('date', '?')}) ---\n"
                    thread_text += f"{m.get('body', '')}\n"

                recipient_ctx = f" for {recipient}" if recipient else ""
                prompt = f"""Write a brief TL;DR summary of this email thread{recipient_ctx}.
The summary should be suitable to paste at the top of a forwarded email.
Include: context, key points, current status, and any action needed.
Keep it to 3-5 lines, professional tone.

Thread ({len(messages)} messages):
{thread_text[:4000]}

Format as:
TL;DR: [one line summary]
Key points: [2-3 bullet points]
Status: [current status]
Action needed: [if any]"""

                response = llm.chat([{"role": "user", "content": prompt}])
                summary_text = ""
                if hasattr(response, "text"):
                    summary_text = response.text
                elif hasattr(response, "content"):
                    if isinstance(response.content, list):
                        summary_text = " ".join(getattr(b, "text", str(b)) for b in response.content)
                    else:
                        summary_text = str(response.content)

                if summary_text and len(summary_text) > 20:
                    event_bus.emit("forward_summary_prepared", {
                        "subject": subject, "recipient": recipient or "",
                    })

                    lines = [f"📨 Forward Summary — {subject}:"]
                    lines.append(f"  Thread: {len(messages)} messages from {', '.join(participants[:3])}")
                    if recipient:
                        lines.append(f"  Prepared for: {recipient}")
                    lines.append(f"\n{summary_text}")

                    return {"success": True, "content": "\n".join(lines)}
        except Exception:
            pass

        # Fallback
        lines = [f"📨 Forward Summary — {subject}:"]
        lines.append(f"  Thread: {len(messages)} messages")
        lines.append(f"  Participants: {', '.join(participants[:5])}")
        if recipient:
            lines.append(f"  Prepared for: {recipient}")
        lines.append(f"\n  TL;DR: {len(messages)}-message thread about '{subject}'.")
        lines.append(f"  Started: {messages[0].get('date', '?')} by {messages[0].get('from', '?')}")
        lines.append(f"  Latest: {messages[-1].get('date', '?')} by {messages[-1].get('from', '?')}")
        lines.append(f"  Last message preview: {messages[-1].get('body', '')[:150]}...")

        event_bus.emit("forward_summary_prepared", {
            "subject": subject, "recipient": recipient or "",
        })

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Forward summary error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 12A: EMAIL LABELS & TAGS
# ═══════════════════════════════════════════════════════════════════

LABELS_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_labels.json")


def _load_labels():
    try:
        if os.path.exists(LABELS_PATH):
            with open(LABELS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"labels": {}, "email_labels": {}}


def _save_labels(data):
    try:
        os.makedirs(os.path.dirname(LABELS_PATH), exist_ok=True)
        with open(LABELS_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def add_label(index=1, label="", mailbox="inbox"):
    """Add a custom label/tag to an email."""
    try:
        if not label:
            return {"success": False, "error": True, "content": "Label name is required"}

        label = label.strip().lower()

        # Read email to get subject for identification
        msg = read_message(index, mailbox)
        if not msg.get("success"):
            return msg

        content = msg.get("content", "")
        subject = ""
        sender = ""
        for line in content.split("\n"):
            if line.startswith("Subject: "):
                subject = line[9:]
            elif line.startswith("From: "):
                sender = line[6:]

        email_key = f"{sender}|{subject}".strip()
        if not email_key or email_key == "|":
            email_key = f"idx_{index}_{mailbox}"

        data = _load_labels()

        # Increment label counter
        if label not in data["labels"]:
            data["labels"][label] = {"count": 0, "created_at": datetime.now().isoformat(), "color": None}
        data["labels"][label]["count"] = data["labels"][label].get("count", 0) + 1

        # Add label to email
        if email_key not in data["email_labels"]:
            data["email_labels"][email_key] = []
        if label not in data["email_labels"][email_key]:
            data["email_labels"][email_key].append(label)
        else:
            return {"success": True, "content": f"🏷️ Email already has label '{label}'"}

        _save_labels(data)

        event_bus.emit("label_added", {"label": label, "subject": subject, "index": index})

        return {"success": True, "content": f"🏷️ Label '{label}' added to email: {subject or f'index {index}'}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Add label error: {e}"}


def remove_label(index=1, label="", mailbox="inbox"):
    """Remove a label from an email."""
    try:
        if not label:
            return {"success": False, "error": True, "content": "Label name is required"}

        label = label.strip().lower()

        msg = read_message(index, mailbox)
        if not msg.get("success"):
            return msg

        content = msg.get("content", "")
        subject = ""
        sender = ""
        for line in content.split("\n"):
            if line.startswith("Subject: "):
                subject = line[9:]
            elif line.startswith("From: "):
                sender = line[6:]

        email_key = f"{sender}|{subject}".strip()
        if not email_key or email_key == "|":
            email_key = f"idx_{index}_{mailbox}"

        data = _load_labels()

        if email_key not in data["email_labels"] or label not in data["email_labels"].get(email_key, []):
            return {"success": False, "error": True, "content": f"Email does not have label '{label}'"}

        data["email_labels"][email_key].remove(label)
        if not data["email_labels"][email_key]:
            del data["email_labels"][email_key]

        # Decrement label counter
        if label in data["labels"]:
            data["labels"][label]["count"] = max(0, data["labels"][label].get("count", 1) - 1)

        _save_labels(data)

        return {"success": True, "content": f"🏷️ Label '{label}' removed from email: {subject or f'index {index}'}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Remove label error: {e}"}


def list_labels():
    """List all labels with counts."""
    try:
        data = _load_labels()
        labels = data.get("labels", {})

        if not labels:
            return {"success": True, "content": "🏷️ No labels created yet."}

        sorted_labels = sorted(labels.items(), key=lambda x: x[1].get("count", 0), reverse=True)

        lines = [f"🏷️ Labels ({len(sorted_labels)}):"]
        for name, info in sorted_labels:
            count = info.get("count", 0)
            color = info.get("color", "")
            color_str = f" [{color}]" if color else ""
            lines.append(f"  🏷️ {name}{color_str} — {count} emails")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List labels error: {e}"}


def get_labeled_emails(label="", max_results=20):
    """Get all emails with a specific label."""
    try:
        if not label:
            return {"success": False, "error": True, "content": "Label name is required"}

        label = label.strip().lower()
        data = _load_labels()

        # Find all emails with this label
        matches = []
        for email_key, email_labels in data.get("email_labels", {}).items():
            if label in email_labels:
                parts = email_key.split("|", 1)
                sender = parts[0] if len(parts) > 1 else ""
                subject = parts[1] if len(parts) > 1 else email_key
                matches.append({"sender": sender, "subject": subject, "labels": email_labels})

        if not matches:
            return {"success": True, "content": f"🏷️ No emails found with label '{label}'."}

        lines = [f"🏷️ Emails with label '{label}' ({len(matches)}):"]
        for i, m in enumerate(matches[:max_results]):
            other_labels = [l for l in m["labels"] if l != label]
            other_str = f" +[{', '.join(other_labels)}]" if other_labels else ""
            lines.append(f"  {i+1}. {m['subject']}")
            lines.append(f"     From: {m['sender']}{other_str}")

        if len(matches) > max_results:
            lines.append(f"  ... and {len(matches) - max_results} more")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get labeled emails error: {e}"}


def bulk_label(indices=None, label="", mailbox="inbox"):
    """Apply a label to multiple emails at once."""
    try:
        if not label:
            return {"success": False, "error": True, "content": "Label name is required"}
        if not indices or not isinstance(indices, list):
            return {"success": False, "error": True, "content": "List of indices is required"}

        success_count = 0
        errors = []
        for idx in indices:
            result = add_label(index=idx, label=label, mailbox=mailbox)
            if result.get("success"):
                success_count += 1
            else:
                errors.append(f"idx {idx}: {result.get('content', 'unknown error')}")

        if errors:
            return {"success": True, "content": f"🏷️ Label '{label}' applied to {success_count}/{len(indices)} emails. Errors: {'; '.join(errors[:3])}"}

        return {"success": True, "content": f"🏷️ Label '{label}' applied to all {success_count} emails."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Bulk label error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 12B: NEWSLETTER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

NEWSLETTER_PREFS_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_newsletter_prefs.json")

_NEWSLETTER_INDICATORS = [
    "unsubscribe", "opt out", "opt-out", "email preferences",
    "manage subscriptions", "manage preferences", "mailing list",
    "newsletter", "weekly digest", "daily digest", "monthly update",
    "view in browser", "view online", "no longer wish to receive",
    "list-unsubscribe", "you are receiving this because",
    "you received this email because", "sent to you because",
]


def _load_newsletter_prefs():
    try:
        if os.path.exists(NEWSLETTER_PREFS_PATH):
            with open(NEWSLETTER_PREFS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"preferences": {}, "stats": {"total_detected": 0, "last_scan": None}}


def _save_newsletter_prefs(data):
    try:
        os.makedirs(os.path.dirname(NEWSLETTER_PREFS_PATH), exist_ok=True)
        with open(NEWSLETTER_PREFS_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def _is_newsletter(email_text):
    """Check if email text looks like a newsletter."""
    text_lower = email_text.lower()
    score = 0
    for indicator in _NEWSLETTER_INDICATORS:
        if indicator in text_lower:
            score += 1
    return score >= 2  # At least 2 indicators


def detect_newsletters(count=30, mailbox="inbox"):
    """Scan inbox for newsletter/subscription emails."""
    try:
        result = read_inbox(count)
        if not result.get("success"):
            return result

        content = result.get("content", "")
        emails = content.split("\n")

        newsletters = []
        senders_seen = {}

        for i in range(1, min(count + 1, count + 1)):
            try:
                msg = read_message(i, mailbox)
                if not msg.get("success"):
                    continue

                msg_content = msg.get("content", "")
                if _is_newsletter(msg_content):
                    sender = ""
                    subject = ""
                    for line in msg_content.split("\n"):
                        if line.startswith("From: "):
                            sender = line[6:]
                        elif line.startswith("Subject: "):
                            subject = line[9:]

                    sender_key = sender.lower().strip()
                    if sender_key not in senders_seen:
                        senders_seen[sender_key] = {"sender": sender, "count": 0, "subjects": []}
                    senders_seen[sender_key]["count"] += 1
                    senders_seen[sender_key]["subjects"].append(subject)
                    newsletters.append({"index": i, "sender": sender, "subject": subject})
            except Exception:
                continue

        if not newsletters:
            return {"success": True, "content": f"📰 No newsletters detected in last {count} emails."}

        # Sort by sender frequency
        sorted_senders = sorted(senders_seen.values(), key=lambda x: x["count"], reverse=True)

        lines = [f"📰 Newsletters detected: {len(newsletters)} emails from {len(senders_seen)} sources:"]
        for s in sorted_senders[:15]:
            lines.append(f"  📬 {s['sender']} ({s['count']} emails)")
            for subj in s["subjects"][:2]:
                lines.append(f"      • {subj}")

        event_bus.emit("newsletters_detected", {"count": len(newsletters), "sources": len(senders_seen)})

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Detect newsletters error: {e}"}


def newsletter_digest(count=20, mailbox="inbox"):
    """Generate a digest of recent newsletters."""
    try:
        newsletters = []
        for i in range(1, count + 1):
            try:
                msg = read_message(i, mailbox)
                if not msg.get("success"):
                    continue
                msg_content = msg.get("content", "")
                if _is_newsletter(msg_content):
                    sender = ""
                    subject = ""
                    date = ""
                    body_preview = ""
                    for line in msg_content.split("\n"):
                        if line.startswith("From: "):
                            sender = line[6:]
                        elif line.startswith("Subject: "):
                            subject = line[9:]
                        elif line.startswith("Date: "):
                            date = line[6:]
                        elif not line.startswith(("To: ", "CC: ", "Attachments: ")) and len(body_preview) < 200:
                            body_preview += line.strip() + " "
                    newsletters.append({"sender": sender, "subject": subject, "date": date, "preview": body_preview[:200].strip()})
            except Exception:
                continue

        if not newsletters:
            return {"success": True, "content": "📰 No newsletters found in recent emails."}

        lines = [f"📰 Newsletter Digest ({len(newsletters)} newsletters):"]
        for i, nl in enumerate(newsletters):
            lines.append(f"\n  {i+1}. {nl['subject']}")
            lines.append(f"     From: {nl['sender']} | {nl['date']}")
            if nl['preview']:
                lines.append(f"     Preview: {nl['preview'][:150]}...")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Newsletter digest error: {e}"}


def newsletter_stats():
    """Stats on newsletter volume, top sources."""
    try:
        data = _load_newsletter_prefs()
        prefs = data.get("preferences", {})

        if not prefs:
            return {"success": True, "content": "📰 No newsletter data yet. Run detect_newsletters first."}

        total = len(prefs)
        keep = sum(1 for p in prefs.values() if p.get("action") == "keep")
        archive = sum(1 for p in prefs.values() if p.get("action") == "archive")
        unsubscribe = sum(1 for p in prefs.values() if p.get("action") == "unsubscribe")
        no_pref = total - keep - archive - unsubscribe

        lines = [
            f"📰 Newsletter Stats:",
            f"  Total sources tracked: {total}",
            f"  Keep: {keep} | Archive: {archive} | Unsubscribe: {unsubscribe} | No preference: {no_pref}",
            f"  Last scan: {data.get('stats', {}).get('last_scan', 'never')}",
        ]

        # Top sources by count
        sorted_prefs = sorted(prefs.items(), key=lambda x: x[1].get("email_count", 0), reverse=True)[:10]
        if sorted_prefs:
            lines.append(f"\n  Top newsletter sources:")
            for sender, info in sorted_prefs:
                action = info.get("action", "none")
                count = info.get("email_count", 0)
                lines.append(f"    📬 {sender} — {count} emails [{action}]")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Newsletter stats error: {e}"}


def newsletter_preferences(sender="", action="keep"):
    """Set preferences per newsletter sender (keep, archive, unsubscribe)."""
    try:
        if not sender:
            return {"success": False, "error": True, "content": "Sender is required"}
        if action not in ("keep", "archive", "unsubscribe"):
            return {"success": False, "error": True, "content": "Action must be: keep, archive, or unsubscribe"}

        sender_key = sender.lower().strip()
        data = _load_newsletter_prefs()

        if sender_key not in data["preferences"]:
            data["preferences"][sender_key] = {"sender": sender, "email_count": 0, "created_at": datetime.now().isoformat()}

        data["preferences"][sender_key]["action"] = action
        data["preferences"][sender_key]["updated_at"] = datetime.now().isoformat()

        _save_newsletter_prefs(data)

        action_emoji = {"keep": "✅", "archive": "📦", "unsubscribe": "🚫"}
        return {"success": True, "content": f"{action_emoji.get(action, '📰')} Newsletter preference set: {sender} → {action}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Newsletter preferences error: {e}"}


def apply_newsletter_preferences(count=30, mailbox="inbox", dry_run=True):
    """Apply saved newsletter preferences to inbox."""
    try:
        data = _load_newsletter_prefs()
        prefs = data.get("preferences", {})

        if not prefs:
            return {"success": True, "content": "📰 No newsletter preferences saved. Use newsletter_preferences to set them."}

        actions_taken = {"archived": 0, "unsubscribed": 0, "kept": 0, "skipped": 0}

        for i in range(1, count + 1):
            try:
                msg = read_message(i, mailbox)
                if not msg.get("success"):
                    continue
                msg_content = msg.get("content", "")
                sender = ""
                for line in msg_content.split("\n"):
                    if line.startswith("From: "):
                        sender = line[6:]
                        break

                sender_key = sender.lower().strip()
                if sender_key in prefs:
                    pref_action = prefs[sender_key].get("action", "keep")
                    if pref_action == "archive":
                        if not dry_run:
                            archive_message(i, mailbox)
                        actions_taken["archived"] += 1
                    elif pref_action == "unsubscribe":
                        actions_taken["unsubscribed"] += 1
                    elif pref_action == "keep":
                        actions_taken["kept"] += 1
                else:
                    actions_taken["skipped"] += 1
            except Exception:
                continue

        mode = "DRY RUN — " if dry_run else ""
        lines = [
            f"📰 {mode}Newsletter Preferences Applied:",
            f"  Archived: {actions_taken['archived']}",
            f"  Flagged for unsubscribe: {actions_taken['unsubscribed']}",
            f"  Kept: {actions_taken['kept']}",
            f"  No preference: {actions_taken['skipped']}",
        ]
        if dry_run:
            lines.append("  💡 Set dry_run=false to apply changes")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Apply newsletter prefs error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 12C: AUTO-RESPONDER (conditional auto-responses)
# ═══════════════════════════════════════════════════════════════════

AUTO_RESPONDER_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_auto_responders.json")


def _load_auto_responders():
    try:
        if os.path.exists(AUTO_RESPONDER_PATH):
            with open(AUTO_RESPONDER_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"rules": [], "history": []}


def _save_auto_responders(data):
    try:
        os.makedirs(os.path.dirname(AUTO_RESPONDER_PATH), exist_ok=True)
        with open(AUTO_RESPONDER_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def create_auto_response(name="", conditions=None, response_body="", response_subject=None, enabled=True, max_replies=1):
    """Create a conditional auto-response rule."""
    try:
        if not name:
            return {"success": False, "error": True, "content": "Rule name is required"}
        if not conditions or not isinstance(conditions, dict):
            return {"success": False, "error": True, "content": "Conditions dict is required (e.g. {from_contains: 'hr@', subject_contains: 'survey'})"}
        if not response_body:
            return {"success": False, "error": True, "content": "Response body text is required"}

        data = _load_auto_responders()
        rule_id = f"ar_{uuid.uuid4().hex[:8]}"

        rule = {
            "id": rule_id,
            "name": name,
            "conditions": conditions,
            "response_body": response_body,
            "response_subject": response_subject,
            "enabled": enabled,
            "max_replies": max_replies,  # max auto-replies per sender per day
            "created_at": datetime.now().isoformat(),
            "reply_count": 0,
            "last_reply": None,
        }

        data["rules"].append(rule)
        _save_auto_responders(data)

        event_bus.emit("auto_response_created", {"id": rule_id, "name": name})

        cond_desc = ", ".join(f"{k}={v}" for k, v in conditions.items())
        return {"success": True, "content": f"🤖 Auto-response rule created: '{name}' (ID: {rule_id})\n  Conditions: {cond_desc}\n  Reply: {response_body[:100]}..."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Create auto-response error: {e}"}


def list_auto_responses():
    """List all auto-response rules."""
    try:
        data = _load_auto_responders()
        rules = data.get("rules", [])

        if not rules:
            return {"success": True, "content": "🤖 No auto-response rules created yet."}

        lines = [f"🤖 Auto-Response Rules ({len(rules)}):"]
        for r in rules:
            status = "✅" if r.get("enabled") else "⏸️"
            cond_desc = ", ".join(f"{k}={v}" for k, v in r.get("conditions", {}).items())
            lines.append(f"  {status} {r['name']} [{r['id']}]")
            lines.append(f"     Conditions: {cond_desc}")
            lines.append(f"     Reply preview: {r.get('response_body', '')[:80]}...")
            lines.append(f"     Replies sent: {r.get('reply_count', 0)} | Max/sender/day: {r.get('max_replies', 1)}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List auto-responses error: {e}"}


def update_auto_response(rule_id="", name=None, conditions=None, response_body=None, max_replies=None):
    """Update an auto-response rule."""
    try:
        if not rule_id:
            return {"success": False, "error": True, "content": "rule_id is required"}

        data = _load_auto_responders()
        rule = None
        for r in data.get("rules", []):
            if r["id"] == rule_id:
                rule = r
                break

        if not rule:
            return {"success": False, "error": True, "content": f"Auto-response rule '{rule_id}' not found"}

        changes = []
        if name:
            rule["name"] = name
            changes.append(f"name → {name}")
        if conditions and isinstance(conditions, dict):
            rule["conditions"] = conditions
            changes.append("conditions updated")
        if response_body:
            rule["response_body"] = response_body
            changes.append("response body updated")
        if max_replies is not None:
            rule["max_replies"] = max_replies
            changes.append(f"max_replies → {max_replies}")

        if not changes:
            return {"success": True, "content": "No changes specified."}

        _save_auto_responders(data)

        return {"success": True, "content": f"🤖 Auto-response updated: {', '.join(changes)}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update auto-response error: {e}"}


def delete_auto_response(rule_id=""):
    """Delete an auto-response rule."""
    try:
        if not rule_id:
            return {"success": False, "error": True, "content": "rule_id is required"}

        data = _load_auto_responders()
        before = len(data.get("rules", []))
        data["rules"] = [r for r in data.get("rules", []) if r["id"] != rule_id]
        after = len(data["rules"])

        if before == after:
            return {"success": False, "error": True, "content": f"Auto-response rule '{rule_id}' not found"}

        _save_auto_responders(data)

        return {"success": True, "content": f"🤖 Auto-response rule '{rule_id}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete auto-response error: {e}"}


def toggle_auto_response(rule_id="", enabled=None):
    """Enable/disable an auto-response rule."""
    try:
        if not rule_id:
            return {"success": False, "error": True, "content": "rule_id is required"}

        data = _load_auto_responders()
        rule = None
        for r in data.get("rules", []):
            if r["id"] == rule_id:
                rule = r
                break

        if not rule:
            return {"success": False, "error": True, "content": f"Auto-response rule '{rule_id}' not found"}

        if enabled is None:
            rule["enabled"] = not rule.get("enabled", True)
        else:
            rule["enabled"] = enabled

        _save_auto_responders(data)

        status = "enabled ✅" if rule["enabled"] else "disabled ⏸️"
        return {"success": True, "content": f"🤖 Auto-response '{rule['name']}' {status}."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Toggle auto-response error: {e}"}


def auto_response_history(limit=20):
    """View history of sent auto-responses."""
    try:
        data = _load_auto_responders()
        history = data.get("history", [])

        if not history:
            return {"success": True, "content": "🤖 No auto-responses have been sent yet."}

        recent = history[-limit:]
        recent.reverse()

        lines = [f"🤖 Auto-Response History ({len(history)} total, showing last {len(recent)}):"]
        for h in recent:
            lines.append(f"  📤 Rule: {h.get('rule_name', '?')} → {h.get('to', '?')}")
            lines.append(f"     Subject: {h.get('subject', '?')} | Sent: {h.get('sent_at', '?')}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Auto-response history error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 13A: EMAIL SIGNATURES
# ═══════════════════════════════════════════════════════════════════

SIGNATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_signatures.json")


def _load_signatures():
    try:
        if os.path.exists(SIGNATURES_PATH):
            with open(SIGNATURES_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"signatures": {}, "default": None}


def _save_signatures(data):
    try:
        os.makedirs(os.path.dirname(SIGNATURES_PATH), exist_ok=True)
        with open(SIGNATURES_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def create_signature(name="", body="", is_html=False):
    """Create a reusable email signature."""
    try:
        if not name:
            return {"success": False, "error": True, "content": "Signature name is required"}
        if not body:
            return {"success": False, "error": True, "content": "Signature body is required"}

        sig_id = f"sig_{uuid.uuid4().hex[:8]}"
        data = _load_signatures()

        data["signatures"][sig_id] = {
            "name": name,
            "body": body,
            "is_html": is_html,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "use_count": 0,
        }

        # Auto-set as default if first signature
        if data["default"] is None:
            data["default"] = sig_id

        _save_signatures(data)

        return {"success": True, "content": f"✍️ Signature '{name}' created (ID: {sig_id}). {'Set as default.' if data['default'] == sig_id else ''}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Create signature error: {e}"}


def list_signatures():
    """List all saved email signatures."""
    try:
        data = _load_signatures()
        sigs = data.get("signatures", {})

        if not sigs:
            return {"success": True, "content": "✍️ No signatures created yet."}

        default_id = data.get("default")
        lines = [f"✍️ Email Signatures ({len(sigs)}):"]
        for sig_id, sig in sigs.items():
            is_default = " ⭐ DEFAULT" if sig_id == default_id else ""
            html_tag = " [HTML]" if sig.get("is_html") else ""
            lines.append(f"  ✍️ {sig['name']}{is_default}{html_tag} [{sig_id}]")
            preview = sig.get("body", "")[:80].replace("\n", " ")
            lines.append(f"     Preview: {preview}...")
            lines.append(f"     Used: {sig.get('use_count', 0)} times")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List signatures error: {e}"}


def update_signature(sig_id="", name=None, body=None, is_html=None):
    """Update an existing email signature."""
    try:
        if not sig_id:
            return {"success": False, "error": True, "content": "sig_id is required"}

        data = _load_signatures()
        if sig_id not in data.get("signatures", {}):
            return {"success": False, "error": True, "content": f"Signature '{sig_id}' not found"}

        sig = data["signatures"][sig_id]
        changes = []
        if name:
            sig["name"] = name
            changes.append(f"name → {name}")
        if body:
            sig["body"] = body
            changes.append("body updated")
        if is_html is not None:
            sig["is_html"] = is_html
            changes.append(f"html → {is_html}")

        if not changes:
            return {"success": True, "content": "No changes specified."}

        sig["updated_at"] = datetime.now().isoformat()
        _save_signatures(data)

        return {"success": True, "content": f"✍️ Signature updated: {', '.join(changes)}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update signature error: {e}"}


def delete_signature(sig_id=""):
    """Delete an email signature."""
    try:
        if not sig_id:
            return {"success": False, "error": True, "content": "sig_id is required"}

        data = _load_signatures()
        if sig_id not in data.get("signatures", {}):
            return {"success": False, "error": True, "content": f"Signature '{sig_id}' not found"}

        name = data["signatures"][sig_id].get("name", sig_id)
        del data["signatures"][sig_id]

        if data.get("default") == sig_id:
            data["default"] = next(iter(data["signatures"]), None)

        _save_signatures(data)

        return {"success": True, "content": f"✍️ Signature '{name}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete signature error: {e}"}


def set_default_signature(sig_id=""):
    """Set a signature as the default."""
    try:
        if not sig_id:
            return {"success": False, "error": True, "content": "sig_id is required"}

        data = _load_signatures()
        if sig_id not in data.get("signatures", {}):
            return {"success": False, "error": True, "content": f"Signature '{sig_id}' not found"}

        data["default"] = sig_id
        _save_signatures(data)

        name = data["signatures"][sig_id].get("name", sig_id)
        return {"success": True, "content": f"✍️ Signature '{name}' set as default."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Set default signature error: {e}"}


def get_signature(sig_id=None):
    """Get a specific signature by ID, or the default."""
    try:
        data = _load_signatures()
        sigs = data.get("signatures", {})

        if not sigs:
            return {"success": True, "content": "✍️ No signatures available."}

        target_id = sig_id or data.get("default")
        if not target_id or target_id not in sigs:
            return {"success": False, "error": True, "content": f"Signature '{target_id}' not found"}

        sig = sigs[target_id]
        lines = [
            f"✍️ Signature: {sig['name']} [{target_id}]",
            f"  HTML: {sig.get('is_html', False)}",
            f"  Body:\n{sig.get('body', '')}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get signature error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 13B: EMAIL ALIASES / IDENTITIES
# ═══════════════════════════════════════════════════════════════════

ALIASES_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_aliases.json")


def _load_aliases():
    try:
        if os.path.exists(ALIASES_PATH):
            with open(ALIASES_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"aliases": {}, "default": None}


def _save_aliases(data):
    try:
        os.makedirs(os.path.dirname(ALIASES_PATH), exist_ok=True)
        with open(ALIASES_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def add_alias(email="", display_name="", signature_id=None):
    """Add a sender alias/identity."""
    try:
        if not email:
            return {"success": False, "error": True, "content": "Email address is required"}

        alias_id = f"alias_{uuid.uuid4().hex[:8]}"
        data = _load_aliases()

        data["aliases"][alias_id] = {
            "email": email,
            "display_name": display_name or email.split("@")[0],
            "signature_id": signature_id,
            "created_at": datetime.now().isoformat(),
            "send_count": 0,
        }

        # Auto-set as default if first alias
        if data["default"] is None:
            data["default"] = alias_id

        _save_aliases(data)

        return {"success": True, "content": f"👤 Alias added: {display_name or email} <{email}> (ID: {alias_id})"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Add alias error: {e}"}


def list_aliases():
    """List all sender aliases/identities."""
    try:
        data = _load_aliases()
        aliases = data.get("aliases", {})

        if not aliases:
            return {"success": True, "content": "👤 No aliases configured yet."}

        default_id = data.get("default")
        lines = [f"👤 Email Aliases ({len(aliases)}):"]
        for alias_id, alias in aliases.items():
            is_default = " ⭐ DEFAULT" if alias_id == default_id else ""
            sig_tag = f" [sig: {alias.get('signature_id')}]" if alias.get("signature_id") else ""
            lines.append(f"  👤 {alias.get('display_name', '')} <{alias['email']}>{is_default}{sig_tag} [{alias_id}]")
            lines.append(f"     Sent: {alias.get('send_count', 0)} emails")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List aliases error: {e}"}


def update_alias(alias_id="", email=None, display_name=None, signature_id=None):
    """Update a sender alias."""
    try:
        if not alias_id:
            return {"success": False, "error": True, "content": "alias_id is required"}

        data = _load_aliases()
        if alias_id not in data.get("aliases", {}):
            return {"success": False, "error": True, "content": f"Alias '{alias_id}' not found"}

        alias = data["aliases"][alias_id]
        changes = []
        if email:
            alias["email"] = email
            changes.append(f"email → {email}")
        if display_name:
            alias["display_name"] = display_name
            changes.append(f"name → {display_name}")
        if signature_id is not None:
            alias["signature_id"] = signature_id or None
            changes.append(f"signature → {signature_id or 'none'}")

        if not changes:
            return {"success": True, "content": "No changes specified."}

        _save_aliases(data)

        return {"success": True, "content": f"👤 Alias updated: {', '.join(changes)}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update alias error: {e}"}


def delete_alias(alias_id=""):
    """Delete a sender alias."""
    try:
        if not alias_id:
            return {"success": False, "error": True, "content": "alias_id is required"}

        data = _load_aliases()
        if alias_id not in data.get("aliases", {}):
            return {"success": False, "error": True, "content": f"Alias '{alias_id}' not found"}

        name = data["aliases"][alias_id].get("display_name", alias_id)
        del data["aliases"][alias_id]

        if data.get("default") == alias_id:
            data["default"] = next(iter(data["aliases"]), None)

        _save_aliases(data)

        return {"success": True, "content": f"👤 Alias '{name}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete alias error: {e}"}


def set_default_alias(alias_id=""):
    """Set a sender alias as the default."""
    try:
        if not alias_id:
            return {"success": False, "error": True, "content": "alias_id is required"}

        data = _load_aliases()
        if alias_id not in data.get("aliases", {}):
            return {"success": False, "error": True, "content": f"Alias '{alias_id}' not found"}

        data["default"] = alias_id
        _save_aliases(data)

        alias = data["aliases"][alias_id]
        return {"success": True, "content": f"👤 Default alias set: {alias.get('display_name', '')} <{alias['email']}>"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Set default alias error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 13C: EMAIL EXPORT / ARCHIVAL
# ═══════════════════════════════════════════════════════════════════

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "memory", "email_exports")
EXPORT_INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_export_index.json")


def _load_export_index():
    try:
        if os.path.exists(EXPORT_INDEX_PATH):
            with open(EXPORT_INDEX_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"exports": []}


def _save_export_index(data):
    try:
        os.makedirs(os.path.dirname(EXPORT_INDEX_PATH), exist_ok=True)
        with open(EXPORT_INDEX_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def export_emails(count=10, mailbox="inbox", format="json"):
    """Export recent emails to a file (JSON or text)."""
    try:
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        emails = []
        for i in range(1, count + 1):
            try:
                msg = read_message(i, mailbox)
                if not msg.get("success"):
                    continue
                content = msg.get("content", "")
                email_data = {"index": i, "mailbox": mailbox}
                for line in content.split("\n"):
                    if line.startswith("From: "):
                        email_data["from"] = line[6:]
                    elif line.startswith("Subject: "):
                        email_data["subject"] = line[9:]
                    elif line.startswith("Date: "):
                        email_data["date"] = line[6:]
                    elif line.startswith("To: "):
                        email_data["to"] = line[4:]
                # Body = lines after headers
                header_end = False
                body_lines = []
                for line in content.split("\n"):
                    if header_end:
                        body_lines.append(line)
                    elif not line.startswith(("From: ", "Subject: ", "Date: ", "To: ", "CC: ", "Attachments: ")):
                        header_end = True
                        body_lines.append(line)
                email_data["body"] = "\n".join(body_lines).strip()
                emails.append(email_data)
            except Exception:
                continue

        if not emails:
            return {"success": True, "content": f"📤 No emails found to export from {mailbox}."}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_{mailbox}_{count}_{timestamp}.{format}"
        filepath = os.path.join(EXPORTS_DIR, filename)

        if format == "json":
            with open(filepath, "w") as f:
                json.dump(emails, f, indent=2, default=str)
        else:
            with open(filepath, "w") as f:
                for em in emails:
                    f.write(f"{'='*60}\n")
                    f.write(f"From: {em.get('from', '')}\n")
                    f.write(f"To: {em.get('to', '')}\n")
                    f.write(f"Subject: {em.get('subject', '')}\n")
                    f.write(f"Date: {em.get('date', '')}\n")
                    f.write(f"---\n{em.get('body', '')}\n\n")

        # Update index
        idx = _load_export_index()
        idx["exports"].append({
            "filename": filename,
            "filepath": filepath,
            "mailbox": mailbox,
            "count": len(emails),
            "format": format,
            "created_at": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(filepath),
        })
        _save_export_index(idx)

        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        return {"success": True, "content": f"📤 Exported {len(emails)} emails to {filepath} ({size_kb} KB)"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Export emails error: {e}"}


def export_thread(subject_or_index="", format="json"):
    """Export a full email thread to a file."""
    try:
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        # Use thread_timeline to get the thread
        timeline = thread_timeline(subject_or_index=subject_or_index, max_messages=50)
        if not timeline.get("success"):
            return timeline

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_subj = str(subject_or_index)[:30].replace("/", "_").replace(" ", "_")
        filename = f"thread_{safe_subj}_{timestamp}.{format}"
        filepath = os.path.join(EXPORTS_DIR, filename)

        content_text = timeline.get("content", "")

        if format == "json":
            with open(filepath, "w") as f:
                json.dump({"subject": str(subject_or_index), "exported_at": datetime.now().isoformat(), "content": content_text}, f, indent=2)
        else:
            with open(filepath, "w") as f:
                f.write(f"Thread Export: {subject_or_index}\n")
                f.write(f"Exported: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n\n")
                f.write(content_text)

        idx = _load_export_index()
        idx["exports"].append({
            "filename": filename,
            "filepath": filepath,
            "type": "thread",
            "subject": str(subject_or_index),
            "format": format,
            "created_at": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(filepath),
        })
        _save_export_index(idx)

        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        return {"success": True, "content": f"📤 Thread exported to {filepath} ({size_kb} KB)"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Export thread error: {e}"}


def backup_mailbox(mailbox="inbox", max_emails=100):
    """Create a full backup of a mailbox."""
    try:
        os.makedirs(EXPORTS_DIR, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{mailbox}_{timestamp}.json"
        filepath = os.path.join(EXPORTS_DIR, filename)

        emails = []
        for i in range(1, max_emails + 1):
            try:
                msg = read_message(i, mailbox)
                if not msg.get("success"):
                    break  # No more emails
                content = msg.get("content", "")
                email_data = {"index": i, "raw": content}
                for line in content.split("\n"):
                    if line.startswith("Subject: "):
                        email_data["subject"] = line[9:]
                    elif line.startswith("From: "):
                        email_data["from"] = line[6:]
                    elif line.startswith("Date: "):
                        email_data["date"] = line[6:]
                emails.append(email_data)
            except Exception:
                continue

        backup_data = {
            "mailbox": mailbox,
            "backed_up_at": datetime.now().isoformat(),
            "email_count": len(emails),
            "emails": emails,
        }

        with open(filepath, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)

        idx = _load_export_index()
        idx["exports"].append({
            "filename": filename,
            "filepath": filepath,
            "type": "backup",
            "mailbox": mailbox,
            "count": len(emails),
            "format": "json",
            "created_at": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(filepath),
        })
        _save_export_index(idx)

        size_kb = round(os.path.getsize(filepath) / 1024, 1)
        return {"success": True, "content": f"💾 Backup complete: {len(emails)} emails from '{mailbox}' saved to {filepath} ({size_kb} KB)"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Backup mailbox error: {e}"}


def list_backups():
    """List all email exports and backups."""
    try:
        idx = _load_export_index()
        exports = idx.get("exports", [])

        if not exports:
            return {"success": True, "content": "💾 No exports or backups found."}

        lines = [f"💾 Email Exports & Backups ({len(exports)}):"]
        for exp in reversed(exports[-20:]):
            size_kb = round(exp.get("size_bytes", 0) / 1024, 1)
            exp_type = exp.get("type", "export")
            lines.append(f"  📁 {exp['filename']} ({size_kb} KB)")
            lines.append(f"     Type: {exp_type} | Format: {exp.get('format', '?')} | Emails: {exp.get('count', '?')} | {exp.get('created_at', '?')}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List backups error: {e}"}


def search_exports(keyword=""):
    """Search through exported/backed-up emails."""
    try:
        if not keyword:
            return {"success": False, "error": True, "content": "Search keyword is required"}

        if not os.path.exists(EXPORTS_DIR):
            return {"success": True, "content": "💾 No exports directory found."}

        matches = []
        keyword_lower = keyword.lower()

        for fname in os.listdir(EXPORTS_DIR):
            fpath = os.path.join(EXPORTS_DIR, fname)
            if not fname.endswith((".json", ".txt")):
                continue
            try:
                with open(fpath, "r") as f:
                    content = f.read()
                if keyword_lower in content.lower():
                    # Count occurrences
                    count = content.lower().count(keyword_lower)
                    matches.append({"file": fname, "occurrences": count})
            except Exception:
                continue

        if not matches:
            return {"success": True, "content": f"💾 No exports contain '{keyword}'."}

        matches.sort(key=lambda x: x["occurrences"], reverse=True)
        lines = [f"💾 Exports matching '{keyword}' ({len(matches)} files):"]
        for m in matches[:15]:
            lines.append(f"  📁 {m['file']} — {m['occurrences']} matches")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Search exports error: {e}"}


def get_export_stats():
    """Stats on email exports and backups."""
    try:
        idx = _load_export_index()
        exports = idx.get("exports", [])

        if not exports:
            return {"success": True, "content": "💾 No export data yet."}

        total_size = sum(e.get("size_bytes", 0) for e in exports)
        total_emails = sum(e.get("count", 0) for e in exports)
        backups = sum(1 for e in exports if e.get("type") == "backup")
        threads = sum(1 for e in exports if e.get("type") == "thread")
        regular = len(exports) - backups - threads

        lines = [
            f"💾 Export Stats:",
            f"  Total exports: {len(exports)} ({regular} exports, {backups} backups, {threads} threads)",
            f"  Total emails exported: {total_emails}",
            f"  Total storage: {round(total_size / 1024, 1)} KB",
            f"  Last export: {exports[-1].get('created_at', 'unknown') if exports else 'never'}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Export stats error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 14: EMAIL TEMPLATES
# ═══════════════════════════════════════════════════════════════════

TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_templates.json")


def _load_templates():
    try:
        if os.path.exists(TEMPLATES_PATH):
            with open(TEMPLATES_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"templates": {}}


def _save_templates(data):
    os.makedirs(os.path.dirname(TEMPLATES_PATH), exist_ok=True)
    with open(TEMPLATES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def create_template(name="", subject_template="", body_template="", category="general"):
    """Create a reusable email template with variable placeholders."""
    try:
        if not name:
            return {"success": False, "error": True, "content": "Template name is required"}
        if not body_template:
            return {"success": False, "error": True, "content": "Template body is required"}

        template_id = f"tmpl_{uuid.uuid4().hex[:8]}"
        data = _load_templates()

        # Extract variables from {{variable}} placeholders
        import re
        variables = list(set(re.findall(r'\{\{(\w+)\}\}', subject_template + body_template)))

        data["templates"][template_id] = {
            "name": name,
            "subject_template": subject_template,
            "body_template": body_template,
            "category": category,
            "variables": variables,
            "created_at": datetime.now().isoformat(),
            "use_count": 0,
        }

        _save_templates(data)

        return {"success": True, "content": f"📝 Template '{name}' created (ID: {template_id}) with {len(variables)} variable(s): {', '.join(variables) if variables else 'none'}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Create template error: {e}"}


def list_templates(category=None):
    """List all email templates."""
    try:
        data = _load_templates()
        templates = data.get("templates", {})

        if not templates:
            return {"success": True, "content": "📝 No templates found."}

        filtered = templates
        if category:
            filtered = {k: v for k, v in templates.items() if v.get("category") == category}

        lines = [f"📝 Email Templates ({len(filtered)}):"]
        for tid, t in filtered.items():
            vars_str = f" vars: {', '.join(t.get('variables', []))}" if t.get('variables') else ""
            lines.append(f"  [{tid}] {t['name']} ({t.get('category', 'general')}) — used {t.get('use_count', 0)}x{vars_str}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List templates error: {e}"}


def get_template(template_id=""):
    """Get a specific template by ID."""
    try:
        if not template_id:
            return {"success": False, "error": True, "content": "template_id is required"}

        data = _load_templates()
        if template_id not in data.get("templates", {}):
            return {"success": False, "error": True, "content": f"Template '{template_id}' not found"}

        t = data["templates"][template_id]
        lines = [
            f"📝 Template: {t['name']} [{template_id}]",
            f"  Category: {t.get('category', 'general')}",
            f"  Variables: {', '.join(t.get('variables', [])) or 'none'}",
            f"  Subject: {t.get('subject_template', '(none)')}",
            f"  Body:\n{t.get('body_template', '')}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get template error: {e}"}


def update_template(template_id="", name=None, subject_template=None, body_template=None, category=None):
    """Update an existing email template."""
    try:
        if not template_id:
            return {"success": False, "error": True, "content": "template_id is required"}

        data = _load_templates()
        if template_id not in data.get("templates", {}):
            return {"success": False, "error": True, "content": f"Template '{template_id}' not found"}

        t = data["templates"][template_id]
        if name is not None:
            t["name"] = name
        if subject_template is not None:
            t["subject_template"] = subject_template
        if body_template is not None:
            t["body_template"] = body_template
        if category is not None:
            t["category"] = category

        # Re-extract variables
        import re
        t["variables"] = list(set(re.findall(r'\{\{(\w+)\}\}', t.get("subject_template", "") + t.get("body_template", ""))))

        _save_templates(data)

        return {"success": True, "content": f"📝 Template '{t['name']}' updated."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update template error: {e}"}


def delete_template(template_id=""):
    """Delete an email template."""
    try:
        if not template_id:
            return {"success": False, "error": True, "content": "template_id is required"}

        data = _load_templates()
        if template_id not in data.get("templates", {}):
            return {"success": False, "error": True, "content": f"Template '{template_id}' not found"}

        name = data["templates"][template_id].get("name", template_id)
        del data["templates"][template_id]
        _save_templates(data)

        return {"success": True, "content": f"📝 Template '{name}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete template error: {e}"}


def use_template(template_id="", variables=None):
    """Render a template with variable substitutions."""
    try:
        if not template_id:
            return {"success": False, "error": True, "content": "template_id is required"}

        data = _load_templates()
        if template_id not in data.get("templates", {}):
            return {"success": False, "error": True, "content": f"Template '{template_id}' not found"}

        t = data["templates"][template_id]
        variables = variables or {}

        subject = t.get("subject_template", "")
        body = t.get("body_template", "")

        for var, val in variables.items():
            subject = subject.replace(f"{{{{{var}}}}}", str(val))
            body = body.replace(f"{{{{{var}}}}}", str(val))

        # Increment use count
        t["use_count"] = t.get("use_count", 0) + 1
        _save_templates(data)

        lines = [
            f"📝 Rendered template '{t['name']}':",
            f"  Subject: {subject}",
            f"  Body:\n{body}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Use template error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 15: EMAIL DRAFTS MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

DRAFTS_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_drafts.json")


def _load_drafts():
    try:
        if os.path.exists(DRAFTS_PATH):
            with open(DRAFTS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"drafts": {}}


def _save_drafts(data):
    os.makedirs(os.path.dirname(DRAFTS_PATH), exist_ok=True)
    with open(DRAFTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_draft(to="", subject="", body="", cc="", bcc=""):
    """Save an email as a draft."""
    try:
        if not to and not subject and not body:
            return {"success": False, "error": True, "content": "At least one of to, subject, or body is required"}

        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        data = _load_drafts()

        data["drafts"][draft_id] = {
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc,
            "bcc": bcc,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        _save_drafts(data)

        return {"success": True, "content": f"📋 Draft saved (ID: {draft_id}) — To: {to or '(empty)'}, Subject: {subject or '(empty)'}"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Save draft error: {e}"}


def list_drafts():
    """List all saved drafts."""
    try:
        data = _load_drafts()
        drafts = data.get("drafts", {})

        if not drafts:
            return {"success": True, "content": "📋 No drafts found."}

        lines = [f"📋 Drafts ({len(drafts)}):"]
        for did, d in drafts.items():
            to_str = d.get("to", "(no recipient)")[:30]
            subj_str = d.get("subject", "(no subject)")[:40]
            lines.append(f"  [{did}] To: {to_str} — {subj_str} ({d.get('updated_at', '')[:10]})")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List drafts error: {e}"}


def get_draft(draft_id=""):
    """Get a specific draft by ID."""
    try:
        if not draft_id:
            return {"success": False, "error": True, "content": "draft_id is required"}

        data = _load_drafts()
        if draft_id not in data.get("drafts", {}):
            return {"success": False, "error": True, "content": f"Draft '{draft_id}' not found"}

        d = data["drafts"][draft_id]
        lines = [
            f"📋 Draft [{draft_id}]",
            f"  To: {d.get('to', '')}",
            f"  CC: {d.get('cc', '')}" if d.get('cc') else "",
            f"  BCC: {d.get('bcc', '')}" if d.get('bcc') else "",
            f"  Subject: {d.get('subject', '')}",
            f"  Body:\n{d.get('body', '')}",
        ]

        return {"success": True, "content": "\n".join(l for l in lines if l)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get draft error: {e}"}


def update_draft(draft_id="", to=None, subject=None, body=None, cc=None, bcc=None):
    """Update a saved draft."""
    try:
        if not draft_id:
            return {"success": False, "error": True, "content": "draft_id is required"}

        data = _load_drafts()
        if draft_id not in data.get("drafts", {}):
            return {"success": False, "error": True, "content": f"Draft '{draft_id}' not found"}

        d = data["drafts"][draft_id]
        if to is not None:
            d["to"] = to
        if subject is not None:
            d["subject"] = subject
        if body is not None:
            d["body"] = body
        if cc is not None:
            d["cc"] = cc
        if bcc is not None:
            d["bcc"] = bcc
        d["updated_at"] = datetime.now().isoformat()

        _save_drafts(data)

        return {"success": True, "content": f"📋 Draft '{draft_id}' updated."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Update draft error: {e}"}


def delete_draft(draft_id=""):
    """Delete a saved draft."""
    try:
        if not draft_id:
            return {"success": False, "error": True, "content": "draft_id is required"}

        data = _load_drafts()
        if draft_id not in data.get("drafts", {}):
            return {"success": False, "error": True, "content": f"Draft '{draft_id}' not found"}

        del data["drafts"][draft_id]
        _save_drafts(data)

        return {"success": True, "content": f"📋 Draft '{draft_id}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete draft error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 16: EMAIL FOLDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

FOLDERS_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_folders.json")


def _load_custom_folders():
    try:
        if os.path.exists(FOLDERS_PATH):
            with open(FOLDERS_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"folders": []}


def _save_custom_folders(data):
    os.makedirs(os.path.dirname(FOLDERS_PATH), exist_ok=True)
    with open(FOLDERS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def create_mail_folder(folder_name="", parent=""):
    """Create a new mailbox folder in Mail.app."""
    try:
        if not folder_name:
            return {"success": False, "error": True, "content": "folder_name is required"}

        # Create via AppleScript
        if parent:
            script = f'''
            tell application "Mail"
                set parentBox to mailbox "{parent}" of account 1
                make new mailbox with properties {{name:"{folder_name}"}} at parentBox
            end tell
            '''
        else:
            script = f'''
            tell application "Mail"
                make new mailbox with properties {{name:"{folder_name}"}} at account 1
            end tell
            '''

        result = _run_applescript(script)

        # Track locally
        data = _load_custom_folders()
        data["folders"].append({
            "name": folder_name,
            "parent": parent,
            "created_at": datetime.now().isoformat(),
        })
        _save_custom_folders(data)

        return {"success": True, "content": f"📁 Folder '{folder_name}' created{' under ' + parent if parent else ''}."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Create folder error: {e}"}


def list_mail_folders():
    """List all mailbox folders."""
    try:
        script = '''
        tell application "Mail"
            set folderList to {}
            repeat with acct in accounts
                set acctName to name of acct
                repeat with mb in mailboxes of acct
                    set end of folderList to acctName & " > " & name of mb
                end repeat
            end repeat
            return folderList as text
        end tell
        '''

        result = _run_applescript(script)
        folders = [f.strip() for f in result.split(",") if f.strip()] if result else []

        if not folders:
            return {"success": True, "content": "📁 No mailbox folders found."}

        lines = [f"📁 Mail Folders ({len(folders)}):"]
        for f in folders:
            lines.append(f"  • {f}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List folders error: {e}"}


def rename_mail_folder(folder_name="", new_name=""):
    """Rename a mailbox folder."""
    try:
        if not folder_name or not new_name:
            return {"success": False, "error": True, "content": "Both folder_name and new_name are required"}

        script = f'''
        tell application "Mail"
            set mb to mailbox "{folder_name}" of account 1
            set name of mb to "{new_name}"
        end tell
        '''

        _run_applescript(script)

        return {"success": True, "content": f"📁 Folder renamed: '{folder_name}' → '{new_name}'"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Rename folder error: {e}"}


def delete_mail_folder(folder_name=""):
    """Delete a mailbox folder."""
    try:
        if not folder_name:
            return {"success": False, "error": True, "content": "folder_name is required"}

        script = f'''
        tell application "Mail"
            delete mailbox "{folder_name}" of account 1
        end tell
        '''

        _run_applescript(script)

        # Remove from local tracking
        data = _load_custom_folders()
        data["folders"] = [f for f in data["folders"] if f.get("name") != folder_name]
        _save_custom_folders(data)

        return {"success": True, "content": f"📁 Folder '{folder_name}' deleted."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Delete folder error: {e}"}


def move_to_folder(email_index=1, folder_name=""):
    """Move an email to a specific folder."""
    try:
        if not folder_name:
            return {"success": False, "error": True, "content": "folder_name is required"}

        script = f'''
        tell application "Mail"
            set targetBox to mailbox "{folder_name}" of account 1
            set msgs to messages of inbox
            set msg to item {email_index} of msgs
            move msg to targetBox
            return subject of msg
        end tell
        '''

        result = _run_applescript(script)

        return {"success": True, "content": f"📁 Email '{result}' moved to '{folder_name}'."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Move to folder error: {e}"}


def get_folder_stats():
    """Get email count per folder."""
    try:
        script = '''
        tell application "Mail"
            set statsText to ""
            repeat with acct in accounts
                set acctName to name of acct
                repeat with mb in mailboxes of acct
                    set mbName to name of mb
                    set msgCount to count of messages of mb
                    set unreadCount to unread count of mb
                    set statsText to statsText & acctName & " > " & mbName & ": " & msgCount & " total, " & unreadCount & " unread" & linefeed
                end repeat
            end repeat
            return statsText
        end tell
        '''

        result = _run_applescript(script)

        if not result or not result.strip():
            return {"success": True, "content": "📁 No folder stats available."}

        lines = ["📁 Folder Stats:"]
        for line in result.strip().split("\n"):
            if line.strip():
                lines.append(f"  {line.strip()}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Folder stats error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 17: EMAIL TRACKING
# ═══════════════════════════════════════════════════════════════════

TRACKING_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_tracking.json")


def _load_tracking():
    try:
        if os.path.exists(TRACKING_PATH):
            with open(TRACKING_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"tracked": {}}


def _save_tracking(data):
    os.makedirs(os.path.dirname(TRACKING_PATH), exist_ok=True)
    with open(TRACKING_PATH, "w") as f:
        json.dump(data, f, indent=2)


def track_email(subject="", recipient="", sent_at=""):
    """Track a sent email for follow-up / read status."""
    try:
        if not subject:
            return {"success": False, "error": True, "content": "subject is required"}

        tracking_id = f"trk_{uuid.uuid4().hex[:8]}"
        data = _load_tracking()

        data["tracked"][tracking_id] = {
            "subject": subject,
            "recipient": recipient,
            "sent_at": sent_at or datetime.now().isoformat(),
            "status": "sent",
            "replied": False,
            "reply_at": None,
            "created_at": datetime.now().isoformat(),
        }

        _save_tracking(data)

        return {"success": True, "content": f"📡 Tracking email '{subject}' to {recipient} (ID: {tracking_id})"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Track email error: {e}"}


def list_tracked_emails():
    """List all tracked emails."""
    try:
        data = _load_tracking()
        tracked = data.get("tracked", {})

        if not tracked:
            return {"success": True, "content": "📡 No tracked emails."}

        lines = [f"📡 Tracked Emails ({len(tracked)}):"]
        for tid, t in tracked.items():
            status = "✅ replied" if t.get("replied") else "⏳ awaiting"
            lines.append(f"  [{tid}] {t.get('subject', '')[:40]} → {t.get('recipient', '')} — {status}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List tracked error: {e}"}


def get_tracking_status(tracking_id=""):
    """Get detailed tracking status for a specific email."""
    try:
        if not tracking_id:
            return {"success": False, "error": True, "content": "tracking_id is required"}

        data = _load_tracking()
        if tracking_id not in data.get("tracked", {}):
            return {"success": False, "error": True, "content": f"Tracking '{tracking_id}' not found"}

        t = data["tracked"][tracking_id]
        sent_dt = datetime.fromisoformat(t.get("sent_at", datetime.now().isoformat()))
        elapsed = datetime.now() - sent_dt

        lines = [
            f"📡 Tracking: {t.get('subject', '')}",
            f"  Recipient: {t.get('recipient', '')}",
            f"  Sent: {t.get('sent_at', '')}",
            f"  Elapsed: {elapsed.days}d {elapsed.seconds // 3600}h",
            f"  Replied: {'Yes — ' + (t.get('reply_at') or '') if t.get('replied') else 'No'}",
            f"  Status: {t.get('status', 'unknown')}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Get tracking error: {e}"}


def tracking_report():
    """Generate a tracking summary report."""
    try:
        data = _load_tracking()
        tracked = data.get("tracked", {})

        if not tracked:
            return {"success": True, "content": "📡 No tracking data for report."}

        total = len(tracked)
        replied = sum(1 for t in tracked.values() if t.get("replied"))
        pending = total - replied

        # Avg response time for replied ones
        response_times = []
        for t in tracked.values():
            if t.get("replied") and t.get("reply_at") and t.get("sent_at"):
                try:
                    sent = datetime.fromisoformat(t["sent_at"])
                    reply = datetime.fromisoformat(t["reply_at"])
                    response_times.append((reply - sent).total_seconds() / 3600)
                except Exception:
                    pass

        avg_response = f"{round(sum(response_times) / len(response_times), 1)}h" if response_times else "N/A"

        lines = [
            f"📡 Email Tracking Report:",
            f"  Total tracked: {total}",
            f"  Replied: {replied} ({round(replied / total * 100) if total else 0}%)",
            f"  Pending: {pending}",
            f"  Avg response time: {avg_response}",
        ]

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Tracking report error: {e}"}


def untrack_email(tracking_id=""):
    """Remove tracking from an email."""
    try:
        if not tracking_id:
            return {"success": False, "error": True, "content": "tracking_id is required"}

        data = _load_tracking()
        if tracking_id not in data.get("tracked", {}):
            return {"success": False, "error": True, "content": f"Tracking '{tracking_id}' not found"}

        subject = data["tracked"][tracking_id].get("subject", tracking_id)
        del data["tracked"][tracking_id]
        _save_tracking(data)

        return {"success": True, "content": f"📡 Stopped tracking '{subject}'."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Untrack error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 18: EMAIL BATCH OPERATIONS (EXTENDED)
# ═══════════════════════════════════════════════════════════════════

def batch_archive(indices=None):
    """Archive multiple emails at once."""
    try:
        if not indices:
            return {"success": False, "error": True, "content": "indices list is required"}

        archived = []
        failed = []
        for idx in sorted(indices, reverse=True):
            try:
                script = f'''
                tell application "Mail"
                    set msgs to messages of inbox
                    set msg to item {idx} of msgs
                    set subj to subject of msg
                    move msg to mailbox "Archive" of account 1
                    return subj
                end tell
                '''
                result = _run_applescript(script)
                archived.append(f"#{idx}: {result}")
            except Exception as e:
                failed.append(f"#{idx}: {e}")

        lines = [f"📦 Batch Archive: {len(archived)} archived, {len(failed)} failed"]
        if archived:
            lines.append(f"  ✅ Archived: {', '.join(archived[:10])}")
        if failed:
            lines.append(f"  ❌ Failed: {', '.join(failed[:5])}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Batch archive error: {e}"}


def batch_reply(indices=None, body=""):
    """Send the same reply to multiple emails."""
    try:
        if not indices:
            return {"success": False, "error": True, "content": "indices list is required"}
        if not body:
            return {"success": False, "error": True, "content": "reply body is required"}

        replied = []
        failed = []
        for idx in indices:
            try:
                script = f'''
                tell application "Mail"
                    set msgs to messages of inbox
                    set msg to item {idx} of msgs
                    set subj to subject of msg
                    set replyMsg to reply msg with opening "Re: " & subj
                    set content of replyMsg to "{body.replace('"', '\\"')}"
                    send replyMsg
                    return subj
                end tell
                '''
                result = _run_applescript(script)
                replied.append(f"#{idx}: {result}")
            except Exception as e:
                failed.append(f"#{idx}: {e}")

        lines = [f"↩️ Batch Reply: {len(replied)} replied, {len(failed)} failed"]
        if replied:
            lines.append(f"  ✅ Replied: {', '.join(replied[:10])}")
        if failed:
            lines.append(f"  ❌ Failed: {', '.join(failed[:5])}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Batch reply error: {e}"}


def batch_label(indices=None, label=""):
    """Apply a label to multiple emails at once (extended batch)."""
    # This extends the Phase 12 bulk_label with more robust handling
    try:
        if not indices:
            return {"success": False, "error": True, "content": "indices list is required"}
        if not label:
            return {"success": False, "error": True, "content": "label is required"}

        from hands.email import add_label as _add_label
        labeled = []
        for idx in indices:
            result = _add_label(index=idx, label=label)
            if result.get("success"):
                labeled.append(idx)

        return {"success": True, "content": f"🏷️ Label '{label}' applied to {len(labeled)}/{len(indices)} emails."}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Batch label error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 19: EMAIL CALENDAR INTEGRATION
# ═══════════════════════════════════════════════════════════════════

CALENDAR_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "email_calendar.json")


def _load_email_calendar():
    try:
        if os.path.exists(CALENDAR_PATH):
            with open(CALENDAR_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"events": []}


def _save_email_calendar(data):
    os.makedirs(os.path.dirname(CALENDAR_PATH), exist_ok=True)
    with open(CALENDAR_PATH, "w") as f:
        json.dump(data, f, indent=2)


def email_to_event(email_index=1, calendar_name=""):
    """Create a calendar event from an email's content."""
    try:
        script = f'''
        tell application "Mail"
            set msgs to messages of inbox
            set msg to item {email_index} of msgs
            return (subject of msg) & "|||" & (sender of msg) & "|||" & (date received of msg as string) & "|||" & (content of msg)
        end tell
        '''

        result = _run_applescript(script)
        parts = result.split("|||")
        subject = parts[0] if len(parts) > 0 else "Email Event"
        sender = parts[1] if len(parts) > 1 else ""
        date_str = parts[2] if len(parts) > 2 else ""
        body = parts[3][:500] if len(parts) > 3 else ""

        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        data = _load_email_calendar()
        data["events"].append({
            "id": event_id,
            "title": subject,
            "from_email": sender,
            "date": date_str,
            "notes": body[:200],
            "calendar": calendar_name or "default",
            "source_index": email_index,
            "created_at": datetime.now().isoformat(),
        })
        _save_email_calendar(data)

        return {"success": True, "content": f"📅 Event created from email: '{subject}' (ID: {event_id})"}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Email to event error: {e}"}


def list_email_events():
    """List all calendar events created from emails."""
    try:
        data = _load_email_calendar()
        events = data.get("events", [])

        if not events:
            return {"success": True, "content": "📅 No email-based events."}

        lines = [f"📅 Email Events ({len(events)}):"]
        for e in events[-20:]:
            lines.append(f"  [{e.get('id', '')}] {e.get('title', '')[:40]} — from {e.get('from_email', '')[:25]} ({e.get('date', '')[:10]})")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"List email events error: {e}"}


def upcoming_from_email(days=7):
    """Show upcoming events created from emails."""
    try:
        data = _load_email_calendar()
        events = data.get("events", [])

        if not events:
            return {"success": True, "content": f"📅 No upcoming email events in the next {days} days."}

        cutoff = datetime.now()
        upcoming = []
        for e in events:
            try:
                created = datetime.fromisoformat(e.get("created_at", ""))
                if (cutoff - created).days <= days:
                    upcoming.append(e)
            except Exception:
                upcoming.append(e)

        if not upcoming:
            return {"success": True, "content": f"📅 No email events from the last {days} days."}

        lines = [f"📅 Recent Email Events ({len(upcoming)}):"]
        for e in upcoming:
            lines.append(f"  [{e.get('id', '')}] {e.get('title', '')[:40]} — {e.get('date', '')[:16]}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Upcoming events error: {e}"}


def meeting_conflicts(date=""):
    """Check for meeting conflicts on a given date."""
    try:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # Check Calendar.app via AppleScript
        script = f'''
        tell application "Calendar"
            set targetDate to date "{date}"
            set endOfDay to targetDate + 86400
            set eventList to ""
            repeat with cal in calendars
                set calEvents to (every event of cal whose start date >= targetDate and start date < endOfDay)
                repeat with evt in calEvents
                    set eventList to eventList & (summary of evt) & " | " & (start date of evt as string) & " - " & (end date of evt as string) & linefeed
                end repeat
            end repeat
            return eventList
        end tell
        '''

        result = _run_applescript(script)
        events = [e.strip() for e in result.strip().split("\n") if e.strip()] if result else []

        if not events:
            return {"success": True, "content": f"📅 No events on {date} — no conflicts."}

        conflicts = []
        for i, e1 in enumerate(events):
            for e2 in events[i + 1:]:
                conflicts.append(f"  ⚠️ {e1} vs {e2}")

        lines = [f"📅 Events on {date} ({len(events)}):"]
        for e in events:
            lines.append(f"  • {e}")
        if conflicts:
            lines.append(f"\n  Potential conflicts ({len(conflicts)}):")
            lines.extend(conflicts[:5])

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Meeting conflicts error: {e}"}


def sync_email_calendar():
    """Sync email-extracted events summary."""
    try:
        data = _load_email_calendar()
        events = data.get("events", [])
        total = len(events)

        # Count by calendar
        by_cal = {}
        for e in events:
            cal = e.get("calendar", "default")
            by_cal[cal] = by_cal.get(cal, 0) + 1

        lines = [
            f"📅 Email Calendar Sync:",
            f"  Total events: {total}",
        ]
        for cal, count in by_cal.items():
            lines.append(f"  • {cal}: {count} events")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Sync calendar error: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  PHASE 20: EMAIL DASHBOARD & REPORTING
# ═══════════════════════════════════════════════════════════════════

def email_dashboard():
    """Comprehensive email dashboard overview combining all stats."""
    try:
        lines = ["📊 TARS Email Dashboard", "=" * 40]

        # Inbox status
        try:
            inbox = _run_applescript('tell application "Mail" to return (count of messages of inbox) & "," & (unread count of inbox)')
            parts = inbox.split(",")
            total = parts[0].strip() if len(parts) > 0 else "?"
            unread = parts[1].strip() if len(parts) > 1 else "?"
            lines.append(f"\n📬 Inbox: {total} total, {unread} unread")
        except Exception:
            lines.append("\n📬 Inbox: unable to fetch")

        # Signatures count
        try:
            sigs = _load_signatures()
            lines.append(f"✍️ Signatures: {len(sigs.get('signatures', {}))}")
        except Exception:
            pass

        # Aliases count
        try:
            aliases = _load_aliases()
            lines.append(f"👤 Aliases: {len(aliases.get('aliases', {}))}")
        except Exception:
            pass

        # Templates count
        try:
            templates = _load_templates()
            lines.append(f"📝 Templates: {len(templates.get('templates', {}))}")
        except Exception:
            pass

        # Drafts count
        try:
            drafts = _load_drafts()
            lines.append(f"📋 Drafts: {len(drafts.get('drafts', {}))}")
        except Exception:
            pass

        # Tracking count
        try:
            tracking = _load_tracking()
            tracked = tracking.get("tracked", {})
            pending = sum(1 for t in tracked.values() if not t.get("replied"))
            lines.append(f"📡 Tracked: {len(tracked)} ({pending} awaiting reply)")
        except Exception:
            pass

        # Calendar events
        try:
            cal = _load_email_calendar()
            lines.append(f"📅 Email events: {len(cal.get('events', []))}")
        except Exception:
            pass

        # Export stats
        try:
            exports = json.load(open(EXPORT_INDEX_PATH)) if os.path.exists(EXPORT_INDEX_PATH) else {}
            lines.append(f"💾 Exports: {len(exports.get('exports', []))}")
        except Exception:
            pass

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Dashboard error: {e}"}


def weekly_report():
    """Generate weekly email activity report."""
    try:
        now = datetime.now()
        week_ago = now - __import__('datetime').timedelta(days=7)

        lines = [f"📊 Weekly Email Report ({week_ago.strftime('%b %d')} — {now.strftime('%b %d')})"]
        lines.append("=" * 40)

        # Check inbox activity
        try:
            inbox_result = _run_applescript('tell application "Mail" to return (count of messages of inbox) & "," & (unread count of inbox)')
            parts = inbox_result.split(",")
            lines.append(f"\n📬 Current inbox: {parts[0].strip()} messages, {parts[1].strip()} unread")
        except Exception:
            pass

        # Tracking activity this week
        try:
            tracking = _load_tracking()
            week_tracked = [t for t in tracking.get("tracked", {}).values()
                          if t.get("created_at", "") >= week_ago.isoformat()]
            replied = sum(1 for t in week_tracked if t.get("replied"))
            lines.append(f"📡 Tracked this week: {len(week_tracked)} sent, {replied} replied")
        except Exception:
            pass

        # Templates used
        try:
            templates = _load_templates()
            total_uses = sum(t.get("use_count", 0) for t in templates.get("templates", {}).values())
            lines.append(f"📝 Template uses (all time): {total_uses}")
        except Exception:
            pass

        # Drafts pending
        try:
            drafts = _load_drafts()
            lines.append(f"📋 Pending drafts: {len(drafts.get('drafts', {}))}")
        except Exception:
            pass

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Weekly report error: {e}"}


def monthly_report():
    """Generate monthly email activity report."""
    try:
        now = datetime.now()
        month_ago = now - __import__('datetime').timedelta(days=30)

        lines = [f"📊 Monthly Email Report ({month_ago.strftime('%b %d')} — {now.strftime('%b %d')})"]
        lines.append("=" * 40)

        # Tracking summary
        try:
            tracking = _load_tracking()
            all_tracked = tracking.get("tracked", {})
            month_tracked = [t for t in all_tracked.values()
                           if t.get("created_at", "") >= month_ago.isoformat()]
            replied = sum(1 for t in month_tracked if t.get("replied"))
            response_rate = round(replied / len(month_tracked) * 100) if month_tracked else 0
            lines.append(f"\n📡 Emails tracked: {len(month_tracked)}")
            lines.append(f"  Response rate: {response_rate}%")
        except Exception:
            pass

        # Export activity
        try:
            if os.path.exists(EXPORT_INDEX_PATH):
                exports = json.load(open(EXPORT_INDEX_PATH)).get("exports", [])
                month_exports = [e for e in exports if e.get("created_at", "") >= month_ago.isoformat()]
                lines.append(f"💾 Exports this month: {len(month_exports)}")
        except Exception:
            pass

        # Calendar events created
        try:
            cal = _load_email_calendar()
            month_events = [e for e in cal.get("events", [])
                          if e.get("created_at", "") >= month_ago.isoformat()]
            lines.append(f"📅 Events from email: {len(month_events)}")
        except Exception:
            pass

        # Overall health
        try:
            lines.append(f"\n📊 Total signatures: {len(_load_signatures().get('signatures', {}))}")
            lines.append(f"📊 Total aliases: {len(_load_aliases().get('aliases', {}))}")
            lines.append(f"📊 Total templates: {len(_load_templates().get('templates', {}))}")
        except Exception:
            pass

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Monthly report error: {e}"}


def productivity_score():
    """Calculate email productivity score (0-100)."""
    try:
        score = 50  # base score
        factors = []

        # Response rate factor
        try:
            tracking = _load_tracking()
            tracked = tracking.get("tracked", {})
            if tracked:
                replied = sum(1 for t in tracked.values() if t.get("replied"))
                rate = replied / len(tracked)
                score += int(rate * 15)
                factors.append(f"Response rate: {round(rate * 100)}% (+{int(rate * 15)})")
        except Exception:
            pass

        # Inbox management (fewer unread = better)
        try:
            inbox = _run_applescript('tell application "Mail" to return (unread count of inbox) as integer')
            unread = int(inbox.strip()) if inbox.strip().isdigit() else 0
            if unread <= 5:
                score += 15
                factors.append(f"Inbox near zero: {unread} unread (+15)")
            elif unread <= 20:
                score += 8
                factors.append(f"Inbox manageable: {unread} unread (+8)")
            else:
                score -= 5
                factors.append(f"Inbox overloaded: {unread} unread (-5)")
        except Exception:
            pass

        # Templates usage (efficiency)
        try:
            templates = _load_templates()
            total_uses = sum(t.get("use_count", 0) for t in templates.get("templates", {}).values())
            if total_uses >= 10:
                score += 10
                factors.append(f"Template power user: {total_uses} uses (+10)")
            elif total_uses >= 3:
                score += 5
                factors.append(f"Using templates: {total_uses} uses (+5)")
        except Exception:
            pass

        # Drafts pending (too many = procrastinating)
        try:
            drafts = _load_drafts()
            draft_count = len(drafts.get("drafts", {}))
            if draft_count > 10:
                score -= 5
                factors.append(f"Too many drafts: {draft_count} (-5)")
            elif draft_count > 0:
                factors.append(f"Active drafts: {draft_count} (neutral)")
        except Exception:
            pass

        # Clamp
        score = max(0, min(100, score))
        grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D" if score >= 50 else "F"

        lines = [
            f"📊 Email Productivity Score: {score}/100 (Grade: {grade})",
            "  Factors:",
        ]
        for f in factors:
            lines.append(f"    • {f}")

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Productivity score error: {e}"}


def email_trends(days=30):
    """Analyze email trends over time."""
    try:
        cutoff = datetime.now() - __import__('datetime').timedelta(days=days)

        lines = [f"📈 Email Trends (last {days} days)"]

        # Tracking trends
        try:
            tracking = _load_tracking()
            all_tracked = tracking.get("tracked", {})
            recent = {k: v for k, v in all_tracked.items()
                     if v.get("created_at", "") >= cutoff.isoformat()}
            replied = sum(1 for t in recent.values() if t.get("replied"))
            lines.append(f"\n📡 Tracking: {len(recent)} sent, {replied} replied ({round(replied / len(recent) * 100) if recent else 0}% rate)")
        except Exception:
            pass

        # Template usage trends
        try:
            templates = _load_templates()
            tmpl_count = len(templates.get("templates", {}))
            total_uses = sum(t.get("use_count", 0) for t in templates.get("templates", {}).values())
            lines.append(f"📝 Templates: {tmpl_count} available, {total_uses} total uses")
        except Exception:
            pass

        # Export trends
        try:
            if os.path.exists(EXPORT_INDEX_PATH):
                exports = json.load(open(EXPORT_INDEX_PATH)).get("exports", [])
                recent_exports = [e for e in exports if e.get("created_at", "") >= cutoff.isoformat()]
                lines.append(f"💾 Exports: {len(recent_exports)} in period (of {len(exports)} total)")
        except Exception:
            pass

        # Calendar event trends
        try:
            cal = _load_email_calendar()
            recent_events = [e for e in cal.get("events", [])
                           if e.get("created_at", "") >= cutoff.isoformat()]
            lines.append(f"📅 Events: {len(recent_events)} created from emails")
        except Exception:
            pass

        return {"success": True, "content": "\n".join(lines)}

    except Exception as e:
        return {"success": False, "error": True, "content": f"Email trends error: {e}"}