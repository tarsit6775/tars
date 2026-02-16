# TARS — Copilot Instructions

## Architecture Overview

TARS is an autonomous macOS agent that receives tasks via iMessage (or CLI/dashboard), plans with Claude API, and executes using macOS system tools. The architecture is a **think → act loop**:

```
User (iMessage/CLI/Dashboard)
  → tars.py (orchestrator, main loop)
    → brain/planner.py (Claude API streaming + tool-use loop)
      → executor.py (routes tool calls to handlers)
        → hands/* (terminal, files, browser, mac control)
        → voice/* (iMessage read/write via AppleScript + chat.db)
        → memory/* (context, preferences, history in flat files)
  → server.py (dashboard: HTTP :8420, WebSocket :8421)
  → utils/event_bus.py (singleton EventBus — every action emits events for the dashboard)
```

## Key Patterns

- **Tool return format**: Every tool handler (`hands/*`, `voice/*`, `memory/*`) returns `{"success": bool, "content": str}` with optional `"error": True`. Never deviate from this shape.
- **Event bus is global**: `from utils.event_bus import event_bus` — it's a singleton. Use `event_bus.emit(event_type, data_dict)` to push real-time updates to the dashboard. Emit events for any new user-visible action.
- **Tool definitions live in `brain/tools.py`** as a list of dicts (`TARS_TOOLS`) matching Anthropic's tool-use JSON schema. When adding a tool: (1) add schema to `TARS_TOOLS`, (2) add handler function in the appropriate `hands/`/`voice/`/`memory/` module, (3) add dispatch case in `executor.py._dispatch()`.
- **Two-model strategy**: `heavy_model` (Sonnet) for complex planning, `fast_model` (Haiku) for simple tasks. Model selection is keyword-based in `brain/planner.py._choose_model()`.
- **Browser has two layers**: `web_search` (quick Google via AppleScript) and `web_task` (autonomous `BrowserAgent` sub-brain that controls Chrome step-by-step). Both use `hands/browser.py` low-level AppleScript+JS primitives — never call those directly from TARS.
- **macOS-only**: All system interaction uses `osascript` (AppleScript) and macOS-specific APIs (Messages.app, `screencapture`, `cliclick`). The iMessage reader polls `~/Library/Messages/chat.db` via SQLite.

## Running & Testing

```bash
cd tars && source venv/bin/activate
python tars.py                    # Start (waits for iMessage)
python tars.py "do something"     # Start with initial task
python test_systems.py            # Smoke test all modules
```

Dashboard: `http://localhost:8420` (HTTP) + WebSocket on `:8421`.

## Safety System

- Destructive commands (regex patterns in `utils/safety.py`) trigger iMessage confirmation before execution.
- Kill words (`STOP`, `HALT`, etc.) in `config.yaml` halt the agent via iMessage or dashboard.
- `config.yaml` → `safety.max_retries`: after N tool failures, Claude is told to ask the user for help.

## Config

All configuration is in `config.yaml` (API keys, phone number, model names, safety settings, memory paths). Loaded once at startup in `tars.py.load_config()` and passed by reference to all components.

## Conversation & Memory

- `brain/planner.py` manages `conversation_history` (list of message dicts), truncated to last 40 messages.
- Memory is flat files: `memory/context.md` (current task state), `memory/preferences.md` (learned user prefs), `memory/history.jsonl` (append-only action log), `memory/projects/` (per-project notes).
- Claude's system prompt is dynamically built in `planner.py._get_system_prompt()` using template variables from `brain/prompts.py.TARS_SYSTEM_PROMPT`.

## Adding a New Tool (Checklist)

1. Define the schema dict in `brain/tools.py` → `TARS_TOOLS` list
2. Implement the handler function (return `{"success": bool, "content": str}`)
3. Add `elif tool_name == "your_tool":` in `executor.py._dispatch()`
4. Emit relevant `event_bus` events for dashboard visibility
5. Add a smoke test line in `test_systems.py`
