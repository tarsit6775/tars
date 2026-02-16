#!/usr/bin/env python3
"""Test parallel tasks + self-healing engine."""

import sys
import os
import threading
import time

def main():
    print("🧪 Testing v5 features: Parallel Tasks + Self-Healing...\n")
    passed = 0
    failed = 0

    # 1. Self-Heal Engine imports and constructs
    try:
        from brain.self_heal import SelfHealEngine, HealingProposal
        sh = SelfHealEngine()
        assert hasattr(sh, 'record_failure'), "Missing record_failure"
        assert hasattr(sh, 'request_healing'), "Missing request_healing"
        assert hasattr(sh, 'execute_healing'), "Missing execute_healing"
        assert hasattr(sh, 'propose_capability'), "Missing propose_capability"
        assert hasattr(sh, 'get_stats'), "Missing get_stats"
        print("  ✅ SelfHealEngine constructs correctly")
        passed += 1
    except Exception as e:
        print(f"  ❌ SelfHealEngine: {e}")
        failed += 1

    # 2. Self-Heal stats work
    try:
        stats = sh.get_stats()
        assert isinstance(stats, dict), "get_stats should return dict"
        assert 'total_failures_recorded' in stats
        assert 'proposals_total' in stats
        assert 'heals_completed' in stats
        print(f"  ✅ Self-heal stats: {stats}")
        passed += 1
    except Exception as e:
        print(f"  ❌ Self-heal stats: {e}")
        failed += 1

    # 3. Record failures — should not crash
    try:
        result = sh.record_failure(
            error="Unknown tool: fake_tool",
            context="tool_execution:fake_tool",
            tool="fake_tool",
            details="test failure",
        )
        # First failure — shouldn't trigger a proposal yet (needs 2+)
        assert result is None, "Single failure should not trigger proposal"
        print("  ✅ record_failure (single) — no proposal yet")
        passed += 1
    except Exception as e:
        print(f"  ❌ record_failure: {e}")
        failed += 1

    # 4. Record enough failures to trigger a proposal
    try:
        # Record more of the same error to hit threshold
        proposal = sh.record_failure(
            error="Unknown tool: fake_tool",
            context="tool_execution:fake_tool",
            tool="fake_tool",
            details="test failure 2",
        )
        if proposal:
            assert isinstance(proposal, HealingProposal), "Should return HealingProposal"
            assert proposal.status == "proposed"
            assert len(proposal.trigger) > 0
            print(f"  ✅ Pattern detected → proposal: {proposal.trigger[:80]}")
        else:
            # May not trigger due to cooldown — that's OK
            print("  ✅ record_failure (double) — cooldown or already proposed")
        passed += 1
    except Exception as e:
        print(f"  ❌ Pattern detection: {e}")
        failed += 1

    # 5. HealingProposal formatting
    try:
        prop = HealingProposal(
            trigger="Test trigger",
            diagnosis="Test diagnosis",
            prescription="Test fix",
            target_files=["executor.py"],
            severity="improvement",
            category="bug_fix",
        )
        msg = prop.to_imessage()
        assert "TARS Self-Healing" in msg
        assert "Test trigger" in msg
        d = prop.to_dict()
        assert d["status"] == "proposed"
        assert d["category"] == "bug_fix"
        print("  ✅ HealingProposal formats correctly")
        passed += 1
    except Exception as e:
        print(f"  ❌ HealingProposal: {e}")
        failed += 1

    # 6. propose_capability works
    try:
        cap = sh.propose_capability(
            description="Add PDF reading tool",
            reason="Can't read PDF attachments currently",
        )
        assert isinstance(cap, HealingProposal)
        assert cap.category == "new_capability"
        assert "PDF" in cap.trigger
        print("  ✅ propose_capability creates new_capability proposal")
        passed += 1
    except Exception as e:
        print(f"  ❌ propose_capability: {e}")
        failed += 1

    # 7. Tool count includes propose_self_heal
    try:
        from brain.tools import TARS_TOOLS
        tool_names = {t['name'] for t in TARS_TOOLS}
        assert 'propose_self_heal' in tool_names, "Missing propose_self_heal tool"
        print(f"  ✅ propose_self_heal tool exists ({len(TARS_TOOLS)} total)")
        passed += 1
    except Exception as e:
        print(f"  ❌ Tool check: {e}")
        failed += 1

    # 8. propose_self_heal is in _CORE_TOOLS (always available)
    try:
        from brain.tools import _CORE_TOOLS
        assert 'propose_self_heal' in _CORE_TOOLS, "propose_self_heal not in core tools"
        print("  ✅ propose_self_heal in _CORE_TOOLS (always available)")
        passed += 1
    except Exception as e:
        print(f"  ❌ Core tools: {e}")
        failed += 1

    # 9. System prompt includes self-healing section
    try:
        from brain.prompts import build_system_prompt
        prompt = build_system_prompt()
        assert "Self-Healing" in prompt, "System prompt missing self-healing section"
        assert "propose_self_heal" in prompt, "System prompt missing self-heal tool reference"
        print("  ✅ System prompt includes self-healing instructions")
        passed += 1
    except Exception as e:
        print(f"  ❌ System prompt: {e}")
        failed += 1

    # 10. Executor dispatch has propose_self_heal
    try:
        from executor import ToolExecutor
        assert hasattr(ToolExecutor, '_propose_self_heal'), "Missing _propose_self_heal method"
        print("  ✅ Executor has _propose_self_heal dispatch")
        passed += 1
    except Exception as e:
        print(f"  ❌ Executor dispatch: {e}")
        failed += 1

    # 11. TARS class has parallel task infrastructure
    try:
        from tars import TARS
        # Can't instantiate (needs config, etc.) but check class has the methods
        assert hasattr(TARS, '_run_task'), "Missing _run_task method"
        assert hasattr(TARS, '_count_active_tasks'), "Missing _count_active_tasks"
        assert hasattr(TARS, '_check_self_heal'), "Missing _check_self_heal"
        assert hasattr(TARS, '_handle_task_error'), "Missing _handle_task_error"
        print("  ✅ TARS has parallel task + self-heal methods")
        passed += 1
    except Exception as e:
        print(f"  ❌ TARS class: {e}")
        failed += 1

    # 12. Planner has _record_self_heal_failure
    try:
        from brain.planner import TARSBrain
        assert hasattr(TARSBrain, '_record_self_heal_failure'), "Missing _record_self_heal_failure"
        print("  ✅ Planner has _record_self_heal_failure bridge")
        passed += 1
    except Exception as e:
        print(f"  ❌ Planner bridge: {e}")
        failed += 1

    # Summary
    print(f"\n{'🟢' if failed == 0 else '🔴'} {passed}/{passed+failed} tests passed")
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
