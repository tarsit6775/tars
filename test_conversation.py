#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   TARS Conversation Test — Full Day Simulation               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Simulates a realistic day of Abdullah + TARS interaction.   ║
║  Sends messages via local WS (like dashboard), waits for     ║
║  TARS to process + respond, captures everything.             ║
║                                                              ║
║  Tests:                                                      ║
║    Phase 1: Casual chat (personality & tone)                 ║
║    Phase 2: Quick info (web search, system check)            ║
║    Phase 3: Research task (agent deployment)                 ║
║    Phase 4: Coding task (coder agent)                        ║
║    Phase 5: System management (reminders, notes, calendar)   ║
║    Phase 6: Flight search (domain-specific tool)             ║
║    Phase 7: Email + report (multi-step orchestration)        ║
║    Phase 8: File management (quick commands + file agent)    ║
║    Phase 9: Follow-up & memory (thread continuity)           ║
║    Phase 10: Wrap-up (conversational close)                  ║
║                                                              ║
║  Usage:                                                      ║
║    python test_conversation.py              # Run all phases ║
║    python test_conversation.py 3            # Run phase 3    ║
║    python test_conversation.py 1 2 3        # Run 1, 2, 3   ║
║    python test_conversation.py --fast       # Short waits    ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import sys
import time
import os
from datetime import datetime

# ── Config ──────────────────────────────────────────
TARS_WS = "ws://localhost:8421"
MAX_WAIT = 120          # Max seconds to wait for TARS response
BETWEEN_PHASES = 5      # Seconds between phases
BETWEEN_MSGS = 3        # Seconds between messages in same phase
FAST_MODE = "--fast" in sys.argv


if FAST_MODE:
    MAX_WAIT = 90
    BETWEEN_PHASES = 3
    BETWEEN_MSGS = 2


# ── Colors ──────────────────────────────────────────
class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def banner(text):
    w = 60
    print(f"\n{C.BOLD}{C.CYAN}{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}{C.END}\n")


def phase_header(num, title, desc):
    print(f"\n{C.BOLD}{C.YELLOW}┌─── Phase {num}: {title} ───┐{C.END}")
    print(f"{C.DIM}  {desc}{C.END}\n")


def msg_sent(text):
    print(f"  {C.BLUE}Abdullah ▸{C.END}  {text}")


def msg_received(text):
    # Truncate very long responses
    display = text[:300] + "..." if len(text) > 300 else text
    print(f"  {C.GREEN}TARS    ◂{C.END}  {display}")


def event_log(etype, detail):
    print(f"  {C.DIM}[{etype}] {detail[:120]}{C.END}")


def result_pass(msg):
    print(f"  {C.GREEN}✅ {msg}{C.END}")


def result_fail(msg):
    print(f"  {C.RED}❌ {msg}{C.END}")


def result_info(msg):
    print(f"  {C.CYAN}ℹ️  {msg}{C.END}")


# ═══════════════════════════════════════════════════════
#  CORE — Send a message and collect TARS's response
# ═══════════════════════════════════════════════════════

