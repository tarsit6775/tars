"""
Phases 14-20 Tests — Templates, Drafts, Folders, Tracking, Batch Ops,
Calendar Integration, Dashboard & Reporting.
35 new functions across 7 phases.

Run: pytest tests/test_email_phases14_20.py -v
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hands.email import (
    # Phase 14: Templates
    create_template, get_template, update_template,
    delete_template, use_template,
    # Phase 15: Drafts Management (the new managed versions at bottom of file)
    save_draft, get_draft, update_draft, delete_draft,
    # Phase 16: Folder Management
    create_mail_folder, list_mail_folders, rename_mail_folder,
    delete_mail_folder, move_to_folder, get_folder_stats,
    # Phase 17: Email Tracking
    track_email, list_tracked_emails, get_tracking_status,
    tracking_report, untrack_email,
    # Phase 18: Extended Batch Ops
    batch_archive, batch_reply, batch_label,
    # Phase 19: Calendar Integration
    email_to_event, list_email_events, upcoming_from_email,
    meeting_conflicts, sync_email_calendar,
    # Phase 20: Dashboard & Reporting
    email_dashboard, weekly_report, monthly_report,
    productivity_score, email_trends,
    # Persistence paths
    TEMPLATES_PATH, DRAFTS_PATH, FOLDERS_PATH,
    TRACKING_PATH, CALENDAR_PATH,
)

# We import list_templates separately since there are two definitions
# (Phase 1 and Phase 14). The Phase 14 version shadows Phase 1.
from hands.email import list_templates


# ═══════════════════════════════════════════════════════════════════
#  PHASE 14: EMAIL TEMPLATES
# ═══════════════════════════════════════════════════════════════════

class TestPhase14Imports(unittest.TestCase):
    """Verify all Phase 14 functions are importable."""

    def test_create_template_callable(self):
        self.assertTrue(callable(create_template))

    def test_list_templates_callable(self):
        self.assertTrue(callable(list_templates))

    def test_get_template_callable(self):
        self.assertTrue(callable(get_template))

    def test_update_template_callable(self):
        self.assertTrue(callable(update_template))

    def test_delete_template_callable(self):
        self.assertTrue(callable(delete_template))

    def test_use_template_callable(self):
        self.assertTrue(callable(use_template))


class TestPhase14Paths(unittest.TestCase):
    def test_templates_path(self):
        self.assertIn("email_templates", TEMPLATES_PATH)


class TestPhase14Logic(unittest.TestCase):
    """Template CRUD + render logic."""

    def setUp(self):
        self.backup = None
        if os.path.exists(TEMPLATES_PATH):
            with open(TEMPLATES_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(TEMPLATES_PATH):
            os.remove(TEMPLATES_PATH)

    def tearDown(self):
        if self.backup is not None:
            with open(TEMPLATES_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(TEMPLATES_PATH):
            os.remove(TEMPLATES_PATH)

    # ── Create ──
    def test_create_template_missing_name(self):
        r = create_template(name="", body_template="hello")
        self.assertFalse(r["success"])

    def test_create_template_missing_body(self):
        r = create_template(name="Test", body_template="")
        self.assertFalse(r["success"])

    def test_create_template_success(self):
        r = create_template(name="Welcome", subject_template="Hi {{name}}", body_template="Hello {{name}}, welcome!")
        self.assertTrue(r["success"])
        self.assertIn("tmpl_", r["content"])
        self.assertIn("name", r["content"])  # variable listed

    def test_create_template_with_category(self):
        r = create_template(name="Invoice", body_template="Pay {{amount}}", category="billing")
        self.assertTrue(r["success"])
        self.assertIn("Invoice", r["content"])

    def test_create_template_no_variables(self):
        r = create_template(name="Plain", body_template="No variables here")
        self.assertTrue(r["success"])
        self.assertIn("none", r["content"].lower())

    # ── List ──
    def test_list_templates_empty(self):
        r = list_templates()
        self.assertTrue(r["success"])
        self.assertIn("No templates", r["content"])

    def test_list_templates_after_create(self):
        create_template(name="T1", body_template="body1")
        r = list_templates()
        self.assertTrue(r["success"])
        self.assertIn("T1", r["content"])
        self.assertIn("1", r["content"])  # count

    def test_list_templates_category_filter(self):
        create_template(name="A", body_template="a", category="work")
        create_template(name="B", body_template="b", category="personal")
        r = list_templates(category="work")
        self.assertTrue(r["success"])
        self.assertIn("A", r["content"])
        self.assertNotIn("B", r["content"])

    # ── Get ──
    def test_get_template_missing_id(self):
        r = get_template(template_id="")
        self.assertFalse(r["success"])

    def test_get_template_not_found(self):
        r = get_template(template_id="tmpl_ghost")
        self.assertFalse(r["success"])

    def test_get_template_success(self):
        c = create_template(name="Fetch Me", subject_template="Subj {{x}}", body_template="Body {{x}}")
        tid = _extract_id(c["content"], "tmpl_")
        r = get_template(template_id=tid)
        self.assertTrue(r["success"])
        self.assertIn("Fetch Me", r["content"])
        self.assertIn("x", r["content"])

    # ── Update ──
    def test_update_template_not_found(self):
        r = update_template(template_id="tmpl_nope", name="New")
        self.assertFalse(r["success"])

    def test_update_template_success(self):
        c = create_template(name="Old", body_template="old body")
        tid = _extract_id(c["content"], "tmpl_")
        r = update_template(template_id=tid, name="New", body_template="new body {{y}}")
        self.assertTrue(r["success"])
        self.assertIn("updated", r["content"].lower())
        # Verify update persisted
        g = get_template(template_id=tid)
        self.assertIn("New", g["content"])
        self.assertIn("y", g["content"])

    # ── Delete ──
    def test_delete_template_not_found(self):
        r = delete_template(template_id="tmpl_gone")
        self.assertFalse(r["success"])

    def test_delete_template_success(self):
        c = create_template(name="Delete Me", body_template="bye")
        tid = _extract_id(c["content"], "tmpl_")
        r = delete_template(template_id=tid)
        self.assertTrue(r["success"])
        self.assertIn("deleted", r["content"].lower())
        # Verify gone
        g = get_template(template_id=tid)
        self.assertFalse(g["success"])

    # ── Use / Render ──
    def test_use_template_missing_id(self):
        r = use_template(template_id="")
        self.assertFalse(r["success"])

    def test_use_template_not_found(self):
        r = use_template(template_id="tmpl_nah")
        self.assertFalse(r["success"])

    def test_use_template_render(self):
        c = create_template(name="Greet", subject_template="Hello {{name}}", body_template="Dear {{name}}, re: {{topic}}")
        tid = _extract_id(c["content"], "tmpl_")
        r = use_template(template_id=tid, variables={"name": "Alice", "topic": "Project X"})
        self.assertTrue(r["success"])
        self.assertIn("Alice", r["content"])
        self.assertIn("Project X", r["content"])
        self.assertNotIn("{{name}}", r["content"])

    def test_use_template_increments_count(self):
        c = create_template(name="Counter", body_template="test")
        tid = _extract_id(c["content"], "tmpl_")
        use_template(template_id=tid)
        use_template(template_id=tid)
        r = list_templates()
        self.assertIn("2x", r["content"])

    def test_use_template_no_variables(self):
        c = create_template(name="Static", body_template="no vars")
        tid = _extract_id(c["content"], "tmpl_")
        r = use_template(template_id=tid, variables={})
        self.assertTrue(r["success"])
        self.assertIn("no vars", r["content"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 15: EMAIL DRAFTS MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

class TestPhase15Imports(unittest.TestCase):
    def test_save_draft_callable(self):
        self.assertTrue(callable(save_draft))

    def test_get_draft_callable(self):
        self.assertTrue(callable(get_draft))

    def test_update_draft_callable(self):
        self.assertTrue(callable(update_draft))

    def test_delete_draft_callable(self):
        self.assertTrue(callable(delete_draft))


class TestPhase15Paths(unittest.TestCase):
    def test_drafts_path(self):
        self.assertIn("email_drafts", DRAFTS_PATH)


class TestPhase15Logic(unittest.TestCase):
    """Managed drafts CRUD."""

    def setUp(self):
        self.backup = None
        if os.path.exists(DRAFTS_PATH):
            with open(DRAFTS_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(DRAFTS_PATH):
            os.remove(DRAFTS_PATH)

    def tearDown(self):
        if self.backup is not None:
            with open(DRAFTS_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(DRAFTS_PATH):
            os.remove(DRAFTS_PATH)

    # ── Save ──
    def test_save_draft_empty(self):
        r = save_draft(to="", subject="", body="")
        self.assertFalse(r["success"])

    def test_save_draft_success(self):
        r = save_draft(to="test@example.com", subject="Test Draft", body="Hello")
        self.assertTrue(r["success"])
        self.assertIn("draft_", r["content"])

    def test_save_draft_minimal(self):
        r = save_draft(body="Just a body")
        self.assertTrue(r["success"])

    # ── List ──
    def test_list_drafts_empty(self):
        # The Phase 15 list_drafts shadows Phase 1's. Just call it.
        from hands.email import list_drafts as list_drafts_managed
        r = list_drafts_managed()
        self.assertTrue(r["success"])
        # Could be "No drafts" or could show Mail.app drafts depending on which is called
        # Phase 15 version returns from JSON store
        self.assertIsInstance(r["content"], str)

    def test_list_drafts_after_save(self):
        save_draft(to="a@b.com", subject="S1", body="B1")
        from hands.email import list_drafts as list_drafts_managed
        r = list_drafts_managed()
        self.assertTrue(r["success"])
        self.assertIn("S1", r["content"])

    # ── Get ──
    def test_get_draft_missing_id(self):
        r = get_draft(draft_id="")
        self.assertFalse(r["success"])

    def test_get_draft_not_found(self):
        r = get_draft(draft_id="draft_nope")
        self.assertFalse(r["success"])

    def test_get_draft_success(self):
        c = save_draft(to="x@y.com", subject="Draft Test", body="Content here")
        did = _extract_id(c["content"], "draft_")
        r = get_draft(draft_id=did)
        self.assertTrue(r["success"])
        self.assertIn("x@y.com", r["content"])
        self.assertIn("Draft Test", r["content"])

    # ── Update ──
    def test_update_draft_not_found(self):
        r = update_draft(draft_id="draft_ghost")
        self.assertFalse(r["success"])

    def test_update_draft_success(self):
        c = save_draft(to="old@test.com", subject="Old Subj", body="Old Body")
        did = _extract_id(c["content"], "draft_")
        r = update_draft(draft_id=did, to="new@test.com", subject="New Subj")
        self.assertTrue(r["success"])
        self.assertIn("updated", r["content"].lower())
        g = get_draft(draft_id=did)
        self.assertIn("new@test.com", g["content"])

    # ── Delete ──
    def test_delete_draft_not_found(self):
        r = delete_draft(draft_id="draft_nope")
        self.assertFalse(r["success"])

    def test_delete_draft_success(self):
        c = save_draft(to="del@test.com", subject="Delete", body="Gone")
        did = _extract_id(c["content"], "draft_")
        r = delete_draft(draft_id=did)
        self.assertTrue(r["success"])
        self.assertIn("deleted", r["content"].lower())
        g = get_draft(draft_id=did)
        self.assertFalse(g["success"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 16: FOLDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

class TestPhase16Imports(unittest.TestCase):
    def test_create_mail_folder_callable(self):
        self.assertTrue(callable(create_mail_folder))

    def test_list_mail_folders_callable(self):
        self.assertTrue(callable(list_mail_folders))

    def test_rename_mail_folder_callable(self):
        self.assertTrue(callable(rename_mail_folder))

    def test_delete_mail_folder_callable(self):
        self.assertTrue(callable(delete_mail_folder))

    def test_move_to_folder_callable(self):
        self.assertTrue(callable(move_to_folder))

    def test_get_folder_stats_callable(self):
        self.assertTrue(callable(get_folder_stats))


class TestPhase16Paths(unittest.TestCase):
    def test_folders_path(self):
        self.assertIn("email_folders", FOLDERS_PATH)


class TestPhase16Validation(unittest.TestCase):
    """Test input validation (no AppleScript calls)."""

    def test_create_folder_missing_name(self):
        r = create_mail_folder(folder_name="")
        self.assertFalse(r["success"])

    def test_rename_folder_missing_params(self):
        r = rename_mail_folder(folder_name="", new_name="")
        self.assertFalse(r["success"])

    def test_delete_folder_missing_name(self):
        r = delete_mail_folder(folder_name="")
        self.assertFalse(r["success"])

    def test_move_to_folder_missing_name(self):
        r = move_to_folder(email_index=1, folder_name="")
        self.assertFalse(r["success"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 17: EMAIL TRACKING
# ═══════════════════════════════════════════════════════════════════

class TestPhase17Imports(unittest.TestCase):
    def test_track_email_callable(self):
        self.assertTrue(callable(track_email))

    def test_list_tracked_callable(self):
        self.assertTrue(callable(list_tracked_emails))

    def test_get_tracking_status_callable(self):
        self.assertTrue(callable(get_tracking_status))

    def test_tracking_report_callable(self):
        self.assertTrue(callable(tracking_report))

    def test_untrack_email_callable(self):
        self.assertTrue(callable(untrack_email))


class TestPhase17Paths(unittest.TestCase):
    def test_tracking_path(self):
        self.assertIn("email_tracking", TRACKING_PATH)


class TestPhase17Logic(unittest.TestCase):
    """Tracking CRUD + report logic."""

    def setUp(self):
        self.backup = None
        if os.path.exists(TRACKING_PATH):
            with open(TRACKING_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(TRACKING_PATH):
            os.remove(TRACKING_PATH)

    def tearDown(self):
        if self.backup is not None:
            with open(TRACKING_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(TRACKING_PATH):
            os.remove(TRACKING_PATH)

    # ── Track ──
    def test_track_missing_subject(self):
        r = track_email(subject="")
        self.assertFalse(r["success"])

    def test_track_success(self):
        r = track_email(subject="Important Email", recipient="boss@corp.com")
        self.assertTrue(r["success"])
        self.assertIn("trk_", r["content"])

    def test_track_with_sent_at(self):
        r = track_email(subject="Timed", sent_at="2026-02-15T10:00:00")
        self.assertTrue(r["success"])

    # ── List ──
    def test_list_tracked_empty(self):
        r = list_tracked_emails()
        self.assertTrue(r["success"])
        self.assertIn("No tracked", r["content"])

    def test_list_tracked_after_track(self):
        track_email(subject="Track Me", recipient="test@test.com")
        r = list_tracked_emails()
        self.assertTrue(r["success"])
        self.assertIn("Track Me", r["content"])
        self.assertIn("awaiting", r["content"])

    # ── Get Status ──
    def test_get_status_missing_id(self):
        r = get_tracking_status(tracking_id="")
        self.assertFalse(r["success"])

    def test_get_status_not_found(self):
        r = get_tracking_status(tracking_id="trk_gone")
        self.assertFalse(r["success"])

    def test_get_status_success(self):
        c = track_email(subject="Status Check", recipient="r@x.com")
        tid = _extract_id(c["content"], "trk_")
        r = get_tracking_status(tracking_id=tid)
        self.assertTrue(r["success"])
        self.assertIn("Status Check", r["content"])
        self.assertIn("Elapsed", r["content"])

    # ── Report ──
    def test_report_empty(self):
        r = tracking_report()
        self.assertTrue(r["success"])
        self.assertIn("No tracking", r["content"])

    def test_report_with_data(self):
        track_email(subject="A", recipient="a@a.com")
        track_email(subject="B", recipient="b@b.com")
        r = tracking_report()
        self.assertTrue(r["success"])
        self.assertIn("Total tracked: 2", r["content"])
        self.assertIn("Pending: 2", r["content"])

    # ── Untrack ──
    def test_untrack_missing_id(self):
        r = untrack_email(tracking_id="")
        self.assertFalse(r["success"])

    def test_untrack_not_found(self):
        r = untrack_email(tracking_id="trk_nah")
        self.assertFalse(r["success"])

    def test_untrack_success(self):
        c = track_email(subject="Remove Me", recipient="r@r.com")
        tid = _extract_id(c["content"], "trk_")
        r = untrack_email(tracking_id=tid)
        self.assertTrue(r["success"])
        self.assertIn("Stopped", r["content"])
        # Verify removed
        g = get_tracking_status(tracking_id=tid)
        self.assertFalse(g["success"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 18: EXTENDED BATCH OPERATIONS
# ═══════════════════════════════════════════════════════════════════

class TestPhase18Imports(unittest.TestCase):
    def test_batch_archive_callable(self):
        self.assertTrue(callable(batch_archive))

    def test_batch_reply_callable(self):
        self.assertTrue(callable(batch_reply))

    def test_batch_label_callable(self):
        self.assertTrue(callable(batch_label))


class TestPhase18Validation(unittest.TestCase):
    """Test input validation (no AppleScript calls)."""

    def test_batch_archive_no_indices(self):
        r = batch_archive(indices=None)
        self.assertFalse(r["success"])

    def test_batch_archive_empty_list(self):
        r = batch_archive(indices=[])
        self.assertFalse(r["success"])

    def test_batch_reply_no_indices(self):
        r = batch_reply(indices=None, body="test")
        self.assertFalse(r["success"])

    def test_batch_reply_no_body(self):
        r = batch_reply(indices=[1, 2], body="")
        self.assertFalse(r["success"])

    def test_batch_label_no_indices(self):
        r = batch_label(indices=None, label="test")
        self.assertFalse(r["success"])

    def test_batch_label_no_label(self):
        r = batch_label(indices=[1], label="")
        self.assertFalse(r["success"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 19: CALENDAR INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestPhase19Imports(unittest.TestCase):
    def test_email_to_event_callable(self):
        self.assertTrue(callable(email_to_event))

    def test_list_email_events_callable(self):
        self.assertTrue(callable(list_email_events))

    def test_upcoming_from_email_callable(self):
        self.assertTrue(callable(upcoming_from_email))

    def test_meeting_conflicts_callable(self):
        self.assertTrue(callable(meeting_conflicts))

    def test_sync_email_calendar_callable(self):
        self.assertTrue(callable(sync_email_calendar))


class TestPhase19Paths(unittest.TestCase):
    def test_calendar_path(self):
        self.assertIn("email_calendar", CALENDAR_PATH)


class TestPhase19Logic(unittest.TestCase):
    """Calendar integration logic."""

    def setUp(self):
        self.backup = None
        if os.path.exists(CALENDAR_PATH):
            with open(CALENDAR_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(CALENDAR_PATH):
            os.remove(CALENDAR_PATH)

    def tearDown(self):
        if self.backup is not None:
            with open(CALENDAR_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(CALENDAR_PATH):
            os.remove(CALENDAR_PATH)

    def test_list_events_empty(self):
        r = list_email_events()
        self.assertTrue(r["success"])
        self.assertIn("No email", r["content"])

    def test_upcoming_empty(self):
        r = upcoming_from_email(days=7)
        self.assertTrue(r["success"])

    def test_sync_calendar_empty(self):
        r = sync_email_calendar()
        self.assertTrue(r["success"])


# ═══════════════════════════════════════════════════════════════════
#  PHASE 20: DASHBOARD & REPORTING
# ═══════════════════════════════════════════════════════════════════

class TestPhase20Imports(unittest.TestCase):
    def test_email_dashboard_callable(self):
        self.assertTrue(callable(email_dashboard))

    def test_weekly_report_callable(self):
        self.assertTrue(callable(weekly_report))

    def test_monthly_report_callable(self):
        self.assertTrue(callable(monthly_report))

    def test_productivity_score_callable(self):
        self.assertTrue(callable(productivity_score))

    def test_email_trends_callable(self):
        self.assertTrue(callable(email_trends))


class TestPhase20Logic(unittest.TestCase):
    """Dashboard & reporting — these aggregate from all stores."""

    def test_dashboard_returns_success(self):
        r = email_dashboard()
        self.assertTrue(r["success"])
        self.assertIn("Dashboard", r["content"])

    def test_weekly_report_returns_success(self):
        r = weekly_report()
        self.assertTrue(r["success"])
        self.assertIn("Weekly", r["content"])

    def test_monthly_report_returns_success(self):
        r = monthly_report()
        self.assertTrue(r["success"])
        self.assertIn("Monthly", r["content"])

    def test_productivity_score_returns_success(self):
        r = productivity_score()
        self.assertTrue(r["success"])
        self.assertIn("Productivity", r["content"])
        self.assertIn("/100", r["content"])

    def test_email_trends_returns_success(self):
        r = email_trends(days=30)
        self.assertTrue(r["success"])
        self.assertIn("Trends", r["content"])

    def test_email_trends_custom_days(self):
        r = email_trends(days=7)
        self.assertTrue(r["success"])
        self.assertIn("7 days", r["content"])


# ═══════════════════════════════════════════════════════════════════
#  CROSS-PHASE INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCrossPhaseIntegration(unittest.TestCase):
    """Tests that span multiple phases."""

    def setUp(self):
        self.backups = {}
        for path in [TEMPLATES_PATH, DRAFTS_PATH, TRACKING_PATH, CALENDAR_PATH]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.backups[path] = f.read()
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        for path in [TEMPLATES_PATH, DRAFTS_PATH, TRACKING_PATH, CALENDAR_PATH]:
            if path in self.backups:
                with open(path, "w") as f:
                    f.write(self.backups[path])
            elif os.path.exists(path):
                os.remove(path)

    def test_template_to_draft_workflow(self):
        """Create template → render → save as draft."""
        c = create_template(name="Invoice", subject_template="Invoice #{{num}}", body_template="Amount: ${{amount}}")
        tid = _extract_id(c["content"], "tmpl_")
        rendered = use_template(template_id=tid, variables={"num": "42", "amount": "100"})
        self.assertTrue(rendered["success"])

        d = save_draft(to="client@corp.com", subject="Invoice #42", body="Amount: $100")
        self.assertTrue(d["success"])

    def test_track_then_report_then_untrack(self):
        """Track emails → generate report → untrack one."""
        t1 = track_email(subject="Email A", recipient="a@a.com")
        t2 = track_email(subject="Email B", recipient="b@b.com")
        self.assertTrue(t1["success"])
        self.assertTrue(t2["success"])

        r = tracking_report()
        self.assertIn("Total tracked: 2", r["content"])

        tid = _extract_id(t1["content"], "trk_")
        u = untrack_email(tracking_id=tid)
        self.assertTrue(u["success"])

        r2 = tracking_report()
        self.assertIn("Total tracked: 1", r2["content"])

    def test_dashboard_reflects_all_stores(self):
        """Dashboard should mention templates, drafts, tracking."""
        create_template(name="DashTest", body_template="hello")
        save_draft(to="x@y.com", subject="DashDraft", body="body")
        track_email(subject="DashTrack", recipient="t@t.com")

        r = email_dashboard()
        self.assertTrue(r["success"])
        content = r["content"]
        # Dashboard should have template, draft, and tracking counts
        self.assertIn("Templates: 1", content)
        self.assertIn("Drafts: 1", content)
        self.assertIn("Tracked: 1", content)

    def test_productivity_score_with_clean_inbox(self):
        """Productivity score should return 0-100 with grade."""
        r = productivity_score()
        self.assertTrue(r["success"])
        # Should have score and grade
        self.assertIn("/100", r["content"])
        # Grade should be one of A+/A/B/C/D/F
        content = r["content"]
        has_grade = any(g in content for g in ["A+", "Grade: A", "Grade: B", "Grade: C", "Grade: D", "Grade: F"])
        self.assertTrue(has_grade, f"No grade found in: {content}")


# ═══════════════════════════════════════════════════════════════════
#  EXECUTOR DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════════

class TestExecutorDispatch(unittest.TestCase):
    """Verify executor.py has dispatch branches for all Phase 14-20 actions."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(__file__), "..", "executor.py"), "r") as f:
            cls.executor_src = f.read()

    def _assert_action(self, action):
        self.assertIn(f'"{action}"', self.executor_src,
                      f"Action '{action}' missing from executor.py dispatch")

    # Phase 14
    def test_dispatch_create_template(self): self._assert_action("create_template")
    def test_dispatch_list_templates(self): self._assert_action("list_templates")
    def test_dispatch_get_template(self): self._assert_action("get_template")
    def test_dispatch_update_template(self): self._assert_action("update_template")
    def test_dispatch_delete_template(self): self._assert_action("delete_template")
    def test_dispatch_use_template(self): self._assert_action("use_template")

    # Phase 15
    def test_dispatch_save_draft(self): self._assert_action("save_draft")
    def test_dispatch_list_drafts_managed(self): self._assert_action("list_drafts_managed")
    def test_dispatch_get_draft(self): self._assert_action("get_draft")
    def test_dispatch_update_draft(self): self._assert_action("update_draft")
    def test_dispatch_delete_draft(self): self._assert_action("delete_draft")

    # Phase 16
    def test_dispatch_create_mail_folder(self): self._assert_action("create_mail_folder")
    def test_dispatch_list_mail_folders(self): self._assert_action("list_mail_folders")
    def test_dispatch_rename_mail_folder(self): self._assert_action("rename_mail_folder")
    def test_dispatch_delete_mail_folder(self): self._assert_action("delete_mail_folder")
    def test_dispatch_move_to_folder(self): self._assert_action("move_to_folder")
    def test_dispatch_get_folder_stats(self): self._assert_action("get_folder_stats")

    # Phase 17
    def test_dispatch_track_email(self): self._assert_action("track_email")
    def test_dispatch_list_tracked(self): self._assert_action("list_tracked_emails")
    def test_dispatch_get_tracking_status(self): self._assert_action("get_tracking_status")
    def test_dispatch_tracking_report(self): self._assert_action("tracking_report")
    def test_dispatch_untrack_email(self): self._assert_action("untrack_email")

    # Phase 18
    def test_dispatch_batch_archive(self): self._assert_action("batch_archive")
    def test_dispatch_batch_reply(self): self._assert_action("batch_reply")

    # Phase 19
    def test_dispatch_email_to_event(self): self._assert_action("email_to_event")
    def test_dispatch_list_email_events(self): self._assert_action("list_email_events")
    def test_dispatch_upcoming_from_email(self): self._assert_action("upcoming_from_email")
    def test_dispatch_meeting_conflicts(self): self._assert_action("meeting_conflicts")
    def test_dispatch_sync_email_calendar(self): self._assert_action("sync_email_calendar")

    # Phase 20
    def test_dispatch_email_dashboard(self): self._assert_action("email_dashboard")
    def test_dispatch_weekly_report(self): self._assert_action("weekly_report")
    def test_dispatch_monthly_report(self): self._assert_action("monthly_report")
    def test_dispatch_productivity_score(self): self._assert_action("productivity_score")
    def test_dispatch_email_trends(self): self._assert_action("email_trends")


