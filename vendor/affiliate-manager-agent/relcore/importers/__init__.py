"""Bring contacts into the relationship layer. Read-only sources; the owner runs `plan` then `apply`.

    python3 -m relcore import plan  csv <folder>              # what would be created, updated, excluded
    python3 -m relcore import apply csv <folder> [--system crm]
    python3 -m relcore import apply ghl [--from-file page.json]   # live: RELCORE_GHL_READ_TOKEN + RELCORE_GHL_LOCATION_ID
    python3 -m relcore import apply composio --toolkit hubspot [--from-file contacts.json]
    python3 -m relcore import apply platform <conversions.csv>
    python3 -m relcore import apply research <research.json>

Every source produces one Batch. apply() writes it as by="import" (record facts, consent, DNC), then recomputes
segments and exclusions. Nothing here can send.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

from .. import clock, config, normalize


@dataclass
class Batch:
    system: str
    people: list = field(default_factory=list)
    orgs: list = field(default_factory=list)
    partnerships: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    producers: list = field(default_factory=list)
    dnc: list = field(default_factory=list)
    conversions: list = field(default_factory=list)
    research: list = field(default_factory=list)


def source_label(system: str) -> str:
    return {"ghl": "GHL import", "crm": "CRM import", "hubspot": "HubSpot import", "salesforce": "Salesforce import",
            "pipedrive": "Pipedrive import"}.get(system, f"{system} import")


def plan(store, batch: Batch) -> dict:
    out = {"people": {"new": 0, "update": 0}, "orgs": {"new": 0, "update": 0}, "partnerships": {"new": 0, "update": 0},
           "relationships": len(batch.relationships), "dnc": len(batch.dnc), "producers": len(batch.producers),
           "conversions": len(batch.conversions), "problems": []}
    for p in batch.people:
        found = store.resolve({"email": p.get("email")}) or store.resolve({"phone": p.get("phone")}) or \
            store.resolve({"crm": f"{batch.system}:{p['key']}"})
        out["people"]["update" if found else "new"] += 1
        if not p.get("email") and not normalize.phone(p.get("phone") or ""):
            out["problems"].append(f"{p['display']}: no email and no valid phone")
    for o in batch.orgs:
        if o.get("client"):
            continue
        found = store.resolve({"domain": o.get("domain")}) or store.resolve({"crm": f"{batch.system}:{o['key']}"})
        out["orgs"]["update" if found else "new"] += 1
    out["partnerships"]["new"] = len(batch.partnerships)
    return out


def apply(store, batch: Batch, *, client: str | None = None) -> dict:
    from .. import segments
    s = store
    client = client or s.settings.get("client") or ""
    if batch.partnerships and not client:
        raise SystemExit("set the client first (apply the charter, or 'client' in relationship.json)")
    sysname = batch.system
    org_ids, person_ids = {}, {}
    for o in batch.orgs:
        if o.get("client"):
            continue
        oid = s.upsert("partner", o["name"], identities={"domain": o.get("domain"), "crm": f"{sysname}:{o['key']}"},
                       fields={k: o[k] for k in ("city", "state", "solo") if o.get(k) not in (None, "")}, by="import",
                       source="record", source_ref=f"{sysname}:{o['key']}")
        org_ids[o["key"]] = oid
        if o.get("domain"):
            org_ids[o["domain"]] = oid
        facts = [{"slot": "partner_kind", "value": o["kind"]}] if o.get("kind") else []
        facts += [{"slot": slot, "value": v} for slot in ("niche", "promo_channels", "region") for v in o.get(slot, [])]
        facts += [{"slot": slot, "value": o[slot]} for slot in ("audience", "website") if o.get(slot)]
        s.remember(oid, facts=facts, hubs={"Sources": [o.get("source") or source_label(sysname)]}, source="record",
                   source_ref=f"{sysname}:{o['key']}", by="import", recorder="import")
    sender_email = (s.settings.get("sender") or {}).get("email")
    for p in batch.people:
        idents = {"email": p.get("email"), "phone": p.get("phone"), "crm": f"{sysname}:{p['key']}"}
        fields = {"first_name": normalize.first_name(p.get("first_name") or p.get("display", "")),
                  "last_name": (p.get("last_name") or "").strip().title() or None, "title": p.get("title") or None}
        pid = s.upsert("person", p["display"], identities=idents, fields={k: v for k, v in fields.items() if v},
                       internal=bool(p.get("internal")), by="import", source="record", source_ref=f"{sysname}:{p['key']}")
        person_ids[p["key"]] = pid
        org = org_ids.get(p.get("org_key") or "") or (s.resolve({"domain": p.get("org_key")}) if p.get("org_key") else None)
        if org and not p.get("internal"):
            s.link(pid, "works_at", org, source="record", source_ref=f"{sysname}:{p['key']}")
        for channel, basis in (p.get("consent") or {}).items():
            if basis:
                s.set_consent(pid, channel, basis, f"{sysname} import", by="import")
        facts, note = [], p.get("notes") or None
        if note:
            from ..extract import rule_facts
            facts = rule_facts(note)
        s.remember(pid, facts=facts, note=note, hubs={"Sources": [p["source"]]} if p.get("source") and not p.get("internal") else None,
                   source="record", source_ref=f"{sysname}:{p['key']}:notes", by="import", recorder="import")
    voice = s.resolve({"email": sender_email}) if sender_email else None
    if not voice:  # the named sender from relationship.json, else the only internal person
        sender_name = ((s.settings.get("sender") or {}).get("name") or "").lower()
        internal = [i for i in s.all_ids("person") if s.entity(i)["internal"]]
        named = [i for i in internal if s.entity(i)["display"].lower() == sender_name]
        voice = named[0] if named else (internal[0] if len(internal) == 1 else None)
    ps_ids = []
    for ps in batch.partnerships:
        partner = org_ids.get(ps["partner_key"]) or s.resolve({"crm": f"{sysname}:{ps['partner_key']}"}) or \
            s.resolve({"domain": ps["partner_key"]})
        if not partner:
            continue
        contacts = [(person_ids.get(k) or s.resolve({"crm": f"{sysname}:{k}"}), role) for k, role in ps.get("contacts", [])]
        pid = s.partnership(client=client, partner_id=partner, type_id=ps["type_id"], voice_id=voice,
                            contacts=[c for c in contacts if c[0]], by="import", source="record",
                            source_ref=f"{sysname}:{ps['partner_key']}:{ps['type_id']}")
        ps_ids.append(pid)
        facts = [{"slot": slot, "value": ps[slot]} for slot in ("tier", "joined", "link", "code") if ps.get(slot)]
        if ps.get("conversions") not in (None, ""):
            facts.append({"slot": "conversions", "value": str(ps["conversions"])})
        if ps.get("last_conversion_at"):
            facts.append({"slot": "last_conversion", "value": ps["last_conversion_at"]})
        if ps.get("status"):
            facts.append({"slot": "production_stage", "value": ps["status"]})
        if ps.get("platform_id"):
            s.upsert("partnership", identities={"platform": ps["platform_id"], "key": f"{client}|{partner}|{ps['type_id']}"},
                     by="import", source="record")
        s.remember(pid, facts=facts, source="record", source_ref=f"{sysname}:{ps['partner_key']}:{ps['type_id']}:record",
                   by="import", recorder="import")
    for r in batch.relationships:
        a = person_ids.get(r["from"]) or s.resolve({"crm": f"{sysname}:{r['from']}"})
        b = person_ids.get(r["to"]) or s.resolve({"crm": f"{sysname}:{r['to']}"})
        if a and b:
            s.link(a, r["type"], b, props={"note": r["note"]} if r.get("note") else None, source="record")
    for d in batch.dnc:
        target = {k: d[k] for k in ("email", "phone") if d.get(k)}
        if target:
            s.suppress(target, channel="*", reason="dnc_list", source=f"{sysname} import")
    apply_conversions(s, batch.conversions)
    for r in batch.research:
        apply_research(s, r)
    producers = set()
    for key in batch.producers:
        eid = person_ids.get(key) or org_ids.get(key) or s.resolve({"crm": f"{sysname}:{key}"})
        if eid:
            producers.add(eid)
    result = segments.compute(s, producers=producers)
    s.vault.render_around(set(s.all_ids()))
    return {"people": len(person_ids), "partners": len({v for v in org_ids.values()}), "partnerships": len(ps_ids),
            "segments": result["segments"], "excluded": result["excluded"]}


def apply_conversions(store, rows: list) -> None:
    for r in rows:
        ps = store.resolve({"platform": r.get("platform_id")}) if r.get("platform_id") else None
        if not ps and r.get("code"):
            hit = store.con.execute("SELECT entity_id FROM facts WHERE slot='code' AND value=? AND removed_at IS NULL",
                                    (r["code"],)).fetchone()
            ps = hit["entity_id"] if hit else None
        if not ps:
            continue
        facts = [{"slot": "conversions", "value": str(r.get("conversions") or 0)}]
        if r.get("last_conversion_at"):
            facts.append({"slot": "last_conversion", "value": r["last_conversion_at"]})
        store.remember(ps, facts=facts, source="record", source_ref=f"platform:{r.get('platform_id') or r.get('code')}:"
                       f"{r.get('conversions')}:{r.get('last_conversion_at')}", by="import", recorder="platform")


def apply_research(store, r: dict) -> None:
    target = store.resolve({"domain": r.get("partner_domain")}) if r.get("partner_domain") else store.resolve(r.get("ref") or {})
    if target:
        store.remember(target, facts=r["facts"], source="research", source_ref=r["url"], by="owner", recorder="research")


def load(source: str, rest: list[str], args) -> Batch:
    if source == "csv":
        from .csv_source import read
        return read(rest[0], system=args.system or "crm")
    if source == "ghl":
        from .ghl_read import read
        return read(from_file=args.from_file)
    if source == "composio":
        from .composio_crm_read import read
        return read(toolkit=args.toolkit, from_file=args.from_file)
    if source == "platform":
        from .platform_export import read
        return read(rest[0])
    if source == "research":
        return Batch(system="research", research=json.loads(open(rest[0]).read()))
    raise SystemExit(f"unknown source {source}")


def main(argv: list[str]) -> int:
    from ..store import Store
    ap = argparse.ArgumentParser(prog="relcore import")
    ap.add_argument("mode", choices=["plan", "apply"])
    ap.add_argument("source")
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--system")
    ap.add_argument("--from-file")
    ap.add_argument("--toolkit", default="hubspot")
    ap.add_argument("--client")
    a = ap.parse_args(argv)
    batch = load(a.source, a.rest, a)
    store = Store(config.resolve())
    if a.mode == "plan":
        print(json.dumps(plan(store, batch), indent=1))
        return 0
    store.audit("import_apply", a.source, {"at": clock.iso(), "people": len(batch.people)}, actor="owner")
    print(json.dumps(apply(store, batch, client=a.client), indent=1))
    return 0