async def send_and_wait(message: str, timeout: int = MAX_WAIT, expect_tools: list = None):
    """
    Send a message to TARS via local WS and wait for the response(s).
    
    Returns dict with:
        - tars_replies: list of TARS's iMessage responses
        - tools_used: list of tool names executed
        - events: list of all events received
        - duration: seconds elapsed
        - success: bool
    """
    import websockets

    result = {
        "tars_replies": [],
        "tools_used": [],
        "agents_deployed": [],
        "events": [],
        "duration": 0,
        "success": False,
    }
    
    start = time.time()
    done_event = asyncio.Event()
    last_activity = [time.time()]  # Mutable for closure
    
    try:
        async with websockets.connect(TARS_WS) as ws:
            # Drain history first (skip old events)
            connect_time = time.time()
            history_drained = False
            
            async def drain_history():
                """Read and discard history events."""
                nonlocal history_drained
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        evt = json.loads(raw)
                        # Skip events from before we connected
                        if evt.get("ts_unix", 0) < connect_time - 2:
                            continue
                        # This is a live event that arrived during drain — process it
                        return evt
                except asyncio.TimeoutError:
                    history_drained = True
                    return None

            # Drain old history
            first_live = await drain_history()
            
            # Send our message
            await ws.send(json.dumps({"type": "send_message", "message": message}))
            msg_sent(message)
            
            # Process first live event if we got one during drain
            if first_live:
                _process_event(first_live, result, last_activity)

            # Listen for events until we see task completion or timeout
            idle_timeout = 15  # If no activity for 15s after last event, assume done
            
            while True:
                elapsed = time.time() - start
                idle = time.time() - last_activity[0]
                
                # Timeout conditions
                if elapsed > timeout:
                    result_info(f"Timeout after {timeout}s")
                    break
                
                # If we got at least one reply and idle for a while, we're done
                if result["tars_replies"] and idle > idle_timeout:
                    break
                
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    evt = json.loads(raw)
                    
                    # Skip old events
                    if evt.get("ts_unix", 0) < connect_time - 2:
                        continue
                    
                    _process_event(evt, result, last_activity)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

    except Exception as e:
        result_fail(f"Connection error: {e}")

    result["duration"] = round(time.time() - start, 1)
    result["success"] = len(result["tars_replies"]) > 0
    
    # Print results
    if result["tars_replies"]:
        for reply in result["tars_replies"]:
            msg_received(reply)
    else:
        result_fail("No response from TARS")
    
    if result["tools_used"]:
        tools_str = ", ".join(set(result["tools_used"]))
        result_info(f"Tools: {tools_str}")
    
    if result["agents_deployed"]:
        agents_str = ", ".join(result["agents_deployed"])
        result_info(f"Agents: {agents_str}")
    
    result_info(f"Duration: {result['duration']}s")
    
    # Verify expected tools
    if expect_tools:
        used = set(result["tools_used"])
        for tool in expect_tools:
            if tool in used:
                result_pass(f"Used {tool}")
            else:
                result_fail(f"Expected {tool} but wasn't used")
    
    return result


def _process_event(evt, result, last_activity):
    """Process a single event from the WS stream."""
    etype = evt.get("type", "")
    data = evt.get("data", {})
    
    # Dedup by event ID or (type + message hash) — server can send same event twice
    evt_id = evt.get("id", "")
    if not evt_id:
        # Build a dedup key from type + data content
        evt_id = f"{etype}:{json.dumps(data, sort_keys=True)}"
    if evt_id in result.get("_seen_ids", set()):
        return
    result.setdefault("_seen_ids", set()).add(evt_id)
    
    if etype == "imessage_sent":
        msg = data.get("message", "")
        if msg and msg not in result["tars_replies"]:
            result["tars_replies"].append(msg)
            last_activity[0] = time.time()
    
    elif etype in ("tool_use", "tool_called"):
        tool = data.get("tool_name", "")
        if tool:
            result["tools_used"].append(tool)
            last_activity[0] = time.time()
            # Check for agent deployments
            if tool.startswith("deploy_"):
                agent = tool.replace("deploy_", "").replace("_agent", "")
                result["agents_deployed"].append(agent)
                event_log("agent", f"Deploying {agent} agent...")
            else:
                event_log("tool", f"{tool}")
    
    elif etype == "tool_result":
        last_activity[0] = time.time()
    
    elif etype in ("thinking_start", "thinking"):
        last_activity[0] = time.time()
        event_log("think", "Reasoning...")
    
    elif etype == "agent_step":
        last_activity[0] = time.time()
        step = data.get("step", "?")
        event_log("agent", f"Step {step}")
    
    elif etype == "task_completed":
        last_activity[0] = time.time()
    
    result["events"].append(evt)


# ═══════════════════════════════════════════════════════
#  CONVERSATION PHASES
# ═══════════════════════════════════════════════════════

async def phase_1_casual_chat():
    """Casual greeting — test personality and tone."""
    phase_header(1, "Casual Chat", "Testing personality, warmth, Interstellar vibes")
    
    r1 = await send_and_wait("yo", expect_tools=["send_imessage"])
    time.sleep(BETWEEN_MSGS)
    
    r2 = await send_and_wait("how are you doing today", expect_tools=["send_imessage"])
    
    # Verify personality
    all_replies = " ".join(r1.get("tars_replies", []) + r2.get("tars_replies", []))
    lower = all_replies.lower()
    
    # Should NOT contain corporate speak
    bad_phrases = ["certainly", "i'd be happy to", "of course!", "how can i assist"]
    for phrase in bad_phrases:
        if phrase in lower:
            result_fail(f"Corporate speak detected: '{phrase}'")
            return False
    
    result_pass("No corporate speak — conversational tone ✓")
    return True


