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
        "description": "Deploy Research Agent v3.0 — PhD-level research intelligence with 25+ tools.\n\nAPI-FIRST architecture: Serper Google Search API, Wikipedia REST API, Yahoo Finance, Semantic Scholar, arXiv, Google News — all instant, zero CAPTCHAs. Chrome CDP browser as fallback only.\n\n🔍 Search: web_search (Google API), multi_search (2-5 queries), news_search (current events)\n📚 Knowledge: wiki_search (instant facts), wiki_article (full articles)\n📈 Finance: stock_quote (real-time prices/charts), finance_search (find tickers)\n🎓 Academic: academic_search (Semantic Scholar), arxiv_search (preprints)\n🌐 Read: browse (HTTP-first), deep_read (50K chars), extract, extract_table, follow_links\n✅ Verify: fact_check (cross-reference claims), cross_reference (independent corroboration)\n📝 Track: note (with citations), compare (tables), research_plan, score_sources\n📊 Calculate: calculate, convert, date_calc\n\nFact-checking: Every important claim is cross-referenced across 2+ sources. Citation system with [1] footnotes.\n\nREAD-ONLY — cannot interact with websites.\n\n✅ GOOD: 'Research NVIDIA stock performance vs AMD over the last year. Include current prices, P/E ratios, market cap, and analyst ratings.'\n✅ GOOD: 'What are the latest peer-reviewed studies on intermittent fasting? Check PubMed and Semantic Scholar.'\n✅ GOOD: 'Compare the top 3 electric SUVs under $50K — specs, range, reviews, total cost of ownership.'\n❌ BAD: 'Find flights' — use search_flights tool\n❌ BAD: 'Book a hotel' — use browser agent",
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
                "task": {"type": "string", "description": "COMPLETE development task: what to build/change, tech preferences, constraints, expected behavior."},
                "project_path": {"type": "string", "description": "Absolute path to the project root (e.g. /Users/abdullah/Downloads/tars-main). Auto-prepended to the task."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_screen_agent",
        "description": "Deploy Screen Agent — controls the Mac like a human using VISION. Sees the screen through screenshots, clicks by coordinates, types with keyboard.\n\nUnlike the Browser Agent (which uses DOM parsing + CSS selectors), the Screen Agent:\n• SEES the actual screen through screenshots sent to a vision LLM\n• Clicks at exact screen coordinates based on what it sees (like a human pointing)\n• Uses real macOS mouse + keyboard input (indistinguishable from human)\n• Works on ANY application — Chrome, Safari, Finder, System Settings, any app\n• Handles CAPTCHAs, iframes, Shadow DOM, and anti-bot detection naturally\n• No DOM parsing, no CSS selectors, no Chrome DevTools Protocol\n\n**When to use Screen Agent vs Browser Agent:**\n- Screen Agent: Sites with anti-bot detection (Instagram, Google), CAPTCHAs, complex dynamic UIs, non-browser apps, anything where DOM parsing fails\n- Browser Agent: Simple web forms, data extraction, basic navigation where speed matters\n\n**The Screen Agent is SLOWER but MORE RELIABLE** — it works exactly like a human sitting at the screen.\n\n✅ GOOD: 'Open Google Chrome, navigate to https://instagram.com/accounts/emailsignup. Fill in the signup form: email tarsitgroup@outlook.com, full name TARS Bot, username tarsbot2026, password MyStr0ng!Pass. Click Sign Up. Handle any CAPTCHAs, birthday forms, or verification steps. When you see the Instagram home feed, call done.'\n✅ GOOD: 'Open System Settings, go to Wi-Fi, and check if connected to a network. Take a screenshot to confirm.'\n✅ GOOD: 'Open Finder, navigate to ~/Desktop, select all .pdf files, and move them to ~/Documents/PDFs'\n❌ BAD: 'Browse instagram' — give COMPLETE instructions with exact values",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "COMPLETE visual task: what app to use, what to do step by step, exact values to type, what success looks like. The agent sees the screen and acts like a human."}
            },
            "required": ["task"]
        }
    },
    {
        "name": "deploy_email_agent",
        "description": "Deploy Email Agent — dedicated email management specialist with 30+ tools.\n\nCapabilities: read inbox, compose & send (plain text + HTML), reply, reply-all, forward, advanced search, CC/BCC, attachments, drafts, folder management, delete/archive/move, flag, mark read/unread, download attachments, email templates, follow-up tracking, contact lookup, AUTO-RULES (persistent rules that auto-apply to new emails), INBOX SUMMARIZATION (priority/regular/newsletter grouping), THREAD TRACKING (view full conversation threads).\n\nAccount: tarsitgroup@outlook.com (Mac Mail.app).\n\n✅ GOOD: 'Read my last 10 emails, find any from Amazon, and forward them to accounting@company.com with a note: Please process these invoices.'\n✅ GOOD: 'Create a rule to auto-archive all newsletters from noreply@*.com'\n✅ GOOD: 'Summarize my inbox and show me what needs attention'\n✅ GOOD: 'Show me the full thread for the email about Q4 Report'\n❌ BAD: 'Send an email' — specify recipient, subject, body\n❌ BAD: 'Check email' — specify what you want to know\n\nFor SIMPLE email ops (send one email, check unread), use `mac_mail` directly. Deploy email agent for COMPLEX multi-step email tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "COMPLETE email task: what to do, which emails, recipients, content, attachments, follow-up needs."}
            },
            "required": ["task"]
        }
    },

    # ═══════════════════════════════════════
    #  Communication
    # ═══════════════════════════════════════
    {
        "name": "send_imessage",
        "description": "Send an iMessage to Abdullah. This is your ONLY output channel — Abdullah NEVER sees your text responses.\n\n**Do ALL work silently, then send ONE message with the result. ZERO progress/ack messages.**\n\nRules:\n- NEVER send 'On it', 'Gimme a sec', 'Working on it', or ANY pre-work message. ONLY results.\n- Keep it under 2-3 sentences. For details → send_imessage_file or email.\n- Conversational tone, contractions (it's, don't, won't). You're TARS, not a corporate bot.\n- NEVER narrate actions ('I am now deploying...'). Just do it and report.\n- Long messages are auto-split into multiple iMessages — no need to worry about length.\n\nGood:\n- \"Toronto → London, $487 direct on AC. Want me to book?\"\n- \"Done ✅ — report's on your Desktop.\"\n- \"Found the bug — API key expired. Already rotated it.\"\n\nBad:\n- \"On it.\" or \"Gimme a sec\" or \"Looking into it...\" (NEVER send these)\n- \"I have successfully completed the task.\"\n- Long multi-paragraph messages with bullet lists (send as file instead)",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The iMessage to send. Write naturally — like texting a friend who's also a genius."}
            },
            "required": ["message"]
        }
    },
    {
        "name": "send_imessage_file",
        "description": "Send a file (image, PDF, report, spreadsheet, etc.) to Abdullah via iMessage.\n\nThe file appears inline in the chat — images show as previews, PDFs as attachments.\nOptionally include a brief caption that's sent as a text message right before the file.\n\nExamples:\n  send_imessage_file(file_path='/tmp/report.xlsx', caption='Here\'s the full breakdown')\n  send_imessage_file(file_path='~/Desktop/screenshot.png')\n  send_imessage_file(file_path='/tmp/analysis.pdf', caption='Full research attached')",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file to send. Supports ~/ expansion."},
                "caption": {"type": "string", "description": "Optional brief text message sent right before the file (e.g. 'Here\'s the report')."}
            },
            "required": ["file_path"]
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
    {
        "name": "list_memories",
        "description": "List all stored memories — shows everything TARS remembers, organized by category.\n\nCategories: preference, credential, learned, context, project, history, agent\n\nUse when the user asks:\n- 'What do you remember?'\n- 'Show me your memories'\n- 'What do you know about me?'\n- 'List your preferences/credentials/etc.'\n\nExamples:\n  list_memories() — show everything\n  list_memories(category='preference') — just preferences\n  list_memories(category='credential') — just saved logins",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["preference", "credential", "learned", "context", "project", "history", "agent"], "description": "Optional filter — only list memories from this category. If omitted, lists all."}
            },
            "required": []
        }
    },
    {
        "name": "delete_memory",
        "description": "Delete a specific memory or wipe an entire category.\n\nUse when the user asks:\n- 'Forget about X'\n- 'Delete my credentials'\n- 'Clear your memory'\n- 'Remove that preference'\n- 'Start fresh / wipe everything'\n\nExamples:\n  delete_memory(category='credential', key='instagram_account') — delete one credential\n  delete_memory(category='preference') — wipe ALL preferences\n  delete_memory(category='agent', key='browser') — reset browser agent learning\n  delete_memory(category='all') — FULL MEMORY WIPE\n\n⚠️ category='all' is destructive — confirm with user first!",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["preference", "credential", "learned", "context", "project", "history", "agent", "all"], "description": "Which memory category to delete from. 'all' wipes everything."},
                "key": {"type": "string", "description": "Specific entry to delete (e.g. 'instagram_account'). If omitted, deletes the entire category."}
            },
            "required": ["category"]
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
    #  Account Management (Keychain-backed)
    # ═══════════════════════════════════════
    {
        "name": "manage_account",
        "description": "Manage website accounts and credentials. Passwords are stored in macOS Keychain (encrypted).\n\nActions:\n- 'store'        → Save credentials after signup/login (password → Keychain)\n- 'lookup'       → Get credentials for a service (retrieves password from Keychain)\n- 'list'         → List all stored accounts (no passwords shown)\n- 'delete'       → Remove an account and its Keychain entry\n- 'get_playbook' → Get step-by-step login/signup instructions for a site\n- 'read_otp'     → Read verification/OTP code from Apple Mail\n- 'get_emails'   → Get available TARS email addresses for signups\n- 'generate_credentials' → Auto-generate secure password, username, and pick email for a service\n\nWorkflow for signups (PREFERRED — auto-generates everything):\n1. manage_account('generate_credentials', service='doordash') → get email, password, username, name, company\n2. deploy_browser_agent with ALL generated credentials in the task\n3. manage_account('store', service='doordash', username='tarsitgroup@outlook.com', password='<generated>')\n\nWorkflow for logins:\n1. manage_account('lookup', service='github') → get stored credentials\n2. deploy_browser_agent with credentials\n\nExamples:\n  manage_account('generate_credentials', service='stripe') → auto-generates everything\n  manage_account('store', service='github', username='tarsbot', password='MyP@ss!', email='tarsitgroup@outlook.com')\n  manage_account('lookup', service='reddit')\n  manage_account('get_playbook', service='outlook', flow='signup')\n  manage_account('read_otp', from_sender='noreply@github.com', subject_contains='verification')\n\nSupported playbooks: google, outlook, github, linkedin, twitter, reddit, amazon, instagram, doordash, stripe",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["store", "lookup", "list", "delete", "get_playbook", "read_otp", "get_emails", "generate_credentials", "generate_totp"]},
                "service": {"type": "string", "description": "Service name (e.g. 'github', 'reddit', 'outlook')"},
                "username": {"type": "string", "description": "Username or email for the account"},
                "password": {"type": "string", "description": "Password (stored encrypted in macOS Keychain)"},
                "email": {"type": "string", "description": "Email used for the account (defaults to username)"},
                "display_name": {"type": "string", "description": "Display name on the service"},
                "flow": {"type": "string", "enum": ["login", "signup"], "description": "Login or signup flow (for get_playbook)"},
                "from_sender": {"type": "string", "description": "Sender to look for (read_otp action)"},
                "subject_contains": {"type": "string", "description": "Subject keyword filter (read_otp action)"},
                "notes": {"type": "string", "description": "Extra notes about the account"},
                "has_2fa": {"type": "boolean", "description": "Whether this account has 2FA enabled"},
                "totp_secret": {"type": "string", "description": "TOTP secret (base32) for 2FA. Store with 'store' action, generate codes with 'generate_totp' action."},
                "recovery_email": {"type": "string", "description": "Recovery email for the account"},
                "status": {"type": "string", "description": "Account status", "default": "active"}
            },
            "required": ["action"]
        }
    },

    # ═══════════════════════════════════════
    #  Direct Mac Control (brain-level, no agent needed)
    # ═══════════════════════════════════════
    {
        "name": "mac_mail",
        "description": "Email via Mac's Mail.app (logged in as tarsitgroup@outlook.com). Quick email ops without deploying an agent.\n\nActions:\n- 'send' → send email (plain/HTML, CC/BCC, attachments)\n- 'unread' → get unread count\n- 'inbox' → read latest emails\n- 'read' → read specific email by index\n- 'search' → search by keyword/sender/subject\n- 'verify_sent' → check Sent folder to confirm delivery\n- 'reply' → reply to an email by index\n- 'forward' → forward an email to someone\n- 'delete' → delete an email (move to Trash)\n- 'archive' → archive an email\n- 'move' → move email to another folder\n- 'flag' → flag/unflag an email\n- 'mark_read' / 'mark_unread' → toggle read status\n- 'drafts' → list draft emails\n- 'list_folders' → list all mailboxes/folders\n- 'download_attachments' → download attachments from an email\n- 'summarize' → smart inbox summary (groups by priority/regular/newsletters, top senders, unread counts)\n- 'categorize' → auto-categorize inbox into priority/meeting/regular/newsletter/notification with confidence scores\n- 'thread' → get full conversation thread by subject (groups Re:/Fwd: emails chronologically)\n- 'run_rules' → manually apply auto-rules to existing inbox messages\n- 'quick_reply' → one-click reply using a template (acknowledge/confirm_meeting/decline_meeting/will_review/follow_up/thank_you/out_of_office/request_info)\n- 'suggest_replies' → analyze email and suggest appropriate quick reply types\n- 'list_quick_replies' → list all available quick reply templates\n- 'save_template' → save a reusable email template\n- 'list_templates' → list saved email templates\n- 'send_template' → send an email using a saved template with variable substitution\n- 'schedule' → schedule an email for later sending\n- 'list_scheduled' → list pending scheduled emails\n- 'cancel_scheduled' → cancel a scheduled email\n- 'batch_read' → mark multiple emails as read at once\n- 'batch_delete' → delete multiple emails at once\n- 'batch_move' → move multiple emails to a folder\n- 'batch_forward' → forward multiple emails to someone\n- 'add_rule' → create a persistent auto-rule for incoming emails\n- 'list_rules' → list all auto-rules\n- 'delete_rule' → delete an auto-rule\n- 'toggle_rule' → enable/disable an auto-rule\n- 'followup' → track an email for follow-up if no reply\n- 'check_followups' → check for overdue follow-ups\n- 'lookup_contact' → find email address by contact name (TARS + macOS Contacts)\n- 'add_contact' → add or update a contact in TARS contacts database\n- 'list_contacts' → list all TARS contacts (optional tag filter)\n- 'search_contacts' → search contacts by name/email/tag/notes\n- 'delete_contact' → delete a contact by ID or email\n- 'auto_learn_contacts' → scan inbox to auto-discover and save new contacts\n- 'snooze' → snooze an email (mark read now, resurface later: '2h', 'tomorrow', 'monday', ISO timestamp)\n- 'list_snoozed' → list all snoozed emails with resurface times\n- 'cancel_snooze' → cancel a snooze and resurface immediately\n- 'priority_inbox' → get inbox sorted by 0-100 priority score (urgency, sender reputation, recency)\n- 'sender_profile' → get sender statistics and relationship info\n- 'digest' → generate daily email briefing (stats, top priority, follow-ups, snoozed)\n- 'set_ooo' → set out-of-office auto-reply with date range (start_date, end_date, ooo_message, optional exceptions list)\n- 'cancel_ooo' → cancel active out-of-office\n- 'ooo_status' → check if OOO is active and get details\n- 'analytics' → comprehensive email analytics (volume, communicators, follow-ups, snooze, rules, health score; optional period: day/week/month)\n- 'email_health' → email health score 0-100 with contributing factors and grade\n- 'stats' → get email statistics for dashboard\n- 'clean_sweep' → bulk archive/delete old low-priority emails (older_than_days, categories, dry_run=true for preview)\n- 'auto_triage' → auto-categorize and sort latest emails into priority/action_needed/FYI/archive_candidate\n- 'inbox_zero_status' → current inbox zero progress (total count, trend, streak, category breakdown)\n- 'smart_unsubscribe' → detect newsletter/marketing and unsubscribe link for an email\n- 'build_attachment_index' → scan inbox and index all attachments (filename, size, sender, date)\n- 'search_attachments' → search attachment index by filename/sender/file_type\n- 'attachment_summary' → summary of attachment storage (total count, total size, by type)\n- 'list_saved_attachments' → list downloaded attachments in TARS storage (optional folder/file_type filter)\n- 'score_relationships' → score all contacts by relationship strength (frequency, recency, reciprocity)\n- 'detect_vips' → auto-detect VIP contacts based on relationship score threshold\n- 'relationship_report' → detailed relationship report for a specific contact\n- 'communication_graph' → top-N communication partners with stats\n- 'decay_contacts' → decay stale contacts inactive for N days\n\n🖊️ Smart Compose & Writing:\n- 'smart_compose' → AI-compose email from prompt (tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic, style: concise/detailed/bullet_points/executive_summary/action_oriented)\n- 'rewrite_email' → AI-rewrite existing email text in a new tone/style\n- 'adjust_tone' → change just the tone of existing email text\n- 'suggest_subject_lines' → generate subject line options from email body\n- 'proofread_email' → check grammar, spelling, clarity, professionalism\n- 'compose_reply_draft' → AI-draft a reply to an email by index with instructions\n\n📋 Email Delegation:\n- 'delegate_email' → delegate an email task to someone (delegate_to, instructions, deadline_hours)\n- 'list_delegations' → list all delegations (optional status filter: pending/in_progress/completed/cancelled)\n- 'update_delegation' → update delegation status/notes (delegation_id, status, notes)\n- 'complete_delegation' → mark delegation as completed with outcome\n- 'cancel_delegation' → cancel a delegation with reason\n- 'delegation_dashboard' → overview of all delegations with stats\n- 'nudge_delegation' → send a reminder for an overdue delegation\n\n🔍 Contextual Search & Memory:\n- 'contextual_search' → natural language email search (\"emails from John about the project last week\")\n- 'build_search_index' → rebuild the email search index\n- 'conversation_recall' → recall full conversation history with a contact\n- 'search_by_date_range' → search emails within a date range with optional keyword\n- 'find_related_emails' → find emails related to a given email by index\n\n🏷️ Labels & Tags:\n- 'add_label' → add a custom label/tag to an email by index\n- 'remove_label' → remove a label from an email\n- 'list_labels' → list all labels with email counts\n- 'get_labeled_emails' → get all emails with a specific label\n- 'bulk_label' → apply a label to multiple emails at once (indices list)\n\n📰 Newsletter Management:\n- 'detect_newsletters' → scan inbox for newsletter/subscription emails\n- 'newsletter_digest' → generate a digest of recent newsletters\n- 'newsletter_stats' → stats on newsletter volume, top sources\n- 'newsletter_preferences' → set preference per newsletter sender (keep/archive/unsubscribe)\n- 'apply_newsletter_preferences' → apply saved preferences to inbox (dry_run=true for preview)\n\n🤖 Auto-Responder:\n- 'create_auto_response' → create conditional auto-response rule (name, conditions, response_body)\n- 'list_auto_responses' → list all auto-response rules\n- 'update_auto_response' → update an auto-response rule\n- 'delete_auto_response' → delete an auto-response rule\n- 'toggle_auto_response' → enable/disable an auto-response\n- 'auto_response_history' → view history of sent auto-responses\n\n✍️ Email Signatures:\n- 'create_signature' → create a reusable email signature\n- 'list_signatures' → list all signatures\n- 'update_signature' → update a signature\n- 'delete_signature' → delete a signature\n- 'set_default_signature' → set default signature\n- 'get_signature' → get a signature by ID or default\n\n👤 Email Aliases / Identities:\n- 'add_alias' → add a sender alias/identity\n- 'list_aliases' → list all aliases\n- 'update_alias' → update an alias\n- 'delete_alias' → delete an alias\n- 'set_default_alias' → set default sender alias\n\n💾 Email Export / Archival:\n- 'export_emails' → export recent emails to JSON/text file\n- 'export_thread' → export a full thread to file\n- 'backup_mailbox' → full mailbox backup\n- 'list_backups' → list all exports and backups\n- 'search_exports' → search through exported emails\n- 'export_stats' → export/backup statistics\n\n📝 Email Templates (Advanced):\n- 'create_template' → create reusable email template with {{variable}} placeholders\n- 'list_templates' → list all templates (optional category filter)\n- 'get_template' → get template details by ID\n- 'update_template' → update a template\n- 'delete_template' → delete a template\n- 'use_template' → render template with variable substitutions\n\n📄 Draft Management:\n- 'save_draft' → save email as managed draft\n- 'list_drafts_managed' → list all saved drafts\n- 'get_draft' → get draft details by ID\n- 'update_draft' → update a saved draft\n- 'delete_draft' → delete a saved draft\n\n📁 Folder Management:\n- 'create_mail_folder' → create a new mailbox folder\n- 'list_mail_folders' → list all mailbox folders\n- 'rename_mail_folder' → rename a folder\n- 'delete_mail_folder' → delete a folder\n- 'move_to_folder' → move email to a specific folder by index\n- 'get_folder_stats' → email count per folder\n\n📊 Email Tracking:\n- 'track_email' → track a sent email for reply status\n- 'list_tracked_emails' → list all tracked emails\n- 'get_tracking_status' → tracking details for a specific email\n- 'tracking_report' → tracking summary report\n- 'untrack_email' → stop tracking an email\n\n📦 Extended Batch Operations:\n- 'batch_archive' → archive multiple emails at once (indices list)\n- 'batch_reply' → reply to multiple emails with the same body\n\n📅 Calendar Integration:\n- 'email_to_event' → create calendar event from an email\n- 'list_email_events' → list all email-created calendar events\n- 'upcoming_from_email' → upcoming events created from emails\n- 'meeting_conflicts' → check meeting conflicts on a date\n- 'sync_email_calendar' → email-calendar sync summary\n\n📈 Dashboard & Reporting:\n- 'email_dashboard' → comprehensive email dashboard overview\n- 'weekly_report' → weekly email activity summary\n- 'monthly_report' → monthly email activity summary\n- 'productivity_score' → email productivity rating 0-100 with grade\n- 'email_trends' → email trend analysis over N days\n\nFor COMPLEX multi-step email tasks, use deploy_email_agent instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["unread", "inbox", "read", "search", "send", "verify_sent", "reply", "forward", "delete", "archive", "move", "flag", "mark_read", "mark_unread", "drafts", "list_folders", "download_attachments", "summarize", "categorize", "thread", "run_rules", "quick_reply", "suggest_replies", "list_quick_replies", "save_template", "list_templates", "send_template", "schedule", "list_scheduled", "cancel_scheduled", "batch_read", "batch_delete", "batch_move", "batch_forward", "add_rule", "list_rules", "delete_rule", "toggle_rule", "followup", "check_followups", "lookup_contact", "add_contact", "list_contacts", "search_contacts", "delete_contact", "auto_learn_contacts", "snooze", "list_snoozed", "cancel_snooze", "priority_inbox", "sender_profile", "digest", "set_ooo", "cancel_ooo", "ooo_status", "analytics", "email_health", "stats", "clean_sweep", "auto_triage", "inbox_zero_status", "smart_unsubscribe", "build_attachment_index", "search_attachments", "attachment_summary", "list_saved_attachments", "score_relationships", "detect_vips", "relationship_report", "communication_graph", "decay_contacts", "scan_email_security", "check_sender_trust", "scan_links", "security_report", "add_trusted_sender", "add_blocked_sender", "list_trusted_senders", "list_blocked_senders", "extract_action_items", "extract_meeting_details", "scan_inbox_actions", "create_reminder", "create_calendar_event", "list_actions", "complete_action", "action_summary", "create_workflow", "list_workflows", "get_workflow", "delete_workflow", "toggle_workflow", "run_workflow", "workflow_templates", "create_from_template", "workflow_history", "smart_compose", "rewrite_email", "adjust_tone", "suggest_subject_lines", "proofread_email", "compose_reply_draft", "delegate_email", "list_delegations", "update_delegation", "complete_delegation", "cancel_delegation", "delegation_dashboard", "nudge_delegation", "contextual_search", "build_search_index", "conversation_recall", "search_by_date_range", "find_related_emails", "analyze_sentiment", "batch_sentiment", "sender_sentiment", "sentiment_alerts", "sentiment_report", "create_smart_folder", "list_smart_folders", "get_smart_folder", "update_smart_folder", "delete_smart_folder", "pin_smart_folder", "summarize_thread", "thread_decisions", "thread_participants", "thread_timeline", "prepare_forward_summary", "add_label", "remove_label", "list_labels", "get_labeled_emails", "bulk_label", "detect_newsletters", "newsletter_digest", "newsletter_stats", "newsletter_preferences", "apply_newsletter_preferences", "create_auto_response", "list_auto_responses", "update_auto_response", "delete_auto_response", "toggle_auto_response", "auto_response_history", "create_signature", "list_signatures", "update_signature", "delete_signature", "set_default_signature", "get_signature", "add_alias", "list_aliases", "update_alias", "delete_alias", "set_default_alias", "export_emails", "export_thread", "backup_mailbox", "list_backups", "search_exports", "export_stats", "create_template", "list_templates", "get_template", "update_template", "delete_template", "use_template", "save_draft", "list_drafts_managed", "get_draft", "update_draft", "delete_draft", "create_mail_folder", "list_mail_folders", "rename_mail_folder", "delete_mail_folder", "move_to_folder", "get_folder_stats", "track_email", "list_tracked_emails", "get_tracking_status", "tracking_report", "untrack_email", "batch_archive", "batch_reply", "email_to_event", "list_email_events", "upcoming_from_email", "meeting_conflicts", "sync_email_calendar", "email_dashboard", "weekly_report", "monthly_report", "productivity_score", "email_trends"]},
                "count": {"type": "integer", "description": "Emails to read (inbox/drafts action)", "default": 5},
                "index": {"type": "integer", "description": "Email index, 1=newest (read/reply/forward/delete/archive/move/flag/quick_reply/suggest_replies)"},
                "keyword": {"type": "string", "description": "Search keyword (search action)"},
                "sender": {"type": "string", "description": "Filter by sender (search/batch_delete action)"},
                "subject_filter": {"type": "string", "description": "Filter by subject (search/thread action)"},
                "unread_only": {"type": "boolean", "description": "Only unread (search action)"},
                "mailbox": {"type": "string", "description": "Mailbox name (default: inbox)"},
                "to": {"type": "string", "description": "Recipient (send/forward/verify_sent/schedule/batch_forward/followup)"},
                "subject": {"type": "string", "description": "Subject (send/verify_sent/schedule/followup)"},
                "body": {"type": "string", "description": "Body (send/reply/forward/schedule)"},
                "cc": {"type": "string", "description": "CC recipient(s) (send)"},
                "bcc": {"type": "string", "description": "BCC recipient(s) (send)"},
                "html": {"type": "boolean", "description": "Send as HTML (send/schedule action)"},
                "attachment_path": {"type": "string", "description": "File path to attach (send)"},
                "from_address": {"type": "string", "description": "Sender address (default: tarsitgroup@outlook.com)"},
                "reply_all": {"type": "boolean", "description": "Reply to all (reply action)"},
                "to_mailbox": {"type": "string", "description": "Destination mailbox (move/batch_move action)"},
                "from_mailbox": {"type": "string", "description": "Source mailbox (batch_move action)"},
                "flagged": {"type": "boolean", "description": "True=flag, false=unflag (flag action)"},
                "account": {"type": "string", "description": "Account name (move action)"},
                "reply_type": {"type": "string", "description": "Quick reply template (quick_reply: acknowledge/confirm_meeting/decline_meeting/will_review/follow_up/thank_you/out_of_office/request_info)"},
                "custom_note": {"type": "string", "description": "Custom text appended to quick reply"},
                "name": {"type": "string", "description": "Template/rule/contact name (save_template/send_template/add_rule/lookup_contact/add_contact)"},
                "variables": {"type": "object", "description": "Template variable substitutions (send_template)"},
                "send_at": {"type": "string", "description": "When to send (schedule: ISO timestamp or minutes like '30m')"},
                "schedule_id": {"type": "string", "description": "Scheduled email ID (cancel_scheduled)"},
                "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of message indices (batch_read/batch_delete/batch_move/batch_forward)"},
                "all_unread": {"type": "boolean", "description": "Mark ALL unread as read (batch_read)"},
                "conditions": {"type": "object", "description": "Rule match conditions (add_rule: sender_contains, subject_contains, etc.)"},
                "actions": {"type": "array", "description": "Rule actions (add_rule: [{action:'move_to',value:'folder'}, ...])", "items": {"type": "object"}},
                "rule_id": {"type": "string", "description": "Rule ID (delete_rule/toggle_rule)"},
                "deadline_hours": {"type": "integer", "description": "Follow-up deadline in hours (followup)", "default": 48},
                "reminder_text": {"type": "string", "description": "Follow-up reminder text (followup)"},
                "email": {"type": "string", "description": "Contact email (add_contact/delete_contact)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Contact tags (add_contact)"},
                "notes": {"type": "string", "description": "Contact notes (add_contact)"},
                "contact_id": {"type": "string", "description": "Contact ID (delete_contact)"},
                "tag": {"type": "string", "description": "Filter by tag (list_contacts)"},
                "query": {"type": "string", "description": "Search query (search_contacts)"},
                "snooze_until": {"type": "string", "description": "When to resurface (snooze: '2h', '30m', '1d', 'tomorrow', 'monday', 'tonight', or ISO timestamp)"},
                "snooze_id": {"type": "string", "description": "Snooze ID (cancel_snooze)"},
                "start_date": {"type": "string", "description": "OOO start date (set_ooo: ISO date 'YYYY-MM-DD', 'today', or 'tomorrow')"},
                "end_date": {"type": "string", "description": "OOO end date (set_ooo: ISO date 'YYYY-MM-DD')"},
                "ooo_message": {"type": "string", "description": "OOO auto-reply message body (set_ooo)"},
                "exceptions": {"type": "array", "items": {"type": "string"}, "description": "Email addresses/domains to NOT auto-reply to (set_ooo)"},
                "period": {"type": "string", "description": "Analytics time period (analytics: day/week/month)", "default": "week"},
                "older_than_days": {"type": "integer", "description": "Archive/delete emails older than N days (clean_sweep)", "default": 7},
                "dry_run": {"type": "boolean", "description": "Preview only, don't actually move (clean_sweep)", "default": True},
                "categories": {"type": "array", "items": {"type": "string"}, "description": "Categories to sweep (clean_sweep: newsletter/notification/promotional)"},
                "threshold": {"type": "integer", "description": "VIP detection score threshold 0-100 (detect_vips)", "default": 70},
                "top_n": {"type": "integer", "description": "Top N contacts to show (communication_graph)", "default": 15},
                "inactive_days": {"type": "integer", "description": "Days of inactivity before decay (decay_contacts)", "default": 90},
                "contact_query": {"type": "string", "description": "Contact name or email to report on (relationship_report)"},
                "filename": {"type": "string", "description": "Filename to search for (search_attachments)"},
                "file_type": {"type": "string", "description": "File type filter e.g. pdf, xlsx, jpg (search_attachments/list_saved_attachments)"},
                "folder": {"type": "string", "description": "Subfolder to list (list_saved_attachments)"},
                "sender_email": {"type": "string", "description": "Sender email to check trust (check_sender_trust)"},
                "email_or_domain": {"type": "string", "description": "Email or @domain to trust/block (add_trusted_sender/add_blocked_sender)"},
                "reason": {"type": "string", "description": "Reason for trusting/blocking (add_trusted_sender/add_blocked_sender)"},
                "action_id": {"type": "string", "description": "Action item ID (complete_action)"},
                "status": {"type": "string", "description": "Filter status: all/pending/completed (list_actions)"},
                "title": {"type": "string", "description": "Reminder/event title (create_reminder/create_calendar_event)"},
                "due_date": {"type": "string", "description": "Reminder due date (create_reminder)"},
                "source_email_subject": {"type": "string", "description": "Source email subject for reminder context (create_reminder)"},
                "start_datetime": {"type": "string", "description": "Event start date/time (create_calendar_event)"},
                "end_datetime": {"type": "string", "description": "Event end date/time (create_calendar_event)"},
                "location": {"type": "string", "description": "Event location (create_calendar_event)"},
                "workflow_name": {"type": "string", "description": "Workflow name (create_workflow)"},
                "workflow_id": {"type": "string", "description": "Workflow ID (get_workflow/delete_workflow/toggle_workflow/run_workflow/workflow_history)"},
                "trigger": {"type": "object", "description": "Workflow trigger conditions: from_contains, subject_contains, from_vip, category, is_unread (create_workflow)"},
                "steps": {"type": "array", "description": "Workflow steps: [{action, params, condition}] (create_workflow)", "items": {"type": "object"}},
                "enabled": {"type": "boolean", "description": "Enable/disable workflow (toggle_workflow/create_workflow)"},
                "template_name": {"type": "string", "description": "Template name: vip_urgent/newsletter_cleanup/team_forward/followup_escalation/auto_categorize_act (create_from_template)"},
                "template_params": {"type": "object", "description": "Template parameter overrides (create_from_template)"},
                "limit": {"type": "integer", "description": "Max history entries (workflow_history)", "default": 20},
                "prompt": {"type": "string", "description": "Compose prompt describing what to write (smart_compose/compose_reply_draft)"},
                "context_email": {"type": "string", "description": "Previous email text for context (smart_compose/compose_reply_draft)"},
                "tone": {"type": "string", "description": "Writing tone: formal/friendly/urgent/apologetic/enthusiastic/concise/diplomatic (smart_compose/rewrite_email/adjust_tone)"},
                "style": {"type": "string", "description": "Writing style: concise/detailed/bullet_points/executive_summary/action_oriented (smart_compose/rewrite_email)"},
                "text": {"type": "string", "description": "Email text to rewrite/adjust/proofread (rewrite_email/adjust_tone/proofread_email/suggest_subject_lines)"},
                "recipient": {"type": "string", "description": "Recipient name/email for context (smart_compose)"},
                "instructions": {"type": "string", "description": "Reply instructions (compose_reply_draft) or delegation instructions (delegate_email)"},
                "delegate_to": {"type": "string", "description": "Person to delegate to (delegate_email)"},
                "delegation_id": {"type": "string", "description": "Delegation ID (update_delegation/complete_delegation/cancel_delegation/nudge_delegation)"},
                "outcome": {"type": "string", "description": "Completion outcome (complete_delegation)"},
                "summarize": {"type": "boolean", "description": "Include AI summary in conversation recall (conversation_recall)", "default": False},
                "max_results": {"type": "integer", "description": "Max search results (contextual_search/search_by_date_range/find_related_emails)", "default": 20},
                "sender_email": {"type": "string", "description": "Sender email address (sender_sentiment)"},
                "threshold": {"type": "integer", "description": "Sentiment threshold score (sentiment_alerts, default -20)", "default": -20},
                "folder_name": {"type": "string", "description": "Smart folder name (create_smart_folder/update_smart_folder)"},
                "folder_id": {"type": "string", "description": "Smart folder ID (get_smart_folder/update_smart_folder/delete_smart_folder/pin_smart_folder)"},
                "criteria": {"type": "object", "description": "Search criteria for smart folders: {from_contains, subject_contains, keyword, has_attachment, is_unread, is_flagged, exclude_from}"},
                "subject_or_index": {"type": "string", "description": "Thread subject string or email index (summarize_thread/thread_decisions/thread_participants/thread_timeline/prepare_forward_summary)"},
                "max_messages": {"type": "integer", "description": "Max messages in thread (summarize_thread/thread_decisions/thread_participants/thread_timeline)", "default": 20},
                "label": {"type": "string", "description": "Label/tag name (add_label/remove_label/get_labeled_emails/bulk_label)"},
                "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of email indices (bulk_label)"},
                "pref_action": {"type": "string", "description": "Newsletter preference: keep/archive/unsubscribe (newsletter_preferences)"},
                "conditions": {"type": "object", "description": "Auto-response conditions: {from_contains, subject_contains, body_contains, mailbox} (create_auto_response/update_auto_response)"},
                "response_body": {"type": "string", "description": "Auto-response reply text (create_auto_response/update_auto_response)"},
                "response_subject": {"type": "string", "description": "Custom subject for auto-response (create_auto_response)"},
                "max_replies": {"type": "integer", "description": "Max auto-replies per sender per day (create_auto_response)", "default": 1},
                "rule_id": {"type": "string", "description": "Auto-response rule ID (update_auto_response/delete_auto_response/toggle_auto_response)"},
                "limit": {"type": "integer", "description": "Max history entries (auto_response_history)", "default": 20},
                "sig_id": {"type": "string", "description": "Signature ID (update_signature/delete_signature/set_default_signature/get_signature)"},
                "is_html": {"type": "boolean", "description": "Whether signature body is HTML (create_signature/update_signature)"},
                "alias_email": {"type": "string", "description": "Alias email address (add_alias/update_alias)"},
                "display_name": {"type": "string", "description": "Display name for alias (add_alias/update_alias)"},
                "alias_id": {"type": "string", "description": "Alias ID (update_alias/delete_alias/set_default_alias)"},
                "export_format": {"type": "string", "description": "Export format: json or txt (export_emails/export_thread)", "enum": ["json", "txt"]},
                "max_emails": {"type": "integer", "description": "Max emails for backup (backup_mailbox)", "default": 100},
                "template_id": {"type": "string", "description": "Template ID (get_template/update_template/delete_template/use_template)"},
                "subject_template": {"type": "string", "description": "Template subject with {{variable}} placeholders (create_template/update_template)"},
                "body_template": {"type": "string", "description": "Template body with {{variable}} placeholders (create_template/update_template)"},
                "category": {"type": "string", "description": "Template category (create_template/list_templates/update_template)"},
                "draft_id": {"type": "string", "description": "Draft ID (get_draft/update_draft/delete_draft)"},
                "parent": {"type": "string", "description": "Parent folder (create_mail_folder)"},
                "new_name": {"type": "string", "description": "New folder name (rename_mail_folder)"},
                "tracking_id": {"type": "string", "description": "Tracking ID (get_tracking_status/untrack_email)"},
                "sent_at": {"type": "string", "description": "When email was sent ISO (track_email)"},
                "calendar_name": {"type": "string", "description": "Calendar name (email_to_event)"},
                "date": {"type": "string", "description": "Date YYYY-MM-DD (meeting_conflicts)"},
                "days": {"type": "integer", "description": "Number of days (upcoming_from_email/email_trends)", "default": 7}
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
        "description": "Generate professional reports (Excel, PDF, or CSV). Reports are saved to ~/Documents/TARS_Reports/ and can be attached to emails.\n\nFormats:\n- 'excel' → .xlsx with styled headers, alternating rows, auto-width, optional summary\n- 'pdf' → .pdf with title, sections, optional table\n- 'csv' → simple .csv data export\n\nTwo ways to pass data:\n1. TABULAR (preferred for excel/csv): headers=['Stock','Price','P/E'], rows=[['NVDA','$182.81','45.25'],['AMD','$206.82','79.43']]\n2. DATA DICT (auto-converted): data={'stock_data': {'NVDA': {'price': '$182.81', 'P/E': '45.25'}, 'AMD': {'price': '$206.82', 'P/E': '79.43'}}, 'news': ['headline1', 'headline2']}\n   → Dict-of-dicts become table rows, lists become summary/sections.\n\nWorkflow: generate_report → get the path → mac_mail send with attachment_path",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["excel", "pdf", "csv"], "description": "Report format"},
                "title": {"type": "string", "description": "Report title"},
                "data": {"type": "object", "description": "Nested data dict — auto-converted to tabular format. Use this when passing research results directly."},
                "headers": {"type": "array", "items": {"type": "string"}, "description": "Column headers (excel/csv/pdf table). Not needed if 'data' is provided."},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Data rows — each row is a list of strings. Not needed if 'data' is provided."},
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
    {
        "name": "get_error_report",
        "description": (
            "Get the full error tracker report, formatted as an actionable dev-agent prompt. "
            "Returns every tracked error with stack traces, fix hints, sample inputs, "
            "and which files to edit. Use this to understand what's failing in TARS, "
            "or pass the output directly to deploy_dev_agent to fix the issues.\n\n"
            "The report includes:\n"
            "- All unfixed errors ranked by frequency\n"
            "- Stack traces and exact code locations\n"
            "- Pattern-matched fix hints (what to change)\n"
            "- Sample inputs that triggered each error\n"
            "- Previous fix attempts (what didn't work)\n"
            "- Error hotspot files\n\n"
            "Use format='dev_prompt' for a dev-agent-ready prompt, or 'summary' for a quick overview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["dev_prompt", "summary"],
                    "description": "'dev_prompt' = full prompt for dev agent with all context. 'summary' = quick human overview.",
                },
            },
            "required": [],
        },
    },

    # ═══════════════════════════════════════
    #  Scheduled Tasks (Proactive Agent)
    # ═══════════════════════════════════════
    {
        "name": "schedule_task",
        "description": "Schedule a recurring autonomous task. TARS will execute it automatically at the specified time.\n\nSchedule formats:\n- Cron: '0 9 * * *' (every day at 9 AM)\n- Natural: 'daily at 9am', 'every 30 minutes', 'every monday at 8am', 'weekdays at 9am'\n\nExamples:\n  schedule_task(task='Check my email and summarize unread', schedule='daily at 9am')\n  schedule_task(task='Track NVDA stock price', schedule='every hour')\n  schedule_task(task='Summarize tech news', schedule='daily at 7pm')\n  schedule_task(task='Backup my projects folder', schedule='every sunday at 2am')",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What TARS should do when triggered."},
                "schedule": {"type": "string", "description": "When to run: cron ('0 9 * * *') or natural language ('daily at 9am', 'every hour', 'every monday at 8am')."}
            },
            "required": ["task", "schedule"]
        }
    },
    {
        "name": "list_scheduled_tasks",
        "description": "List all scheduled recurring tasks with their status, last run time, and next run time.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "remove_scheduled_task",
        "description": "Remove a scheduled task by its ID. Use list_scheduled_tasks first to see task IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The ID of the scheduled task to remove."}
            },
            "required": ["task_id"]
        }
    },

    # ═══════════════════════════════════════
    #  Image Generation (DALL-E 3)
    # ═══════════════════════════════════════
    {
        "name": "generate_image",
        "description": "Generate an image using DALL-E 3. The image is saved to ~/Documents/TARS_Reports/ and can be attached to emails.\n\nExamples:\n  generate_image(prompt='A cyberpunk cityscape at sunset with neon signs')\n  generate_image(prompt='Logo for a tech startup called NexaAI', size='1024x1024', quality='hd')\n  generate_image(prompt='Professional headshot style portrait, corporate background')",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed description of the image to generate."},
                "size": {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"], "description": "Image size (default: 1024x1024).", "default": "1024x1024"},
                "quality": {"type": "string", "enum": ["standard", "hd"], "description": "Image quality (default: standard).", "default": "standard"},
                "style": {"type": "string", "enum": ["vivid", "natural"], "description": "Image style (default: vivid).", "default": "vivid"}
            },
            "required": ["prompt"]
        }
    },

    # ═══════════════════════════════════════
    #  Home Automation (Home Assistant)
    # ═══════════════════════════════════════
    {
        "name": "smart_home",
        "description": "Control smart home devices via Home Assistant.\n\nActions:\n- 'list' — list all devices and their states\n- 'turn_on' / 'turn_off' — control a device by entity_id\n- 'set' — set brightness, temperature, color, etc.\n- 'scene' — activate a Home Assistant scene\n- 'status' — get status of a specific device\n\nExamples:\n  smart_home(action='list')\n  smart_home(action='turn_on', entity_id='light.living_room')\n  smart_home(action='set', entity_id='light.bedroom', data={'brightness': 128})\n  smart_home(action='turn_off', entity_id='switch.coffee_maker')\n  smart_home(action='scene', entity_id='scene.movie_night')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "turn_on", "turn_off", "set", "scene", "status"], "description": "What to do."},
                "entity_id": {"type": "string", "description": "Home Assistant entity ID (e.g., 'light.living_room', 'switch.fan')."},
                "data": {"type": "object", "description": "Additional data for 'set' action (brightness, temperature, color, etc.)."}
            },
            "required": ["action"]
        }
    },

    # ═══════════════════════════════════════
    #  PowerPoint Generation
    # ═══════════════════════════════════════
    {
        "name": "generate_presentation",
        "description": "Generate a PowerPoint (.pptx) presentation. Saved to ~/Documents/TARS_Reports/.\n\nExamples:\n  generate_presentation(title='Q4 Results', slides=[{title:'Revenue', bullets:['$2.1B revenue','15% YoY growth']}, {title:'Outlook', bullets:['Expanding to APAC','New product launch Q1']}])\n  generate_presentation(title='AI Chip Market', slides=[{title:'Overview', body:'The AI chip market is projected...'}, {title:'Key Players', bullets:['NVIDIA','AMD','Intel']}])",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Presentation title (first slide)."},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Slide title"},
                            "bullets": {"type": "array", "items": {"type": "string"}, "description": "Bullet points for this slide"},
                            "body": {"type": "string", "description": "Body text (alternative to bullets)"},
                            "image_path": {"type": "string", "description": "Optional image path to include on slide"}
                        },
                        "required": ["title"]
                    },
                    "description": "List of slides (each has title + bullets or body)."
                },
                "subtitle": {"type": "string", "description": "Subtitle on title slide."},
                "filename": {"type": "string", "description": "Custom filename (auto-generated if omitted)."}
            },
            "required": ["title", "slides"]
        }
    },

    # ═══════════════════════════════════════
    #  Video/Audio Processing
    # ═══════════════════════════════════════
    {
        "name": "process_media",
        "description": "Process video/audio files using FFmpeg and Whisper.\n\nActions:\n- 'transcribe' — Transcribe audio/video to text (uses Whisper)\n- 'convert' — Convert between formats (mp4→mp3, wav→mp3, etc.)\n- 'trim' — Trim a clip (start/end times)\n- 'extract_audio' — Extract audio track from video\n- 'compress' — Compress video (reduce file size)\n- 'info' — Get media file info (duration, codec, resolution)\n\nExamples:\n  process_media(action='transcribe', input_path='~/meeting.mp4')\n  process_media(action='convert', input_path='~/audio.wav', output_format='mp3')\n  process_media(action='trim', input_path='~/video.mp4', start='00:01:30', end='00:05:00')\n  process_media(action='extract_audio', input_path='~/lecture.mp4')",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["transcribe", "convert", "trim", "extract_audio", "compress", "info"], "description": "What to do."},
                "input_path": {"type": "string", "description": "Path to the input media file."},
                "output_format": {"type": "string", "description": "Output format for 'convert' (mp3, mp4, wav, etc.)."},
                "start": {"type": "string", "description": "Start time for 'trim' (HH:MM:SS or seconds)."},
                "end": {"type": "string", "description": "End time for 'trim' (HH:MM:SS or seconds)."},
                "output_path": {"type": "string", "description": "Custom output path (auto-generated if omitted)."}
            },
            "required": ["action", "input_path"]
        }
    },

    # ═══════════════════════════════════════
    #  Document Ingestion (RAG)
    # ═══════════════════════════════════════
    {
        "name": "ingest_document",
        "description": "Ingest a document into TARS's semantic memory for RAG (Retrieval-Augmented Generation). Once ingested, you can search the document's contents using search_documents or recall_memory.\n\nSupported formats: PDF, DOCX, TXT, MD, PY, JSON, CSV, HTML, YAML, JS, TS\n\nExamples:\n  ingest_document(file_path='~/Documents/research_paper.pdf')\n  ingest_document(file_path='~/notes.md')\n  ingest_document(file_path='~/code/README.md')\n\nAfter ingesting, use: search_documents(query='what does the paper say about X?')",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the document to ingest."},
                "chunk_size": {"type": "integer", "description": "Characters per chunk (default: 1000).", "default": 1000},
                "chunk_overlap": {"type": "integer", "description": "Overlap between chunks (default: 200).", "default": 200}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "search_documents",
        "description": "Search previously ingested documents using semantic (meaning-based) search. Returns the most relevant chunks from all ingested PDFs, docs, and files.\n\nExamples:\n  search_documents(query='machine learning performance benchmarks')\n  search_documents(query='what are the key findings?', n_results=10)\n\nFirst ingest documents with ingest_document, then search them with this tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query."},
                "n_results": {"type": "integer", "description": "Max results to return (default: 5).", "default": 5}
            },
            "required": ["query"]
        }
    },

    # ═══════════════════════════════════════
    #  Headless Browser (Playwright)
    # ═══════════════════════════════════════
    {
        "name": "headless_browse",
        "description": "Fast headless browser for web scraping and screenshots without opening Chrome. Uses Playwright.\n\nActions:\n- 'scrape' — Extract text content from a URL (faster than browser agent)\n- 'screenshot' — Take a full-page screenshot\n- 'links' — Extract all links from a page\n- 'tables' — Extract HTML tables as structured data\n\nExamples:\n  headless_browse(action='scrape', url='https://example.com')\n  headless_browse(action='screenshot', url='https://news.ycombinator.com')\n  headless_browse(action='links', url='https://github.com/trending')\n  headless_browse(action='tables', url='https://en.wikipedia.org/wiki/List_of_countries')\n\n⚠️ For interactive browsing (clicking, forms, login), use deploy_browser_agent instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["scrape", "screenshot", "links", "tables"], "description": "What to do."},
                "url": {"type": "string", "description": "URL to browse."}
            },
            "required": ["action", "url"]
        }
    },

    # ═══════════════════════════════════════
    #  MCP (Model Context Protocol) Client
    # ═══════════════════════════════════════
    {
        "name": "mcp_list_tools",
        "description": "List all available tools from connected MCP servers. MCP (Model Context Protocol) allows TARS to connect to external tool servers for additional capabilities.\n\nUse this to discover what MCP tools are available before calling them.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "mcp_call_tool",
        "description": "Call a tool on a connected MCP server. Use mcp_list_tools first to discover available tools.\n\nTool names are formatted as: mcp_<server_name>__<tool_name>\n\nExamples:\n  mcp_call_tool(tool='mcp_filesystem__read_file', arguments={'path': '/tmp/data.txt'})\n  mcp_call_tool(tool='mcp_github__search_repos', arguments={'query': 'language:python stars:>1000'})\n  mcp_call_tool(tool='mcp_sqlite__query', arguments={'sql': 'SELECT * FROM users LIMIT 10'})",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Full MCP tool name: mcp_<server>__<tool_name>."},
                "arguments": {"type": "object", "description": "Arguments to pass to the MCP tool."}
            },
            "required": ["tool"]
        }
    },
]


