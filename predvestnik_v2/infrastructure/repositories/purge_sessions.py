# infrastructure/repositories/purge_sessions.py — admin_audit B4: сессии Чистки 2.0.
# Персистентное состояние чистки: начал в чате → продолжай на сайте и наоборот.
# Только SQL; логика/отправка — services/purge.py.
from infrastructure.pg_adapter import PGAdapter


async def get_active(db: PGAdapter, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM purge_sessions WHERE chat_id = ? AND status = 'active' "
        "ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ) as c:
        r = await c.fetchone()
    return dict(r) if r else None


async def get_by_id(db: PGAdapter, session_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM purge_sessions WHERE id = ?", (session_id,)
    ) as c:
        r = await c.fetchone()
    return dict(r) if r else None


async def create(db: PGAdapter, chat_id: int, initiator_id: int, norm: int,
                 date_from: str, date_to: str, dest_chat_id: int) -> int:
    async with db.execute(
        "INSERT INTO purge_sessions (chat_id, initiator_id, norm, date_from, date_to, dest_chat_id) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (chat_id, initiator_id, norm, date_from, date_to, dest_chat_id),
    ) as c:
        r = await c.fetchone()
    return int(r[0])


async def add_target(db: PGAdapter, session_id: int, user_id: int, username: str | None,
                     msg_count: int, days_in_chat: int, warns: int) -> None:
    await db.execute(
        "INSERT INTO purge_targets (session_id, user_id, username, msg_count, days_in_chat, warns) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (session_id, user_id) DO NOTHING",
        (session_id, user_id, username, msg_count, days_in_chat, warns),
    )


async def unsent_targets(db: PGAdapter, session_id: int, limit: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM purge_targets WHERE session_id = ? AND dossier_sent = FALSE "
        "ORDER BY msg_count ASC LIMIT ?",
        (session_id, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def mark_sent(db: PGAdapter, session_id: int, user_id: int) -> None:
    await db.execute(
        "UPDATE purge_targets SET dossier_sent = TRUE WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    )


async def get_target(db: PGAdapter, session_id: int, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM purge_targets WHERE session_id = ? AND user_id = ?",
        (session_id, user_id),
    ) as c:
        r = await c.fetchone()
    return dict(r) if r else None


async def set_verdict(db: PGAdapter, session_id: int, user_id: int,
                      verdict: str, verdict_by: int) -> bool:
    """Атомарно: вердикт ставится один раз (WHERE verdict IS NULL)."""
    async with db.execute(
        "UPDATE purge_targets SET verdict = ?, verdict_by = ?, verdict_at = NOW() "
        "WHERE session_id = ? AND user_id = ? AND verdict IS NULL RETURNING user_id",
        (verdict, verdict_by, session_id, user_id),
    ) as c:
        return (await c.fetchone()) is not None


async def counts(db: PGAdapter, session_id: int) -> dict:
    async with db.execute(
        "SELECT COUNT(*) AS total, "
        "COUNT(*) FILTER (WHERE dossier_sent) AS sent, "
        "COUNT(*) FILTER (WHERE verdict IS NOT NULL) AS decided, "
        "COUNT(*) FILTER (WHERE verdict = 'warn') AS warned, "
        "COUNT(*) FILTER (WHERE verdict = 'kick') AS kicked, "
        "COUNT(*) FILTER (WHERE verdict = 'ban') AS banned, "
        "COUNT(*) FILTER (WHERE verdict = 'skip') AS skipped "
        "FROM purge_targets WHERE session_id = ?",
        (session_id,),
    ) as c:
        r = await c.fetchone()
    return dict(r) if r else {"total": 0, "sent": 0, "decided": 0,
                              "warned": 0, "kicked": 0, "banned": 0, "skipped": 0}


async def list_targets(db: PGAdapter, session_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM purge_targets WHERE session_id = ? ORDER BY msg_count ASC",
        (session_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def finish(db: PGAdapter, session_id: int, status: str = "done") -> None:
    await db.execute(
        "UPDATE purge_sessions SET status = ?, finished_at = NOW() WHERE id = ?",
        (status, session_id),
    )
