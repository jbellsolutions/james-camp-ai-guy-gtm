"""The exact text that goes out. Lint and the sender both call final_text(), so what is checked is what is sent.

The sender's identity, physical address and footer come from the root-owned sender.json (relsend and relapprove
read it); trp's relationship.json is used only for previews and drafts.
"""
from __future__ import annotations

OPT_OUT = "Reply STOP to opt out."
EMAIL_UNSUB = "If you would rather not hear from me, reply unsubscribe and I will not email you again."


def footer(channel: str, sender: dict) -> str:
    if channel != "email":
        return ""
    lines = [sender.get("name") or "", ", ".join(x for x in (sender.get("title"), sender.get("business")) if x),
             sender.get("physical_address") or "", EMAIL_UNSUB]
    return "\n".join(line for line in lines if line)


def final_text(channel: str, body: str, sender: dict, *, first_in_thread: bool) -> str:
    body = (body or "").strip()
    if channel == "sms":
        if not first_in_thread:
            return body
        tail = []
        ident = ", ".join(x for x in ((sender.get("name") or "").split(" ")[0], sender.get("business")) if x)
        if ident and ident.lower() not in body.lower():
            tail.append(ident + ".")
        if OPT_OUT not in body:  # the exact sentence; a different wording still gets the line
            tail.append(OPT_OUT)
        return body + ("\n" + " ".join(tail) if tail else "")
    if channel == "email":
        return body + "\n\n" + footer("email", sender)
    return body
