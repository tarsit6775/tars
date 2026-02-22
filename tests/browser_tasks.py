#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║   TARS — 10 Real Browser Tasks: Accounts, API Keys, Workflows   ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Complex, multi-step browser tasks that a real developer does.   ║
║  Each task is designed to stress-test different TARS capabilities.║
║                                                                  ║
║  Usage:                                                          ║
║    python tests/browser_tasks.py              → list all         ║
║    python tests/browser_tasks.py 1            → send task 1      ║
║    python tests/browser_tasks.py 1 --dry-run  → preview only     ║
║    python tests/browser_tasks.py 1 --listen   → send + stream    ║
║                                                                  ║
║  Requires: TARS running (python tars.py) on ports 8420/8421     ║
║                                                                  ║
║  Difficulty ramp:                                                ║
║    Tasks 1-3:   Account creation + API key (single site)         ║
║    Tasks 4-6:   Signup + configure + extract (multi-step)        ║
║    Tasks 7-8:   Multi-tool workflows (browser + terminal + file) ║
║    Tasks 9-10:  Cross-site orchestration (2-3 services)          ║
║                                                                  ║
║  Emails: tarsitgroup@outlook.com / tarsitsales@gmail.com         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import time
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
#  THE 10 TASKS
# ═══════════════════════════════════════════════════════════════

