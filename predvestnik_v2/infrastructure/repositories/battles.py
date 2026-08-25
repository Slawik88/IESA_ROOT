"""
infrastructure/repositories/battles.py — legacy сессии боя (retirement LCB-001).
Server-authoritative: state_json (статы, волны, QTE-окно, анти-чит-счётчики)
живёт только здесь.
"""
import json


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS battles (
            id             SERIAL PRIMARY KEY,
            user_id        BIGINT NOT NULL,
            pet_id         INTEGER NOT NULL,
            mode           TEXT NOT NULL,
            ref_id         BIGINT NOT NULL DEFAULT 0,
            state_json     TEXT NOT NULL DEFAULT '{}',
            status         TEXT NOT NULL DEFAULT 'active',
            last_action_at FLOAT8 NOT NULL DEFAULT 0,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_battles_user ON battles(user_id, status)"
    )
    await db.commit()


async def get_active(db, user_id: int, mode: str | None = None) -> dict | None:
    q = "SELECT * FROM battles WHERE user_id = ? AND status = 'active'"
    p: tuple = (user_id,)
    if mode:
        q += " AND mode = ?"
        p = (user_id, mode)
    q += " ORDER BY id DESC LIMIT 1"
    async with db.execute(q, p) as c:
        row = await c.fetchone()
    if not row:
        return None
    d = dict(row)
    d["state"] = json.loads(d.get("state_json") or "{}")
    return d


async def create(db, user_id: int, pet_id: int, mode: str, ref_id: int, state_json: str) -> int:
    async with db.execute(
        "INSERT INTO battles (user_id, pet_id, mode, ref_id, state_json) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        (user_id, pet_id, mode, ref_id, state_json),
    ) as c:
        row = await c.fetchone()
    return int(row[0])


async def save_state(db, battle_id: int, state_json: str, last_action_at: float) -> None:
    await db.execute(
        "UPDATE battles SET state_json = ?, last_action_at = ? WHERE id = ?",
        (state_json, last_action_at, battle_id),
    )


async def finish(db, battle_id: int, status: str) -> None:
    await db.execute("UPDATE battles SET status = ? WHERE id = ?", (status, battle_id))


async def count_today(db, user_id: int, mode: str) -> int:
    """Сколько боёв этого режима игрок НАЧАЛ за текущие UTC-сутки (лимит входов)."""
    async with db.execute(
        "SELECT COUNT(*) FROM battles WHERE user_id = ? AND mode = ? "
        "AND created_at >= DATE_TRUNC('day', NOW())",
        (user_id, mode),
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0)


async def has_completed(db, user_id: int, mode: str, status: str = "won") -> bool:
    """Whether the player has a persisted completed battle of this mode.

    This is deliberately based on the immutable battle outcome rather than a
    cached user flag, so callers can reconcile derived progression state.
    """
    async with db.execute(
        "SELECT EXISTS(SELECT 1 FROM battles "
        "WHERE user_id = ? AND mode = ? AND status = ?)",
        (user_id, mode, status),
    ) as c:
        row = await c.fetchone()
    return bool(row and row[0])
