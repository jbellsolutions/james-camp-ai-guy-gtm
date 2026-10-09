"""trp side of the spool: what relapprove decided, what relsend sent, and what partners wrote back.

    python3 -m relcore ingest        (trp crontab, every 5 minutes; also run at the start of rel_inbox_pending)

results/   per-message outcomes: sent becomes an outbound interaction on the person and the partnership (stage moves
           to contacted), skipped/failed/expired release the reservation, unknown becomes an urgent owner task.
approved/  decisions are mirrored into Approvals/ (read-only for the agent); release-* files release a hold. Only
           relapprove can write this folder; in agent mode each file's owner is checked as well.
inbound/   each turn is matched by address, deduplicated by message id, run through the intent floor, recorded
           (quoted, never_store redacted), rule facts extracted, and the intent's effect applied: suppression,
           holds, tasks, open loops, next touch, the engagement register. Unmatched turns go to unmatched/.
"""
from __future__ import annotations

import json
import os
import re
from datetime import timedelta

from . import clock, extract, intents, privacy, quoting, spool
from .db import tx

STAGE_RANK = {s: i for i, s in enumerate(("new", "contacted", "replied", "engaged", "call_booked", "planned", "producing"))}


def _owner_ok(store, path) -> bool:
    """In agent mode the file must belong to the relapprove user (the folder is relapprove-writable only)."""
    if store.paths.mode != "agent":
        return True
    try:
        import pwd
        return os.stat(path).st_uid == pwd.getpwnam("relapprove").pw_uid
    except (KeyError, OSError):
        return False


def _seen(store, d: str, name: str) -> bool:
    return bool(store.con.execute("SELECT 1 FROM spool_seen WHERE dir=? AND name=?", (d, name)).fetchone())


def _mark(store, d: str, name: str, outcome: str) -> None:
    store.con.execute("INSERT OR IGNORE INTO spool_seen VALUES (?,?,?,?)", (d, name, clock.iso(), outcome))


def task(store, kind: str, eid: str | None, title: str, detail: str = "", *, urgent: bool = False, assignee: str = "human",
         ref: str | None = None) -> None:
    store.con.execute("INSERT OR IGNORE INTO tasks (kind, entity_id, title, detail, urgent, assignee, ref, created_at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (kind, eid, title, detail, int(urgent), assignee, ref or f"{kind}:{eid}:{title}",
                                                   clock.iso()))


def _advance(store, ps: str | None, stage: str) -> None:
    if not ps:
        return
    cur = store.entity(ps)["fields"].get("stage") or "new"
    if STAGE_RANK.get(stage, -1) > STAGE_RANK.get(cur, -1):
        store._set_fields(ps, "partnership", {"stage": stage}, "rule")
        store._hub_link(ps, "Stages", stage, "record")


def _release_if_done(store, aid: str) -> None:
    left = store.con.execute("SELECT COUNT(*) FROM action_messages WHERE action_id=? AND state IN ('prepared','approved')",
                             (aid,)).fetchone()[0]
    if left:
        return
    unknown = store.con.execute("SELECT entity_id, partnership_id FROM action_messages WHERE action_id=? AND state='unknown'",
                                (aid,)).fetchall()
    store.con.execute("UPDATE actions SET state=? WHERE action_id=? AND state IN ('approved','prepared','needs_owner')",
                      ("needs_owner" if unknown else "done", aid))
    keep = {x for r in unknown for x in (r["entity_id"], r["partnership_id"]) if x}  # until the owner resolves them
    for r in store.con.execute("SELECT entity_id FROM reservations WHERE action_id=?", (aid,)).fetchall():
        if r["entity_id"] not in keep:
            store.con.execute("DELETE FROM reservations WHERE action_id=? AND entity_id=?", (aid, r["entity_id"]))


