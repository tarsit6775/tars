# TARS — Copilot Instructions

> **Living document** — When Copilot makes an error or a pattern breaks, add a rule to § "Lessons Learned" at the bottom so it never happens again.

---

## ⚙️ Editing Rules (READ FIRST)

These rules prevent garbled/broken edits. Copilot MUST follow them:

1. **Never rewrite an entire file** when only a few lines change. Make surgical, minimal edits.
2. **Preserve exact indentation** — this project uses **4-space indentation** everywhere (Python). Never mix tabs and spaces.
3. **Keep all existing imports** unless explicitly asked to remove one. Don't silently drop imports.
4. **Don't reorder functions/methods** — add new code at the logical position (end of class, next to related code) without shuffling what's already there.
5. **Don't rename existing variables, functions, or parameters** unless explicitly asked. Other files depend on those names.
6. **Preserve blank lines and comments** — don't collapse formatting or strip comments.
7. **One concern per edit** — if asked to change multiple things, make each change independently. Don't combine unrelated changes in one edit block.
8. **Always show the full function** when editing a function body — don't truncate with `...` or `# existing code`. But do NOT rewrite the full file.
9. **Never duplicate code** — check if a function/import already exists before adding it again.
10. **Test mentally** — before finalizing, mentally trace the change to make sure it doesn't break call sites.

---

## Architecture Overview

TARS is an autonomous macOS agent that receives tasks via iMessage (or CLI/dashboard), plans with LLMs (multi-provider: Gemini, Groq, Claude), and executes using macOS system tools. The architecture is a **think → act loop**:

```
User (iMessage/CLI/Dashboard)
  → tars.py (orchestrator, main loop)
    → brain/planner.py (LLM streaming + tool-use loop)
      → executor.py (routes tool calls to handlers)
        → hands/* (terminal, files, browser, mac control)
        → voice/* (iMessage read/write via AppleScript + chat.db)
        → memory/* (context, preferences, history in flat files)
      → agents/* (sub-agents: browser, coder, file, research, system)
  → server.py (dashboard: HTTP :8420, WebSocket :8421)
  → utils/event_bus.py (singleton EventBus — every action emits events for the dashboard)
```

---

## Key Patterns (MUST follow)

### Tool Return Format
Every tool handler in `hands/*`, `voice/*`, `memory/*` returns this exact shape:
```python
# Success
{"success": True, "content": "Human-readable result"}

# Failure
{"success": False, "error": True, "content": "Human-readable error"}
```
**Never deviate.** No extra keys, no different shapes. The executor and planner depend on this.

### Event Bus
```python
from utils.event_bus import event_bus   # singleton, import this exact line
event_bus.emit("event_type", {"key": "value"})
```
- It's thread-safe. Use it from any thread.
- Every user-visible action MUST emit an event so the dashboard stays live.
- Common event types: `"thinking"`, `"tool_use"`, `"tool_result"`, `"imessage_sent"`, `"imessage_received"`, `"agent_step"`, `"environment_scan"`, `"verification"`.

### Import Conventions
```python
# 1. stdlib
import os, sys, json, time, subprocess, threading
from datetime import datetime

# 2. third-party (minimal — yaml, websockets, requests)
import yaml

# 3. project modules — ALWAYS absolute imports from repo root
from brain.planner import TARSBrain
from utils.event_bus import event_bus
from hands.terminal import run_terminal
from agents.browser_agent import BrowserAgent
```
- **No relative imports** (`from . import ...` is not used).
- **No duplicate imports** — check before adding.

### Error Handling Pattern
```python
def my_tool_handler(params):
    try:
        # do work
        return {"success": True, "content": "result"}
    except SpecificError as e:
        return {"success": False, "error": True, "content": f"Specific issue: {e}"}
    except Exception as e:
        return {"success": False, "error": True, "content": f"Error: {e}"}
```
- Handlers should **never raise** — always return the dict.
- The executor has a top-level catch as safety net, but don't rely on it.

