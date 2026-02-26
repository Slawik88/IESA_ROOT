#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

echo "🔄 Running database migrations..."
python manage.py migrate --noinput

echo "✅ Migrations complete!"
echo "🚀 Starting Daphne ASGI server..."

exec daphne \
    -b 0.0.0.0 \
    -p 8080 \
    --access-log - \
    IESA_ROOT.asgi:application
