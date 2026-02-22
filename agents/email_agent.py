"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Email Agent: Full Email Management Specialist    ║
╠══════════════════════════════════════════════════════════════╣
║  Dedicated email agent with 20+ tools for complete email     ║
║  lifecycle management: read, compose, reply, forward, search,║
║  drafts, folders, attachments, templates, follow-ups.        ║
║                                                              ║
║  Own LLM loop. Inherits from BaseAgent.                      ║
║  Account: tarsitgroup@outlook.com (Mac Mail.app)             ║
╚══════════════════════════════════════════════════════════════╝
"""

from agents.base_agent import BaseAgent
from agents.agent_tools import (
    TOOL_DONE, TOOL_STUCK,
    # Email tools
    TOOL_EMAIL_READ_INBOX, TOOL_EMAIL_READ_MESSAGE, TOOL_EMAIL_SEND,
    TOOL_EMAIL_REPLY, TOOL_EMAIL_FORWARD, TOOL_EMAIL_SEARCH,
    TOOL_EMAIL_UNREAD_COUNT, TOOL_EMAIL_MARK_READ, TOOL_EMAIL_MARK_UNREAD,
    TOOL_EMAIL_FLAG, TOOL_EMAIL_DELETE, TOOL_EMAIL_ARCHIVE,
    TOOL_EMAIL_MOVE, TOOL_EMAIL_LIST_FOLDERS,
    TOOL_EMAIL_DOWNLOAD_ATTACHMENTS, TOOL_EMAIL_SAVE_DRAFT,
    TOOL_EMAIL_LIST_DRAFTS, TOOL_EMAIL_VERIFY_SENT,
    TOOL_EMAIL_TEMPLATE_SAVE, TOOL_EMAIL_TEMPLATE_LIST,
    TOOL_EMAIL_TEMPLATE_SEND, TOOL_EMAIL_FOLLOWUP,
    TOOL_EMAIL_CHECK_FOLLOWUPS, TOOL_EMAIL_CONTACT_LOOKUP,
    TOOL_EMAIL_STATS,
    # Auto-rules, summarization, threads
    TOOL_EMAIL_ADD_RULE, TOOL_EMAIL_LIST_RULES,
    TOOL_EMAIL_DELETE_RULE, TOOL_EMAIL_TOGGLE_RULE,
    TOOL_EMAIL_RUN_RULES, TOOL_EMAIL_SUMMARIZE,
    TOOL_EMAIL_CATEGORIZE, TOOL_EMAIL_THREAD,
    # Scheduling
    TOOL_EMAIL_SCHEDULE, TOOL_EMAIL_LIST_SCHEDULED,
    TOOL_EMAIL_CANCEL_SCHEDULED,
    # Batch operations
    TOOL_EMAIL_BATCH_READ, TOOL_EMAIL_BATCH_DELETE,
    TOOL_EMAIL_BATCH_MOVE, TOOL_EMAIL_BATCH_FORWARD,
    # Smart compose / quick replies
    TOOL_EMAIL_LIST_QUICK_REPLIES, TOOL_EMAIL_SEND_QUICK_REPLY,
    TOOL_EMAIL_SUGGEST_REPLIES,
    # Phase 5: Contacts management
    TOOL_EMAIL_CONTACT_ADD, TOOL_EMAIL_CONTACT_LIST,
    TOOL_EMAIL_CONTACT_SEARCH, TOOL_EMAIL_CONTACT_DELETE,
    TOOL_EMAIL_AUTO_LEARN_CONTACTS,
    # Phase 6: Snooze, Priority, Digest
    TOOL_EMAIL_SNOOZE, TOOL_EMAIL_LIST_SNOOZED,
    TOOL_EMAIL_CANCEL_SNOOZE, TOOL_EMAIL_PRIORITY_INBOX,
    TOOL_EMAIL_SENDER_PROFILE, TOOL_EMAIL_DIGEST,
    # Phase 7: OOO, Analytics
    TOOL_EMAIL_SET_OOO, TOOL_EMAIL_CANCEL_OOO,
    TOOL_EMAIL_OOO_STATUS, TOOL_EMAIL_ANALYTICS,
    TOOL_EMAIL_HEALTH,
    # Phase 8: Inbox Zero, Attachments, Contact Intelligence
    TOOL_EMAIL_CLEAN_SWEEP, TOOL_EMAIL_AUTO_TRIAGE,
    TOOL_EMAIL_INBOX_ZERO_STATUS, TOOL_EMAIL_SMART_UNSUBSCRIBE,
    TOOL_EMAIL_BUILD_ATTACHMENT_INDEX, TOOL_EMAIL_SEARCH_ATTACHMENTS,
    TOOL_EMAIL_ATTACHMENT_SUMMARY, TOOL_EMAIL_LIST_SAVED_ATTACHMENTS,
    TOOL_EMAIL_SCORE_RELATIONSHIPS, TOOL_EMAIL_DETECT_VIPS,
    TOOL_EMAIL_RELATIONSHIP_REPORT, TOOL_EMAIL_COMMUNICATION_GRAPH,
    TOOL_EMAIL_DECAY_CONTACTS,
    # Phase 9: Security & Trust, Action Items, Workflow Chains
    TOOL_EMAIL_SCAN_SECURITY, TOOL_EMAIL_CHECK_SENDER_TRUST,
    TOOL_EMAIL_SCAN_LINKS, TOOL_EMAIL_SECURITY_REPORT,
    TOOL_EMAIL_ADD_TRUSTED, TOOL_EMAIL_ADD_BLOCKED,
    TOOL_EMAIL_LIST_TRUSTED, TOOL_EMAIL_LIST_BLOCKED,
    TOOL_EMAIL_EXTRACT_ACTIONS, TOOL_EMAIL_EXTRACT_MEETING,
    TOOL_EMAIL_SCAN_INBOX_ACTIONS, TOOL_EMAIL_CREATE_REMINDER,
    TOOL_EMAIL_CREATE_CALENDAR, TOOL_EMAIL_LIST_ACTIONS,
    TOOL_EMAIL_COMPLETE_ACTION, TOOL_EMAIL_ACTION_SUMMARY,
    TOOL_EMAIL_CREATE_WORKFLOW, TOOL_EMAIL_LIST_WORKFLOWS,
    TOOL_EMAIL_GET_WORKFLOW, TOOL_EMAIL_DELETE_WORKFLOW,
    TOOL_EMAIL_TOGGLE_WORKFLOW, TOOL_EMAIL_RUN_WORKFLOW,
    TOOL_EMAIL_WORKFLOW_TEMPLATES, TOOL_EMAIL_CREATE_FROM_TEMPLATE,
    TOOL_EMAIL_WORKFLOW_HISTORY,
    # Phase 10: Smart Compose, Delegation, Contextual Search
    TOOL_EMAIL_SMART_COMPOSE, TOOL_EMAIL_REWRITE,
    TOOL_EMAIL_ADJUST_TONE, TOOL_EMAIL_SUGGEST_SUBJECTS,
    TOOL_EMAIL_PROOFREAD, TOOL_EMAIL_COMPOSE_REPLY_DRAFT,
    TOOL_EMAIL_DELEGATE, TOOL_EMAIL_LIST_DELEGATIONS,
    TOOL_EMAIL_UPDATE_DELEGATION, TOOL_EMAIL_COMPLETE_DELEGATION,
    TOOL_EMAIL_CANCEL_DELEGATION, TOOL_EMAIL_DELEGATION_DASHBOARD,
    TOOL_EMAIL_NUDGE_DELEGATION,
    TOOL_EMAIL_CONTEXTUAL_SEARCH, TOOL_EMAIL_BUILD_SEARCH_INDEX,
    TOOL_EMAIL_CONVERSATION_RECALL, TOOL_EMAIL_SEARCH_DATE_RANGE,
    TOOL_EMAIL_FIND_RELATED,
    # Phase 11: Sentiment Analysis, Smart Folders, Thread Summarization
    TOOL_EMAIL_ANALYZE_SENTIMENT, TOOL_EMAIL_BATCH_SENTIMENT,
    TOOL_EMAIL_SENDER_SENTIMENT, TOOL_EMAIL_SENTIMENT_ALERTS,
    TOOL_EMAIL_SENTIMENT_REPORT,
    TOOL_EMAIL_CREATE_SMART_FOLDER, TOOL_EMAIL_LIST_SMART_FOLDERS,
    TOOL_EMAIL_GET_SMART_FOLDER, TOOL_EMAIL_UPDATE_SMART_FOLDER,
    TOOL_EMAIL_DELETE_SMART_FOLDER, TOOL_EMAIL_PIN_SMART_FOLDER,
    TOOL_EMAIL_SUMMARIZE_THREAD, TOOL_EMAIL_THREAD_DECISIONS,
    TOOL_EMAIL_THREAD_PARTICIPANTS, TOOL_EMAIL_THREAD_TIMELINE,
    TOOL_EMAIL_PREPARE_FORWARD_SUMMARY,
    # Phase 12: Labels & Tags, Newsletter Management, Auto-Responder
    TOOL_EMAIL_ADD_LABEL, TOOL_EMAIL_REMOVE_LABEL,
    TOOL_EMAIL_LIST_LABELS, TOOL_EMAIL_GET_LABELED,
    TOOL_EMAIL_BULK_LABEL,
    TOOL_EMAIL_DETECT_NEWSLETTERS, TOOL_EMAIL_NEWSLETTER_DIGEST,
    TOOL_EMAIL_NEWSLETTER_STATS, TOOL_EMAIL_NEWSLETTER_PREFS,
    TOOL_EMAIL_APPLY_NEWSLETTER_PREFS,
    TOOL_EMAIL_CREATE_AUTO_RESPONSE, TOOL_EMAIL_LIST_AUTO_RESPONSES,
    TOOL_EMAIL_UPDATE_AUTO_RESPONSE, TOOL_EMAIL_DELETE_AUTO_RESPONSE,
    TOOL_EMAIL_TOGGLE_AUTO_RESPONSE, TOOL_EMAIL_AUTO_RESPONSE_HISTORY,
    # Phase 13: Signatures, Aliases, Export/Archival
    TOOL_EMAIL_CREATE_SIGNATURE, TOOL_EMAIL_LIST_SIGNATURES,
    TOOL_EMAIL_UPDATE_SIGNATURE, TOOL_EMAIL_DELETE_SIGNATURE,
    TOOL_EMAIL_SET_DEFAULT_SIGNATURE, TOOL_EMAIL_GET_SIGNATURE,
    TOOL_EMAIL_ADD_ALIAS, TOOL_EMAIL_LIST_ALIASES,
    TOOL_EMAIL_UPDATE_ALIAS, TOOL_EMAIL_DELETE_ALIAS,
    TOOL_EMAIL_SET_DEFAULT_ALIAS,
    TOOL_EMAIL_EXPORT_EMAILS, TOOL_EMAIL_EXPORT_THREAD,
    TOOL_EMAIL_BACKUP_MAILBOX, TOOL_EMAIL_LIST_BACKUPS,
    TOOL_EMAIL_SEARCH_EXPORTS, TOOL_EMAIL_EXPORT_STATS,
    # Phase 14: Templates
    TOOL_EMAIL_CREATE_TEMPLATE, TOOL_EMAIL_LIST_TEMPLATES,
    TOOL_EMAIL_GET_TEMPLATE, TOOL_EMAIL_UPDATE_TEMPLATE,
    TOOL_EMAIL_DELETE_TEMPLATE, TOOL_EMAIL_USE_TEMPLATE,
    # Phase 15: Drafts Management
    TOOL_EMAIL_SAVE_DRAFT_MANAGED, TOOL_EMAIL_LIST_DRAFTS_MANAGED,
    TOOL_EMAIL_GET_DRAFT, TOOL_EMAIL_UPDATE_DRAFT,
    TOOL_EMAIL_DELETE_DRAFT_MANAGED,
    # Phase 16: Folder Management
    TOOL_EMAIL_CREATE_MAIL_FOLDER, TOOL_EMAIL_LIST_MAIL_FOLDERS,
    TOOL_EMAIL_RENAME_MAIL_FOLDER, TOOL_EMAIL_DELETE_MAIL_FOLDER,
    TOOL_EMAIL_MOVE_TO_FOLDER, TOOL_EMAIL_GET_FOLDER_STATS,
    # Phase 17: Email Tracking
    TOOL_EMAIL_TRACK_EMAIL, TOOL_EMAIL_LIST_TRACKED,
    TOOL_EMAIL_GET_TRACKING_STATUS, TOOL_EMAIL_TRACKING_REPORT,
    TOOL_EMAIL_UNTRACK,
    # Phase 18: Extended Batch Ops
    TOOL_EMAIL_BATCH_ARCHIVE, TOOL_EMAIL_BATCH_REPLY,
    # Phase 19: Calendar Integration
    TOOL_EMAIL_TO_EVENT, TOOL_EMAIL_LIST_EMAIL_EVENTS,
    TOOL_EMAIL_UPCOMING_FROM_EMAIL, TOOL_EMAIL_MEETING_CONFLICTS,
    TOOL_EMAIL_SYNC_CALENDAR,
    # Phase 20: Dashboard & Reporting
    TOOL_EMAIL_DASHBOARD, TOOL_EMAIL_WEEKLY_REPORT,
    TOOL_EMAIL_MONTHLY_REPORT, TOOL_EMAIL_PRODUCTIVITY_SCORE,
    TOOL_EMAIL_TRENDS,
)
from hands.file_manager import read_file
import hands.email as mail


# ─────────────────────────────────────────────
#  System Prompt
# ─────────────────────────────────────────────

EMAIL_AGENT_PROMPT = """You are TARS Email Agent — the world's most capable email management specialist. You have FULL CONTROL of email via Mac Mail.app, logged in as tarsitgroup@outlook.com.