async def phase_2_quick_info():
    """Quick information requests — web search, system check."""
    phase_header(2, "Quick Info", "Web search + system awareness")
    
    r1 = await send_and_wait(
        "whats the weather like in toronto right now",
        expect_tools=["send_imessage", "web_search"]
    )
    time.sleep(BETWEEN_MSGS)
    
    r2 = await send_and_wait(
        "how much disk space do i have left",
        expect_tools=["send_imessage", "run_quick_command"]
    )
    
    return r1["success"] and r2["success"]


async def phase_3_research():
    """Research task — deploys research agent."""
    phase_header(3, "Research Task", "Deploy research agent for deep info gathering")
    
    r = await send_and_wait(
        "research the top 5 AI agent frameworks right now — like CrewAI, AutoGen, LangGraph etc. "
        "compare their features, stars, and which is best for building autonomous agents. "
        "give me a summary",
        timeout=180,
        expect_tools=["send_imessage"]
    )
    
    return r["success"]


async def phase_4_coding():
    """Coding task — coder agent or quick command."""
    phase_header(4, "Coding Task", "Create a script with the coder agent")
    
    r = await send_and_wait(
        "write me a python script that takes a github username and shows their "
        "top 5 repos by stars, with star count and description. save it to my Desktop as github_stats.py",
        timeout=120,
        expect_tools=["send_imessage"]
    )
    
    return r["success"]


async def phase_5_system():
    """System management — reminders, notes, calendar."""
    phase_header(5, "System Management", "Mac productivity apps integration")
    
    r1 = await send_and_wait(
        "create a reminder for tomorrow at 10am — review AI agent frameworks research",
        expect_tools=["send_imessage", "mac_reminders"]
    )
    time.sleep(BETWEEN_MSGS)
    
    r2 = await send_and_wait(
        "add a note called 'TARS Project Ideas' with these bullet points: "
        "dashboard improvements, flight booking automation, email templates, voice control",
        expect_tools=["send_imessage", "mac_notes"]
    )
    
    return r1["success"] and r2["success"]


async def phase_6_flights():
    """Flight search — domain-specific tool."""
    phase_header(6, "Flight Search", "Google Flights integration")
    
    r = await send_and_wait(
        "find me flights from toronto to london departing march 15 returning march 25",
        timeout=180,
        expect_tools=["send_imessage"]
    )
    
    return r["success"]


async def phase_7_email():
    """Email + report — multi-step orchestration."""
    phase_header(7, "Email", "Send email via Mail.app")
    
    r = await send_and_wait(
        "send an email to tarsitgroup@outlook.com with subject 'TARS Status Report' "
        "and body saying that all systems are operational, dashboard chat is mirroring properly, "
        "and the conversation test passed. sign it as TARS.",
        timeout=60,
        expect_tools=["send_imessage", "mac_mail"]
    )
    
    return r["success"]


async def phase_8_files():
    """File management — quick commands."""
    phase_header(8, "File Management", "System commands and file operations")
    
    r1 = await send_and_wait(
        "show me whats on my Desktop — just the first 15 files",
        expect_tools=["send_imessage", "run_quick_command"]
    )
    time.sleep(BETWEEN_MSGS)
    
    r2 = await send_and_wait(
        "how big is the tars-main folder in total",
        expect_tools=["send_imessage", "run_quick_command"]
    )
    
    return r1["success"] and r2["success"]


async def phase_9_memory():
    """Follow-up & memory — thread continuity."""
    phase_header(9, "Memory & Context", "Recall and save to persistent memory")
    
    r1 = await send_and_wait(
        "save to memory that my preferred flight class is economy and "
        "i prefer direct flights, departure from toronto pearson YYZ",
        expect_tools=["send_imessage", "save_memory"]
    )
    time.sleep(BETWEEN_MSGS)
    
    r2 = await send_and_wait(
        "what do you remember about my preferences",
        expect_tools=["send_imessage", "recall_memory"]
    )
    
    return r1["success"] and r2["success"]


