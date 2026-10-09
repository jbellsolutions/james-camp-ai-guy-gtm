"""Forget a person (owner CLI only; never an MCP tool).

    python3 -m relcore purge <email | phone | pe_id> [--yes]

Removes the person's card, manager note and calls, every index row about them (identities, facts, edges,
interactions, loops, tasks, holds, consent, inbound, the timeline, their engagement row) and their unmatched
files. The suppression stays: it holds only the address and the reason, and it is what keeps them from being
contacted again. The audit log records that a purge happened, not what was removed. The cards that linked to
them are rendered again without them. Without --yes it only lists what it would remove.
"""
from __future__ import annotations

import json

from . import clock
from .db import append_only, tx

TABLES = (("identities", "entity_id"), ("facts", "entity_id"), ("interactions", "entity_id"), ("open_loops", "entity_id"),
          ("tasks", "entity_id"), ("holds", "entity_id"), ("consent", "entity_id"), ("inbound", "entity_id"),
          ("reservations", "entity_id"), ("drafts", "entity_id"), ("applied_refs", "entity_id"), ("refused", "entity_id"),
          ("processed_inbound", "entity_id"), ("arms", "entity_id"), ("search", "entity_id"))


def plan(store, ref) -> dict:
    pid = store.resolve(ref)
    if not pid or store.entity(pid)["kind"] != "person":
        raise LookupError(f"no person card for {ref}")
    con = store.con
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t} WHERE {c}=?", (pid,)).fetchone()[0] for t, c in TABLES}
    counts["edges"] = con.execute("SELECT COUNT(*) FROM edges WHERE src=? OR dst=?", (pid, pid)).fetchone()[0]
    counts["timeline"] = con.execute("SELECT COUNT(*) FROM timeline WHERE entity_id=?", (pid,)).fetchone()[0]
    counts["engagement"] = con.execute("SELECT COUNT(*) FROM engagement WHERE entity_id=?", (pid,)).fetchone()[0]
    calls = [r["note_path"] for r in con.execute("SELECT note_path FROM calls WHERE person_id=?", (pid,)) if r["note_path"]]
    ent = store.entity(pid)
    return {"person": pid, "display": ent["display"], "note": ent["note_path"], "calls": calls, "rows": counts,
            "kept": "suppression rows (address and reason only) and the audit log"}


def run(store, ref, *, yes: bool = False) -> dict:
    p = plan(store, ref)
    if not yes:
        return {**p, "done": False, "note": "nothing removed; run again with --yes"}
    pid, con = p["person"], store.con
    neighbours = {e["other"] for e in store.edges(pid) if e["other"].startswith(("pe_", "pt_", "ps_"))}
    addresses = [r["value_norm"] for r in con.execute("SELECT value_norm FROM identities WHERE entity_id=?", (pid,))]
    with tx(con):
        for t, c in TABLES:
            con.execute(f"DELETE FROM {t} WHERE {c}=?", (pid,))
        con.execute("DELETE FROM edges WHERE src=? OR dst=?", (pid, pid))
        con.execute("UPDATE calls SET person_id=NULL, transcript='[]' WHERE person_id=?", (pid,))
        for table in ("timeline", "engagement"):  # append-only everywhere else; the owner's purge is the one exception
            con.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
            con.execute(f"DELETE FROM {table} WHERE entity_id=?", (pid,))
        con.execute("DELETE FROM entities WHERE id=?", (pid,))
        store._audit("purged", None, {"at": clock.iso(), "rows": sum(p["rows"].values())}, actor="owner")
    con.executescript(append_only("timeline") + append_only("engagement"))
    vault = store.paths.vault
    for rel in [p["note"], f"People/_manager/{pid}.md", *p["calls"]]:
        if rel and (vault / rel).exists():
            (vault / rel).unlink()
    unmatched = store.paths.home / "unmatched"
    if unmatched.exists():
        for f in unmatched.glob("*.json"):
            try:
                text = f.read_text()
            except OSError:
                continue
            if any(a and a in text for a in addresses):
                f.unlink()
    if store.render_enabled and neighbours:
        store.vault.render_around({n for n in neighbours if store.entity(n)})
    return {**p, "done": True}


def main(argv) -> int:
    import argparse
    from . import config
    from .cli import _ref
    from .store import Store
    ap = argparse.ArgumentParser(prog="relcore purge")
    ap.add_argument("ref")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(run(Store(config.resolve()), _ref(a.ref), yes=a.yes), indent=1))
    return 0
