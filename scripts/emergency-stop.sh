#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'Usage: emergency-stop.sh STATE_ROOT'; exit 2; }
state="$1"
mkdir -p "$state"
touch "$state/EXTERNAL_WRITES_STOPPED"
for install in cold-email conversations; do
  base="$state/$install"
  if [ -d "$base/hermes/data" ]; then touch "$base/hermes/data/EXTERNAL_WRITES_STOPPED"; fi
  if [ -f "$base/compose.yml" ]; then
    (cd "$base" && docker compose --env-file .env stop hermes)
  fi
done
printf '%s\n' 'Local workers stopped. Pause active provider campaigns and GHL workflows, then reconcile receipts before owner-authorized restart.'
