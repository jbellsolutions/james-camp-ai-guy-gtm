"""Program registers (spec 6.8). Eligibility is frozen before a program's first send; engagement is append-only;
the holdout is a stratified random slice never contacted until the program review.

    python3 -m relcore registers freeze <program> [--segments past_producer,registered_never_produced]
"""
from __future__ import annotations

import hashlib
import json

from . import clock
from .db import tx

ELIGIBLE_DEFAULT = ("past_producer", "registered_never_produced", "thin_record")


def snapshot(store, ps_id: str) -> dict:
    p = store.profile(ps_id)
    return {"segment": p["fields"].get("segment"), "exclusions": p["fields"].get("exclusions") or [],
            "record": {k: p["slots"][k][0]["value"] for k in ("tier", "joined", "conversions", "last_conversion", "production_stage")
                       if k in p["slots"]}}


def freeze(store, program: str, segments=ELIGIBLE_DEFAULT) -> dict:
    """Record who is eligible and why, once. A second freeze of the same program is refused."""
    if store.con.execute("SELECT 1 FROM eligibility WHERE program=? LIMIT 1", (program,)).fetchone():
        raise ValueError(f"eligibility for {program} is already frozen")
    rule = f"segment in {sorted(segments)}; no exclusions; inactive {store.settings['eligibility']['inactive_days']} days"
    as_of = clock.iso()
    rows, all_snap = [], {}
    for ps in store.all_ids("partnership"):
        snap = snapshot(store, ps)
        all_snap[ps] = snap
        if snap["segment"] in segments and not snap["exclusions"]:
            rows.append((program, ps, rule, as_of, json.dumps(snap, sort_keys=True)))
    digest = hashlib.sha256(json.dumps(all_snap, sort_keys=True).encode()).hexdigest()
    with tx(store.con):
        for r in rows:
            store.con.execute("INSERT INTO eligibility VALUES (?,?,?,?,?,?)", (*r, digest))
        store._audit("eligibility_frozen", program, {"eligible": len(rows), "snapshot_hash": digest, "rule": rule})
        for ps in (r[1] for r in rows):
            store._set_fields(ps, "partnership", {"eligibility": f"{program}@{clock.day(as_of)}"}, "import")
    store.vault.render_around({r[1] for r in rows})
    return {"program": program, "eligible": len(rows), "snapshot_hash": digest, "rule": rule}


def eligible(store, program: str) -> list[str]:
    return [r["entity_id"] for r in store.con.execute("SELECT entity_id FROM eligibility WHERE program=? ORDER BY entity_id", (program,))]


def main(argv: list[str]) -> int:
    import argparse
    from . import config
    from .store import Store
    ap = argparse.ArgumentParser(prog="relcore registers")
    ap.add_argument("action", choices=["freeze", "show"])
    ap.add_argument("program")
    ap.add_argument("--segments", default=",".join(ELIGIBLE_DEFAULT))
    a = ap.parse_args(argv)
    store = Store(config.resolve())
    if a.action == "freeze":
        print(json.dumps(freeze(store, a.program, tuple(a.segments.split(","))), indent=1))
    else:
        print(json.dumps(eligible(store, a.program), indent=1))
    return 0
