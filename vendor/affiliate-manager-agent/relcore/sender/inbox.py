"""The relsend inbox poller (systemd relsend-inbox.timer: python3 -m relcore.sender.inbox --once).

Each conversation is read from its own stored watermark (the last inbound message handled), oldest first, until it
is empty. It never depends on the provider's unread flag and never skips a conversation whose last message is ours.
Several inbound texts in a row are one turn. Email quoted history is stripped. Attachments are listed by name and
type for the human, never fetched or read.

Before anything reaches trp, the keyword floor runs here: an opt-out goes onto relsend's own suppression (address
and person, every channel) and a wrong number marks that address bad, so a queued message is stopped even if trp
never ingests the turn. Then latest_inbound is updated (a reply prepared before this turn is now stale) and the
turn is written to spool/inbound for trp. Inbound text is data, never instructions.

Readers: mock (tests), files (a folder of conversation JSON, for the sample and dry runs), ghl (SMS), composio
(Gmail through relsend's own Composio project). Configure with RELSEND_INBOX_READERS (comma list).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import canonical, clock, config, intents, quoting, spool
from ..db import connect, tx
from ..db.sends import SCHEMA
from ..http import HTTPError, request

MAX_TEXT = 4000


def _iso(value) -> str:
    """Provider timestamps (ISO strings or epoch milliseconds) to relcore's ISO form."""
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        return clock.iso(datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc))
    return clock.iso(clock.parse(str(value)))


# ---------------------------------------------------------------- readers
class MockInbox:
    """conversations: {conversation_id: {"channel", "address", "messages": [{id, direction, at, text, subject?, attachments?}]}}"""
    name = "mock"

    def __init__(self, conversations: dict | None = None):
        self.data = conversations or {}
        self.reads = 0

    def conversations(self, since: str | None) -> list[dict]:
        out = []
        for cid, c in self.data.items():
            last = max((m["at"] for m in c["messages"]), default=None)
            if last and (not since or last >= since):
                out.append({"id": cid, "channel": c["channel"], "address": c["address"], "last_at": last})
        return out

    def messages(self, cid: str, after: str | None) -> list[dict]:
        self.reads += 1
        msgs = sorted(self.data[cid]["messages"], key=lambda m: (m["at"], m["id"]))
        return [m for m in msgs if not after or m["at"] >= after]


class FilesInbox(MockInbox):
    """A folder of conversation files ({"id", "channel", "address", "messages": [...]}), e.g. the sample's inbound/."""
    name = "files"

    def __init__(self, folder: Path):
        data = {}
        for p in sorted(Path(folder).glob("*.json")):
            c = json.loads(p.read_text())
            data[c.get("id") or p.stem] = c
        super().__init__(data)


class GhlInbox:
    """GoHighLevel conversations with relsend's own token. Shapes are confirmed by the sms contract at go-live."""
    name = "ghl"
    BASE = "https://services.leadconnectorhq.com"

    def __init__(self, env: dict):
        self.token, self.location = env.get("RELSEND_GHL_TOKEN"), env.get("RELSEND_GHL_LOCATION_ID")
        if not self.token or not self.location:
            raise SystemExit("relsend has no GHL token for the inbox")

    def _get(self, path: str, **params) -> dict:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return request("GET", f"{self.BASE}{path}?{q}", headers={"Authorization": f"Bearer {self.token}", "Version": "2021-04-15"})

    def conversations(self, since: str | None) -> list[dict]:
        out, after = [], None
        floor = clock.parse(since).timestamp() * 1000 if since else 0
        for _ in range(50):  # pages of 100, newest first, until older than the last poll
            page = self._get("/conversations/search", locationId=self.location, sortBy="last_message_date", sort="desc",
                             limit=100, startAfterDate=after).get("conversations") or []
            for c in page:
                last = c.get("lastMessageDate") or 0
                if last and float(last) < floor:
                    return out
                out.append({"id": c["id"], "channel": "sms", "address": c.get("phone") or "", "last_at": _iso(last) if last else None})
            if len(page) < 100:
                break
            after = page[-1].get("lastMessageDate")
        return out

    def messages(self, cid: str, after: str | None) -> list[dict]:
        msgs, last_id = [], None
        for _ in range(20):
            body = (self._get(f"/conversations/{cid}/messages", limit=100, lastMessageId=last_id).get("messages") or {})
            page = body.get("messages") or []
            for m in page:
                if m.get("messageType") not in (None, "TYPE_SMS", "SMS"):
                    continue
                at = _iso(m.get("dateAdded"))
                msgs.append({"id": m["id"], "direction": "in" if m.get("direction") == "inbound" else "out", "at": at,
                             "text": m.get("body") or "", "attachments": [{"name": str(a).rsplit("/", 1)[-1], "type": "file"}
                                                                          for a in m.get("attachments") or []]})
            if not body.get("nextPage") or not page or (after and min(_iso(m.get("dateAdded")) for m in page) < after):
                break
            last_id = body.get("lastMessageId")
        msgs.sort(key=lambda m: (m["at"], m["id"]))
        return [m for m in msgs if not after or m["at"] >= after]


