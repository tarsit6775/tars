#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     TARS — 10 Real-World Browser Tasks (Progressive Difficulty)  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  These are REAL tasks to send to TARS one at a time.             ║
║  Each task tests a different browsing capability.                ║
║                                                                  ║
║  Usage:                                                          ║
║    python tests/real_world_tasks.py              → list all      ║
║    python tests/real_world_tasks.py 1            → send task 1   ║
║    python tests/real_world_tasks.py 1 --dry-run  → preview only  ║
║                                                                  ║
║  Difficulty ramp:                                                ║
║    Tasks 1-3:  Single-site signup (form fill + verify)           ║
║    Tasks 4-6:  Signup + navigate + extract data                  ║
║    Tasks 7-8:  Multi-step workflows (create + configure + use)   ║
║    Tasks 9-10: Multi-site orchestration (cross-platform)         ║
║                                                                  ║
║  All tasks use tarsitgroup@outlook.com (Outlook) or              ║
║  tarsitsales@gmail.com (Gmail/OAuth). Never @example.com.        ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
#  THE 10 TASKS
# ═══════════════════════════════════════════════════════════════

TASKS = [

    # ──────────────────────────────────────────────────────────
    #  TASK 1: Discord Account Creation
    #  Difficulty: ★★☆☆☆
    #  Tests: Signup form, email verification, captcha handling
    #  Why: Discord has hCaptcha — tests CAPTCHA solving
    # ──────────────────────────────────────────────────────────
    {
        "id": 1,
        "name": "Discord Account Creation",
        "difficulty": "★★☆☆☆",
        "tests": ["Google-first navigation", "Form filling", "hCaptcha", "Email verification (OTP)", "Store credentials"],
        "expected_agent": "Screen Agent (hCaptcha is visual)",
        "estimated_steps": 25,
        "task": (
            "Create a Discord account for me. "
            "Use email tarsitgroup@outlook.com, display name 'TARS Agent', "
            "username 'tarsagent2026', password 'Tars.Discord2026!', "
            "birthday: January 15, 1998. "
            "Handle any CAPTCHA that appears. "
            "If Discord sends a verification email, check for it and enter the code. "
            "After the account is created, skip any onboarding prompts. "
            "Store the credentials when done."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 2: Supabase Account + New Project
    #  Difficulty: ★★★☆☆
    #  Tests: GitHub OAuth, project creation, API key extraction
    #  Why: Supabase uses GitHub OAuth — tests OAuth popup flow
    # ──────────────────────────────────────────────────────────
    {
        "id": 2,
        "name": "Supabase Signup + Project + API Keys",
        "difficulty": "★★★☆☆",
        "tests": ["Google-first navigation", "GitHub OAuth popup", "Project creation form", "API key extraction", "Store credentials"],
        "expected_agent": "Browser Agent (developer portal, cooperative)",
        "estimated_steps": 30,
        "task": (
            "Create a Supabase account and set up a new project. "
            "Sign up using GitHub OAuth (my GitHub is already logged in on Chrome). "
            "If GitHub OAuth isn't available, use email tarsitgroup@outlook.com with password 'Tars.Supa2026!'. "
            "After signup, create a new project with these settings: "
            "Name: 'tars-backend', Database Password: 'TarsDB2026!', Region: closest to US East. "
            "Wait for the project to finish provisioning. "
            "Then go to Project Settings > API and extract ALL of these: "
            "1) Project URL, 2) anon/public key, 3) service_role key. "
            "Report all three keys back to me and store them as credentials for 'supabase'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 3: Vercel Account + Deploy from Template
    #  Difficulty: ★★★☆☆
    #  Tests: OAuth signup, template selection, deployment flow
    #  Why: Vercel has GitHub import — tests multi-step wizard
    # ──────────────────────────────────────────────────────────
    {
        "id": 3,
        "name": "Vercel Signup + Deploy Next.js Template",
        "difficulty": "★★★☆☆",
        "tests": ["Google-first navigation", "GitHub OAuth", "Template wizard", "Deployment monitoring", "Extract deploy URL"],
        "expected_agent": "Browser Agent (cooperative dev portal)",
        "estimated_steps": 25,
        "task": (
            "Create a Vercel account and deploy a Next.js starter project. "
            "Sign up via GitHub OAuth (already logged in on Chrome). "
            "If not possible, use email tarsitgroup@outlook.com, password 'Tars.Vercel2026!'. "
            "After signup, click 'Add New Project' or 'New Project'. "
            "Choose 'Clone Template' and select the 'Next.js Boilerplate' or any basic Next.js template. "
            "Name the project 'tars-app'. Accept default settings and deploy. "
            "Wait for the deployment to complete (should take 30-60 seconds). "
            "Once deployed, get me the live URL (something like tars-app.vercel.app). "
            "Also go to Project Settings > Environment Variables and note any defaults. "
            "Store the account credentials and the deploy URL."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 4: Stripe Developer Account + API Keys + Test Payment
    #  Difficulty: ★★★☆☆
    #  Tests: Dev portal signup, dashboard navigation, key extraction
    #  Why: Stripe has test mode — safe to explore fully
    # ──────────────────────────────────────────────────────────
    {
        "id": 4,
        "name": "Stripe Dev Account + API Keys",
        "difficulty": "★★★☆☆",
        "tests": ["Google-first navigation", "Developer signup form", "Dashboard navigation", "API key extraction (publishable + secret)", "Store credentials"],
        "expected_agent": "Browser Agent (Stripe is dev-friendly)",
        "estimated_steps": 30,
        "task": (
            "Create a Stripe developer account and get me the API keys. "
            "Use email tarsitgroup@outlook.com, name 'Tars Agent', password 'Tars.Stripe2026!'. "
            "After signup and email verification (if needed), go to the Stripe Dashboard. "
            "Make sure you're in TEST MODE (not live). "
            "Navigate to Developers > API Keys. "
            "Get me both: 1) Publishable key (pk_test_...), 2) Secret key (sk_test_...). "
            "You may need to reveal the secret key by clicking 'Reveal test key'. "
            "Report both keys back to me and store them as credentials for 'stripe'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 5: Twilio Account + Phone Number + API Keys
    #  Difficulty: ★★★★☆
    #  Tests: Signup, phone verification skip, free trial setup,
    #         SID/Auth Token extraction, trial phone number
    #  Why: Twilio requires phone verification — complex onboarding
    # ──────────────────────────────────────────────────────────
    {
        "id": 5,
        "name": "Twilio Signup + SID/Auth Token + Trial Number",
        "difficulty": "★★★★☆",
        "tests": ["Google-first navigation", "Multi-step onboarding wizard", "Phone verification handling", "SID/Auth Token extraction", "Trial number provisioning"],
        "expected_agent": "Screen Agent (Twilio has aggressive bot detection)",
        "estimated_steps": 35,
        "task": (
            "Create a Twilio account and get me the API credentials. "
            "Use email tarsitgroup@outlook.com, name 'Tars Agent', password 'Tars.Twilio2026!'. "
            "During signup, Twilio will ask for a phone number for verification — "
            "if you can skip it, skip it. If not, let me know you need my phone number. "
            "After account creation, navigate to the Twilio Console dashboard. "
            "Extract: 1) Account SID, 2) Auth Token (you may need to click 'Show' to reveal it). "
            "Then go to Phone Numbers > Manage > Active Numbers. "
            "If no trial number exists, get a free trial number (any US number). "
            "Report back: Account SID, Auth Token, and the trial phone number. "
            "Store everything as credentials for 'twilio'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 6: Firebase Project + Web App + Config Keys
    #  Difficulty: ★★★★☆
    #  Tests: Google console navigation, project creation wizard,
    #         app registration, config extraction
    #  Why: Firebase has a multi-step wizard + Google auth
    # ──────────────────────────────────────────────────────────
    {
        "id": 6,
        "name": "Firebase Project + Web App + Config",
        "difficulty": "★★★★☆",
        "tests": ["Google-first navigation", "Google account auth", "Project creation wizard", "App registration", "Firebase config extraction"],
        "expected_agent": "Screen Agent (Google sites block automation)",
        "estimated_steps": 35,
        "task": (
            "Create a Firebase project and register a web app to get the config. "
            "Use the Gmail account tarsitsales@gmail.com (should already be logged into Google on Chrome). "
            "If not logged in, sign in first with tarsitsales@gmail.com. "
            "Steps: "
            "1) Go to Firebase Console (search Google for 'Firebase Console'). "
            "2) Click 'Create a project' or 'Add project'. "
            "3) Name it 'tars-project'. "
            "4) Disable Google Analytics if asked (to simplify). "
            "5) Wait for project creation to complete. "
            "6) Once in the project, click the web icon '</>' to add a web app. "
            "7) Register the app with nickname 'tars-web'. "
            "8) Copy the entire firebaseConfig object (apiKey, authDomain, projectId, etc). "
            "Report the full config back to me and store it as credentials for 'firebase'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 7: Notion Account + Create Workspace + Integration + API Key
    #  Difficulty: ★★★★☆
    #  Tests: Signup, workspace setup, integration creation,
    #         internal API token, connect to page
    #  Why: Notion has a unique integration system (not just API keys)
    # ──────────────────────────────────────────────────────────
    {
        "id": 7,
        "name": "Notion Signup + Integration + API Token",
        "difficulty": "★★★★☆",
        "tests": ["Google-first navigation", "Account creation", "Workspace creation", "Developer integration setup", "Internal API token extraction"],
        "expected_agent": "Browser Agent (Notion is dev-friendly)",
        "estimated_steps": 35,
        "task": (
            "Create a Notion account, set up a workspace, and create an API integration to get an API token. "
            "Use email tarsitgroup@outlook.com, name 'Tars Agent', password 'Tars.Notion2026!'. "
            "After signing up: "
            "1) Set up a personal workspace named 'TARS Workspace' (skip team invite). "
            "2) Create a blank page called 'TARS Notes'. "
            "3) Now go to Notion's developer portal: search Google for 'Notion create integration'. "
            "4) Click 'New integration'. Name it 'TARS Bot'. "
            "5) Select the 'TARS Workspace' as the associated workspace. "
            "6) Set capabilities to 'Read content', 'Update content', 'Insert content'. "
            "7) Submit and copy the Internal Integration Token (starts with 'ntn_' or 'secret_'). "
            "Report the API token back to me and store it as credentials for 'notion'. "
            "Also note the workspace ID if visible."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 8: Resend (Email API) — Signup + API Key + Send Test Email
    #  Difficulty: ★★★★☆
    #  Tests: Dev portal signup, API key creation, verify by
    #         actually sending a test email through the API
    #  Why: End-to-end verification — creates account, gets key,
    #        then USES it to send an email
    # ──────────────────────────────────────────────────────────
    {
        "id": 8,
        "name": "Resend Signup + API Key + Send Test Email",
        "difficulty": "★★★★☆",
        "tests": ["Google-first navigation", "Developer signup", "API key creation", "Terminal API call to verify key works", "End-to-end verification"],
        "expected_agent": "Browser Agent (signup) + run_quick_command (API test)",
        "estimated_steps": 30,
        "task": (
            "Create a Resend account (email API service), get an API key, and verify it works by sending a test email. "
            "Use email tarsitgroup@outlook.com, name 'Tars Agent', password 'Tars.Resend2026!'. "
            "After signup: "
            "1) Navigate to API Keys section in the Resend dashboard. "
            "2) Create a new API key named 'tars-key' with full access. "
            "3) Copy the API key (starts with 're_'). "
            "4) Verify the key works by running this curl command: "
            "   curl -X POST 'https://api.resend.com/emails' "
            "   -H 'Authorization: Bearer <YOUR_KEY>' "
            "   -H 'Content-Type: application/json' "
            "   -d '{\"from\": \"onboarding@resend.dev\", \"to\": \"tarsitgroup@outlook.com\", "
            "   \"subject\": \"TARS Test\", \"html\": \"<p>API key works!</p>\"}' "
            "5) Check that the response has a success status. "
            "Store the API key as credentials for 'resend'. "
            "Report back the key and whether the test email was sent successfully."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 9: Full Cloudflare Setup — Account + Site + DNS + API Token
    #  Difficulty: ★★★★★
    #  Tests: Signup, add domain wizard, DNS configuration,
    #         API token creation with permissions, multi-tab workflow
    #  Why: Cloudflare has a deep multi-step wizard + tokens with scopes
    # ──────────────────────────────────────────────────────────
    {
        "id": 9,
        "name": "Cloudflare Signup + API Token + Workers Setup",
        "difficulty": "★★★★★",
        "tests": ["Google-first navigation", "Developer signup", "Dashboard navigation", "API token creation with scoped permissions", "Workers setup"],
        "expected_agent": "Browser Agent (Cloudflare is dev-friendly)",
        "estimated_steps": 40,
        "task": (
            "Create a Cloudflare account, get an API token, and set up a Workers project. "
            "Use email tarsitgroup@outlook.com, name 'Tars Agent', password 'Tars.CF2026!'. "
            "After signup and email verification: "
            "1) Skip the 'Add a site' wizard (we'll use Workers instead). "
            "2) Go to 'My Profile' > 'API Tokens'. "
            "3) Click 'Create Token'. "
            "4) Use the 'Edit Cloudflare Workers' template (or create custom with Workers permissions). "
            "5) Set the token to allow 'All accounts' and 'All zones'. "
            "6) Create the token and COPY IT (it's only shown once). "
            "7) Then go to Workers & Pages in the sidebar. "
            "8) Click 'Create Worker' or 'Create Application'. "
            "9) Name it 'tars-worker'. "
            "10) Deploy the default 'Hello World' template. "
            "11) Get the worker URL (something.workers.dev). "
            "Report back: API Token, Account ID (from the overview page), and Worker URL. "
            "Store everything as credentials for 'cloudflare'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 10: Neon Serverless Postgres + Prisma Schema + Connection String
    #  Difficulty: ★★★★★
    #  Tests: DB-as-a-service signup, project creation,
    #         SQL execution in web console, connection string extraction,
    #         schema creation
    #  Why: Tests interacting with a web-based SQL console + copying
    #       structured data (connection strings)
    # ──────────────────────────────────────────────────────────
    {
        "id": 10,
        "name": "Neon DB Signup + Database + Table + Connection String",
        "difficulty": "★★★★★",
        "tests": ["Google-first navigation", "Developer signup", "Database provisioning", "SQL console interaction", "Connection string extraction"],
        "expected_agent": "Browser Agent (Neon is developer-friendly)",
        "estimated_steps": 35,
        "task": (
            "Create a Neon serverless Postgres account, set up a database, create a table, and get the connection string. "
            "Sign up using GitHub OAuth if available (already logged in). "
            "If not, use email tarsitgroup@outlook.com, password 'Tars.Neon2026!'. "
            "After signup: "
            "1) Create a new project named 'tars-db'. "
            "2) Select region closest to US East. Use the free tier. "
            "3) Wait for the database to provision. "
            "4) Go to the SQL Editor or Console. "
            "5) Run this SQL to create a table: "
            "   CREATE TABLE tasks (id SERIAL PRIMARY KEY, title TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW()); "
            "6) Verify the table was created: SELECT * FROM tasks; "
            "7) Insert a test row: INSERT INTO tasks (title) VALUES ('TARS test task'); "
            "8) Go to Connection Details or Dashboard. "
            "9) Copy the full connection string (postgres://...). "
            "Report back: the connection string (both pooled and direct if available). "
            "Store everything as credentials for 'neon'."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════
#  TASK RUNNER
# ═══════════════════════════════════════════════════════════════

def list_tasks():
    """Display all 10 tasks with metadata."""
    print()
    print("=" * 70)
    print("  TARS — 10 Real-World Browser Tasks")
    print("  Progressive difficulty: ★☆☆☆☆ → ★★★★★")
    print("=" * 70)

    for t in TASKS:
        print(f"\n  {'─' * 66}")
        print(f"  Task {t['id']:2d} │ {t['difficulty']} │ {t['name']}")
        print(f"         │ Agent: {t['expected_agent']}")
        print(f"         │ Est. steps: ~{t['estimated_steps']}")
        print(f"         │ Tests: {', '.join(t['tests'][:3])}")
        if len(t['tests']) > 3:
            print(f"         │        {', '.join(t['tests'][3:])}")

    print(f"\n  {'─' * 66}")
    print()
    print("  Usage:")
    print("    python tests/real_world_tasks.py 1            # send task 1 to TARS")
    print("    python tests/real_world_tasks.py 5 --dry-run  # preview task 5")
    print("    python tests/real_world_tasks.py all          # send ALL sequentially")
    print()


def send_task(task_id, dry_run=False):
    """Send a single task to TARS via CLI argument."""
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        print(f"❌ No task with ID {task_id}. Valid: 1-10")
        return

    print()
    print(f"  ╔{'═' * 60}╗")
    print(f"  ║  Task {task['id']}: {task['name']:<50s}  ║")
    print(f"  ║  Difficulty: {task['difficulty']:<47s}  ║")
    print(f"  ║  Expected: {task['expected_agent']:<49s}║")
    print(f"  ╚{'═' * 60}╝")
    print()
    print(f"  📋 Task text:")
    print(f"  {'─' * 60}")
    # Word wrap the task at 60 chars
    words = task["task"].split()
    line = "  "
    for word in words:
        if len(line) + len(word) + 1 > 62:
            print(line)
            line = "  " + word
        else:
            line += " " + word if line.strip() else "  " + word
    if line.strip():
        print(line)
    print(f"  {'─' * 60}")
    print()

    if dry_run:
        print("  🔍 DRY RUN — task NOT sent. Remove --dry-run to send.")
        return

    # Write a launcher script that starts TARS with this task
    launcher = os.path.join(os.path.dirname(__file__), "..", "_run_task.py")
    launcher = os.path.abspath(launcher)

    # Escape for Python string
    task_text = task["task"].replace("\\", "\\\\").replace('"', '\\"')

    script = f'''#!/usr/bin/env python3
"""Auto-generated launcher for Task {task["id"]}: {task["name"]}"""
import sys
sys.argv = ["tars.py", "{task_text}"]
exec(open("tars.py").read())
'''

    with open(launcher, "w") as f:
        f.write(script)

    print(f"  ✅ Launcher written to _run_task.py")
    print(f"  ")
    print(f"  To run:")
    print(f"    cd /Users/abdullah/Downloads/tars-main")
    print(f"    .venv/bin/python _run_task.py")
    print()
    print(f"  Or send via iMessage to TARS if it's already running.")
    print()

    return task["task"]


def main():
    args = sys.argv[1:]

    if not args:
        list_tasks()
        return

    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if args[0] == "all":
        print("⚠️  Running all 10 tasks sequentially is not recommended.")
        print("    Each task takes 3-10 minutes. Run one at a time.")
        print("    Use: python tests/real_world_tasks.py <number>")
        return

    try:
        task_id = int(args[0])
    except ValueError:
        print(f"❌ Invalid task ID: {args[0]}. Use a number 1-10.")
        return

    send_task(task_id, dry_run=dry_run)


if __name__ == "__main__":
    main()
