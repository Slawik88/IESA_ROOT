# infrastructure/repositories/users.py
import aiosqlite


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


async def get_user_id_by_username(db: aiosqlite.Connection, username: str) -> int | None:
    clean = username.lstrip("@")
    async with db.execute(
        "SELECT user_tg_id FROM users WHERE LOWER(user_tg_username) = LOWER(?)",
        (clean,),
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_user_name(db: aiosqlite.Connection, user_id: int) -> str:
    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row and row[0] else str(user_id)


async def create_user(db: aiosqlite.Connection, user_id: int, username: str | None):
    await db.execute(
        "INSERT OR IGNORE INTO users (user_tg_id, user_tg_username) VALUES (?, ?)",
        (user_id, username),
    )
    await db.commit()


async def set_global_rank(db: aiosqlite.Connection, user_id: int, rank_id: int):
    await db.execute(
        "UPDATE users SET global_rank = ? WHERE user_tg_id = ?", (rank_id, user_id)
    )
    await db.commit()


async def get_global_rank(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
        "SELECT global_rank FROM users WHERE user_tg_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def accept_tos(db: aiosqlite.Connection, user_id: int,
                     username: str | None = None) -> None:
    """БЛОК22: зафиксировать принятие документов. Idempotent — повторное принятие
    не перезаписывает время первого согласия. Создаёт строку при отсутствии."""
    await db.execute(
        "INSERT INTO users (user_tg_id, user_tg_username, tos_accepted_at) "
        "VALUES (?, ?, NOW()) "
        "ON CONFLICT(user_tg_id) DO UPDATE SET "
        "tos_accepted_at = COALESCE(users.tos_accepted_at, NOW())",
        (user_id, username),
    )
    await db.commit()


async def get_first_seen(db: aiosqlite.Connection, user_id: int) -> str | None:
    """Return ISO date string of the earliest joined_at across all chats, or None."""
    async with db.execute(
        "SELECT MIN(joined_at) FROM user_chat_stats WHERE user_tg_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return row[0] if row and row[0] else None


async def get_messages_global(db: aiosqlite.Connection, user_id: int) -> dict:
    """Return sum of per-day, per-week, all-time messages across all chats."""
    async with db.execute(
        """SELECT
               COALESCE(SUM(user_messages_count_per_day), 0)   AS day,
               COALESCE(SUM(user_messages_count_per_week), 0)  AS week,
               COALESCE(SUM(user_messages_count_all_time), 0)  AS all_time
           FROM user_chat_stats WHERE user_tg_id = ?""",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        return {"day": 0, "week": 0, "all_time": 0}
    return {"day": row[0], "week": row[1], "all_time": row[2]}


async def get_nickname(db: aiosqlite.Connection, user_id: int, chat_id: int) -> str | None:
    async with db.execute(
        "SELECT nickname FROM user_nicknames WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def set_nickname(
    db: aiosqlite.Connection, user_id: int, chat_id: int, nickname: str
) -> None:
    await db.execute(
        "INSERT INTO user_nicknames (user_id, chat_id, nickname) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, chat_id) DO UPDATE SET nickname = excluded.nickname, "
        "set_at = CURRENT_TIMESTAMP",
        (user_id, chat_id, nickname),
    )
    await db.commit()


async def delete_nickname(db: aiosqlite.Connection, user_id: int, chat_id: int) -> None:
    await db.execute(
        "DELETE FROM user_nicknames WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    await db.commit()


# ── R0/R1: уровень аккаунта и Индекс Силы (GDD_REBUILD_PLAN.md) ────────────────

async def ensure_account_columns(db) -> None:
    """Идемпотентные колонки прогрессии аккаунта. Зовётся и из бот-init,
    и из FastAPI lifespan (веб-процесс может стартовать раньше бота)."""
    for stmt in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_xp BIGINT DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_level INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS combat_power INTEGER DEFAULT 0",
        # Growth-полиш 2026-07-13: та же дуальная защита от гонки бот/веб-процессов,
        # что и у трёх колонок выше.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL",
        # Онбординг боя 2026-07-21: пройден ли скриптованный «Первый бой».
        # DEFAULT FALSE → и существующим игрокам предложим новое обучение (не форс —
        # заметная кнопка «▶ Первый бой» + «Пропустить», см. app.11.js).
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS combat_tutorial_done BOOLEAN DEFAULT FALSE",
        # «Что нового» 2026-07-23: id последней прочитанной записи ленты обновлений.
        # Раньше хранилось ТОЛЬКО в localStorage — Telegram WebView не гарантирует его
        # сохранность (чистка кэша/переустановка/долгий простой), поэтому у многих
        # игроков лента периодически «сбрасывалась» и всё показывалось заново «Новое».
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsnew_seen_id TEXT DEFAULT NULL",
    ):
        # КАЖДЫЙ ALTER — в своей транзакции (commit после успеха, rollback после сбоя).
        # PostgreSQL при ошибке ЛЮБОГО стейтмента аварийно завершает ВСЮ транзакцию, и
        # последующие команды молча игнорируются до конца блока. Раньше все ALTER'ы шли
        # одной транзакцией с общим commit в конце: сбой/гонка на ранней колонке отравлял
        # транзакцию, и combat_tutorial_done (последняя) НЕ создавалась — на проде это
        # давало «column combat_tutorial_done does not exist».
        try:
            await db.execute(stmt)
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass  # колонка уже есть / гонка двух процессов — не фатально


async def get_combat_tutorial_done(db, user_id: int) -> bool:
    """Онбординг боя: пройден ли «Первый бой» (флаг переживает смену устройства/кэша)."""
    try:
        async with db.execute(
            "SELECT combat_tutorial_done FROM users WHERE user_tg_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
        return bool(row and row[0])
    except Exception:
        return False  # колонка ещё не создана на этом процессе — считаем «не пройден»


async def set_combat_tutorial_done(db, user_id: int) -> None:
    """Отметить «Первый бой» пройденным (идемпотентно)."""
    await db.execute(
        "UPDATE users SET combat_tutorial_done = TRUE WHERE user_tg_id = ?", (user_id,))


async def add_account_xp(db, user_id: int, amount: int) -> dict:
    """Начислить XP аккаунту, вернуть свежие {account_xp, account_level}.
    Уровень здесь НЕ пересчитывается — это делает services.leveling
    (единственный владелец формулы кривой)."""
    async with db.execute(
        "UPDATE users SET account_xp = account_xp + ? WHERE user_tg_id = ? "
        "RETURNING account_xp, account_level",
        (amount, user_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else {"account_xp": 0, "account_level": 1}


async def set_account_level(db, user_id: int, level: int) -> None:
    await db.execute(
        "UPDATE users SET account_level = ? WHERE user_tg_id = ?",
        (level, user_id),
    )


async def get_account_progress(db, user_id: int) -> dict:
    """{account_xp, account_level} игрока (0/1, если строки users ещё нет)."""
    async with db.execute(
        "SELECT COALESCE(account_xp, 0) AS account_xp, "
        "COALESCE(account_level, 1) AS account_level "
        "FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else {"account_xp": 0, "account_level": 1}
