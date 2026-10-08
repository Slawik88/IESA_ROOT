"""Storage for player marks (hand-given and earned ones the server awarded) and an append-only log of every grant and revoke."""
from __future__ import annotations

import os

# Same zone and same date text as the counters in infrastructure/repositories/chat.py (daily_user_stats.date is a local «YYYY-MM-DD»).
_TZ = os.getenv("TIMEZONE_OFFSET", "+3 hours").replace("'", "")


async def ensure_tables(db) -> None:
    async with db.execute("SELECT to_regclass('player_marks_v1') IS NOT NULL AND to_regclass('player_marks_v1_log') IS NOT NULL") as c:
        if (await c.fetchone())[0]:
            return
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_marks_v1 (
            user_id BIGINT NOT NULL,
            mark_id TEXT NOT NULL,
            granted_by BIGINT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, mark_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS player_marks_v1_log (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            mark_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('grant', 'revoke')),
            actor_id BIGINT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS player_marks_v1_log_user ON player_marks_v1_log(user_id, id DESC)")


async def held(db, user_id: int) -> list[str]:
    async with db.execute("SELECT mark_id FROM player_marks_v1 WHERE user_id=? ORDER BY granted_at", (int(user_id),)) as c:
        return [str(r[0]) for r in await c.fetchall()]


async def held_batch(db, user_ids: list[int]) -> dict[int, list[str]]:
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    out: dict[int, list[str]] = {}
    async with db.execute(f"SELECT user_id, mark_id FROM player_marks_v1 WHERE user_id IN ({marks})", tuple(ids)) as c:
        for row in await c.fetchall():
            out.setdefault(int(row[0]), []).append(str(row[1]))
    return out


async def grant(db, user_id: int, mark_id: str, actor_id: int, reason: str) -> bool:
    """True when the mark was new for the player. The log row is written only for a real change."""
    async with db.execute(
        "INSERT INTO player_marks_v1(user_id, mark_id, granted_by, reason) VALUES (?,?,?,?) ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), str(mark_id), int(actor_id), reason),
    ) as c:
        created = await c.fetchone() is not None
    if created:
        await db.execute("INSERT INTO player_marks_v1_log(user_id, mark_id, action, actor_id, reason) VALUES (?,?, 'grant', ?, ?)",
                         (int(user_id), str(mark_id), int(actor_id), reason))
    return created


async def award(db, user_id: int, mark_id: str) -> bool:
    """The server gives an earned mark the first time its rule is met (actor 0, reason «auto»). True when it was new; the log row only then."""
    return await grant(db, user_id, mark_id, 0, "auto")


async def revoke(db, user_id: int, mark_id: str, actor_id: int, reason: str) -> bool:
    async with db.execute("DELETE FROM player_marks_v1 WHERE user_id=? AND mark_id=? RETURNING 1", (int(user_id), str(mark_id))) as c:
        removed = await c.fetchone() is not None
    if removed:
        await db.execute("INSERT INTO player_marks_v1_log(user_id, mark_id, action, actor_id, reason) VALUES (?,?, 'revoke', ?, ?)",
                         (int(user_id), str(mark_id), int(actor_id), reason))
    return removed


async def history(db, user_id: int, limit: int = 30) -> list[dict]:
    async with db.execute(
        "SELECT mark_id, action, actor_id, reason, created_at FROM player_marks_v1_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (int(user_id), int(limit)),
    ) as c:
        return [{"mark_id": str(r[0]), "action": str(r[1]), "actor_id": int(r[2]), "reason": str(r[3]), "at": r[4].isoformat() if r[4] else None}
                for r in await c.fetchall()]


async def best_streak_before(db, user_id: int) -> int:
    """The longest streak the old data remembers: any chat's streak row (the old per-chat streaks included), the streak lost at the last break
    (recovery), and the legacy «Постоянство» achievement, which kept the best streak ever until it was retired."""
    async with db.execute("SELECT COALESCE(MAX(GREATEST(COALESCE(streak, 0), COALESCE(recovery_streak, 0))), 0) FROM daily_login WHERE user_id=?", (int(user_id),)) as c:
        rows = (await c.fetchone())[0]
    async with db.execute("SELECT COALESCE(progress, 0) FROM achievements WHERE user_id=? AND achievement_id='persistent'", (int(user_id),)) as c:
        legacy = await c.fetchone()
    return max(int(rows or 0), int(legacy[0]) if legacy else 0)


def _since(days: int) -> str:
    """SQL for the first date of a window of `days` days that ends today."""
    return f"TO_CHAR(NOW() + INTERVAL '{_TZ}' - INTERVAL '{max(1, int(days)) - 1} days', 'YYYY-MM-DD')"


async def messages_recent_batch(db, user_ids: list[int], windows: tuple[int, ...] = (30, 60)) -> dict[int, dict[int, int]]:
    """Messages written in all chats per player over each window of days that ends today: {user_id: {days: count}}. One query for all of them."""
    ids = [int(u) for u in dict.fromkeys(user_ids or [])]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    sums = ", ".join(f"COALESCE(SUM(message_count) FILTER (WHERE date >= {_since(w)}), 0)" for w in windows)
    async with db.execute(f"SELECT user_id, {sums} FROM daily_user_stats WHERE user_id IN ({marks}) AND date >= {_since(max(windows))} GROUP BY user_id",
                          tuple(ids)) as c:
        return {int(r[0]): {w: int(r[1 + k] or 0) for k, w in enumerate(windows)} for r in await c.fetchall()}
