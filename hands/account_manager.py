"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Account Manager                                  ║
╠══════════════════════════════════════════════════════════════╣
║  Manages accounts, credentials, and login sessions across    ║
║  websites. Stores passwords in macOS Keychain (encrypted).   ║
║  Provides login detection, OTP reading, and site playbooks.  ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import subprocess
import logging
import re
import base64
from datetime import datetime

logger = logging.getLogger("TARS")

# ─── Constants ────────────────────────────────────────
KEYCHAIN_SERVICE_PREFIX = "TARS-Account"
ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "accounts.json")

# ─── Known Email Accounts ────────────────────────────
# These are the TARS-managed email accounts available for signups
TARS_EMAILS = {
    "outlook": {
        "email": "tarsitgroup@outlook.com",
        "provider": "outlook",
        "use_for": "signups, Microsoft services, general accounts",
    },
    "gmail": {
        "email": "tarsitsales@gmail.com",
        "provider": "gmail",
        "use_for": "Google Sign-In, Google services, OAuth",
    },
}

# ─── Site Playbooks ──────────────────────────────────
# Structured login/signup flows for common sites.
# The browser agent uses these as step-by-step instructions.
SITE_PLAYBOOKS = {
    "google": {
        "name": "Google",
        "login_url": "https://accounts.google.com/signin",
        "signup_url": "https://accounts.google.com/signup",
        "login_check": {
            "url_pattern": "myaccount.google.com|mail.google.com",
            "js": "document.querySelector('[data-ogsr-up]') !== null || document.querySelector('a[aria-label*=\"Google Account\"]') !== null",
        },
        "login_steps": [
            "goto accounts.google.com/signin",
            "look for email field (usually input[type=email])",
            "type email address",
            "click Next",
            "wait 2s, look for password field",
            "type password",
            "click Next",
            "wait 3s, check if logged in",
        ],
        "signup_steps": [
            "goto accounts.google.com/signup",
            "fill First name, Last name",
            "click Next",
            "fill birthday (month/day/year), gender",
            "click Next",
            "choose 'Create your own Gmail address' if prompted",
            "type desired email",
            "click Next",
            "type password and confirm",
            "click Next, agree to terms",
        ],
        "default_email": "gmail",
    },
    "outlook": {
        "name": "Microsoft / Outlook",
        "login_url": "https://login.live.com",
        "signup_url": "https://signup.live.com",
        "login_check": {
            "url_pattern": "outlook.live.com|office.com",
            "js": "document.querySelector('#O365_MainLink_Me') !== null || document.querySelector('[data-task=\"signout\"]') !== null",
        },
        "login_steps": [
            "goto login.live.com",
            "look for email field",
            "type email address",
            "click Next",
            "wait 2s, look for password field",
            "type password",
            "click Sign in",
            "if 'Stay signed in?' appears, click Yes",
            "wait 3s, check if logged in",
        ],
        "signup_steps": [
            "goto signup.live.com",
            "look for email field",
            "type desired email (e.g. tarsitgroup@outlook.com)",
            "check domain dropdown — select @outlook.com if needed",
            "click Next",
            "type password (must be 8+ chars, mixed case + numbers)",
            "click Next",
            "fill first name and last name",
            "click Next",
            "select country, fill birthday (month/day/year)",
            "click Next",
            "solve CAPTCHA if present (call solve_captcha)",
            "wait for verification or inbox redirect",
        ],
        "default_email": "outlook",
    },
    "github": {
        "name": "GitHub",
        "login_url": "https://github.com/login",
        "signup_url": "https://github.com/signup",
        "login_check": {
            "url_pattern": "github.com",
            "js": "document.querySelector('.AppHeader-user') !== null || document.querySelector('[aria-label=\"Open user navigation menu\"]') !== null",
        },
        "login_steps": [
            "goto github.com/login",
            "type username/email",
            "type password",
            "click Sign in",
            "if 2FA required: check email for code, type it",
            "wait 3s, verify logged in",
        ],
        "signup_steps": [
            "goto github.com/signup",
            "type email when prompted",
            "click Continue",
            "type password when prompted",
            "click Continue",
            "type username when prompted",
            "click Continue",
            "answer email preferences (n)",
            "solve CAPTCHA/puzzle if present",
            "click Create account",
            "check email for verification code",
            "type verification code",
        ],
        "default_email": "gmail",
    },
    "linkedin": {
        "name": "LinkedIn",
        "login_url": "https://www.linkedin.com/login",
        "signup_url": "https://www.linkedin.com/signup",
        "login_check": {
            "url_pattern": "linkedin.com/feed|linkedin.com/in/",
            "js": "document.querySelector('.global-nav__me') !== null || document.querySelector('[data-control-name=\"identity_welcome_message\"]') !== null",
        },
        "login_steps": [
            "goto linkedin.com/login",
            "type email",
            "type password",
            "click Sign in",
            "if verification needed: check email for code",
            "wait 3s, verify logged in",
        ],
        "signup_steps": [
            "goto linkedin.com/signup",
            "type email and password",
            "click Agree & Join",
            "fill first name, last name",
            "click Continue",
            "solve CAPTCHA if present",
            "enter verification code from email",
        ],
        "default_email": "outlook",
    },
    "twitter": {
        "name": "Twitter / X",
        "login_url": "https://x.com/i/flow/login",
        "signup_url": "https://x.com/i/flow/signup",
        "login_check": {
            "url_pattern": "x.com/home|twitter.com/home",
            "js": "document.querySelector('[data-testid=\"SideNav_AccountSwitcher_Button\"]') !== null",
        },
        "login_steps": [
            "goto x.com/i/flow/login",
            "type email/username",
            "click Next",
            "if username verification: type username",
            "type password",
            "click Log in",
            "wait 3s, verify logged in",
        ],
        "default_email": "outlook",
    },
    "reddit": {
        "name": "Reddit",
        "login_url": "https://www.reddit.com/login",
        "signup_url": "https://www.reddit.com/register",
        "login_check": {
            "url_pattern": "reddit.com",
            "js": "document.querySelector('[id*=\"email-collection\"]') === null && (document.cookie.includes('reddit_session') || document.querySelector('button[aria-label*=\"profile\"]') !== null)",
        },
        "login_steps": [
            "goto reddit.com/login",
            "type username",
            "type password",
            "click Log In",
            "wait 3s, verify logged in",
        ],
        "default_email": "outlook",
    },
    "amazon": {
        "name": "Amazon",
        "login_url": "https://www.amazon.com/ap/signin",
        "signup_url": "https://www.amazon.com/ap/register",
        "login_check": {
            "url_pattern": "amazon.com",
            "js": "document.querySelector('#nav-link-accountList')?.textContent?.includes('Sign in') === false",
        },
        "login_steps": [
            "goto amazon.com/ap/signin",
            "type email",
            "click Continue",
            "type password",
            "click Sign-In",
            "if OTP needed: check email for code, type it",
        ],
        "default_email": "outlook",
    },
    "instagram": {
        "name": "Instagram",
        "login_url": "https://www.instagram.com/accounts/login/",
        "signup_url": "https://www.instagram.com/accounts/emailsignup/",
        "login_check": {
            "url_pattern": "instagram.com",
            "js": "document.querySelector('svg[aria-label=\"Home\"]') !== null || window.location.pathname === '/'",
        },
        "login_steps": [
            "goto instagram.com/accounts/login/",
            "look for the page fields",
            "type email into the field with aria-label 'Phone number, username, or email'",
            "type password into the password field",
            "click 'Log in' button",
            "if 'Save Your Login Info?' appears, click 'Save Info' or 'Not Now'",
            "wait 5s, check if home feed loaded (look for Home icon)",
        ],
        "signup_steps": [
            "STEP 1 — INITIAL FORM (all fields on one page):",
            "goto instagram.com/accounts/emailsignup/",
            "look at the page to see all fields",
            "type email into the field with aria-label 'Mobile number or email'",
            "type full name into the field with aria-label 'Full Name'",
            "type username into the field with aria-label 'Username'",
            "type password into the field with aria-label 'Password'",
            "click the 'Sign up' button (it's a button with type=submit)",
            "",
            "STEP 2 — BIRTHDAY PAGE (appears after clicking Sign up):",
            "wait 3s for the birthday page to load",
            "look at the page — you should see 3 dropdown selects for Month, Day, Year",
            "IMPORTANT: These are native <select> elements. Use the select tool:",
            "  select(dropdown='Month', option='January')  — or the desired month",
            "  select(dropdown='Day', option='15')  — or the desired day",
            "  select(dropdown='Year', option='1995')  — or the desired year",
            "After setting all 3 dropdowns, scroll down to see the submit button",
            "The button may say 'Next' OR 'Submit' — look at the page to see the actual text",
            "Click whatever submit button you see (do NOT guess the text — read it from look output)",
            "If you don't see a button, scroll('down') first — it may be below the fold",
            "NEVER navigate back to the signup URL after this point!",
            "",
            "STEP 3 — VERIFICATION CODE:",
            "wait 5s — Instagram will send a verification code to the email",
            "Call read_otp(subject_contains='Instagram', timeout=90) to get the code from Mac Mail",
            "The read_otp tool will poll Mail.app for up to 90 seconds waiting for the email",
            "DO NOT call stuck() or done() here — wait for the code!",
            "",
            "STEP 4 — COMPLETE:",
            "Type the verification code into the confirmation code field",
            "Click 'Next' or 'Confirm'",
            "If 'Turn on Notifications?' appears, click 'Not Now'",
            "Wait 3s, check if home feed loaded",
        ],
        "signup_notes": [
            "Instagram signup is MULTI-PAGE — do NOT try to fill birthday on the first page",
            "The birthday dropdowns are standard <select> elements — use select() tool, NOT click()",
            "After clicking 'Sign up', wait 3s for the birthday page to appear before interacting",
            "The birthday page submit button may say 'Next' OR 'Submit' — ALWAYS look() to check the actual text",
            "You may need to scroll('down') to see the birthday submit button",
            "Use a REAL email (tarsitgroup@outlook.com) — fake @example.com emails get silently rejected",
            "If CAPTCHA appears at any step, call solve_captcha() and wait 5s",
            "If the page seems stuck after Sign up, look() to see what's actually showing — it might be the birthday page",
            "NEVER navigate back to the signup URL after progress — you will lose all progress!",
            "For verification code: call read_otp(subject_contains='Instagram', timeout=90) — it polls Mac Mail automatically",
        ],
        "default_email": "outlook",
    },
    # ── Generic Developer Portal Playbook ──
    # Works for DoorDash, Stripe, Twilio, SendGrid, Shopify, etc.
    "_developer_portal": {
        "name": "Generic Developer Portal",
        "signup_steps": [
            "PHASE 1 — CREATE ACCOUNT:",
            "Navigate to the developer portal signup/register page",
            "Use fill_form() to fill ALL visible fields at once (email, name, password, company)",
            "Use email: tarsitgroup@outlook.com, generate a strong password like 'Tars.Dev2026!'",
            "For company/org name: use 'TARS Dev' or 'Personal Project'",
            "Click the signup/register/create account button",
            "If email verification required: call read_otp(subject_contains='ServiceName', timeout=120)",
            "Type verification code and confirm",
            "",
            "PHASE 2 — COMPLETE PROFILE (if required):",
            "Some portals require profile completion before API access",
            "Fill any required fields: company info, use case, phone (use 0000000000 if optional)",
            "Accept terms of service, developer agreement",
            "Skip optional steps (newsletter, tutorials, onboarding tours)",
            "",
            "PHASE 3 — GET API CREDENTIALS:",
            "Navigate to: Dashboard → API Keys, Apps, Credentials, or Developer Settings",
            "Common paths: /dashboard, /apps, /api-keys, /settings/api, /developers",
            "Look for: 'Create App', 'New Application', 'Generate API Key', 'Get Started'",
            "Click to create a new app/project if needed (name it 'TARS App' or 'My App')",
            "Copy the API Key, Secret Key, Client ID, Client Secret — whatever is shown",
            "Report ALL credentials found in done() summary",
        ],
        "signup_notes": [
            "EFFICIENCY: Use fill_form() to batch-fill ALL form fields in one call",
            "Most developer portals follow: Signup → Verify Email → Dashboard → Create App → API Keys",
            "For 'What are you building?' questions: say 'Personal project / API integration'",
            "For 'Expected API volume': choose the lowest/free tier",
            "Skip onboarding tours/tutorials — click 'Skip', 'Maybe Later', 'X' on modals",
            "API keys are often shown ONCE — copy them immediately and include in done() summary",
            "If the portal has OAuth setup, note the Client ID and Client Secret",
            "Common gotchas: some portals require credit card for API access (report this as stuck)",
        ],
        "default_email": "outlook",
    },
    "doordash": {
        "name": "DoorDash Developer",
        "signup_url": "https://developer.doordash.com/",
        "signup_steps": [
            "PHASE 1 — CREATE DEVELOPER ACCOUNT:",
            "Navigate to developer.doordash.com",
            "Look for 'Get Started', 'Sign Up', or 'Create Account'",
            "Use fill_form() to fill ALL fields at once (email, password, name, company)",
            "Email: tarsitgroup@outlook.com, Password: Tars.Dev2026!",
            "Company: TARS Dev, Use case: 'API Integration'",
            "Click submit/create account",
            "If email verification: call read_otp(subject_contains='DoorDash', timeout=120)",
            "",
            "PHASE 2 — GET API CREDENTIALS:",
            "After login, navigate to developer portal dashboard",
            "Look for 'Create App' or 'API Keys' or 'Credentials'",
            "Create a new application if needed (name: 'TARS App')",
            "Copy: Developer ID, Key ID, Signing Secret",
            "Report all credentials in done() summary",
        ],
        "default_email": "outlook",
    },
    "stripe": {
        "name": "Stripe Developer",
        "signup_url": "https://dashboard.stripe.com/register",
        "signup_steps": [
            "goto dashboard.stripe.com/register",
            "Use fill_form() to fill email, full name, country, password at once",
            "Click 'Create account'",
            "If email verification: call read_otp(subject_contains='Stripe', timeout=120)",
            "After login: navigate to Developers → API Keys",
            "Copy both Publishable Key and Secret Key",
            "Report both keys in done() summary",
        ],
        "default_email": "outlook",
    },
}


