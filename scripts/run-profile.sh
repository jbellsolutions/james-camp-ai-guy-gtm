#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 4 ] || { echo 'Usage: run-profile.sh STATE_ROOT INSTALL PROFILE PROMPT_FILE' >&2; exit 2; }
state="$1"; install="$2"; profile="$3"; prompt="$4"
[[ "$install" = cold-email || "$install" = conversations ]] || exit 2
[[ "$profile" =~ ^[a-z0-9-]+$ ]] || exit 2
[ -f "$state/$install/hermes/data/profiles/$profile/CHARTER.md" ] || { echo 'Profile not installed' >&2; exit 1; }
[ ! -e "$state/EXTERNAL_WRITES_STOPPED" ] || { echo 'External work stopped; use a separate draft-only session.' >&2; exit 1; }
cd "$state/$install"
docker compose --env-file .env exec -T -e "HERMES_HOME=/opt/data/profiles/$profile" hermes hermes chat -q "$(cat "$prompt")"
