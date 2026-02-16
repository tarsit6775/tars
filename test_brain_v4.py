#!/usr/bin/env python3
"""Brain v4 integration test — Phases 1-6."""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_phase_1():
    """Phase 1: Message Stream Parser."""
    print("Testing Phase 1: Message Stream Parser...")
    from brain.message_parser import MessageStreamParser, MessageBatch

    batches = []
    parser = MessageStreamParser(on_batch_ready=lambda b: batches.append(b))
    
    # Test single message (force flush since we can't wait 3s in test)
    parser.ingest("search flights to NYC")
    parser.force_flush()
    assert len(batches) == 1
    assert batches[0].batch_type == "single"
    assert batches[0].merged_text == "search flights to NYC"
    print("  ✅ Single message parsed")

    # Test correction detection
    batches.clear()
    parser.ingest("search flights to NYC")
    parser.ingest("actually make it Tokyo")
    parser.force_flush()
    assert len(batches) == 1
    b = batches[0]
    assert b.batch_type == "correction"
    print(f"  ✅ Correction detected: '{b.merged_text}'")

    # Test addition detection
    batches.clear()
    parser.ingest("search flights to NYC")
    parser.ingest("also check hotels")
    parser.force_flush()
    assert len(batches) == 1
    b = batches[0]
    assert b.batch_type == "addition"
    print(f"  ✅ Addition detected: '{b.merged_text}'")

    # Test acknowledgment immediate flush
    batches.clear()
    parser.ingest("ok")
    time.sleep(0.1)  # Give it a moment to emit
    assert len(batches) == 1
    assert batches[0].batch_type == "single"
    print("  ✅ Acknowledgment flushed immediately")

    print("  ✅ Phase 1 PASSED\n")

def test_phase_2():
    """Phase 2: Intent Classifier."""
    print("Testing Phase 2: Intent Classifier...")
    from brain.intent import IntentClassifier, Intent

    c = IntentClassifier()

    # Task detection
    i = c.classify("search flights from Tampa to NYC")
    assert i.type == "TASK"
    assert i.is_actionable
    assert "flights" in i.domain_hints
    print(f"  ✅ Task: {i}")

    # Conversation detection
    i = c.classify("hey whats up")
    assert i.type == "CONVERSATION"
    assert i.is_conversational
    print(f"  ✅ Conversation: {i}")

    # Acknowledgment detection
    i = c.classify("ok go ahead")
    assert i.type == "ACKNOWLEDGMENT"
    print(f"  ✅ Acknowledgment: {i}")

    # Follow-up detection
    i = c.classify("did it work?", has_active_thread=True)
    assert i.type == "FOLLOW_UP"
    assert i.needs_context
    print(f"  ✅ Follow-up: {i}")

    # Quick question
    i = c.classify("what time is it?")
    assert i.type == "QUICK_QUESTION"
    print(f"  ✅ Quick question: {i}")

    # Emergency
    i = c.classify("stop everything now!")
    assert i.type == "EMERGENCY"
    print(f"  ✅ Emergency: {i}")

    # Correction
    i = c.classify("actually make it business class", batch_type="correction")
    assert i.type == "CORRECTION"
    assert i.needs_context
    print(f"  ✅ Correction: {i}")

    # Domain detection
    i = c.classify("build a react app with TypeScript")
    assert "dev" in i.domain_hints
    print(f"  ✅ Dev domain: {i}")

    i = c.classify("send an email to john about the meeting")
    assert "email" in i.domain_hints
    print(f"  ✅ Email domain: {i}")

    print("  ✅ Phase 2 PASSED\n")

def test_phase_3():
    """Phase 3: Conversation Threading."""
    print("Testing Phase 3: Conversation Threading...")
    from brain.threads import ThreadManager

    tm = ThreadManager()
    assert not tm.has_active_thread

    # New task creates thread
    t1 = tm.route_message("search flights TPA to NYC", "TASK", 0.85)
    assert tm.has_active_thread
    assert t1.id == tm.active_thread.id
    print(f"  ✅ Thread created: {t1.topic} ({t1.id})")

    # Follow-up goes to same thread
    t2 = tm.route_message("make it nonstop", "FOLLOW_UP", 0.8)
    assert t2.id == t1.id
    print(f"  ✅ Follow-up routed to same thread: {t2.id}")

    # Acknowledgment goes to same thread
    t3 = tm.route_message("ok", "ACKNOWLEDGMENT", 0.95)
    assert t3.id == t1.id
    print(f"  ✅ Acknowledgment routed to same thread: {t3.id}")

    # New task creates new thread
    t4 = tm.route_message("send email to john", "TASK", 0.85)
    assert t4.id != t1.id
    print(f"  ✅ New task creates new thread: {t4.id}")

    # Record response
    tm.record_response("On it! Searching flights...")
    assert len(tm.active_thread.messages) > 0
    print("  ✅ Response recorded")

    # Decision journal
    tm.log_decision("search_flights", "User wants TPA→NYC nonstop", 85)
    tm.update_decision_outcome("success")
    print("  ✅ Decision logged and outcome updated")

    # Context for brain
    ctx = tm.get_context_for_brain()
    assert len(ctx) > 0
    print(f"  ✅ Context for brain: {len(ctx)} chars")

    # Thread stats
    stats = tm.get_thread_stats()
    assert stats["total_threads"] >= 2
    print(f"  ✅ Stats: {stats}")

    print("  ✅ Phase 3 PASSED\n")

