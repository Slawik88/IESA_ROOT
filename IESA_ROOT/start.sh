#!/bin/bash
# Production startup script for DigitalOcean App Platform
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

echo "🔄 Running database migrations..."
cd "$PROJECT_ROOT"
python manage.py migrate --noinput || echo "⚠️  Migration failed (DB may be overloaded) — continuing startup anyway"

# V6 (дизайн-аудит 2026-07-17): легаси-данные лежали в сырых колонках (position, title...),
# а переводные (position_en...) были пустыми — карточки рендерились с дырами.
# Команда идемпотентно переносит сырые значения в поле дефолтного языка.
echo "🈯 Populating translation fields (update_translation_fields)..."
python manage.py update_translation_fields || echo "⚠️  update_translation_fields failed — continuing startup"

# BLOCK auto-deploy (audit v4): синхронизация переводов при каждом deploy.
# Скрипт извлекает {% trans %} из шаблонов, обновляет .po файлы, пересобирает .mo.
# Если polib не установлен ИЛИ скрипт упал — НЕ блокируем старт сервера.
echo "🌍 Syncing translations (sync_translations.py)..."
python scripts/sync_translations.py 2>&1 || echo "⚠️  Translation sync skipped (polib missing or error) — continuing startup"

# Также Django compilemessages — на случай если .mo устарели в репозитории
# (gettext в DigitalOcean buildpack-е есть)
echo "🔧 Compiling .mo files (compilemessages)..."
python manage.py compilemessages --ignore=node_modules --ignore=venv 2>&1 || echo "⚠️  compilemessages failed — continuing startup"

echo "✅ Startup check done! Starting Daphne ASGI server..."

exec daphne \
    -b 0.0.0.0 \
    -p 8080 \
    --access-log - \
    --proxy-headers \
    -t 30 \
    IESA_ROOT.asgi:application
