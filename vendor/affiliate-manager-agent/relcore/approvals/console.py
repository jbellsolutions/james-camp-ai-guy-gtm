"""Owner console over SSH (forced command). The owner's identity comes from the forced command, never from input:

    authorized_keys (user relapprove):
      command="python3 -m relcore.approvals.console --user sam",no-port-forwarding,no-pty ssh-ed25519 AAAA...

Then:  ssh relapprove@droplet list | show ac_x | approve ac_x [except 4, 17] | edit ac_x 9: text | reject ac_x |
       release pe_x identity
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys

from .service import Refused, Service, parse_command


def run(service: Service, user: str, line: str) -> str:
    owner = service.owner_for(console_user=user)
    if not owner:
        return f"{user} is not an owner in /etc/relcore/owners.json"
    service.scan()
    words = shlex.split(line) if line.strip() else ["list"]
    try:
        if words[0] == "list":
            rows = service.pending()
            return "\n".join(f"{r['action_id']}  {r['state']}  {r['shown_at']}" for r in rows) or "nothing waiting"
        if words[0] == "show":
            return service.card_text(words[1])
        if words[0] == "release" and len(words) == 3:
            return json.dumps(service.release_hold(words[1], words[2], approver=owner, via="console"))
        cmd = parse_command(line)
        if not cmd:
            return "commands: list | show <id> | approve <id> [except 4, 17] | edit <id> <n>: <text> | reject <id> | release <entity> <kind>"
        if cmd["verb"] == "edit":
            return json.dumps(service.edit(cmd["action_id"], cmd["n"], cmd["text"], approver=owner))
        out = service.decide(cmd["action_id"], cmd["verb"], approver=owner, via="console", exclusions=cmd.get("exclusions", []))
        return json.dumps(out)
    except (Refused, IndexError, ValueError) as err:
        return f"refused: {err}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="relapprove-console")
    ap.add_argument("--user", required=True, help="set by the forced command in authorized_keys")
    ap.add_argument("line", nargs="*")
    a = ap.parse_args(argv)
    line = os.environ.get("SSH_ORIGINAL_COMMAND") or " ".join(a.line)
    print(run(Service(), a.user, line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