# ═══════════════════════════════════════════════════════════════════
#  BRAIN TOOLS ENUM TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBrainToolsEnum(unittest.TestCase):
    """Verify brain/tools.py enum includes all Phase 14-20 actions."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(__file__), "..", "brain", "tools.py"), "r") as f:
            cls.tools_src = f.read()

    def _assert_enum(self, action):
        self.assertIn(f'"{action}"', self.tools_src,
                      f"Action '{action}' missing from brain/tools.py enum")

    # Phase 14
    def test_enum_create_template(self): self._assert_enum("create_template")
    def test_enum_list_templates(self): self._assert_enum("list_templates")
    def test_enum_get_template(self): self._assert_enum("get_template")
    def test_enum_update_template(self): self._assert_enum("update_template")
    def test_enum_delete_template(self): self._assert_enum("delete_template")
    def test_enum_use_template(self): self._assert_enum("use_template")

    # Phase 15
    def test_enum_save_draft(self): self._assert_enum("save_draft")
    def test_enum_list_drafts_managed(self): self._assert_enum("list_drafts_managed")
    def test_enum_get_draft(self): self._assert_enum("get_draft")
    def test_enum_update_draft(self): self._assert_enum("update_draft")
    def test_enum_delete_draft(self): self._assert_enum("delete_draft")

    # Phase 16
    def test_enum_create_mail_folder(self): self._assert_enum("create_mail_folder")
    def test_enum_list_mail_folders(self): self._assert_enum("list_mail_folders")
    def test_enum_rename_mail_folder(self): self._assert_enum("rename_mail_folder")
    def test_enum_delete_mail_folder(self): self._assert_enum("delete_mail_folder")
    def test_enum_move_to_folder(self): self._assert_enum("move_to_folder")
    def test_enum_get_folder_stats(self): self._assert_enum("get_folder_stats")

    # Phase 17
    def test_enum_track_email(self): self._assert_enum("track_email")
    def test_enum_list_tracked(self): self._assert_enum("list_tracked_emails")
    def test_enum_get_tracking_status(self): self._assert_enum("get_tracking_status")
    def test_enum_tracking_report(self): self._assert_enum("tracking_report")
    def test_enum_untrack_email(self): self._assert_enum("untrack_email")

    # Phase 18
    def test_enum_batch_archive(self): self._assert_enum("batch_archive")
    def test_enum_batch_reply(self): self._assert_enum("batch_reply")

    # Phase 19
    def test_enum_email_to_event(self): self._assert_enum("email_to_event")
    def test_enum_list_email_events(self): self._assert_enum("list_email_events")
    def test_enum_upcoming_from_email(self): self._assert_enum("upcoming_from_email")
    def test_enum_meeting_conflicts(self): self._assert_enum("meeting_conflicts")
    def test_enum_sync_email_calendar(self): self._assert_enum("sync_email_calendar")

    # Phase 20
    def test_enum_email_dashboard(self): self._assert_enum("email_dashboard")
    def test_enum_weekly_report(self): self._assert_enum("weekly_report")
    def test_enum_monthly_report(self): self._assert_enum("monthly_report")
    def test_enum_productivity_score(self): self._assert_enum("productivity_score")
    def test_enum_email_trends(self): self._assert_enum("email_trends")


# ═══════════════════════════════════════════════════════════════════
#  AGENT TOOLS SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAgentToolSchemas(unittest.TestCase):
    """Verify agent_tools.py schema constants exist and have correct structure."""

    def test_phase14_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_CREATE_TEMPLATE, TOOL_EMAIL_LIST_TEMPLATES,
            TOOL_EMAIL_GET_TEMPLATE, TOOL_EMAIL_UPDATE_TEMPLATE,
            TOOL_EMAIL_DELETE_TEMPLATE, TOOL_EMAIL_USE_TEMPLATE,
        )
        for t in [TOOL_EMAIL_CREATE_TEMPLATE, TOOL_EMAIL_LIST_TEMPLATES,
                   TOOL_EMAIL_GET_TEMPLATE, TOOL_EMAIL_UPDATE_TEMPLATE,
                   TOOL_EMAIL_DELETE_TEMPLATE, TOOL_EMAIL_USE_TEMPLATE]:
            self.assertIn("name", t)
            self.assertIn("input_schema", t)
            self.assertIn("type", t["input_schema"])

    def test_phase15_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_SAVE_DRAFT_MANAGED, TOOL_EMAIL_LIST_DRAFTS_MANAGED,
            TOOL_EMAIL_GET_DRAFT, TOOL_EMAIL_UPDATE_DRAFT,
            TOOL_EMAIL_DELETE_DRAFT_MANAGED,
        )
        for t in [TOOL_EMAIL_SAVE_DRAFT_MANAGED, TOOL_EMAIL_LIST_DRAFTS_MANAGED,
                   TOOL_EMAIL_GET_DRAFT, TOOL_EMAIL_UPDATE_DRAFT,
                   TOOL_EMAIL_DELETE_DRAFT_MANAGED]:
            self.assertIn("name", t)
            self.assertIn("input_schema", t)

    def test_phase16_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_CREATE_MAIL_FOLDER, TOOL_EMAIL_LIST_MAIL_FOLDERS,
            TOOL_EMAIL_RENAME_MAIL_FOLDER, TOOL_EMAIL_DELETE_MAIL_FOLDER,
            TOOL_EMAIL_MOVE_TO_FOLDER, TOOL_EMAIL_GET_FOLDER_STATS,
        )
        for t in [TOOL_EMAIL_CREATE_MAIL_FOLDER, TOOL_EMAIL_LIST_MAIL_FOLDERS,
                   TOOL_EMAIL_RENAME_MAIL_FOLDER, TOOL_EMAIL_DELETE_MAIL_FOLDER,
                   TOOL_EMAIL_MOVE_TO_FOLDER, TOOL_EMAIL_GET_FOLDER_STATS]:
            self.assertIn("name", t)

    def test_phase17_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_TRACK_EMAIL, TOOL_EMAIL_LIST_TRACKED,
            TOOL_EMAIL_GET_TRACKING_STATUS, TOOL_EMAIL_TRACKING_REPORT,
            TOOL_EMAIL_UNTRACK,
        )
        for t in [TOOL_EMAIL_TRACK_EMAIL, TOOL_EMAIL_LIST_TRACKED,
                   TOOL_EMAIL_GET_TRACKING_STATUS, TOOL_EMAIL_TRACKING_REPORT,
                   TOOL_EMAIL_UNTRACK]:
            self.assertIn("name", t)

    def test_phase18_schemas(self):
        from agents.agent_tools import TOOL_EMAIL_BATCH_ARCHIVE, TOOL_EMAIL_BATCH_REPLY
        for t in [TOOL_EMAIL_BATCH_ARCHIVE, TOOL_EMAIL_BATCH_REPLY]:
            self.assertIn("name", t)

    def test_phase19_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_TO_EVENT, TOOL_EMAIL_LIST_EMAIL_EVENTS,
            TOOL_EMAIL_UPCOMING_FROM_EMAIL, TOOL_EMAIL_MEETING_CONFLICTS,
            TOOL_EMAIL_SYNC_CALENDAR,
        )
        for t in [TOOL_EMAIL_TO_EVENT, TOOL_EMAIL_LIST_EMAIL_EVENTS,
                   TOOL_EMAIL_UPCOMING_FROM_EMAIL, TOOL_EMAIL_MEETING_CONFLICTS,
                   TOOL_EMAIL_SYNC_CALENDAR]:
            self.assertIn("name", t)

    def test_phase20_schemas(self):
        from agents.agent_tools import (
            TOOL_EMAIL_DASHBOARD, TOOL_EMAIL_WEEKLY_REPORT,
            TOOL_EMAIL_MONTHLY_REPORT, TOOL_EMAIL_PRODUCTIVITY_SCORE,
            TOOL_EMAIL_TRENDS,
        )
        for t in [TOOL_EMAIL_DASHBOARD, TOOL_EMAIL_WEEKLY_REPORT,
                   TOOL_EMAIL_MONTHLY_REPORT, TOOL_EMAIL_PRODUCTIVITY_SCORE,
                   TOOL_EMAIL_TRENDS]:
            self.assertIn("name", t)

    def test_original_drafts_not_overridden(self):
        """Ensure Phase 15 managed drafts don't override Phase 1 originals."""
        from agents.agent_tools import TOOL_EMAIL_SAVE_DRAFT, TOOL_EMAIL_LIST_DRAFTS
        # Original Phase 1 names start with "email_"
        self.assertEqual(TOOL_EMAIL_SAVE_DRAFT["name"], "email_save_draft")
        self.assertEqual(TOOL_EMAIL_LIST_DRAFTS["name"], "email_list_drafts")


