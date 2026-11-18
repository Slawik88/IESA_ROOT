# 01 · Границы проектов

## Один проект в этом репозитории (с 2026-11-18)

Здесь только **сайт IESA** и его бот **IESA Helper**. Личные проекты вынесены в отдельные
закрытые репозитории вместе с историей; их код, документы и задачи сюда не возвращаются.

| | Сайт IESA + IESA Helper | Предвестник | Домовой | CKBGL (бокс) |
|---|---|---|---|---|
| Репозиторий | **этот** (`Slawik88/IESA_ROOT`) | `Slawik88/predvestnik` | `Slawik88/domovoy` | `Slawik88/ckbgl-site` |
| Стек | Django, шаблоны + HTMX; бот — webhook Bot API внутри Django | aiogram + FastAPI | aiogram + закрытый FastAPI | статический сайт |
| Production | App Platform, компонент `iesa-root`, `iesasport.ch` | Droplet `projects-fra1` | Droplet `projects-fra1` | Droplet `projects-fra1` |
| Правила | `docs/agent/` | `AGENTS.md`, `docs/HOSTING.md` там | `AGENTS.md`, `docs/HOSTING.md` там | `README.md`, `docs/HOSTING.md` там |

Старый `/predvestnik` на доменах IESA — только HTTP-перенаправление App Platform на новый адрес
Предвестника, не место работы бота.

## Что относится к сайту

`IESA_ROOT/` целиком: приложения `core`, `users` (включая `users/telegram/` — бот IESA Helper:
привязка аккаунта, уведомления, команды), `blog`, `gallery`, `products`, `notifications`,
шаблоны, статика, переводы (`locale/`), настройки (`IESA_ROOT/IESA_ROOT/settings*.py`),
`docs/audits/` внутри `IESA_ROOT/`. А также корневые `requirements.txt`, `constraints.txt`,
`Procfile`, этот `docs/agent/`.

- **`app.yaml` в `IESA_ROOT/`** — устаревший черновик, **не** реальная конфигурация DO (имена компонентов
  и пути не совпадают). Истина — панель DigitalOcean.
- Старая managed-БД сайта содержит таблицы сайта и в схеме `predvestnik` (историческое имя):
  **не удалять** при «чистке» — сайт их использует.

## Архив / не источник истины

`frontend/` (старый), корневые `*.md` аудитов (`ui_ux_audit*.md`, `FULL_CODE_AUDIT_2026.md`,
`DEEP_BUGS_BACKLOG.md`, …), одноразовые скрипты в корне (`fix_*.py`, `diagnose_*.py`, `ui_*.py`),
`graphify-out/`, `server_output.txt`, `logs/`. Не читать и не править без прямого запроса.
Исторические адреса, лимиты и выводы в этих файлах не переопределяют текущий документ хостинга.
В истории git и старых аудитах встречаются `predvestnik_v2/`, `domovoy/`, `scripts/run_bots.sh` —
это прошлое общего репозитория, сейчас этих путей здесь нет.

## Как не перепутать

- Задача про игру, Домового или сайт бокса → работай в их репозитории, не здесь.
- Сообщение коммита сайта начинай с `fix(auth):`, `feat(site):` и т.п.
- Если задача затрагивает общее для сборки (`requirements.txt`, `constraints.txt`, `Procfile`, DO-настройки) —
  скажи пользователю явно: это пересоберёт сайт в App Platform.
