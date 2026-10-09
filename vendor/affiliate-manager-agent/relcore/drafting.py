"""Drafting rules as code: hook order, segment wording, the one easy question, channel choice and reply moves.

The Hermes agent writes most drafts itself after reading rel_context; templates here are the floor (and what
waves use when the agent supplies no bodies). Every draft, template or agent-written, goes through lint() and the
context digest check before it can be prepared.
"""
from __future__ import annotations

import re

from . import clock, copy, graph, privacy

SEGMENT_OPENERS = {
    "past_producer": "Thank you for every client you have sent us.",
    "registered_never_produced": "You signed up as a partner a while back and I never followed up properly.",
    "thin_record": "I do not want to waste your time, so just one quick question.",
    "new_recruit": "Welcome aboard, and thank you for joining.",
    "prospect": "",
}
SUBJECTS = {"one_word_ask": "quick question", "give": "your partner link"}


def _slot(profile, name):
    v = profile["slots"].get(name)
    return v[0] if v else None


def hooks(store, ps_id: str) -> list[tuple[str, str]]:
    """Every available hook line in the business's hook order, most specific first. Numbers only if verified."""
    p = store.profile(ps_id)
    partner_id, _ = store.route(ps_id, "partner")
    pp = store.profile(partner_id) if partner_id else {"slots": {}}
    out = []
    for name in store.settings.get("hook_order", []):
        if name == "last_result":
            conv = _slot(p, "conversions")
            if conv and conv["source"] == "record" and int(conv["value"] or 0) > 0:
                out.append((name, f"Your referrals have become {conv['value']} clients with us so far, and each one mattered."))
        elif name == "tier_benefit":
            tier = _slot(p, "tier")
            if tier:
                out.append((name, f"As one of our {tier['value']} partners you are first in line for anything new we make for partners."))
        elif name == "audience":
            aud = _slot(pp, "audience")
            if aud and aud["confidence"] != "low":
                out.append((name, f"I know a lot of your work is with {aud['value']}."))
        elif name == "niche":
            niche = _slot(pp, "niche")
            if niche:
                out.append((name, f"We see a real overlap between {niche['value'].lower()} and the clients we help."))
        elif name == "tenure":
            joined = _slot(p, "joined")
            if joined:
                out.append((name, f"You have been a partner with us since {joined['value'][:4]}."))
        elif name == "source":
            src = next((l["label"] for l in pp.get("links", {}).get("member_of_hub", []) if l["id"].startswith("hub:Sources/")), None)
            if src and src.lower() not in ("ghl import", "crm import", "research"):
                out.append((name, f"We first connected through {src}."))
        elif name == "fallback":
            out.append((name, "I wanted to thank you for being part of our partner program."))
    return out


