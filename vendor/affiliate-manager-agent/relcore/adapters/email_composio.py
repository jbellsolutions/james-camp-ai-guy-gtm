"""Email through Composio REST, using a separate Composio project whose key only relsend holds
(RELSEND_COMPOSIO_API_KEY, RELSEND_COMPOSIO_CONNECTED_ACCOUNT, RELSEND_COMPOSIO_EMAIL_SLUG default GMAIL_SEND_EMAIL).
The request shape is confirmed by the email contract script before the channel goes live."""
from __future__ import annotations

from . import SendError
from ..http import HTTPError, request

URL = "https://backend.composio.dev/api/v3/tools/execute/{slug}"


class ComposioEmail:
    name = "composio"

    def __init__(self, env: dict):
        self.key = env.get("RELSEND_COMPOSIO_API_KEY")
        self.account = env.get("RELSEND_COMPOSIO_CONNECTED_ACCOUNT")
        self.slug = env.get("RELSEND_COMPOSIO_EMAIL_SLUG", "GMAIL_SEND_EMAIL")
        if not self.key or not self.account:
            raise SendError("relsend has no Composio send project configured")

    def send(self, row: dict) -> dict:
        body = {"connected_account_id": self.account,
                "arguments": {"recipient_email": row["address"], "subject": row["subject"] or "", "body": row["final_body"],
                              "is_html": False}}
        try:
            out = request("POST", URL.format(slug=self.slug), headers={"x-api-key": self.key}, body=body, timeout=45)
        except HTTPError as err:
            if err.accepted_maybe or err.status >= 500:
                raise SendError(str(err), accepted_maybe=True) from None
            raise SendError(str(err), retry=err.status == 429) from None
        if out.get("successful") is False or out.get("error"):
            raise SendError(f"composio refused: {out.get('error')}")
        data = out.get("data") or {}
        return {"provider_msg_id": str(data.get("id") or data.get("message_id") or (data.get("response_data") or {}).get("id") or "accepted")}
