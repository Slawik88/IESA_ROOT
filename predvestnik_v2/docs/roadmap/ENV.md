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
| Зависимости | venv вне репозитория (`~/.venvs/predvestnik`, Python 3.12). Полный `requirements.txt` ставить не нужно (на 3.13 `psycopg2-binary==2.9.9` не собирался, а он и Django нужны только сайту IESA). Ставятся версии Предвестника из того же файла (aiogram по `requirements.txt` (сейчас 3.22.0, после S23a выше), asyncpg, fastapi, uvicorn, httpx, loguru, Pillow, matplotlib, av, pymorphy3, aiosqlite, python-dotenv) и `playwright==1.63.0` |
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

Остальные команды проверок (`ui_stand.py`, `ui_skin_lab.py`, `ui_smoke.py --perf`, тесты по областям) — в `docs/UI_STAND_AND_SMOKE.md` и в файлах сессий. **Не все 287 тестов проверялись в облаке**:
перед тем как считать тест эталоном, запусти его на чистом `origin/master` и запиши результат.

## Симулятор Telegram

Готовый симулятор для проверки бота без реального Telegram: `tools/mafia_sim/` (`World`, `FakeSession`, `Harness` гоняют настоящий диспетчер с роутерами и middlewares). **Работает только на базе `predvestnik_preprod` (loopback)**, то есть на общей базе из `env-setup.sh`, а не на `--fresh-db ИМЯ`. Запуск образцов: `tools/test_mafia_v1_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod`. Общий набор сценариев для бота создаёт сессия S23a.

## Известные ограничения и шум (не считать за ваш дефект)

- **Нет выхода в интернет, кроме пакетного зеркала PyPI** (установка пакетов работает, остальное нет): диагностика пула печатает `Internet 8.8.8.8:53 TIMEOUT` (безвредно). Внешние ресурсы (Google Fonts, `telegram-web-app.js`) в браузерных прогонах не грузятся:
  вид использует запасные шрифты, а проверки, зависящие от Telegram SDK, ведут себя как «SDK не загрузился».
- **Чистая база неполна по сравнению с прод.** При смоуке в логе бывает `column "bot_rank" does not exist` (предупреждение `profile: staff check skipped`): колонка создаётся при старте бота, а не `init_db`.
  Смоук при этом проходит. Если тест требует колонку, добавь её в подготовку теста, а не в продуктовый код, и запиши в «Находки по пути».
- **Прод из облака не виден**: адреса `iesasport.ch/predvestnik/...` и `*.ondigitalocean.app` недоступны (HTTP 000, проверено 27.10), логи DigitalOcean, `EXPLAIN` на реальных данных, значения фича-флагов, размер инстанса тоже. Проверку деплоя делает владелец (раздел «Ждёт подтверждения прода» в `STATUS.md`), цифры просить у него (раздел «Что нужно принести»).
- **`core.telegram.org` недоступен** из облака; PyPI доступен: факты про Bot API сверять по пакетам aiogram.
- **Git-история в облаке обрезана** (с 22.10.2026). Для старых изменений опора на документы и `docs/audits/AUTONOMOUS_RELEASE_BACKLOG.md`.
- **Артефакты прошлых сессий** (скриншоты, доказательства) лежат на Windows-машине владельца и недоступны. Всё, что нужно сохранить, коммитить в репозиторий (небольшие картинки) или публиковать как Artifact.
- Хранить временные файлы в папке-«scratchpad» сессии, а не в репозитории и не в `/tmp`. Исключение: данные PostgreSQL лежат в `/var/lib/postgresql` (владелец `postgres`).

## Кто запускает `env-setup.sh`

**Сама сессия**, на шаге 5 «Протокола старта» (`README.md`): `bash predvestnik_v2/docs/roadmap/env-setup.sh` из корня репозитория. Скрипт идемпотентен: на уже собранном окружении он отрабатывает за секунды. **Владельцу ничего вставлять в настройки не нужно.**
Авто-запуск хуком `SessionStart` возможен как улучшение (записано в «Находки по пути», `STATUS.md`): он ускорил бы старт, но затронет все облачные сессии репозитория, включая работу над сайтом.

## Health-эндпоинты и «Здоровье» (с S01)

| Адрес | Что значит | Кому |
|---|---|---|
| `/api/health` | процесс жив и слушает порт; базу **не трогает**, всегда `{"status":"ok"}` | проверка живости в панели DigitalOcean: медленная база не должна перезапускать контейнер |
| `/api/ready` | запуск закончен и таблицы, которые читают первые запросы, есть (иначе 503) | проверка готовности |
| `/api/health/deep` | пинг базы с таймаутом 2 с (503, если база недоступна) и свежесть метрик (`status: degraded`, если сборщик не работает) | людям и внешнему мониторингу; **не ставить** проверкой живости в панели |

