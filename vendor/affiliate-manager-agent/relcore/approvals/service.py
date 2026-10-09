"""Approval core shared by the Slack socket app and the SSH console."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta

from .. import canonical, clock, config, copy, ids, spool
from ..compose import final_text
from ..db import connect, tx
from ..db.approvals import SCHEMA

ACTION_ID = re.compile(r"^ac_[0-9a-f]{10}$")
ENTITY_ID = re.compile(r"^(pe|pt|ps)_[0-9a-f]{10}$")


class Refused(Exception):
    pass


class Service:
    def __init__(self, paths: config.Paths | None = None):
        clock.refuse_fake_clock("relapprove")
        self.paths = paths or config.resolve("approve")
        self.home = self.paths.approve_home or self.paths.home
        self.home.mkdir(parents=True, exist_ok=True)
        self.con = connect(self.paths.approvals_db, SCHEMA)
        self.settings = config.root_json(self.paths, "approvals.json", {}) or {}

    # ------------------------------------------------------------- root config
    def owners(self) -> list[dict]:
        data = config.root_json(self.paths, "owners.json", {"owners": []}) or {"owners": []}
        return [o for o in data.get("owners", []) if o.get("name")]

    def owner_for(self, *, slack_user: str | None = None, console_user: str | None = None) -> dict | None:
        for o in self.owners():
            if slack_user and o.get("slack_member_id") == slack_user:
                return o
            if console_user and o.get("console_user") == console_user:
                return o
        return None

    def sender(self) -> dict:
        s = config.root_json(self.paths, "sender.json")
        if not s:
            raise Refused("sender.json is missing from the root config (install/connect-sender.sh)")
        return s

    def key(self) -> bytes:
        return config.read_key(self.paths.key_file)

    # ------------------------------------------------------------- intake
    def _withdrawn(self, action_id: str) -> bool:
        return (self.paths.spool / "suppress" / f"withdraw-{action_id}.json").exists()

    def check_bundle(self, bundle: dict) -> list[str]:
        problems = []
        if bundle.get("format") != "relcore-bundle/v1" or not ACTION_ID.match(bundle.get("action_id", "")):
            return ["not a relcore bundle"]
        if clock.parse(bundle["expires_at"]) <= clock.now():
            problems.append("expired before approval")
        sender = self.sender()
        seen = set()
        for m in bundle.get("messages", []):
            if m["channel"] not in ("email", "sms"):
                problems.append(f"{m['n']}: {m['channel']} cannot be sent")
            if not m.get("consent_basis"):
                problems.append(f"{m['n']}: no consent basis")
            addr = canonical.address_norm(m["channel"], m.get("address") or "")
            if not addr or addr in seen:
                problems.append(f"{m['n']}: missing or duplicate address")
            seen.add(addr)
            result = copy.lint(m["channel"], m["body"], subject=m.get("subject", ""), first_touch=bool(m.get("first_touch")), profile=m.get("lint_profile"),
                               sender=sender)
            if not result["ok"]:
                problems.append(f"{m['n']}: {'; '.join(result['errors'])}")
        if not bundle.get("messages"):
            problems.append("no messages")
        return problems

    def scan(self) -> list[dict]:
        """Take in new bundles from spool/prepared. Returns the ones newly shown (for posting to Slack)."""
        shown = []
        for path in spool.entries(self.paths.spool / "prepared"):
            try:
                bundle = spool.read(path)
            except (ValueError, OSError) as err:
                self._audit("bundle_unreadable", path.name, {"error": str(err)})
                continue
            aid = bundle.get("action_id", "")
            if not ACTION_ID.match(aid) or path.name != f"{aid}.json":
                continue
            h = canonical.payload_hash(bundle)
            row = self.con.execute("SELECT payload_hash, state FROM bundles_seen WHERE action_id=?", (aid,)).fetchone()
            if row and row["payload_hash"] == h:
                continue
            if row and row["state"] not in ("shown", "invalid"):
                continue  # decided or withdrawn: a changed file never reopens it
            state = "withdrawn" if self._withdrawn(aid) else "shown"
            problems = self.check_bundle(bundle) if state == "shown" else []
            if problems:
                state = "invalid"
            with tx(self.con):
                self.con.execute("INSERT OR REPLACE INTO bundles_seen (action_id, payload_hash, body, state, problems, shown_at) "
                                 "VALUES (?,?,?,?,?,?)", (aid, h, canonical.encode(bundle).decode(), state, json.dumps(problems),
                                                          clock.iso()))
                self._audit("bundle_" + state + ("_changed" if row else ""), aid, {"payload_hash": h, "problems": problems})
            if state in ("shown", "invalid"):
                shown.append({"action_id": aid, "state": state, "problems": problems, "card": self.card_text(aid)})
        return shown

    def shown_bundle(self, action_id: str) -> tuple[dict, dict]:
        row = self.con.execute("SELECT * FROM bundles_seen WHERE action_id=?", (action_id,)).fetchone()
        if not row:
            raise Refused(f"{action_id} has not been shown")
        return json.loads(row["body"]), dict(row)

    def card_text(self, action_id: str) -> str:
        """What the owner reads. Built here from the shown bundle bytes, never from text trp wrote."""
        b, row = self.shown_bundle(action_id)
        sender = self.sender()
        lines = [f"*{b['kind']} {action_id}* from {b.get('employee')}, {len(b['messages'])} message(s), "
                 f"voice {b['voice']['name'] if b.get('voice') else 'none'}, expires {b['expires_at']}"]
        problems = json.loads(row["problems"])
        if problems:
            lines += ["*Cannot be approved:*", *[f"- {p}" for p in problems]]
        sel = b.get("selection") or {}
        if sel:
            lines.append(f"Picked {sel.get('picked')}, held out {sel.get('held_out')}, skipped "
                         + ", ".join(f"{k} {v}" for k, v in (sel.get("skipped") or {}).items()))
        if b.get("anomalies"):
            lines += ["Anomalies:", *[f"- {a}" for a in b["anomalies"]]]
        for m in sorted(b["messages"], key=lambda m: m["n"]):
            text = final_text(m["channel"], m["body"], sender, first_in_thread=bool(m.get("first_touch")))
            lines += ["", f"*{m['n']}.* {m.get('recipient', '')} · {m['channel']} · {m['address']}"
                      + (f" · subject: {m['subject']}" if m.get("subject") else "")]
            lines += [f"> {l}" if l else ">" for l in text.splitlines()]
        lines += ["", f"Reply `approve {action_id}`, `approve {action_id} except 4, 17`, `edit {action_id} 9: <text>` or "
                      f"`reject {action_id}`."]
        return "\n".join(lines)

    # ------------------------------------------------------------- decide
    def decide(self, action_id: str, decision: str, *, approver: dict, via: str, exclusions=(), edits: dict | None = None) -> dict:
        if not ACTION_ID.match(action_id or ""):
            raise Refused("bad action id")
        if not approver or approver not in self.owners():
            raise Refused("only an owner in /etc/relcore/owners.json can decide")
        if decision not in ("approve", "reject"):
            raise Refused("decision must be approve or reject")
        bundle, row = self.shown_bundle(action_id)
        if row["state"] != "shown":
            raise Refused(f"{action_id} is {row['state']}: {', '.join(json.loads(row['problems'])) or 'not open'}")
        if self.con.execute("SELECT 1 FROM decisions WHERE action_id=?", (action_id,)).fetchone():
            raise Refused(f"{action_id} was already decided")
        if self._withdrawn(action_id):
            raise Refused(f"{action_id} was withdrawn")
        current = self.paths.spool / "prepared" / f"{action_id}.json"
        if current.exists() and canonical.payload_hash(spool.read(current)) != row["payload_hash"]:
            raise Refused(f"{action_id} changed after it was shown; it will be shown again")
        if clock.parse(bundle["expires_at"]) <= clock.now():
            raise Refused(f"{action_id} expired")
        ns = {m["n"] for m in bundle["messages"]}
        exclusions = sorted({int(n) for n in exclusions})
        if set(exclusions) - ns:
            raise Refused(f"no message numbered {sorted(set(exclusions) - ns)}")
        edits = {**{int(k): v for k, v in json.loads(row.get("edits") or "{}").items()},
                 **{int(k): v for k, v in (edits or {}).items()}}
        if set(edits) - ns:
            raise Refused(f"no message numbered {sorted(set(edits) - ns)}")
        sender = self.sender()
        final = dict(bundle)
        msgs = []
        for m in bundle["messages"]:
            if m["n"] in exclusions:
                continue
            m = dict(m)
            if m["n"] in edits:
                m["body"] = edits[m["n"]].strip()
                check = copy.lint(m["channel"], m["body"], subject=m.get("subject", ""), first_touch=bool(m.get("first_touch")), profile=m.get("lint_profile"),
                                  sender=sender)
                if not check["ok"]:
                    raise Refused(f"edit {m['n']} breaks the copy rules: {'; '.join(check['errors'])}")
                m["edited_by_owner"] = True
            msgs.append(m)
        final["messages"] = msgs if decision == "approve" else []
        if decision == "approve" and not msgs:
            raise Refused("every message is excluded; reject instead")
        hours = float(self.settings.get("approval_valid_hours", 24))
        approval = {"approval_id": ids.new_id("approval"), "action_id": action_id, "decision": "approved" if decision == "approve" else "rejected",
                    "payload_hash": canonical.payload_hash(final), "exclusions": exclusions,
                    "edits": {str(n): hashlib.sha256(canonical.encode(v)).hexdigest()[:16] for n, v in sorted(edits.items())},
                    "approver": approver.get("slack_member_id") or approver.get("console_user"), "decided_at": clock.iso(),
                    "expires_at": clock.iso(clock.now() + timedelta(hours=hours)), "key_id": canonical.KEY_ID}
        signature = canonical.sign(self.key(), approval)
        spool.write(self.paths.spool / "approved", f"{action_id}.json",
                    {"approval": approval, "signature": signature, "bundle": final, "approver_name": approver["name"]})
        with tx(self.con):
            self.con.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (approval["approval_id"], action_id, approval["decision"], approval["payload_hash"],
                              json.dumps(exclusions), json.dumps(approval["edits"]), approval["approver"], approver["name"], via,
                              approval["decided_at"], approval["expires_at"], signature))
            self.con.execute("UPDATE bundles_seen SET state=? WHERE action_id=?", (approval["decision"], action_id))
            self._audit("decided", action_id, {"decision": approval["decision"], "via": via, "excluded": exclusions,
                                               "edited": sorted(edits)}, actor=approver["name"])
        return {"approval_id": approval["approval_id"], "decision": approval["decision"], "messages": len(final["messages"]),
                "expires_at": approval["expires_at"]}

    def edit(self, action_id: str, n: int, text: str, *, approver: dict) -> dict:
        """Owner rewrites one message. It is linted now; the approval later signs the edited text."""
        if not approver or approver not in self.owners():
            raise Refused("only an owner can edit")
        bundle, row = self.shown_bundle(action_id)
        if row["state"] != "shown":
            raise Refused(f"{action_id} is {row['state']}")
        m = next((m for m in bundle["messages"] if m["n"] == int(n)), None)
        if not m:
            raise Refused(f"no message {n}")
        check = copy.lint(m["channel"], text, subject=m.get("subject", ""), first_touch=bool(m.get("first_touch")), profile=m.get("lint_profile"), sender=self.sender())
        if not check["ok"]:
            raise Refused(f"edit breaks the copy rules: {'; '.join(check['errors'])}")
        edits = json.loads(row.get("edits") or "{}")
        edits[str(int(n))] = text.strip()
        with tx(self.con):
            self.con.execute("UPDATE bundles_seen SET edits=? WHERE action_id=?", (json.dumps(edits, sort_keys=True), action_id))
            self._audit("edited", action_id, {"n": int(n)}, actor=approver["name"])
        return {"action_id": action_id, "edited": int(n), "final": check.get("final") or text}

    def release_hold(self, entity_id: str, kind: str, *, approver: dict, via: str) -> dict:
        if not ENTITY_ID.match(entity_id or "") or kind not in ("identity", "complaint", "dispute", "staff_handled"):
            raise Refused("bad hold")
        if not approver or approver not in self.owners():
            raise Refused("only an owner can release a hold")
        approval = {"approval_id": ids.new_id("approval"), "action_id": f"release:{entity_id}:{kind}", "decision": "release_hold",
                    "payload_hash": hashlib.sha256(f"{entity_id}|{kind}".encode()).hexdigest(), "exclusions": [], "edits": {},
                    "approver": approver.get("slack_member_id") or approver.get("console_user"), "decided_at": clock.iso(),
                    "expires_at": clock.plus(hours=24), "key_id": canonical.KEY_ID}
        sig = canonical.sign(self.key(), approval)
        spool.write(self.paths.spool / "approved", f"release-{entity_id}-{approval['approval_id'][3:]}.json",
                    {"approval": approval, "signature": sig, "release": {"entity_id": entity_id, "kind": kind},
                     "approver_name": approver["name"]})
        with tx(self.con):
            self.con.execute("INSERT INTO holds_released VALUES (?,?,?,?,?)", (approval["approval_id"], entity_id, kind,
                                                                               approval["approver"], approval["decided_at"]))
            self._audit("hold_released", entity_id, {"kind": kind, "via": via}, actor=approver["name"])
        return {"released": entity_id, "kind": kind}

    def alerts(self) -> list[dict]:
        """Sender alerts (unknown outcomes, halts, an unconfigured inbox) not yet posted to the approvals channel."""
        out = []
        for path in spool.entries(self.paths.spool / "alerts"):
            if self.con.execute("SELECT 1 FROM alerts_seen WHERE name=?", (path.name,)).fetchone():
                continue
            try:
                doc = spool.read(path)
            except (ValueError, OSError):
                continue
            out.append({"name": path.name, "text": f"Sender alert ({doc.get('kind', 'alert')}): {doc.get('reason', '')}. "
                        "Check the provider, then use the relsend console (status, unknown, resolve, clear-halt)."})
        return out

    def alert_posted(self, name: str) -> None:
        with tx(self.con):
            self.con.execute("INSERT OR IGNORE INTO alerts_seen VALUES (?,?)", (name, clock.iso()))

    def pending(self) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT action_id, state, problems, shown_at FROM bundles_seen WHERE state IN ('shown','invalid') ORDER BY shown_at")]

    def _audit(self, action, ref, detail=None, actor="relapprove"):
        self.con.execute("INSERT INTO audit (at, actor, action, ref, detail) VALUES (?,?,?,?,?)",
                         (clock.iso(), actor, action, ref, json.dumps(detail or {}, sort_keys=True)))


COMMAND = re.compile(r"^\s*(approve|reject|edit)\s+(ac_[0-9a-f]{10})\s*(.*)$", re.I | re.S)


def parse_command(text: str) -> dict | None:
    """`approve ac_x`, `approve ac_x except 4, 17`, `edit ac_x 9: new text`, `reject ac_x`."""
    m = COMMAND.match(text or "")
    if not m:
        return None
    verb, aid, rest = m.group(1).lower(), m.group(2), m.group(3).strip()
    if verb == "approve":
        ex = re.match(r"^except\s+([\d,\s]+)$", rest, re.I)
        if rest and not ex:
            return None
        return {"verb": "approve", "action_id": aid, "exclusions": [int(x) for x in re.findall(r"\d+", ex.group(1))] if ex else []}
    if verb == "reject":
        return {"verb": "reject", "action_id": aid} if not rest else None
    ed = re.match(r"^(\d+)\s*:\s*(.+)$", rest, re.S)
    return {"verb": "edit", "action_id": aid, "n": int(ed.group(1)), "text": ed.group(2).strip()} if ed else None
