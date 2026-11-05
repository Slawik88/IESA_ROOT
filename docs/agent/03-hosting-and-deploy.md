# 03 · Хостинг (DigitalOcean) и деплой

Здесь только факты о том, **где что лежит**. Значений секретов тут нет и быть не должно.

## Общая картина

- Хостинг: **DigitalOcean App Platform**, одно приложение `iesaroot-app`, регион **FRA1** (Франкфурт),
  проект DO «IESA», команда «MyTeam». Сборка — Python-buildpack (Ubuntu 22.04), **без Dockerfile**.
- Панель приложения: `https://cloud.digitalocean.com/apps/9527863a-d5e5-4d5b-82a0-73ee174493fb`
  (вкладки: Overview, Insights, Activity, Runtime Logs, Console, Networking, Settings).
- Репозиторий: GitHub `Slawik88/IESA_ROOT`, ветка **`master`**, Source Directory `/`, **Autodeploy ON**.
- Компоненты приложения:

| Компонент | Что | Как запускается | Маршрут |
|---|---|---|---|
| `iesa-root` | сайт IESA (Django) | build/run command в панели пустые → берётся `Procfile`: `web: cd IESA_ROOT && sh start.sh`; порт 8080 | `/` |
| `predvestnik-bot` | Предвестник (бот + FastAPI) | Run Command: `cd predvestnik_v2 && python -m bot`; порт 8000 | `/predvestnik` |
| `app-d06558f4-…` | Managed **PostgreSQL 17** | — | — |

- Публичные входные IP (Cloudflare-узлы DO): `162.159.140.98`, `172.66.0.96`. Домен: **iesasport.ch**
  (+ служебный `iesaroot-app-8kuyb.ondigitalocean.app`). Записи `www` в DNS нет.

## Как идёт деплой

### Закрытый домашний кабинет: код интеграции 2026-11-01

Домовой запускает собственный HTTP-сервис на `127.0.0.1:8011`; он не должен
публиковаться отдельным внешним портом. `PrivateHouseGateway` перед приложением
Предвестника перенаправляет только непрогнозируемый префикс, вычисленный из
`DOMOVOY_BOT_TOKEN`. Публичный базовый URL — текущий `MINIAPP_URL` или явный
`DOMOVOY_WEB_BASE_URL`; по умолчанию `https://iesasport.ch/predvestnik`.
Маршруты не добавляются в OpenAPI, sitemap и пользовательские страницы игры.

Для loopback-прокси оба бота должны реально запускаться в одном компоненте
через `sh scripts/run_bots.sh` из корня. **Run Command компонента в DO может
перекрывать Procfile**: если там остаётся `cd predvestnik_v2 && python -m bot`,
закрытый backend не поднимется. Не запускать второй экземпляр polling отдельно.
Доступность нового кабинета и фактический Run Command после выкладки надо
проверять отдельно; наличие исходников в master не доказывает Healthy кабинета.
При отсутствующем/несовпадающем токене вход скрыт, при недоступном backend —
нейтральный 503. Игровые маршруты продолжают работать независимо.

Проверено в панели 2026-11-01: фактический Run Command `predvestnik-bot` уже
`sh scripts/run_bots.sh`. Деплой кода `7d43f6565` (deployment
`f9f9afc3-300f-409e-bff7-eae066dec857`) завершился **Success / Live**.
После него закрытая оболочка отвечает 200 с `Cache-Control: no-store`, API без
авторизации и случайный закрытый префикс — 404; `/predvestnik/api/health` — 200.
Проверки не создавали операций и не подделывали пользовательский вход в production.

1. Пуш в `master` → DO собирает **оба** компонента (корневой `requirements.txt` + `constraints.txt` с точными версиями транзитивных пакетов — без него
   сборка сама подтягивала новые aiohttp/starlette и могла уронить ботов; `collectstatic` выполняет buildpack).
   Обновление библиотек — только по процедуре `06-git-and-release.md` → «Обновление зависимостей».
2. Сайт стартует `IESA_ROOT/start.sh`: `migrate` → `update_translation_fields` → `scripts/sync_translations.py` →
   `compilemessages` → `daphne -b 0.0.0.0 -p 8080 --proxy-headers IESA_ROOT.asgi:application`.
   Если миграция упала, скрипт всё равно продолжит старт (смотри логи!).
3. `--proxy-headers`: Django видит реальный IP клиента в `REMOTE_ADDR` (важно для rate-limit).
4. Смена любой переменной окружения в панели **тоже** запускает пересборку/перезапуск.

Проверка после выкладки: Overview показывает `Healthy`; Activity — статус последнего деплоя; Runtime Logs —
ошибки при старте. Затем руками: главная, `/auth/login/`, `/auth/register/`, `/privacy/` отвечают 200.

