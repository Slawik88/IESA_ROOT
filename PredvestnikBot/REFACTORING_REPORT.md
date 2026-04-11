# Отчёт о рефакторинге PredvestnikBot

**Коммиты:** `4c02de8e` (Block 1), `20926617` (Blocks 2–4)  
**Файлов затронуто:** 45 (+ 1 удалён)  
**Строк удалено:** ~1717 | **Добавлено:** ~289 | **Чистое сокращение:** ~1428 строк

---

## Блок 1 — Поиск и исправление багов

### Подтверждённые баги (исправлены)

| # | Файл | Описание | Опасность |
|---|------|----------|-----------|
| 1 | `handlers/stars.py` | `CommandStart(deep_link=True)` перехватывал **все** deep links (включая `join_{chat_id}`), блокируя вступление в чат. Добавлен lambda-фильтр `buycrystals_` | 🔴 Критическая |
| 2 | `middlewares/message_counter.py:~790` | `settings["antiflood_enabled"]` → KeyError если настройка отсутствует. Заменено на `.get()` с дефолтами | 🟠 Высокая |
| 3 | `middlewares/message_counter.py:~818` | `stats["rank"]` (модераторский ранг: admin/owner) использовался для lookup trust-level (newcomer/regular/trusted). Заменено на `sv.trust` | 🟠 Высокая |

### Проверено и НЕ является багом (отфильтрованные false positives)

- `db.fetchone()` в api/casino, auction, roulette — PostgresConnection имеет нативный `fetchone()` метод
- `get_all_chat_admin_links()` без `await` — это sync-функция (чтение из in-memory dict)
- `tax_event.py` KeyError — уже обработан try/except
- `PostgresConnection.commit()` — no-op (`pass`), вызов безвреден
- Race conditions в `fun.py`/`casino.py` — безопасны в asyncio single-threaded event loop
- **Вся экономическая математика** (casino, wallet, roulette, bank) — проверена, ошибок не найдено

---

## Блок 2 — Clean Code

### `except Exception: pass` → логирование

**312 замен суммарно** (195 в Block 1 + 117 в Block 2)

Паттерн: `except Exception: pass` → `except Exception as _e: _log.debug("%s", _e)`

**Затронутые файлы (Block 2, 25 файлов):**

| Директория | Файлы |
|-----------|-------|
| `api/` | bank, bonds, casino, checkin, expeditions, gacha, loans, shop |
| `handlers/` | auction, auto_mod, bank, casino, economy, espionage, expeditions, food, gacha, gifts, moderator, owner, pets, reputation, shop, user |
| `filters/` | feature_flag |

### Удалённые неиспользуемые импорты

**~68 импортов из 30+ файлов**, включая:

- `is_community_admin_chat` из owner.py
- `get_staff_in_chat`, `get_top_by_xp_in_chat`, `set_bio_in_chat` из user.py
- `get_user`, `level_for_xp`, `set_bio_in_chat` из reputation.py
- `remove_user_from_banlist` из extras.py
- `AF2_ANTISPAM_ENABLED` из flood.py
- `FRAMES_CATALOG` из db.py
- И ещё 61 импорт через автоматизированный скрипт

---

## Блок 3 — Уничтожение мёртвого кода

### Удалённые мёртвые функции: **43 функции, 708 строк**

Каждая функция верифицирована через:
1. AST-парсинг для нахождения определений
2. Полнотекстовый поиск по **всему** проекту (включая `miniapp_views.py` в Django)
3. Подтверждение: имя функции встречается ТОЛЬКО в месте определения

#### `api/` — 4 функции

| Файл | Функция | Строк |
|------|---------|-------|
| achievements.py | `get_user_achievements()` | 24 |
| bonds.py | `get_portfolio()` | 46 |
| marriage.py | `respond_to_proposal_api()` | 55 |
| pets.py | `walk_pet()` | 14 |

#### `database/db.py` — 32 функции

