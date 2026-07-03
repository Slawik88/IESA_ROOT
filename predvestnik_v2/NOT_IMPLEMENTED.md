# NOT IMPLEMENTED — Предвестник V2

> Конкретные доработки уже начатых механик. "Делаем пункт N" → берём отсюда, фиксим, `node --check` / `py_compile`, commit+push.
> Обновлено: 2026-06-30 (аудит кодовой базы).

---

## БЛОК 20 (остаток): КОСМЕТИКА 2.0 И КОНСТРУКТОР НАГРАД

> БЛОК 20 «Глобальный ремастер» — запущен, частично выполнен.
> Закрыто: история кошелька (БЛОК 15 Ш1) ✅, фикс удаления сезона (аудит 2026-06-28) ✅.
> Ниже — только нереализованные части.

### 20.A — Примерочная (Dressing Room Modal)
Fullscreen-модалка предпросмотра косметики с тяжёлыми эффектами:
- Партиклы/глитч — только внутри модалки, свой `requestAnimationFrame`-цикл
- Обязательный `cancelAnimationFrame` + dispose WebGL/текстур + снятие всех `addEventListener` при закрытии (главная точка утечек)
- Object pooling для частиц (не create/destroy каждый кадр)
- `will-change` — точечно, снимается после завершения анимации
- `prefers-reduced-motion` + тоггл «Отключить анимации» в настройках (per-user, в настройках)
- В общем гриде — только лёгкие статичные превью (`webp`), без Canvas/WebGL
- Lazy loading карточек через `IntersectionObserver`

### 20.B — Пресеты косметики ✅ ЗАКРЫТО 2026-06-30
Реализованы: таблица `cosmetic_presets`, API GET/POST/DELETE/apply, UI-строка чипов в каталоге.
Ограничение: 5 пресетов на пользователя. Apply применяет только owned-предметы из пресета.
Остаток (если нужно): мини-превью карточки в чипе, переименование пресета.

### 20.C — Конструктор и администрирование БП ✅ ЗАКРЫТО 2026-06-30
- SQL-инъекции не было: `/dev/items` читает `ITEMS_REGISTRY`, не `information_schema`.
- Удаление сезона: исправлено ранее в коммите `7036d402` (явное сообщение о registry-откате).
- UI не обновлялся: `devBpWeekendSet` (нет `loadBpXpActions`) и `devBpCopy` (нет `loadBpTable`) — оба исправлены.
- `devBpCopy` теперь переключает отображение на целевой сезон и сразу показывает скопированное.

### 20.D — Журнал admin-действий ✅ ЗАКРЫТО 2026-06-30
`admin_log.add_sys()` — системные действия (season_upsert, season_delete, bp_freeze/unfreeze) пишутся
в `admin_grant_log` с `target_id=0`. DevConsole «Журнал выдач» рендерит их отдельным стилем.
Грантовые выдачи уже логировались ранее.

### 20.E — Синхронизация тем (race condition) ✅ НЕ АКТУАЛЬНО
Проверка 2026-06-30: `GET /themes` каждый раз читает DB — кеша нет (нет `lru_cache`, нет `updated_at`-TTL).
ETag не нужен. Если в будущем добавится server-side кеш — вернуться к версионированию.

---

## БЛОК 21: АУДИТ И РЕМОНТ АДМИНИСТРИРОВАНИЯ

> Источник: запрос 2026-06-30.
> Порядок: сначала 21.1 (создать аудит-файл и согласовать список), потом остальные пункты.

### 21.1 — Создать admin_audit.md
Провести полный аудит всего, что касается администрирования чата и панели разработчика (DevConsole):
- Найти баги, нелогичные моменты, места где механика работает не так как должна
- Найти неудобства UX/UI — оформить как список с приоритетами
- Зафиксировать всё странное и подозрительное
- Оформить как `predvestnik_v2/admin_audit.md` → согласовать с пользователем → только потом вносить изменения в код

### 21.2 — DevConsole: быстрый переход в профиль Telegram ✅ ЗАКРЫТО
Исправлено 2026-06-30. В `static/app.08.js` в карточку досье добавлены две кнопки:
- `tg://user?id={uid}` — «🔗 Открыть в TG» (всегда работает)
- `https://t.me/{username}` — `@username` (только если username известен)

### 21.3 — Топ: скрывать ушедших из чата ✅ ЗАКРЫТО
Исправлено 2026-06-30. Два места в `infrastructure/repositories/stats.py`:
- `_global_user_ids` (строки 67-72): добавлен `AND is_left = FALSE` → затронуло 6 глобальных топов (мора, алмазы, питомцы, ачивки, стрики, аукцион)
- `get_top_messages_global` (строки 135-148): добавлен `WHERE s.is_left = FALSE`
Web `/top/global` и бот-кнопки «Глобально» теперь исключают ушедших игроков.

### 21.4 — Система банов: два уровня доступа

**Текущее поведение:** бан перекрывает весь доступ к боту.

**Нужно разделить:**

1. **Игровой бан** → нет доступа к игровой инфраструктуре (гача, зоопарк, экспедиции, аукцион, магазин, профиль...)
2. **Административные функции** → доступны ВСЕГДА, бан не влияет (`бот топ`, `бот кто я`, получение предупреждений и т.п.)

**Блокировка сайта для забаненных на уровне HTTP:**
`бот сайт` — не единственный способ попасть на сайт (другой игрок может поделиться ссылкой).
Блокировать в FastAPI `require_tg_user` deps или отдельном middleware — проверять бан и возвращать `403 Forbidden` до входа в любой игровой эндпоинт.

---

## ✅ БЛОК 22: БИРЖА — РАСШИРЕНИЕ ФУНКЦИЙ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 22.1: `crypto_holdings.avg_buy_price` — средневзвешенная цена покупки. Обновляется при каждой покупке. Отображается в детальном виде монеты: «P&L: +1234 🪙 (+5.6%) · ср. цена 800 🪙». В списке — цветной значок +/-. В шапке портфеля — суммарный P&L.
- 22.2: `crypto_trades` — лог сделок; `GET /exchange/crypto/history?coin_id=X` — история по монете; кнопка «📋 История сделок» в детальном виде. `crypto_watchlist` + `POST /exchange/crypto/watchlist/{coin_id}` — избранные монеты (звёздочка ☆/★ в каждой строке). `GET /exchange/crypto/top` — топ-10 трейдеров по стоимости портфеля (кнопка 🏆 в шапке). Алерты на цену — отложено (требуют scheduler + уведомления).

---

## ✅ БЛОК 23: АУДИТ КОНСИСТЕНТНОСТИ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 23.1: ACHIEVEMENTS и QUESTS чистые — нет egg-метрик. `gacha_spins`/`gacha_spins_today` уже были на замену яйцам. Ничего не требовалось убирать.
- 23.2: Полный grep по репо. GvG — нет ни строки кода. Egg-кнопки в боте и JS удалены ещё в БЛОК19. `crystal_egg_chance` в FOX_BONUSES — функциональный ключ (даёт spin_token_diamond), текст верный «🎟 Алмазный Жетон». Удалено мёртвое поле `double_egg_chance` из всех 10 уровней `TURTLE_BONUSES` (было 0.0 везде, нигде не читалось). Обновлена таблица черепахи в `BOT_AUDIT.md`.

---

## БЛОК 13 (остаток): ТЕНЕВЫЕ РЕЛИКВИИ

> Ядро реликвий реализовано: каталог, покупка, бонусы, бот-команды ✅
> Не сделано: ивентовая часть и перенос на сайт. Полный план — IMPLEMENTATION_BLOCKS.md БЛОК 13.

### 13.X — Теневые реликвии (ивентовая часть)
- Теневые реликвии (4 шт.) задуманы как награда ивента «Теневой Торговец»; в магазине **не продаются**
- Таблицы `shadow_relics` / `user_shadow_relics` — **не созданы** (нет миграции)
- Хендлер выдачи теневой реликвии победителям ивента — **не реализован**
- Вкладка «Реликвии» на сайте — **bot-only**, read-only + покупка на веб-стороне отсутствуют

---

## БЛОК 24: МЁРТВЫЕ ИВЕНТ-МЕХАНИКИ

> Найдено аудитом 2026-06-30. Константы и темы объявлены, но хендлеров / scheduler-задачи нет.

### 24.A — Ивент «Теневой Торговец» — нет хендлера
`core/constants.py:521-525` содержит: `DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS`, `WINNERS`, `REWARD_MIN/MAX`, `ACTIVE_MINUTES`.
- Нет записи в `services/scheduler.py`
- Нет логики отбора победителей и выдачи Тёмной Моры
- Нет выдачи теневой реликвии (привязан к БЛОК 13.X)
- Решить: реанимировать (полный план в IMPLEMENTATION_BLOCKS.md БЛОК 13) или удалить мёртвые константы

### 24.B — Ивент «Предательство» — ✅ ЗАКРЫТО
`core/constants.py:528-530`: `DARK_MORA_BETRAYAL_REWARD`, `TOP_STREAK`, `SILENCE_DAYS` — **удалены**.
Механика «исчезнуть после топ-активности» признана нежизнеспособной.

### 24.C — Mythic-темы с `source="event"` без механики выдачи
`core/themes.py`: `theme_eclipsed` (строка ~286), `theme_void` (~294), `theme_bloodmoon` (~468).
- Все три заявлены как ивент-награды (`"source": "event"`), но **нигде в коде не выдаются**
- Нет ни одного `set_user_theme` / `grant_theme` для этих ключей
- **Решение отложено** — не трогать до запуска ивент-системы (БЛОК 13.X / БЛОК 24.A)


---

## БЛОК 25: DEV-MOD — ОВЕРЛЕЙ ДЛЯ РАЗРАБОТЧИКА НА САЙТЕ

> Идея 2026-06-30. Режим отладки поверх обычного мини-аппа, доступный только DEVELOPER_ID и хелперам.
> Это НЕ отдельная страница — это плавающая панель поверх обычного сайта.

### 25.A — Что такое dev-mod
Плавающая отладочная панель, которая:
- Показывает сырые DB-поля рядом с UI-элементами (откуда берётся каждое число)
- Помечает расхождения бот/сайт (стрик, уровень, монеты — красным если не совпадают)
- Даёт сырой JSON ответов текущих API-эндпоинтов
- Показывает все флаги игрока: is_left, is_banned, все метрики, все timestamps
- Показывает айди каждого предмета

### 25.B — Архитектура реализации

**Backend:**
- `DEVELOPER_HELPER_IDS: list[int]` в `core/constants.py` — список доп. ID с dev-доступом (хелперы)
- `FastAPI/routers/dev_overlay.py`: dep `require_dev_user` проверяет `uid in {DEVELOPER_ID} | set(DEVELOPER_HELPER_IDS)`
- `GET /api/dev/overlay/{user_id}` → полный raw-слепок: users, user_chat_stats, pets, wallet, metrics

**Frontend (`static/app.devmode.js` — отдельный файл):**
- В `main.py` подключается **только** если `tg_user_id in DEVELOPER_IDS` (рендерится в шаблон)
- Плавающая кнопка 🛠 (position: fixed, bottom-right) → toggle панели
- Keyboard shortcut: `Ctrl+Shift+D`
- Три вкладки:
  - **«Данные»** — сырые поля из БД для текущего просматриваемого игрока
  - **«API»** — последние 10 fetch-запросов: URL / статус / время / payload
  - **«Расхождения»** — автодетект по известным точкам из БЛОК 26

---

## БЛОК 26: ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ — АУДИТ РАСХОЖДЕНИЙ

> Обнаружено 2026-06-30: стрик в боте «15 дн.», на сайте «23» — расходятся.

### 26.1 — Стрик: бот vs сайт ✅ ЗАКРЫТО
Исправлено 2026-06-30. Баг: сайт читал `MAX(streak) ORDER BY streak DESC LIMIT 1` без фильтра `chat_id = 0`,
брал стрик из любого чата (в т.ч. устаревшие per-chat строки). Бот всегда читал `chat_id = 0`.
Исправлено в `FastAPI/routers/streak.py` (calendar) и `FastAPI/routers/profile.py` → теперь используют
`get_global_streak(db, uid)` из `infrastructure/repositories/streak.py` — единый источник правды.

### 26.2 — Общий аудит единого источника правды на сайте ✅ ЗАКРЫТО 2026-07-01
Полный отчёт: `SSOT_AUDIT.md`. Найдено и исправлено 6 расхождений (запрос «делай всё»):
1. ✅ Аукцион: лимит лота 10→снят (равен инвентарю, как в боте)
2. ✅ Аукцион: мин. ставка теперь с бэка (`min_bid_floor` в `/auction/lots`), не хардкод
3. ✅ XP-бар: `xp_per_level` теперь в `/profile/me`, не хардкод `3000`
4. ✅ Бейджи предметов: `dup_count` в реестре вместо хардкода, дублирующий бейдж study_notes убран
5. ✅ Таблицы редкости объединены в `RARITY_META` (app.01.js) — попутно найден и исправлен
   реальный дрейф цвета `legendary` (#e8c45a vs #e8b54d) между двумя экранами
6. ✅ dev-текст теперь тянет `xp_per_level` из уже существующего API-поля

Структурный аудит (god-файлы/god-функции, SQL вне repositories/) — `CODE_STRUCTURE_AUDIT.md`.

---


---

## ✅ БЛОК 27: ВАРП-КОМАНДЫ — АУДИТ И УЛУЧШЕНИЕ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 27.1: "пользователь не найден" и "укажи цель" теперь разные сообщения (`_rest == "error_user_not_found"`)
- 27.1: приватный чат → сообщение вместо silent return
- 27.1: `safe_html(warp_name)` в подсказке
- 27.1: добавлен `self_response` к 6 NSFW-командам без него (ласкать, облизать, поцеловать страстно, нашептать на ухо, флиртовать, обнять сзади)

---

## БЛОК 28: «БОТ РЕСТ» — СИСТЕМА ЗАЩИТЫ ОТ ЧИСТКИ ✅ ЗАКРЫТО 2026-06-30

> Реализовано в сессии 2026-06-30 (prod push).

### 28.1 — Алиасы и основная команда ✅
- `бот рест` — основная команда (временный щит)
- Алиасы: `отдых`, `защита`, `защитить`
- `бот иммунитет` — отдельная команда постоянной защиты (без алиасов)
- «абсолют» алиас удалён

### 28.2 — Фикс: @username не в БД → молчание ✅
Если @username не найден — бот отвечает понятным «❌ Пользователь не найден» вместо молчания.
Исправлено в `cmd_protect`, `cmd_immune`, `cmd_unprotect`.

### 28.3 — «бот кто рест» / «бот ресты» ✅
Новые команды: показывают список всех в ресте или с иммунитетом в чате.
Разделяет иммунитет (∞) и рест (до даты).

### 28.4 — Чистка: явные метки защиты ✅
`бот чистка` теперь явно указывает: `[иммунитет ∞]` или `[рест до дд.мм]`.

---

## БЛОК 29: ГЛОБАЛЬНЫЕ ПЕРЕКЛЮЧАТЕЛИ МОДУЛЕЙ (DEV ПОЛЗУНКИ) ✅ ЗАКРЫТО 2026-06-30

> Реализовано в сессии 2026-06-30 (prod push).

### 29.1 — Таблица `system_flags` ✅
8 флагов: tab_bp, tab_zoo, tab_market, tab_auction, tab_economy, tab_purge, tab_cosmetics, tab_quests.

### 29.2 — Dev-консоль: ползунки в карточке «🔌 Модули системы» ✅
Тоггл-слайдеры в dev-вкладке. POST `/admin/dev/flags/{key}` — девелопер только.

### 29.3 — Сайт: блокировка вкладок ✅
`_applySysFlags()` вызывается из `loadProfile()` (флаги приходят в `/profile/me` → нет лишнего запроса).
Отключённая вкладка показывает заглушку 🚧.

### 29.4 — Бот: блокировка команд ✅
`feature_guard(message, db, key, label)` в entry-point хэндлерах:
bp, магазин, гача, аукцион, переводы, чистки.

---

## БЛОК 30: РЕФАНД КОСМЕТИКИ И НОВАЯ ЦЕНОВАЯ ИЕРАРХИЯ ✅ ЗАКРЫТО 2026-06-30

> Источник: запрос 2026-06-30.

### 30.1 — Одноразовый скрипт рефанда ✅
- `scripts/cosmetics_refund.py` — рефанд по СТАРЫМ ценам (3 эпохи из git-истории).
- Идемпотент: таблица `cosmetic_refund_log`; повторный запуск пропустит уже обработанные.
- `--dry-run` для превью без изменений БД.
- Stars-покупки помечаются отдельно (ручной возврат через BotFather).

### 30.2 — Новая ценовая иерархия ✅
- Все предметы в `core/cosmetics.py` обновлены: common=250✨, rare=440✨, epic=630✨, legendary=820✨, mythic=1000✨.
- `vip_required=False` для всех (VIP влияет только на отображение, не покупку).
- BP/VIP/reward-предметы получили `price`, сохранив `source` для `sync_auto_grants`.

### 30.3 — Убрать Stars полностью ✅
- `services/cosmetics.py`: удалены `_RARITY_STARS` и поле `stars_price` из `_public()`.
- `FastAPI/routers/cosmetics.py`: удалён endpoint `/stars-invoice` и `StarsInvoiceRequest`.
- `bot/handlers/payments.py`: удалён `elif payload.startswith("cosmetic:")` + `cosmetic:` из `pre_checkout_query`.

### 30.4 — VIP-гейт через `is_vip_locked()` ✅
- `is_vip_locked()` в `core/cosmetics.py` теперь гейтит по редкости (не common → спит без VIP).
- Покупка НЕ блокируется — только отображение на профиле.

---

## БЛОК 31: VIP-ГЕЙТ ДЛЯ КОСМЕТИКИ ✅ ЗАКРЫТО 2026-07-01

> Источник: запрос 2026-06-30.

### 31.1 — Косметика выше «Обычной» = только при активном VIP ✅
- `is_vip_locked()` в `core/cosmetics.py` гейтит по rarity (не common → спит без VIP).
- `get_active_cosmetics()` уже применяет `is_vip_locked` — без изменений.
- Покупка не блокируется, предмет хранится в БД, при продлении VIP появляется сам.

### 31.2 — Предупреждение при покупке без VIP ✅
- `services/cosmetics.py` `buy()`: success-сообщение добавляет ⚠️-предупреждение для non-common без VIP.
- `app.02.js`: в preview-модалке VIP-варн под кнопкой «Купить» (`.cos-prev-vipwarn`).
- `vipBar` в шапке модалки обновлён: «Купить можно любую, редкая+ — только с VIP».

---

## ✅ БЛОК 32: НАСТРОЙКИ ЧАТА — АУДИТ И РЕМОНТ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 32.1: Аудит выполнен. `chat_settings.py` работает полноценно (10 модулей, rank≥5, per-chat). Бот: `ModuleCheckMiddleware` на всех 10 роутерах. Сайт — была дыра.
- 32.2: Добавлен `require_module(module_key)` в `FastAPI/deps.py`. Извлекает `chat_id` из initData (Telegram-signed) или `x-chat-id` заголовка. Проверяет per-chat (`chat_settings`) и глобально (`global_module_toggles`). Добавлен как router-level dependency в: shop, gacha, auction, games, exchange, quests, zoo, dark_mora (warps), daily_deal.
- 32.3: `show_alert=not new_val` в `cb_toggle_setting` — при отключении модуля всплывает алерт.

---

## ✅ БЛОК 33: КОСМЕТИКА В МАГАЗИНЕ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 33.1: Внешний вид был доступен в профиле, остался без изменений.
- 33.2: Добавлена вкладка «🎨 Косметика» в Маркет (`#pg-market`). `loadMarketCosmetics()` + `_renderMarketCos()` — рендерит каталог по слотам через те же `_looksSlotHtml`/`_looksCard`. Owned → equip selection (синхронно с модалкой профиля). Unowned → `_showCosmeticPreview()` → покупка. `_looksEquip/Unequip/Reset` теперь освежает и маркет-вкладку через `_looksRefreshMkt()`. Deep link `startapp=cosmetics` / `startapp=looks` → перейти к вкладке. Бот: добавлено в web_redirect (`бот косметика/внешний вид/скин/образ` → кнопка в мини-апп).

---

## ✅ БЛОК 34: РАЗДЕЛЕНИЕ DEV-КОНСОЛИ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 34.1: `pg-admin` уже существовал как отдельная вкладка для чат-adminов — без изменений.
- 34.2: `loadGlobalDev()` переработан: 7 подвкладок через `swDev()` — Система / Игроки / Контент / Вещание / SQL / Метрики / Темы. Старые 12 секций распределены по подвкладкам.
- 34.3: В «Система» — карточка «🧩 Модули чата»: список чатов + 10 тогглов. `GET/POST /admin/dev/chat-modules/{chat_id}` в `dev_console/system.py`. Функции `devLoadChatsMod/devLoadChatMods/devSetChatMod` в `app.08.js`.

---

## ✅ БЛОК 35: МЕТРИКИ ПОСЕЩАЕМОСТИ — ЗАКРЫТО 2026-07-01

**Что сделано:**
- 35.1: Таблица `site_analytics` (user_id, tab, session_id, visited_at). `ensure_table` в lifespan main.py.
- 35.2: `switchPage()` в `app.01.js` — `POST /analytics/tab` (fire-and-forget). `_analyticsSession` — UUID per page load.
- 35.3: Дашборд в подвкладке «Метрики» дев-консоли: DAU/WAU/MAU + таблица по дням + топ-10 вкладок. `GET /admin/dev/analytics` в `dev_console/metrics.py`. `loadDevMetrics()` в `app.08.js`.

---

## БЛОК 36: НАХОДКИ ПРИ СОСТАВЛЕНИИ GAME_BIBLE.md (2026-07-02)

> Источник: полный код-аудит всей игровой механики для `GAME_BIBLE.md` (7 параллельных агентов,
> каждая цифра перепроверена по коду). Ничего из этого блока НЕ исправлено — только зафиксировано,
> часть пунктов меняет игровое поведение и требует решения пользователя (как формула усталости Волка
> в прошлой сессии).

### 36.1 — Полностью мёртвые механики (заявлены, недостижимы игроком)
- **«Отпустить питомца → 💠 Осколок Души»** нигде не доступна: `bot/handlers/zoo.py` не зарегистрирован
  в `main_router`, а на сайте кнопки/эндпоинта для этого действия нет вообще. Крафт `summon_token`
  требует Осколки, которые физически неоткуда взять, кроме старого текста в реестре.
- **`bot/handlers/duel.py`** тоже не зарегистрирован — команда `дуэль` в чате не отвечает картой боя,
  только редиректом на мини-апп (сама дуэльная логика на сайте рабочая, это не потеря функционала).
- **Теневой Торговец** (ивент Тёмной Моры) — константы/таблицы есть, `INSERT`/планировщика нет нигде.
  Анонсируется в `бот ивент`, но у игроков нет способа получить награду.
- **8 тем оформления** (3 mythic: Затмение/Пустота/Кровавая Луна + 5 seasonal: Новый Год/Солнцестояние/
  Самайн/Цветение/Азарт) и **тема `theme_royal`** (заявлена как аукционная награда) — `grant_theme()`
  для них нигде не вызывается, получить нельзя никак, кроме ручной правки в dev-консоли.
- **`бот уведомления`** — хендлер выключения `vip_expiry`/`bp_reminder` мёртв, веб-редирект ведёт на
  голую вкладку «Профиль» без UI. Игрок сегодня не может отключить эти два DM-напоминания вообще.
- **`pet_showcase.py`** — дублирует алиасы `web_redirect.py` для «питомец», но сам никогда не выполняется.

### 36.2 — Расхождения бот/сайт (кандидаты в SSOT-фикс по прецеденту БЛОК 26)
- Магазин: категории `booster` (🧪 Зелье Удачи М) и `donate` (донат-предметы за ✨) продаются только на
  сайте — `bot/handlers/shop.py::CATEGORIES` их не рендерит вообще.
- История кошелька: сайтовые метки `auction_win`/`auction_sell` не совпадают с реальными источниками
  `auction_buy`/`auction_sale` — записи показываются сырым текстом вместо метки. `gacha_mora`/
  `gacha_diamond` (актуальные источники списания за крутку) не имеют метки ни в боте, ни на сайте.
- Фильтр «Гача» в `бот история кошелька` матчит только вымершие 4-тирные `gacha_novice/standard/
  premium/diamond` — ни одной современной гача-транзакции не покажет.
- Категория лота на аукционе: бот нормализует в 4 корзины, сайт пишет сырую категорию предмета —
  один и тот же товар может попасть в разные категории в зависимости от платформы выставления.
- Порог рангов настроек чата: бот требует ранг 5 для входа в меню `бот настройки чата`, сайт разрешает
  сохранение тех же настроек с ранга 4.

### 36.3 — Игровой баланс (нужно решение — меняет поведение экономики)
- **`FAMILY_BANK_DEFAULT_CAP = 50 000` объявлена, но нигде не проверяется** — семейный общак сегодня
  фактически безлимитный. Текст карточки Дракона «🏦 +N к банку» — декоративный (ссылается на
  несуществующий ключ `family_bank_cap_bonus` в `DRAGON_BONUSES`, реально там `bank_bonus`, но и он
  ни на что не влияет, т.к. проверки капа нет).
- **БЛОК 21.4 (два уровня бана) реализован частично**: `restrict` уже разделяет игровые/неигровые
  команды (экономика недоступна, остальное работает), а `ban` по-прежнему блокирует ВСЁ, включая
  «топ»/«я»/«помощь» — как и было зафиксировано в исходной задаче.

### 36.4 — Мелкие технические хвосты (низкий приоритет, косметика документации/UX)
- `_ITEM_DETAILS` в `bot/handlers/inventory.py` — устаревшие цифры в тексте подсказок для `food_elite`/
  `food_super`/`food_diamond` (реальный эффект и цена в БД верны, страдает только текст).
- Текст `gacha_rates` в рецепте `summon_token` («80/19/1%») — статичная строка, не совпадает с реальными
  весами `GACHA_TABLES["mora"]`, риск рассинхрона при следующем ребалансе гачи.
- DM-уведомление о дуэли с сайта советует набрать `бот принять` — такой команды в боте нет (принять
  можно только кнопкой или через сайт).
- Дублирование команды часового пояса чата (`chat_settings.py` и `routing.py`, один и тот же стор) —
  не баг, но избыточность.
- Два независимых рендерера профиля (`identity.py` для «я/кто» vs `profile.py` для «инфо/досье») —
  разный набор полей на вывод, не всегда синхронизированы.
- `COMBAT_MEDKIT_ITEM`/`RAID_THRESHOLDS` — объявленные, но нигде не используемые константы.
- Нет автозакрытия просроченных (48ч) Клановых Рейдов в `scheduler.py`.
- 13 файлов `bot/handlers/*.py` не импортированы в `main_router` — осознанное решение (БЛОК19 «Web
  First»), но при чтении кода легко принять за живой функционал; кандидат на явную пометку
  `# DEPRECATED` в шапке файла или удаление.

---

## ✅ БЛОК 37: FLOOD CONTROL — БОТ САМ СЕБЯ ЗАФЛУЖИВАЛ — ЗАКРЫТО 2026-07-03

> Источник: прод-логи от пользователя (2026-07-03, ~10:59:33–10:59:46, ~450 апдейтов за 13 секунд
> в чате `-1003841515877`). Симптом: десятки `Update id=... is not handled`, парные traceback'и
> `TelegramRetryAfter: Flood control exceeded on method 'SendMessage'` с растущим `retry_after`
> (30с → 33с → 37с → 40с → 42с) — снежный ком, пользователи не получали ответы на команды без
> единой подсказки почему.

**Корневая причина:** у бота не было никакого троттлинга исходящих сообщений. При высокой
активности в одном чате (много юзеров одновременно шлют «бот», варп-команды, «бот я», «бот сайт»)
каждый апдейт немедленно порождал `message.answer()`, бот упирался в лимит Telegram (~1
SendMessage/сек на чат), и это только нарастало, т.к. ничего не ждало и не повторяло попытку.

**37.1 — Глобальный троттлинг исходящих запросов ✅**
Новый `bot/middlewares/outbound_throttle.py` — `OutboundThrottleMiddleware`, request middleware
на уровне `bot.session` (aiogram 3.x поддерживает это нативно, `bot.session.middleware(...)`, —
единственная точка, через которую идут ВСЕ исходящие вызовы Bot API, без правок в хендлерах).
Разгоняет отправку так, чтобы не более 1 сообщения/1.05с в один и тот же чат и не более 25/сек
на всего бота разом (запас под лимит Telegram 30/сек). Если `TelegramRetryAfter` всё же прилетает
(гонка/особенности подсчёта на стороне Telegram) — ждёт ровно `retry_after` и повторяет запрос
(до 3 раз), вместо того чтобы просто терять ответ пользователю. Проверено юнит-тестами на тайминги
и на retry-путь (5 последовательных отправок в 1 чат растягиваются на ~4.2с; 10 параллельных
отправок в разные чаты не блокируют друг друга; flaky-ответ с 2 `TelegramRetryAfter` подряд
восстанавливается на 3-й попытке; исчерпание лимита повторов корректно пробрасывает исключение
дальше, не проглатывает молча).

**37.2 — `db_middleware` дублировал выполнение хендлера при любом сбое ✅**
Найдено попутно при разборе тех же логов: `bot/middlewares/db.py::db_middleware` оборачивал
`await handler(event, data)` в тот же `try`, что и служебный трекинг (XP/квесты/ачивки), и в
`except` при ЛЮБОМ исключении (не только флуд-контроле) повторно вызывал `handler(event, data)`
ЕЩЁ РАЗ — это и объясняло парные traceback'и в логе («During handling of the above exception,
another exception occurred») и означало риск задвоения побочных эффектов хендлера (квестовые
метрики, начисления и т.п. в других хендлерах) при любом транзиентном сбое на этапе отправки
ответа. Исправлено: `handler()` теперь вызывается ровно один раз, СНАРУЖИ `try` служебного
трекинга; сбой трекинга логируется и не блокирует сам хендлер, но и не запускает его повторно.

