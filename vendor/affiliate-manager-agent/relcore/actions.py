"""Prepared actions: the only way anything the agent writes can head outside. Nothing here sends.

prepare_wave():   select (not excluded, reserved, held out or already contacted), hold out a stratified slice,
                  split into at most two arms, draft, lint, reserve, freeze the bundle with its payload hash,
                  write spool/prepared/<action>.json and Reviews/<date> <action>.md
prepare_single(): one agent-written message (draft_submit with prepare=true), same checks
withdraw():       release reservations; after approval, a withdrawal notice in spool/suppress tells relsend to stop

Plugin mode has no approvals service or sender: prepared messages land in the outbox for copy and paste, and
rel_sent_record (relcore.manual) records each one the human sent.
"""
from __future__ import annotations

import json
import random
import re

from . import canonical, clock, copy, drafting, graph, ids, spool
from .db import tx

ACTION_ID = re.compile(r"^ac_[0-9a-f]{10}$")


def stopped(store) -> bool:
    from .mcp_server import stopped as _stopped
    return _stopped(store.paths)


def _contacted_before(store, person_id: str) -> bool:
    if store.con.execute("SELECT 1 FROM interactions WHERE entity_id=? AND direction='out' LIMIT 1", (person_id,)).fetchone():
        return True
    return bool(store.con.execute(
        "SELECT 1 FROM action_messages m JOIN actions a USING (action_id) WHERE m.entity_id=? AND m.first_touch_flag=1 AND "
        "((m.state IN ('prepared','approved','sent','unknown') AND a.state NOT IN ('rejected','withdrawn','expired')) "
        # drafts-only: the human may have sent it and not said so yet, so it counts until it is recorded or withdrawn
        "OR (m.state='outbox' AND a.state NOT IN ('rejected','withdrawn'))) LIMIT 1",
        (person_id,)).fetchone())


def _release_expired(store) -> None:
    now = clock.iso()
    with tx(store.con):
        store.con.execute("DELETE FROM reservations WHERE expires_at < ?", (now,))
        store.con.execute("UPDATE actions SET state='expired' WHERE state='prepared' AND expires_at < ?", (now,))


def _primary_contact(store, ps_id: str) -> str | None:
    for link in store.profile(ps_id)["links"].get("contact_for<", []):
        if not store.entity(link["id"])["internal"] and not store.do_not(link["id"]):
            return link["id"]
    return None


