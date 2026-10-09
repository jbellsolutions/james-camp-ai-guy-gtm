"""Dry provider: the default until a channel's contract script passes. Records what would have gone out."""
from __future__ import annotations

from .. import clock


class DryProvider:
    name = "dry"

    def __init__(self, con=None):
        self.con = con

    def send(self, row: dict) -> dict:
        if self.con is not None:
            self.con.execute("INSERT OR REPLACE INTO dry_sends VALUES (?,?,?,?,?)",
                             (row["row_id"], clock.iso(), row["channel"], row["address"], row["final_body"]))
        return {"provider_msg_id": f"dry-{row['row_id']}"}
