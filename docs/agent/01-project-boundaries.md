# 01 · Границы проектов

## Три проекта в одном репозитории (production с 2026-11-13)

| | Сайт IESA | Предвестник | Домовой |
|---|---|---|---|
| Папка | `IESA_ROOT/`, настройки в `IESA_ROOT/IESA_ROOT/` | `predvestnik_v2/` | `domovoy/` |
| Стек | Django, шаблоны + HTMX | aiogram + FastAPI, asyncpg | aiogram + закрытый FastAPI-интерфейс |
| Production | App Platform, компонент `iesa-root`, `iesasport.ch` | Droplet `projects-fra1`, `predvestnik.service` | тот же личный Droplet, `domovoy.service` |
| Запуск | `Procfile` → `web: cd IESA_ROOT && sh start.sh`, порт 8080 | отдельный systemd-процесс, порт 8000 через nginx | отдельный systemd-процесс, закрытый порт 8011 через gateway |
| База | Managed PG17, `DATABASE_URL` / `DATABASE_POOL_URL` | локальная PG17, БД `predvestnik`, `DATABASE_URL` | локальная PG17, БД `domovoy`, `DOMOVOY_DATABASE_URL` |
| Правила | `docs/agent/` | `predvestnik_v2/AGENTS.md` | `domovoy/AGENTS.md` |

Независимый адрес Предвестника и закрытый вход Домового — в
[`03-hosting-and-deploy.md`](03-hosting-and-deploy.md). Старый `/predvestnik`
на доменах IESA — только HTTP-перенаправление, не место работы бота.

## Что общее (осторожно — затрагивает несколько проектов)

- **Репозиторий и ветка `master`** общие. Автодеплой из неё обновляет только сайт IESA.
  Боты обновляются отдельной выкладкой на Droplet; их переменные и данные не переносить заново.
- **Корневые `requirements.txt` и `constraints.txt`** общие. Изменение зависимостей проверять
  для затронутых проектов; уже работающий venv ботов не меняется от одного пуша в GitHub.
- **`Procfile`** оставлен только для сайта. Старый `scripts/run_bots.sh` — исторический
  совместный лаунчер, не текущий production и не способ выкладки новых проектов.
- **`iesaroot-app`** содержит сайт и его managed DB. Неиспользуемые переменные ботов
  из него удалены. Личные службы используют `/etc/iesa/*.env` на своём сервере.
- **`app.yaml` в `IESA_ROOT/`** — устаревший черновик, **не** реальная конфигурация DO (имена компонентов
  и пути не совпадают). Истина — панель DigitalOcean.

## Что только сайт

`IESA_ROOT/` целиком: приложения `core`, `users`, `blog`, `gallery`, `products`, `notifications`,
шаблоны, статика, переводы (`locale/`), настройки (`IESA_ROOT/IESA_ROOT/settings*.py`),
`docs/audits/` внутри `IESA_ROOT/`. А также: root `requirements.txt` (сайтовая часть), этот `docs/agent/`.

## Что только Предвестник

`predvestnik_v2/` целиком (бот, FastAPI, `infrastructure/`, `services/`, `ai_knowledge/`, его `docs/`,
`.codex/`). Сайтовые задачи туда не заходят: ни правок, ни «заодно».

## Что только Домовой

`domovoy/` целиком. Общий технический вход через gateway не делает Домового частью
игры: не добавлять его в UI Предвестника и не раскрывать приватный путь.
Runtime, БД, права и настройки Домового самостоятельны.

## Архив / не источник истины

`frontend/` (старый), корневые `*.md` аудитов (`ui_ux_audit*.md`, `FULL_CODE_AUDIT_2026.md`,
`DEEP_BUGS_BACKLOG.md`, …), одноразовые скрипты в корне (`fix_*.py`, `diagnose_*.py`, `ui_*.py`),
`graphify-out/`, `server_output.txt`, `logs/`. Не читать и не править без прямого запроса.
Исторические адреса, лимиты и выводы в этих файлах не переопределяют текущий документ хостинга.

## Как не перепутать

- Путь начинается с `predvestnik_v2/` → Предвестник, `domovoy/` → Домовой, `IESA_ROOT/` → сайт.
- Сообщение коммита сайта начинай с `fix(auth):`, `feat(site):` и т.п.; Предвестника — `feat(ui):`,
  `fix(game):`… (так уже заведено в истории: коммиты `feat(ui): …` в основном про Предвестника).
- Если задача затрагивает общее (`requirements.txt`, `Procfile`, DO-настройки) — скажи пользователю явно,
  какие действующие службы или сборки это затронет. Общей production-БД у трёх проектов больше нет.