TASKS = [

    # ──────────────────────────────────────────────────────────
    #  TASK 1: GitHub Fine-Grained PAT + New Repo + Webhook
    #  Difficulty: ★★☆☆☆
    #  Tests: Login to existing account, navigate settings,
    #         create token with scopes, repo creation, webhook
    #  Why: GitHub is well-structured — good warmup. Tests
    #       settings navigation and multi-page workflows.
    # ──────────────────────────────────────────────────────────
    {
        "id": 1,
        "name": "GitHub — PAT + Repo + Webhook",
        "difficulty": "★★☆☆☆",
        "tests": [
            "Google-first navigation",
            "Login to existing account",
            "Settings deep navigation",
            "Fine-grained token creation with scopes",
            "Repo creation",
            "Webhook configuration",
            "Store credentials",
        ],
        "estimated_time": "4-6 min",
        "task": (
            "Log into GitHub with tarsitsales@gmail.com (should already be logged in on Chrome). "
            "Then do these 3 things:\n\n"
            "1) CREATE A NEW REPO:\n"
            "   - Name: 'tars-automation-hub'\n"
            "   - Description: 'Central repo for TARS agent automation scripts'\n"
            "   - Make it Private\n"
            "   - Initialize with a README\n"
            "   - Add .gitignore for Python\n"
            "   - Add MIT license\n\n"
            "2) GENERATE A FINE-GRAINED PERSONAL ACCESS TOKEN:\n"
            "   - Go to Settings > Developer settings > Personal access tokens > Fine-grained tokens\n"
            "   - Click 'Generate new token'\n"
            "   - Name: 'tars-agent-token'\n"
            "   - Expiration: 90 days\n"
            "   - Repository access: 'Only select repositories' → select 'tars-automation-hub'\n"
            "   - Permissions: Contents (Read and write), Metadata (Read-only), Webhooks (Read and write)\n"
            "   - Generate and COPY the token (it's only shown once!)\n\n"
            "3) SET UP A WEBHOOK on the repo:\n"
            "   - Go to tars-automation-hub > Settings > Webhooks > Add webhook\n"
            "   - Payload URL: https://tars-production-58a6.up.railway.app/webhook/github\n"
            "   - Content type: application/json\n"
            "   - Secret: 'tars-webhook-secret-2026'\n"
            "   - Events: 'Send me everything'\n"
            "   - Save\n\n"
            "Report back the Personal Access Token. Store token as credentials for 'github'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 2: OpenAI Platform — API Key + Organization + Test Call
    #  Difficulty: ★★★☆☆
    #  Tests: Platform signup/login, billing check, API key creation,
    #         terminal verification with curl
    #  Why: OpenAI has onboarding wizard + org settings — tests
    #       multi-section dashboard navigation
    # ──────────────────────────────────────────────────────────
    {
        "id": 2,
        "name": "OpenAI Platform — API Key + Test Call",
        "difficulty": "★★★☆☆",
        "tests": [
            "Google-first navigation",
            "Platform signup / Google OAuth login",
            "Dashboard section navigation",
            "API key creation with name",
            "Organization ID extraction",
            "Terminal curl verification",
            "Store credentials",
        ],
        "estimated_time": "5-7 min",
        "task": (
            "Sign up for (or log into) the OpenAI developer platform and get me an API key. "
            "Try signing in with Google (tarsitsales@gmail.com) first. "
            "If that doesn't work, sign up with email tarsitgroup@outlook.com, password 'Tars.OpenAI2026!'.\n\n"
            "After you're in the platform dashboard:\n"
            "1) Go to API Keys section (usually under Settings or the sidebar)\n"
            "2) Create a new API key:\n"
            "   - Name: 'tars-agent-key'\n"
            "   - Permissions: All (default)\n"
            "   - COPY the key immediately (starts with 'sk-' — only shown once)\n\n"
            "3) Go to Organization settings and note the Organization ID (starts with 'org-')\n\n"
            "4) Check if there's any billing/credits info visible — report the current balance/status\n\n"
            "5) Verify the key works by running this curl command:\n"
            "   curl https://api.openai.com/v1/models \\\n"
            "     -H 'Authorization: Bearer <YOUR_KEY>' \\\n"
            "     -s | head -50\n"
            "   (If it returns a list of models, the key works)\n\n"
            "Report back: API Key, Organization ID, billing status. "
            "Store everything as credentials for 'openai'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 3: MongoDB Atlas — Free Cluster + DB User + Connection String
    #  Difficulty: ★★★☆☆
    #  Tests: Signup, cluster provisioning (wait for it),
    #         network access config, DB user creation,
    #         connection string extraction
    #  Why: Atlas has a multi-step wizard with provisioning delays.
    #       Tests patience (waiting for cluster) and security config.
    # ──────────────────────────────────────────────────────────
    {
        "id": 3,
        "name": "MongoDB Atlas — Free Cluster + Connection String",
        "difficulty": "★★★☆☆",
        "tests": [
            "Google-first navigation",
            "Signup with Google OAuth",
            "Cluster creation wizard",
            "Wait for provisioning (30-60s)",
            "Network access whitelist",
            "Database user creation",
            "Connection string extraction",
            "Store credentials",
        ],
        "estimated_time": "5-8 min",
        "task": (
            "Create a MongoDB Atlas account and set up a free cluster with a connection string. "
            "Sign up using Google (tarsitsales@gmail.com) or email tarsitgroup@outlook.com, password 'Tars.Mongo2026!'.\n\n"
            "After signup and initial onboarding:\n"
            "1) CREATE A FREE CLUSTER:\n"
            "   - Choose the FREE tier (M0 Sandbox)\n"
            "   - Provider: AWS\n"
            "   - Region: US East (N. Virginia) or closest free region\n"
            "   - Cluster name: 'tars-cluster'\n"
            "   - Create the cluster and WAIT for it to finish provisioning\n\n"
            "2) CONFIGURE NETWORK ACCESS:\n"
            "   - Go to Network Access (Security section)\n"
            "   - Add IP Address → 'Allow Access from Anywhere' (0.0.0.0/0)\n"
            "   - This is for dev/testing — confirm if it asks\n\n"
            "3) CREATE A DATABASE USER:\n"
            "   - Go to Database Access\n"
            "   - Add New Database User\n"
            "   - Username: 'tarsadmin'\n"
            "   - Password: 'TarsDB2026!Atlas'\n"
            "   - Role: Atlas admin (or readWriteAnyDatabase)\n\n"
            "4) GET THE CONNECTION STRING:\n"
            "   - Go back to Database (Clusters)\n"
            "   - Click 'Connect' on your cluster\n"
            "   - Choose 'Connect your application' or 'Drivers'\n"
            "   - Copy the connection string (mongodb+srv://...)\n"
            "   - Replace <password> with the actual password in your report\n\n"
            "Report back the full connection string (with password filled in). "
            "Store as credentials for 'mongodb'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 4: SendGrid — Account + Verified Sender + API Key + Test Email
    #  Difficulty: ★★★☆☆
    #  Tests: Signup, sender identity verification, API key with
    #         scoped permissions, curl-based email send, verification
    #  Why: SendGrid requires sender verification before sending.
    #       Tests understanding of "can't use API until X is done" flows.
    # ──────────────────────────────────────────────────────────
    {
        "id": 4,
        "name": "SendGrid — Verified Sender + API Key + Test Email",
        "difficulty": "★★★☆☆",
        "tests": [
            "Google-first navigation",
            "Signup with onboarding questionnaire",
            "Sender identity verification",
            "Email verification loop",
            "Scoped API key creation",
            "Terminal curl to send test email",
            "End-to-end verification",
            "Store credentials",
        ],
        "estimated_time": "6-8 min",
        "task": (
            "Create a SendGrid account, set up a verified sender, get an API key, "
            "and send a test email to prove it works.\n\n"
            "Use email tarsitgroup@outlook.com, password 'Tars.SendGrid2026!'.\n\n"
            "STEP 1 — SIGN UP:\n"
            "   - Search Google for 'SendGrid signup'\n"
            "   - Fill in the signup form (name: Tars Agent, company: TARS Dev)\n"
            "   - Complete any onboarding questionnaire (select: developer, sending transactional email, <10k emails/month)\n"
            "   - Verify email if needed\n\n"
            "STEP 2 — VERIFY A SENDER:\n"
            "   - Go to Settings > Sender Authentication (or Marketing > Senders)\n"
            "   - Click 'Verify a Single Sender'\n"
            "   - From Name: 'TARS Agent', From Email: tarsitgroup@outlook.com\n"
            "   - Reply To: tarsitgroup@outlook.com\n"
            "   - Company: TARS Dev, Address: 123 Main St, City: San Francisco, State: CA, Zip: 94105, Country: US\n"
            "   - Save, then check tarsitgroup@outlook.com inbox for the verification email\n"
            "   - Use read_otp or check Mail.app for the SendGrid verification link\n"
            "   - Click the verification link to confirm\n\n"
            "STEP 3 — CREATE API KEY:\n"
            "   - Go to Settings > API Keys\n"
            "   - Create an API key named 'tars-mailer' with 'Full Access'\n"
            "   - COPY the key immediately (only shown once, starts with 'SG.')\n\n"
            "STEP 4 — SEND TEST EMAIL:\n"
            "   - Run this curl command to send a test email:\n"
            "     curl -X POST 'https://api.sendgrid.com/v3/mail/send' \\\n"
            "       -H 'Authorization: Bearer <YOUR_API_KEY>' \\\n"
            "       -H 'Content-Type: application/json' \\\n"
            "       -d '{\"personalizations\":[{\"to\":[{\"email\":\"tarsitgroup@outlook.com\"}]}],\"from\":{\"email\":\"tarsitgroup@outlook.com\"},\"subject\":\"TARS SendGrid Test\",\"content\":[{\"type\":\"text/plain\",\"value\":\"SendGrid API key works!\"}]}'\n"
            "   - Check if the response is 202 Accepted\n\n"
            "Report: API key, sender verification status, test email result. "
            "Store the API key as credentials for 'sendgrid'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 5: Railway — Deploy Postgres + Redis + Get Env Vars
    #  Difficulty: ★★★★☆
    #  Tests: GitHub OAuth, project creation, service addition from
    #         marketplace, environment variable extraction, multi-service
    #  Why: Railway's UI has a drag-and-drop canvas — tests interacting
    #       with non-standard web UIs. Multiple services = multi-step.
    # ──────────────────────────────────────────────────────────
    {
        "id": 5,
        "name": "Railway — Postgres + Redis Deploy + Env Vars",
        "difficulty": "★★★★☆",
        "tests": [
            "Google-first navigation",
            "GitHub OAuth login",
            "Project canvas interaction",
            "Marketplace service addition",
            "Environment variable extraction",
            "Multi-service configuration",
            "Connection URL extraction",
            "Store credentials",
        ],
        "estimated_time": "6-10 min",
        "task": (
            "Create a Railway project and deploy Postgres + Redis services. "
            "Sign in with GitHub OAuth (already logged in on Chrome).\n\n"
            "STEP 1 — CREATE PROJECT:\n"
            "   - Search Google for 'Railway app deploy'\n"
            "   - Sign in with GitHub\n"
            "   - Click 'New Project'\n"
            "   - Name it 'tars-infra'\n\n"
            "STEP 2 — ADD POSTGRES:\n"
            "   - In the project canvas, click '+ New' or 'Add Service'\n"
            "   - Choose 'Database' → 'PostgreSQL'\n"
            "   - Wait for it to provision (usually instant)\n"
            "   - Click on the Postgres service\n"
            "   - Go to the 'Variables' or 'Connect' tab\n"
            "   - Copy: DATABASE_URL, PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE\n\n"
            "STEP 3 — ADD REDIS:\n"
            "   - Click '+ New' again\n"
            "   - Choose 'Database' → 'Redis'\n"
            "   - Wait for provision\n"
            "   - Click on Redis service → Variables\n"
            "   - Copy: REDIS_URL\n\n"
            "STEP 4 — PROJECT SETTINGS:\n"
            "   - Go to project Settings\n"
            "   - Note the Project ID\n"
            "   - Check if there's an API token option (Settings > Tokens)\n\n"
            "Report back ALL connection strings (DATABASE_URL, REDIS_URL) and the Project ID. "
            "Store everything as credentials for 'railway'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 6: Netlify — Deploy Site from GitHub + Custom Headers + Functions
    #  Difficulty: ★★★★☆
    #  Tests: OAuth signup, Git repo connection, deploy settings,
    #         custom headers config, serverless function setup
    #  Why: Tests full deploy pipeline with configuration and
    #       file-based setup (netlify.toml) via the web UI
    # ──────────────────────────────────────────────────────────
    {
        "id": 6,
        "name": "Netlify — Deploy from GitHub + API Token",
        "difficulty": "★★★★☆",
        "tests": [
            "Google-first navigation",
            "GitHub OAuth signup",
            "Git repo connection",
            "Build & deploy settings",
            "Deploy monitoring",
            "Personal access token creation",
            "Site URL extraction",
            "Store credentials",
        ],
        "estimated_time": "6-10 min",
        "task": (
            "Create a Netlify account, deploy the GitHub repo we created earlier, "
            "and generate a personal access token.\n\n"
            "Sign up via GitHub OAuth (already logged in on Chrome). "
            "If GitHub OAuth doesn't work, use email tarsitgroup@outlook.com, password 'Tars.Netlify2026!'.\n\n"
            "STEP 1 — SIGN UP & LINK GITHUB:\n"
            "   - Search Google for 'Netlify signup'\n"
            "   - Sign up with GitHub\n"
            "   - Authorize Netlify to access your repos\n\n"
            "STEP 2 — DEPLOY A SITE:\n"
            "   - Click 'Add new site' → 'Import an existing project'\n"
            "   - Select GitHub as the provider\n"
            "   - Choose the repo 'tars-automation-hub' (created in Task 1)\n"
            "   - If that repo doesn't exist, deploy any available repo\n"
            "   - Build settings: leave defaults (or set Build command: empty, Publish directory: '.')\n"
            "   - Click 'Deploy site'\n"
            "   - Wait for the deploy to complete\n"
            "   - Note the live site URL (something.netlify.app)\n\n"
            "STEP 3 — GET PERSONAL ACCESS TOKEN:\n"
            "   - Go to User Settings (click avatar → User Settings)\n"
            "   - Go to Applications → Personal access tokens\n"
            "   - Click 'New access token'\n"
            "   - Description: 'tars-deploy-token'\n"
            "   - Expiration: choose the longest available\n"
            "   - Generate and COPY the token\n\n"
            "STEP 4 — GET SITE API ID:\n"
            "   - Go back to the deployed site\n"
            "   - Go to Site configuration > General\n"
            "   - Note the API ID (Site ID)\n\n"
            "Report back: Site URL, Personal Access Token, Site API ID. "
            "Store as credentials for 'netlify'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 7: Airtable — Base + Table + Fields + API Token + Test Query
    #  Difficulty: ★★★★☆
    #  Tests: Signup, base creation, custom field configuration,
    #         personal access token, API verification via curl
    #  Why: Airtable's field configuration is drag-and-drop with
    #       custom types — tests interacting with rich form builders
    # ──────────────────────────────────────────────────────────
    {
        "id": 7,
        "name": "Airtable — Base + Custom Fields + API Token + Test Query",
        "difficulty": "★★★★☆",
        "tests": [
            "Google-first navigation",
            "Account creation",
            "Base/table creation",
            "Custom field configuration",
            "Record insertion",
            "Personal access token generation",
            "API verification via curl",
            "Store credentials",
        ],
        "estimated_time": "7-10 min",
        "task": (
            "Create an Airtable account, build a structured base, generate an API token, "
            "and verify it works with a curl call.\n\n"
            "Sign up with Google (tarsitsales@gmail.com) or email tarsitgroup@outlook.com, password 'Tars.Airtable2026!'.\n\n"
            "STEP 1 — CREATE A BASE:\n"
            "   - After signup, click 'Start from scratch' (not a template)\n"
            "   - Name the base: 'TARS Task Tracker'\n\n"
            "STEP 2 — CONFIGURE THE TABLE:\n"
            "   - Rename the first table to 'Tasks'\n"
            "   - Set up these fields (columns):\n"
            "     a) 'Task Name' (Single line text) — already exists, rename 'Name' to 'Task Name'\n"
            "     b) 'Status' (Single select) — options: 'To Do', 'In Progress', 'Done', 'Blocked'\n"
            "     c) 'Priority' (Single select) — options: 'Low', 'Medium', 'High', 'Critical'\n"
            "     d) 'Assigned To' (Single line text)\n"
            "     e) 'Due Date' (Date field)\n"
            "     f) 'Notes' (Long text)\n\n"
            "STEP 3 — ADD SAMPLE RECORDS:\n"
            "   - Add 3 rows:\n"
            "     Row 1: Task='Set up CI/CD pipeline', Status='To Do', Priority='High', Assigned='TARS'\n"
            "     Row 2: Task='Write API documentation', Status='In Progress', Priority='Medium', Assigned='TARS'\n"
            "     Row 3: Task='Deploy to production', Status='Blocked', Priority='Critical', Assigned='Abdullah'\n\n"
            "STEP 4 — GENERATE PERSONAL ACCESS TOKEN:\n"
            "   - Go to airtable.com/create/tokens (search Google for 'Airtable create token')\n"
            "   - Click 'Create new token'\n"
            "   - Name: 'tars-api-token'\n"
            "   - Scopes: data.records:read, data.records:write, schema.bases:read\n"
            "   - Access: the 'TARS Task Tracker' base\n"
            "   - Create and COPY the token (starts with 'pat')\n\n"
            "STEP 5 — GET BASE ID & VERIFY:\n"
            "   - Go to airtable.com/api or check the URL when viewing the base\n"
            "   - The base ID is in the URL (starts with 'app')\n"
            "   - Verify with curl:\n"
            "     curl 'https://api.airtable.com/v0/<BASE_ID>/Tasks' \\\n"
            "       -H 'Authorization: Bearer <TOKEN>' \\\n"
            "       -s | head -80\n"
            "   - Should return the 3 records we created\n\n"
            "Report: API Token, Base ID, verification result. "
            "Store as credentials for 'airtable'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 8: Linear — Workspace + Team + Project + Issues + API Key
    #  Difficulty: ★★★★☆
    #  Tests: Signup, workspace/team creation, project config,
    #         issue creation with labels, personal API key generation
    #  Why: Linear has a very polished UI with keyboard shortcuts
    #       and custom workflows — tests navigating a pro tool
    # ──────────────────────────────────────────────────────────
    {
        "id": 8,
        "name": "Linear — Workspace + Project + Issues + API Key",
        "difficulty": "★★★★☆",
        "tests": [
            "Google-first navigation",
            "Google OAuth signup",
            "Workspace setup wizard",
            "Team creation",
            "Project creation with details",
            "Issue creation (3 issues)",
            "Label creation",
            "API key generation",
            "Store credentials",
        ],
        "estimated_time": "7-10 min",
        "task": (
            "Create a Linear account, set up a workspace with a project, "
            "create issues, and generate an API key.\n\n"
            "Sign up with Google (tarsitsales@gmail.com) or email tarsitgroup@outlook.com, password 'Tars.Linear2026!'.\n\n"
            "STEP 1 — WORKSPACE SETUP:\n"
            "   - Search Google for 'Linear app signup'\n"
            "   - Sign up and create a new workspace: 'TARS Engineering'\n"
            "   - Skip team member invitations\n"
            "   - Set up a team called 'Core' (or use the default)\n\n"
            "STEP 2 — CREATE A PROJECT:\n"
            "   - In the sidebar, go to Projects\n"
            "   - Create a new project:\n"
            "     Name: 'TARS v6 Launch'\n"
            "     Description: 'Ship TARS v6 with full browser automation, email, and multi-agent orchestration'\n"
            "     Status: 'In Progress'\n"
            "     Target date: 3 months from now\n"
            "     Team: Core\n\n"
            "STEP 3 — CREATE ISSUES:\n"
            "   - Create 5 issues in the project 'TARS v6 Launch':\n"
            "     1) Title: 'Browser agent CAPTCHA solver reliability'\n"
            "        Priority: Urgent, Status: In Progress\n"
            "     2) Title: 'Multi-agent orchestration budget system'\n"
            "        Priority: High, Status: Todo\n"
            "     3) Title: 'Dashboard real-time event streaming'\n"
            "        Priority: Medium, Status: Done\n"
            "     4) Title: 'Email attachment delivery via iMessage'\n"
            "        Priority: High, Status: In Progress\n"
            "     5) Title: 'Self-healing error tracker with fix registry'\n"
            "        Priority: Medium, Status: Done\n\n"
            "STEP 4 — GENERATE API KEY:\n"
            "   - Go to Settings (gear icon) → Account → API\n"
            "   - Or go to linear.app/settings/api\n"
            "   - Create a Personal API Key\n"
            "   - Label: 'tars-integration'\n"
            "   - Copy the key (starts with 'lin_api_')\n\n"
            "Report: API Key, Workspace URL, number of issues created. "
            "Store as credentials for 'linear'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 9: Render — Web Service from GitHub + Env Vars + PostgreSQL
    #  Difficulty: ★★★★★
    #  Tests: OAuth signup, service creation from repo, build config,
    #         env var management, database addon, multi-service linking
    #  Why: Render has a similar flow to Railway but with different UI
    #       patterns. Linking services via env vars is a real workflow.
    # ──────────────────────────────────────────────────────────
    {
        "id": 9,
        "name": "Render — Web Service + PostgreSQL + Env Linking",
        "difficulty": "★★★★★",
        "tests": [
            "Google-first navigation",
            "GitHub OAuth signup",
            "Web service creation from repo",
            "Build & deploy configuration",
            "Environment variable management",
            "PostgreSQL database creation",
            "Internal connection URL linking",
            "Deploy monitoring",
            "Service URL extraction",
            "Store credentials",
        ],
        "estimated_time": "8-12 min",
        "task": (
            "Create a Render account, deploy a web service connected to a PostgreSQL database, "
            "and link them via environment variables.\n\n"
            "Sign up with GitHub OAuth (already logged in on Chrome). "
            "If not available, use email tarsitgroup@outlook.com, password 'Tars.Render2026!'.\n\n"
            "STEP 1 — CREATE POSTGRESQL DATABASE:\n"
            "   - After signing up, go to Dashboard\n"
            "   - Click 'New +' → 'PostgreSQL'\n"
            "   - Name: 'tars-db'\n"
            "   - Region: US East (Ohio) or Oregon\n"
            "   - Plan: Free\n"
            "   - Create Database\n"
            "   - Wait for it to be available\n"
            "   - Note the Internal Database URL and External Database URL\n\n"
            "STEP 2 — CREATE WEB SERVICE:\n"
            "   - Click 'New +' → 'Web Service'\n"
            "   - Connect your GitHub account if not already\n"
            "   - Select the 'tars-automation-hub' repo (from Task 1)\n"
            "   - If not available, use any public repo or select 'Deploy an existing image'\n"
            "   - Name: 'tars-api'\n"
            "   - Region: same as database\n"
            "   - Branch: main\n"
            "   - Runtime: Python 3 (or Docker)\n"
            "   - Build Command: pip install -r requirements.txt\n"
            "   - Start Command: python server.py\n"
            "   - Plan: Free\n\n"
            "STEP 3 — LINK DATABASE TO SERVICE:\n"
            "   - In the web service settings, go to 'Environment'\n"
            "   - Add environment variable:\n"
            "     Key: DATABASE_URL\n"
            "     Value: (paste the Internal Database URL from Step 1)\n"
            "   - Add another:\n"
            "     Key: TARS_MODE\n"
            "     Value: production\n\n"
            "STEP 4 — DEPLOY & GET URL:\n"
            "   - Trigger a manual deploy or wait for auto-deploy\n"
            "   - Note the service URL (something.onrender.com)\n"
            "   - Go to the database dashboard and copy the connection details\n\n"
            "Report: Service URL, Internal DB URL, External DB URL, any API keys or credentials. "
            "Store everything as credentials for 'render'."
        ),
    },

    # ──────────────────────────────────────────────────────────
    #  TASK 10: Full Stack — Upstash Redis + QStash Messaging + Vercel Edge
    #  Difficulty: ★★★★★
    #  Tests: Multi-site account creation, REST API key extraction,
    #         QStash messaging setup, Vercel Edge Function deployment,
    #         end-to-end webhook verification across 2 platforms
    #  Why: This is the most complex task — involves creating accounts
    #       on 2 platforms, linking them via webhooks, and verifying
    #       the connection end-to-end. Tests cross-platform orchestration.
    # ──────────────────────────────────────────────────────────
    {
        "id": 10,
        "name": "Upstash Redis + QStash — Cross-Platform Setup + Test",
        "difficulty": "★★★★★",
        "tests": [
            "Google-first navigation",
            "Multi-platform account creation",
            "Redis database provisioning",
            "REST API token extraction",
            "QStash messaging setup",
            "Terminal verification with curl",
            "Cross-platform webhook linking",
            "End-to-end verification",
            "Store credentials for multiple services",
        ],
        "estimated_time": "10-15 min",
        "task": (
            "Create an Upstash account and set up both a Redis database and QStash messaging. "
            "Then verify both work with curl commands.\n\n"
            "Sign up with Google (tarsitsales@gmail.com) or GitHub OAuth. "
            "If neither works, use email tarsitgroup@outlook.com, password 'Tars.Upstash2026!'.\n\n"
            "STEP 1 — SIGN UP ON UPSTASH:\n"
            "   - Search Google for 'Upstash console signup'\n"
            "   - Sign up (they support GitHub/Google OAuth)\n\n"
            "STEP 2 — CREATE REDIS DATABASE:\n"
            "   - After signup, go to Redis section\n"
            "   - Click 'Create Database'\n"
            "   - Name: 'tars-cache'\n"
            "   - Region: US-East-1 (or closest)\n"
            "   - Type: Regional\n"
            "   - TLS: Enabled (default)\n"
            "   - Eviction: Enabled\n"
            "   - Create\n"
            "   - Once created, go to the database details\n"
            "   - Copy: UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN\n\n"
            "STEP 3 — VERIFY REDIS WITH CURL:\n"
            "   - Run this to test:\n"
            "     curl '<UPSTASH_REDIS_REST_URL>/set/tars-test/hello-from-tars' \\\n"
            "       -H 'Authorization: Bearer <UPSTASH_REDIS_REST_TOKEN>'\n"
            "   - Then read it back:\n"
            "     curl '<UPSTASH_REDIS_REST_URL>/get/tars-test' \\\n"
            "       -H 'Authorization: Bearer <UPSTASH_REDIS_REST_TOKEN>'\n"
            "   - Should return 'hello-from-tars'\n\n"
            "STEP 4 — SET UP QSTASH:\n"
            "   - In the Upstash console, go to QStash section\n"
            "   - Note the QSTASH_TOKEN (shown on the QStash dashboard)\n"
            "   - Also note the QSTASH_CURRENT_SIGNING_KEY and QSTASH_NEXT_SIGNING_KEY\n\n"
            "STEP 5 — VERIFY QSTASH:\n"
            "   - Send a test message to a webhook testing service:\n"
            "     curl -X POST 'https://qstash.upstash.io/v2/publish/https://httpbin.org/post' \\\n"
            "       -H 'Authorization: Bearer <QSTASH_TOKEN>' \\\n"
            "       -H 'Content-Type: application/json' \\\n"
            "       -d '{\"message\": \"Hello from TARS via QStash\"}'\n"
            "   - Check the response for a messageId (confirms QStash works)\n\n"
            "Report ALL credentials:\n"
            "  - UPSTASH_REDIS_REST_URL\n"
            "  - UPSTASH_REDIS_REST_TOKEN\n"
            "  - QSTASH_TOKEN\n"
            "  - QSTASH_CURRENT_SIGNING_KEY\n"
            "  - QSTASH_NEXT_SIGNING_KEY\n"
            "  - Verification results (Redis SET/GET and QStash publish)\n\n"
            "Store Redis creds as 'upstash_redis' and QStash creds as 'upstash_qstash'."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════
#  TASK DISPLAY & RUNNER
# ═══════════════════════════════════════════════════════════════

# ANSI colors
C = {
    "h":  "\033[1;36m",   # cyan bold (headers)
    "g":  "\033[1;32m",   # green bold (success)
    "y":  "\033[1;33m",   # yellow bold (warning)
    "r":  "\033[1;31m",   # red bold (error)
    "d":  "\033[0;37m",   # dim (descriptions)
    "b":  "\033[1m",      # bold
    "0":  "\033[0m",      # reset
}


def list_tasks():
    """Display all 10 tasks with metadata."""
    print()
    print(f"{C['h']}{'═' * 70}")
    print(f"  TARS — 10 Browser Tasks: Accounts, API Keys & Workflows")
    print(f"{'═' * 70}{C['0']}")

    for t in TASKS:
        diff_color = C['g'] if t['difficulty'].count('★') <= 2 else C['y'] if t['difficulty'].count('★') <= 4 else C['r']
        print(f"\n  {C['d']}{'─' * 66}{C['0']}")
        print(f"  {C['b']}Task {t['id']:2d}{C['0']} │ {diff_color}{t['difficulty']}{C['0']} │ {C['b']}{t['name']}{C['0']}")
        print(f"         │ {C['d']}Time: ~{t['estimated_time']}{C['0']}")
        print(f"         │ {C['d']}Tests: {', '.join(t['tests'][:3])}{C['0']}")
        if len(t['tests']) > 3:
            print(f"         │ {C['d']}       {', '.join(t['tests'][3:6])}{C['0']}")
        if len(t['tests']) > 6:
            print(f"         │ {C['d']}       {', '.join(t['tests'][6:])}{C['0']}")

    print(f"\n  {C['d']}{'─' * 66}{C['0']}")
    print()
    print(f"  {C['b']}Usage:{C['0']}")
    print(f"    python tests/browser_tasks.py 1              {C['d']}# send task 1 to running TARS{C['0']}")
    print(f"    python tests/browser_tasks.py 1 --dry-run    {C['d']}# preview task 1 only{C['0']}")
    print(f"    python tests/browser_tasks.py 1 --listen     {C['d']}# send + stream live events{C['0']}")
    print()


def preview_task(task):
    """Show task details without sending."""
    print()
    diff_color = C['g'] if task['difficulty'].count('★') <= 2 else C['y'] if task['difficulty'].count('★') <= 4 else C['r']
    print(f"  {C['h']}╔{'═' * 62}╗")
    print(f"  ║  Task {task['id']}: {task['name']:<52s}  ║")
    print(f"  ║  Difficulty: {task['difficulty']:<48s}  ║")
    print(f"  ║  Est. time: {task['estimated_time']:<49s} ║")
    print(f"  ╚{'═' * 62}╝{C['0']}")
    print()
    print(f"  {C['b']}Tests:{C['0']}")
    for t in task['tests']:
        print(f"    • {t}")
    print()
    print(f"  {C['b']}Task text:{C['0']}")
    print(f"  {C['d']}{'─' * 62}{C['0']}")
    for line in task["task"].split("\n"):
        print(f"  {line}")
    print(f"  {C['d']}{'─' * 62}{C['0']}")
    print()


def _get_dashboard_token():
    """Read the dashboard session token from the token file written by server.py."""
    token_path = os.path.join(os.path.dirname(__file__), "..", ".dashboard_token")
    token_path = os.path.abspath(token_path)
    try:
        with open(token_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def send_task_ws(task, listen=False):
    """Send a task to running TARS via WebSocket and optionally stream events."""

    async def _send():
        token = _get_dashboard_token()
        ws_url = "ws://127.0.0.1:8421"
        if token:
            ws_url += f"?token={token}"
        else:
            print(f"  {C['y']}⚠️  No dashboard token found (.dashboard_token). Connection may fail.{C['0']}")

        try:
            ws = await asyncio.wait_for(
                asyncio.ensure_future(
                    __import__('websockets').connect(ws_url)
                ),
                timeout=5,
            )
        except Exception as e:
            print(f"  {C['r']}❌ Cannot connect to TARS on ws://127.0.0.1:8421{C['0']}")
            print(f"  {C['d']}   Make sure TARS is running: .venv/bin/python tars.py{C['0']}")
            print(f"  {C['d']}   Error: {e}{C['0']}")
            return False

        try:
            msg = json.dumps({"type": "send_task", "task": task["task"]})
            await ws.send(msg)
            print(f"  {C['g']}✅ Task {task['id']} sent to TARS!{C['0']}")
            print(f"  {C['d']}   '{task['name']}'{C['0']}")
            print()

            if not listen:
                await ws.close()
                return True

            # Stream live events
            print(f"  {C['h']}📡 Streaming live events (Ctrl+C to stop)...{C['0']}")
            print(f"  {'─' * 62}")

            interesting = {
                "thinking", "tool_use", "tool_result", "agent_step",
                "status_change", "task_received", "imessage_sent",
                "environment_setup", "error_tracked", "auto_fix_available",
            }
            count = 0
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    data = json.loads(raw)
                    evt_type = data.get("type", "?")
                    evt_data = data.get("data", {})

                    if evt_type not in interesting:
                        continue

                    count += 1
                    icon = {
                        "thinking": "🧠",
                        "tool_use": "🔧",
                        "tool_result": "📋",
                        "agent_step": "🤖",
                        "status_change": "📊",
                        "task_received": "📬",
                        "imessage_sent": "💬",
                        "environment_setup": "🖥️",
                        "error_tracked": "⚠️",
                        "auto_fix_available": "🔄",
                    }.get(evt_type, "•")

                    # Compact display
                    summary = ""
                    if evt_type == "thinking":
                        text = evt_data.get("text", evt_data.get("content", ""))
                        summary = text[:120] + "..." if len(text) > 120 else text
                    elif evt_type == "tool_use":
                        name = evt_data.get("name", evt_data.get("tool", "?"))
                        summary = f"{name}({json.dumps(evt_data.get('input', evt_data.get('params', {})))[:80]})"
                    elif evt_type == "tool_result":
                        content = str(evt_data.get("content", ""))
                        ok = "✅" if evt_data.get("success", True) else "❌"
                        summary = f"{ok} {content[:100]}"
                    elif evt_type == "agent_step":
                        summary = f"Step {evt_data.get('step', '?')}: {str(evt_data.get('action', ''))[:80]}"
                    elif evt_type == "status_change":
                        summary = f"{evt_data.get('old', '?')} → {evt_data.get('new', '?')}"
                    else:
                        summary = str(evt_data)[:120]

                    print(f"  {icon} {C['d']}[{evt_type}]{C['0']} {summary}")

                    # Stop on completion signals
                    if evt_type == "status_change" and evt_data.get("new") in ("idle", "error"):
                        print(f"\n  {C['g']}🏁 Task complete! ({count} events){C['0']}")
                        break

                except asyncio.TimeoutError:
                    print(f"\n  {C['y']}⏰ No events for 120s — task may have finished or stalled{C['0']}")
                    break

        except KeyboardInterrupt:
            print(f"\n\n  {C['y']}⏹  Stopped listening ({count} events captured){C['0']}")
        except Exception as e:
            print(f"  {C['r']}Error: {e}{C['0']}")
        finally:
            await ws.close()

        return True

    return asyncio.run(_send())


def main():
    args = sys.argv[1:]

    if not args:
        list_tasks()
        return

    listen = "--listen" in args
    dry_run = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]

    if not args:
        list_tasks()
        return

    if args[0] == "all":
        print(f"  {C['y']}⚠️  Running all 10 tasks sequentially takes 60-90 minutes.{C['0']}")
        print(f"  {C['d']}   Run one at a time: python tests/browser_tasks.py <number>{C['0']}")
        return

    try:
        task_id = int(args[0])
    except ValueError:
        print(f"  {C['r']}❌ Invalid task ID: {args[0]}. Use 1-10.{C['0']}")
        return

    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        print(f"  {C['r']}❌ No task with ID {task_id}. Valid: 1-10.{C['0']}")
        return

    preview_task(task)

    if dry_run:
        print(f"  {C['y']}🔍 DRY RUN — task NOT sent. Remove --dry-run to send.{C['0']}")
        return

    send_task_ws(task, listen=listen)


if __name__ == "__main__":
    main()
