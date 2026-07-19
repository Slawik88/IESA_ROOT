# ИИ-помощник: обнаружение и видимость — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Игроки узнают о существовании ИИ-помощника («бот, [вопрос]») из приветствия новичка,
из главной справки, и (если пропустили оба) — из разовой проактивной подсказки после 30-го
сообщения в чате.

**Architecture:** Два статических текстовых изменения (приветствие, справка) + один флаг
`users.ai_hint_shown` (по образцу уже существующего `users.onboarded`) с атомарным
guard-апдейтом, триггерящийся по уже существующему счётчику
`user_chat_stats.user_messages_count_all_time`, который сейчас считается, но не прокидывается
наружу из `services/leveling.py::process_message_xp`.

**Tech Stack:** Python 3.11, aiogram 3.x, PostgreSQL (через `infrastructure/pg_adapter.PGAdapter`,
`?`-плейсхолдеры транслируются в `$1,$2...`), asyncio fire-and-forget для нотификаций в чат.

**Спека:** `docs/superpowers/specs/2026-07-19-ai-assistant-discovery-design.md` — полный дизайн
и обоснование решений.

## Global Constraints

- Полный текст подсказки о фиче: `🤖 Кстати — если что-то не понятно, просто напиши «бот, [вопрос]» — отвечу как помощник` — используется дословно.
- Аргумент команды в справочных текстах — в `[квадратных скобках]`, не в `<угловых>` (весь `HELP_PAGES` уже так делает — избегает HTML-экранирования внутри `<code>`).
- Порог проактивной подсказки — **ровно 30** (`msg_count == 30`), не диапазон. Это осознанное упрощение из спеки (см. «Принятое ограничение» там) — не расширять до `>= 30`.
- Подсказка шлётся только если `os.getenv("GEMINI_API_KEY")` непустой.
- Новая колонка `ai_hint_shown` — `BOOLEAN DEFAULT TRUE` (существующие игроки = «уже видели»), мигрируется идемпотентным `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` в `bot/core/database.py`, по образцу соседней колонки `onboarded`.
- В проекте нет pytest/тестового фреймворка (проверено: `find` по репозиторию не находит `conftest.py`/`pytest.ini`/`tests/`). Не вводим новый тестовый фреймворк ради этой фичи — верификация каждого шага: `python -m py_compile` + чтение диффа. Финальная проверка поведения — ручной смоук на проде (Task 6), как это сделано для всех предыдущих фич в этом репозитории.
- Иерархия слоёв (`CLAUDE.md`/`BASE_PROMPT.md`): `services/` не импортирует `bot.*`; новый файл `services/ai_hint.py` этому правилу подчиняется.

---

### Task 1: Тексты обнаружения — приветствие новичка и главная справка

**Files:**
- Modify: `bot/middlewares/db.py:56-64` (функция `_notify_starter_kit`)
- Modify: `bot/handlers/common.py:35-58` (`HELP_PAGES["main"]`)

**Interfaces:**
- Consumes: ничего (чисто текстовые правки, независимая задача).
- Produces: ничего, на что опираются другие задачи.

- [ ] **Step 1: Добавить строку про ИИ-помощника в приветствие новичка**

В `bot/middlewares/db.py` найти функцию `_notify_starter_kit` (текущее содержимое):

```python
    text = (
        f"🎉 <b>Добро пожаловать, {name}!</b>\n"
        f"Тебе выдан стартовый набор:\n"
        f"🐾 Питомец: {safe_html(kit['species_name'])}\n"
        f"🪙 +{int(kit['mora'])} Моры\n"
        f"💎 +{int(kit['diamonds'])} Алмазов (хватит на 1 алмазный спин)\n"
        f"🎟 +{kit['spin_tokens']} Жетон Гачи (бесплатный спин за Мору)\n\n"
        f"Загляни в «бот зоопарк» и «бот крутка» 🎲"
    )
```

Заменить на:

```python
    text = (
        f"🎉 <b>Добро пожаловать, {name}!</b>\n"
        f"Тебе выдан стартовый набор:\n"
        f"🐾 Питомец: {safe_html(kit['species_name'])}\n"
        f"🪙 +{int(kit['mora'])} Моры\n"
        f"💎 +{int(kit['diamonds'])} Алмазов (хватит на 1 алмазный спин)\n"
        f"🎟 +{kit['spin_tokens']} Жетон Гачи (бесплатный спин за Мору)\n\n"
        f"Загляни в «бот зоопарк» и «бот крутка» 🎲\n"
        f"🤖 А если что-то будет непонятно — просто напиши «бот, [вопрос]»"
    )
```