def test_phase_5():
    """Phase 5: System Prompt v2."""
    print("Testing Phase 5: System Prompt v2...")
    from brain.prompts import build_system_prompt, RECOVERY_PROMPT

    # Basic prompt (no domain injection)
    p1 = build_system_prompt(humor_level=75, intent_type="CONVERSATION")
    assert "TARS" in p1
    assert len(p1) > 500
    print(f"  ✅ Conversation prompt: {len(p1)} chars")

    # Task with flight domain
    p2 = build_system_prompt(
        humor_level=75,
        intent_type="TASK",
        domain_hints=["flights"],
        thread_context="Thread: search flights TPA→NYC",
    )
    assert len(p2) > len(p1)  # Should be longer with domain
    assert "FLIGHT" in p2.upper() or "flight" in p2.lower()
    print(f"  ✅ Task+flights prompt: {len(p2)} chars (domain injected)")

    # Task with dev domain
    p3 = build_system_prompt(
        humor_level=75,
        intent_type="TASK",
        domain_hints=["dev"],
    )
    assert "Dev Agent" in p3 or "dev" in p3.lower()
    print(f"  ✅ Task+dev prompt: {len(p3)} chars")

    # Recovery prompt
    assert len(RECOVERY_PROMPT) > 100
    print(f"  ✅ Recovery prompt: {len(RECOVERY_PROMPT)} chars")

    print("  ✅ Phase 5 PASSED\n")

def test_phase_6():
    """Phase 6: web_search tool + updated dev_agent."""
    print("Testing Phase 6: Tools update...")
    from brain.tools import TARS_TOOLS

    names = [t["name"] for t in TARS_TOOLS]

    assert "web_search" in names, "web_search tool missing!"
    print(f"  ✅ web_search tool present ({len(TARS_TOOLS)} total tools)")

    assert "deploy_dev_agent" in names
    dev_tool = next(t for t in TARS_TOOLS if t["name"] == "deploy_dev_agent")
    assert "VS Code Agent Mode" in dev_tool["description"] or "Claude Opus" in dev_tool["description"]
    print(f"  ✅ deploy_dev_agent updated to v2")

    ws_tool = next(t for t in TARS_TOOLS if t["name"] == "web_search")
    assert "query" in ws_tool["input_schema"]["properties"]
    print(f"  ✅ web_search schema has 'query' param")

    print("  ✅ Phase 6 PASSED\n")

def test_wiring():
    """Test tars.py imports work."""
    print("Testing tars.py wiring...")
    from brain.message_parser import MessageStreamParser, MessageBatch
    
    # Simulate what tars.py does
    batch = MessageBatch(
        messages=[],
        merged_text="test task",
        batch_type="single",
        timestamp=time.time(),
    )
    assert batch.merged_text == "test task"
    print("  ✅ MessageBatch creation works")

    # Test batch types used in _on_batch_ready
    multi_batch = MessageBatch(
        messages=[],
        merged_text="task1 | task2",
        batch_type="multi_task",
        individual_tasks=["task1", "task2"],
        timestamp=time.time(),
    )
    assert len(multi_batch.individual_tasks) == 2
    print("  ✅ Multi-task batch works")

    print("  ✅ Wiring PASSED\n")

if __name__ == "__main__":
    print("=" * 60)
    print("  TARS Brain v4 — Integration Tests")
    print("=" * 60)
    print()

    try:
        test_phase_1()
        test_phase_2()
        test_phase_3()
        test_phase_5()
        test_phase_6()
        test_wiring()

        print("=" * 60)
        print("  ✅ ALL PHASES PASS — Brain v4 is ready!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
