"""One canonical encoding for everything that is hashed or signed, shared by trp, relapprove and relsend.

payload_hash(bundle) covers, per message: n, channel, the normalized address, subject and body (NFC), the person
and partnership ids, the first-touch flag, the consent basis and reply_to; plus the action id, kind, employee,
voice and the bundle's own expiry. Nobody trusts a hash field inside a bundle: every role recomputes it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import unicodedata

DOMAIN = b"relcore-approval-v1\n"
KEY_ID = "relcore-1"
MESSAGE_FIELDS = ("n", "channel", "address", "subject", "body", "person_id", "partnership_id", "first_touch",
                  "consent_basis", "reply_to")


def nfc(obj):
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [nfc(x) for x in obj]
    if isinstance(obj, dict):
        return {nfc(k): nfc(v) for k, v in obj.items()}
    return obj


def encode(obj) -> bytes:
    return json.dumps(nfc(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def address_norm(channel: str, address: str) -> str:
    from . import normalize
    if channel == "email":
        return normalize.email(address) or address.strip().lower()
    if channel == "sms":
        return normalize.phone(address) or address.strip()
    return address.strip()


def message_core(m: dict) -> dict:
    core = {k: m.get(k) for k in MESSAGE_FIELDS}
    core["address"] = address_norm(m["channel"], m["address"])
    core["subject"] = core["subject"] or ""
    core["first_touch"] = bool(core["first_touch"])
    if m.get("lint_profile") not in (None, "", "standard"):  # signed too, so nobody can relax the rules after approval
        core["lint_profile"] = m["lint_profile"]
    return core


def payload_hash(bundle: dict) -> str:
    body = {"action_id": bundle["action_id"], "kind": bundle["kind"], "employee": bundle.get("employee"),
            "voice": bundle.get("voice"), "expires_at": bundle["expires_at"],
            "messages": [message_core(m) for m in sorted(bundle["messages"], key=lambda m: m["n"])]}
    return hashlib.sha256(encode(body)).hexdigest()


def approval_record(approval: dict) -> dict:
    keys = ("approval_id", "action_id", "decision", "payload_hash", "exclusions", "edits", "approver", "decided_at",
            "expires_at", "key_id")
    return {k: approval.get(k) for k in keys}


def sign(key: bytes, approval: dict) -> str:
    return hmac.new(key, DOMAIN + encode(approval_record(approval)), hashlib.sha256).hexdigest()


def verify(key: bytes, approval: dict, signature: str) -> bool:
    return hmac.compare_digest(sign(key, approval), signature or "")
