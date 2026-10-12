"""Жалобы игроков на нарушителей: «бот жалоба» в чате -> очередь в админке.

Статусы: new (новая) -> in_work (взята в работу) -> resolved (нарушение подтверждено) | rejected (отклонена).
Строки не удаляются: закрытая жалоба остаётся в истории.

Жалоба анонимна: автора не видит ни нарушитель, ни чат. В админке его видят только те, чья роль не ниже
`reporter_min_rank` (настройка жалоб), остальные — «автор скрыт». Куда уходит отчёт о жалобе, настраивается отдельно:
админ-чат, личка модераторам чата, личка персоналу бота.
"""
from __future__ import annotations

from services import member_tags

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
SETTINGS_KEY = "report_settings"
# dm_chat_rank — ранг в чате, с которого модераторам пишут в личку (0 — не писать);
# dm_staff_rank — роль в боте, с которой пишут в личку персоналу (0 — не писать);
# reporter_min_rank — роль в боте, с которой в админке виден автор жалобы.
DEFAULT_SETTINGS = {"to_admin_chat": True, "dm_chat_rank": 4, "dm_staff_rank": 0, "reporter_min_rank": 5}
OPEN = ("new", "in_work")
CLOSED = ("resolved", "rejected")
STATUS_TITLES = {"new": "Новая", "in_work": "В работе", "resolved": "Нарушение подтверждено", "rejected": "Отклонена"}
DAILY_LIMIT = 10


class ReportError(Exception):
    pass


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


_ready = False


async def _ensure(db) -> None:
    """Таблица создаётся при старте бота; если старт до неё не дошёл, создаём при первом обращении."""
    global _ready
    if not _ready:
        await ensure_schema(db)
        _ready = True


async def about(db, user_id: int, limit: int = 5) -> dict:
    """Жалобы на игрока для его карточки в админке. Авторов жалоб здесь нет: жалоба анонимна."""
    await _ensure(db)
    async with db.execute(
        "SELECT status, COUNT(*) FROM bot_reports WHERE target_id = ? GROUP BY status", (user_id,)) as cur:
        by_status = {r[0]: int(r[1]) for r in await cur.fetchall()}
    async with db.execute(
        "SELECT r.id, r.status, r.reason, c.chat_title, r.chat_id, r.created_at FROM bot_reports r "
        "LEFT JOIN chat_settings c ON c.chat_id = r.chat_id WHERE r.target_id = ? ORDER BY r.id DESC LIMIT ?",
        (user_id, limit)) as cur:
        rows = await cur.fetchall()
    return {"total": sum(by_status.values()), "open": sum(by_status.get(s, 0) for s in OPEN),
            "confirmed": by_status.get("resolved", 0),
            "last": [{"id": int(r[0]), "status": r[1], "status_title": STATUS_TITLES.get(r[1], r[1]), "reason": r[2] or "",
                      "chat": r[3] or str(r[4]), "created_at": r[5].isoformat() if r[5] else None} for r in rows]}


async def settings(db) -> dict:
    from bot.chat import settings as bot_settings
    saved = await bot_settings.get_json(db, SETTINGS_KEY, {})
    out = dict(DEFAULT_SETTINGS)
    if isinstance(saved, dict):
        out.update({k: saved[k] for k in DEFAULT_SETTINGS if k in saved})
    return out


async def save_settings(db, data: dict, actor_id: int) -> dict:
    from bot.chat import ranks
    from bot.chat import settings as bot_settings
    from bot.chat.global_ranks import CREATOR
    current = await settings(db)

    def number(key: str, low: int, high: int, off: bool) -> int:
        if key not in data:
            return current[key]
        try:
            value = int(data[key])
        except (TypeError, ValueError):
            raise ReportError("Ранг — целое число.")
        if not (low <= value <= high or (off and value == 0)):
            raise ReportError("Такого ранга нет.")
        return value

    new = {
        "to_admin_chat": bool(data["to_admin_chat"]) if "to_admin_chat" in data else current["to_admin_chat"],
        "dm_chat_rank": number("dm_chat_rank", 1, ranks.OWNER, True),
        "dm_staff_rank": number("dm_staff_rank", 1, CREATOR, True),
        "reporter_min_rank": number("reporter_min_rank", 1, CREATOR, False),
    }
    await bot_settings.set_json(db, SETTINGS_KEY, new, actor_id)
    return new