async def phase_10_wrapup():
    """Conversational close — personality test."""
    phase_header(10, "Wrap-up", "Conversational close with personality")
    
    r = await send_and_wait(
        "good work today tars. lets call it a night",
        expect_tools=["send_imessage"]
    )
    
    # Check for warmth / personality in response
    if r["success"]:
        reply = " ".join(r["tars_replies"]).lower()
        if any(w in reply for w in ["night", "rest", "tomorrow", "good", "see", "sleep", "ready"]):
            result_pass("Warm sign-off with personality ✓")
        else:
            result_info("Response was functional but could be warmer")
    
    return r["success"]


# ═══════════════════════════════════════════════════════
#  MAIN RUNNER
# ═══════════════════════════════════════════════════════

ALL_PHASES = {
    1: ("Casual Chat", phase_1_casual_chat),
    2: ("Quick Info", phase_2_quick_info),
    3: ("Research", phase_3_research),
    4: ("Coding", phase_4_coding),
    5: ("System Mgmt", phase_5_system),
    6: ("Flights", phase_6_flights),
    7: ("Email", phase_7_email),
    8: ("Files", phase_8_files),
    9: ("Memory", phase_9_memory),
    10: ("Wrap-up", phase_10_wrapup),
}


async def main():
    banner("TARS CONVERSATION TEST — Full Day Simulation")
    print(f"  {C.DIM}Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target: {TARS_WS}")
    print(f"  Mode: {'FAST' if FAST_MODE else 'NORMAL'}")
    print(f"  Max wait per message: {MAX_WAIT}s{C.END}\n")
    
    # Determine which phases to run
    args = [a for a in sys.argv[1:] if a != "--fast"]
    if args:
        selected = []
        for a in args:
            try:
                n = int(a)
                if n in ALL_PHASES:
                    selected.append(n)
            except ValueError:
                pass
        if not selected:
            selected = list(ALL_PHASES.keys())
    else:
        selected = list(ALL_PHASES.keys())
    
    print(f"  {C.BOLD}Running phases: {', '.join(str(s) for s in selected)}{C.END}")
    
    # Verify TARS is reachable
    try:
        import websockets
        async with websockets.connect(TARS_WS) as ws:
            result_pass("Connected to TARS WebSocket")
    except Exception as e:
        result_fail(f"Cannot connect to TARS: {e}")
        print(f"\n  {C.RED}Make sure TARS is running: python tars.py{C.END}")
        return
    
    # Run phases
    results = {}
    total_start = time.time()
    
    for phase_num in selected:
        name, func = ALL_PHASES[phase_num]
        try:
            passed = await func()
            results[phase_num] = passed
        except Exception as e:
            result_fail(f"Phase {phase_num} crashed: {e}")
            results[phase_num] = False
        
        if phase_num != selected[-1]:
            time.sleep(BETWEEN_PHASES)
    
    # ── Final Report ──
    total_time = round(time.time() - total_start, 1)
    
    banner("RESULTS")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for num in sorted(results):
        name = ALL_PHASES[num][0]
        if results[num]:
            print(f"  {C.GREEN}✅ Phase {num}: {name}{C.END}")
        else:
            print(f"  {C.RED}❌ Phase {num}: {name}{C.END}")
    
    print()
    color = C.GREEN if passed == total else C.YELLOW if passed > total // 2 else C.RED
    print(f"  {C.BOLD}{color}{passed}/{total} phases passed — {total_time}s total{C.END}")
    
    if passed == total:
        print(f"\n  {C.GREEN}{C.BOLD}🎯 PERFECT SCORE — TARS is fully operational.{C.END}")
        print(f"  {C.DIM}\"That's what I do, Cooper.\"{C.END}")
    elif passed > total // 2:
        print(f"\n  {C.YELLOW}⚡ Most phases passed. Check failures above.{C.END}")
    else:
        print(f"\n  {C.RED}⚠️  Multiple failures. Check TARS logs.{C.END}")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
