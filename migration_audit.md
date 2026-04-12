# Аудит миграции на новый стек (React Mini App)
> Дата: 12 апреля 2026  
> Новый стек: React 19 + Vite 6 + TailwindCSS v4 → `PredvestnikBot/web/`  
> Бэкенд API: Django/Daphne (порт 8080) — `IESA_ROOT/miniapp_views.py` (118 endpoint-функций)

---

## 1. ЧТО УЖЕ РЕАЛИЗОВАНО В MINI APP

| Страница       | Файл                    | Что отображает                                                                                               | Интерактивность |
|----------------|-------------------------|--------------------------------------------------------------------------------------------------------------|-----------------|
| **Профиль**    | `Profile.tsx`           | Имя, уровень, XP-прогресс, баланс, кристаллы, ранг, кастом-титул, биография, chat_role, RPG-стат, питомец (статус прогулки), партнёр, семейный кошелёк, crystal-предметы (transfer_passes, камни, свитки), облигации, pity, warn, message_count, streak | ❌ только чтение |
| **Инвентарь**  | `Inventory.tsx`         | Список предметов из `user_data.items[]` (строки вида `"Название (rarity)"`, подсветка rariry, значок ★ для equipped) | ❌ только чтение |
| **Достижения** | `Achievements.tsx`      | Категории, прогресс по рангам, unlocked/locked, дата получения; при chatId=0 — информационный экран           | ❌ только чтение |

**API-функции объявлены в `api.ts`, но не используются ни одной страницей:**
- `fetchBadges()` → `/api/achievements/badges`
- `fetchSeasonData()` → `/api/season/data`

---

## 2. BACKEND ENDPOINTS БЕЗ FRONTEND-СТРАНИЦЫ

Всего в `miniapp_views.py` **118 функций**. Из них подключены к фронту: **3** (user_data, achievements, + частично season_data).

### 2.1 Экономика и кошелёк

| Endpoint                          | URL                          | Описание                                        | Приоритет |
|-----------------------------------|------------------------------|-------------------------------------------------|-----------|
| `miniapp_wallet_history`          | `GET /api/wallet/history`    | История транзакций кошелька                     | 🔴 высокий |
| `miniapp_transfer`                | `POST /api/transfer`         | Перевод моры другому пользователю               | 🔴 высокий |
| `miniapp_crystals_transfer`       | `POST /api/crystals/transfer`| Перевод кристаллов                              | 🔴 высокий |
| `miniapp_convert_crystals`        | `POST /api/convert_crystals` | Конвертация кристаллов → мора                   | 🟡 средний |
| `miniapp_use_transfer_pass`       | `POST /api/use_transfer_pass`| Использование Transfer Pass (особый предмет)     | 🟡 средний |

### 2.2 Банк

| Endpoint                 | URL                    | Описание                        | Приоритет |
|--------------------------|------------------------|---------------------------------|-----------|
| `miniapp_bank`           | `GET /api/bank`        | Баланс банковского вклада, %     | 🔴 высокий |
| `miniapp_bank_deposit`   | `POST /api/bank/deposit`   | Положить мору в банк        | 🔴 высокий |
| `miniapp_bank_withdraw`  | `POST /api/bank/withdraw`  | Забрать из банка            | 🔴 высокий |

### 2.3 Заёмная система (Loans)

| Endpoint               | URL                    | Описание                        | Приоритет |
|------------------------|------------------------|---------------------------------|-----------|
| `miniapp_loans`        | `GET /api/loans`       | Список долгов (дал/взял)        | 🟡 средний |
| `miniapp_loans_create` | `POST /api/loans/create`   | Создать займ            | 🟡 средний |
| `miniapp_loans_repay`  | `POST /api/loans/repay`    | Вернуть долг            | 🟡 средний |
| `miniapp_loans_respond`| `POST /api/loans/respond`  | Принять/отклонить займ  | 🟡 средний |
| `miniapp_loans_cancel` | `POST /api/loans/cancel`   | Отменить займ           | 🟡 средний |

### 2.4 Облигации и Инвестиции

| Endpoint               | URL                    | Описание                             | Приоритет |
|------------------------|------------------------|--------------------------------------|-----------|
| `miniapp_bonds`        | `GET /api/bonds`       | Список облигаций и их котировки       | 🔴 высокий |
| `miniapp_bonds_buy`    | `POST /api/bonds/buy`  | Купить облигацию                      | 🔴 высокий |
| `miniapp_bonds_sell`   | `POST /api/bonds/sell` | Продать облигацию                     | 🔴 высокий |

