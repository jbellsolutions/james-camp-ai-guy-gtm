"""SQLite helpers. One writer per file: rel.sqlite3 (trp), approvals.sqlite3 (relapprove), sends.sqlite3 (relsend)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def connect(path: Path, schema: str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    old = os.umask(0o077)
    try:
        con = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    finally:
        os.umask(old)
    if fresh:
        os.chmod(path, 0o600)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(schema)
    return con


class tx:
    """BEGIN IMMEDIATE ... COMMIT; rolls back on error. Re-entrant (inner blocks join the outer one)."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.outer = False

    def __enter__(self):
        if not self.con.in_transaction:
            self.con.execute("BEGIN IMMEDIATE")
            self.outer = True
        return self.con

    def __exit__(self, exc_type, *_):
        if self.outer:
            self.con.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def append_only(table: str) -> str:
    return (f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;\n"
            f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;\n")


def fts5_available() -> bool:
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.OperationalError:
        return False
