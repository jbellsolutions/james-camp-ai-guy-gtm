"""Partner types: type id -> name, family, owning family profile, and the dossier note in the vault.

The map is RELCORE_TAXONOMY when set, else data/revenue-partnerships.json in the repo (TRP's 339 types), else a small
generic map in defaults/. Dossier notes come from knowledge/30-Families when that folder exists; without it a type has
no dossier, and the owning profile comes from profiles/families when that folder exists, else "default"."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from .config import DEFAULTS, REPO


def _map_path() -> Path:
    if os.environ.get("RELCORE_TAXONOMY"):
        return Path(os.environ["RELCORE_TAXONOMY"])
    own = REPO / "data" / "revenue-partnerships.json"
    return own if own.exists() else DEFAULTS / "taxonomy-generic.json"


def _dirs(path: Path) -> list:
    return [p for p in path.iterdir() if p.is_dir()] if path.is_dir() else []


@lru_cache(maxsize=1)
def index() -> dict:
    data = json.loads(_map_path().read_text())
    fam_dirs = {p.name.split("-", 1)[0]: p for p in _dirs(REPO / "knowledge" / "30-Families")}
    profiles = {p.name.split("-")[1].upper(): p.name for p in _dirs(REPO / "profiles" / "families") if "-" in p.name}
    out = {}
    for fam in data["families"]:
        fnum = int(fam["id"][1:])
        fdir = fam_dirs.get(f"F{fnum:02d}")
        profile = profiles.get(f"F{fnum:02d}", "default")
        for sub in fam["subcategories"]:
            sdir = next((p for p in _dirs(fdir) if p.name.startswith(sub["id"] + "-")), None) if fdir else None
            for t in sub["types"]:
                note = next((p for p in sdir.glob(t["id"] + "-*.md")), None) if sdir else None
                out[t["id"]] = {
                    "id": t["id"], "name": t["name"], "what": t.get("what", ""), "family": fam["id"],
                    "family_name": fam["name"], "worker": fam.get("worker", ""), "subcategory": sub["id"],
                    "subcategory_name": sub["name"], "profile": profile,
                    "note": str(note.relative_to(REPO / "knowledge"))[:-3] if note else None,
                }
    return out


def get(type_id: str) -> dict:
    try:
        return index()[type_id]
    except KeyError:
        raise KeyError(f"unknown partner type {type_id}") from None


def link(type_id: str) -> str:
    t = get(type_id)
    return f"[[{t['note']}|{t['id']} {t['name']}]]" if t["note"] else f"{t['id']} {t['name']}"


def family_profile(family_id: str) -> str:
    for t in index().values():
        if t["family"] == family_id:
            return t["profile"]
    return "default"


def dossier(type_id: str, vault: Path | None = None, limit: int = 1200) -> dict:
    """Why they say yes, objections and the first-touch hook from the type's dossier note (vault copy preferred)."""
    t = get(type_id)
    if not t["note"]:
        return {}
    path = (vault / (t["note"] + ".md")) if vault and (vault / (t["note"] + ".md")).exists() \
        else REPO / "knowledge" / (t["note"] + ".md")
    if not path.exists():
        return {}
    text = path.read_text()

    def section(title):
        m = re.search(rf"(?ms)^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text)
        return m.group(1).strip() if m else ""

    first = section("First touch")
    hook = re.search(r"(?m)^Hi \{name\}, (.+?)(?:\n|$)", first)
    return {
        "why_yes": section("Why they say yes")[:400],
        "fit_signals": section("Fit signals")[:400],
        "disqualifiers": section("Disqualifiers")[:300],
        "objections": section("Objections")[:limit // 2],
        "type_hook": (hook.group(1).split(". ")[0] + ".") if hook else "",
    }
