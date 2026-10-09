"""Inbound intents: an ordered keyword floor that runs before any model sees the text.

The first intent that matches wins, in ORDER. Matching is on whole words of normalized text (lowercase, accents
folded, curly quotes straightened), after quoted email history is stripped, so "nonstop" is not STOP and an
"unsubscribe" inside a quoted earlier message is not an opt-out.

The model (the Hermes agent) may refine the intent through rel_replies_prepare. It can never downgrade an opt_out,
identity_question or complaint the floor found, and it can never turn anything into a softer intent than
wrong_number or help either: those four plus help are decided here only.
"""
from __future__ import annotations

import re
import unicodedata

from . import quoting

ORDER = ("opt_out", "help", "wrong_number", "identity_question", "complaint", "has_opportunity", "accept_with_time",
         "accept", "not_now", "not_interested", "commission_question", "question", "wants_help", "general")
LOCKED = {"opt_out", "help", "wrong_number", "identity_question", "complaint"}   # the model cannot change these
NO_DRAFT = {"opt_out", "wrong_number", "identity_question", "complaint"}         # no reply is drafted at all
NOT_ENGAGEMENT = {"opt_out", "help", "wrong_number", "identity_question", "not_interested"}  # never counted

_STRONG_STOP = r"stop|stopall|unsubscribe|optout|opt out|revoke"
_WEAK_STOP = r"cancel|end|quit"  # only when the message is little more than the word ("END", "quit please")
_STOP_PHRASES = (r"take me off", r"remove me", r"(do not|dont|don't) (contact|text|email|message|call) me( again)?",
                 r"lose my number", r"delete my number", r"stop (texting|emailing|messaging|contacting)",
                 r"leave me alone", r"no more (texts|emails|messages)")
_TIME = (r"(mon|tues|wednes|thurs|fri|satur|sun)day|tomorrow|today|tonight|this (morning|afternoon|evening|week)|"
         r"(next|this) (mon|tues|wednes|thurs|fri)day|mornings?|afternoons?|evenings?|noon|"
         r"\d{1,2}(:\d{2})?\s?(am|pm)|\d{1,2}:\d{2}|next week")
_ACCEPT = (r"yes|yeah|yep|yup|sure|ok|okay|sounds good|sounds great|works for me|that works|happy to|let'?s do it|"
           r"i'?m in|count me in|definitely|absolutely|of course|love to|i'?d like that|interested")
_DEFER = (r"not (right )?now|check back|circle back|reach out (again )?(later|in)|next (month|quarter|year)|"
          r"later (this|next) (month|year|quarter)|maybe later|slammed|swamped|buried|too busy|busy (right now|season)|"
          r"after the (holidays|new year|summer|season|launch)|in a (few|couple of) (weeks|months)|not a good time|"
          r"bad timing|another time|down the road|q[1-4]")
_DECLINE = (r"not interested|no thanks|no thank you|not for (me|us)|not a (good )?fit|we'?re good|i'?m good|"
            r"(do not|don'?t) need|pass on this|i'?ll pass|we'?ll pass|no longer|not something (we|i)")
_IDENTITY = (r"(is|are) (this|you) (a )?(bot|robot|ai|automated|real|a real person|a person|human)|"
             r"am i (talking|texting|speaking) (to|with) (a )?(bot|robot|ai|person|human)|"
             r"is this automated|chat ?gpt|who am i (talking|texting) to")
_COMPLAINT = (r"never (got )?paid|you owe|owe me|still waiting (on|for) (my )?(payment|commission|check|money)|"
              r"(have not|haven'?t) been paid|scam|scammer|rip ?off|fraud|lost (me )?my client|stole|harass(ing|ment)?|"
              r"report (you|this)|lawyer|attorney")
_WRONG = (r"wrong (number|person|guy|girl|contact)|you have the wrong|no one (here )?by that name|"
          r"(there'?s|there is) no \w+ (here|at this number)|not my number|this number (is|was) (new|reassigned)")
_REALLY_NAME = re.compile(r"\b(?:is|are) (?:this|you) (?:really|actually) ([A-Z][a-z]+)\b(?! (?:free|true|worth|necessary|it))")
_OPPORTUNITY = (r"i (have|got) (a|an|someone|somebody|two|three|\d+) (client|patient|member|lead|referral|friend|person)s?|"
                r"(have|got) a (client|patient|referral|lead) for you|someone who (needs|could use|wants)|"
                r"know (someone|somebody|a few people)|referr(al|ing) (for|to) you|(we'?re|i'?m) launching|launching (a|our|my)|"
                r"(have|got) a (launch|deal)|"
                r"(sending|send) (someone|somebody|a client|a patient) (your way|over)")
_COMMISSION = r"commission|payout|pay ?out|percentage|how much (do|would|will) (i|we) (get|make|earn)|rev(enue)? share|get paid|paid out|rate"
_HELP_WANTED = (r"send (me|over) (the |some )?(assets|graphics|images|copy|materials|a flyer|flyers|a page|posts|a link|templates?)|"
                r"(assets|graphics|swipe|flyer|templates?|something i can (share|post))|a landing page|write (a|the) post")