> ⚠️ Облигации показываются в Profile как read-only список, но купить/продать нельзя.

### 2.5 Семейный кошелёк (Family)

| Endpoint                   | URL                        | Описание                        | Приоритет |
|----------------------------|----------------------------|---------------------------------|-----------|
| `miniapp_family_deposit`   | `POST /api/family/deposit` | Пополнить семейный кошелёк      | 🔴 высокий |
| `miniapp_family_withdraw`  | `POST /api/family/withdraw`| Снять из семейного кошелька      | 🔴 высокий |
| `miniapp_family_log`       | `GET /api/family/log`      | История операций семейного кош.  | 🟡 средний |

> ⚠️ Балансы партнёра и семьи отображаются в Profile (только чтение).

### 2.6 Казначейство (Treasury)

| Endpoint                  | URL                          | Описание                       | Приоритет |
|---------------------------|------------------------------|--------------------------------|-----------|
| `miniapp_treasury`        | `GET /api/treasury`          | Состояние казны чата            | 🟢 низкий  |
| `miniapp_treasury_payout` | `POST /api/treasury/payout`  | Выплата из казны (admin)        | 🟢 низкий  |

---

### 2.7 Инвентарь — действия

| Endpoint                     | URL                              | Описание                             | Приоритет |
|------------------------------|----------------------------------|--------------------------------------|-----------|
| `miniapp_inventory`          | `GET /api/inventory`             | Полный инвентарь (обогащённые данные) | 🔴 высокий |
| `miniapp_inventory_sell_junk`| `POST /api/inventory/sell_junk`  | Продать хлам (common-предметы)        | 🔴 высокий |
| `miniapp_equip`              | `POST /api/equip`                | Экипировать предмет                   | 🔴 высокий |
| `miniapp_enhance_item`       | `POST /api/enhance_item`         | Улучшить предмет (Enhancement Stone)  | 🟡 средний |
| `miniapp_consume_potion`     | `POST /api/consume_potion`       | Использовать зелье                    | 🟡 средний |
| `miniapp_batch_sell`         | `POST /api/batch_sell`           | Продать несколько предметов           | 🟡 средний |

> ⚠️ Инвентарь сейчас берёт `user_data.items[]` — упрощённые строки. Полный `/api/inventory` возвращает объекты с rariry, level, equipped, effect и прочим.

---

### 2.8 Гача

| Endpoint             | URL                  | Описание                                           | Приоритет |
|----------------------|----------------------|----------------------------------------------------|-----------|
| `miniapp_gacha_roll` | `POST /api/gacha/roll`| Гача-крутка (1× / 10×), pity-система, анимация    | 🔴 высокий |

---

### 2.9 Магазин (Shop)

| Endpoint                  | URL                       | Описание                        | Приоритет |
|---------------------------|---------------------------|---------------------------------|-----------|
| `miniapp_shop_catalog`    | `GET /api/shop/catalog`   | Каталог предметов в магазине     | 🔴 высокий |
| `miniapp_shop_buy`        | `POST /api/shop/buy`      | Купить предмет                   | 🔴 высокий |
| `miniapp_shop_set_title`  | `POST /api/shop/set_title`| Установить купленный титул        | 🟡 средний |

---

### 2.10 Питомцы — действия

| Endpoint              | URL                  | Описание                            | Приоритет |
|-----------------------|----------------------|-------------------------------------|-----------|
| `miniapp_pet_walk`    | `POST /api/pet/walk` | Отправить питомца на прогулку        | 🔴 высокий |
| `miniapp_pet_feed`    | `POST /api/pet/feed` | Покормить питомца (восстановить HP)  | 🔴 высокий |
| `miniapp_pets_rename` | `POST /api/pets/rename`| Переименовать питомца              | 🟡 средний |

> ⚠️ Состояние питомца (fatigue, on_walk, walk_mins_left) отображается в Profile, но кнопок нет.

---

### 2.11 Экспедиции

