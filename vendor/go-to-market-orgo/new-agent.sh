#!/usr/bin/env bash
# Idempotent one-command installer for Orgo, DigitalOcean, or any Linux Docker host.
set -euo pipefail

TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${1:-$TEMPLATE_DIR/agent.env}"
NO_START=false
[ "${2:-}" = "--no-start" ] && NO_START=true

fail() { printf 'Setup stopped: %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Run ./provision-vps.sh first."
docker compose version >/dev/null 2>&1 || fail "Docker Compose is not available."

if [ ! -f "$CFG" ]; then
  cp "$TEMPLATE_DIR/agent.example.env" "$CFG"
  chmod 600 "$CFG"
  fail "A private agent.env was created at $CFG. Add the existing model key, then run this installer again."
fi

set -a
# shellcheck disable=SC1090
source "$CFG"
set +a
: "${AGENT_NAME:?Set AGENT_NAME in $CFG}"
: "${BASE_DIR:?Set BASE_DIR in $CFG}"
[[ "$AGENT_NAME" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || fail "AGENT_NAME must use lowercase letters, numbers, and dashes."
[[ "$BASE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "BASE_DIR must be an absolute Linux path without spaces."
[ -n "${FIREWORKS_API_KEY:-}" ] && [ "$FIREWORKS_API_KEY" != fw_REPLACE_ME ] || fail "Add the Fireworks model key to $CFG."
[ "${ENABLE_AGENT_BUNDLE:-false}" != true ] || fail "Agent Bundle is reserved for the Co-Founder template."

echo "Installing the AI Guy Go-To-Market Agent at $BASE_DIR"
mkdir -p "$BASE_DIR"/{bin,hermes/data,vault/daily-logs,logs,sync}
cp "$TEMPLATE_DIR/compose.yml" "$BASE_DIR/compose.yml"
cp "$TEMPLATE_DIR/bin/watchdog.sh" "$BASE_DIR/bin/watchdog.sh"
cp "$TEMPLATE_DIR/bin/configure-managed.sh" "$BASE_DIR/bin/configure-managed.sh"
cp "$TEMPLATE_DIR/bin/connect-stack.sh" "$BASE_DIR/bin/connect-stack.sh"
cp "$TEMPLATE_DIR/bin/connect-a2a.sh" "$BASE_DIR/bin/connect-a2a.sh"
cp "$TEMPLATE_DIR/bin/approve-agent.sh" "$BASE_DIR/bin/approve-agent.sh"
cp "$TEMPLATE_DIR/bin/verify.sh" "$BASE_DIR/bin/verify.sh"
find "$TEMPLATE_DIR/sync" -maxdepth 1 -type f -exec cp {} "$BASE_DIR/sync/" \;
chmod +x "$BASE_DIR/bin/"*.sh

if [ ! -f "$BASE_DIR/.env" ]; then
  cp "$CFG" "$BASE_DIR/.env"
  chmod 600 "$BASE_DIR/.env"
fi

if ! grep -q '^HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=..' "$BASE_DIR/.env"; then
  dashboard_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  temp_env="$(mktemp "$BASE_DIR/.env.XXXXXX")"
  awk 'index($0, "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=") != 1 {print}' "$BASE_DIR/.env" > "$temp_env"
  printf 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=%s\n' "$dashboard_password" >> "$temp_env"
  chmod 600 "$temp_env"
  mv "$temp_env" "$BASE_DIR/.env"
  unset dashboard_password
fi

python3 "$TEMPLATE_DIR/services/install_assets.py" --root "$TEMPLATE_DIR" --home "$BASE_DIR/hermes/data"
mkdir -p "$HOME/.config/ai-guy-agent"
printf '{"schema_version":1,"role":"go-to-market","deployment_dir":"%s"}\n' "$BASE_DIR" \
  > "$HOME/.config/ai-guy-agent/go-to-market.json"
chmod 600 "$HOME/.config/ai-guy-agent/go-to-market.json"

config="$BASE_DIR/hermes/data/config.yaml"
if [ ! -f "$config" ]; then
  slack=false
  telegram=false
  [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_APP_TOKEN:-}" ] && slack=true
  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && telegram=true
  sed -e "s#__SLACK_ENABLED__#$slack#g" \
      -e "s#__TELEGRAM_ENABLED__#$telegram#g" \
      -e "s#__AGENT_PERSONA__#${AGENT_PERSONA:-helpful}#g" \
      -e "s#__TELEGRAM_HOME_CHANNEL__#${TELEGRAM_HOME_CHANNEL:-}#g" \
      -e "s#__SLACK_HOME_CHANNEL__#${SLACK_HOME_CHANNEL:-}#g" \
      "$TEMPLATE_DIR/hermes/config.template.yaml" > "$config"
  if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    sed -i.bak '/__OPENROUTER_FALLBACK_START__/,/__OPENROUTER_FALLBACK_END__/d' "$config"
  else
    sed -i.bak -e '/__OPENROUTER_FALLBACK_START__/d' -e '/__OPENROUTER_FALLBACK_END__/d' "$config"
  fi
  [ -n "${TELEGRAM_HOME_CHANNEL:-}" ] || sed -i.bak "/^TELEGRAM_HOME_CHANNEL: ''$/d" "$config"
  [ -n "${SLACK_HOME_CHANNEL:-}" ] || sed -i.bak "/^SLACK_HOME_CHANNEL: ''$/d" "$config"
  rm -f "$config.bak"
  chmod 600 "$config"
else
  echo "Keeping the existing Hermes configuration and conversation state."
fi

sed -i.bak -e "s#__AGENT_NAME__#$AGENT_NAME#g" -e "s#__BASE_DIR__#$BASE_DIR#g" "$BASE_DIR/bin/watchdog.sh"
rm -f "$BASE_DIR/bin/watchdog.sh.bak"

install_watchdog_schedule() {
  command -v crontab >/dev/null 2>&1 || \
    fail "The recovery scheduler is missing. Run ./provision-vps.sh, then run this installer again."

  local current updated marker schedule
  current="$(mktemp)"
  updated="$(mktemp)"
  marker="# AI Guy watchdog: $AGENT_NAME"
  schedule="* * * * * flock -n '$BASE_DIR/.watchdog.lock' '$BASE_DIR/bin/watchdog.sh' >/dev/null 2>&1"

  crontab -l > "$current" 2>/dev/null || true
  awk -v marker="$marker" -v watchdog="$BASE_DIR/bin/watchdog.sh" \
    'index($0, marker) == 0 && index($0, watchdog) == 0 { print }' \
    "$current" > "$updated"
  printf '%s\n%s\n' "$marker" "$schedule" >> "$updated"
  crontab "$updated"
  rm -f "$current" "$updated"
}

install_watchdog_schedule

if [ "$NO_START" = false ]; then
  cd "$BASE_DIR"
  docker compose --env-file .env config --quiet
  docker compose --env-file .env pull hermes
  docker compose --env-file .env up -d hermes
  for _ in {1..30}; do
    docker compose --env-file .env exec -T hermes hermes gateway status >/dev/null 2>&1 && break
    sleep 2
  done
  "$BASE_DIR/bin/configure-managed.sh"
  docker compose --env-file .env restart hermes >/dev/null
  "$BASE_DIR/bin/verify.sh" --allow-unconnected
fi

echo
echo "AI Guy Go-To-Market Agent installation is complete."
echo "Dashboard: http://127.0.0.1:${HERMES_PORT:-18789}"
echo "Private credentials: $BASE_DIR/.env"
echo "Connect Honcho or Latitude: $BASE_DIR/bin/connect-stack.sh"
echo "Connect another agent: $BASE_DIR/bin/connect-a2a.sh"
echo "Automatic recovery: checked every minute"
