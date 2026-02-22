# TARS — Copilot Instructions


Dont use unline commands in terminal. it will get garbled. 


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
- Common event types: `"thinking"`, `"tool_use"`, `"tool_result"`, `"imessage_sent"`, `"imessage_received"`, `"agent_step"`, `"environment_scan"`, `"verification"`, `"email_sent"`, `"email_received"`, `"email_rule_triggered"`, `"email_batch_action"`, `"email_scheduled_sent"`, `"email_stats"`, `"email_snoozed"`, `"email_resurfaced"`, `"email_digest"`, `"email_ooo_set"`, `"email_ooo_replied"`, `"email_ooo_expired"`, `"email_ooo_cancelled"`, `"email_followup_overdue"`, `"email_auto_digest"`, `"email_clean_sweep"`, `"email_auto_triage"`, `"email_unsubscribed"`, `"email_vip_detected"`, `"inbox_zero_progress"`, `"email_security_scan"`, `"phishing_detected"`, `"suspicious_link_found"`, `"sender_blocked"`, `"sender_trusted"`, `"action_item_extracted"`, `"meeting_extracted"`, `"reminder_created"`, `"calendar_event_created"`, `"action_completed"`, `"workflow_created"`, `"workflow_triggered"`, `"workflow_completed"`, `"email_composed"`, `"email_rewritten"`, `"email_proofread"`, `"email_delegated"`, `"delegation_completed"`, `"delegation_nudged"`, `"search_index_built"`, `"email_search"`, `"conversation_recalled"`, `"email_sentiment_analyzed"`, `"email_sentiment_alert"`, `"smart_folder_created"`, `"smart_folder_updated"`, `"smart_folder_deleted"`, `"thread_summarized"`, `"thread_decisions_extracted"`, `"forward_summary_prepared"`, `"label_added"`, `"newsletters_detected"`, `"auto_response_created"`, `"signature_created"`, `"alias_added"`, `"emails_exported"`, `"template_created"`, `"template_used"`, `"draft_saved"`, `"draft_updated"`, `"mail_folder_created"`, `"mail_folder_renamed"`, `"mail_folder_deleted"`, `"email_moved_to_folder"`, `"email_tracked"`, `"email_untracked"`, `"email_tracking_report"`, `"batch_archived"`, `"batch_replied"`, `"email_to_calendar"`, `"calendar_synced"`, `"email_dashboard"`, `"weekly_report"`, `"monthly_report"`, `"productivity_scored"`, `"email_trends"`.

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
| `hands/email.py` | Unified email backend (Mail.app + SMTP) | `send_email()`, `read_inbox()`, `inbox_monitor`, `add_email_rule()`, `summarize_inbox()`, `categorize_inbox()`, `get_email_thread()`, `schedule_email()`, `batch_mark_read()`, `send_quick_reply()`, `suggest_replies()`, `get_email_stats()`, `add_contact()`, `list_contacts()`, `search_contacts()`, `auto_learn_contacts()`, `snooze_email()`, `list_snoozed()`, `cancel_snooze()`, `priority_inbox()`, `get_sender_profile()`, `generate_daily_digest()`, `set_ooo()`, `cancel_ooo()`, `get_ooo_status()`, `get_email_analytics()`, `get_email_health()`, `clean_sweep()`, `auto_triage()`, `inbox_zero_status()`, `smart_unsubscribe()`, `build_attachment_index()`, `search_attachments()`, `attachment_summary()`, `list_saved_attachments()`, `score_relationships()`, `auto_detect_vips()`, `get_relationship_report()`, `communication_graph()`, `decay_stale_contacts()`, `scan_email_security()`, `check_sender_trust()`, `scan_links()`, `get_security_report()`, `add_trusted_sender()`, `add_blocked_sender()`, `list_trusted_senders()`, `list_blocked_senders()`, `extract_action_items()`, `extract_meeting_details()`, `scan_inbox_actions()`, `create_reminder_from_email()`, `create_calendar_event()`, `list_extracted_actions()`, `complete_action()`, `get_action_summary()`, `create_workflow()`, `list_workflows()`, `get_workflow()`, `delete_workflow()`, `toggle_workflow()`, `run_workflow_manual()`, `get_workflow_templates()`, `create_workflow_from_template()`, `get_workflow_history()`, `smart_compose()`, `rewrite_email()`, `adjust_tone()`, `suggest_subject_lines()`, `proofread_email()`, `compose_reply_draft()`, `delegate_email()`, `list_delegations()`, `update_delegation()`, `complete_delegation()`, `cancel_delegation()`, `delegation_dashboard()`, `nudge_delegation()`, `contextual_search()`, `build_search_index()`, `conversation_recall()`, `search_by_date_range()`, `find_related_emails()`, `analyze_sentiment()`, `batch_sentiment()`, `sender_sentiment()`, `sentiment_alerts()`, `sentiment_report()`, `create_smart_folder()`, `list_smart_folders()`, `get_smart_folder()`, `update_smart_folder()`, `delete_smart_folder()`, `pin_smart_folder()`, `summarize_thread()`, `thread_decisions()`, `thread_participants()`, `thread_timeline()`, `prepare_forward_summary()`, `add_label()`, `remove_label()`, `list_labels()`, `get_labeled_emails()`, `bulk_label()`, `detect_newsletters()`, `newsletter_digest()`, `newsletter_stats()`, `newsletter_preferences()`, `apply_newsletter_preferences()`, `create_auto_response()`, `list_auto_responses()`, `update_auto_response()`, `delete_auto_response()`, `toggle_auto_response()`, `auto_response_history()`, `create_signature()`, `list_signatures()`, `update_signature()`, `delete_signature()`, `set_default_signature()`, `get_signature()`, `add_alias()`, `list_aliases()`, `update_alias()`, `delete_alias()`, `set_default_alias()`, `export_emails()`, `export_thread()`, `backup_mailbox()`, `list_backups()`, `search_exports()`, `get_export_stats()`, `create_template()`, `list_templates()`, `get_template()`, `update_template()`, `delete_template()`, `use_template()`, `save_draft()`, `list_drafts()`, `get_draft()`, `update_draft()`, `delete_draft()`, `create_mail_folder()`, `list_mail_folders()`, `rename_mail_folder()`, `delete_mail_folder()`, `move_to_folder()`, `get_folder_stats()`, `track_email()`, `list_tracked_emails()`, `get_tracking_status()`, `tracking_report()`, `untrack_email()`, `batch_archive()`, `batch_reply()`, `batch_label()`, `email_to_event()`, `list_email_events()`, `upcoming_from_email()`, `meeting_conflicts()`, `sync_email_calendar()`, `email_dashboard()`, `weekly_report()`, `monthly_report()`, `productivity_score()`, `email_trends()` |
| `agents/email_agent.py` | Dedicated email agent (199 tools) | `EmailAgent` class |
| `voice/imessage_send.py` | Send iMessage via AppleScript | `send_imessage()`, `send_file()` |
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

