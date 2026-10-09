#!/bin/sh
# Nightly consistent copies (sqlite online backup) of rel.sqlite3, approvals.sqlite3 and sends.sqlite3 (root).
# Optional off-droplet copy: set RELCORE_BACKUP_CMD in /etc/relcore/backup.env (receives the folder path).
set -eu
DAY="$(date -u +%Y-%m-%d)"; OUT="/var/backups/relcore/$DAY"
install -d -m 0700 "$OUT"
for db in /home/*/.hermes/trp/private-business/relationship/rel.sqlite3 /var/lib/relapprove/approvals.sqlite3 /var/lib/relsend/sends.sqlite3; do
  [ -f "$db" ] || continue
  python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" "$db" "$OUT/$(basename "$db")"
done
chmod 0600 "$OUT"/* 2>/dev/null || true
find /var/backups/relcore -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
[ -f /etc/relcore/backup.env ] && . /etc/relcore/backup.env
[ -n "${RELCORE_BACKUP_CMD:-}" ] && sh -c "$RELCORE_BACKUP_CMD \"$OUT\""
exit 0
