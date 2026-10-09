"""The relsend worker.

    python3 -m relcore.sender.worker --once     intake + restrictions + drain, then exit (tests, cron)
    python3 -m relcore.sender.worker            loop (systemd relsend.service)

Intake verifies every approved file: HMAC in constant time, the payload hash recomputed over the final bundle,
the approver against root owners.json, the decision, the approval's expiry, and that neither the approval id nor
the action was seen before. Then each message is checked again right before it goes out.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import timedelta

from .. import canonical, clock, config, copy, spool
from ..adapters import SendError, provider_for
from ..compose import final_text
from ..db import connect, tx
from ..db.sends import SCHEMA
from . import checks

DEFAULTS = {"windows": {"sms": {"start": "09:00", "end": "20:00"}, "email": {"start": "07:00", "end": "21:00"}},
            "caps": {"per_day": 1, "per_week": 2, "replies_exempt": True},
            "consent_required": {"sms": ["express", "existing_relationship_sms"],
                                 "email": ["existing_relationship", "express", "public_business_address"]},
            "pacing_seconds": 3, "retry_minutes": 10, "window_retry_minutes": 15}


class Worker:
    def __init__(self, paths: config.Paths | None = None, env: dict | None = None, providers: dict | None = None):
        clock.refuse_fake_clock("relsend")
        self.paths = paths or config.resolve("send")
        self.home = self.paths.send_home or self.paths.home
        self.home.mkdir(parents=True, exist_ok=True)
        self.con = connect(self.paths.sends_db, SCHEMA)
        self.env = dict(env if env is not None else os.environ)
        self.providers = providers or {}
        root = config.root_json(self.paths, "sender.json") or {}
        self.cfg = {**DEFAULTS, **{k: v for k, v in root.items() if k in DEFAULTS}}
        self.sender = root
        self._recover_inflight()

    # ------------------------------------------------------------- helpers
    def _audit(self, action, ref=None, detail=None, actor="relsend"):
        self.con.execute("INSERT INTO audit (at, actor, action, ref, detail) VALUES (?,?,?,?,?)",
                         (clock.iso(), actor, action, ref, json.dumps(detail or {}, sort_keys=True)))

    def halt(self, reason: str, row_id=None) -> None:
        (self.home / "HALT").write_text(f"{clock.iso()} {reason}\n")
        spool.write(self.paths.spool / "alerts", f"alert-{int(time.time() * 1000)}.json",
                    {"kind": "halt", "reason": reason, "row_id": row_id, "at": clock.iso()})
        with tx(self.con):
            self._audit("halt", str(row_id or ""), {"reason": reason})

    def _recover_inflight(self) -> None:
        """A row left in `sending` by a crash may or may not have gone out: unknown, halt, never resend."""
        stuck = self.con.execute("SELECT row_id FROM outbox WHERE state='sending'").fetchall()
        for r in stuck:
            with tx(self.con):
                self.con.execute("UPDATE outbox SET state='unknown', reason='process stopped mid-send', updated_at=? WHERE row_id=?",
                                 (clock.iso(), r["row_id"]))
        if stuck:
            self.halt("a send was interrupted; check the provider before resolving", stuck[0]["row_id"])

    def contracts_passed(self, channel: str) -> bool:
        kinds = {r["kind"] for r in self.con.execute(
            "SELECT kind FROM contract_runs WHERE channel=? AND ok=1", (channel,))}
        return {"positive", "negative"} <= kinds

    def live(self, channel: str) -> bool:
        wanted = {c.strip() for c in self.env.get("RELSEND_LIVE_CHANNELS", "").split(",") if c.strip()}
        return channel in wanted and self.contracts_passed(channel)

    def provider(self, channel: str):
        if channel in self.providers:
            return self.providers[channel]
        return provider_for(channel, self.live(channel), self.env, self.con)

    def owners(self) -> set:
        data = config.root_json(self.paths, "owners.json", {"owners": []}) or {"owners": []}
        return {x for o in data.get("owners", []) for x in (o.get("slack_member_id"), o.get("console_user")) if x}

    # ------------------------------------------------------------- intake
    def verify(self, doc: dict) -> str | None:
        a, sig, bundle = doc.get("approval") or {}, doc.get("signature"), doc.get("bundle") or {}
        if not canonical.verify(config.read_key(self.paths.key_file), a, sig):
            return "bad signature"
        if a.get("key_id") != canonical.KEY_ID:
            return "unknown key id"
        if bundle.get("action_id") != a.get("action_id"):
            return "bundle and approval disagree"
        if canonical.payload_hash(bundle) != a.get("payload_hash"):
            return "payload changed after approval"
        if a.get("approver") not in self.owners():
            return "approver is not an owner"
        if clock.parse(a["expires_at"]) <= clock.now():
            return "approval expired"
        if self.con.execute("SELECT 1 FROM approved_actions WHERE approval_id=? OR action_id=?",
                            (a["approval_id"], a["action_id"])).fetchone():
            return "replayed approval"
        return None

    def intake(self) -> dict:
        out = {"queued": 0, "rejected": 0, "refused": 0}
        for path in spool.entries(self.paths.spool / "approved"):
            if self.con.execute("SELECT 1 FROM approvals_seen WHERE file=?", (path.name,)).fetchone():
                continue
            if path.name.startswith("release-"):
                with tx(self.con):
                    self.con.execute("INSERT INTO approvals_seen VALUES (?,?,?,?)", (path.name, None, "release (for trp)", clock.iso()))
                continue
            try:
                doc = spool.read(path)
                problem = self.verify(doc)
            except (ValueError, KeyError, OSError) as err:
                doc, problem = {}, f"unreadable: {err}"
            a = doc.get("approval") or {}
            with tx(self.con):
                if problem:
                    self.con.execute("INSERT INTO approvals_seen VALUES (?,?,?,?)", (path.name, a.get("approval_id"), f"refused: {problem}", clock.iso()))
                    self._audit("approval_refused", path.name, {"problem": problem})
                    out["refused"] += 1
                    continue
                self.con.execute("INSERT INTO approved_actions VALUES (?,?,?,?,?,?,?,?,?)",
                                 (a["action_id"], a["approval_id"], a["payload_hash"], a["approver"], a["decided_at"], a["expires_at"],
                                  doc["bundle"].get("prepared_at"), clock.iso(), a["decision"]))
                self.con.execute("INSERT INTO approvals_seen VALUES (?,?,?,?)", (path.name, a["approval_id"], a["decision"], clock.iso()))
                if a["decision"] != "approved":
                    out["rejected"] += 1
                    continue
                for m in sorted(doc["bundle"]["messages"], key=lambda m: m["n"]):
                    address = canonical.address_norm(m["channel"], m["address"])
                    text = final_text(m["channel"], m["body"], self.sender, first_in_thread=bool(m.get("first_touch")))
                    lint = copy.lint(m["channel"], m["body"], subject=m.get("subject", ""), first_touch=bool(m.get("first_touch")), profile=m.get("lint_profile"),
                                     sender=self.sender)
                    state, reason = ("queued", None) if lint["ok"] else ("blocked", "; ".join(lint["errors"]))
                    self.con.execute(
                        "INSERT INTO outbox (action_id, n, person_id, partnership_id, channel, address, subject, body, final_body, "
                        "first_touch, consent_basis, reply_to, timezone, state, reason, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (a["action_id"], m["n"], m.get("person_id"), m.get("partnership_id"), m["channel"], address, m.get("subject"),
                         m["body"], text, int(bool(m.get("first_touch"))), m.get("consent_basis"), m.get("reply_to"),
                         m.get("timezone"), state, reason, clock.iso()))
                    out["queued"] += state == "queued"
                self._audit("approval_accepted", a["action_id"], {"messages": len(doc["bundle"]["messages"])})
        return out

    def restrictions(self) -> int:
        """Add-only restrictions and withdrawals from trp (spool/suppress) and the inbox floor."""
        n = 0
        for path in spool.entries(self.paths.spool / "suppress"):
            if self.con.execute("SELECT 1 FROM spool_cursor WHERE dir='suppress' AND name=?", (path.name,)).fetchone():
                continue
            try:
                doc = spool.read(path)
            except (ValueError, OSError):
                continue
            with tx(self.con):
                if doc.get("kind") == "withdraw" and doc.get("action_id"):
                    self.con.execute("INSERT OR IGNORE INTO withdrawn VALUES (?,?,?)", (doc["action_id"], clock.iso(), doc.get("reason")))
                elif doc.get("kind") == "suppress":
                    for item in doc.get("items", []):
                        if item.get("type") in ("entity", "address") and item.get("value"):
                            value = item["value"] if item["type"] == "entity" else canonical.address_norm(
                                "email" if "@" in item["value"] else "sms", item["value"])
                            self.con.execute("INSERT OR IGNORE INTO suppression VALUES (?,?,?,?,?,?)",
                                             (item["type"], value, item.get("channel", "*"), item.get("reason", "requested"), "trp", clock.iso()))
                elif doc.get("kind") == "touch":
                    self.con.execute("INSERT INTO touches (person_key, address, channel, at, source) VALUES (?,?,?,?,?)",
                                     (doc.get("person_id") or "", doc.get("address") or "", doc.get("channel"), doc.get("at") or clock.iso(), "trp"))
                self.con.execute("INSERT INTO spool_cursor VALUES ('suppress', ?, ?)", (path.name, clock.iso()))
            n += 1
        return n

    # ------------------------------------------------------------- drain
    def _result(self, row: dict, state: str, reason: str | None = None, provider_msg_id: str | None = None) -> None:
        spool.write(self.paths.spool / "results", f"res-{row['row_id']:08d}-{state}.json",
                    {"row_id": row["row_id"], "action_id": row["action_id"], "n": row["n"], "person_id": row["person_id"],
                     "partnership_id": row["partnership_id"], "channel": row["channel"], "state": state, "reason": reason,
                     "provider_msg_id": provider_msg_id, "first_touch": bool(row["first_touch"]), "at": clock.iso(),
                     "final_body": row["final_body"] if state == "sent" else None})

    def _set(self, row_id: int, state: str, **kw) -> None:
        sets = ", ".join(f"{k}=?" for k in kw)
        self.con.execute(f"UPDATE outbox SET state=?, updated_at=?{', ' + sets if sets else ''} WHERE row_id=?",
                         (state, clock.iso(), *kw.values(), row_id))

    def drain(self, limit: int | None = None) -> dict:
        out = {"sent": 0, "skipped": 0, "failed": 0, "deferred": 0, "unknown": 0, "halted": None}
        rows = [dict(r) for r in self.con.execute(
            "SELECT * FROM outbox WHERE state='queued' AND (next_try_at IS NULL OR next_try_at <= ?) ORDER BY action_id, n",
            (clock.iso(),))]
        last_send = 0.0
        for row in rows[:limit] if limit else rows:
            stop = checks.stop_reason(self.paths, self.home)  # before every single message
            if stop:
                out["halted"] = stop
                break
            action = self.con.execute("SELECT * FROM approved_actions WHERE action_id=?", (row["action_id"],)).fetchone()
            if clock.parse(action["expires_at"]) <= clock.now():
                with tx(self.con):
                    self._set(row["row_id"], "expired", reason="approval expired before it could be sent")
                self._result(row, "expired", "approval expired")
                out["skipped"] += 1
                continue
            reason = (checks.suppression_reason(self.con, row) or checks.consent_reason(row, self.cfg)
                      or checks.first_touch_reason(self.con, row)
                      or checks.stale_reason(self.con, row, action["prepared_at"]))
            if reason:
                with tx(self.con):
                    self._set(row["row_id"], "skipped", reason=reason)
                self._result(row, "skipped", reason)
                out["skipped"] += 1
                continue
            person_key = row["person_id"] or row["address"]
            reason = checks.caps_reason(self.con, person_key, row["address"], self.cfg, row=row) or checks.window_reason(row, self.cfg)
            if reason:  # try again later, never dropped silently
                with tx(self.con):
                    self._set(row["row_id"], "queued", reason=reason,
                              next_try_at=clock.iso(clock.now() + timedelta(minutes=self.cfg["window_retry_minutes"])))
                out["deferred"] += 1
                continue
            wait = self.cfg["pacing_seconds"] - (time.time() - last_send)
            if wait > 0 and last_send:
                time.sleep(wait)
            provider = self.provider(row["channel"])
            with tx(self.con):
                self._set(row["row_id"], "sending", attempts=row["attempts"] + 1, provider=getattr(provider, "name", "?"))
            try:
                res = provider.send(row)
            except SendError as err:
                if err.accepted_maybe:
                    with tx(self.con):
                        self._set(row["row_id"], "unknown", reason=str(err))
                    self._result(row, "unknown", str(err))
                    self.halt(f"unknown outcome for {row['action_id']} #{row['n']}: {err}", row["row_id"])
                    out["unknown"] += 1
                    out["halted"] = "unknown outcome"
                    break
                if err.retry:
                    with tx(self.con):
                        self._set(row["row_id"], "queued", reason=str(err),
                                  next_try_at=clock.iso(clock.now() + timedelta(minutes=self.cfg["retry_minutes"] * (row["attempts"] + 1))))
                    out["deferred"] += 1
                    continue
                with tx(self.con):
                    self._set(row["row_id"], "failed", reason=str(err))
                self._result(row, "failed", str(err))
                out["failed"] += 1
                continue
            last_send = time.time()
            with tx(self.con):
                self._set(row["row_id"], "sent", provider_msg_id=res["provider_msg_id"], reason=None)
                self.con.execute("INSERT INTO touches (person_key, address, channel, at, row_id) VALUES (?,?,?,?,?)",
                                 (person_key, row["address"], row["channel"], clock.iso(), row["row_id"]))
                if row["first_touch"]:
                    for key in (f"person:{row['person_id']}", f"address:{row['address']}"):
                        self.con.execute("INSERT OR IGNORE INTO first_touch VALUES (?,?,?)", (key, row["row_id"], clock.iso()))
                self.con.execute("INSERT INTO limiter VALUES (?,?)", (row["channel"], clock.iso()))
            self._result(row, "sent", provider_msg_id=res["provider_msg_id"])
            out["sent"] += 1
        return out

    def run_once(self) -> dict:
        return {"intake": self.intake(), "restrictions": self.restrictions(), "drain": self.drain()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relsend")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    a = ap.parse_args(argv)
    worker = Worker()
    while True:
        result = worker.run_once()
        if a.once:
            print(json.dumps(result))
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
