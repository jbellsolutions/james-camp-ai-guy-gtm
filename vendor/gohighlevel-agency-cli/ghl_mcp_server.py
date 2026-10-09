#!/usr/bin/env python3
"""
GoHighLevel MCP server.

A thin, reliable bridge that exposes the full GoHighLevel CLI surface
(contacts, opportunities, calendars, workflows, conversations, emails,
payments, forms, social, locations, documents) to any MCP client —
Claude Code, Claude Desktop, etc.

Design: instead of re-implementing ~45 endpoints (and drifting from the
CLI), every tool forwards exact argv to the proven `ghl` CLI via
`python -m cli_anything.gohighlevel`. No shell=True, so argv is passed as
a list and there is no shell-injection surface. All endpoint logic lives
in the tested CLI; this file is just the transport + discovery layer.

Credentials are read from a single source of truth: the repo `.env`
(GHL_API_KEY, GHL_LOCATION_ID, GHL_FIREBASE_REFRESH_TOKEN), merged over
the process environment and passed to each CLI subprocess.

For multi-tenant use (many GHL sub-accounts across several businesses),
`profiles/registry.json` holds one named entry per sub-account/agency token.
Pass `profile=` to `ghl()` to run a command against a specific entry instead
of the .env default; call `ghl_profiles()` first to discover what's available
without a human enumerating IDs in the prompt.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_anything.gohighlevel.utils import profiles as profile_registry  # noqa: E402

# --------------------------------------------------------------------------
# Paths / configuration
# --------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent
VENV_PY = REPO / ".venv" / "bin" / "python"
ENV_FILE = REPO / ".env"
DEFAULT_TIMEOUT = 90  # seconds — CRM calls are not high-frequency

# The full command catalog, kept here so a fresh MCP client can discover the
# surface in one call (ghl_catalog) without spawning --help for every group.
CATALOG: dict[str, dict[str, str]] = {
    "contacts": {
        "list": "List contacts in the location.",
        "get": "Get a single contact by ID. (positional: <contact_id>)",
        "create": "Create a new contact. (--email --first-name --last-name --phone --tag ...)",
        "update": "Update a contact by ID. (positional: <contact_id>)",
        "delete": "Delete a contact by ID. (positional: <contact_id>)",
        "search": "Search contacts with advanced filters. (positional: <query>)",
        "add-tag": "Add tags to a contact.",
        "remove-tag": "Remove tags from a contact.",
    },
    "opportunities": {
        "list": "List opportunities. (--pipeline-id --status)",
        "get": "Get opportunity details. (positional: <id>)",
        "create": "Create a new opportunity.",
        "update": "Update an opportunity.",
        "delete": "Delete an opportunity.",
        "pipelines": "List all pipelines.",
    },
    "calendars": {
        "list": "List all calendars.",
        "get": "Get calendar details.",
        "slots": "Get available appointment slots. (<calendar_id> --start --end)",
        "appointments": "List appointments.",
        "book": "Book an appointment.",
        "groups": "List calendar groups.",
    },
    "workflows": {
        "list": "List all workflows.",
        "enroll": "Enroll a contact in a workflow (public API). (--contact-id --workflow-id)",
        "remove": "Remove a contact from a workflow (public API).",
        "create": "EXPERIMENTAL: Create workflows from a campaign JSON file (internal API, needs Firebase token).",
        "create-n8n": "EXPERIMENTAL: Create a workflow that triggers an n8n webhook (internal API).",
        "create-step": "Build a workflow step and append to a JSON file (local helper).",
    },
    "conversations": {
        "list": "List conversations. (--contact-id --status)",
        "get": "Get conversation details.",
        "get-email": "Get full email details (subject, body, headers, attachments).",
        "messages": "Get messages in a conversation.",
        "send": "Send a message in a conversation. (<conversation_id> --type SMS|Email --message ...)",
    },
    "emails": {
        "list-campaigns": "List email campaigns.",
    },
    "payments": {
        "transactions": "List transactions.",
        "orders": "List orders.",
        "invoices": "List invoices.",
        "create-invoice": "Create a new invoice.",
    },
    "forms": {
        "list": "List forms.",
        "submissions": "Get form submissions.",
    },
    "social": {
        "accounts": "List connected social media accounts.",
        "posts": "List social media posts.",
        "create-post": "Create a social media post. (--account-id --text --schedule)",
    },
    "locations": {
        "get": "Get current location details.",
        "search": "Search locations (requires company-level access).",
        "tags": "List tags for current location.",
        "custom-fields": "List custom fields for current location.",
        "custom-values": "List custom values for current location.",
    },
    "documents": {
        "(varies)": "Documents, contracts, and proposals — run ghl_help(['documents']) for exact commands.",
    },
    "profiles": {
        "list": "List credential profiles, optionally --business <name>. Use ghl_profiles() instead when available.",
        "get": "Show one profile's config (token redacted). (positional: <name>)",
        "add": "Add/update a profile. (--business --location-id [--api-key] [--label] [--default])",
        "remove": "Remove a profile. (positional: <name>)",
    },
    "rollup": {
        "opportunities": "Aggregate opportunities across every profile in one --business bucket "
        "(e.g. --business connectmed) — GHL has no agency-level pipeline view, so this loops "
        "profiles list --business X and merges. Each result gets a _profile field; profiles "
        "with no api_key yet are skipped, not fatal (see the skipped list).",
    },
}

mcp = FastMCP("gohighlevel")


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------
def _env(profile: str | None = None) -> dict[str, str]:
    """Process env merged with the repo .env, then optionally overridden by
    a named profiles/registry.json entry (single source of truth either way)."""
    import os

    merged = dict(os.environ)
    if ENV_FILE.exists():
        for k, v in dotenv_values(ENV_FILE).items():
            if v is not None:
                merged[k] = v
    if profile:
        overrides = profile_registry.resolve_profile(profile)  # raises ProfileError
        merged.update(overrides)
    # Keep the unofficial-internal-API warning out of stdout/stderr JSON.
    merged.setdefault("GHL_SUPPRESS_INTERNAL_WARNING", "1")
    return merged


def _run(tokens: list[str], timeout: int = DEFAULT_TIMEOUT, profile: str | None = None) -> dict:
    """Run `ghl <tokens>` via the venv interpreter and capture the result."""
    cmd = [str(VENV_PY), "-m", "cli_anything.gohighlevel", *tokens]
    try:
        env = _env(profile)
    except profile_registry.ProfileError as e:
        return {"ok": False, "error": str(e), "command": tokens}
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s", "command": tokens}
    except FileNotFoundError:
        return {
            "ok": False,
            "error": f"venv python not found at {VENV_PY}. Re-run install.",
            "command": tokens,
        }

    out = proc.stdout.strip()
    result: dict = {"ok": proc.returncode == 0, "exit_code": proc.returncode, "command": tokens}

    # Prefer structured JSON when the CLI emitted it.
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
    if parsed is not None:
        result["data"] = parsed
    elif out:
        result["output"] = out
    if proc.stderr.strip():
        result["stderr"] = proc.stderr.strip()
    return result


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@mcp.tool()
def ghl(
    args: list[str],
    json_output: bool = True,
    experimental: bool = False,
    profile: str | None = None,
) -> dict:
    """Run any GoHighLevel CLI command and return its result.

    This is the universal entry point — it can drive the ENTIRE GHL surface:
    contacts, opportunities, calendars, workflows, conversations, emails,
    payments, forms, social, locations, and documents.

    `args` is the exact list of CLI tokens AFTER `ghl`, e.g.:
      • ["contacts", "list", "--limit", "5"]
      • ["contacts", "search", "jay@"]
      • ["contacts", "create", "--email", "a@b.com", "--first-name", "Jay"]
      • ["opportunities", "list", "--status", "open"]
      • ["conversations", "send", "<conv_id>", "--type", "SMS", "--message", "hi"]
      • ["workflows", "list"]

    Set `json_output=True` (default) for machine-readable JSON (recommended).
    Set `experimental=True` ONLY for workflow CREATION via GHL's unofficial
    internal API — it uses your full-account Firebase token; own-agency only.

    Set `profile=` to target a specific business/sub-account instead of the
    .env default — e.g. `profile="connectmed-acme"`. GHL has no native way to
    group sub-accounts by business, so call `ghl_profiles()` FIRST to see what
    profiles exist and which `business` bucket each belongs to; never assume
    a bare call (no `profile=`) is targeting the client you mean — it targets
    whatever `.env`'s default is, currently Revenue Partners.

    Call `ghl_catalog()` to see all groups/commands, or `ghl_help([...])` to
    see exact flags for a specific command.
    """
    tokens: list[str] = []
    if json_output:
        tokens.append("--json")
    if experimental:
        tokens.append("--experimental")
    tokens.extend(args)
    return _run(tokens, profile=profile)


@mcp.tool()
def ghl_help(command: list[str] | None = None) -> dict:
    """Show CLI help for discovery — exact flags, positionals, and subcommands.

    Pass the command path as tokens (no flags), e.g.:
      • []                       → top-level groups
      • ["contacts"]             → contacts subcommands
      • ["contacts", "create"]   → exact flags for `contacts create`
      • ["documents"]            → the documents subcommands

    Always includes --experimental so experimental commands are visible.
    """
    cmd = list(command or [])
    cmd = ["--experimental", *cmd, "--help"]
    return _run(cmd, timeout=30)


@mcp.tool()
def ghl_catalog() -> dict:
    """Return the full catalog of GHL command groups and their commands.

    Fast, no subprocess — use this first to learn what's available, then call
    `ghl(...)` to run a command or `ghl_help([...])` for exact flags.
    """
    return {
        "groups": CATALOG,
        "notes": [
            "Add --json (json_output=True) for machine-readable output.",
            "Read-only ops need only GHL_API_KEY + GHL_LOCATION_ID.",
            "workflows create / create-n8n need experimental=True + GHL_FIREBASE_REFRESH_TOKEN.",
            "Use ghl_help(['group','command']) to see exact flags before writing.",
            "Multi-tenant: call ghl_profiles() to see available businesses/sub-accounts, "
            "then pass profile=\"<name>\" to ghl() to target one instead of the .env default.",
        ],
    }


@mcp.tool()
def ghl_profiles(business: str | None = None) -> dict:
    """List configured GHL credential profiles — one per sub-account/business.

    GHL's API has no concept of grouping sub-accounts, so this registry
    (profiles/registry.json) is the only place "which locations belong to
    ConnectMed" is answered. Call this BEFORE running any command against a
    specific client, to discover the right `profile=` name for `ghl()` — do
    not guess a profile name from a client's display name.

    Pass `business=` to filter to one bucket, e.g. business="connectmed".
    Returns each profile's label, location_id, and business bucket
    (never the API key itself).
    """
    try:
        data = profile_registry.list_profiles(business=business)
    except profile_registry.ProfileError as e:
        return {"ok": False, "error": str(e)}
    redacted = {
        name: {k: v for k, v in entry.items() if k != "api_key"}
        for name, entry in data.items()
    }
    default = profile_registry.default_profile_name()
    return {"ok": True, "profiles": redacted, "default_profile": default}


if __name__ == "__main__":
    mcp.run()
