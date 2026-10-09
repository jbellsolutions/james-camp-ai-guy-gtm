"""Normalizers: every slot value is tidied the same way whether it came from a rule, a model or an import."""
from __future__ import annotations

import re
import unicodedata

# North American area codes to time zones (conservative subset; unknown codes fall back with basis "fallback").
AREA_TZ = {
    "America/New_York": "201 202 203 207 212 215 216 239 240 248 267 301 302 305 313 315 321 336 347 352 386 401 404 407 410 412 434 440 443 470 475 478 484 502 513 516 518 540 551 561 571 585 586 603 607 609 610 614 617 631 646 678 703 704 706 716 718 727 732 734 740 754 757 770 772 774 781 786 802 803 804 813 828 843 845 856 860 862 863 864 865 904 908 910 912 914 917 919 929 941 954 973 978 980 984",
    "America/Chicago": "205 210 214 217 218 219 224 225 251 254 256 262 270 281 309 312 314 316 318 319 320 331 334 337 346 361 402 405 409 414 417 430 432 469 479 501 504 507 512 515 563 573 601 608 612 615 618 620 630 636 641 651 662 682 708 712 713 715 731 737 763 769 773 779 785 806 815 816 817 830 832 847 850 870 901 903 913 918 920 931 936 940 952 956 972 979 985",
    "America/Denver": "303 307 385 406 435 505 575 719 720 801 970",
    "America/Phoenix": "480 520 602 623 928",
    "America/Los_Angeles": "206 209 213 253 310 323 341 360 408 415 424 425 442 503 509 510 530 541 559 562 619 626 628 650 657 661 669 702 707 714 725 747 760 775 805 818 831 858 909 916 925 949 951 971",
}
_AREA = {code: tz for tz, codes in AREA_TZ.items() for code in codes.split()}


def phone(raw: str, default_country: str = "1") -> str | None:
    """E.164 or None. North American numbers default to +1."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        return "+" + digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 10:
        return f"+{default_country}{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def email(raw: str) -> str | None:
    raw = (raw or "").strip().lower()
    return raw if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", raw) else None


def tz_from_phone(e164: str | None) -> tuple[str | None, str]:
    """(timezone, basis). Basis is area_code or fallback; never a silent guess."""
    if e164 and e164.startswith("+1") and len(e164) == 12:
        tz = _AREA.get(e164[2:5])
        if tz:
            return tz, "area_code"
    return None, "fallback"


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def first_name(raw: str) -> str:
    """Greeting name. Emoji removed, ALL CAPS fixed; an email, a company or blank gives ''."""
    text = _EMOJI.sub("", raw or "").strip()
    if not text or "@" in text or re.search(r"\b(inc|llc|ltd|co|corp|clinic|group|studio|pt|gym)\b\.?$", text, re.I):
        return ""
    word = re.split(r"[\s,]+", text)[0].strip(".")
    if not re.search(r"[A-Za-zÀ-ÿ]", word):
        return ""
    if word.isupper() or word.islower():
        word = word.capitalize()
    return word


def greeting_name(raw: str) -> str:
    return first_name(raw) or "there"


CHANNELS = {"email": "email", "e-mail": "email", "mail": "email", "text": "sms", "texting": "sms", "sms": "sms",
            "phone": "call", "call": "call", "calls": "call", "linkedin": "linkedin", "dm": "dm", "instagram": "dm"}


def channel(raw: str) -> str | None:
    return CHANNELS.get((raw or "").strip().lower())


def daypart(raw: str) -> str | None:
    t = (raw or "").lower()
    for key in ("morning", "afternoon", "evening", "weekend"):
        if key in t:
            return key
    return None


def count(raw) -> int | None:
    """'12k' -> 12000, '1.2m' -> 1200000, '850' -> 850."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([km])?\b", str(raw or "").lower().replace(",", ""))
    if not m:
        return None
    n = float(m.group(1))
    return int(n * {"k": 1_000, "m": 1_000_000}.get(m.group(2) or "", 1))


def region(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip()).title()


def hub_value(raw: str) -> str:
    """Keep real case (CPA, SaaS, YouTube); trim whitespace."""
    return re.sub(r"\s+", " ", (raw or "").strip())


def text_key(raw) -> str:
    """Dedupe key for a fact value."""
    t = unicodedata.normalize("NFKC", str(raw)).lower()
    return re.sub(r"[^\w]+", " ", t).strip()


def apply(kind: str | None, value):
    if kind == "count":
        return count(value)
    if kind == "channel":
        return channel(value)
    if kind == "daypart":
        return daypart(value)
    if kind == "region":
        return region(value)
    return value.strip() if isinstance(value, str) else value
