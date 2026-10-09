"""Stable ids and filenames for cards."""
from __future__ import annotations

import hashlib
import re
import secrets

PREFIX = {"person": "pe", "partner": "pt", "partnership": "ps", "action": "ac", "call": "cl", "task": "tk", "approval": "ap"}


ID_HEX = 10  # 40 bits: no realistic collision across a CRM; filenames show the first 6


def new_id(kind: str, seed: str | None = None, salt: int = 0) -> str:
    """`pe_8f2c1a03bd`. With a seed (e.g. a CRM id) the id is deterministic, so re-imports never duplicate.
    The store re-calls with salt+1 if a seeded id is already taken by a different seed."""
    if seed:
        tail = hashlib.sha256(f"{seed}#{salt}".encode() if salt else seed.encode()).hexdigest()[:ID_HEX]
    else:
        tail = secrets.token_hex(ID_HEX // 2)
    return f"{PREFIX[kind]}_{tail}"


def kind_of(entity_id: str) -> str:
    rev = {v: k for k, v in PREFIX.items()}
    return rev[entity_id.split("_", 1)[0]]


_BAD = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]')


def safe_name(text: str, limit: int = 80) -> str:
    text = _BAD.sub(" ", text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rstrip(" .") or "Unnamed"


def card_filename(display: str, entity_id: str) -> str:
    return f"{safe_name(display)} ({entity_id.split('_', 1)[1][:6]}).md"