## Your Capabilities (197 tools)

### Read & Triage
- **email_read_inbox** — Read latest N emails with sender, subject, date, read/unread status
- **email_read_message** — Read full email content (from, to, cc, subject, body, attachments)
- **email_unread_count** — Get number of unread emails
- **email_mark_read** / **email_mark_unread** — Mark emails as read/unread
- **email_flag** — Flag/unflag important emails

### Compose & Send
- **email_send** — Send emails (plain text or HTML, with CC/BCC, multiple recipients, attachments)
- **email_reply** — Reply to an email (with optional reply-all)
- **email_forward** — Forward an email to a new recipient
- **email_save_draft** — Save a draft for later
- **email_verify_sent** — Confirm an email was actually sent by checking the Sent folder

### Search & Filter
- **email_search** — Advanced search with filters: keyword, sender, subject, unread only, flagged only, has attachments, date range

### Organize
- **email_delete** — Delete an email (move to Trash)
- **email_archive** — Archive an email
- **email_move** — Move email to any folder
- **email_list_folders** — List all mailboxes/folders across accounts
- **email_download_attachments** — Download attachments from an email

### Templates & Automation
- **email_template_save** — Save a reusable email template
- **email_template_list** — List saved templates
- **email_template_send** — Send an email using a template with variable substitution
- **email_followup** — Track an email for follow-up if no reply
- **email_check_followups** — Check for overdue follow-ups

### Contacts
- **email_contact_lookup** — Look up email addresses by contact name (macOS Contacts)

### Stats
- **email_stats** — Get email statistics (unread count, etc.)

### Auto-Rules
- **email_add_rule** — Add a persistent auto-rule (conditions → actions). Rules auto-apply to new incoming emails.
- **email_list_rules** — List all auto-rules with hit counts
- **email_delete_rule** — Delete a rule by ID
- **email_toggle_rule** — Enable/disable a rule
- **email_run_rules** — Manually run all rules against existing inbox messages

### Summarization & Threads
- **email_summarize** — Generate a structured inbox summary: priority/regular/newsletters, top senders, unread counts
- **email_thread** — Get full conversation thread by subject or message index (groups Re:/Fwd: emails chronologically)

### Scheduling
- **email_schedule** — Schedule an email for later (ISO timestamp or minutes from now). Inbox monitor auto-sends when time arrives.
- **email_list_scheduled** — List all pending scheduled emails
- **email_cancel_scheduled** — Cancel a scheduled email before it sends

### Batch Operations
- **email_batch_mark_read** — Mark multiple emails as read at once (by indices or all_unread=true)
- **email_batch_delete** — Delete multiple emails at once (by indices or by sender)
- **email_batch_move** — Move multiple emails to a folder at once
- **email_batch_forward** — Forward multiple emails to someone at once

### Smart Compose / Quick Replies
- **email_list_quick_replies** — List all available quick reply templates (acknowledge, confirm_meeting, decline_meeting, etc.) plus custom saved templates
- **email_send_quick_reply** — Send a quick reply using a template (e.g. 'acknowledge', 'confirm_meeting', 'template:my_template'). Can append a custom_note.
- **email_suggest_replies** — Analyze an email and suggest appropriate quick reply types based on its content

### Snooze
- **email_snooze** — Snooze an email (mark read now, resurface later). Supports '2h', '30m', '1d', 'tomorrow', 'monday', 'tonight', 'next_week', or ISO timestamp.
- **email_list_snoozed** — List all snoozed emails with resurface times
- **email_cancel_snooze** — Cancel a snooze, immediately resurface the email

### Priority & Intelligence
- **email_priority_inbox** — Get inbox sorted by 0-100 priority score (factors: urgency, sender reputation, recency, unread, thread depth, category)
- **email_sender_profile** — Get detailed sender stats: message counts, frequency, relationship
- **email_digest** — Generate daily email briefing: stats overview, top priority, category breakdown, follow-ups, snoozed

### Out-of-Office
- **set_ooo** — Set auto-reply for a date range (start_date, end_date, message, optional exceptions). Auto-disables when period ends.
- **cancel_ooo** — Cancel the active out-of-office auto-reply
- **ooo_status** — Check if OOO is active and get details (dates, message, reply count)