def _ascii(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def ask_line(store, ps_id: str, arm: str, audience: str | None) -> str:
    category = store.settings.get("category") or "what we do"
    if arm == "give":
        return "Want me to send your partner link and our one-page brief?"
    if audience:
        return f"Are you still mostly working with {audience}?"
    return f"Do your clients ever ask you about {category}?"


def first_touch(store, ps_id: str, person_id: str, channel: str, arm: str, sender: dict) -> dict:
    p = store.profile(ps_id)
    person = store.profile(person_id)
    first = person["fields"].get("first_name") or "there"
    seg = p["fields"].get("segment", "registered_never_produced")
    hk = hooks(store, ps_id)
    # A niche or audience hook beats a bare tenure line when both exist.
    chosen = next(((n, t) for n, t in hk if n != "tenure"), hk[0] if hk else ("fallback", ""))
    partner_id, _ = store.route(ps_id, "partner")
    aud = _slot(store.profile(partner_id), "audience") if partner_id else None
    audience = aud["value"] if aud and aud["confidence"] != "low" and chosen[0] != "audience" else None
    ask = ask_line(store, ps_id, arm, audience)
    me = (sender.get("name") or "").split(" ")[0]
    business = sender.get("business") or store.settings.get("client") or ""
    opener = SEGMENT_OPENERS.get(seg, "")
    if channel == "sms":
        short_ask = "Want your partner link?" if arm == "give" else (f"Still mostly working with {audience}?" if audience else
                                                                     "Do your clients ever ask about what we do?")
        folded = _ascii(first)
        tries = [(f"Hi {first}, {me} at {business} here. {opener} {ask}", None),
                 (f"Hi {first}, {me} at {business} here. {ask}", None),
                 (f"Hi {first}, {me} at {business} here. {short_ask}", None),
                 (f"Hi {first}, {me} at {business}. {short_ask}", None)]
        if folded != first:  # last resort: the name without accents, flagged on the review
            tries += [(f"Hi {folded}, {me} at {business} here. {short_ask}", "name shown without accents to fit 2 sms segments")]
        for body, note in tries:
            body = " ".join(body.split())
            if not copy.lint("sms", body, first_touch=True, sender=sender)["errors"]:
                break
        return {"channel": "sms", "subject": "", "body": body, "hook": chosen[0], "template": f"ft-sms-{seg}-{arm}", "note": note}
    why = (store.settings.get("why_now") or "") if seg == "past_producer" else ""
    parts = [f"Hi {first},", "", f"{me} here from {business}. {opener} {why}".strip(), "", chosen[1], "", ask, "",
             "Thanks,", me]
    body = "\n".join(parts)
    words = len(re.findall(r"\b[\w'’]+\b", body))
    extra = [t for n, t in hk if t != chosen[1]]
    while words < 50 and extra:
        parts.insert(5, extra.pop(0))
        body = "\n".join(parts)
        words = len(re.findall(r"\b[\w'’]+\b", body))
    return {"channel": "email", "subject": SUBJECTS.get(arm, "quick question"), "body": body, "hook": chosen[0],
            "template": f"ft-email-{seg}-{arm}"}


def choose_channel(store, person_id: str, allowed: list[str]) -> tuple[str | None, str]:
    """Preferred channel if consent allows it, else email, else sms. (channel, reason-if-none)."""
    p = store.profile(person_id)
    consent = p["consent"]
    needs = store.settings["consent_required"]
    usable = [c for c in allowed if consent.get(c) in needs.get(c, []) and p["identities"].get("email" if c == "email" else "phone")]
    if not usable:
        return None, "no consent basis or address for any allowed channel"
    pref = (p["slots"].get("preferred_channel") or [{}])[0].get("value")
    if pref in usable:
        return pref, ""
    return ("email" if "email" in usable else usable[0]), ""


def address_for(store, person_id: str, channel: str) -> str | None:
    ids = store.profile(person_id)["identities"]
    vals = ids.get("email" if channel == "email" else "phone") or []
    return vals[0] if vals else None


def check_draft(store, *, ps_id: str | None, person_id: str, channel: str, subject: str, body: str, digest: str,
                first_touch: bool, sender: dict, profile: str | None = None) -> dict:
    """Digest, restrictions, channel preference, re-asking, privacy and lint. Returns lint result plus errors."""
    ref = ps_id or person_id
    ctx = graph.context(store, ref)
    errors = []
    if ctx["context_digest"] != digest:
        errors.append("stale or missing context: call rel_context again and redraft")
    if store.do_not(person_id) or (ps_id and store.do_not(ps_id)):
        errors.append("a do-not restriction applies to this card")
    pref = (store.profile(person_id)["slots"].get("preferred_channel") or [{}])[0].get("value")
    if pref == "sms" and copy.CALL_ASK.search(body or ""):
        errors.append("they prefer text: never ask them for a call")
    answered = graph._recently_answered(store, {person_id})
    for slot in answered:
        q = store.schema["slots"].get(slot, {}).get("question")
        if q and q.lower().rstrip("?") in (body or "").lower():
            errors.append(f"re-asks {slot}, which they just answered")
    if privacy.violations(f"{subject}\n{body}", store.schema["never_store"]):
        errors.append("contains a never_store category")
    result = copy.lint(channel, body, subject=subject, first_touch=first_touch, sender=sender, settings=store.settings,
                       profile=profile)
    result["errors"] = errors + result["errors"]
    result["ok"] = not result["errors"]
    return result


def preview_sender(store) -> dict:
    """For drafts and previews only. The sender's real identity comes from relsend's root-owned sender.json."""
    return dict(store.settings.get("sender") or {})
