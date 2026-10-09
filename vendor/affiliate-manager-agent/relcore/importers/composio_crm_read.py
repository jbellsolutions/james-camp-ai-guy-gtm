"""CRM contacts through Composio, read-only. Only tool slugs on policies/mcp-tool-allowlist.json are called, and
only with the read Composio project key (COMPOSIO_API_KEY in ~/.trp/.env, never the sender's project).

Live: POST https://backend.composio.dev/api/v3/tools/execute/<SLUG> {"arguments": {...}} (shape checked by
install/doctor at go-live). --from-file reads a saved response."""
from __future__ import annotations

import json
import os

from . import Batch
from .. import config

SLUGS = {"hubspot": "HUBSPOT_LIST_CONTACTS", "salesforce": "SALESFORCE_SEARCH_CONTACTS", "pipedrive": "PIPEDRIVE_GET_ALL_PERSONS"}


def _allowed(slug: str) -> bool:
    allow = json.loads((config.REPO / "policies" / "mcp-tool-allowlist.json").read_text())
    return slug in allow["servers"].get("composio", [])


def read(toolkit: str = "hubspot", from_file: str | None = None) -> Batch:
    slug = SLUGS.get(toolkit)
    if not slug or not _allowed(slug):
        raise SystemExit(f"{toolkit}: no read-only slug on the allowlist")
    if from_file:
        data = json.loads(open(from_file).read())
    else:
        from ..http import request
        key = os.environ.get("COMPOSIO_API_KEY")
        if not key:
            raise SystemExit("COMPOSIO_API_KEY is not set (install/connect.sh --composio)")
        data = request("POST", f"https://backend.composio.dev/api/v3/tools/execute/{slug}",
                       headers={"x-api-key": key}, body={"arguments": {"limit": 100}})
    items = (data.get("data") or {}).get("results") or data.get("results") or data.get("contacts") or []
    b = Batch(system=toolkit)
    for it in items:
        props = it.get("properties") or it
        email = props.get("email") or props.get("Email")
        domain = email.split("@", 1)[1].lower() if email and "@" in email else None
        account = props.get("Account") if isinstance(props.get("Account"), dict) else {}
        company = props.get("company") or account.get("Name")
        if company and domain and not any(o["domain"] == domain for o in b.orgs):
            b.orgs.append({"key": f"org:{domain}", "name": company, "domain": domain, "client": False})
        name = " ".join(x for x in (props.get("firstname") or props.get("FirstName"), props.get("lastname") or props.get("LastName")) if x)
        b.people.append({"key": str(it.get("id") or props.get("Id") or email), "display": name or email or "Unnamed",
                         "first_name": props.get("firstname") or props.get("FirstName"),
                         "last_name": props.get("lastname") or props.get("LastName"), "email": email,
                         "phone": props.get("phone") or props.get("Phone"), "title": props.get("jobtitle") or props.get("Title"),
                         "org_key": domain, "source": f"{toolkit} import", "consent": {}, "internal": False})
    return b
