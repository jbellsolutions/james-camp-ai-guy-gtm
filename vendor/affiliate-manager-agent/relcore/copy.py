"""House copy rules as code. lint() is run when a draft is submitted, when relapprove builds the card, after
every owner edit, and again by relsend before each message.

email: body 50 to 100 words (footer not counted), subject 1 to 4 lowercase words, no links in a first touch
plan:  the partner plan profile: an email of 80 to 260 words, never a first touch
sms:   at most 2 segments of the final text (opt-out and identity included), GSM-7 or UCS-2 counted correctly
dm:    under 400 characters (drafts only)
all:   no em or en dashes, no exclamation marks, one question at most, no call ask on a first touch, no mention of
       AI or automation, no earnings claims, no banned hype words
"""
from __future__ import annotations

import re

from .compose import final_text

GSM7 = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
           "abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = set("^{}\\[~]|€\f")
BANNED = ("unlock", "elevate", "game-changer", "game changer", "dive in", "supercharge", "revolutionize", "seamless",
          "in today's fast-paced world", "synergy", "leverage our", "circle back")
AI = re.compile(r"\b(ai|a\.i\.|artificial intelligence|assistant|automated|automation|bot|chatgpt|gpt|drafted|"
                r"language model|llm)\b", re.I)
CALL_ASK = re.compile(r"\b(hop on|jump on|quick call|a call|short call|15 minutes|20 minutes|zoom|calendly|book a time|"
                      r"grab time|meeting|schedule a|set up a time|chat for)\b", re.I)
EARNINGS = re.compile(r"\$\s?\d|\b\d+\s?%|\b(earn|earning|earnings|income|make money|passive|commission of|per referral pays|"
                      r"guaranteed|figures?)\b", re.I)
LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|co)\b", re.I)


def sms_segments(text: str) -> tuple[int, str]:
    if all(c in GSM7 or c in GSM7_EXT for c in text):
        units = sum(2 if c in GSM7_EXT else 1 for c in text)
        return (1 if units <= 160 else -(-units // 153)), "GSM-7"
    units = len(text.encode("utf-16-le")) // 2
    return (1 if units <= 70 else -(-units // 67)), "UCS-2"


PROFILES = ("standard", "plan")


def lint(channel: str, body: str, *, subject: str = "", first_touch: bool = False, sender: dict | None = None,
         first_in_thread: bool | None = None, settings: dict | None = None, profile: str | None = None) -> dict:
    cfg = dict((settings or {}).get("copy") or {"email_words": [50, 100], "subject_words": [1, 4], "sms_segments": 2, "dm_chars": 400})
    errors, warnings = [], []
    profile = profile or "standard"
    if profile not in PROFILES:
        errors.append(f"unknown copy profile {profile}")
    elif profile == "plan":  # the partner plan: a longer email, never a first touch, every other rule unchanged
        cfg["email_words"] = cfg.get("plan_words", [80, 260])
        if channel != "email":
            errors.append("a partner plan goes by email")
        if first_touch:
            errors.append("a partner plan is never a first touch")
    body = body or ""
    text = f"{subject}\n{body}"
    if re.search("[–—]", text):
        errors.append("em or en dash")
    if "!" in text:
        errors.append("exclamation mark")
    if body.count("?") > 1:
        errors.append("more than one question")
    if AI.search(body):
        errors.append("mentions AI, an assistant or automation")
    if EARNINGS.search(body):
        errors.append("earnings claim or figure")
    for word in BANNED:
        if word in text.lower():
            errors.append(f"banned phrase: {word}")
    if first_touch and CALL_ASK.search(body):
        errors.append("first touch asks for a call")
    if first_touch and LINK.search(body):
        errors.append("link in a first touch")
    if re.search(r"\baffiliates?\b", body, re.I):
        warnings.append("say partner, not affiliate, unless the client says otherwise")
    out = {"channel": channel}
    if channel == "email":
        words = len(re.findall(r"\b[\w'’]+\b", body))
        lo, hi = cfg["email_words"]
        if not lo <= words <= hi:
            errors.append(f"email body is {words} words (want {lo} to {hi})")
        sw = len(subject.split())
        slo, shi = cfg["subject_words"]
        if not subject:
            errors.append("email needs a subject")
        elif not slo <= sw <= shi or subject != subject.lower():
            errors.append(f"subject must be {slo} to {shi} lowercase words")
        out["words"] = words
    elif channel == "sms":
        final = final_text("sms", body, sender or {}, first_in_thread=first_touch if first_in_thread is None else first_in_thread)
        segs, enc = sms_segments(final)
        if segs > cfg["sms_segments"]:
            errors.append(f"sms is {segs} segments ({enc}) with the opt-out line (max {cfg['sms_segments']})")
        if enc == "UCS-2":
            warnings.append("UCS-2 characters (emoji, curly quotes or accents) shrink each segment to 70 characters")
        out.update(segments=segs, encoding=enc, final=final)
    elif channel in ("dm", "linkedin"):
        if len(body) >= cfg["dm_chars"]:
            errors.append(f"dm is {len(body)} characters (max {cfg['dm_chars'] - 1})")
    else:
        errors.append(f"unknown channel {channel}")
    out.update(ok=not errors, errors=errors, warnings=warnings)
    return out
