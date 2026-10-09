#!/usr/bin/env python3
"""Install versioned agent assets without overwriting local customizations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def files(root: Path) -> Iterable[Path]:
    return sorted(item for item in root.rglob("*") if item.is_file() and "__pycache__" not in item.parts)


def install_file(source: Path, target: Path, prior: dict[str, str], current: dict[str, str]) -> str:
    key = str(target)
    source_hash = digest(source)
    previous_hash = prior.get(key)
    if not target.exists() or (previous_hash and digest(target) == previous_hash):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        current[key] = source_hash
        return "installed"
    current[key] = previous_hash or digest(target)
    return "preserved"


def install_tree(source: Path, target: Path, prior: dict[str, str], current: dict[str, str]) -> tuple[int, int]:
    installed = preserved = 0
    for item in files(source):
        result = install_file(item, target / item.relative_to(source), prior, current)
        installed += result == "installed"
        preserved += result == "preserved"
    return installed, preserved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    home = args.home.resolve()
    managed = home / "managed"
    manifest_path = managed / "installed-manifest.json"
    prior = load_manifest(manifest_path)
    current: dict[str, str] = {}
    installed = preserved = 0

    soul = home / "SOUL.md"
    if soul.exists() and str(soul) not in prior:
        backup = home / "SOUL.md.before-ai-guy-template"
        if not backup.exists():
            shutil.copy2(soul, backup)

    single_files = [
        (root / "profiles/default/SOUL.md", soul),
        (root / "policies/agent-factory.json", managed / "policies/agent-factory.json"),
    ]
    for source, target in single_files:
        result = install_file(source, target, prior, current)
        installed += result == "installed"
        preserved += result == "preserved"

    trees = [
        (root / "skills", home / "skills/ai-guy"),
        (root / "plugins/latitude-observer", home / "plugins/latitude-observer"),
        (root / "agent-templates", managed / "agent-templates"),
        (root / "services", managed / "services"),
        (root / "scripts", managed / "scripts"),
    ]
    for source, target in trees:
        one, two = install_tree(source, target, prior, current)
        installed += one
        preserved += two

    managed.mkdir(parents=True, exist_ok=True)
    state = managed / "state"
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    atomic_json(manifest_path, current)
    print(json.dumps({"installed": installed, "preserved_customized": preserved, "home": str(home)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
