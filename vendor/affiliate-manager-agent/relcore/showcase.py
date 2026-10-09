"""The sample program after one full loop, for screenshots and demos (everything fictional, nothing leaves the folder).

    python3 -m relcore showcase --out <dir>

Builds the Harborline sample, then runs the real code through one cycle: a first-touch wave with its holdout, the
owner's signed approval, the sender's checks and a dry send, the sample's fifteen replies read by the inbox and
triaged by the floor, the sample call turned into commitments, an answer to the partner who offered a time, a
partner plan for Peak Orthopedics and the scorecard. Open <dir>/vault in Obsidian.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from . import clock
from .sample import OWNERS, SAMPLE, build

PLAN = {"offers": ["the post-op knee program", "the return to running screen"],
        "situations": ["A patient is cleared by their surgeon but still nervous about stairs",
                       "A runner keeps tweaking the same knee before race season",
                       "Someone asks where to go after physical therapy ends"],
        "message": "If your knee still is not right, Harborline in Charlotte gets people back to moving. Use my link to book.",
        "assets": ["a referral pad for the front desk", "a one-page brief for the surgeons"],
        "next_check_in": "2026-10-08"}


def _at(when: str) -> None:
    os.environ["RELCORE_NOW"] = when


def run(out: Path) -> dict:
    before = os.environ.get("RELCORE_NOW")
    try:
        return _run(out)
    finally:
        if before is None:
            os.environ.pop("RELCORE_NOW", None)
        else:
            os.environ["RELCORE_NOW"] = before


def _run(out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    built = build(out)
    paths, store = built["paths"], built["store"]
    etc = paths.etc
    etc.mkdir(parents=True, exist_ok=True)
    (etc / "owners.json").write_text(json.dumps(OWNERS))
    (etc / "sender.json").write_text(json.dumps({"name": "Sam Rivera", "title": "Owner", "business": "Harborline Physical Therapy",
                                                 "physical_address": "100 Example Street, Charlotte, NC 28202", "pacing_seconds": 0}))
    (etc / "approvals.json").write_text(json.dumps({"approval_valid_hours": 24, "slack_channel": "C0SHOWCASE"}))
    paths.control.mkdir(parents=True, exist_ok=True)
    paths.key_file.write_bytes(("ab" * 32).encode())
    for sub in ("prepared", "suppress", "approved", "results", "inbound", "alerts"):
        (paths.spool / sub).mkdir(parents=True, exist_ok=True)

    from . import actions, graph, ingest, plan, replies, scorecard
    from .adapters.mock import MockProvider
    from .approvals.service import Service
    from .sender.inbox import FilesInbox, Inbox
    from .sender.worker import Worker
    owner = OWNERS["owners"][0]
    mock = MockProvider()
    worker = Worker(paths, env={}, providers={"sms": mock, "email": mock})

    def approve_all():
        svc = Service(paths)
        svc.scan()
        for b in svc.pending():
            if b["state"] == "shown":
                svc.decide(b["action_id"], "approve", approver=owner, via="console")

    _at("2026-10-01T15:00:00Z")
    wave = actions.prepare_wave(store, employee=None)
    approve_all()
    worker.run_once()
    ingest.run(store)

    _at("2026-10-01T19:00:00Z")  # the replies arrive, and the call recording lands in the call inbox
    Inbox(paths, env={}, readers=[FilesInbox(SAMPLE / "inbound")]).poll()
    drop = paths.home / "call-inbox"
    drop.mkdir(parents=True, exist_ok=True)
    for p in (SAMPLE / "calls").iterdir():
        shutil.copy(p, drop / p.name)
    ingest.run(store)

    answered = []
    for row in replies.pending(store):
        if row["intent"] != "accept_with_time":
            continue
        raw = store.con.execute("SELECT * FROM inbound WHERE id=?", (row["inbound_id"],)).fetchone()
        first = store.profile(row["person"]["id"])["fields"].get("first_name") or row["person"]["name"].split()[0]
        body = f"Perfect, {first}. {raw['matched'].capitalize()} works for me, a calendar hold is on its way."
        out = replies.prepare(store, employee=wave.get("selection", {}).get("employee") or "default",
                              replies=[{"inbound_id": row["inbound_id"], "body": body,
                                        "context_digest": graph.context(store, row["context_ref"])["context_digest"]}])
        answered.append(out.get("action_id"))
    _at("2026-10-01T19:30:00Z")
    approve_all()
    worker.run_once()
    ingest.run(store)

    peak = store.resolve({"key": f"Harborline Physical Therapy|{store.resolve({'domain': 'peakortho.example.com'})}|F6.B.1"})
    saved = plan.save(store, {"id": peak}, partner=PLAN,
                      internal={"promised": ["send the referral pad", "bring the surgeon brief to the Wednesday visit"],
                                "measure": "first referral booked from the brief"}, employee="trp-f06-power-partner-builder")
    card = scorecard.write(store, days=30)
    for emp in {r["employee"] for r in store.con.execute("SELECT DISTINCT employee FROM actions WHERE employee IS NOT NULL")}:
        store.vault.render_employee(emp)
    summary = {"vault": str(paths.vault), "wave": wave.get("action_id"), "wave_messages": wave["messages"],
               "sent": len(mock.sent), "replies_answered": answered, "plan": saved.get("plan"), "plan_ok": saved.get("ok"),
               "scorecard": card["note"], "cards": sum(1 for _ in paths.vault.rglob("*.md")), "at": clock.iso()}
    worker.con.close()
    store.con.close()
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relcore showcase")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not SAMPLE.is_dir():
        print("the showcase builds the True Revenue Partner sample program, which this install does not include")
        return 2
    print(json.dumps(run(Path(a.out)), indent=1))
    return 0