- [ ] **Step 2: Добавить строку про ИИ-помощника в главную справку**

В `bot/handlers/common.py`, в `HELP_PAGES["main"]` найти конец блока (текущее содержимое):

```python
        "⚡ <b>Быстрый старт</b> — пишется в группе с ботом:\n"
        "<code>бот я</code> · <code>бот баланс</code> · <code>бот поход</code> · <code>бот сайт</code>"
    ),
```

Заменить на:

```python
        "⚡ <b>Быстрый старт</b> — пишется в группе с ботом:\n"
        "<code>бот я</code> · <code>бот баланс</code> · <code>бот поход</code> · <code>бот сайт</code>\n\n"
        "🤖 <b>Вопрос?</b> Напиши <code>бот, [вопрос]</code> — отвечу как помощник"
    ),
```

- [ ] **Step 3: Проверить синтаксис**

Run: `cd predvestnik_v2 && python -m py_compile bot/middlewares/db.py bot/handlers/common.py`
Expected: команда завершается без вывода и без ошибок (код выхода 0).

- [ ] **Step 4: Commit**

```bash
git add predvestnik_v2/bot/middlewares/db.py predvestnik_v2/bot/handlers/common.py
git commit -m "feat(bot): упомянуть ИИ-помощника в приветствии новичка и главной справке"
```

---

### Task 2: Схема — колонка `users.ai_hint_shown`

**Files:**
- Modify: `bot/core/database.py:121-146` (список миграционных `ALTER TABLE` для `users`)
- Modify: `infrastructure/repositories/users.py:5-17` (`update_user`)

**Interfaces:**
- Consumes: ничего.
- Produces: колонка `users.ai_hint_shown BOOLEAN DEFAULT TRUE` в схеме; новые игроки
  вставляются с `ai_hint_shown = FALSE`. Используется в Task 4 (`services/ai_hint.py`).

- [ ] **Step 1: Добавить колонку в список миграций**

В `bot/core/database.py` найти список миграций `users` (текущий фрагмент):

```python
        # Block 10: DEFAULT TRUE → существующие игроки уже «онбордингованы»
        # (стартовый набор не получат); новые вставляются с FALSE (update_user).
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS contrabanda_last_at TIMESTAMP DEFAULT NULL",
```

Заменить на:

```python
        # Block 10: DEFAULT TRUE → существующие игроки уже «онбордингованы»
        # (стартовый набор не получат); новые вставляются с FALSE (update_user).
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded BOOLEAN DEFAULT TRUE",
        # Discovery-полиш 2026-07-19 (docs/superpowers/specs/2026-07-19-
        # ai-assistant-discovery-design.md): тот же приём для разовой подсказки
        # про ИИ-помощника — существующие игроки «уже видели», новые вставляются
        # с FALSE (update_user), переключает только services.ai_hint.mark_ai_hint_shown.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_hint_shown BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS contrabanda_last_at TIMESTAMP DEFAULT NULL",
```

- [ ] **Step 2: Вставлять новых игроков с `ai_hint_shown = FALSE`**

В `infrastructure/repositories/users.py` текущее содержимое `update_user`:

```python
async def update_user(db: aiosqlite.Connection, user_id: int, username: str | None):
    """Upsert: register user or refresh username if it changed.

    Block 10: новые игроки вставляются с onboarded=FALSE (колонка иначе DEFAULT
    TRUE — существующие игроки набор не получают). Флаг переключает только
    services.onboarding.grant_starter_kit.
    """
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, onboarded) VALUES (?, ?, FALSE) "
        "ON CONFLICT(user_tg_id) DO UPDATE SET user_tg_username = ?",
        (user_id, username, username),
    )
    await db.commit()
```

Заменить на:

```python
async def update_user(db: aiosqlite.Connection, user_id: int, username: str | None):
    """Upsert: register user or refresh username if it changed.

    Block 10: новые игроки вставляются с onboarded=FALSE (колонка иначе DEFAULT
    TRUE — существующие игроки набор не получают). Флаг переключает только
    services.onboarding.grant_starter_kit.
    Discovery-полиш 2026-07-19: тот же приём для ai_hint_shown — переключает
    только services.ai_hint.mark_ai_hint_shown.
    """
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, onboarded, ai_hint_shown) "
        "VALUES (?, ?, FALSE, FALSE) "
        "ON CONFLICT(user_tg_id) DO UPDATE SET user_tg_username = ?",
        (user_id, username, username),
    )
    await db.commit()
```

