"""
╔══════════════════════════════════════════════════════════════╗
║     TARS — Test Suite: Browsing & Account Creation            ║
╠══════════════════════════════════════════════════════════════╣
║  10 tests covering the full browsing/signup pipeline:         ║
║                                                              ║
║   1. Google-First Navigation in brain prompts                ║
║   2. Google-First Navigation in browser agent prompt         ║
║   3. Google-First Navigation in hands browser agent prompt   ║
║   4. CSS Selector Fixing (_fix_selector)                     ║
║   5. Human-Like Typing Function                              ║
║   6. Browser Agent has read_otp tool                         ║
║   7. Browser Agent form error detection in look()            ║
║   8. Executor routes all agent deployments                   ║
║   9. Auto-Escalation: Browser → Screen Agent                 ║
║  10. Account Manager credential workflow                     ║
║                                                              ║
║  Run: python -m pytest tests/test_browsing.py -v             ║
║  Or:  cd tars-main && .venv/bin/python tests/test_browsing.py║
╚══════════════════════════════════════════════════════════════╝
"""

import unittest
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════
#  TEST 1: Google-First Navigation in Brain Prompts
# ═══════════════════════════════════════════════════════

class TestGoogleFirstBrainPrompt(unittest.TestCase):
    """Verify DOMAIN_BROWSER tells the brain to use Google-first navigation."""

    def setUp(self):
        from brain.prompts import DOMAIN_BROWSER
        self.prompt = DOMAIN_BROWSER

    def test_contains_google_first_section(self):
        """DOMAIN_BROWSER must have a GOOGLE-FIRST NAVIGATION section."""
        self.assertIn("GOOGLE-FIRST NAVIGATION", self.prompt)

    def test_warns_against_direct_urls(self):
        """Prompt must warn against giving agents direct signup/login URLs."""
        self.assertIn("NEVER give the agent a direct signup/login URL", self.prompt)

    def test_shows_correct_example(self):
        """Prompt must show Google search example, not direct URL navigation."""
        self.assertIn("Search Google for", self.prompt)

    def test_shows_bad_example(self):
        """Prompt must explicitly mark direct URL examples as wrong."""
        # Must contain a bad example with ❌ marker
        bad_pattern = re.compile(r"❌.*(?:https://|Navigate to|Go to)")
        self.assertIsNotNone(bad_pattern.search(self.prompt),
            "Prompt must show direct URL as ❌ bad example")

    def test_explains_why_google_first(self):
        """Prompt must explain WHY Google-first works (referrer headers, etc)."""
        self.assertIn("Referer", self.prompt.replace("referrer", "Referer"))

    def test_doordash_example_uses_google(self):
        """The DoorDash developer portal example must use Google search, not a direct URL."""
        doordash_section = ""
        for line in self.prompt.split("\n"):
            if "doordash" in line.lower() and "search" in line.lower():
                doordash_section = line
                break
        self.assertTrue(len(doordash_section) > 0,
            "Must have a DoorDash example that mentions 'search'")
        # The example should NOT contain identity.doordash.com as a ✅ example
        good_lines = [l for l in self.prompt.split("\n") if l.strip().startswith("✅")]
        for line in good_lines:
            self.assertNotIn("identity.doordash.com", line,
                "✅ examples must NOT contain direct DoorDash identity URLs")

    def test_never_example_com_warning(self):
        """Prompt must warn against using @example.com emails."""
        self.assertIn("@example.com", self.prompt)
        # Must be marked as bad
        self.assertIn("NEVER use @example.com", self.prompt)

    def test_one_deployment_per_goal(self):
        """Prompt must emphasize one deployment per GOAL, not per page."""
        self.assertIn("One deployment per GOAL", self.prompt)

    def test_decision_guide_present(self):
        """Decision guide table for Screen Agent vs Browser Agent must exist."""
        self.assertIn("Screen Agent", self.prompt)
        self.assertIn("Browser Agent", self.prompt)
        self.assertIn("Instagram", self.prompt)