# ---------------------------------------------------------------- decisions (relapprove)
def decisions(store) -> dict:
    out = {"decided": 0, "released": 0, "refused": 0}
    for path in spool.entries(store.paths.spool / "approved"):
        if _seen(store, "approved", path.name):
            continue
        if not _owner_ok(store, path):
            with tx(store.con):
                _mark(store, "approved", path.name, "refused: not written by relapprove")
                store._audit("spool_refused", path.name, {"dir": "approved"})
            out["refused"] += 1
            continue
        doc = spool.read(path)
        a = doc.get("approval") or {}
        touched = set()
        with tx(store.con):
            if doc.get("release"):
                r = doc["release"]
                store.con.execute("UPDATE holds SET released_at=?, released_by=? WHERE entity_id=? AND kind=? AND released_at IS NULL",
                                  (a.get("decided_at") or clock.iso(), doc.get("approver_name") or a.get("approver"), r["entity_id"], r["kind"]))
                store.con.execute("UPDATE tasks SET status='done', closed_at=? WHERE entity_id=? AND kind=? AND status='open'",
                                  (clock.iso(), r["entity_id"], {"identity": "reply_personally", "complaint": "grievance"}.get(r["kind"], r["kind"])))
                store._timeline(r["entity_id"], f"Hold released by {doc.get('approver_name') or 'the owner'}: {r['kind']}",
                                f"release:{a.get('approval_id')}")
                touched.add(r["entity_id"])
                _mark(store, "approved", path.name, "released")
                out["released"] += 1
            else:
                aid = a.get("action_id")
                row = store.con.execute("SELECT * FROM actions WHERE action_id=?", (aid,)).fetchone()
                if not row:
                    _mark(store, "approved", path.name, "unknown action")
                    continue
                state = "approved" if a.get("decision") == "approved" else "rejected"
                store.con.execute("UPDATE actions SET state=?, decided_at=? WHERE action_id=?", (state, a.get("decided_at"), aid))
                kept = {m["n"]: m for m in (doc.get("bundle") or {}).get("messages", [])}
                for m in store.con.execute("SELECT n, partnership_id, entity_id FROM action_messages WHERE action_id=?", (aid,)).fetchall():
                    if state == "rejected":
                        new = "rejected"
                    elif m["n"] in kept:
                        new = "approved"
                        if kept[m["n"]].get("edited_by_owner"):
                            store.con.execute("UPDATE action_messages SET body=? WHERE action_id=? AND n=?", (kept[m["n"]]["body"], aid, m["n"]))
                    else:
                        new = "excluded"
                    store.con.execute("UPDATE action_messages SET state=? WHERE action_id=? AND n=?", (new, aid, m["n"]))
                    if new != "approved":
                        store.con.execute("DELETE FROM reservations WHERE action_id=? AND entity_id IN (?,?)", (aid, m["partnership_id"], m["entity_id"]))
                        if new == "excluded":
                            store.con.execute("UPDATE inbound SET status='pending', action_id=NULL WHERE action_id=? AND entity_id=?", (aid, m["entity_id"]))
                    if m["partnership_id"]:
                        store._timeline(m["partnership_id"], f"{aid} message {m['n']} {new} by {doc.get('approver_name') or 'the owner'}",
                                        f"decision:{aid}:{m['n']}")
                        touched.add(m["partnership_id"])
                if state == "rejected":
                    store.con.execute("UPDATE inbound SET status='pending', action_id=NULL WHERE action_id=?", (aid,))
                    store.con.execute("DELETE FROM reservations WHERE action_id=?", (aid,))
                _mark(store, "approved", path.name, state)
                _mirror(store, doc, state)
                out["decided"] += 1
        if store.render_enabled and touched:
            store.vault.render_around(touched)
    return out