### Config Access
Config is a dict loaded from `config.yaml` once at startup. Accessed via:
```python
config["section"]["key"]                              # required keys
config.get("optional_section", {}).get("key", default) # optional keys
```
- Multi-provider LLM: `brain_llm`, `agent_llm`, `fallback_llm` — each has `provider`, `api_key`, `model`.
- Env var overrides exist for secrets (see `tars.py`).

### Async vs Sync
- **Everything is synchronous** except `server.py` (WebSocket server uses `asyncio`/`websockets`).
- Tool handlers, LLM loops, agent execution — all sync.
- Threading is used for concurrency (not asyncio). Event bus bridges sync→async for the dashboard.

---

## Multi-Provider LLM Architecture

The project supports multiple LLM providers via `brain/llm_client.py`:
- `brain_llm` — orchestrator/planner (Gemini 2.5 Flash)
- `agent_llm` — sub-agents (Groq / Llama)
- `fallback_llm` — auto-switch when brain_llm is rate-limited

**When editing LLM code**: the client abstracts provider differences. Don't add provider-specific logic outside `llm_client.py`.

---

## Error Tracker + Fix Registry (`memory/error_tracker.py`)

The error tracker is a **persistent log of every error**, paired with known fixes. Over time, TARS auto-heals from past lessons:

```
Error happens → tracker.record_error()
  ├─ New error → log it, return None
  └─ Known error with fix → return the fix immediately (auto-heal)

Fix discovered → tracker.record_fix()
  └─ Next time same error → auto-applied
```

**Key APIs:**
```python
from memory.error_tracker import error_tracker  # singleton

# Record an error (returns fix info if known)
fix_info = error_tracker.record_error(error="...", context="tool_name", tool="...", agent="...")

# Record a fix for a known error
error_tracker.record_fix(error="...", fix="description", context="...", source="self_heal")

# Check if fix exists without recording
error_tracker.get_known_fix(error="...", context="...")

# Dashboard stats
error_tracker.get_stats()         # {unique_errors, auto_fixable, fix_rate, ...}
error_tracker.get_top_errors(10)   # Most frequent errors
error_tracker.get_unfixed_errors() # Recurring errors without fixes
error_tracker.get_error_report()   # Human-readable report
```

**Data flow:**
- `brain/planner.py` → records tool failures + checks for auto-fixes
- `executor.py` → records agent deployment failures
- `tars.py` → records task-level failures
- `brain/self_heal.py` → records fixes when self-healing succeeds

**Events emitted:** `"error_tracked"`, `"fix_recorded"`, `"auto_fix_available"`

**Persistence:** `memory/error_tracker.json` (max 200 entries, auto-pruned)

---

## Sub-Agent System (`agents/`)

- `base_agent.py` — base class. All agents inherit from it.
- Agents have their own tool sets defined in `agent_tools.py`.
- Agent `run()` returns a result dict — different shape from tool handlers (agents have their own output format).
- Agents are invoked from `executor.py` when a tool like `web_task` or `code_task` is called.

---

## File-by-File Quick Reference

| File | Purpose | Key exports |
|---|---|---|
| `tars.py` | Main entry, orchestrator loop | `TARS` class |
| `executor.py` | Routes tool calls → handlers | `ToolExecutor._dispatch()` |
| `brain/planner.py` | LLM conversation loop | `TARSBrain.think()` |
| `brain/tools.py` | Tool schemas (Anthropic format) | `TARS_TOOLS` list |
| `brain/prompts.py` | System prompt template | `TARS_SYSTEM_PROMPT` |
| `brain/llm_client.py` | Multi-provider LLM client | `LLMClient` |
| `hands/terminal.py` | Shell command execution | `run_terminal()` |
| `hands/browser.py` | AppleScript Chrome control | `Browser` class |
| `hands/file_manager.py` | File read/write/search | `read_file()`, `write_file()` |
| `hands/mac_control.py` | macOS GUI control | `mac_control()` |
| `voice/imessage_send.py` | Send iMessage via AppleScript | `send_imessage()` |
| `voice/imessage_read.py` | Poll `chat.db` for new msgs | `check_messages()` |
| `utils/event_bus.py` | Global event singleton | `event_bus` |
| `utils/safety.py` | Destructive command detection | `is_destructive()` |
| `server.py` | Dashboard HTTP + WebSocket | Ports 8420/8421 |
| `memory/memory_manager.py` | Flat-file memory ops | `MemoryManager` |
| `memory/error_tracker.py` | Error log + fix registry | `error_tracker` singleton |