def select(store, *, segments, employee: str | None, program: str | None, channels: list[str]) -> tuple[list, dict]:
    from . import registers
    picked, skipped = [], {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    eligible = set(registers.eligible(store, program)) if program else None
    if program and not eligible:
        raise ValueError(f"freeze eligibility for {program} before its first send (python3 -m relcore registers freeze {program})")
    reserved = {r["entity_id"] for r in store.con.execute("SELECT entity_id FROM reservations")}
    for ps in store.all_ids("partnership"):
        ent = store.entity(ps)
        f = ent["fields"]
        if employee and employee != "default":
            owner = next((e["other"][4:] for e in store.edges(ps, typ="owned_by_employee", direction="out")), None)
            if owner != employee:
                continue
        if f.get("segment") not in segments:
            continue
        if f.get("exclusions"):
            for e in f["exclusions"]:
                skip(f"excluded: {e}")
            continue
        if f.get("holdout"):
            skip("holdout")
            continue
        if eligible is not None and ps not in eligible:
            skip("not in the frozen eligibility register")
            continue
        if store.do_not(ps):
            skip("do-not restriction")
            continue
        person = _primary_contact(store, ps)
        if not person:
            skip("no contactable person")
            continue
        if ps in reserved or person in reserved:
            skip("reserved by another pending action")
            continue
        if _contacted_before(store, person):
            skip("already contacted (first touch done)")
            continue
        channel, why = drafting.choose_channel(store, person, channels)
        if not channel:
            skip(why)
            continue
        address = drafting.address_for(store, person, channel)
        if any(c["person_id"] == person or c["address"] == address for c in picked):
            skip("same person or address already in this wave (one message each)")
            continue
        picked.append({"partnership_id": ps, "person_id": person, "channel": channel, "segment": f["segment"], "address": address})
    return picked, skipped


def _holdout(store, picked: list, action_id: str) -> tuple[list, list]:
    pct = store.settings["wave"]["holdout_pct"]
    rng = random.Random(action_id)
    keep, held = [], []
    by_seg = {}
    for c in picked:
        by_seg.setdefault(c["segment"], []).append(c)
    for seg, items in sorted(by_seg.items()):
        items = sorted(items, key=lambda c: c["partnership_id"])
        rng.shuffle(items)
        n = round(len(items) * pct / 100)
        held += items[:n]
        keep += items[n:]
    return keep, held


def _arms(store, items: list, action_id: str) -> None:
    arms = store.settings.get("first_touch_arms", ["one_word_ask"])[: store.settings["wave"]["arms_max"]]
    rng = random.Random(action_id + ":arms")
    by_seg = {}
    for c in items:
        by_seg.setdefault(c["segment"], []).append(c)
    for seg, group in sorted(by_seg.items()):
        group.sort(key=lambda c: c["partnership_id"])
        rng.shuffle(group)
        for i, c in enumerate(group):
            c["arm"] = arms[i % len(arms)]


def _voice(store, ps_id: str) -> dict | None:
    v = next((e["other"] for e in store.edges(ps_id, typ="voiced_by", direction="out")), None)
    return {"id": v, "name": store.entity(v)["display"]} if v else None


def _write(store, bundle: dict, selection: dict, anomalies: list) -> dict:
    bundle["payload_hash"] = canonical.payload_hash(bundle)  # informational; every reader recomputes it
    bundle["selection"], bundle["anomalies"] = selection, anomalies
    aid = bundle["action_id"]
    with tx(store.con):
        for m in bundle["messages"]:  # belt and braces: no person or partnership in two pending actions
            for eid in (m["person_id"], m["partnership_id"]):
                held_by = store.con.execute("SELECT action_id FROM reservations WHERE entity_id=? AND expires_at >= ?",
                                            (eid, clock.iso())).fetchone() if eid else None
                if held_by and held_by["action_id"] != aid:
                    raise ValueError(f"{eid} is already in pending action {held_by['action_id']}")
        store.con.execute("INSERT INTO actions (action_id, kind, employee, state, payload_hash, prepared_at, expires_at, detail) "
                          "VALUES (?,?,?,?,?,?,?,?)", (aid, bundle["kind"], bundle["employee"],
                                                       "prepared" if store.paths.spool else "outbox", bundle["payload_hash"],
                                                       bundle["prepared_at"], bundle["expires_at"],
                                                       json.dumps({"selection": selection, "anomalies": len(anomalies)})))
        for m in bundle["messages"]:
            store.con.execute(
                "INSERT INTO action_messages (action_id, n, entity_id, partnership_id, channel, address, subject, body, body_hash, "
                "hook, template, arm, reply_to, context_digest, state, first_touch_flag) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, m["n"], m["person_id"], m["partnership_id"], m["channel"], m["address"], m["subject"], m["body"],
                 canonical.payload_hash({"action_id": aid, "kind": "msg", "expires_at": "", "messages": [m]})[:16],
                 m.get("hook"), m.get("template"), m.get("arm"), m.get("reply_to"), m.get("context_digest"), "prepared",
                 int(m["first_touch"])))
            for eid in (m["person_id"], m["partnership_id"]):
                if eid:
                    store.con.execute("INSERT OR REPLACE INTO reservations VALUES (?,?,?)", (eid, aid, bundle["expires_at"]))
            if m["partnership_id"]:
                store._timeline(m["partnership_id"], f"Prepared {m['channel']} {m['n']} in {aid} (waiting for approval)", f"prep:{aid}:{m['n']}")
        store._audit("action_prepared", aid, {"messages": len(bundle["messages"]), "kind": bundle["kind"]},
                     actor=f"agent:{bundle['employee']}")
    if store.paths.spool:
        spool.write(store.paths.spool / "prepared", f"{aid}.json", bundle)
    else:
        _outbox(store, bundle)
    review = write_review(store, bundle)
    with tx(store.con):
        store.con.execute("UPDATE actions SET review_path=? WHERE action_id=?", (review, aid))
    store.vault.render_around({m["partnership_id"] for m in bundle["messages"] if m["partnership_id"]})
    if bundle["employee"]:
        store.vault.render_employee(bundle["employee"])
    return {"action_id": aid, "messages": len(bundle["messages"]), "review": review, "selection": selection,
            "anomalies": anomalies, "state": "prepared" if store.paths.spool else "outbox (plugin mode: copy and paste)"}


