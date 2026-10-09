"""Multi-tenant credential registry — one Private Integration Token per
GHL sub-account (or the agency), keyed by a profile name and tagged with
a `business` bucket (revenue-partners / connectmed / funding / ...).

GHL's public API has no concept of grouping locations (confirmed by probing
/locations/search: only companyId/skip/limit/order/email are accepted, no
group/tag filter). This registry is what fills that gap — it is the single
source of truth other tooling (CLI --profile, MCP ghl_profiles()) reads to
resolve "which token/location for this business/client" without a human
enumerating IDs in every prompt.

Shared by both the CLI (in-process import) and the MCP server (imported
directly since ghl_mcp_server.py runs under this same venv) so registry
parsing/validation lives in exactly one place.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parents[3] / "profiles" / "registry.json"


class ProfileError(RuntimeError):
    """Registry missing, malformed, or the requested profile isn't in it."""


def _check_perms(path: Path) -> None:
    """Warn (don't fail) if the registry is group/world readable — it holds
    live API tokens for every connected business."""
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            print(
                f"Warning: {path} is readable by group/other. "
                f"Run: chmod 600 {path}",
                file=sys.stderr,
            )
    except OSError:
        pass


def load_registry() -> dict[str, dict[str, Any]]:
    """Load the full profile registry. Returns {} if the file doesn't exist yet
    (a brand-new install with no profiles configured is not an error)."""
    if not REGISTRY_PATH.exists():
        return {}
    _check_perms(REGISTRY_PATH)
    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except json.JSONDecodeError as e:
        raise ProfileError(f"{REGISTRY_PATH} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ProfileError(f"{REGISTRY_PATH} must contain a JSON object")
    return data


def save_registry(data: dict[str, dict[str, Any]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.chmod(REGISTRY_PATH, 0o600)


def list_profiles(business: str | None = None) -> dict[str, dict[str, Any]]:
    """All profiles, excluding the special `_agency` entry, optionally
    filtered by business bucket."""
    reg = load_registry()
    out = {k: v for k, v in reg.items() if k != "_agency"}
    if business:
        out = {k: v for k, v in out.items() if v.get("business") == business}
    return out


def get_agency() -> dict[str, Any] | None:
    return load_registry().get("_agency")


def resolve_profile(name: str) -> dict[str, str]:
    """Look up one profile and return the env-var overrides it implies.

    Raises ProfileError with an actionable message if the profile or the
    registry file itself doesn't exist — this is a config error, not a
    network error, so it must never look like an API failure downstream.
    """
    reg = load_registry()
    if not reg:
        raise ProfileError(
            f"No profile registry at {REGISTRY_PATH}. "
            f"Run: ghl profiles add {name}"
        )
    entry = reg.get(name)
    if entry is None:
        known = ", ".join(k for k in reg if k != "_agency") or "(none yet)"
        raise ProfileError(f"No profile named '{name}'. Known profiles: {known}")

    overrides: dict[str, str] = {}
    if entry.get("api_key"):
        overrides["GHL_API_KEY"] = entry["api_key"]
    if entry.get("location_id"):
        overrides["GHL_LOCATION_ID"] = entry["location_id"]
    if entry.get("company_id"):
        overrides["GHL_COMPANY_ID"] = entry["company_id"]
    if not overrides.get("GHL_API_KEY"):
        raise ProfileError(f"Profile '{name}' has no api_key set.")
    return overrides


def default_profile_name() -> str | None:
    for name, entry in load_registry().items():
        if name != "_agency" and entry.get("is_default"):
            return name
    return None
