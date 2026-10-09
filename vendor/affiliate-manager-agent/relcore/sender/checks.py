"""Checks before every single message. Each returns None (pass) or a reason. Order matters: stops first."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import clock, normalize

US_ZONES = ("America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles")


def stop_reason(paths, send_home) -> str | None:
    """The stop mirror, an unreadable control folder, or relsend's own HALT file all stop the worker."""
    control = paths.control
    try:
        if control is None or not control.is_dir():
            return "control folder missing: treated as stopped"
        if (control / "EXTERNAL_WRITES_STOPPED").exists():
            return "kill switch is on"
        list(control.iterdir())
    except OSError:
        return "control folder unreadable: treated as stopped"
    if (send_home / "HALT").exists():
        return "relsend is halted (an unknown outcome needs the owner)"
    return None


def _within(now_utc: datetime, tz: str, start: str, end: str) -> bool:
    local = now_utc.astimezone(ZoneInfo(tz))
    hm = local.strftime("%H:%M")
    return start <= hm < end


def window_reason(row: dict, cfg: dict, now: datetime | None = None) -> str | None:
    """SMS: the time zone comes from the number itself (never from the bundle). Unknown: every US zone must be inside."""
    now = now or clock.now()
    win = cfg["windows"][row["channel"]] if row["channel"] in cfg["windows"] else None
    if not win:
        return None
    if row["channel"] == "sms":
        tz, _ = normalize.tz_from_phone(row["address"])
    else:
        tz = row.get("timezone")
    zones = [tz] if tz else list(US_ZONES)
    for z in zones:
        if not _within(now, z, win["start"], win["end"]):
            return f"outside the {row['channel']} window ({win['start']} to {win['end']} {z})"
    return None


def responsive(con, row: dict, person_key: str) -> bool:
    """A reply that answers the partner's latest message, which they wrote after our last message to them. The caps are
    for what we start: a partner who just wrote gets one answer without waiting a day. The answer still counts as a
    touch, so the caps on everything we start next include it, and a second answer to the same message is capped."""
    if not row.get("reply_to"):
        return False
    latest = con.execute("SELECT msg_id, at FROM latest_inbound WHERE address=?", (row["address"],)).fetchone()
    if not latest or latest["msg_id"] != row["reply_to"]:
        return False
    last = con.execute("SELECT MAX(at) FROM touches WHERE person_key=? OR address=?", (person_key, row["address"])).fetchone()[0]
    return not last or latest["at"] > last


def caps_reason(con, person_key: str, address: str, cfg: dict, now: datetime | None = None, row: dict | None = None) -> str | None:
    now = now or clock.now()
    if row and cfg["caps"].get("replies_exempt", True) and responsive(con, row, person_key):
        return None
    day, week = clock.iso(now - timedelta(days=1)), clock.iso(now - timedelta(days=7))
    q = "SELECT COUNT(*) FROM touches WHERE (person_key=? OR address=?) AND at >= ?"
    if con.execute(q, (person_key, address, day)).fetchone()[0] >= cfg["caps"]["per_day"]:
        return f"frequency cap: {cfg['caps']['per_day']} a day"
    if con.execute(q, (person_key, address, week)).fetchone()[0] >= cfg["caps"]["per_week"]:
        return f"frequency cap: {cfg['caps']['per_week']} a week"
    return None


def suppression_reason(con, row: dict) -> str | None:
    for typ, value in (("entity", row.get("person_id")), ("address", row["address"])):
        if not value:
            continue
        hit = con.execute("SELECT reason FROM suppression WHERE type=? AND value=? AND channel IN ('*', ?)",
                          (typ, value, row["channel"])).fetchone()
        if hit:
            return f"do not contact: {hit['reason']}"
    if con.execute("SELECT 1 FROM withdrawn WHERE action_id=?", (row["action_id"],)).fetchone():
        return "action withdrawn"
    return None


def first_touch_reason(con, row: dict) -> str | None:
    if not row["first_touch"]:
        return None
    for key in (f"person:{row.get('person_id')}", f"address:{row['address']}"):
        if con.execute("SELECT 1 FROM first_touch WHERE key=?", (key,)).fetchone():
            return "a first touch already went to this person or address"
    return None


def stale_reason(con, row: dict, prepared_at: str | None) -> str | None:
    """A reply is stale if the partner wrote again after it was prepared."""
    if not row.get("reply_to"):
        return None
    latest = con.execute("SELECT msg_id, at FROM latest_inbound WHERE address=?", (row["address"],)).fetchone()
    if latest and latest["msg_id"] != row["reply_to"] and prepared_at and latest["at"] > prepared_at:
        return "stale: a newer message arrived after this reply was prepared"
    return None


def consent_reason(row: dict, cfg: dict) -> str | None:
    allowed = cfg.get("consent_required", {}).get(row["channel"], [])
    if row.get("consent_basis") not in allowed:
        return f"no {row['channel']} consent basis on file"
    return None
