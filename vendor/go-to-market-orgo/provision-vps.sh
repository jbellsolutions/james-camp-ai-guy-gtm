#!/usr/bin/env bash
# Prepare an Ubuntu Orgo/DigitalOcean computer; safe to rerun.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${AI_GUY_REPO:-https://github.com/jbellsolutions/go-to-market-orgo.git}"
DEST="${AI_GUY_TEMPLATE_DIR:-$SCRIPT_DIR}"

fail() { printf 'Provisioning stopped: %s\n' "$*" >&2; exit 1; }
[ "$(uname -s)" = Linux ] || fail "this provisioner is for a Linux computer"
if [ "$(id -u)" -eq 0 ]; then ELEVATE=(); else
  command -v sudo >/dev/null 2>&1 || fail "administrator access is required to install Docker"
  ELEVATE=(sudo)
fi

echo "Preparing this computer for Go-To-Market for Orgo"
if ! command -v git >/dev/null 2>&1 || \
   ! command -v curl >/dev/null 2>&1 || \
   ! command -v python3 >/dev/null 2>&1 || \
   ! command -v crontab >/dev/null 2>&1 || \
   ! command -v flock >/dev/null 2>&1; then
  "${ELEVATE[@]}" apt-get update -qq
  "${ELEVATE[@]}" apt-get install -y -qq ca-certificates cron curl git python3 util-linux
fi

ensure_cron_service() {
  pgrep -x cron >/dev/null 2>&1 && return 0
  if command -v systemctl >/dev/null 2>&1 && "${ELEVATE[@]}" systemctl enable --now cron >/dev/null 2>&1; then
    return 0
  fi
  if command -v supervisorctl >/dev/null 2>&1; then
    local supervisor_dir supervisor_config temporary
    supervisor_dir=/etc/supervisor/conf.d
    supervisor_config="$supervisor_dir/ai-guy-cron.conf"
    temporary="$(mktemp)"
    cat > "$temporary" <<'EOF'
[program:ai-guy-cron]
command=/usr/sbin/cron -f -L 15
autostart=true
autorestart=true
priority=20
stdout_logfile=/var/log/ai-guy-cron.log
stderr_logfile=/var/log/ai-guy-cron-error.log
EOF
    "${ELEVATE[@]}" mkdir -p "$supervisor_dir"
    "${ELEVATE[@]}" install -m 0644 "$temporary" "$supervisor_config"
    rm -f "$temporary"
    "${ELEVATE[@]}" supervisorctl reread >/dev/null 2>&1 || true
    "${ELEVATE[@]}" supervisorctl update >/dev/null 2>&1 || true
  else
    "${ELEVATE[@]}" service cron start >/dev/null 2>&1 || true
  fi
  pgrep -x cron >/dev/null 2>&1 || \
    echo "Warning: cron is installed but its service could not be confirmed."
}

ensure_small_host_swap() {
  local memory_kib swap_kib available_kib swapfile created
  memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  swap_kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
  [ "${memory_kib:-0}" -lt 6291456 ] || return 0
  [ "${swap_kib:-0}" -eq 0 ] || return 0

  available_kib="$(df -Pk / | awk 'NR == 2 {print $4}')"
  if [ "${available_kib:-0}" -lt 6291456 ]; then
    echo "Warning: less than 6 GB is free, so the optional 4 GB swap safety net was skipped."
    return 0
  fi

  swapfile="${AI_GUY_SWAP_FILE:-/swapfile}"
  case "$swapfile" in /*) ;; *) echo "Warning: swap path must be absolute; swap was skipped."; return 0 ;; esac
  if [ -e "$swapfile" ]; then
    echo "An existing $swapfile was left untouched."
    return 0
  fi

  created=false
  if "${ELEVATE[@]}" fallocate -l 4G "$swapfile" >/dev/null 2>&1; then
    created=true
  elif "${ELEVATE[@]}" dd if=/dev/zero of="$swapfile" bs=1M count=4096 status=none; then
    created=true
  fi
  [ "$created" = true ] || { echo "Warning: the optional swap safety net could not be created."; return 0; }

  if ! "${ELEVATE[@]}" chmod 600 "$swapfile" || \
     ! "${ELEVATE[@]}" mkswap "$swapfile" >/dev/null; then
    "${ELEVATE[@]}" rm -f "$swapfile"
    echo "Warning: the optional swap safety net could not be prepared."
    return 0
  fi
  if "${ELEVATE[@]}" swapon "$swapfile" >/dev/null 2>&1; then
    if ! grep -Fq "$swapfile none swap sw 0 0" /etc/fstab; then
      printf '%s none swap sw 0 0\n' "$swapfile" | "${ELEVATE[@]}" tee -a /etc/fstab >/dev/null
    fi
    echo "Added a persistent 4 GB swap safety net for this small computer."
  else
    "${ELEVATE[@]}" rm -f "$swapfile"
    echo "Warning: this host does not allow swap; provisioning will continue without it."
  fi
}

ensure_cron_service
ensure_small_host_swap

if ! command -v docker >/dev/null 2>&1; then
  installer="$(mktemp)"
  trap 'rm -f "${installer:-}"' EXIT
  curl -fsSL https://get.docker.com -o "$installer"
  "${ELEVATE[@]}" sh "$installer"
fi
docker compose version >/dev/null 2>&1 || {
  "${ELEVATE[@]}" apt-get update -qq
  "${ELEVATE[@]}" apt-get install -y -qq docker-compose-plugin
}
"${ELEVATE[@]}" systemctl enable --now docker >/dev/null 2>&1 || true
if [ "$(id -u)" -ne 0 ] && ! docker info >/dev/null 2>&1; then
  "${ELEVATE[@]}" usermod -aG docker "$USER"
  fail "Docker is installed. Start a new login session once so the Docker group becomes active."
fi

if [ ! -d "$DEST/.git" ]; then
  git clone "$REPO" "$DEST"
fi
if [ ! -f "$DEST/agent.env" ]; then
  cp "$DEST/agent.example.env" "$DEST/agent.env"
  chmod 600 "$DEST/agent.env"
fi

echo "Computer preparation is complete. The private agent file is $DEST/agent.env."
echo "The installation agent can now reuse existing secrets and run $DEST/new-agent.sh."
