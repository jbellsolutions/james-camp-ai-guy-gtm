"""Mock provider with fault injection (tests and the simulation).

faults: list consumed one per send: "ok", "timeout_after_accept", "429", "500_before", "reject", "drop_after_accept"."""
from __future__ import annotations

from . import SendError


class MockProvider:
    name = "mock"
    _shared = None

    def __init__(self):
        self.faults: list[str] = []
        self.sent: list[dict] = []   # what the "provider" actually accepted
        self.calls = 0

    @classmethod
    def shared(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def send(self, row: dict) -> dict:
        self.calls += 1
        fault = self.faults.pop(0) if self.faults else "ok"
        if fault == "429":
            raise SendError("429 rate limited", retry=True)
        if fault == "500_before":
            raise SendError("500 before accept", retry=True)
        if fault == "reject":
            raise SendError("400 invalid recipient")
        self.sent.append(dict(row))
        if fault in ("timeout_after_accept", "drop_after_accept"):
            raise SendError("timeout after the request went out", accepted_maybe=True)
        return {"provider_msg_id": f"mock-{len(self.sent)}"}
