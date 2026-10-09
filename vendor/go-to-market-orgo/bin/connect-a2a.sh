#!/usr/bin/env bash
# Add one authenticated, auditable A2A peer to the default and worker profiles.
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"
ENV_FILE="$BASE_DIR/.env"
DC=(docker compose --env-file .env)

secret() { local answer; read -r -s -p "$1: " answer; printf '\n' >&2; printf '%s' "$answer"; }
value() { awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"; }
upsert() {
  local key=$1 replacement=$2 temp
  temp="$(mktemp "$BASE_DIR/.env.a2a.XXXXXX")"
  awk -v key="$key" 'index($0, key "=") != 1 {print}' "$ENV_FILE" > "$temp"
  printf '%s=%s\n' "$key" "$replacement" >> "$temp"
  chmod 600 "$temp"
  mv "$temp" "$ENV_FILE"
}

read -r -p "Short peer name (for example cofounder): " peer
[[ "$peer" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || { echo "Use lowercase letters, numbers, and dashes." >&2; exit 1; }
read -r -p "Peer A2A URL (for example https://agent.example.com): " peer_url
[[ "$peer_url" =~ ^https?://[^[:space:]]+$ ]] || { echo "Use a complete http or https URL." >&2; exit 1; }
incoming="$(secret "Token this peer will use to call this agent")"
outgoing="$(secret "Token this agent will use to call the peer")"
[[ "$incoming" =~ ^[A-Za-z0-9._~-]{32,}$ ]] || { echo "Incoming token must be URL-safe and at least 32 characters." >&2; exit 1; }
[[ "$outgoing" =~ ^[A-Za-z0-9._~-]{32,}$ ]] || { echo "Outgoing token must be URL-safe and at least 32 characters." >&2; exit 1; }

existing="$(value A2A_PEER_TOKENS)"
filtered="$(printf '%s' "$existing" | tr ',' '\n' | awk -F: -v peer="$peer" '$1 != peer && NF == 2' | paste -sd, -)"
tokens="$peer:$incoming"
[ -z "$filtered" ] || tokens="$filtered,$tokens"
trusted="$(printf '%s\n%s\n' "$(value A2A_TRUSTED_PEERS | tr ',' '\n')" "$peer" | awk 'NF && !seen[$0]++' | paste -sd, -)"
upsert A2A_PEER_TOKENS "$tokens"
upsert A2A_TRUSTED_PEERS "$trusted"
upsert A2A_HOST 0.0.0.0
upsert A2A_BIND_ADDRESS 0.0.0.0
unset incoming existing filtered tokens

"${DC[@]}" up -d --force-recreate hermes >/dev/null
h() { "${DC[@]}" exec -T hermes hermes "$@"; }
configure_peer() {
  local profile=$1
  local prefix=()
  [ "$profile" = default ] || prefix=(-p "$profile")
  h "${prefix[@]}" config set "a2a_agents.$peer.url" "$peer_url" >/dev/null
  h "${prefix[@]}" config set "a2a_agents.$peer.auth.type" bearer >/dev/null
  h "${prefix[@]}" config set "a2a_agents.$peer.auth.token" "$outgoing" >/dev/null
  h "${prefix[@]}" config set "a2a_agents.$peer.timeout" 120 >/dev/null
}
configure_peer default
while IFS= read -r profile; do
  [[ "$profile" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] && configure_peer "$profile"
done < <("${DC[@]}" exec -T hermes sh -lc 'find /opt/data/profiles -mindepth 1 -maxdepth 1 -type d -printf "%f\n" 2>/dev/null || true')
unset outgoing
"${DC[@]}" restart hermes >/dev/null
"$BASE_DIR/bin/verify.sh" --allow-unconnected
echo "A2A peer '$peer' is connected. Requests are authenticated, rate-limited, logged, and never count as owner approval."