def _new_bundle(store, kind: str, employee: str, voice: dict | None) -> dict:
    aid = ids.new_id("action")
    hours = store.settings["wave"]["expires_hours"]
    return {"format": "relcore-bundle/v1", "action_id": aid, "kind": kind, "employee": employee, "voice": voice,
            "prepared_at": clock.iso(), "expires_at": clock.plus(hours=hours), "messages": []}


def _message(store, n, c, draft, digest) -> dict:
    consent = store.profile(c["person_id"])["consent"].get(c["channel"])
    return {"n": n, "channel": c["channel"], "address": drafting.address_for(store, c["person_id"], c["channel"]),
            "subject": draft.get("subject") or "", "body": draft["body"], "person_id": c["person_id"],
            "partnership_id": c.get("partnership_id"), "first_touch": not _contacted_before(store, c["person_id"]),
            "consent_basis": consent, "reply_to": c.get("reply_to"), "hook": draft.get("hook"), "template": draft.get("template"),
            "arm": c.get("arm"), "context_digest": digest, "recipient": store.entity(c["person_id"])["display"],
            "segment": c.get("segment")}


def prepare_wave(store, **kw) -> dict:
    """One preparer at a time across processes, so two waves can never pick the same person."""
    from .lock import held
    with held(store.paths.home / ".prepare.lock"):
        return _prepare_wave(store, **kw)


def _prepare_wave(store, *, employee: str, size: int | None = None, segments=None, program: str | None = None,
                  channels: list[str] | None = None, drafts: list[dict] | None = None) -> dict:
    if stopped(store):
        raise PermissionError("external writes are stopped (kill switch): nothing can be prepared")
    _release_expired(store)
    w = store.settings["wave"]
    size = min(size or w["default_size"], w["max_size"])
    segments = tuple(segments or ("past_producer", "registered_never_produced", "thin_record"))
    channels = channels or store.settings.get("prepare_channels", ["email", "sms"])
    picked, skipped = select(store, segments=segments, employee=employee, program=program, channels=channels)
    voices = {}
    for c in picked:
        v = _voice(store, c["partnership_id"])
        voices.setdefault(v["id"] if v else None, []).append(c)
    if not picked:
        return {"action_id": None, "messages": 0, "selection": {"picked": 0, "skipped": skipped}}
    voice_id = max(voices, key=lambda k: (k is not None, len(voices[k])))
    for k, items in voices.items():
        if k != voice_id:
            skipped["different named sender (prepare separately)"] = skipped.get("different named sender (prepare separately)", 0) + len(items)
    picked = voices[voice_id]
    bundle = _new_bundle(store, "wave", employee, {"id": voice_id, "name": store.entity(voice_id)["display"]} if voice_id else None)
    aid = bundle["action_id"]
    keep, held = _holdout(store, picked, aid)
    with tx(store.con):
        for c in held:
            store.con.execute("INSERT OR IGNORE INTO holdout VALUES (?,?,?,?)", (c["partnership_id"], aid, c["segment"], clock.iso()))
            store._set_fields(c["partnership_id"], "partnership", {"holdout": aid}, "import")
            store._timeline(c["partnership_id"], f"Held out of {aid}: never contacted until the program review", f"holdout:{aid}")
    keep = keep[:size]
    _arms(store, keep, aid)
    supplied = {(d.get("partnership_id"), d.get("person_id")): d for d in drafts or []}
    sender = drafting.preview_sender(store)
    anomalies, n = [], 0
    for c in keep:
        d = supplied.get((c["partnership_id"], c["person_id"]))
        digest = graph.context(store, c["partnership_id"])["context_digest"]
        if d:
            draft = {"subject": d.get("subject", ""), "body": d["body"], "hook": "agent", "template": "agent-written"}
            if d.get("context_digest") != digest:
                anomalies.append(f"{store.label(c['person_id'])}: agent draft used stale context, left out")
                continue
        else:
            draft = drafting.first_touch(store, c["partnership_id"], c["person_id"], c["channel"], c["arm"], sender)
        check = drafting.check_draft(store, ps_id=c["partnership_id"], person_id=c["person_id"], channel=c["channel"],
                                     subject=draft["subject"], body=draft["body"], digest=digest, first_touch=True, sender=sender)
        if not check["ok"]:
            anomalies.append(f"{store.label(c['person_id'])}: left out, {'; '.join(check['errors'])}")
            continue
        if draft.get("note"):
            anomalies.append(f"{store.label(c['person_id'])}: {draft['note']}")
        if check.get("encoding") == "UCS-2":
            anomalies.append(f"{store.label(c['person_id'])}: UCS-2 sms ({check['segments']} segments)")
        n += 1
        bundle["messages"].append(_message(store, n, c, draft, digest))
    selection = {"rule": f"segments {', '.join(segments)}; owner {employee or 'any employee'}; program {program or 'none'}; channels {', '.join(channels)}",
                 "picked": len(bundle["messages"]), "held_out": len(held), "skipped": dict(sorted(skipped.items()))}
    if not bundle["messages"]:
        return {"action_id": None, "messages": 0, "selection": selection, "anomalies": anomalies}
    return _write(store, bundle, selection, anomalies)


