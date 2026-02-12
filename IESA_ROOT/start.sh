#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

echo "🔄 Running database migrations..."
python manage.py migrate --noinput

echo "✅ Migrations complete!"
echo "🚀 Starting Gunicorn server..."

exec gunicorn IESA_ROOT.wsgi:application \
    --bind 0.0.0.0:8080 \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
