# A1 · Стабильность, вход, аватарки, скорость (исследование 2026-10-27)

Пути — от `predvestnik_v2/`. Номера строк на 27.10.2026: **сверять с текущим кодом**, они могли сдвинуться.
Это вывод из кода, а не замеры: прод, `EXPLAIN` и размер инстанса DigitalOcean из облака не видны.

## Главный диагноз: один процесс, один event loop, 10 соединений

Всё живёт в одном процессе: aiogram polling, uvicorn (`lifespan="off"`, один воркер, `bot/__main__.py:133-139`) и около 9 фоновых задач.

Пул asyncpg жёстко ограничен: `min(configured, 10)` в `infrastructure/database.py:32`. Два соединения заняты навсегда:
- advisory lock (`bot/__main__.py:180`);
- LISTEN для баланса (`FastAPI/notifications.py:53-70`).

Остаётся около 8 соединений на всё сразу:
- каждый апдейт Telegram держит соединение на всё время хендлера (`bot/middlewares/db.py:15`, `bot/__main__.py:197`);
- каждый HTTP-запрос держит соединение через `get_db` (`FastAPI/deps.py:25`);
- фоновые циклы.

Нет `acquire`-таймаута и метрики ожидания пула. Прочее: `statement_cache_size=0` (`database.py:166`, каждый запрос парсится заново),
`statement_timeout` 30 с.

## Вход (авторизация Mini App)

Уже чинили: `7150ae5`, `3efeb71` (игры после Telegram-bridge, заголовки), `1ca2e9d`, `35b4348` (VIP-фото). Корень не закрыт и не диагностируется.

Подозрения по коду:
- **initData старше 24 ч → 401.** `FastAPI/auth.py:53` отвергает `auth_date` старше суток. Mini App может висеть свёрнутой дольше, initData сам не
  обновляется. Причина отказа нигде не логируется (`FastAPI/deps.py:81-86`). На 401 клиент стирает `pv_sess` и показывает оверлей Login Widget
  (`FastAPI/static/app.01.js:152`): внутри Telegram это не лечит.
- `INIT_DATA` фиксируется один раз (`app.01.js:35`).
- `telegram-web-app.js` грузится блокирующим тегом из внешнего источника без fallback (`FastAPI/static/index.html:18`). Не загрузился →
  `INIT_DATA=''`, оверлей входа. Тот же класс гонки чинили для игр, но не для основного бандла.
- `api()` без таймаута и ретраев (`app.01.js:149-168`). Таймауты есть только у purge (25 с) и админки (15 с). При пустом пуле запрос просто висит.
- initData попадает в URL WebSocket (`app.01.js:230`, `FastAPI/main.py:349`): то есть в логи прокси.

## Аватарки

- **Аватарки в Mini App — перк VIP.** Не-VIP всегда получают `avatar=null` (`FastAPI/routers/profile.py:204-207,241`). Часть жалоб «не грузятся» штатна.
- Цепочка: `initData.photo_url` (`infrastructure/telegram_photo.py`) → Bot API `getUserProfilePhotos` → `getFile` → скачивание (`profile.py:99-136`).
  Новый `httpx.AsyncClient` на каждую загрузку. Три последовательных запроса по 6 с превышают бюджет 8 с (`profile.py:65`).
- Результат — data-URI прямо в JSON (`/profile/me`, топы, публичные карточки). Кэш 6 ч в памяти процесса (`profile.py:58-59`), при промахе 15 с.
- `file_path` не хранится, качается сразу: протухание ссылок не проблема.
- Нестабильность: кэш обнуляется каждым деплоем; на `/me` и в топах `wait=False` (`profile.py:570`, `FastAPI/routers/leaderboards.py`): при промахе клиент
  получает `null`, загрузка идёт в фоне, повторного запроса нет; шапка запрашивает фото один раз за сессию (ограничение зафиксировано в A13).
- Приватность профиля (пустой `getUserProfilePhotos`) и 404/сбой Telegram. Фолбэк — инициал или созвездие; в админке `onerror` и плейсхолдер.

## Ошибки и мониторинг (чего нет)

- Sentry и глобальных `exception_handler` нет.
- Фронт: только `unhandledrejection` → toast и console (`app.01.js:184`). `window.onerror` нет, телеметрии ошибок нет (`FastAPI/routers/analytics.py` пишет только вкладки).
- `/api/health` всегда отвечает ok и не проверяет БД (`FastAPI/main.py:421`). `/api/ready` проверяет таблицы (`:426`). Какой из них стоит в DO — смотреть в панели.
- Ошибки: кольцевой буфер loguru в памяти на 200 записей (`services/bot_health.py:17`), сбрасывается деплоем.
- Алерты в Telegram есть только по действиям админов (`admin_security.alert`) и суточный дайджест владельцу. Метрик latency, 5xx и ожидания пула нет.

## Тесты и процесс

- ~330 файлов `tools/test_*.py|js`. PG-тесты требуют локальный PostgreSQL (`--dsn`). `tools/ui_smoke.py` — Playwright 320/390/430, админку не проверяет.
  `tools/verify_production_http.py` — health, ready, статика, 401, без авторизации.
