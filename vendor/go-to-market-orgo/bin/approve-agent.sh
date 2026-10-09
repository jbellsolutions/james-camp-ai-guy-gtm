#!/usr/bin/env bash
# Private owner gate for a profile proposed by the Agent Factory.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"
proposal="${1:-}"
approved_by="${2:-owner}"
[[ "$proposal" =~ ^ap_[0-9a-f]{12}$ ]] || { echo "Usage: $0 ap_XXXXXXXXXXXX [approver-name]" >&2; exit 1; }
docker compose --env-file .env exec hermes \
  /opt/hermes/.venv/bin/python /opt/data/managed/services/agent_factory.py \
  approve "$proposal" --approved-by "$approved_by"
docker compose --env-file .env exec -T hermes \
  /opt/hermes/.venv/bin/python /opt/data/managed/services/agent_factory.py activate "$proposal"
docker compose --env-file .env restart hermes >/dev/null
echo "The approved worker profile is active and its A2A route is registered."