| Endpoint                      | URL                            | Описание                     | Приоритет |
|-------------------------------|--------------------------------|------------------------------|-----------|
| `miniapp_expeditions`         | `GET /api/expeditions`         | Статус/список экспедиций      | 🟡 средний |
| `miniapp_expeditions_start`   | `POST /api/expeditions/start`  | Начать экспедицию             | 🟡 средний |
| `miniapp_expeditions_collect` | `POST /api/expeditions/collect`| Собрать награду               | 🟡 средний |
| `miniapp_expeditions_boost`   | `POST /api/expeditions/boost`  | Ускорить экспедицию           | 🟡 средний |

---

### 2.12 Боссы

| Endpoint                       | URL                              | Описание                         | Приоритет |
|--------------------------------|----------------------------------|----------------------------------|-----------|
| `miniapp_boss_damage`          | `POST /api/boss/submit_damage`   | Атака группового босса            | 🟡 средний |
| `miniapp_solo_boss_status`     | `GET /api/solo_boss/status`      | Статус соло-босса                 | 🟡 средний |
| `miniapp_solo_boss_start`      | `POST /api/solo_boss/start`      | Начать бой с соло-боссом          | 🟡 средний |
| `miniapp_solo_boss_attack`     | `POST /api/solo_boss/attack`     | Атаковать соло-босса              | 🟡 средний |
| `miniapp_couple_boss_status`   | `GET /api/couple_boss/status`    | Статус совместного босса (с парой)| 🟢 низкий  |
| `miniapp_couple_boss_start`    | `POST /api/couple_boss/start`    | Начать бой пары с боссом          | 🟢 низкий  |
| `miniapp_couple_boss_attack`   | `POST /api/couple_boss/attack`   | Атаковать с парой                 | 🟢 низкий  |

---

### 2.13 Казино

| Endpoint                  | URL                       | Описание                      | Приоритет |
|---------------------------|---------------------------|-------------------------------|-----------|
| `miniapp_casino_coin`     | `POST /api/casino/coin`   | Орёл/решка на мору             | 🔴 высокий |
| `miniapp_casino_roulette` | `POST /api/casino/roulette`| Рулетка                       | 🔴 высокий |
| `miniapp_casino_lottery`  | `POST /api/casino/lottery` | Лотерея                       | 🟡 средний |

---

### 2.14 Ежедневный check-in

| Endpoint           | URL               | Описание                          | Приоритет |
|--------------------|-------------------|-----------------------------------|-----------|
| `miniapp_checkin`  | `POST /api/checkin`| Daily check-in, стрик + награда   | 🔴 высокий |

> ⚠️ Стрик (`streak`) отображается в Profile, но сделать check-in нельзя.

---

### 2.15 Брак / Партнёрство

| Endpoint                         | URL                          | Описание                      | Приоритет |
|----------------------------------|------------------------------|-------------------------------|-----------|
| `miniapp_marriage`               | `GET /api/marriage`           | Детали брака                  | 🟡 средний |
| `miniapp_marriage_propose`       | `POST /api/marriage/propose`  | Сделать предложение           | 🟡 средний |
| `miniapp_marriage_proposals_list`| `GET /api/marriage/proposals` | Входящие предложения          | 🟡 средний |
| `miniapp_marriage_respond`       | `POST /api/marriage/respond`  | Принять/отклонить предложение | 🟡 средний |

> ⚠️ Партнёр показан в Profile (только чтение). Нельзя подать на развод или принять предложение.

---

### 2.16 Аукцион

| Endpoint                  | URL                       | Описание                      | Приоритет |
|---------------------------|---------------------------|-------------------------------|-----------|
| `miniapp_auction_list`    | `GET /api/auction/list`   | Список лотов аукциона          | 🟡 средний |
| `miniapp_auction_create`  | `POST /api/auction/create`| Выставить предмет на торги     | 🟡 средний |
| `miniapp_auction_bid`     | `POST /api/auction/bid`   | Ставка                         | 🟡 средний |
| `miniapp_auction_buyout`  | `POST /api/auction/buyout`| Мгновенный выкуп               | 🟡 средний |
| `miniapp_auction_cancel`  | `POST /api/auction/cancel`| Отменить лот                   | 🟡 средний |

---

### 2.17 Подарки

| Endpoint                 | URL                      | Описание                      | Приоритет |
|--------------------------|--------------------------|-------------------------------|-----------|
| `miniapp_gifts_catalog`  | `GET /api/gifts/catalog` | Каталог подарков               | 🟡 средний |
| `miniapp_gifts_send`     | `POST /api/gifts/send`   | Отправить подарок пользователю | 🟡 средний |

