"""
infrastructure/repositories/minigames.py — сессии интеллектуальных мини-игр.
Server-authoritative: раскладка мин/секрет сейфа
живут ТОЛЬКО в state_json на сервере, клиент видит их после конца сессии.
"""
import json


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS minigame_sessions (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            game       TEXT NOT NULL,
            stake      FLOAT8 NOT NULL,
            state_json TEXT NOT NULL DEFAULT '{}',
            status     TEXT NOT NULL DEFAULT 'active',
            payout     FLOAT8 NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_mgs_user ON minigame_sessions(user_id, game, status)"
    )
    await db.commit()


async def get_active(db, user_id: int, game: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM minigame_sessions "
        "WHERE user_id = ? AND game = ? AND status = 'active' "
        "ORDER BY id DESC LIMIT 1",
        (user_id, game),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    d = dict(row)
    d["state"] = json.loads(d.get("state_json") or "{}")
    return d


async def seconds_since_last_start(db, user_id: int) -> int | None:
    """Секунд с последнего СТАРТА любой скилл-игры (для кулдауна). None = не играл."""
    async with db.execute(
        "SELECT CAST(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) AS BIGINT) "
        "FROM minigame_sessions WHERE user_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row and row[0] is not None else None


async def seconds_since_created(db, session_id: int) -> int:
    """Секунд с момента создания КОНКРЕТНОЙ сессии (анти-чит: честный дедлайн
    таймерных игр вроде Алхимии — не доверяем клиентским часам)."""
    async with db.execute(
        "SELECT CAST(EXTRACT(EPOCH FROM (NOW() - created_at)) AS BIGINT) "
        "FROM minigame_sessions WHERE id = ?",
        (session_id,),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


async def create_session(db, user_id: int, game: str, stake: float, state: dict) -> int:
    async with db.execute(
        "INSERT INTO minigame_sessions (user_id, game, stake, state_json) "
        "VALUES (?, ?, ?, ?) RETURNING id",
        (user_id, game, stake, json.dumps(state, ensure_ascii=False)),
    ) as c:
        row = await c.fetchone()
    return int(row[0])


async def update_state(db, session_id: int, state: dict) -> None:
    await db.execute(
        "UPDATE minigame_sessions SET state_json = ?, updated_at = NOW() WHERE id = ?",
        (json.dumps(state, ensure_ascii=False), session_id),
    )


async def finish(db, session_id: int, status: str, payout: float = 0.0) -> None:
    await db.execute(
        "UPDATE minigame_sessions SET status = ?, payout = ?, updated_at = NOW() WHERE id = ?",
        (status, payout, session_id),
    )