Цифры для владельца: админка → «Состояние» → блок «Здоровье» (1 ч / 24 ч / 7 дн, хранится 14 дней, перезапуск не обнуляет). Там: лаг сервера, ожидание и занятость пула, очередь в Telegram, самые медленные запросы, причины 401, ошибки у игроков в приложении (по типам, версиям, повторяющиеся), **ошибки бота по обработчикам**.
Устройство: `core/ops_metrics.py` (счётчики в памяти), `services/ops_health.py` (сборщик, тревоги, сводка; пороги — константы в начале файла), `infrastructure/repositories/ops_telemetry.py` (таблицы `ops_metrics_5m`, `client_telemetry_events`, `bot_handler_errors`), приём ошибок Mini App — `POST /telemetry` (`FastAPI/routers/telemetry.py`, клиент — `FastAPI/static/support-diagnostics.js`), перехват ошибок бота — `bot/dispatcher.py` (общий для бота и симулятора).

```bash
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_ops_metrics.py                                   # без базы: перцентили, лимиты, тревоги
DSN=$(bash "$R/predvestnik_v2/docs/roadmap/env-setup.sh" --fresh-db pv_test_ops_health)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_ops_health_pg.py --dsn "$DSN"                    # 401, телеметрия, хранение, нагрузка, health
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_bot_error_monitor_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod   # симулятор
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod $PY tools/test_client_telemetry_browser.py
BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod $PY tools/bench_http_overhead.py   # серверная задержка /api/health, p50 ≈ 1,2 мс
```

## Вход и аватарки (с S02)

```bash
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod $PY tools/test_auth_recovery_browser.py   # копия SDK, вход без SDK, экран «открой заново», повтор только GET, сокет
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_avatar_pool_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod        # фото в базе: пул, перезапуск, VIP на прямом адресе, админка
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_avatar_recovery.py && BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_avatar_signed_photo.py          # без базы
node tools/test_avatar_recovery_ui.js && node tools/test_leaderboard_avatar_ui.js
```

Устройство: фото — `services/avatar_photos.py` (правила, состояния `ready/loading/absent/vip_only`), таблица `avatar_photos` (`infrastructure/repositories/avatar_photos.py`), Telegram — `infrastructure/telegram_photo.py`.
Копия Telegram SDK — `FastAPI/static/vendor/telegram-web-app.js` (заменять целиком новой версией официального файла, не править).

## Пул базы и троттлер Telegram (с S03)

```bash
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_outbound_throttle.py                 # без базы: слот только для сообщений, отмена, приоритет админки, повтор после flood
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_pool_starvation_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod   # 10 зависших вызовов Telegram не трогают Mini App; ленивое соединение; блокировка и LISTEN вне пула
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_global_ban_job_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod    # бан во всех чатах фоновым заданием
```

Устройство: `infrastructure/lazy_db.py` (соединение берётся на первом SQL и отдаётся перед каждым вызовом Telegram, если нет открытой транзакции; это делают бот, `get_db`, `pool_db_factory`, обслуживание и цикл Мафии), `bot/middlewares/db.py` (`DbReleaseMiddleware`), `bot/dispatcher.attach_outbound` (порядок исходящих middleware, общий для бота и симулятора), `infrastructure/database.py` (`acquire_connection`, `PoolBusy` → HTTP 503, `connect_direct` для advisory lock и LISTEN).
Переменные окружения: `DB_POOL_MAX_SIZE` — **всего** соединений процесса (не больше 10; два из них прямые: блокировка экземпляра и LISTEN, пул = остальное), `DB_ACQUIRE_TIMEOUT_SEC` — сколько ждать свободное соединение (по умолчанию 10 с). Задавать не обязательно.
Сервер базы общий с сайтом IESA: число соединений всего сервера видно в «Здоровье» → «Сервер и база» (`pg_stat_activity`, соединения Предвестника подписаны `application_name=predvestnik`).

## База и кэши (с S04)

```bash
DSN=$(bash "$R/predvestnik_v2/docs/roadmap/env-setup.sh" --fresh-db pv_test_db_hot_paths)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_db_hot_paths_pg.py --dsn "$DSN"          # бюджет SQL профиля и топов, снимок и ETag, пачка «пульса», индексы CONCURRENTLY
node tools/test_client_request_trims.js                                            # клиент: топ раз в 10 с, «пульс» раз в минуту, вход в «Чистку»
DSN=$(bash "$R/predvestnik_v2/docs/roadmap/env-setup.sh" --fresh-db pv_s04_bench)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/bench_db_hot_queries.py --dsn "$DSN" --indexes  # замер на синтетике ~1M строк (первый запуск наполняет базу ~30 с)
```