---

### 2.18 Задания (Quests)

| Endpoint               | URL                   | Описание                        | Приоритет |
|------------------------|-----------------------|---------------------------------|-----------|
| `miniapp_quest`        | `GET /api/quest`      | Текущее задание + прогресс       | 🔴 высокий |
| `miniapp_quest_reroll` | `POST /api/quest/reroll`| Перебросить задание (кристалл) | 🟡 средний |
| `miniapp_newbie_quest` | `GET /api/newbie_quest`| Обучающий квест новичка         | 🟡 средний |

---

### 2.19 Сезонный пропуск (Season Pass)

| Endpoint                 | URL                      | Описание                           | Приоритет |
|--------------------------|--------------------------|------------------------------------|-----------|
| `miniapp_season_data`    | `GET /api/season/data`   | Трек, прогресс, награды (объявлен в api.ts, но нет страницы!) | 🔴 высокий |
| `miniapp_season_claim`   | `POST /api/season/claim` | Забрать награду                     | 🔴 высокий |
| `miniapp_season_premium` | `POST /api/season/premium`| Купить премиум-трек                | 🔴 высокий |

---

### 2.20 Таланты и Осколки

| Endpoint                  | URL                       | Описание                       | Приоритет |
|---------------------------|---------------------------|--------------------------------|-----------|
| `miniapp_shards`          | `GET /api/shards`         | Коллекция осколков              | 🟡 средний |
| `miniapp_shards_craft`    | `POST /api/shards/craft`  | Скрафтить предмет из осколков  | 🟡 средний |
| `miniapp_talents`         | `GET /api/talents`        | Дерево талантов                 | 🟡 средний |
| `miniapp_talents_upgrade` | `POST /api/talents/upgrade`| Прокачать талант               | 🟡 средний |

---

### 2.21 Профиль — редактирование

| Endpoint              | URL                 | Описание                        | Приоритет |
|-----------------------|---------------------|---------------------------------|-----------|
| `miniapp_set_bio`     | `POST /api/set_bio` | Изменить биографию               | 🔴 высокий |
| `miniapp_themes`      | `GET /api/themes`   | Список тем оформления            | 🟡 средний |
| `miniapp_get_avatar`  | `GET /api/get_avatar`| Получить аватар SVG/PNG          | 🟡 средний |
| `miniapp_save_avatar` | `POST /api/save_avatar`| Сохранить аватар                | 🟡 средний |
| `miniapp_user_avatar` | `GET /api/user_avatar/<id>`| Аватар произвольного пользователя | 🟡 средний |

---

### 2.22 Кристальный магазин

| Endpoint                  | URL                      | Описание                              | Приоритет |
|---------------------------|--------------------------|---------------------------------------|-----------|
| `miniapp_crystals_spend`  | `POST /api/crystals/spend`| Потратить кристаллы (VIP, рамка, тема и т.д.) | 🔴 высокий |

---

### 2.23 Рейтинг и социальное

| Endpoint                 | URL                    | Описание                              | Приоритет |
|--------------------------|------------------------|---------------------------------------|-----------|
| `miniapp_leaderboard`    | `GET /api/leaderboard` | ТОП пользователей чата                 | 🔴 высокий |
| `miniapp_members`        | `GET /api/members`     | Полный список участников               | 🟡 средний |
| `miniapp_public_profile` | `GET /api/public_profile`| Публичный профиль другого игрока     | 🟡 средний |
| `miniapp_spy`            | `POST /api/spy`        | Шпионаж за балансом другого            | 🟢 низкий  |

---

### 2.24 Модерация (Admin-only endpoints)

| Endpoint                      | URL                          | Описание                          |
|-------------------------------|------------------------------|-----------------------------------|
| `miniapp_warnlist`            | `GET /api/warnlist`          | Список предупреждений              |
| `miniapp_chat_banlist`        | `GET /api/chat/banlist`      | Бан-лист чата                      |
| `miniapp_admin_chat_summary`  | `GET /api/admin/chat_summary`| Сводка активности чата             |
| `miniapp_admin_roster`        | `GET /api/admin/roster`      | Полный ростер участников           |
| `miniapp_cleanup_config`      | `GET/POST /api/cleanup/config`| Настройки чистки                  |
| `miniapp_cleanup_pass`        | `POST /api/cleanup/pass`     | Купить пропуск чистки              |
| `miniapp_chat_buff`           | `POST /api/chat/buff`        | Активировать чат-бафф (admin)      |