def prepare_single(store, **kw) -> dict:
    from .lock import held
    with held(store.paths.home / ".prepare.lock"):
        return _prepare_single(store, **kw)


def _prepare_single(store, *, employee: str, ps_id: str | None, person_id: str, channel: str, subject: str, body: str,
                    digest: str, reply_to: str | None = None, kind: str = "single", profile: str | None = None) -> dict:
    if stopped(store):
        raise PermissionError("external writes are stopped (kill switch): nothing can be prepared")
    _release_expired(store)
    if store.con.execute("SELECT 1 FROM reservations WHERE entity_id=?", (person_id,)).fetchone():
        raise ValueError("this person is already in a pending action")
    if channel not in store.settings.get("prepare_channels", ["email", "sms"]):
        raise ValueError(f"{channel} is draft-only; copy it from the draft instead")
    sender = drafting.preview_sender(store)
    first = not _contacted_before(store, person_id)
    check = drafting.check_draft(store, ps_id=ps_id, person_id=person_id, channel=channel, subject=subject, body=body,
                                 digest=digest, first_touch=first, sender=sender, profile=profile)
    if not check["ok"]:
        return {"action_id": None, "lint": check}
    consent = store.profile(person_id)["consent"].get(channel)
    if consent not in store.settings["consent_required"].get(channel, []):
        return {"action_id": None, "lint": {**check, "ok": False, "errors": [f"no consent basis on file for {channel}"]}}
    voice = _voice(store, ps_id) if ps_id else None
    bundle = _new_bundle(store, kind, employee, voice)
    c = {"partnership_id": ps_id, "person_id": person_id, "channel": channel, "reply_to": reply_to}
    bundle["messages"].append(_message(store, 1, c, {"subject": subject, "body": body, "hook": "agent", "template": "agent-written"}, digest))
    if profile and profile != "standard":
        bundle["messages"][0]["lint_profile"] = profile
    return _write(store, bundle, {"rule": "single message", "picked": 1, "held_out": 0, "skipped": {}}, [])


