#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'Usage: verify-runtime.sh RUNTIME_DIR'; exit 2; }
cd "$1"
docker compose --env-file .env config --quiet
for attempt in {1..30}; do
  if docker compose --env-file .env exec -T hermes hermes gateway status >/dev/null 2>&1; then
    docker compose --env-file .env exec -T hermes hermes chat --help >/dev/null
    echo 'Gateway responds; live model/channel/profile tests still required.'
    exit 0
  fi
  sleep 2
done
echo 'Gateway did not become ready' >&2
exit 1