---

### 2.25 Настройки и прочее

| Endpoint                      | URL                           | Описание                            | Приоритет |
|-------------------------------|-------------------------------|-------------------------------------|-----------|
| `miniapp_settings_local`      | `GET/POST /api/settings/local` | Chat-specific настройки (admin)     | 🟢 низкий  |
| `miniapp_settings_global`     | `GET/POST /api/settings/global`| Глобальные настройки (dev)          | 🟢 низкий  |
| `miniapp_timezone`            | `GET/POST /api/timezone`       | Установить часовой пояс             | 🟢 низкий  |
| `miniapp_chat_tags`           | `GET /api/chat/tags`           | Теги пользователей в чате           | 🟢 низкий  |
| `miniapp_tag_definitions`     | `GET /api/tag/definitions`     | Определения тегов                   | 🟢 низкий  |
| `miniapp_frontend_error_log`  | `POST /api/frontend/error_log` | Логирование ошибок фронта           | 🟡 средний |

---

## 3. ФУНКЦИОНАЛЬНОСТЬ ТОЛЬКО В БОТЕ (нет API, нет фронта)

Эти фичи существуют **только в bot handlers** и не имеют никакого API в miniapp_views.py. Перед миграцией необходимо создать новые endpoints.

### 3.1 Развлечения / Fun

- **Анимированные действия** (`fun.py`): пни, укуси, обними, поцелуй, погладь, кинь, бонк, ткни — `PlainCommand` + reply
- **Кубик/Дуэль** (`casino.py`): ставка на Telegram Dice, PvP
- **Анонимное сообщение** (`economy.py`): `/анонимка @user текст`
- **Секретное сообщение** (`economy.py`): `/секрет @user текст` — зашифрованное, смотреть за кристаллы
- **Погода** (`weather.py`): реальная погода города

### 3.2 Покупки (только через Telegram)

- **Telegram Stars → Кристаллы** (`stars.py`): `successful_payment` flow — целый платёжный флоу через Telegram
- **VIP** (`economy.py`): `/купить вип` — покупка VIP-статуса
- **XP-буст** (`economy.py`): `/купить буст` — покупка бустера опыта
- **Рамки/Frames** (`economy.py`): `/рамки` — витрина и покупка рамок профиля
- **Emoji-статус** (`shop.py`): `/эмодзи-статус` — установка emoji-статуса в Telegram

### 3.3 Административное (только бот)

- **Антифлуд** (`admin.py`): настройки + callback `af2:` — полная конфигурация AF2
- **Приветствие/Прощание** (`admin.py`): welcome/farewell сообщения
- **Автоответы/Фильтры** (`extras.py`): `/автоответ` — добавление авто-ответов на ключевые слова
- **Рассылка** (`owner.py`): broadcast по всем участникам
- **Чистка** (`admin.py`): kickout неактивных — `cmd_cleanup` + дата-чистка
- **Дилижанс** (`diligence.py`): рейтинг прилежности (только admin_senior+)
- **Сундук** (`owner.py`): виртуальный сундук с наградами
- **Тег входа** (`admin.py`): welcome call при вступлении

### 3.4 Вступление в сообщество (Join Flow)

- Весь `join_flow.py` — многошаговый онбординг нового участника (ссылка → DM → выбор роли → подтверждение → одобрение admin):
  - `jf:pick:`, `jf:confirm:`, `jfadm:accept:`, `jfadm:reject:`, `jfadm:postpone:`
  - **Нет API и нет плана миграции**

### 3.5 Роли в ЛС (DM Roles)

- Весь `dm_roles.py` — выбор роли в личных сообщениях бота:
  - Список доступных ролей, просмотр занятых, выбор и подтверждение
  - **Нет API и нет плана миграции**

### 3.6 Привязки чатов (Ecosystem)

- `owner.py`: `/привязать`, `/принять`, `/отвязать` — привязка нескольких чатов к одной экосистеме
- **Нет API**

---

## 4. ДАННЫЕ В БД, НЕ ОТОБРАЖАЕМЫЕ ВО ФРОНТЕ

