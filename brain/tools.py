"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Brain v4: Orchestrator Tool Definitions          ║
╠══════════════════════════════════════════════════════════════╣
║  The brain doesn't do tasks itself — it DEPLOYS AGENTS.      ║
║  These tools let the brain deploy agents, communicate with   ║
║  the user, manage memory, scan the environment, verify       ║
║  results, search the web, and checkpoint progress.           ║
║                                                              ║
║  Phase 1-6 tools for full autonomy.                          ║
║  + web_search (Phase 6: Live Knowledge Access)               ║
║  + deploy_dev_agent v2 (VS Code Agent Mode orchestrator)     ║
╚══════════════════════════════════════════════════════════════╝
"""

TARS_TOOLS = [
    # ═══════════════════════════════════════
    #  Core Thinking Tool (Phase 1)
    # ═══════════════════════════════════════
    {
        "name": "think",
        "description": "MANDATORY before every deployment. Reason through the problem step by step.\n\nUse this to:\n- Classify the message (Type A-E)\n- Decompose tasks into subtasks\n- Identify which agent handles each subtask\n- Define success criteria for each step\n- Anticipate failures and plan recovery\n- Evaluate results after each tool call\n\nYour thinking is logged internally but NEVER shown to Abdullah.\n\nExample: think('Type C task. Need to create Outlook account. Steps: 1) deploy browser_agent to navigate signup.live.com and fill form, 2) verify with browser check for inbox URL, 3) save credentials to memory, 4) report via iMessage. Risk: CAPTCHA may appear — browser agent has solve_captcha. Backup: if Outlook fails, try ProtonMail.')",
        "input_schema": {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Your detailed reasoning. Include: message classification, task decomposition, agent selection, success criteria, risk assessment, backup plans."}
            },
            "required": ["thought"]
        }
    },

    # ═══════════════════════════════════════
    #  Environmental Awareness (Phase 2)
    # ═══════════════════════════════════════
    {
        "name": "scan_environment",
        "description": "Scan the Mac environment BEFORE acting. Returns: running apps, Chrome tabs, current directory, network status, system info, deployment budget.\n\nUse at the START of every Type C task to:\n- See what's already running (Chrome open? Which tabs?)\n- Check internet connectivity\n- Know deployment budget remaining\n- Avoid blind deployments\n\nFor Type A/B messages, skip this — just respond.\n\nExample: scan_environment(['apps', 'tabs']) — quick check of what's open\nExample: scan_environment(['all']) — full system scan before complex task",
        "input_schema": {
            "type": "object",
            "properties": {
                "checks": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["apps", "tabs", "files", "network", "system", "all"]},
                    "description": "What to scan. 'all' for full scan, or pick specific: 'apps' (running apps), 'tabs' (Chrome tabs), 'files' (current dir), 'network' (internet check), 'system' (disk/battery/uptime).",
                    "default": ["all"]
                }
            },
            "required": []
        }
    },

    # ═══════════════════════════════════════
    #  Verification Loop (Phase 3)
    # ═══════════════════════════════════════
    {
        "name": "verify_result",
        "description": "MANDATORY after every agent deployment. Verify that the work ACTUALLY succeeded — don't trust agent claims.\n\nModes:\n- 'browser': Checks current Chrome page URL + visible text. Use after browser agent tasks.\n- 'command': Runs a shell command and checks output. Use after coder/system agent tasks.\n- 'file': Checks if a file/directory exists + preview. Use after file agent tasks.\n- 'process': Checks if a process is running. Use after launching apps/servers.\n\nExamples:\n  verify_result('browser', 'outlook', 'outlook.live.com') — checks if browser shows Outlook inbox\n  verify_result('command', 'cat ~/project/index.html', '<html>') — checks file was created correctly\n  verify_result('file', '~/project/package.json') — checks file exists\n  verify_result('process', 'node') — checks if Node.js is running\n\nIf verification FAILS, use the Smart Recovery Ladder — don't blindly retry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["browser", "command", "file", "process"],
                    "description": "Verification mode."
                },
                "check": {
                    "type": "string",
                    "description": "What to check. browser: expected URL/text. command: shell command to run. file: file path. process: process name."
                },
                "expected": {
                    "type": "string",
                    "description": "Expected substring in the result. If found → VERIFIED. If not → FAILED. Omit for info-only checks."
                }
            },
            "required": ["type", "check"]
        }
    },

    # ═══════════════════════════════════════
    #  Checkpoint & Progress (Phase 8)
    # ═══════════════════════════════════════
    {
        "name": "checkpoint",
        "description": "Save progress so you can resume if interrupted. Use before risky operations.\n\nExample: checkpoint('Created outlook account, password saved', 'Still need to verify inbox access and save to memory')",
        "input_schema": {
            "type": "object",
            "properties": {
                "completed": {"type": "string", "description": "What's done so far (specific: URLs, files, accounts, etc.)"},
                "remaining": {"type": "string", "description": "What still needs to be done"}
            },
            "required": ["completed", "remaining"]
        }
    },

    # ═══════════════════════════════════════
    #  Agent Deployment
    # ═══════════════════════════════════════
    {
        "name": "deploy_browser_agent",
        "description": "Deploy Browser Agent for web tasks. Controls Chrome PHYSICALLY (real mouse + keyboard clicks).\n\nCapabilities: Navigate URLs, fill forms, click buttons, sign up for accounts, read page content, handle CAPTCHAs, manage tabs.\n\nCRITICAL — Give COMPLETE instructions:\n✅ GOOD: 'Go to https://signup.live.com. Fill the email field (#floatingLabelInput4) with tarsbot2026@outlook.com. Click Next. Wait 3 seconds. Fill the password field with MyP@ss2026!. Click Next. Fill first name with Tars, last name with Bot. Click Next. Select birth month January, day 1, year 1999. Click Next. If CAPTCHA appears, call solve_captcha(), wait 3s, look again. When you see the Outlook inbox or a welcome page, call done.'\n❌ BAD: 'Create an Outlook account'\n\nThe agent has NO context about your plan. Spell out EVERY step, EVERY value, EVERY click target.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "COMPLETE browser task with ALL details: exact URLs, exact values to type, exact buttons to click, CAPTCHA instructions, and what success looks like."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_coder_agent",
        "description": "Deploy Coder Agent for software development.\n\nCapabilities: Write code (any language), build projects, debug, run tests, git ops, install packages, deploy.\n\nIMPORTANT: Always use ABSOLUTE paths in the task (e.g. /Users/abdullah/Desktop/script.py). Never use ~ (tilde). Use the EXACT filename requested.\n\nGive COMPLETE task:\n✅ GOOD: 'Create a Python script at /Users/abdullah/Desktop/fibonacci.py that prints the first 20 Fibonacci numbers. Run it with python3 to verify it works.'\n❌ BAD: 'Write me a Fibonacci script'\n❌ BAD: 'Create ~/Desktop/script.py' — NEVER use ~, use full /Users/abdullah/Desktop/script.py",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "COMPLETE coding task: requirements, tech stack, file paths, expected behavior, test criteria."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_system_agent",
        "description": "Deploy System Agent for macOS automation.\n\nCapabilities: Open/control apps, type text, press keyboard shortcuts, click at coordinates, take screenshots, run AppleScript, manage system settings.\n\nCANNOT browse the web — never send web tasks to this agent.\n\n✅ GOOD: 'Open System Settings, navigate to Wi-Fi, and check if connected. Take a screenshot to confirm.'\n❌ BAD: 'Go to google.com' — use browser agent for that",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "System task: app names, specific actions, keyboard shortcuts, expected result."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_research_agent",
        "description": "Deploy Research Agent v2.0 — world-class deep researcher and analyst.\n\n15+ specialized tools: multi_search (2-5 queries at once), deep_read (scroll through 50K+ char pages), extract_table (pricing/specs/schedules), compare (side-by-side tables), follow_links (discover subpages), calculate (math/percentages), convert (unit conversion), date_calc (date arithmetic), research_plan (track progress), score_sources (credibility scoring).\n\nSource credibility scoring: 3-tier domain authority system (80+ trusted domains). Notes with confidence levels (high/medium/low) and source attribution.\n\nREAD-ONLY — cannot interact with websites (no clicking, no form filling, no signups).\nUse for finding info BEFORE deploying other agents.\n\n✅ GOOD: 'Compare MacBook Pro vs Dell XPS vs ThinkPad X1. Research specs, prices, reviews from 3+ sources. Build comparison table.'\n✅ GOOD: 'Research best noise-cancelling headphones under $300. Check reviews from RTINGS, WireCutter, Reddit.'\n❌ BAD: 'Find me flights' — use search_flights tool directly, NOT research agent\n❌ BAD: 'Book me a flight' — use browser agent for booking",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Research question: what info to find, how many sources to check, what details needed. Be specific about deliverables."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_file_agent",
        "description": "Deploy File Agent for file management.\n\nCapabilities: Find, organize, move, copy, delete, compress, extract files and directories.\n\n✅ GOOD: 'Organize ~/Desktop — move all .pdf files to ~/Documents/PDFs, all .png/.jpg to ~/Pictures/Screenshots, delete any .tmp files. Show a tree of ~/Desktop when done.'\n❌ BAD: 'Clean up my files'",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "File task: paths, patterns, where to move things, what to clean up."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_dev_agent",
        "description": "Deploy Dev Agent v2 — orchestrates VS Code Agent Mode (Claude Opus 4) for autonomous software development.\n\nThe Dev Agent opens VS Code, activates Agent Mode (Copilot with Claude Opus 4), and gives it a complete task. It monitors progress autonomously — no human interaction needed.\n\nCapabilities: Full-stack development, multi-file edits, refactoring, debugging, testing, git operations, package management, project scaffolding. Has access to the entire codebase, terminal, and VS Code APIs.\n\nCRITICAL — Give COMPLETE context:\n- Full project path (absolute)\n- What to build/change (specific requirements)\n- Tech stack preferences\n- File locations if known\n- Expected behavior / test criteria\n\n✅ GOOD: 'In /Users/abdullah/projects/myapp, add a dark mode toggle to src/components/Settings.tsx. Use Tailwind CSS. Save preference to localStorage. Toggle should be in the header nav.'\n✅ GOOD: 'Refactor the auth module in /Users/abdullah/api to use JWT. Update routes in src/routes/auth.ts, src/routes/users.ts, and src/middleware/auth.ts. Add tests.'\n❌ BAD: 'Write a hello world script' — too simple, use run_quick_command\n❌ BAD: 'Fix a bug' — be specific about what and where\n\n⚠️ Sessions take 5-30 min. Only deploy for substantial development work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "COMPLETE development task: project path, what to build/change, tech preferences, constraints, expected behavior."}
            },
            "required": ["task"]
        }
    },

    # ═══════════════════════════════════════
    #  Communication
    # ═══════════════════════════════════════
    {
        "name": "send_imessage",
        "description": "Send an iMessage to Abdullah. This is your ONLY output channel — Abdullah NEVER sees your text responses.\n\n**ONE message per task. Short and sweet.**\n\nRules:\n- Send ONE message with the result. Don't send 'On it' then the result separately.\n- Keep it under 2-3 sentences. If detail is needed, email it and say 'Emailed you the details.'\n- No progress updates ('Working on it...', 'Almost done...'). The dashboard handles that.\n- For tasks >60s, you may send ONE brief ack, then ONE result. Max 2 messages ever.\n- Conversational tone, contractions (it's, don't, won't). You're TARS, not a corporate bot.\n- NEVER narrate actions ('I am now deploying...'). Just do it and report.\n\nGood:\n- \"Toronto → London, $487 direct on AC. Want me to book?\"\n- \"Done ✅ — report's on your Desktop.\"\n- \"Found the bug — API key expired. Already rotated it.\"\n- \"Emailed you the full research breakdown.\"\n\nBad:\n- \"On it. Searching for flights now.\" (don't ack short tasks)\n- \"I have successfully completed the task.\"\n- Long multi-paragraph messages with bullet lists (email those instead)",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The iMessage to send. Write naturally — like texting a friend who's also a genius."}
            },
            "required": ["message"]
        }
    },
    {
        "name": "wait_for_reply",
        "description": "Wait for Abdullah to reply via iMessage. Blocks until reply received or timeout.\n\nUse after asking a question. Default timeout is 5 minutes.\n\nExample: After sending 'Which email provider — Outlook or Gmail?', call wait_for_reply(300) to wait up to 5 min.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout": {"type": "integer", "description": "Max seconds to wait (default 300)", "default": 300}
            },
            "required": []
        }
    },

    # ═══════════════════════════════════════
    #  Memory (Phase 9)
    # ═══════════════════════════════════════
    {
        "name": "save_memory",
        "description": "Save information to persistent memory for future sessions.\n\nCategories:\n- 'credential': Login info (ALWAYS save after account creation)\n- 'preference': User likes/dislikes\n- 'project': Project details, tech stack, repo URLs\n- 'learned': Patterns that work/don't work (e.g., 'Outlook signup needs #floatingLabelInput4 for email')\n- 'context': Current state/task info\n- 'note': General notes\n\nExamples:\n  save_memory('credential', 'outlook_tarsbot', 'tarsbot2026@outlook.com / MyP@ss2026!')\n  save_memory('learned', 'outlook_signup_flow', 'Email field is #floatingLabelInput4, password step comes after clicking Next')\n  save_memory('preference', 'code_style', 'Abdullah prefers Python, dark themes, minimal comments')",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["preference", "project", "context", "note", "credential", "learned"]},
                "key": {"type": "string", "description": "Short label (e.g., 'outlook_account', 'project_tars_repo')"},
                "value": {"type": "string", "description": "Information to remember (include all relevant details)"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "recall_memory",
        "description": "Search persistent memory for information from past sessions.\n\nSearches: context, preferences, projects, credentials, learned patterns, and action history.\n\nALWAYS check memory before:\n- Starting a task that might relate to previous work\n- Creating accounts (might already exist)\n- Working on a project (might have saved context)\n\nExamples:\n  recall_memory('outlook account')\n  recall_memory('project tars')\n  recall_memory('flight preferences')",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for (keywords, not full sentences)"}
            },
            "required": ["query"]
        }
    },

    # ═══════════════════════════════════════
    #  Quick Tools
    # ═══════════════════════════════════════
    {
        "name": "run_quick_command",
        "description": "Run a quick shell command for fast checks. Returns stdout + stderr.\n\nGood for: ls, cat, grep, curl, ping, which, brew list, pip list, git status, df -h, uptime, whoami, date\nNOT for: complex multi-step operations (use deploy_coder_agent), long-running processes, interactive commands.\n\nExamples:\n  run_quick_command('curl -s wttr.in/Tampa?format=3') — weather\n  run_quick_command('git -C ~/projects/tars status') — git status\n  run_quick_command('pip list | grep flask') — check if flask installed",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run (non-interactive, short-running)"},
                "timeout": {"type": "integer", "description": "Timeout seconds (default 30)", "default": 30}
            },
            "required": ["command"]
        }
    },
    {
        "name": "web_search",
        "description": "Quick Google search — returns top results with titles and snippets. Use this for fast factual lookups WITHOUT deploying an agent.\n\nPhase 6: Live Knowledge Access. The Brain can search the web directly when it needs current info to reason about a task.\n\nGood for: current events, quick facts, product prices, API docs, error messages, 'what is X', definitions, recent news.\nNOT for: deep research (use deploy_research_agent), multi-page analysis, comparison shopping.\n\nExamples:\n  web_search('current weather Tampa FL')\n  web_search('Python asyncio gather timeout')\n  web_search('latest iPhone 17 release date')\n  web_search('litellm rate limit error 429 fix')",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Google search query — be specific for better results"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "quick_read_file",
        "description": "Read a file's contents quickly. Returns full text (truncated at 50KB).\n\nUse absolute paths. For large files, use run_quick_command with head/tail/grep instead.\n\nExamples:\n  quick_read_file('/Users/abdullah/Desktop/notes.txt')\n  quick_read_file('/Users/abdullah/Desktop/untitled folder/tars/config.yaml')",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path to read"}
            },
            "required": ["path"]
        }
    },

    # ═══════════════════════════════════════
    #  Direct Mac Control (brain-level, no agent needed)
    # ═══════════════════════════════════════
    {
        "name": "mac_mail",
        "description": "Email via Mac's Mail.app (logged in as tarsitgroup@outlook.com). Actions:\n- 'send' → send email (with optional file attachment)\n- 'unread' → get unread count\n- 'inbox' → read latest emails\n- 'read' → read specific email by index\n- 'search' → search by keyword\n- 'verify_sent' → check Sent folder to confirm an email was actually delivered\n\nExamples:\n  mac_mail('send', to='bob@gmail.com', subject='Report', body='See attached.', attachment_path='/Users/abdullah/Documents/TARS_Reports/report.xlsx')\n  mac_mail('verify_sent', subject='Report') — confirms it landed in Sent\n  mac_mail('inbox', count=10)",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["unread", "inbox", "read", "search", "send", "verify_sent"]},
                "count": {"type": "integer", "description": "Emails to read (inbox action)", "default": 5},
                "index": {"type": "integer", "description": "Email index (read action)"},
                "keyword": {"type": "string", "description": "Search keyword (search action)"},
                "to": {"type": "string", "description": "Recipient (send action)"},
                "subject": {"type": "string", "description": "Subject (send/verify_sent action)"},
                "body": {"type": "string", "description": "Body (send action)"},
                "attachment_path": {"type": "string", "description": "Absolute path to file to attach (send action, optional)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "mac_notes",
        "description": "Quick Apple Notes operations.\n- 'list' → list all notes\n- 'read' → read a note by name\n- 'create' → create a note\n- 'search' → search notes\n\nExamples:\n  mac_notes('list')\n  mac_notes('create', title='Shopping List', body='Milk, eggs, bread')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read", "create", "search"]},
                "note_name": {"type": "string", "description": "Note name (read action)"},
                "title": {"type": "string", "description": "Title (create action)"},
                "body": {"type": "string", "description": "Body (create action)"},
                "query": {"type": "string", "description": "Search query (search action)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "mac_calendar",
        "description": "Quick calendar operations.\n- 'events' → upcoming events\n- 'create' → create event\n\nExamples:\n  mac_calendar('events', days=14)\n  mac_calendar('create', title='Meeting', start='March 1, 2026 2:00 PM', end='March 1, 2026 3:00 PM')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["events", "create"]},
                "days": {"type": "integer", "description": "Days ahead (events)", "default": 7},
                "calendar_name": {"type": "string", "description": "Calendar name"},
                "title": {"type": "string", "description": "Event title (create)"},
                "start": {"type": "string", "description": "Start date (create)"},
                "end": {"type": "string", "description": "End date (create)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "mac_reminders",
        "description": "Quick reminders operations.\n- 'list' → list reminders\n- 'create' → create reminder\n- 'complete' → complete reminder\n\nExamples:\n  mac_reminders('list')\n  mac_reminders('create', title='Buy milk', due='March 1, 2026')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "create", "complete"]},
                "list_name": {"type": "string", "description": "Reminders list name"},
                "title": {"type": "string", "description": "Reminder title"},
                "due": {"type": "string", "description": "Due date (optional)"},
                "notes": {"type": "string", "description": "Notes (optional)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "mac_system",
        "description": "Quick system controls — no agent needed.\n- 'volume' → set volume (0-100)\n- 'dark_mode' → toggle dark mode\n- 'notify' → send notification\n- 'clipboard' → read clipboard\n- 'screenshot' → take screenshot\n- 'environment' → full Mac snapshot\n- 'battery' → battery status\n- 'spotlight' → search files\n\nExamples:\n  mac_system('volume', value=50)\n  mac_system('notify', message='Task complete!')\n  mac_system('environment')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["volume", "dark_mode", "notify", "clipboard", "screenshot", "environment", "battery", "spotlight"]},
                "value": {"type": "integer", "description": "Volume level (volume action)"},
                "enabled": {"type": "boolean", "description": "Enable/disable (dark_mode action)"},
                "message": {"type": "string", "description": "Message (notify action)"},
                "query": {"type": "string", "description": "Search query (spotlight action)"}
            },
            "required": ["action"]
        }
    },

    # ═══════════════════════════════════════
    #  Smart Services (API-First, no browser UI)
    # ═══════════════════════════════════════
    {
        "name": "search_flights",
        "description": "Search for flights using the v5.0 Structured DOM engine. Navigates Google Flights via CDP, extracts structured flight data from the DOM (not text scraping), with automatic retry and 15-minute search cache.\n\nReturns structured data per flight: airline, price, times, duration, stops, layover airport + duration, fare class, baggage info, booking link, value score (0-100).\nAlso returns: Google price insight ('prices are low/high'), return flight details, auto-suggested tracker target, and analytics.\n\nExamples:\n  search_flights(origin='Tampa', destination='New York', depart_date='March 15')\n  search_flights(origin='LAX', destination='London', depart_date='June 1', return_date='June 15', stops='nonstop', cabin='business')\n\nAccepts city names OR airport codes (250+ airports). Dates can be natural language ('March 15') or ISO ('2026-03-15').\n\n⚠️ For flight + Excel + Email in one call, use `search_flights_report` instead.\nFor cheapest date across a month, use `find_cheapest_dates`.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Departure city or airport code (e.g., 'Tampa', 'TPA', 'Los Angeles', 'LAX')"},
                "destination": {"type": "string", "description": "Arrival city or airport code (e.g., 'New York', 'JFK', 'London', 'LHR')"},
                "depart_date": {"type": "string", "description": "Departure date: 'March 15', 'Mar 15 2026', '2026-03-15', '3/15'"},
                "return_date": {"type": "string", "description": "Return date (optional, omit for one-way)"},
                "passengers": {"type": "integer", "description": "Number of passengers (default 1)", "default": 1},
                "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "description": "Trip type", "default": "round_trip"},
                "cabin": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "description": "Cabin class", "default": "economy"},
                "stops": {"type": "string", "enum": ["any", "nonstop", "1stop"], "description": "Stop filter", "default": "any"},
                "max_price": {"type": "integer", "description": "Maximum price in USD (0 = no limit)", "default": 0}
            },
            "required": ["origin", "destination", "depart_date"]
        }
    },
    {
        "name": "search_flights_report",
        "description": "Search flights + generate Excel report + email — ALL IN ONE CALL (v5.0 engine).\n\nDoes everything: searches Google Flights with structured DOM parser, builds a professional Excel spreadsheet (with Layover, Fare Class, Baggage, Value Score columns + Insights sheet), and emails a premium HTML report with price insight banner, price chart, return flight details, and smart suggestions.\n\nUSE THIS when:\n- User asks for flights with a SPECIFIC departure date (and optional return date)\n- User wants a 'full report', 'detailed report', Excel, or email\n- User gives a ROUND-TRIP with two dates like 'Sept 20 - Oct 15' (depart_date=Sept 20, return_date=Oct 15)\n- User says 'search flights from X to Y on DATE' and wants results emailed\n\n⚠️ If user gives TWO dates (e.g., 'Sept 20 - Oct 15'), that means round-trip: depart_date is the FIRST date, return_date is the SECOND date. Do NOT use find_cheapest_dates for this.\n\nResults now include: layover details, fare class, baggage info, Google price insight, return flight details, auto tracker suggestion, 250+ airports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Departure city or airport code"},
                "destination": {"type": "string", "description": "Arrival city or airport code"},
                "depart_date": {"type": "string", "description": "Departure date (natural language or ISO)"},
                "return_date": {"type": "string", "description": "Return date (optional)"},
                "passengers": {"type": "integer", "description": "Number of passengers", "default": 1},
                "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "default": "round_trip"},
                "cabin": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "default": "economy"},
                "stops": {"type": "string", "enum": ["any", "nonstop", "1stop"], "default": "any"},
                "max_price": {"type": "integer", "description": "Max price filter (0 = no limit)", "default": 0},
                "email_to": {"type": "string", "description": "Email address to send the report to. Leave empty to skip email."}
            },
            "required": ["origin", "destination", "depart_date"]
        }
    },
    {
        "name": "find_cheapest_dates",
        "description": "Find the cheapest day to fly within a date range — ONLY when user explicitly asks 'when is cheapest' or 'best day to fly'.\n\nv5.0: Now uses parallel scanning (2x faster) and search cache. Scans multiple dates across a range (e.g., all of March), searches each date on Google Flights, ranks by price, and produces a date-vs-price comparison Excel.\n\nUSE THIS ONLY when the user asks:\n- 'When is the cheapest time to fly to NYC?'\n- 'Find the best day to fly SLC to LA in March'\n- 'Cheapest dates for spring break flights'\n\n⚠️ DO NOT USE THIS when user gives specific travel dates like 'Sept 20 - Oct 15'. That's a round-trip → use search_flights_report instead with depart_date + return_date.\n\nExamples:\n  find_cheapest_dates(origin='SLC', destination='LAX', start_date='March 1', end_date='March 31')\n  find_cheapest_dates(origin='Tampa', destination='NYC', start_date='June 1', end_date='June 30', email_to='user@gmail.com')\n\n⚠️ This searches MULTIPLE dates (10-15 searches) so it takes 1-2 minutes. Always warn the user it will take a moment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Departure city or airport code"},
                "destination": {"type": "string", "description": "Arrival city or airport code"},
                "start_date": {"type": "string", "description": "Start of date range (e.g., 'March 1', '2026-03-01')"},
                "end_date": {"type": "string", "description": "End of date range (e.g., 'March 31'). Defaults to +30 days if omitted."},
                "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "default": "one_way"},
                "cabin": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "default": "economy"},
                "stops": {"type": "string", "enum": ["any", "nonstop", "1stop"], "default": "any"},
                "email_to": {"type": "string", "description": "Email address to send the report to. Leave empty to skip email."}
            },
            "required": ["origin", "destination", "start_date"]
        }
    },

    # ═══════════════════════════════════════
    #  Flight Price Tracker
    # ═══════════════════════════════════════
    {
        "name": "track_flight_price",
        "description": "Set up a persistent price tracker for a flight route. TARS will monitor the price on Google Flights at regular intervals and send a beautiful HTML email alert + iMessage when the price drops to or below your target.\n\nUSE THIS when user says:\n- 'Track flights from SLC to NYC and alert me when it drops below $200'\n- 'Monitor TPA to LAX price, notify me under $150'\n- 'Set a price alert for my trip'\n\nThe tracker runs in the background and checks every N hours (default 6).\nAlerts include a direct booking link.\n\nExamples:\n  track_flight_price(origin='SLC', destination='NYC', depart_date='March 15', target_price=200)\n  track_flight_price(origin='TPA', destination='LAX', depart_date='June 1', return_date='June 10', target_price=150, email_to='user@gmail.com')",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Departure city or airport code"},
                "destination": {"type": "string", "description": "Arrival city or airport code"},
                "depart_date": {"type": "string", "description": "Departure date"},
                "target_price": {"type": "integer", "description": "Target price in USD — alert triggers when price ≤ this"},
                "return_date": {"type": "string", "description": "Return date (optional)"},
                "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "default": "round_trip"},
                "cabin": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "default": "economy"},
                "stops": {"type": "string", "enum": ["any", "nonstop", "1stop"], "default": "any"},
                "email_to": {"type": "string", "description": "Email for alerts (default: tarsitgroup@outlook.com)", "default": "tarsitgroup@outlook.com"},
                "check_interval_hours": {"type": "integer", "description": "Hours between price checks (default 6)", "default": 6}
            },
            "required": ["origin", "destination", "depart_date", "target_price"]
        }
    },
    {
        "name": "get_tracked_flights",
        "description": "List all active flight price trackers with their current status, last price, and price history trend.\n\nUSE THIS when user says:\n- 'What flights am I tracking?'\n- 'Show my price trackers'\n- 'Status of my flight alerts'",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "stop_tracking",
        "description": "Stop/deactivate a specific flight price tracker by its ID.\n\nUSE THIS when user says:\n- 'Stop tracking SLC-NYC-20260315'\n- 'Cancel my flight tracker'\n- 'Remove the price alert for...'",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracker_id": {"type": "string", "description": "The tracker ID to stop (e.g., 'SLC-NYC-20260315')"}
            },
            "required": ["tracker_id"]
        }
    },
    {
        "name": "book_flight",
        "description": "Book a flight directly! Opens the airline's booking page (or Google Flights) in Chrome via browser automation, selects the flight, and navigates to the checkout page for the user to complete payment.\n\nUSE THIS when user says:\n- 'Book the cheapest flight from SLC to NYC on March 15'\n- 'Book that Delta flight'\n- 'I want to book the $234 United flight'\n- 'Book a flight from Tampa to Tokyo'\n\nWorkflow:\n1. If an airline is specified, opens their direct booking page with route pre-filled\n2. Otherwise, searches Google Flights, selects the best flight, and clicks through to booking\n3. Chrome opens to the airline checkout page\n4. User completes passenger details + payment in the browser\n5. TARS notifies via iMessage that the booking page is ready\n\n⚠️ TARS handles search + navigation. The user completes the final payment step.\n\nExamples:\n  book_flight(origin='SLC', destination='NYC', depart_date='March 15', return_date='March 22')\n  book_flight(origin='Tampa', destination='Tokyo', depart_date='June 1', airline='Delta', cabin='business')\n  book_flight(origin='LAX', destination='London', depart_date='Sept 20', return_date='Oct 5', passengers=2)",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Departure city name or airport code (e.g., 'Tampa', 'SLC', 'LAX')"},
                "destination": {"type": "string", "description": "Arrival city name or airport code (e.g., 'New York', 'NRT', 'LHR')"},
                "depart_date": {"type": "string", "description": "Departure date in any format: 'March 15', '2026-03-15', 'next Friday'"},
                "return_date": {"type": "string", "description": "Return date (optional for one-way trips)"},
                "airline": {"type": "string", "description": "Preferred airline name (optional — picks cheapest if not specified)"},
                "trip_type": {"type": "string", "enum": ["round_trip", "one_way"], "description": "Trip type (default: round_trip)", "default": "round_trip"},
                "cabin": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "description": "Cabin class (default: economy)", "default": "economy"},
                "passengers": {"type": "integer", "description": "Number of passengers (default: 1)", "default": 1},
                "flight_number": {"type": "integer", "description": "Index of the flight to book from search results. 0 = cheapest (default)", "default": 0}
            },
            "required": ["origin", "destination", "depart_date"]
        }
    },

    # ═══════════════════════════════════════
    #  Report Generation
    # ═══════════════════════════════════════
    {
        "name": "generate_report",
        "description": "Generate professional reports (Excel, PDF, or CSV). Reports are saved to ~/Documents/TARS_Reports/ and can be attached to emails.\n\nFormats:\n- 'excel' → .xlsx with styled headers, alternating rows, auto-width, optional summary\n- 'pdf' → .pdf with title, sections, optional table\n- 'csv' → simple .csv data export\n\nWorkflow: generate_report → get the path → mac_mail send with attachment_path\n\nExamples:\n  generate_report('excel', 'Sales Report', headers=['Product','Revenue'], rows=[['Widget','$1000'],['Gadget','$2500']])\n  generate_report('pdf', 'Project Summary', sections=[{'heading':'Overview','body':'Project completed on time.'}])\n  generate_report('excel', 'Analysis', headers=['Metric','Value'], rows=[...], summary={'Total':'$5000','Average':'$2500'})",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["excel", "pdf", "csv"], "description": "Report format"},
                "title": {"type": "string", "description": "Report title"},
                "headers": {"type": "array", "items": {"type": "string"}, "description": "Column headers (excel/csv/pdf table)"},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Data rows — each row is a list of strings"},
                "sections": {"type": "array", "items": {"type": "object"}, "description": "PDF sections: [{heading: str, body: str}, ...]"},
                "summary": {"type": "object", "description": "Key-value summary pairs shown below table (excel only)"},
                "filename": {"type": "string", "description": "Custom filename (auto-generated if omitted)"}
            },
            "required": ["format", "title"]
        }
    },

    # ═══════════════════════════════════════
    #  Self-Healing (v5)
    # ═══════════════════════════════════════
    {
        "name": "propose_self_heal",
        "description": (
            "Propose a self-healing modification to TARS's own code. "
            "Use this when you notice a recurring failure, missing capability, "
            "or something that could be improved in your own behavior.\n\n"
            "This will ask Abdullah for permission via iMessage. If approved, "
            "the dev agent will be deployed to modify TARS's codebase.\n\n"
            "Examples:\n"
            "- 'I keep failing at X because I don't have a tool for Y'\n"
            "- 'My browser agent crashes when pages have CAPTCHAs'\n"
            "- 'I need better error handling for timeout scenarios'\n\n"
            "IMPORTANT: Only propose changes you're confident will help. "
            "Abdullah has to approve, so be specific about WHAT and WHY."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What capability to add or what to fix. Be specific.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this change is needed. What failure triggered this?",
                },
            },
            "required": ["description", "reason"],
        },
    },
]


# ═══════════════════════════════════════════════════
#  DYNAMIC TOOL PRUNING (Phase 22)
# ═══════════════════════════════════════════════════

# Core tools always included regardless of intent
_CORE_TOOLS = {
    "think", "send_imessage", "wait_for_reply", "recall_memory",
    "save_memory", "scan_environment", "checkpoint", "propose_self_heal",
}

# Domain-specific tool groups
_DOMAIN_TOOLS = {
    "coding": {"run_command", "run_quick_command", "write_file", "quick_read_file",
               "code_task", "file_task", "verify_result"},
    "web": {"web_search", "web_task", "browse_url", "browse_page"},
    "files": {"write_file", "quick_read_file", "file_task", "verify_result",
              "run_quick_command"},
    "system": {"run_command", "run_quick_command", "system_task",
               "scan_environment", "mac_control"},
    "communication": {"send_imessage", "wait_for_reply", "send_email"},
    "research": {"web_search", "web_task", "browse_url", "browse_page",
                 "research_task", "quick_read_file"},
    "report": {"generate_report", "write_file", "quick_read_file"},
}

# Build a name→tool lookup once
_TOOL_BY_NAME = {t["name"]: t for t in TARS_TOOLS}


def get_tools_for_intent(intent) -> list:
    """
    Return a filtered subset of TARS_TOOLS based on the classified intent.

    For CONVERSATION intents, returns only core tools (saves tokens).
    For TASK intents, uses domain hints to select relevant tool groups.
    Falls back to full tool set if no pruning applies.
    """
    if intent is None:
        return TARS_TOOLS

    intent_type = intent.type if hasattr(intent, "type") else str(intent)

    # Conversations only need core tools
    if intent_type == "CONVERSATION":
        return [t for t in TARS_TOOLS if t["name"] in _CORE_TOOLS]

    # For tasks, build a set of relevant tool names
    if intent_type == "TASK":
        needed = set(_CORE_TOOLS)

        domain_hints = getattr(intent, "domain_hints", [])
        if domain_hints:
            for hint in domain_hints:
                hint_lower = hint.lower()
                for domain, tools in _DOMAIN_TOOLS.items():
                    if domain in hint_lower or hint_lower in domain:
                        needed.update(tools)

        # If domain hints gave us a good set, use it
        if len(needed) > len(_CORE_TOOLS):
            # Always include verify_result for tasks
            needed.add("verify_result")
            filtered = [t for t in TARS_TOOLS if t["name"] in needed]
            # Minimum 10 tools to avoid over-pruning
            if len(filtered) >= 10:
                return filtered

    # Default: return all tools
    return TARS_TOOLS