### 2026-02-17 — Groq Llama ignores tools with tool_choice=auto
**Problem**: With `tool_choice="auto"` and 26 tools, Groq Llama 3.3 70B returns text-only responses from training knowledge instead of making tool_use calls. The agent enters a text-only loop, never calling web_search/wiki_search/stock_quote etc. With just 2 tools, `auto` works fine — the issue is specific to large tool sets.
**Fix**: Always set `tool_choice="required"` in `base_agent.py`. Since `done()` and `stuck()` are in the tool list, the model can still finish by calling those tools. This forces every step to produce a tool_use block. Result: zero text-only responses, every step produces a real tool call.

### 2026-02-17 — Brain web_search uses DuckDuckGo (CAPTCHAs)
**Problem**: The brain's `_web_search()` in `executor.py` only used DuckDuckGo HTTP scraping, which frequently returns CAPTCHAs ("Unfortunately, bots use DuckDuc..."). The research agent had Serper API but the brain's direct web_search tool didn't.
**Fix**: Added Serper API as primary search in `executor.py._web_search()`, falling back to DuckDuckGo only if Serper is unavailable. Reads `config["research"]["serper_api_key"]`.

### 2026-02-17 — Agent tool-call loop (stock_quote→finance_search→web_search ×20)
**Problem**: With `tool_choice="required"`, the research agent must call a tool every step. When given a multi-entity task (e.g., 4 stocks), the agent would query all 4 in parallel, then re-query the same 4 again, endlessly cycling `stock_quote → finance_search → web_search` without ever calling `done()`. Context window fills with repetitive data, burying the original task. The agent burned 72+ tool calls in 18 steps before being killed.
**Fix**: Added two mechanisms in `base_agent.py`:
1. **Tool-call loop detection**: Tracks the sorted tool names per step. If the same 3-step pattern repeats 3x, injects a "WRAP UP — call done() NOW" nudge. If still looping after the nudge, force-stops and returns best-effort data.
2. **Context window trimming**: After 20+ messages, old tool result contents are truncated to 500 chars with "[truncated]" marker. Keeps the first message (task) and last 6 messages (recent context) intact, so the model can still see the original instruction.

