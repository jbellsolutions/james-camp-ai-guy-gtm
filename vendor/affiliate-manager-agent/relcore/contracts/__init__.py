"""Contract scripts: prove a channel works, and prove the agent cannot use it, before it goes live.

  positive (as relsend):  python3 -m relcore.contracts positive <email|sms> --to <owner's own test address> --yes
      sends exactly one message through the live adapter to the owner's own address and records it
  negative (as trp):      python3 -m relcore.contracts negative <email|sms>
      as the agent's user: the approval key, relsend.env and spool/approved must be unreadable or unwritable, and the
      agent's own credentials must fail to send (Composio send slug, GHL conversations endpoint)
  record (as relsend):    python3 -m relcore.contracts record negative <channel> < result.json   (root script pipes it)
  status (as relsend):    python3 -m relcore.contracts status <channel>      exit 0 when both have passed

install/connect-sender.sh --live <channel> refuses until status passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .. import clock, config


def _record(channel: str, kind: str, ok: bool, detail: dict) -> None:
    from ..sender.worker import Worker
    w = Worker()
    from ..db import tx
    with tx(w.con):
        w.con.execute("INSERT INTO contract_runs (channel, kind, ok, at, detail) VALUES (?,?,?,?,?)",
                      (channel, kind, int(ok), clock.iso(), json.dumps(detail, sort_keys=True)))


def positive(channel: str, to: str) -> dict:
    from ..adapters import provider_for
    from ..compose import final_text
    from ..sender.worker import Worker
    w = Worker()
    provider = provider_for(channel, True, w.env, w.con)  # live adapter regardless of RELSEND_LIVE_CHANNELS
    body = "Contract check from True Revenue Partner. If you see this, the channel works. No reply needed."
    row = {"row_id": 0, "channel": channel, "address": to, "subject": "contract check",
           "final_body": final_text(channel, body, w.sender, first_in_thread=True)}
    try:
        res = provider.send(row)
        out = {"ok": True, "provider": getattr(provider, "name", "?"), "provider_msg_id": res.get("provider_msg_id"), "to": to}
    except Exception as err:  # noqa: BLE001 - a contract reports every failure
        out = {"ok": False, "error": str(err), "to": to}
    _record(channel, "positive", out["ok"], out)
    return out


def negative(channel: str, env_file: Path | None = None, network: bool = True) -> dict:
    """Run as trp. Every probe must FAIL for the contract to pass."""
    paths = config.resolve("agent")
    probes = {}

    def must_fail(name, fn):
        try:
            fn()
            probes[name] = "SUCCEEDED (bad)"
        except Exception as err:  # noqa: BLE001
            probes[name] = f"failed as required: {type(err).__name__}"

    must_fail("read approval key", lambda: Path(paths.key_file).read_bytes())
    must_fail("read relsend.env", lambda: Path("/etc/relcore/relsend.env").read_text())
    must_fail("read relapprove.env", lambda: Path("/etc/relcore/relapprove.env").read_text())
    probe = paths.spool / "approved" / f".contract-probe-{os.getpid()}"

    def write_probe():
        with open(probe, "x") as fh:  # never overwrite; remove at once if it was allowed
            fh.write("{}")
        probe.unlink()
    must_fail("write spool/approved", write_probe)
    must_fail("write root owners.json", lambda: Path("/etc/relcore/owners.json").open("a").write(""))
    from ..http import HTTPError, request

    def http_must_fail(name, method, url, **kw):
        def go():
            out = request(method, url, timeout=20, retries=1, **kw)
            if isinstance(out, dict) and (out.get("successful") is False or out.get("error")):
                raise HTTPError(200, json.dumps(out)[:200])
            return out
        must_fail(name, go)

    env = dict(os.environ)
    trp_env = env_file or Path.home() / ".trp" / ".env"
    if not network:
        env = {}
    elif trp_env.exists():
        for line in trp_env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    if channel == "email" and env.get("COMPOSIO_API_KEY"):
        http_must_fail("agent Composio key sends email", "POST", "https://backend.composio.dev/api/v3/tools/execute/GMAIL_SEND_EMAIL",
                       headers={"x-api-key": env["COMPOSIO_API_KEY"]},
                       body={"arguments": {"recipient_email": "contract-probe@example.com", "subject": "probe", "body": "probe"}})
    if channel == "sms" and env.get("RELCORE_GHL_READ_TOKEN"):
        http_must_fail("agent GHL token sends sms", "POST", "https://services.leadconnectorhq.com/conversations/messages",
                       headers={"Authorization": f"Bearer {env['RELCORE_GHL_READ_TOKEN']}", "Version": "2021-04-15"},
                       body={"type": "SMS", "contactId": "contract-probe", "message": "probe"})
    ok = all(v.startswith("failed as required") for v in probes.values())
    return {"ok": ok, "channel": channel, "user": os.environ.get("USER"), "probes": probes, "at": clock.iso()}


def status(channel: str) -> bool:
    from ..sender.worker import Worker
    return Worker().contracts_passed(channel)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relcore.contracts")
    ap.add_argument("kind", choices=["positive", "negative", "record", "status"])
    ap.add_argument("rest", nargs="+")
    ap.add_argument("--to")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    if a.kind == "positive":
        if not a.to or not a.yes:
            raise SystemExit("positive contract sends one real message: pass --to <your own test address> --yes")
        out = positive(a.rest[0], a.to)
    elif a.kind == "negative":
        out = negative(a.rest[0])
    elif a.kind == "record":
        kind, channel = a.rest[0], a.rest[1]
        result = json.loads(sys.stdin.read())
        _record(channel, kind, bool(result.get("ok")), result)
        out = {"recorded": kind, "channel": channel, "ok": bool(result.get("ok"))}
    else:
        ok = status(a.rest[0])
        print(json.dumps({"channel": a.rest[0], "passed": ok}))
        return 0 if ok else 1
    print(json.dumps(out, indent=1))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
