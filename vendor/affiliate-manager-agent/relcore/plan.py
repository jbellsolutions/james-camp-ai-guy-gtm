"""The partner plan (spec 6.7). Written after the first real conversation and sent to the partner, not kept as
internal paperwork. The partner's version has their link, the two offers that fit their audience, three situations
where their audience needs the offer, a message they can copy and paste, the assets we will provide and the next
check-in. The internal version adds what we promised and the measure we will watch.

rel_plan_save records it (Plans/<partnership>.md, the plan slots on the partnership, an open loop per promise, the
next touch) and returns the partner email. To send it, pass that exact text to rel_draft_submit with plan=true: the
longer "plan" copy profile applies only to the saved plan's own text, and the owner still approves it.
"""
from __future__ import annotations

import hashlib

from . import clock, copy, ids, privacy
from .db import tx


def _first(store, ps: str) -> tuple[str | None, str]:
    for link in store.profile(ps)["links"].get("contact_for<", []):
        if not store.entity(link["id"])["internal"]:
            f = store.entity(link["id"])["fields"]
            return link["id"], f.get("first_name") or store.label(link["id"]).split(" ")[0]
    return None, ""


def _had_conversation(store, ps: str) -> bool:
    people = [l["id"] for l in store.profile(ps)["links"].get("contact_for<", [])]
    if not people:
        return False
    marks = ",".join("?" * len(people))
    return bool(store.con.execute(f"SELECT 1 FROM interactions WHERE direction='in' AND (entity_id IN ({marks}) OR partnership_id=?) LIMIT 1",
                                  (*people, ps)).fetchone())


def render(plan: dict, first: str) -> str:
    offers = plan["offers"]
    lines = [f"Here is the plan we talked about, {first}." if first else "Here is the plan we talked about.", "",
             f"Your link: {plan['link']}", "",
             "The offers that fit your people: " + " and ".join(offers) + ".", "",
             "When they need it:", *[f"{i}. {s}" for i, s in enumerate(plan["situations"], 1)], "",
             "A message you can copy and paste:", f"\"{plan['message']}\"", ""]
    if plan.get("assets"):
        lines += ["What we will send you: " + ", ".join(plan["assets"]) + ".", ""]
    lines.append(f"I will check in on {plan['next_check_in']}.")
    return "\n".join(lines)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


def save(store, ref, *, partner: dict, internal: dict | None = None, employee: str = "") -> dict:
    ps = store.resolve(ref)
    if not ps or store.entity(ps)["kind"] != "partnership":
        raise ValueError("a partner plan belongs to a revenue partnership")
    if not _had_conversation(store, ps):
        raise ValueError("a partner plan comes after the first real conversation (no reply or call on this partnership yet)")
    internal = internal or {}
    prof = store.profile(ps)
    link = partner.get("link") or (prof["slots"].get("link") or [{}])[0].get("value")
    plan = {"link": link, "offers": [str(o).strip() for o in partner.get("offers", []) if str(o).strip()],
            "situations": [str(s).strip() for s in partner.get("situations", []) if str(s).strip()],
            "message": str(partner.get("message", "")).strip(), "assets": [str(a).strip() for a in partner.get("assets", []) if str(a).strip()],
            "next_check_in": str(partner.get("next_check_in", "")).strip()}
    errors = []
    if not plan["link"]:
        errors.append("no link on record for this partnership (the owner or the import sets it)")
    if not 1 <= len(plan["offers"]) <= 2:
        errors.append("one or two offers that fit their audience")
    if len(plan["situations"]) != 3:
        errors.append("exactly three situations where their audience needs the offer")
    if not plan["message"]:
        errors.append("a message they can copy and paste")
    if not plan["next_check_in"]:
        errors.append("the next check-in date")
    everything = " ".join([*plan["offers"], *plan["situations"], plan["message"], *plan["assets"],
                           *map(str, internal.get("promised", [])), str(internal.get("measure", ""))])
    if privacy.violations(everything, store.schema["never_store"]):
        errors.append("contains a never_store category")
    if copy.EARNINGS.search(plan["message"]) or copy.EARNINGS.search(" ".join(plan["situations"] + plan["offers"])):
        errors.append("no earnings claims or figures in what the partner will share")
    person, first = _first(store, ps)
    text = render(plan, first) if not errors else ""
    if text:
        check = copy.lint("email", text, subject="your partner plan", first_touch=False, settings=store.settings, profile="plan")
        errors += check["errors"]
    if errors:
        return {"ok": False, "errors": errors}
    rel = f"Plans/{ids.safe_name(store.label(ps))} ({ps[3:9]}).md"
    note = ["---", "type: partner-plan", f"partnership: \"{store.vault.wikilink(ps)}\"", f"saved: {clock.day(clock.now())}",
            f"by: {employee or 'agent'}", f"text_hash: {text_hash(text)}", "tags:", "  - trp/plan", "---",
            f"# Partner plan: {store.label(ps)}", "", "## What the partner gets", "", *[f"> {l}" if l else ">" for l in text.splitlines()], "",
            "## Internal", "", "What we promised:", *([f"- {p}" for p in internal.get("promised", [])] or ["- nothing yet"]), "",
            f"Measure we watch: {internal.get('measure') or 'first conversion from their link'}", ""]
    store.vault._write(rel, "\n".join(note) + "\n")
    facts = [{"slot": "offers_fit", "value": o} for o in plan["offers"]] + [{"slot": "situations", "value": s} for s in plan["situations"]]
    facts.append({"slot": "next_step", "value": f"check in on {plan['next_check_in']}"})
    ref_id = f"plan:{text_hash(text)}"
    store.remember(ps, facts=facts, source="plan", source_ref=ref_id, by="model", recorder=employee or "agent",
                   loops=[{"owner": "us", "text": str(p), "partnership_id": ps, "due": plan["next_check_in"] if len(plan["next_check_in"]) == 10 else None}
                          for p in internal.get("promised", [])],
                   fields={"stage": "planned", **({"next_touch": plan["next_check_in"]} if len(plan["next_check_in"]) == 10 else {})})
    with tx(store.con):
        store.con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (f"plan:{ps}", text_hash(text)))
        store._timeline(ps, f"Partner plan saved: [[{rel[:-3]}]]", ref_id)
    store.vault.render_around({ps})
    return {"ok": True, "plan": rel, "partnership": ps, "person": person, "email": {"subject": "your partner plan", "body": text},
            "send": "pass this exact body to rel_draft_submit with plan=true, prepare=true and the context_digest from rel_context"}


def is_saved_plan(store, ps: str | None, body: str) -> bool:
    if not ps:
        return False
    row = store.con.execute("SELECT value FROM meta WHERE key=?", (f"plan:{ps}",)).fetchone()
    return bool(row and row["value"] == text_hash(body))


def _t_plan_save(srv, ref, partner, internal=None):
    return save(srv.store, ref, partner=partner, internal=internal, employee=srv.employee)


MCP_TOOLS = [
    {"name": "rel_plan_save", "read": False, "handler": _t_plan_save,
     "description": "Save the partner plan after the first real conversation: partner = {link (defaults to their record link), "
                    "offers (two that fit), situations (three), message (copy and paste), assets, next_check_in (YYYY-MM-DD)}, "
                    "internal = {promised, measure}. Returns the partner email; send it with rel_draft_submit plan=true.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["ref", "partner"],
                     "properties": {"ref": {"oneOf": [{"type": "string"}, {"type": "object"}]}, "partner": {"type": "object"},
                                    "internal": {"type": "object"}}}},
]
