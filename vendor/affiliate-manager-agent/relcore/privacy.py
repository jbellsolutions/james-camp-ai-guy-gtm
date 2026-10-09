"""never_store, not_from_model and volunteered_only, applied on every write path."""
from __future__ import annotations

import re

# Categories match a disclosure about a specific person (a pronoun or relative near the term), not business
# vocabulary: "orthopedic surgery practice" and "refers post-surgery patients" are fine; "she had knee surgery" is not.
_WHO = r"(?:\bi\b|\bi'm\b|\bi've\b|\bi was\b|\bhe\b|\bshe\b|\bthey\b|\bwe\b|\bmy\b|\bhis\b|\bher\b|\btheir\b|\bour\b|"\
       r"\bwife\b|\bhusband\b|\bson\b|\bdaughter\b|\bmom\b|\bdad\b|\bmother\b|\bfather\b|\bkid\b)"
_NEAR = r"[^.!?\n]{0,40}?"
_AGGREGATE = re.compile(r"\b(patients|clients|customers|members|athletes|runners|people|folks|referrals|cases)\b", re.I)
CATEGORY_WORDS = {
    "health": _WHO + _NEAR + r"\b(surgery|surgical|operation|diagnos\w*|cancer|chemo\w*|diabet\w*|pregnan\w*|hiv|medication|"
              r"prescription|depress\w*|anxiety|disabilit\w*|injur\w*|illness|sick|hospital\w*|in rehab|therapy|condition|"
              r"mental health|recovering|treatment)\b",
    "religion": r"\b(my faith|my church|my mosque|my synagogue|my temple|attends? (?:church|mosque|synagogue|temple)|"
                r"(?:i'm|i am|he's|he is|she's|she is|they're|they are) (?:a |an )?(?:devout |practicing )?"
                r"(?:christian|catholic|muslim|jewish|hindu|buddhist|mormon|atheist|evangelical))\b",
    "politics": r"\b(voted for|my politics|(?:i'm|i am|he's|he is|she's|she is|they're|they are) (?:a )?"
                r"(?:democrat|republican|liberal|conservative|libertarian|socialist)|(?:supports?|donated to) the "
                r"(?:democrats|republicans|gop))\b",
    "sexual_orientation": r"\b((?:i'm|i am|he's|he is|she's|she is|they're|they are) (?:gay|lesbian|bi|bisexual|"
                          r"trans\w*|queer|straight)|sexual orientation|came out as)\b",
    "minors": r"\b(my (?:son|daughter|kid|child|kids|children)'s (?:school|age|name|teacher|class)|"
              r"(?:son|daughter|kid|child) is \d{1,2}\b|\d{1,2}[- ]years?[- ]old (?:son|daughter|kid|child))",
    "passwords": r"\b(password|passcode|pin code|login is)\b",
}
PATTERNS = {
    "government_ids": r"\b\d{3}-\d{2}-\d{4}\b|\b\d{2}-\d{7}\b|\bpassport (?:no\.?|number)\s*\w+",
    "account_numbers": r"\b(?:account|routing|acct)\s*(?:no\.?|number|#)?\s*:?\s*\d{6,}\b",
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def card_numbers(text: str) -> bool:
    for m in re.finditer(r"(?:\d[ -]?){13,19}", text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    return False


def violations(text: str, never_store: list[str]) -> list[str]:
    """Categories found in text. Empty list means the text may be stored."""
    text = str(text or "")
    found = []
    for cat in never_store:
        rx = CATEGORY_WORDS.get(cat) or PATTERNS.get(cat)
        if not rx:
            continue
        for m in re.finditer(rx, text, re.I):
            # "their patients recovering from surgery" is the partner's business, not a person's health.
            if cat == "health" and _AGGREGATE.search(m.group(0)):
                continue
            found.append(cat)
            break
    if "payment_cards" in never_store and card_numbers(text):
        found.append("payment_cards")
    return found


def redact(text: str, never_store: list[str]) -> str:
    """For call notes and research: drop whole sentences that hit a never_store category."""
    kept = [s for s in re.split(r"(?<=[.!?])\s+", str(text or "")) if not violations(s, never_store)]
    return " ".join(kept)


class Refused(ValueError):
    pass


TRUSTED_WRITERS = ("import", "owner")  # `by` values allowed to set not_from_model slots
# Which sources each writer may claim. `by` is fixed by the entrypoint (MCP server = model, importer = import,
# owner CLI = owner, rule extractors = rule) and is never taken from tool arguments.
WRITER_SOURCES = {
    "model": ("reply", "call", "research", "plan"),
    "rule": ("reply", "call", "record"),
    "import": ("record",),
    "owner": ("owner", "record", "reply", "call", "research", "plan"),
}


def check_fact(slot: str, value, source: str, schema: dict, *, by: str = "model", volunteered: bool = True) -> None:
    """Raise Refused when a fact may not be stored. `by` is who wrote it: model (the agent), rule, import, owner."""
    if slot in schema.get("not_from_model", []) and by not in TRUSTED_WRITERS:
        raise Refused(f"{slot} comes only from systems of record or the owner")
    spec = schema["slots"].get(slot)
    if spec is None:
        raise Refused(f"unknown slot {slot}")
    if source not in WRITER_SOURCES.get(by, ()):
        raise Refused(f"a {by} write cannot claim source {source}")
    allowed = spec.get("sources")
    if allowed and source not in allowed and by != "owner":
        raise Refused(f"{slot} cannot be filled from {source}")
    if spec.get("volunteered_only") and not volunteered:
        raise Refused(f"{slot} is kept only when the person raised it")
    hits = violations(str(value), schema.get("never_store", []))
    if hits:
        raise Refused(f"never_store: {', '.join(hits)}")
