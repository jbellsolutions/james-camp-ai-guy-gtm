"""One clock for the whole package. RELCORE_NOW (ISO 8601) freezes it for tests and the golden sample."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def now() -> datetime:
    """Wall clock, except in test mode, where RELCORE_NOW freezes it. Approve and send modes refuse to start with
    RELCORE_NOW set (approval expiry and send windows must never run on a fake clock)."""
    fixed = os.environ.get("RELCORE_NOW") if os.environ.get("RELCORE_MODE") == "test" else None
    if fixed:
        return datetime.fromisoformat(fixed.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def day(text_or_dt) -> str:
    dt = parse(text_or_dt) if isinstance(text_or_dt, str) else text_or_dt
    return dt.date().isoformat()


def plus(hours: float = 0, days: float = 0) -> str:
    return iso(now() + timedelta(hours=hours, days=days))


def refuse_fake_clock(role: str) -> None:
    """Approve and send processes call this at start: a frozen clock outside test mode is a misconfiguration."""
    if os.environ.get("RELCORE_NOW") and os.environ.get("RELCORE_MODE") != "test":
        raise SystemExit(f"{role}: refusing to start with RELCORE_NOW set")
