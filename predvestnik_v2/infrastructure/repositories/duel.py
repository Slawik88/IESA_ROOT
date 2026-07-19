import aiosqlite
from datetime import datetime, timezone


async def create_duel(
    db: aiosqlite.Connection,
    challenger_id: int,
    challenged_id: int,
    chat_id: int,
    stake: float,
    challenger_pet_id: int,
) -> int:
    """Insert pending duel. Returns new duel id."""
    async with db.execute(
        """INSERT INTO duels (challenger_id, challenged_id, chat_id, stake, challenger_pet_id)
           VALUES (?, ?, ?, ?, ?) RETURNING id""",
        (challenger_id, challenged_id, chat_id, stake, challenger_pet_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def get_duel(db: aiosqlite.Connection, duel_id: int) -> dict | None:
    async with db.execute("SELECT * FROM duels WHERE id = ?", (duel_id,)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def set_duel_status(
    db: aiosqlite.Connection,
    duel_id: int,
    status: str,
    winner_id: int | None = None,
    challenged_pet_id: int | None = None,
    winner_gain: float | None = None,
    commission: float | None = None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE duels SET status = ?, winner_id = ?, challenged_pet_id = COALESCE(?, challenged_pet_id), "
        "winner_gain = COALESCE(?, winner_gain), commission = COALESCE(?, commission), "
        "resolved_at = ? WHERE id = ?",
        (status, winner_id, challenged_pet_id, winner_gain, commission,
         now if status in ("finished", "declined", "timeout") else None, duel_id),
    )


async def get_cooldown(db: aiosqlite.Connection, user_a: int, user_b: int) -> str | None:
    """Return last_duel timestamp for this pair, or None."""
    key_a, key_b = min(user_a, user_b), max(user_a, user_b)
    async with db.execute(
        "SELECT last_duel FROM duel_cooldowns WHERE user_a = ? AND user_b = ?",
        (key_a, key_b),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def get_user_cooldowns(db, user_id: int) -> list[dict]:
    """Все пары этого юзера с временем последней дуэли и именем соперника
    (для ИИ-помощника: «с кем у меня кулдаун дуэли»). Фильтрацию по окну
    24ч делает вызывающий код — тут только сырые last_duel."""
    async with db.execute(
        "SELECT dc.user_a, dc.user_b, dc.last_duel, "
        "ua.user_tg_username, ub.user_tg_username "
        "FROM duel_cooldowns dc "
        "LEFT JOIN users ua ON ua.user_tg_id = dc.user_a "
        "LEFT JOIN users ub ON ub.user_tg_id = dc.user_b "
        "WHERE dc.user_a = ? OR dc.user_b = ?",
        (user_id, user_id),
    ) as c:
        rows = await c.fetchall()
    out = []
    for a, b, last, name_a, name_b in rows:
        opp_id, opp_name = (b, name_b) if a == user_id else (a, name_a)
        out.append({"opponent_id": opp_id, "opponent_name": opp_name, "last_duel": last})
    return out


async def set_cooldown(db: aiosqlite.Connection, user_a: int, user_b: int) -> None:
    key_a, key_b = min(user_a, user_b), max(user_a, user_b)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "INSERT INTO duel_cooldowns (user_a, user_b, last_duel) VALUES (?, ?, ?) "
        "ON CONFLICT(user_a, user_b) DO UPDATE SET last_duel = excluded.last_duel",
        (key_a, key_b, now),
    )


async def get_expired_pending(db: aiosqlite.Connection, timeout_seconds: int) -> list[dict]:
    """Return pending duels that timed out."""
    async with db.execute(
        "SELECT * FROM duels WHERE status = 'pending' "
        "AND EXTRACT(EPOCH FROM (NOW() - created_at)) >= ?",
        (timeout_seconds,),
    ) as c:
        rows = await c.fetchall()
    return [dict(r) for r in rows]