# ═══════════════════════════════════════════════════════════════════
#  EMAIL AGENT DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEmailAgentDispatch(unittest.TestCase):
    """Verify email_agent.py has dispatch for all Phase 14-20 tools."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(__file__), "..", "agents", "email_agent.py"), "r") as f:
            cls.agent_src = f.read()

    def _assert_dispatch(self, action):
        self.assertIn(f'"{action}"', self.agent_src,
                      f"Action '{action}' missing from email_agent.py dispatch")

    # Phase 14
    def test_agent_create_template(self): self._assert_dispatch("create_template")
    def test_agent_list_templates(self): self._assert_dispatch("list_templates")
    def test_agent_get_template(self): self._assert_dispatch("get_template")
    def test_agent_update_template(self): self._assert_dispatch("update_template")
    def test_agent_delete_template(self): self._assert_dispatch("delete_template")
    def test_agent_use_template(self): self._assert_dispatch("use_template")

    # Phase 15
    def test_agent_save_draft(self): self._assert_dispatch("save_draft")
    def test_agent_list_drafts_managed(self): self._assert_dispatch("list_drafts_managed")
    def test_agent_get_draft(self): self._assert_dispatch("get_draft")
    def test_agent_update_draft(self): self._assert_dispatch("update_draft")
    def test_agent_delete_draft(self): self._assert_dispatch("delete_draft")

    # Phase 16
    def test_agent_create_mail_folder(self): self._assert_dispatch("create_mail_folder")
    def test_agent_list_mail_folders(self): self._assert_dispatch("list_mail_folders")
    def test_agent_rename_mail_folder(self): self._assert_dispatch("rename_mail_folder")
    def test_agent_delete_mail_folder(self): self._assert_dispatch("delete_mail_folder")
    def test_agent_move_to_folder(self): self._assert_dispatch("move_to_folder")
    def test_agent_get_folder_stats(self): self._assert_dispatch("get_folder_stats")

    # Phase 17
    def test_agent_track_email(self): self._assert_dispatch("track_email")
    def test_agent_list_tracked(self): self._assert_dispatch("list_tracked_emails")
    def test_agent_get_tracking_status(self): self._assert_dispatch("get_tracking_status")
    def test_agent_tracking_report(self): self._assert_dispatch("tracking_report")
    def test_agent_untrack_email(self): self._assert_dispatch("untrack_email")

    # Phase 18
    def test_agent_batch_archive(self): self._assert_dispatch("batch_archive")
    def test_agent_batch_reply(self): self._assert_dispatch("batch_reply")

    # Phase 19
    def test_agent_email_to_event(self): self._assert_dispatch("email_to_event")
    def test_agent_list_email_events(self): self._assert_dispatch("list_email_events")
    def test_agent_upcoming_from_email(self): self._assert_dispatch("upcoming_from_email")
    def test_agent_meeting_conflicts(self): self._assert_dispatch("meeting_conflicts")
    def test_agent_sync_email_calendar(self): self._assert_dispatch("sync_email_calendar")

    # Phase 20
    def test_agent_email_dashboard(self): self._assert_dispatch("email_dashboard")
    def test_agent_weekly_report(self): self._assert_dispatch("weekly_report")
    def test_agent_monthly_report(self): self._assert_dispatch("monthly_report")
    def test_agent_productivity_score(self): self._assert_dispatch("productivity_score")
    def test_agent_email_trends(self): self._assert_dispatch("email_trends")


# ═══════════════════════════════════════════════════════════════════
#  RESULT FORMAT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestResultFormat(unittest.TestCase):
    """Verify all functions return the standard {success, content} dict."""

    def _check_result(self, result, fn_name):
        self.assertIsInstance(result, dict, f"{fn_name} didn't return dict")
        self.assertIn("success", result, f"{fn_name} missing 'success' key")
        self.assertIn("content", result, f"{fn_name} missing 'content' key")
        self.assertIsInstance(result["success"], bool, f"{fn_name} 'success' is not bool")
        self.assertIsInstance(result["content"], str, f"{fn_name} 'content' is not str")

    def test_create_template_format(self):
        self._check_result(create_template(name="", body_template="x"), "create_template")

    def test_list_templates_format(self):
        self._check_result(list_templates(), "list_templates")

    def test_get_template_format(self):
        self._check_result(get_template(template_id="nonexistent"), "get_template")

    def test_track_email_format(self):
        self._check_result(track_email(subject="test"), "track_email")

    def test_list_tracked_format(self):
        self._check_result(list_tracked_emails(), "list_tracked_emails")

    def test_tracking_report_format(self):
        self._check_result(tracking_report(), "tracking_report")

    def test_save_draft_format(self):
        self._check_result(save_draft(body="test"), "save_draft")

    def test_email_dashboard_format(self):
        self._check_result(email_dashboard(), "email_dashboard")

    def test_weekly_report_format(self):
        self._check_result(weekly_report(), "weekly_report")

    def test_monthly_report_format(self):
        self._check_result(monthly_report(), "monthly_report")

    def test_productivity_score_format(self):
        self._check_result(productivity_score(), "productivity_score")

    def test_email_trends_format(self):
        self._check_result(email_trends(), "email_trends")

    def test_batch_archive_format(self):
        self._check_result(batch_archive(indices=None), "batch_archive")

    def test_batch_reply_format(self):
        self._check_result(batch_reply(indices=None), "batch_reply")

    def test_batch_label_format(self):
        self._check_result(batch_label(indices=None), "batch_label")

    def test_list_email_events_format(self):
        self._check_result(list_email_events(), "list_email_events")

    def test_upcoming_from_email_format(self):
        self._check_result(upcoming_from_email(), "upcoming_from_email")

    def test_sync_email_calendar_format(self):
        self._check_result(sync_email_calendar(), "sync_email_calendar")


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _extract_id(content, prefix):
    """Extract an ID (tmpl_xxx, draft_xxx, trk_xxx) from result content string."""
    for word in content.replace("(", " ").replace(")", " ").replace(",", " ").split():
        if word.startswith(prefix):
            return word.rstrip(".,):")
    return None


if __name__ == "__main__":
    unittest.main()
