"""The one writer for relationship cards: people, partner organizations and revenue partnerships.

    store = Store(config.resolve())
    store.remember({"email": "dana@example.com"}, facts=[{"slot": "audience_size", "value": "about 12k"}],
                   source="reply", source_ref="msg_123", by="model")
    store.profile({"id": "pe_..."})

remember():
  1. resolves the reference (id, email, phone, CRM id, platform id, partnership key);
  2. routes each fact to the card its slot belongs to (person, partner or partnership);
  3. drops never_store categories and refuses not_from_model slots from the agent;
  4. dedupes on (slot, normalized value), applies each source_ref once per writer, and lets a single-value slot
     be replaced only by an equal or stronger source (owner > record > call > reply/plan > research);
  5. writes the index, then re-renders the affected cards, hubs and employee cards in the vault.

`by` (model, rule, import, owner) is set by the entrypoint, never by tool arguments.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import clock, config, ids, normalize, privacy, quoting, spool
from .db import connect, tx
from .db.rel import SCHEMA
from .lock import held

PRECEDENCE = {"owner": 5, "record": 4, "call": 3, "reply": 2, "plan": 2, "research": 1}
EDGE_TYPES = {
    "works_at": ("person", "partner"), "contact_for": ("person", "partnership"), "partner_in": ("partner", "partnership"),
    "introduced_by": ("person", "person"), "referred_by": ("*", "person"), "knows": ("person", "person"),
    "type_of": ("partnership", "type"), "owned_by_employee": ("partnership", "emp"), "voiced_by": ("partnership", "person"),
    "from_campaign": ("*", "hub"), "for_offer": ("partnership", "hub"), "attended_call": ("person", "call"),
    "member_of_hub": ("*", "hub"), "overlaps_audience_with": ("partner", "partner"),
}
EDGE_WORDS = {"works_at": "Works at", "contact_for": "Contact for", "partner_in": "Partner in", "type_of": "Partner type",
              "owned_by_employee": "Owned by employee", "voiced_by": "Named sender", "introduced_by": "Introduced by",
              "referred_by": "Referred by", "knows": "Knows", "attended_call": "On call", "for_offer": "Offer",
              "from_campaign": "From campaign", "overlaps_audience_with": "Audience overlaps with"}
HUB_KINDS = ("Tiers", "Niches", "PromoChannels", "Sources", "Offers", "Campaigns", "Regions", "Stages")
CONVERSATION_STAGES = ("new", "contacted", "replied", "engaged", "call_booked", "planned", "producing", "paused", "closed")
# Plain fields per card. Protected ones come only from importers or the owner (never the agent).
FIELDS = {
    "person": {"first_name": False, "last_name": False, "title": False, "timezone": True, "timezone_basis": True},
    "partner": {"org_kind": False, "city": False, "state": False, "country": False, "solo": False},
    "partnership": {"client": True, "type_id": True, "stage": False, "next_touch": False, "status": False,
                    "segment": True, "eligibility": True, "holdout": True, "arm": True, "terms_ref": True,
                    "attribution": True, "exclusions": True},
}
CONFIDENCE = {"research": "low", "reply": "high", "call": "high", "record": "high", "owner": "high", "plan": "medium"}


def node(kind: str, value: str) -> str:
    return f"{kind}:{value}"


class Store:
    def __init__(self, paths: config.Paths | None = None, *, render: bool = True):
        self.paths = paths or config.resolve()
        self.paths.home.mkdir(parents=True, exist_ok=True)
        self.con = connect(self.paths.rel_db, SCHEMA)
        self.schema = config.schema(self.paths)
        self.settings = config.settings(self.paths)
        self.render_enabled = render
        self._vault = None

    @property
    def vault(self):
        if self._vault is None:
            from .vault import Vault
            self._vault = Vault(self)
        return self._vault

    # ---------------------------------------------------------------- identity
    def resolve(self, ref) -> str | None:
        """Entity id for a reference, or None. ref: an id string, or a dict with one of id, email, phone, crm,
        platform, handle, domain, key (partnership key client|partner_id|type_id)."""
        if isinstance(ref, str):
            ref = {"id": ref}
        if ref.get("id"):
            row = self.con.execute("SELECT id FROM entities WHERE id=?", (ref["id"],)).fetchone()
            return row["id"] if row else None
        for typ in ("email", "phone", "crm", "platform", "handle", "domain", "key"):
            if ref.get(typ):
                value = self._norm_identity(typ, ref[typ])
                if value:
                    row = self.con.execute("SELECT entity_id FROM identities WHERE type=? AND value_norm=?",
                                           (typ, value)).fetchone()
                    if row:
                        return row["entity_id"]
        return None

    @staticmethod
    def _norm_identity(typ: str, value) -> str | None:
        value = str(value or "").strip()
        if typ == "email":
            return normalize.email(value)
        if typ == "phone":
            return normalize.phone(value)
        if typ == "domain":
            value = value.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
            return value or None
        return value or None

    def entity(self, entity_id: str) -> dict | None:
        row = self.con.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["fields"] = json.loads(out["fields"])
        return out

    def _new_id(self, kind: str, seed: str | None) -> str:
        for salt in range(50):
            eid = ids.new_id(kind, seed, salt)
            if not self.con.execute("SELECT 1 FROM entities WHERE id=?", (eid,)).fetchone():
                return eid
        raise RuntimeError("could not allocate an id")

    def upsert(self, kind: str, display: str | None = None, *, identities: dict | None = None, fields: dict | None = None,
               internal: bool | None = None, seed: str | None = None, by: str = "model", source: str = "reply",
               source_ref: str | None = None) -> str:
        """Create or update an entity found by any of its identities. Identities never move between entities:
        a conflicting identity is reported, not reassigned."""
        identities = {k: v for k, v in (identities or {}).items() if v}
        eid = None
        for typ, values in identities.items():
            for value in values if isinstance(values, (list, tuple)) else [values]:
                found = self.resolve({typ: value})
                if found:
                    eid = found
                    break
            if eid:
                break
        now = clock.iso()
        with tx(self.con):
            if eid is None:
                if not display:
                    raise ValueError(f"a new {kind} needs a display name")
                first = next((f"{t}:{self._norm_identity(t, v if not isinstance(v, (list, tuple)) else v[0])}"
                              for t, v in identities.items()), None)
                eid = self._new_id(kind, seed or (f"{kind}|{first}" if first else None))
                self.con.execute("INSERT INTO entities (id, kind, display, fields, internal, created_at, updated_at) "
                                 "VALUES (?,?,?,?,?,?,?)", (eid, kind, ids.safe_name(display, 120), "{}",
                                                            int(bool(internal)), now, now))
                self._timeline(eid, f"Card created from {source}", f"created:{eid}")
            else:
                ent = self.entity(eid)
                if ent["kind"] != kind:
                    raise ValueError(f"{eid} is a {ent['kind']}, not a {kind}")
                if display and by in ("import", "owner") and ids.safe_name(display, 120) != ent["display"]:
                    self.con.execute("UPDATE entities SET display=?, updated_at=? WHERE id=?",
                                     (ids.safe_name(display, 120), now, eid))
            for typ, values in identities.items():
                for value in values if isinstance(values, (list, tuple)) else [values]:
                    norm = self._norm_identity(typ, value)
                    if not norm:
                        continue
                    owner = self.con.execute("SELECT entity_id FROM identities WHERE type=? AND value_norm=?",
                                             (typ, norm)).fetchone()
                    if owner and owner["entity_id"] != eid:
                        self._audit("identity_conflict", eid, {"type": typ, "held_by": owner["entity_id"]})
                        continue
                    self.con.execute("INSERT OR IGNORE INTO identities VALUES (?,?,?,?,?)", (typ, norm, eid, source, now))
            if internal is not None and by in ("import", "owner"):
                self.con.execute("UPDATE entities SET internal=? WHERE id=?", (int(internal), eid))
            if fields:
                self._set_fields(eid, kind, fields, by)
            if kind == "person" and not self.entity(eid)["fields"].get("timezone"):
                phone = self.con.execute("SELECT value_norm FROM identities WHERE entity_id=? AND type='phone'",
                                         (eid,)).fetchone()
                tz, basis = normalize.tz_from_phone(phone["value_norm"] if phone else None)
                self._set_fields(eid, kind, {"timezone": tz, "timezone_basis": basis}, "import")
        return eid

    def _set_fields(self, eid: str, kind: str, fields: dict, by: str) -> list[str]:
        ent = self.entity(eid)
        current, refused = ent["fields"], []
        for key, value in fields.items():
            protected = FIELDS[kind].get(key)
            if protected is None:
                refused.append(f"{key}: unknown field")
                continue
            if protected and by not in privacy.TRUSTED_WRITERS:
                refused.append(f"{key}: set only by the system of record or the owner")
                continue
            if key == "stage" and value not in CONVERSATION_STAGES:
                refused.append(f"stage: {value} is not a conversation stage")
                continue
            if isinstance(value, str) and privacy.violations(value, self.schema["never_store"]):
                refused.append(f"{key}: never_store")
                continue
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        self.con.execute("UPDATE entities SET fields=?, updated_at=? WHERE id=?",
                         (json.dumps(current, sort_keys=True), clock.iso(), eid))
        return refused

    # ---------------------------------------------------------------- graph
    def link(self, src: str, typ: str, dst: str, *, props: dict | None = None, source: str = "record",
             source_ref: str | None = None, confidence: str = "high") -> None:
        if typ not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {typ}")
        if typ == "member_of_hub" or typ in ("from_campaign", "for_offer"):
            kind, value = dst.split(":", 1)[1].split("/", 1)
            self.con.execute("INSERT OR IGNORE INTO hubs VALUES (?,?)", (kind, value))
        with tx(self.con):
            existing = self.con.execute("SELECT id, until FROM edges WHERE src=? AND type=? AND dst=?",
                                        (src, typ, dst)).fetchone()
            if existing:
                self.con.execute("UPDATE edges SET until=NULL, props=?, confidence=? WHERE id=?",
                                 (json.dumps(props or {}, sort_keys=True), confidence, existing["id"]))
                if existing["until"] is None:
                    return
            else:
                self.con.execute("INSERT INTO edges (src, type, dst, props, source, source_ref, confidence, since) "
                                 "VALUES (?,?,?,?,?,?,?,?)", (src, typ, dst, json.dumps(props or {}, sort_keys=True),
                                                              source, source_ref, confidence, clock.iso()))
            if src.startswith(("pe_", "pt_", "ps_")):
                if dst.startswith("hub:"):
                    hk, hv = dst[4:].split("/", 1)
                    line = f"Tagged {hk}: {hv}"
                else:
                    line = f"{EDGE_WORDS.get(typ, typ.replace('_', ' '))} {self.label(dst)}"
                self._timeline(src, line, f"edge:{typ}:{dst}")

    def unlink(self, src: str, typ: str, dst: str) -> None:
        with tx(self.con):
            self.con.execute("UPDATE edges SET until=? WHERE src=? AND type=? AND dst=? AND until IS NULL",
                             (clock.iso(), src, typ, dst))

    def edges(self, entity_id: str, *, typ: str | None = None, direction: str = "both") -> list[dict]:
        out = []
        if direction in ("both", "out"):
            q = "SELECT * FROM edges WHERE src=? AND until IS NULL" + (" AND type=?" if typ else "")
            out += [dict(r, other=r["dst"], dir="out") for r in self.con.execute(q, (entity_id, typ) if typ else (entity_id,))]
        if direction in ("both", "in"):
            q = "SELECT * FROM edges WHERE dst=? AND until IS NULL" + (" AND type=?" if typ else "")
            out += [dict(r, other=r["src"], dir="in") for r in self.con.execute(q, (entity_id, typ) if typ else (entity_id,))]
        for e in out:
            e["props"] = json.loads(e["props"])
        return sorted(out, key=lambda e: (e["type"], e["other"]))

    def label(self, node_id: str) -> str:
        if node_id.startswith(("pe_", "pt_", "ps_")):
            ent = self.entity(node_id)
            return ent["display"] if ent else node_id
        kind, _, value = node_id.partition(":")
        return value.split("/", 1)[-1] if kind == "hub" else value

    def partnership(self, *, client: str, partner_id: str, type_id: str, employee: str | None = None,
                    voice_id: str | None = None, contacts: list[tuple[str, str]] = (), fields: dict | None = None,
                    by: str = "import", source: str = "record", source_ref: str | None = None) -> str:
        """Create or find the revenue partnership <client> x <partner> - <type>; link partner, type, owner employee,
        voice and contacts. The owning employee defaults to the type's family profile."""
        from . import taxonomy
        t = taxonomy.get(type_id)
        partner = self.entity(partner_id)
        key = f"{client}|{partner_id}|{type_id}"
        display = f"{client} x {partner['display']} - {type_id}"
        allowed = (fields or {}) if by in privacy.TRUSTED_WRITERS else \
            {k: v for k, v in (fields or {}).items() if not FIELDS["partnership"].get(k)}
        eid = self.upsert("partnership", display, identities={"key": key}, seed=f"partnership|{key}", by=by,
                          source=source, source_ref=source_ref, fields=allowed)
        with tx(self.con):  # structural fields come from the call itself, not from the writer
            self._set_fields(eid, "partnership", {"client": client, "type_id": type_id}, "import")
        self.link(partner_id, "partner_in", eid, source=source, source_ref=source_ref)
        self.link(eid, "type_of", node("type", type_id), props={"family": t["family"]}, source=source)
        self.link(eid, "owned_by_employee", node("emp", employee or t["profile"]), source=source)
        if voice_id:
            self.link(eid, "voiced_by", voice_id, source=source)
        for person_id, role in contacts:
            self.link(person_id, "contact_for", eid, props={"role": role} if role else {}, source=source)
        if not self.entity(eid)["fields"].get("stage"):
            self._set_fields(eid, "partnership", {"stage": "new"}, by)
        self._hub_link(eid, "Stages", self.entity(eid)["fields"].get("stage", "new"), source)
        return eid

    def _hub_link(self, eid: str, kind: str, value: str, source: str, source_ref: str | None = None) -> None:
        value = normalize.hub_value(value)
        if not value or kind not in HUB_KINDS:
            return
        same = self.con.execute("SELECT value FROM hubs WHERE kind=? AND lower(value)=lower(?)", (kind, value)).fetchone()
        value = same["value"] if same else value  # one hub per value whatever the case (filenames are case-insensitive)
        if kind == "Stages":  # one stage at a time
            for e in self.edges(eid, typ="member_of_hub", direction="out"):
                if e["other"].startswith("hub:Stages/") and e["other"] != f"hub:Stages/{value}":
                    self.unlink(eid, "member_of_hub", e["other"])
        self.link(eid, "member_of_hub", node("hub", f"{kind}/{value}"), source=source, source_ref=source_ref)

    # ---------------------------------------------------------------- routing
    def route(self, target: str, entity_kind: str) -> tuple[str | None, str]:
        """The card a slot for `entity_kind` lands on, starting from `target`. (id, reason-if-none)."""
        ent = self.entity(target)
        if ent["kind"] == entity_kind:
            return target, ""
        if ent["kind"] == "person" and entity_kind == "partner":
            orgs = [e["other"] for e in self.edges(target, typ="works_at", direction="out")]
            return (orgs[0], "") if len(orgs) == 1 else (None, f"person has {len(orgs)} organizations; name the partner")
        if ent["kind"] == "person" and entity_kind == "partnership":
            ps = [e["other"] for e in self.edges(target, typ="contact_for", direction="out")]
            return (ps[0], "") if len(ps) == 1 else (None, f"person is on {len(ps)} partnerships; name the partnership")
        if ent["kind"] == "partnership" and entity_kind == "partner":
            orgs = [e["other"] for e in self.edges(target, typ="partner_in", direction="in")]
            return (orgs[0], "") if orgs else (None, "partnership has no partner")
        if ent["kind"] == "partner" and entity_kind == "partnership":
            ps = [e["other"] for e in self.edges(target, typ="partner_in", direction="out")]
            return (ps[0], "") if len(ps) == 1 else (None, f"partner has {len(ps)} partnerships; name the partnership")
        if entity_kind == "person":
            people = [e["other"] for e in self.edges(target, typ="contact_for" if ent["kind"] == "partnership" else "works_at",
                                                      direction="in")]
            return (people[0], "") if len(people) == 1 else (None, f"{len(people)} people; name the person")
        return None, "no route"

    # ---------------------------------------------------------------- write
    def remember(self, ref, *, facts=(), interaction: dict | None = None, fields: dict | None = None,
                 hubs: dict | None = None, edges=(), loops=(), note: str | None = None, source: str = "reply",
                 source_ref: str | None = None, by: str = "model", recorder: str = "agent") -> dict:
        target = self.resolve(ref)
        if not target:
            raise LookupError(f"no card for {ref}; create it first (import or rel_entity_upsert)")
        report = {"written": [], "skipped": [], "refused": []}
        touched = {target}
        self._pending_refs = []
        with held(self.paths.home / ".write.lock"):
            with tx(self.con):
                kind = self.entity(target)["kind"]
                if fields:
                    for r in self._set_fields(target, kind, fields, by):
                        report["refused"].append(r)
                    if "stage" in fields and fields["stage"] in CONVERSATION_STAGES:
                        self._hub_link(target, "Stages", fields["stage"], source, source_ref)
                for hub_kind, values in (hubs or {}).items():
                    for value in values if isinstance(values, (list, tuple)) else [values]:
                        if privacy.violations(str(value), self.schema["never_store"]):
                            report["refused"].append(f"hub {hub_kind}: never_store")
                            continue
                        self._hub_link(target, hub_kind, value, source, source_ref)
                for fact in facts:
                    eid = self._remember_fact(target, fact, source, source_ref, by, recorder, report)
                    if eid:
                        touched.add(eid)
                if interaction:
                    touched |= self._interaction(target, interaction, source_ref)
                for loop in loops:
                    touched.add(self._loop(target, loop, source_ref))
                for e in edges:
                    self.link(e.get("src", target), e["type"], e["dst"], props=e.get("props"), source=source,
                              source_ref=source_ref, confidence=e.get("confidence", CONFIDENCE.get(source, "medium")))
                    touched |= {x for x in (e.get("src", target), e["dst"]) if x.startswith(("pe_", "pt_", "ps_"))}
                if note:
                    clean = privacy.redact(note, self.schema["never_store"])
                    if clean:
                        self._timeline(target, quoting.quote(clean, "Note", 300), f"note:{source_ref or hashlib.sha1(clean.encode()).hexdigest()[:10]}")
                for row in self._pending_refs:  # recorded after the batch, so several values of one slot all land
                    self.con.execute("INSERT OR IGNORE INTO applied_refs VALUES (?,?,?,?)", row)
                self._pending_refs = []
                for eid in touched:
                    self.con.execute("UPDATE entities SET updated_at=? WHERE id=?", (clock.iso(), eid))
            if self.render_enabled:
                self.vault.render_around(touched)
        out = self.profile(target)
        out["report"] = report
        return out

    def _remember_fact(self, target, fact, source, source_ref, by, recorder, report) -> str | None:
        slot, raw = fact.get("slot"), fact.get("value")
        spec = self.schema["slots"].get(slot)
        if spec is None:
            report["refused"].append(f"{slot}: unknown slot")
            return None
        if fact.get("entity"):
            eid = self.resolve(fact["entity"])
            if not eid or self.entity(eid)["kind"] != spec["entity"]:
                report["refused"].append(f"{slot}: {fact['entity']} is not a {spec['entity']}")
                return None
        else:
            eid, why = self.route(target, spec["entity"])
            if not eid:
                report["refused"].append(f"{slot}: {why}")
                return None
        ref = fact.get("source_ref") or source_ref
        if ref and self.con.execute("SELECT 1 FROM applied_refs WHERE entity_id=? AND source_ref=? AND by=?",
                                    (eid, f"{ref}#{slot}", by)).fetchone():
            report["skipped"].append(f"{slot}: {ref} already applied")
            return None
        try:
            privacy.check_fact(slot, raw, source, self.schema, by=by, volunteered=bool(fact.get("volunteered", True)))
        except privacy.Refused as err:
            self.con.execute("INSERT INTO refused (at, entity_id, slot, reason, source_ref) VALUES (?,?,?,?,?)",
                             (clock.iso(), eid, slot, str(err), ref))
            report["refused"].append(f"{slot}: {err}")
            return None
        value = normalize.apply(spec.get("normalize"), raw)
        if value in (None, ""):
            report["refused"].append(f"{slot}: could not read a value")
            return None
        value_s = str(value)
        key = normalize.text_key(value_s)
        conf = fact.get("confidence") or CONFIDENCE.get(source, "medium")
        if source == "research":
            conf = "low"
        now = clock.iso()
        active = [dict(r) for r in self.con.execute(
            "SELECT * FROM facts WHERE entity_id=? AND slot=? AND removed_at IS NULL", (eid, slot))]
        same = next((r for r in active if r["value_key"] == key), None)
        if same:
            if PRECEDENCE.get(source, 0) > PRECEDENCE.get(same["source"], 0):
                self.con.execute("UPDATE facts SET source=?, source_ref=?, by=?, confidence=?, recorded_at=? WHERE id=?",
                                 (source, ref, by, conf, now, same["id"]))
                report["written"].append(f"{slot}: confirmed by {source}")
            else:
                report["skipped"].append(f"{slot}: already known")
            self._applied(eid, ref, slot, by)
            return eid
        if not spec.get("multi") and active:
            old = max(active, key=lambda r: (PRECEDENCE.get(r["source"], 0), r["recorded_at"]))
            if PRECEDENCE.get(source, 0) < PRECEDENCE.get(old["source"], 0):
                report["skipped"].append(f"{slot}: {old['source']} value kept over {source}")
                self._applied(eid, ref, slot, by)
                return None
            self.con.execute("UPDATE facts SET removed_at=? WHERE entity_id=? AND slot=? AND removed_at IS NULL",
                             (now, eid, slot))
        self.con.execute(
            "INSERT INTO facts (entity_id, slot, value, value_key, source, source_ref, by, recorded_at, recorded_by, "
            "confidence, volunteered) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (entity_id, slot, value_key) DO UPDATE SET "
            "value=excluded.value, source=excluded.source, source_ref=excluded.source_ref, by=excluded.by, "
            "recorded_at=excluded.recorded_at, recorded_by=excluded.recorded_by, confidence=excluded.confidence, removed_at=NULL",
            (eid, slot, value_s, key, source, ref, by, now, recorder, conf, int(bool(fact.get("volunteered")))))
        if spec.get("hub"):
            self._hub_link(eid, spec["hub"], value_s, source, ref)
        self._applied(eid, ref, slot, by)
        shown = value_s if not spec.get("volunteered_only") else "(personal note)"
        self._timeline(eid, f"Learned {slot.replace('_', ' ')}: {shown} ({source})", f"fact:{slot}:{key}:{ref}")
        report["written"].append(f"{slot} -> {eid}")
        return eid

    def _applied(self, eid, ref, slot, by):
        if ref:
            pending = getattr(self, "_pending_refs", None)
            row = (eid, f"{ref}#{slot}", by, clock.iso())
            if pending is None:
                self.con.execute("INSERT OR IGNORE INTO applied_refs VALUES (?,?,?,?)", row)
            else:
                pending.append(row)

    def _interaction(self, target: str, it: dict, source_ref: str | None) -> set:
        person = target if self.entity(target)["kind"] == "person" else self.route(target, "person")[0] or target
        text = privacy.redact(quoting.strip_quoted_email(it.get("text", "")), self.schema["never_store"])
        who = it.get("who") or {"in": "Partner", "out": "We", "internal": "Note"}.get(it.get("direction"), "Partner")
        summary = quoting.quote(text, who, 300, it.get("verb", "wrote")) if text else it.get("summary", "")
        provider, msg_id = it.get("provider", "manual"), it.get("provider_msg_id") or source_ref
        cur = self.con.execute(
            "INSERT OR IGNORE INTO interactions (entity_id, partnership_id, kind, channel, direction, provider, "
            "provider_msg_id, at, summary, body_hash, template_version, action_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (person, it.get("partnership_id"), it.get("kind", "message"), it.get("channel"), it.get("direction", "in"),
             provider, msg_id, it.get("at") or clock.iso(), summary,
             hashlib.sha256(text.encode()).hexdigest()[:16] if text else None, it.get("template_version"), it.get("action_id")))
        if cur.rowcount:
            ch = it.get("channel") or it.get("kind", "message")
            line = it.get("timeline") or {"in": f"They replied by {ch}", "out": f"We sent {ch}", "internal": f"Internal note ({ch})"}.get(
                it.get("direction", "in"), f"Logged {ch}")
            self._timeline(person, line, f"int:{provider}:{msg_id}")
        touched = {person}
        if it.get("partnership_id"):
            touched.add(it["partnership_id"])
        return touched

    def _loop(self, target: str, loop: dict, source_ref: str | None) -> str:
        text = privacy.redact(loop["text"], self.schema["never_store"])
        eid = self.resolve(loop["entity"]) if loop.get("entity") else target
        self.con.execute("INSERT OR IGNORE INTO open_loops (entity_id, partnership_id, owner, text, due, source_ref, created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (eid, loop.get("partnership_id"), loop.get("owner", "us"), text,
                                                   loop.get("due"), source_ref, clock.iso()))
        self._timeline(eid, f"Open loop ({loop.get('owner', 'us')}): {text}", f"loop:{normalize.text_key(text)}:{source_ref}")
        return eid

    def close_loop(self, loop_id: int, status: str = "done") -> None:
        with tx(self.con):
            row = self.con.execute("SELECT entity_id, text FROM open_loops WHERE id=?", (loop_id,)).fetchone()
            self.con.execute("UPDATE open_loops SET status=?, closed_at=? WHERE id=?", (status, clock.iso(), loop_id))
            self._timeline(row["entity_id"], f"Loop {status}: {row['text']}", f"loopclose:{loop_id}")
        if self.render_enabled:
            self.vault.render_around({row["entity_id"]})

    # ---------------------------------------------------------------- restrictions (add only)
    def suppress(self, ref, channel: str = "*", reason: str = "opt_out", source: str = "reply") -> None:
        eid = self.resolve(ref)
        rows = [("entity", eid)] if eid else []
        if eid:
            rows += [(r["type"], r["value_norm"]) for r in self.con.execute(
                "SELECT type, value_norm FROM identities WHERE entity_id=? AND type IN ('email','phone')", (eid,))]
        elif isinstance(ref, dict):
            rows += [(t, self._norm_identity(t, ref[t])) for t in ("email", "phone") if ref.get(t)]
        with tx(self.con):
            for typ, value in rows:
                self.con.execute("INSERT OR IGNORE INTO suppression_local VALUES (?,?,?,?,?,?)",
                                 (typ, value, channel, reason, source, clock.iso()))
            if eid:
                self._timeline(eid, f"Do not contact ({channel}): {reason}", f"suppress:{channel}:{reason}")
        if self.paths.spool and rows:  # relsend keeps its own copy: it never reads rel.sqlite3
            items = [{"type": "entity" if typ == "entity" else "address", "value": value, "channel": channel, "reason": reason}
                     for typ, value in rows if value]
            name = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:16]
            spool.write(self.paths.spool / "suppress", f"sup-{name}.json",
                        {"kind": "suppress", "items": items, "source": source, "at": clock.iso()})
        if eid and self.render_enabled:
            self.vault.render_around({eid})

    def hold(self, ref, kind: str, reason: str, ref_id: str | None = None) -> None:
        eid = self.resolve(ref)
        with tx(self.con):
            self.con.execute("INSERT OR IGNORE INTO holds (entity_id, kind, reason, ref, created_at) VALUES (?,?,?,?,?)",
                             (eid, kind, reason, ref_id or "", clock.iso()))
            self._timeline(eid, f"Hold: {kind} ({reason})", f"hold:{kind}:{ref_id}")
        if self.render_enabled:
            self.vault.render_around({eid})

    def set_consent(self, ref, channel: str, basis: str, source: str, *, by: str) -> None:
        if by not in privacy.TRUSTED_WRITERS:
            raise privacy.Refused("consent comes only from the system of record or the owner")
        eid = self.resolve(ref)
        with tx(self.con):
            self.con.execute("INSERT OR REPLACE INTO consent VALUES (?,?,?,?,?)", (eid, channel, basis, source, clock.iso()))

    def do_not(self, entity_id: str) -> list[str]:
        """Restrictions that block drafting or sending, most serious first."""
        ent = self.entity(entity_id)
        flags = []
        if ent["internal"]:
            flags.append("internal: our own staff, never a recipient")
        idents = [("entity", entity_id)] + [(r["type"], r["value_norm"]) for r in self.con.execute(
            "SELECT type, value_norm FROM identities WHERE entity_id=?", (entity_id,))]
        for typ, value in idents:
            for r in self.con.execute("SELECT channel, reason FROM suppression_local WHERE type=? AND value_norm=?", (typ, value)):
                flags.append(f"do not contact ({r['channel']}): {r['reason']}")
        for r in self.con.execute("SELECT kind, reason FROM holds WHERE entity_id=? AND released_at IS NULL", (entity_id,)):
            flags.append(f"hold {r['kind']}: {r['reason']}")
        if ent["kind"] == "partnership":
            for e in self.edges(entity_id, typ="contact_for", direction="in"):
                flags += [f"{self.label(e['other'])}: {f}" for f in self.do_not(e["other"])]
        return sorted(set(flags), key=lambda f: (not f.startswith(("do not", "hold")), f))

    # ---------------------------------------------------------------- read
    def facts(self, entity_id: str, *, include_removed: bool = False) -> list[dict]:
        q = "SELECT * FROM facts WHERE entity_id=?" + ("" if include_removed else " AND removed_at IS NULL")
        return [dict(r) for r in self.con.execute(q + " ORDER BY slot, recorded_at, id", (entity_id,))]

    def profile(self, ref) -> dict:
        eid = self.resolve(ref)
        if not eid:
            raise LookupError(f"no card for {ref}")
        ent = self.entity(eid)
        kind = ent["kind"]
        slots: dict[str, list] = {}
        for f in self.facts(eid):
            slots.setdefault(f["slot"], []).append({"value": f["value"], "source": f["source"], "at": clock.day(f["recorded_at"]),
                                                    "confidence": f["confidence"], "ref": f["source_ref"]})
        key_slots = self.schema["key_slots"].get(kind, [])
        missing = [s for s in key_slots if s not in slots]
        nxt = next((self.schema["slots"][s].get("question") for s in missing if self.schema["slots"][s].get("question")), None)
        idents: dict[str, list] = {}
        for r in self.con.execute("SELECT type, value_norm FROM identities WHERE entity_id=? ORDER BY type, value_norm", (eid,)):
            idents.setdefault(r["type"], []).append(r["value_norm"])
        loops = [dict(r) for r in self.con.execute(
            "SELECT id, owner, text, due, partnership_id FROM open_loops WHERE (entity_id=? OR partnership_id=?) AND status='open' "
            "ORDER BY due IS NULL, due, id", (eid, eid))]
        recent = [dict(r) for r in self.con.execute(
            "SELECT at, channel, direction, kind, summary FROM interactions WHERE entity_id=? OR partnership_id=? "
            "ORDER BY at DESC, id DESC LIMIT ?", (eid, eid, self.settings["context"]["interactions"]))]
        links = {}
        for e in self.edges(eid):
            links.setdefault(e["type"] + ("" if e["dir"] == "out" else "<"), []).append(
                {"id": e["other"], "label": self.label(e["other"]), **({"props": e["props"]} if e["props"] else {}),
                 **({"confidence": e["confidence"]} if e["confidence"] != "high" else {})})
        consent = {r["channel"]: r["basis"] for r in self.con.execute("SELECT channel, basis FROM consent WHERE entity_id=?", (eid,))}
        return {
            "id": eid, "kind": kind, "display": ent["display"], "note": ent["note_path"], "fields": ent["fields"],
            "internal": bool(ent["internal"]), "identities": idents, "slots": slots,
            "completeness": round(100 * (len(key_slots) - len(missing)) / len(key_slots)) if key_slots else 100,
            "missing": missing, "next_question": nxt, "do_not": self.do_not(eid), "consent": consent,
            "open_loops": loops, "recent": recent, "links": links, "updated": ent["updated_at"],
        }

    def all_ids(self, kind: str | None = None) -> list[str]:
        q = "SELECT id FROM entities" + (" WHERE kind=?" if kind else "") + " ORDER BY id"
        return [r["id"] for r in self.con.execute(q, (kind,) if kind else ())]

    # ---------------------------------------------------------------- log
    def _timeline(self, eid: str, line: str, ref: str) -> None:
        self.con.execute("INSERT OR IGNORE INTO timeline (entity_id, at, line, ref) VALUES (?,?,?,?)",
                         (eid, clock.iso(), line, ref))

    def _audit(self, action: str, ref: str | None, detail: dict | None = None, actor: str = "relcore") -> None:
        self.con.execute("INSERT INTO audit (at, actor, action, ref, detail) VALUES (?,?,?,?,?)",
                         (clock.iso(), actor, action, ref, json.dumps(detail or {}, sort_keys=True)))

    def audit(self, action: str, ref: str | None = None, detail: dict | None = None, actor: str = "relcore") -> None:
        with tx(self.con):
            self._audit(action, ref, detail, actor)
