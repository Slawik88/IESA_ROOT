# 01 · Границы проектов

## Два проекта в одном репозитории

| | Сайт IESA | Предвестник |
|---|---|---|
| Папка | `IESA_ROOT/` (Django-проект, внутри ещё одна `IESA_ROOT/IESA_ROOT/` с настройками) | `predvestnik_v2/` |
| Стек | Django 5.2, Python 3.11, шаблоны + HTMX, PostgreSQL (прод) / SQLite (локально) | aiogram (Telegram-бот) + FastAPI (веб/мини-приложение), asyncpg |
| Где живёт на проде | компонент DO `iesa-root`, домен `https://iesasport.ch` | компонент DO `predvestnik-bot`, путь `https://iesasport.ch/predvestnik` (порт 8000) |
| Запуск | `Procfile` → `web: cd IESA_ROOT && sh start.sh` (Daphne, порт 8080) | `cd predvestnik_v2 && python -m bot` |
| Своя база | `DATABASE_URL` / `DATABASE_POOL_URL` (Managed PostgreSQL 17) | `PREDVESTNIK_DATABASE_URL` |
| Правила работы | этот каталог `docs/agent/` | `predvestnik_v2/AGENTS.md` и его маршрутизация |

## Что общее (осторожно — затрагивает оба)

- **Ветка `master` и автодеплой**: оба компонента собираются из `Slawik88/IESA_ROOT`, ветка `master`,
  Source Directory `/`, Autodeploy ON. Пуш → оба пересобираются и перезапускаются.
- **Корневой `requirements.txt`**: один на оба проекта (ставится в обеих сборках). Добавляя зависимость
  для сайта, помни, что она встанет и в сборку бота; не закрепляй версии, конфликтующие с `predvestnik_v2`.
- **`Procfile`** в корне: содержит и `web` (сайт), и `worker` (бот). Не править без нужды.
- **Приложение DO `iesaroot-app`** (одно) с общей базой Postgres-кластера и общими «App-level» переменными
  окружения — в списке переменных вперемешку ключи сайта и бота (см. `03-hosting-and-deploy.md`).
- **`app.yaml` в `IESA_ROOT/`** — устаревший черновик, **не** реальная конфигурация DO (имена компонентов
  и пути не совпадают). Истина — панель DigitalOcean.

## Что только сайт

`IESA_ROOT/` целиком: приложения `core`, `users`, `blog`, `gallery`, `products`, `notifications`,
шаблоны, статика, переводы (`locale/`), настройки (`IESA_ROOT/IESA_ROOT/settings*.py`),
`docs/audits/` внутри `IESA_ROOT/`. А также: root `requirements.txt` (сайтовая часть), этот `docs/agent/`.

## Что только Предвестник

`predvestnik_v2/` целиком (бот, FastAPI, `infrastructure/`, `services/`, `ai_knowledge/`, его `docs/`,
`.codex/`). Сайтовые задачи туда не заходят: ни правок, ни «заодно».

## Архив / не источник истины

`frontend/` (старый), корневые `*.md` аудитов (`ui_ux_audit*.md`, `FULL_CODE_AUDIT_2026.md`,
`DEEP_BUGS_BACKLOG.md`, …), одноразовые скрипты в корне (`fix_*.py`, `diagnose_*.py`, `ui_*.py`),
`graphify-out/`, `server_output.txt`, `logs/`. Не читать и не править без прямого запроса.

## Как не перепутать

- Путь начинается с `predvestnik_v2/` → Предвестник. С `IESA_ROOT/` → сайт.
- Сообщение коммита сайта начинай с `fix(auth):`, `feat(site):` и т.п.; Предвестника — `feat(ui):`,
  `fix(game):`… (так уже заведено в истории: коммиты `feat(ui): …` в основном про Предвестника).
- Если задача затрагивает общее (`requirements.txt`, `Procfile`, DO-настройки) — скажи пользователю явно,
  что это заденет оба компонента.
