#!/usr/bin/env bash
# Start the same bot-owned FastAPI topology used by production, but hermetically.
# It intentionally starts from env -i: inherited production URLs/tokens cannot win.
set -euo pipefail

miniapp_url="${PREPROD_MINIAPP_URL:?Set PREPROD_MINIAPP_URL to the temporary HTTPS tunnel URL}"
allowed_ids="${PREPROD_ALLOWED_TG_IDS:?Set PREPROD_ALLOWED_TG_IDS to your test Telegram ID(s)}"
db_port="${PREPROD_PG_PORT:-55432}"
api_port="${PREPROD_API_PORT:-8403}"

case "$miniapp_url" in https://*) ;; *) echo 'PREPROD_MINIAPP_URL must be HTTPS.' >&2; exit 2 ;; esac
case "$db_port:$api_port" in *[!0-9:]*|:*) echo 'Preprod ports must be numeric.' >&2; exit 2 ;; esac
if ! python -c 'import websockets' >/dev/null 2>&1; then
  echo 'Preprod requires the Python websockets package for the production WebSocket surface.' >&2
  exit 2
fi

exec env -i \
  PATH="$PATH" PYTHONPATH="${PYTHONPATH:-}" \
  SSL_CERT_FILE="${SSL_CERT_FILE:-}" NIX_SSL_CERT_FILE="${NIX_SSL_CERT_FILE:-}" \
  LANG="${LANG:-C.UTF-8}" TERM="${TERM:-dumb}" \
  PREDVESTNIK_ENV=preprod \
  PREPROD_ALLOWED_TG_IDS="$allowed_ids" \
  DATABASE_URL="postgresql://predvestnik_preprod@127.0.0.1:${db_port}/predvestnik_preprod" \
  PORT="$api_port" ROOT_PATH=/predvestnik MINIAPP_URL="$miniapp_url" \
  python -m bot
