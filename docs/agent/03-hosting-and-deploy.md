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

1. Пуш в `master` → DO собирает **оба** компонента (корневой `requirements.txt`, `collectstatic` выполняет buildpack).
2. Сайт стартует `IESA_ROOT/start.sh`: `migrate` → `update_translation_fields` → `scripts/sync_translations.py` →
   `compilemessages` → `daphne -b 0.0.0.0 -p 8080 --proxy-headers IESA_ROOT.asgi:application`.
   Если миграция упала, скрипт всё равно продолжит старт (смотри логи!).
3. `--proxy-headers`: Django видит реальный IP клиента в `REMOTE_ADDR` (важно для rate-limit).
4. Смена любой переменной окружения в панели **тоже** запускает пересборку/перезапуск.

Проверка после выкладки: Overview показывает `Healthy`; Activity — статус последнего деплоя; Runtime Logs —
ошибки при старте. Затем руками: главная, `/auth/login/`, `/auth/register/`, `/privacy/` отвечают 200.

## Переменные окружения (только имена)

Settings → «App-Level Environment Variables» → Edit (там их ~29; значения скрыты, секреты зашифрованы).
Компонентные переменные — Settings → компонент → Environment Variables.

**Сайт:** `SECRET_KEY_DJANGO`, `DEBUG`, `DATABASE_URL`, `DATABASE_POOL_URL` (PgBouncer), `DB_CONN_MAX_AGE`,
`USE_SPACES`, `SPACES_KEY`, `SPACES_SECRET`, `SPACES_BUCKET`, `SPACES_ENDPOINT` (медиа в DO Spaces),
`CLEVERREACH_CLIENT_ID|CLIENT_SECRET|ACCESS_TOKEN|REFRESH_TOKEN|SENDER_EMAIL|SENDER_NAME` (почта),
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NAME` (бот-администратор сайта), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`. Компонент `iesa-root`: `BOT_USERNAME`, `DATABASE_URL`.

**Предвестник:** `BOT_TOKEN`, `DEVELOPER_ID`, `DB_PATH`, `TIMEZONE_OFFSET`, `MINIAPP_URL`, `RARITY_STICKER_ID`,
`PREDVESTNIK_DATABASE_URL`, `GEMINI_API_KEY`. Компонент `predvestnik-bot`: `ROOT_PATH`, `DATABASE_URL`.

Необязательные для сайта (кнопка/провайдер включается, когда заданы): `MICROSOFT_CLIENT_ID|SECRET`,
`FACEBOOK_CLIENT_ID|SECRET`, `APPLE_CLIENT_ID|TEAM_ID|KEY_ID|PRIVATE_KEY` — **сейчас не используются** (платно/не нужно).

### Перенос файлов из Spaces в Cloudflare R2

Код поддерживает R2 через существующие `SPACES_*` переменные. Само наличие этой
поддержки не означает, что production уже переключён. На 2026-11-01 все 62
объекта скопированы и дважды проверены по SHA-256: 61 публичный объект —
в `iesa-media`, `predvestnik-bot/db.sqlite3` — в закрытом `iesa-backups`.
Исходный `iesa-bucket` пока сохраняется, сайт ещё не переключён.

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