_QUESTION_START = r"^(what|how|when|where|why|who|which|can|could|do|does|did|is|are|will|would|should)\b"


def normalize(text: str, channel: str = "sms") -> str:
    body = quoting.strip_quoted_email(text) if channel == "email" else str(text or "")
    body = unicodedata.normalize("NFKD", body)
    body = "".join(c for c in body if not unicodedata.combining(c))
    body = body.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", body.lower()).strip()


def _has(pattern: str, t: str) -> re.Match | None:
    return re.search(rf"(?<![\w'])(?:{pattern})(?![\w'])", t)


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t)


def classify(text: str, channel: str = "sms") -> dict:
    """The floor. Returns {"intent", "matched", "deferral", "time"}; matched is the words that decided it."""
    t = normalize(text, channel)
    words = _words(t)

    def hit(intent, m):
        return {"intent": intent, "matched": m.group(0) if hasattr(m, "group") else m, "text": t}

    if not t:
        return {"intent": "general", "matched": "", "text": t}
    m = _has(_STRONG_STOP, t)
    if m:
        return hit("opt_out", m)
    if len(words) <= 3:
        m = _has(_WEAK_STOP, t)
        if m:
            return hit("opt_out", m)
    for p in _STOP_PHRASES:
        m = _has(p, t)
        if m:
            return hit("opt_out", m)
    if len(words) <= 2 and _has(r"help|info", t):
        return hit("help", _has(r"help|info", t))
    m = _has(_WRONG, t)
    if m:
        return hit("wrong_number", m)
    m = _has(_IDENTITY, t) or _REALLY_NAME.search(unicodedata.normalize("NFKD", str(text or "")).replace("\u2019", "'"))
    if m:
        return hit("identity_question", m)
    m = _has(_COMPLAINT, t)
    if m:
        return hit("complaint", m)
    m = _has(_OPPORTUNITY, t)
    if m:
        return hit("has_opportunity", m)
    defer, decline = _has(_DEFER, t), _has(_DECLINE, t)
    when, yes = _has(_TIME, t), _has(_ACCEPT, t)
    cue = _has(r"how about|what about|free|available|works|open", t)
    if when and not defer and not decline and (yes or cue or "?" in t):
        return {**hit("accept_with_time", when), "time": when.group(0)}
    if yes and not defer and not decline and not _has(r"not|no|maybe", t.split(",")[0]):
        return hit("accept", yes)
    if defer:
        return hit("not_now", defer)
    if decline:
        return hit("not_interested", decline)
    m = _has(_COMMISSION, t)
    if m and ("?" in t or re.search(_QUESTION_START, t)):
        return hit("commission_question", m)
    m = _has(_HELP_WANTED, t)  # a concrete ask for assets beats the generic question below
    if m and _has(r"send|need|want|could (you|i|we) get|do you have|share|can i get|post", t):
        return hit("wants_help", m)
    if "?" in t or re.search(_QUESTION_START, t):
        return hit("question", "?")
    return {"intent": "general", "matched": "", "text": t}


def refine(floor: str, proposed: str | None) -> tuple[str, str | None]:
    """The model's refinement, applied only where the floor allows it. Returns (intent, refusal reason or None)."""
    if not proposed or proposed == floor:
        return floor, None
    if proposed not in ORDER:
        return floor, f"{proposed} is not an intent"
    if floor in LOCKED:
        return floor, f"the keyword floor found {floor}; it cannot be changed"
    if proposed in LOCKED - {"identity_question", "complaint", "opt_out"}:
        return floor, f"{proposed} is decided by the keyword floor only"
    return proposed, None


def counts_as_engagement(intent: str) -> bool:
    return intent not in NOT_ENGAGEMENT


# What a reply does for each intent (shown to the drafting employee with each pending message).
MOVES = {
    "opt_out": "No reply. They are on the do-not-contact list on every channel.",
    "help": "Send the HELP reply from config only (who we are, how to stop). Not counted as a reply or engagement.",
    "wrong_number": "No reply. The number is marked bad; find the right contact another way.",
    "identity_question": "No draft. The named sender replies personally; drafts stay blocked until the owner releases the hold.",
    "complaint": "No draft. Urgent task for the owner; the partner is on the grievance list.",
    "has_opportunity": "Same-day: reply with their own link and 'text me a name'. The owner has an urgent task.",
    "accept_with_time": "Confirm the exact time they gave, say a calendar hold is coming. Nothing else.",
    "accept": "Offer two specific times. One question.",
    "not_now": "Short and warm, no ask. The next touch is set from what they said.",
    "not_interested": "Thank them, offer the link once, stop the sequence.",
    "commission_question": "Answer only from the terms on file; otherwise say you will find out (the owner has a task).",
    "question": "Answer from approved facts only; otherwise say you will find out (a task is created).",
    "wants_help": "Send the starter kit if it exists; scope a call only if they ask for one.",
    "general": "Reflect one thing they said, then ask the next question from the brief.",
}