**37.3 — Fire-and-forget уведомления теряли исключения молча ✅**
`_notify_achievements`/`_notify_starter_kit`/`_notify_quest_completions` в `db.py` слали
`asyncio.ensure_future(bot.send_message(...))` без обработки ошибок — при сбое исключение
никогда не забиралось (`ERROR:asyncio:Task exception was never retrieved` в логе). Добавлена
общая обёртка `_safe_send()` с `try/except` + предупреждением в лог.

**Не трогал:** сами лимиты Telegram (30/сек глобально, ~1/сек на чат) — это официальные цифры,
запас в коде (25/сек, 1.05с) взят намеренно с небольшим буфером.

---

## ✅ БЛОК 38: ЧУЖИЕ БОТЫ В ГРУППАХ КАЧАЛИ XP КАК ИГРОКИ — ЗАКРЫТО 2026-07-03

> Источник: пользователь заметил в dry-run `scripts/migrate_account_levels.py` подозрительный ID
> (совпал с `DEVELOPER_ID`) и попросил перепроверить код — «ты уверен что тут все люди?».

**Причина:** `bot/middlewares/db.py::db_middleware` считает XP/сообщения/квесты/ачивки для
**любого** отправителя текстового сообщения в группе — нигде не проверялся `user.is_bot`. Если
в чате есть посторонние боты (модерация, статистика и т.п.), их сообщения качали уровень и
статистику на общих основаниях с игроками.

**38.1 — Фикс корня ✅**
`db_middleware`: добавлена `is_bot_sender = bool(user and getattr(user, "is_bot", False))`,
регистрация (`update_user`/стартовый набор) и весь блок XP/квестов/ачивок теперь пропускают
ботов-отправителей. Дальше боты в чате для трекинга невидимы (сами игровые команды при этом
не трогали — технически другой бот, если бы вдруг написал текст-триггер команды, всё ещё
получил бы ответ, это не менялось).

**38.2 — Защита ретро-миграции уровней ✅**
`scripts/migrate_account_levels.py`: до фикса 38.1 чужие боты уже могли накопить `user_xp`
в существующих данных — правило Telegram «username любого бота обязан оканчиваться на bot»
(платформенное требование, не догадка) используется как фильтр: такие аккаунты **не получают**
«Пакет Обновления 2.0» и не пишутся в `rebuild_grant_log` (не трогаются вообще, не блокируются
навсегда) — в dry-run печатаются отдельным списком `⚠️ Исключено как похожие на ботов` для
ручной проверки человеком, а не молча пропускаются.

**Не проверено (нет прод-доступа к БД из дев-окружения на момент фикса):** сколько именно из
уже накопленных 80 кандидатов в миграции реально боты — эвристика по `username` должна отсеять
их автоматически при следующем запуске `--dry-run`, финальную проверку списка перед боевым
прогоном должен сделать пользователь.

---

## ЖУРНАЛ ИЗМЕНЕНИЙ NOT_IMPLEMENTED.md

| Дата | Изменение | Статус |
|------|-----------|--------|
| 2026-06-30 | Аудит кодовой базы: добавлены БЛОК 13 (ост.), уточнён БЛОК 21.3 (конкретные строки в stats.py) | Не исправлено |
| 2026-06-30 | БЛОК 21.3 — глобальный топ показывал ушедших из чата: `_global_user_ids` и `get_top_messages_global` не фильтровали `is_left` | ✅ Исправлено |
| 2026-06-30 | «бот топ неделя» считал скользящие 7 дней вместо Пн 00:00 — Вс 23:59 календарной недели | ✅ Исправлено |
| 2026-06-30 | БЛОК 21.2 — DevConsole: добавлены кнопки «🔗 Открыть в TG» и `@username` в карточку досье | ✅ Исправлено |
| 2026-06-30 | БЛОК 24.B «Предательство» — 3 мёртвые константы удалены из `constants.py` | ✅ Исправлено |
| 2026-06-30 | БЛОК 26.1 — стрик бот≠сайт: `FastAPI/routers/streak.py` и `profile.py` исправлены → `get_global_streak` | ✅ Исправлено |
| 2026-06-30 | Топ: страница увеличена с 15 до 30 пользователей | ✅ Исправлено |
| 2026-06-30 | БЛОК 24.C Mythic-темы без механики выдачи — решение отложено до ивент-системы | Отложено |
| 2026-06-30 | БЛОК 20.C — добавлены баги БП-админки (UI не реагирует, удаление сезона не работает) | Не исправлено |
| 2026-06-30 | Добавлен БЛОК 25 (dev-mod — оверлей разработчика на сайте) | Не исправлено |
| 2026-06-30 | Добавлен БЛОК 26 (аудит единого источника правды, расхождение стрика бот≠сайт) | Не исправлено |
| 2026-06-30 | БЛОК 20.A частично — примерочная «Примерка» с превью до/после реализована; тяжёлые партиклы/WebGL отложены | ✅ Базово |
| 2026-06-30 | БЛОК 20: косметика только за ✨ зарники (очищены микс мора+зарники); прямая покупка за ⭐ Stars (20/50/120) | ✅ Готово |
| 2026-06-30 | БЛОК 20.B — пресеты образов: save/apply/delete + UI чипов в модалке «Внешний вид» | ✅ Готово |
| 2026-06-30 | БЛОК 28 — система «бот рест»: алиасы, фикс @username не в БД, «кто рест», чистка с метками иммунитет/рест | ✅ Готово |
| 2026-06-30 | БЛОК 29 — глобальные ползунки модулей: `system_flags` таблица, dev-консоль тогглы, блокировка на сайте и в боте | ✅ Готово |
| 2026-06-30 | `profile.py` `/me` — добавлено поле `system_flags` (публично, для обычных юзеров); убран отдельный dev-only запрос из JS | ✅ Готово |
| 2026-06-30 | `main.py` lifespan — добавлен `system_flags.ensure_table` (веб стартует раньше бота) | ✅ Готово |
| 2026-06-30 | Добавлены БЛОК 30 (рефанд косметики + новые цены), БЛОК 31 (VIP-гейт косметики), БЛОК 32 (настройки чата), БЛОК 33 (косметика в магазине), БЛОК 34 (разделение dev/admin), БЛОК 35 (метрики посещений) | Ожидание |
| 2026-07-02 | Создан `GAME_BIBLE.md` — полная энциклопедия игрового контента (питомцы/предметы/косметика/экономика/прогрессия/ивенты/команды). Добавлен БЛОК 36 — находки при составлении (мёртвые механики, расхождения бот/сайт, вопрос семейного банка без лимита) | Ожидание |
| 2026-07-03 | БЛОК 37 — бот сам себя заваливал flood control под нагрузкой (нет троттлинга исходящих) + попутно найден дубль-вызов хендлера в `db_middleware` при любом сбое + непойманные исключения в fire-and-forget уведомлениях | ✅ Исправлено |
| 2026-07-03 | `scripts/migrate_account_levels.py` — `--dry-run` падал (`UndefinedTableError`, DDL скипался под `if not dry_run`) | ✅ Исправлено |
| 2026-07-03 | БЛОК 38 — чужие боты в группах качали XP/уровни как игроки (нет проверки `is_bot` в `db_middleware`); ретро-миграция уровней отфильтрована по username-эвристике Telegram | ✅ Исправлено |




Ещё идеии, сделать какое-то событие что каждую неделю будет 5 товаров из косметики продаваться по скидке 15-30% любая косметика вообще. И обновляеться осортимент раз в неделю. И сделать так что бы каждый товар сначала быть помечен как темная карточка, и при нажатии она будет розворачиваться и там будет показываться уже товар сам. Типо игрок должен нажать на карточку, и только тогда он узнает, что там лежит и по какой цене.
✅ Реализовано как R4.2 «Витрина недели» (2026-07-03, коммит `b9c3c80d`) — `/showcase/*`, см. GDD_REBUILD_PLAN.md.

Удали лишние файлы аудита которые больше не нужны. 