| Данные                        | Где хранится              | В Profile? | Страница с действием? |
|-------------------------------|---------------------------|------------|----------------------|
| Банковский баланс + %         | `BankAccount` table       | ❌          | ❌                    |
| История кошелька              | `WalletTransaction` table | ❌          | ❌                    |
| Уровень улучшения предметов   | `InventoryItem.level`     | ❌ (только название) | ❌         |
| Эффекты зелий (активные баффы)| `UserBuff` / поле         | ❌          | ❌                    |
| Детали осколков               | `ShardCollection`         | ❌          | ❌                    |
| Дерево талантов               | `TalentNode` / JSON       | ❌          | ❌                    |
| Прогресс сезонного пропуска   | `SeasonProgress`          | ❌          | ❌                    |
| Активные экспедиции           | `Expedition`              | ❌          | ❌                    |
| Теги пользователя в чате      | `ChatTag`                 | ❌          | ❌                    |
| Активный emoji-статус         | поле профиля              | ❌          | ❌                    |
| Рамка профиля (frame)         | `active_frame` — показывается в user_data, но не отображается визуально | частично | ❌ |
| Активная тема (theme)         | `active_theme` — в user_data, но нет UI переключения | частично | ❌ |
| История аукционных торгов     | `AuctionLot` / `Bid`      | ❌          | ❌                    |
| Полученные подарки            | `Gift`                    | ❌          | ❌                    |
| Репутация/Diligence балл      | `DiligenceRecord`         | ❌          | ❌                    |
| Пропуска чистки               | `CleanupPass`             | ❌          | ❌                    |
| Ноты/заметки                  | `notes.py` — `UserNote`   | ❌          | ❌                    |
| Chatlog/история ухода         | `LeaveLog`                | ❌          | ❌                    |
| Warn история (только счётчик) | `Warn` table              | ⚠️ только счётчик `warns` | ❌ |
| Newbie Shield дата            | `newbie_shield_until` — показана в user_data но не объяснена | частично | ❌ |

---

## 5. СВОДНАЯ СТАТИСТИКА

| Категория                                       | Кол-во |
|-------------------------------------------------|--------|
| **Всего Django endpoints**                      | 118    |
| **Подключены к React Mini App**                  | 3      |
| **Объявлены в api.ts, но нет страницы**          | 2      |
| **Endpoints без фронтенда (нужны страницы)**     | 113    |
| **Bot-only features без API (нужны endpoint+UI)**| ~25    |
| **Поля в user_data отображены в Profile**        | 28/35  |
| **Страниц в React Mini App**                     | 4 (Profile, Inventory, Achievements, NotInTelegram) |

---

## 6. ПЛАН ПРИОРИТЕТОВ (РЕКОМЕНДУЕМЫЙ ПОРЯДОК)

### 🔴 Фаза 1 — Критично (пользователи ожидают это каждый день)
1. **Check-in** — `/api/checkin` → новая страница/кнопка
2. **Гача** — `/api/gacha/roll` → полноценная страница с анимацией
3. **Задания (Quests)** — `/api/quest` + reroll
4. **Инвентарь v2** — `/api/inventory` + equip + sell_junk (заменить текущий Inventory.tsx)
5. **Питомец (действия)** — walk + feed в Profile или отдельная страница
6. **Перевод моры** — `/api/transfer`
7. **Лидерборд** — `/api/leaderboard`
8. **Казино** — coin + roulette
9. **Изменение биографии** — кнопка в Profile
10. **Сезонный пропуск** — используется api.ts, нужна страница

### 🟡 Фаза 2 — Важно
11. **Банк** — deposit/withdraw
12. **Облигации (действия)** — buy/sell (данные уже в Profile)
13. **Семейный кошелёк (действия)** — deposit/withdraw/log
14. **История кошелька**
15. **Магазин (Shop)**
16. **Аукцион**
17. **Экспедиции**
18. **Подарки**
19. **Таланты и Осколки**
20. **Брак (действия)** — propose/respond

### 🟢 Фаза 3 — Приятно иметь
21. Темы (смена темы)
22. Аватар редактор
23. Тайм-зона
24. Публичный профиль
25. Шпионаж
26. Займы
27. Пропуск чистки
28. Теги
29. Настройки чата (для admin)
30. Admin панель (roster, summary, banlist)

---

*Файл сгенерирован автоматически на основе анализа `miniapp_views.py`, `handlers/`, `frontend/src/`*
