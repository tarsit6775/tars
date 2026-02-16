"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Orchestrator Executor                            ║
╠══════════════════════════════════════════════════════════════╣
║  Routes the brain's tool calls to agent deployments and      ║
║  direct handlers. Tracks ALL deployments so the brain sees   ║
║  what already failed and can make smarter decisions.         ║
║                                                              ║
║  Phase 1-5 Upgrades:                                         ║
║    - scan_environment: Full Mac state awareness              ║
║    - verify_result: Post-deployment verification             ║
║    - checkpoint: Progress saving for resume                  ║
║    - Smart recovery ladder with failure enrichment           ║
║                                                              ║
║  Key design: The executor NEVER silently retries the same    ║
║  thing. Every failure goes back to the brain with full       ║
║  context so the LLM can reason about the next move.          ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import logging
import subprocess
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

logger = logging.getLogger("TARS")

from brain.llm_client import LLMClient
from brain.self_improve import SelfImproveEngine
from agents.browser_agent import BrowserAgent
from agents.coder_agent import CoderAgent
from agents.system_agent import SystemAgent
from agents.research_agent import ResearchAgent
from agents.file_agent import FileAgent
from agents.dev_agent import DevAgent
from agents.comms import agent_comms
from memory.agent_memory import AgentMemory
from hands.terminal import run_terminal
from hands.file_manager import read_file
from hands.browser import act_google as browser_google
from hands import mac_control as mac
from hands.report_gen import generate_report as _gen_report
from utils.event_bus import event_bus
from utils.agent_monitor import agent_monitor
from memory.error_tracker import error_tracker


# Agent class registry
AGENT_CLASSES = {
    "browser": BrowserAgent,
    "coder": CoderAgent,
    "system": SystemAgent,
    "research": ResearchAgent,
    "file": FileAgent,
    "dev": DevAgent,
}

# Hard limit: max agent deployments per brain task cycle
# Configurable via config.yaml safety.max_deployments (default 15)
DEFAULT_MAX_DEPLOYMENTS = 15


