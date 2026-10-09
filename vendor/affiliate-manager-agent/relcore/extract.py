"""Rule-based fact extraction (no model). The Hermes agent is the model: it submits richer facts through
rel_facts_record. Rules run first on every inbound message, call and CRM note so the floor never depends on a model."""
from __future__ import annotations

import re

from . import normalize

_UNITS = r"(members|followers|subscribers|downloads|listeners|patients|clients|readers|people|businesses|employees)"


def rule_facts(text: str) -> list[dict]:
    t = " " + (text or "").lower() + " "
    out = []
    if re.search(r"\b(prefer|prefers|easier|best)\b[^.]{0,20}\b(text|texting|sms)\b|\btext is (easier|best)\b|\btext me\b", t):
        out.append({"slot": "preferred_channel", "value": "sms"})
    elif re.search(r"\b(prefer|prefers|easier|best)\b[^.]{0,20}\bemail\b|\bemail is (easier|best)\b|\bemail me\b", t):
        out.append({"slot": "preferred_channel", "value": "email"})
    elif re.search(r"\b(prefer|prefers|easier|best)\b[^.]{0,20}\b(call|phone)\b|\bcall me\b", t):
        out.append({"slot": "preferred_channel", "value": "call"})
    m = re.search(r"\b(?:best|reach me|easiest|free)\b[^.]{0,25}\b(mornings?|afternoons?|evenings?|weekends?)\b", t)
    if m:
        out.append({"slot": "best_time", "value": m.group(1)})
    m = re.search(r"(?:about|around|roughly|~|over|nearly)?\s*(\d[\d,.]*\s?[km]?)\s+" + _UNITS + r"\b", t)
    if m and normalize.count(m.group(1)):
        out.append({"slot": "audience_size", "value": m.group(1)})
    return out