# ═══════════════════════════════════════════════════════
#  Keychain Operations (macOS encrypted credential store)
# ═══════════════════════════════════════════════════════

def _keychain_save(service, account, password):
    """Save or update a password in macOS Keychain."""
    keychain_svc = f"{KEYCHAIN_SERVICE_PREFIX}:{service}"
    try:
        # Try to delete existing entry first (update = delete + add)
        subprocess.run(
            ["security", "delete-generic-password", "-s", keychain_svc, "-a", account],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["security", "add-generic-password", "-s", keychain_svc, "-a", account, "-w", password],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True
        logger.warning(f"Keychain save failed: {result.stderr}")
        return False
    except Exception as e:
        logger.warning(f"Keychain save error: {e}")
        return False


def _keychain_get(service, account):
    """Retrieve a password from macOS Keychain."""
    keychain_svc = f"{KEYCHAIN_SERVICE_PREFIX}:{service}"
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", keychain_svc, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def _keychain_delete(service, account):
    """Delete a password from macOS Keychain."""
    keychain_svc = f"{KEYCHAIN_SERVICE_PREFIX}:{service}"
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-s", keychain_svc, "-a", account],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════
#  Accounts JSON (metadata — passwords are in Keychain)
# ═══════════════════════════════════════════════════════

def _load_accounts():
    """Load accounts metadata from JSON file."""
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_accounts(accounts):
    """Save accounts metadata to JSON file."""
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    tmp = ACCOUNTS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(accounts, f, indent=2, default=str)
    os.replace(tmp, ACCOUNTS_FILE)


# ═══════════════════════════════════════════════════════
#  OTP / Verification Code Reader (Apple Mail)
# ═══════════════════════════════════════════════════════

def read_verification_code(from_sender=None, subject_contains=None, timeout=60):
    """Read a verification/OTP code from Mac Mail inbox.
    
    Polls Apple Mail for recent messages matching the criteria,
    extracts numeric codes (4-8 digits) from the message body.
    
    Args:
        from_sender: Filter by sender email (e.g. "noreply@github.com")
        subject_contains: Filter by subject keyword (e.g. "verification")
        timeout: Max seconds to wait for the email to arrive
    
    Returns:
        Standard tool result dict with the code.
    """
    start = time.time()
    poll_interval = 5
    
    while time.time() - start < timeout:
        try:
            # Build AppleScript filter
            sender_filter = ""
            if from_sender:
                sender_filter = f'whose sender contains "{from_sender}"'
            elif subject_contains:
                sender_filter = f'whose subject contains "{subject_contains}"'
            
            # Get recent messages (last 5) from the unified inbox
            # NOTE: Using global "inbox" (not "inbox of acct") because Exchange/IMAP
            # accounts don't have "inbox" as a direct child — they use named mailboxes.
            # The global "inbox" merges all account inboxes and always works.
            script = f'''
            tell application "Mail"
                set recentMsgs to {{}}
                try
                    set msgs to (messages of inbox {sender_filter})
                    if (count of msgs) > 0 then
                        set maxIdx to (count of msgs)
                        if maxIdx > 5 then set maxIdx to 5
                        repeat with i from 1 to maxIdx
                            set msg to item i of msgs
                            set msgDate to date received of msg
                            -- Only messages from last 10 minutes
                            if (current date) - msgDate < 600 then
                                set msgSubject to subject of msg
                                set msgContent to content of msg
                                set msgSender to sender of msg
                                set clipLen to length of msgContent
                                if clipLen > 500 then set clipLen to 500
                                set end of recentMsgs to "FROM: " & msgSender & linefeed & "SUBJECT: " & msgSubject & linefeed & "BODY: " & (text 1 thru clipLen of msgContent) & linefeed & "---"
                            end if
                        end repeat
                    end if
                end try
                if (count of recentMsgs) = 0 then
                    return "NO_MESSAGES"
                end if
                set AppleScript's text item delimiters to linefeed
                return recentMsgs as text
            end tell
            '''
            
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15,
            )
            
            if result.returncode == 0 and result.stdout.strip() != "NO_MESSAGES":
                output = result.stdout.strip()
                
                # Extract verification codes (4-8 digit numbers)
                # Common patterns: "123456", "Your code is 123456", "Code: 123456"
                code_patterns = [
                    r'(?:code|pin|otp|verification|confirm)[\s:]*(\d{4,8})',
                    r'(\d{6})',  # Most common: 6-digit code
                    r'(\d{4,8})',  # Fallback: any 4-8 digit number
                ]
                
                for pattern in code_patterns:
                    matches = re.findall(pattern, output, re.IGNORECASE)
                    if matches:
                        code = matches[0]
                        # Return with context
                        return {
                            "success": True,
                            "content": f"Verification code: {code}",
                            "code": code,
                            "raw_email": output[:500],
                        }
                
                # No code found but emails exist — return the content
                return {
                    "success": True,
                    "content": f"Found emails but no clear verification code. Email content:\n{output[:800]}",
                    "code": None,
                    "raw_email": output[:800],
                }
            
            # No matching emails yet — wait and retry
            time.sleep(poll_interval)
            
        except Exception as e:
            logger.warning(f"OTP reader error: {e}")
            time.sleep(poll_interval)
    
    return {
        "success": False,
        "error": True,
        "content": f"No verification email found within {timeout}s. Check Mail app manually.",
    }


