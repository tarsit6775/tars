"""
Phase 13 Tests — Email Signatures, Email Aliases/Identities, Email Export/Archival
17 new functions. Run: pytest tests/test_email_phase13.py -v
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hands.email import (
    # Phase 13A: Signatures
    create_signature, list_signatures, update_signature,
    delete_signature, set_default_signature, get_signature,
    # Phase 13B: Aliases / Identities
    add_alias, list_aliases, update_alias,
    delete_alias, set_default_alias,
    # Phase 13C: Export / Archival
    export_emails, export_thread, backup_mailbox,
    list_backups, search_exports, get_export_stats,
    # Persistence paths
    SIGNATURES_PATH, ALIASES_PATH, EXPORT_INDEX_PATH, EXPORTS_DIR,
)


# ─── Phase 13A: Signatures Import ───

class TestPhase13ASignaturesImport(unittest.TestCase):
    """Test Phase 13A function imports."""

    def test_create_signature_callable(self):
        self.assertTrue(callable(create_signature))

    def test_list_signatures_callable(self):
        self.assertTrue(callable(list_signatures))

    def test_update_signature_callable(self):
        self.assertTrue(callable(update_signature))

    def test_delete_signature_callable(self):
        self.assertTrue(callable(delete_signature))

    def test_set_default_signature_callable(self):
        self.assertTrue(callable(set_default_signature))

    def test_get_signature_callable(self):
        self.assertTrue(callable(get_signature))


# ─── Phase 13B: Aliases Import ───

class TestPhase13BAliasesImport(unittest.TestCase):
    """Test Phase 13B function imports."""

    def test_add_alias_callable(self):
        self.assertTrue(callable(add_alias))

    def test_list_aliases_callable(self):
        self.assertTrue(callable(list_aliases))

    def test_update_alias_callable(self):
        self.assertTrue(callable(update_alias))

    def test_delete_alias_callable(self):
        self.assertTrue(callable(delete_alias))

    def test_set_default_alias_callable(self):
        self.assertTrue(callable(set_default_alias))


# ─── Phase 13C: Export Import ───

class TestPhase13CExportImport(unittest.TestCase):
    """Test Phase 13C function imports."""

    def test_export_emails_callable(self):
        self.assertTrue(callable(export_emails))

    def test_export_thread_callable(self):
        self.assertTrue(callable(export_thread))

    def test_backup_mailbox_callable(self):
        self.assertTrue(callable(backup_mailbox))

    def test_list_backups_callable(self):
        self.assertTrue(callable(list_backups))

    def test_search_exports_callable(self):
        self.assertTrue(callable(search_exports))

    def test_get_export_stats_callable(self):
        self.assertTrue(callable(get_export_stats))


# ─── Persistence Paths ───

class TestPhase13Paths(unittest.TestCase):
    """Test persistence paths are defined."""

    def test_signatures_path(self):
        self.assertIn("email_signatures", SIGNATURES_PATH)

    def test_aliases_path(self):
        self.assertIn("email_aliases", ALIASES_PATH)

    def test_export_index_path(self):
        self.assertIn("email_export_index", EXPORT_INDEX_PATH)

    def test_exports_dir(self):
        self.assertIn("email_exports", EXPORTS_DIR)


# ─── Phase 13A: Signatures Logic ───

class TestPhase13ASignaturesLogic(unittest.TestCase):
    """Test signature operations with real data."""

    def setUp(self):
        self.backup = None
        if os.path.exists(SIGNATURES_PATH):
            with open(SIGNATURES_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(SIGNATURES_PATH):
            os.remove(SIGNATURES_PATH)

    def tearDown(self):
        if self.backup:
            with open(SIGNATURES_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(SIGNATURES_PATH):
            os.remove(SIGNATURES_PATH)

    def test_list_signatures_empty(self):
        result = list_signatures()
        self.assertTrue(result["success"])
        self.assertIn("No signatures", result["content"])

    def test_create_signature_missing_name(self):
        result = create_signature(name="", body="test body")
        self.assertFalse(result["success"])

    def test_create_signature_missing_body(self):
        result = create_signature(name="Test Sig", body="")
        self.assertFalse(result["success"])

    def test_create_signature_success(self):
        result = create_signature(name="Work Sig", body="Best regards,\nTest User")
        self.assertTrue(result["success"])
        self.assertIn("sig_", result["content"])

    def test_create_signature_html(self):
        result = create_signature(name="HTML Sig", body="<b>Bold</b>", is_html=True)
        self.assertTrue(result["success"])
        self.assertIn("HTML", result["content"])

    def test_get_signature_by_id(self):
        r1 = create_signature(name="Fetch Test", body="body here")
        sig_id = None
        for part in r1["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        self.assertIsNotNone(sig_id)
        r2 = get_signature(sig_id=sig_id)
        self.assertTrue(r2["success"])
        self.assertIn("Fetch Test", r2["content"])

    def test_get_signature_default_when_none(self):
        result = get_signature()
        self.assertTrue(result["success"])
        # No default set yet
        self.assertIn("No", result["content"].lower()) if "default" in result["content"].lower() else None

    def test_update_signature_not_found(self):
        result = update_signature(sig_id="sig_nonexistent", name="New Name")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["content"].lower())

    def test_update_signature_success(self):
        r1 = create_signature(name="Update Me", body="old body")
        sig_id = None
        for part in r1["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        r2 = update_signature(sig_id=sig_id, body="new body")
        self.assertTrue(r2["success"])

    def test_delete_signature_not_found(self):
        result = delete_signature(sig_id="sig_ghost")
        self.assertFalse(result["success"])

    def test_delete_signature_success(self):
        r1 = create_signature(name="Delete Me", body="will be gone")
        sig_id = None
        for part in r1["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        r2 = delete_signature(sig_id=sig_id)
        self.assertTrue(r2["success"])
        # Verify gone — list is now empty so get returns "No signatures"
        r3 = get_signature(sig_id=sig_id)
        self.assertTrue(r3["success"])
        self.assertIn("No signatures", r3["content"])

    def test_set_default_signature_not_found(self):
        result = set_default_signature(sig_id="sig_nope")
        self.assertFalse(result["success"])

    def test_set_default_signature_success(self):
        r1 = create_signature(name="Default Sig", body="default body")
        sig_id = None
        for part in r1["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        r2 = set_default_signature(sig_id=sig_id)
        self.assertTrue(r2["success"])
        # Verify it's default
        r3 = get_signature()
        self.assertTrue(r3["success"])
        self.assertIn("Default Sig", r3["content"])


# ─── Phase 13B: Aliases Logic ───

class TestPhase13BAliasesLogic(unittest.TestCase):
    """Test alias operations with real data."""

    def setUp(self):
        self.backup = None
        if os.path.exists(ALIASES_PATH):
            with open(ALIASES_PATH, "r") as f:
                self.backup = f.read()
        if os.path.exists(ALIASES_PATH):
            os.remove(ALIASES_PATH)

    def tearDown(self):
        if self.backup:
            with open(ALIASES_PATH, "w") as f:
                f.write(self.backup)
        elif os.path.exists(ALIASES_PATH):
            os.remove(ALIASES_PATH)

    def test_list_aliases_empty(self):
        result = list_aliases()
        self.assertTrue(result["success"])
        self.assertIn("No aliases", result["content"])

    def test_add_alias_missing_email(self):
        result = add_alias(email="", display_name="Test")
        self.assertFalse(result["success"])

    def test_add_alias_missing_display_name(self):
        # Empty display_name still succeeds (falls back to email prefix)
        result = add_alias(email="alias@test.com", display_name="")
        self.assertTrue(result["success"])

    def test_add_alias_success(self):
        result = add_alias(email="work@company.com", display_name="Work Account")
        self.assertTrue(result["success"])
        self.assertIn("alias_", result["content"])

    def test_add_alias_with_signature(self):
        # First create a signature
        sig = create_signature(name="Alias Sig", body="regards")
        sig_id = None
        for part in sig["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        result = add_alias(email="formal@company.com", display_name="Formal", signature_id=sig_id)
        self.assertTrue(result["success"])

    def test_update_alias_not_found(self):
        result = update_alias(alias_id="alias_ghost", display_name="New Name")
        self.assertFalse(result["success"])

    def test_update_alias_success(self):
        r1 = add_alias(email="update@test.com", display_name="Old Name")
        alias_id = None
        for part in r1["content"].split():
            if part.startswith("alias_"):
                alias_id = part.rstrip(").,")
                break
        r2 = update_alias(alias_id=alias_id, display_name="New Name")
        self.assertTrue(r2["success"])

    def test_delete_alias_not_found(self):
        result = delete_alias(alias_id="alias_nope")
        self.assertFalse(result["success"])

    def test_delete_alias_success(self):
        r1 = add_alias(email="delete@test.com", display_name="Delete Me")
        alias_id = None
        for part in r1["content"].split():
            if part.startswith("alias_"):
                alias_id = part.rstrip(").,")
                break
        r2 = delete_alias(alias_id=alias_id)
        self.assertTrue(r2["success"])
        # Verify gone
        r3 = list_aliases()
        self.assertNotIn(alias_id, r3["content"])

    def test_set_default_alias_not_found(self):
        result = set_default_alias(alias_id="alias_nope")
        self.assertFalse(result["success"])

    def test_set_default_alias_success(self):
        r1 = add_alias(email="default@test.com", display_name="Default")
        alias_id = None
        for part in r1["content"].split():
            if part.startswith("alias_"):
                alias_id = part.rstrip(").,")
                break
        r2 = set_default_alias(alias_id=alias_id)
        self.assertTrue(r2["success"])


# ─── Phase 13C: Export Logic ───

class TestPhase13CExportLogic(unittest.TestCase):
    """Test export operations."""

    def setUp(self):
        self.backup_index = None
        if os.path.exists(EXPORT_INDEX_PATH):
            with open(EXPORT_INDEX_PATH, "r") as f:
                self.backup_index = f.read()
        if os.path.exists(EXPORT_INDEX_PATH):
            os.remove(EXPORT_INDEX_PATH)

    def tearDown(self):
        if self.backup_index:
            with open(EXPORT_INDEX_PATH, "w") as f:
                f.write(self.backup_index)
        elif os.path.exists(EXPORT_INDEX_PATH):
            os.remove(EXPORT_INDEX_PATH)

    def test_list_backups_empty(self):
        result = list_backups()
        self.assertTrue(result["success"])
        self.assertIn("No", result["content"])

    def test_search_exports_empty(self):
        result = search_exports(keyword="anything")
        self.assertTrue(result["success"])

    def test_get_export_stats_empty(self):
        result = get_export_stats()
        self.assertTrue(result["success"])
        self.assertIn("No export", result["content"])

    def test_search_exports_no_keyword(self):
        result = search_exports(keyword="")
        self.assertFalse(result["success"])


# ─── Tool Schemas ───

class TestPhase13ToolSchemas(unittest.TestCase):
    """Test that tool schemas exist in brain/tools.py."""

    def test_brain_enum_has_phase13_actions(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        enum_vals = mac_mail["input_schema"]["properties"]["action"]["enum"]
        phase13_actions = [
            "create_signature", "list_signatures", "update_signature",
            "delete_signature", "set_default_signature", "get_signature",
            "add_alias", "list_aliases", "update_alias",
            "delete_alias", "set_default_alias",
            "export_emails", "export_thread", "backup_mailbox",
            "list_backups", "search_exports", "export_stats",
        ]
        for action in phase13_actions:
            self.assertIn(action, enum_vals, f"Missing action: {action}")

    def test_brain_enum_count(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        enum_vals = mac_mail["input_schema"]["properties"]["action"]["enum"]
        self.assertGreaterEqual(len(enum_vals), 163, f"Expected >=163 actions, got {len(enum_vals)}")

    def test_brain_params_has_sig_id(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("sig_id", props)

    def test_brain_params_has_alias_email(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("alias_email", props)

    def test_brain_params_has_alias_id(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("alias_id", props)

    def test_brain_params_has_display_name(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("display_name", props)

    def test_brain_params_has_export_format(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("export_format", props)

    def test_brain_params_has_max_emails(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("max_emails", props)

    def test_brain_params_has_is_html(self):
        from brain.tools import TARS_TOOLS
        mac_mail = next(t for t in TARS_TOOLS if t["name"] == "mac_mail")
        props = mac_mail["input_schema"]["properties"]
        self.assertIn("is_html", props)


# ─── Agent Tools ───

class TestPhase13AgentTools(unittest.TestCase):
    """Test that agent tool schemas exist."""

    def test_agent_tool_imports(self):
        from agents.agent_tools import (
            TOOL_EMAIL_CREATE_SIGNATURE, TOOL_EMAIL_LIST_SIGNATURES,
            TOOL_EMAIL_UPDATE_SIGNATURE, TOOL_EMAIL_DELETE_SIGNATURE,
            TOOL_EMAIL_SET_DEFAULT_SIGNATURE, TOOL_EMAIL_GET_SIGNATURE,
            TOOL_EMAIL_ADD_ALIAS, TOOL_EMAIL_LIST_ALIASES,
            TOOL_EMAIL_UPDATE_ALIAS, TOOL_EMAIL_DELETE_ALIAS,
            TOOL_EMAIL_SET_DEFAULT_ALIAS,
            TOOL_EMAIL_EXPORT_EMAILS, TOOL_EMAIL_EXPORT_THREAD,
            TOOL_EMAIL_BACKUP_MAILBOX, TOOL_EMAIL_LIST_BACKUPS,
            TOOL_EMAIL_SEARCH_EXPORTS, TOOL_EMAIL_EXPORT_STATS,
        )
        self.assertEqual(TOOL_EMAIL_CREATE_SIGNATURE["name"], "create_signature")
        self.assertEqual(TOOL_EMAIL_ADD_ALIAS["name"], "add_alias")
        self.assertEqual(TOOL_EMAIL_EXPORT_EMAILS["name"], "export_emails")

    def test_agent_tool_schemas_valid(self):
        from agents.agent_tools import (
            TOOL_EMAIL_CREATE_SIGNATURE, TOOL_EMAIL_ADD_ALIAS,
            TOOL_EMAIL_EXPORT_EMAILS,
        )
        for tool in [TOOL_EMAIL_CREATE_SIGNATURE, TOOL_EMAIL_ADD_ALIAS, TOOL_EMAIL_EXPORT_EMAILS]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("input_schema", tool)
            self.assertIn("type", tool["input_schema"])


# ─── Email Agent ───

class TestPhase13EmailAgent(unittest.TestCase):
    """Test that email agent has Phase 13 tools."""

    def test_email_agent_has_phase13_tools(self):
        from agents.email_agent import EmailAgent
        agent = EmailAgent.__new__(EmailAgent)
        tools = EmailAgent.tools.fget(agent)
        tool_names = [t["name"] for t in tools]
        phase13_tools = [
            "create_signature", "list_signatures", "update_signature",
            "delete_signature", "set_default_signature", "get_signature",
            "add_alias", "list_aliases", "update_alias",
            "delete_alias", "set_default_alias",
            "export_emails", "export_thread", "backup_mailbox",
            "list_backups", "search_exports", "export_stats",
        ]
        for tool_name in phase13_tools:
            self.assertIn(tool_name, tool_names, f"Missing agent tool: {tool_name}")

    def test_email_agent_tool_count(self):
        from agents.email_agent import EmailAgent
        agent = EmailAgent.__new__(EmailAgent)
        tools = EmailAgent.tools.fget(agent)
        # 163 email tools + 2 (done + stuck) = 165
        self.assertIn(len(tools), range(165, 300), f"Expected ~165 tools, got {len(tools)}")


# ─── Brain Prompts ───

class TestPhase13Prompts(unittest.TestCase):
    """Test brain prompts reference Phase 13."""

    def test_prompts_reference_signatures(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("create_signature", DOMAIN_EMAIL)
        self.assertIn("Signatures", DOMAIN_EMAIL)

    def test_prompts_reference_aliases(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("add_alias", DOMAIN_EMAIL)
        self.assertIn("Aliases", DOMAIN_EMAIL)

    def test_prompts_reference_export(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertIn("export_emails", DOMAIN_EMAIL)
        self.assertIn("Export", DOMAIN_EMAIL)

    def test_prompts_updated_counts(self):
        from brain.prompts import DOMAIN_EMAIL
        self.assertTrue(
            "163 actions" in DOMAIN_EMAIL or "197 actions" in DOMAIN_EMAIL,
            "Expected '163 actions' or '197 actions' in DOMAIN_EMAIL"
        )
        self.assertTrue(
            "165-tool" in DOMAIN_EMAIL or "199-tool" in DOMAIN_EMAIL,
            "Expected '165-tool' or '199-tool' in DOMAIN_EMAIL"
        )


# ─── Executor ───

class TestPhase13Executor(unittest.TestCase):
    """Test executor dispatches Phase 13 actions."""

    def test_executor_source_has_phase13(self):
        import inspect
        from executor import ToolExecutor
        source = inspect.getsource(ToolExecutor._mac_mail)
        phase13_actions = [
            "create_signature", "list_signatures", "update_signature",
            "delete_signature", "set_default_signature", "get_signature",
            "add_alias", "list_aliases", "update_alias",
            "delete_alias", "set_default_alias",
            "export_emails", "export_thread", "backup_mailbox",
            "list_backups", "search_exports", "export_stats",
        ]
        for action in phase13_actions:
            self.assertIn(action, source, f"Executor missing: {action}")


# ─── Integration ───

class TestPhase13Integration(unittest.TestCase):
    """Integration tests for Phase 13 features."""

    def setUp(self):
        self.backups = {}
        for path in [SIGNATURES_PATH, ALIASES_PATH, EXPORT_INDEX_PATH]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.backups[path] = f.read()
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        for path, content in self.backups.items():
            with open(path, "w") as f:
                f.write(content)
        for path in [SIGNATURES_PATH, ALIASES_PATH, EXPORT_INDEX_PATH]:
            if path not in self.backups and os.path.exists(path):
                os.remove(path)

    def test_signature_full_lifecycle(self):
        """Create → list → get → update → set default → delete."""
        # Create
        r1 = create_signature(name="Lifecycle Sig", body="-- Best, Test")
        self.assertTrue(r1["success"])
        sig_id = None
        for part in r1["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        self.assertIsNotNone(sig_id)

        # List
        r2 = list_signatures()
        self.assertTrue(r2["success"])
        self.assertIn("Lifecycle Sig", r2["content"])

        # Get
        r3 = get_signature(sig_id=sig_id)
        self.assertTrue(r3["success"])
        self.assertIn("Lifecycle Sig", r3["content"])

        # Update
        r4 = update_signature(sig_id=sig_id, body="-- Cheers, Test")
        self.assertTrue(r4["success"])

        # Set default
        r5 = set_default_signature(sig_id=sig_id)
        self.assertTrue(r5["success"])

        # Get default
        r6 = get_signature()
        self.assertTrue(r6["success"])
        self.assertIn("Lifecycle Sig", r6["content"])

        # Delete
        r7 = delete_signature(sig_id=sig_id)
        self.assertTrue(r7["success"])

        # Verify gone — list is now empty
        r8 = get_signature(sig_id=sig_id)
        self.assertTrue(r8["success"])
        self.assertIn("No signatures", r8["content"])

    def test_alias_full_lifecycle(self):
        """Add → list → update → set default → delete."""
        # Add
        r1 = add_alias(email="lifecycle@test.com", display_name="Lifecycle Alias")
        self.assertTrue(r1["success"])
        alias_id = None
        for part in r1["content"].split():
            if part.startswith("alias_"):
                alias_id = part.rstrip(").,")
                break
        self.assertIsNotNone(alias_id)

        # List
        r2 = list_aliases()
        self.assertTrue(r2["success"])
        self.assertIn("lifecycle@test.com", r2["content"])

        # Update
        r3 = update_alias(alias_id=alias_id, display_name="Updated Alias")
        self.assertTrue(r3["success"])

        # Set default
        r4 = set_default_alias(alias_id=alias_id)
        self.assertTrue(r4["success"])

        # Delete
        r5 = delete_alias(alias_id=alias_id)
        self.assertTrue(r5["success"])

        # Verify gone
        r6 = list_aliases()
        if alias_id:
            self.assertNotIn(alias_id, r6["content"])

    def test_export_stats_and_list(self):
        """export_stats and list_backups with no data."""
        r1 = get_export_stats()
        self.assertTrue(r1["success"])

        r2 = list_backups()
        self.assertTrue(r2["success"])

    def test_multiple_signatures(self):
        """Create multiple signatures, list shows all."""
        create_signature(name="Sig Alpha", body="Alpha body")
        create_signature(name="Sig Beta", body="Beta body")
        create_signature(name="Sig Gamma", body="Gamma body")
        r = list_signatures()
        self.assertTrue(r["success"])
        self.assertIn("Sig Alpha", r["content"])
        self.assertIn("Sig Beta", r["content"])
        self.assertIn("Sig Gamma", r["content"])

    def test_multiple_aliases(self):
        """Create multiple aliases, list shows all."""
        add_alias(email="a@test.com", display_name="Alias A")
        add_alias(email="b@test.com", display_name="Alias B")
        r = list_aliases()
        self.assertTrue(r["success"])
        self.assertIn("a@test.com", r["content"])
        self.assertIn("b@test.com", r["content"])

    def test_alias_with_linked_signature(self):
        """Create signature, link to alias, verify."""
        sig = create_signature(name="Linked Sig", body="linked body")
        sig_id = None
        for part in sig["content"].split():
            if part.startswith("sig_"):
                sig_id = part.rstrip(").,")
                break
        r = add_alias(email="linked@test.com", display_name="Linked", signature_id=sig_id)
        self.assertTrue(r["success"])


if __name__ == "__main__":
    unittest.main()