async def recipients(db, chat_id: int, reporter_id: int, conf: dict) -> list[int]:
    """Кому писать в личку о новой жалобе: модераторы этого чата и/или персонал бота (без автора жалобы)."""
    from bot.chat import ranks
    from bot.config import config
    found: set[int] = set()
    if conf["dm_chat_rank"]:
        owner = await ranks.get_owner(db, chat_id)
        if owner:
            found.add(int(owner))
        async with db.execute(
            "SELECT user_tg_id FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE "
            "AND COALESCE(chat_rank, 0) >= ? AND COALESCE(is_bot, FALSE) = FALSE", (chat_id, conf["dm_chat_rank"])) as cur:
            found.update(int(r[0]) for r in await cur.fetchall())
    if conf["dm_staff_rank"]:
        async with db.execute("SELECT user_tg_id FROM users WHERE COALESCE(bot_rank, 0) >= ?", (conf["dm_staff_rank"],)) as cur:
            found.update(int(r[0]) for r in await cur.fetchall())
    found.discard(int(reporter_id))
    # Создатель бота (DEVELOPER_ID) рангом в БД не хранится, но в личку ему писать можно.
    if conf["dm_staff_rank"] and config.developer_id and int(config.developer_id) != int(reporter_id):
        found.add(int(config.developer_id))
    return sorted(found)[:40]


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


REPEAT_DAYS = 30
REPEAT_MIN = 3


async def repeat_offenders(db, limit: int = 10) -> list[dict]:
    """Игроки, на которых за последние 30 дней подали 3 жалобы и больше (отклонённые не считаются).
    Авторов не показываем, только сколько разных людей пожаловалось: одна и та же обида трижды — не то же, что трое разных."""
    await _ensure(db)
    async with db.execute(
        "SELECT r.target_id, u.user_tg_username, COUNT(*), COUNT(DISTINCT r.reporter_id), "
        "COUNT(*) FILTER (WHERE r.status = 'resolved'), COUNT(*) FILTER (WHERE r.status IN ('new', 'in_work')), MAX(r.created_at) "
        "FROM bot_reports r LEFT JOIN users u ON u.user_tg_id = r.target_id "
        "WHERE r.created_at > NOW() - make_interval(days => ?) AND r.status <> 'rejected' "
        "GROUP BY r.target_id, u.user_tg_username HAVING COUNT(*) >= ? ORDER BY COUNT(*) DESC, MAX(r.created_at) DESC LIMIT ?",
        (REPEAT_DAYS, REPEAT_MIN, limit)) as cur:
        return [{"id": int(r[0]), "name": f"@{r[1]}" if r[1] else f"id{r[0]}", "reports": int(r[2]), "reporters": int(r[3]),
                 "confirmed": int(r[4]), "open": int(r[5]), "last": r[6].isoformat() if r[6] else None} for r in await cur.fetchall()]


async def listing(db, kind: str = "open", limit: int = 100, *, show_reporter: bool = False) -> list[dict]:
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
    tags = await member_tags.pairs(db, [(r[1], r[5]) for r in rows])   # тег жалуемого в том чате, где подана жалоба
    return [{
        "id": int(r[0]), "chat": {"id": int(r[1]), "title": r[2] or str(r[1])},
        "reporter": who(r[3], r[4]) if show_reporter else None, "reporter_hidden": not show_reporter,
        "target": ({**who(r[5], r[6]), "tag": tags.get((int(r[1]), int(r[5])))} if r[5] else None), "reason": r[7] or "",
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
