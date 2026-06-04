# 🔮 ПРЕДВЕСТНИК V2 — КОНТЕКСТНЫЙ ПРОМТ ДЛЯ ИИ

> Вставь этот промт в начало нового чата чтобы ИИ сразу был в курсе проекта.

---

## ПРОЕКТ

**Предвестник V2** — Telegram-бот (игровой, с экономикой, питомцами, аукционом, браком) + FastAPI мини-апп (сайт внутри Telegram и в браузере).

- **Репозиторий:** `Slawik88/IESA_ROOT` → папка `predvestnik_v2/`
- **Деплой:** DigitalOcean App Platform, компонент `predvestnik-bot` (Web Service, port 8000)
- **URL мини-апп:** `https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik`
- **БД:** PostgreSQL (asyncpg + PGAdapter), схема `predvestnik`
- **Бот:** aiogram 3.x, long-polling, `@IIIPredvestnikIIIBot`

---

## ИЕРАРХИЯ КОДА (железные правила)

```
core/           ← константы и реестры. БЕЗ внешних зависимостей
services/       ← бизнес-логика. БЕЗ импортов bot.* или FastAPI.*
infrastructure/ ← репозитории БД. Только SQL, никакой логики
bot/            ← адаптер Telegram. handlers → services + infrastructure
FastAPI/        ← адаптер Web. routers → services + infrastructure
```

**Нарушения = баги:**
- Никаких inline-импортов внутри функций (только вверху файла)
- `services/` никогда не импортирует `bot.*` или `FastAPI.*`
- Новая DB-операция → только в `infrastructure/repositories/*.py`
- Handler — только UI: форматирование, вызовы, отправка

---

## СТЕК И КЛЮЧЕВЫЕ ФАЙЛЫ

| Файл | Назначение |
|---|---|
| `core/constants.py` | Все игровые числа (цены, лимиты, кулдауны) |
| `core/registry.py` | ITEMS_REGISTRY, ACHIEVEMENTS, CRAFT_RECIPES, EXPEDITIONS_DATA |
| `core/themes.py` | THEMES — темы профиля с top/sep/bot/accent |
| `bot/__main__.py` | Запуск: пул БД → FastAPI uvicorn → advisory lock → бот |
| `bot/middlewares/db.py` | Каждое сообщение: XP, квесты (messages_in_chat_today), ачивки (talker) |
| `bot/middlewares/streak_mw.py` | Стрик, marriage_days_total, persistent ачивка |
| `FastAPI/main.py` | Точка входа (~170 строк): роутеры, auth, WS, отдача статики |
| `FastAPI/static/index.html` | HTML-каркас мини-аппа (~126 строк) |
| `FastAPI/static/app.css` | Все стили мини-аппа (~279 строк) |
| `FastAPI/static/app.js` | Вся клиентская логика (~1825 строк, classic script) |
| `FastAPI/notifications.py` | In-process Queue для WebSocket push-уведомлений |
| `services/scheduler.py` | Фоновые задачи: экспедиции, аукцион, сундуки, обмен |

---

## ТЕКУЩЕЕ СОСТОЯНИЕ МИНИ-АПП

**Реализовано на сайте (FastAPI роутеры):**
- `/profile/me` — профиль, баланс, питомцы, стрик, ачивки
- `/zoo/` + `/zoo/expeditions` + `/zoo/pet/{id}` + `/zoo/move` + `/zoo/feed` + `/zoo/boost`
- `/gacha/` + `/gacha/spin`
- `/craft/` + `/craft/{id}`
- `/quests/{chat_id}`
- `/auction/lots?page=N` + `/auction/bid` + `/auction/create` + `/auction/reserved`
- `/duels/active|history|challenge|decline`
- `/achievements/`
- `/themes/` + `/themes/buy` + `/themes/equip`
- `/streak/calendar`
- `/exchange/` + `/exchange/convert`
- `/dark-mora/contrabanda` + `/dark-mora/ritual` + `/dark-mora/merchant-status`
- `/marriage/` + `/marriage/bank`
- `/daily-deal/` + `/daily-deal/buy`
- `/promo/redeem`
- `/wallet/history`
- `/top/local/{chat_id}` + `/top/global`
- `/inventory/` + `/inventory/open-egg` + `/inventory/apply-dust`
- `/shop/` + `/shop/buy`

**Навигация (5 вкладок):** Профиль (3 подвкладки) | Зоопарк | Арена | Рынок (6 подвкладок) | Коллекция

**WebSocket:** `/ws/{user_id}` — реалтайм уведомления (expedition_done, duel_challenge)

---

## КЛЮЧЕВЫЕ ТЕХНИЧЕСКИЕ ДЕТАЛИ

