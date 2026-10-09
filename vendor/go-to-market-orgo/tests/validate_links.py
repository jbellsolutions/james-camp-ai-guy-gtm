#!/usr/bin/env python3
from pathlib import Path
import re
import sys


root = Path(__file__).resolve().parents[1]
failed = []
pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
for document in root.rglob("*.md"):
    if ".git" in document.parts:
        continue
    for target in pattern.findall(document.read_text()):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (document.parent / target).resolve().exists():
            failed.append(f"{document.relative_to(root)} -> {target}")
if failed:
    print("\n".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("Documentation links passed.")