- [ ] **Step 3: Проверить синтаксис**

Run: `cd predvestnik_v2 && python -m py_compile bot/core/database.py infrastructure/repositories/users.py`
Expected: без вывода, код выхода 0.

- [ ] **Step 4: Проверить, что новая строка ALTER присутствует ровно один раз**

Run: `cd predvestnik_v2 && grep -c "ai_hint_shown BOOLEAN DEFAULT TRUE" bot/core/database.py`
Expected: `1`

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/bot/core/database.py predvestnik_v2/infrastructure/repositories/users.py
git commit -m "feat(db): колонка users.ai_hint_shown — флаг разовой подсказки про ИИ"
```

---

### Task 3: `process_message_xp` — прокинуть счётчик сообщений наружу

**Files:**
- Modify: `services/leveling.py:83-147`

**Interfaces:**
- Consumes: ничего нового (внутри уже вычисляется `msg_count = stats.get("user_messages_count_all_time", 0)` на строке 97 — используем существующую переменную).
- Produces: новая сигнатура
  `process_message_xp(db, user_id: int, chat_id: int, timezone_offset: str = "+3 hours") -> tuple[bool, int, int]`
  — `(level_up, account_level, msg_count)`. Используется в Task 5.
  Единственный существующий вызывающий (`bot/middlewares/db.py`) сейчас не распаковывает
  возврат вообще — расширение с 2 до 3 элементов кортежа не ломает его до Task 5.

- [ ] **Step 1: Обновить сигнатуру и докстринг**

Текущее:

```python
async def process_message_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> tuple[bool, int]:
    """Начислить XP за одно сообщение: per-chat счётчик (топы) + XP аккаунта.

    Аккаунт получает: base×софт-кап + бонус Конспекта + бонус Совы.
    Per-chat user_xp получает те же слагаемые БЕЗ софт-капа (это счётчик
    активности, а не прогрессия — резать его незачем).
    Возвращает (был ли левел-ап аккаунта, текущий уровень аккаунта)."""
```

Заменить на:

```python
async def process_message_xp(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    timezone_offset: str = "+3 hours",
) -> tuple[bool, int, int]:
    """Начислить XP за одно сообщение: per-chat счётчик (топы) + XP аккаунта.

    Аккаунт получает: base×софт-кап + бонус Конспекта + бонус Совы.
    Per-chat user_xp получает те же слагаемые БЕЗ софт-капа (это счётчик
    активности, а не прогрессия — резать его незачем).
    Возвращает (был ли левел-ап аккаунта, текущий уровень аккаунта,
    счётчик сообщений юзера в этом чате — user_messages_count_all_time)."""
```

- [ ] **Step 2: Прокинуть `msg_count` в оба return**

Текущее (конец функции):

```python
    if new_lvl > old_lvl:
        await users_repo.set_account_level(db, user_id, new_lvl)
        mora, diamonds = _level_up_rewards(old_lvl, new_lvl)
        await eco_repo.add_balance(
            db, user_id, mora=mora, diamonds=diamonds,
            source="level_up", note=f"Уровень аккаунта {new_lvl}",
        )
        return True, new_lvl

    return False, new_lvl
```

Заменить на:

```python
    if new_lvl > old_lvl:
        await users_repo.set_account_level(db, user_id, new_lvl)
        mora, diamonds = _level_up_rewards(old_lvl, new_lvl)
        await eco_repo.add_balance(
            db, user_id, mora=mora, diamonds=diamonds,
            source="level_up", note=f"Уровень аккаунта {new_lvl}",
        )
        return True, new_lvl, msg_count

    return False, new_lvl, msg_count
