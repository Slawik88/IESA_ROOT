# Состояние: админка 3.0 — пересобрана с нуля

Дата: 20.10.2026 · ветка `claude/eloquent-wozniak-kuwcym`. Полный аудит, критерии и доказательства:
`docs/audits/ADMIN_V3_REDESIGN_2026-10-20.md`.

## Что сделано

Фронтенд `/bot-admin` переписан целиком поверх прежнего API: адреса экранов (`#/player/123`), главная «что требует
внимания», глобальный поиск, стек шторок с «‹» к прошлому шагу и липкой кнопкой, скелетоны вместо заставки, чипы
сроков и причин, карточки игрока и чата со вкладками и «Снять» рядом с наказанием, жалобы с одной кнопкой «Решить»,
рассылка шагами с липкой сводкой, функции с причиной в шторке, владелец чата ищет участника по @нику
(новый `GET /owner/chat/{cid}/members`, лимит `lookup`).

## Файлы

- `FastAPI/static/bot-admin/`: `admin.js` (ядро: API, роутер, оболочка, шторки, компоненты, безопасные действия),
  `admin-home.js`, `admin-people.js`, `admin-lists.js`, `admin-ops.js`, `admin-boot.js`, `admin.css`, `index.html`.
- `FastAPI/routers/bot_admin/page.py` `_TYPES` — порядок совпадает с `<script>` в `index.html` (проверяет тест).
- Новый экран: `route('путь/:id', {section, title, render})` в файле раздела; данные — `ctx.load(path)`; разметка —
  помощники `row/pill/stat/seg/chipPick/callout/field`; обработчики — `data-on` + `on(ctx.view, {...})`.

## Проверки

`node tools/test_admin_safety.js`, `python tools/test_bot_admin_ui_flows.py`, `python tools/admin_stand.py`,
`test_bot_admin_page.py`, `test_bot_admin_ui_contract.py`, PG-наборы админки (кроме двух красных и на master:
`chats_reports`, `promo`).

## Следующий шаг

1. Открыть в Telegram на телефоне: «назад» Telegram, клавиатура над шторкой, светлая тема, `startapp`.
2. Решить судьбу двух красных PG-тестов master (порог варна, список разделов `/me`).
3. Собрать замечания владельца по новой админке.
