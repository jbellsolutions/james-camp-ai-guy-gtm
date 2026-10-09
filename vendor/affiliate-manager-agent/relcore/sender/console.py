"""relsend owner console (forced-command SSH, user relsend). Resolves unknown outcomes and clears the halt.

    ssh relsend@droplet status | unknown | resolve <row_id> sent|not_sent | clear-halt | contracts
"""
from __future__ import annotations

import argparse
import json
import os

from .. import clock
from ..db import tx
from .worker import Worker


def run(worker: Worker, user: str, line: str) -> str:
    if user not in worker.owners():
        return f"{user} is not an owner in /etc/relcore/owners.json"
    words = line.split() or ["status"]
    con = worker.con
    if words[0] == "status":
        counts = {r["state"]: r["n"] for r in con.execute("SELECT state, COUNT(*) n FROM outbox GROUP BY state")}
        halt = (worker.home / "HALT")
        readers = [r.strip() for r in worker.env.get("RELSEND_INBOX_READERS", "").split(",") if r.strip()]
        return json.dumps({"outbox": counts, "halted": halt.read_text().strip() if halt.exists() else None,
                           "live": {c: worker.live(c) for c in ("email", "sms")},
                           "inbox_readers": readers or "NONE: replies and opt-outs are not being read"}, indent=1)
    if words[0] == "unknown":
        rows = con.execute("SELECT row_id, action_id, n, channel, address, reason, updated_at FROM outbox WHERE state='unknown'")
        return "\n".join(f"{r['row_id']} {r['action_id']} #{r['n']} {r['channel']} {r['address']} {r['reason']}" for r in rows) or "none"
    if words[0] == "resolve" and len(words) == 3 and words[2] in ("sent", "not_sent"):
        row = con.execute("SELECT * FROM outbox WHERE row_id=? AND state='unknown'", (int(words[1]),)).fetchone()
        if not row:
            return "no unknown row with that id"
        with tx(con):
            if words[2] == "sent":  # it went out: count it, so it is never sent again
                con.execute("INSERT INTO touches (person_key, address, channel, at, row_id, source) VALUES (?,?,?,?,?,?)",
                            (row["person_id"] or row["address"], row["address"], row["channel"], clock.iso(), row["row_id"], "owner"))
                if row["first_touch"]:
                    for key in (f"person:{row['person_id']}", f"address:{row['address']}"):
                        con.execute("INSERT OR IGNORE INTO first_touch VALUES (?,?,?)", (key, row["row_id"], clock.iso()))
            worker._audit("unknown_resolved", str(row["row_id"]), {"as": words[2]}, actor=user)
        worker._result(dict(row), "sent" if words[2] == "sent" else "failed", f"owner resolved as {words[2]}")
        return f"row {row['row_id']} resolved as {words[2]} (it stays unknown in the outbox and is never re-sent)"
    if words[0] == "clear-halt":
        left = con.execute("SELECT COUNT(*) FROM outbox WHERE state='unknown' AND row_id NOT IN "
                           "(SELECT CAST(ref AS INTEGER) FROM audit WHERE action='unknown_resolved')").fetchone()[0]
        if left:
            return f"{left} unknown row(s) still unresolved"
        (worker.home / "HALT").unlink(missing_ok=True)
        with tx(con):
            worker._audit("halt_cleared", None, {}, actor=user)
        return "halt cleared"
    if words[0] == "contracts":
        rows = con.execute("SELECT channel, kind, ok, at FROM contract_runs ORDER BY id")
        return "\n".join(f"{r['channel']} {r['kind']} {'ok' if r['ok'] else 'FAIL'} {r['at']}" for r in rows) or "none yet"
    return "commands: status | unknown | resolve <row_id> sent|not_sent | clear-halt | contracts"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relsend-console")
    ap.add_argument("--user", required=True)
    ap.add_argument("line", nargs="*")
    a = ap.parse_args(argv)
    print(run(Worker(), a.user, os.environ.get("SSH_ORIGINAL_COMMAND") or " ".join(a.line)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
