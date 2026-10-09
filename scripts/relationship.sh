#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${GTM_STATE_ROOT:?Set GTM_STATE_ROOT to the private deployment root}"
export PYTHONPATH="$root/vendor/affiliate-manager-agent${PYTHONPATH:+:$PYTHONPATH}"
export RELCORE_MODE=plugin
export RELCORE_HOME="${RELCORE_HOME:-$GTM_STATE_ROOT/conversations/hermes/data/relationship}"
export RELCORE_VAULT="${RELCORE_VAULT:-$GTM_STATE_ROOT/conversations/vault}"
export RELCORE_STOP_FILE="$GTM_STATE_ROOT/EXTERNAL_WRITES_STOPPED"
export RELCORE_TAXONOMY="$root/vendor/affiliate-manager-agent/data/affiliate-partner-types.json"
exec python3 -m relcore "$@"