- CI: единственный workflow `build-frontend.yml` для старой папки `frontend/`. Тесты на пуш не запускаются, а пуш в master — это деплой.
- Не покрыто: нагрузка и пул, троттлер, срок initData, многопользовательские сценарии.
- Прод: в репозитории только `Procfile` (запускает `python -m bot`), реальные настройки DO в панели. `IESA_ROOT/IESA_ROOT/app.yaml` устарел (`basic-xxs`).
  Один контейнер: бот, uvicorn и фоновые задачи. Деплой: SIGTERM → `SystemExit`. Новый инстанс слушает порт и отвечает `/api/health`, пока не получил
  advisory lock. Запросы блокируются на `create_pool` (до нескольких минут при проблемах с БД). При рестарте теряются in-memory кэши
  (аватарки, переключатели), `_hush` и фоновые досье.

## Топ-10 источников лагов (порядок «эффект / усилие»)

1. **`season_pass.ensure_tables` на каждый запрос.** Три `CREATE TABLE IF NOT EXISTS` на каждый `GET /season-pass/me`
   (`infrastructure/repositories/season_pass.py:7-37`, роутер `:19,26`). У остальных репозиториев есть быстрый путь `_schema_ready`. Исправление: флаг готовности.
2. **Троттлер на read-only методах** (`bot/middlewares/outbound_throttle.py:101-105`). Правка на несколько строк, эффект на все чаты и «чистку».
3. **Пул и соединение на время Telegram:** лениво брать соединение только вокруг SQL (`bot/middlewares/db.py`); advisory lock и LISTEN на прямые соединения;
   основной пул через PgBouncer DO, по размеру 20–30; `acquire(timeout)` и метрика ожидания.
4. **Топ сообщений без кэша и без индекса по дате.** Запросы: `services/leaderboards_v1.py:142-144,185-186`, `infrastructure/repositories/stats.py:61-75,140-190`.
   Агрегат по `daily_user_stats` идёт по фильтру только по `date`, а индекс `(chat_id,date)` (`bot/core/database.py:1318`): вероятный seq scan. WS-событие
   `activity_changed` сбрасывает `_v3TopCache` и запрашивает топ заново (`app.01.js:300-304`), то есть почти на каждое сообщение игрока.
   Исправление: кэш 30–60 с и индекс `(date,user_id)`.
5. **Холодный старт фронта.** 55 render-blocking CSS общим размером 1.5 МБ (`index.html:19-72`), в том числе `skin-scene-d` 341 КБ, `c` 250 КБ, `b` 143 КБ.
   Неминифицированный JS 1.15 МБ (~341 КБ gzip, `FastAPI/main.py:499`), `updates.json` 234 КБ без ETag (`main.py:623`). GZip уровня 9 синхронно в event
   loop на каждый запрос (~50 мс на МБ JS по замеру исследователя). После деплоя все клиенты тянут бандл заново (хэш всего пакета в `?v=`).
   Исправление: прекомпрессия при старте, ленивая загрузка skin-CSS, ETag для `updates.json`.
6. **Heartbeat `/analytics/tab-duration` каждые 15 с** на клиента (`app.01.js:704-707`). Каждый вызов: auth, соединение, UPDATE и две фоновые задачи
   (`deps.py:94,96`). Исправление: раз в 60 с или `sendBeacon`, с накоплением в памяти.
7. **Админский поиск и журнал** (`services/admin_people.py:97-100,256-262,350,408-411`): триграммный GIN на username/name/tag, предрасчитанные last-seen и сумма
   сообщений (есть `presence_v1`), индексы на `moderation_logs`.
8. **`/profile/me`** (`profile.py:456-600`): десятки последовательных запросов на одном соединении плюс data-URI аватарки в JSON. Вызывается при открытии, после
   каждой мутации (`app.01.js:142-155`) и по WS. Исправление: кэш 5–10 с, ETag, аватар отдельным запросом.
9. **Фоновые циклы.** Опрос mafia каждые 2 с (`services/scheduler.py:171-189`, `mafia_online_scheduler.py:31`) и биржи каждые 15 с (`scheduler.py:18,40`);
   `maintenance` и `backfill` держат соединение на время вызовов Telegram. Исправление: ожидание по due-time или LISTEN, соединение только вокруг SQL.
10. **Запись на каждое сообщение в группе.** `record_message` делает не меньше 7 UPSERT (`bot/chat/tracking.py:96-135`), включая горячую строку `chat_settings`, плюс 3 SELECT
    на gate-проверки. Исправление: буфер счётчиков в памяти с периодическим сбросом и `ON CONFLICT ... WHERE IS DISTINCT FROM`.

Побочно: два `BaseHTTPMiddleware` на каждый запрос, включая статику (`FastAPI/main.py:305-320`). Блокирующих `requests`/`time.sleep` в async-коде нет, PIL и matplotlib
вынесены в `to_thread`.

## Что измерять первым (задача S01)

- Пул: размер, свободные соединения и p95 ожидания `acquire`, каждые 10 с. Лаг event loop (сдвиг `loop.time()`). Ожидание в `_reserve_slot` по методам и чатам.
- HTTP: p50/p95/p99 и 4xx/5xx по маршрутам; отдельно 401 с причиной (`stale auth_date`, `bad hash`, пустой заголовок, SDK не загрузился).
- Фронт: `window.onerror`, `unhandledrejection`, неуспешные fetch, «SDK не загрузился», тайминги холодного старта: всё в простой rate-limited эндпоинт `/telemetry`.
- SQL: `pg_stat_statements` top-10; `EXPLAIN` для `_PLAYER_SQL`, топов, `find_violators` и журнала; размеры `daily_user_stats`, `user_chat_stats`, `moderation_logs`.
- Инфраструктура DO: размер инстанса, RAM/CPU, число рестартов, время до Healthy после деплоя.