def withdraw(store, action_id: str, reason: str) -> dict:
    if not ACTION_ID.match(action_id or ""):
        raise ValueError("bad action id")
    row = store.con.execute("SELECT state FROM actions WHERE action_id=?", (action_id,)).fetchone()
    if not row:
        raise LookupError(f"no action {action_id}")
    with tx(store.con):
        store.con.execute("UPDATE actions SET state='withdrawn' WHERE action_id=?", (action_id,))
        store.con.execute("DELETE FROM reservations WHERE action_id=?", (action_id,))
        store._audit("action_withdrawn", action_id, {"reason": reason})
    if store.paths.spool:  # relapprove skips it; relsend stops any remaining messages
        spool.write(store.paths.spool / "suppress", f"withdraw-{action_id}.json",
                    {"kind": "withdraw", "action_id": action_id, "reason": reason, "at": clock.iso()})
    return {"action_id": action_id, "state": "withdrawn", "was": row["state"]}


def write_review(store, bundle: dict) -> str:
    """Reviews/<date> <action>.md: for reading in Obsidian. The approval card is built by relapprove from the bundle."""
    sel, msgs = bundle["selection"], bundle["messages"]
    lines = ["---", "type: review", f"action: {bundle['action_id']}", f"kind: {bundle['kind']}", f"employee: {bundle['employee'] or 'orchestrator'}",
             f"expires: {bundle['expires_at']}", "tags:", "  - trp/review", "---", f"# Review {bundle['action_id']}", "",
             f"Prepared by {bundle['employee'] or 'the orchestrator'} for {bundle['voice']['name'] if bundle.get('voice') else 'the owner'} to approve. "
             "Approve, approve except, edit or reject in the approvals channel. Nothing is sent until then.", "",
             "## Anomalies", *([f"- {a}" for a in bundle["anomalies"]] or ["- none"]), "",
             "## Selection", f"- rule: {sel['rule']}", f"- picked: {sel['picked']}", f"- held out: {sel['held_out']}"]
    lines += [f"- skipped, {k}: {v}" for k, v in sel.get("skipped", {}).items()]
    groups = {}
    for m in msgs:
        groups.setdefault((m.get("template"), m.get("hook")), []).append(m)
    lines += ["", "## Messages"]
    for (template, hook), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        lines += ["", f"### {template} · hook {hook} · {len(items)}"]
        for m in items:
            tags = [m["channel"], m["segment"], m.get("arm") and f"arm {m['arm']}"]
            lines += ["", f"**{m['n']}. {m['recipient']}** · " + " · ".join(t for t in tags if t)]
            if m["subject"]:
                lines.append(f"Subject: {m['subject']}")
            lines += ["", *[f"> {l}" if l else ">" for l in m["body"].splitlines()]]
    rel = f"Reviews/{clock.day(bundle['prepared_at'])} {bundle['action_id']}.md"
    store.vault._write(rel, "\n".join(lines) + "\n")
    return rel


def _outbox(store, bundle: dict) -> None:
    out = store.paths.home.parent / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# {bundle['action_id']} ({bundle['kind']})", "", "No sender on this install. Copy each message, send it yourself, "
             f"then record it with rel_sent_record (action_id {bundle['action_id']}, n) so the card shows it went out.", ""]
    for m in bundle["messages"]:
        lines += [f"## {m['n']}. {m['recipient']} · {m['channel']} · {m['address']}", *(["Subject: " + m["subject"]] if m["subject"] else []),
                  "", m["body"], ""]
    (out / f"{bundle['action_id']}.md").write_text("\n".join(lines))


# ---------------------------------------------------------------- MCP tools
def _t_lint(srv, channel, body, subject="", first_touch=False):
    return copy.lint(channel, body, subject=subject, first_touch=first_touch, sender=drafting.preview_sender(srv.store),
                     settings=srv.store.settings)