### 2026-02-17 — Brain burns all deployments on one area, never finishes
**Problem**: For a complex multi-domain task (stock data + news + academic papers + Excel report + email), the brain deployed 6 research agents — one per company — spending the entire deployment budget on stock data alone. It never reached academic papers, report generation, or email delivery. Then it fell into a `web_search` loop trying to re-fetch data its agents already returned, triggering metacognition force-break. Root causes: (1) prompt said "ONCE per sub-topic" and brain treated each company as a sub-topic, (2) no task planning or budget allocation guidance, (3) `max_deploys=8` hardcoded in prompt but executor allows 15, (4) no forward-progress nudge when deployments are being wasted.
**Fix**: Four changes:
1. **Task Planning Discipline** in `brain/prompts.py` — brain MUST call `think` before deploying to plan task areas, allocate deployment budget, and batch related items. Includes concrete example plan.
2. **Research Orchestration Pattern rewrite** — explicitly says "one deployment per DOMAIN, not per entity", "BATCH entities into single deployments", "accept partial data and move on", and "NEVER spend more than 50% of budget on data gathering."
3. **`max_deploys` synced to executor** — planner.py now reads `self.tool_executor.max_deployments` instead of hardcoded 8. Default in prompts.py updated to 15.
4. **Budget awareness nudge** in `executor.py` — after every successful deployment, if the brain has used 3+ agents of the same type or >50% of budget, a nudge is appended: "MOVE FORWARD to the next phase."

### 2026-02-17 — generate_report fails when brain passes nested data dict
**Problem**: After successfully gathering all research data (4 deployments covering stocks, news, papers), the brain called `generate_report` with a nested `data` dict (e.g. `{"stock_data": {"NVDA": {"price": "$182"}}, "news": [...]}`) instead of flat `headers`/`rows` arrays. It failed 3 times with `KeyError: 'format'`, `KeyError: 'title'`, and `"Excel needs 'headers' and 'rows'"` — then gave up and returned an apology instead of the report.
**Fix**: Three changes:
1. **Auto-convert data dicts** in `executor.py._generate_report()` — when brain passes `data={...}` without `headers`/`rows`, the new `_data_dict_to_tabular()` method auto-flattens dict-of-dicts into tabular rows and lists into summary/sections.
2. **Param name normalization** — executor now accepts both `format` and `report_format`, defaults title to "TARS Report" if missing.
3. **Tool schema updated** in `brain/tools.py` — added `data` property to the schema with description and examples showing how nested dicts are auto-converted. Clear instructions that either `data` OR `headers`+`rows` can be used.

