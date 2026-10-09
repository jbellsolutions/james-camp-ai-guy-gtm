"""A process-wide write lock (fcntl), so two writers never interleave a card render."""
from __future__ import annotations

import contextlib
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows plugin users: SQLite's own lock still serializes the index
    fcntl = None


@contextlib.contextmanager
def held(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)