| Функция | Строк | Функция | Строк |
|---------|-------|---------|-------|
| `is_community_admin_chat()` | 7 | `get_resting_user_ids()` | 23 |
| `get_chat_tag()` | 12 | `get_pending_join_requests()` | 17 |
| `can_give_rep()` | 16 | `reset_cleanup_counts()` | 10 |
| `get_pending_cleanup_passes()` | 14 | `get_todays_quest()` | 12 |
| `get_achievements()` | 10 | `award_achievement()` | 17 |
| `set_mora_public()` | 14 | `cancel_expired_duels()` | 13 |
| `reset_user_quest()` | 12 | `get_rep_last_time()` | 13 |
| `cleanup_expired_chat_buffs()` | 9 | `create_deposit()` | 17 |
| `get_mora_boost_pct()` | 17 | `award_badge()` | 12 |
| `get_user_greeting()` | 11 | `set_user_greeting()` | 15 |
| `check_greeting_today()` | 15 | `mark_greeting_shown()` | 12 |
| `get_rpg_stats()` | 40 | `reset_treasury()` | 10 |
| `touch_miniapp_online()` | 13 | `get_online_status()` | 22 |
| `get_crystal_chat_role()` | 12 | `get_chat_config()` | 24 |
| `upsert_chat_config()` | 28 | `get_weekly_top_users()` | 20 |
| `get_vip_users()` | 15 | `get_couple_boss_session()` | 20 |

#### `database/postgres.py` — 6 функций

| Функция | Строк |
|---------|-------|
| `close_pg_pool()` | 13 |
| `executemany()` | 8 |
| `execute_query()` | 7 |
| `fetch_all()` | 7 |
| `fetch_one()` | 7 |
| `fetch_value()` | 7 |

#### `filters/feature_flag.py` — 1 функция

| Функция | Строк |
|---------|-------|
| `get_feature_states()` | 18 |

### Прочий мёртвый код
- **Закомментированный код:** Просканированы все файлы. Найдено 7 блоков ≥5 строк — все являются легитимной документацией, не мёртвым кодом.
- **`refactor_block7.py`** — скрипт уже был применён (тема `bamboo` присутствует в `index.html`). Удалён.

---

## Блок 4 — Deep Code Review (DRY / Сложность)

### Созданные вспомогательные функции (`utils/helpers.py`)

| Функция | Назначение | Заменяет паттерн в |
|---------|------------|-------------------|
| `kb_grid(buttons, cols, footer)` | Построение InlineKeyboardMarkup сеткой | 15+ мест в handlers/ |
| `kb_single(text, callback_data)` | Одна кнопка → клавиатура | 10+ мест |
| `not_your_button(callback, owner_id, msg)` | Проверка владельца кнопки | 20+ мест |

### Выявленные паттерны DRY (для постепенной миграции)

| Паттерн | Количество | Рекомендация |
|---------|-----------|--------------|
| `UPDATE users SET balance=balance-?` (дедукция баланса) | 60+ | Вынести в `deduct_balance()` в economy_service.py |
| `callback.data.split(":")` + валидация | 60+ | Централизовать парсинг callback data |
| `InlineKeyboardMarkup(inline_keyboard=[[btn]])` | 100+ | Использовать новый `kb_single()` |
| Grid-building (loop + row append) | 15+ | Использовать новый `kb_grid()` |
| Проверка "не твоя кнопка" | 20+ | Использовать новый `not_your_button()` |

### Самые сложные функции (кандидаты на рефакторинг)

| Функция | Файл | Строк | Вложенность |
|---------|------|-------|-------------|
| `AutoModMiddleware.__call__()` | message_counter.py | 591 | 8+ уровней |
| `cmd_cleanup()` | admin.py | 231 | 6+ уровней |
| `_process_economy()` | message_counter.py | 93 | 5+ уровней |
| `cmd_spy()` | espionage.py | 125 | 5+ уровней |
| `cmd_dice()` | casino.py | 102 | 5+ уровней |

> ⚠️ `AutoModMiddleware.__call__()` — центральный middleware (591 строк). Рефакторинг требует отдельной ветки и тестирования.

---

## Итого

| Метрика | Значение |
|---------|---------|
| Баги исправлены | 3 (1 критический + 2 высоких) |
| `except: pass` → логирование | 312 |
| Неиспользуемые импорты удалены | ~68 |
| Мёртвые функции удалены | 43 (708 строк) |
| Строк удалено чистыми | ~1428 |
| Файлов затронуто | 45 |
| Вспомогательные функции созданы | 3 |
| AST-проверка | ✅ 1146 файлов — 0 ошибок |
