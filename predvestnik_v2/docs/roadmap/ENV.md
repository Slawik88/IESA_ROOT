# Окружение облачной сессии: как проверять работу

Проверено 2026-10-27 в облачной сессии (Ubuntu 24.04, root, PostgreSQL 16.15, Node 22, Chromium 153 из `/opt/pw-browsers`; сборка с нуля — около 75 секунд).
Прод Предвестника работает на **Python 3.12** (`predvestnik_v2/runtime.txt`), поэтому скрипт строит окружение на `python3.12` (он есть в образе; системный `python3` — 3.13, корневой `.python-version` = 3.11 относится к сайту).
Одна команда поднимает всё нужное (идемпотентно), запускать **из корня репозитория**:

```bash
bash predvestnik_v2/docs/roadmap/env-setup.sh
```

Скрипт печатает пути и готовые команды. Дальше везде `PY` = `~/.venvs/predvestnik/bin/python` (или путь из `PV_VENV`).

## Что скрипт делает и почему так

| Шаг | Детали |
|---|---|
| Зависимости | venv вне репозитория (`~/.venvs/predvestnik`, Python 3.12). Полный `requirements.txt` ставить не нужно (на 3.13 `psycopg2-binary==2.9.9` не собирался, а он и Django нужны только сайту IESA). Ставятся версии Предвестника из того же файла (aiogram 3.22.0, asyncpg, fastapi, uvicorn, httpx, loguru, Pillow, matplotlib, av, pymorphy3, aiosqlite, python-dotenv) и `playwright==1.63.0` |
| Playwright | Версия обязана совпадать с Chromium из `/opt/pw-browsers` (1.63 ↔ chromium-1243). **`playwright install` не запускать.** Для Python-скриптов `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; Node-вариант лежит в `/opt/node-tools/node_modules/playwright` |
| PostgreSQL | В образе стоит PostgreSQL 16. Репозиторный `tools/preprod_postgres.sh` требует 17 (`--locale-provider=builtin`), поэтому кластер создаётся с libc-локалью `C.UTF-8` в `/var/lib/postgresql/preprod-16`, порт **5433**, роль и база `predvestnik_preprod`, без пароля. Postgres не стартует от root, поэтому через `runuser -u postgres` |
| Схема | Нужен `create_pool()` + `bot.core.database.init_db()`: тест на пустой базе падает на `relation "users" does not exist` |
| Миграция браков | `tools/migrate_marriage_members_v1.py --apply` добавляет `marriages.ended_at`. Без неё `/profile/me` на чистой базе отвечает 500 (в проде колонка есть: миграция операторская) |

DSN общей базы: `postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod`. Все PG-тесты принимают только loopback-DSN.

**Пустая база для тестов.** Тесты вида `test_bot_health_pg.py`, `test_bot_admin_metrics_pg.py` (в докстринге «пустая тестовая БД!») на общей базе (со схемой и данными смоуков) **падают**, на свежей проходят (проверено 27.10). Свежую базу создаёт
`DSN=$(bash predvestnik_v2/docs/roadmap/env-setup.sh --fresh-db pv_test_bot_health_pg)` и тест запускается с `--dsn "$DSN"`.

## Проверенные команды

`PY` — это `~/.venvs/predvestnik/bin/python`. Если не сказано иное, команды запускаются из `predvestnik_v2/`; скрипт `env-setup.sh` — из корня репозитория (`R` — корень: `R=$(git rev-parse --show-toplevel)`).

```bash
# Контракты без базы
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_player_copy_contract.py          # OK: 32 темы, 49 терминов, 42 ответа
BOT_TOKEN=1:x PYTHONPATH=. node tools/test_guide_navigation.js             # OK: 28 запросов

# PG-тест на общей базе
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_avatar_pool_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod   # OK

# PG-тест, требующий пустую базу (bot_health, admin_metrics): OK на свежей базе
DSN=$(bash "$R/predvestnik_v2/docs/roadmap/env-setup.sh" --fresh-db pv_test_bot_health_pg)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_bot_health_pg.py --dsn "$DSN"

# Браузерный смоук экрана (Chromium + общая база)
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $PY tools/ui_smoke.py --only profile --widths 390   # 1 scenarios: 0 failed

# Стенд админки: снимки вкладок на фикстурах (без входа и сервера), 320/390/430, две темы. Проверено: 6 снимков, проблем 0
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $PY tools/admin_stand.py --out <папка> --tabs health,metrics
```

Остальные команды проверок (`ui_stand.py`, `ui_skin_lab.py`, `ui_smoke.py --perf`, тесты по областям) — в `docs/UI_STAND_AND_SMOKE.md` и в файлах сессий. **Не все 330 тестов проверялись в облаке**:
перед тем как считать тест эталоном, запусти его на чистом `origin/master` и запиши результат.

## Известные ограничения и шум (не считать за ваш дефект)

- **Нет выхода в интернет** для скриптов: диагностика пула печатает `Internet 8.8.8.8:53 TIMEOUT` (безвредно). Внешние ресурсы (Google Fonts, `telegram-web-app.js`) в браузерных прогонах не грузятся:
  вид использует запасные шрифты, а проверки, зависящие от Telegram SDK, ведут себя как «SDK не загрузился».
- **Чистая база неполна по сравнению с прод.** При смоуке в логе бывает `column "bot_rank" does not exist` (предупреждение `profile: staff check skipped`): колонка создаётся при старте бота, а не `init_db`.
  Смоук при этом проходит. Если тест требует колонку, добавь её в подготовку теста, а не в продуктовый код, и запиши в «Находки по пути».
- **Прод из облака не виден**: адреса `iesasport.ch/predvestnik/...` и `*.ondigitalocean.app` недоступны (HTTP 000, проверено 27.10), логи DigitalOcean, `EXPLAIN` на реальных данных, значения фича-флагов, размер инстанса тоже. Проверку деплоя делает владелец (раздел «Ждёт подтверждения прода» в `STATUS.md`), цифры просить у него (раздел «Что нужно принести»).
- **`core.telegram.org` недоступен** из облака; PyPI доступен: факты про Bot API сверять по пакетам aiogram.
- **Git-история в облаке обрезана** (с 22.10.2026). Для старых изменений опора на документы и `docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md`.
- **Артефакты прошлых сессий** (скриншоты, доказательства) лежат на Windows-машине владельца и недоступны. Всё, что нужно сохранить, коммитить в репозиторий (небольшие картинки) или публиковать как Artifact.
- Хранить временные файлы в папке-«scratchpad» сессии, а не в репозитории и не в `/tmp`. Исключение: данные PostgreSQL лежат в `/var/lib/postgresql` (владелец `postgres`).

## Что вставить в setup-script окружения (делает владелец один раз)

В настройках облачного окружения (Claude Code → окружение → «Setup script») добавить строку:

```bash
bash predvestnik_v2/docs/roadmap/env-setup.sh
```

Тогда каждая новая сессия стартует с готовым venv, запущенной базой и миграциями. Инструкция по самому окну настроек: раздел `environment.setup_script` документации среды
(`read_documentation`). Если скрипта в окружении нет, сессия запускает его сама в начале работы (шаг 6 «Протокола старта»).

## Остановка и сброс

```bash
runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/preprod-16 stop     # остановить базу
rm -rf /var/lib/postgresql/preprod-16                                                               # полный сброс (потом снова env-setup.sh)
```