### Analytics & Health
- **email_analytics** — Comprehensive analytics: volume, top communicators, follow-up rates, snooze stats, rules, health score (optional period: day/week/month)
- **email_health** — Email health score 0-100 with grade (A-D) and contributing factors

### Inbox Zero
- **clean_sweep** — Bulk archive old low-priority emails (newsletters, notifications, promotional). Use dry_run=true to preview first.
- **auto_triage** — Auto-categorize latest emails into priority/action_needed/FYI/archive_candidate with suggested actions
- **inbox_zero_status** — Current inbox zero progress: total count, trend vs yesterday, streak, category breakdown
- **smart_unsubscribe** — Detect newsletter/marketing email and extract unsubscribe link

### Attachment Intelligence
- **build_attachment_index** — Scan inbox and index all attachments (filename, size, sender, date)
- **search_attachments** — Search attachment index by filename, sender, or file type
- **attachment_summary** — Summary: total count, total size, breakdown by file type, top senders
- **list_saved_attachments** — List downloaded attachments in TARS storage (optional folder/file_type filter)

### Contact Relationship Intelligence
- **score_relationships** — Score all contacts by communication frequency, recency, reciprocity (0-100)
- **detect_vips** — Auto-detect VIP contacts above score threshold, auto-tag them
- **relationship_report** — Detailed relationship report for a specific contact
- **communication_graph** — Top N communication partners with relationship metrics
- **decay_contacts** — Decay stale contacts inactive for N days

### Email Security & Trust
- **scan_email_security** — Full security scan: phishing score, link analysis, sender trust, risk level
- **check_sender_trust** — Sender trust score 0-100 (contacts, history, domain reputation)
- **scan_links** — Extract and analyze all URLs (shortened, IP-based, typosquat detection)
- **security_report** — Inbox-wide security scan for threats
- **add_trusted_sender** — Add email/domain to trusted list
- **add_blocked_sender** — Add email/domain to blocked list
- **list_trusted_senders** — List all trusted senders/domains
- **list_blocked_senders** — List all blocked senders/domains

### Action Item & Meeting Extraction
- **extract_action_items** — Parse email for tasks, deadlines, requests
- **extract_meeting_details** — Parse email for meeting date/time/link/location/attendees
- **scan_inbox_actions** — Batch-scan inbox for all action items and meetings
- **create_reminder** — Create macOS Reminder from an action item
- **create_calendar_event** — Create Calendar.app event from meeting details
- **list_actions** — List extracted action items (filter: all/pending/completed)
- **complete_action** — Mark an action item as completed
- **action_summary** — Dashboard summary of pending/completed actions

### Workflow Chains
- **create_workflow** — Create multi-step workflow chain (trigger + steps)
- **list_workflows** — List all workflows
- **get_workflow** — Get full workflow definition
- **delete_workflow** — Delete a workflow
- **toggle_workflow** — Enable/disable a workflow
- **run_workflow** — Manually run workflow against a specific email
- **workflow_templates** — List built-in workflow templates
- **create_from_template** — Create workflow from a template
- **workflow_history** — Get workflow execution history

### Smart Compose & Writing Assistance (AI-Powered)
- **smart_compose** — AI-compose email from natural language prompt (tone, style, context, recipient)
- **rewrite_email** — AI-rewrite existing email text in a new tone/style
- **adjust_tone** — Change just the tone of existing email text
- **suggest_subject_lines** — Generate 5 subject line options from email body
- **proofread_email** — Check grammar, spelling, clarity, professionalism
- **compose_reply_draft** — Read email by index, then AI-draft a reply based on instructions

### Email Delegation & Task Assignment
- **delegate_email** — Delegate an email task to someone (delegate_to, instructions, deadline)
- **list_delegations** — List all delegations (optional status filter)
- **update_delegation** — Update delegation status/notes
- **complete_delegation** — Mark delegation as completed with outcome
- **cancel_delegation** — Cancel a delegation with reason
- **delegation_dashboard** — Overview: totals, by status, overdue, avg completion time
- **nudge_delegation** — Send reminder for an overdue delegation

### Contextual Search & Email Memory
- **contextual_search** — Natural language email search ("emails from John about project last week")
- **build_search_index** — Rebuild email search index from inbox
- **conversation_recall** — Full conversation history with a contact (optional AI summary)
- **search_by_date_range** — Search emails within a date range with optional keyword
- **find_related_emails** — Find emails related to a given email by subject/sender/content

### Sentiment Analysis
- **analyze_sentiment** — Analyze sentiment/tone of a single email (score -100 to +100, label, keywords)
- **batch_sentiment** — Batch sentiment analysis across N emails — average score, positive/neutral/negative counts
- **sender_sentiment** — Sentiment history & trends for a specific sender
- **sentiment_alerts** — Flag emails with negative sentiment below threshold
- **sentiment_report** — Period-based sentiment analytics (day/week/month)

### Smart Folders (Saved Searches)
- **create_smart_folder** — Create a dynamic folder with saved search criteria (auto-updates)
- **list_smart_folders** — List all smart folders
- **get_smart_folder** — Execute smart folder's search and return results
- **update_smart_folder** — Update name or criteria
- **delete_smart_folder** — Delete a smart folder
- **pin_smart_folder** — Pin/unpin for quick access

### Thread Summarization (AI-Powered)
- **summarize_thread** — AI summary of an email thread: key points, status, pending items
- **thread_decisions** — Extract key decisions from a thread (who decided what, when)
- **thread_participants** — Who said what: message counts, word counts, participation breakdown
- **thread_timeline** — Chronological timeline of events in a thread
- **prepare_forward_summary** — Generate TL;DR for forwarding a thread

### Labels & Tags
- **add_label** — Add a custom label/tag to an email
- **remove_label** — Remove a label from an email
- **list_labels** — List all labels with email counts
- **get_labeled_emails** — Get all emails with a specific label
- **bulk_label** — Apply a label to multiple emails at once

### Newsletter Management
- **detect_newsletters** — Scan inbox for newsletter/subscription emails
- **newsletter_digest** — Generate a digest of recent newsletters
- **newsletter_stats** — Stats on newsletter volume and top sources
- **newsletter_preferences** — Set preference per newsletter sender (keep/archive/unsubscribe)
- **apply_newsletter_preferences** — Apply saved preferences to inbox

### Auto-Responder
- **create_auto_response** — Create conditional auto-response rule
- **list_auto_responses** — List all auto-response rules
- **update_auto_response** — Update an auto-response rule
- **delete_auto_response** — Delete an auto-response rule
- **toggle_auto_response** — Enable/disable an auto-response
- **auto_response_history** — View history of sent auto-responses

### Email Signatures
- **create_signature** — Create a reusable email signature
- **list_signatures** — List all signatures
- **update_signature** — Update a signature
- **delete_signature** — Delete a signature
- **set_default_signature** — Set default signature
- **get_signature** — Get a signature by ID or default

### Email Aliases / Identities
- **add_alias** — Add a sender alias/identity
- **list_aliases** — List all aliases
- **update_alias** — Update an alias
- **delete_alias** — Delete an alias
- **set_default_alias** — Set default sender alias

### Email Export / Archival
- **export_emails** — Export recent emails to JSON/text
- **export_thread** — Export a full thread to file
- **backup_mailbox** — Full mailbox backup
- **list_backups** — List all exports and backups
- **search_exports** — Search through exported emails
- **export_stats** — Export/backup statistics

### Email Templates
- **create_template** — Create reusable email template with {{var}} placeholders
- **list_templates** — List all templates (optional category filter)
- **get_template** — Get template details by ID
- **update_template** — Update a template
- **delete_template** — Delete a template
- **use_template** — Render template with variable substitutions

### Draft Management
- **save_draft** — Save email as draft
- **list_drafts_managed** — List all saved drafts
- **get_draft** — Get draft details
- **update_draft** — Update a draft
- **delete_draft** — Delete a draft

### Folder Management
- **create_mail_folder** — Create a mailbox folder
- **list_mail_folders** — List all folders
- **rename_mail_folder** — Rename a folder
- **delete_mail_folder** — Delete a folder
- **move_to_folder** — Move email to folder
- **get_folder_stats** — Folder email counts

### Email Tracking
- **track_email** — Track sent email for reply status
- **list_tracked_emails** — List tracked emails
- **get_tracking_status** — Tracking details for an email
- **tracking_report** — Tracking summary report
- **untrack_email** — Stop tracking an email

### Extended Batch Operations
- **batch_archive** — Archive multiple emails
- **batch_reply** — Reply to multiple emails

### Calendar Integration
- **email_to_event** — Create calendar event from email
- **list_email_events** — List email-created events
- **upcoming_from_email** — Upcoming email events
- **meeting_conflicts** — Check meeting conflicts
- **sync_email_calendar** — Calendar sync summary

### Dashboard & Reporting
- **email_dashboard** — Full email dashboard overview
- **weekly_report** — Weekly activity summary
- **monthly_report** — Monthly activity summary
- **productivity_score** — Productivity rating 0-100
- **email_trends** — Trend analysis

