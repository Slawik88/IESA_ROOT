#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

echo "🔄 Running database migrations..."
cd "$PROJECT_ROOT"
python manage.py migrate --noinput || echo "⚠️  Migration failed (DB may be overloaded) — continuing startup anyway"

# Optional fallback: run Predvestnik in the same app container as a background process.
# Useful when App Platform ignores workers in app spec for existing apps.
if [ "${RUN_PREDVESTNIK_IN_WEB:-1}" = "1" ]; then
    if [ -n "${PREDVESTNIK_BOT_TOKEN:-}" ]; then
        echo "🤖 Starting Predvestnik bot in background..."
        (
            cd "$PROJECT_ROOT/../PredvestnikBot"
            python main.py
        ) &
        echo "🤖 Predvestnik bot started with PID $!"
    else
        echo "⚠️  PREDVESTNIK_BOT_TOKEN is empty — skipping Predvestnik startup"
    fi
fi

echo "✅ Startup check done!"
echo "🚀 Starting Daphne ASGI server..."

exec daphne \
    -b 0.0.0.0 \
    -p 8080 \
    --access-log - \
    --proxy-headers \
    -t 30 \
    IESA_ROOT.asgi:application