def _t_draft_submit(srv, ref, channel, body, context_digest, subject="", person=None, prepare=False, reply_to=None, plan=False):
    s = srv.store
    target = s.resolve(ref)
    if not target:
        raise LookupError(f"no card for {ref}")
    kind = s.entity(target)["kind"]
    ps = target if kind == "partnership" else (s.route(target, "partnership")[0] if kind == "person" else None)
    person_id = s.resolve(person) if person else (target if kind == "person" else s.route(target, "person")[0])
    if not person_id:
        raise ValueError("name the person this message is for")
    first = not _contacted_before(s, person_id)
    profile = None
    if plan:
        from . import plan as plans
        if not plans.is_saved_plan(s, ps, body):
            raise ValueError("plan=true is only for the exact partner email rel_plan_save returned for this partnership")
        profile = "plan"
    check = drafting.check_draft(s, ps_id=ps, person_id=person_id, channel=channel, subject=subject, body=body,
                                 digest=context_digest, first_touch=first, sender=drafting.preview_sender(s), profile=profile)
    with tx(s.con):
        cur = s.con.execute("INSERT INTO drafts (entity_id, partnership_id, channel, subject, body, context_digest, lint, employee, "
                            "created_at, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (person_id, ps, channel, subject, body, context_digest, json.dumps(check), srv.employee, clock.iso(),
                             "draft" if check["ok"] else "rejected"))
    out = {"draft_id": cur.lastrowid, "lint": check}
    if prepare and check["ok"]:
        out["prepared"] = prepare_single(s, employee=srv.employee, ps_id=ps, person_id=person_id, channel=channel,
                                         subject=subject, body=body, digest=context_digest, reply_to=reply_to,
                                         kind="plan" if plan else "single", profile=profile)
    return out


def _t_wave_prepare(srv, size=None, segments=None, program=None, channels=None, drafts=None):
    return prepare_wave(srv.store, employee=srv.employee, size=size, segments=segments, program=program,
                        channels=channels, drafts=drafts)


def _t_action_withdraw(srv, action_id, reason):
    return withdraw(srv.store, action_id, reason)


_CH = {"enum": ["email", "sms", "dm", "linkedin"]}
MCP_TOOLS = [
    {"name": "rel_lint", "read": True, "handler": _t_lint,
     "description": "Check a message against the house copy rules (word counts, subject, one question, no call ask on a first "
                    "touch, no links in a first touch, no dashes, no AI mention, no earnings claims, sms segments with the opt-out line).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["channel", "body"],
                     "properties": {"channel": _CH, "body": {"type": "string"}, "subject": {"type": "string"},
                                    "first_touch": {"type": "boolean"}}}},
    {"name": "rel_draft_submit", "read": False, "handler": _t_draft_submit,
     "description": "Submit a draft written from rel_context (pass its context_digest). It is checked (digest, restrictions, "
                    "channel preference, re-asking, privacy, copy rules) and saved. With prepare=true an email or sms becomes a "
                    "prepared action waiting for the owner's signed approval; LinkedIn and DMs stay drafts.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["ref", "channel", "body", "context_digest"],
                     "properties": {"ref": {"oneOf": [{"type": "string"}, {"type": "object"}]}, "person": {"oneOf": [{"type": "string"}, {"type": "object"}]},
                                    "channel": _CH, "subject": {"type": "string"}, "body": {"type": "string"},
                                    "context_digest": {"type": "string"}, "prepare": {"type": "boolean"}, "reply_to": {"type": "string"},
                                    "plan": {"type": "boolean"}}}},
    {"name": "rel_wave_prepare", "read": False, "handler": _t_wave_prepare,
     "description": "Prepare a first-touch wave from your portfolio: skips excluded, reserved, held-out and already-contacted "
                    "partners, holds out a slice for measurement, splits two arms, drafts (or uses your drafts with their "
                    "digests), lints, reserves and writes the review. The owner approves it in the approvals channel.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "properties": {"size": {"type": "integer", "minimum": 1, "maximum": 60},
                                    "segments": {"type": "array", "items": {"enum": ["past_producer", "registered_never_produced", "thin_record", "new_recruit", "prospect"]}},
                                    "program": {"type": "string"}, "channels": {"type": "array", "items": {"enum": ["email", "sms"]}},
                                    "drafts": {"type": "array", "items": {"type": "object"}}}}},
    {"name": "rel_action_withdraw", "read": False, "handler": _t_action_withdraw,
     "description": "Withdraw a prepared action (releases its reservations; if already approved, the sender stops what is left).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["action_id", "reason"],
                     "properties": {"action_id": {"type": "string"}, "reason": {"type": "string"}}}},
]