class ComposioGmailInbox:
    """Gmail through relsend's Composio project (GMAIL_FETCH_EMAILS). One conversation per thread."""
    name = "composio"
    URL = "https://backend.composio.dev/api/v3/tools/execute/{slug}"

    def __init__(self, env: dict):
        self.key, self.account = env.get("RELSEND_COMPOSIO_API_KEY"), env.get("RELSEND_COMPOSIO_CONNECTED_ACCOUNT")
        self.slug = env.get("RELSEND_COMPOSIO_FETCH_SLUG", "GMAIL_FETCH_EMAILS")
        self.me = (env.get("RELSEND_EMAIL_FROM") or "").lower()
        if not self.key or not self.account:
            raise SystemExit("relsend has no Composio project for the inbox")
        self._cache: dict[str, list] = {}

    def conversations(self, since: str | None) -> list[dict]:
        after = int(clock.parse(since).timestamp()) if since else int(clock.now().timestamp()) - 14 * 86400
        # A POST, but a read: Composio executes tools by POST. It is never retried (http only retries GETs).
        out = request("POST", self.URL.format(slug=self.slug), headers={"x-api-key": self.key},
                      body={"connected_account_id": self.account,
                            "arguments": {"query": f"in:inbox after:{after}", "max_results": 100, "include_payload": False}})
        rows = ((out.get("data") or {}).get("messages")) or []
        convs = {}
        for r in rows:
            tid = r.get("threadId") or r.get("messageId")
            sender = (r.get("sender") or "").split("<")[-1].rstrip(">").strip().lower()
            direction = "out" if self.me and sender == self.me else "in"
            msg = {"id": r.get("messageId"), "direction": direction, "at": _iso(r.get("messageTimestamp") or clock.iso()),
                   "text": r.get("messageText") or "", "subject": r.get("subject") or "",
                   "attachments": [{"name": a.get("filename", "file"), "type": a.get("mimeType", "file")} for a in r.get("attachmentList") or []]}
            self._cache.setdefault(tid, []).append(msg)
            c = convs.setdefault(tid, {"id": tid, "channel": "email", "address": "", "last_at": msg["at"]})
            if direction == "in":
                c["address"] = sender
            c["last_at"] = max(c["last_at"], msg["at"])
        return [c for c in convs.values() if c["address"]]

    def messages(self, cid: str, after: str | None) -> list[dict]:
        msgs = sorted(self._cache.get(cid, []), key=lambda m: (m["at"], m["id"]))
        return [m for m in msgs if not after or m["at"] >= after]