```

- [ ] **Step 3: Проверить синтаксис**

Run: `cd predvestnik_v2 && python -m py_compile services/leveling.py`
Expected: без вывода, код выхода 0.

- [ ] **Step 4: Убедиться, что единственный вызывающий не распаковывает возврат (иначе Task 3 сломает Task 5 до его старта)**

Run: `cd predvestnik_v2 && grep -rn "process_message_xp" --include=*.py .`
Expected: ровно два совпадения — определение в `services/leveling.py` и вызов в
`bot/middlewares/db.py` вида `await leveling.process_message_xp(` **без** `=` слева
(возврат не распаковывается). Если найдётся третий вызывающий — остановиться и
скорректировать план, а не расширять сигнатуру вслепую.

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/services/leveling.py
git commit -m "feat(leveling): process_message_xp возвращает msg_count третьим элементом"
```

---

### Task 4: `services/ai_hint.py` — атомарный guard-флаг

**Files:**
- Create: `services/ai_hint.py`

**Interfaces:**
- Consumes: колонку `users.ai_hint_shown` из Task 2.
- Produces: `async def mark_ai_hint_shown(db, user_id: int) -> bool` — `True`, если это первый
  вызов для юзера (подсказку нужно отправить сейчас), `False` — уже отправляли или гонка
  параллельного чата уже забрала право первой отправки. Используется в Task 5.

- [ ] **Step 1: Написать файл**

```python
"""services/ai_hint.py — разовая проактивная подсказка про ИИ-помощника после
N-го сообщения новичка в чате (docs/superpowers/specs/2026-07-19-ai-assistant-
discovery-design.md). Атомарный флаг-гард — тот же приём, что
services/onboarding.py::grant_starter_kit для users.onboarded.
"""


async def mark_ai_hint_shown(db, user_id: int) -> bool:
    """True — это первый вызов для юзера, подсказку нужно отправить.
    False — уже отправляли (или гонка: параллельный чат уже забрал право
    первой отправки между чтением msg_count и этим вызовом)."""
    async with db.execute(
        "UPDATE users SET ai_hint_shown = TRUE "
        "WHERE user_tg_id = ? AND ai_hint_shown = FALSE RETURNING user_tg_id",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        return False
    await db.commit()
    return True
```

- [ ] **Step 2: Проверить синтаксис**

Run: `cd predvestnik_v2 && python -m py_compile services/ai_hint.py`
Expected: без вывода, код выхода 0.

- [ ] **Step 3: Проверить, что файл не импортирует `bot.*`/`FastAPI.*` (иерархия слоёв проекта)**

Run: `cd predvestnik_v2 && grep -E "^(from|import) (bot|FastAPI)" services/ai_hint.py`
Expected: пустой вывод (нет совпадений).

- [ ] **Step 4: Commit**

```bash
git add predvestnik_v2/services/ai_hint.py
git commit -m "feat(services): ai_hint.mark_ai_hint_shown — атомарный guard для разовой подсказки"
```

---

### Task 5: Подключить триггер в `bot/middlewares/db.py`

**Files:**
- Modify: `bot/middlewares/db.py:1-16` (imports)
- Modify: `bot/middlewares/db.py:50` (новая функция `_notify_ai_hint`, рядом с `_notify_starter_kit`)
- Modify: `bot/middlewares/db.py:196-201` (точка вызова `process_message_xp`)

**Interfaces:**
- Consumes: `leveling.process_message_xp(...) -> tuple[bool, int, int]` (Task 3),
  `services.ai_hint.mark_ai_hint_shown(db, user_id: int) -> bool` (Task 4).
- Produces: ничего, на что опираются другие задачи — финальная точка интеграции.

- [ ] **Step 1: Добавить `import os`**

В `bot/middlewares/db.py` текущий верх файла:

```python
import time
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from loguru import logger
```

Заменить на:

```python
import os
import time
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from loguru import logger
```

- [ ] **Step 2: Добавить `_notify_ai_hint` рядом с `_notify_starter_kit`**

Текущее (после `_notify_starter_kit`, перед `_notify_quest_completions`):

```python
    asyncio.ensure_future(_safe_send(bot, chat_id, text))


def _notify_quest_completions(bot, chat_id: int, user, completed: list) -> None:
```

Заменить на:

```python
    asyncio.ensure_future(_safe_send(bot, chat_id, text))


def _notify_ai_hint(bot, chat_id: int, user) -> None:
    """Discovery-полиш 2026-07-19: разовая подсказка про ИИ-помощника после
    30-го сообщения новичка в чате (fire-and-forget)."""
    import asyncio
    if not bot:
        return
    text = "🤖 Кстати — если что-то не понятно, просто напиши «бот, [вопрос]» — отвечу как помощник"
    asyncio.ensure_future(_safe_send(bot, chat_id, text))


def _notify_quest_completions(bot, chat_id: int, user, completed: list) -> None:
```

- [ ] **Step 3: Подключить триггер на точке вызова `process_message_xp`**

Текущее:

```python
                # process_message_xp → chat_repo.increment_stats_and_get_xp which
                # updates BOTH user_chat_stats rolling counters AND daily_user_stats.
                # Single source of truth — no second INSERT needed here.
                await leveling.process_message_xp(
                    db, user.id, chat_obj.id, _tz
                )
```

Заменить на:

```python
                # process_message_xp → chat_repo.increment_stats_and_get_xp which
                # updates BOTH user_chat_stats rolling counters AND daily_user_stats.
                # Single source of truth — no second INSERT needed here.
                _, _, _msg_count = await leveling.process_message_xp(
                    db, user.id, chat_obj.id, _tz
                )

                # Discovery-полиш 2026-07-19: разовая подсказка про ИИ-помощника
                # после 30-го сообщения новичка в чате (см. spec в docs/superpowers).
                if _msg_count == 30 and os.getenv("GEMINI_API_KEY"):
                    try:
                        from services.ai_hint import mark_ai_hint_shown
                        if await mark_ai_hint_shown(db, user.id):
                            _notify_ai_hint(data.get("bot"), chat_obj.id, user)
                    except Exception:
                        pass
```

- [ ] **Step 4: Проверить синтаксис**

Run: `cd predvestnik_v2 && python -m py_compile bot/middlewares/db.py`
Expected: без вывода, код выхода 0.

- [ ] **Step 5: Проверить, что новый блок действительно внутри того же `try`, что и остальной трекинг (не должен ронять хендлер игрока при сбое)**

Run: `cd predvestnik_v2 && python - <<'EOF'
import ast
tree = ast.parse(open("bot/middlewares/db.py", encoding="utf-8").read())
src = open("bot/middlewares/db.py", encoding="utf-8").read()
assert "_msg_count == 30" in src, "триггер не найден"
assert "mark_ai_hint_shown" in src, "вызов guard-функции не найден"
print("OK: триггер на месте, файл — валидный Python")
EOF
`
Expected: `OK: триггер на месте, файл — валидный Python`

- [ ] **Step 6: Commit**

```bash
git add predvestnik_v2/bot/middlewares/db.py
git commit -m "feat(bot): триггер разовой подсказки про ИИ-помощника после 30-го сообщения"
```

---

### Task 6: Деплой и ручной смоук на проде

**Files:** нет (только верификация уже задеплоенного поведения).

**Interfaces:**
- Consumes: весь функционал из Task 1–5.
- Produces: ничего.

- [ ] **Step 1: Задеплоить на DigitalOcean**

Обычный деплой ветки (push/merge — по текущему процессу проекта). Дождаться рестарта
процесса — миграция `ai_hint_shown` применится сама при старте (`bot/core/database.py::init_db`).

- [ ] **Step 2: Проверить главную справку**

В чате с ботом (или тестовом группе) написать `бот помощь`. В открывшемся главном экране под
блоком «⚡ Быстрый старт» должна быть строка `🤖 Вопрос? Напиши бот, [вопрос] — отвечу как
помощник`.

- [ ] **Step 3: Проверить приветствие новичка**

Зайти в тестовый чат с ботом новым (ранее не игравшим) Telegram-аккаунтом, написать любое
сообщение. Должно прийти приветствие со стартовым набором, заканчивающееся строкой
`🤖 А если что-то будет непонятно — просто напиши «бот, [вопрос]»`.

- [ ] **Step 4: Проверить проактивную подсказку**

Тем же новым тестовым аккаунтом написать в чате ещё 29 любых сообщений (итого 30, включая
первое из Step 3). Ровно после 30-го сообщения должно прийти отдельное сообщение бота:
`🤖 Кстати — если что-то не понятно, просто напиши «бот, [вопрос]» — отвечу как помощник`.
Написать 31-е сообщение — подсказка НЕ должна повториться.

- [ ] **Step 5: Проверить, что сама фича ИИ по-прежнему работает**

Тем же аккаунтом написать `бот, что такое поход`. Должен прийти ответ ИИ-помощника (не
«недоступен»/«не настроен») — подтверждает, что `GEMINI_API_KEY` на проде задан и правки не
задели сам вызов Gemini.

- [ ] **Step 6: Обновить PLAYER_CHANGELOG.md**

Добавить в начало `predvestnik_v2/PLAYER_CHANGELOG.md` короткую запись простым языком
(например: «Бот теперь сам подсказывает про ИИ-помощника новичкам — в приветствии, в справке
и один раз в чате после того, как освоишься»). Формат — как в существующих записях файла
(смотреть верх файла перед добавлением).

- [ ] **Step 7: Commit changelog**

```bash
git add predvestnik_v2/PLAYER_CHANGELOG.md
git commit -m "docs(changelog): ИИ-помощник — обнаружение в приветствии/справке/чате"
```
