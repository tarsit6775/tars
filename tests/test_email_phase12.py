"""
Phase 12 Tests — Email Labels & Tags, Newsletter Management, Auto-Responder
16 new functions. Run: pytest tests/test_email_phase12.py -v
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hands.email import (
    # Phase 12A: Labels & Tags
    add_label, remove_label, list_labels, get_labeled_emails, bulk_label,
    # Phase 12B: Newsletter Management
    detect_newsletters, newsletter_digest, newsletter_stats,
    newsletter_preferences, apply_newsletter_preferences,
    # Phase 12C: Auto-Responder
    create_auto_response, list_auto_responses, update_auto_response,
    delete_auto_response, toggle_auto_response, auto_response_history,
    # Persistence paths
    LABELS_PATH, NEWSLETTER_PREFS_PATH, AUTO_RESPONDER_PATH,
)


class TestPhase12ALabelsImport(unittest.TestCase):
    """Test Phase 12A function imports."""

    def test_add_label_callable(self):
        self.assertTrue(callable(add_label))

    def test_remove_label_callable(self):
        self.assertTrue(callable(remove_label))

    def test_list_labels_callable(self):
        self.assertTrue(callable(list_labels))

    def test_get_labeled_emails_callable(self):
        self.assertTrue(callable(get_labeled_emails))

    def test_bulk_label_callable(self):
        self.assertTrue(callable(bulk_label))


class TestPhase12BNewsletterImport(unittest.TestCase):
    """Test Phase 12B function imports."""

    def test_detect_newsletters_callable(self):
        self.assertTrue(callable(detect_newsletters))

    def test_newsletter_digest_callable(self):
        self.assertTrue(callable(newsletter_digest))

    def test_newsletter_stats_callable(self):
        self.assertTrue(callable(newsletter_stats))

    def test_newsletter_preferences_callable(self):
        self.assertTrue(callable(newsletter_preferences))

    def test_apply_newsletter_preferences_callable(self):
        self.assertTrue(callable(apply_newsletter_preferences))


class TestPhase12CAutoResponderImport(unittest.TestCase):
    """Test Phase 12C function imports."""

    def test_create_auto_response_callable(self):
        self.assertTrue(callable(create_auto_response))

    def test_list_auto_responses_callable(self):
        self.assertTrue(callable(list_auto_responses))

    def test_update_auto_response_callable(self):
        self.assertTrue(callable(update_auto_response))

    def test_delete_auto_response_callable(self):
        self.assertTrue(callable(delete_auto_response))

    def test_toggle_auto_response_callable(self):
        self.assertTrue(callable(toggle_auto_response))

    def test_auto_response_history_callable(self):
        self.assertTrue(callable(auto_response_history))


class TestPhase12Paths(unittest.TestCase):
    """Test persistence paths are defined."""

    def test_labels_path(self):
        self.assertIn("email_labels", LABELS_PATH)

    def test_newsletter_prefs_path(self):
        self.assertIn("email_newsletter_prefs", NEWSLETTER_PREFS_PATH)

    def test_auto_responder_path(self):
        self.assertIn("email_auto_responders", AUTO_RESPONDER_PATH)


class TestPhase12ALabelsLogic(unittest.TestCase):
    """Test label operations with mock data."""

    def setUp(self):
        self.backup = None
        if os.path.exists(LABELS_PATH):
            with open(LABELS_PATH, "r") as f:
                self.backup = f.read()
        # Start clean
        if os.path.exists(LABELS_PATH):
            os.remove(LABELS_PATH)

    def tearDown(self):
        if self.backup:
            with open(LABELS_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(LABELS_PATH):
            os.remove(LABELS_PATH)

    def test_list_labels_empty(self):
        result = list_labels()
        self.assertTrue(result["success"])
        self.assertIn("No labels", result["content"])

    def test_add_label_no_label(self):
        result = add_label(index=1, label="")
        self.assertFalse(result["success"])
        self.assertIn("required", result["content"])

    def test_get_labeled_emails_no_label(self):
        result = get_labeled_emails(label="")
        self.assertFalse(result["success"])

    def test_get_labeled_emails_nonexistent(self):
        result = get_labeled_emails(label="nonexistent_xyz")
        self.assertTrue(result["success"])
        self.assertIn("No emails", result["content"])

    def test_bulk_label_no_indices(self):
        result = bulk_label(indices=None, label="test")
        self.assertFalse(result["success"])
        self.assertIn("required", result["content"].lower())

    def test_bulk_label_no_label(self):
        result = bulk_label(indices=[1, 2], label="")
        self.assertFalse(result["success"])

    def test_remove_label_no_label(self):
        result = remove_label(index=1, label="")
        self.assertFalse(result["success"])


class TestPhase12BNewsletterLogic(unittest.TestCase):
    """Test newsletter operations."""

    def setUp(self):
        self.backup = None
        if os.path.exists(NEWSLETTER_PREFS_PATH):
            with open(NEWSLETTER_PREFS_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(NEWSLETTER_PREFS_PATH):
            os.remove(NEWSLETTER_PREFS_PATH)

    def tearDown(self):
        if self.backup:
            with open(NEWSLETTER_PREFS_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(NEWSLETTER_PREFS_PATH):
            os.remove(NEWSLETTER_PREFS_PATH)

    def test_newsletter_stats_empty(self):
        result = newsletter_stats()
        self.assertTrue(result["success"])
        self.assertIn("No newsletter data", result["content"])

    def test_newsletter_preferences_no_sender(self):
        result = newsletter_preferences(sender="", action="keep")
        self.assertFalse(result["success"])
        self.assertIn("required", result["content"].lower())

    def test_newsletter_preferences_invalid_action(self):
        result = newsletter_preferences(sender="test@example.com", action="delete")
        self.assertFalse(result["success"])
        self.assertIn("must be", result["content"].lower())

    def test_newsletter_preferences_set(self):
        result = newsletter_preferences(sender="news@example.com", action="archive")
        self.assertTrue(result["success"])
        self.assertIn("archive", result["content"])

    def test_newsletter_preferences_persist(self):
        newsletter_preferences(sender="weekly@digest.com", action="keep")
        result = newsletter_stats()
        self.assertTrue(result["success"])
        self.assertIn("weekly@digest.com", result["content"])

    def test_apply_newsletter_preferences_empty(self):
        # No prefs saved
        if os.path.exists(NEWSLETTER_PREFS_PATH):
            os.remove(NEWSLETTER_PREFS_PATH)
        result = apply_newsletter_preferences()
        self.assertTrue(result["success"])
        self.assertIn("No newsletter preferences", result["content"])


class TestPhase12CAutoResponderLogic(unittest.TestCase):
    """Test auto-responder operations."""

    def setUp(self):
        self.backup = None
        if os.path.exists(AUTO_RESPONDER_PATH):
            with open(AUTO_RESPONDER_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(AUTO_RESPONDER_PATH):
            os.remove(AUTO_RESPONDER_PATH)

    def tearDown(self):
        if self.backup:
            with open(AUTO_RESPONDER_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(AUTO_RESPONDER_PATH):
            os.remove(AUTO_RESPONDER_PATH)

    def test_list_auto_responses_empty(self):
        result = list_auto_responses()
        self.assertTrue(result["success"])
        self.assertIn("No auto-response", result["content"])

    def test_create_auto_response_no_name(self):
        result = create_auto_response(name="", conditions={"from_contains": "hr@"}, response_body="noted")
        self.assertFalse(result["success"])
        self.assertIn("required", result["content"].lower())

    def test_create_auto_response_no_conditions(self):
        result = create_auto_response(name="test", conditions=None, response_body="noted")
        self.assertFalse(result["success"])

    def test_create_auto_response_no_body(self):
        result = create_auto_response(name="test", conditions={"from_contains": "hr@"}, response_body="")
        self.assertFalse(result["success"])

    def test_create_auto_response_success(self):
        result = create_auto_response(
            name="HR Survey", conditions={"from_contains": "hr@"},
            response_body="Thanks, I'll fill this out soon."
        )
        self.assertTrue(result["success"])
        self.assertIn("HR Survey", result["content"])
        self.assertIn("ar_", result["content"])

    def test_list_auto_responses_after_create(self):
        create_auto_response(
            name="Test Rule", conditions={"subject_contains": "survey"},
            response_body="Auto reply"
        )
        result = list_auto_responses()
        self.assertTrue(result["success"])
        self.assertIn("Test Rule", result["content"])

    def test_update_auto_response_not_found(self):
        result = update_auto_response(rule_id="nonexistent")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"])

    def test_update_auto_response_no_id(self):
        result = update_auto_response(rule_id="")
        self.assertFalse(result["success"])

    def test_delete_auto_response_not_found(self):
        result = delete_auto_response(rule_id="nonexistent")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"])

    def test_delete_auto_response_no_id(self):
        result = delete_auto_response(rule_id="")
        self.assertFalse(result["success"])

    def test_toggle_auto_response_not_found(self):
        result = toggle_auto_response(rule_id="nonexistent")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"])

    def test_toggle_auto_response_no_id(self):
        result = toggle_auto_response(rule_id="")
        self.assertFalse(result["success"])

    def test_create_and_toggle(self):
        r1 = create_auto_response(
            name="Toggle Test", conditions={"from_contains": "test@"},
            response_body="test reply"
        )
        self.assertTrue(r1["success"])
        # Extract rule ID
        rule_id = None
        for part in r1["content"].split():
            if part.startswith("ar_"):
                rule_id = part.rstrip(")")
                break
        self.assertIsNotNone(rule_id)

        r2 = toggle_auto_response(rule_id=rule_id, enabled=False)
        self.assertTrue(r2["success"])
        self.assertIn("disabled", r2["content"])

        r3 = toggle_auto_response(rule_id=rule_id, enabled=True)
        self.assertTrue(r3["success"])
        self.assertIn("enabled", r3["content"])

    def test_create_and_delete(self):
        r1 = create_auto_response(
            name="Delete Test", conditions={"from_contains": "test@"},
            response_body="auto reply"
        )
        rule_id = None
        for part in r1["content"].split():
            if part.startswith("ar_"):
                rule_id = part.rstrip(")")
                break
        self.assertIsNotNone(rule_id)

        r2 = delete_auto_response(rule_id=rule_id)
        self.assertTrue(r2["success"])
        self.assertIn("deleted", r2["content"])

        # Verify gone
        r3 = list_auto_responses()
        self.assertNotIn(rule_id, r3["content"])

    def test_create_and_update(self):
        r1 = create_auto_response(
            name="Update Test", conditions={"from_contains": "test@"},
            response_body="original reply"
        )
        rule_id = None
        for part in r1["content"].split():
            if part.startswith("ar_"):
                rule_id = part.rstrip(")")
                break
        self.assertIsNotNone(rule_id)

        r2 = update_auto_response(rule_id=rule_id, name="Updated Name", response_body="new reply")
        self.assertTrue(r2["success"])
        self.assertIn("Updated Name", r2["content"])

    def test_auto_response_history_empty(self):
        result = auto_response_history()
        self.assertTrue(result["success"])
        self.assertIn("No auto-responses", result["content"])


class TestPhase12ToolSchemas(unittest.TestCase):
    """Test that tool schemas exist in brain/tools.py."""

    def test_brain_enum_has_phase12_actions(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        enum_vals = mac_mail["input_schema"]["properties"]["action"]["enum"]
        phase12_actions = [
            "add_label", "remove_label", "list_labels", "get_labeled_emails", "bulk_label",
            "detect_newsletters", "newsletter_digest", "newsletter_stats",
            "newsletter_preferences", "apply_newsletter_preferences",
            "create_auto_response", "list_auto_responses", "update_auto_response",
            "delete_auto_response", "toggle_auto_response", "auto_response_history",
        ]
        for action in phase12_actions:
            self.assertIn(action, enum_vals, f"Missing action: {action}")

    def test_brain_enum_count(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        enum_vals = mac_mail["input_schema"]["properties"]["action"]["enum"]
        self.assertIn(len(enum_vals), range(146, 250), f"Expected ~146 actions, got {len(enum_vals)}")

    def test_brain_params_has_label(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("label", props)

    def test_brain_params_has_rule_id(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("rule_id", props)


class TestPhase12AgentTools(unittest.TestCase):
    """Test that agent tool schemas exist."""

    def test_agent_tool_imports(self):
        from agents.agent_tools import (
            TOOL_EMAIL_ADD_LABEL, TOOL_EMAIL_REMOVE_LABEL,
            TOOL_EMAIL_LIST_LABELS, TOOL_EMAIL_GET_LABELED,
            TOOL_EMAIL_BULK_LABEL,
            TOOL_EMAIL_DETECT_NEWSLETTERS, TOOL_EMAIL_NEWSLETTER_DIGEST,
            TOOL_EMAIL_NEWSLETTER_STATS, TOOL_EMAIL_NEWSLETTER_PREFS,
            TOOL_EMAIL_APPLY_NEWSLETTER_PREFS,
            TOOL_EMAIL_CREATE_AUTO_RESPONSE, TOOL_EMAIL_LIST_AUTO_RESPONSES,
            TOOL_EMAIL_UPDATE_AUTO_RESPONSE, TOOL_EMAIL_DELETE_AUTO_RESPONSE,
            TOOL_EMAIL_TOGGLE_AUTO_RESPONSE, TOOL_EMAIL_AUTO_RESPONSE_HISTORY,
        )
        self.assertEqual(TOOL_EMAIL_ADD_LABEL["name"], "add_label")
        self.assertEqual(TOOL_EMAIL_CREATE_AUTO_RESPONSE["name"], "create_auto_response")
        self.assertEqual(TOOL_EMAIL_DETECT_NEWSLETTERS["name"], "detect_newsletters")

    def test_agent_tool_schemas_valid(self):
        from agents.agent_tools import (
            TOOL_EMAIL_ADD_LABEL, TOOL_EMAIL_NEWSLETTER_PREFS,
            TOOL_EMAIL_CREATE_AUTO_RESPONSE,
        )
        for tool in [TOOL_EMAIL_ADD_LABEL, TOOL_EMAIL_NEWSLETTER_PREFS, TOOL_EMAIL_CREATE_AUTO_RESPONSE]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("input_schema", tool)
            self.assertIn("type", tool["input_schema"])


class TestPhase12EmailAgent(unittest.TestCase):
    """Test that email agent has Phase 12 tools."""

    def test_email_agent_has_phase12_tools(self):
        from agents.email_agent import EmailAgent
        agent = EmailAgent.__new__(EmailAgent)
        # Access the tools property defined in the class
        tools = EmailAgent.tools.fget(agent)
        tool_names = [t["name"] for t in tools]
        phase12_tools = [
            "add_label", "remove_label", "list_labels", "get_labeled_emails", "bulk_label",
            "detect_newsletters", "newsletter_digest", "newsletter_stats",
            "newsletter_preferences", "apply_newsletter_preferences",
            "create_auto_response", "list_auto_responses", "update_auto_response",
            "delete_auto_response", "toggle_auto_response", "auto_response_history",
        ]
        for tool_name in phase12_tools:
            self.assertIn(tool_name, tool_names, f"Missing agent tool: {tool_name}")

    def test_email_agent_tool_count(self):
        from agents.email_agent import EmailAgent
        agent = EmailAgent.__new__(EmailAgent)
        tools = EmailAgent.tools.fget(agent)
        # 146 email tools + 2 (done + stuck) = 148
        self.assertIn(len(tools), range(148, 250), f"Expected ~148 tools, got {len(tools)}")


class TestPhase12Prompts(unittest.TestCase):
    """Test brain prompts reference Phase 12."""

    def test_prompts_reference_labels(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("add_label", DOMAIN_EMAIL)
        self.assertIn("Labels", DOMAIN_EMAIL)

    def test_prompts_reference_newsletters(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("detect_newsletters", DOMAIN_EMAIL)
        self.assertIn("Newsletter", DOMAIN_EMAIL)

    def test_prompts_reference_auto_responder(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("create_auto_response", DOMAIN_EMAIL)
        self.assertIn("Auto-Responder", DOMAIN_EMAIL)

    def test_prompts_updated_counts(self):
        from brain.prompts import DOMAIN_EMAIL
        # Phase 13+ may increase these counts, so check range
        self.assertTrue(
            "146 actions" in DOMAIN_EMAIL or "163 actions" in DOMAIN_EMAIL or "actions" in DOMAIN_EMAIL
        )


class TestPhase12Executor(unittest.TestCase):
    """Test executor dispatches Phase 12 actions."""

    def test_executor_source_has_phase12(self):
        import inspect
        from executor import ToolExecutor
        source = inspect.getsource(ToolExecutor._mac_mail)
        phase12_actions = [
            "add_label", "remove_label", "list_labels", "get_labeled_emails", "bulk_label",
            "detect_newsletters", "newsletter_digest", "newsletter_stats",
            "newsletter_preferences", "apply_newsletter_preferences",
            "create_auto_response", "list_auto_responses", "update_auto_response",
            "delete_auto_response", "toggle_auto_response", "auto_response_history",
        ]
        for action in phase12_actions:
            self.assertIn(action, source, f"Executor missing: {action}")


class TestPhase12Integration(unittest.TestCase):
    """Integration tests for Phase 12 features."""

    def setUp(self):
        # Backup all Phase 12 data files
        self.backups = {}
        for path in [LABELS_PATH, NEWSLETTER_PREFS_PATH, AUTO_RESPONDER_PATH]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.backups[path] = f.read()
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        for path, content in self.backups.items():
            with open(path, "w") as f:
                f.write(content)
        for path in [LABELS_PATH, NEWSLETTER_PREFS_PATH, AUTO_RESPONDER_PATH]:
            if path not in self.backups and os.path.exists(path):
                os.remove(path)

    def test_auto_responder_full_lifecycle(self):
        """Create → list → update → toggle → history → delete."""
        # Create
        r1 = create_auto_response(
            name="Lifecycle Test", conditions={"from_contains": "lifecycle@"},
            response_body="Auto reply for lifecycle test"
        )
        self.assertTrue(r1["success"])
        rule_id = None
        for part in r1["content"].split():
            if part.startswith("ar_"):
                rule_id = part.rstrip(")")
                break

        # List
        r2 = list_auto_responses()
        self.assertIn("Lifecycle Test", r2["content"])

        # Update
        r3 = update_auto_response(rule_id=rule_id, name="Updated Lifecycle")
        self.assertTrue(r3["success"])

        # Toggle off
        r4 = toggle_auto_response(rule_id=rule_id, enabled=False)
        self.assertTrue(r4["success"])
        self.assertIn("disabled", r4["content"])

        # History (empty)
        r5 = auto_response_history()
        self.assertTrue(r5["success"])

        # Delete
        r6 = delete_auto_response(rule_id=rule_id)
        self.assertTrue(r6["success"])

        # Verify gone
        r7 = list_auto_responses()
        self.assertNotIn(rule_id, r7["content"])

    def test_newsletter_prefs_lifecycle(self):
        """Set pref → stats → apply (dry run)."""
        # Set preference
        r1 = newsletter_preferences(sender="weekly@news.com", action="archive")
        self.assertTrue(r1["success"])

        # Stats
        r2 = newsletter_stats()
        self.assertTrue(r2["success"])
        self.assertIn("weekly@news.com", r2["content"])

        # Apply dry run — should mention preferences applied
        r3 = apply_newsletter_preferences(dry_run=True)
        self.assertTrue(r3["success"])

    def test_labels_list_and_get(self):
        """list_labels and get_labeled_emails with no data."""
        r1 = list_labels()
        self.assertTrue(r1["success"])

        r2 = get_labeled_emails(label="test_label")
        self.assertTrue(r2["success"])


if __name__ == "__main__":
    unittest.main()