## Your Process
1. **Understand the request** — What email operation is needed?
2. **Gather context** — Check inbox/unread count/search as needed
3. **Execute precisely** — Use the right tool with correct parameters
4. **Verify** — After sending, use email_verify_sent to confirm delivery
5. **Report back** — Call `done` with specific details of what was accomplished

## Rules
1. ALWAYS verify emails were sent using email_verify_sent after sending important emails
2. When composing, use proper formatting — professional tone unless told otherwise
3. For HTML emails, set html=true and provide well-structured HTML
4. NEVER fabricate email content — only report what you actually see in the inbox
5. When searching, try multiple approaches if the first search returns nothing
6. For attachments, always verify the file exists before trying to send
7. Use templates for recurring email types
8. Set follow-ups for emails that need replies
9. The default account is tarsitgroup@outlook.com — use this unless told otherwise
10. Call `done` with a clear summary. Call `stuck` with what you tried.

## Email Composition Guidelines
- **Subject**: Clear, specific, actionable (e.g., "Q4 Report — Action Required by Friday")
- **Body**: Professional, concise, with clear ask or information
- **HTML**: Use for reports, formatted content, tables. Plain text for simple messages.
- **Attachments**: Always use absolute paths (e.g., /Users/abdullah/Documents/report.pdf)
- **CC/BCC**: Use CC for visibility, BCC for privacy