# ═══════════════════════════════════════════════════════
#  Account Manager — Public API
# ═══════════════════════════════════════════════════════

def manage_account(params):
    """Main entry point for account management operations.
    
    Actions:
        store       — Save credentials (password goes to Keychain)
        lookup      — Get credentials for a service
        list        — List all stored accounts
        delete      — Remove an account
        get_playbook — Get login/signup steps for a site
        read_otp    — Read verification code from email
        get_emails  — Get available TARS email addresses
    
    Returns:
        Standard tool result dict: {"success": bool, "content": str}
    """
    action = params.get("action", "").lower()
    
    if action == "store":
        return _action_store(params)
    elif action == "lookup":
        return _action_lookup(params)
    elif action == "list":
        return _action_list(params)
    elif action == "delete":
        return _action_delete(params)
    elif action == "get_playbook":
        return _action_get_playbook(params)
    elif action == "read_otp":
        return _action_read_otp(params)
    elif action == "get_emails":
        return _action_get_emails(params)
    elif action == "generate_credentials":
        return _action_generate_credentials(params)
    elif action == "generate_totp":
        return _action_generate_totp(params)
    else:
        available = "store, lookup, list, delete, get_playbook, read_otp, get_emails, generate_credentials, generate_totp"
        return {
            "success": False,
            "error": True,
            "content": f"Unknown action '{action}'. Available: {available}",
        }


