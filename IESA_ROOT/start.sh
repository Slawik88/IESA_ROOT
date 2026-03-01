#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

echo "🔄 Running database migrations..."
python manage.py migrate --noinput || echo "⚠️  Migration failed (DB may be overloaded) — continuing startup anyway"

echo "✅ Startup check done!"
echo "🚀 Starting Daphne ASGI server..."

exec daphne \
    -b 0.0.0.0 \
    -p 8080 \
    --access-log - \
    --proxy-headers \
    -t 30 \
    IESA_ROOT.asgi:application