### БД
- Схема `predvestnik` (не public). Поиск через `search_path`
- `PGAdapter` конвертирует SQLite-стиль (`?`) в PostgreSQL (`$1,$2...`)
- `user_chat_stats` — статистика per-chat; `daily_user_stats` — по дате для топов
- **Топ периодов** — через `daily_user_stats`, НЕ через `user_messages_count_per_day`
- `auction_lots.item_name` формат: `"Название||real_item_id"` (суффикс для resolve)

### Аукцион
- `item_id_or_pet_id` в БД = числовой хэш (`abs(hash(item_id)) % 10^9`)
- **Реальный item_id** всегда извлекается из `item_name.split("||")[1]`
- При создании лота через сайт — удалять предмет из инвентаря (эскроу)
- При разрешении лота — `services/auction.py` берёт item_id из item_name, не из item_id_or_pet_id

### Профиль и темы
- Темы имеют: `top`, `sep`, `bot`, `accent` — обволакивают ВЕСЬ профиль
- `bot/handlers/identity.py` — полный профиль с секциями через `t_sep`
- Мобильный дизайн: без fixed-width, секции через emoji-разделители

### Квесты и ачивки
- `services/quests.py::increment_metric` — вызывается из middleware И из FastAPI
- `services/achievements.py::increment_metric` — аналогично
- `vow_keeper` (marriage_days_total) — инкрементируется в `streak_mw.py` каждый день
- Если бот добавил ачивку ПОСЛЕ того как игрок уже выполнил условие → backfill в `/marriage/` роутере

### Темная тема сайта
- `html { color-scheme: dark only; }` — всегда тёмная, не зависит от Telegram/системы

---

## ПРАВИЛА НАПИСАНИЯ КОДА

1. **DRY / KISS / YAGNI** — не писать код "на будущее"
2. **Константы** — только в `core/constants.py`
3. **Импорты** — только вверху файла, никаких inline
4. **Плавающая точка** — `int(mora * MULT) - mora`, НЕ `int(mora * (MULT - 1.0))`
5. **Tree-форматирование** — замена последнего `├` через `text.rfind("├")`, НЕ срезом
6. **Деструктивные действия** — диалог ✅/❌
7. **JS в HTML** — нет `let varName` внутри функциональных блоков (TDZ!), только вверху скрипта
8. **Template literals** — `${...}` работает только внутри backtick-строк, не в `'...'`

---

## ЧАСТЫЕ БАГИ (НЕ ПОВТОРЯТЬ)

| Баг | Причина | Правило |
|---|---|---|
| Сайт пустой | `let varName` объявлен после первого использования (TDZ) | Все `let/const` — в самое начало `<script>` |
| `SyntaxError: Unexpected '{'` | `${expr}` внутри обычной строки `'...'` | Использовать template literal `` ` `` |
| Аукцион "948026284" в инвентаре | `item_id_or_pet_id` — хэш, не настоящий id | Извлекать из `item_name.split("||")[1]` |
| Глобальный топ 500 | `GROUP BY s.user_tg_id` без `u.user_tg_username` | Добавлять все не-агрегированные колонки |
| `reserved_mora` ambiguous | PostgreSQL ON CONFLICT без квалификатора | `user_reserve.reserved_mora + $3` |
| Зоопарк пустой | `_zooTab='active'` но вкладка называется `'nursery'` | Синхронизировать имена вкладок |
| Дублированные функции | `swArena`, `swMkt`, `doSpin` объявлялись дважды | Одна функция — одно определение |

---

## ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (DigitalOcean)

| Переменная | Значение | Где используется |
|---|---|---|
| `BOT_TOKEN` | (encrypted) | Предвестник бот |
| `DATABASE_URL` | postgres://doadmin:... | Postgres (общая с IESA) |
| `DEVELOPER_ID` | 1460945748 | Developer-only команды |
| `TIMEZONE_OFFSET` | +3 hours | Дефолтный TZ бота |
| `MINIAPP_URL` | https://...ondigitalocean.app/predvestnik | Кнопка меню бота |
| `BOT_USERNAME` | IIIPredvestnikIIIBot | Telegram Login Widget |
| `RARITY_STICKER_ID` | CAACAgIA... | Стикер Рарити |
| `ROOT_PATH` | /predvestnik | Prefix stripping middleware |
| `PORT` | 8000 | FastAPI (DigitalOcean Web Service) |

---

## КОД, КОТОРЫЙ НЕ ТРОГАЕМ

- `g:\IESA_ROOT\` корень — IESA платформа (Django), НЕ трогаем вообще
- Только `predvestnik_v2/` — наш код

---

*Последнее обновление: 2026-06-03*
