#!/bin/sh
set -eu

# Preserve the existing IESA startup maintenance before replacing only the
# public ASGI server with the combined Django + Predvestnik dispatcher.
cd /workspace 2>/dev/null || cd "$(dirname "$0")/../.."

cd IESA_ROOT
python manage.py migrate --noinput || echo "Django migration failed; continuing startup"
python manage.py update_translation_fields || echo "Translation fields update skipped"
python scripts/sync_translations.py 2>&1 || echo "Translation sync skipped"
python manage.py compilemessages --ignore=node_modules --ignore=venv 2>&1 || echo "compilemessages skipped"
cd ..

export ROOT_PATH="/predvestnik"
(
  cd IESA_ROOT
  exec daphne -b 127.0.0.1 -p 18081 --proxy-headers -t 30 IESA_ROOT.asgi:application
) &
site_pid=$!

(
  cd predvestnik_v2
  exec uvicorn FastAPI.main:app --host 127.0.0.1 --port 18082 --proxy-headers
) &
miniapp_pid=$!

cleanup() {
  kill "$site_pid" "$miniapp_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec uvicorn predvestnik_v2.FastAPI.public_gateway:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --proxy-headers
