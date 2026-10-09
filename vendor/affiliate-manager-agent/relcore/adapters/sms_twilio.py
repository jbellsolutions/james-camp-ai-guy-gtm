"""SMS through Twilio (RELSEND_TWILIO_SID, RELSEND_TWILIO_TOKEN, RELSEND_TWILIO_MESSAGING_SERVICE)."""
from __future__ import annotations

from . import SendError
from ..http import HTTPError, request


class TwilioSms:
    name = "twilio"

    def __init__(self, env: dict):
        self.sid, self.token = env.get("RELSEND_TWILIO_SID"), env.get("RELSEND_TWILIO_TOKEN")
        self.service = env.get("RELSEND_TWILIO_MESSAGING_SERVICE")
        if not (self.sid and self.token and self.service):
            raise SendError("relsend has no Twilio account configured")

    def send(self, row: dict) -> dict:
        try:
            out = request("POST", f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                          form={"To": row["address"], "MessagingServiceSid": self.service, "Body": row["final_body"]},
                          basic=(self.sid, self.token), timeout=45)
        except HTTPError as err:
            if err.accepted_maybe or err.status >= 500:
                raise SendError(str(err), accepted_maybe=True) from None
            raise SendError(str(err), retry=err.status == 429) from None
        return {"provider_msg_id": out.get("sid", "accepted")}
