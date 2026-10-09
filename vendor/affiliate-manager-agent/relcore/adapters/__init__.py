"""Channel adapters used by relsend only. Credentials come from relsend's environment (/etc/relcore/relsend.env).

Every adapter raises SendError. `accepted_maybe=True` means the provider may have taken the message (timeout,
connection drop, 5xx after the request body went out): the worker marks the row unknown and halts.
`retry=True` means the provider certainly refused it for now (429 before acceptance)."""
from __future__ import annotations


class SendError(Exception):
    def __init__(self, message: str, *, accepted_maybe: bool = False, retry: bool = False):
        super().__init__(message)
        self.accepted_maybe, self.retry = accepted_maybe, retry


def provider_for(channel: str, live: bool, env: dict, con=None):
    if not live:
        from .dry import DryProvider
        return DryProvider(con)
    kind = env.get(f"RELSEND_{channel.upper()}_PROVIDER") or {"email": "composio", "sms": "ghl"}[channel]
    if channel == "email" and kind == "composio":
        from .email_composio import ComposioEmail
        return ComposioEmail(env)
    if channel == "email" and kind == "gmail":
        from .email_gmail_direct import GmailDirect
        return GmailDirect(env)
    if channel == "sms" and kind == "ghl":
        from .sms_ghl import GhlSms
        return GhlSms(env)
    if channel == "sms" and kind == "twilio":
        from .sms_twilio import TwilioSms
        return TwilioSms(env)
    if kind == "mock":
        from .mock import MockProvider
        return MockProvider.shared()
    raise SendError(f"no provider {kind} for {channel}")
