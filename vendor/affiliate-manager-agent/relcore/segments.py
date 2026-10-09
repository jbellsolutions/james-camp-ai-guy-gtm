"""Segments and exclusions for every revenue partnership, recomputed after each import.

Segments (spec 6.1): past_producer (conversions in the record), new_recruit (joined recently),
thin_record (joined, no production and almost nothing known), registered_never_produced, prospect (no record).
Exclusions are reasons a partnership is left out of every wave: active producer, do not contact, hold,
internal, no reachable contact. Draft, prepare and send all honor them and every review card counts them.
"""
from __future__ import annotations

from datetime import timedelta

from . import clock
from .db import tx

NEW_RECRUIT_DAYS = 30


def _slot(profile: dict, name: str):
    v = profile["slots"].get(name)
    return v[0]["value"] if v else None


def segment_of(store, ps_id: str) -> str:
    p = store.profile(ps_id)
    conversions = int(_slot(p, "conversions") or 0)
    joined = _slot(p, "joined")
    if conversions > 0:
        return "past_producer"
    if not joined:
        return "prospect"
    if clock.parse(joined + "T00:00:00Z") >= clock.now() - timedelta(days=NEW_RECRUIT_DAYS):
        return "new_recruit"
    partner, _ = store.route(ps_id, "partner")
    slots = store.profile(partner)["slots"] if partner else {}
    if not ({"partner_kind", "audience", "goals"} & set(slots)):
        return "thin_record"  # registered, never produced, and we know nothing about who they reach
    return "registered_never_produced"


def exclusions_of(store, ps_id: str, producers: set) -> list[str]:
    p = store.profile(ps_id)
    out = []
    inactive_days = store.settings["eligibility"]["inactive_days"]
    last = _slot(p, "last_conversion")
    contacts = [l["id"] for l in p["links"].get("contact_for<", [])]
    partner = next((l["id"] for l in p["links"].get("partner_in<", [])), None)
    if producers & set(contacts + [partner, ps_id]) or (last and clock.parse(last + "T00:00:00Z") >= clock.now() - timedelta(days=inactive_days)):
        out.append("active_producer")
    reachable = False
    for c in contacts:
        ent = store.entity(c)
        flags = store.do_not(c)
        if ent["internal"]:
            continue
        if any(f.startswith("do not contact") for f in flags):
            out.append("do_not_contact")
        if any(f.startswith("hold") for f in flags):
            out.append("hold")
        ids = store.profile(c)["identities"]
        if ids.get("email") or ids.get("phone"):
            reachable = True
    if not reachable:
        out.append("no_reachable_contact")
    for f in store.do_not(ps_id):
        if f.startswith("hold"):
            out.append("hold")
    return sorted(set(out))


def compute(store, producers: set | None = None) -> dict:
    producers = producers or set()
    seg_counts, excl_counts = {}, {}
    for ps in store.all_ids("partnership"):
        seg = segment_of(store, ps)
        excl = exclusions_of(store, ps, producers)
        with tx(store.con):
            store._set_fields(ps, "partnership", {"segment": seg, "exclusions": excl or None}, "import")
        seg_counts[seg] = seg_counts.get(seg, 0) + 1
        for e in excl:
            excl_counts[e] = excl_counts.get(e, 0) + 1
    return {"segments": dict(sorted(seg_counts.items())), "excluded": dict(sorted(excl_counts.items()))}