def _mirror(store, doc: dict, state: str) -> None:
    """Approvals/<date> <action>.md: a read-only mirror of the signed decision (the signature itself stays with relsend)."""
    a, bundle = doc["approval"], doc.get("bundle") or {}
    lines = ["---", "type: approval", f"action: {a['action_id']}", f"decision: {state}", f"approver: {doc.get('approver_name', '')}",
             f"decided_at: {a['decided_at']}", f"expires_at: {a['expires_at']}", f"payload_hash: {a['payload_hash']}",
             "tags:", "  - trp/approval", "---", f"# {state.title()}: {a['action_id']}", "",
             f"Signed by relapprove for {doc.get('approver_name', 'the owner')}. Mirror only: changing this note changes nothing.", "",
             f"- messages approved: {len(bundle.get('messages', []))}",
             f"- excluded: {', '.join(map(str, a.get('exclusions') or [])) or 'none'}",
             f"- edited by the owner: {', '.join(sorted(a.get('edits') or {})) or 'none'}"]
    store.vault._write(f"Approvals/{clock.day(a['decided_at'])} {a['action_id']}.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------- results (relsend)
def _dir(store, folder, name):
    return folder or (store.paths.spool / name if store.paths.spool else None)


def results(store, folder=None) -> dict:
    """relsend's results, or (drafts-only installs) the human's own send records from relcore.manual."""
    out = {"sent": 0, "other": 0, "unknown": 0}
    for path in spool.entries(_dir(store, folder, "results")):
        if _seen(store, "results", path.name):
            continue
        doc = spool.read(path)
        aid, n, state = doc["action_id"], doc["n"], doc["state"]
        msg = store.con.execute("SELECT * FROM action_messages WHERE action_id=? AND n=?", (aid, n)).fetchone()
        touched = set()
        with tx(store.con):
            _mark(store, "results", path.name, state)
            if not msg:
                continue
            store.con.execute("UPDATE action_messages SET state=? WHERE action_id=? AND n=?", (state, aid, n))
            person, ps = msg["entity_id"], msg["partnership_id"]
            if state == "sent":
                touched |= store._interaction(person, {"direction": "out", "channel": msg["channel"], "provider": "relsend",
                                                       "provider_msg_id": doc.get("provider_msg_id") or f"{aid}:{n}",
                                                       "at": doc["at"], "text": doc.get("final_body") or msg["body"],
                                                       "partnership_id": ps, "action_id": aid, "kind": "message",
                                                       "template_version": msg["template"]}, f"{aid}:{n}")
                _advance(store, ps, "contacted")
                if msg["reply_to"]:
                    store.con.execute("UPDATE inbound SET status='replied' WHERE last_msg_id=? AND entity_id=?", (msg["reply_to"], person))
                out["sent"] += 1
            elif state == "unknown":
                task(store, "send_unknown", person, f"Check whether {aid} message {n} went out",
                     "relsend could not tell if the provider accepted it and has halted. Check the provider, then "
                     "resolve it from the relsend console (resolve <row_id> sent|not_sent).", urgent=True, ref=f"unknown:{aid}:{n}")
                out["unknown"] += 1
            else:
                if msg["reply_to"]:
                    newer = store.con.execute("SELECT 1 FROM inbound WHERE entity_id=? AND at > (SELECT at FROM inbound WHERE last_msg_id=? "
                                              "LIMIT 1)", (person, msg["reply_to"])).fetchone()
                    store.con.execute("UPDATE inbound SET status=?, action_id=NULL WHERE last_msg_id=? AND entity_id=?",
                                      ("superseded" if newer else "pending", msg["reply_to"], person))
                if ps:
                    store._timeline(ps, f"{aid} message {n} {state}: {doc.get('reason') or ''}".strip(), f"result:{aid}:{n}")
                    touched.add(ps)
                out["other"] += 1
            if state != "unknown":  # an unknown row keeps its reservation until the owner resolves it
                store.con.execute("DELETE FROM reservations WHERE action_id=? AND entity_id IN (?,?)", (aid, person, ps))
            _release_if_done(store, aid)
        if store.render_enabled and touched:
            store.vault.render_around(touched)
    return out


# ---------------------------------------------------------------- inbound (relsend inbox)
def _match(store, channel: str, address: str) -> str | None:
    typ = "email" if channel == "email" else "phone"
    row = store.con.execute("SELECT entity_id FROM identities WHERE type=? AND value_norm=?",
                            (typ, store._norm_identity(typ, address))).fetchone()
    return row["entity_id"] if row else None


def _partnership_for(store, person: str) -> str | None:
    row = store.con.execute("SELECT partnership_id FROM interactions WHERE entity_id=? AND partnership_id IS NOT NULL "
                            "ORDER BY at DESC, id DESC LIMIT 1", (person,)).fetchone()
    if row:
        return row["partnership_id"]
    links = store.edges(person, typ="contact_for", direction="out")
    return links[0]["other"] if links else None


def _next_touch(text: str) -> str:
    t = text.lower()
    days = 45
    if re.search(r"next year|after the new year", t):
        days = 180
    elif re.search(r"next quarter|q[1-4]|few months|couple of months", t):
        days = 90
    elif re.search(r"next month|after the holidays|after the summer|after the season", t):
        days = 30
    elif re.search(r"few weeks|couple of weeks", t):
        days = 21
    return clock.day(clock.now() + timedelta(days=days))


def _effects(store, intent: str, floor: dict, person: str, ps: str | None, doc: dict, row_ref: str) -> tuple[str, str | None]:
    """Apply the intent's effect. Returns (inbound status, note)."""
    name = store.label(person)
    quoted = quoting.quote(privacy.redact(doc["text"], store.schema["never_store"]), name, 300)
    if intent == "opt_out":
        store.suppress(person, "*", "opt_out", source="reply")
        if ps:
            store._set_fields(ps, "partnership", {"status": "opted out"}, "rule")
        return "no_reply", "opted out: do not contact on any channel"
    if intent == "help":
        return "no_reply", "HELP: the provider's registered HELP response answers it; not counted as a reply"
    if intent == "wrong_number":
        store.suppress(person, doc["channel"], "wrong_number", source="reply")
        task(store, "fix_contact", person, f"Find the right {doc['channel']} contact for {name}", quoted, ref=f"wrong:{row_ref}")
        return "no_reply", "wrong number: marked bad"
    voice = next((e["other"] for e in store.edges(ps, typ="voiced_by", direction="out")), None) if ps else None
    if intent == "identity_question":
        store.hold(person, "identity", "asked whether they are talking to a person", ref_id=row_ref)
        task(store, "reply_personally", person, f"Reply personally to {name}", f"{quoted}\nThey asked who they are talking to. "
             "Reply yourself; drafts stay blocked until you release the hold.", urgent=True,
             assignee=store.label(voice) if voice else "owner", ref=f"identity:{row_ref}")
        return "no_reply", "identity question: the named sender replies personally"
    if intent == "complaint":
        store.hold(person, "complaint", "complaint or payment dispute", ref_id=row_ref)
        task(store, "grievance", person, f"Grievance from {name}", quoted, urgent=True, assignee="owner", ref=f"grievance:{row_ref}")
        return "no_reply", "complaint: on the grievance list, drafting stopped"
    if intent == "has_opportunity":
        task(store, "opportunity", person, f"Same day: {name} has an opportunity", quoted, urgent=True, ref=f"opp:{row_ref}")
        _advance(store, ps, "engaged")
    elif intent == "accept_with_time":
        when = floor.get("matched") or "the time they gave"
        store._loop(ps or person, {"owner": "us", "text": f"Confirm {when} with {name} and send the calendar hold",
                                   "due": clock.day(clock.now()), "partnership_id": ps}, row_ref)
        task(store, "calendar_hold", person, f"Calendar hold: {name}, {when}", quoted, ref=f"cal:{row_ref}")
        _advance(store, ps, "engaged")
    elif intent == "accept":
        _advance(store, ps, "engaged")
    elif intent == "not_now":
        if ps:
            store._set_fields(ps, "partnership", {"next_touch": _next_touch(doc["text"])}, "rule")
    elif intent == "not_interested":
        if ps:
            store._set_fields(ps, "partnership", {"status": "sequence stopped: not interested", "next_touch": None}, "rule")
    elif intent == "commission_question":
        task(store, "question", person, f"Commission question from {name}", f"{quoted}\nAnswer only from the terms on file.",
             assignee="owner", ref=f"q:{row_ref}")
    elif intent == "question":
        task(store, "question", person, f"Question from {name}", quoted, ref=f"q:{row_ref}")
    elif intent == "wants_help":
        task(store, "starter_kit", person, f"Send {name} the starter kit", quoted, ref=f"kit:{row_ref}")
    if intent in ("question", "commission_question", "general", "accept", "accept_with_time", "not_now",
                  "not_interested", "has_opportunity", "wants_help"):
        _advance(store, ps, "replied")
    return "pending", None


def inbound(store, folder=None) -> dict:
    """relsend's inbox turns, or (drafts-only installs) the replies the human pasted through relcore.manual."""
    out = {"turns": 0, "matched": 0, "unmatched": 0, "duplicates": 0}
    for path in spool.entries(_dir(store, folder, "inbound")):
        if _seen(store, "inbound", path.name):
            continue
        doc = spool.read(path)
        out["turns"] += 1
        provider, ids = doc["provider"], doc["msg_ids"]
        if all(store.con.execute("SELECT 1 FROM processed_inbound WHERE provider=? AND provider_msg_id=?", (provider, i)).fetchone()
               for i in ids):
            with tx(store.con):
                _mark(store, "inbound", path.name, "duplicate")
            out["duplicates"] += 1
            continue
        person = _match(store, doc["channel"], doc["address"]) or (doc.get("person_id") if doc.get("person_id") and store.entity(doc["person_id"]) else None)
        if person and store.entity(person)["internal"]:  # our own staff writing to the line is not a partner reply
            with tx(store.con):
                for i in ids:
                    store.con.execute("INSERT OR IGNORE INTO processed_inbound VALUES (?,?,?,?)", (provider, i, person, clock.iso()))
                _mark(store, "inbound", path.name, "internal")
            continue
        floor = intents.classify(doc["text"], doc["channel"])
        if floor["intent"] != (doc.get("floor") or {}).get("intent"):
            floor = {**floor, "note": f"relsend floor said {(doc.get('floor') or {}).get('intent')}"}
        if (doc.get("floor") or {}).get("intent") == "opt_out":  # never weaker than what relsend already applied
            floor["intent"] = "opt_out"
        intent = floor["intent"]
        redacted = privacy.redact(doc["text"], store.schema["never_store"])
        if not person:
            target = store.paths.home / "unmatched"
            target.mkdir(parents=True, exist_ok=True)
            (target / path.name).write_text(json.dumps({**doc, "text": redacted}, indent=1, ensure_ascii=False))
            with tx(store.con):
                store.con.execute("INSERT OR IGNORE INTO inbound (provider, last_msg_id, msg_ids, channel, address, at, floor_intent, intent, "
                                  "matched, summary, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (provider, doc["last_msg_id"], json.dumps(ids), doc["channel"], doc["address"], doc["at"], intent,
                                   intent, floor["matched"], quoting.quote(redacted, "Unknown sender", 300), "unmatched", clock.iso()))
                task(store, "unmatched", None, f"Who is {doc['address']}?",
                     f"{quoting.quote(redacted, 'Unknown sender', 300)}\nAdd them to a card (or import), then re-run ingest.",
                     ref=f"unmatched:{provider}:{doc['last_msg_id']}")
                for i in ids:
                    store.con.execute("INSERT OR IGNORE INTO processed_inbound VALUES (?,?,?,?)", (provider, i, None, clock.iso()))
                _mark(store, "inbound", path.name, "unmatched")
            if intent in ("opt_out", "wrong_number"):
                key = "email" if doc["channel"] == "email" else "phone"
                store.suppress({key: doc["address"]}, "*" if intent == "opt_out" else doc["channel"], intent, source="reply")
            out["unmatched"] += 1
            continue
        ps = _partnership_for(store, person)
        ref = f"{provider}:{doc['last_msg_id']}"
        facts = extract.rule_facts(redacted) if intent not in ("opt_out", "wrong_number", "help") else []
        store.remember(person, facts=facts, interaction={"direction": "in", "channel": doc["channel"], "provider": provider,
                                                        "provider_msg_id": doc["last_msg_id"], "at": doc["at"], "text": doc["text"],
                                                        "partnership_id": ps, "kind": "message"},
                       source="reply", source_ref=doc["last_msg_id"], by="rule", recorder="ingest")  # = the interaction's msg id
        touched = {person} | ({ps} if ps else set())
        with tx(store.con):
            status, note = _effects(store, intent, floor, person, ps, doc, ref)
            if status == "pending" and _blocked(store, person, doc["channel"]):
                status, note = "no_reply", "a do-not restriction or hold applies on this channel"
            store.con.execute("UPDATE inbound SET status='superseded' WHERE entity_id=? AND status='pending'", (person,))
            store.con.execute("INSERT OR IGNORE INTO inbound (provider, last_msg_id, msg_ids, entity_id, partnership_id, channel, address, at, "
                              "floor_intent, intent, matched, summary, status, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (provider, doc["last_msg_id"], json.dumps(ids), person, ps, doc["channel"], doc["address"], doc["at"],
                               intent, intent, floor["matched"], quoting.quote(redacted, store.label(person), 300), status,
                               note or floor.get("note"), clock.iso()))
            if intents.counts_as_engagement(intent) and _after_program_message(store, person, doc["at"]):
                tier = (store.profile(ps)["slots"].get("tier") or [{}])[0].get("value") if ps else None
                store.con.execute("INSERT OR IGNORE INTO engagement (entity_id, partnership_id, msg_ref, at, channel, tier_at) "
                                  "VALUES (?,?,?,?,?,?)", (ps or person, ps, ref, doc["at"], doc["channel"], tier))
            for i in ids:
                store.con.execute("INSERT OR IGNORE INTO processed_inbound VALUES (?,?,?,?)", (provider, i, person, clock.iso()))
            _mark(store, "inbound", path.name, intent)
        if doc.get("attachments"):
            store.remember(person, note=f"They sent {len(doc['attachments'])} attachment(s): "
                           + ", ".join(a.get("name", "file") for a in doc["attachments"])[:200] + " (not opened)",
                           source="reply", source_ref=f"{ref}:att", by="rule", recorder="ingest")
        if store.render_enabled:
            store.vault.render_around(touched)
        out["matched"] += 1
    return out


