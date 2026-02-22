"""
╔══════════════════════════════════════════════════════════════╗
║      TARS — Smart Credential Generator                       ║
╠══════════════════════════════════════════════════════════════╣
║  Auto-generates secure passwords, usernames, and fills       ║
║  common form defaults so the brain doesn't need to ask       ║
║  Abdullah for every signup.                                  ║
║                                                              ║
║  Returns the standard TARS tool shape:                       ║
║    {"success": True, "content": "..."}                       ║
╚══════════════════════════════════════════════════════════════╝
"""

import random
import string
import json
import os
from datetime import datetime, timedelta

import logging
logger = logging.getLogger("TARS")


# ═══════════════════════════════════════════════════════
#  TARS Email Accounts (canonical source)
# ═══════════════════════════════════════════════════════

TARS_EMAILS = {
    "outlook": {
        "email": "tarsitgroup@outlook.com",
        "use_for": "General signups, developer portals, most services",
    },
    "gmail": {
        "email": "tarsitsales@gmail.com",
        "use_for": "Google Sign-In, OAuth, Google-related services",
    },
}

# Default identity for signups
TARS_IDENTITY_DEFAULTS = {
    "first_name": "Tars",
    "last_name": "Agent",
    "full_name": "Tars Agent",
    "company": "TARS Dev",
    "job_title": "Software Engineer",
    "phone": "",  # No phone by default
    "website": "https://github.com/tarsagent",
    "country": "United States",
    "city": "San Francisco",
    "state": "California",
    "zip": "94105",
}


def generate_password(service="", length=16, require_special=True):
    """Generate a secure, site-compatible password.

    Most sites require: uppercase, lowercase, digit, special char.
    Some sites restrict which special chars are allowed.

    Args:
        service: Site name (for site-specific rules)
        length: Password length (default 16, minimum 12)
        require_special: Whether to include special characters

    Returns:
        A secure password string.
    """
    length = max(length, 12)

    # Some sites restrict special chars
    restricted_sites = {
        "instagram": "!@#$%",
        "facebook": "!@#$%^&*",
        "twitter": "!@#$%^&*",
    }
    special_chars = restricted_sites.get(service.lower(), "!@#$%^&*._-")

    # Guarantee at least one of each required type
    password_chars = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
    ]
    if require_special:
        password_chars.append(random.choice(special_chars))

    # Fill remaining with mixed characters
    all_chars = string.ascii_letters + string.digits
    if require_special:
        all_chars += special_chars

    remaining = length - len(password_chars)
    password_chars.extend(random.choice(all_chars) for _ in range(remaining))

    # Shuffle to randomize position of guaranteed chars
    random.shuffle(password_chars)
    return "".join(password_chars)


def generate_username(service="", base="tarsagent"):
    """Generate a unique username for a service.

    Args:
        service: Site name (for format preferences)
        base: Base username to build from

    Returns:
        A username string (e.g., "tarsagent2026", "tars_dev_42")
    """
    suffix = random.randint(100, 9999)

    # Some patterns
    patterns = [
        f"{base}{suffix}",
        f"{base}_{suffix}",
        f"{base}{datetime.now().year}",
        f"{base}dev{suffix}",
    ]

    return random.choice(patterns)


def generate_birthday(min_age=21, max_age=35):
    """Generate a random valid birthday.

    Returns:
        dict with year, month, day as strings.
    """
    age = random.randint(min_age, max_age)
    birth_year = datetime.now().year - age
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)  # Safe for all months

    return {
        "year": str(birth_year),
        "month": str(birth_month),
        "day": str(birth_day),
        "formatted": f"{birth_month:02d}/{birth_day:02d}/{birth_year}",
        "iso": f"{birth_year}-{birth_month:02d}-{birth_day:02d}",
    }


