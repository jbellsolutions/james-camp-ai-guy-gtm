"""Spool files between trp, relapprove and relsend. Each directory has one producer; consumers keep cursors.

  prepared/  trp        bundles waiting for a human
  suppress/  trp        add-only restrictions and withdrawals the sender must honour
  touches/   trp        (reserved) touches recorded outside the sender
  approved/  relapprove signed decisions with the final bundle
  results/   relsend    per-message outcomes
  inbound/   relsend    new partner messages, already floor-checked for opt-outs
  alerts/    relsend    unknown outcomes and halts for the owner

Writes are atomic (dot-prefixed temp file, then rename). Names are built only from relcore ids and checked.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

NAME = re.compile(r"^[a-z]{2,10}[_-][a-z0-9_-]{4,80}\.json$")
MAX_BYTES = 2_000_000


def write(directory: Path, name: str, payload: dict) -> Path:
    if not NAME.match(name):
        raise ValueError(f"bad spool name {name}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    tmp = directory / f".{name}.{os.getpid()}.tmp"
    old = os.umask(0o027)
    try:
        tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False))
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    finally:
        os.umask(old)
    return path


def entries(directory: Path) -> list[Path]:
    if not directory or not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if not p.name.startswith(".") and NAME.match(p.name) and p.is_file())


def read(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"{path.name} is too large")
    return json.loads(path.read_text())
