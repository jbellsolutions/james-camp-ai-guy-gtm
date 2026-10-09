#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "${1:-}" = "--static" ]; then
  exec "$REPO_DIR/bin/verify.sh" --static
fi
descriptor="$HOME/.config/ai-guy-agent/go-to-market.json"
[ -f "$descriptor" ] || { echo "Go-to-market deployment descriptor is missing." >&2; exit 1; }
deployment="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["deployment_dir"])' "$descriptor")"
exec "$deployment/bin/verify.sh" "${1:-}"