## CRITICAL ANTI-HALLUCINATION RULES
- You can ONLY do things through your tools. If you didn't call a tool, it didn't happen.
- NEVER claim you sent an email unless email_send returned success.
- NEVER fabricate inbox contents — only report what email_read_inbox/email_read_message returns.
- Your `done(summary)` must describe SPECIFIC actions with SPECIFIC results.
- If you can't complete the task, call `stuck` with what you tried.
"""


class EmailAgent(BaseAgent):
    """Autonomous email agent — manages email via Mail.app with 20+ tools."""

    @property
    def agent_name(self):
        return "Email Agent"

    @property
    def agent_emoji(self):
        return "📧"

    @property
    def system_prompt(self):
        return EMAIL_AGENT_PROMPT

    @property
    def tools(self):
        return [
            TOOL_DONE, TOOL_STUCK,
            # Read & Triage
            TOOL_EMAIL_READ_INBOX, TOOL_EMAIL_READ_MESSAGE,
            TOOL_EMAIL_UNREAD_COUNT, TOOL_EMAIL_MARK_READ,
            TOOL_EMAIL_MARK_UNREAD, TOOL_EMAIL_FLAG,
            # Compose & Send
            TOOL_EMAIL_SEND, TOOL_EMAIL_REPLY, TOOL_EMAIL_FORWARD,
            TOOL_EMAIL_SAVE_DRAFT, TOOL_EMAIL_VERIFY_SENT,
            # Search
            TOOL_EMAIL_SEARCH,
            # Organize
            TOOL_EMAIL_DELETE, TOOL_EMAIL_ARCHIVE, TOOL_EMAIL_MOVE,
            TOOL_EMAIL_LIST_FOLDERS, TOOL_EMAIL_DOWNLOAD_ATTACHMENTS,
            # Templates & Automation
            TOOL_EMAIL_TEMPLATE_SAVE, TOOL_EMAIL_TEMPLATE_LIST,
            TOOL_EMAIL_TEMPLATE_SEND, TOOL_EMAIL_FOLLOWUP,
            TOOL_EMAIL_CHECK_FOLLOWUPS,
            # Contacts & Stats
            TOOL_EMAIL_CONTACT_LOOKUP, TOOL_EMAIL_STATS,
            TOOL_EMAIL_CONTACT_ADD, TOOL_EMAIL_CONTACT_LIST,
            TOOL_EMAIL_CONTACT_SEARCH, TOOL_EMAIL_CONTACT_DELETE,
            TOOL_EMAIL_AUTO_LEARN_CONTACTS,
            # Auto-Rules
            TOOL_EMAIL_ADD_RULE, TOOL_EMAIL_LIST_RULES,
            TOOL_EMAIL_DELETE_RULE, TOOL_EMAIL_TOGGLE_RULE,
            TOOL_EMAIL_RUN_RULES,
            # Summarization, Categorization & Threads
            TOOL_EMAIL_SUMMARIZE, TOOL_EMAIL_CATEGORIZE,
            TOOL_EMAIL_THREAD,
            # Scheduling
            TOOL_EMAIL_SCHEDULE, TOOL_EMAIL_LIST_SCHEDULED,
            TOOL_EMAIL_CANCEL_SCHEDULED,
            # Batch Operations
            TOOL_EMAIL_BATCH_READ, TOOL_EMAIL_BATCH_DELETE,
            TOOL_EMAIL_BATCH_MOVE, TOOL_EMAIL_BATCH_FORWARD,
            # Smart Compose / Quick Replies
            TOOL_EMAIL_LIST_QUICK_REPLIES, TOOL_EMAIL_SEND_QUICK_REPLY,
            TOOL_EMAIL_SUGGEST_REPLIES,
            # Snooze, Priority & Digest
            TOOL_EMAIL_SNOOZE, TOOL_EMAIL_LIST_SNOOZED,
            TOOL_EMAIL_CANCEL_SNOOZE, TOOL_EMAIL_PRIORITY_INBOX,
            TOOL_EMAIL_SENDER_PROFILE, TOOL_EMAIL_DIGEST,
            # OOO & Analytics
            TOOL_EMAIL_SET_OOO, TOOL_EMAIL_CANCEL_OOO,
            TOOL_EMAIL_OOO_STATUS, TOOL_EMAIL_ANALYTICS,
            TOOL_EMAIL_HEALTH,
            # Inbox Zero
            TOOL_EMAIL_CLEAN_SWEEP, TOOL_EMAIL_AUTO_TRIAGE,
            TOOL_EMAIL_INBOX_ZERO_STATUS, TOOL_EMAIL_SMART_UNSUBSCRIBE,
            # Attachments
            TOOL_EMAIL_BUILD_ATTACHMENT_INDEX, TOOL_EMAIL_SEARCH_ATTACHMENTS,
            TOOL_EMAIL_ATTACHMENT_SUMMARY, TOOL_EMAIL_LIST_SAVED_ATTACHMENTS,
            # Contact Intelligence
            TOOL_EMAIL_SCORE_RELATIONSHIPS, TOOL_EMAIL_DETECT_VIPS,
            TOOL_EMAIL_RELATIONSHIP_REPORT, TOOL_EMAIL_COMMUNICATION_GRAPH,
            TOOL_EMAIL_DECAY_CONTACTS,
            # Security & Trust
            TOOL_EMAIL_SCAN_SECURITY, TOOL_EMAIL_CHECK_SENDER_TRUST,
            TOOL_EMAIL_SCAN_LINKS, TOOL_EMAIL_SECURITY_REPORT,
            TOOL_EMAIL_ADD_TRUSTED, TOOL_EMAIL_ADD_BLOCKED,
            TOOL_EMAIL_LIST_TRUSTED, TOOL_EMAIL_LIST_BLOCKED,
            # Action Items & Meetings
            TOOL_EMAIL_EXTRACT_ACTIONS, TOOL_EMAIL_EXTRACT_MEETING,
            TOOL_EMAIL_SCAN_INBOX_ACTIONS, TOOL_EMAIL_CREATE_REMINDER,
            TOOL_EMAIL_CREATE_CALENDAR, TOOL_EMAIL_LIST_ACTIONS,
            TOOL_EMAIL_COMPLETE_ACTION, TOOL_EMAIL_ACTION_SUMMARY,
            # Workflow Chains
            TOOL_EMAIL_CREATE_WORKFLOW, TOOL_EMAIL_LIST_WORKFLOWS,
            TOOL_EMAIL_GET_WORKFLOW, TOOL_EMAIL_DELETE_WORKFLOW,
            TOOL_EMAIL_TOGGLE_WORKFLOW, TOOL_EMAIL_RUN_WORKFLOW,
            TOOL_EMAIL_WORKFLOW_TEMPLATES, TOOL_EMAIL_CREATE_FROM_TEMPLATE,
            TOOL_EMAIL_WORKFLOW_HISTORY,
            # Smart Compose & Writing
            TOOL_EMAIL_SMART_COMPOSE, TOOL_EMAIL_REWRITE,
            TOOL_EMAIL_ADJUST_TONE, TOOL_EMAIL_SUGGEST_SUBJECTS,
            TOOL_EMAIL_PROOFREAD, TOOL_EMAIL_COMPOSE_REPLY_DRAFT,
            # Delegation
            TOOL_EMAIL_DELEGATE, TOOL_EMAIL_LIST_DELEGATIONS,
            TOOL_EMAIL_UPDATE_DELEGATION, TOOL_EMAIL_COMPLETE_DELEGATION,
            TOOL_EMAIL_CANCEL_DELEGATION, TOOL_EMAIL_DELEGATION_DASHBOARD,
            TOOL_EMAIL_NUDGE_DELEGATION,
            # Contextual Search
            TOOL_EMAIL_CONTEXTUAL_SEARCH, TOOL_EMAIL_BUILD_SEARCH_INDEX,
            TOOL_EMAIL_CONVERSATION_RECALL, TOOL_EMAIL_SEARCH_DATE_RANGE,
            TOOL_EMAIL_FIND_RELATED,
            # Sentiment Analysis
            TOOL_EMAIL_ANALYZE_SENTIMENT, TOOL_EMAIL_BATCH_SENTIMENT,
            TOOL_EMAIL_SENDER_SENTIMENT, TOOL_EMAIL_SENTIMENT_ALERTS,
            TOOL_EMAIL_SENTIMENT_REPORT,
            # Smart Folders
            TOOL_EMAIL_CREATE_SMART_FOLDER, TOOL_EMAIL_LIST_SMART_FOLDERS,
            TOOL_EMAIL_GET_SMART_FOLDER, TOOL_EMAIL_UPDATE_SMART_FOLDER,
            TOOL_EMAIL_DELETE_SMART_FOLDER, TOOL_EMAIL_PIN_SMART_FOLDER,
            # Thread Summarization
            TOOL_EMAIL_SUMMARIZE_THREAD, TOOL_EMAIL_THREAD_DECISIONS,
            TOOL_EMAIL_THREAD_PARTICIPANTS, TOOL_EMAIL_THREAD_TIMELINE,
            TOOL_EMAIL_PREPARE_FORWARD_SUMMARY,
            # Labels & Tags
            TOOL_EMAIL_ADD_LABEL, TOOL_EMAIL_REMOVE_LABEL,
            TOOL_EMAIL_LIST_LABELS, TOOL_EMAIL_GET_LABELED,
            TOOL_EMAIL_BULK_LABEL,
            # Newsletter Management
            TOOL_EMAIL_DETECT_NEWSLETTERS, TOOL_EMAIL_NEWSLETTER_DIGEST,
            TOOL_EMAIL_NEWSLETTER_STATS, TOOL_EMAIL_NEWSLETTER_PREFS,
            TOOL_EMAIL_APPLY_NEWSLETTER_PREFS,
            # Auto-Responder
            TOOL_EMAIL_CREATE_AUTO_RESPONSE, TOOL_EMAIL_LIST_AUTO_RESPONSES,
            TOOL_EMAIL_UPDATE_AUTO_RESPONSE, TOOL_EMAIL_DELETE_AUTO_RESPONSE,
            TOOL_EMAIL_TOGGLE_AUTO_RESPONSE, TOOL_EMAIL_AUTO_RESPONSE_HISTORY,
            # Signatures
            TOOL_EMAIL_CREATE_SIGNATURE, TOOL_EMAIL_LIST_SIGNATURES,
            TOOL_EMAIL_UPDATE_SIGNATURE, TOOL_EMAIL_DELETE_SIGNATURE,
            TOOL_EMAIL_SET_DEFAULT_SIGNATURE, TOOL_EMAIL_GET_SIGNATURE,
            # Aliases / Identities
            TOOL_EMAIL_ADD_ALIAS, TOOL_EMAIL_LIST_ALIASES,
            TOOL_EMAIL_UPDATE_ALIAS, TOOL_EMAIL_DELETE_ALIAS,
            TOOL_EMAIL_SET_DEFAULT_ALIAS,
            # Export / Archival
            TOOL_EMAIL_EXPORT_EMAILS, TOOL_EMAIL_EXPORT_THREAD,
            TOOL_EMAIL_BACKUP_MAILBOX, TOOL_EMAIL_LIST_BACKUPS,
            TOOL_EMAIL_SEARCH_EXPORTS, TOOL_EMAIL_EXPORT_STATS,
            # Templates
            TOOL_EMAIL_CREATE_TEMPLATE, TOOL_EMAIL_LIST_TEMPLATES,
            TOOL_EMAIL_GET_TEMPLATE, TOOL_EMAIL_UPDATE_TEMPLATE,
            TOOL_EMAIL_DELETE_TEMPLATE, TOOL_EMAIL_USE_TEMPLATE,
            # Drafts Management
            TOOL_EMAIL_SAVE_DRAFT_MANAGED, TOOL_EMAIL_LIST_DRAFTS_MANAGED,
            TOOL_EMAIL_GET_DRAFT, TOOL_EMAIL_UPDATE_DRAFT,
            TOOL_EMAIL_DELETE_DRAFT_MANAGED,
            # Folder Management
            TOOL_EMAIL_CREATE_MAIL_FOLDER, TOOL_EMAIL_LIST_MAIL_FOLDERS,
            TOOL_EMAIL_RENAME_MAIL_FOLDER, TOOL_EMAIL_DELETE_MAIL_FOLDER,
            TOOL_EMAIL_MOVE_TO_FOLDER, TOOL_EMAIL_GET_FOLDER_STATS,
            # Email Tracking
            TOOL_EMAIL_TRACK_EMAIL, TOOL_EMAIL_LIST_TRACKED,
            TOOL_EMAIL_GET_TRACKING_STATUS, TOOL_EMAIL_TRACKING_REPORT,
            TOOL_EMAIL_UNTRACK,
            # Extended Batch Ops
            TOOL_EMAIL_BATCH_ARCHIVE, TOOL_EMAIL_BATCH_REPLY,
            # Calendar Integration
            TOOL_EMAIL_TO_EVENT, TOOL_EMAIL_LIST_EMAIL_EVENTS,
            TOOL_EMAIL_UPCOMING_FROM_EMAIL, TOOL_EMAIL_MEETING_CONFLICTS,
            TOOL_EMAIL_SYNC_CALENDAR,
            # Dashboard & Reporting
            TOOL_EMAIL_DASHBOARD, TOOL_EMAIL_WEEKLY_REPORT,
            TOOL_EMAIL_MONTHLY_REPORT, TOOL_EMAIL_PRODUCTIVITY_SCORE,
            TOOL_EMAIL_TRENDS,
        ]

    def _dispatch(self, name, inp):
        """Route email tool calls to hands/email.py functions."""
        try:
            # ── Read & Triage ──
            if name == "email_read_inbox":
                return self._r(mail.read_inbox(inp.get("count", 10)))

            elif name == "email_read_message":
                return self._r(mail.read_message(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_unread_count":
                return self._r(mail.get_unread_count())

            elif name == "email_mark_read":
                return self._r(mail.mark_read(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_mark_unread":
                return self._r(mail.mark_unread(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_flag":
                return self._r(mail.flag_message(
                    inp.get("index", 1),
                    inp.get("flagged", True),
                    inp.get("mailbox", "inbox"),
                ))

            # ── Compose & Send ──
            elif name == "email_send":
                return self._r(mail.send_email(
                    to=inp["to"],
                    subject=inp["subject"],
                    body=inp["body"],
                    cc=inp.get("cc"),
                    bcc=inp.get("bcc"),
                    attachment_paths=inp.get("attachment_paths"),
                    html=inp.get("html", False),
                    from_address=inp.get("from_address", "tarsitgroup@outlook.com"),
                ))

            elif name == "email_reply":
                return self._r(mail.reply_to(
                    inp.get("index", 1),
                    inp.get("body", ""),
                    inp.get("reply_all", False),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_forward":
                return self._r(mail.forward_to(
                    inp.get("index", 1),
                    inp["to"],
                    inp.get("body", ""),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_save_draft":
                return self._r(mail.save_draft(
                    inp["to"],
                    inp["subject"],
                    inp["body"],
                    cc=inp.get("cc"),
                    html=inp.get("html", False),
                ))

            elif name == "email_verify_sent":
                return self._r(mail.verify_sent(
                    inp["subject"],
                    inp.get("to"),
                ))

            # ── Search ──
            elif name == "email_search":
                return self._r(mail.search_emails(
                    keyword=inp.get("keyword", ""),
                    sender=inp.get("sender", ""),
                    subject=inp.get("subject", ""),
                    unread_only=inp.get("unread_only", False),
                    flagged_only=inp.get("flagged_only", False),
                    has_attachments=inp.get("has_attachments", False),
                    mailbox=inp.get("mailbox", "inbox"),
                    max_results=inp.get("max_results", 20),
                ))

            # ── Organize ──
            elif name == "email_delete":
                return self._r(mail.delete_message(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_archive":
                return self._r(mail.archive_message(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                ))

            elif name == "email_move":
                return self._r(mail.move_message(
                    inp.get("index", 1),
                    inp.get("from_mailbox", "inbox"),
                    inp["to_mailbox"],
                    inp.get("account"),
                ))

            elif name == "email_list_folders":
                return self._r(mail.list_mailboxes())

            elif name == "email_download_attachments":
                return self._r(mail.download_attachments(
                    inp.get("index", 1),
                    inp.get("mailbox", "inbox"),
                    inp.get("save_dir"),
                ))

            # ── Templates ──
            elif name == "email_template_save":
                return self._r(mail.save_template(
                    inp["name"],
                    inp["subject"],
                    inp["body"],
                    inp.get("html", False),
                ))

            elif name == "email_template_list":
                return self._r(mail.list_templates())

            elif name == "email_template_send":
                return self._r(mail.send_template(
                    inp["name"],
                    inp["to"],
                    inp.get("variables"),
                ))

            # ── Follow-ups ──
            elif name == "email_followup":
                return self._r(mail.add_followup(
                    inp["subject"],
                    inp["to"],
                    inp.get("deadline_hours", 48),
                    inp.get("reminder_text", ""),
                ))

            elif name == "email_check_followups":
                return self._r(mail.check_followups())

            # ── Contacts ──
            elif name == "email_contact_lookup":
                return self._r(mail.lookup_contact_email(inp["name"]))

            elif name == "email_contact_add":
                return self._r(mail.add_contact(inp["name"], inp["email"], inp.get("tags"), inp.get("notes", "")))

            elif name == "email_contact_list":
                return self._r(mail.list_contacts(inp.get("tag")))

            elif name == "email_contact_search":
                return self._r(mail.search_contacts(inp.get("query", inp.get("name", ""))))

            elif name == "email_contact_delete":
                return self._r(mail.delete_contact(inp.get("contact_id"), inp.get("email")))

            elif name == "email_auto_learn_contacts":
                return self._r(mail.auto_learn_contacts())

            # ── Stats ──
            elif name == "email_stats":
                return self._r(mail.get_email_stats())

            # ── Auto-Rules ──
            elif name == "email_add_rule":
                return self._r(mail.add_email_rule(
                    inp["name"], inp["conditions"], inp["actions"],
                    inp.get("enabled", True),
                ))

            elif name == "email_list_rules":
                return self._r(mail.list_email_rules())

            elif name == "email_delete_rule":
                return self._r(mail.delete_email_rule(inp["rule_id"]))

            elif name == "email_toggle_rule":
                return self._r(mail.toggle_email_rule(
                    inp["rule_id"], inp.get("enabled"),
                ))

            elif name == "email_run_rules":
                return self._r(mail.run_rules_on_inbox(inp.get("count", 20)))

            # ── Summarization & Threads ──
            elif name == "email_summarize":
                return self._r(mail.summarize_inbox(inp.get("count", 20)))

            elif name == "email_categorize":
                return self._r(mail.categorize_inbox(inp.get("count", 20)))

            elif name == "email_thread":
                return self._r(mail.get_email_thread(
                    inp["subject_or_index"],
                    inp.get("max_messages", 20),
                ))

            # ── Scheduling ──
            elif name == "email_schedule":
                return self._r(mail.schedule_email(
                    to=inp["to"], subject=inp["subject"], body=inp["body"],
                    send_at=inp["send_at"],
                    cc=inp.get("cc"), bcc=inp.get("bcc"),
                    attachment_paths=inp.get("attachment_paths"),
                    html=inp.get("html", False),
                ))

            elif name == "email_list_scheduled":
                return self._r(mail.list_scheduled())

            elif name == "email_cancel_scheduled":
                return self._r(mail.cancel_scheduled(inp["scheduled_id"]))

            # ── Batch Operations ──
            elif name == "email_batch_mark_read":
                return self._r(mail.batch_mark_read(
                    indices=inp.get("indices"),
                    mailbox=inp.get("mailbox", "inbox"),
                    all_unread=inp.get("all_unread", False),
                ))

            elif name == "email_batch_delete":
                return self._r(mail.batch_delete(
                    indices=inp.get("indices"),
                    mailbox=inp.get("mailbox", "inbox"),
                    sender=inp.get("sender"),
                ))

            elif name == "email_batch_move":
                return self._r(mail.batch_move(
                    indices=inp["indices"],
                    to_mailbox=inp["to_mailbox"],
                    from_mailbox=inp.get("from_mailbox", "inbox"),
                ))

            elif name == "email_batch_forward":
                return self._r(mail.batch_forward(
                    indices=inp["indices"],
                    to_address=inp["to"],
                    body=inp.get("body", ""),
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            # ── Smart Compose / Quick Replies ──
            elif name == "email_list_quick_replies":
                return self._r(mail.list_quick_replies())

            elif name == "email_send_quick_reply":
                return self._r(mail.send_quick_reply(
                    message_index=inp["message_index"],
                    reply_type=inp["reply_type"],
                    mailbox=inp.get("mailbox", "inbox"),
                    custom_note=inp.get("custom_note", ""),
                ))

            elif name == "email_suggest_replies":
                return self._r(mail.suggest_replies(
                    message_index=inp["message_index"],
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            # ── Snooze ──
            elif name == "email_snooze":
                return self._r(mail.snooze_email(
                    index=inp["index"],
                    snooze_until=inp["snooze_until"],
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            elif name == "email_list_snoozed":
                return self._r(mail.list_snoozed())

            elif name == "email_cancel_snooze":
                return self._r(mail.cancel_snooze(inp["snooze_id"]))

            # ── Priority & Digest ──
            elif name == "email_priority_inbox":
                return self._r(mail.priority_inbox(inp.get("count", 20)))

            elif name == "email_sender_profile":
                return self._r(mail.get_sender_profile(inp["query"]))

            elif name == "email_digest":
                return self._r(mail.generate_daily_digest())

            # ── OOO ──
            elif name == "set_ooo":
                return self._r(mail.set_ooo(
                    inp.get("start_date", "today"),
                    inp["end_date"],
                    inp["message"],
                    inp.get("exceptions", []),
                ))

            elif name == "cancel_ooo":
                return self._r(mail.cancel_ooo())

            elif name == "ooo_status":
                return self._r(mail.get_ooo_status())

            # ── Analytics ──
            elif name == "email_analytics":
                return self._r(mail.get_email_analytics(inp.get("period", "week")))

            elif name == "email_health":
                return self._r(mail.get_email_health())

            # ── Inbox Zero ──
            elif name == "clean_sweep":
                return self._r(mail.clean_sweep(
                    older_than_days=inp.get("older_than_days", 7),
                    categories=inp.get("categories"),
                    dry_run=inp.get("dry_run", True),
                ))

            elif name == "auto_triage":
                return self._r(mail.auto_triage(count=inp.get("count", 20)))

            elif name == "inbox_zero_status":
                return self._r(mail.inbox_zero_status())

            elif name == "smart_unsubscribe":
                return self._r(mail.smart_unsubscribe(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            # ── Attachments ──
            elif name == "build_attachment_index":
                return self._r(mail.build_attachment_index(
                    count=inp.get("count", 50),
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            elif name == "search_attachments":
                return self._r(mail.search_attachments(
                    filename=inp.get("filename"),
                    sender=inp.get("sender"),
                    file_type=inp.get("file_type"),
                    max_results=inp.get("max_results", 20),
                ))

            elif name == "attachment_summary":
                return self._r(mail.attachment_summary(count=inp.get("count", 50)))

            elif name == "list_saved_attachments":
                return self._r(mail.list_saved_attachments(
                    folder=inp.get("folder"),
                    file_type=inp.get("file_type"),
                ))

            # ── Contact Intelligence ──
            elif name == "score_relationships":
                return self._r(mail.score_relationships())

            elif name == "detect_vips":
                return self._r(mail.auto_detect_vips(threshold=inp.get("threshold", 70)))

            elif name == "relationship_report":
                return self._r(mail.get_relationship_report(
                    contact_query=inp.get("contact_query", ""),
                ))

            elif name == "communication_graph":
                return self._r(mail.communication_graph(top_n=inp.get("top_n", 15)))

            elif name == "decay_contacts":
                return self._r(mail.decay_stale_contacts(
                    inactive_days=inp.get("inactive_days", 90),
                ))

            # ── Phase 9: Security & Trust ──
            elif name == "scan_email_security":
                return self._r(mail.scan_email_security(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "check_sender_trust":
                return self._r(mail.check_sender_trust(
                    sender_email=inp.get("sender_email", ""),
                ))
            elif name == "scan_links":
                return self._r(mail.scan_links(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "security_report":
                return self._r(mail.get_security_report(count=inp.get("count", 20)))
            elif name == "add_trusted_sender":
                return self._r(mail.add_trusted_sender(
                    email_or_domain=inp.get("email_or_domain", ""),
                    reason=inp.get("reason", ""),
                ))
            elif name == "add_blocked_sender":
                return self._r(mail.add_blocked_sender(
                    email_or_domain=inp.get("email_or_domain", ""),
                    reason=inp.get("reason", ""),
                ))
            elif name == "list_trusted_senders":
                return self._r(mail.list_trusted_senders())
            elif name == "list_blocked_senders":
                return self._r(mail.list_blocked_senders())

            # ── Phase 9: Action Items & Meetings ──
            elif name == "extract_action_items":
                return self._r(mail.extract_action_items(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "extract_meeting_details":
                return self._r(mail.extract_meeting_details(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "scan_inbox_actions":
                return self._r(mail.scan_inbox_actions(count=inp.get("count", 20)))
            elif name == "create_reminder":
                return self._r(mail.create_reminder_from_email(
                    title=inp.get("title", ""),
                    due_date=inp.get("due_date"),
                    notes=inp.get("notes", ""),
                    source_email_subject=inp.get("source_email_subject", ""),
                ))
            elif name == "create_calendar_event":
                return self._r(mail.create_calendar_event(
                    title=inp.get("title", ""),
                    start_datetime=inp.get("start_datetime", ""),
                    end_datetime=inp.get("end_datetime"),
                    location=inp.get("location", ""),
                    notes=inp.get("notes", ""),
                ))
            elif name == "list_actions":
                return self._r(mail.list_extracted_actions(status=inp.get("status", "all")))
            elif name == "complete_action":
                return self._r(mail.complete_action(action_id=inp.get("action_id", "")))
            elif name == "action_summary":
                return self._r(mail.get_action_summary())

            # ── Phase 9: Workflow Chains ──
            elif name == "create_workflow":
                return self._r(mail.create_workflow(
                    name=inp.get("workflow_name", ""),
                    trigger=inp.get("trigger", {}),
                    steps=inp.get("steps", []),
                    enabled=inp.get("enabled", True),
                ))
            elif name == "list_workflows":
                return self._r(mail.list_workflows())
            elif name == "get_workflow":
                return self._r(mail.get_workflow(workflow_id=inp.get("workflow_id", "")))
            elif name == "delete_workflow":
                return self._r(mail.delete_workflow(workflow_id=inp.get("workflow_id", "")))
            elif name == "toggle_workflow":
                return self._r(mail.toggle_workflow(
                    workflow_id=inp.get("workflow_id", ""),
                    enabled=inp.get("enabled"),
                ))
            elif name == "run_workflow":
                return self._r(mail.run_workflow_manual(
                    workflow_id=inp.get("workflow_id", ""),
                    email_index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "workflow_templates":
                return self._r(mail.get_workflow_templates())
            elif name == "create_from_template":
                return self._r(mail.create_workflow_from_template(
                    template_name=inp.get("template_name", ""),
                    params=inp.get("template_params"),
                ))
            elif name == "workflow_history":
                return self._r(mail.get_workflow_history(
                    workflow_id=inp.get("workflow_id"),
                    limit=inp.get("limit", 20),
                ))

            # ── Phase 10: Smart Compose & Writing ──
            elif name == "smart_compose":
                return self._r(mail.smart_compose(
                    prompt=inp.get("prompt", ""),
                    tone=inp.get("tone", "formal"),
                    style=inp.get("style", "concise"),
                    context_email=inp.get("context_email"),
                    recipient=inp.get("recipient"),
                ))
            elif name == "rewrite_email":
                return self._r(mail.rewrite_email(
                    text=inp.get("text", ""),
                    tone=inp.get("tone", "formal"),
                    style=inp.get("style"),
                ))
            elif name == "adjust_tone":
                return self._r(mail.adjust_tone(
                    text=inp.get("text", ""),
                    tone=inp.get("tone", "formal"),
                ))
            elif name == "suggest_subject_lines":
                return self._r(mail.suggest_subject_lines(
                    text=inp.get("text", ""),
                ))
            elif name == "proofread_email":
                return self._r(mail.proofread_email(
                    text=inp.get("text", ""),
                ))
            elif name == "compose_reply_draft":
                return self._r(mail.compose_reply_draft(
                    index=inp.get("index", 1),
                    instructions=inp.get("instructions", ""),
                    tone=inp.get("tone", "formal"),
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            # ── Phase 10: Delegation ──
            elif name == "delegate_email":
                return self._r(mail.delegate_email(
                    index=inp.get("index", 1),
                    delegate_to=inp.get("delegate_to", ""),
                    instructions=inp.get("instructions", ""),
                    deadline_hours=inp.get("deadline_hours", 24),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "list_delegations":
                return self._r(mail.list_delegations(
                    status=inp.get("status"),
                ))
            elif name == "update_delegation":
                return self._r(mail.update_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                    status=inp.get("status"),
                    notes=inp.get("notes"),
                ))
            elif name == "complete_delegation":
                return self._r(mail.complete_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                    outcome=inp.get("outcome", ""),
                ))
            elif name == "cancel_delegation":
                return self._r(mail.cancel_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                    reason=inp.get("reason", ""),
                ))
            elif name == "delegation_dashboard":
                return self._r(mail.delegation_dashboard())
            elif name == "nudge_delegation":
                return self._r(mail.nudge_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                ))

            # ── Phase 10: Contextual Search ──
            elif name == "contextual_search":
                return self._r(mail.contextual_search(
                    query=inp.get("query", ""),
                    max_results=inp.get("max_results", 20),
                ))
            elif name == "build_search_index":
                return self._r(mail.build_search_index(
                    count=inp.get("count", 100),
                ))
            elif name == "conversation_recall":
                return self._r(mail.conversation_recall(
                    contact_query=inp.get("contact_query", ""),
                    summarize=inp.get("summarize", False),
                    max_results=inp.get("max_results", 20),
                ))
            elif name == "search_by_date_range":
                return self._r(mail.search_by_date_range(
                    start_date=inp.get("start_date", ""),
                    end_date=inp.get("end_date", ""),
                    keyword=inp.get("keyword"),
                    max_results=inp.get("max_results", 20),
                ))
            elif name == "find_related_emails":
                return self._r(mail.find_related_emails(
                    index=inp.get("index", 1),
                    max_results=inp.get("max_results", 10),
                    mailbox=inp.get("mailbox", "inbox"),
                ))

            # ── Phase 11A: Sentiment Analysis ──
            elif name == "analyze_sentiment":
                return self._r(mail.analyze_sentiment(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "batch_sentiment":
                return self._r(mail.batch_sentiment(
                    count=inp.get("count", 20),
                    mailbox=inp.get("mailbox", "inbox"),
                ))
            elif name == "sender_sentiment":
                return self._r(mail.sender_sentiment(
                    sender_email=inp.get("sender_email", ""),
                ))
            elif name == "sentiment_alerts":
                return self._r(mail.sentiment_alerts(
                    threshold=inp.get("threshold", -20),
                ))
            elif name == "sentiment_report":
                return self._r(mail.sentiment_report(
                    period=inp.get("period", "week"),
                ))

            # ── Phase 11B: Smart Folders ──
            elif name == "create_smart_folder":
                return self._r(mail.create_smart_folder(
                    name=inp.get("name", ""),
                    criteria=inp.get("criteria", {}),
                    pinned=inp.get("pinned", False),
                ))
            elif name == "list_smart_folders":
                return self._r(mail.list_smart_folders())
            elif name == "get_smart_folder":
                return self._r(mail.get_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    max_results=inp.get("max_results", 20),
                ))
            elif name == "update_smart_folder":
                return self._r(mail.update_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    name=inp.get("name"),
                    criteria=inp.get("criteria"),
                ))
            elif name == "delete_smart_folder":
                return self._r(mail.delete_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                ))
            elif name == "pin_smart_folder":
                return self._r(mail.pin_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    pinned=inp.get("pinned", True),
                ))

            # ── Phase 11C: Thread Summarization ──
            elif name == "summarize_thread":
                return self._r(mail.summarize_thread(
                    subject_or_index=inp.get("subject_or_index", ""),
                    max_messages=inp.get("max_messages", 20),
                ))
            elif name == "thread_decisions":
                return self._r(mail.thread_decisions(
                    subject_or_index=inp.get("subject_or_index", ""),
                    max_messages=inp.get("max_messages", 20),
                ))
            elif name == "thread_participants":
                return self._r(mail.thread_participants(
                    subject_or_index=inp.get("subject_or_index", ""),
                    max_messages=inp.get("max_messages", 20),
                ))
            elif name == "thread_timeline":
                return self._r(mail.thread_timeline(
                    subject_or_index=inp.get("subject_or_index", ""),
                    max_messages=inp.get("max_messages", 20),
                ))
            elif name == "prepare_forward_summary":
                return self._r(mail.prepare_forward_summary(
                    subject_or_index=inp.get("subject_or_index", ""),
                    recipient=inp.get("recipient"),
                    max_messages=inp.get("max_messages", 20),
                ))

            # ── Phase 12A: Labels & Tags ──
            elif name == "add_label":
                return self._r(mail.add_label(index=inp.get("index", 1), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox")))
            elif name == "remove_label":
                return self._r(mail.remove_label(index=inp.get("index", 1), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox")))
            elif name == "list_labels":
                return self._r(mail.list_labels())
            elif name == "get_labeled_emails":
                return self._r(mail.get_labeled_emails(label=inp.get("label", ""), max_results=inp.get("max_results", 20)))
            elif name == "bulk_label":
                return self._r(mail.bulk_label(indices=inp.get("indices", []), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox")))

            # ── Phase 12B: Newsletter Management ──
            elif name == "detect_newsletters":
                return self._r(mail.detect_newsletters(count=inp.get("count", 30), mailbox=inp.get("mailbox", "inbox")))
            elif name == "newsletter_digest":
                return self._r(mail.newsletter_digest(count=inp.get("count", 20), mailbox=inp.get("mailbox", "inbox")))
            elif name == "newsletter_stats":
                return self._r(mail.newsletter_stats())
            elif name == "newsletter_preferences":
                return self._r(mail.newsletter_preferences(sender=inp.get("sender", ""), action=inp.get("pref_action", "keep")))
            elif name == "apply_newsletter_preferences":
                return self._r(mail.apply_newsletter_preferences(count=inp.get("count", 30), mailbox=inp.get("mailbox", "inbox"), dry_run=inp.get("dry_run", True)))

            # ── Phase 12C: Auto-Responder ──
            elif name == "create_auto_response":
                return self._r(mail.create_auto_response(
                    name=inp.get("name", ""), conditions=inp.get("conditions", {}),
                    response_body=inp.get("response_body", ""), response_subject=inp.get("response_subject"),
                    enabled=inp.get("enabled", True), max_replies=inp.get("max_replies", 1),
                ))
            elif name == "list_auto_responses":
                return self._r(mail.list_auto_responses())
            elif name == "update_auto_response":
                return self._r(mail.update_auto_response(
                    rule_id=inp.get("rule_id", ""), name=inp.get("name"),
                    conditions=inp.get("conditions"), response_body=inp.get("response_body"),
                    max_replies=inp.get("max_replies"),
                ))
            elif name == "delete_auto_response":
                return self._r(mail.delete_auto_response(rule_id=inp.get("rule_id", "")))
            elif name == "toggle_auto_response":
                return self._r(mail.toggle_auto_response(rule_id=inp.get("rule_id", ""), enabled=inp.get("enabled")))
            elif name == "auto_response_history":
                return self._r(mail.auto_response_history(limit=inp.get("limit", 20)))

            # ── Phase 13A: Signatures ──
            elif name == "create_signature":
                return self._r(mail.create_signature(name=inp.get("name", ""), body=inp.get("body", ""), is_html=inp.get("is_html", False)))
            elif name == "list_signatures":
                return self._r(mail.list_signatures())
            elif name == "update_signature":
                return self._r(mail.update_signature(sig_id=inp.get("sig_id", ""), name=inp.get("name"), body=inp.get("body"), is_html=inp.get("is_html")))
            elif name == "delete_signature":
                return self._r(mail.delete_signature(sig_id=inp.get("sig_id", "")))
            elif name == "set_default_signature":
                return self._r(mail.set_default_signature(sig_id=inp.get("sig_id", "")))
            elif name == "get_signature":
                return self._r(mail.get_signature(sig_id=inp.get("sig_id")))

            # ── Phase 13B: Aliases / Identities ──
            elif name == "add_alias":
                return self._r(mail.add_alias(email=inp.get("alias_email", ""), display_name=inp.get("display_name", ""), signature_id=inp.get("sig_id")))
            elif name == "list_aliases":
                return self._r(mail.list_aliases())
            elif name == "update_alias":
                return self._r(mail.update_alias(alias_id=inp.get("alias_id", ""), email=inp.get("alias_email"), display_name=inp.get("display_name"), signature_id=inp.get("sig_id")))
            elif name == "delete_alias":
                return self._r(mail.delete_alias(alias_id=inp.get("alias_id", "")))
            elif name == "set_default_alias":
                return self._r(mail.set_default_alias(alias_id=inp.get("alias_id", "")))

            # ── Phase 13C: Export / Archival ──
            elif name == "export_emails":
                return self._r(mail.export_emails(count=inp.get("count", 10), mailbox=inp.get("mailbox", "inbox"), format=inp.get("export_format", "json")))
            elif name == "export_thread":
                return self._r(mail.export_thread(subject_or_index=inp.get("subject_or_index", ""), format=inp.get("export_format", "json")))
            elif name == "backup_mailbox":
                return self._r(mail.backup_mailbox(mailbox=inp.get("mailbox", "inbox"), max_emails=inp.get("max_emails", 100)))
            elif name == "list_backups":
                return self._r(mail.list_backups())
            elif name == "search_exports":
                return self._r(mail.search_exports(keyword=inp.get("keyword", "")))
            elif name == "export_stats":
                return self._r(mail.get_export_stats())

            # ── Phase 14: Templates ──
            elif name == "create_template":
                return self._r(mail.create_template(name=inp.get("name", ""), subject_template=inp.get("subject_template", ""), body_template=inp.get("body_template", ""), category=inp.get("category", "general")))
            elif name == "list_templates":
                return self._r(mail.list_templates(category=inp.get("category")))
            elif name == "get_template":
                return self._r(mail.get_template(template_id=inp.get("template_id", "")))
            elif name == "update_template":
                return self._r(mail.update_template(template_id=inp.get("template_id", ""), name=inp.get("name"), subject_template=inp.get("subject_template"), body_template=inp.get("body_template"), category=inp.get("category")))
            elif name == "delete_template":
                return self._r(mail.delete_template(template_id=inp.get("template_id", "")))
            elif name == "use_template":
                return self._r(mail.use_template(template_id=inp.get("template_id", ""), variables=inp.get("variables", {})))

            # ── Phase 15: Drafts Management ──
            elif name == "save_draft":
                return self._r(mail.save_draft(to=inp.get("to", ""), subject=inp.get("subject", ""), body=inp.get("body", ""), cc=inp.get("cc"), bcc=inp.get("bcc")))
            elif name == "list_drafts_managed":
                return self._r(mail.list_drafts())
            elif name == "get_draft":
                return self._r(mail.get_draft(draft_id=inp.get("draft_id", "")))
            elif name == "update_draft":
                return self._r(mail.update_draft(draft_id=inp.get("draft_id", ""), to=inp.get("to"), subject=inp.get("subject"), body=inp.get("body"), cc=inp.get("cc"), bcc=inp.get("bcc")))
            elif name == "delete_draft":
                return self._r(mail.delete_draft(draft_id=inp.get("draft_id", "")))

            # ── Phase 16: Folder Management ──
            elif name == "create_mail_folder":
                return self._r(mail.create_mail_folder(folder_name=inp.get("folder_name", ""), parent=inp.get("parent")))
            elif name == "list_mail_folders":
                return self._r(mail.list_mail_folders())
            elif name == "rename_mail_folder":
                return self._r(mail.rename_mail_folder(folder_name=inp.get("folder_name", ""), new_name=inp.get("new_name", "")))
            elif name == "delete_mail_folder":
                return self._r(mail.delete_mail_folder(folder_name=inp.get("folder_name", "")))
            elif name == "move_to_folder":
                return self._r(mail.move_to_folder(email_index=inp.get("index", 1), folder_name=inp.get("folder_name", "")))
            elif name == "get_folder_stats":
                return self._r(mail.get_folder_stats())

            # ── Phase 17: Email Tracking ──
            elif name == "track_email":
                return self._r(mail.track_email(subject=inp.get("subject", ""), recipient=inp.get("recipient"), sent_at=inp.get("sent_at")))
            elif name == "list_tracked_emails":
                return self._r(mail.list_tracked_emails())
            elif name == "get_tracking_status":
                return self._r(mail.get_tracking_status(tracking_id=inp.get("tracking_id", "")))
            elif name == "tracking_report":
                return self._r(mail.tracking_report())
            elif name == "untrack_email":
                return self._r(mail.untrack_email(tracking_id=inp.get("tracking_id", "")))

            # ── Phase 18: Extended Batch Ops ──
            elif name == "batch_archive":
                return self._r(mail.batch_archive(indices=inp.get("indices", [])))
            elif name == "batch_reply":
                return self._r(mail.batch_reply(indices=inp.get("indices", []), reply_body=inp.get("body", "")))

            # ── Phase 19: Calendar Integration ──
            elif name == "email_to_event":
                return self._r(mail.email_to_event(email_index=inp.get("index", 1), calendar_name=inp.get("calendar_name")))
            elif name == "list_email_events":
                return self._r(mail.list_email_events())
            elif name == "upcoming_from_email":
                return self._r(mail.upcoming_from_email(days=inp.get("days", 7)))
            elif name == "meeting_conflicts":
                return self._r(mail.meeting_conflicts(date=inp.get("date")))
            elif name == "sync_email_calendar":
                return self._r(mail.sync_email_calendar())

            # ── Phase 20: Dashboard & Reporting ──
            elif name == "email_dashboard":
                return self._r(mail.email_dashboard())
            elif name == "weekly_report":
                return self._r(mail.weekly_report())
            elif name == "monthly_report":
                return self._r(mail.monthly_report())
            elif name == "productivity_score":
                return self._r(mail.productivity_score())
            elif name == "email_trends":
                return self._r(mail.email_trends(days=inp.get("days", 30)))

            return f"Unknown email tool: {name}"
        except Exception as e:
            return f"ERROR: {e}"

    def _r(self, result):
        """Extract content from result dict."""
        if isinstance(result, dict):
            return result.get("content", str(result))
        return str(result)