# ═══════════════════════════════════════════════════
#  DYNAMIC TOOL PRUNING (Phase 22)
# ═══════════════════════════════════════════════════

# Core tools always included regardless of intent
_CORE_TOOLS = {
    "think", "send_imessage", "send_imessage_file", "wait_for_reply", "recall_memory",
    "save_memory", "list_memories", "delete_memory", "scan_environment", "checkpoint",
    "propose_self_heal",
}

# Domain-specific tool groups
_DOMAIN_TOOLS = {
    "coding": {"run_quick_command", "quick_read_file",
               "deploy_coder_agent", "deploy_file_agent", "deploy_dev_agent", "verify_result"},
    "web": {"web_search", "deploy_browser_agent", "deploy_screen_agent", "headless_browse",
            "manage_account"},
    "files": {"quick_read_file", "deploy_file_agent", "verify_result",
              "run_quick_command", "ingest_document", "search_documents"},
    "system": {"run_quick_command", "deploy_system_agent",
               "scan_environment", "mac_system", "mac_calendar", "mac_notes",
               "mac_reminders", "smart_home"},
    "communication": {"send_imessage", "send_imessage_file", "wait_for_reply", "mac_mail",
                       "deploy_email_agent"},
    "research": {"web_search", "deploy_browser_agent", "deploy_research_agent",
                 "headless_browse", "quick_read_file",
                 "search_documents", "ingest_document"},
    "report": {"generate_report", "quick_read_file", "generate_presentation",
               "generate_image"},
    "scheduling": {"schedule_task", "list_scheduled_tasks", "remove_scheduled_task"},
    "media": {"process_media"},
    "home": {"smart_home"},
    "creative": {"generate_image", "generate_presentation", "generate_report"},
    "documents": {"ingest_document", "search_documents", "quick_read_file"},
    "memory": {"save_memory", "recall_memory", "list_memories", "delete_memory", "ingest_document", "search_documents"},
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
