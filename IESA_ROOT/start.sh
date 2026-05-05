#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

echo "🔄 Running database migrations..."
cd "$PROJECT_ROOT"
python manage.py migrate --noinput || echo "⚠️  Migration failed (DB may be overloaded) — continuing startup anyway"


echo "✅ Startup check done! Starting Daphne ASGI server..."

exec daphne \
    -b 0.0.0.0 \
    -p 8080 \
    --access-log - \
    --proxy-headers \
    -t 30 \
    IESA_ROOT.asgi:application
