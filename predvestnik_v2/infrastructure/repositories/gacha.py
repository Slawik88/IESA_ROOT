import json
import aiosqlite


async def get_pity(db: aiosqlite.Connection, user_id: int, spin_type: str) -> int:
    async with db.execute(
        "SELECT count FROM gacha_pity WHERE user_id = ? AND spin_type = ?",
        (user_id, spin_type),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def get_pity_locked(db: aiosqlite.Connection, user_id: int, spin_type: str) -> int:
    """Get pity count and hold a row-level lock for the current transaction.
    Ensures the row exists first so FOR UPDATE always locks something."""
    await db.execute(
        "INSERT INTO gacha_pity (user_id, spin_type, count) VALUES (?, ?, 0) "
        "ON CONFLICT(user_id, spin_type) DO NOTHING",
        (user_id, spin_type),
    )
    async with db.execute(
        "SELECT count FROM gacha_pity WHERE user_id = ? AND spin_type = ? FOR UPDATE",
        (user_id, spin_type),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def incr_pity(db: aiosqlite.Connection, user_id: int, spin_type: str) -> int:
    """Increment pity counter by 1 and return the new value. No commit."""
    async with db.execute(
        """INSERT INTO gacha_pity (user_id, spin_type, count) VALUES (?, ?, 1)
           ON CONFLICT(user_id, spin_type) DO UPDATE SET count = gacha_pity.count + 1
           RETURNING count""",
        (user_id, spin_type),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 1


async def reset_pity(db: aiosqlite.Connection, user_id: int, spin_type: str) -> None:
    """Reset pity counter to 0. No commit."""
    await db.execute(
        "INSERT INTO gacha_pity (user_id, spin_type, count) VALUES (?, ?, 0) "
        "ON CONFLICT(user_id, spin_type) DO UPDATE SET count = 0",
        (user_id, spin_type),
    )


async def get_all_pity(db: aiosqlite.Connection, user_id: int) -> dict:
    """Return {spin_type: count} for all active spin types. Missing default to 0."""
    from core.constants import SPIN_TYPE_LABELS
    async with db.execute(
        "SELECT spin_type, count FROM gacha_pity WHERE user_id = ?", (user_id,)
    ) as c:
        rows = await c.fetchall()
    result = {st: 0 for st in SPIN_TYPE_LABELS}  # Block 8: mora/diamond
    for spin_type, count in rows:
        if spin_type in result:
            result[spin_type] = count
    return result


async def log_history(
    db: aiosqlite.Connection,
    user_id: int,
    spin_type: str,
    reward_summary: dict,
) -> None:
    """Append one spin result to gacha_history. No commit."""
    await db.execute(
        "INSERT INTO gacha_history (user_id, spin_type, reward_json) VALUES (?, ?, ?)",
        (user_id, spin_type, json.dumps(reward_summary, ensure_ascii=False)),
    )


async def get_recent_history(
    db: aiosqlite.Connection,
    user_id: int,
    limit: int = 20,
) -> list[dict]:
    async with db.execute(
        "SELECT spin_type, reward_json, rolled_at FROM gacha_history "
        "WHERE user_id = ? ORDER BY rolled_at DESC LIMIT ?",
        (user_id, limit),
    ) as c:
        rows = await c.fetchall()
    result = []
    for spin_type, reward_json, rolled_at in rows:
        try:
            reward = json.loads(reward_json)
        except Exception:
            reward = {}
        result.append({"spin_type": spin_type, "reward": reward, "rolled_at": rolled_at})
    return result
