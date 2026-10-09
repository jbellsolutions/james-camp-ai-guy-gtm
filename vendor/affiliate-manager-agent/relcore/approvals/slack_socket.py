"""The approvals Slack app (Socket Mode, its own app and tokens, separate from the agent's Slack app).

Slack delivers a button click to the app that posted the message, so this app posts every approval card itself.
It accepts decisions only from owner Member IDs in /etc/relcore/owners.json, ignores bots, message subtypes and
edits, and dedupes every event.

    RELAPPROVE_SLACK_BOT_TOKEN, RELAPPROVE_SLACK_APP_TOKEN in /etc/relcore/relapprove.env
    approvals.json: {"slack_channel": "C0123", "approval_valid_hours": 24}
"""
from __future__ import annotations

import json
import os
import time

from .. import clock
from ..db import tx
from .service import Refused, Service, parse_command


def blocks_for(service: Service, item: dict) -> list:
    text = service.card_text(item["action_id"])
    chunks = [text[i:i + 2900] for i in range(0, len(text), 2900)]
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": c}} for c in chunks[:45]]
    if item["state"] == "shown":
        _, row = service.shown_bundle(item["action_id"])
        value = json.dumps({"action_id": item["action_id"], "payload_hash": row["payload_hash"]})
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Approve all"}, "style": "primary", "action_id": "relcore_approve", "value": value},
            {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger", "action_id": "relcore_reject", "value": value}]})
    return blocks


class Handler:
    """Transport-free event handling, so it can be tested without Slack."""

    def __init__(self, service: Service, post):
        self.service, self.post = service, post

    def seen(self, event_id: str) -> bool:
        with tx(self.service.con):
            cur = self.service.con.execute("INSERT OR IGNORE INTO slack_events_seen VALUES (?,?)", (event_id, clock.iso()))
        return cur.rowcount == 0

    def on_block_action(self, payload: dict, event_id: str) -> str:
        if self.seen(event_id):
            return "duplicate"
        user = (payload.get("user") or {}).get("id")
        owner = self.service.owner_for(slack_user=user)
        if not owner:
            return "ignored: not an owner"
        act = (payload.get("actions") or [{}])[0]
        value = json.loads(act.get("value") or "{}")
        _, row = self.service.shown_bundle(value.get("action_id", ""))
        if row["payload_hash"] != value.get("payload_hash"):
            return "refused: the card is out of date"
        verb = {"relcore_approve": "approve", "relcore_reject": "reject"}.get(act.get("action_id"))
        try:
            out = self.service.decide(value["action_id"], verb, approver=owner, via="slack")
        except Refused as err:
            return f"refused: {err}"
        return f"{out['decision']} by {owner['name']}: {out['messages']} message(s)"

    def on_message(self, event: dict, event_id: str) -> str | None:
        if self.seen(event_id):
            return None
        if event.get("bot_id") or event.get("subtype") or event.get("edited"):
            return None
        owner = self.service.owner_for(slack_user=event.get("user"))
        cmd = parse_command(event.get("text", ""))
        if not cmd or not owner:
            return None
        try:
            if cmd["verb"] == "edit":
                out = self.service.edit(cmd["action_id"], cmd["n"], cmd["text"], approver=owner)
                return f"edit saved for {cmd['n']}. It goes out as:\n> " + out["final"].replace("\n", "\n> ")
            out = self.service.decide(cmd["action_id"], cmd["verb"], approver=owner, via="slack", exclusions=cmd.get("exclusions", []))
            return f"{out['decision']} by {owner['name']}: {out['messages']} message(s)"
        except Refused as err:
            return f"refused: {err}"


def main() -> int:  # pragma: no cover - needs Slack
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    service = Service()
    channel = service.settings.get("slack_channel")
    if not channel:
        raise SystemExit("approvals.json needs slack_channel")
    web = WebClient(token=os.environ["RELAPPROVE_SLACK_BOT_TOKEN"])
    handler = Handler(service, post=lambda text, ts=None: web.chat_postMessage(channel=channel, text=text, thread_ts=ts))

    def listener(client, req):
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type == "interactive" and req.payload.get("type") == "block_actions":
            msg = handler.on_block_action(req.payload, req.envelope_id)
            web.chat_postMessage(channel=channel, text=msg, thread_ts=(req.payload.get("message") or {}).get("ts"))
        elif req.type == "events_api":
            ev = req.payload.get("event") or {}
            if ev.get("type") == "message" and ev.get("channel") == channel:
                reply = handler.on_message(ev, req.payload.get("event_id") or req.envelope_id)
                if reply:
                    web.chat_postMessage(channel=channel, text=reply, thread_ts=ev.get("thread_ts") or ev.get("ts"))

    sm = SocketModeClient(app_token=os.environ["RELAPPROVE_SLACK_APP_TOKEN"], web_client=web)
    sm.socket_mode_request_listeners.append(listener)
    sm.connect()
    while True:
        for item in service.scan():
            r = web.chat_postMessage(channel=channel, text=f"Approval needed: {item['action_id']}", blocks=blocks_for(service, item))
            with tx(service.con):
                service.con.execute("UPDATE bundles_seen SET slack_channel=?, slack_ts=? WHERE action_id=?",
                                    (channel, r["ts"], item["action_id"]))
        for alert in service.alerts():  # unknown outcomes and halts reach the owner at once
            web.chat_postMessage(channel=channel, text=alert["text"])
            service.alert_posted(alert["name"])
        time.sleep(15)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
