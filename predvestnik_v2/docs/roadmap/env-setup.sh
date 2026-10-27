#!/usr/bin/env bash
# Поднимает окружение для проверок «Предвестника» в облачной сессии (Ubuntu 24.04, root).
# Python берём 3.12: так же указано для прода в predvestnik_v2/runtime.txt (системный python3 здесь 3.13, корневой .python-version 3.11 относится к сайту).
# Идемпотентно: повторный запуск ничего не ломает. Подробности и проверенные результаты — в ENV.md.
#   bash predvestnik_v2/docs/roadmap/env-setup.sh                  # поднять окружение (из корня репозитория)
#   bash predvestnik_v2/docs/roadmap/env-setup.sh --fresh-db ИМЯ   # пересоздать ПУСТУЮ базу и напечатать её DSN
# «Пустая тестовая БД» нужна тестам вида test_bot_health_pg.py: на общей базе (со схемой и данными смоуков) они падают.
# Переменные: PV_VENV (по умолчанию ~/.venvs/predvestnik), PV_PYTHON (по умолчанию python3.12), PV_PGPORT (по умолчанию 5433).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV="${PV_VENV:-$HOME/.venvs/predvestnik}"
PYBIN="${PV_PYTHON:-python3.12}"
command -v "$PYBIN" >/dev/null || { echo "нет $PYBIN: переопредели PV_PYTHON (прод работает на 3.12, см. runtime.txt)"; exit 1; }
PGBIN=/usr/lib/postgresql/16/bin
PGDATA=/var/lib/postgresql/preprod-16
PGPORT="${PV_PGPORT:-5433}"
DB=predvestnik_preprod
DSN="postgresql://${DB}@127.0.0.1:${PGPORT}/${DB}"

if [ "${1:-}" = "--fresh-db" ]; then
  NAME="${2:?укажи имя базы, например: --fresh-db pv_test_bot_health_pg}"
  PSQL=(psql -h 127.0.0.1 -p "$PGPORT" -U "$DB" -v ON_ERROR_STOP=1 -q)
  # завершить чужие подключения к этой базе, иначе DROP упадёт; любая ошибка прерывает скрипт (set -e), а не печатает DSN «вхолостую»
  "${PSQL[@]}" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$NAME' AND pid <> pg_backend_pid()" >/dev/null
  "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS \"$NAME\"" -c "CREATE DATABASE \"$NAME\"" 2>&1 | { grep -v NOTICE || true; }
  [ "$("${PSQL[@]}" -d "$NAME" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema')")" = 0 ] \
    || { echo "база $NAME не пуста или недоступна" >&2; exit 1; }
  echo "postgresql://${DB}@127.0.0.1:${PGPORT}/${NAME}"
  exit 0
fi

as_pg() { if [ "$(id -u)" = 0 ]; then runuser -u postgres -- "$@"; else "$@"; fi; }

echo "== 1/4 Python-зависимости (только Предвестник) =="
# Ставим только пакеты Предвестника (psycopg2-binary и Django нужны лишь сайту; на 3.13 полный requirements.txt не собирался). Версии берём из requirements.txt, чтобы не разъезжались.
[ -x "$VENV/bin/python" ] || "$PYBIN" -m venv "$VENV"
mapfile -t PINS < <(grep -i -E '^(aiogram|aiosqlite|loguru|asyncpg|pymorphy3|matplotlib|av|fastapi|uvicorn\[standard\]|httpx|Pillow|python-dotenv)==' "$REPO/requirements.txt" | sed 's/[[:space:]]*#.*$//')
# playwright должен совпадать с Chromium из /opt/pw-browsers (1.63.0 ↔ chromium-1243); новый playwright install запрещён.
"$VENV/bin/pip" install -q "${PINS[@]}" "playwright==1.63.0"
"$VENV/bin/python" -c "import aiogram, asyncpg, fastapi, uvicorn, httpx, loguru, PIL, matplotlib, av, pymorphy3, playwright; print('imports ok, aiogram', aiogram.__version__)"

echo "== 2/4 Локальный PostgreSQL 16 на 127.0.0.1:${PGPORT} =="
# Скрипт репозитория tools/preprod_postgres.sh требует PostgreSQL 17 (builtin-локаль), в образе стоит 16: используем libc C.UTF-8.
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  as_pg "$PGBIN/initdb" -D "$PGDATA" --locale=C.UTF-8 --encoding=UTF8 --auth=trust --username="$DB" >/dev/null
fi
mkdir -p "$PGDATA/socket"; [ "$(id -u)" = 0 ] && chown postgres:postgres "$PGDATA/socket"
if ! as_pg "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  as_pg "$PGBIN/pg_ctl" -D "$PGDATA" -o "-h 127.0.0.1 -p $PGPORT -k $PGDATA/socket" -l "$PGDATA/postgres.log" --wait --timeout=30 start >/dev/null
fi
psql -h 127.0.0.1 -p "$PGPORT" -U "$DB" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -qx 1 \
  || "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U "$DB" "$DB"

echo "== 3/4 Схема базы и миграция браков =="
cd "$REPO/predvestnik_v2"
INIT_OUT=$(DATABASE_URL="$DSN" BOT_TOKEN=1:x PYTHONPATH=. "$VENV/bin/python" - <<'PY' 2>&1
import asyncio
from infrastructure import database as idb
from bot.core import database as d
async def main():
    await idb.create_pool()
    await d.init_db()
    print("init_db ok")
asyncio.run(main())
PY
) || true
echo "$INIT_OUT" | grep -q "init_db ok" || { echo "init_db не отработал:" >&2; echo "$INIT_OUT" | tail -15 >&2; exit 1; }
echo "init_db ok"
# Колонка marriages.ended_at появляется только этой операторской миграцией; без неё /profile/me на чистой базе падает.
BOT_TOKEN=1:x PYTHONPATH=. "$VENV/bin/python" tools/migrate_marriage_members_v1.py --dsn "$DSN" --apply

echo "== 4/4 Готово =="
cat <<EOF
Python:      $VENV/bin/python
DSN:         $DSN
Тест без БД: cd predvestnik_v2 && BOT_TOKEN=1:x PYTHONPATH=. $VENV/bin/python tools/test_player_copy_contract.py
PG-тест:     ... $VENV/bin/python tools/test_avatar_pool_pg.py --dsn $DSN
UI-смоук:    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $VENV/bin/python tools/ui_smoke.py --only profile --widths 390
EOF