### 2026-02-17 — Agent burns 84 dispatches, returns "Done." with no data
**Problem**: Research agent batched 12 tool_use blocks per step (stock_quote×4 + finance_search×4 + web_search×4). Loop detection only checked step-level patterns (3 steps repeating 3x), so it took 9 steps × 12 dispatches = 84 tool calls before triggering. Then when the wrap-up nudge told the agent to call done(), context trimming had wiped all the gathered data, so the agent returned just "Done." — losing everything. Brain had to re-deploy.
**Fix**: Four changes in `base_agent.py`:
1. **Parallel tool cap** (`_MAX_PARALLEL_TOOLS=6`): Only execute first 6 tool_use blocks per step, skip the rest with "SKIPPED" message. Prevents 12-16 call batches.
2. **Dispatch budget** (`_MAX_DISPATCHES=40`, hard limit `55`): After 40 dispatches, inject wrap-up nudge regardless of step patterns. After 55, force-stop and return collected data.
3. **Preserve notes during context trimming**: Note tool results (containing the agent's findings) are no longer truncated during context window trimming. Only raw search results are truncated.
4. **`_collect_notes_for_summary()`**: New method that extracts all saved notes from the agent (using `_get_notes()` or `_notes` dict) when force-stopping, so the brain gets the actual data even when the agent failed to compile a summary.

### 2026-02-17 — mac_mail reports success but email stays as draft (Exchange + attachments)
**Problem**: `mail_send()` in `hands/mac_control.py` used `visible:false` and called `send msg` immediately. AppleScript returned success, but with Exchange/IMAP accounts, attachment emails take ~12 seconds to actually leave the Outbox. Without waiting, the message appeared as a draft/stuck in Outbox. Plain text emails (no attachment) sent fine.
**Fix**: Three changes in `mail_send()`:
1. **`visible:true` for attachment emails** — Mail.app needs the compose window rendered to fully process attachments before sending. Plain text emails still use `visible:false`.
2. **`delay 3` before `send`** — gives Mail.app time to load and encode the attachment.
3. **Outbox polling after `send`** — instead of a flat delay, polls outbox count every 2 seconds for up to 30 seconds. Returns success only when outbox is empty (message actually sent). Returns `"outbox_stuck"` error if still in outbox after 30s, with guidance to check Mail.app > Outbox manually.
Total send time with attachment: ~15 seconds (3s pre-send + 12s Exchange processing).
### 2026-02-17 — Instagram signup fails 10+ times — browser agent stuck on form
**Problem**: TARS attempted Instagram account creation ~10 times across 3 tasks and failed every time. Five root causes:
1. Brain used fake `@example.com` emails — Instagram silently rejects them (form stays, no visible error).
2. Instagram's signup is multi-page (form → Sign up → birthday → CAPTCHA → verification code), but the brain/agent tried to fill everything on one page.
3. Birthday dropdowns use `aria-label` attributes, not `<label>` elements. The `act_select_option()` function in `browser.py` only searched by `<label>` text and `name`/`id`, missing `aria-label` and `title`.
4. The agent called `stuck()` after 10s waiting for "Welcome to Instagram" — but the birthday page comes next, not the home page.
5. No Instagram playbook existed in `account_manager.py`, so the brain had no structured flow to follow.
**Fix**: Five changes:
1. **Instagram playbook** added to `hands/account_manager.py` — detailed multi-step signup/login flow with notes about multi-page handling, email requirements, and birthday dropdown behavior.
2. **`act_select_option()` in `browser.py`** — now searches `aria-label`, `title`, and first-option placeholder text in addition to `<label>`, `name`, `id`.
3. **`getLabel()` in `look` output** — now checks `title` attribute so dropdowns are labeled correctly in page inspection.
4. **Brain prompts updated** — DOMAIN_BROWSER now warns against `@example.com`, explains multi-page flows, and tells brain to deploy one page per browser agent.
5. **Fixes recorded in error tracker** — auto-heals if same error recurs.

### 2026-02-17 — Browser agent stuck 8/8 deployments: 5 fundamental CDP + agent bugs
**Problem**: After Instagram playbook/prompt fixes, browser agent still failed 8/8 deployments across 2 tasks. All stuck on "page still shows the sign-up form." Five root causes found:
1. `Input.insertText` dumps entire string instantly — React/Instagram detects as bot (no individual keyDown/keyUp events).
2. `act_click()` had zero post-click verification — didn't check URL changes, DOM mutations, or error messages. Just returned "Clicked X at (x,y)".
3. Parallel tool cap (6) skipped `look` when it was the 7th tool in a batch `[type×4, click, wait, look]`. Verification step lost every time.
4. Form validation errors existed on page but weren't surfaced in `look` output — hidden below LINKS section.
5. Browser agent system prompt allowed `stuck()` after 6 steps, didn't teach multi-page forms, didn't distinguish "form errors" from "truly stuck."
6. `_cdp_click_at()` clicked at exact center pixel with fixed 20ms timing — trivially detectable as bot.
**Fix**: Seven changes across 4 files:
1. **Human-like typing** (`_cdp_type_human()` in `browser.py`) — char-by-char keyDown/keyUp with 30-120ms random delays, 8% chance of longer pauses. `act_fill()` rewritten to use it + Cmd+A clear + post-fill verification.
2. **Click verification** (`act_click()` in `browser.py`) — captures URL before click, checks for navigation and inline errors (`[role=alert]`, `.error`, `.validation-error`, `[data-testid*=error]`, `span[class*=coreSpriteInputError]`) after click. Returns enriched result.
3. **Form error detection** (`act_inspect_page()` in `browser.py`) — `🚨 FORM ERRORS:` section added right after FIELDS with `❌` prefix per error.
4. **Click humanization** (`_cdp_click_at()` in `browser.py`) — random ±2px jitter on coordinates, variable timing (20-80ms mousemove, 40-120ms hold) instead of fixed 20ms.
5. **Smart parallel cap** (`base_agent.py`) — pre-scans tool blocks to detect verification tools (look/read/url/screenshot) at end of batch, reserves 1 slot so they always execute.
6. **Browser system prompts rewritten** (both `agents/browser_agent.py` and `hands/browser_agent.py`) — multi-page form handling, "FORM ERRORS ≠ STUCK", minimum 10+ steps before stuck, one-field-at-a-time workflow.
7. **`solve_captcha`** added to `agents/browser_agent.py` tool list and dispatch.

### 2026-02-17 — Browser agent can't read OTP, new deployments reset confirmation page
**Problem**: Browser agent successfully navigated Instagram signup through form + birthday + CAPTCHA and reached the "Enter confirmation code" page. But: (1) the browser agent had NO tool to read email/OTP — it could only interact with Chrome, (2) brain deployed a NEW browser agent for the OTP step which called `goto(signup_url)` as step 1, resetting the page and losing the confirmation code page entirely, (3) `manage_account('read_otp')` existed as a brain-level tool but browser agents couldn't call it, (4) `done()` guard treated "confirmation" as a success signal even when it was a "confirmation code" page (still pending), (5) Instagram playbook told agent to "tell the brain you need a verification code" but the agent had no way to communicate this back.
**Fix**: Six changes across 4 files:
1. **`read_otp` tool added to both browser agents** (`agents/browser_agent.py` + `hands/browser_agent.py`) — imports `read_verification_code` from `hands/account_manager.py`, adds tool definition with `from_sender`/`subject_contains`/`timeout` params, adds dispatch routing that returns the code directly or the email content.
2. **Browser agent prompts updated** — both `BROWSER_SYSTEM_PROMPT` and `BROWSER_AGENT_PROMPT` now include: `read_otp` in tools list, "Step 6b: Verification/Confirmation Code Pages" with step-by-step instructions, and warnings to NEVER navigate away from the code page.
3. **Brain prompt `DOMAIN_BROWSER` rewritten** — removed `manage_account('read_otp')` from the signup workflow (browser agent handles it now), changed multi-page strategy from "one page per deployment" to "agent handles ALL pages in ONE deployment", added explicit warnings: "NEVER deploy a second browser agent that navigates to the signup URL after progress" and "browser agent has read_otp() built-in."
4. **Instagram playbook updated** (`hands/account_manager.py`) — STEP 3 now says "Call read_otp(subject_contains='Instagram')" instead of "tell the brain you need a verification code."
5. **`done()` guard hardened** — removed "confirmation" and "verify your email" from success_signals (a confirmation code page ≠ success). Added `otp_signals` list (`"confirmation code"`, `"enter the code"`, `"verification code"`, `"we sent a code"`, `"check your email"`) with a new rejection path that tells the agent to call `read_otp` instead.
6. **All files compile-verified clean.**

### 2026-02-20 — iMessage conversation overhaul: rate limit, splitting, attachments, corrections, ack fast-path
**Problem**: Multiple conversation-killing issues: (1) 30s rate limit made every reply feel slow. (2) Long messages truncated with "... (truncated)" instead of splitting. (3) No way to send files/images via iMessage. (4) `_apply_correction()` had a `pass` — "actually Tokyo" appended "(correction: tokyo)" instead of replacing. (5) "ok"/"👍" burned a full LLM call through brain.process(). (6) Brain still sent "Gimme a sec" ack messages even though dashboard shows progress.
**Fix**: Seven changes across 6 files:
1. **Rate limit: 30s → 1.5s** (`voice/imessage_send.py`) — hardcoded `_MIN_SEND_GAP = 1.5` instead of config-driven 30s. Non-blocking (only sleeps the delta).
2. **Smart message splitting** (`voice/imessage_send.py`) — new `_split_message()` splits at paragraph → sentence → hard boundaries. Never truncates.
3. **File attachments** (`voice/imessage_send.py`) — new `send_file()` method uses `POSIX file` AppleScript to send images/PDFs/reports inline in iMessage.
4. **`send_imessage_file` tool** (`brain/tools.py`, `executor.py`, `brain/planner.py`) — full tool schema with `file_path` + `caption`, dispatch routing, added to DEPENDENT_TOOLS/_CORE_TOOLS/communication domain, sets `brain_sent_imessage` flag.
5. **Correction logic rebuilt** (`brain/message_parser.py`) — 4 strategies: (a) "X instead of Y" regex swap, (b) "not X, use Y" regex swap, (c) short correction → replace last content-word in previous, (d) full action verb → complete replacement. Also strips trailing "instead" and handles "use X instead" → just "X".
6. **Acknowledgment fast-path** (`tars.py`) — `_is_standalone_ack()` + check in `_on_batch_ready()`: if no active tasks, skip LLM entirely. If tasks active, don't double-queue (reader handles it via wait_for_reply).
7. **Communication rules hardened** (`brain/prompts.py`) — removed ALL ack guidance ("Gimme a sec", "On it"). Rule 1 now says "ZERO progress/ack messages". Rule 9 now mentions `send_imessage_file`. Rule 10 explicitly bans every form of pre-work message.

### 2026-02-20 — iMessage file attachments silently fail (iCloud CloudKit stuck)
**Problem**: `send_file()` in `voice/imessage_send.py` used AppleScript `send POSIX file` which always returned exit 0 (success), but files never arrived on the phone. Investigation via `~/Library/Messages/chat.db` revealed ALL attachments had `transfer_state=6` (failed) and `is_sent=0, is_delivered=0`, while text messages delivered fine (`is_sent=1, is_delivered=1`). Root cause: AppleScript's `send POSIX file` scripting bridge on macOS 26 uses a broken internal path that fails to upload via CloudKit, even though drag-and-drop/paste in the Messages UI works perfectly. Manual drag-and-drop confirmed working — same iCloud account, same file, delivered instantly.
**Fix**: Four changes in `voice/imessage_send.py`:
1. **Finder-paste pipeline** (`_send_file_via_paste()`) — new primary send method. Selects file in Finder, copies (Cmd+C), switches to Messages, pastes (Cmd+V — file appears as inline attachment), then presses Enter. This uses the same UI pipeline as drag-and-drop, bypassing the broken scripting bridge. Files now deliver with `transfer_state=5, is_sent=1, is_delivered=1`.
2. **Legacy AppleScript fallback** (`_send_file_via_applescript()`) — old `send POSIX file` method kept as fallback if paste fails (e.g., no GUI session).
3. **Delivery verification** (`_verify_file_delivery()`) — after send, polls `chat.db` for up to 8 seconds checking `transfer_state` on the latest outgoing attachment. Returns True if `state=5` (delivered), False if `state=6` (stuck/failed).
4. **Email fallback** (`_email_fallback()`) — when verification detects stuck attachment, imports `mail_send` from `hands/mac_control` and sends the file as an email attachment. Then sends a text iMessage telling the user the file was emailed instead.
**Key insight**: AppleScript `send POSIX file` and UI-initiated sends use completely different internal paths in Messages.app. The scripting bridge path is broken on macOS 26 but the UI path works fine.

### 2026-02-21 — Browser agent burns 40 steps exploring DoorDash dev portal, never acts
**Problem**: User asked "create a DoorDash developer portal account and get the API key." Brain deployed a **reconnaissance-only** task ("look for a Sign Up button, if not found describe options"). Agent spent 40 steps doing `look→scroll→look→scroll→read→click→scroll...` aimlessly. At step 38, agent correctly concluded in a text-only response "the page does not have a direct Sign Up button" — but `tool_choice=required` forced 2 more useless clicks. TARS was killed after 8.5 minutes with zero progress. Three root causes: (1) text-only conclusions weren't auto-converted to `done()`, wasting steps, (2) no detection of "observation-only loops" where agent scrolls/looks without ever clicking or typing, (3) the generic "You MUST use a tool now" nudge after text-only didn't mention `done()` as an option.
**Fix**: Three changes in `agents/base_agent.py`:
1. **Auto-done for text conclusions** — after text-only loop detection, if agent has done 8+ dispatches and the text contains conclusion signals ("does not have", "not possible", "unfortunately", "successfully", "in summary", etc.) and is ≥80 chars, auto-return it as a `done()` result. Prevents wasting 2+ steps after the agent already answered.
2. **Observation-only streak detection** — tracks consecutive browser steps where only observe tools (look/scroll/read/screenshot/url) are used with zero action tools (click/type/fill_form/goto). After 6 consecutive observe-only steps, injects a nudge: "TAKE ACTION, CONCLUDE, or TRY A DIFFERENT URL — do NOT keep scrolling the same page."
3. **Better text-only nudge message** — changed from "Call web_search, wiki_search..." (wrong for browser agents) to "If you have finished or determined it cannot be completed, call done(summary). Otherwise, call your next tool."

### 2026-02-21 — React form fill fails: CSS selectors with colons break querySelector
**Problem**: Browser agent navigated to DoorDash signup page correctly but could never fill any form fields. `act_fill()` always returned "ERROR: No visible field for: #fieldWrapper-:r1:". Root cause: React-generated IDs contain colons (e.g., `fieldWrapper-:r1:`, `fieldWrapper-:r2:`). `getSel()` used `CSS.escape()` which produces `#fieldWrapper-\:r1\:` with backslash escapes. LLMs strip the backslashes when passing selectors in JSON tool calls → `#fieldWrapper-:r1:` is invalid CSS (`:r1:` parsed as pseudo-class) → `querySelector()` fails → form never gets filled. Agent burned 24+ steps retrying the same broken selector.
**Fix**: Six changes across `hands/browser.py`:
1. **`getSel()` in `act_inspect_page()`** — for IDs containing special CSS chars (`:`, `.`, `[`, `]`, etc.), use `[id="..."]` attribute selector instead of `#CSS.escape(id)`. Attribute selectors handle special chars naturally without escaping. Regular IDs still use `#id`.
2. **`getSel()` in `act_full_page_scan()`** — same fix applied to the second `getSel()` instance.
3. **`_fix_selector()` helper** — new function that auto-converts broken `#` selectors (with special chars) to `[id="..."]` attribute selectors. Catches selectors the LLM already mangled.
4. **`act_fill()`** — calls `_fix_selector()` before querySelector.
5. **`_find_element_coords()`** — calls `_fix_selector()` before querySelector (used by `act_click()`).
6. **`act_select_option()`** — calls `_fix_selector()` before querySelector.
**Key insight**: Never use CSS.escape() for selectors that will pass through LLM tool calls — LLMs strip backslashes. Attribute selectors `[id="value"]` are LLM-safe.

### 2026-02-21 — Direct URL navigation triggers CAPTCHAs, blocks browser agent
**Problem**: Browser agent used `goto("https://identity.doordash.com/auth/user/signup?...")` to navigate directly to the signup page. DoorDash's anti-bot system immediately threw aggressive CAPTCHAs (Arkose/FunCAPTCHA), solved them but got redirected back with new CAPTCHAs in a loop. The agent burned 40 steps in `goto→look→solve_captcha→goto` cycles with zero progress. Root cause: Direct URL navigation to signup/login pages is a classic bot signal — no referrer header, no browsing history, just a raw URL hit. Real humans Google "DoorDash developer signup" and click through search results, which sets proper Referer headers and creates natural traffic patterns that bypass anti-bot systems.
**Fix**: Three prompt changes across 3 files:
1. **`brain/prompts.py` DOMAIN_BROWSER** — added "GOOGLE-FIRST NAVIGATION" section. Brain now instructs agents to "Search Google for 'X signup'" instead of providing direct URLs. Developer Portal example rewritten to use Google search. Explicit rule: "NEVER give the agent a direct signup/login URL."
2. **`agents/browser_agent.py` BROWSER_SYSTEM_PROMPT** — added full "GOOGLE-FIRST NAVIGATION" section after OODA loop. Explains why (Referer headers, organic traffic patterns, CAPTCHA bypass), shows examples of `goto("https://www.google.com/search?q=...")` → click result. Updated Account Creation workflow to start with Google search. Added "GOOGLE FIRST" as Critical Rule #2. Updated `goto` tool description to note it should only be used for Google search URLs.
3. **`hands/browser_agent.py` BROWSER_AGENT_PROMPT** — same Google-first section added, Account Creation updated, Rule 12 added.
**Key insight**: Direct URL navigation is a bot fingerprint. Searching Google and clicking results creates natural referrer chains that sites trust. This single change eliminates most CAPTCHA encounters.