class TwilioInbox:
    """Replies to the Twilio number (RELSEND_TWILIO_FROM): inbound messages listed by date, grouped by sender."""
    name = "twilio"

    def __init__(self, env: dict):
        self.sid, self.token, self.number = env.get("RELSEND_TWILIO_SID"), env.get("RELSEND_TWILIO_TOKEN"), env.get("RELSEND_TWILIO_FROM")
        if not self.sid or not self.token or not self.number:
            raise SystemExit("relsend needs RELSEND_TWILIO_SID, RELSEND_TWILIO_TOKEN and RELSEND_TWILIO_FROM for the inbox")
        self._cache: dict[str, list] = {}

    def conversations(self, since: str | None) -> list[dict]:
        after = clock.day(since) if since else clock.day(clock.now() - timedelta(days=14))
        url = (f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json?"
               + urllib.parse.urlencode({"To": self.number, "DateSent>": after, "PageSize": 200}))
        rows = request("GET", url, basic=(self.sid, self.token)).get("messages") or []
        for r in rows:
            if not str(r.get("direction", "")).startswith("inbound"):
                continue
            at = clock.iso(datetime.strptime(r["date_sent"], "%a, %d %b %Y %H:%M:%S %z")) if r.get("date_sent") else clock.iso()
            self._cache.setdefault(r["from"], []).append({"id": r["sid"], "direction": "in", "at": at, "text": r.get("body") or "",
                                                          "attachments": [{"name": "media", "type": "file"}] * int(r.get("num_media") or 0)})
        return [{"id": k, "channel": "sms", "address": k, "last_at": max(m["at"] for m in v)} for k, v in self._cache.items()]

    def messages(self, cid: str, after: str | None) -> list[dict]:
        return sorted((m for m in self._cache.get(cid, []) if not after or m["at"] >= after), key=lambda m: (m["at"], m["id"]))


