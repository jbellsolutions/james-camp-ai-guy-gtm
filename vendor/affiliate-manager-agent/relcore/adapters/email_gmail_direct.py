"""Email straight through the Gmail API with relsend's own OAuth token (RELSEND_GMAIL_ACCESS_TOKEN, RELSEND_GMAIL_FROM).
Adds List-Unsubscribe (mailto) so mailbox providers show an unsubscribe control."""
from __future__ import annotations

import base64
from email.message import EmailMessage

from . import SendError
from ..http import HTTPError, request


class GmailDirect:
    name = "gmail"

    def __init__(self, env: dict):
        self.token, self.sender = env.get("RELSEND_GMAIL_ACCESS_TOKEN"), env.get("RELSEND_GMAIL_FROM")
        if not self.token or not self.sender:
            raise SendError("relsend has no Gmail token configured")

    def send(self, row: dict) -> dict:
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = row["address"], self.sender, row["subject"] or ""
        msg["List-Unsubscribe"] = f"<mailto:{self.sender}?subject=unsubscribe>"
        msg.set_content(row["final_body"])
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            out = request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                          headers={"Authorization": f"Bearer {self.token}"}, body={"raw": raw}, timeout=45)
        except HTTPError as err:
            if err.accepted_maybe or err.status >= 500:
                raise SendError(str(err), accepted_maybe=True) from None
            raise SendError(str(err), retry=err.status == 429) from None
        return {"provider_msg_id": out.get("id", "accepted")}