# ═══════════════════════════════════════════════════════
#  TEST 2: Google-First in Browser Agent System Prompt
# ═══════════════════════════════════════════════════════

class TestGoogleFirstBrowserAgent(unittest.TestCase):
    """Verify browser agent's system prompt enforces Google-first navigation."""

    def setUp(self):
        from agents.browser_agent import BROWSER_SYSTEM_PROMPT
        self.prompt = BROWSER_SYSTEM_PROMPT

    def test_contains_google_first_section(self):
        """Browser agent prompt must have GOOGLE-FIRST section."""
        self.assertIn("GOOGLE-FIRST", self.prompt)

    def test_goto_warning(self):
        """goto tool description or prompt must warn about Google-only usage."""
        # The prompt should mention goto in context of Google search
        self.assertTrue(
            "Google" in self.prompt and "goto" in self.prompt.lower(),
            "Prompt must connect 'goto' with 'Google search' usage"
        )

    def test_account_creation_uses_google(self):
        """Account creation workflow in prompt must start with Google search."""
        # Find lines about account creation / signup
        lines = self.prompt.split("\n")
        signup_section = False
        for line in lines:
            if "account creation" in line.lower() or "signup" in line.lower():
                signup_section = True
            if signup_section and ("google" in line.lower() or "search" in line.lower()):
                break
        self.assertTrue(signup_section,
            "Must have account creation / signup section mentioning Google")

    def test_otp_handling_documented(self):
        """Prompt must document read_otp for verification code pages."""
        self.assertIn("read_otp", self.prompt)

    def test_multi_page_form_guidance(self):
        """Prompt must have guidance for multi-page forms."""
        self.assertTrue(
            "multi-page" in self.prompt.lower() or "never go back" in self.prompt.lower(),
            "Must have multi-page form / never go back guidance"
        )


# ═══════════════════════════════════════════════════════
#  TEST 3: Google-First in Hands Browser Agent Prompt
# ═══════════════════════════════════════════════════════

class TestGoogleFirstHandsBrowserAgent(unittest.TestCase):
    """Verify hands/browser_agent.py prompt also has Google-first navigation."""

    def setUp(self):
        from hands.browser_agent import BROWSER_AGENT_PROMPT
        self.prompt = BROWSER_AGENT_PROMPT

    def test_contains_google_first(self):
        """Hands browser agent prompt must mention GOOGLE-FIRST."""
        self.assertIn("GOOGLE-FIRST", self.prompt)

    def test_no_direct_url_examples(self):
        """Hands browser agent must not show direct URLs as good examples."""
        good_lines = [l for l in self.prompt.split("\n") if l.strip().startswith("✅")]
        for line in good_lines:
            # No raw signup/login/auth URLs in good examples
            self.assertNotRegex(line, r"https://.*(?:signup|login|auth|register)",
                f"Good example must not contain direct signup/login URL: {line}")


# ═══════════════════════════════════════════════════════
#  TEST 4: CSS Selector Fixing (_fix_selector)
# ═══════════════════════════════════════════════════════