class ToolExecutor:
    def __init__(self, config, imessage_sender, imessage_reader, memory_manager, logger, kill_event=None):
        self.config = config
        self.sender = imessage_sender
        self.reader = imessage_reader
        self.memory = memory_manager
        self.logger = logger
        self.comms = agent_comms
        self.monitor = agent_monitor
        self._kill_event = kill_event  # Shared threading.Event — set when kill word received

        # ── Reply routing — thread-local so each task thread knows its source ──
        self._reply_source = threading.local()

        # ── Deployment tracker — resets per task ──
        # Every deployment and its result, so brain sees full history
        self._deployment_log = []  # [{agent, task, success, steps, reason}]
        self._deployment_lock = threading.Lock()  # Thread safety for parallel tasks
        self.max_deployments = config.get("safety", {}).get("max_deployments", DEFAULT_MAX_DEPLOYMENTS)

        # ── Dual-provider: agents use agent_llm (fast/free) ──
        agent_cfg = config.get("agent_llm")
        llm_cfg = config["llm"]
        
        if agent_cfg and agent_cfg.get("api_key"):
            # Dedicated agent provider (e.g. Groq for fast execution)
            self.llm_client = LLMClient(
                provider=agent_cfg["provider"],
                api_key=agent_cfg["api_key"],
                base_url=agent_cfg.get("base_url"),
            )
            self.heavy_model = agent_cfg["model"]
            self.fast_model = agent_cfg["model"]
            logger.info(f"🤖 Agents: {agent_cfg['provider']}/{self.heavy_model}")
        else:
            # Fallback: single provider
            self.llm_client = LLMClient(
                provider=llm_cfg["provider"],
                api_key=llm_cfg["api_key"],
                base_url=llm_cfg.get("base_url"),
            )
            self.heavy_model = llm_cfg["heavy_model"]
            self.fast_model = llm_cfg.get("fast_model", self.heavy_model)
        
        self.phone = config["imessage"]["owner_phone"]

        # Agent memory + self-improvement engine
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.agent_memory = AgentMemory(base_dir)
        self.self_improve = SelfImproveEngine(
            agent_memory=self.agent_memory,
            llm_client=self.llm_client,
            model=self.fast_model,
        )

    # ── Reply routing ────────────────────────────────────
    def set_reply_source(self, source: str):
        """Set the reply source for the current thread (called from tars._run_task)."""
        self._reply_source.source = source

    def get_reply_source(self) -> str:
        """Get the reply source for the current thread."""
        return getattr(self._reply_source, "source", "imessage")

    def send_reply(self, message: str):
        """Send a reply routed to the correct channel (iMessage or dashboard).

        When the task came from the dashboard, the reply is emitted as a
        WebSocket event so the dashboard can display it.  iMessage is also
        sent as a fallback for now, so the user gets the message either way.
        """
        source = self.get_reply_source()
        if source == "dashboard":
            event_bus.emit("imessage_sent", {"message": message, "source": "dashboard"})
            logger.info(f"  📤 Reply sent to dashboard")
            return {"success": True, "content": f"Reply sent to dashboard"}
        else:
            event_bus.emit("imessage_sent", {"message": message})
            return self.sender.send(message)

    def reset_task_tracker(self):
        """Call this when a new user task starts (from tars.py)."""
        self._deployment_log = []

    def _get_failure_summary(self):
        """Build a summary of all failed deployments this task for the brain to see."""
        failures = [d for d in self._deployment_log if not d["success"]]
        if not failures:
            return ""
        lines = ["## ⚠️ PREVIOUS FAILED ATTEMPTS THIS TASK:"]
        for i, f in enumerate(failures, 1):
            lines.append(f"  {i}. [{f['agent']}] task='{f['task'][:100]}' → FAILED ({f['steps']} steps): {f['reason'][:200]}")
        lines.append("")
        lines.append("DO NOT repeat the same approach. Analyze WHY each failed and try something DIFFERENT.")
        return "\n".join(lines)

    def execute(self, tool_name, tool_input):
        """Execute a tool call and return the result."""
        self.logger.info(f"🔧 {tool_name} → {str(tool_input)[:120]}")

        try:
            result = self._dispatch(tool_name, tool_input)
        except Exception as e:
            result = {"success": False, "error": True, "content": f"Tool execution error: {e}"}

        # Log to memory
        self.memory.log_action(tool_name, tool_input, result)

        # Log result
        status = "✅" if result.get("success") else "❌"
        self.logger.info(f"  {status} {str(result.get('content', ''))[:120]}")

        return result

    def _dispatch(self, tool_name, inp):
        """Route tool call to the right handler."""

        # ─── Agent Deployments ───────────────────
        if tool_name == "deploy_browser_agent":
            return self._deploy_agent("browser", inp["task"])

        elif tool_name == "deploy_coder_agent":
            return self._deploy_agent("coder", inp["task"])

        elif tool_name == "deploy_system_agent":
            return self._deploy_agent("system", inp["task"])

        elif tool_name == "deploy_research_agent":
            return self._deploy_agent("research", inp["task"])

        elif tool_name == "deploy_file_agent":
            return self._deploy_agent("file", inp["task"])

        elif tool_name == "deploy_dev_agent":
            return self._deploy_agent("dev", inp["task"])

        # ─── Direct Tools ────────────────────────
        elif tool_name == "send_imessage":
            event_bus.emit("imessage_sent", {"message": inp["message"]})
            return self.send_reply(inp["message"])

        elif tool_name == "wait_for_reply":
            result = self.reader.wait_for_reply(timeout=inp.get("timeout", 300))
            if result.get("success"):
                event_bus.emit("imessage_received", {"message": result.get("content", "")})
            return result

        elif tool_name == "save_memory":
            return self.memory.save(inp["category"], inp["key"], inp["value"])

        elif tool_name == "recall_memory":
            return self.memory.recall(inp["query"])

        elif tool_name == "run_quick_command":
            cmd = inp.get("command", "")
            if not cmd:
                return {"success": False, "error": True, "content": "⚠️ Missing 'command' parameter. Example: run_quick_command({\"command\": \"ls -la\"})"}
            return run_terminal(cmd, timeout=inp.get("timeout", 30))

        elif tool_name == "quick_read_file":
            return read_file(inp["path"])

        elif tool_name == "think":
            thought = inp.get("thought", "")
            if not thought:
                return {"success": False, "error": True, "content": "⚠️ Empty thought. You MUST provide a 'thought' string. Example: think({\"thought\": \"Analyzing the request...\"})"}
            self.logger.info(f"💭 Brain thinking: {thought[:200]}")
            event_bus.emit("thinking", {"text": thought, "model": "brain"})
            return {"success": True, "content": "Thought recorded. Continue with your plan."}

        # ─── Phase 2: Environmental Awareness ──
        elif tool_name == "scan_environment":
            return self._scan_environment(inp.get("checks", ["all"]))

        # ─── Phase 3: Verification Loop ──
        elif tool_name == "verify_result":
            return self._verify_result(inp["type"], inp["check"], inp.get("expected", ""))

        # ─── Phase 8: Checkpoint ──
        elif tool_name == "checkpoint":
            return self._checkpoint(inp["completed"], inp["remaining"])

        # ─── Legacy tool names ──
        elif tool_name == "web_task":
            return self._deploy_agent("browser", inp["task"])

        elif tool_name == "web_search":
            query = inp.get("query", "")
            if not query:
                return {"success": False, "error": True, "content": "⚠️ Missing 'query' parameter. Example: web_search({\"query\": \"weather in Miami\"})"}
            return self._web_search(query)

        # ─── Direct Mac Control (brain-level) ──
        elif tool_name == "mac_mail":
            return self._mac_mail(inp)
        elif tool_name == "mac_notes":
            return self._mac_notes(inp)
        elif tool_name == "mac_calendar":
            return self._mac_calendar(inp)
        elif tool_name == "mac_reminders":
            return self._mac_reminders(inp)
        elif tool_name == "mac_system":
            return self._mac_system(inp)

        # ─── Smart Services (API-first) ──
        elif tool_name == "search_flights":
            return self._search_flights(inp)
        elif tool_name == "search_flights_report":
            return self._search_flights_report(inp)
        elif tool_name == "find_cheapest_dates":
            return self._find_cheapest_dates(inp)
        elif tool_name == "track_flight_price":
            return self._track_flight_price(inp)
        elif tool_name == "get_tracked_flights":
            return self._get_tracked_flights(inp)
        elif tool_name == "stop_tracking":
            return self._stop_tracking(inp)
        elif tool_name == "book_flight":
            return self._book_flight(inp)

        # ─── Report Generation ──
        elif tool_name == "generate_report":
            return self._generate_report(inp)

        # ─── Self-Healing ──
        elif tool_name == "propose_self_heal":
            return self._propose_self_heal(inp)

        else:
            return {"success": False, "error": True, "content": f"Unknown tool: {tool_name}"}

    def _web_search(self, query):
        """Fast web search — HTTP-based DuckDuckGo, no browser needed.
        
        Uses lightweight HTTP scrape of DuckDuckGo HTML (< 5s) instead of
        spinning up the full CDP browser which can hang.
        """
        import urllib.request
        import urllib.parse
        import re

        # ── Fast path: DuckDuckGo HTML (no browser, no CAPTCHA) ──
        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            req = urllib.request.Request(url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            # Extract result snippets from DuckDuckGo HTML
            snippets = re.findall(r'class="result__snippet">(.*?)</a>', html, re.S)
            titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
            if snippets:
                results = []
                for i, (t, s) in enumerate(zip(titles, snippets), 1):
                    t_clean = re.sub(r'<[^>]+>', '', t).strip()
                    s_clean = re.sub(r'<[^>]+>', '', s).strip()
                    results.append(f"{i}. {t_clean}\n   {s_clean}")
                text = "\n\n".join(results[:10])
                return {"success": True, "content": f"Search results for '{query}':\n\n{text}"}
            # Fallback: strip all HTML
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 200:
                return {"success": True, "content": f"Search results for '{query}':\n\n{text[:6000]}"}
        except Exception as e:
            logger.warning(f"⚠️ HTTP search failed ({e}), trying browser...")

        # ── Slow fallback: CDP browser (with hard 30s timeout) ──
        import concurrent.futures
        def _browser_search():
            return browser_google(query)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_browser_search)
                text = future.result(timeout=30)
                return {"success": True, "content": text if isinstance(text, str) else str(text)}
        except Exception as e2:
            return {"success": False, "error": True, "content": f"Web search failed: {e2}"}

    def _scan_environment(self, checks):
        """
        Phase 2: Environmental Awareness
        Scan the current Mac state so the brain can make informed decisions.
        Uses mac_control for comprehensive snapshots.
        """
        results = []
        check_set = set(checks)
        do_all = "all" in check_set

        # ── Full Mac snapshot (if all requested) ──
        if do_all:
            try:
                snap = mac.get_environment_snapshot()
                if snap.get("success"):
                    results.append(snap["content"])
            except Exception as e:
                results.append(f"## Mac Snapshot\n⚠️ Error: {e}")

        # ── Running applications ──
        if not do_all and "apps" in check_set:
            try:
                r = mac.get_running_apps()
                results.append(f"## Running Apps\n{r.get('content', 'unknown')}")
            except Exception as e:
                results.append(f"## Running Apps\n⚠️ Could not check: {e}")

        # ── Browser tabs ──
        if do_all or "tabs" in check_set:
            try:
                r = subprocess.run(
                    ["osascript", "-e", '''
                    tell application "Google Chrome"
                        set tabInfo to ""
                        repeat with w in windows
                            repeat with t in tabs of w
                                set tabInfo to tabInfo & (URL of t) & " | " & (title of t) & linefeed
                            end repeat
                        end repeat
                        return tabInfo
                    end tell
                    '''],
                    capture_output=True, text=True, timeout=10
                )
                tabs = r.stdout.strip()
                if tabs:
                    results.append(f"## Browser Tabs\n{tabs}")
                else:
                    results.append("## Browser Tabs\nNo tabs open or Chrome not running")
            except Exception as e:
                results.append(f"## Browser Tabs\nChrome not running or error: {e}")

        # ── Current directory files ──
        if do_all or "files" in check_set:
            try:
                cwd = os.getcwd()
                items = os.listdir(cwd)[:30]
                file_list = "\n".join(f"  {'📁' if os.path.isdir(os.path.join(cwd, f)) else '📄'} {f}" for f in sorted(items))
                results.append(f"## Current Directory ({cwd})\n{file_list}")
            except Exception as e:
                results.append(f"## Current Directory\n⚠️ Error: {e}")

        # ── Network ──
        if do_all or "network" in check_set:
            try:
                r = subprocess.run(
                    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "5", "https://google.com"],
                    capture_output=True, text=True, timeout=10
                )
                status = r.stdout.strip()
                if status == "200" or status == "301":
                    results.append("## Network\n✅ Internet connected")
                else:
                    results.append(f"## Network\n⚠️ HTTP status {status} — may have issues")
            except Exception:
                results.append("## Network\n❌ No internet connection")

        # ── System info ──
        if do_all or "system" in check_set:
            try:
                # Disk space
                disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
                disk_line = disk.stdout.strip().split("\n")[-1] if disk.stdout else "unknown"

                # Battery
                batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
                batt_info = batt.stdout.strip().split("\n")[-1] if batt.stdout else "unknown"

                # Uptime
                up = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
                uptime_info = up.stdout.strip() if up.stdout else "unknown"

                results.append(f"## System Info\nDisk: {disk_line}\nBattery: {batt_info}\nUptime: {uptime_info}")
            except Exception as e:
                results.append(f"## System Info\n⚠️ Error: {e}")

        # ── Deployment status this task ──
        deployed = len(self._deployment_log)
        remaining = self.max_deployments - deployed
        if self._deployment_log:
            dep_summary = "\n".join(
                f"  {'✅' if d['success'] else '❌'} {d['agent']}: {d['task'][:80]}"
                for d in self._deployment_log
            )
            results.append(f"## Deployment Status ({deployed}/{self.max_deployments} used, {remaining} remaining)\n{dep_summary}")
        else:
            results.append(f"## Deployment Status\nNo agents deployed yet. Budget: {self.max_deployments}")

        full_scan = "\n\n".join(results)
        self.logger.info(f"🔍 Environment scan: {len(results)} checks completed")
        event_bus.emit("environment_scan", {"checks": len(results)})

        return {"success": True, "content": full_scan}

    def _verify_result(self, verify_type, check, expected=""):
        """
        Phase 3: Verification Loop
        Verify that an agent's work actually succeeded.
        """
        self.logger.info(f"🔎 Verifying ({verify_type}): {check[:100]}")
        event_bus.emit("verification", {"type": verify_type, "check": check[:100]})

        try:
            if verify_type == "browser":
                # Check current browser page URL and content
                from hands.browser import act_read_url, act_read_page
                url_result = act_read_url()
                url = url_result if isinstance(url_result, str) else url_result.get("content", str(url_result))

                page_result = act_read_page()
                page_text = page_result if isinstance(page_result, str) else page_result.get("content", str(page_result))
                page_preview = page_text[:3000] if page_text else "(empty page)"

                # Check if expected content is found
                combined = f"{url}\n{page_preview}".lower()
                if expected and expected.lower() in combined:
                    verdict = f"✅ VERIFIED — Found '{expected}' in page"
                elif expected:
                    verdict = f"⚠️ NOT VERIFIED — '{expected}' not found in page"
                else:
                    verdict = "ℹ️ Page state retrieved — review below"

                return {
                    "success": bool(expected and expected.lower() in combined),
                    "content": f"{verdict}\n\nURL: {url}\n\nPage Preview:\n{page_preview[:2000]}"
                }

            elif verify_type == "command":
                # Run a shell command to verify
                result = run_terminal(check, timeout=30)
                output = result.get("content", str(result))

                if expected and expected.lower() in output.lower():
                    verdict = f"✅ VERIFIED — Found '{expected}' in output"
                    success = True
                elif expected:
                    verdict = f"⚠️ NOT VERIFIED — '{expected}' not found in output"
                    success = False
                else:
                    verdict = "ℹ️ Command output retrieved — review below"
                    success = result.get("success", True)

                return {
                    "success": success,
                    "content": f"{verdict}\n\nCommand: {check}\nOutput:\n{output[:2000]}"
                }

            elif verify_type == "file":
                # Check if file/directory exists and get info
                path = os.path.expanduser(check)
                exists = os.path.exists(path)
                if exists:
                    is_dir = os.path.isdir(path)
                    size = os.path.getsize(path) if not is_dir else sum(
                        os.path.getsize(os.path.join(dp, f))
                        for dp, dn, fnames in os.walk(path) for f in fnames
                    )
                    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")

                    if not is_dir:
                        try:
                            with open(path, 'r') as f:
                                preview = f.read(1000)
                        except Exception:
                            preview = "(binary file)"
                    else:
                        items = os.listdir(path)[:20]
                        preview = "\n".join(items)

                    return {
                        "success": True,
                        "content": f"✅ VERIFIED — {'Directory' if is_dir else 'File'} exists\nPath: {path}\nSize: {size:,} bytes\nModified: {mtime}\n\nPreview:\n{preview}"
                    }
                else:
                    return {
                        "success": False,
                        "content": f"❌ NOT VERIFIED — Path does not exist: {path}"
                    }

            elif verify_type == "process":
                # Check if a process is running
                result = subprocess.run(
                    ["pgrep", "-fl", check],
                    capture_output=True, text=True, timeout=5
                )
                processes = result.stdout.strip()
                if processes:
                    return {
                        "success": True,
                        "content": f"✅ VERIFIED — Process '{check}' is running:\n{processes}"
                    }
                else:
                    return {
                        "success": False,
                        "content": f"❌ NOT VERIFIED — Process '{check}' is NOT running"
                    }

            else:
                return {"success": False, "content": f"Unknown verification type: {verify_type}"}

        except Exception as e:
            return {"success": False, "content": f"Verification error: {e}"}

    def _checkpoint(self, completed, remaining):
        """
        Phase 8: Checkpoint
        Save current progress so the brain can resume if interrupted.
        """
        checkpoint_data = {
            "timestamp": datetime.now().isoformat(),
            "completed": completed,
            "remaining": remaining,
            "deployments": len(self._deployment_log),
            "deployment_log": self._deployment_log,
        }

        # Save to memory
        self.memory.save("context", "last_checkpoint", json.dumps(checkpoint_data, indent=2))

        # Also save to a checkpoint file
        checkpoint_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory", "checkpoint.json")
        try:
            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint_data, f, indent=2)
        except Exception:
            pass

        self.logger.info(f"💾 Checkpoint saved: completed={completed[:100]}, remaining={remaining[:100]}")
        event_bus.emit("checkpoint", {"completed": completed[:200], "remaining": remaining[:200]})

        return {
            "success": True,
            "content": f"💾 Checkpoint saved.\nCompleted: {completed}\nRemaining: {remaining}\nDeployments used: {len(self._deployment_log)}/{self.max_deployments}"
        }

    # ─────────────────────────────────────────────
    #  Direct Mac Control (brain-level tools)
    # ─────────────────────────────────────────────

    def _mac_mail(self, inp):
        """Handle mac_mail brain tool — direct Mail.app control."""
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: send, unread, inbox, read, search, verify_sent"}
        try:
            if action == "unread":
                return mac.mail_unread_count()
            elif action == "inbox":
                return mac.mail_read_inbox(inp.get("count", 5))
            elif action == "read":
                return mac.mail_read_message(inp.get("index", 1))
            elif action == "search":
                return mac.mail_search(inp.get("keyword", ""))
            elif action == "send":
                return mac.mail_send(
                    inp["to"], inp["subject"], inp["body"],
                    attachment_path=inp.get("attachment_path"),
                    from_address=inp.get("from_address", "tarsitgroup@outlook.com")
                )
            elif action == "verify_sent":
                return mac.mail_verify_sent(
                    inp["subject"],
                    to_address=inp.get("to")
                )
            return {"success": False, "error": True, "content": f"Unknown mail action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Mail error: {e}"}

    def _mac_notes(self, inp):
        """Handle mac_notes brain tool — direct Apple Notes control."""
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: list, read, create, search"}
        try:
            if action == "list":
                return mac.notes_list()
            elif action == "read":
                return mac.notes_read(inp.get("note_name", ""))
            elif action == "create":
                return mac.notes_create(inp["title"], inp["body"], inp.get("folder", "Notes"))
            elif action == "search":
                return mac.notes_search(inp.get("query", ""))
            return {"success": False, "error": True, "content": f"Unknown notes action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Notes error: {e}"}

    def _mac_calendar(self, inp):
        """Handle mac_calendar brain tool — direct Calendar control."""
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: events, create"}
        try:
            if action == "events":
                return mac.calendar_events(inp.get("calendar_name"), inp.get("days", 7))
            elif action == "create":
                return mac.calendar_create_event(
                    inp["title"], inp["start"], inp["end"],
                    inp.get("calendar_name", "Calendar")
                )
            return {"success": False, "error": True, "content": f"Unknown calendar action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Calendar error: {e}"}

    def _mac_reminders(self, inp):
        """Handle mac_reminders brain tool — direct Reminders control."""
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: list, create, complete"}
        try:
            if action == "list":
                return mac.reminders_list(inp.get("list_name"))
            elif action == "create":
                return mac.reminders_create(
                    inp["title"], inp.get("list_name", "Reminders"),
                    inp.get("due"), inp.get("notes")
                )
            elif action == "complete":
                return mac.reminders_complete(
                    inp["title"], inp.get("list_name", "Reminders")
                )
            return {"success": False, "error": True, "content": f"Unknown reminders action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Reminders error: {e}"}

    def _mac_system(self, inp):
        """Handle mac_system brain tool — direct system controls."""
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: volume, dark_mode, notify, clipboard, screenshot, environment, battery, spotlight"}
        try:
            if action == "volume":
                return mac.set_volume(inp.get("value", 50))
            elif action == "dark_mode":
                return mac.set_dark_mode(inp.get("enabled", True))
            elif action == "notify":
                return mac.notify(inp.get("message", "TARS notification"))
            elif action == "clipboard":
                return mac.clipboard_read()
            elif action == "screenshot":
                return mac.take_screenshot()
            elif action == "environment":
                return mac.get_environment_snapshot()
            elif action == "battery":
                return mac.get_battery()
            elif action == "spotlight":
                return mac.spotlight_search(inp.get("query", ""))
            return {"success": False, "error": True, "content": f"Unknown system action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"System error: {e}"}

    def _search_flights(self, inp):
        """Handle search_flights brain tool — API-first flight search."""
        try:
            # Validate required args — Gemini sometimes sends empty {}
            for req in ("origin", "destination", "depart_date"):
                if req not in inp or not inp[req]:
                    return {"success": False, "error": True, "content": f"⚠️ Missing required parameter '{req}'. You MUST provide origin, destination, and depart_date. Example: search_flights({{\"origin\": \"SLC\", \"destination\": \"NYC\", \"depart_date\": \"March 15\"}})"}
            from hands.flight_search import search_flights
            event_bus.emit("tool_start", {"tool": "search_flights", "input": inp})
            result = search_flights(
                origin=inp["origin"],
                destination=inp["destination"],
                depart_date=inp["depart_date"],
                return_date=inp.get("return_date", ""),
                passengers=inp.get("passengers", 1),
                trip_type=inp.get("trip_type", "round_trip"),
                cabin=inp.get("cabin", "economy"),
                stops=inp.get("stops", "any"),
                max_price=inp.get("max_price", 0),
            )
            event_bus.emit("tool_end", {"tool": "search_flights", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Flight search error: {e}"}

    def _search_flights_report(self, inp):
        """Handle search_flights_report — search + Excel + email pipeline."""
        try:
            for req in ("origin", "destination", "depart_date"):
                if req not in inp or not inp[req]:
                    return {"success": False, "error": True, "content": f"⚠️ Missing required parameter '{req}'. You MUST provide origin, destination, and depart_date. Example: search_flights_report({{\"origin\": \"Tampa\", \"destination\": \"Tokyo\", \"depart_date\": \"March 20\", \"email_to\": \"tarsitgroup@outlook.com\"}})"}
            from hands.flight_search import search_flights_report
            event_bus.emit("tool_start", {"tool": "search_flights_report", "input": inp})
            result = search_flights_report(
                origin=inp["origin"],
                destination=inp["destination"],
                depart_date=inp["depart_date"],
                return_date=inp.get("return_date", ""),
                passengers=inp.get("passengers", 1),
                trip_type=inp.get("trip_type", "round_trip"),
                cabin=inp.get("cabin", "economy"),
                stops=inp.get("stops", "any"),
                max_price=inp.get("max_price", 0),
                email_to=inp.get("email_to", ""),
            )
            event_bus.emit("tool_end", {"tool": "search_flights_report", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Flight report error: {e}"}

    def _find_cheapest_dates(self, inp):
        """Handle find_cheapest_dates — scan date range for cheapest flight."""
        try:
            for req in ("origin", "destination", "start_date"):
                if req not in inp or not inp[req]:
                    return {"success": False, "error": True, "content": f"⚠️ Missing required parameter '{req}'. You MUST provide origin, destination, and start_date. Example: find_cheapest_dates({{\"origin\": \"SLC\", \"destination\": \"LAX\", \"start_date\": \"March 1\", \"end_date\": \"March 31\"}})"}
            from hands.flight_search import find_cheapest_dates
            event_bus.emit("tool_start", {"tool": "find_cheapest_dates", "input": inp})
            result = find_cheapest_dates(
                origin=inp["origin"],
                destination=inp["destination"],
                start_date=inp["start_date"],
                end_date=inp.get("end_date", ""),
                trip_type=inp.get("trip_type", "one_way"),
                cabin=inp.get("cabin", "economy"),
                stops=inp.get("stops", "any"),
                email_to=inp.get("email_to", ""),
            )
            event_bus.emit("tool_end", {"tool": "find_cheapest_dates", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Cheapest dates error: {e}"}

    def _track_flight_price(self, inp):
        """Handle track_flight_price — set up a price tracker for a route."""
        try:
            for req in ("origin", "destination", "depart_date", "target_price"):
                if req not in inp:
                    return {"success": False, "error": True, "content": f"⚠️ Missing required parameter '{req}'. You MUST provide origin, destination, depart_date, and target_price. Example: track_flight_price({{\"origin\": \"SLC\", \"destination\": \"NYC\", \"depart_date\": \"March 15\", \"target_price\": 200}})"}
            from hands.flight_search import track_flight_price
            event_bus.emit("tool_start", {"tool": "track_flight_price", "input": inp})
            result = track_flight_price(
                origin=inp["origin"],
                destination=inp["destination"],
                depart_date=inp["depart_date"],
                target_price=inp["target_price"],
                return_date=inp.get("return_date", ""),
                trip_type=inp.get("trip_type", "round_trip"),
                cabin=inp.get("cabin", "economy"),
                stops=inp.get("stops", "any"),
                email_to=inp.get("email_to", "tarsitgroup@outlook.com"),
                check_interval_hours=inp.get("check_interval_hours", 6),
            )
            event_bus.emit("tool_end", {"tool": "track_flight_price", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Price tracker error: {e}"}

    def _get_tracked_flights(self, inp):
        """Handle get_tracked_flights — list all active price trackers."""
        try:
            from hands.flight_search import get_tracked_flights
            event_bus.emit("tool_start", {"tool": "get_tracked_flights", "input": inp})
            result = get_tracked_flights()
            event_bus.emit("tool_end", {"tool": "get_tracked_flights", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Get trackers error: {e}"}

    def _stop_tracking(self, inp):
        """Handle stop_tracking — deactivate a specific price tracker."""
        try:
            from hands.flight_search import stop_tracking
            event_bus.emit("tool_start", {"tool": "stop_tracking", "input": inp})
            result = stop_tracking(tracker_id=inp["tracker_id"])
            event_bus.emit("tool_end", {"tool": "stop_tracking", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Stop tracking error: {e}"}

    def _book_flight(self, inp):
        """Handle book_flight — navigate browser to airline booking page."""
        try:
            from hands.flight_search import book_flight
            event_bus.emit("tool_start", {"tool": "book_flight", "input": inp})
            result = book_flight(
                origin=inp["origin"],
                destination=inp["destination"],
                depart_date=inp["depart_date"],
                return_date=inp.get("return_date", ""),
                airline=inp.get("airline", ""),
                trip_type=inp.get("trip_type", "round_trip"),
                cabin=inp.get("cabin", "economy"),
                passengers=inp.get("passengers", 1),
                flight_number=inp.get("flight_number", 0),
            )
            event_bus.emit("tool_end", {"tool": "book_flight", "success": result.get("success")})
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Flight booking error: {e}"}

    def _generate_report(self, inp):
        """Handle generate_report brain tool — create Excel/PDF/CSV reports."""
        try:
            return _gen_report(
                format_type=inp["format"],
                title=inp["title"],
                headers=inp.get("headers"),
                rows=inp.get("rows"),
                sections=inp.get("sections"),
                filename=inp.get("filename"),
                summary=inp.get("summary"),
            )
        except Exception as e:
            return {"success": False, "error": True, "content": f"Report generation error: {e}"}

    def _propose_self_heal(self, inp):
        """Handle propose_self_heal brain tool — brain proposes a code change to itself."""
        description = inp.get("description", "")
        reason = inp.get("reason", "")
        if not description:
            return {"success": False, "error": True, "content": "Missing 'description' parameter."}

        try:
            from brain.self_heal import SelfHealEngine
            # Get or create the self-heal engine (tars.py owns the primary instance,
            # but we can create one here for the proposal mechanism)
            if not hasattr(self, '_self_heal'):
                self._self_heal = SelfHealEngine()

            proposal = self._self_heal.propose_capability(description, reason)

            # Ask for approval
            approved = self._self_heal.request_healing(
                self.sender,
                self.reader,
                proposal,
            )

            if approved:
                result = self._self_heal.execute_healing(approved, self)
                if result.get("success"):
                    return {
                        "success": True,
                        "content": (
                            f"🩹 Self-healing COMPLETE! I modified my own code.\n"
                            f"Change: {description[:200]}\n"
                            f"The fix will take effect on the next task cycle."
                        ),
                    }
                else:
                    return {
                        "success": False,
                        "error": True,
                        "content": f"🩹 Self-healing was approved but failed: {result.get('content', 'unknown')[:300]}",
                    }
            else:
                return {
                    "success": True,
                    "content": "🩹 Self-healing proposal was sent to Abdullah but not approved. Moving on.",
                }
        except Exception as e:
            return {"success": False, "error": True, "content": f"Self-heal error: {e}"}

    def _deploy_agent(self, agent_type, task):
        """
        Deploy a specialist agent. No hidden retry loops.
        
        If the agent succeeds → return success to brain.
        If the agent gets stuck → return the failure WITH full context 
        of all previous failures so the brain can make a smarter decision.
        
        The BRAIN decides what to do next, not the executor.
        """
        agent_class = AGENT_CLASSES.get(agent_type)
        if not agent_class:
            return {"success": False, "error": True, "content": f"Unknown agent type: {agent_type}"}

        # ── Hard limit: prevent infinite deployment loops ──
        deployment_count = len(self._deployment_log)
        if deployment_count >= self.max_deployments:
            failures = self._get_failure_summary()
            return {
                "success": False,
                "error": True,
                "content": (
                    f"DEPLOYMENT LIMIT REACHED ({self.max_deployments} agents deployed this task). "
                    f"You MUST ask Abdullah for help via send_imessage now.\n\n"
                    f"{failures}"
                ),
            }

        # ── Build context from previous failures + memory ──
        context_parts = []

        # Previous failure history (most important — prevents repeating mistakes)
        failure_summary = self._get_failure_summary()
        if failure_summary:
            context_parts.append(failure_summary)

        # Memory advice from past tasks
        memory_context = self.self_improve.get_pre_task_advice(agent_type, task)
        if memory_context:
            context_parts.append(f"## Learned from past tasks\n{memory_context}")

        # Inject home directory context for coder/file/system agents
        # Prevents ~ usage in Python open() calls and write_file paths
        if agent_type in ("coder", "file", "system"):
            import os as _os
            home = _os.path.expanduser("~")
            context_parts.append(
                f"## Environment\n"
                f"- Home directory: {home}\n"
                f"- Desktop: {home}/Desktop\n"
                f"- Downloads: {home}/Downloads\n"
                f"- IMPORTANT: Always use absolute paths starting with {home}/... — NEVER use ~ in file paths or Python open() calls."
            )

        # Handoff from another agent
        handoff = self.comms.get_handoff_context(agent_type)
        if handoff:
            context_parts.append(handoff)

        context = "\n\n".join(context_parts) if context_parts else None

        # ── Expand ~ in task string to absolute path (belt-and-suspenders) ──
        import os as _os
        home = _os.path.expanduser("~")
        if "~/" in task:
            task = task.replace("~/", f"{home}/")

        # ── Emit events ──
        attempt = deployment_count + 1
        event_bus.emit("agent_started", {
            "agent": agent_type,
            "task": task[:200],
            "attempt": attempt,
        })
        self.monitor.on_started(agent_type, task[:200], attempt)
        self.logger.info(f"🚀 Deploying {agent_type} agent (deployment {attempt}/{self.max_deployments}): {task[:100]}")

        # ── Reset browser state before deployment (prevents stale tab issues) ──
        if agent_type in ("research", "browser"):
            try:
                from hands.browser import _reset_page
                _reset_page()
            except Exception:
                pass

        # ── Create and run the agent (with timeout) ──
        agent_kwargs = dict(
            llm_client=self.llm_client,
            model=self.heavy_model,
            max_steps=40,
            phone=self.phone,
            kill_event=self._kill_event,
        )
        # Dev agent needs iMessage for interactive approval loop
        if agent_type == "dev":
            agent_kwargs["imessage_sender"] = self.sender
            agent_kwargs["imessage_reader"] = self.reader
            agent_kwargs["max_steps"] = 80  # Dev Agent v2: PRD sessions need more steps
        agent = agent_class(**agent_kwargs)

        agent_timeout = 300  # 5 minutes max per agent deployment
        if agent_type == "dev":
            agent_timeout = 3600  # 60 minutes for autonomous PRD-to-production sessions
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(agent.run, task, context)
                result = future.result(timeout=agent_timeout)
        except FuturesTimeout:
            result = {
                "success": False,
                "content": f"Agent timed out after {agent_timeout}s. The task may be too complex for a single agent deployment — try breaking it into smaller steps.",
                "steps": 0,
                "stuck": True,
                "stuck_reason": f"Timed out after {agent_timeout}s",
            }
            self.logger.warning(f"⏰ {agent_type} agent timed out after {agent_timeout}s")
        except Exception as e:
            result = {
                "success": False,
                "content": f"Agent crashed: {e}",
                "steps": 0,
                "stuck": True,
                "stuck_reason": f"Agent exception: {e}",
            }
            self.logger.error(f"💥 {agent_type} agent crashed: {e}")

        # ── Record this deployment ──
        entry = {
            "agent": agent_type,
            "task": task[:300],
            "success": result.get("success", False),
            "steps": result.get("steps", 0),
            "reason": result.get("stuck_reason") or result.get("content", "")[:300],
        }
        self._deployment_log.append(entry)

        # ── Record in self-improvement engine ──
        self.self_improve.record_task_outcome(
            agent_name=agent_type,
            task=task,
            result=result,
            escalation_history=[],
        )

        # ── Run post-task review for failures and high-step tasks ──
        try:
            review = self.self_improve.run_post_task_review(agent_type, task, result)
            if review:
                self.logger.info(f"📝 Post-task review: {review[:150]}")
        except Exception as e:
            self.logger.debug(f"Post-task review skipped: {e}")

        # ── Handoff context on success ──
        if result.get("success"):
            self.comms.send(
                from_agent=agent_type,
                to_agent="brain",
                content=result.get("content", "")[:500],
                msg_type="result",
            )

        # ── Emit completion ──
        event_bus.emit("agent_completed", {
            "agent": agent_type,
            "success": result.get("success", False),
            "steps": result.get("steps", 0),
            "stuck": result.get("stuck", False),
        })
        self.monitor.on_completed(agent_type, result.get("success", False), result.get("steps", 0))

        # ── Record in error tracker for pattern learning ──
        if not result.get("success"):
            stuck_reason = result.get("stuck_reason", result.get("content", "Unknown"))
            fix_info = error_tracker.record_error(
                error=stuck_reason[:500],
                context=f"deploy_{agent_type}_agent",
                tool=f"deploy_{agent_type}_agent",
                agent=agent_type,
                details=task[:200],
            )
            if fix_info and fix_info.get("has_fix"):
                self.logger.info(f"🩹 Known fix for {agent_type}: {fix_info['fix'][:80]}")

        # ── If failed, enrich with structured recovery guidance ──
        if not result.get("success"):
            stuck_reason = result.get("stuck_reason", result.get("content", "Unknown"))
            self.logger.warning(f"⚠️ {agent_type} agent stuck: {stuck_reason[:200]}")

            # Build rich failure response with recovery ladder
            all_failures = self._get_failure_summary()
            remaining = self.max_deployments - len(self._deployment_log)
            attempt_num = len([d for d in self._deployment_log if d["agent"] == agent_type])

            # Structured recovery ladder — escalates with each failure
            if attempt_num <= 1:
                recovery_level = "LEVEL 1 — SAME AGENT, BETTER INSTRUCTIONS"
                recovery_advice = (
                    "Analyze WHY the agent failed. The most likely cause: instructions were incomplete or ambiguous. "
                    "Redeploy the SAME agent with MORE SPECIFIC instructions — include exact CSS selectors, "
                    "exact text to look for, explicit wait times, and clearer success criteria."
                )
            elif attempt_num == 2:
                recovery_level = "LEVEL 2 — SAME AGENT, DIFFERENT APPROACH"
                recovery_advice = (
                    "The same approach failed twice. Try a COMPLETELY DIFFERENT strategy: "
                    "different URL, different navigation path, different form-filling order, "
                    "or break the task into smaller micro-steps (do ONLY step 1, verify, then step 2)."
                )
            elif attempt_num == 3:
                recovery_level = "LEVEL 3 — DIFFERENT AGENT"
                recovery_advice = (
                    "Three failures with the same agent type. Consider: "
                    "(1) Use research_agent to find an alternative approach first, "
                    "(2) Use coder_agent for a scripted approach instead of browser automation, "
                    "(3) Use system_agent if this can be done via native macOS apps."
                )
            else:
                recovery_level = "LEVEL 4+ — ASK ABDULLAH"
                recovery_advice = (
                    "Multiple failures across approaches. Ask Abdullah for help via send_imessage "
                    "with a SPECIFIC question: what exactly is failing, what you've tried, "
                    "and what information you need to proceed."
                )

            result["content"] = (
                f"❌ {agent_type} agent FAILED after {result.get('steps', 0)} steps.\n"
                f"Reason: {stuck_reason[:400]}\n\n"
                f"## Recovery: {recovery_level}\n{recovery_advice}\n\n"
                f"{all_failures}\n\n"
                f"Budget: {remaining} deployments remaining."
            )

        return result