def _action_store(params):
    """Store credentials for a service."""
    service = params.get("service", "").lower().strip()
    username = params.get("username", "").strip()
    password = params.get("password", "").strip()
    
    if not service or not username:
        return {"success": False, "error": True, "content": "Missing 'service' and/or 'username'."}
    
    # Save password to Keychain
    if password:
        saved = _keychain_save(service, username, password)
        if not saved:
            return {"success": False, "error": True, "content": f"Failed to save password to Keychain for {service}/{username}"}
    
    # Save metadata to accounts.json
    accounts = _load_accounts()
    account_key = f"{service}:{username}"
    accounts[account_key] = {
        "service": service,
        "username": username,
        "email": params.get("email", username),
        "display_name": params.get("display_name", ""),
        "created": accounts.get(account_key, {}).get("created", datetime.now().isoformat()),
        "updated": datetime.now().isoformat(),
        "last_login": accounts.get(account_key, {}).get("last_login"),
        "status": params.get("status", "active"),
        "notes": params.get("notes", ""),
        "has_2fa": params.get("has_2fa", False),
        "totp_secret": params.get("totp_secret", accounts.get(account_key, {}).get("totp_secret", "")),
        "recovery_email": params.get("recovery_email", ""),
    }
    _save_accounts(accounts)
    
    logger.info(f"  🔑 Stored credentials for {service}/{username}")
    return {
        "success": True,
        "content": f"Credentials saved for {service} (user: {username}). Password stored in macOS Keychain.",
    }


