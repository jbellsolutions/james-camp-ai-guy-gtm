"""relcore owner CLI (runs as the trp user, or as the plugin user under ./trp).

    python3 -m relcore init                 create folders, config and the index; take the client from the charter
    python3 -m relcore status               counts and restrictions
    python3 -m relcore reindex              read owner edits back from the cards, then rewrite every card
    python3 -m relcore doctor               check folders, modes, the write fence and the stop files
    python3 -m relcore card <ref>           print a card's profile (id, email, phone or domain)
    python3 -m relcore context <ref>        print the context brief
    python3 -m relcore sample [--check]     load the fictional sample program (or check it against the golden vault)
    python3 -m relcore import <plan|apply> <source> [options]   bring in contacts (see relcore/importers)
    python3 -m relcore registers freeze <program>   freeze who is eligible before a program's first send
    python3 -m relcore purge <ref> [--yes]  forget a person (the suppression stays so they are never contacted again)
    python3 -m relcore scorecard [--days 30]   the relationship scorecard (also writes a Reports/ note)
    python3 -m relcore sim [--seed N]          the simulation: personas with a hidden truth through the whole loop, in a throwaway root
    python3 -m relcore showcase --out <dir>    the sample program after one full loop, as a vault to open in Obsidian
    python3 -m relcore ingest               read decisions, send results and partner replies from the spool (cron, 5 min)
    python3 -m relcore backup <dir>         consistent copy of rel.sqlite3 (sqlite backup API)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import config


def _store(render: bool = True):
    from .store import Store
    return Store(config.resolve(), render=render)


def init(paths: config.Paths) -> dict:
    for sub in ("", "config", "call-inbox", "unmatched", "backups"):
        d = paths.home / sub
        d.mkdir(parents=True, exist_ok=True)
        if paths.mode == "agent":
            d.chmod(0o700)
    vault_ready = paths.vault.exists() or paths.mode != "agent"  # on the droplet setup seeds the vault first
    if vault_ready:
        for d in ("People", "Partners", "Partnerships", "Employees", "Hubs", "Calls", "Reviews", "Approvals", "Plans"):
            (paths.vault / d).mkdir(parents=True, exist_ok=True)
    own = paths.home / "config" / "relationship.json"
    settings = json.loads(own.read_text()) if own.exists() else json.loads((config.DEFAULTS / "relationship.json").read_text())
    trp_home = os.environ.get("TRP_HOME") or (str(Path.home() / ".hermes" / "trp") if paths.mode == "agent" else "")
    charter = Path(trp_home) / "private-business" / "charter" / "charter.json" if trp_home else None
    if charter and charter.exists():
        client = json.loads(charter.read_text()).get("client", {})
        settings["client"] = client.get("company") or settings.get("client", "")  # the charter is the source of truth
        settings["client_slug"] = client.get("slug") or settings.get("client_slug", "")
        settings["sender"]["name"] = settings["sender"].get("name") or client.get("approver") or client.get("owner", "")
        settings["sender"]["business"] = settings["sender"].get("business") or client.get("company", "")
    own.write_text(json.dumps(settings, indent=2) + "\n")
    store = _store(render=vault_ready)
    if vault_ready:
        fams = config.REPO / "profiles" / "families"
        extra = [p for p in os.environ.get("RELCORE_PROFILES", "").split(",") if p]
        found = sorted(p.name for p in fams.iterdir() if p.is_dir()) if fams.is_dir() else []
        for profile in ["default"] + found + extra:
            store.vault.render_employee(profile)
    return {"home": str(paths.home), "vault": str(paths.vault) if vault_ready else "(not seeded yet; run setup.sh)",
            "client": settings.get("client") or "(set by the charter)"}


def doctor(paths: config.Paths) -> list[tuple[bool, str]]:
    out = []
    out.append((paths.rel_db.exists(), f"index at {paths.rel_db}"))
    if paths.mode == "agent" and paths.home.exists():
        out.append((oct(paths.home.stat().st_mode & 0o777) == "0o700", "relationship folder mode 700"))
    fence = os.environ.get("HERMES_WRITE_SAFE_ROOT", "")
    if fence:
        roots = fence.split(os.pathsep)
        bad = [r for r in roots if Path(r).name in ("People", "Partners", "Partnerships", "Employees", "Hubs") or r == str(paths.vault)]
        out.append((not bad, "agent write fence excludes the card folders"))
    if paths.key_file:
        try:
            paths.key_file.read_bytes()
            out.append((False, "approval key is NOT readable by this user (it must not be)"))
        except (PermissionError, FileNotFoundError):
            out.append((True, "approval key unreadable by this user"))
    if paths.control:
        stop = paths.control / "EXTERNAL_WRITES_STOPPED"
        primary = paths.stop_primary
        if primary and primary.exists():
            out.append((stop.exists(), "stop mirror matches the kill switch"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relcore", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    paths = config.resolve()
    if a.command == "init":
        print(json.dumps(init(paths), indent=1))
    elif a.command == "status":
        from .mcp_server import Server
        print(json.dumps(Server.t_rel_status(_bare(paths)), indent=1))
    elif a.command == "reindex":
        print(json.dumps(_store().vault.reindex()))
    elif a.command == "doctor":
        bad = 0
        for ok, label in doctor(paths):
            print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
            bad += not ok
        return 1 if bad else 0
    elif a.command == "card":
        print(json.dumps(_store(render=False).profile(_ref(a.rest[0])), indent=1, default=str))
    elif a.command == "context":
        from . import graph
        print(graph.context(_store(render=False), _ref(a.rest[0]))["brief"])
    elif a.command == "sample":
        from .sample import main as sample_main
        return sample_main(a.rest)
    elif a.command == "import":
        from .importers import main as import_main
        return import_main(a.rest)
    elif a.command == "registers":
        from .registers import main as reg_main
        return reg_main(a.rest)
    elif a.command == "purge":
        from .purge import main as purge_main
        return purge_main(a.rest)
    elif a.command == "scorecard":
        from .scorecard import main as score_main
        return score_main(a.rest)
    elif a.command == "sim":
        from .sim import main as sim_main  # a throwaway root of its own; never touches this install
        return sim_main(a.rest)
    elif a.command == "showcase":
        from .showcase import main as showcase_main  # builds its own root under --out; never touches this install
        return showcase_main(a.rest)
    elif a.command == "ingest":
        from . import ingest
        print(json.dumps(ingest.run(_store())))  # ingest.run takes the ingest lock itself
    elif a.command == "backup":
        dst = Path(a.rest[0]) / "rel.sqlite3"
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(str(paths.rel_db))
        with sqlite3.connect(str(dst)) as out:
            src.backup(out)
        dst.chmod(0o600)
        print(dst)
    else:
        ap.print_help()
        return 2
    return 0


def _bare(paths):
    class S:  # status without starting a server
        pass
    s = S()
    s.store, s.paths, s.mode = _store(render=False), paths, paths.mode
    s.employee = paths.employee or "owner"
    return s


def _ref(text: str):
    if text.startswith(("pe_", "pt_", "ps_")):
        return {"id": text}
    if "@" in text:
        return {"email": text}
    if any(c.isdigit() for c in text) and len([c for c in text if c.isdigit()]) >= 10:
        return {"phone": text}
    return {"domain": text}
