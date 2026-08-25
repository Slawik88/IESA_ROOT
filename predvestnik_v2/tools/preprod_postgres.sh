#!/usr/bin/env bash
# Lifecycle for the deliberately isolated local PostgreSQL used by preprod.
# Run through Nix: nix-shell -p postgresql --run './tools/preprod_postgres.sh start'
set -euo pipefail

action="${1:-status}"
data_dir="${PREPROD_PG_DATA_DIR:-.local/preprod-postgres}"
port="${PREPROD_PG_PORT:-55432}"
role="predvestnik_preprod"

case "$port" in
  ''|*[!0-9]*) echo 'PREPROD_PG_PORT must be numeric.' >&2; exit 2 ;;
esac

init() {
  if [ ! -f "$data_dir/PG_VERSION" ]; then
    mkdir -p "$data_dir"
    initdb --no-locale --encoding=UTF8 --auth=trust --username="$role" --pgdata="$data_dir" >/dev/null
  fi
}

case "$action" in
  start)
    init
    data_dir="$(cd "$data_dir" && pwd)"
    socket_dir="$data_dir/socket"
    mkdir -p "$socket_dir"
    if ! pg_ctl --pgdata="$data_dir" status >/dev/null 2>&1; then
      pg_ctl --pgdata="$data_dir" --wait --timeout=30 \
        --options="-h 127.0.0.1 -p $port -k $socket_dir" \
        --log="$data_dir/postgres.log" start >/dev/null
    fi
    if ! psql --host=127.0.0.1 --port="$port" --username="$role" --dbname=postgres \
      --tuples-only --no-align --command="SELECT 1 FROM pg_database WHERE datname='$role'" \
      | grep -qx '1'; then
      createdb --host=127.0.0.1 --port="$port" --username="$role" "$role"
    fi
    echo "PREPROD_POSTGRES_READY port=$port database=predvestnik_preprod"
    ;;
  stop)
    if [ -f "$data_dir/postmaster.pid" ]; then
      pg_ctl --pgdata="$data_dir" --wait --timeout=30 stop >/dev/null
    fi
    echo 'PREPROD_POSTGRES_STOPPED'
    ;;
  status)
    if [ -f "$data_dir/postmaster.pid" ]; then
      pg_ctl --pgdata="$data_dir" status
    else
      echo 'PREPROD_POSTGRES_STOPPED'
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}" >&2
    exit 2
    ;;
esac