class GmailDirectInbox:
    """Replies in the sending Gmail mailbox through the Gmail API (RELSEND_GMAIL_ACCESS_TOKEN with gmail.readonly)."""
    name = "gmail"
    BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, env: dict):
        self.token, self.me = env.get("RELSEND_GMAIL_ACCESS_TOKEN"), (env.get("RELSEND_GMAIL_FROM") or "").lower()
        if not self.token or not self.me:
            raise SystemExit("relsend needs RELSEND_GMAIL_ACCESS_TOKEN and RELSEND_GMAIL_FROM for the inbox")
        self._cache: dict[str, list] = {}

    def _get(self, path: str) -> dict:
        return request("GET", f"{self.BASE}{path}", headers={"Authorization": f"Bearer {self.token}"})

    @staticmethod
    def _text(payload: dict) -> str:
        import base64
        if payload.get("mimeType") == "text/plain" and (payload.get("body") or {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode(errors="replace")
        for part in payload.get("parts") or []:
            text = GmailDirectInbox._text(part)
            if text:
                return text
        return ""

    def conversations(self, since: str | None) -> list[dict]:
        after = int(clock.parse(since).timestamp()) if since else int(clock.now().timestamp()) - 14 * 86400
        listing = self._get("/messages?" + urllib.parse.urlencode({"q": f"in:inbox after:{after}", "maxResults": 100}))
        convs = {}
        for ref in listing.get("messages") or []:
            m = self._get(f"/messages/{ref['id']}?format=full")
            headers = {h["name"].lower(): h["value"] for h in (m.get("payload") or {}).get("headers", [])}
            sender = headers.get("from", "").split("<")[-1].rstrip(">").strip().lower()
            msg = {"id": m["id"], "direction": "out" if sender == self.me else "in", "at": _iso(m.get("internalDate") or clock.iso()),
                   "text": self._text(m.get("payload") or {}), "subject": headers.get("subject", ""),
                   "attachments": [{"name": p.get("filename"), "type": p.get("mimeType")} for p in (m.get("payload") or {}).get("parts") or []
                                   if p.get("filename")]}
            self._cache.setdefault(m["threadId"], []).append(msg)
            c = convs.setdefault(m["threadId"], {"id": m["threadId"], "channel": "email", "address": "", "last_at": msg["at"]})
            if msg["direction"] == "in":
                c["address"] = sender
            c["last_at"] = max(c["last_at"], msg["at"])
        return [c for c in convs.values() if c["address"]]

    def messages(self, cid: str, after: str | None) -> list[dict]:
        return sorted((m for m in self._cache.get(cid, []) if not after or m["at"] >= after), key=lambda m: (m["at"], m["id"]))


def readers_from_env(env: dict) -> list:
    names = [n.strip() for n in env.get("RELSEND_INBOX_READERS", "").split(",") if n.strip()]
    out = []
    for n in names:
        if n == "ghl":
            out.append(GhlInbox(env))
        elif n == "twilio":
            out.append(TwilioInbox(env))
        elif n == "gmail":
            out.append(GmailDirectInbox(env))
        elif n == "composio":
            if not env.get("RELSEND_EMAIL_FROM"):  # without it our own sent mail (and its footer) would read as replies
                raise SystemExit("set RELSEND_EMAIL_FROM (the sending mailbox) before reading the email inbox")
            out.append(ComposioGmailInbox(env))
        elif n == "files":
            out.append(FilesInbox(Path(env["RELSEND_INBOX_DIR"])))
        else:
            raise SystemExit(f"unknown inbox reader {n}")
    return out


# ---------------------------------------------------------------- poller
class Inbox:
    def __init__(self, paths: config.Paths | None = None, env: dict | None = None, readers: list | None = None):
        clock.refuse_fake_clock("relsend inbox")
        self.paths = paths or config.resolve("send")
        self.home = self.paths.send_home or self.paths.home
        self.home.mkdir(parents=True, exist_ok=True)
        self.con = connect(self.paths.sends_db, SCHEMA)
        self.env = dict(env if env is not None else os.environ)
        self.readers = readers if readers is not None else readers_from_env(self.env)

    def _audit(self, action, ref=None, detail=None):
        self.con.execute("INSERT INTO audit (at, actor, action, ref, detail) VALUES (?,?,?,?,?)",
                         (clock.iso(), "relsend-inbox", action, ref, json.dumps(detail or {}, sort_keys=True)))

    def _watermark(self, provider: str, cid: str):
        return self.con.execute("SELECT last_inbound_id, last_inbound_at FROM inbox_watermark WHERE provider=? AND conversation_id=?",
                                (provider, cid)).fetchone()

    def _turns(self, reader, conv: dict) -> list[dict]:
        wm = self._watermark(reader.name, conv["id"])
        after = wm["last_inbound_at"] if wm else None
        msgs = reader.messages(conv["id"], after)
        turns, cur = [], None
        for m in msgs:
            if m["direction"] != "in":
                cur = None  # our message ends the turn; the next inbound starts a new one
                continue
            seen = self.con.execute("SELECT 1 FROM inbound_seen WHERE provider=? AND msg_id=?", (reader.name, m["id"])).fetchone()
            if seen:
                continue
            if cur is None or conv["channel"] == "email":
                cur = {"provider": reader.name, "conversation_id": conv["id"], "channel": conv["channel"],
                       "address": canonical.address_norm(conv["channel"], conv["address"]), "msgs": []}
                turns.append(cur)
            cur["msgs"].append(m)
        return turns

    def poll(self) -> dict:
        out = {"turns": 0, "opt_outs": 0, "wrong_numbers": 0, "conversations": 0}
        started = clock.iso()
        turns = []
        for reader in self.readers:
            last = self._watermark(reader.name, "*")
            since = last["last_inbound_at"] if last else None
            for conv in reader.conversations(since):
                out["conversations"] += 1
                turns += self._turns(reader, conv)
        turns.sort(key=lambda t: (t["msgs"][0]["at"], t["conversation_id"]))  # oldest first across every conversation
        for turn in turns:
            floor = self.handle(turn)
            out["turns"] += 1
            out["opt_outs"] += floor == "opt_out"
            out["wrong_numbers"] += floor == "wrong_number"
        with tx(self.con):
            for reader in self.readers:  # the next poll lists conversations active since this one started (with overlap)
                self.con.execute("INSERT OR REPLACE INTO inbox_watermark VALUES (?,?,?,?)",
                                 (reader.name, "*", None, clock.iso(clock.parse(started) - timedelta(minutes=10))))
        return out

    def handle(self, turn: dict) -> str:
        channel, address = turn["channel"], turn["address"]
        texts = [quoting.strip_quoted_email(m["text"]) if channel == "email" else str(m["text"] or "") for m in turn["msgs"]]
        text = "\n".join(t for t in texts if t.strip())[:MAX_TEXT]
        floor = intents.classify(text, channel)
        last = turn["msgs"][-1]
        person = self.con.execute("SELECT person_id FROM outbox WHERE address=? AND person_id IS NOT NULL ORDER BY row_id DESC LIMIT 1",
                                  (address,)).fetchone()
        person_id = person["person_id"] if person else None
        applied = []
        ids = [m["id"] for m in turn["msgs"]]
        doc = {"format": "relcore-inbound/v1", "provider": turn["provider"], "conversation_id": turn["conversation_id"],
               "channel": channel, "address": address, "person_id": person_id, "msg_ids": ids, "last_msg_id": last["id"],
               "first_at": turn["msgs"][0]["at"], "at": last["at"], "subject": turn["msgs"][0].get("subject", ""),
               "text": text, "quoted_history_removed": channel == "email",
               "attachments": [a for m in turn["msgs"] for a in m.get("attachments") or []],
               "floor": {"intent": floor["intent"], "matched": floor["matched"]}, "applied": applied}
        if floor["intent"] == "opt_out":
            applied += [{"type": "address", "value": address, "channel": "*", "reason": "opt_out"}]
            if person_id:
                applied += [{"type": "entity", "value": person_id, "channel": "*", "reason": "opt_out"}]
        elif floor["intent"] == "wrong_number":
            applied += [{"type": "address", "value": address, "channel": channel, "reason": "wrong_number"}]
        digest = hashlib.sha256("|".join([turn["provider"], *ids]).encode()).hexdigest()[:12]
        stamp = last["at"].replace("-", "").replace(":", "").lower()
        spool.write(self.paths.spool / "inbound", f"in-{stamp}-{digest}.json", doc)  # first: a crash re-reads, trp dedupes
        with tx(self.con):
            for item in applied:
                self.con.execute("INSERT OR IGNORE INTO suppression VALUES (?,?,?,?,?,?)",
                                 (item["type"], item["value"], item["channel"], item["reason"], "inbox", clock.iso()))
            for m in turn["msgs"]:
                self.con.execute("INSERT OR IGNORE INTO inbound_seen VALUES (?,?,?)", (turn["provider"], m["id"], clock.iso()))
            prev = self.con.execute("SELECT at FROM latest_inbound WHERE address=?", (address,)).fetchone()
            if not prev or prev["at"] <= last["at"]:
                self.con.execute("INSERT OR REPLACE INTO latest_inbound VALUES (?,?,?)", (address, last["id"], last["at"]))
            wm = self._watermark(turn["provider"], turn["conversation_id"])
            if not wm or (wm["last_inbound_at"] or "") <= last["at"]:
                self.con.execute("INSERT OR REPLACE INTO inbox_watermark VALUES (?,?,?,?)",
                                 (turn["provider"], turn["conversation_id"], last["id"], last["at"]))
            if applied:
                self._audit("inbox_floor", address, {"intent": floor["intent"], "matched": floor["matched"]})
        return floor["intent"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relsend-inbox")
    ap.add_argument("--once", action="store_true")
    ap.parse_args(argv)
    inbox = Inbox()
    if not inbox.readers:  # loud: replies (and opt-outs) would otherwise go unread without anyone noticing
        reason = "no inbox readers configured (RELSEND_INBOX_READERS): partner replies and opt-outs are not being read"
        spool.write(inbox.paths.spool / "alerts", f"alert-inbox-unconfigured-{clock.day(clock.now())}.json",
                    {"kind": "inbox_unconfigured", "reason": reason, "at": clock.iso()})
        print(json.dumps({"turns": 0, "error": reason}))
        return 1
    try:
        print(json.dumps(inbox.poll()))
    except HTTPError as err:
        print(json.dumps({"error": str(err)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
