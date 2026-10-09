#!/usr/bin/env bash
# Install the bundled GHL CLI/MCP inside the selected conversation container.
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'Usage: connect-ghl.sh STATE_ROOT'; exit 2; }
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state="$1"; base="$state/conversations"; tools="$base/hermes/data/tools/gohighlevel"
[ "$(uname -s)" = Linux ] || { echo 'Run on the selected Linux target'; exit 1; }
[ ! -e "$tools" ] || { echo 'GHL tools already present; inspect/upgrade in place, preserving state.'; exit 1; }
mkdir -p "$(dirname "$tools")"
cp -R "$root/vendor/gohighlevel-agency-cli" "$tools"
cd "$base"
docker compose --env-file .env exec -T --user 0 hermes sh -c 'chown -R "${HERMES_UID:-1000}:${HERMES_GID:-1000}" /opt/data/tools/gohighlevel'
docker compose --env-file .env exec -T hermes python3 -m venv /opt/data/tools/gohighlevel/.venv
docker compose --env-file .env exec -T hermes /opt/data/tools/gohighlevel/.venv/bin/pip install -e /opt/data/tools/gohighlevel python-dotenv mcp
python3 - "$base/hermes/data" <<'PY'
import json,sys
from pathlib import Path
home=Path(sys.argv[1])
for directory in [home]+[p for p in (home/'profiles').iterdir() if p.name in ['crm-agent-4','conversion-specialist','conversion-manager','affiliate-manager']]:
 path=directory/'config.yaml';config=json.loads(path.read_text())
 config.setdefault('mcp_servers',{})['gohighlevel']={'command':'/opt/data/tools/gohighlevel/.venv/bin/python','args':['/opt/data/tools/gohighlevel/ghl_mcp_server.py'],'trust':'untrusted','enabled':True}
 path.write_text(json.dumps(config,indent=2)+'\n');path.chmod(0o600)
PY
docker compose --env-file .env exec -T hermes /opt/data/tools/gohighlevel/.venv/bin/ghl --help >/dev/null
docker compose --env-file .env restart hermes
printf '%s\n' 'GHL CLI/MCP installed. Scoped location, test CRM and consented SMS acceptance still required.'
