"""Simulation: a synthetic program of partners with a hidden truth, run through the whole loop over simulated days.

    python3 -m relcore sim [--seed 1 --seed 2] [--people 40] [--days 9] [--out report.md] [--keep DIR]
    python3 -m relcore sim --write-example charter/examples/sample-client/relationship/worked-example
    python3 -m relcore sim --check-example charter/examples/sample-client/relationship/worked-example

Each persona has a hidden truth drawn from the seed: how they will answer (one of the floor intents, or silence), how
long they take, whether they reveal their audience size (sometimes next to a health detail that must never be stored)
and whether they convert later. The loop then runs hour by hour on a fake clock in a throwaway root:

    the agent prepares waves -> the owner approves (signed) -> relsend checks and sends (mock provider, with an
    unknown outcome and a 429 injected) -> personas answer -> relsend reads the inbox -> trp ingests -> the agent
    drafts replies -> ... -> conversions arrive through the import path -> the scorecard

Replies are written by a templated stand-in for the model, one move per intent, revised when the checks refuse a
draft (refusals are counted). This proves the rules, not the quality of the model's writing.

Every invariant is checked from database state and the provider's own log, never from the loop's counters:
one first touch per person and address; nothing after an opt-out or a wrong number; SMS only inside 09:00 to 20:00
in the number's own zone; caps (1 a day, 2 a week); the holdout never contacted; an unknown outcome halts and is
never resent; the floor intent equals the hidden intent; engagement equals the hidden qualifying replies; nothing
never-store is stored; the audience sizes they told us are on the cards; the scorecard denominator equals the
reachable, consented count.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters.mock import MockProvider

START = "2026-10-05T12:00:00Z"  # a Monday, 08:00 in New York
EMP = "trp-f06-power-partner-builder"
OWNER = {"name": "Sam Rivera", "slack_member_id": "U0SIM00001", "console_user": "sam"}
AREAS = [("704", "America/New_York"), ("312", "America/Chicago"), ("303", "America/Denver"), ("213", "America/Los_Angeles")]
FIRST = ["Ana", "Ben", "Cara", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jo", "Kai", "Lena", "Milo", "Nia", "Omar",
         "Pia", "Quinn", "Rosa", "Sol", "Tess", "Uma", "Vic", "Wren", "Xavi", "Yara", "Zed"]
LAST = ["Diaz", "Lane", "Moss", "Park", "Reed", "Shaw", "Cole", "Hart", "Wolfe", "Vance", "Nash", "Kerr", "Byrd"]
SENSITIVE = "surgery"

# What each persona says first. Each phrase is checked against the keyword floor before the run (it must classify
# as its own intent on its own channel), so the comparison with the hidden truth is never circular.
PHRASES = {
    "accept_with_time": ["Sounds good, Wednesday afternoon?", "Sure, Thursday at 2pm works"],
    "accept": ["Sure, send it over.", "Yes please, happy to hear more"],
    "not_now": ["maybe next quarter", "Swamped right now, try me in January"],
    "opt_out": ["take me off your list", "STOP"],
    "help": ["HELP"],
    "wrong_number": ["Wrong number, no {first} here"],
    "identity_question": ["Is this a bot? It reads like one."],
    "complaint": ["You owe us for the May referrals and nobody has answered."],
    "not_interested": ["No thanks, we are all set"],
    "has_opportunity": ["Actually, I have a client who could use you. Who should she call?"],
    "wants_help": ["Send me the flyer and I will post it in the members group"],
    "commission_question": ["What's the commission on the new class pack?"],
    "question": ["What does a partnership with you usually look like?"],
    "general": ["hi, saw your flyer at the gym", "Our front desk talks about you a lot"],
}
WEIGHTS = {"silent": 22, "accept_with_time": 6, "accept": 8, "not_now": 8, "opt_out": 6, "help": 3, "wrong_number": 3,
           "identity_question": 3, "complaint": 2, "not_interested": 7, "has_opportunity": 4, "wants_help": 5,
           "commission_question": 4, "question": 6, "general": 9}
FOLLOW_UP = {"accept", "accept_with_time", "general", "question", "wants_help", "has_opportunity", "commission_question"}
UNITS = ["patients a month", "members", "clients", "followers"]


# ------------------------------------------------------------------ setup
class _Secrets:
    """Seeded stand-in for ids.secrets, so action ids (and so the whole run) repeat byte for byte for a seed."""
    def __init__(self, seed):
        self.rng = random.Random(f"ids:{seed}")

    def token_hex(self, n):
        return "".join(self.rng.choice("0123456789abcdef") for _ in range(n * 2))


def _personas(rng, n):
    out = []
    for i in range(n):
        area, tz = AREAS[i % len(AREAS)]
        first = FIRST[i % len(FIRST)] + ("" if i < len(FIRST) else str(i // len(FIRST) + 1))
        name = f"{first} {LAST[(i * 7) % len(LAST)]}"
        consent = ["sms"], ["email"], ["sms", "email"]
        channels = [] if i % 10 == 9 else consent[i % 3]
        kind = ["past_producer", "registered", "thin", "active"][0 if i % 8 == 7 else (i % 5) % 3] if i % 8 != 7 else "active"
        intent = rng.choices(list(WEIGHTS), weights=list(WEIGHTS.values()))[0]
        size = rng.choice([150, 400, 900, 2000, 12000])
        out.append({
            "i": i, "name": name, "first": first, "tz": tz, "phone": f"{area}-555-01{i:02d}", "email": f"{first.lower()}@p{i:02d}.example.com",
            "consent": channels, "kind": kind, "intent": intent, "delay_hours": rng.choice([1, 2, 3, 5, 8, 20, 30]),
            "phrase": rng.choice(PHRASES[intent]) if intent != "silent" else None,
            "reveals": intent in FOLLOW_UP and rng.random() < 0.7, "size": size, "unit": rng.choice(UNITS),
            "sensitive": rng.random() < 0.4, "converts": rng.random() < (0.45 if intent in FOLLOW_UP else 0.15)})
    return out


def _check_phrases():
    from . import intents
    bad = []
    for intent, texts in PHRASES.items():
        for t in texts:
            for ch in ("sms", "email"):
                got = intents.classify(t.format(first="Kim"), ch)["intent"]
                if got != intent:
                    bad.append(f"{t!r} on {ch}: floor says {got}, persona means {intent}")
    if bad:
        raise AssertionError("persona phrases disagree with the floor:\n" + "\n".join(bad))


class World:
    def __init__(self, seed: int, people: int, root: Path):
        self.seed, self.root = seed, root
        self.rng = random.Random(seed)
        os.environ.update(RELCORE_MODE="test", RELCORE_ROOT=str(root), RELCORE_NOW=START)
        from . import config, ids
        ids.secrets = _Secrets(seed)
        from .store import Store
        self.paths = config.resolve()
        self._root_config()
        self.store = Store(self.paths)
        self.store.settings.update(client="Harborline Physical Therapy",
                                   sender={"name": "Sam Rivera", "business": "Harborline PT", "title": "Owner"})
        self.people = _personas(self.rng, people)
        self.by_id = {}
        self._program()
        from .sender.inbox import MockInbox
        self.provider = _Clocked()
        self.provider.faults = self._faults()
        self.reader = MockInbox({})
        self.log = {"refusals": {}, "replies_prepared": 0, "approvals": 0, "owner_resolved": [], "waves": []}

    def _root_config(self):
        etc = self.paths.etc
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "owners.json").write_text(json.dumps({"owners": [OWNER]}))
        (etc / "sender.json").write_text(json.dumps({"name": "Sam Rivera", "title": "Owner", "business": "Harborline PT",
                                                     "physical_address": "100 Example Street, Charlotte, NC 28202", "pacing_seconds": 0}))
        (etc / "approvals.json").write_text(json.dumps({"approval_valid_hours": 24, "slack_channel": "C0SIM"}))
        self.paths.control.mkdir(parents=True, exist_ok=True)
        self.paths.key_file.write_bytes(bytes(random.Random(f"key:{self.seed}").getrandbits(8) for _ in range(32)).hex().encode())
        for sub in ("prepared", "suppress", "approved", "results", "inbound", "alerts"):
            (self.paths.spool / sub).mkdir(parents=True, exist_ok=True)

    def _program(self):
        from . import segments
        s = self.store
        sam = s.upsert("person", "Sam Rivera", identities={"email": "sam@harborline.example.com"}, internal=True, by="import", source="record")
        types = ["F6.A.2", "F6.B.1", "F7.A.1", "F5.A.1"]
        for p in self.people:
            org = s.upsert("partner", f"{p['name']} Studio", identities={"domain": f"p{p['i']:02d}.example.com"}, by="import", source="record")
            per = s.upsert("person", p["name"], identities={"phone": p["phone"], "email": p["email"], "crm": f"sim:{p['i']}"},
                           fields={"first_name": p["first"]}, by="import", source="record")
            s.link(per, "works_at", org)
            ps = s.partnership(client="Harborline Physical Therapy", partner_id=org, type_id=types[p["i"] % len(types)],
                               employee=EMP, voice_id=sam, contacts=[(per, "owner")])
            for ch in p["consent"]:
                s.set_consent(per, ch, "express" if ch == "sms" else "existing_relationship", "crm", by="import")
            rec = [{"slot": "code", "value": f"SIM{p['i']:02d}"}]
            if p["kind"] in ("past_producer", "active"):
                rec += [{"slot": "joined", "value": "2024-02-01"}, {"slot": "conversions", "value": "3"},
                        {"slot": "last_conversion", "value": "2026-09-20" if p["kind"] == "active" else "2025-11-15"}]
            else:
                rec += [{"slot": "joined", "value": "2025-03-01"}]
            s.remember(ps, facts=rec, source="record", source_ref=f"crm:{p['i']}", by="import")
            if p["kind"] == "registered":
                s.remember(org, facts=[{"slot": "partner_kind", "value": "refers clients directly"}], source="record",
                           source_ref=f"crm:{p['i']}:kind", by="import")
            p.update(person=per, partner=org, ps=ps)
            self.by_id[per] = p
        segments.compute(s)

    def _faults(self):
        """One unknown outcome and one 429 at seeded positions among the first sends."""
        faults = ["ok"] * 30
        a, b = self.rng.sample(range(2, 20), 2)
        faults[a], faults[b] = "timeout_after_accept", "429"
        return faults

    # ------------------------------------------------------------- clock
    def now(self):
        from . import clock
        return clock.now()

    def set(self, dt: datetime):
        os.environ["RELCORE_NOW"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Clocked(MockProvider):
    """The mock provider, also noting the fake time of each accepted send."""
    def send(self, row):
        from . import clock
        before = len(self.sent)
        try:
            return super().send(row)
        finally:
            if len(self.sent) > before:
                self.sent[-1]["sim_at"] = clock.iso()


# ------------------------------------------------------------------ the agent stand-in
def _reply_bodies(store, row, p, intent, channel, turn):
    """Candidate replies for one move, best first. The stand-in revises by trying the next one when checks refuse."""
    from . import graph
    first = p["first"]
    nq = graph.context(store, row["context_ref"])["next_question"]
    t = row.get("matched") or ""
    m = re.search(r"about (\d[\d,]*) (" + "|".join(UNITS) + ")", row.get("message") or "")
    said = f"{m.group(1)} {m.group(2)}" if m else None
    opener = ["Thanks, {f}.", "Got it, {f}.", "Appreciate it, {f}.", "Good to hear from you, {f}."]
    o = opener[turn % len(opener)].format(f=first)
    o2 = opener[(turn + 1) % len(opener)].format(f=first)
    sms = {
        "accept_with_time": [f"{o} {t} works, I will send a calendar hold shortly.", f"{o2} {t} it is, a calendar hold is on its way."],
        "accept": [f"{o} I will send the one page overview today. {nq or 'Anything you want it to cover?'}",
                   f"{o2} Overview coming today. Anything you want it to cover?"],
        "not_now": [f"{o} Totally fair. Should I check back in January?",  # asks after not_now: the checks must refuse it
                    f"{o} Totally fair, I will check back then and keep it short.", f"{o2} No rush at all, talk then."],
        "not_interested": [f"{o} Understood. Would a different offer be more useful?",  # refused: no ask after a no
                           f"{o} Understood, thanks for letting me know. Here if anything changes.",
                           f"{o2} No problem at all, thanks for the reply."],
        "has_opportunity": [f"{o} That is great. Text me a name and I will reach out today.",
                            f"{o2} Wonderful. Text me a name and I will take it from there."],
        "wants_help": [f"{o} Sending the starter kit with the flyer today.", f"{o2} The starter kit is on its way today."],
        "commission_question": [f"{o} Let me confirm the exact terms and get back to you today.",
                                f"{o2} I will check the current terms and reply today."],
        "question": [f"{o} Usually a short intro, then we share referrals both ways. I will send a one page outline.",
                     f"{o2} I will send a one page outline of how it usually works."],
        "general": ([f"{o} {said} is a real community.", f"{o} {said} is a real community, thanks for telling me."] if said else [])
                   + [f"{o} {nq}" if nq else f"{o} Glad it reached you.", f"{o2} Glad it reached you."],
    }[intent]
    if channel == "sms":
        return [("", b) for b in sms]
    pad = (" We work with a small group of local partners, and I try to keep every note short and useful for your "
           "team. Nothing here needs a quick decision, and you can reply whenever it suits you. I will keep the details "
           "brief and send only what you asked for, so it is easy to share with anyone on your side who should see it.")
    return [("quick note", b + pad) for b in sms]


def _agent_replies(w: "World") -> None:
    from . import graph, replies
    store = w.store
    rows = replies.pending(store)
    batch = []
    for r in rows:
        raw = store.con.execute("SELECT * FROM inbound WHERE id=?", (r["inbound_id"],)).fetchone()
        p = w.by_id.get(r["person"]["id"])
        if not p:
            continue
        turn = store.con.execute("SELECT COUNT(*) FROM interactions WHERE entity_id=? AND direction='out'", (p["person"],)).fetchone()[0]
        digest = graph.context(store, r["context_ref"])["context_digest"]
        chosen = None
        for subject, body in _reply_bodies(store, {**r, "matched": raw["matched"]}, p, r["intent"], r["channel"], turn):
            check = replies.check_reply(store, raw, body, subject, digest, r["intent"])
            if check["ok"]:
                chosen = {"inbound_id": r["inbound_id"], "body": body, "subject": subject, "context_digest": digest}
                break
            for e in check["errors"]:
                key = e.split(":")[0][:60]
                w.log["refusals"][key] = w.log["refusals"].get(key, 0) + 1
        if chosen:
            batch.append(chosen)
    if batch:
        out = replies.prepare(store, employee=EMP, replies=batch)
        w.log["replies_prepared"] += out["messages"]


def _owner_approves(w: "World") -> None:
    from .approvals.service import Service
    svc = Service(w.paths)
    svc.scan()
    for b in svc.pending():
        if b["state"] == "shown":
            svc.decide(b["action_id"], "approve", approver=OWNER, via="console")
            w.log["approvals"] += 1


def _owner_resolves_unknown(w: "World", worker) -> None:
    from .sender.console import run
    if not (worker.home / "HALT").exists():
        return
    for r in worker.con.execute("SELECT row_id, action_id, n FROM outbox WHERE state='unknown'").fetchall():
        accepted = any(s.get("action_id") == r["action_id"] and s.get("n") == r["n"] for s in w.provider.sent)
        out = run(worker, "sam", f"resolve {r['row_id']} {'sent' if accepted else 'not_sent'}")
        if "resolved" in out:
            w.log["owner_resolved"].append({"row_id": r["row_id"], "as": "sent" if accepted else "not_sent"})
    run(worker, "sam", "clear-halt")


def _personas_answer(w: "World") -> None:
    """Each persona answers our latest message after their delay, following their hidden script."""
    from . import clock
    now = clock.now()
    for s in w.provider.sent:
        p = w.by_id.get(s.get("person_id"))
        if not p or p["intent"] == "silent":
            continue
        cid = f"{s['channel']}:{s['address']}"
        conv = w.reader.data.setdefault(cid, {"channel": s["channel"], "address": s["address"], "messages": []})
        out_id = f"out-{s['action_id']}-{s['n']}"
        if not any(m["id"] == out_id for m in conv["messages"]):
            conv["messages"].append({"id": out_id, "direction": "out", "at": s["sim_at"], "text": s.get("final_body") or s.get("body")})
        said = [m for m in conv["messages"] if m["direction"] == "in"]
        due = clock.parse(s["sim_at"]) + timedelta(hours=p["delay_hours"])
        if now < due:
            continue
        if not said and s.get("first_touch"):
            text = p["phrase"].format(first="Kim" if p["intent"] == "wrong_number" else p["first"])
        elif len(said) == 1 and not s.get("first_touch") and p["reveals"] and not p.get("revealed"):
            text = (f"Sorry for the slow reply, I had knee {SENSITIVE} last week. " if p["sensitive"] else "") + \
                   f"We have about {p['size']} {p['unit']} by the way."
            p["revealed"] = True
        else:
            continue
        at = clock.iso(due) if due > clock.parse(s["sim_at"]) else s["sim_at"]
        mid = f"in-{p['i']}-{len(said) + 1}"
        conv["messages"].append({"id": mid, "direction": "in", "at": at, "text": text})
        p.setdefault("said", []).append({"id": mid, "at": at, "text": text, "channel": s["channel"],
                                         "intent": p["intent"] if not said else "general"})


def _conversions(w: "World") -> None:
    from . import segments
    from .importers import apply_conversions
    from . import clock
    day = clock.day(clock.now())
    rows = [{"code": f"SIM{p['i']:02d}", "conversions": 4, "last_conversion_at": day} for p in w.people if p["converts"] and p["kind"] != "active"]
    apply_conversions(w.store, rows)
    segments.compute(w.store)


# ------------------------------------------------------------------ run
def run(seed: int = 1, people: int = 40, days: int = 9, keep: Path | None = None) -> dict:
    _check_phrases()
    saved = {k: os.environ.get(k) for k in ("RELCORE_MODE", "RELCORE_ROOT", "RELCORE_NOW", "RELCORE_EMPLOYEE")}
    root = Path(tempfile.mkdtemp(prefix=f"relcore-sim-{seed}-"))
    from . import ids
    real_secrets = ids.secrets
    try:
        w = World(seed, people, root)
        from . import actions, ingest
        from .sender.inbox import Inbox
        from .sender.worker import Worker
        worker = Worker(w.paths, env={}, providers={"sms": w.provider, "email": w.provider})
        poller = Inbox(w.paths, env={}, readers=[w.reader])
        t0 = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        for h in range(days * 24):
            now = t0 + timedelta(hours=h)
            w.set(now)
            if h % 24 == 1 and h // 24 in (0, 2):  # two waves, 09:00 New York on day 0 and day 2
                out = actions.prepare_wave(w.store, employee=EMP, size=20)
                w.log["waves"].append({"day": h // 24, "action_id": out.get("action_id"), "messages": out["messages"],
                                       "selection": out.get("selection")})
            if h == (days - 2) * 24:
                _conversions(w)
            _owner_approves(w)
            worker.run_once()
            _owner_resolves_unknown(w, worker)
            _personas_answer(w)
            poller.poll()
            ingest.run(w.store)
            _agent_replies(w)
        result = check(w, worker)
        from . import scorecard
        result["scorecard"] = scorecard.write(w.store, days=30)
        result["log"] = w.log
        result["seed"], result["people"], result["days"] = seed, people, days
        result["example"] = _example(w, result["scorecard"]["note"])
        if keep:
            if keep.exists():
                shutil.rmtree(keep)
            shutil.copytree(root, keep)
        worker.con.close()
        poller.con.close() if hasattr(poller, "con") else None
        w.store.con.close()
        return result
    finally:
        ids.secrets = real_secrets
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------ invariants
def check(w: "World", worker) -> dict:
    from . import clock, intents, scorecard
    s, sent = w.store, w.provider.sent
    inv = {}

    def ok(name, cond, detail=None):
        inv[name] = {"ok": bool(cond), **({"detail": detail} if detail and not cond else {})}

    # outbox state vs what the provider actually accepted
    rows = {(r["action_id"], r["n"]): dict(r) for r in worker.con.execute("SELECT * FROM outbox")}
    keys = [(x["action_id"], x["n"]) for x in sent]
    ok("the provider never got the same message twice", len(keys) == len(set(keys)), keys)
    unknown = [r for r in rows.values() if r["state"] == "unknown"]
    ok("an unknown outcome happened, halted the sender and was resolved by the owner",
       unknown and len(w.log["owner_resolved"]) == len(unknown) and not (worker.home / "HALT").exists(),
       {"unknown": len(unknown), "resolved": w.log["owner_resolved"]})
    exp = {r["action_id"]: r["expires_at"] for r in worker.con.execute("SELECT action_id, expires_at FROM approved_actions")}
    stuck = [r for r in rows.values() if r["state"] == "sending" or (r["state"] == "queued" and exp.get(r["action_id"], "") <= clock.iso())]
    ok("nothing stuck sending or queued past its approval", not stuck, [(r["action_id"], r["n"], r["reason"]) for r in stuck])

    failed = [r for r in rows.values() if r["state"] == "failed"]
    ok("the 429 before accept was retried and sent, not dropped", w.provider.calls == len(sent) + 1 and not failed,
       {"calls": w.provider.calls, "accepted": len(sent), "failed": len(failed)})
    asked = sum(v for k, v in w.log["refusals"].items() if k in ("not_now", "not_interested"))
    told_no = sum(1 for p in w.people for x in p.get("said", []) if x["intent"] in ("not_now", "not_interested"))
    ok("every reply that asked after a not now or a no was refused, then revised", asked == told_no and told_no,
       {"refused": asked, "answers": told_no})

    firsts = [x for x in sent if x.get("first_touch")]
    per_person = {}
    for x in firsts:
        per_person.setdefault(x["person_id"], []).append(x)
    per_addr = {}
    for x in firsts:
        per_addr.setdefault(x["address"], []).append(x)
    ok("one first touch per person", all(len(v) == 1 for v in per_person.values()))
    ok("one first touch per address", all(len(v) == 1 for v in per_addr.values()))

    late = []
    for p in w.people:
        for said in p.get("said", []):
            if said["intent"] == "opt_out":
                late += [x for x in sent if x["person_id"] == p["person"] and x["sim_at"] > said["at"]]
            if said["intent"] == "wrong_number":
                addr = p["phone"] if said["channel"] == "sms" else p["email"]
                late += [x for x in sent if x["address"] in (addr, s.profile(p["person"])["identities"].get("phone")) and
                         x["channel"] == said["channel"] and x["sim_at"] > said["at"]]
    ok("nothing sent after an opt-out or to a wrong number", not late, [(x["person_id"], x["sim_at"]) for x in late])

    window = []
    for x in sent:
        if x["channel"] != "sms":
            continue
        p = w.by_id[x["person_id"]]
        local = clock.parse(x["sim_at"]).astimezone(ZoneInfo(p["tz"]))
        if not 9 <= local.hour < 20:
            window.append((p["name"], x["sim_at"], local.strftime("%H:%M")))
    ok("every SMS inside 09:00 to 20:00 in the number's own zone", not window, window)

    caps, answers = [], {}
    for x in sent:  # caps bind what we start; every earlier message, answers included, counts toward them
        if x.get("reply_to"):
            answers.setdefault(x["reply_to"], []).append(x)
            continue
        t = clock.parse(x["sim_at"])
        before = [clock.parse(y["sim_at"]) for y in sent if y["person_id"] == x["person_id"] and clock.parse(y["sim_at"]) < t]
        if any(t - b < timedelta(hours=24) for b in before):
            caps.append((w.by_id[x["person_id"]]["name"], x["sim_at"], "two within 24 hours"))
        if sum(t - b < timedelta(days=7) for b in before) >= 2:
            caps.append((w.by_id[x["person_id"]]["name"], x["sim_at"], "three within 7 days"))
    ok("caps held on everything we started (1 a day, 2 a week, across channels)", not caps, caps)
    ok("one answer per partner message", all(len(v) == 1 for v in answers.values()),
       [k for k, v in answers.items() if len(v) > 1])

    held = {r["entity_id"] for r in s.con.execute("SELECT entity_id FROM holdout")}
    ok("the holdout was never contacted", held and not [x for x in sent if x["partnership_id"] in held],
       {"held": len(held)})

    excluded = {p["person"] for p in w.people if p["kind"] == "active" or not p["consent"]}
    ok("active producers and people without consent were never contacted", not [x for x in sent if x["person_id"] in excluded])

    floor_bad = []
    for p in w.people:
        for said in p.get("said", []):
            row = s.con.execute("SELECT floor_intent FROM inbound WHERE entity_id=? AND last_msg_id=?", (p["person"], said["id"])).fetchone()
            if said["intent"] in intents.LOCKED or said is p["said"][0]:
                if not row or row["floor_intent"] != said["intent"]:
                    floor_bad.append((p["name"], said["text"], said["intent"], row["floor_intent"] if row else None))
    ok("the floor read every first answer as the persona meant it", not floor_bad, floor_bad)

    expect_engaged = {p["ps"] for p in w.people if any(intents.counts_as_engagement(x["intent"]) for x in p.get("said", []))}
    engaged = {r["partnership_id"] or r["entity_id"] for r in s.con.execute("SELECT entity_id, partnership_id FROM engagement")}
    names = {p["ps"]: p["name"] for p in w.people}
    ok("engagement equals the hidden qualifying replies", engaged == expect_engaged,
       {"missing": sorted(names.get(e, e) for e in expect_engaged - engaged), "extra": sorted(names.get(e, e) for e in engaged - expect_engaged)})

    leaks = []
    for f in w.paths.vault.rglob("*.md"):
        if SENSITIVE in f.read_text().lower():
            leaks.append(str(f.relative_to(w.paths.vault)))
    if any(SENSITIVE in line.lower() for line in s.con.iterdump()):
        leaks.append("rel.sqlite3")
    told = [p for p in w.people if p.get("revealed") and p["sensitive"]]
    ok("a health detail was told and never stored", told and not leaks, {"told": len(told), "found_in": leaks})

    sizes = []
    for p in w.people:
        if p.get("revealed") and s.con.execute("SELECT 1 FROM inbound WHERE entity_id=? AND last_msg_id=?",
                                                (p["person"], f"in-{p['i']}-2")).fetchone():
            got = (s.profile(p["partner"])["slots"].get("audience_size") or [{}])[0].get("value")
            from .normalize import count
            if count(got) != p["size"]:
                sizes.append((p["name"], p["size"], got))
    ok("the audience sizes they told us are on their partner cards", not sizes, sizes)

    reach = scorecard.reachable(s)
    expect = set()
    for p in w.people:
        said = {x["intent"] for x in p.get("said", [])}
        if said & {"opt_out", "identity_question", "complaint"}:
            continue
        chans = set(p["consent"]) - ({x["channel"] for x in p.get("said", []) if x["intent"] == "wrong_number"})
        if chans:
            expect.add(p["ps"])
    got = set(reach) if not isinstance(reach, dict) else set(reach)
    ok("scorecard denominator equals the reachable, consented partnerships", got == expect,
       {"missing": len(expect - got), "extra": len(got - expect)})

    return {"invariants": inv, "ok": all(v["ok"] for v in inv.values()),
            "counts": {"sent": len(sent), "first_touches": len(firsts), "held_out": len(held),
                       "outbox": {st: sum(r["state"] == st for r in rows.values()) for st in sorted({r["state"] for r in rows.values()})},
                       "inbound": s.con.execute("SELECT COUNT(*) FROM inbound").fetchone()[0], "engaged": len(engaged),
                       "hidden": {k: sum(p["intent"] == k for p in w.people) for k in WEIGHTS}}}


def _example(w: "World", scorecard_note: str) -> dict:
    """The cards of the partner with the fullest conversation (a told audience size and a dropped health detail when
    there is one), plus the scorecard: what an owner would open in Obsidian after the run."""
    def turns(p):
        return w.store.con.execute("SELECT COUNT(*) FROM interactions WHERE entity_id=?", (p["person"],)).fetchone()[0]
    p = max(w.people, key=lambda p: (bool(p.get("revealed")), p["sensitive"] and bool(p.get("revealed")), turns(p), -p["i"]))
    files = {}
    for eid in (p["person"], p["partner"], p["ps"]):
        rel = w.store.entity(eid)["note_path"]
        files[rel] = (w.paths.vault / rel).read_text()
    files[scorecard_note] = (w.paths.vault / scorecard_note).read_text()
    return {"persona": {k: p[k] for k in ("name", "intent", "size", "unit", "sensitive", "delay_hours")}, "files": files}


def write_example(results: list[dict], out: Path) -> list[Path]:
    """Writes simulation.md and the seed-1 example cards under out/. Returns every path written."""
    out.mkdir(parents=True, exist_ok=True)
    written = [out / "simulation.md", out / "README.md"]
    written[0].write_text(markdown(results))
    first = results[0]["example"]
    p = first["persona"]
    written[1].write_text(
        "# Worked example\n\n"
        "Frozen output of `python3 -m relcore sim` (seeds " + ", ".join(str(r["seed"]) for r in results) + "). CI reruns it and "
        "fails on any difference, so this is what the code does today, byte for byte. Everything here is fictional.\n\n"
        "- `simulation.md`: every invariant for each seed, with the counts and the scorecard.\n"
        f"- `vault/`: the cards of {p['name']} from seed {results[0]['seed']}, the partner with the fullest conversation, "
        "and the scorecard note, as the owner would open them in Obsidian.\n"
        "- `persona.json`: that partner's hidden truth, to compare with what the cards learned.\n\n"
        f"{p['name']} answered the first touch with a general reply, then told us their audience size"
        + (" next to a health detail. The cards keep the size, with its source, and nothing of the health detail."
           if p["sensitive"] else ".") + " When the stand-in tried to ask the same unanswered question again, the reply "
        "checks refused it and the next draft reflected what they said instead.\n\n"
        "The replies come from a templated stand-in for the model: this proves the rules, not the writing.\n\n"
        "Regenerate after an intended change:\n\n"
        "```bash\npython3 -m relcore sim --write-example charter/examples/sample-client/relationship/worked-example\n```\n")
    for rel, text in first["files"].items():
        path = out / "vault" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)
    (out / "persona.json").write_text(json.dumps(first["persona"], indent=1, sort_keys=True) + "\n")
    written.append(out / "persona.json")
    return written


def check_example(results: list[dict], out: Path) -> list[str]:
    """Differences between a fresh run and the frozen example (empty when they match byte for byte)."""
    tmp = Path(tempfile.mkdtemp(prefix="relcore-sim-example-"))
    try:
        fresh = {p.relative_to(tmp) for p in write_example(results, tmp)}
        frozen = {p.relative_to(out) for p in out.rglob("*") if p.is_file()}
        diffs = [f"only in the frozen example: {x}" for x in sorted(frozen - fresh)]
        diffs += [f"missing from the frozen example: {x}" for x in sorted(fresh - frozen)]
        diffs += [f"differs: {x}" for x in sorted(fresh & frozen) if (tmp / x).read_bytes() != (out / x).read_bytes()]
        return diffs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def markdown(results: list[dict]) -> str:
    lines = ["# Relationship layer simulation", "",
             "Synthetic partners with a hidden truth, run hour by hour through prepare, signed approval, the sender's checks, "
             "the inbox, ingest and replies, with an unknown outcome and a 429 injected. Replies come from a templated "
             "stand-in for the model, so this proves the rules, not the writing. Every check reads database state and the "
             "provider's own log.", ""]
    for r in results:
        c = r["counts"]
        lines += [f"## Seed {r['seed']}: {'PASS' if r['ok'] else 'FAIL'}", "",
                  f"{r['people']} partners over {r['days']} days. Sent {c['sent']} ({c['first_touches']} first touches), "
                  f"held out {c['held_out']}, inbound turns {c['inbound']}, engaged {c['engaged']}, replies prepared "
                  f"{r['log']['replies_prepared']}, owner approvals {r['log']['approvals']}.", "",
                  "| Check | Result |", "|---|---|"]
        lines += [f"| {k} | {'ok' if v['ok'] else 'FAIL ' + json.dumps(v.get('detail'), default=str)[:200]} |" for k, v in r["invariants"].items()]
        lines += ["", f"Outbox: {c['outbox']}. Hidden intents: " + ", ".join(f"{k} {v}" for k, v in c["hidden"].items() if v) + ".",
                  f"Drafts the checks refused before a revision passed: {r['log']['refusals'] or 'none'}."]
        sc = r["scorecard"]
        lines += [f"Scorecard: reachable {sc['reachable_consented_partnerships']['n']}, replies counted "
                  f"{sc['replies']['counted_as_replies']} of {sc['replies']['turns']}, engaged {sc['funnel']['engaged']}, "
                  f"conversions on record {sc['production']['conversions_on_record']}."]
        for wv in sc["waves"]:
            l = wv["lift"]
            lines.append(f"Wave {wv['prepared']}: sent {wv['sent']}, converted {l['contacted']['converted_pct']}% of "
                         f"{l['contacted']['n']} vs holdout {l['holdout']['converted_pct']}% of {l['holdout']['n']}"
                         + (f" ({l['caution']})" if l["caution"] else "") + ".")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="relcore sim")
    ap.add_argument("--seed", type=int, action="append")
    ap.add_argument("--people", type=int, default=40)
    ap.add_argument("--days", type=int, default=9)
    ap.add_argument("--out")
    ap.add_argument("--keep", help="copy the simulated root (vault, databases, spool) here")
    ap.add_argument("--write-example", help="freeze simulation.md and the seed's example cards in this folder")
    ap.add_argument("--check-example", help="fail if a fresh run differs from the frozen example in this folder")
    a = ap.parse_args(argv)
    results = [run(s, a.people, a.days, Path(a.keep) / f"seed-{s}" if a.keep else None) for s in (a.seed or [1, 2])]
    text = markdown(results)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    if a.write_example:
        for p in write_example(results, Path(a.write_example)):
            print(f"wrote {p}")
    if a.check_example:
        diffs = check_example(results, Path(a.check_example))
        for d in diffs:
            print(d)
        if diffs:
            return 1
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