Jul 03 18:57:38  2026-07-03 18:57:38.277 | INFO     | __main__:main:34 - ══════════════════════════════════════════════════
Jul 03 18:57:38  2026-07-03 18:57:38.278 | INFO     | __main__:main:35 - 🔮 ПРЕДВЕСТНИК V2 — ЗАПУСК СИСТЕМЫ
Jul 03 18:57:38  2026-07-03 18:57:38.279 | INFO     | __main__:main:36 - ══════════════════════════════════════════════════
Jul 03 18:57:38  2026-07-03 18:57:38.279 | INFO     | __main__:main:37 - 📊 Архитектура: PostgreSQL + asyncpg
Jul 03 18:57:40  2026-07-03 18:57:40.736 | INFO     | __main__:main:63 - 🌐 FastAPI мини-апп запущен на порту 8000 (prefix='/predvestnik')
Jul 03 18:57:40  2026-07-03 18:57:40.737 | INFO     | __main__:main:68 - 🐘 Подключение к PostgreSQL...
Jul 03 18:57:40  2026-07-03 18:57:40.737 | INFO     | infrastructure.database:create_pool:95 - 📦 asyncpg version: 0.30.0
Jul 03 18:57:40  2026-07-03 18:57:40.737 | INFO     | infrastructure.database:create_pool:96 - 🔬 Источники подключения (2): DATABASE_URL, PREDVESTNIK_DATABASE_URL
Jul 03 18:57:40  2026-07-03 18:57:40.738 | INFO     | infrastructure.database:create_pool:103 - 🔌 [DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 03 18:57:40  2026-07-03 18:57:40.738 | INFO     | infrastructure.database:create_pool:108 - 🌐 [DATABASE_URL] Цель: app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 03 18:57:41  2026-07-03 18:57:41.046 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [DATABASE_URL] DNS  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com → ['100.126.247.195']
Jul 03 18:57:49  2026-07-03 18:57:49.049 | INFO     | infrastructure.database:_diagnose:67 - ❌ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 03 18:57:49  2026-07-03 18:57:49.049 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25060 → OK
Jul 03 18:57:49  2026-07-03 18:57:49.049 | INFO     | infrastructure.database:_diagnose:67 - ✅ [DATABASE_URL] TCP  app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-23226291-0.k.db.ondigitalocean.com:25061 → OK
Jul 03 18:57:49  2026-07-03 18:57:49.050 | INFO     | infrastructure.database:create_pool:103 - 🔌 [PREDVESTNIK_DATABASE_URL] URL (masked) = postgresql://iesaroot-db:***@private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060/iesaroot-db?sslmode=require
Jul 03 18:57:49  2026-07-03 18:57:49.050 | INFO     | infrastructure.database:create_pool:108 - 🌐 [PREDVESTNIK_DATABASE_URL] Цель: private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 (db=iesaroot-db)
Jul 03 18:57:49  2026-07-03 18:57:49.067 | INFO     | infrastructure.database:_diagnose:57 - 🔍 [PREDVESTNIK_DATABASE_URL] DNS  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com → ['10.114.0.2']
Jul 03 18:57:50  ERROR:    Exception in ASGI application
Jul 03 18:57:50  Traceback (most recent call last):
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:50      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:50      return await self.app(scope, receive, send)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:50      await super().__call__(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:50      await self.app(scope, receive, _send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 93, in __call__
Jul 03 18:57:50      await self.simple_response(scope, receive, send, request_headers=headers)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 144, in simple_response
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:50      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:50      await route.handle(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:50      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:50      response = await f(request)
Jul 03 18:57:50                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:50      solved_result = await solve_dependencies(
Jul 03 18:57:50                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:50      solved = await solve_generator(
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:50      return await stack.enter_async_context(cm)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:50      result = await _enter(cm)
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:50      return await anext(self.gen)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:50      async with get_pool().acquire() as conn:
Jul 03 18:57:50                 ^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:50      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:50  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:50  ERROR:    Exception in ASGI application
Jul 03 18:57:50  Traceback (most recent call last):
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:50      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:50      return await self.app(scope, receive, send)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:50      await super().__call__(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:50      await self.app(scope, receive, _send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:50      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:50      await route.handle(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:50      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:50      response = await f(request)
Jul 03 18:57:50                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:50      solved_result = await solve_dependencies(
Jul 03 18:57:50                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 615, in solve_dependencies
Jul 03 18:57:50      solved_result = await solve_dependencies(
Jul 03 18:57:50                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:50      solved = await solve_generator(
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:50      return await stack.enter_async_context(cm)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:50      result = await _enter(cm)
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:50      return await anext(self.gen)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:50      async with get_pool().acquire() as conn:
Jul 03 18:57:50                 ^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:50      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:50  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:50  ERROR:    Exception in ASGI application
Jul 03 18:57:50  Traceback (most recent call last):
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:50      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:50      return await self.app(scope, receive, send)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:50      await super().__call__(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:50      await self.app(scope, receive, _send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:50      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:50      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:50      await route.handle(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:50      await self.app(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:50      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:50      raise exc
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:50      await app(scope, receive, sender)
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:50      response = await f(request)
Jul 03 18:57:50                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:50      solved_result = await solve_dependencies(
Jul 03 18:57:50                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 615, in solve_dependencies
Jul 03 18:57:50      solved_result = await solve_dependencies(
Jul 03 18:57:50                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:50      solved = await solve_generator(
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:50      return await stack.enter_async_context(cm)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:50      result = await _enter(cm)
Jul 03 18:57:50               ^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:50      return await anext(self.gen)
Jul 03 18:57:50             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:50      async with get_pool().acquire() as conn:
Jul 03 18:57:50                 ^^^^^^^^^^
Jul 03 18:57:50    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:50      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:50  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:52  ERROR:    Exception in ASGI application
Jul 03 18:57:52  Traceback (most recent call last):
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:52      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:52               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:52      return await self.app(scope, receive, send)
Jul 03 18:57:52             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:52      await self.app(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:52      await super().__call__(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:52      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:52      raise exc
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:52      await self.app(scope, receive, _send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 93, in __call__
Jul 03 18:57:52      await self.simple_response(scope, receive, send, request_headers=headers)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 144, in simple_response
Jul 03 18:57:52      await self.app(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:52      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:52      raise exc
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:52      await app(scope, receive, sender)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:52      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:52      await route.handle(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:52      await self.app(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:52      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:52      raise exc
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:52      await app(scope, receive, sender)
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:52      response = await f(request)
Jul 03 18:57:52                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:52      solved_result = await solve_dependencies(
Jul 03 18:57:52                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:52      solved = await solve_generator(
Jul 03 18:57:52               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:52      return await stack.enter_async_context(cm)
Jul 03 18:57:52             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:52      result = await _enter(cm)
Jul 03 18:57:52               ^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:52      return await anext(self.gen)
Jul 03 18:57:52             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:52      async with get_pool().acquire() as conn:
Jul 03 18:57:52                 ^^^^^^^^^^
Jul 03 18:57:52    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:52      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:52  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:53  ERROR:    Exception in ASGI application
Jul 03 18:57:53  Traceback (most recent call last):
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:53      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:53               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:53      return await self.app(scope, receive, send)
Jul 03 18:57:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:53      await self.app(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:53      await super().__call__(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:53      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:53      raise exc
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:53      await self.app(scope, receive, _send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:53      await self.app(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:53      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:53      raise exc
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:53      await app(scope, receive, sender)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:53      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:53      await route.handle(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:53      await self.app(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:53      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:53      raise exc
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:53      await app(scope, receive, sender)
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:53      response = await f(request)
Jul 03 18:57:53                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:53      solved_result = await solve_dependencies(
Jul 03 18:57:53                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:53      solved = await solve_generator(
Jul 03 18:57:53               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:53      return await stack.enter_async_context(cm)
Jul 03 18:57:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:53      result = await _enter(cm)
Jul 03 18:57:53               ^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:53      return await anext(self.gen)
Jul 03 18:57:53             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:53      async with get_pool().acquire() as conn:
Jul 03 18:57:53                 ^^^^^^^^^^
Jul 03 18:57:53    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:53      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:53  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:54  ERROR:    Exception in ASGI application
Jul 03 18:57:54  Traceback (most recent call last):
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:54      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:54      return await self.app(scope, receive, send)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:54      await super().__call__(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:54      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:54      await self.app(scope, receive, _send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:54      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:54      await app(scope, receive, sender)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:54      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:54      await route.handle(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:54      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:54      await app(scope, receive, sender)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:54      response = await f(request)
Jul 03 18:57:54                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:54      solved_result = await solve_dependencies(
Jul 03 18:57:54                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:54      solved = await solve_generator(
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:54      return await stack.enter_async_context(cm)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:54      result = await _enter(cm)
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:54      return await anext(self.gen)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:54      async with get_pool().acquire() as conn:
Jul 03 18:57:54                 ^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:54      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:54  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:54  ERROR:    Exception in ASGI application
Jul 03 18:57:54  Traceback (most recent call last):
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:54      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:54      return await self.app(scope, receive, send)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:54      await super().__call__(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:54      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:54      await self.app(scope, receive, _send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:54      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:54      await app(scope, receive, sender)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:54      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:54      await route.handle(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:54      await self.app(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:54      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:54      raise exc
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:54      await app(scope, receive, sender)
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:54      response = await f(request)
Jul 03 18:57:54                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:54      solved_result = await solve_dependencies(
Jul 03 18:57:54                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:54      solved = await solve_generator(
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:54      return await stack.enter_async_context(cm)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:54      result = await _enter(cm)
Jul 03 18:57:54               ^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:54      return await anext(self.gen)
Jul 03 18:57:54             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:54      async with get_pool().acquire() as conn:
Jul 03 18:57:54                 ^^^^^^^^^^
Jul 03 18:57:54    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:54      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:54  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:56  ERROR:    Exception in ASGI application
Jul 03 18:57:56  Traceback (most recent call last):
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:56      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:56      return await self.app(scope, receive, send)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:56      await super().__call__(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:56      await self.app(scope, receive, _send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:56      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:56      await route.handle(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:56      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:56      response = await f(request)
Jul 03 18:57:56                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:56      solved_result = await solve_dependencies(
Jul 03 18:57:56                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:56      solved = await solve_generator(
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:56      return await stack.enter_async_context(cm)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:56      result = await _enter(cm)
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:56      return await anext(self.gen)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:56      async with get_pool().acquire() as conn:
Jul 03 18:57:56                 ^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:56      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:56  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:56  ERROR:    Exception in ASGI application
Jul 03 18:57:56  Traceback (most recent call last):
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:56      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:56      return await self.app(scope, receive, send)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:56      await super().__call__(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:56      await self.app(scope, receive, _send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:56      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:56      await route.handle(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:56      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:56      response = await f(request)
Jul 03 18:57:56                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:56      solved_result = await solve_dependencies(
Jul 03 18:57:56                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:56      solved = await solve_generator(
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:56      return await stack.enter_async_context(cm)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:56      result = await _enter(cm)
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:56      return await anext(self.gen)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:56      async with get_pool().acquire() as conn:
Jul 03 18:57:56                 ^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:56      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:56  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:56  ERROR:    Exception in ASGI application
Jul 03 18:57:56  Traceback (most recent call last):
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:57:56      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:57:56      return await self.app(scope, receive, send)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:57:56      await super().__call__(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:57:56      await self.app(scope, receive, _send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:57:56      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:57:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:57:56      await route.handle(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:57:56      await self.app(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:57:56      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:57:56      raise exc
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:57:56      await app(scope, receive, sender)
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:57:56      response = await f(request)
Jul 03 18:57:56                 ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 291, in app
Jul 03 18:57:56      solved_result = await solve_dependencies(
Jul 03 18:57:56                      ^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 634, in solve_dependencies
Jul 03 18:57:56      solved = await solve_generator(
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/dependencies/utils.py", line 560, in solve_generator
Jul 03 18:57:56      return await stack.enter_async_context(cm)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 650, in enter_async_context
Jul 03 18:57:56      result = await _enter(cm)
Jul 03 18:57:56               ^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/.heroku/python/lib/python3.11/contextlib.py", line 210, in __aenter__
Jul 03 18:57:56      return await anext(self.gen)
Jul 03 18:57:56             ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/FastAPI/deps.py", line 18, in get_db
Jul 03 18:57:56      async with get_pool().acquire() as conn:
Jul 03 18:57:56                 ^^^^^^^^^^
Jul 03 18:57:56    File "/workspace/predvestnik_v2/infrastructure/database.py", line 156, in get_pool
Jul 03 18:57:56      raise RuntimeError("Pool not initialised. Call create_pool() first.")
Jul 03 18:57:56  RuntimeError: Pool not initialised. Call create_pool() first.
Jul 03 18:57:57  2026-07-03 18:57:57.072 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:5432 → TIMEOUT 8.0s
Jul 03 18:57:57  2026-07-03 18:57:57.073 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25060 → TIMEOUT 8.0s
Jul 03 18:57:57  2026-07-03 18:57:57.073 | INFO     | infrastructure.database:_diagnose:67 - ❌ [PREDVESTNIK_DATABASE_URL] TCP  private-app-d06558f4-264c-4852-9c6f-b0de9fc4e36d-do-user-232262.k.db.ondigitalocean.com:25061 → TIMEOUT 8.0s
Jul 03 18:57:57  2026-07-03 18:57:57.078 | INFO     | infrastructure.database:create_pool:114 - ✅ Internet  8.8.8.8:53 → OK
Jul 03 18:57:57  2026-07-03 18:57:57.079 | INFO     | infrastructure.database:create_pool:115 - 🔬 Диагностика завершена, пробуем asyncpg...
Jul 03 18:57:57  2026-07-03 18:57:57.079 | INFO     | infrastructure.database:create_pool:120 - 🐘 Пробуем подключиться через [DATABASE_URL]...
Jul 03 18:57:57  2026-07-03 18:57:57.080 | INFO     | infrastructure.database:create_pool:122 - 🐘 [DATABASE_URL] asyncpg create_pool — попытка 1/2 (timeout=30s)...
Jul 03 18:57:57  2026-07-03 18:57:57.115 | INFO     | infrastructure.database:create_pool:133 - ✅ PostgreSQL pool готов через [DATABASE_URL] (min=1 max=15, schema=predvestnik)
Jul 03 18:57:57  2026-07-03 18:57:57.116 | INFO     | __main__:main:71 - 🗄️  Инициализация схемы БД...
Jul 03 18:57:57  2026-07-03 18:57:57.116 | INFO     | bot.core.database:init_db:1278 - Проверка и создание таблиц PostgreSQL...
Jul 03 18:57:57  2026-07-03 18:57:57.659 | INFO     | bot.core.database:init_db:1308 - ✅ Схема PostgreSQL готова!
Jul 03 18:57:57  2026-07-03 18:57:57.660 | INFO     | __main__:main:73 - ✅ База данных готова!
Jul 03 18:57:57  2026-07-03 18:57:57.660 | INFO     | __main__:main:80 - 🔒 Ожидание advisory lock (единственный инстанс)...
Jul 03 18:58:15  2026-07-03 18:58:15.568 | INFO     | __main__:main:83 - 🔒 Advisory lock получен — этот инстанс единственный.
Jul 03 18:58:15  2026-07-03 18:58:15.568 | INFO     | __main__:main:86 - ⚙️  Инициализация Telegram Bot API...
Jul 03 18:58:15  2026-07-03 18:58:15.653 | INFO     | __main__:main:93 - 🔌 Подключение Middleware...
Jul 03 18:58:15  2026-07-03 18:58:15.654 | INFO     | __main__:main:100 - 📡 Регистрация роутеров...
Jul 03 18:58:15  2026-07-03 18:58:15.654 | INFO     | __main__:main:102 - ✅ Все роутеры подключены!
Jul 03 18:58:15  2026-07-03 18:58:15.740 | INFO     | __main__:main:128 - ✅ Кнопка меню → https://iesaroot-app-8kuyb.ondigitalocean.app/predvestnik
Jul 03 18:58:15  2026-07-03 18:58:15.741 | INFO     | __main__:main:135 - 🦄 RARITY_STICKER_ID установлен: CAACAgIAAxkBAAIDgmof-8HXbDv5WsJ4bPs7rqs2qMJqAAIvBAACeKazBLT_Kx2NSudQOwQ
Jul 03 18:58:15  2026-07-03 18:58:15.741 | INFO     | __main__:main:144 - ══════════════════════════════════════════════════
Jul 03 18:58:15  2026-07-03 18:58:15.741 | INFO     | __main__:main:145 - 🟢 БОТ ГОТОВ К ПРИЕМУ СООБЩЕНИЙ
Jul 03 18:58:15  2026-07-03 18:58:15.741 | INFO     | __main__:main:146 - ══════════════════════════════════════════════════
Jul 03 18:58:15  INFO:aiogram.dispatcher:Start polling
Jul 03 18:58:15  2026-07-03 18:58:15.743 | INFO     | services.scheduler:expedition_background_task:214 - Фоновый процесс экспедиций запущен.
Jul 03 18:58:15  2026-07-03 18:58:15.743 | INFO     | services.scheduler:daily_deal_task:242 - Фоновая задача акции дня запущена.
Jul 03 18:58:15  2026-07-03 18:58:15.744 | INFO     | services.scheduler:duel_and_auction_task:525 - Фоновая задача дуэлей/аукциона запущена.
Jul 03 18:58:15  2026-07-03 18:58:15.744 | INFO     | services.scheduler:chest_spawn_task:670 - Фоновая задача сундуков запущена.
Jul 03 18:58:15  2026-07-03 18:58:15.745 | INFO     | services.scheduler:anniversary_task:736 - Фоновая задача годовщин брака запущена.
Jul 03 18:58:15  2026-07-03 18:58:15.745 | INFO     | services.scheduler:smart_pulse_task:622 - Фоновая задача «Умный Пульс» запущена.
Jul 03 18:58:15  INFO:aiogram.dispatcher:Run polling for bot @IIIPredvestnikIIIBot id=8485867534 - '12 предвестник'
Jul 03 18:58:32  2026-07-03 18:58:32.693 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 18:58:32  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 18:58:32  Args: ['W2026-27']
Jul 03 18:58:32  ERROR:    Exception in ASGI application
Jul 03 18:58:32  Traceback (most recent call last):
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:58:32      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:58:32               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:58:32      return await self.app(scope, receive, send)
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:58:32      await self.app(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:58:32      await super().__call__(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:58:32      await self.middleware_stack(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:58:32      raise exc
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:58:32      await self.app(scope, receive, _send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:58:32      await self.app(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:58:32      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:58:32      raise exc
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:58:32      await app(scope, receive, sender)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:58:32      await self.middleware_stack(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:58:32      await route.handle(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:58:32      await self.app(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:58:32      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:58:32      raise exc
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:58:32      await app(scope, receive, sender)
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:58:32      response = await f(request)
Jul 03 18:58:32                 ^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 18:58:32      raw_response = await run_endpoint_function(
Jul 03 18:58:32                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 18:58:32      return await dependant.call(**values)
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 18:58:32      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 18:58:32              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 18:58:32      async with db.execute(
Jul 03 18:58:32    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 18:58:32      return await self._run()
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 18:58:32      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 18:58:32      return await self._execute(
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 18:58:32      result, _ = await self.__execute(
Jul 03 18:58:32                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 18:58:32      result, stmt = await self._do_execute(
Jul 03 18:58:32                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 18:58:32      stmt = await self._get_statement(
Jul 03 18:58:32             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 18:58:32      statement = await self._protocol.prepare(
Jul 03 18:58:32                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:58:32    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 18:58:32  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 18:58:33  INFO:aiogram.event:Update id=976651432 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 18:58:36  INFO:aiogram.event:Update id=976651433 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 18:58:39  INFO:aiogram.event:Update id=976651434 is not handled. Duration 250 ms by bot id=8485867534
Jul 03 18:58:47  INFO:aiogram.event:Update id=976651435 is not handled. Duration 102 ms by bot id=8485867534
Jul 03 18:58:49  INFO:aiogram.event:Update id=976651436 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 18:58:53  INFO:aiogram.event:Update id=976651437 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 18:58:58  INFO:aiogram.event:Update id=976651438 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 18:59:08  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getUserProfilePhotos?user_id=1942882561&limit=1 "HTTP/1.1 200 OK"
Jul 03 18:59:08  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getFile?file_id=AgACAgIAAxUAAWpHluC7CCEoMNqNZRFO7omgai-aAAJAGWsbUosxSki1Fm1krQ4TAQADAgADYQADPAQ "HTTP/1.1 200 OK"
Jul 03 18:59:08  INFO:httpx:HTTP Request: GET https://api.telegram.org/file/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/photos/file_44.jpg "HTTP/1.1 200 OK"
Jul 03 18:59:10  INFO:aiogram.event:Update id=976651439 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 18:59:17  INFO:aiogram.event:Update id=976651440 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 18:59:19  INFO:aiogram.event:Update id=976651441 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 18:59:23  INFO:aiogram.event:Update id=976651442 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 18:59:40  INFO:aiogram.event:Update id=976651443 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 18:59:42  INFO:aiogram.event:Update id=976651444 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 18:59:48  INFO:aiogram.event:Update id=976651445 is not handled. Duration 87 ms by bot id=8485867534
Jul 03 18:59:51  INFO:aiogram.event:Update id=976651446 is not handled. Duration 156 ms by bot id=8485867534
Jul 03 18:59:56  2026-07-03 18:59:56.395 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 18:59:56  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 18:59:56  Args: ['W2026-27']
Jul 03 18:59:56  ERROR:    Exception in ASGI application
Jul 03 18:59:56  Traceback (most recent call last):
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 18:59:56      result = await app(  # type: ignore[func-returns-value]
Jul 03 18:59:56               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 18:59:56      return await self.app(scope, receive, send)
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 18:59:56      await self.app(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 18:59:56      await super().__call__(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 18:59:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 18:59:56      raise exc
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 18:59:56      await self.app(scope, receive, _send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 18:59:56      await self.app(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 18:59:56      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:59:56      raise exc
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:59:56      await app(scope, receive, sender)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 18:59:56      await self.middleware_stack(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 18:59:56      await route.handle(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 18:59:56      await self.app(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 18:59:56      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 18:59:56      raise exc
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 18:59:56      await app(scope, receive, sender)
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 18:59:56      response = await f(request)
Jul 03 18:59:56                 ^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 18:59:56      raw_response = await run_endpoint_function(
Jul 03 18:59:56                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 18:59:56      return await dependant.call(**values)
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 18:59:56      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 18:59:56              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 18:59:56      async with db.execute(
Jul 03 18:59:56    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 18:59:56      return await self._run()
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 18:59:56      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 18:59:56      return await self._execute(
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 18:59:56      result, _ = await self.__execute(
Jul 03 18:59:56                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 18:59:56      result, stmt = await self._do_execute(
Jul 03 18:59:56                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 18:59:56      stmt = await self._get_statement(
Jul 03 18:59:56             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 18:59:56      statement = await self._protocol.prepare(
Jul 03 18:59:56                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 18:59:56    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 18:59:56  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 18:59:56  INFO:aiogram.event:Update id=976651447 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 18:59:57  INFO:aiogram.event:Update id=976651448 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 18:59:57  INFO:aiogram.event:Update id=976651449 is not handled. Duration 91 ms by bot id=8485867534
Jul 03 19:00:04  INFO:aiogram.event:Update id=976651450 is not handled. Duration 336 ms by bot id=8485867534
Jul 03 19:00:13  INFO:aiogram.event:Update id=976651451 is not handled. Duration 223 ms by bot id=8485867534
Jul 03 19:00:18  INFO:aiogram.event:Update id=976651452 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:00:19  INFO:aiogram.event:Update id=976651453 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:00:31  INFO:aiogram.event:Update id=976651454 is not handled. Duration 259 ms by bot id=8485867534
Jul 03 19:00:31  INFO:aiogram.event:Update id=976651455 is not handled. Duration 188 ms by bot id=8485867534
Jul 03 19:00:35  INFO:aiogram.event:Update id=976651456 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:00:36  INFO:aiogram.event:Update id=976651457 is not handled. Duration 371 ms by bot id=8485867534
Jul 03 19:00:51  INFO:aiogram.event:Update id=976651458 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:00:53  INFO:aiogram.event:Update id=976651459 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:00:55  INFO:aiogram.event:Update id=976651460 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:01:13  INFO:aiogram.event:Update id=976651461 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 19:01:15  INFO:aiogram.event:Update id=976651462 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:01:17  INFO:aiogram.event:Update id=976651463 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:01:24  INFO:aiogram.event:Update id=976651464 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 19:01:29  INFO:aiogram.event:Update id=976651465 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:01:51  2026-07-03 19:01:51.974 | INFO     | bot.handlers.events:on_user_status_changed:246 - Юзер 2122226808 вошёл в чат -1003841515877.
Jul 03 19:01:51  INFO:aiogram.event:Update id=976651466 is handled. Duration 1213 ms by bot id=8485867534
Jul 03 19:01:52  INFO:aiogram.event:Update id=976651468 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:01:53  INFO:aiogram.event:Update id=976651467 is not handled. Duration 2081 ms by bot id=8485867534
Jul 03 19:01:53  INFO:aiogram.event:Update id=976651469 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:02:05  2026-07-03 19:02:05.181 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 19:02:05  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 19:02:05  Args: ['W2026-27']
Jul 03 19:02:05  ERROR:    Exception in ASGI application
Jul 03 19:02:05  Traceback (most recent call last):
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 19:02:05      result = await app(  # type: ignore[func-returns-value]
Jul 03 19:02:05               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 19:02:05      return await self.app(scope, receive, send)
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 19:02:05      await self.app(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 19:02:05      await super().__call__(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 19:02:05      await self.middleware_stack(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 19:02:05      raise exc
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 19:02:05      await self.app(scope, receive, _send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 19:02:05      await self.app(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 19:02:05      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 19:02:05      raise exc
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 19:02:05      await app(scope, receive, sender)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 19:02:05      await self.middleware_stack(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 19:02:05      await route.handle(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 19:02:05      await self.app(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 19:02:05      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 19:02:05      raise exc
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 19:02:05      await app(scope, receive, sender)
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 19:02:05      response = await f(request)
Jul 03 19:02:05                 ^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 19:02:05      raw_response = await run_endpoint_function(
Jul 03 19:02:05                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 19:02:05      return await dependant.call(**values)
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 19:02:05      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 19:02:05              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 19:02:05      async with db.execute(
Jul 03 19:02:05    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 19:02:05      return await self._run()
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 19:02:05      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 19:02:05      return await self._execute(
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 19:02:05      result, _ = await self.__execute(
Jul 03 19:02:05                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 19:02:05      result, stmt = await self._do_execute(
Jul 03 19:02:05                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 19:02:05      stmt = await self._get_statement(
Jul 03 19:02:05             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 19:02:05      statement = await self._protocol.prepare(
Jul 03 19:02:05                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:02:05    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 19:02:05  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 19:02:07  INFO:aiogram.event:Update id=976651470 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:02:12  INFO:aiogram.event:Update id=976651471 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:02:21  INFO:aiogram.event:Update id=976651472 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:02:22  INFO:aiogram.event:Update id=976651473 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:02:28  INFO:aiogram.event:Update id=976651474 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:02:32  INFO:aiogram.event:Update id=976651475 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:02:37  INFO:aiogram.event:Update id=976651476 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:02:44  INFO:aiogram.event:Update id=976651477 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:02:55  INFO:aiogram.event:Update id=976651478 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:02:58  INFO:aiogram.event:Update id=976651479 is not handled. Duration 94 ms by bot id=8485867534
Jul 03 19:03:09  INFO:aiogram.event:Update id=976651480 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:03:11  INFO:aiogram.event:Update id=976651481 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:03:21  INFO:aiogram.event:Update id=976651482 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:03:23  INFO:aiogram.event:Update id=976651483 is not handled. Duration 158 ms by bot id=8485867534
Jul 03 19:03:30  INFO:aiogram.event:Update id=976651484 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:03:32  INFO:aiogram.event:Update id=976651485 is not handled. Duration 192 ms by bot id=8485867534
Jul 03 19:03:33  INFO:aiogram.event:Update id=976651486 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 19:03:49  INFO:aiogram.event:Update id=976651487 is handled. Duration 50 ms by bot id=8485867534
Jul 03 19:03:56  INFO:aiogram.event:Update id=976651488 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:03:56  INFO:aiogram.event:Update id=976651489 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:04:04  INFO:aiogram.event:Update id=976651490 is not handled. Duration 165 ms by bot id=8485867534
Jul 03 19:04:05  INFO:aiogram.event:Update id=976651491 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:04:11  INFO:aiogram.event:Update id=976651492 is not handled. Duration 195 ms by bot id=8485867534
Jul 03 19:04:20  INFO:aiogram.event:Update id=976651493 is handled. Duration 50 ms by bot id=8485867534
Jul 03 19:04:25  INFO:aiogram.event:Update id=976651494 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:04:27  INFO:aiogram.event:Update id=976651495 is not handled. Duration 156 ms by bot id=8485867534
Jul 03 19:04:40  INFO:aiogram.event:Update id=976651496 is not handled. Duration 185 ms by bot id=8485867534
Jul 03 19:04:48  INFO:aiogram.event:Update id=976651497 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:04:49  INFO:aiogram.event:Update id=976651498 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:04:57  INFO:aiogram.event:Update id=976651499 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 19:04:59  INFO:aiogram.event:Update id=976651500 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:05:00  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getUserProfilePhotos?user_id=738240269&limit=1 "HTTP/1.1 200 OK"
Jul 03 19:05:00  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getFile?file_id=AgACAgIAAxUAAWpHllIaAaKuFlwbkn3XJGSd9_9wAAIQC2sbDacAASwYie14KaIY9QEAAwIAA2EAAzwE "HTTP/1.1 200 OK"
Jul 03 19:05:00  INFO:httpx:HTTP Request: GET https://api.telegram.org/file/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/photos/file_41.jpg "HTTP/1.1 200 OK"
Jul 03 19:05:08  INFO:aiogram.event:Update id=976651501 is not handled. Duration 336 ms by bot id=8485867534
Jul 03 19:05:09  INFO:aiogram.event:Update id=976651502 is not handled. Duration 315 ms by bot id=8485867534
Jul 03 19:05:10  INFO:aiogram.event:Update id=976651503 is not handled. Duration 187 ms by bot id=8485867534
Jul 03 19:05:12  INFO:aiogram.event:Update id=976651504 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:05:14  INFO:aiogram.event:Update id=976651505 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 19:05:26  INFO:aiogram.event:Update id=976651506 is handled. Duration 310 ms by bot id=8485867534
Jul 03 19:05:31  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getUserProfilePhotos?user_id=1460945748&limit=1 "HTTP/1.1 200 OK"
Jul 03 19:05:31  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getFile?file_id=AgACAgIAAxUAAWpHmKrE37JakUtesm51kPHmjqflAAJCFmsbR3O5SpORsAU9n-zeAQADAgADYQADPAQ "HTTP/1.1 200 OK"
Jul 03 19:05:32  INFO:httpx:HTTP Request: GET https://api.telegram.org/file/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/photos/file_45.jpg "HTTP/1.1 200 OK"
Jul 03 19:05:40  INFO:aiogram.event:Update id=976651507 is not handled. Duration 220 ms by bot id=8485867534
Jul 03 19:05:47  INFO:aiogram.event:Update id=976651508 is not handled. Duration 170 ms by bot id=8485867534
Jul 03 19:05:51  INFO:aiogram.event:Update id=976651509 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:05:56  INFO:aiogram.event:Update id=976651510 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:05:57  INFO:aiogram.event:Update id=976651511 is not handled. Duration 98 ms by bot id=8485867534
Jul 03 19:06:05  INFO:aiogram.event:Update id=976651512 is not handled. Duration 158 ms by bot id=8485867534
Jul 03 19:06:06  INFO:aiogram.event:Update id=976651513 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:06:08  INFO:aiogram.event:Update id=976651514 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:06:10  INFO:aiogram.event:Update id=976651515 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:06:14  INFO:aiogram.event:Update id=976651516 is not handled. Duration 95 ms by bot id=8485867534
Jul 03 19:06:17  INFO:aiogram.event:Update id=976651517 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:06:22  INFO:aiogram.event:Update id=976651518 is handled. Duration 110 ms by bot id=8485867534
Jul 03 19:06:24  INFO:aiogram.event:Update id=976651519 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:06:28  INFO:aiogram.event:Update id=976651520 is not handled. Duration 99 ms by bot id=8485867534
Jul 03 19:06:29  INFO:aiogram.event:Update id=976651521 is not handled. Duration 94 ms by bot id=8485867534
Jul 03 19:06:31  INFO:aiogram.event:Update id=976651522 is not handled. Duration 172 ms by bot id=8485867534
Jul 03 19:06:38  INFO:aiogram.event:Update id=976651523 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:06:41  INFO:aiogram.event:Update id=976651524 is not handled. Duration 253 ms by bot id=8485867534
Jul 03 19:06:42  INFO:aiogram.event:Update id=976651525 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:06:43  INFO:aiogram.event:Update id=976651526 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:06:48  INFO:aiogram.event:Update id=976651528 is not handled. Duration 245 ms by bot id=8485867534
Jul 03 19:06:48  INFO:aiogram.event:Update id=976651527 is not handled. Duration 245 ms by bot id=8485867534
Jul 03 19:06:52  INFO:aiogram.event:Update id=976651529 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:07:02  INFO:aiogram.event:Update id=976651530 is not handled. Duration 707 ms by bot id=8485867534
Jul 03 19:07:07  INFO:aiogram.event:Update id=976651531 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:07:11  INFO:aiogram.event:Update id=976651532 is handled. Duration 197 ms by bot id=8485867534
Jul 03 19:07:15  INFO:aiogram.event:Update id=976651533 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:07:19  INFO:aiogram.event:Update id=976651534 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:07:25  INFO:aiogram.event:Update id=976651536 is not handled. Duration 147 ms by bot id=8485867534
Jul 03 19:07:25  INFO:aiogram.event:Update id=976651535 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 19:07:26  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:07:37  INFO:aiogram.event:Update id=976651538 is not handled. Duration 355 ms by bot id=8485867534
Jul 03 19:07:37  INFO:aiogram.event:Update id=976651537 is not handled. Duration 394 ms by bot id=8485867534
Jul 03 19:07:38  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:07:40  INFO:aiogram.event:Update id=976651539 is not handled. Duration 183 ms by bot id=8485867534
Jul 03 19:07:40  INFO:aiogram.event:Update id=976651540 is not handled. Duration 206 ms by bot id=8485867534
Jul 03 19:07:41  INFO:aiogram.event:Update id=976651541 is not handled. Duration 269 ms by bot id=8485867534
Jul 03 19:07:43  INFO:aiogram.event:Update id=976651542 is not handled. Duration 95 ms by bot id=8485867534
Jul 03 19:07:46  INFO:aiogram.event:Update id=976651543 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 19:07:50  INFO:aiogram.event:Update id=976651544 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 19:07:51  INFO:aiogram.event:Update id=976651545 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:07:53  INFO:aiogram.event:Update id=976651546 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:07:57  INFO:aiogram.event:Update id=976651547 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:08:03  INFO:aiogram.event:Update id=976651548 is not handled. Duration 187 ms by bot id=8485867534
Jul 03 19:08:05  INFO:aiogram.event:Update id=976651549 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:08:13  INFO:aiogram.event:Update id=976651550 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:08:14  INFO:aiogram.event:Update id=976651551 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:08:16  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:20  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:24  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:24  INFO:aiogram.event:Update id=976651552 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:08:25  INFO:aiogram.event:Update id=976651553 is handled. Duration 239 ms by bot id=8485867534
Jul 03 19:08:27  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:27  INFO:aiogram.event:Update id=976651554 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:08:30  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:33  INFO:aiogram.event:Update id=976651555 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:08:33  INFO:aiogram.event:Update id=976651556 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:08:35  INFO:aiogram.event:Update id=976651557 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:08:36  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:40  INFO:aiogram.event:Update id=976651558 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:08:40  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:41  INFO:aiogram.event:Update id=976651559 is not handled. Duration 447 ms by bot id=8485867534
Jul 03 19:08:42  INFO:aiogram.event:Update id=976651560 is handled. Duration 477 ms by bot id=8485867534
Jul 03 19:08:44  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:47  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:49  INFO:aiogram.event:Update id=976651561 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:08:51  INFO:aiogram.event:Update id=976651562 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:08:54  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:54  INFO:aiogram.event:Update id=976651563 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:08:55  INFO:aiogram.event:Update id=976651564 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:08:55  INFO:aiogram.event:Update id=976651565 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:08:56  INFO:aiogram.event:Update id=976651566 is not handled. Duration 100 ms by bot id=8485867534
Jul 03 19:08:56  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:57  INFO:aiogram.event:Update id=976651567 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:08:58  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:08:58  INFO:aiogram.event:Update id=976651568 is not handled. Duration 246 ms by bot id=8485867534
Jul 03 19:09:00  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:09:02  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:09:03  INFO:aiogram.event:Update id=976651569 is not handled. Duration 216 ms by bot id=8485867534
Jul 03 19:09:11  INFO:aiogram.event:Update id=976651570 is not handled. Duration 165 ms by bot id=8485867534
Jul 03 19:09:13  INFO:aiogram.event:Update id=976651571 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:09:13  INFO:aiogram.event:Update id=976651572 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:09:17  INFO:aiogram.event:Update id=976651573 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:09:18  INFO:aiogram.event:Update id=976651574 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:09:23  INFO:aiogram.event:Update id=976651575 is handled. Duration 197 ms by bot id=8485867534
Jul 03 19:09:23  INFO:aiogram.event:Update id=976651576 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:09:24  INFO:aiogram.event:Update id=976651577 is not handled. Duration 99 ms by bot id=8485867534
Jul 03 19:09:40  INFO:aiogram.event:Update id=976651578 is not handled. Duration 197 ms by bot id=8485867534
Jul 03 19:09:43  INFO:aiogram.event:Update id=976651579 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:09:48  INFO:aiogram.event:Update id=976651580 is not handled. Duration 100 ms by bot id=8485867534
Jul 03 19:10:01  INFO:aiogram.event:Update id=976651581 is not handled. Duration 491 ms by bot id=8485867534
Jul 03 19:10:02  INFO:aiogram.event:Update id=976651582 is handled. Duration 447 ms by bot id=8485867534
Jul 03 19:10:13  INFO:aiogram.event:Update id=976651583 is handled. Duration 131 ms by bot id=8485867534
Jul 03 19:10:22  INFO:aiogram.event:Update id=976651584 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:10:22  INFO:aiogram.event:Update id=976651585 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 19:10:24  INFO:aiogram.event:Update id=976651586 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:10:28  INFO:aiogram.event:Update id=976651587 is not handled. Duration 100 ms by bot id=8485867534
Jul 03 19:10:38  INFO:aiogram.event:Update id=976651588 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:10:46  INFO:aiogram.event:Update id=976651589 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:10:46  INFO:aiogram.event:Update id=976651590 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:10:46  INFO:aiogram.event:Update id=976651591 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:10:50  INFO:aiogram.event:Update id=976651592 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:10:53  INFO:aiogram.event:Update id=976651593 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:10:56  INFO:aiogram.event:Update id=976651594 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:10:57  INFO:aiogram.event:Update id=976651595 is handled. Duration 96 ms by bot id=8485867534
Jul 03 19:11:16  INFO:aiogram.event:Update id=976651596 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:11:19  INFO:aiogram.event:Update id=976651597 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:11:22  INFO:aiogram.event:Update id=976651599 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:11:22  INFO:aiogram.event:Update id=976651598 is not handled. Duration 180 ms by bot id=8485867534
Jul 03 19:11:29  INFO:aiogram.event:Update id=976651600 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 19:11:33  INFO:aiogram.event:Update id=976651601 is not handled. Duration 149 ms by bot id=8485867534
Jul 03 19:11:34  INFO:aiogram.event:Update id=976651602 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:11:43  INFO:aiogram.event:Update id=976651603 is not handled. Duration 2820 ms by bot id=8485867534
Jul 03 19:11:47  INFO:aiogram.event:Update id=976651604 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:11:52  INFO:aiogram.event:Update id=976651605 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 19:11:54  INFO:aiogram.event:Update id=976651606 is not handled. Duration 189 ms by bot id=8485867534
Jul 03 19:11:55  INFO:aiogram.event:Update id=976651607 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:12:01  INFO:aiogram.event:Update id=976651608 is not handled. Duration 320 ms by bot id=8485867534
Jul 03 19:12:04  INFO:aiogram.event:Update id=976651609 is not handled. Duration 234 ms by bot id=8485867534
Jul 03 19:12:07  INFO:aiogram.event:Update id=976651610 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:12:09  INFO:aiogram.event:Update id=976651611 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:12:10  INFO:aiogram.event:Update id=976651612 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:12:14  INFO:aiogram.event:Update id=976651613 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:12:21  INFO:aiogram.event:Update id=976651614 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:12:25  INFO:aiogram.event:Update id=976651615 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:12:32  INFO:aiogram.event:Update id=976651616 is not handled. Duration 259 ms by bot id=8485867534
Jul 03 19:12:34  INFO:aiogram.event:Update id=976651617 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:12:37  INFO:aiogram.event:Update id=976651618 is not handled. Duration 293 ms by bot id=8485867534
Jul 03 19:12:57  INFO:aiogram.event:Update id=976651619 is not handled. Duration 335 ms by bot id=8485867534
Jul 03 19:12:58  INFO:aiogram.event:Update id=976651620 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 19:13:01  INFO:aiogram.event:Update id=976651621 is not handled. Duration 336 ms by bot id=8485867534
Jul 03 19:13:04  INFO:aiogram.event:Update id=976651622 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:13:19  INFO:aiogram.event:Update id=976651623 is not handled. Duration 165 ms by bot id=8485867534
Jul 03 19:13:22  INFO:aiogram.event:Update id=976651624 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:13:30  INFO:aiogram.event:Update id=976651625 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:13:33  INFO:aiogram.event:Update id=976651626 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:13:35  INFO:aiogram.event:Update id=976651627 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:13:38  INFO:aiogram.event:Update id=976651628 is not handled. Duration 316 ms by bot id=8485867534
Jul 03 19:13:39  INFO:aiogram.event:Update id=976651629 is not handled. Duration 350 ms by bot id=8485867534
Jul 03 19:13:40  INFO:aiogram.event:Update id=976651630 is not handled. Duration 205 ms by bot id=8485867534
Jul 03 19:13:55  INFO:aiogram.event:Update id=976651631 is handled. Duration 107 ms by bot id=8485867534
Jul 03 19:14:02  INFO:aiogram.event:Update id=976651632 is not handled. Duration 210 ms by bot id=8485867534
Jul 03 19:14:07  INFO:aiogram.event:Update id=976651633 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:14:10  INFO:aiogram.event:Update id=976651634 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 19:14:17  INFO:aiogram.event:Update id=976651635 is not handled. Duration 151 ms by bot id=8485867534
Jul 03 19:14:24  INFO:aiogram.event:Update id=976651636 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:14:28  INFO:aiogram.event:Update id=976651637 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 19:14:32  INFO:aiogram.event:Update id=976651638 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:14:34  INFO:aiogram.event:Update id=976651639 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:14:35  INFO:aiogram.event:Update id=976651640 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:14:36  INFO:aiogram.event:Update id=976651641 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:14:37  INFO:aiogram.event:Update id=976651642 is not handled. Duration 228 ms by bot id=8485867534
Jul 03 19:14:52  INFO:aiogram.event:Update id=976651643 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:15:05  INFO:aiogram.event:Update id=976651644 is not handled. Duration 201 ms by bot id=8485867534
Jul 03 19:15:07  INFO:aiogram.event:Update id=976651645 is not handled. Duration 149 ms by bot id=8485867534
Jul 03 19:15:10  INFO:aiogram.event:Update id=976651646 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:15:15  INFO:aiogram.event:Update id=976651647 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:15:16  INFO:aiogram.event:Update id=976651648 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:15:22  INFO:aiogram.event:Update id=976651649 is handled. Duration 88 ms by bot id=8485867534
Jul 03 19:15:26  INFO:aiogram.event:Update id=976651650 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:15:29  INFO:aiogram.event:Update id=976651651 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:15:33  INFO:aiogram.event:Update id=976651652 is not handled. Duration 269 ms by bot id=8485867534
Jul 03 19:15:38  INFO:aiogram.event:Update id=976651653 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:15:40  INFO:aiogram.event:Update id=976651654 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 19:15:43  INFO:aiogram.event:Update id=976651655 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:15:47  INFO:aiogram.event:Update id=976651656 is handled. Duration 131 ms by bot id=8485867534
Jul 03 19:15:52  INFO:aiogram.event:Update id=976651657 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:15:52  INFO:aiogram.event:Update id=976651658 is handled. Duration 119 ms by bot id=8485867534
Jul 03 19:15:59  INFO:aiogram.event:Update id=976651659 is handled. Duration 93 ms by bot id=8485867534
Jul 03 19:16:01  INFO:aiogram.event:Update id=976651660 is handled. Duration 162 ms by bot id=8485867534
Jul 03 19:16:05  INFO:aiogram.event:Update id=976651661 is not handled. Duration 192 ms by bot id=8485867534
Jul 03 19:16:06  INFO:aiogram.event:Update id=976651662 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:16:13  INFO:aiogram.event:Update id=976651663 is handled. Duration 104 ms by bot id=8485867534
Jul 03 19:16:14  INFO:aiogram.event:Update id=976651664 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 19:16:15  INFO:aiogram.event:Update id=976651665 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:16:23  INFO:aiogram.event:Update id=976651666 is not handled. Duration 96 ms by bot id=8485867534
Jul 03 19:16:25  INFO:aiogram.event:Update id=976651667 is handled. Duration 76 ms by bot id=8485867534
Jul 03 19:16:28  INFO:aiogram.event:Update id=976651668 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:16:35  INFO:aiogram.event:Update id=976651669 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 19:16:37  INFO:aiogram.event:Update id=976651670 is not handled. Duration 142 ms by bot id=8485867534
Jul 03 19:16:45  INFO:aiogram.event:Update id=976651671 is handled. Duration 138 ms by bot id=8485867534
Jul 03 19:16:48  INFO:aiogram.event:Update id=976651672 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:16:49  INFO:aiogram.event:Update id=976651673 is handled. Duration 175 ms by bot id=8485867534
Jul 03 19:16:52  INFO:aiogram.event:Update id=976651674 is not handled. Duration 142 ms by bot id=8485867534
Jul 03 19:16:55  INFO:aiogram.event:Update id=976651675 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:17:01  INFO:aiogram.event:Update id=976651676 is handled. Duration 1191 ms by bot id=8485867534
Jul 03 19:17:02  INFO:aiogram.event:Update id=976651677 is not handled. Duration 1664 ms by bot id=8485867534
Jul 03 19:17:10  INFO:aiogram.event:Update id=976651678 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:17:13  INFO:aiogram.event:Update id=976651679 is handled. Duration 83 ms by bot id=8485867534
Jul 03 19:17:19  INFO:aiogram.event:Update id=976651680 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 19:17:22  INFO:aiogram.event:Update id=976651681 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:17:25  INFO:aiogram.event:Update id=976651682 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:17:32  INFO:aiogram.event:Update id=976651683 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:17:38  INFO:aiogram.event:Update id=976651684 is handled. Duration 114 ms by bot id=8485867534
Jul 03 19:17:38  INFO:aiogram.event:Update id=976651685 is not handled. Duration 180 ms by bot id=8485867534
Jul 03 19:17:45  INFO:aiogram.event:Update id=976651686 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:17:47  INFO:aiogram.event:Update id=976651687 is not handled. Duration 168 ms by bot id=8485867534
Jul 03 19:17:52  INFO:aiogram.event:Update id=976651688 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:17:58  INFO:aiogram.event:Update id=976651689 is not handled. Duration 186 ms by bot id=8485867534
Jul 03 19:18:10  INFO:aiogram.event:Update id=976651690 is handled. Duration 119 ms by bot id=8485867534
Jul 03 19:18:18  INFO:aiogram.event:Update id=976651691 is handled. Duration 87 ms by bot id=8485867534
Jul 03 19:18:19  INFO:aiogram.event:Update id=976651692 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:18:25  INFO:aiogram.event:Update id=976651693 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:18:26  INFO:aiogram.event:Update id=976651694 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:18:30  INFO:aiogram.event:Update id=976651695 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 19:18:30  INFO:aiogram.event:Update id=976651696 is not handled. Duration 172 ms by bot id=8485867534
Jul 03 19:18:36  INFO:aiogram.event:Update id=976651697 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:18:38  INFO:aiogram.event:Update id=976651698 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:18:39  INFO:aiogram.event:Update id=976651699 is handled. Duration 110 ms by bot id=8485867534
Jul 03 19:18:44  INFO:aiogram.event:Update id=976651700 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:18:47  INFO:aiogram.event:Update id=976651701 is handled. Duration 103 ms by bot id=8485867534
Jul 03 19:18:47  INFO:aiogram.event:Update id=976651702 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:18:50  INFO:aiogram.event:Update id=976651703 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 19:18:56  INFO:aiogram.event:Update id=976651704 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:18:57  INFO:aiogram.event:Update id=976651705 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:18:57  INFO:aiogram.event:Update id=976651706 is handled. Duration 103 ms by bot id=8485867534
Jul 03 19:18:59  INFO:aiogram.event:Update id=976651707 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:19:01  INFO:aiogram.event:Update id=976651708 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 19:19:04  INFO:aiogram.event:Update id=976651709 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:19:09  INFO:aiogram.event:Update id=976651710 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:19:17  INFO:aiogram.event:Update id=976651711 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:19:18  INFO:aiogram.event:Update id=976651712 is handled. Duration 86 ms by bot id=8485867534
Jul 03 19:19:22  INFO:aiogram.event:Update id=976651713 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:19:24  INFO:aiogram.event:Update id=976651714 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:19:28  INFO:aiogram.event:Update id=976651715 is handled. Duration 83 ms by bot id=8485867534
Jul 03 19:19:30  INFO:aiogram.event:Update id=976651716 is not handled. Duration 182 ms by bot id=8485867534
Jul 03 19:19:31  INFO:aiogram.event:Update id=976651717 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:19:40  INFO:aiogram.event:Update id=976651718 is handled. Duration 143 ms by bot id=8485867534
Jul 03 19:19:44  INFO:aiogram.event:Update id=976651719 is not handled. Duration 100 ms by bot id=8485867534
Jul 03 19:19:46  INFO:aiogram.event:Update id=976651720 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:19:46  INFO:aiogram.event:Update id=976651721 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:19:51  INFO:aiogram.event:Update id=976651722 is handled. Duration 102 ms by bot id=8485867534
Jul 03 19:19:53  INFO:aiogram.event:Update id=976651723 is handled. Duration 96 ms by bot id=8485867534
Jul 03 19:20:19  INFO:aiogram.event:Update id=976651724 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:20:30  INFO:aiogram.event:Update id=976651725 is handled. Duration 176 ms by bot id=8485867534
Jul 03 19:20:34  INFO:aiogram.event:Update id=976651726 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:20:37  INFO:aiogram.event:Update id=976651727 is not handled. Duration 172 ms by bot id=8485867534
Jul 03 19:20:55  INFO:aiogram.event:Update id=976651728 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:21:00  INFO:aiogram.event:Update id=976651729 is not handled. Duration 237 ms by bot id=8485867534
Jul 03 19:21:10  INFO:aiogram.event:Update id=976651730 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:21:15  INFO:aiogram.event:Update id=976651731 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:21:22  INFO:aiogram.event:Update id=976651732 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:21:26  INFO:aiogram.event:Update id=976651733 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:21:29  INFO:aiogram.event:Update id=976651734 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:21:36  INFO:aiogram.event:Update id=976651735 is handled. Duration 122 ms by bot id=8485867534
Jul 03 19:21:41  INFO:aiogram.event:Update id=976651736 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:21:44  INFO:aiogram.event:Update id=976651737 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:21:48  INFO:aiogram.event:Update id=976651738 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:22:00  INFO:aiogram.event:Update id=976651739 is not handled. Duration 306 ms by bot id=8485867534
Jul 03 19:22:03  INFO:aiogram.event:Update id=976651740 is handled. Duration 430 ms by bot id=8485867534
Jul 03 19:22:10  INFO:aiogram.event:Update id=976651741 is handled. Duration 142 ms by bot id=8485867534
Jul 03 19:22:11  INFO:aiogram.event:Update id=976651742 is not handled. Duration 276 ms by bot id=8485867534
Jul 03 19:22:13  INFO:aiogram.event:Update id=976651743 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:22:18  INFO:aiogram.event:Update id=976651744 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:22:24  INFO:aiogram.event:Update id=976651745 is handled. Duration 87 ms by bot id=8485867534
Jul 03 19:22:25  INFO:aiogram.event:Update id=976651746 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:22:28  INFO:aiogram.event:Update id=976651747 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:22:30  INFO:aiogram.event:Update id=976651748 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:22:30  INFO:aiogram.event:Update id=976651749 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:22:31  INFO:aiogram.event:Update id=976651750 is not handled. Duration 147 ms by bot id=8485867534
Jul 03 19:22:32  INFO:aiogram.event:Update id=976651751 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:22:39  INFO:aiogram.event:Update id=976651752 is handled. Duration 110 ms by bot id=8485867534
Jul 03 19:22:40  INFO:aiogram.event:Update id=976651753 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:22:43  INFO:aiogram.event:Update id=976651754 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:22:46  INFO:aiogram.event:Update id=976651755 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:22:48  INFO:aiogram.event:Update id=976651756 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:22:48  INFO:aiogram.event:Update id=976651757 is handled. Duration 85 ms by bot id=8485867534
Jul 03 19:22:49  INFO:aiogram.event:Update id=976651758 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:22:49  INFO:aiogram.event:Update id=976651759 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:22:57  INFO:aiogram.event:Update id=976651760 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:23:01  INFO:aiogram.event:Update id=976651761 is not handled. Duration 424 ms by bot id=8485867534
Jul 03 19:23:04  INFO:aiogram.event:Update id=976651762 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 19:23:10  INFO:aiogram.event:Update id=976651763 is handled. Duration 96 ms by bot id=8485867534
Jul 03 19:23:17  INFO:aiogram.event:Update id=976651764 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:23:23  INFO:aiogram.event:Update id=976651765 is handled. Duration 87 ms by bot id=8485867534
Jul 03 19:23:26  INFO:aiogram.event:Update id=976651766 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:23:35  INFO:aiogram.event:Update id=976651767 is not handled. Duration 156 ms by bot id=8485867534
Jul 03 19:23:50  INFO:aiogram.event:Update id=976651768 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:23:56  INFO:aiogram.event:Update id=976651769 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:23:59  INFO:aiogram.event:Update id=976651770 is handled. Duration 113 ms by bot id=8485867534
Jul 03 19:23:59  INFO:aiogram.event:Update id=976651771 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:24:02  INFO:aiogram.event:Update id=976651772 is not handled. Duration 249 ms by bot id=8485867534
Jul 03 19:24:02  INFO:aiogram.event:Update id=976651773 is not handled. Duration 209 ms by bot id=8485867534
Jul 03 19:24:16  INFO:aiogram.event:Update id=976651774 is handled. Duration 95 ms by bot id=8485867534
Jul 03 19:24:16  INFO:aiogram.event:Update id=976651775 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:24:21  INFO:aiogram.event:Update id=976651776 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 19:24:24  INFO:aiogram.event:Update id=976651777 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:24:27  INFO:aiogram.event:Update id=976651778 is handled. Duration 92 ms by bot id=8485867534
Jul 03 19:24:29  INFO:aiogram.event:Update id=976651779 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:24:33  INFO:aiogram.event:Update id=976651780 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:24:35  INFO:aiogram.event:Update id=976651781 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:24:35  INFO:aiogram.event:Update id=976651782 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:24:36  INFO:aiogram.event:Update id=976651783 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 19:24:54  INFO:aiogram.event:Update id=976651784 is handled. Duration 89 ms by bot id=8485867534
Jul 03 19:24:55  INFO:aiogram.event:Update id=976651785 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:25:00  INFO:aiogram.event:Update id=976651786 is not handled. Duration 252 ms by bot id=8485867534
Jul 03 19:25:01  INFO:aiogram.event:Update id=976651787 is not handled. Duration 365 ms by bot id=8485867534
Jul 03 19:25:03  INFO:aiogram.event:Update id=976651788 is not handled. Duration 193 ms by bot id=8485867534
Jul 03 19:25:08  INFO:aiogram.event:Update id=976651789 is not handled. Duration 217 ms by bot id=8485867534
Jul 03 19:25:14  INFO:aiogram.event:Update id=976651790 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:25:24  INFO:aiogram.event:Update id=976651791 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:25:50  INFO:aiogram.event:Update id=976651792 is handled. Duration 253 ms by bot id=8485867534
Jul 03 19:25:53  INFO:aiogram.event:Update id=976651793 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:25:57  INFO:aiogram.event:Update id=976651794 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:26:09  INFO:aiogram.event:Update id=976651795 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:26:23  INFO:aiogram.event:Update id=976651796 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:26:27  INFO:aiogram.event:Update id=976651797 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:26:33  INFO:aiogram.event:Update id=976651798 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:26:37  INFO:aiogram.event:Update id=976651799 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 19:26:52  INFO:aiogram.event:Update id=976651800 is not handled. Duration 993 ms by bot id=8485867534
Jul 03 19:27:07  INFO:aiogram.event:Update id=976651801 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:27:10  INFO:aiogram.event:Update id=976651802 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 19:27:25  INFO:aiogram.event:Update id=976651803 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:27:47  INFO:aiogram.event:Update id=976651804 is handled. Duration 102 ms by bot id=8485867534
Jul 03 19:27:54  INFO:aiogram.event:Update id=976651805 is handled. Duration 88 ms by bot id=8485867534
Jul 03 19:28:21  INFO:aiogram.event:Update id=976651806 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:28:25  INFO:aiogram.event:Update id=976651807 is handled. Duration 94 ms by bot id=8485867534
Jul 03 19:28:28  INFO:aiogram.event:Update id=976651808 is handled. Duration 73 ms by bot id=8485867534
Jul 03 19:28:37  INFO:aiogram.event:Update id=976651809 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:28:44  INFO:aiogram.event:Update id=976651810 is not handled. Duration 165 ms by bot id=8485867534
Jul 03 19:28:48  INFO:aiogram.event:Update id=976651811 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:28:50  INFO:aiogram.event:Update id=976651812 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:29:17  INFO:aiogram.event:Update id=976651813 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 19:29:18  INFO:aiogram.event:Update id=976651814 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:29:22  INFO:aiogram.event:Update id=976651815 is handled. Duration 105 ms by bot id=8485867534
Jul 03 19:29:22  INFO:aiogram.event:Update id=976651816 is handled. Duration 115 ms by bot id=8485867534
Jul 03 19:29:23  INFO:aiogram.event:Update id=976651817 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:29:50  INFO:aiogram.event:Update id=976651818 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:30:15  INFO:aiogram.event:Update id=976651819 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:30:16  INFO:aiogram.event:Update id=976651820 is handled. Duration 94 ms by bot id=8485867534
Jul 03 19:30:22  INFO:aiogram.event:Update id=976651821 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 19:30:39  INFO:aiogram.event:Update id=976651822 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 19:30:46  INFO:aiogram.event:Update id=976651823 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:31:07  INFO:aiogram.event:Update id=976651824 is handled. Duration 115 ms by bot id=8485867534
Jul 03 19:31:07  INFO:aiogram.event:Update id=976651825 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:31:14  INFO:aiogram.event:Update id=976651826 is not handled. Duration 151 ms by bot id=8485867534
Jul 03 19:31:19  INFO:aiogram.event:Update id=976651827 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:31:24  INFO:aiogram.event:Update id=976651828 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:31:24  INFO:aiogram.event:Update id=976651829 is handled. Duration 110 ms by bot id=8485867534
Jul 03 19:31:47  INFO:aiogram.event:Update id=976651830 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:31:52  INFO:aiogram.event:Update id=976651831 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:32:01  INFO:aiogram.event:Update id=976651832 is handled. Duration 207 ms by bot id=8485867534
Jul 03 19:32:07  INFO:aiogram.event:Update id=976651833 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:32:16  INFO:aiogram.event:Update id=976651834 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:32:19  INFO:aiogram.event:Update id=976651835 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:32:20  INFO:aiogram.event:Update id=976651836 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:32:25  INFO:aiogram.event:Update id=976651837 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:32:26  INFO:aiogram.event:Update id=976651838 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:32:28  INFO:aiogram.event:Update id=976651839 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:32:32  INFO:aiogram.event:Update id=976651840 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:32:35  INFO:aiogram.event:Update id=976651841 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:32:37  INFO:aiogram.event:Update id=976651842 is handled. Duration 81 ms by bot id=8485867534
Jul 03 19:32:38  INFO:aiogram.event:Update id=976651843 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:32:44  INFO:aiogram.event:Update id=976651844 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:32:54  INFO:aiogram.event:Update id=976651845 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:32:54  INFO:aiogram.event:Update id=976651846 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:32:56  INFO:aiogram.event:Update id=976651847 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:32:56  INFO:aiogram.event:Update id=976651848 is not handled. Duration 171 ms by bot id=8485867534
Jul 03 19:32:58  INFO:aiogram.event:Update id=976651849 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:32:59  INFO:aiogram.event:Update id=976651850 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:33:01  INFO:aiogram.event:Update id=976651851 is not handled. Duration 182 ms by bot id=8485867534
Jul 03 19:33:04  INFO:aiogram.event:Update id=976651852 is handled. Duration 86 ms by bot id=8485867534
Jul 03 19:33:05  INFO:aiogram.event:Update id=976651853 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:33:08  INFO:aiogram.event:Update id=976651854 is handled. Duration 97 ms by bot id=8485867534
Jul 03 19:33:09  INFO:aiogram.event:Update id=976651855 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:33:10  INFO:aiogram.event:Update id=976651856 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:33:16  INFO:aiogram.event:Update id=976651857 is not handled. Duration 171 ms by bot id=8485867534
Jul 03 19:33:19  INFO:aiogram.event:Update id=976651858 is handled. Duration 317 ms by bot id=8485867534
Jul 03 19:33:22  INFO:aiogram.event:Update id=976651859 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:33:24  INFO:aiogram.event:Update id=976651860 is handled. Duration 248 ms by bot id=8485867534
Jul 03 19:33:25  INFO:aiogram.event:Update id=976651861 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:33:27  INFO:aiogram.event:Update id=976651862 is handled. Duration 245 ms by bot id=8485867534
Jul 03 19:33:33  INFO:aiogram.event:Update id=976651863 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:33:37  INFO:aiogram.event:Update id=976651864 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:33:42  INFO:aiogram.event:Update id=976651865 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:33:44  INFO:aiogram.event:Update id=976651866 is not handled. Duration 98 ms by bot id=8485867534
Jul 03 19:33:46  INFO:aiogram.event:Update id=976651867 is not handled. Duration 97 ms by bot id=8485867534
Jul 03 19:33:46  INFO:aiogram.event:Update id=976651868 is not handled. Duration 99 ms by bot id=8485867534
Jul 03 19:33:48  INFO:aiogram.event:Update id=976651869 is handled. Duration 94 ms by bot id=8485867534
Jul 03 19:33:51  INFO:aiogram.event:Update id=976651870 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:33:53  INFO:aiogram.event:Update id=976651871 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 19:33:54  INFO:aiogram.event:Update id=976651872 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:33:54  INFO:aiogram.event:Update id=976651873 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:33:56  INFO:aiogram.event:Update id=976651874 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:33:56  INFO:aiogram.event:Update id=976651875 is handled. Duration 103 ms by bot id=8485867534
Jul 03 19:33:56  INFO:aiogram.event:Update id=976651876 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:34:02  INFO:aiogram.event:Update id=976651877 is not handled. Duration 173 ms by bot id=8485867534
Jul 03 19:34:03  INFO:aiogram.event:Update id=976651878 is handled. Duration 115 ms by bot id=8485867534
Jul 03 19:34:03  INFO:aiogram.event:Update id=976651879 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 19:34:08  INFO:aiogram.event:Update id=976651880 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:34:09  INFO:aiogram.event:Update id=976651881 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:34:11  INFO:aiogram.event:Update id=976651882 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:34:13  INFO:aiogram.event:Update id=976651883 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:34:14  INFO:aiogram.event:Update id=976651884 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:34:24  INFO:aiogram.event:Update id=976651885 is not handled. Duration 182 ms by bot id=8485867534
Jul 03 19:34:24  INFO:aiogram.event:Update id=976651886 is not handled. Duration 175 ms by bot id=8485867534
Jul 03 19:34:27  INFO:aiogram.event:Update id=976651887 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:34:27  INFO:aiogram.event:Update id=976651888 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:34:29  INFO:aiogram.event:Update id=976651889 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:34:29  INFO:aiogram.event:Update id=976651890 is handled. Duration 96 ms by bot id=8485867534
Jul 03 19:34:33  INFO:aiogram.event:Update id=976651891 is handled. Duration 179 ms by bot id=8485867534
Jul 03 19:34:34  INFO:aiogram.event:Update id=976651892 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:34:36  INFO:aiogram.event:Update id=976651893 is not handled. Duration 184 ms by bot id=8485867534
Jul 03 19:34:38  INFO:aiogram.event:Update id=976651894 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:34:43  INFO:aiogram.event:Update id=976651895 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:34:43  INFO:aiogram.event:Update id=976651896 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:34:50  INFO:aiogram.event:Update id=976651897 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:34:53  INFO:aiogram.event:Update id=976651898 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:34:54  INFO:aiogram.event:Update id=976651899 is not handled. Duration 170 ms by bot id=8485867534
Jul 03 19:34:59  INFO:aiogram.event:Update id=976651900 is handled. Duration 97 ms by bot id=8485867534
Jul 03 19:34:59  INFO:aiogram.event:Update id=976651901 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:35:03  INFO:aiogram.event:Update id=976651902 is not handled. Duration 253 ms by bot id=8485867534
Jul 03 19:35:06  INFO:aiogram.event:Update id=976651903 is not handled. Duration 272 ms by bot id=8485867534
Jul 03 19:35:17  INFO:aiogram.event:Update id=976651904 is not handled. Duration 1413 ms by bot id=8485867534
Jul 03 19:35:24  INFO:aiogram.event:Update id=976651905 is not handled. Duration 209 ms by bot id=8485867534
Jul 03 19:35:24  INFO:aiogram.event:Update id=976651906 is handled. Duration 125 ms by bot id=8485867534
Jul 03 19:35:25  INFO:aiogram.event:Update id=976651907 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:35:27  INFO:aiogram.event:Update id=976651908 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:35:29  INFO:aiogram.event:Update id=976651909 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:35:31  INFO:aiogram.event:Update id=976651910 is not handled. Duration 358 ms by bot id=8485867534
Jul 03 19:35:33  INFO:aiogram.event:Update id=976651911 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 19:35:37  INFO:aiogram.event:Update id=976651912 is not handled. Duration 287 ms by bot id=8485867534
Jul 03 19:35:42  INFO:aiogram.event:Update id=976651913 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:35:45  INFO:aiogram.event:Update id=976651914 is not handled. Duration 250 ms by bot id=8485867534
Jul 03 19:35:46  INFO:aiogram.event:Update id=976651915 is not handled. Duration 167 ms by bot id=8485867534
Jul 03 19:35:47  INFO:aiogram.event:Update id=976651916 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:35:48  INFO:aiogram.event:Update id=976651917 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:35:48  INFO:aiogram.event:Update id=976651918 is handled. Duration 95 ms by bot id=8485867534
Jul 03 19:35:50  INFO:aiogram.event:Update id=976651919 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:35:50  INFO:aiogram.event:Update id=976651920 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:35:57  INFO:aiogram.event:Update id=976651921 is handled. Duration 86 ms by bot id=8485867534
Jul 03 19:36:00  INFO:aiogram.event:Update id=976651922 is not handled. Duration 202 ms by bot id=8485867534
Jul 03 19:36:07  INFO:aiogram.event:Update id=976651923 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:36:11  INFO:aiogram.event:Update id=976651924 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:36:20  INFO:aiogram.event:Update id=976651925 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:36:21  INFO:aiogram.event:Update id=976651926 is handled. Duration 99 ms by bot id=8485867534
Jul 03 19:36:36  INFO:aiogram.event:Update id=976651927 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:36:44  INFO:aiogram.event:Update id=976651928 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:36:44  INFO:aiogram.event:Update id=976651929 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:36:47  INFO:aiogram.event:Update id=976651930 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:36:49  INFO:aiogram.event:Update id=976651931 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 19:36:51  INFO:aiogram.event:Update id=976651932 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:36:52  INFO:aiogram.event:Update id=976651933 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:36:55  INFO:aiogram.event:Update id=976651934 is handled. Duration 166 ms by bot id=8485867534
Jul 03 19:36:56  INFO:aiogram.event:Update id=976651935 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:37:07  INFO:aiogram.event:Update id=976651936 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:37:10  INFO:aiogram.event:Update id=976651937 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 19:37:11  INFO:aiogram.event:Update id=976651938 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:37:12  INFO:aiogram.event:Update id=976651939 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:37:16  INFO:aiogram.event:Update id=976651940 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:37:21  INFO:aiogram.event:Update id=976651941 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 19:37:21  INFO:aiogram.event:Update id=976651942 is not handled. Duration 199 ms by bot id=8485867534
Jul 03 19:37:28  INFO:aiogram.event:Update id=976651943 is handled. Duration 117 ms by bot id=8485867534
Jul 03 19:37:32  INFO:aiogram.event:Update id=976651944 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:37:37  INFO:aiogram.event:Update id=976651945 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:37:38  INFO:aiogram.event:Update id=976651946 is not handled. Duration 195 ms by bot id=8485867534
Jul 03 19:37:40  INFO:aiogram.event:Update id=976651947 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:37:40  INFO:aiogram.event:Update id=976651948 is not handled. Duration 322 ms by bot id=8485867534
Jul 03 19:37:41  INFO:aiogram.event:Update id=976651949 is not handled. Duration 214 ms by bot id=8485867534
Jul 03 19:37:45  INFO:aiogram.event:Update id=976651950 is not handled. Duration 192 ms by bot id=8485867534
Jul 03 19:37:45  INFO:aiogram.event:Update id=976651951 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:37:50  INFO:aiogram.event:Update id=976651952 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 19:37:50  INFO:aiogram.event:Update id=976651953 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:37:56  INFO:aiogram.event:Update id=976651954 is not handled. Duration 175 ms by bot id=8485867534
Jul 03 19:37:57  INFO:aiogram.event:Update id=976651955 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:38:00  INFO:aiogram.event:Update id=976651956 is not handled. Duration 372 ms by bot id=8485867534
Jul 03 19:38:01  INFO:aiogram.event:Update id=976651957 is not handled. Duration 240 ms by bot id=8485867534
Jul 03 19:38:04  INFO:aiogram.event:Update id=976651958 is not handled. Duration 269 ms by bot id=8485867534
Jul 03 19:38:07  INFO:aiogram.event:Update id=976651959 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:38:10  INFO:aiogram.event:Update id=976651960 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:38:10  INFO:aiogram.event:Update id=976651961 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:38:13  INFO:aiogram.event:Update id=976651962 is handled. Duration 90 ms by bot id=8485867534
Jul 03 19:38:14  INFO:aiogram.event:Update id=976651963 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:38:14  INFO:aiogram.event:Update id=976651964 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:38:16  INFO:aiogram.event:Update id=976651965 is not handled. Duration 170 ms by bot id=8485867534
Jul 03 19:38:18  INFO:aiogram.event:Update id=976651966 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:38:19  INFO:aiogram.event:Update id=976651967 is handled. Duration 99 ms by bot id=8485867534
Jul 03 19:38:20  INFO:aiogram.event:Update id=976651968 is handled. Duration 125 ms by bot id=8485867534
Jul 03 19:38:23  INFO:aiogram.event:Update id=976651969 is handled. Duration 141 ms by bot id=8485867534
Jul 03 19:38:24  INFO:aiogram.event:Update id=976651970 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:38:29  INFO:aiogram.event:Update id=976651971 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:38:29  INFO:aiogram.event:Update id=976651972 is handled. Duration 128 ms by bot id=8485867534
Jul 03 19:38:29  INFO:aiogram.event:Update id=976651973 is handled. Duration 235 ms by bot id=8485867534
Jul 03 19:38:32  INFO:aiogram.event:Update id=976651974 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:38:40  INFO:aiogram.event:Update id=976651975 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:38:49  INFO:aiogram.event:Update id=976651976 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:38:54  INFO:aiogram.event:Update id=976651977 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:39:04  INFO:aiogram.event:Update id=976651978 is not handled. Duration 302 ms by bot id=8485867534
Jul 03 19:39:13  INFO:aiogram.event:Update id=976651979 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:39:14  INFO:aiogram.event:Update id=976651980 is not handled. Duration 164 ms by bot id=8485867534
Jul 03 19:39:14  INFO:aiogram.event:Update id=976651981 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:39:16  INFO:aiogram.event:Update id=976651982 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:39:19  INFO:aiogram.event:Update id=976651983 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:39:20  INFO:aiogram.event:Update id=976651984 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:39:22  INFO:aiogram.event:Update id=976651985 is not handled. Duration 196 ms by bot id=8485867534
Jul 03 19:39:24  INFO:aiogram.event:Update id=976651986 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:39:26  INFO:aiogram.event:Update id=976651987 is not handled. Duration 188 ms by bot id=8485867534
Jul 03 19:39:32  INFO:aiogram.event:Update id=976651988 is not handled. Duration 147 ms by bot id=8485867534
Jul 03 19:39:34  INFO:aiogram.event:Update id=976651989 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:39:37  INFO:aiogram.event:Update id=976651990 is not handled. Duration 223 ms by bot id=8485867534
Jul 03 19:39:41  INFO:aiogram.event:Update id=976651991 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:39:47  INFO:aiogram.event:Update id=976651992 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 19:39:50  INFO:aiogram.event:Update id=976651993 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:39:51  INFO:aiogram.event:Update id=976651994 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:40:05  INFO:aiogram.event:Update id=976651995 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:40:06  INFO:aiogram.event:Update id=976651996 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:40:11  INFO:aiogram.event:Update id=976651997 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:40:15  INFO:aiogram.event:Update id=976651998 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:40:15  INFO:aiogram.event:Update id=976651999 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:40:18  INFO:aiogram.event:Update id=976652000 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:40:20  INFO:aiogram.event:Update id=976652001 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:40:24  INFO:aiogram.event:Update id=976652002 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:40:25  INFO:aiogram.event:Update id=976652003 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:40:28  INFO:aiogram.event:Update id=976652004 is handled. Duration 198 ms by bot id=8485867534
Jul 03 19:40:29  INFO:aiogram.event:Update id=976652005 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:40:30  INFO:aiogram.event:Update id=976652006 is not handled. Duration 182 ms by bot id=8485867534
Jul 03 19:40:32  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getUserProfilePhotos?user_id=682822210&limit=1 "HTTP/1.1 200 OK"
Jul 03 19:40:32  INFO:httpx:HTTP Request: GET https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/getFile?file_id=AgACAgIAAxUAAWpHlpv8e6fgFA-2xp3AA_hQreVJAAJWC2sbQgqzKAAB53TH7VdEzgEAAwIAA2EAAzwE "HTTP/1.1 200 OK"
Jul 03 19:40:32  INFO:httpx:HTTP Request: GET https://api.telegram.org/file/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/photos/file_42.jpg "HTTP/1.1 200 OK"
Jul 03 19:40:33  INFO:aiogram.event:Update id=976652007 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 19:40:33  INFO:aiogram.event:Update id=976652008 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:40:34  INFO:aiogram.event:Update id=976652009 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:40:35  INFO:aiogram.event:Update id=976652010 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 19:40:38  INFO:aiogram.event:Update id=976652011 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:40:39  INFO:aiogram.event:Update id=976652012 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:40:40  INFO:aiogram.event:Update id=976652013 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:40:41  INFO:aiogram.event:Update id=976652014 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 19:40:42  INFO:aiogram.event:Update id=976652015 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:40:44  INFO:aiogram.event:Update id=976652016 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 19:40:45  INFO:aiogram.event:Update id=976652017 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:40:49  INFO:aiogram.event:Update id=976652018 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:40:53  INFO:aiogram.event:Update id=976652019 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:40:54  INFO:aiogram.event:Update id=976652020 is not handled. Duration 111 ms by bot id=8485867534
Jul 03 19:40:57  INFO:aiogram.event:Update id=976652021 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:40:58  INFO:aiogram.event:Update id=976652022 is not handled. Duration 151 ms by bot id=8485867534
Jul 03 19:40:59  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:00  INFO:aiogram.event:Update id=976652023 is not handled. Duration 368 ms by bot id=8485867534
Jul 03 19:41:02  INFO:aiogram.event:Update id=976652024 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 19:41:03  INFO:aiogram.event:Update id=976652025 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:41:03  INFO:aiogram.event:Update id=976652026 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:41:03  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:06  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:06  INFO:aiogram.event:Update id=976652027 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:41:07  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:09  INFO:aiogram.event:Update id=976652028 is not handled. Duration 95 ms by bot id=8485867534
Jul 03 19:41:12  INFO:aiogram.event:Update id=976652029 is not handled. Duration 142 ms by bot id=8485867534
Jul 03 19:41:13  INFO:aiogram.event:Update id=976652030 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:41:15  INFO:aiogram.event:Update id=976652031 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:41:19  INFO:aiogram.event:Update id=976652032 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:41:21  INFO:aiogram.event:Update id=976652033 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:41:23  INFO:aiogram.event:Update id=976652034 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:41:26  INFO:aiogram.event:Update id=976652035 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:41:28  INFO:aiogram.event:Update id=976652036 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:41:28  INFO:aiogram.event:Update id=976652037 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:41:33  INFO:aiogram.event:Update id=976652038 is not handled. Duration 95 ms by bot id=8485867534
Jul 03 19:41:34  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:35  INFO:aiogram.event:Update id=976652039 is not handled. Duration 103 ms by bot id=8485867534
Jul 03 19:41:37  INFO:aiogram.event:Update id=976652040 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:41:42  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:42  INFO:aiogram.event:Update id=976652041 is not handled. Duration 90 ms by bot id=8485867534
Jul 03 19:41:44  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:41:44  INFO:aiogram.event:Update id=976652042 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:41:46  INFO:aiogram.event:Update id=976652043 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 19:41:52  INFO:aiogram.event:Update id=976652044 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 19:41:58  INFO:aiogram.event:Update id=976652045 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:42:01  INFO:aiogram.event:Update id=976652046 is not handled. Duration 349 ms by bot id=8485867534
Jul 03 19:42:03  INFO:aiogram.event:Update id=976652047 is not handled. Duration 190 ms by bot id=8485867534
Jul 03 19:42:04  INFO:aiogram.event:Update id=976652048 is not handled. Duration 214 ms by bot id=8485867534
Jul 03 19:42:11  INFO:aiogram.event:Update id=976652049 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:42:14  INFO:aiogram.event:Update id=976652050 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:42:22  INFO:aiogram.event:Update id=976652051 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:42:28  INFO:aiogram.event:Update id=976652052 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:42:30  INFO:aiogram.event:Update id=976652053 is not handled. Duration 197 ms by bot id=8485867534
Jul 03 19:42:42  INFO:aiogram.event:Update id=976652054 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:42:46  INFO:aiogram.event:Update id=976652055 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:42:53  INFO:aiogram.event:Update id=976652056 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:42:56  INFO:aiogram.event:Update id=976652057 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:43:00  INFO:aiogram.event:Update id=976652058 is not handled. Duration 286 ms by bot id=8485867534
Jul 03 19:43:02  INFO:aiogram.event:Update id=976652059 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:43:03  INFO:aiogram.event:Update id=976652060 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:43:04  INFO:aiogram.event:Update id=976652061 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:43:07  INFO:aiogram.event:Update id=976652062 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:43:10  INFO:aiogram.event:Update id=976652063 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:43:17  INFO:aiogram.event:Update id=976652064 is handled. Duration 266 ms by bot id=8485867534
Jul 03 19:43:18  INFO:aiogram.event:Update id=976652065 is handled. Duration 308 ms by bot id=8485867534
Jul 03 19:43:25  INFO:aiogram.event:Update id=976652066 is handled. Duration 93 ms by bot id=8485867534
Jul 03 19:43:36  INFO:aiogram.event:Update id=976652067 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:43:37  INFO:aiogram.event:Update id=976652068 is not handled. Duration 166 ms by bot id=8485867534
Jul 03 19:43:42  INFO:aiogram.event:Update id=976652069 is not handled. Duration 941 ms by bot id=8485867534
Jul 03 19:43:44  INFO:aiogram.event:Update id=976652070 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:43:47  INFO:aiogram.event:Update id=976652071 is handled. Duration 186 ms by bot id=8485867534
Jul 03 19:43:48  INFO:aiogram.event:Update id=976652072 is not handled. Duration 168 ms by bot id=8485867534
Jul 03 19:43:51  INFO:aiogram.event:Update id=976652073 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:43:53  INFO:aiogram.event:Update id=976652074 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:44:03  INFO:aiogram.event:Update id=976652075 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:44:09  INFO:aiogram.event:Update id=976652076 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:44:16  INFO:aiogram.event:Update id=976652077 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:44:21  INFO:aiogram.event:Update id=976652078 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:44:24  INFO:aiogram.event:Update id=976652079 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 19:44:24  INFO:aiogram.event:Update id=976652080 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:44:31  INFO:aiogram.event:Update id=976652081 is not handled. Duration 188 ms by bot id=8485867534
Jul 03 19:44:34  INFO:aiogram.event:Update id=976652082 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:44:35  INFO:aiogram.event:Update id=976652083 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:44:37  INFO:aiogram.event:Update id=976652084 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:44:38  INFO:aiogram.event:Update id=976652085 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:44:43  INFO:aiogram.event:Update id=976652086 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:44:49  INFO:aiogram.event:Update id=976652087 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:44:50  INFO:aiogram.event:Update id=976652088 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:44:57  INFO:aiogram.event:Update id=976652089 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:44:58  INFO:aiogram.event:Update id=976652090 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 19:44:59  INFO:aiogram.event:Update id=976652091 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 19:44:59  INFO:aiogram.event:Update id=976652092 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:45:03  INFO:aiogram.event:Update id=976652093 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:45:07  INFO:aiogram.event:Update id=976652094 is not handled. Duration 269 ms by bot id=8485867534
Jul 03 19:45:10  INFO:aiogram.event:Update id=976652095 is not handled. Duration 425 ms by bot id=8485867534
Jul 03 19:45:12  INFO:aiogram.event:Update id=976652096 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:45:15  INFO:aiogram.event:Update id=976652097 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:45:17  INFO:aiogram.event:Update id=976652098 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:45:19  INFO:aiogram.event:Update id=976652099 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:45:29  INFO:aiogram.event:Update id=976652100 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:45:37  INFO:aiogram.event:Update id=976652101 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:45:42  INFO:aiogram.event:Update id=976652102 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:45:47  INFO:aiogram.event:Update id=976652103 is handled. Duration 155 ms by bot id=8485867534
Jul 03 19:45:53  INFO:aiogram.event:Update id=976652104 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:46:12  INFO:aiogram.event:Update id=976652105 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:46:12  INFO:aiogram.event:Update id=976652106 is not handled. Duration 202 ms by bot id=8485867534
Jul 03 19:46:16  INFO:aiogram.event:Update id=976652107 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:46:20  INFO:aiogram.event:Update id=976652108 is not handled. Duration 158 ms by bot id=8485867534
Jul 03 19:46:28  INFO:aiogram.event:Update id=976652109 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 19:46:31  INFO:aiogram.event:Update id=976652110 is not handled. Duration 254 ms by bot id=8485867534
Jul 03 19:46:35  INFO:aiogram.event:Update id=976652111 is not handled. Duration 164 ms by bot id=8485867534
Jul 03 19:46:39  INFO:aiogram.event:Update id=976652112 is not handled. Duration 149 ms by bot id=8485867534
Jul 03 19:46:50  INFO:aiogram.event:Update id=976652113 is not handled. Duration 181 ms by bot id=8485867534
Jul 03 19:46:55  INFO:aiogram.event:Update id=976652114 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:46:56  INFO:aiogram.event:Update id=976652115 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:46:58  INFO:aiogram.event:Update id=976652116 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:47:01  INFO:aiogram.event:Update id=976652117 is not handled. Duration 264 ms by bot id=8485867534
Jul 03 19:47:04  INFO:aiogram.event:Update id=976652118 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:47:06  INFO:aiogram.event:Update id=976652119 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:47:07  INFO:aiogram.event:Update id=976652120 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:47:08  INFO:aiogram.event:Update id=976652121 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:47:12  INFO:aiogram.event:Update id=976652122 is not handled. Duration 173 ms by bot id=8485867534
Jul 03 19:47:15  INFO:aiogram.event:Update id=976652123 is not handled. Duration 159 ms by bot id=8485867534
Jul 03 19:47:18  INFO:aiogram.event:Update id=976652124 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:47:23  INFO:aiogram.event:Update id=976652125 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:47:27  INFO:aiogram.event:Update id=976652126 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:47:30  INFO:aiogram.event:Update id=976652127 is not handled. Duration 207 ms by bot id=8485867534
Jul 03 19:47:31  INFO:aiogram.event:Update id=976652128 is not handled. Duration 246 ms by bot id=8485867534
Jul 03 19:47:31  INFO:aiogram.event:Update id=976652129 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:47:34  INFO:aiogram.event:Update id=976652130 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 19:47:36  INFO:aiogram.event:Update id=976652131 is not handled. Duration 238 ms by bot id=8485867534
Jul 03 19:47:38  INFO:aiogram.event:Update id=976652132 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:47:40  INFO:aiogram.event:Update id=976652133 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:47:41  INFO:aiogram.event:Update id=976652134 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 19:47:43  INFO:aiogram.event:Update id=976652135 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:47:47  INFO:aiogram.event:Update id=976652136 is handled. Duration 362 ms by bot id=8485867534
Jul 03 19:47:48  INFO:aiogram.event:Update id=976652137 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:47:50  INFO:aiogram.event:Update id=976652138 is handled. Duration 291 ms by bot id=8485867534
Jul 03 19:47:53  INFO:aiogram.event:Update id=976652139 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:47:53  INFO:aiogram.event:Update id=976652140 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:48:00  INFO:aiogram.event:Update id=976652141 is not handled. Duration 407 ms by bot id=8485867534
Jul 03 19:48:00  INFO:aiogram.event:Update id=976652142 is not handled. Duration 311 ms by bot id=8485867534
Jul 03 19:48:01  INFO:aiogram.event:Update id=976652143 is not handled. Duration 327 ms by bot id=8485867534
Jul 03 19:48:01  INFO:aiogram.event:Update id=976652144 is not handled. Duration 289 ms by bot id=8485867534
Jul 03 19:48:04  INFO:aiogram.event:Update id=976652145 is handled. Duration 288 ms by bot id=8485867534
Jul 03 19:48:04  INFO:aiogram.event:Update id=976652146 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:48:07  INFO:aiogram.event:Update id=976652147 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:48:07  INFO:aiogram.event:Update id=976652148 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:48:09  INFO:aiogram.event:Update id=976652149 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:48:10  INFO:aiogram.event:Update id=976652150 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:48:10  INFO:aiogram.event:Update id=976652151 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:48:16  INFO:aiogram.event:Update id=976652152 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:48:19  INFO:aiogram.event:Update id=976652153 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:48:20  INFO:aiogram.event:Update id=976652154 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:48:21  INFO:aiogram.event:Update id=976652155 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 19:48:27  INFO:aiogram.event:Update id=976652156 is handled. Duration 245 ms by bot id=8485867534
Jul 03 19:48:29  INFO:aiogram.event:Update id=976652157 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 19:48:33  INFO:aiogram.event:Update id=976652158 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:48:35  INFO:aiogram.event:Update id=976652159 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:48:36  INFO:aiogram.event:Update id=976652160 is not handled. Duration 253 ms by bot id=8485867534
Jul 03 19:48:38  INFO:aiogram.event:Update id=976652161 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:48:39  INFO:aiogram.event:Update id=976652162 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:48:39  INFO:aiogram.event:Update id=976652163 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:48:42  INFO:aiogram.event:Update id=976652164 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:48:42  INFO:aiogram.event:Update id=976652165 is not handled. Duration 102 ms by bot id=8485867534
Jul 03 19:48:45  INFO:aiogram.event:Update id=976652166 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:48:46  INFO:aiogram.event:Update id=976652167 is not handled. Duration 173 ms by bot id=8485867534
Jul 03 19:48:47  INFO:aiogram.event:Update id=976652168 is not handled. Duration 92 ms by bot id=8485867534
Jul 03 19:48:49  INFO:aiogram.event:Update id=976652169 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:48:50  INFO:aiogram.event:Update id=976652170 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:48:51  INFO:aiogram.event:Update id=976652171 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 19:48:52  INFO:aiogram.event:Update id=976652172 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:48:54  INFO:aiogram.event:Update id=976652173 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 19:48:56  INFO:aiogram.event:Update id=976652174 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:48:59  INFO:aiogram.event:Update id=976652175 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:48:59  INFO:aiogram.event:Update id=976652176 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 19:48:59  INFO:aiogram.event:Update id=976652177 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:49:00  INFO:aiogram.event:Update id=976652178 is not handled. Duration 253 ms by bot id=8485867534
Jul 03 19:49:03  INFO:aiogram.event:Update id=976652179 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:49:04  INFO:aiogram.event:Update id=976652180 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:49:05  INFO:aiogram.event:Update id=976652181 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:49:09  INFO:aiogram.event:Update id=976652182 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 19:49:10  INFO:aiogram.event:Update id=976652183 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 19:49:17  INFO:aiogram.event:Update id=976652184 is not handled. Duration 166 ms by bot id=8485867534
Jul 03 19:49:17  INFO:aiogram.event:Update id=976652185 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:49:18  INFO:aiogram.event:Update id=976652186 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 19:49:19  INFO:aiogram.event:Update id=976652187 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 19:49:20  INFO:aiogram.event:Update id=976652188 is not handled. Duration 157 ms by bot id=8485867534
Jul 03 19:49:20  INFO:aiogram.event:Update id=976652189 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:49:22  INFO:aiogram.event:Update id=976652190 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:49:25  INFO:aiogram.event:Update id=976652191 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 19:49:30  INFO:aiogram.event:Update id=976652192 is not handled. Duration 335 ms by bot id=8485867534
Jul 03 19:49:30  INFO:aiogram.event:Update id=976652193 is not handled. Duration 181 ms by bot id=8485867534
Jul 03 19:49:33  INFO:aiogram.event:Update id=976652194 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 19:49:34  INFO:aiogram.event:Update id=976652195 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 19:49:34  INFO:aiogram.event:Update id=976652196 is not handled. Duration 142 ms by bot id=8485867534
Jul 03 19:49:38  INFO:aiogram.event:Update id=976652197 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:49:43  INFO:aiogram.event:Update id=976652198 is not handled. Duration 151 ms by bot id=8485867534
Jul 03 19:49:48  INFO:aiogram.event:Update id=976652199 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:49:49  INFO:aiogram.event:Update id=976652200 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:49:51  INFO:aiogram.event:Update id=976652201 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:49:52  INFO:aiogram.event:Update id=976652202 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 19:49:53  INFO:aiogram.event:Update id=976652203 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:49:53  INFO:aiogram.event:Update id=976652204 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:49:56  INFO:aiogram.event:Update id=976652205 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:49:57  INFO:aiogram.event:Update id=976652206 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:49:59  INFO:aiogram.event:Update id=976652207 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 19:50:01  INFO:aiogram.event:Update id=976652208 is not handled. Duration 188 ms by bot id=8485867534
Jul 03 19:50:01  INFO:aiogram.event:Update id=976652209 is not handled. Duration 234 ms by bot id=8485867534
Jul 03 19:50:02  INFO:aiogram.event:Update id=976652210 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 19:50:06  INFO:aiogram.event:Update id=976652211 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:50:07  INFO:aiogram.event:Update id=976652212 is not handled. Duration 186 ms by bot id=8485867534
Jul 03 19:50:09  INFO:aiogram.event:Update id=976652213 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:50:10  INFO:aiogram.event:Update id=976652214 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:50:16  INFO:aiogram.event:Update id=976652215 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:50:17  INFO:aiogram.event:Update id=976652216 is not handled. Duration 94 ms by bot id=8485867534
Jul 03 19:50:20  INFO:aiogram.event:Update id=976652217 is not handled. Duration 102 ms by bot id=8485867534
Jul 03 19:50:23  INFO:aiogram.event:Update id=976652218 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:50:24  INFO:aiogram.event:Update id=976652219 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:50:25  INFO:aiogram.event:Update id=976652220 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:50:26  INFO:aiogram.event:Update id=976652221 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 19:50:28  INFO:aiogram.event:Update id=976652222 is not handled. Duration 101 ms by bot id=8485867534
Jul 03 19:50:29  INFO:aiogram.event:Update id=976652223 is not handled. Duration 97 ms by bot id=8485867534
Jul 03 19:50:30  INFO:aiogram.event:Update id=976652224 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 19:50:32  INFO:aiogram.event:Update id=976652225 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:50:36  INFO:aiogram.event:Update id=976652226 is not handled. Duration 207 ms by bot id=8485867534
Jul 03 19:50:37  INFO:aiogram.event:Update id=976652227 is not handled. Duration 164 ms by bot id=8485867534
Jul 03 19:50:37  INFO:aiogram.event:Update id=976652228 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:50:40  INFO:aiogram.event:Update id=976652229 is handled. Duration 207 ms by bot id=8485867534
Jul 03 19:50:49  INFO:aiogram.event:Update id=976652230 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:50:50  INFO:aiogram.event:Update id=976652231 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 19:50:54  INFO:aiogram.event:Update id=976652232 is not handled. Duration 94 ms by bot id=8485867534
Jul 03 19:50:56  INFO:aiogram.event:Update id=976652233 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 19:51:02  INFO:aiogram.event:Update id=976652234 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 19:51:04  INFO:aiogram.event:Update id=976652235 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 19:51:05  INFO:aiogram.event:Update id=976652236 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 19:51:10  INFO:aiogram.event:Update id=976652237 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 19:51:10  INFO:aiogram.event:Update id=976652238 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 19:51:13  INFO:aiogram.event:Update id=976652239 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 19:51:14  INFO:aiogram.event:Update id=976652240 is handled. Duration 185 ms by bot id=8485867534
Jul 03 19:51:20  INFO:aiogram.event:Update id=976652241 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:51:28  INFO:aiogram.event:Update id=976652242 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 19:51:29  INFO:aiogram.event:Update id=976652243 is not handled. Duration 276 ms by bot id=8485867534
Jul 03 19:51:32  INFO:aiogram.event:Update id=976652244 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 19:51:33  INFO:aiogram.event:Update id=976652245 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:51:38  INFO:aiogram.event:Update id=976652246 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:51:40  INFO:aiogram.event:Update id=976652247 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 19:51:43  INFO:aiogram.event:Update id=976652248 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:51:45  INFO:aiogram.event:Update id=976652249 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:51:51  INFO:aiogram.event:Update id=976652250 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 19:51:54  2026-07-03 19:51:54.415 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 19:51:54  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 19:51:54  Args: ['W2026-27']
Jul 03 19:51:54  ERROR:    Exception in ASGI application
Jul 03 19:51:54  Traceback (most recent call last):
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 19:51:54      result = await app(  # type: ignore[func-returns-value]
Jul 03 19:51:54               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 19:51:54      return await self.app(scope, receive, send)
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 19:51:54      await self.app(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 19:51:54      await super().__call__(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 19:51:54      await self.middleware_stack(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 19:51:54      raise exc
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 19:51:54      await self.app(scope, receive, _send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 19:51:54      await self.app(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 19:51:54      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 19:51:54      raise exc
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 19:51:54      await app(scope, receive, sender)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 19:51:54      await self.middleware_stack(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 19:51:54      await route.handle(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 19:51:54      await self.app(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 19:51:54      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 19:51:54      raise exc
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 19:51:54      await app(scope, receive, sender)
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 19:51:54      response = await f(request)
Jul 03 19:51:54                 ^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 19:51:54      raw_response = await run_endpoint_function(
Jul 03 19:51:54                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 19:51:54      return await dependant.call(**values)
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 19:51:54      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 19:51:54              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 19:51:54      async with db.execute(
Jul 03 19:51:54    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 19:51:54      return await self._run()
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 19:51:54      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 19:51:54      return await self._execute(
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 19:51:54      result, _ = await self.__execute(
Jul 03 19:51:54                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 19:51:54      result, stmt = await self._do_execute(
Jul 03 19:51:54                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 19:51:54      stmt = await self._get_statement(
Jul 03 19:51:54             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 19:51:54      statement = await self._protocol.prepare(
Jul 03 19:51:54                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 19:51:54    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 19:51:54  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 19:52:05  INFO:aiogram.event:Update id=976652251 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:52:06  INFO:aiogram.event:Update id=976652252 is not handled. Duration 147 ms by bot id=8485867534
Jul 03 19:52:18  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:52:20  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:52:22  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:52:34  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:52:37  INFO:aiogram.event:Update id=976652253 is not handled. Duration 196 ms by bot id=8485867534
Jul 03 19:52:43  INFO:aiogram.event:Update id=976652254 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 19:52:46  INFO:aiogram.event:Update id=976652255 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 19:52:47  INFO:aiogram.event:Update id=976652256 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 19:52:55  INFO:aiogram.event:Update id=976652257 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 19:53:04  INFO:aiogram.event:Update id=976652258 is not handled. Duration 88 ms by bot id=8485867534
Jul 03 19:53:05  INFO:aiogram.event:Update id=976652259 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 19:53:07  INFO:aiogram.event:Update id=976652260 is not handled. Duration 188 ms by bot id=8485867534
Jul 03 19:53:09  INFO:aiogram.event:Update id=976652261 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:53:19  INFO:aiogram.event:Update id=976652262 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 19:53:21  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 19:53:23  INFO:aiogram.event:Update id=976652263 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 19:53:29  INFO:aiogram.event:Update id=976652264 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 19:53:43  INFO:aiogram.event:Update id=976652265 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 19:54:01  INFO:aiogram.event:Update id=976652266 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 19:54:11  INFO:aiogram.event:Update id=976652267 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 19:54:13  INFO:aiogram.event:Update id=976652268 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 19:54:17  INFO:aiogram.event:Update id=976652269 is not handled. Duration 152 ms by bot id=8485867534
Jul 03 19:54:17  INFO:aiogram.event:Update id=976652270 is not handled. Duration 102 ms by bot id=8485867534
Jul 03 19:54:21  INFO:aiogram.event:Update id=976652271 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 19:54:29  INFO:aiogram.event:Update id=976652272 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 19:55:39  INFO:aiogram.event:Update id=976652273 is not handled. Duration 192 ms by bot id=8485867534
Jul 03 19:56:23  INFO:aiogram.event:Update id=976652274 is not handled. Duration 101 ms by bot id=8485867534
Jul 03 19:56:26  INFO:aiogram.event:Update id=976652275 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 19:58:52  INFO:aiogram.event:Update id=976652276 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 19:59:17  INFO:aiogram.event:Update id=976652277 is handled. Duration 244 ms by bot id=8485867534
Jul 03 19:59:19  INFO:aiogram.event:Update id=976652278 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 19:59:22  INFO:aiogram.event:Update id=976652279 is handled. Duration 177 ms by bot id=8485867534
Jul 03 20:05:02  INFO:aiogram.event:Update id=976652280 is not handled. Duration 303 ms by bot id=8485867534
Jul 03 20:05:05  INFO:aiogram.event:Update id=976652281 is handled. Duration 295 ms by bot id=8485867534
Jul 03 20:09:21  INFO:aiogram.event:Update id=976652282 is not handled. Duration 244 ms by bot id=8485867534
Jul 03 20:09:38  INFO:aiogram.event:Update id=976652283 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 20:09:43  INFO:aiogram.event:Update id=976652284 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:09:46  INFO:aiogram.event:Update id=976652285 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 20:09:51  INFO:aiogram.event:Update id=976652286 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 20:09:59  INFO:aiogram.event:Update id=976652287 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:11:49  INFO:aiogram.event:Update id=976652288 is handled. Duration 193 ms by bot id=8485867534
Jul 03 20:15:03  INFO:aiogram.event:Update id=976652289 is not handled. Duration 199 ms by bot id=8485867534
Jul 03 20:15:10  INFO:aiogram.event:Update id=976652290 is handled. Duration 275 ms by bot id=8485867534
Jul 03 20:15:17  INFO:aiogram.event:Update id=976652291 is handled. Duration 265 ms by bot id=8485867534
Jul 03 20:15:23  INFO:aiogram.event:Update id=976652292 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 20:15:27  INFO:aiogram.event:Update id=976652293 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:15:34  INFO:aiogram.event:Update id=976652294 is handled. Duration 1391 ms by bot id=8485867534
Jul 03 20:16:20  2026-07-03 20:16:20.915 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 20:16:20  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 20:16:20  Args: ['W2026-27']
Jul 03 20:16:20  ERROR:    Exception in ASGI application
Jul 03 20:16:20  Traceback (most recent call last):
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 20:16:20      result = await app(  # type: ignore[func-returns-value]
Jul 03 20:16:20               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 20:16:20      return await self.app(scope, receive, send)
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 20:16:20      await self.app(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 20:16:20      await super().__call__(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 20:16:20      await self.middleware_stack(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 20:16:20      raise exc
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 20:16:20      await self.app(scope, receive, _send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 20:16:20      await self.app(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 20:16:20      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 20:16:20      raise exc
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 20:16:20      await app(scope, receive, sender)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 20:16:20      await self.middleware_stack(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 20:16:20      await route.handle(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 20:16:20      await self.app(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 20:16:20      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 20:16:20      raise exc
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 20:16:20      await app(scope, receive, sender)
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 20:16:20      response = await f(request)
Jul 03 20:16:20                 ^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 20:16:20      raw_response = await run_endpoint_function(
Jul 03 20:16:20                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 20:16:20      return await dependant.call(**values)
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 20:16:20      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 20:16:20              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 20:16:20      async with db.execute(
Jul 03 20:16:20    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 20:16:20      return await self._run()
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 20:16:20      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 20:16:20      return await self._execute(
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 20:16:20      result, _ = await self.__execute(
Jul 03 20:16:20                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 20:16:20      result, stmt = await self._do_execute(
Jul 03 20:16:20                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 20:16:20      stmt = await self._get_statement(
Jul 03 20:16:20             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 20:16:20      statement = await self._protocol.prepare(
Jul 03 20:16:20                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:16:20    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 20:16:20  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 20:16:49  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:16:54  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:00  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:07  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:14  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:18  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:21  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:30  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:33  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:17:41  2026-07-03 20:17:41.683 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 20:17:41  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 20:17:41  Args: ['W2026-27']
Jul 03 20:17:41  ERROR:    Exception in ASGI application
Jul 03 20:17:41  Traceback (most recent call last):
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 20:17:41      result = await app(  # type: ignore[func-returns-value]
Jul 03 20:17:41               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 20:17:41      return await self.app(scope, receive, send)
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 20:17:41      await self.app(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 20:17:41      await super().__call__(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 20:17:41      await self.middleware_stack(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 20:17:41      raise exc
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 20:17:41      await self.app(scope, receive, _send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 20:17:41      await self.app(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 20:17:41      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 20:17:41      raise exc
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 20:17:41      await app(scope, receive, sender)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 20:17:41      await self.middleware_stack(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 20:17:41      await route.handle(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 20:17:41      await self.app(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 20:17:41      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 20:17:41      raise exc
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 20:17:41      await app(scope, receive, sender)
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 20:17:41      response = await f(request)
Jul 03 20:17:41                 ^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 20:17:41      raw_response = await run_endpoint_function(
Jul 03 20:17:41                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 20:17:41      return await dependant.call(**values)
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 20:17:41      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 20:17:41              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 20:17:41      async with db.execute(
Jul 03 20:17:41    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 20:17:41      return await self._run()
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 20:17:41      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 20:17:41      return await self._execute(
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 20:17:41      result, _ = await self.__execute(
Jul 03 20:17:41                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 20:17:41      result, stmt = await self._do_execute(
Jul 03 20:17:41                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 20:17:41      stmt = await self._get_statement(
Jul 03 20:17:41             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 20:17:41      statement = await self._protocol.prepare(
Jul 03 20:17:41                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 20:17:41    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 20:17:41  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 20:18:04  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:18:07  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:18:23  INFO:aiogram.event:Update id=976652295 is handled. Duration 193 ms by bot id=8485867534
Jul 03 20:18:36  INFO:aiogram.event:Update id=976652296 is handled. Duration 259 ms by bot id=8485867534
Jul 03 20:18:37  INFO:aiogram.event:Update id=976652297 is handled. Duration 141 ms by bot id=8485867534
Jul 03 20:19:26  INFO:aiogram.event:Update id=976652298 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 20:20:25  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:27  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:31  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:33  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:35  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:37  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:38  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:40  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:42  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:20:44  INFO:httpx:HTTP Request: POST https://api.telegram.org/bot8485867534:AAEtHBH9uWrWSYWskoffSJUQkjqGxCTa_3M/sendMessage "HTTP/1.1 200 OK"
Jul 03 20:21:37  INFO:aiogram.event:Update id=976652299 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 20:29:16  INFO:aiogram.event:Update id=976652300 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 20:29:27  INFO:aiogram.event:Update id=976652301 is not handled. Duration 106 ms by bot id=8485867534
Jul 03 20:29:32  INFO:aiogram.event:Update id=976652302 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 20:29:44  INFO:aiogram.event:Update id=976652303 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:29:53  INFO:aiogram.event:Update id=976652304 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 20:29:59  INFO:aiogram.event:Update id=976652305 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:30:11  INFO:aiogram.event:Update id=976652306 is not handled. Duration 181 ms by bot id=8485867534
Jul 03 20:30:21  INFO:aiogram.event:Update id=976652307 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 20:30:27  INFO:aiogram.event:Update id=976652308 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 20:30:34  INFO:aiogram.event:Update id=976652309 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 20:30:40  INFO:aiogram.event:Update id=976652310 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 20:30:42  INFO:aiogram.event:Update id=976652311 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 20:30:49  INFO:aiogram.event:Update id=976652312 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 20:30:51  INFO:aiogram.event:Update id=976652313 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 20:30:53  INFO:aiogram.event:Update id=976652314 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 20:31:01  INFO:aiogram.event:Update id=976652315 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 20:31:02  INFO:aiogram.event:Update id=976652316 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 20:31:10  INFO:aiogram.event:Update id=976652317 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:31:18  INFO:aiogram.event:Update id=976652318 is not handled. Duration 124 ms by bot id=8485867534
Jul 03 20:31:21  INFO:aiogram.event:Update id=976652319 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 20:31:21  INFO:aiogram.event:Update id=976652320 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 20:31:25  INFO:aiogram.event:Update id=976652321 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:31:57  INFO:aiogram.event:Update id=976652322 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 20:32:04  INFO:aiogram.event:Update id=976652323 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:32:08  INFO:aiogram.event:Update id=976652324 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 20:32:18  INFO:aiogram.event:Update id=976652325 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 20:32:19  INFO:aiogram.event:Update id=976652326 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 20:32:20  INFO:aiogram.event:Update id=976652327 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 20:32:22  INFO:aiogram.event:Update id=976652328 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 20:32:25  INFO:aiogram.event:Update id=976652329 is not handled. Duration 172 ms by bot id=8485867534
Jul 03 20:32:38  INFO:aiogram.event:Update id=976652330 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 20:32:46  INFO:aiogram.event:Update id=976652331 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 20:32:49  INFO:aiogram.event:Update id=976652332 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 20:33:02  INFO:aiogram.event:Update id=976652333 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 20:33:13  INFO:aiogram.event:Update id=976652334 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 20:33:40  INFO:aiogram.event:Update id=976652335 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:33:45  INFO:aiogram.event:Update id=976652336 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 20:33:52  INFO:aiogram.event:Update id=976652337 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:34:04  INFO:aiogram.event:Update id=976652338 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 20:34:07  INFO:aiogram.event:Update id=976652339 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 20:34:40  INFO:aiogram.event:Update id=976652340 is not handled. Duration 149 ms by bot id=8485867534
Jul 03 20:34:44  INFO:aiogram.event:Update id=976652341 is not handled. Duration 161 ms by bot id=8485867534
Jul 03 20:34:53  INFO:aiogram.event:Update id=976652342 is not handled. Duration 142 ms by bot id=8485867534
Jul 03 20:35:01  INFO:aiogram.event:Update id=976652343 is not handled. Duration 273 ms by bot id=8485867534
Jul 03 20:35:03  INFO:aiogram.event:Update id=976652344 is not handled. Duration 198 ms by bot id=8485867534
Jul 03 20:36:06  INFO:aiogram.event:Update id=976652345 is not handled. Duration 211 ms by bot id=8485867534
Jul 03 20:36:10  INFO:aiogram.event:Update id=976652346 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:36:16  INFO:aiogram.event:Update id=976652347 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:36:21  INFO:aiogram.event:Update id=976652348 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:36:27  INFO:aiogram.event:Update id=976652349 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 20:36:40  INFO:aiogram.event:Update id=976652350 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:36:43  INFO:aiogram.event:Update id=976652351 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 20:36:43  INFO:aiogram.event:Update id=976652352 is not handled. Duration 133 ms by bot id=8485867534
Jul 03 20:36:50  INFO:aiogram.event:Update id=976652353 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 20:36:59  INFO:aiogram.event:Update id=976652354 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 20:41:20  INFO:aiogram.event:Update id=976652355 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 20:41:21  INFO:aiogram.event:Update id=976652356 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:42:18  INFO:aiogram.event:Update id=976652357 is not handled. Duration 151 ms by bot id=8485867534
Jul 03 20:42:33  INFO:aiogram.event:Update id=976652358 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 20:42:34  INFO:aiogram.event:Update id=976652359 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 20:42:58  INFO:aiogram.event:Update id=976652360 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 20:43:19  INFO:aiogram.event:Update id=976652361 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 20:43:53  INFO:aiogram.event:Update id=976652362 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:44:19  INFO:aiogram.event:Update id=976652363 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 20:44:20  INFO:aiogram.event:Update id=976652364 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 20:45:03  INFO:aiogram.event:Update id=976652365 is not handled. Duration 149 ms by bot id=8485867534
Jul 03 20:45:08  INFO:aiogram.event:Update id=976652366 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:45:09  INFO:aiogram.event:Update id=976652367 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 20:45:31  INFO:aiogram.event:Update id=976652368 is not handled. Duration 315 ms by bot id=8485867534
Jul 03 20:45:33  INFO:aiogram.event:Update id=976652369 is not handled. Duration 313 ms by bot id=8485867534
Jul 03 20:45:49  INFO:aiogram.event:Update id=976652370 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:45:53  INFO:aiogram.event:Update id=976652371 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 20:45:58  INFO:aiogram.event:Update id=976652372 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 20:46:14  INFO:aiogram.event:Update id=976652373 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 20:46:16  INFO:aiogram.event:Update id=976652374 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 20:46:19  INFO:aiogram.event:Update id=976652375 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 20:47:21  INFO:aiogram.event:Update id=976652376 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 20:47:24  INFO:aiogram.event:Update id=976652377 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 20:47:54  INFO:aiogram.event:Update id=976652378 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 20:47:55  INFO:aiogram.event:Update id=976652379 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 20:48:35  INFO:aiogram.event:Update id=976652380 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 20:48:36  INFO:aiogram.event:Update id=976652381 is not handled. Duration 171 ms by bot id=8485867534
Jul 03 20:49:10  INFO:aiogram.event:Update id=976652382 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 20:49:14  INFO:aiogram.event:Update id=976652383 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 20:49:22  INFO:aiogram.event:Update id=976652384 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 20:49:25  INFO:aiogram.event:Update id=976652385 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 20:49:27  INFO:aiogram.event:Update id=976652386 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 20:49:31  INFO:aiogram.event:Update id=976652387 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 20:49:36  INFO:aiogram.event:Update id=976652388 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 20:49:45  INFO:aiogram.event:Update id=976652389 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 20:49:55  INFO:aiogram.event:Update id=976652390 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 20:49:56  INFO:aiogram.event:Update id=976652391 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 20:49:58  INFO:aiogram.event:Update id=976652392 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 20:50:17  INFO:aiogram.event:Update id=976652393 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:50:22  INFO:aiogram.event:Update id=976652394 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:51:23  INFO:aiogram.event:Update id=976652395 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 20:52:57  INFO:aiogram.event:Update id=976652396 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 20:53:58  INFO:aiogram.event:Update id=976652397 is not handled. Duration 107 ms by bot id=8485867534
Jul 03 20:54:02  INFO:aiogram.event:Update id=976652398 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 20:54:16  INFO:aiogram.event:Update id=976652399 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 20:54:23  INFO:aiogram.event:Update id=976652400 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 20:54:36  INFO:aiogram.event:Update id=976652401 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 20:56:11  INFO:aiogram.event:Update id=976652402 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 20:57:33  INFO:aiogram.event:Update id=976652403 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 21:25:55  INFO:aiogram.event:Update id=976652404 is not handled. Duration 594 ms by bot id=8485867534
Jul 03 21:27:27  INFO:aiogram.event:Update id=976652405 is not handled. Duration 331 ms by bot id=8485867534
Jul 03 21:27:47  INFO:aiogram.event:Update id=976652406 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 21:28:02  INFO:aiogram.event:Update id=976652407 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 21:28:07  INFO:aiogram.event:Update id=976652408 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 21:29:24  INFO:aiogram.event:Update id=976652409 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 21:29:50  INFO:aiogram.event:Update id=976652410 is not handled. Duration 332 ms by bot id=8485867534
Jul 03 21:31:58  INFO:aiogram.event:Update id=976652411 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 21:32:09  INFO:aiogram.event:Update id=976652412 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 21:32:28  INFO:aiogram.event:Update id=976652413 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 21:32:28  INFO:aiogram.event:Update id=976652414 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 21:32:47  INFO:aiogram.event:Update id=976652415 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 21:32:54  INFO:aiogram.event:Update id=976652416 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 21:32:54  INFO:aiogram.event:Update id=976652417 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 21:33:06  INFO:aiogram.event:Update id=976652418 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 21:33:06  INFO:aiogram.event:Update id=976652419 is not handled. Duration 129 ms by bot id=8485867534
Jul 03 21:33:12  INFO:aiogram.event:Update id=976652420 is not handled. Duration 154 ms by bot id=8485867534
Jul 03 21:33:13  INFO:aiogram.event:Update id=976652421 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 21:33:22  INFO:aiogram.event:Update id=976652422 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 21:33:25  INFO:aiogram.event:Update id=976652423 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 21:33:30  INFO:aiogram.event:Update id=976652424 is not handled. Duration 198 ms by bot id=8485867534
Jul 03 21:33:41  INFO:aiogram.event:Update id=976652425 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 21:33:42  INFO:aiogram.event:Update id=976652426 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 21:34:04  INFO:aiogram.event:Update id=976652427 is not handled. Duration 307 ms by bot id=8485867534
Jul 03 21:34:09  INFO:aiogram.event:Update id=976652428 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 21:35:45  INFO:aiogram.event:Update id=976652429 is not handled. Duration 612 ms by bot id=8485867534
Jul 03 21:36:02  INFO:aiogram.event:Update id=976652430 is not handled. Duration 187 ms by bot id=8485867534
Jul 03 21:36:11  INFO:aiogram.event:Update id=976652431 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 21:36:13  INFO:aiogram.event:Update id=976652432 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 21:36:15  INFO:aiogram.event:Update id=976652433 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 21:36:24  INFO:aiogram.event:Update id=976652434 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 21:36:26  INFO:aiogram.event:Update id=976652435 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 21:36:31  INFO:aiogram.event:Update id=976652436 is not handled. Duration 297 ms by bot id=8485867534
Jul 03 21:36:37  INFO:aiogram.event:Update id=976652437 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 21:36:43  INFO:aiogram.event:Update id=976652438 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 21:36:46  INFO:aiogram.event:Update id=976652439 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 21:36:53  INFO:aiogram.event:Update id=976652440 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 21:36:54  INFO:aiogram.event:Update id=976652441 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 21:37:11  INFO:aiogram.event:Update id=976652442 is not handled. Duration 235 ms by bot id=8485867534
Jul 03 21:37:13  INFO:aiogram.event:Update id=976652443 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 21:37:22  INFO:aiogram.event:Update id=976652444 is handled. Duration 284 ms by bot id=8485867534
Jul 03 21:37:26  INFO:aiogram.event:Update id=976652445 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 21:37:30  INFO:aiogram.event:Update id=976652446 is not handled. Duration 431 ms by bot id=8485867534
Jul 03 21:37:39  INFO:aiogram.event:Update id=976652447 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 21:37:45  INFO:aiogram.event:Update id=976652448 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 21:37:45  INFO:aiogram.event:Update id=976652449 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 21:37:56  INFO:aiogram.event:Update id=976652450 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 21:38:02  INFO:aiogram.event:Update id=976652451 is not handled. Duration 185 ms by bot id=8485867534
Jul 03 21:38:20  INFO:aiogram.event:Update id=976652452 is handled. Duration 128 ms by bot id=8485867534
Jul 03 21:38:24  INFO:aiogram.event:Update id=976652453 is not handled. Duration 144 ms by bot id=8485867534
Jul 03 21:38:28  INFO:aiogram.event:Update id=976652454 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 21:38:32  INFO:aiogram.event:Update id=976652455 is handled. Duration 121 ms by bot id=8485867534
Jul 03 21:38:39  INFO:aiogram.event:Update id=976652456 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 21:38:39  INFO:aiogram.event:Update id=976652457 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 21:38:48  INFO:aiogram.event:Update id=976652458 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 21:38:51  INFO:aiogram.event:Update id=976652459 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 21:38:55  INFO:aiogram.event:Update id=976652460 is not handled. Duration 150 ms by bot id=8485867534
Jul 03 21:39:02  INFO:aiogram.event:Update id=976652461 is not handled. Duration 266 ms by bot id=8485867534
Jul 03 21:39:11  INFO:aiogram.event:Update id=976652462 is not handled. Duration 179 ms by bot id=8485867534
Jul 03 21:39:21  INFO:aiogram.event:Update id=976652463 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 21:39:27  INFO:aiogram.event:Update id=976652464 is not handled. Duration 155 ms by bot id=8485867534
Jul 03 21:39:31  INFO:aiogram.event:Update id=976652465 is not handled. Duration 209 ms by bot id=8485867534
Jul 03 21:39:38  INFO:aiogram.event:Update id=976652466 is handled. Duration 109 ms by bot id=8485867534
Jul 03 21:39:50  INFO:aiogram.event:Update id=976652467 is not handled. Duration 166 ms by bot id=8485867534
Jul 03 21:40:21  INFO:aiogram.event:Update id=976652468 is handled. Duration 117 ms by bot id=8485867534
Jul 03 21:40:22  INFO:aiogram.event:Update id=976652469 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 21:40:24  INFO:aiogram.event:Update id=976652470 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 21:40:34  INFO:aiogram.event:Update id=976652471 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 21:40:37  INFO:aiogram.event:Update id=976652472 is not handled. Duration 148 ms by bot id=8485867534
Jul 03 21:40:45  INFO:aiogram.event:Update id=976652473 is handled. Duration 108 ms by bot id=8485867534
Jul 03 21:40:52  INFO:aiogram.event:Update id=976652474 is not handled. Duration 176 ms by bot id=8485867534
Jul 03 21:40:58  INFO:aiogram.event:Update id=976652475 is handled. Duration 101 ms by bot id=8485867534
Jul 03 21:41:00  INFO:aiogram.event:Update id=976652476 is not handled. Duration 246 ms by bot id=8485867534
Jul 03 21:41:09  INFO:aiogram.event:Update id=976652477 is handled. Duration 78 ms by bot id=8485867534
Jul 03 21:41:15  INFO:aiogram.event:Update id=976652478 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 21:41:17  INFO:aiogram.event:Update id=976652479 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 21:41:21  INFO:aiogram.event:Update id=976652480 is handled. Duration 88 ms by bot id=8485867534
Jul 03 21:41:21  INFO:aiogram.event:Update id=976652481 is not handled. Duration 104 ms by bot id=8485867534
Jul 03 21:41:42  INFO:aiogram.event:Update id=976652482 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 21:42:03  INFO:aiogram.event:Update id=976652483 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 21:42:17  INFO:aiogram.event:Update id=976652484 is handled. Duration 94 ms by bot id=8485867534
Jul 03 21:42:27  INFO:aiogram.event:Update id=976652485 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 21:42:44  INFO:aiogram.event:Update id=976652486 is handled. Duration 120 ms by bot id=8485867534
Jul 03 21:42:55  INFO:aiogram.event:Update id=976652487 is handled. Duration 105 ms by bot id=8485867534
Jul 03 21:43:08  INFO:aiogram.event:Update id=976652488 is handled. Duration 111 ms by bot id=8485867534
Jul 03 21:43:57  INFO:aiogram.event:Update id=976652489 is handled. Duration 102 ms by bot id=8485867534
Jul 03 21:43:57  INFO:aiogram.event:Update id=976652490 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 21:44:06  INFO:aiogram.event:Update id=976652491 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 21:44:16  INFO:aiogram.event:Update id=976652492 is handled. Duration 91 ms by bot id=8485867534
Jul 03 21:44:24  INFO:aiogram.event:Update id=976652493 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 21:44:41  INFO:aiogram.event:Update id=976652494 is not handled. Duration 141 ms by bot id=8485867534
Jul 03 21:44:44  INFO:aiogram.event:Update id=976652495 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 21:45:02  INFO:aiogram.event:Update id=976652496 is handled. Duration 117 ms by bot id=8485867534
Jul 03 21:45:23  INFO:aiogram.event:Update id=976652497 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 21:45:39  INFO:aiogram.event:Update id=976652498 is handled. Duration 2056 ms by bot id=8485867534
Jul 03 21:45:40  INFO:aiogram.event:Update id=976652499 is not handled. Duration 2275 ms by bot id=8485867534
Jul 03 21:45:53  INFO:aiogram.event:Update id=976652500 is not handled. Duration 300 ms by bot id=8485867534
Jul 03 21:46:03  INFO:aiogram.event:Update id=976652501 is not handled. Duration 113 ms by bot id=8485867534
Jul 03 21:46:46  INFO:aiogram.event:Update id=976652502 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 21:47:09  INFO:aiogram.event:Update id=976652503 is handled. Duration 143 ms by bot id=8485867534
Jul 03 21:47:20  INFO:aiogram.event:Update id=976652504 is not handled. Duration 200 ms by bot id=8485867534
Jul 03 21:47:24  INFO:aiogram.event:Update id=976652505 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 21:47:42  INFO:aiogram.event:Update id=976652506 is not handled. Duration 318 ms by bot id=8485867534
Jul 03 21:47:44  INFO:aiogram.event:Update id=976652507 is handled. Duration 94 ms by bot id=8485867534
Jul 03 21:48:18  INFO:aiogram.event:Update id=976652508 is handled. Duration 108 ms by bot id=8485867534
Jul 03 21:48:38  INFO:aiogram.event:Update id=976652509 is handled. Duration 95 ms by bot id=8485867534
Jul 03 21:48:40  INFO:aiogram.event:Update id=976652510 is not handled. Duration 168 ms by bot id=8485867534
Jul 03 21:48:58  INFO:aiogram.event:Update id=976652511 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 21:49:31  INFO:aiogram.event:Update id=976652512 is handled. Duration 83 ms by bot id=8485867534
Jul 03 21:49:47  INFO:aiogram.event:Update id=976652513 is handled. Duration 106 ms by bot id=8485867534
Jul 03 21:49:54  INFO:aiogram.event:Update id=976652514 is not handled. Duration 97 ms by bot id=8485867534
Jul 03 21:50:16  INFO:aiogram.event:Update id=976652515 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 21:50:19  INFO:aiogram.event:Update id=976652516 is handled. Duration 101 ms by bot id=8485867534
Jul 03 21:50:25  INFO:aiogram.event:Update id=976652517 is handled. Duration 91 ms by bot id=8485867534
Jul 03 21:50:31  INFO:aiogram.event:Update id=976652518 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 21:50:40  INFO:aiogram.event:Update id=976652519 is not handled. Duration 165 ms by bot id=8485867534
Jul 03 21:51:10  INFO:aiogram.event:Update id=976652520 is handled. Duration 80 ms by bot id=8485867534
Jul 03 21:51:31  INFO:aiogram.event:Update id=976652521 is handled. Duration 83 ms by bot id=8485867534
Jul 03 21:51:52  INFO:aiogram.event:Update id=976652522 is not handled. Duration 110 ms by bot id=8485867534
Jul 03 21:51:53  INFO:aiogram.event:Update id=976652523 is handled. Duration 79 ms by bot id=8485867534
Jul 03 21:52:13  INFO:aiogram.event:Update id=976652524 is handled. Duration 161 ms by bot id=8485867534
Jul 03 21:52:39  INFO:aiogram.event:Update id=976652525 is not handled. Duration 162 ms by bot id=8485867534
Jul 03 21:53:07  INFO:aiogram.event:Update id=976652526 is handled. Duration 139 ms by bot id=8485867534
Jul 03 21:53:21  INFO:aiogram.event:Update id=976652527 is handled. Duration 100 ms by bot id=8485867534
Jul 03 21:53:46  INFO:aiogram.event:Update id=976652528 is handled. Duration 94 ms by bot id=8485867534
Jul 03 21:54:25  INFO:aiogram.event:Update id=976652529 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 21:54:27  INFO:aiogram.event:Update id=976652530 is not handled. Duration 95 ms by bot id=8485867534
Jul 03 21:54:45  INFO:aiogram.event:Update id=976652531 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 21:55:24  INFO:aiogram.event:Update id=976652532 is not handled. Duration 302 ms by bot id=8485867534
Jul 03 21:55:36  INFO:aiogram.event:Update id=976652533 is not handled. Duration 164 ms by bot id=8485867534
Jul 03 21:55:47  INFO:aiogram.event:Update id=976652534 is not handled. Duration 139 ms by bot id=8485867534
Jul 03 21:55:50  INFO:aiogram.event:Update id=976652535 is handled. Duration 177 ms by bot id=8485867534
Jul 03 21:56:03  INFO:aiogram.event:Update id=976652536 is not handled. Duration 197 ms by bot id=8485867534
Jul 03 21:56:11  INFO:aiogram.event:Update id=976652537 is handled. Duration 96 ms by bot id=8485867534
Jul 03 21:56:13  INFO:aiogram.event:Update id=976652538 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 21:56:26  INFO:aiogram.event:Update id=976652539 is handled. Duration 78 ms by bot id=8485867534
Jul 03 21:56:31  INFO:aiogram.event:Update id=976652540 is handled. Duration 96 ms by bot id=8485867534
Jul 03 21:57:09  INFO:aiogram.event:Update id=976652541 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 21:57:52  INFO:aiogram.event:Update id=976652542 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 21:58:05  INFO:aiogram.event:Update id=976652543 is handled. Duration 140 ms by bot id=8485867534
Jul 03 21:58:24  INFO:aiogram.event:Update id=976652544 is not handled. Duration 109 ms by bot id=8485867534
Jul 03 21:58:25  INFO:aiogram.event:Update id=976652545 is not handled. Duration 131 ms by bot id=8485867534
Jul 03 21:58:31  INFO:aiogram.event:Update id=976652546 is handled. Duration 86 ms by bot id=8485867534
Jul 03 21:58:38  INFO:aiogram.event:Update id=976652547 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 21:59:06  INFO:aiogram.event:Update id=976652548 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 21:59:08  INFO:aiogram.event:Update id=976652549 is handled. Duration 108 ms by bot id=8485867534
Jul 03 21:59:19  INFO:aiogram.event:Update id=976652550 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 21:59:28  INFO:aiogram.event:Update id=976652551 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 21:59:35  INFO:aiogram.event:Update id=976652552 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 21:59:42  INFO:aiogram.event:Update id=976652553 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 21:59:47  INFO:aiogram.event:Update id=976652554 is not handled. Duration 153 ms by bot id=8485867534
Jul 03 21:59:47  INFO:aiogram.event:Update id=976652555 is not handled. Duration 262 ms by bot id=8485867534
Jul 03 21:59:49  INFO:aiogram.event:Update id=976652556 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 21:59:51  INFO:aiogram.event:Update id=976652557 is handled. Duration 91 ms by bot id=8485867534
Jul 03 21:59:55  INFO:aiogram.event:Update id=976652558 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 21:59:55  INFO:aiogram.event:Update id=976652559 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 22:00:02  INFO:aiogram.event:Update id=976652560 is handled. Duration 306 ms by bot id=8485867534
Jul 03 22:00:08  INFO:aiogram.event:Update id=976652561 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 22:00:20  INFO:aiogram.event:Update id=976652562 is handled. Duration 99 ms by bot id=8485867534
Jul 03 22:00:28  INFO:aiogram.event:Update id=976652563 is handled. Duration 121 ms by bot id=8485867534
Jul 03 22:00:37  INFO:aiogram.event:Update id=976652564 is handled. Duration 180 ms by bot id=8485867534
Jul 03 22:00:53  INFO:aiogram.event:Update id=976652565 is not handled. Duration 163 ms by bot id=8485867534
Jul 03 22:00:53  INFO:aiogram.event:Update id=976652566 is not handled. Duration 128 ms by bot id=8485867534
Jul 03 22:01:03  INFO:aiogram.event:Update id=976652567 is not handled. Duration 279 ms by bot id=8485867534
Jul 03 22:01:11  INFO:aiogram.event:Update id=976652568 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 22:01:14  INFO:aiogram.event:Update id=976652569 is not handled. Duration 168 ms by bot id=8485867534
Jul 03 22:01:19  INFO:aiogram.event:Update id=976652570 is handled. Duration 112 ms by bot id=8485867534
Jul 03 22:01:38  INFO:aiogram.event:Update id=976652571 is not handled. Duration 112 ms by bot id=8485867534
Jul 03 22:01:47  INFO:aiogram.event:Update id=976652572 is handled. Duration 117 ms by bot id=8485867534
Jul 03 22:01:52  INFO:aiogram.event:Update id=976652573 is handled. Duration 100 ms by bot id=8485867534
Jul 03 22:01:59  INFO:aiogram.event:Update id=976652574 is handled. Duration 79 ms by bot id=8485867534
Jul 03 22:02:05  INFO:aiogram.event:Update id=976652575 is not handled. Duration 93 ms by bot id=8485867534
Jul 03 22:02:11  INFO:aiogram.event:Update id=976652576 is handled. Duration 122 ms by bot id=8485867534
Jul 03 22:02:15  INFO:aiogram.event:Update id=976652577 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 22:02:20  INFO:aiogram.event:Update id=976652578 is handled. Duration 106 ms by bot id=8485867534
Jul 03 22:02:23  INFO:aiogram.event:Update id=976652579 is handled. Duration 96 ms by bot id=8485867534
Jul 03 22:02:26  INFO:aiogram.event:Update id=976652580 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 22:02:47  INFO:aiogram.event:Update id=976652581 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:02:50  INFO:aiogram.event:Update id=976652582 is not handled. Duration 123 ms by bot id=8485867534
Jul 03 22:02:52  INFO:aiogram.event:Update id=976652583 is handled. Duration 87 ms by bot id=8485867534
Jul 03 22:03:07  INFO:aiogram.event:Update id=976652584 is handled. Duration 104 ms by bot id=8485867534
Jul 03 22:03:15  INFO:aiogram.event:Update id=976652585 is handled. Duration 87 ms by bot id=8485867534
Jul 03 22:03:19  INFO:aiogram.event:Update id=976652586 is not handled. Duration 127 ms by bot id=8485867534
Jul 03 22:03:24  INFO:aiogram.event:Update id=976652587 is not handled. Duration 119 ms by bot id=8485867534
Jul 03 22:03:37  INFO:aiogram.event:Update id=976652588 is handled. Duration 105 ms by bot id=8485867534
Jul 03 22:03:45  INFO:aiogram.event:Update id=976652589 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 22:03:55  INFO:aiogram.event:Update id=976652590 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 22:04:15  INFO:aiogram.event:Update id=976652591 is handled. Duration 99 ms by bot id=8485867534
Jul 03 22:04:21  INFO:aiogram.event:Update id=976652592 is handled. Duration 106 ms by bot id=8485867534
Jul 03 22:04:40  INFO:aiogram.event:Update id=976652593 is handled. Duration 97 ms by bot id=8485867534
Jul 03 22:04:47  INFO:aiogram.event:Update id=976652594 is handled. Duration 103 ms by bot id=8485867534
Jul 03 22:05:13  INFO:aiogram.event:Update id=976652595 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 22:05:17  INFO:aiogram.event:Update id=976652596 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:05:38  INFO:aiogram.event:Update id=976652597 is handled. Duration 1827 ms by bot id=8485867534
Jul 03 22:05:39  INFO:aiogram.event:Update id=976652598 is not handled. Duration 1902 ms by bot id=8485867534
Jul 03 22:05:42  INFO:aiogram.event:Update id=976652599 is not handled. Duration 322 ms by bot id=8485867534
Jul 03 22:05:52  INFO:aiogram.event:Update id=976652600 is handled. Duration 113 ms by bot id=8485867534
Jul 03 22:06:00  INFO:aiogram.event:Update id=976652601 is not handled. Duration 304 ms by bot id=8485867534
Jul 03 22:06:01  INFO:aiogram.event:Update id=976652602 is not handled. Duration 567 ms by bot id=8485867534
Jul 03 22:06:18  INFO:aiogram.event:Update id=976652603 is not handled. Duration 458 ms by bot id=8485867534
Jul 03 22:06:25  INFO:aiogram.event:Update id=976652604 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 22:06:31  INFO:aiogram.event:Update id=976652605 is handled. Duration 126 ms by bot id=8485867534
Jul 03 22:06:31  INFO:aiogram.event:Update id=976652606 is not handled. Duration 185 ms by bot id=8485867534
Jul 03 22:06:37  INFO:aiogram.event:Update id=976652607 is not handled. Duration 202 ms by bot id=8485867534
Jul 03 22:06:39  INFO:aiogram.event:Update id=976652608 is not handled. Duration 145 ms by bot id=8485867534
Jul 03 22:06:42  INFO:aiogram.event:Update id=976652609 is not handled. Duration 177 ms by bot id=8485867534
Jul 03 22:06:44  INFO:aiogram.event:Update id=976652610 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 22:06:45  INFO:aiogram.event:Update id=976652611 is handled. Duration 114 ms by bot id=8485867534
Jul 03 22:06:46  INFO:aiogram.event:Update id=976652612 is not handled. Duration 114 ms by bot id=8485867534
Jul 03 22:07:01  INFO:aiogram.event:Update id=976652613 is not handled. Duration 440 ms by bot id=8485867534
Jul 03 22:07:04  INFO:aiogram.event:Update id=976652614 is not handled. Duration 644 ms by bot id=8485867534
Jul 03 22:07:07  INFO:aiogram.event:Update id=976652615 is not handled. Duration 206 ms by bot id=8485867534
Jul 03 22:07:09  INFO:aiogram.event:Update id=976652616 is handled. Duration 99 ms by bot id=8485867534
Jul 03 22:07:11  INFO:aiogram.event:Update id=976652617 is not handled. Duration 194 ms by bot id=8485867534
Jul 03 22:07:13  INFO:aiogram.event:Update id=976652618 is handled. Duration 117 ms by bot id=8485867534
Jul 03 22:07:17  INFO:aiogram.event:Update id=976652619 is handled. Duration 224 ms by bot id=8485867534
Jul 03 22:07:39  INFO:aiogram.event:Update id=976652620 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:07:40  INFO:aiogram.event:Update id=976652621 is not handled. Duration 310 ms by bot id=8485867534
Jul 03 22:07:42  INFO:aiogram.event:Update id=976652622 is handled. Duration 583 ms by bot id=8485867534
Jul 03 22:07:43  INFO:aiogram.event:Update id=976652623 is handled. Duration 1407 ms by bot id=8485867534
Jul 03 22:07:44  INFO:aiogram.event:Update id=976652626 is handled. Duration 2575 ms by bot id=8485867534
Jul 03 22:07:44  INFO:aiogram.event:Update id=976652624 is handled. Duration 2588 ms by bot id=8485867534
Jul 03 22:07:44  INFO:aiogram.event:Update id=976652625 is handled. Duration 2590 ms by bot id=8485867534
Jul 03 22:08:10  INFO:aiogram.event:Update id=976652627 is not handled. Duration 146 ms by bot id=8485867534
Jul 03 22:08:13  INFO:aiogram.event:Update id=976652628 is not handled. Duration 117 ms by bot id=8485867534
Jul 03 22:08:57  INFO:aiogram.event:Update id=976652629 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:08:59  INFO:aiogram.event:Update id=976652630 is handled. Duration 113 ms by bot id=8485867534
Jul 03 22:09:14  INFO:aiogram.event:Update id=976652631 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 22:09:22  INFO:aiogram.event:Update id=976652632 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:09:24  INFO:aiogram.event:Update id=976652633 is not handled. Duration 105 ms by bot id=8485867534
Jul 03 22:09:28  INFO:aiogram.event:Update id=976652634 is not handled. Duration 138 ms by bot id=8485867534
Jul 03 22:09:33  INFO:aiogram.event:Update id=976652635 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:09:57  INFO:aiogram.event:Update id=976652636 is not handled. Duration 101 ms by bot id=8485867534
Jul 03 22:09:59  INFO:aiogram.event:Update id=976652637 is handled. Duration 76 ms by bot id=8485867534
Jul 03 22:10:07  INFO:aiogram.event:Update id=976652638 is handled. Duration 99 ms by bot id=8485867534
Jul 03 22:10:32  INFO:aiogram.event:Update id=976652639 is handled. Duration 105 ms by bot id=8485867534
Jul 03 22:10:48  INFO:aiogram.event:Update id=976652640 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 22:11:01  INFO:aiogram.event:Update id=976652641 is handled. Duration 139 ms by bot id=8485867534
Jul 03 22:11:11  INFO:aiogram.event:Update id=976652642 is not handled. Duration 190 ms by bot id=8485867534
Jul 03 22:11:11  INFO:aiogram.event:Update id=976652643 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 22:11:14  INFO:aiogram.event:Update id=976652644 is not handled. Duration 108 ms by bot id=8485867534
Jul 03 22:12:18  INFO:aiogram.event:Update id=976652645 is not handled. Duration 226 ms by bot id=8485867534
Jul 03 22:12:28  INFO:aiogram.event:Update id=976652646 is not handled. Duration 137 ms by bot id=8485867534
Jul 03 22:12:43  INFO:aiogram.event:Update id=976652647 is handled. Duration 1458 ms by bot id=8485867534
Jul 03 22:12:45  INFO:aiogram.event:Update id=976652648 is handled. Duration 239 ms by bot id=8485867534
Jul 03 22:12:47  INFO:aiogram.event:Update id=976652649 is not handled. Duration 136 ms by bot id=8485867534
Jul 03 22:12:50  INFO:aiogram.event:Update id=976652650 is handled. Duration 186 ms by bot id=8485867534
Jul 03 22:13:04  INFO:aiogram.event:Update id=976652651 is handled. Duration 131 ms by bot id=8485867534
Jul 03 22:13:04  INFO:aiogram.event:Update id=976652652 is not handled. Duration 183 ms by bot id=8485867534
Jul 03 22:13:11  INFO:aiogram.event:Update id=976652653 is not handled. Duration 143 ms by bot id=8485867534
Jul 03 22:13:12  INFO:aiogram.event:Update id=976652654 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 22:13:33  INFO:aiogram.event:Update id=976652655 is handled. Duration 86 ms by bot id=8485867534
Jul 03 22:13:53  2026-07-03 22:13:53.787 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "minigame_sessions" does not exist
Jul 03 22:13:53  SQL: SELECT * FROM minigame_sessions WHERE user_id = $1 AND game = $2 AND status = 'active' ORDER BY id DESC LIMIT 1
Jul 03 22:13:53  Args: [1460945748, 'sapper']
Jul 03 22:13:53  ERROR:    Exception in ASGI application
Jul 03 22:13:53  Traceback (most recent call last):
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 22:13:53      result = await app(  # type: ignore[func-returns-value]
Jul 03 22:13:53               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 22:13:53      return await self.app(scope, receive, send)
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 22:13:53      await self.app(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 22:13:53      await super().__call__(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 22:13:53      await self.middleware_stack(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 22:13:53      raise exc
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 22:13:53      await self.app(scope, receive, _send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 22:13:53      await self.app(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 22:13:53      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 22:13:53      raise exc
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 22:13:53      await app(scope, receive, sender)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 22:13:53      await self.middleware_stack(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 22:13:53      await route.handle(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 22:13:53      await self.app(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 22:13:53      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 22:13:53      raise exc
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 22:13:53      await app(scope, receive, sender)
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 22:13:53      response = await f(request)
Jul 03 22:13:53                 ^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 22:13:53      raw_response = await run_endpoint_function(
Jul 03 22:13:53                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 22:13:53      return await dependant.call(**values)
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/predvestnik_v2/FastAPI/routers/skill_games.py", line 35, in skill_state
Jul 03 22:13:53      sapper = await mg_repo.get_active(db, uid, "sapper")
Jul 03 22:13:53               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/predvestnik_v2/infrastructure/repositories/minigames.py", line 30, in get_active
Jul 03 22:13:53      async with db.execute(
Jul 03 22:13:53    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 22:13:53      return await self._run()
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 22:13:53      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 22:13:53      return await self._execute(
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 22:13:53      result, _ = await self.__execute(
Jul 03 22:13:53                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 22:13:53      result, stmt = await self._do_execute(
Jul 03 22:13:53                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 22:13:53      stmt = await self._get_statement(
Jul 03 22:13:53             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 22:13:53      statement = await self._protocol.prepare(
Jul 03 22:13:53                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:13:53    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 22:13:53  asyncpg.exceptions.UndefinedTableError: relation "minigame_sessions" does not exist
Jul 03 22:14:08  INFO:aiogram.event:Update id=976652656 is not handled. Duration 140 ms by bot id=8485867534
Jul 03 22:14:09  INFO:aiogram.event:Update id=976652657 is not handled. Duration 121 ms by bot id=8485867534
Jul 03 22:14:14  INFO:aiogram.event:Update id=976652658 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 22:14:24  2026-07-03 22:14:24.771 | ERROR    | infrastructure.pg_adapter:_run:228 - PG error: relation "weekly_showcase" does not exist
Jul 03 22:14:24  SQL: SELECT slots_json FROM weekly_showcase WHERE week_key = $1
Jul 03 22:14:24  Args: ['W2026-27']
Jul 03 22:14:24  ERROR:    Exception in ASGI application
Jul 03 22:14:24  Traceback (most recent call last):
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
Jul 03 22:14:24      result = await app(  # type: ignore[func-returns-value]
Jul 03 22:14:24               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
Jul 03 22:14:24      return await self.app(scope, receive, send)
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/predvestnik_v2/FastAPI/prefix.py", line 20, in __call__
Jul 03 22:14:24      await self.app(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
Jul 03 22:14:24      await super().__call__(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/applications.py", line 112, in __call__
Jul 03 22:14:24      await self.middleware_stack(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
Jul 03 22:14:24      raise exc
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
Jul 03 22:14:24      await self.app(scope, receive, _send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/cors.py", line 85, in __call__
Jul 03 22:14:24      await self.app(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
Jul 03 22:14:24      await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 22:14:24      raise exc
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 22:14:24      await app(scope, receive, sender)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 714, in __call__
Jul 03 22:14:24      await self.middleware_stack(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 734, in app
Jul 03 22:14:24      await route.handle(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
Jul 03 22:14:24      await self.app(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
Jul 03 22:14:24      await wrap_app_handling_exceptions(app, request)(scope, receive, send)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
Jul 03 22:14:24      raise exc
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
Jul 03 22:14:24      await app(scope, receive, sender)
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
Jul 03 22:14:24      response = await f(request)
Jul 03 22:14:24                 ^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
Jul 03 22:14:24      raw_response = await run_endpoint_function(
Jul 03 22:14:24                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/fastapi/routing.py", line 212, in run_endpoint_function
Jul 03 22:14:24      return await dependant.call(**values)
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/predvestnik_v2/FastAPI/routers/showcase.py", line 44, in get_showcase
Jul 03 22:14:24      slots = await sc_repo.get_week_slots(db, wk)
Jul 03 22:14:24              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/predvestnik_v2/infrastructure/repositories/showcase.py", line 72, in get_week_slots
Jul 03 22:14:24      async with db.execute(
Jul 03 22:14:24    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 237, in __aenter__
Jul 03 22:14:24      return await self._run()
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/predvestnik_v2/infrastructure/pg_adapter.py", line 222, in _run
Jul 03 22:14:24      rows = await self._conn.fetch(pg_sql, *args)
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 690, in fetch
Jul 03 22:14:24      return await self._execute(
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1864, in _execute
Jul 03 22:14:24      result, _ = await self.__execute(
Jul 03 22:14:24                  ^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 1961, in __execute
Jul 03 22:14:24      result, stmt = await self._do_execute(
Jul 03 22:14:24                     ^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 2004, in _do_execute
Jul 03 22:14:24      stmt = await self._get_statement(
Jul 03 22:14:24             ^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "/workspace/.heroku/python/lib/python3.11/site-packages/asyncpg/connection.py", line 432, in _get_statement
Jul 03 22:14:24      statement = await self._protocol.prepare(
Jul 03 22:14:24                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Jul 03 22:14:24    File "asyncpg/protocol/protocol.pyx", line 165, in prepare
Jul 03 22:14:24  asyncpg.exceptions.UndefinedTableError: relation "weekly_showcase" does not exist
Jul 03 22:14:53  INFO:aiogram.event:Update id=976652659 is handled. Duration 106 ms by bot id=8485867534
Jul 03 22:15:08  INFO:aiogram.event:Update id=976652660 is handled. Duration 90 ms by bot id=8485867534
Jul 03 22:15:18  INFO:aiogram.event:Update id=976652661 is not handled. Duration 125 ms by bot id=8485867534
Jul 03 22:15:24  INFO:aiogram.event:Update id=976652662 is handled. Duration 95 ms by bot id=8485867534
Jul 03 22:15:28  INFO:aiogram.event:Update id=976652663 is not handled. Duration 182 ms by bot id=8485867534
Jul 03 22:15:36  INFO:aiogram.event:Update id=976652664 is not handled. Duration 476 ms by bot id=8485867534
Jul 03 22:15:39  INFO:aiogram.event:Update id=976652665 is not handled. Duration 171 ms by bot id=8485867534
Jul 03 22:15:43  INFO:aiogram.event:Update id=976652666 is not handled. Duration 130 ms by bot id=8485867534
Jul 03 22:15:51  INFO:aiogram.event:Update id=976652667 is not handled. Duration 132 ms by bot id=8485867534
Jul 03 22:16:09  INFO:aiogram.event:Update id=976652668 is not handled. Duration 147 ms by bot id=8485867534
Jul 03 22:16:11  INFO:aiogram.event:Update id=976652669 is not handled. Duration 134 ms by bot id=8485867534
Jul 03 22:16:31  INFO:aiogram.event:Update id=976652670 is handled. Duration 465 ms by bot id=8485867534
Jul 03 22:16:37  INFO:aiogram.event:Update id=976652671 is not handled. Duration 135 ms by bot id=8485867534
Jul 03 22:16:45  INFO:aiogram.event:Update id=976652672 is not handled. Duration 120 ms by bot id=8485867534
Jul 03 22:16:56  INFO:aiogram.event:Update id=976652673 is handled. Duration 109 ms by bot id=8485867534
Jul 03 22:17:22  INFO:aiogram.event:Update id=976652674 is not handled. Duration 115 ms by bot id=8485867534
Jul 03 22:17:25  INFO:aiogram.event:Update id=976652675 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 22:17:31  INFO:aiogram.event:Update id=976652676 is not handled. Duration 241 ms by bot id=8485867534
Jul 03 22:17:40  INFO:aiogram.event:Update id=976652677 is not handled. Duration 116 ms by bot id=8485867534
Jul 03 22:17:42  INFO:aiogram.event:Update id=976652678 is handled. Duration 96 ms by bot id=8485867534
Jul 03 22:17:49  INFO:aiogram.event:Update id=976652679 is handled. Duration 84 ms by bot id=8485867534
Jul 03 22:17:52  INFO:aiogram.event:Update id=976652680 is handled. Duration 93 ms by bot id=8485867534
Jul 03 22:17:58  INFO:aiogram.event:Update id=976652681 is not handled. Duration 118 ms by bot id=8485867534
Jul 03 22:18:00  INFO:aiogram.event:Update id=976652682 is not handled. Duration 501 ms by bot id=8485867534
Jul 03 22:18:18  INFO:aiogram.event:Update id=976652683 is not handled. Duration 126 ms by bot id=8485867534
Jul 03 22:18:22  INFO:aiogram.event:Update id=976652684 is handled. Duration 93 ms by bot id=8485867534
Jul 03 22:18:23  INFO:aiogram.event:Update id=976652685 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 22:18:29  INFO:aiogram.event:Update id=976652686 is not handled. Duration 122 ms by bot id=8485867534
Jul 03 22:19:14  INFO:aiogram.event:Update id=976652687 is handled. Duration 79 ms by bot id=8485867534
Jul 03 22:19:25  INFO:aiogram.event:Update id=976652688 is handled. Duration 99 ms by bot id=8485867534