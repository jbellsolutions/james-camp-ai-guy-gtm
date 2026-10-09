"""Lifecycle stages from the system of record only (spec 6.8):

    registered -> first_promotion -> first_conversion -> repeat -> lapsed -> offboarded

A conversation moves a partnership to "engaged" (a conversation stage), which is not production. Lifecycle is a
record slot: it is recomputed from imported facts (joined, conversions, last_conversion, the record status) and
written with by=import, so no model output can move it.
"""
from __future__ import annotations

from datetime import timedelta

from . import clock

STAGES = ("registered", "first_promotion", "first_conversion", "repeat", "lapsed", "offboarded")
OFFBOARDED = {"offboarded", "terminated", "removed", "inactive", "closed"}


def _slot(profile, name):
    v = profile["slots"].get(name)
    return v[0]["value"] if v else None


def stage_of(store, ps: str) -> str | None:
    p = store.profile(ps)
    status = str(_slot(p, "production_stage") or "").lower()  # the record's own status, imported
    if status in OFFBOARDED:
        return "offboarded"
    joined = _slot(p, "joined")
    if not joined:
        return None  # a prospect: not in the program yet
    conversions = int(_slot(p, "conversions") or 0)
    last = _slot(p, "last_conversion")
    lapse = store.settings.get("lifecycle", {}).get("lapsed_days", 120)
    if conversions and last and clock.parse(last + "T00:00:00Z") < clock.now() - timedelta(days=lapse):
        return "lapsed"
    if conversions >= 2:
        return "repeat"
    if conversions == 1:
        return "first_conversion"
    if status in ("promoting", "first_promotion", "promoted"):
        return "first_promotion"
    return "registered"


def compute(store) -> dict:
    counts = {s: 0 for s in STAGES}
    for ps in store.all_ids("partnership"):
        stage = stage_of(store, ps)
        if not stage:
            continue
        counts[stage] += 1
        current = (store.profile(ps)["slots"].get("lifecycle") or [{}])[0].get("value")
        if current != stage:
            store.remember(ps, facts=[{"slot": "lifecycle", "value": stage}], source="record",
                           source_ref=f"lifecycle:{stage}:{clock.day(clock.now())}", by="import", recorder="lifecycle")
    return counts