def _action_lookup(params):
    """Look up credentials for a service."""
    service = params.get("service", "").lower().strip()
    if not service:
        return {"success": False, "error": True, "content": "Missing 'service' parameter."}
    
    accounts = _load_accounts()
    
    # Find all accounts matching this service
    matches = []
    for key, acct in accounts.items():
        if acct["service"] == service:
            # Retrieve password from Keychain
            password = _keychain_get(service, acct["username"])
            matches.append({
                **acct,
                "password": password or "(not in Keychain)",
            })
    
    if not matches:
        # Check if we have a playbook for this service
        playbook = SITE_PLAYBOOKS.get(service)
        suggestion = ""
        if playbook:
            default_email_key = playbook.get("default_email", "outlook")
            default_email = TARS_EMAILS.get(default_email_key, {}).get("email", "tarsitgroup@outlook.com")
            suggestion = f"\n\nTo create one, use deploy_browser_agent with the signup URL: {playbook.get('signup_url', 'N/A')}\nSuggested email: {default_email}"
        
        return {
            "success": True,
            "content": f"No saved account for '{service}'.{suggestion}",
        }
    
    # Format results
    result_lines = [f"Found {len(matches)} account(s) for {service}:\n"]
    for acct in matches:
        result_lines.append(f"  Service:  {acct['service']}")
        result_lines.append(f"  Username: {acct['username']}")
        result_lines.append(f"  Email:    {acct.get('email', acct['username'])}")
        result_lines.append(f"  Password: {acct['password']}")
        if acct.get("display_name"):
            result_lines.append(f"  Name:     {acct['display_name']}")
        result_lines.append(f"  Status:   {acct.get('status', 'active')}")
        result_lines.append(f"  2FA:      {'yes' if acct.get('has_2fa') else 'no'}")
        if acct.get("last_login"):
            result_lines.append(f"  Last login: {acct['last_login']}")
        result_lines.append("")
    
    return {"success": True, "content": "\n".join(result_lines)}


