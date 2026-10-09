"""The fictional sample program (Harborline Physical Therapy), loaded end to end and checked against a golden vault.

    python3 -m relcore sample --out <dir>      load it into <dir> (home/, vault/) and print the summary
    python3 -m relcore sample --check          rebuild in a temp dir and compare with charter/examples/.../golden
    python3 -m relcore sample --update         rewrite the golden vault and briefs (after an intended change)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from . import config

SAMPLE = config.REPO / "charter" / "examples" / "sample-client" / "relationship"
GOLDEN = SAMPLE / "golden"
NOW = "2026-10-01T15:00:00Z"
SETTINGS = {"client": "Harborline Physical Therapy", "client_slug": "harborline-physical-therapy",
            "category": "post-surgery rehab and sports injury care",
            "sender": {"name": "Sam Rivera", "title": "Owner", "business": "Harborline Physical Therapy",
                       "physical_address": "100 Example Street, Charlotte, NC 28202", "email": "sam@harborlinept.example.com",
                       "phone": "704-555-0100"}}
OWNERS = {"owners": [{"name": "Sam Rivera", "slack_member_id": "U0SAMPLE01", "console_user": "owner"}]}
BRIEFS = {"peak-referral": {"key": "Harborline Physical Therapy|{peak}|F6.B.1"},
          "iron-republic": {"domain": "ironrepublic.example.com"},
          "run-strong-podcast": {"key": "Harborline Physical Therapy|{runstrong}|F5.A.1"},
          "dana-ortiz": {"email": "dana@peakortho.example.com"}}


def build(root: Path) -> dict:
    os.environ.update(RELCORE_MODE="test", RELCORE_ROOT=str(root), RELCORE_NOW=NOW)
    os.environ.pop("RELCORE_EMPLOYEE", None)
    paths = config.resolve("test")
    (paths.home / "config").mkdir(parents=True, exist_ok=True)
    base = json.loads((config.DEFAULTS / "relationship.json").read_text())
    base.update(SETTINGS)
    (paths.home / "config" / "relationship.json").write_text(json.dumps(base, indent=2) + "\n")
    from .cli import init
    from .importers import apply
    from .importers.csv_source import read
    from .store import Store
    init(paths)
    store = Store(paths)
    summary = apply(store, read(SAMPLE, system="ghl"))
    briefs = {}
    from . import graph
    peak = store.resolve({"domain": "peakortho.example.com"})
    runstrong = store.resolve({"domain": "runstrongpod.example.com"})
    for name, ref in BRIEFS.items():
        ref = {k: v.format(peak=peak, runstrong=runstrong) for k, v in ref.items()}
        briefs[name] = graph.context(store, ref)["brief"] + "\n"
    return {"paths": paths, "store": store, "summary": summary, "briefs": briefs}


def snapshot(vault: Path) -> dict:
    return {str(p.relative_to(vault)): p.read_text() for p in sorted(vault.rglob("*.md"))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relcore sample")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="relcore-sample-"))
    built = build(root)
    vault = built["paths"].vault
    if a.update:
        if GOLDEN.exists():
            shutil.rmtree(GOLDEN)
        shutil.copytree(vault, GOLDEN / "vault")
        (GOLDEN / "briefs").mkdir(parents=True)
        for name, text in built["briefs"].items():
            (GOLDEN / "briefs" / f"{name}.md").write_text(text)
        (GOLDEN / "summary.json").write_text(json.dumps(built["summary"], indent=1, sort_keys=True) + "\n")
        print(f"golden updated: {len(snapshot(vault))} cards")
        return 0
    if a.check:
        want, got = snapshot(GOLDEN / "vault"), snapshot(vault)
        diffs = sorted(set(want) ^ set(got)) + sorted(k for k in set(want) & set(got) if want[k] != got[k])
        for name, text in built["briefs"].items():
            gold = GOLDEN / "briefs" / f"{name}.md"
            if not gold.exists() or gold.read_text() != text:
                diffs.append(f"briefs/{name}.md")
        if diffs:
            print("sample differs from golden (run: python3 -m relcore sample --update after an intended change):")
            for d in diffs[:20]:
                print("  ", d)
            return 1
        print(f"sample matches golden: {len(got)} cards, {len(built['briefs'])} briefs")
        return 0
    print(json.dumps({"root": str(root), **built["summary"]}, indent=1))
    return 0
