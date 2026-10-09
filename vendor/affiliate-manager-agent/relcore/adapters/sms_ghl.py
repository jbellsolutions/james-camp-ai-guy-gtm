"""SMS through GoHighLevel conversations with relsend's own private integration token (RELSEND_GHL_TOKEN,
RELSEND_GHL_LOCATION_ID). POST /conversations/messages (Version 2021-04-15). The contract script confirms the shape.
The agent's GHL token is read-only and cannot reach this endpoint."""
from __future__ import annotations

import urllib.parse

from . import SendError
from ..http import HTTPError, request

BASE = "https://services.leadconnectorhq.com"


class GhlSms:
    name = "ghl"

    def __init__(self, env: dict):
        self.token, self.location = env.get("RELSEND_GHL_TOKEN"), env.get("RELSEND_GHL_LOCATION_ID")
        if not self.token or not self.location:
            raise SendError("relsend has no GHL send token configured")

    def _contact(self, phone: str) -> str:
        q = urllib.parse.urlencode({"locationId": self.location, "number": phone})
        out = request("GET", f"{BASE}/contacts/search/duplicate?{q}",
                      headers={"Authorization": f"Bearer {self.token}", "Version": "2021-07-28"})
        cid = (out.get("contact") or {}).get("id")
        if not cid:
            raise SendError(f"no GHL contact for {phone}")
        return cid

    def send(self, row: dict) -> dict:
        try:
            cid = self._contact(row["address"])
        except HTTPError as err:
            raise SendError(f"contact lookup failed: {err}", retry=err.status in (0, 429, 500, 502, 503)) from None
        try:
            out = request("POST", f"{BASE}/conversations/messages", headers={"Authorization": f"Bearer {self.token}",
                                                                              "Version": "2021-04-15"},
                          body={"type": "SMS", "contactId": cid, "message": row["final_body"]}, timeout=45)
        except HTTPError as err:
            if err.accepted_maybe or err.status >= 500:
                raise SendError(str(err), accepted_maybe=True) from None
            raise SendError(str(err), retry=err.status == 429) from None
        return {"provider_msg_id": str(out.get("messageId") or out.get("id") or "accepted")}