def _action_list(params):
    """List all stored accounts."""
    accounts = _load_accounts()
    
    if not accounts:
        email_list = ", ".join(e["email"] for e in TARS_EMAILS.values())
        return {
            "success": True,
            "content": f"No saved accounts yet.\n\nAvailable emails for new signups: {email_list}\n\nUse manage_account(action='get_playbook', service='...') to get signup steps for a specific site.",
        }
    
    # Group by service
    by_service = {}
    for key, acct in accounts.items():
        svc = acct["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append(acct)
    
    lines = [f"Stored accounts ({len(accounts)} total):\n"]
    for service, accts in sorted(by_service.items()):
        lines.append(f"  {service.upper()}:")
        for acct in accts:
            status = acct.get("status", "active")
            lines.append(f"    • {acct['username']} ({status})")
        lines.append("")
    
    return {"success": True, "content": "\n".join(lines)}


def _action_delete(params):
    """Delete an account."""
    service = params.get("service", "").lower().strip()
    username = params.get("username", "").strip()
    
    if not service or not username:
        return {"success": False, "error": True, "content": "Missing 'service' and/or 'username'."}
    
    # Remove from Keychain
    _keychain_delete(service, username)
    
    # Remove from accounts.json
    accounts = _load_accounts()
    key = f"{service}:{username}"
    if key in accounts:
        del accounts[key]
        _save_accounts(accounts)
        return {"success": True, "content": f"Deleted account {service}/{username} (Keychain + metadata)."}
    
    return {"success": True, "content": f"Account {service}/{username} not found in metadata (Keychain entry removed if existed)."}


def _action_get_playbook(params):
    """Get login/signup playbook for a site."""
    service = params.get("service", "").lower().strip()
    flow = params.get("flow", "login").lower()  # "login" or "signup"
    
    if not service:
        available = ", ".join(sorted(SITE_PLAYBOOKS.keys()))
        return {
            "success": True,
            "content": f"Available site playbooks: {available}\n\nUse: manage_account(action='get_playbook', service='github', flow='signup')",
        }
    
    playbook = SITE_PLAYBOOKS.get(service)
    if not playbook:
        # Fuzzy match
        for key, pb in SITE_PLAYBOOKS.items():
            if service in key or key in service or service in pb["name"].lower():
                playbook = pb
                service = key
                break
    
    if not playbook:
        # Fall back to generic developer portal playbook for unknown services
        playbook = SITE_PLAYBOOKS["_developer_portal"]
        # Customize the name for the requested service
        playbook = {**playbook, "name": f"{service.title()} (using generic developer portal playbook)"}
        available = ", ".join(sorted(k for k in SITE_PLAYBOOKS.keys() if not k.startswith("_")))
        # Still return the generic playbook — it works for most developer portals
    
    # Check if we already have credentials for this service
    accounts = _load_accounts()
    existing = [a for a in accounts.values() if a["service"] == service]
    
    # Get the recommended email
    default_email_key = playbook.get("default_email", "outlook")
    default_email = TARS_EMAILS.get(default_email_key, {}).get("email", "tarsitgroup@outlook.com")
    
    lines = [f"{'Signup' if flow == 'signup' else 'Login'} playbook for {playbook['name']}:\n"]
    
    if existing:
        lines.append(f"⚡ Existing account(s) found:")
        for acct in existing:
            password = _keychain_get(service, acct["username"])
            lines.append(f"   • {acct['username']} (password: {password or 'not in Keychain'})")
        lines.append("")
    
    if flow == "signup":
        lines.append(f"URL: {playbook.get('signup_url', 'N/A')}")
        lines.append(f"Recommended email: {default_email}")
        lines.append(f"\nSteps:")
        for i, step in enumerate(playbook.get("signup_steps", []), 1):
            lines.append(f"  {i}. {step}")
    else:
        lines.append(f"URL: {playbook.get('login_url', 'N/A')}")
        if not existing:
            lines.append(f"\n⚠️ No stored credentials — you may need to sign up first.")
            lines.append(f"Signup URL: {playbook.get('signup_url', 'N/A')}")
        lines.append(f"\nSteps:")
        for i, step in enumerate(playbook.get("login_steps", []), 1):
            lines.append(f"  {i}. {step}")
    
    lines.append(f"\n💡 After success, store credentials with:")
    lines.append(f"   manage_account(action='store', service='{service}', username='...', password='...')")
    
    return {"success": True, "content": "\n".join(lines)}


def _action_generate_credentials(params):
    """Generate a complete set of credentials for account creation."""
    try:
        from hands.credential_gen import generate_credentials
        service = params.get("service", "")
        flow = params.get("flow", "signup")
        return generate_credentials(service=service, flow=flow)
    except Exception as e:
        return {"success": False, "error": True, "content": f"Failed to generate credentials: {e}"}


def _action_read_otp(params):
    """Read a verification/OTP code from email."""
    from_sender = params.get("from_sender")
    subject = params.get("subject_contains")
    timeout = params.get("timeout", 60)
    
    if not from_sender and not subject:
        return {
            "success": False,
            "error": True,
            "content": "Provide 'from_sender' (e.g. 'noreply@github.com') and/or 'subject_contains' (e.g. 'verification') to filter emails.",
        }
    
    return read_verification_code(
        from_sender=from_sender,
        subject_contains=subject,
        timeout=timeout,
    )


def _action_get_emails(params):
    """Get available TARS email addresses for account creation."""
    lines = ["Available TARS email accounts:\n"]
    for key, info in TARS_EMAILS.items():
        lines.append(f"  {key.upper()}: {info['email']}")
        lines.append(f"    Use for: {info['use_for']}")
        lines.append("")
    
    lines.append("Tip: Use Outlook for general signups, Gmail for Google Sign-In / OAuth.")
    return {"success": True, "content": "\n".join(lines)}


def _action_generate_totp(params):
    """Generate a TOTP code from a stored secret.

    When 2FA/MFA is set up, the site gives a TOTP secret (base32 string).
    Store it with manage_account('store', service='...', totp_secret='...').
    Then call manage_account('generate_totp', service='...') to get the current code.

    This replaces Google Authenticator / Authy — TARS generates codes itself.
    """
    service = params.get("service", "")
    secret = params.get("totp_secret", "")

    if not service and not secret:
        return {"success": False, "error": True, "content": "Need 'service' (to look up stored secret) or 'totp_secret' (direct)."}

    # If no direct secret, look up from stored accounts
    if not secret:
        accounts = _load_accounts()
        for acct in accounts.values():
            if acct.get("service", "").lower() == service.lower():
                secret = acct.get("totp_secret", "")
                break
        if not secret:
            return {"success": False, "error": True, "content": f"No TOTP secret stored for '{service}'. Store it first with manage_account('store', service='{service}', totp_secret='YOUR_SECRET')."}

    try:
        import hmac
        import hashlib
        import struct

        # Clean the secret — remove spaces, dashes, uppercase
        secret = secret.replace(" ", "").replace("-", "").upper()

        # Base32 decode
        # Pad to multiple of 8
        padding = 8 - len(secret) % 8
        if padding != 8:
            secret += "=" * padding

        key = base64.b32decode(secret)

        # TOTP: time-based counter (30-second window)
        counter = int(time.time()) // 30
        counter_bytes = struct.pack(">Q", counter)

        # HMAC-SHA1
        hmac_result = hmac.new(key, counter_bytes, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_result[-1] & 0x0F
        code = struct.unpack(">I", hmac_result[offset:offset + 4])[0]
        code = code & 0x7FFFFFFF
        code = code % 1000000

        # Time remaining in current window
        remaining = 30 - (int(time.time()) % 30)

        totp_code = str(code).zfill(6)
        return {
            "success": True,
            "content": f"TOTP code: {totp_code} (valid for {remaining}s). Type this into the 2FA/MFA field now.",
            "code": totp_code,
            "remaining_seconds": remaining,
        }

    except Exception as e:
        return {"success": False, "error": True, "content": f"TOTP generation failed: {e}. Make sure the secret is a valid base32 string."}



# ═══════════════════════════════════════════════════════
#  Browser Agent Helper — Generate task instructions
# ═══════════════════════════════════════════════════════

def build_browser_task(service, flow="login", extra_instructions=""):
    """Build a detailed browser agent task string for login/signup.
    
    This is called by the brain/executor to construct the task string
    passed to deploy_browser_agent, including credentials and playbook steps.
    
    Args:
        service: Site name (e.g. "github", "outlook")
        flow: "login" or "signup"
        extra_instructions: Additional task context
    
    Returns:
        A detailed task string with all steps and credentials.
    """
    playbook = SITE_PLAYBOOKS.get(service.lower())
    if not playbook:
        return f"{flow.title()} to {service}. {extra_instructions}"
    
    accounts = _load_accounts()
    existing = [a for a in accounts.values() if a["service"] == service.lower()]
    
    parts = []
    
    if flow == "login" and existing:
        acct = existing[0]
        password = _keychain_get(service.lower(), acct["username"])
        parts.append(f"Log in to {playbook['name']}.")
        parts.append(f"URL: {playbook['login_url']}")
        parts.append(f"Email/Username: {acct['username']}")
        if password:
            parts.append(f"Password: {password}")
        parts.append("")
        parts.append("Steps:")
        for i, step in enumerate(playbook.get("login_steps", []), 1):
            parts.append(f"  {i}. {step}")
    elif flow == "signup":
        default_email_key = playbook.get("default_email", "outlook")
        email = TARS_EMAILS.get(default_email_key, {}).get("email", "tarsitgroup@outlook.com")
        parts.append(f"Create a new account on {playbook['name']}.")
        parts.append(f"URL: {playbook['signup_url']}")
        parts.append(f"Email to use: {email}")
        parts.append("")
        parts.append("Steps:")
        for i, step in enumerate(playbook.get("signup_steps", []), 1):
            parts.append(f"  {i}. {step}")
        parts.append("")
        parts.append("IMPORTANT: After account creation, save the credentials by reporting them in your done() summary.")
    else:
        parts.append(f"Log in to {playbook['name']}.")
        parts.append(f"URL: {playbook['login_url']}")
        parts.append("No stored credentials found — you may need to sign up first.")
    
    if extra_instructions:
        parts.append(f"\nAdditional: {extra_instructions}")
    
    parts.append("\nIf CAPTCHA appears, call solve_captcha() and wait 3 seconds.")
    parts.append("If verification code needed, call done() with what you need — the brain will read OTP from email.")
    
    return "\n".join(parts)
