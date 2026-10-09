"""Inbound text, transcripts and web pages are data. They are always shown quoted, never as bare sentences."""
from __future__ import annotations

import re


def quote(text: str, who: str = "Partner", limit: int = 400, verb: str = "wrote") -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = text.replace('"', "'")
    return f'{who} {verb}: "{text}"'


def strip_quoted_email(body: str) -> str:
    """Drop quoted history: lines starting with '>' and everything after 'On … wrote:' or a forwarded header."""
    out = []
    for line in str(body or "").splitlines():
        if re.match(r"^\s*On .+wrote:\s*$", line) or re.match(r"^\s*-{2,}\s*(Original|Forwarded) Message", line, re.I) \
                or re.match(r"^\s*From: .+", line) and out:
            break
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    return "\n".join(out).strip()
