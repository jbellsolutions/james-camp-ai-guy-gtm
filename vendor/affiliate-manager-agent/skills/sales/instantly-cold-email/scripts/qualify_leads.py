#!/usr/bin/env python3
"""Qualify Apify-scraped leads before uploading to a cold email platform.

Filters out:
- Generic/role-based emails (info@, contact@, support@, etc.)
- Invalid or malformed emails
- Companies without real names (too short, numeric-only)
- Duplicate emails within batch

Usage: python3 qualify_leads.py <input_json> <output_json>
"""

import json
import re
import sys

# ── Generic email prefixes to reject ─────────────────────────────────
GENERIC_PREFIXES = {
    "info", "contact", "hello", "support", "admin", "sales", "hr",
    "help", "office", "team", "general", "enquiries", "inquiries",
    "noreply", "no-reply", "careers", "jobs", "hiring", "press",
    "media", "marketing", "investors", "webmaster", "abuse", "postmaster",
    "billing", "accounts", "enquiry", "service", "services", "mail",
    "customerservice", "customer", "orders", "order", "feedback",
    "complaints", "legal", "it", "security", "privacy", "newsletter",
    "notifications", "noreply", "donotreply", "do-not-reply",
}

# ── Suspicious company name patterns ─────────────────────────────────
BAD_COMPANY_PATTERNS = [
    (re.compile(r"^[0-9\s\-\.]+$"), "numeric only"),
    (re.compile(r"^.{,2}$"), "too short (≤2 chars)"),
    (re.compile(r"^(test|demo|example|sample|none|n/a|tbd|unknown)\b", re.I), "placeholder name"),
]


def is_generic_email(email: str) -> bool:
    """Check if email prefix is generic (info@, contact@, etc.)."""
    if not email or "@" not in email:
        return True
    local = email.split("@")[0].lower().strip()
    return local in GENERIC_PREFIXES


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    if not email or "@" not in email:
        return False
    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    return bool(pattern.match(email.strip()))


def is_suspicious_company(name: str) -> tuple[bool, str]:
    """Check if company name looks fake/placeholder."""
    if not name or not name.strip():
        return True, "empty"
    name = name.strip()
    for pattern, reason in BAD_COMPANY_PATTERNS:
        if pattern.match(name):
            return True, reason
    return False, ""


def qualify_leads(input_path: str, output_path: str) -> dict:
    """Qualify leads and write clean output."""
    with open(input_path) as f:
        raw = json.load(f)

    stats = {
        "total": len(raw),
        "no_email": 0,
        "invalid_email": 0,
        "generic_email": 0,
        "no_name": 0,
        "bad_company": 0,
        "duplicate_email": 0,
        "qualified": 0,
    }

    seen_emails = set()
    qualified = []

    for l in raw:
        email = (l.get("email") or "").strip()
        first = (l.get("firstName") or l.get("first_name") or "").strip()
        last = (l.get("lastName") or l.get("last_name") or "").strip()
        company = (l.get("companyName") or l.get("company_name") or "").strip()

        # Email checks
        if not email:
            stats["no_email"] += 1
            continue
        if not is_valid_email(email):
            stats["invalid_email"] += 1
            continue
        if is_generic_email(email):
            stats["generic_email"] += 1
            continue
        if email.lower() in seen_emails:
            stats["duplicate_email"] += 1
            continue

        # Name checks
        if not first:
            stats["no_name"] += 1
            continue

        # Company checks
        suspicious, reason = is_suspicious_company(company)
        if suspicious:
            stats["bad_company"] += 1
            continue

        seen_emails.add(email.lower())
        qualified.append(l)
        stats["qualified"] += 1

    with open(output_path, "w") as f:
        json.dump(qualified, f)

    return stats


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 qualify_leads.py <input.json> <output.json>")
        sys.exit(1)

    stats = qualify_leads(sys.argv[1], sys.argv[2])
    print(f"Input: {stats['total']}")
    print(f"Qualified: {stats['qualified']} ({100*stats['qualified']//max(stats['total'],1)}%)")
    print(f"Rejected:")
    print(f"  No email: {stats['no_email']}")
    print(f"  Invalid email: {stats['invalid_email']}")
    print(f"  Generic email (info@, etc.): {stats['generic_email']}")
    print(f"  No first name: {stats['no_name']}")
    print(f"  Bad company name: {stats['bad_company']}")
    print(f"  Duplicate email: {stats['duplicate_email']}")
