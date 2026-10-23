# IESA website

Django 5.2, Python 3.11, серверные шаблоны и HTMX. Запускной файл —
`manage.py` в этом каталоге. `../frontend/` и `../predvestnik_v2/` относятся
к другому приложению.

## Установка для разработки и проверок

Из этого каталога, PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -r requirements.txt ruff==0.17.1
.\.venv\Scripts\python.exe scripts/check_site.py
```

Для проверки JavaScript нужен Node.js в PATH. На Linux используются
`.venv/bin/python` и обычная установка Node.js.

`scripts/check_site.py` последовательно запускает Ruff, `pip check`, Django
check, поиск забытых миграций, тесты шести приложений и `node --check` для
собственного JavaScript. `--skip-tests` пропускает только тесты.

Настройки `IESA_ROOT.settings_test` используют отдельную тестовую БД, временный
каталог медиа, локальное хранилище и почту в памяти. Быстрый MD5-хешер включён
только в этих настройках. Для PostgreSQL задайте **адрес отдельной тестовой БД**
в `IESA_TEST_DATABASE_URL`; по умолчанию используется SQLite в памяти.
Реальные тесты блокировок строк на SQLite пропускаются. Workflow
`../.github/workflows/check-iesa.yml` запускает оба варианта.

Локальный сервер с существующими настройками разработки:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe manage.py migrate --settings=IESA_ROOT.settings_dev
.\.venv\Scripts\python.exe manage.py runserver --settings=IESA_ROOT.settings_dev
```

`settings_dev` использует `dev.sqlite3`, создавая её копированием `db.sqlite3`
при первом запуске. `settings_test` рабочие базы не копирует и не использует.
Не применяйте `settings_test` для рабочего сервера.

## Структура

| Каталог | Ответственность |
|---|---|
| `IESA_ROOT/` | Настройки, корневые URL, безопасность и хранилища |
| `core/` | Главная, публичные партнёры, преимущества и обращения |
| `users/` | Аккаунты, роли, кабинет партнёра, визиты, встречи, Telegram |
| `users/services/` | Транзакции визитов, PIN, календарная сетка и экспорт |
| `blog/` | Публикации, модерация, комментарии, события и поиск |
| `notifications/` | Уведомления, счётчики, polling и SSE |
| `products/`, `gallery/` | Каталог и галерея |
| `templates/`, `static/` | Общие шаблоны и исходные статические файлы |

`core.Partner` — публичная карточка организации; `users.Partner` — бизнес-профиль
аккаунта, которому принадлежат визиты и встречи. Это разные модели.

Мутации визитов выполняются через `users/services/visit_service.py`.
Редактирование и отмена сохраняют предыдущее состояние и аудит в одной
транзакции. Уведомления этого сервиса регистрируются через `on_commit`.

Для пользовательских данных в JavaScript применяйте `json_script`, а не
`json.dumps(...)|safe`. Быстрое сохранение профиля использует `ProfileFieldForm`
с теми же валидаторами, что и полная форма.

## Сборка и зависимости

Этот `requirements.txt` содержит зависимости сайта. Общий файл в корне
репозитория включает его и дополнительно перечисляет зависимости бота.
DigitalOcean с `source_dir: IESA_ROOT` использует файл из этого каталога.

Перед запуском production нужны переменные окружения из `.env.example`,
миграции и `collectstatic`. `start.sh` прекращает запуск при ошибке миграции.
Миграция `users/0037_social_handles` меняет валидацию Discord/Telegram на
строковые идентификаторы; существующие значения не переписывает.

Подробности аудита, результаты проверок и оставшиеся задачи:
[аудит от 22 октября 2026](docs/audits/2026-10-22-global-code-review/README.md).
