#!/usr/bin/env python3
"""Test all brain v5 bug fixes."""

import sys
import os

def main():
    print("🧪 Testing brain v5 bug fixes...\n")
    passed = 0
    failed = 0

    # 1. MetaCognitionMonitor API
    try:
        from brain.metacognition import MetaCognitionMonitor, MetaCognitiveState
        mc = MetaCognitionMonitor()
        state = mc.analyze()
        assert isinstance(state, MetaCognitiveState), "analyze() should return MetaCognitiveState"
        assert hasattr(state, 'recommendation'), "Missing recommendation attr"
        assert hasattr(state, 'is_looping'), "Missing is_looping attr"
        assert hasattr(state, 'is_stalled'), "Missing is_stalled attr"
        assert hasattr(state, 'confidence_trend'), "Missing confidence_trend attr"
        stats = mc.get_stats()
        assert isinstance(stats, dict), "get_stats should return dict"
        assert 'total_steps' in stats, "Missing total_steps in stats"
        assert 'consecutive_failures' in stats, "Missing consecutive_failures in stats"
        injection = mc.get_injection()
        assert injection is None or isinstance(injection, str), "get_injection wrong type"
        print("  ✅ MetaCognitionMonitor API correct")
        passed += 1
    except Exception as e:
        print(f"  ❌ MetaCognitionMonitor: {e}")
        failed += 1

    # 2. DecisionCache API
    try:
        from brain.decision_cache import DecisionCache
        dc = DecisionCache(base_dir='/tmp/test_dc_fixes')
        result = dc.lookup('TASK', ['general'], 'test')
        assert result is None or hasattr(result, 'reliability'), "lookup wrong return type"
        print("  ✅ DecisionCache API correct")
        passed += 1
    except Exception as e:
        print(f"  ❌ DecisionCache: {e}")
        failed += 1

    # 3. ThreadManager has add_subtasks (plural), NOT add_subtask (singular)
    try:
        from brain.threads import ThreadManager
        tm = ThreadManager()
        assert hasattr(tm, 'add_subtasks'), "ThreadManager missing add_subtasks"
        assert not hasattr(tm, 'add_subtask'), "ThreadManager should NOT have add_subtask"
        # Test that add_subtasks accepts list of dicts
        thread = tm.route_message("test task", "TASK", 0.9)
        tm.add_subtasks([{"description": "step 1", "agent": "auto", "depends_on": []}])
        print("  ✅ ThreadManager.add_subtasks(list of dicts) works")
        passed += 1
    except Exception as e:
        print(f"  ❌ ThreadManager: {e}")
        failed += 1

    # 4. TARSBrain imports cleanly
    try:
        from brain.planner import TARSBrain
        print("  ✅ TARSBrain imports clean")
        passed += 1
    except Exception as e:
        print(f"  ❌ TARSBrain import: {e}")
        failed += 1

    # 5. Tool names match what planner references
    try:
        from brain.tools import TARS_TOOLS
        tool_names = {t['name'] for t in TARS_TOOLS}
        assert 'deploy_coder_agent' in tool_names, "Missing deploy_coder_agent"
        assert 'deploy_file_agent' in tool_names, "Missing deploy_file_agent"
        assert 'run_quick_command' in tool_names, "Missing run_quick_command"
        # These SHOULD NOT exist (they were the wrong names):
        assert 'code_task' not in tool_names, "code_task should not exist"
        print(f"  ✅ {len(TARS_TOOLS)} tools with correct names")
        passed += 1
    except Exception as e:
        print(f"  ❌ Tool names: {e}")
        failed += 1

    # 6. Verify planner methods don't crash on init
    brain = None
    try:
        import yaml
        import threading
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
        from brain.planner import TARSBrain
        from executor import ToolExecutor
        from memory.memory_manager import MemoryManager
        from voice.imessage_send import IMessageSender
        from voice.imessage_read import IMessageReader
        from utils.logger import setup_logger

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        mm = MemoryManager(config, BASE_DIR)
        logger = setup_logger(config, BASE_DIR)
        sender = IMessageSender(config)
        reader = IMessageReader(config)
        kill_event = threading.Event()
        te = ToolExecutor(config, sender, reader, mm, logger, kill_event=kill_event)
        brain = TARSBrain(config, te, mm)

        # Test get_thread_stats (was crashing with .state)
        stats = brain.get_thread_stats()
        assert 'metacognition' in stats, "Missing metacognition in stats"
        assert 'total_tool_calls' in stats['metacognition'], "Missing total_tool_calls"
        assert 'total_failures' in stats['metacognition'], "Missing total_failures"
        print("  ✅ get_thread_stats() works (no .state crash)")
        passed += 1
    except Exception as e:
        print(f"  ❌ get_thread_stats: {e}")
        failed += 1

    # 7. Verify _build_system_prompt doesn't crash
    try:
        assert brain is not None, "Brain not initialized (test 6 failed)"
        from brain.intent import IntentClassifier
        ic = IntentClassifier()
        intent = ic.classify("test message", False, "single")
        prompt = brain._build_system_prompt(intent)
        assert isinstance(prompt, str), "System prompt should be string"
        assert len(prompt) > 100, "System prompt too short"
        print(f"  ✅ _build_system_prompt() works ({len(prompt)} chars)")
        passed += 1
    except Exception as e:
        print(f"  ❌ _build_system_prompt: {e}")
        failed += 1

    # 8. Verify _decompose_task doesn't crash
    try:
        assert brain is not None, "Brain not initialized (test 6 failed)"
        text = "1. First find the file\n2. Then edit line 10\n3. Then test it"
        intent = ic.classify(text, False, "single")
        plan = brain._decompose_task(text, intent)
        assert isinstance(plan, str), "Plan should be string"
        assert "Task Breakdown" in plan, "Plan should have breakdown header"
        print(f"  ✅ _decompose_task() works (builds plan correctly)")
        passed += 1
    except Exception as e:
        print(f"  ❌ _decompose_task: {e}")
        failed += 1

    # 9. Verify self_improve bridge exists
    try:
        assert brain is not None, "Brain not initialized (test 6 failed)"
        assert hasattr(brain, '_record_brain_outcome'), "Missing _record_brain_outcome"
        print("  ✅ _record_brain_outcome() method exists")
        passed += 1
    except Exception as e:
        print(f"  ❌ _record_brain_outcome: {e}")
        failed += 1

    # Summary
    print(f"\n{'🟢' if failed == 0 else '🔴'} {passed}/{passed+failed} tests passed")
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