def pick_email(service="", prefer="outlook"):
    """Pick the best TARS email for a given service.

    Args:
        service: The service being signed up for
        prefer: Preferred email provider ("outlook" or "gmail")

    Returns:
        Email address string.
    """
    # Google-related services should use Gmail
    google_services = ["google", "youtube", "android", "firebase", "gcp", "google cloud"]
    if any(g in service.lower() for g in google_services):
        return TARS_EMAILS["gmail"]["email"]

    # Default to preferred
    return TARS_EMAILS.get(prefer, TARS_EMAILS["outlook"])["email"]


def generate_credentials(service="", flow="signup"):
    """Generate a complete set of credentials for account creation.

    This is the main entry point — generates everything needed for signup.

    Args:
        service: The service name (e.g., "doordash", "stripe", "github")
        flow: "signup" or "login"

    Returns:
        Standard TARS tool result with all generated credentials.
    """
    email = pick_email(service)
    password = generate_password(service)
    username = generate_username(service)
    birthday = generate_birthday()

    credentials = {
        "email": email,
        "password": password,
        "username": username,
        "first_name": TARS_IDENTITY_DEFAULTS["first_name"],
        "last_name": TARS_IDENTITY_DEFAULTS["last_name"],
        "full_name": TARS_IDENTITY_DEFAULTS["full_name"],
        "company": TARS_IDENTITY_DEFAULTS["company"],
        "job_title": TARS_IDENTITY_DEFAULTS["job_title"],
        "birthday": birthday,
        "country": TARS_IDENTITY_DEFAULTS["country"],
        "city": TARS_IDENTITY_DEFAULTS["city"],
        "state": TARS_IDENTITY_DEFAULTS["state"],
        "zip": TARS_IDENTITY_DEFAULTS["zip"],
    }

    # Format as clear text for the brain
    lines = [
        f"Generated credentials for {service or 'account signup'}:",
        f"",
        f"  Email: {email}",
        f"  Password: {password}",
        f"  Username: {username}",
        f"  Name: {credentials['full_name']}",
        f"  Company: {credentials['company']}",
        f"  Birthday: {birthday['formatted']}",
        f"  Location: {credentials['city']}, {credentials['state']}, {credentials['country']}",
        f"",
        f"Include ALL of these in your agent deployment instruction.",
        f"After signup, store credentials with: manage_account('store', service='{service}', username='{email}', password='{password}')",
    ]

    return {"success": True, "content": "\n".join(lines), "credentials": credentials}


def get_form_defaults(service=""):
    """Get common form field defaults for a service.

    Returns a dict of field_name → value pairs for common form fields.
    Useful for fill_form() — agent can match field labels to these values.
    """
    defaults = {
        "first name": TARS_IDENTITY_DEFAULTS["first_name"],
        "last name": TARS_IDENTITY_DEFAULTS["last_name"],
        "full name": TARS_IDENTITY_DEFAULTS["full_name"],
        "name": TARS_IDENTITY_DEFAULTS["full_name"],
        "company": TARS_IDENTITY_DEFAULTS["company"],
        "company name": TARS_IDENTITY_DEFAULTS["company"],
        "organization": TARS_IDENTITY_DEFAULTS["company"],
        "job title": TARS_IDENTITY_DEFAULTS["job_title"],
        "role": TARS_IDENTITY_DEFAULTS["job_title"],
        "country": TARS_IDENTITY_DEFAULTS["country"],
        "city": TARS_IDENTITY_DEFAULTS["city"],
        "state": TARS_IDENTITY_DEFAULTS["state"],
        "zip": TARS_IDENTITY_DEFAULTS["zip"],
        "zip code": TARS_IDENTITY_DEFAULTS["zip"],
        "postal code": TARS_IDENTITY_DEFAULTS["zip"],
        "website": TARS_IDENTITY_DEFAULTS["website"],
        "url": TARS_IDENTITY_DEFAULTS["website"],
        # Common dropdown selections
        "what are you building": "Personal project",
        "use case": "API integration",
        "how did you hear about us": "Web search",
        "industry": "Technology",
        "team size": "1-10",
        "company size": "1-10",
    }

    return defaults
