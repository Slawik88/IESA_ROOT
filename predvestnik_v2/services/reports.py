"""Жалобы игроков на нарушителей: «бот жалоба» в чате -> очередь в админке.

Статусы: new (новая) -> in_work (взята в работу) -> resolved (нарушение подтверждено) | rejected (отклонена).
Строки не удаляются: закрытая жалоба остаётся в истории.
"""
from __future__ import annotations

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_reports (
        id           BIGSERIAL PRIMARY KEY,
        chat_id      BIGINT NOT NULL,
        reporter_id  BIGINT NOT NULL,
        target_id    BIGINT NOT NULL,
        reason       TEXT   NOT NULL DEFAULT '',
        message_id   BIGINT,
        message_text TEXT,
        status       TEXT   NOT NULL DEFAULT 'new',
        handled_by   BIGINT,
        handled_at   TIMESTAMPTZ,
        note         TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_reports_open ON bot_reports (created_at) WHERE status IN ('new', 'in_work')",
    "CREATE INDEX IF NOT EXISTS idx_bot_reports_target ON bot_reports (target_id)",
)
OPEN = ("new", "in_work")
CLOSED = ("resolved", "rejected")
STATUS_TITLES = {"new": "Новая", "in_work": "В работе", "resolved": "Нарушение подтверждено", "rejected": "Отклонена"}
DAILY_LIMIT = 10


class ReportError(Exception):
    pass


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def create(db, *, chat_id: int, reporter_id: int, target_id: int, reason: str,
                 message_id: int | None = None, message_text: str | None = None) -> int:
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"bot_report:{reporter_id}",))
        async with db.execute(
            "SELECT 1 FROM bot_reports WHERE reporter_id = ? AND target_id = ? AND chat_id = ? "
            "AND status IN ('new', 'in_work')", (reporter_id, target_id, chat_id)) as cur:
            if await cur.fetchone():
                raise ReportError("Ваша жалоба на этого игрока уже в очереди.")
        async with db.execute(
            "SELECT COUNT(*) FROM bot_reports WHERE reporter_id = ? AND created_at > NOW() - INTERVAL '1 day'",
            (reporter_id,)) as cur:
            if int((await cur.fetchone())[0]) >= DAILY_LIMIT:
                raise ReportError(f"Не больше {DAILY_LIMIT} жалоб в сутки.")
        async with db.execute(
            "INSERT INTO bot_reports (chat_id, reporter_id, target_id, reason, message_id, message_text) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (chat_id, reporter_id, target_id, reason[:300], message_id, (message_text or "")[:1000] or None)) as cur:
            return int((await cur.fetchone())[0])


async def counts(db) -> dict[str, int]:
    async with db.execute("SELECT status, COUNT(*) FROM bot_reports GROUP BY status") as cur:
        rows = {r[0]: int(r[1]) for r in await cur.fetchall()}
    return {s: rows.get(s, 0) for s in STATUS_TITLES}


async def listing(db, kind: str = "open", limit: int = 100) -> list[dict]:
    statuses = OPEN if kind == "open" else CLOSED
    order = "r.created_at ASC" if kind == "open" else "r.handled_at DESC NULLS LAST, r.id DESC"
    async with db.execute(
        "SELECT r.id, r.chat_id, c.chat_title, r.reporter_id, ur.user_tg_username, r.target_id, ut.user_tg_username, "
        "r.reason, r.message_id, r.message_text, r.status, r.handled_by, uh.user_tg_username, r.handled_at, r.note, "
        "r.created_at, (SELECT COUNT(*) FROM bot_reports x WHERE x.target_id = r.target_id) "
        "FROM bot_reports r LEFT JOIN chat_settings c ON c.chat_id = r.chat_id "
        "LEFT JOIN users ur ON ur.user_tg_id = r.reporter_id LEFT JOIN users ut ON ut.user_tg_id = r.target_id "
        "LEFT JOIN users uh ON uh.user_tg_id = r.handled_by "
        f"WHERE r.status IN (?, ?) ORDER BY {order} LIMIT ?", (*statuses, limit)) as cur:
        rows = await cur.fetchall()
    who = lambda uid, name: {"id": int(uid), "name": f"@{name}" if name else f"id{uid}"} if uid else None
    return [{
        "id": int(r[0]), "chat": {"id": int(r[1]), "title": r[2] or str(r[1])},
        "reporter": who(r[3], r[4]), "target": who(r[5], r[6]), "reason": r[7] or "",
        "message_id": r[8], "message_text": r[9] or "", "status": r[10], "status_title": STATUS_TITLES.get(r[10], r[10]),
        "handled_by": who(r[11], r[12]), "handled_at": r[13].isoformat() if r[13] else None, "note": r[14] or "",
        "created_at": r[15].isoformat() if r[15] else None, "target_reports": int(r[16]),
    } for r in rows]


async def get(db, report_id: int) -> dict | None:
    async with db.execute(
        "SELECT id, chat_id, reporter_id, target_id, status, reason FROM bot_reports WHERE id = ?", (report_id,)) as cur:
        r = await cur.fetchone()
    return {"id": int(r[0]), "chat_id": int(r[1]), "reporter_id": int(r[2]), "target_id": int(r[3]),
            "status": r[4], "reason": r[5] or ""} if r else None


async def set_status(db, report_id: int, status: str, actor_id: int, note: str = "") -> bool:
    """Сменить статус; False — жалоба уже закрыта (или её нет)."""
    if status not in STATUS_TITLES or status == "new":
        raise ReportError("Нет такого статуса.")
    async with db.execute(
        "UPDATE bot_reports SET status = ?, handled_by = ?, handled_at = NOW(), note = COALESCE(NULLIF(?, ''), note) "
        "WHERE id = ? AND status IN ('new', 'in_work') RETURNING id", (status, actor_id, note[:300], report_id)) as cur:
        return await cur.fetchone() is not None