## Соединения с базой (бюджет 22 слота)

Кластер `db-s-1vcpu-1gb`: `max_connections=25`, 3 зарезервированы → **22 слота на всех**: сайт, Предвестник,
Домовой и служебные подключения DO (бэкап, управление). Снимок 2026-11-03: сайт 12, Предвестник 5, Домовой 1,
служебные ~2 (запаса оставалось 2). Исчерпание даёт на сайте 500 `remaining connection slots are reserved…`.

- **Сайт ходит через PgBouncer** (пул `gBouncer_fix`, порт **25061**, режим transaction, размер 5) — переменная
  `DATABASE_POOL_URL`. Раньше она молча игнорировалась: `dj_database_url.config(default=…)` сначала читает
  `DATABASE_URL`; теперь `settings.py` использует `parse()` (тест `scripts/test_database_settings.py`).
  Не-пул (порт 25060) — только запасной вариант, когда `DATABASE_POOL_URL` пуст.
- **Предвестник — напрямую** (порт 25060): ему нужны advisory lock и LISTEN, через transaction-пул они не работают.
  Потолок процесса `DB_POOL_MAX_SIZE` (по умолчанию 10, из них 3 вне пула). **Домовой**: пул ≤ 3, соединения подписаны
  `application_name=domovoy`.
- Тревога «Здоровье сервиса» считает только `backend_type = 'client backend'`; фоновые процессы Postgres слотов не
  занимают (раньше завышало число на ~5).
- Посмотреть, кто держит слоты: `pg_stat_activity` по `usename`/`application_name`/`state` (read-only). Подключение —
  с доверенного IP (Databases → кластер → Settings → Trusted Sources); строку подключения брать у `doctl databases
  connection <id>` и **не печатать**.
- `doctl` (winget `DigitalOcean.Doctl`) настроен токеном в `%APPDATA%\doctl\config.yaml` (`auth init` без TTY не
  работает — токен кладут в этот файл). Операции на проде (изменение spec/переменных, пуш в `master`) выполняются
  по явному разрешению пользователя.

## Память контейнера ботов

`predvestnik-bot` = `apps-s-1vcpu-0.5gb`: **512 МБ** на Предвестника, Домового (два процесса со своими aiogram/pydantic/aiohttp — по ~75 МиБ только на импорт aiogram) и мини-приложение; в обычное время занято 79–85 % (метрика `memory_percentage` в DO API
`/v2/monitoring/metrics/apps/memory_percentage?app_id=…&app_component=predvestnik-bot`, число перезапусков — `restart_count`). Запаса почти нет: 3 ноября 2026 подъём aiogram до 3.31.0 (+≈107 МиБ на два процесса) увёл контейнер в цикл
перезапусков. Поэтому любое обновление библиотек ботов проверяется `predvestnik_v2/tools/check_full_start.py` (память и запуск целиком) и после выкатки — по метрике памяти.

**5 ноября 2026, ~11:20–11:30 UTC:** контейнер дважды убит по памяти (84 % → всплеск до 97 %), бот не отвечал минуты: после убийства новый экземпляр ждёт advisory lock старого соединения ~60 с, а затем разбирает накопившуюся очередь команд — новый всплеск. Исправлено: matplotlib (график активности) вынесен из процесса бота в короткоживущий `bot/chat/activity_graph_render.py --worker` (рисует по одной картинке, завершается через 30 с простоя), кэш картинок 256 → 48, `MALLOC_ARENA_MAX=2` в `scripts/run_bots.sh`. Замер `check_full_start`: Предвестник 247 → 210 МиБ. Владелец поднял контейнер до `apps-s-1vcpu-1gb-fixed` (1 ГБ), но код продолжает беречь память.

## Переменные окружения (только имена)

Settings → «App-Level Environment Variables» → Edit (там их ~29; значения скрыты, секреты зашифрованы).
Компонентные переменные — Settings → компонент → Environment Variables.

**Сайт:** `SECRET_KEY_DJANGO`, `DEBUG`, `DATABASE_URL`, `DATABASE_POOL_URL` (PgBouncer), `DB_CONN_MAX_AGE`,
`USE_SPACES`, `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_ENDPOINT` (production: Cloudflare R2; исторические имена переменных сохранены),
`CLEVERREACH_CLIENT_ID|CLIENT_SECRET|ACCESS_TOKEN|REFRESH_TOKEN|SENDER_EMAIL|SENDER_NAME` (почта),
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NAME` (бот-администратор сайта), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`. Компонент `iesa-root`: `BOT_USERNAME`, `DATABASE_URL`.

