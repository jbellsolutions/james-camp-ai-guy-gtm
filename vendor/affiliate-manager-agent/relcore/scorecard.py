"""The relationship scorecard (spec 12). Every number states its definition and window. Production comes from the
system of record (imported facts), never from message volume; lift is measured against each wave's holdout.

    python3 -m relcore scorecard [--days 30]      prints JSON and writes Reports/Relationship scorecard <date>.md
"""
from __future__ import annotations

import json
import statistics
from datetime import timedelta

from . import clock, intents, lifecycle

POSITIVE = {"accept", "accept_with_time", "has_opportunity", "wants_help", "question", "commission_question"}


def _slot(store, eid, name):
    v = store.profile(eid)["slots"].get(name)
    return v[0]["value"] if v else None


def _rate(n, d):
    return round(100 * n / d, 1) if d else None


def reachable(store) -> list[str]:
    """Partnerships with at least one outside contact who has a consent basis on some channel and no restriction."""
    out = []
    for ps in store.all_ids("partnership"):
        if store.do_not(ps):
            continue
        for link in store.profile(ps)["links"].get("contact_for<", []):
            if store.entity(link["id"])["internal"] or store.do_not(link["id"]):
                continue
            if store.profile(link["id"])["consent"]:
                out.append(ps)
                break
    return out


def waves(store, since: str) -> list[dict]:
    rows = store.con.execute("SELECT * FROM actions WHERE kind='wave' AND prepared_at >= ? ORDER BY prepared_at", (since,)).fetchall()
    out = []
    for a in rows:
        msgs = store.con.execute("SELECT * FROM action_messages WHERE action_id=?", (a["action_id"],)).fetchall()
        sent = [m for m in msgs if m["state"] == "sent"]
        held = [r["entity_id"] for r in store.con.execute("SELECT entity_id FROM holdout WHERE wave=?", (a["action_id"],))]
        start = clock.day(a["prepared_at"])

        def converted(ps):
            last = _slot(store, ps, "last_conversion")
            return bool(last and last >= start)
        contacted = [m["partnership_id"] for m in sent if m["partnership_id"]]
        c_rate, h_rate = _rate(sum(map(converted, contacted)), len(contacted)), _rate(sum(map(converted, held)), len(held))
        people = [m["entity_id"] for m in sent]
        replies = store.con.execute(
            f"SELECT entity_id, intent FROM inbound WHERE entity_id IN ({','.join('?' * len(people))}) AND at >= ?",
            (*people, a["prepared_at"])).fetchall() if people else []
        opt = sum(r["intent"] == "opt_out" for r in replies)
        by_arm, by_seg = {}, {}
        for m in sent:
            by_arm[m["arm"] or "-"] = by_arm.get(m["arm"] or "-", 0) + 1
            seg = store.entity(m["partnership_id"])["fields"].get("segment") if m["partnership_id"] else None
            by_seg[seg or "-"] = by_seg.get(seg or "-", 0) + 1
        out.append({
            "wave": a["action_id"], "employee": a["employee"], "prepared": start, "messages": len(msgs), "sent": len(sent),
            "undelivered": sum(m["state"] in ("failed", "skipped", "expired", "unknown") for m in msgs),
            "opt_outs_per_100_sends": _rate(opt, len(sent)),
            "positive_reply_rate": _rate(len({r["entity_id"] for r in replies if r["intent"] in POSITIVE}), len(sent)),
            "by_arm": by_arm, "by_segment": by_seg,
            "lift": {"definition": "share with a conversion in the system of record on or after the wave date, contacted minus held out",
                     "contacted": {"n": len(contacted), "converted_pct": c_rate}, "holdout": {"n": len(held), "converted_pct": h_rate},
                     "lift_points": round(c_rate - h_rate, 1) if c_rate is not None and h_rate is not None else None,
                     "caution": "too few partnerships to read" if min(len(contacted), len(held)) < 20 else None}})
    return out


def response_hours(store, since: str) -> float | None:
    hours = []
    for r in store.con.execute("SELECT i.at AS inbound_at, x.at AS reply_at FROM inbound i JOIN interactions x "
                               "ON x.action_id = i.action_id AND x.entity_id = i.entity_id AND x.direction='out' "
                               "WHERE i.status='replied' AND i.at >= ?", (since,)):
        hours.append((clock.parse(r["reply_at"]) - clock.parse(r["inbound_at"])).total_seconds() / 3600)
    return round(statistics.median(hours), 1) if hours else None