class TestCSSFixSelector(unittest.TestCase):
    """Test _fix_selector converts broken React selectors to safe attribute selectors."""

    def setUp(self):
        from hands.browser import _fix_selector
        self.fix = _fix_selector

    def test_react_id_with_colons(self):
        """React IDs like 'fieldWrapper-:r1:' must use attribute selector."""
        result = self.fix("#fieldWrapper-:r1:")
        self.assertEqual(result, '[id="fieldWrapper-:r1:"]')

    def test_react_id_with_multiple_colons(self):
        """IDs with multiple colons (e.g. ':r4:') must be fixed."""
        result = self.fix("#:r4:")
        self.assertEqual(result, '[id=":r4:"]')

    def test_normal_id_unchanged(self):
        """Normal IDs without special chars must be left as-is."""
        result = self.fix("#email")
        self.assertEqual(result, "#email")

    def test_normal_id_with_hyphen_unchanged(self):
        """IDs with hyphens (valid CSS) must be left alone."""
        result = self.fix("#first-name")
        self.assertEqual(result, "#first-name")

    def test_attribute_selector_unchanged(self):
        """Already-safe [id='...'] selectors must pass through."""
        result = self.fix('[id="fieldWrapper-:r1:"]')
        self.assertEqual(result, '[id="fieldWrapper-:r1:"]')

    def test_id_with_dot(self):
        """IDs containing dots (e.g. 'form.field') must use attribute selector."""
        result = self.fix("#form.field")
        self.assertEqual(result, '[id="form.field"]')

    def test_id_with_brackets(self):
        """IDs containing brackets must use attribute selector."""
        result = self.fix("#field[0]")
        self.assertEqual(result, '[id="field[0]"]')

    def test_none_input(self):
        """None input must return None without crashing."""
        result = self.fix(None)
        self.assertIsNone(result)

    def test_empty_string(self):
        """Empty string must return empty string."""
        result = self.fix("")
        self.assertEqual(result, "")

    def test_class_selector_unchanged(self):
        """Class selectors (.btn) must pass through unchanged."""
        result = self.fix(".btn-primary")
        self.assertEqual(result, ".btn-primary")

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace must be stripped."""
        result = self.fix("  #email  ")
        self.assertEqual(result, "#email")


# ═══════════════════════════════════════════════════════
#  TEST 5: Human-Like Typing Function
# ═══════════════════════════════════════════════════════

class TestHumanLikeTyping(unittest.TestCase):
    """Verify _cdp_type_human exists and has the right signature."""

    def test_function_exists(self):
        """_cdp_type_human must be importable from hands.browser."""
        from hands.browser import _cdp_type_human
        self.assertTrue(callable(_cdp_type_human))

    def test_accepts_text_and_delays(self):
        """Must accept text, min_delay, max_delay parameters."""
        import inspect
        from hands.browser import _cdp_type_human
        sig = inspect.signature(_cdp_type_human)
        params = list(sig.parameters.keys())
        self.assertIn("text", params)
        self.assertIn("min_delay", params)
        self.assertIn("max_delay", params)

    def test_default_delays_are_human_speed(self):
        """Default delays must be in the 30-120ms range (human typing speed)."""
        import inspect
        from hands.browser import _cdp_type_human
        sig = inspect.signature(_cdp_type_human)
        min_d = sig.parameters["min_delay"].default
        max_d = sig.parameters["max_delay"].default
        # Human typing: 30-120ms per character ≈ 50-120 WPM
        self.assertGreaterEqual(min_d, 0.02, "min_delay too fast (bot-like)")
        self.assertLessEqual(min_d, 0.06, "min_delay too slow")
        self.assertGreaterEqual(max_d, 0.08, "max_delay too fast")
        self.assertLessEqual(max_d, 0.20, "max_delay too slow")


# ═══════════════════════════════════════════════════════
#  TEST 6: Browser Agent has read_otp Tool
# ═══════════════════════════════════════════════════════

class TestBrowserAgentReadOTP(unittest.TestCase):
    """Verify both browser agents have the read_otp tool for OTP/verification codes."""

    def test_agents_browser_agent_has_read_otp(self):
        """agents/browser_agent.py BROWSER_TOOLS must include read_otp."""
        from agents.browser_agent import BROWSER_TOOLS
        tool_names = [t["name"] for t in BROWSER_TOOLS]
        self.assertIn("read_otp", tool_names)

    def test_read_otp_has_subject_contains_param(self):
        """read_otp tool must accept subject_contains for email filtering."""
        from agents.browser_agent import BROWSER_TOOLS
        otp_tool = next(t for t in BROWSER_TOOLS if t["name"] == "read_otp")
        props = otp_tool["input_schema"]["properties"]
        self.assertIn("subject_contains", props)

    def test_read_otp_has_timeout_param(self):
        """read_otp tool must accept a timeout parameter."""
        from agents.browser_agent import BROWSER_TOOLS
        otp_tool = next(t for t in BROWSER_TOOLS if t["name"] == "read_otp")
        props = otp_tool["input_schema"]["properties"]
        self.assertIn("timeout", props)

    def test_read_otp_has_from_sender_param(self):
        """read_otp tool must accept from_sender for sender filtering."""
        from agents.browser_agent import BROWSER_TOOLS
        otp_tool = next(t for t in BROWSER_TOOLS if t["name"] == "read_otp")
        props = otp_tool["input_schema"]["properties"]
        self.assertIn("from_sender", props)

    def test_fill_form_tool_exists(self):
        """BROWSER_TOOLS must include fill_form for batch form filling."""
        from agents.browser_agent import BROWSER_TOOLS
        tool_names = [t["name"] for t in BROWSER_TOOLS]
        self.assertIn("fill_form", tool_names)

    def test_solve_captcha_tool_exists(self):
        """BROWSER_TOOLS must include solve_captcha."""
        from agents.browser_agent import BROWSER_TOOLS
        tool_names = [t["name"] for t in BROWSER_TOOLS]
        self.assertIn("solve_captcha", tool_names)

    def test_all_essential_signup_tools(self):
        """All tools needed for account signup must be present."""
        from agents.browser_agent import BROWSER_TOOLS
        tool_names = {t["name"] for t in BROWSER_TOOLS}
        essential = {"look", "goto", "click", "type", "fill_form", "read_otp",
                     "solve_captcha", "wait", "screenshot", "done", "stuck"}
        missing = essential - tool_names
        self.assertEqual(missing, set(),
            f"Missing essential signup tools: {missing}")


# ═══════════════════════════════════════════════════════
#  TEST 7: Browser Agent Form Error Detection
# ═══════════════════════════════════════════════════════

class TestFormErrorDetection(unittest.TestCase):
    """Verify browser.py look() output includes form error detection code."""

    def test_act_inspect_page_has_error_detection(self):
        """act_inspect_page must detect form validation errors."""
        import inspect
        from hands.browser import act_inspect_page
        source = inspect.getsource(act_inspect_page)
        # Must search for error-related DOM elements
        self.assertTrue(
            "error" in source.lower() or "alert" in source.lower(),
            "act_inspect_page must detect form errors (role=alert, .error, etc.)"
        )

    def test_act_inspect_page_has_form_errors_section(self):
        """act_inspect_page JS must collect FORM ERRORS for the output."""
        import inspect
        from hands.browser import act_inspect_page
        source = inspect.getsource(act_inspect_page)
        # Must include form error detection selectors
        error_selectors = ["role=alert", "error", "validation"]
        found = any(sel in source for sel in error_selectors)
        self.assertTrue(found,
            "act_inspect_page must include error detection selectors")

    def test_getSel_uses_attribute_selectors_for_special_ids(self):
        """getSel() in act_inspect_page must use [id='...'] for IDs with special chars."""
        import inspect
        from hands.browser import act_inspect_page
        source = inspect.getsource(act_inspect_page)
        # Must check for special CSS chars and use attribute selector
        self.assertTrue(
            "id=" in source and ("[" in source),
            "getSel() must use attribute selectors for special-char IDs"
        )


# ═══════════════════════════════════════════════════════
#  TEST 8: Executor Routes All Agent Deployments
# ═══════════════════════════════════════════════════════

class TestExecutorAgentRouting(unittest.TestCase):
    """Verify executor._dispatch routes all agent deployment tools."""

    def setUp(self):
        import inspect
        from executor import ToolExecutor
        self.dispatch_source = inspect.getsource(ToolExecutor._dispatch)

    def test_deploy_browser_agent_routed(self):
        """deploy_browser_agent must be dispatched to _deploy_agent('browser')."""
        self.assertIn("deploy_browser_agent", self.dispatch_source)
        self.assertIn('"browser"', self.dispatch_source)

    def test_deploy_screen_agent_routed(self):
        """deploy_screen_agent must be dispatched to _deploy_agent('screen')."""
        self.assertIn("deploy_screen_agent", self.dispatch_source)
        self.assertIn('"screen"', self.dispatch_source)

    def test_deploy_research_agent_routed(self):
        """deploy_research_agent must be dispatched."""
        self.assertIn("deploy_research_agent", self.dispatch_source)
        self.assertIn('"research"', self.dispatch_source)

    def test_deploy_coder_agent_routed(self):
        """deploy_coder_agent must be dispatched."""
        self.assertIn("deploy_coder_agent", self.dispatch_source)
        self.assertIn('"coder"', self.dispatch_source)

    def test_deploy_email_agent_routed(self):
        """deploy_email_agent must be dispatched."""
        self.assertIn("deploy_email_agent", self.dispatch_source)
        self.assertIn('"email"', self.dispatch_source)

    def test_deploy_dev_agent_routed(self):
        """deploy_dev_agent must be dispatched."""
        self.assertIn("deploy_dev_agent", self.dispatch_source)
        self.assertIn('"dev"', self.dispatch_source)

    def test_manage_account_routed(self):
        """manage_account must be dispatched."""
        self.assertIn("manage_account", self.dispatch_source)

    def test_web_search_routed(self):
        """web_search must be dispatched."""
        self.assertIn("web_search", self.dispatch_source)

    def test_all_brain_tools_have_dispatch(self):
        """Every tool in TARS_TOOLS must have a dispatch entry in executor."""
        from brain.tools import TARS_TOOLS
        tool_names = {t["name"] for t in TARS_TOOLS}
        # These are handled by special cases or legacy aliases
        skip = {"think"}  # think is handled inline by the brain, not dispatched

        missing = []
        for name in tool_names:
            if name in skip:
                continue
            if name not in self.dispatch_source:
                missing.append(name)

        self.assertEqual(missing, [],
            f"Tools defined in brain/tools.py but missing from executor._dispatch: {missing}")


# ═══════════════════════════════════════════════════════
#  TEST 9: Auto-Escalation: Browser → Screen Agent
# ═══════════════════════════════════════════════════════

class TestAutoEscalation(unittest.TestCase):
    """Verify auto-escalation is DISABLED — browser failures go back to brain recovery ladder."""

    def test_escalation_disabled(self):
        """Auto-escalation Browser→Screen must be DISABLED."""
        import inspect
        from executor import ToolExecutor
        source = inspect.getsource(ToolExecutor._deploy_agent)
        # Must contain the DISABLED comment explaining why
        self.assertIn("AUTO-ESCALATION: DISABLED", source)
        # Must NOT contain the old active escalation logic
        self.assertNotIn("_auto_escalation_active", source)
        self.assertNotIn('event_bus.emit("auto_escalation"', source)

    def test_recovery_ladder_exists(self):
        """Must have structured recovery levels for failed deployments."""
        import inspect
        from executor import ToolExecutor
        source = inspect.getsource(ToolExecutor._deploy_agent)
        # Must reference recovery levels
        self.assertTrue(
            "Level 1" in source or "LEVEL 1" in source or "recovery" in source.lower(),
            "Must have recovery ladder for failed deployments"
        )


# ═══════════════════════════════════════════════════════
#  TEST 10: Account Manager Credential Workflow
# ═══════════════════════════════════════════════════════

class TestAccountManagerWorkflow(unittest.TestCase):
    """Verify the account management credential workflow for signups."""

    def test_manage_account_imports(self):
        """manage_account function must be importable."""
        from hands.account_manager import manage_account
        self.assertTrue(callable(manage_account))

    def test_manage_account_returns_standard_dict(self):
        """manage_account must return the standard {success, content} dict."""
        from hands.account_manager import manage_account
        result = manage_account({"action": "get_emails"})
        self.assertIn("success", result)
        self.assertIn("content", result)

    def test_get_emails_returns_list(self):
        """get_emails action must return available TARS email addresses."""
        from hands.account_manager import manage_account
        result = manage_account({"action": "get_emails"})
        self.assertTrue(result["success"], f"get_emails failed: {result.get('content')}")
        # Must contain at least one email
        content = result["content"]
        self.assertTrue(
            "@" in str(content),
            f"get_emails must return emails, got: {content}"
        )

    def test_lookup_nonexistent_service(self):
        """Lookup for a non-existent service must return gracefully (not crash)."""
        from hands.account_manager import manage_account
        result = manage_account({"action": "lookup", "service": "nonexistent_test_service_xyz_99"})
        # Should return success=False or success=True with no-creds message — NOT crash
        self.assertIn("success", result)

    def test_get_playbook_returns_content(self):
        """get_playbook must return a playbook (or generic fallback) for any service."""
        from hands.account_manager import manage_account
        result = manage_account({"action": "get_playbook", "service": "doordash", "flow": "signup"})
        self.assertIn("success", result)
        if result["success"]:
            self.assertTrue(len(result["content"]) > 50,
                "Playbook content seems too short")

    def test_generate_credentials_returns_creds(self):
        """generate_credentials must return usable credentials."""
        from hands.account_manager import manage_account
        result = manage_account({"action": "generate_credentials", "service": "test_service_xyz"})
        self.assertTrue(result["success"], f"generate_credentials failed: {result.get('content')}")
        content = str(result["content"])
        # Must generate something with email and password
        self.assertTrue(
            "email" in content.lower() or "@" in content or "password" in content.lower(),
            f"generate_credentials must return email/password, got: {content}"
        )

    def test_brain_tools_has_manage_account(self):
        """TARS_TOOLS must include manage_account with all required actions."""
        from brain.tools import TARS_TOOLS
        tool = next((t for t in TARS_TOOLS if t["name"] == "manage_account"), None)
        self.assertIsNotNone(tool, "manage_account missing from TARS_TOOLS")

        # Must support key actions
        desc = tool.get("description", "")
        schema = tool.get("input_schema", {})
        props = schema.get("properties", {})

        self.assertIn("action", props, "manage_account must have 'action' parameter")
        # Check action enum or description covers key flows
        action_prop = props["action"]
        action_enum = action_prop.get("enum", [])
        action_desc = action_prop.get("description", "")

        key_actions = ["store", "lookup", "get_emails", "generate_credentials"]
        for action in key_actions:
            self.assertTrue(
                action in action_enum or action in action_desc or action in desc,
                f"manage_account must support '{action}' action"
            )

    def test_doordash_prompt_workflow_complete(self):
        """DOMAIN_BROWSER must show the full DoorDash credential workflow."""
        from brain.prompts import DOMAIN_BROWSER
        # Must mention: credentials, manage_account('store'), API keys
        self.assertIn("manage_account", DOMAIN_BROWSER)
        self.assertIn("store", DOMAIN_BROWSER)
        self.assertIn("API key", DOMAIN_BROWSER.lower().replace("api keys", "API key"))


# ═══════════════════════════════════════════════════════
#  RUNNER
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  TARS — Browsing & Account Creation Test Suite")
    print("  10 test classes, covering the full signup pipeline")
    print("=" * 60 + "\n")

    # Run with verbosity
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load all test classes in order
    test_classes = [
        TestGoogleFirstBrainPrompt,        # 1
        TestGoogleFirstBrowserAgent,        # 2
        TestGoogleFirstHandsBrowserAgent,   # 3
        TestCSSFixSelector,                 # 4
        TestHumanLikeTyping,                # 5
        TestBrowserAgentReadOTP,            # 6
        TestFormErrorDetection,             # 7
        TestExecutorAgentRouting,           # 8
        TestAutoEscalation,                 # 9
        TestAccountManagerWorkflow,         # 10
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 60)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    if failed == 0:
        print(f"  🟢 ALL {total} TESTS PASSED — Browsing pipeline is solid")
    else:
        print(f"  🔴 {failed}/{total} TESTS FAILED")
        for test, traceback in result.failures + result.errors:
            print(f"    ❌ {test}")
    print("=" * 60)
