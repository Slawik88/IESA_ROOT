"""Список «на контроле»: игроки, за которыми персонал хочет присмотреть (раздел «Игроки и чаты»).

Видят и ведут его сотрудники; игрок о пометке не узнаёт и ограничений от неё не получает.
Снятие с контроля ничего не стирает: строка остаётся с отметкой removed_at, а кто и когда ставил и снимал — в журнале админки.
"""
from __future__ import annotations

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_staff_watch (
        user_id    BIGINT PRIMARY KEY,
        added_by   BIGINT NOT NULL,
        reason     TEXT   NOT NULL DEFAULT '',
        added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        removed_at TIMESTAMPTZ,
        removed_by BIGINT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_staff_watch_active ON bot_staff_watch (added_at DESC) WHERE removed_at IS NULL",
)
MAX_REASON = 200

_ready = False


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


async def _ensure(db) -> None:
    if not _ready:
        await ensure_schema(db)


async def ensure_once(db) -> None:
    """Создать таблицу только при первом обращении в процессе: без DDL на каждом запросе."""
    await _ensure(db)


async def info(db, user_id: int) -> dict | None:
    """Кто и почему поставил игрока на контроль; None — не на контроле."""
    await _ensure(db)
    async with db.execute(
        "SELECT w.reason, w.added_by, u.user_tg_username, w.added_at FROM bot_staff_watch w "
        "LEFT JOIN users u ON u.user_tg_id = w.added_by WHERE w.user_id = ? AND w.removed_at IS NULL", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"reason": row[0] or "", "by": {"id": int(row[1]), "username": row[2]}, "at": row[3].isoformat() if row[3] else None}


async def add(db, user_id: int, actor_id: int, reason: str) -> bool:
    """True — поставлен сейчас; False — уже был на контроле (причина и автор остаются прежними)."""
    await _ensure(db)
    async with db.execute(
        "INSERT INTO bot_staff_watch (user_id, added_by, reason) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET added_by = EXCLUDED.added_by, reason = EXCLUDED.reason, added_at = NOW(), "
        "removed_at = NULL, removed_by = NULL WHERE bot_staff_watch.removed_at IS NOT NULL RETURNING 1",
        (user_id, actor_id, (reason or "").strip()[:MAX_REASON])) as cur:
        return bool(await cur.fetchone())


async def remove(db, user_id: int, actor_id: int) -> bool:
    await _ensure(db)
    async with db.execute(
        "UPDATE bot_staff_watch SET removed_at = NOW(), removed_by = ? WHERE user_id = ? AND removed_at IS NULL RETURNING 1",
        (actor_id, user_id)) as cur:
        return bool(await cur.fetchone())