def build(store, days: int = 30) -> dict:
    since = clock.iso(clock.now() - timedelta(days=days))
    stages = lifecycle.compute(store)
    reach = reachable(store)
    inbound = store.con.execute("SELECT intent, status FROM inbound WHERE at >= ?", (since,)).fetchall()
    counted = [r for r in inbound if intents.counts_as_engagement(r["intent"])]
    engaged = store.con.execute("SELECT entity_id, partnership_id, at FROM engagement").fetchall()
    to_conversion = []
    for e in engaged:
        last = _slot(store, e["partnership_id"], "last_conversion") if e["partnership_id"] else None
        if last and last >= clock.day(e["at"]):
            to_conversion.append((clock.parse(last + "T00:00:00Z") - clock.parse(e["at"])).days)
    complete = {}
    for kind in ("person", "partner", "partnership"):
        vals = [store.profile(i)["completeness"] for i in store.all_ids(kind) if not store.entity(i)["internal"]]
        complete[kind] = {"cards": len(vals), "avg_completeness": round(sum(vals) / len(vals)) if vals else None}
    grievances = store.con.execute("SELECT status, COUNT(*) n FROM tasks WHERE kind='grievance' GROUP BY status").fetchall()
    usage = store.con.execute("SELECT COALESCE(SUM(cost), 0) c, COALESCE(SUM(tokens_in + tokens_out), 0) t FROM usage WHERE at >= ?",
                              (since,)).fetchone()
    budget = store.settings.get("ai_budget_month")
    conversions = sum(int(_slot(store, ps, "conversions") or 0) for ps in store.all_ids("partnership"))
    return {
        "window": {"days": days, "since": clock.day(since), "until": clock.day(clock.now())},
        "reachable_consented_partnerships": {"n": len(reach), "definition": "an outside contact with a consent basis on a channel and no do-not restriction; the denominator for every rate"},
        "waves": waves(store, since),
        "replies": {"turns": len(inbound), "counted_as_replies": len(counted),
                    "positive": sum(r["intent"] in POSITIVE for r in inbound),
                    "identity_questions": sum(r["intent"] == "identity_question" for r in inbound),
                    "not_counted": "opt-outs, HELP, wrong numbers, identity questions and not-interested never count",
                    "median_hours_to_our_reply": response_hours(store, since)},
        "funnel": {"engaged": len(engaged), **{s: stages[s] for s in lifecycle.STAGES},
                   "median_days_engaged_to_conversion": statistics.median(to_conversion) if to_conversion else None,
                   "definition": "engaged = first qualifying two-way reply (engagement register); the rest come from the system of record"},
        "production": {"conversions_on_record": conversions, "source": "affiliate platform or CRM import; revenue is reported only when the import carries it"},
        "profiles": complete,
        "calls_held": store.con.execute("SELECT COUNT(*) FROM calls WHERE status != 'unmatched' AND started_at >= ?", (since,)).fetchone()[0],
        "plans_sent": store.con.execute("SELECT COUNT(*) FROM action_messages m JOIN actions a USING (action_id) WHERE a.kind='plan' "
                                        "AND m.state='sent' AND a.prepared_at >= ?", (since,)).fetchone()[0],
        "grievances": {r["status"]: r["n"] for r in grievances},
        "ai_cost": {"spent": round(usage["c"], 2), "tokens": usage["t"], "budget_month": budget},
    }


def markdown(card: dict) -> str:
    w = card["window"]
    lines = ["---", "type: report", "tags:", "  - trp/scorecard", "---", f"# Relationship scorecard {w['until']}", "",
             f"Window: {w['since']} to {w['until']} ({w['days']} days). Production is from the system of record, never message volume.", "",
             f"- Reachable, consented partnerships: {card['reachable_consented_partnerships']['n']}",
             f"- Replies counted: {card['replies']['counted_as_replies']} of {card['replies']['turns']} "
             f"({card['replies']['positive']} positive, {card['replies']['identity_questions']} identity question{'' if card['replies']['identity_questions'] == 1 else 's'})",
             f"- Median hours to our reply: {card['replies']['median_hours_to_our_reply']}",
             f"- Engaged: {card['funnel']['engaged']} · registered {card['funnel']['registered']} · first conversion "
             f"{card['funnel']['first_conversion']} · repeat {card['funnel']['repeat']} · lapsed {card['funnel']['lapsed']}",
             f"- Conversions on record: {card['production']['conversions_on_record']}",
             f"- Calls held: {card['calls_held']} · plans sent: {card['plans_sent']}",
             f"- Grievances: {', '.join(f'{n} {k}' for k, n in card['grievances'].items()) or 'none'}", "", "## Waves"]
    for wv in card["waves"]:
        lift = wv["lift"]
        held = (f"holdout {lift['holdout']['converted_pct']}% of {lift['holdout']['n']}" if lift["holdout"]["n"]
                else "no holdout in this wave")
        lines += [f"- {wv['wave']} ({wv['prepared']}, {wv['employee'] or 'orchestrator'}): sent {wv['sent']}, undelivered {wv['undelivered']}, "
                  f"opt-outs per 100 {wv['opt_outs_per_100_sends']}, positive replies {wv['positive_reply_rate']}%; "
                  f"converted {lift['contacted']['converted_pct']}% of {lift['contacted']['n']} vs {held}"
                  + (f" ({lift['caution']})" if lift["caution"] else "")]
    if not card["waves"]:
        lines.append("- none in this window")
    return "\n".join(lines) + "\n"


def write(store, days: int = 30) -> dict:
    card = build(store, days)
    rel = f"Reports/Relationship scorecard {card['window']['until']}.md"
    store.vault._write(rel, markdown(card))
    card["note"] = rel
    return card


def _t_scorecard(srv, days=30):
    return write(srv.store, days)


def main(argv=None) -> int:
    import argparse
    from . import config
    from .store import Store
    ap = argparse.ArgumentParser(prog="relcore scorecard")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args(argv)
    print(json.dumps(write(Store(config.resolve()), a.days), indent=1, default=str))
    return 0


MCP_TOOLS = [
    {"name": "rel_scorecard", "read": False, "handler": _t_scorecard,
     "description": "The relationship scorecard for a window (default 30 days): reachable consented partnerships, per-wave sends, "
                    "undelivered, opt-outs, positive replies and lift against the holdout, the funnel from engaged to repeat, "
                    "conversions on record, calls held, plans sent, grievances and AI cost. Writes a Reports/ note.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 365}}}},
]