Устройство: индексы больших таблиц строит фоновая задача после блокировки экземпляра (`infrastructure/db_indexes.py`: `CREATE INDEX CONCURRENTLY IF NOT EXISTS` по одному, своё прямое соединение на время постройки, `lock_timeout` 60 с; брошенный деплоем INVALID-индекс удаляется и строится заново при следующем старте; итог — строка `db indexes: …` в логе).
Триграммные индексы поиска админки строятся, только если расширение `pg_trgm` уже установлено в базе (само расширение не ставится).
Кэши в памяти процесса (общий для бота и Mini App): топы сообщений — 45 с (`services/leaderboards_v1.py`), свой профиль `/profile/me` — 8 с с ETag, сбрасывается любым не-GET запросом игрока и любым живым событием о нём (`FastAPI/profile_snapshot.py`); время на вкладках копится в памяти и пишется пачкой раз в минуту (`services/tab_time.py`).
Соединения Предвестника открываются с `jit=off` (`infrastructure/database.py`): JIT компилировал план ~200 мс на запросах с большой оценкой строк. Если когда-нибудь включат пул соединений DigitalOcean (PgBouncer), проверить, что он пропускает параметры `jit`, `statement_timeout`, `search_path`.

## «Чистка» (с S05)

```bash
DSN=$(bash "$R/predvestnik_v2/docs/roadmap/env-setup.sh" --fresh-db pv_test_purge_queue)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/bootstrap_test_db.py --dsn "$DSN"          # схема как на старте бота (нужны столбцы чата: required_norm и др.)
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_purge_queue_pg.py --dsn "$DSN"        # фон 202, очередь после «перезапуска», 0 getChatMember на опрос, 304, живые события, бан не держит соединение
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_purge_reliability_pg.py --dsn "$DSN"  # Telegram вне транзакции, сверка, сбой записи → сверка
BOT_TOKEN=1:x PYTHONPATH=. $PY tools/bench_purge_two_viewers_pg.py --dsn "$DSN" # замер «двое смотрят»: p50/p95 ответа и getChatMember на опрос
node tools/test_purge_live_ui.js                                                # экран «Чистка» (настоящий app.07.js)
```

Без `bootstrap_test_db.py` тесты «Чистки» на свежей базе падают на `required_norm` (столбцы чата добавляет старт бота, а не `init_db`).
Устройство: решение — `services/purge.py` (резерв → Telegram без транзакции → запись), очередь досье и запуск фоном — `bot/chat/purge.py` (`launch_dossiers`, `resume_dossiers` при старте, `launch_start`),
живой ход — `FastAPI/purge_live.py` (зрители с `live=1`, событие `data_changed{scope:'purge'}` не чаще раза в секунду на чат), адрес — `FastAPI/routers/purge_v1.py` (`?live=1`, `?background=1`; без них — прежние ответы).

## Быстрый запуск фронта (с S06)

```bash
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $PY tools/bench_cold_start.py --device mid --runs 3            # холодный старт: Slow 4G + CPU ×4, байты до готового профиля
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $PY tools/bench_cold_start.py --device mid --skin void         # то же в образе с картинками сцены
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. $PY tools/test_late_css_gate.py                             # «ворота» поздних стилей экранов: медленный, сломанный файл, нет события загрузки (~30 с)
BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod $PY tools/test_js_minify.py            # сжатие JS не меняет ни одного токена (нужен node с acorn из /opt/node-tools)
BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod $PY tools/test_static_delivery_asgi.py   # gzip заранее, ETag/304, версия у каждого файла, «пробный деплой»
```

Устройство: `FastAPI/static_assets.py` (`prepare` — один раз при старте процесса: JS без комментариев и отступов (`minify_js`, переносы строк на месте, поэтому номера строк в ошибках те же), gzip, ETag, своя версия у каждого файла; `respond` — 304, `Content-Encoding`, `Vary`), список файлов — `_STORE` в `FastAPI/main.py`.
Страница ссылается на `/static/<имя>?v=<хэш этого файла>`: деплой перекачивает у игрока только изменённые файлы. Версия выпуска (баннер «Доступно обновление», отчёты об ошибках) — в `<meta name="pv-release">`.
**Правило:** новый CSS с картинками сцены образа подключается лениво (буква в `_SKIN_SCENE_ART`, `FastAPI/main.py`), а не ссылкой в `index.html`: сцена сама просит свой файл (`_scArt`, `app.35.js`), до прихода слой с картинкой невидим.
Аварийный выключатель сжатия JS: переменная окружения `PV_MINIFY_JS=0` (отдаёт исходники как есть). Локальный стенд работает по HTTP/1.1 (6 соединений на адрес), прод — по HTTP/2: число запросов на проде стоит дешевле, чем в замере.

## Остановка и сброс

```bash
runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/preprod-16 stop     # остановить базу
rm -rf /var/lib/postgresql/preprod-16                                                               # полный сброс (потом снова env-setup.sh)
```