def _blocked(store, person: str, channel: str) -> bool:
    idents = [("entity", person)] + [(r["type"], r["value_norm"]) for r in store.con.execute(
        "SELECT type, value_norm FROM identities WHERE entity_id=?", (person,))]
    for typ, value in idents:
        if store.con.execute("SELECT 1 FROM suppression_local WHERE type=? AND value_norm=? AND channel IN ('*', ?)",
                             (typ, value, channel)).fetchone():
            return True
    return bool(store.con.execute("SELECT 1 FROM holds WHERE entity_id=? AND released_at IS NULL", (person,)).fetchone())


def _after_program_message(store, person: str, at: str) -> bool:
    return bool(store.con.execute("SELECT 1 FROM interactions WHERE entity_id=? AND direction='out' AND action_id IS NOT NULL AND at <= ?",
                                  (person, at)).fetchone())


def alerts(store) -> dict:
    out = {"alerts": 0}
    for path in spool.entries(store.paths.spool / "alerts"):
        if _seen(store, "alerts", path.name):
            continue
        try:
            doc = spool.read(path)
        except (ValueError, OSError):
            continue
        with tx(store.con):
            task(store, "sender_alert", None, f"Sender alert: {doc.get('kind', 'alert')}", str(doc.get("reason", ""))[:500]
                 + "\nCheck the provider, then use the relsend console (status, unknown, resolve, clear-halt).",
                 urgent=True, assignee="owner", ref=f"alert:{path.name}")
            _mark(store, "alerts", path.name, doc.get("kind", "alert"))
        out["alerts"] += 1
    return out


def run(store) -> dict:
    """Every entry point (cron and rel_inbox_pending) takes the same lock, so two ingests never interleave."""
    from .lock import held
    with held(store.paths.home / ".ingest.lock"):
        return _run(store)


def _run(store) -> dict:
    if not store.paths.spool:
        from . import calls
        return {"note": "plugin mode has no spool", "calls": calls.run_drop(store)}
    from . import calls
    out = {"decisions": decisions(store), "results": results(store), "inbound": inbound(store), "alerts": alerts(store),
           "calls": calls.run_drop(store)}
    if os.environ.get("RELCORE_CALLS_GHL") == "1":
        out["calls_ghl"] = calls.run_ghl(store, dict(os.environ))
    if store.render_enabled:
        for emp in {r["employee"] for r in store.con.execute("SELECT DISTINCT employee FROM actions WHERE employee IS NOT NULL")}:
            store.vault.render_employee(emp)
    return out
