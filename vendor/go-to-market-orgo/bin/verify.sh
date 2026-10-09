#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${1:-}" = "--static" ]; then
  cd "$BASE_DIR"
  bash -n new-agent.sh provision-vps.sh bin/*.sh orgo/*.sh
  python3 -m compileall -q services plugins scripts sync
  python3 - <<'PY'
import json
from pathlib import Path
for path in Path(".").rglob("*.json"):
    if ".git" not in path.parts:
        json.loads(path.read_text())
PY
  grep -q 'nousresearch/hermes-agent:v2026.9.11@sha256:9469b3e78b9545b6d576eb8887a95352e9a0ea83730eaf31431cf862ca1010e1' compose.yml
  if awk '/^  hermes:/{inside=1} /^  sync:/{inside=0} inside && /entrypoint:|init: true/{bad=1} END{exit bad?0:1}' compose.yml; then
    echo "Hermes entrypoint override detected." >&2
    exit 1
  fi
  grep -q '"persistent_activation_requires_human_approval": true' policies/agent-factory.json
  grep -q '^LATITUDE_CAPTURE_MODE=metadata$' agent.example.env
  grep -q '^ENABLE_AGENT_BUNDLE=false$' agent.example.env
  grep -Fq '${HERMES_MEM_LIMIT:-3g}' compose.yml
  grep -q '^HERMES_MEM_LIMIT=3g$' agent.example.env
  grep -q 'install_watchdog_schedule' new-agent.sh
  grep -q 'ensure_small_host_swap' provision-vps.sh
  echo "Static verification passed."
  exit 0
fi

cd "$BASE_DIR"
[ -f .env ] || { echo "Private .env is missing." >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a

if [ "${A2A_BIND_ADDRESS:-127.0.0.1}" != 127.0.0.1 ] || [ "${A2A_HOST:-127.0.0.1}" != 127.0.0.1 ]; then
  [ -n "${A2A_PEER_TOKENS:-${A2A_BEARER_TOKEN:-}}" ] || {
    echo "Remote A2A requires a bearer token." >&2
    exit 1
  }
  [ -n "${A2A_TRUSTED_PEERS:-}" ] || {
    echo "Remote A2A requires a trusted-peer list." >&2
    exit 1
  }
fi
[ "${ENABLE_AGENT_BUNDLE:-false}" = false ] || {
  echo "Agent Bundle must remain disabled for this role." >&2
  exit 1
}

command -v crontab >/dev/null 2>&1 || {
  echo "The automatic recovery scheduler is missing." >&2
  exit 1
}
crontab -l 2>/dev/null | grep -Fq "$BASE_DIR/bin/watchdog.sh" || {
  echo "The automatic recovery check is not scheduled." >&2
  exit 1
}

docker compose --env-file .env config --quiet
image="$(docker compose --env-file .env config --images | head -1)"
case "$image" in
  *sha256:9469b3e78b9545b6d576eb8887a95352e9a0ea83730eaf31431cf862ca1010e1) ;;
  *) echo "Running definition does not use the reviewed Hermes image." >&2; exit 1 ;;
esac

for _ in {1..45}; do
  health="$(docker inspect "${AGENT_NAME}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  [ "$health" = healthy ] && break
  [ "$health" = unhealthy ] && { echo "Hermes container is unhealthy." >&2; exit 1; }
  sleep 2
done
[ "${health:-}" = healthy ] || { echo "Hermes did not become healthy." >&2; exit 1; }

h() { docker compose --env-file .env exec -T hermes hermes "$@"; }
[ "$(h config get gateway.platforms.a2a.enabled | tr -d '[:space:]')" = true ]
[ "$(h config get approvals.mode | tr -d '[:space:]')" = manual ]
[ "$(h config get mcp_servers.agent-factory.enabled | tr -d '[:space:]')" = true ]
h plugins list >/dev/null
echo "Runtime verification passed. Optional unconnected services are not treated as failures."