**Предвестник:** `BOT_TOKEN`, `DEVELOPER_ID`, `DB_PATH`, `TIMEZONE_OFFSET`, `MINIAPP_URL`, `RARITY_STICKER_ID`,
`PREDVESTNIK_DATABASE_URL`, `GEMINI_API_KEY`. Компонент `predvestnik-bot`: `ROOT_PATH`, `DATABASE_URL`.

Необязательные для сайта (кнопка/провайдер включается, когда заданы): `MICROSOFT_CLIENT_ID|SECRET`,
`FACEBOOK_CLIENT_ID|SECRET`, `APPLE_CLIENT_ID|TEAM_ID|KEY_ID|PRIVATE_KEY` — **сейчас не используются** (платно/не нужно).

### Перенос файлов из Spaces в Cloudflare R2

Код поддерживает R2 через существующие `SPACES_*` переменные. Само наличие этой
поддержки само по себе не переключает production. На 2026-11-01 сайт переключён
на R2; все 62 исходных объекта скопированы и трижды проверены по SHA-256:
61 публичный объект —
в `iesa-media`, `predvestnik-bot/db.sqlite3` — в закрытом `iesa-backups`.
После подтверждения владельца `iesa-bucket` поставлен на удаление
2026-11-15 в 15:05 Europe/Zurich. Панель DO подтверждает, что начисления за
него уже остановлены; это последний бакет, поэтому подписка Spaces завершена
автоматически. Временный read-only ключ `iesa-r2-migration-read` отозван.
Финальная проверка после удаления: все 61 публичный файл совпадают по SHA-256
через HTTP, закрытая копия БД присутствует в R2 и недоступна через Worker.

Переменные R2 заданы как overrides компонента `iesa-root`, ключ и секрет
помечены Encrypt. Старые app-level переменные Spaces остаются устаревшими
и перекрыты настройками компонента; после удаления бакета они не служат откатом.
Деплой кода `adf39997a` и последующее изменение конфигурации выполнены;
приложение Healthy. Проверены главная, вход, регистрация, privacy и галерея
(HTTP 200); на главной и в галерее ссылки используют Worker, ссылок Spaces нет.
Проверка всех строковых/текстовых полей моделей в живой БД не нашла старого
домена `digitaloceanspaces.com`. Через live Django storage проверены запись,
чтение S3 API, публичное чтение HTTP и удаление временного тестового файла.
Worker по-прежнему возвращает 404 для закрытой копии БД и 405 для PUT.
Cloudflare отклоняет стандартный User-Agent `Python-urllib` (1010), поэтому
HTTP smoke-проверка использует обычный браузерный User-Agent.

- Для R2 нужны `SPACES_ENDPOINT=https://<account>.r2.cloudflarestorage.com`,
  `SPACES_REGION=auto`, ключи R2 в `SPACES_KEY` / `SPACES_SECRET` и бакет медиа
  в `SPACES_BUCKET`. `SPACES_PUBLIC_DOMAIN` — постоянный публичный hostname
  без `https://` и пути. Без него R2-конфигурация останавливается с ошибкой,
  чтобы сайт не продолжал выдавать старые ссылки Spaces.
- Публичный hostname готовится в Cloudflare после проверки скопированных
  объектов. `r2.dev` предназначен для разработки и не заменяет production-домен.
  Смена DNS сайта — отдельное решение владельца, не обязательная часть переноса.
- Без переноса DNS файлы раздаёт Worker `iesa-media.iesa-157.workers.dev`.
  Исходник и конфигурация: `IESA_ROOT/cloudflare/media-worker.mjs` и
  `wrangler.jsonc`. Единственная привязка — `MEDIA=iesa-media`; закрытый бакет
  не подключается к Worker. Разрешены только GET/HEAD, ключи файлов сохраняются.
  Worker использует Free plan (100 000 запросов в сутки); платный план не включён.
  Проверка: `node --test IESA_ROOT/cloudflare/media-worker.test.mjs`.
- R2 не поддерживает объектные ACL: код не отправляет `public-read` / `private`.
  Публичность задаётся на уровне бакета. Для закрытых объектов нужен отдельный
  бакет **без публичного доступа**, включая `predvestnik-bot/db.sqlite3` и дампы БД.
  `BACKUP_BUCKET` задаёт этот закрытый бакет для `scripts/backup_db.py`;
  для R2 совпадение с бакетом медиа запрещено до запуска `pg_dump`.