---

## Adding a New Tool (Checklist)

1. **Schema** → Add dict to `brain/tools.py` → `TARS_TOOLS` list (Anthropic tool-use JSON schema)
2. **Handler** → Implement in `hands/`, `voice/`, or `memory/` (return `{"success": bool, "content": str}`)
3. **Dispatch** → Add `elif tool_name == "your_tool":` in `executor.py._dispatch()`
4. **Events** → Emit `event_bus` events for dashboard visibility
5. **Test** → Add smoke test in `test_systems.py`

---

## Running & Testing

```bash
cd tars && source venv/bin/activate
python tars.py                    # Start (waits for iMessage)
python tars.py "do something"     # Start with initial task
python test_systems.py            # Smoke test all modules
```

Dashboard: `http://localhost:8420` (HTTP) + WebSocket on `:8421`.

---

## Safety System

- Destructive commands (regex patterns in `utils/safety.py`) trigger iMessage confirmation before execution.
- Kill words (`STOP`, `HALT`, etc.) in `config.yaml` halt the agent.
- `safety.max_retries` (default 3): after N tool failures, LLM is told to ask the user for help.

---

## Dashboard (`dashboard/`)

- React + TypeScript + Vite + Tailwind
- State managed via WebSocket context (`context/ConnectionContext.tsx`)
- Components are in `dashboard/src/components/`
- **When editing dashboard**: preserve TypeScript types, don't use `any` unless absolutely necessary.

---

## 🚨 Known Pitfalls (Don't repeat these)

1. **browser.py functions return mixed types** — some return raw strings, some return the standard dict. The browser_agent handles this with `isinstance()` checks. Don't assume browser functions return the standard dict.
2. **`conversation_history` is a plain list** — mutated from the main thread. Don't access it from other threads without care.
3. **Agent `run()` vs tool handler return** — agents return their own shape (with `final_response`, etc.), NOT `{"success", "content"}`. The executor wraps it.
4. **AppleScript strings need escaping** — backslashes, quotes, and Unicode can break `osascript` calls. Always escape properly.
5. **`config.yaml` has API keys** — never print config to logs or dashboard events. It's in `.gitignore` but be careful.

---

## 📝 Lessons Learned (append here when something breaks)

<!-- Add entries like:
### YYYY-MM-DD — Short title
**Problem**: What went wrong
**Fix**: What the rule is now
-->

### 2026-02-16 — Copilot garbles inline edits
**Problem**: When making changes, Copilot sometimes rewrites entire files, drops imports, reorders code, or produces garbled partial edits.
**Fix**: Added § "Editing Rules" at the top. Copilot must make minimal surgical edits, preserve all imports, never reorder existing code, and never truncate with `...` placeholders.

### 2026-02-16 — Errors repeat without learning
**Problem**: TARS would hit the same error (e.g. missing 'command' param 11x, missing 'query' 18x) without ever learning from it. Self-heal existed but only proposed code changes — no persistent fix registry.
**Fix**: Created `memory/error_tracker.py` — a persistent error log with fix registry. Wired into planner, executor, tars.py, and self_heal.py. Now every error is recorded, and when a fix is found (via self-heal or manual), it's auto-applied next time the same error recurs. The fix rate is tracked in stats.

### 2026-02-17 — Agent text-only loop burns 40 steps
**Problem**: Groq Llama outputs tool calls as `<function>done{"summary":"..."}</function>` text instead of proper tool_use blocks. `base_agent.py` didn't parse these, so the agent looped 36+ times with the same text output, burning through all 40 max steps with no result.
**Fix**: Added `_parse_function_tags()` to `base_agent.py` — regex-parses `<function>` tags from text and executes `done()`/`stuck()` immediately. Also added text-only loop detection: if the agent outputs identical text 3x in a row, force-stop and return the content as best-effort result.
