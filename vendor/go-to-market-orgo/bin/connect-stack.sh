#!/usr/bin/env bash
# Connect Honcho memory and Latitude observability without printing credentials.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"
ENV_FILE="$BASE_DIR/.env"
DC=(docker compose --env-file .env)

secret() { local value; read -r -s -p "$1: " value; printf '\n' >&2; printf '%s' "$value"; }
value() { awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"; }
upsert() {
  local key=$1 replacement=$2 temp
  temp="$(mktemp "$BASE_DIR/.env.stack.XXXXXX")"
  awk -v key="$key" 'index($0, key "=") != 1 {print}' "$ENV_FILE" > "$temp"
  printf '%s=%s\n' "$key" "$replacement" >> "$temp"
  chmod 600 "$temp"
  mv "$temp" "$ENV_FILE"
}
h() { "${DC[@]}" exec -T hermes hermes "$@"; }

status() {
  echo "Managed stack status"
  h config get memory.provider 2>/dev/null | sed 's/^/  Memory provider: /' || echo "  Memory provider: local"
  if [ -n "$(value HONCHO_API_KEY)" ]; then echo "  Honcho credential: present"; else echo "  Honcho credential: not connected"; fi
  if [ -n "$(value LATITUDE_API_KEY)" ] && [ -n "$(value LATITUDE_PROJECT_SLUG)" ]; then
    echo "  Latitude observer: configured"
  else
    echo "  Latitude observer: not connected"
  fi
  echo "  Agent Bundle: intentionally disabled for this role"
}

connect_honcho() {
  local key
  key="$(value HONCHO_API_KEY)"
  [ -n "$key" ] || key="$(secret "Paste the Honcho API key")"
  [ -n "$key" ] || { echo "Honcho key cannot be blank." >&2; return 1; }
  upsert HONCHO_API_KEY "$key"
  unset key
  "${DC[@]}" up -d --force-recreate hermes >/dev/null
  h config set memory.provider honcho >/dev/null
  h honcho sync
}

connect_latitude() {
  local key project mode
  key="$(value LATITUDE_API_KEY)"
  project="$(value LATITUDE_PROJECT_SLUG)"
  [ -n "$key" ] || key="$(secret "Paste the Latitude project API key")"
  [ -n "$project" ] || read -r -p "Latitude project slug: " project
  [ -n "$key" ] && [[ "$project" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || {
    echo "Latitude key or project slug is missing." >&2
    return 1
  }
  read -r -p "Capture metadata only (recommended) or sanitized text? [metadata/sanitized]: " mode
  case "${mode:-metadata}" in metadata|sanitized) ;; *) echo "Choose metadata or sanitized." >&2; return 1 ;; esac
  upsert LATITUDE_API_KEY "$key"
  upsert LATITUDE_PROJECT_SLUG "$project"
  upsert LATITUDE_CAPTURE_MODE "${mode:-metadata}"
  unset key
  "${DC[@]}" up -d --force-recreate hermes >/dev/null
  h plugins enable latitude-observer >/dev/null
  echo "Latitude tracing is connected. Workspace-management tools remain disabled until separately approved."
}

case "${1:-}" in
  --honcho) connect_honcho ;;
  --latitude) connect_latitude ;;
  --all) connect_honcho; connect_latitude ;;
  --status) status; exit 0 ;;
  "")
    echo "Connect the managed agent stack"
    echo "  1. Honcho memory"
    echo "  2. Latitude observability"
    echo "  3. Both"
    echo "  4. Show status"
    read -r -p "Choose 1, 2, 3, or 4: " choice
    case "$choice" in
      1) connect_honcho ;;
      2) connect_latitude ;;
      3) connect_honcho; connect_latitude ;;
      4) status; exit 0 ;;
      *) echo "Choose 1, 2, 3, or 4." >&2; exit 1 ;;
    esac
    ;;
  *) echo "Use --honcho, --latitude, --all, or --status." >&2; exit 1 ;;
esac

"${DC[@]}" restart hermes >/dev/null
"$BASE_DIR/bin/verify.sh" --allow-unconnected
status
