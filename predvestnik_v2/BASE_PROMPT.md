# ПРЕДВЕСТНИК V2 — BASE PROMPT

**Проект:** Telegram-бот + FastAPI мини-апп. Репо: `Slawik88/IESA_ROOT` → `predvestnik_v2/`
**Деплой:** DigitalOcean, URL: `https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik`
**БД:** PostgreSQL (asyncpg + PGAdapter схема `predvestnik`, `?` → `$1,$2...`)
**Бот:** aiogram 3.x, `@IIIPredvestnikIIIBot`

## ИЕРАРХИЯ (железные правила)
```
core/           ← константы/реестры. Без внешних зависимостей
services/       ← бизнес-логика. Без bot.* / FastAPI.*
infrastructure/ ← только SQL в repositories/
bot/            ← Telegram-адаптер
FastAPI/        ← Web-адаптер
```
- `increment_metric(db, uid, METRIC_NAME)` — metric_name из registry, НЕ ключ ачивки
- `auction_lots.item_name` = `"Название||real_item_id"` → split("||")[1]
- `item_id_or_pet_id` = хэш abs(hash(item_id))%10^9, не настоящий id
- `FastAPI/static/app.js` — classic script (не ES-модуль), проверять `node --check`

## КЛЮЧЕВЫЕ ФАЙЛЫ
| Файл | Назначение |
|---|---|
| `core/constants.py` | Все числа (цены, лимиты) |
| `core/registry.py` | ITEMS_REGISTRY, ACHIEVEMENTS, CRAFT_RECIPES |
| `core/themes.py` | THEMES (top/sep/bot/accent) |
| `FastAPI/static/app.js` | JS ~4800 строк — ТОЛЬКО grep+offset Read |
| `services/scheduler.py` | Фоновые задачи |
| `GAME_BIBLE.md` | Полная энциклопедия игрового контента (питомцы/предметы/косметика/экономика/прогрессия/ивенты/команды) — вытащена из кода, не обновляется автоматически |
| `NOT_IMPLEMENTED.md` | Что доделать (пиши "делаем пункт N") |
| `FUTURE_IDEAS.md` | Идеи на потом — после NOT_IMPLEMENTED.md |
| `IMPLEMENTATION_BLOCKS.md` | Готовые планы фич из FUTURE_IDEAS.md (пиши "делаем блок N") |
| `GDD_REBUILD_PLAN.md` | Утверждённый техплан Rebuild 2.0: уровни/CP/боёвка/кланы 2.0/экономика (блоки R0–R8, пиши "делаем блок RN") |
| `PLAYER_CHANGELOG.md` | Пост для TG-канала — простыми словами, без техжаргона. Обновлять в конце КАЖДОЙ сессии, если было что-то видимое игроку (фикс/фича/контент); чисто внутренние правки туда не идут. Новое — в начало файла |
| `admin_audit.md` | Аудит администрирования/DevConsole (БЛОК 21.1) — согласованные фиксы: «делаем пункт A1» |
| `PRODUCT.md` + `DESIGN.md` | Дизайн-контекст (/impeccable): стратегия продукта и визуальная система «Золото в темноте» — читать перед любой UI-работой |

## КРИТИЧЕСКИЕ ПРАВИЛА
- `services/` не импортирует `bot.*` / `FastAPI.*`
- `let/const` только вверху script (TDZ!)
- `${...}` только в backtick-строках
- PostgreSQL ON CONFLICT: `table.column + $N`
- Дублированные JS-функции — проверять `node --check`
- Не трогать `g:\IESA_ROOT\` корень (IESA Django) и `g:\IESA_ROOT\frontend\` (старый React-мини-апп "predvestnik-miniapp", без коммитов с апреля — мёртвый параллельный трек, не наш код)

## ENV (DigitalOcean)
`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_ID=1460945748`, `ROOT_PATH=/predvestnik`, `PORT=8000`, `BOT_USERNAME=IIIPredvestnikIIIBot`

## ПАМЯТЬ (C:\Users\makss\.claude\projects\g--IESA-ROOT\memory\)
- НЕ чистить каждую сессию.
- Раз в несколько сессий — или когда видно, что инфо устарела/тема закрыта — пройтись по `MEMORY.md` и убрать:
  - записи про баги/задачи, которые решены и больше не всплывают
  - project-память про темы, с которых команда явно переключилась
  - дубли/противоречия после новых указаний пользователя
- Цель — экономия токенов: `MEMORY.md` грузится целиком в каждую сессию.

*Обновлено: 2026-07-07 | Доделки: NOT_IMPLEMENTED.md | Идеи: FUTURE_IDEAS.md | Планы фич: IMPLEMENTATION_BLOCKS.md | Админ-аудит: admin_audit.md | Игровой контент: GAME_BIBLE.md*

