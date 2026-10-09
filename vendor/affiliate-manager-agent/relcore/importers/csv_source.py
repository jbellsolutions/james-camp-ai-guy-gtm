"""CSV folder importer: contacts.csv (required) plus organizations, partnerships, relationships, producers,
dnc, conversions and research.json when present. Column names match charter/examples/sample-client/relationship."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import Batch


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(fh)]


def _list(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def read(folder, system: str = "crm") -> Batch:
    d = Path(folder)
    if not (d / "contacts.csv").exists():
        raise SystemExit(f"{d}/contacts.csv not found")
    b = Batch(system=system)
    for r in _rows(d / "organizations.csv"):
        b.orgs.append({"key": r["crm_id"], "name": r["name"], "domain": r.get("domain"), "kind": r.get("kind"),
                       "solo": r.get("solo", "").lower() in ("yes", "true", "1"), "city": r.get("city"), "state": r.get("state"),
                       "niche": _list(r.get("niches")), "promo_channels": _list(r.get("promo_channels")),
                       "region": _list(r.get("regions")), "audience": r.get("audience"), "website": r.get("website"),
                       "client": r.get("kind") == "client"})
    for r in _rows(d / "contacts.csv"):
        display = " ".join(x for x in (r.get("first_name", "").strip().title() if r.get("first_name", "").isupper() else r.get("first_name", ""),
                                        r.get("last_name", "")) if x).strip() or r.get("email") or r["crm_id"]
        b.people.append({"key": r["crm_id"], "display": display, "first_name": r.get("first_name"), "last_name": r.get("last_name"),
                         "email": r.get("email"), "phone": r.get("phone"), "title": r.get("title"),
                         "org_key": r.get("company_domain"), "source": r.get("source"), "notes": r.get("notes"),
                         "internal": r.get("internal", "").lower() in ("yes", "true", "1"),
                         "consent": {"email": r.get("consent_email"), "sms": r.get("consent_sms")}})
    for r in _rows(d / "partnerships.csv"):
        contacts = []
        for item in _list(r.get("contacts")):
            key, _, role = item.partition(":")
            contacts.append((key.strip(), role.strip()))
        b.partnerships.append({"partner_key": r["partner_crm_id"], "type_id": r["type_id"], "contacts": contacts,
                               **{k: r.get(k) for k in ("tier", "joined", "conversions", "last_conversion_at", "link", "code",
                                                         "platform_id", "status")}})
    b.relationships = [{"from": r["from_crm_id"], "type": r["type"], "to": r["to_crm_id"], "note": r.get("note")}
                       for r in _rows(d / "relationships.csv")]
    b.producers = [r["crm_id"] for r in _rows(d / "producers.csv")]
    b.dnc = _rows(d / "dnc.csv")
    b.conversions = _rows(d / "conversions.csv")
    if (d / "research.json").exists():
        b.research = json.loads((d / "research.json").read_text())
    return b