Повторяемая утилита: `IESA_ROOT/scripts/migrate_spaces_to_r2.py`. Она читает
исходные `SPACES_KEY|SECRET|BUCKET|ENDPOINT` и целевые
`R2_KEY|SECRET|ENDPOINT|BUCKET|PRIVATE_BUCKET` из окружения. Без флагов — только
инвентаризация, `--apply` — копирование, `--verify-only` — повторная проверка.
Каждый объект попадает в публичный либо закрытый бакет по исходному ACL;
базы данных и префиксы `backups/`, `predvestnik-bot/`, `protected/` всегда
попадают в закрытый бакет, даже если старый ACL ошибочно был публичным.
Сохраняются ключи и HTTP-метаданные; содержимое сверяется SHA-256 после чтения
из R2. Совпадающая копия пропускается, отличающаяся не перезаписывается.
Утилита не удаляет данные и не переключает сайт.

Порядок переключения:

1. Создать два закрытых R2-бакета и получить ограниченные ими ключи.
2. На время финального копирования приостановить загрузки/изменение файлов;
   проверить инвентаризацию, затем `--apply` и `--verify-only`. При изменении
   исходных данных или ACL проверка завершается ошибкой; переключать сайт нельзя.
3. Настроить публичный адрес **только** бакету медиа. Проверить, что закрытые
   объекты доступны только с ключами. Бакет резервных копий остаётся закрытым.
4. Проверить абсолютные ссылки на старый Spaces-домен в текстах статей и других
   полях БД: смена Django storage сама их не перепишет. После резервной копии
   выполнить адресную замену домена, сохранив пути объектов.
5. Переключить переменные сайта, дождаться Healthy, проверить изображения,
   галерею, QR-карты и загрузку нового файла. Проверить задачи резервирования:
   регион `auto`, закрытый `BACKUP_BUCKET`, срок хранения. Скрипты старого
   обслуживания `fix_acl_simple.py`, `delete_wrong_files.py`,
   `regenerate_qr_codes.py`, `spaces_lifecycle.py` предназначены для Spaces;
   их нельзя запускать против R2 без отдельной адаптации.
6. Только после этих проверок удалить исходные объекты/бакет и отменить
   подписку Spaces. До этого $5/месяц продолжают начисляться. Удаление требует
   отдельного подтверждения непосредственно перед действием.

   **Состояние на 2026-11-04:** в DO Spaces бакетов нет; единственный ключ Spaces
   (`iesa-media-full`) был в публичной истории git (коммит `9c0ebc9d3`) и отозван —
   ключей Spaces в аккаунте больше нет. Переменные `SPACES_*` уровня приложения
   (`iesa-bucket`, fra1) теперь мёртвые: сайт берёт свои R2-значения уровня
   компонента `iesa-root`, боты `SPACES_*` не читают. В тот же день ротирован
   `SECRET_KEY_DJANGO` (утёк через `.env` в истории; дубль записи в спеке убран).

Проверки подготовки: `.venv/Scripts/python.exe -m unittest discover
-s IESA_ROOT/scripts -p "test_storage_*.py" -v` из корня репозитория.

### Как добавить переменную через браузер

Settings → App-Level Environment Variables → Edit → «Add environment variable» → ключ, значение; для секретов
ставь галочку **Encrypt** → Save (запустится деплой). Проверяй длину введённого значения через JS, не печатая
секрет. Если интерфейс прыгает при узком окне — пользуйся `read_page`/`find`, а не координатами.

## Домен и DNS

Зона `iesasport.ch` лежит в DO: `https://cloud.digitalocean.com/networking/domains/iesasport.ch`
(NS `ns1-3.digitalocean.com`). Что в зоне и зачем — `05-email-and-dns.md`.
**Внимание:** защита Claude Code может блокировать действия с DNS/доменом («DNS / Domain / Cert Changes»);
блокировка выборочная. Если так — подготовь запись полностью, останови и попроси пользователя нажать
нужное поле/кнопку самому.

## Логи и консоль

- Runtime Logs (`…/logs/iesa-root`): окно короткое (последние минуты–часы), поиска нет; видны запросы и
  предупреждения. Для ботов-сканеров WordPress — это нормальный шум.
- Console (вкладка в панели): shell внутри контейнера — здесь запускают `python manage.py …`
  (например `prune_bot_accounts`, `createsuperuser`).
- Резервное копирование БД: `IESA_ROOT/scripts/backup_db.py`; управляемый кластер Postgres сам делает бэкапы.

## Типичные проблемы

| Симптом | Куда смотреть |
|---|---|
| Деплой «Error» | Activity → Build Logs; чаще всего зависимость из `requirements.txt` |
| 500 на одной странице только на проде | `{% static %}` на несуществующий файл (манифест), либо миграция не применилась |
| Новая переменная «не работает» | деплой после её сохранения должен завершиться; имя — точно как в `settings.py` |
| На проде старый CSS/JS | Service worker кэширует статику; поднимай версию кэша в `static/service-worker.js` |
