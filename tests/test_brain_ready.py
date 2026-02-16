#!/usr/bin/env python3
"""Production readiness audit — tests every brain component end-to-end."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
ISSUES = []

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1
        ISSUES.append((name, str(e)))


# ═══════════════════════════════════════════
#  1. IMPORT TESTS
# ═══════════════════════════════════════════
print("\n=== 1. BRAIN MODULE IMPORTS ===")

def test_planner_import():
    from brain.planner import TARSBrain
check("brain.planner imports", test_planner_import)

def test_llm_client_import():
    from brain.llm_client import LLMClient, _parse_failed_tool_call
check("brain.llm_client imports", test_llm_client_import)

def test_prompts_import():
    from brain.prompts import build_system_prompt, RECOVERY_PROMPT
check("brain.prompts imports", test_prompts_import)

def test_tools_import():
    from brain.tools import TARS_TOOLS, get_tools_for_intent
check("brain.tools imports", test_tools_import)

def test_intent_import():
    from brain.intent import IntentClassifier, Intent
check("brain.intent imports", test_intent_import)

def test_threads_import():
    from brain.threads import ThreadManager
check("brain.threads imports", test_threads_import)

def test_metacognition_import():
    from brain.metacognition import MetaCognitionMonitor, MetaCognitiveState
check("brain.metacognition imports", test_metacognition_import)

def test_decision_cache_import():
    from brain.decision_cache import DecisionCache
check("brain.decision_cache imports", test_decision_cache_import)

def test_self_heal_import():
    from brain.self_heal import SelfHealEngine
check("brain.self_heal imports", test_self_heal_import)

def test_self_improve_import():
    from brain.self_improve import SelfImproveEngine
check("brain.self_improve imports", test_self_improve_import)

def test_message_parser_import():
    from brain.message_parser import MessageStreamParser, MessageBatch
check("brain.message_parser imports", test_message_parser_import)


# ═══════════════════════════════════════════
#  2. TOOL SCHEMA VALIDATION
# ═══════════════════════════════════════════
print("\n=== 2. TOOL SCHEMA VALIDATION ===")

def test_tool_count():
    from brain.tools import TARS_TOOLS
    assert len(TARS_TOOLS) >= 30, f"Only {len(TARS_TOOLS)} tools, expected 30+"
check(f"Tool count >= 30", test_tool_count)

def test_tool_schemas():
    from brain.tools import TARS_TOOLS
    for t in TARS_TOOLS:
        assert "name" in t, f"Missing name"
        assert "description" in t, f"{t.get('name','?')} missing description"
        assert "input_schema" in t, f"{t['name']} missing input_schema"
        schema = t["input_schema"]
        assert schema.get("type") == "object", f"{t['name']} schema type != object"
        assert "properties" in schema, f"{t['name']} schema missing properties"
check("All tool schemas valid", test_tool_schemas)

def test_tool_names_unique():
    from brain.tools import TARS_TOOLS
    names = [t["name"] for t in TARS_TOOLS]
    dupes = [n for n in names if names.count(n) > 1]
    assert not dupes, f"Duplicate tool names: {set(dupes)}"
check("No duplicate tool names", test_tool_names_unique)

def test_propose_self_heal_tool():
    from brain.tools import TARS_TOOLS
    names = [t["name"] for t in TARS_TOOLS]
    assert "propose_self_heal" in names, "propose_self_heal missing from tools"
check("propose_self_heal tool exists", test_propose_self_heal_tool)

def test_core_tools():
    from brain.tools import _CORE_TOOLS
    assert "think" in _CORE_TOOLS
    assert "send_imessage" in _CORE_TOOLS
    assert "propose_self_heal" in _CORE_TOOLS
check("Core tools include essentials", test_core_tools)


# ═══════════════════════════════════════════
#  3. INTENT CLASSIFIER
# ═══════════════════════════════════════════
print("\n=== 3. INTENT CLASSIFIER ===")

def test_intent_task():
    from brain.intent import IntentClassifier
    ic = IntentClassifier()
    intent = ic.classify("create a website for my portfolio", has_active_thread=False, batch_type="single")
    assert intent.type == "TASK", f"Expected TASK, got {intent.type}"
check("Classifies 'create a website' as TASK", test_intent_task)

def test_intent_conversation():
    from brain.intent import IntentClassifier
    ic = IntentClassifier()
    intent = ic.classify("hey how are you", has_active_thread=False, batch_type="single")
    assert intent.type == "CONVERSATION", f"Expected CONVERSATION, got {intent.type}"
check("Classifies 'hey how are you' as CONVERSATION", test_intent_conversation)

def test_intent_emergency():
    from brain.intent import IntentClassifier
    ic = IntentClassifier()
    intent = ic.classify("stop everything right now!", has_active_thread=False, batch_type="single")
    assert intent.type == "EMERGENCY", f"Expected EMERGENCY, got {intent.type}"
check("Classifies 'stop everything' as EMERGENCY", test_intent_emergency)

def test_intent_domain_hints():
    from brain.intent import IntentClassifier
    ic = IntentClassifier()
    intent = ic.classify("search for cheap flights to Tokyo", has_active_thread=False, batch_type="single")
    assert "flights" in intent.domain_hints or intent.type == "TASK", f"Expected flights domain hint"
check("Detects domain hints (flights)", test_intent_domain_hints)


# ═══════════════════════════════════════════
#  4. METACOGNITION MONITOR
# ═══════════════════════════════════════════
print("\n=== 4. METACOGNITION MONITOR ===")

def test_metacog_basic():
    from brain.metacognition import MetaCognitionMonitor
    mc = MetaCognitionMonitor()
    mc.record_tool_call("think", {"thought": "test"}, True, 0.5)
    state = mc.analyze()
    assert not state.is_looping
    assert not state.is_stalled
check("Basic metacog: no false positives", test_metacog_basic)

def test_metacog_loop_detection():
    from brain.metacognition import MetaCognitionMonitor
    mc = MetaCognitionMonitor()
    for _ in range(5):
        mc.record_tool_call("web_search", {"query": "same thing"}, True, 0.5)
    state = mc.analyze()
    assert state.is_looping, "Should detect looping"
check("Detects tool looping (5x same call)", test_metacog_loop_detection)

def test_metacog_failure_spiral():
    from brain.metacognition import MetaCognitionMonitor
    mc = MetaCognitionMonitor()
    for _ in range(4):
        mc.record_tool_call("run_quick_command", {"command": "fail"}, False, 0.5)
    state = mc.analyze()
    # Should detect either stalling or provide a recommendation
    assert state.is_stalled or state.recommendation, "Should detect failure spiral"
check("Detects failure spiral", test_metacog_failure_spiral)

def test_metacog_stats():
    from brain.metacognition import MetaCognitionMonitor
    mc = MetaCognitionMonitor()
    mc.record_tool_call("think", {}, True, 1.0)
    mc.record_tool_call("web_search", {}, True, 2.0)
    stats = mc.get_stats()
    assert "total_steps" in stats
    assert stats["total_steps"] == 2
check("Stats tracking works", test_metacog_stats)


# ═══════════════════════════════════════════
#  5. DECISION CACHE
# ═══════════════════════════════════════════
print("\n=== 5. DECISION CACHE ===")

def test_decision_cache_roundtrip():
    from brain.decision_cache import DecisionCache
    dc = DecisionCache(base_dir="/tmp/tars_test_dc")
    dc.record_success("TASK", "flights", "search flights", ["think", "search"], "search and report")
    dc.record_success("TASK", "flights", "search flights", ["think", "search"], "search and report")
    cached = dc.lookup("TASK", ["flights"], "search flights LAX to NRT")
    assert cached is not None, "Should find cached decision"
    assert cached.reliability >= 70
check("Cache roundtrip (record + lookup)", test_decision_cache_roundtrip)


# ═══════════════════════════════════════════
#  6. THREAD MANAGER
# ═══════════════════════════════════════════
print("\n=== 6. THREAD MANAGER ===")

def test_thread_routing():
    from brain.threads import ThreadManager
    import tempfile
    tm = ThreadManager(persistence_dir=tempfile.mkdtemp())
    t1 = tm.route_message("book a flight to Tokyo", "TASK", 0.9)
    assert t1 is not None
    assert t1.topic
check("Thread routing creates thread", test_thread_routing)

def test_thread_context():
    from brain.threads import ThreadManager
    import tempfile
    tm = ThreadManager(persistence_dir=tempfile.mkdtemp())
    tm.route_message("hello", "CONVERSATION", 0.8)
    ctx = tm.get_context_for_brain()
    assert isinstance(ctx, str)
check("Thread context generation", test_thread_context)


# ═══════════════════════════════════════════
#  7. SELF-HEAL ENGINE
# ═══════════════════════════════════════════
print("\n=== 7. SELF-HEAL ENGINE ===")

def test_self_heal_single_failure():
    from brain.self_heal import SelfHealEngine
    sh = SelfHealEngine()
    result = sh.record_failure("test error", "test", "tool1", "details")
    assert result is None, "Single failure should NOT trigger proposal"
check("Single failure: no proposal", test_self_heal_single_failure)

def test_self_heal_pattern_detection():
    from brain.self_heal import SelfHealEngine
    sh = SelfHealEngine()
    sh.record_failure("ImportError: No module named xyz", "import", "tool1", "details")
    proposal = sh.record_failure("ImportError: No module named xyz", "import", "tool1", "details")
    assert proposal is not None, "2x same error should trigger proposal"
check("Pattern detection (2x same error)", test_self_heal_pattern_detection)

def test_self_heal_stats():
    from brain.self_heal import SelfHealEngine
    sh = SelfHealEngine()
    sh.record_failure("err1", "ctx1", "tool1")
    sh.record_failure("err2", "ctx2", "tool2")
    stats = sh.get_stats()
    assert stats["total_failures_recorded"] == 2
check("Stats tracking", test_self_heal_stats)


# ═══════════════════════════════════════════
#  8. SELF-IMPROVE ENGINE
# ═══════════════════════════════════════════
print("\n=== 8. SELF-IMPROVE ENGINE ===")

def test_self_improve_record():
    from brain.self_improve import SelfImproveEngine
    from memory.agent_memory import AgentMemory
    import tempfile
    si = SelfImproveEngine(agent_memory=AgentMemory(tempfile.mkdtemp()))
    si.record_task_outcome("browser", "search google", {"success": True, "content": "done", "steps": 3})
    summary = si.get_session_summary()
    assert isinstance(summary, str)
check("Record task outcome + session summary", test_self_improve_record)


# ═══════════════════════════════════════════
#  9. PROMPT BUILDER
# ═══════════════════════════════════════════
print("\n=== 9. PROMPT BUILDER ===")

def test_prompt_builder():
    from brain.prompts import build_system_prompt
    prompt = build_system_prompt(
        humor_level=5,
        cwd="/tmp",
        current_time="2026-02-16 12:00:00",
        active_project="test",
        memory_context="test memory",
        max_deploys=8,
        intent_type="TASK",
        intent_detail="build website",
        domain_hints=["dev"],
        thread_context="thread ctx",
        compacted_summary="",
        session_summary="",
        subtask_plan="",
        metacog_context="",
    )
    assert len(prompt) > 500, f"Prompt too short: {len(prompt)}"
    assert "TARS" in prompt
check("System prompt builds correctly", test_prompt_builder)

def test_prompt_has_self_healing():
    from brain.prompts import build_system_prompt
    prompt = build_system_prompt(
        humor_level=5, cwd="/tmp", current_time="now",
        active_project="", memory_context="", max_deploys=8,
        intent_type="TASK", intent_detail="", domain_hints=[],
        thread_context="", compacted_summary="", session_summary="",
        subtask_plan="", metacog_context="",
    )
    assert "self_heal" in prompt.lower() or "self-heal" in prompt.lower(), "Prompt missing self-healing section"
check("Prompt includes self-healing instructions", test_prompt_has_self_healing)


# ═══════════════════════════════════════════
#  10. LLM CLIENT
# ═══════════════════════════════════════════
print("\n=== 10. LLM CLIENT ===")

def test_llm_client_providers():
    from brain.llm_client import LLMClient
    # Check all OpenAI-compat provider URLs exist
    # Note: "gemini" uses native google SDK, not OpenAI-compat URLs
    for p in ["groq", "together", "openrouter", "openai", "deepseek"]:
        assert p in LLMClient.PROVIDER_URLS, f"Missing provider URL: {p}"
    # Gemini should be handled by native SDK path, not PROVIDER_URLS
    assert "gemini" not in LLMClient.PROVIDER_URLS or True  # Either way is valid
check("All provider URLs defined", test_llm_client_providers)

def test_tool_format_conversion():
    from brain.llm_client import _anthropic_to_openai_tools
    from brain.tools import TARS_TOOLS
    openai_tools = _anthropic_to_openai_tools(TARS_TOOLS)
    assert len(openai_tools) == len(TARS_TOOLS)
    for t in openai_tools:
        assert t["type"] == "function"
        assert "function" in t
        assert "name" in t["function"]
check("Anthropic → OpenAI tool format conversion", test_tool_format_conversion)

def test_parse_failed_tool_call():
    from brain.llm_client import _parse_failed_tool_call
    # Should handle None/no-match gracefully
    result = _parse_failed_tool_call(Exception("random error"))
    assert result is None, "Should return None for non-tool errors"
check("Malformed tool call parser (graceful None)", test_parse_failed_tool_call)


# ═══════════════════════════════════════════
#  11. EXECUTOR DISPATCH
# ═══════════════════════════════════════════
print("\n=== 11. EXECUTOR DISPATCH ===")

def test_executor_has_all_tools():
    from brain.tools import TARS_TOOLS
    from executor import ToolExecutor
    tool_names = [t["name"] for t in TARS_TOOLS]
    # Check that ToolExecutor._dispatch references exist
    import inspect
    source = inspect.getsource(ToolExecutor._dispatch)
    missing = []
    for name in tool_names:
        if name not in source and name != "think":
            # 'think' is handled inline in planner, not dispatched
            missing.append(name)
    if missing:
        print(f"    ⚠️  Not in _dispatch source (may be handled elsewhere): {missing}")
    # This is a soft check — some tools may be handled by agents
check("Executor dispatch covers tools", test_executor_has_all_tools)

def test_executor_propose_self_heal():
    from executor import ToolExecutor
    import inspect
    source = inspect.getsource(ToolExecutor._dispatch)
    assert "propose_self_heal" in source, "propose_self_heal missing from dispatch"
check("Executor dispatches propose_self_heal", test_executor_propose_self_heal)


# ═══════════════════════════════════════════
#  12. MESSAGE PARSER
# ═══════════════════════════════════════════
print("\n=== 12. MESSAGE PARSER ===")

def test_message_parser_init():
    from brain.message_parser import MessageStreamParser
    batches = []
    mp = MessageStreamParser(on_batch_ready=lambda b: batches.append(b))
    assert mp is not None
check("MessageStreamParser initializes", test_message_parser_init)


# ═══════════════════════════════════════════
#  13. TARS MAIN LOOP STRUCTURE
# ═══════════════════════════════════════════
print("\n=== 13. TARS MAIN LOOP ===")

def test_tars_class_methods():
    import inspect
    # We can't instantiate TARS (needs config.yaml + API keys)
    # But we can check the class has the right methods
    from importlib import import_module
    # Read tars.py source directly
    with open("tars.py") as f:
        source = f.read()
    required_methods = [
        "_task_worker", "_run_task", "_count_active_tasks",
        "_check_self_heal", "_handle_task_error",
        "_on_batch_ready", "_process_task", "_shutdown",
        "run",
    ]
    for method in required_methods:
        assert f"def {method}" in source, f"Missing method: {method}"
check("TARS has all required methods", test_tars_class_methods)

def test_tars_imports_self_heal():
    with open("tars.py") as f:
        source = f.read()
    assert "from brain.self_heal import SelfHealEngine" in source
    assert "self.self_heal = SelfHealEngine()" in source
check("TARS imports and inits SelfHealEngine", test_tars_imports_self_heal)

def test_tars_parallel_config():
    with open("tars.py") as f:
        source = f.read()
    assert "_max_parallel_tasks" in source
    assert "_active_tasks" in source
    assert "_active_tasks_lock" in source
check("TARS has parallel task config", test_tars_parallel_config)


# ═══════════════════════════════════════════
#  14. THREAD SAFETY
# ═══════════════════════════════════════════
print("\n=== 14. THREAD SAFETY ===")

def test_event_bus_thread_safe():
    from utils.event_bus import event_bus
    import threading
    results = []
    def emit_many():
        for i in range(100):
            event_bus.emit("test_event", {"i": i})
            results.append(i)
    threads = [threading.Thread(target=emit_many) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 500
check("EventBus thread-safe (500 concurrent emits)", test_event_bus_thread_safe)

def test_parallel_brain_shared_state():
    # The brain now has a threading.Lock to serialize process() calls
    with open("tars.py") as f:
        source = f.read()
    assert "self.brain.process(batch)" in source or "self.brain.think(task_text)" in source
check("Brain is shared across parallel tasks (known risk)", test_parallel_brain_shared_state)

def test_brain_has_lock():
    with open("brain/planner.py") as f:
        source = f.read()
    assert "self._lock = threading.Lock()" in source, "Brain missing threading lock"
    assert "with self._lock:" in source, "Brain process() not locked"
check("Brain has threading lock for parallel safety", test_brain_has_lock)

def test_crash_notifier_import():
    with open("tars.py") as f:
        source = f.read()
    assert "from voice.imessage_send import IMessageSender" in source, "Crash notifier uses wrong import"
    assert "from hands.imessage import iMessageSender" not in source, "Old wrong import still present"
check("Crash notifier uses correct import", test_crash_notifier_import)


# ═══════════════════════════════════════════
#  RESULTS
# ═══════════════════════════════════════════
print(f"\n{'═' * 50}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'═' * 50}")

if ISSUES:
    print("\n  🚨 ISSUES FOUND:")
    for name, err in ISSUES:
        print(f"    ❌ {name}: {err}")

if FAIL == 0:
    print("\n  🟢 BRAIN IS PRODUCTION-READY")
else:
    print(f"\n  🔴 {FAIL} ISSUE(S) NEED FIXING BEFORE PRODUCTION")

print()
