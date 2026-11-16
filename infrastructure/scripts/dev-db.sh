#!/usr/bin/env bash
# Project-local PostgreSQL cluster for development (no superuser password or Docker needed).
# Uses the installed PostgreSQL binaries; data lives in apps/api/var/pgdata (git-ignored).
#
#   infrastructure/scripts/dev-db.sh init     # create cluster + smartestate and smartestate_test databases
#   infrastructure/scripts/dev-db.sh start|stop|status
#
# Reads DB_USER, DB_PASSWORD, DB_PORT from the repository .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
DATA="$ROOT/apps/api/var/pgdata"
LOG="$ROOT/apps/api/var/postgres.log"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE (copy .env.example first)"; exit 1; }
env_get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }
DB_USER="$(env_get DB_USER)"; DB_PASSWORD="$(env_get DB_PASSWORD)"; DB_PORT="$(env_get DB_PORT)"

# Locate PostgreSQL binaries (PATH first, then the default Windows install location).
if ! command -v pg_ctl >/dev/null 2>&1; then
  for d in "/c/Program Files/PostgreSQL"/*/bin; do [[ -x "$d/pg_ctl.exe" ]] && PATH="$d:$PATH"; done
fi
command -v pg_ctl >/dev/null || { echo "PostgreSQL binaries (pg_ctl, initdb) not found"; exit 1; }

start() {
  if pg_ctl -D "$DATA" status >/dev/null 2>&1; then echo "Already running on port $DB_PORT"; return; fi
  # Redirect stdio: otherwise the server inherits this shell's pipes and the caller never returns.
  pg_ctl -D "$DATA" -l "$LOG" -w -o "-p $DB_PORT -c listen_addresses=127.0.0.1" start </dev/null >/dev/null 2>&1
  echo "Started on 127.0.0.1:$DB_PORT (log: $LOG)"
}

case "${1:-status}" in
  init)
    if [[ -f "$DATA/PG_VERSION" ]]; then echo "Cluster already exists at $DATA"; else
      mkdir -p "$(dirname "$DATA")"
      PWFILE="$(mktemp)"; printf '%s' "$DB_PASSWORD" > "$PWFILE"
      initdb -D "$DATA" -U "$DB_USER" --pwfile="$PWFILE" -A scram-sha-256 -E UTF8 --no-locale >/dev/null
      rm -f "$PWFILE"
    fi
    start
    for db in smartestate smartestate_test; do
      PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
        || PGPASSWORD="$DB_PASSWORD" createdb -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" "$db"
    done
    echo "Databases ready on 127.0.0.1:$DB_PORT"
    ;;
  start) start ;;
  stop) pg_ctl -D "$DATA" -m fast stop ;;
  status) pg_ctl -D "$DATA" status || true ;;
  *) echo "usage: $0 init|start|stop|status"; exit 2 ;;
esac
