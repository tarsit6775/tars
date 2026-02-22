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
from agents.screen_agent import ScreenAgent
from agents.email_agent import EmailAgent
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
    "screen": ScreenAgent,
    "email": EmailAgent,
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

        # ── Fallback LLM client for agents (auto-failover when primary dies) ──
        # Use brain_llm as fallback since it's a different provider (Gemini vs Groq)
        self.fallback_llm_client = None
        self.fallback_model = None
        brain_cfg = config.get("brain_llm")
        if brain_cfg and brain_cfg.get("api_key"):
            # Only create fallback if it's a DIFFERENT provider than the agent's
            agent_provider = (agent_cfg or llm_cfg).get("provider", "")
            if brain_cfg["provider"] != agent_provider:
                self.fallback_llm_client = LLMClient(
                    provider=brain_cfg["provider"],
                    api_key=brain_cfg["api_key"],
                    base_url=brain_cfg.get("base_url"),
                )
                self.fallback_model = brain_cfg.get("heavy_model", brain_cfg.get("model", ""))
                logger.info(f"🔄 Agent fallback: {brain_cfg['provider']}/{self.fallback_model}")
        
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
        """Send a reply to BOTH iMessage AND the dashboard (true mirror).

        Every outgoing message appears on both platforms regardless of
        where the original message came from. If voice mode is active,
        also speaks the response via TTS.
        """
        # 1. Always emit WS event so dashboard shows TARS's reply
        event_bus.emit("imessage_sent", {"message": message})

        # 2. Always send iMessage so phone gets it too
        result = self.sender.send(message)

        # 3. Speak via TTS if voice is active
        source = self.get_reply_source()
        if source == "voice" and hasattr(self, '_voice_interface') and self._voice_interface:
            try:
                self._voice_interface.speak(message)
            except Exception as e:
                logger.warning(f"  🔊 Voice reply failed: {e}")

        logger.info(f"  📤 Reply mirrored to iMessage + dashboard")
        return result

    def set_voice_interface(self, voice_interface):
        """Set the voice interface reference for TTS replies."""
        self._voice_interface = voice_interface

    def reset_task_tracker(self):
        """Call this when a new user task starts (from tars.py)."""
        self._deployment_log = []

    @staticmethod
    def _safe_params(tool_input) -> dict:
        """Extract a safe, JSON-serializable copy of tool_input for error tracking.

        Strips long values and sensitive fields so the error tracker stores
        only what's needed to reproduce the issue.
        """
        if not isinstance(tool_input, dict):
            return {"raw": str(tool_input)[:300]}
        safe = {}
        sensitive = {"api_key", "password", "token", "secret", "key"}
        for k, v in tool_input.items():
            if k.lower() in sensitive:
                safe[k] = "***"
            elif isinstance(v, str) and len(v) > 300:
                safe[k] = v[:300] + "…"
            elif isinstance(v, (dict, list)):
                safe[k] = str(v)[:300]
            else:
                safe[k] = v
        return safe

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
            # Record every tool crash — this is the single funnel for ALL tools
            from memory.error_tracker import error_tracker
            error_tracker.record_error(
                error=f"Tool crash: {type(e).__name__}: {e}",
                context=tool_name,
                tool=tool_name,
                source_file="executor.py",
                details=f"Unhandled exception in _dispatch()",
                params=self._safe_params(tool_input),
            )

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

        elif tool_name == "deploy_screen_agent":
            return self._deploy_agent("screen", inp["task"])

        elif tool_name == "deploy_email_agent":
            return self._deploy_agent("email", inp["task"])

        elif tool_name == "deploy_dev_agent":
            # Prepend project_path to task string so the Dev Agent knows where to work
            task = inp["task"]
            project_path = inp.get("project_path", "")
            if project_path and project_path not in task:
                task = f"[Project: {project_path}]\n\n{task}"
            return self._deploy_agent("dev", task)

        # ─── Direct Tools ────────────────────────
        elif tool_name == "send_imessage":
            return self.send_reply(inp["message"])

        elif tool_name == "send_imessage_file":
            result = self.sender.send_file(
                file_path=inp["file_path"],
                caption=inp.get("caption"),
            )
            if result.get("success"):
                fname = os.path.basename(os.path.expanduser(inp["file_path"]))
                display = inp.get("caption", f"📎 {fname}")
                event_bus.emit("imessage_sent", {"message": f"{display}\n📎 {fname}"})
            return result

        elif tool_name == "wait_for_reply":
            result = self.reader.wait_for_reply(timeout=inp.get("timeout", 300))
            if result.get("success"):
                event_bus.emit("imessage_received", {"message": result.get("content", "")})
            return result

        elif tool_name == "save_memory":
            return self.memory.save(inp["category"], inp["key"], inp["value"])

        elif tool_name == "recall_memory":
            return self.memory.recall(inp["query"])

        elif tool_name == "list_memories":
            result = self.memory.list_all(category=inp.get("category"))
            event_bus.emit("tool_result", {"tool": "list_memories", "category": inp.get("category", "all")})
            return result

        elif tool_name == "delete_memory":
            result = self.memory.delete(inp["category"], key=inp.get("key"))
            event_bus.emit("tool_result", {"tool": "delete_memory", "category": inp["category"], "key": inp.get("key", "*")})
            return result

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

        # ─── Legacy / hallucinated tool names ──
        elif tool_name == "web_task":
            return self._deploy_agent("browser", inp["task"])

        elif tool_name == "browser_agent":
            # LLM sometimes hallucinates "browser_agent" instead of "deploy_browser_agent"
            task = inp.get("task", inp.get("command", inp.get("url", str(inp))))
            return self._deploy_agent("browser", task)

        elif tool_name == "screen_agent":
            # LLM sometimes hallucinates "screen_agent" instead of "deploy_screen_agent"
            task = inp.get("task", inp.get("command", str(inp)))
            return self._deploy_agent("screen", task)

        elif tool_name == "web_search":
            query = inp.get("query", "")
            if not query:
                return {"success": False, "error": True, "content": "⚠️ Missing 'query' parameter. Example: web_search({\"query\": \"weather in Miami\"})"}
            return self._web_search(query)

        # ─── Account Management (Keychain-backed) ──
        elif tool_name == "manage_account":
            return self._manage_account(inp)

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

        # ─── Scheduled Tasks ──
        elif tool_name == "schedule_task":
            return self._schedule_task(inp)
        elif tool_name == "list_scheduled_tasks":
            return self._list_scheduled_tasks(inp)
        elif tool_name == "remove_scheduled_task":
            return self._remove_scheduled_task(inp)

        # ─── Image Generation ──
        elif tool_name == "generate_image":
            return self._generate_image(inp)

        # ─── Home Automation ──
        elif tool_name == "smart_home":
            return self._smart_home(inp)

        # ─── PowerPoint ──
        elif tool_name == "generate_presentation":
            return self._generate_presentation(inp)

        # ─── Media Processing ──
        elif tool_name == "process_media":
            return self._process_media(inp)

        # ─── Document Ingestion (RAG) ──
        elif tool_name == "ingest_document":
            return self._ingest_document(inp)
        elif tool_name == "search_documents":
            return self._search_documents(inp)

        # ─── Headless Browser ──
        elif tool_name == "headless_browse":
            return self._headless_browse(inp)

        # ─── MCP (Model Context Protocol) ──
        elif tool_name == "mcp_list_tools":
            return self._mcp_list_tools(inp)
        elif tool_name == "mcp_call_tool":
            return self._mcp_call_tool(inp)

        # ─── Self-Healing ──
        elif tool_name == "propose_self_heal":
            return self._propose_self_heal(inp)

        elif tool_name == "get_error_report":
            return self._get_error_report(inp)

        else:
            from memory.error_tracker import error_tracker
            error_tracker.record_error(
                error=f"Unknown tool: {tool_name}",
                context="dispatch",
                tool=tool_name,
                source_file="executor.py",
                details="Brain hallucinated a tool name that doesn't exist",
                params=self._safe_params(inp),
            )
            return {"success": False, "error": True, "content": f"Unknown tool: {tool_name}"}

    def _web_search(self, query):
        """Fast web search — Serper API (primary), DuckDuckGo (fallback).
        
        Uses Serper Google Search API first (fast, reliable, no CAPTCHAs).
        Falls back to DuckDuckGo HTTP if Serper is unavailable.
        """
        import urllib.request
        import urllib.parse
        import re

        # ── Fast path: Serper API (most reliable) ──
        serper_key = self.config.get("research", {}).get("serper_api_key", "")
        if serper_key:
            try:
                from hands.research_apis import serper_search
                result = serper_search(query, serper_key, num_results=10)
                if result:
                    return {"success": True, "content": result}
            except Exception as e:
                logger.warning(f"⚠️ Serper search failed ({e}), trying DuckDuckGo...")

        # ── Fallback: DuckDuckGo HTML (no browser, no CAPTCHA) ──
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
    #  Account Management (Keychain-backed)
    # ─────────────────────────────────────────────

    def _manage_account(self, inp):
        """Handle manage_account brain tool — credential storage, playbooks, OTP."""
        try:
            from hands.account_manager import manage_account
            result = manage_account(inp)
            event_bus.emit("tool_result", {
                "tool": "manage_account",
                "action": inp.get("action", ""),
                "service": inp.get("service", ""),
                "success": result.get("success", False),
            })
            return result
        except Exception as e:
            return {"success": False, "error": True, "content": f"Account manager error: {e}"}

    # ─────────────────────────────────────────────
    #  Direct Mac Control (brain-level tools)
    # ─────────────────────────────────────────────

    def _mac_mail(self, inp):
        """Handle mac_mail brain tool — direct Mail.app control via hands/email.py."""
        from hands import email as mail_backend
        action = inp.get("action")
        if not action:
            return {"success": False, "error": True, "content": "Missing required 'action' parameter. Use: send, unread, inbox, read, search, verify_sent, reply, forward, delete, archive, move, flag, mark_read, mark_unread, drafts, list_folders, download_attachments, summarize, thread, run_rules, quick_reply, suggest_replies, list_quick_replies, save_template, list_templates, send_template, schedule, list_scheduled, cancel_scheduled, batch_read, batch_delete, batch_move, batch_forward, add_rule, list_rules, delete_rule, toggle_rule, followup, check_followups, lookup_contact, stats"}
        try:
            if action == "unread":
                return mail_backend.get_unread_count()
            elif action == "inbox":
                return mail_backend.read_inbox(inp.get("count", 5))
            elif action == "read":
                return mail_backend.read_message(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "search":
                return mail_backend.search_emails(
                    keyword=inp.get("keyword", ""),
                    sender=inp.get("sender", ""),
                    subject=inp.get("subject_filter", ""),
                    unread_only=inp.get("unread_only", False),
                    mailbox=inp.get("mailbox", "inbox"),
                )
            elif action == "send":
                return mail_backend.send_email(
                    to=inp["to"], subject=inp["subject"], body=inp["body"],
                    cc=inp.get("cc"), bcc=inp.get("bcc"),
                    attachment_paths=inp.get("attachment_path"),
                    html=inp.get("html", False),
                    from_address=inp.get("from_address", "tarsitgroup@outlook.com"),
                )
            elif action == "verify_sent":
                return mail_backend.verify_sent(inp["subject"], inp.get("to"))
            elif action == "reply":
                return mail_backend.reply_to(
                    inp.get("index", 1), inp.get("body", ""),
                    inp.get("reply_all", False), inp.get("mailbox", "inbox"),
                )
            elif action == "forward":
                return mail_backend.forward_to(
                    inp.get("index", 1), inp["to"],
                    inp.get("body", ""), inp.get("mailbox", "inbox"),
                )
            elif action == "delete":
                return mail_backend.delete_message(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "archive":
                return mail_backend.archive_message(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "move":
                return mail_backend.move_message(
                    inp.get("index", 1), inp.get("from_mailbox", "inbox"),
                    inp["to_mailbox"], inp.get("account"),
                )
            elif action == "flag":
                return mail_backend.flag_message(inp.get("index", 1), inp.get("flagged", True), inp.get("mailbox", "inbox"))
            elif action == "mark_read":
                return mail_backend.mark_read(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "mark_unread":
                return mail_backend.mark_unread(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "drafts":
                return mail_backend.list_drafts(inp.get("count", 10))
            elif action == "list_folders":
                return mail_backend.list_mailboxes()
            elif action == "download_attachments":
                return mail_backend.download_attachments(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "summarize":
                return mail_backend.summarize_inbox(inp.get("count", 20))
            elif action == "categorize":
                return mail_backend.categorize_inbox(inp.get("count", 20))
            elif action == "thread":
                subj = inp.get("subject_filter") or inp.get("keyword") or inp.get("index", "")
                return mail_backend.get_email_thread(subj, inp.get("count", 20))
            elif action == "run_rules":
                return mail_backend.run_rules_on_inbox(inp.get("count", 20))
            # ── Quick Replies ──
            elif action == "quick_reply":
                return mail_backend.send_quick_reply(
                    inp.get("index", 1), inp.get("reply_type", "acknowledge"),
                    inp.get("mailbox", "inbox"), inp.get("custom_note", ""),
                )
            elif action == "suggest_replies":
                return mail_backend.suggest_replies(inp.get("index", 1), inp.get("mailbox", "inbox"))
            elif action == "list_quick_replies":
                return mail_backend.list_quick_replies()
            # ── Templates ──
            elif action == "save_template":
                return mail_backend.save_template(inp["name"], inp.get("subject", ""), inp.get("body", ""))
            elif action == "list_templates":
                return mail_backend.list_templates()
            elif action == "send_template":
                return mail_backend.send_template(inp["name"], inp["to"], inp.get("variables", {}))
            # ── Scheduling ──
            elif action == "schedule":
                return mail_backend.schedule_email(
                    inp["to"], inp["subject"], inp["body"],
                    inp["send_at"], inp.get("html", False),
                )
            elif action == "list_scheduled":
                return mail_backend.list_scheduled()
            elif action == "cancel_scheduled":
                return mail_backend.cancel_scheduled(inp["schedule_id"])
            # ── Batch ──
            elif action == "batch_read":
                return mail_backend.batch_mark_read(
                    inp.get("indices"), inp.get("mailbox", "inbox"),
                    inp.get("all_unread", False),
                )
            elif action == "batch_delete":
                return mail_backend.batch_delete(inp.get("indices"), inp.get("mailbox", "inbox"), inp.get("sender"))
            elif action == "batch_move":
                return mail_backend.batch_move(inp["indices"], inp["to_mailbox"], inp.get("from_mailbox", "inbox"))
            elif action == "batch_forward":
                return mail_backend.batch_forward(inp["indices"], inp["to"], inp.get("body", ""), inp.get("mailbox", "inbox"))
            # ── Rules ──
            elif action == "add_rule":
                return mail_backend.add_email_rule(
                    inp["name"], inp.get("conditions", {}), inp.get("actions", []),
                )
            elif action == "list_rules":
                return mail_backend.list_email_rules()
            elif action == "delete_rule":
                return mail_backend.delete_email_rule(inp["rule_id"])
            elif action == "toggle_rule":
                return mail_backend.toggle_email_rule(inp["rule_id"])
            # ── Follow-ups ──
            elif action == "followup":
                return mail_backend.add_followup(
                    inp["subject"], inp["to"],
                    inp.get("deadline_hours", 48), inp.get("reminder_text", ""),
                )
            elif action == "check_followups":
                return mail_backend.check_followups()
            # ── Contacts ──
            elif action == "lookup_contact":
                return mail_backend.lookup_contact_email(inp["name"])
            elif action == "add_contact":
                return mail_backend.add_contact(inp["name"], inp["email"], inp.get("tags"), inp.get("notes", ""))
            elif action == "list_contacts":
                return mail_backend.list_contacts(inp.get("tag"))
            elif action == "search_contacts":
                return mail_backend.search_contacts(inp.get("query", inp.get("name", "")))
            elif action == "delete_contact":
                return mail_backend.delete_contact(inp.get("contact_id"), inp.get("email"))
            elif action == "auto_learn_contacts":
                return mail_backend.auto_learn_contacts()
            # ── Snooze ──
            elif action == "snooze":
                return mail_backend.snooze_email(
                    inp.get("index", 1), inp.get("snooze_until", "2h"),
                    inp.get("mailbox", "inbox"),
                )
            elif action == "list_snoozed":
                return mail_backend.list_snoozed()
            elif action == "cancel_snooze":
                return mail_backend.cancel_snooze(inp["snooze_id"])
            # ── Priority ──
            elif action == "priority_inbox":
                return mail_backend.priority_inbox(inp.get("count", 20))
            elif action == "sender_profile":
                return mail_backend.get_sender_profile(inp.get("sender", inp.get("query", "")))
            # ── Digest ──
            elif action == "digest":
                return mail_backend.generate_daily_digest()
            # ── OOO ──
            elif action == "set_ooo":
                return mail_backend.set_ooo(
                    inp.get("start_date", "today"),
                    inp["end_date"],
                    inp["ooo_message"],
                    inp.get("exceptions", []),
                )
            elif action == "cancel_ooo":
                return mail_backend.cancel_ooo()
            elif action == "ooo_status":
                return mail_backend.get_ooo_status()
            # ── Analytics ──
            elif action == "analytics":
                return mail_backend.get_email_analytics(inp.get("period", "week"))
            elif action == "email_health":
                return mail_backend.get_email_health()
            # ── Stats ──
            elif action == "stats":
                return mail_backend.get_email_stats()
            # ── Phase 8: Inbox Zero ──
            elif action == "clean_sweep":
                return mail_backend.clean_sweep(
                    older_than_days=inp.get("older_than_days", 7),
                    categories=inp.get("categories"),
                    dry_run=inp.get("dry_run", True)
                )
            elif action == "auto_triage":
                return mail_backend.auto_triage(count=inp.get("count", 20))
            elif action == "inbox_zero_status":
                return mail_backend.inbox_zero_status()
            elif action == "smart_unsubscribe":
                return mail_backend.smart_unsubscribe(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            # ── Phase 8: Attachments ──
            elif action == "build_attachment_index":
                return mail_backend.build_attachment_index(
                    count=inp.get("count", 50),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "search_attachments":
                return mail_backend.search_attachments(
                    filename=inp.get("filename"),
                    sender=inp.get("sender"),
                    file_type=inp.get("file_type"),
                    max_results=inp.get("max_results", 20)
                )
            elif action == "attachment_summary":
                return mail_backend.attachment_summary(count=inp.get("count", 50))
            elif action == "list_saved_attachments":
                return mail_backend.list_saved_attachments(
                    folder=inp.get("folder"),
                    file_type=inp.get("file_type")
                )
            # ── Phase 8: Contact Intelligence ──
            elif action == "score_relationships":
                return mail_backend.score_relationships()
            elif action == "detect_vips":
                return mail_backend.auto_detect_vips(threshold=inp.get("threshold", 70))
            elif action == "relationship_report":
                return mail_backend.get_relationship_report(contact_query=inp.get("contact_query", ""))
            elif action == "communication_graph":
                return mail_backend.communication_graph(top_n=inp.get("top_n", 15))
            elif action == "decay_contacts":
                return mail_backend.decay_stale_contacts(inactive_days=inp.get("inactive_days", 90))
            # ── Phase 9: Security & Trust ──
            elif action == "scan_email_security":
                return mail_backend.scan_email_security(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "check_sender_trust":
                return mail_backend.check_sender_trust(sender_email=inp.get("sender_email", ""))
            elif action == "scan_links":
                return mail_backend.scan_links(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "security_report":
                return mail_backend.get_security_report(count=inp.get("count", 20))
            elif action == "add_trusted_sender":
                return mail_backend.add_trusted_sender(
                    email_or_domain=inp.get("email_or_domain", ""),
                    reason=inp.get("reason", "")
                )
            elif action == "add_blocked_sender":
                return mail_backend.add_blocked_sender(
                    email_or_domain=inp.get("email_or_domain", ""),
                    reason=inp.get("reason", "")
                )
            elif action == "list_trusted_senders":
                return mail_backend.list_trusted_senders()
            elif action == "list_blocked_senders":
                return mail_backend.list_blocked_senders()
            # ── Phase 9: Action Items & Meetings ──
            elif action == "extract_action_items":
                return mail_backend.extract_action_items(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "extract_meeting_details":
                return mail_backend.extract_meeting_details(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "scan_inbox_actions":
                return mail_backend.scan_inbox_actions(count=inp.get("count", 20))
            elif action == "create_reminder":
                return mail_backend.create_reminder_from_email(
                    title=inp.get("title", ""),
                    due_date=inp.get("due_date"),
                    notes=inp.get("notes", ""),
                    source_email_subject=inp.get("source_email_subject", "")
                )
            elif action == "create_calendar_event":
                return mail_backend.create_calendar_event(
                    title=inp.get("title", ""),
                    start_datetime=inp.get("start_datetime", ""),
                    end_datetime=inp.get("end_datetime"),
                    location=inp.get("location", ""),
                    notes=inp.get("notes", "")
                )
            elif action == "list_actions":
                return mail_backend.list_extracted_actions(status=inp.get("status", "all"))
            elif action == "complete_action":
                return mail_backend.complete_action(action_id=inp.get("action_id", ""))
            elif action == "action_summary":
                return mail_backend.get_action_summary()
            # ── Phase 9: Workflow Chains ──
            elif action == "create_workflow":
                return mail_backend.create_workflow(
                    name=inp.get("workflow_name", ""),
                    trigger=inp.get("trigger", {}),
                    steps=inp.get("steps", []),
                    enabled=inp.get("enabled", True)
                )
            elif action == "list_workflows":
                return mail_backend.list_workflows()
            elif action == "get_workflow":
                return mail_backend.get_workflow(workflow_id=inp.get("workflow_id", ""))
            elif action == "delete_workflow":
                return mail_backend.delete_workflow(workflow_id=inp.get("workflow_id", ""))
            elif action == "toggle_workflow":
                return mail_backend.toggle_workflow(
                    workflow_id=inp.get("workflow_id", ""),
                    enabled=inp.get("enabled")
                )
            elif action == "run_workflow":
                return mail_backend.run_workflow_manual(
                    workflow_id=inp.get("workflow_id", ""),
                    email_index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "workflow_templates":
                return mail_backend.get_workflow_templates()
            elif action == "create_from_template":
                return mail_backend.create_workflow_from_template(
                    template_name=inp.get("template_name", ""),
                    params=inp.get("template_params")
                )
            elif action == "workflow_history":
                return mail_backend.get_workflow_history(
                    workflow_id=inp.get("workflow_id"),
                    limit=inp.get("limit", 20)
                )
            # ── Phase 10A: Smart Compose ──
            elif action == "smart_compose":
                return mail_backend.smart_compose(
                    prompt=inp.get("prompt", ""),
                    context_email=inp.get("context_email"),
                    tone=inp.get("tone", "professional"),
                    recipient=inp.get("recipient")
                )
            elif action == "rewrite_email":
                return mail_backend.rewrite_email(
                    text=inp.get("text", ""),
                    style=inp.get("style", "concise"),
                    tone=inp.get("tone", "professional")
                )
            elif action == "adjust_tone":
                return mail_backend.adjust_tone(
                    text=inp.get("text", ""),
                    tone=inp.get("tone", "formal")
                )
            elif action == "suggest_subject_lines":
                return mail_backend.suggest_subject_lines(
                    body=inp.get("body", inp.get("text", "")),
                    count=inp.get("count", 3)
                )
            elif action == "proofread_email":
                return mail_backend.proofread_email(
                    text=inp.get("text", "")
                )
            elif action == "compose_reply_draft":
                return mail_backend.compose_reply_draft(
                    index=inp.get("index", 1),
                    instructions=inp.get("instructions", ""),
                    tone=inp.get("tone", "professional"),
                    mailbox=inp.get("mailbox", "inbox")
                )
            # ── Phase 10B: Delegation ──
            elif action == "delegate_email":
                return mail_backend.delegate_email(
                    index=inp.get("index", 1),
                    delegate_to=inp.get("delegate_to", ""),
                    instructions=inp.get("instructions", ""),
                    deadline_hours=inp.get("deadline_hours", 48),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "list_delegations":
                return mail_backend.list_delegations(
                    status=inp.get("status", "all"),
                    delegate_to=inp.get("delegate_to")
                )
            elif action == "update_delegation":
                return mail_backend.update_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                    status=inp.get("status"),
                    notes=inp.get("notes")
                )
            elif action == "complete_delegation":
                return mail_backend.complete_delegation(
                    delegation_id=inp.get("delegation_id", ""),
                    outcome=inp.get("outcome", "")
                )
            elif action == "cancel_delegation":
                return mail_backend.cancel_delegation(
                    delegation_id=inp.get("delegation_id", "")
                )
            elif action == "delegation_dashboard":
                return mail_backend.delegation_dashboard()
            elif action == "nudge_delegation":
                return mail_backend.nudge_delegation(
                    delegation_id=inp.get("delegation_id", "")
                )
            # ── Phase 10C: Contextual Search ──
            elif action == "contextual_search":
                return mail_backend.contextual_search(
                    query=inp.get("query", ""),
                    max_results=inp.get("max_results", 10)
                )
            elif action == "build_search_index":
                return mail_backend.build_search_index(
                    count=inp.get("count", 200),
                    mailbox=inp.get("mailbox", "inbox")
                )
            elif action == "conversation_recall":
                return mail_backend.conversation_recall(
                    contact_query=inp.get("contact_query", inp.get("query", "")),
                    days=inp.get("days", 14),
                    summarize=inp.get("summarize", False)
                )
            elif action == "search_by_date_range":
                return mail_backend.search_by_date_range(
                    start_date=inp.get("start_date", ""),
                    end_date=inp.get("end_date", ""),
                    sender=inp.get("sender"),
                    keyword=inp.get("keyword")
                )
            elif action == "find_related_emails":
                return mail_backend.find_related_emails(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                    max_results=inp.get("max_results", 5)
                )
            # ── Phase 11A: Sentiment Analysis ──
            elif action == "analyze_sentiment":
                return mail_backend.analyze_sentiment(
                    index=inp.get("index", 1),
                    mailbox=inp.get("mailbox", "inbox"),
                )
            elif action == "batch_sentiment":
                return mail_backend.batch_sentiment(
                    count=inp.get("count", 20),
                    mailbox=inp.get("mailbox", "inbox"),
                )
            elif action == "sender_sentiment":
                return mail_backend.sender_sentiment(
                    sender_email=inp.get("sender_email", inp.get("sender", "")),
                )
            elif action == "sentiment_alerts":
                return mail_backend.sentiment_alerts(
                    threshold=inp.get("threshold", -20),
                )
            elif action == "sentiment_report":
                return mail_backend.sentiment_report(
                    period=inp.get("period", "week"),
                )
            # ── Phase 11B: Smart Folders ──
            elif action == "create_smart_folder":
                return mail_backend.create_smart_folder(
                    name=inp.get("folder_name", inp.get("name", "")),
                    criteria=inp.get("criteria", {}),
                    pinned=inp.get("pinned", False),
                )
            elif action == "list_smart_folders":
                return mail_backend.list_smart_folders()
            elif action == "get_smart_folder":
                return mail_backend.get_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    max_results=inp.get("max_results", 20),
                )
            elif action == "update_smart_folder":
                return mail_backend.update_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    name=inp.get("folder_name", inp.get("name")),
                    criteria=inp.get("criteria"),
                )
            elif action == "delete_smart_folder":
                return mail_backend.delete_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                )
            elif action == "pin_smart_folder":
                return mail_backend.pin_smart_folder(
                    folder_id=inp.get("folder_id", ""),
                    pinned=inp.get("pinned", True),
                )
            # ── Phase 11C: Thread Summarization ──
            elif action == "summarize_thread":
                return mail_backend.summarize_thread(
                    subject_or_index=inp.get("subject_or_index", inp.get("subject_filter", "")),
                    max_messages=inp.get("max_messages", 20),
                )
            elif action == "thread_decisions":
                return mail_backend.thread_decisions(
                    subject_or_index=inp.get("subject_or_index", inp.get("subject_filter", "")),
                    max_messages=inp.get("max_messages", 20),
                )
            elif action == "thread_participants":
                return mail_backend.thread_participants(
                    subject_or_index=inp.get("subject_or_index", inp.get("subject_filter", "")),
                    max_messages=inp.get("max_messages", 20),
                )
            elif action == "thread_timeline":
                return mail_backend.thread_timeline(
                    subject_or_index=inp.get("subject_or_index", inp.get("subject_filter", "")),
                    max_messages=inp.get("max_messages", 20),
                )
            elif action == "prepare_forward_summary":
                return mail_backend.prepare_forward_summary(
                    subject_or_index=inp.get("subject_or_index", inp.get("subject_filter", "")),
                    recipient=inp.get("recipient"),
                    max_messages=inp.get("max_messages", 20),
                )
            # ── Phase 12A: Labels & Tags ──
            elif action == "add_label":
                return mail_backend.add_label(index=inp.get("index", 1), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox"))
            elif action == "remove_label":
                return mail_backend.remove_label(index=inp.get("index", 1), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox"))
            elif action == "list_labels":
                return mail_backend.list_labels()
            elif action == "get_labeled_emails":
                return mail_backend.get_labeled_emails(label=inp.get("label", ""), max_results=inp.get("max_results", 20))
            elif action == "bulk_label":
                return mail_backend.bulk_label(indices=inp.get("indices", []), label=inp.get("label", ""), mailbox=inp.get("mailbox", "inbox"))
            # ── Phase 12B: Newsletter Management ──
            elif action == "detect_newsletters":
                return mail_backend.detect_newsletters(count=inp.get("count", 30), mailbox=inp.get("mailbox", "inbox"))
            elif action == "newsletter_digest":
                return mail_backend.newsletter_digest(count=inp.get("count", 20), mailbox=inp.get("mailbox", "inbox"))
            elif action == "newsletter_stats":
                return mail_backend.newsletter_stats()
            elif action == "newsletter_preferences":
                return mail_backend.newsletter_preferences(sender=inp.get("sender", ""), action=inp.get("pref_action", inp.get("action_value", "keep")))
            elif action == "apply_newsletter_preferences":
                return mail_backend.apply_newsletter_preferences(count=inp.get("count", 30), mailbox=inp.get("mailbox", "inbox"), dry_run=inp.get("dry_run", True))
            # ── Phase 12C: Auto-Responder ──
            elif action == "create_auto_response":
                return mail_backend.create_auto_response(
                    name=inp.get("name", ""), conditions=inp.get("conditions", {}),
                    response_body=inp.get("response_body", ""), response_subject=inp.get("response_subject"),
                    enabled=inp.get("enabled", True), max_replies=inp.get("max_replies", 1),
                )
            elif action == "list_auto_responses":
                return mail_backend.list_auto_responses()
            elif action == "update_auto_response":
                return mail_backend.update_auto_response(
                    rule_id=inp.get("rule_id", ""), name=inp.get("name"),
                    conditions=inp.get("conditions"), response_body=inp.get("response_body"),
                    max_replies=inp.get("max_replies"),
                )
            elif action == "delete_auto_response":
                return mail_backend.delete_auto_response(rule_id=inp.get("rule_id", ""))
            elif action == "toggle_auto_response":
                return mail_backend.toggle_auto_response(rule_id=inp.get("rule_id", ""), enabled=inp.get("enabled"))
            elif action == "auto_response_history":
                return mail_backend.auto_response_history(limit=inp.get("limit", 20))
            # ── Phase 13A: Signatures ──
            elif action == "create_signature":
                return mail_backend.create_signature(name=inp.get("name", ""), body=inp.get("body", ""), is_html=inp.get("is_html", False))
            elif action == "list_signatures":
                return mail_backend.list_signatures()
            elif action == "update_signature":
                return mail_backend.update_signature(sig_id=inp.get("sig_id", ""), name=inp.get("name"), body=inp.get("body"), is_html=inp.get("is_html"))
            elif action == "delete_signature":
                return mail_backend.delete_signature(sig_id=inp.get("sig_id", ""))
            elif action == "set_default_signature":
                return mail_backend.set_default_signature(sig_id=inp.get("sig_id", ""))
            elif action == "get_signature":
                return mail_backend.get_signature(sig_id=inp.get("sig_id"))
            # ── Phase 13B: Aliases / Identities ──
            elif action == "add_alias":
                return mail_backend.add_alias(email=inp.get("alias_email", ""), display_name=inp.get("display_name", ""), signature_id=inp.get("sig_id"))
            elif action == "list_aliases":
                return mail_backend.list_aliases()
            elif action == "update_alias":
                return mail_backend.update_alias(alias_id=inp.get("alias_id", ""), email=inp.get("alias_email"), display_name=inp.get("display_name"), signature_id=inp.get("sig_id"))
            elif action == "delete_alias":
                return mail_backend.delete_alias(alias_id=inp.get("alias_id", ""))
            elif action == "set_default_alias":
                return mail_backend.set_default_alias(alias_id=inp.get("alias_id", ""))
            # ── Phase 13C: Export / Archival ──
            elif action == "export_emails":
                return mail_backend.export_emails(count=inp.get("count", 10), mailbox=inp.get("mailbox", "inbox"), format=inp.get("export_format", "json"))
            elif action == "export_thread":
                return mail_backend.export_thread(subject_or_index=inp.get("subject_or_index", ""), format=inp.get("export_format", "json"))
            elif action == "backup_mailbox":
                return mail_backend.backup_mailbox(mailbox=inp.get("mailbox", "inbox"), max_emails=inp.get("max_emails", 100))
            elif action == "list_backups":
                return mail_backend.list_backups()
            elif action == "search_exports":
                return mail_backend.search_exports(keyword=inp.get("keyword", ""))
            elif action == "export_stats":
                return mail_backend.get_export_stats()

            # ── Phase 14: Templates ──
            elif action == "create_template":
                return mail_backend.create_template(name=inp.get("name", ""), subject_template=inp.get("subject_template", ""), body_template=inp.get("body_template", ""), category=inp.get("category", "general"))
            elif action == "list_templates":
                return mail_backend.list_templates(category=inp.get("category"))
            elif action == "get_template":
                return mail_backend.get_template(template_id=inp.get("template_id", ""))
            elif action == "update_template":
                return mail_backend.update_template(template_id=inp.get("template_id", ""), name=inp.get("name"), subject_template=inp.get("subject_template"), body_template=inp.get("body_template"), category=inp.get("category"))
            elif action == "delete_template":
                return mail_backend.delete_template(template_id=inp.get("template_id", ""))
            elif action == "use_template":
                return mail_backend.use_template(template_id=inp.get("template_id", ""), variables=inp.get("variables"))

            # ── Phase 15: Drafts Management ──
            elif action == "save_draft":
                return mail_backend.save_draft(to=inp.get("to", ""), subject=inp.get("subject", ""), body=inp.get("body", ""), cc=inp.get("cc", ""), bcc=inp.get("bcc", ""))
            elif action == "list_drafts_managed":
                return mail_backend.list_drafts()
            elif action == "get_draft":
                return mail_backend.get_draft(draft_id=inp.get("draft_id", ""))
            elif action == "update_draft":
                return mail_backend.update_draft(draft_id=inp.get("draft_id", ""), to=inp.get("to"), subject=inp.get("subject"), body=inp.get("body"), cc=inp.get("cc"), bcc=inp.get("bcc"))
            elif action == "delete_draft":
                return mail_backend.delete_draft(draft_id=inp.get("draft_id", ""))

            # ── Phase 16: Folder Management ──
            elif action == "create_mail_folder":
                return mail_backend.create_mail_folder(folder_name=inp.get("folder_name", ""), parent=inp.get("parent", ""))
            elif action == "list_mail_folders":
                return mail_backend.list_mail_folders()
            elif action == "rename_mail_folder":
                return mail_backend.rename_mail_folder(folder_name=inp.get("folder_name", ""), new_name=inp.get("new_name", ""))
            elif action == "delete_mail_folder":
                return mail_backend.delete_mail_folder(folder_name=inp.get("folder_name", ""))
            elif action == "move_to_folder":
                return mail_backend.move_to_folder(email_index=inp.get("index", 1), folder_name=inp.get("folder_name", ""))
            elif action == "get_folder_stats":
                return mail_backend.get_folder_stats()

            # ── Phase 17: Email Tracking ──
            elif action == "track_email":
                return mail_backend.track_email(subject=inp.get("subject", ""), recipient=inp.get("recipient", ""), sent_at=inp.get("sent_at", ""))
            elif action == "list_tracked_emails":
                return mail_backend.list_tracked_emails()
            elif action == "get_tracking_status":
                return mail_backend.get_tracking_status(tracking_id=inp.get("tracking_id", ""))
            elif action == "tracking_report":
                return mail_backend.tracking_report()
            elif action == "untrack_email":
                return mail_backend.untrack_email(tracking_id=inp.get("tracking_id", ""))

            # ── Phase 18: Extended Batch Ops ──
            elif action == "batch_archive":
                return mail_backend.batch_archive(indices=inp.get("indices", []))
            elif action == "batch_reply":
                return mail_backend.batch_reply(indices=inp.get("indices", []), body=inp.get("body", ""))

            # ── Phase 19: Calendar Integration ──
            elif action == "email_to_event":
                return mail_backend.email_to_event(email_index=inp.get("index", 1), calendar_name=inp.get("calendar_name", ""))
            elif action == "list_email_events":
                return mail_backend.list_email_events()
            elif action == "upcoming_from_email":
                return mail_backend.upcoming_from_email(days=inp.get("days", 7))
            elif action == "meeting_conflicts":
                return mail_backend.meeting_conflicts(date=inp.get("date", ""))
            elif action == "sync_email_calendar":
                return mail_backend.sync_email_calendar()

            # ── Phase 20: Dashboard & Reporting ──
            elif action == "email_dashboard":
                return mail_backend.email_dashboard()
            elif action == "weekly_report":
                return mail_backend.weekly_report()
            elif action == "monthly_report":
                return mail_backend.monthly_report()
            elif action == "productivity_score":
                return mail_backend.productivity_score()
            elif action == "email_trends":
                return mail_backend.email_trends(days=inp.get("days", 30))

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
        """Handle generate_report brain tool — create Excel/PDF/CSV reports.
        
        Accepts either:
          A) Flat tabular: headers=["A","B"], rows=[["1","2"]]
          B) Nested data dict: data={...} — auto-converted to tabular format
        """
        try:
            # ── Normalize param names (brain sometimes uses 'report_format') ──
            fmt = inp.get("format") or inp.get("report_format", "excel")
            title = inp.get("title", "TARS Report")
            headers = inp.get("headers")
            rows = inp.get("rows")
            sections = inp.get("sections")
            filename = inp.get("filename")
            summary = inp.get("summary")

            # ── Auto-convert nested 'data' dict → tabular headers+rows ──
            raw_data = inp.get("data")
            if raw_data and isinstance(raw_data, dict) and not headers:
                headers, rows, extra_sections = self._data_dict_to_tabular(raw_data)
                # If we extracted list-type data as sections (e.g. news, papers),
                # auto-switch to PDF if no explicit format or merge into summary
                if extra_sections and not sections:
                    sections = extra_sections
                    if fmt in ("excel", "xlsx"):
                        # Add list data as summary key-value pairs for Excel
                        if not summary:
                            summary = {}
                        for sec in extra_sections:
                            summary[sec["heading"]] = sec["body"][:500]

            return _gen_report(
                format_type=fmt,
                title=title,
                headers=headers,
                rows=rows,
                sections=sections,
                filename=filename,
                summary=summary,
            )
        except Exception as e:
            return {"success": False, "error": True, "content": f"Report generation error: {e}"}

    def _data_dict_to_tabular(self, data):
        """Convert a nested data dict from research into tabular headers+rows.
        
        Handles patterns like:
          {"stock_data": {"NVDA": {"price": "$182", "P/E": "45"}, ...}}
          {"news": ["headline1", "headline2"], ...}
          
        Returns: (headers, rows, extra_sections)
          - headers/rows for tabular data (dicts-of-dicts)
          - extra_sections for list data (news, papers) as PDF sections
        """
        headers = []
        rows = []
        extra_sections = []

        # Separate dict-of-dicts (tabular) from lists (text sections)
        tabular_keys = {}   # key → {entity: {col: val}}
        list_keys = {}      # key → [items]

        for key, value in data.items():
            if isinstance(value, dict):
                # Check if it's a dict of dicts (e.g. stock_data → {NVDA: {...}})
                if all(isinstance(v, dict) for v in value.values()):
                    tabular_keys[key] = value
                else:
                    # Flat dict — treat as single-row tabular
                    tabular_keys[key] = {"": value}
            elif isinstance(value, list):
                list_keys[key] = value
            else:
                # Scalar — add as summary-like
                list_keys[key] = [str(value)]

        # ── Build tabular data from dict-of-dicts ──
        if tabular_keys:
            # Collect all column names across all entities
            all_columns = set()
            all_entities = []
            for section_name, entities in tabular_keys.items():
                for entity_name, entity_data in entities.items():
                    label = f"{entity_name}" if entity_name else section_name
                    all_columns.update(entity_data.keys())
                    all_entities.append((label, entity_data))

            # Build headers and rows
            sorted_cols = sorted(all_columns)
            headers = ["Name"] + [col.replace("_", " ").title() for col in sorted_cols]
            for label, entity_data in all_entities:
                row = [label] + [str(entity_data.get(col, "N/A")) for col in sorted_cols]
                rows.append(row)

        # ── Build sections from list data ──
        for key, items in list_keys.items():
            heading = key.replace("_", " ").title()
            body = "\n".join(f"• {item}" if isinstance(item, str) else f"• {json.dumps(item)}" for item in items)
            extra_sections.append({"heading": heading, "body": body})

        return headers, rows, extra_sections

    # ─── Scheduled Tasks Handlers ────────────────────────

    def set_scheduler(self, scheduler):
        """Set the task scheduler reference."""
        self._scheduler = scheduler

    def _schedule_task(self, inp):
        """Add a scheduled recurring task."""
        task = inp.get("task", "")
        schedule = inp.get("schedule", "")
        if not task or not schedule:
            return {"success": False, "error": True, "content": "Both 'task' and 'schedule' are required."}
        if not hasattr(self, '_scheduler') or not self._scheduler:
            return {"success": False, "error": True, "content": "Task scheduler not initialized."}
        event_bus.emit("tool_use", {"tool": "schedule_task", "task": task, "schedule": schedule})
        return self._scheduler.add_task(task, schedule)

    def _list_scheduled_tasks(self, inp):
        """List all scheduled tasks."""
        if not hasattr(self, '_scheduler') or not self._scheduler:
            return {"success": False, "error": True, "content": "Task scheduler not initialized."}
        return self._scheduler.list_tasks()

    def _remove_scheduled_task(self, inp):
        """Remove a scheduled task."""
        task_id = inp.get("task_id", "")
        if not task_id:
            return {"success": False, "error": True, "content": "task_id required. Use list_scheduled_tasks to see IDs."}
        if not hasattr(self, '_scheduler') or not self._scheduler:
            return {"success": False, "error": True, "content": "Task scheduler not initialized."}
        return self._scheduler.remove_task(task_id)

    # ─── Image Generation Handler ─────────────────────

    def _generate_image(self, inp):
        """Generate an image using DALL-E 3."""
        from hands.image_gen import generate_image

        prompt = inp.get("prompt", "")
        if not prompt:
            return {"success": False, "error": True, "content": "Missing 'prompt' parameter."}

        # Get API key from config
        api_key = (
            self.config.get("image_generation", {}).get("api_key", "") or
            self.config.get("voice", {}).get("openai_api_key", "") or
            self.config.get("openai", {}).get("api_key", "")
        )

        img_cfg = self.config.get("image_generation", {})
        event_bus.emit("tool_use", {"tool": "generate_image", "prompt": prompt[:100]})

        result = generate_image(
            prompt=prompt,
            api_key=api_key,
            size=inp.get("size", img_cfg.get("default_size", "1024x1024")),
            quality=inp.get("quality", img_cfg.get("default_quality", "standard")),
            style=inp.get("style", "vivid"),
        )
        return result

    # ─── Home Automation Handler ──────────────────────

    def _smart_home(self, inp):
        """Control smart home devices via Home Assistant."""
        from hands.home_automation import HomeAutomation

        if not hasattr(self, '_home'):
            self._home = HomeAutomation(self.config)

        event_bus.emit("tool_use", {"tool": "smart_home", "action": inp.get("action", "")})
        return self._home.execute(
            action=inp.get("action", ""),
            entity_id=inp.get("entity_id"),
            data=inp.get("data"),
        )

    # ─── PowerPoint Handler ──────────────────────────

    def _generate_presentation(self, inp):
        """Generate a PowerPoint presentation."""
        from hands.pptx_gen import generate_presentation

        title = inp.get("title", "TARS Presentation")
        slides = inp.get("slides", [])
        if not slides:
            return {"success": False, "error": True, "content": "At least one slide required."}

        event_bus.emit("tool_use", {"tool": "generate_presentation", "title": title})
        return generate_presentation(
            title=title,
            slides=slides,
            subtitle=inp.get("subtitle"),
            filename=inp.get("filename"),
        )

    # ─── Media Processing Handler ─────────────────────

    def _process_media(self, inp):
        """Process video/audio files."""
        from hands.media_processor import process_media

        action = inp.get("action", "")
        input_path = inp.get("input_path", "")
        if not action or not input_path:
            return {"success": False, "error": True, "content": "Both 'action' and 'input_path' are required."}

        # Get OpenAI key for transcription
        api_key = (
            self.config.get("voice", {}).get("openai_api_key", "") or
            self.config.get("image_generation", {}).get("api_key", "") or
            self.config.get("openai", {}).get("api_key", "")
        )

        event_bus.emit("tool_use", {"tool": "process_media", "action": action})
        return process_media(
            action=action,
            input_path=input_path,
            output_format=inp.get("output_format"),
            start=inp.get("start"),
            end=inp.get("end"),
            output_path=inp.get("output_path"),
            openai_api_key=api_key,
        )

    def _ingest_document(self, inp):
        """Ingest a document into semantic memory for RAG search."""
        file_path = inp.get("file_path", "")
        if not file_path:
            return {"success": False, "error": True, "content": "Missing 'file_path' parameter."}

        if not self.memory.semantic or not self.memory.semantic.available:
            return {"success": False, "error": True, "content": "Semantic memory unavailable (pip install chromadb)."}

        event_bus.emit("tool_use", {"tool": "ingest_document", "file": file_path})
        return self.memory.semantic.ingest_document(
            file_path=file_path,
            chunk_size=inp.get("chunk_size", 1000),
            chunk_overlap=inp.get("chunk_overlap", 200),
        )

    def _search_documents(self, inp):
        """Search ingested documents using semantic search (RAG)."""
        query = inp.get("query", "")
        if not query:
            return {"success": False, "error": True, "content": "Missing 'query' parameter."}

        if not self.memory.semantic or not self.memory.semantic.available:
            return {"success": False, "error": True, "content": "Semantic memory unavailable (pip install chromadb)."}

        event_bus.emit("tool_use", {"tool": "search_documents", "query": query})
        return self.memory.semantic.search_documents(query, n_results=inp.get("n_results", 5))

    def _headless_browse(self, inp):
        """Fast headless browser for scraping/screenshots without Chrome."""
        action = inp.get("action", "")
        url = inp.get("url", "")
        if not action or not url:
            return {"success": False, "error": True, "content": "Both 'action' and 'url' are required."}

        event_bus.emit("tool_use", {"tool": "headless_browse", "action": action, "url": url})

        try:
            from hands.headless_browser import scrape_page, take_screenshot, extract_links, extract_tables

            if action == "scrape":
                return scrape_page(url)
            elif action == "screenshot":
                return take_screenshot(url)
            elif action == "links":
                return extract_links(url)
            elif action == "tables":
                return extract_tables(url)
            else:
                return {"success": False, "error": True, "content": f"Unknown action: {action}. Use: scrape, screenshot, links, tables."}
        except ImportError:
            return {"success": False, "error": True, "content": "Headless browser unavailable (pip install playwright && playwright install chromium)."}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Headless browse error: {e}"}

    def set_mcp_client(self, mcp_client):
        """Set the MCP client reference for tool routing."""
        self._mcp_client = mcp_client

    def _mcp_list_tools(self, inp):
        """List all available MCP tools."""
        if not hasattr(self, '_mcp_client') or not self._mcp_client:
            return {"success": False, "error": True, "content": "No MCP client configured. Add 'mcp.servers' to config.yaml."}

        event_bus.emit("tool_use", {"tool": "mcp_list_tools"})
        return self._mcp_client.list_tools()

    def _mcp_call_tool(self, inp):
        """Call a tool on a connected MCP server."""
        if not hasattr(self, '_mcp_client') or not self._mcp_client:
            return {"success": False, "error": True, "content": "No MCP client configured. Add 'mcp.servers' to config.yaml."}

        tool_ref = inp.get("tool", "")
        if not tool_ref:
            return {"success": False, "error": True, "content": "Missing 'tool' parameter. Use mcp_list_tools to discover available tools."}

        event_bus.emit("tool_use", {"tool": "mcp_call_tool", "mcp_tool": tool_ref})
        return self._mcp_client.call_tool(tool_ref, inp.get("arguments", {}))

    def _get_error_report(self, inp):
        """Return the error tracker report in the requested format."""
        try:
            fmt = inp.get("format", "dev_prompt")
            if fmt == "dev_prompt":
                report = error_tracker.generate_dev_prompt(max_errors=15)
            else:
                report = error_tracker.get_error_report()
            return {"success": True, "content": report}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Error generating report: {e}"}

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

        # Inject previous browser agent's state checkpoint for continuity
        if agent_type == "browser":
            for prev in reversed(self._deployment_log):
                if prev.get("agent") == "browser" and prev.get("checkpoint"):
                    cp = prev["checkpoint"]
                    checkpoint_ctx = (
                        f"## Previous Browser Agent State\n"
                        f"- Domain: {cp.get('domain', '?')}\n"
                        f"- Visited URLs: {', '.join(cp.get('visited_urls', [])[:5])}\n"
                        f"- Past signup form: {cp.get('past_first_page', False)}\n"
                        f"- Flow progress: {' → '.join(cp.get('flow_steps', [])[-5:])}\n"
                        f"- ⚠️ Do NOT navigate back to URLs the previous agent already visited.\n"
                        f"- ⚠️ Chrome may still be on the page where the previous agent stopped — look first!"
                    )
                    context_parts.append(checkpoint_ctx)
                    break

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

        # ── Reset browser state before deployment ──
        # For browser agents: only clear internal state, DON'T navigate away
        #   (preserves page for multi-step flows like signup → birthday → CAPTCHA)
        # For research agents: navigate to blank (they shouldn't have pages open)
        if agent_type in ("research", "browser"):
            try:
                from hands.browser import _reset_page
                _reset_page(navigate=(agent_type != "browser"))
            except Exception:
                pass

        # ── Create and run the agent (with timeout) ──
        agent_kwargs = dict(
            llm_client=self.llm_client,
            model=self.heavy_model,
            max_steps=40,
            phone=self.phone,
            kill_event=self._kill_event,
            fallback_client=self.fallback_llm_client,
            fallback_model=self.fallback_model,
        )
        # Dev agent needs iMessage for interactive approval loop
        if agent_type == "dev":
            agent_kwargs["imessage_sender"] = self.sender
            agent_kwargs["imessage_reader"] = self.reader
            agent_kwargs["max_steps"] = 80  # Dev Agent v2: PRD sessions need more steps
        # Research agent needs config for API keys (Serper, etc.)
        if agent_type == "research":
            agent_kwargs["config"] = self.config
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

        # ── Save browser agent checkpoint on failure for handoff ──
        if agent_type == "browser" and not result.get("success"):
            try:
                checkpoint = agent.get_state_checkpoint() if hasattr(agent, 'get_state_checkpoint') else None
                if checkpoint:
                    entry["checkpoint"] = checkpoint
            except Exception:
                pass

        # ── Record browser errors to site_knowledge for learning ──
        if agent_type == "browser" and not result.get("success"):
            try:
                from memory.site_knowledge import site_knowledge as _sk
                stuck_reason = result.get("stuck_reason", "")
                content = result.get("content", "")[:200]
                domain = entry.get("checkpoint", {}).get("domain", "")
                if domain and (stuck_reason or content):
                    _sk.learn_error_fix(domain, stuck_reason or content, "pending investigation")
            except Exception:
                pass

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

            # ── Budget awareness nudge ──
            # When >50% of deployments used, or same agent type deployed 3+ times,
            # remind the brain to move forward to the next phase
            deployed = len(self._deployment_log)
            remaining = self.max_deployments - deployed
            same_type_count = sum(1 for d in self._deployment_log if d["agent"] == agent_type)

            budget_nudge = ""
            if same_type_count >= 3:
                budget_nudge = (
                    f"\n\n⚡ BUDGET ALERT: You've deployed {same_type_count} {agent_type} agents this task. "
                    f"Only {remaining} deployments remaining. "
                    f"If you have enough data, MOVE FORWARD to the next phase (compile → report → deliver). "
                    f"Don't keep researching — use what you have."
                )
            elif deployed > self.max_deployments * 0.5:
                budget_nudge = (
                    f"\n\n⚡ Budget: {remaining}/{self.max_deployments} deployments remaining. "
                    f"Make sure you've saved enough for report generation and delivery."
                )

            if budget_nudge:
                result["content"] = result.get("content", "") + budget_nudge

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
            stuck_reason = result.get("stuck_reason", "Unknown")
            # Use stuck_reason directly (not content which may have recovery guidance)
            fix_info = error_tracker.record_error(
                error=stuck_reason[:500],
                context=f"deploy_{agent_type}_agent",
                tool=f"deploy_{agent_type}_agent",
                agent=agent_type,
                source_file="executor.py",
                details=f"Agent stuck after {result.get('steps', 0)} steps",
                params={"task": task[:300], "steps": result.get("steps", 0)},
            )
            if fix_info and fix_info.get("has_fix"):
                self.logger.info(f"🩹 Known fix for {agent_type}: {fix_info['fix'][:80]}")

        # ── AUTO-ESCALATION: DISABLED ──
        # Previously auto-escalated Browser→Screen Agent on failure.
        # DISABLED because:
        # 1. Screen agent is WORSE at web forms than browser agent (40 steps wasted every time)
        # 2. Screen agent types into wrong windows when focus shifts (corrupts VS Code files)
        # 3. Better to let the brain re-deploy browser agent with a smaller/simpler task
        # The brain's recovery ladder (LEVEL 1-3) handles retries with better instructions.

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
