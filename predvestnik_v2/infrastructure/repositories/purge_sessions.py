# infrastructure/repositories/purge_sessions.py — admin_audit B4: сессии Чистки 2.0.
# Персистентное состояние чистки: начал в чате → продолжай на сайте и наоборот.
# Только SQL; логика/отправка — services/purge.py.
from infrastructure.pg_adapter import PGAdapter


async def ensure_operations(db) -> None:
    # Inspect the actual database, rather than caching readiness across rollbacks.
    async with db.execute("SELECT COUNT(*)=10 AND to_regclass('purge_start_receipt') IS NOT NULL "
                          "FROM pg_attribute WHERE attrelid='purge_targets'::regclass "
                          "AND attname=ANY(?::text[]) AND NOT attisdropped",
                          (["decision_state", "decision_action", "decision_actor", "decision_key", "decision_error",
                            "decision_started_at", "verdict_by", "verdict_at", "total_messages", "note"],)) as cursor:
        if (await cursor.fetchone())[0]:
            return
    await db.execute("ALTER TABLE purge_sessions ADD COLUMN IF NOT EXISTS request_key TEXT")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS purge_start_receipt ON purge_sessions(chat_id,initiator_id,request_key) WHERE request_key IS NOT NULL")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_state TEXT NOT NULL DEFAULT 'idle'")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_action TEXT")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_actor BIGINT")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_key TEXT")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_error TEXT")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS decision_started_at TIMESTAMPTZ")
    # Dossier facts kept with the target: the background queue resends after a restart from the database alone.
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS total_messages INTEGER")
    await db.execute("ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS note TEXT")


async def insert_targets(db, session_id: int, targets: list[dict]) -> None:
    if not targets:
        return
    await db.execute("INSERT INTO purge_targets(session_id,user_id,username,msg_count,days_in_chat,warns,required_norm,member_tag,"
                     "total_messages,note) "
                     "SELECT ?,t.* FROM unnest(?::bigint[],?::text[],?::integer[],?::integer[],?::integer[],?::integer[],?::text[],"
                     "?::integer[],?::text[]) "
                     "AS t(user_id,username,msg_count,days_in_chat,warns,required_norm,member_tag,total_messages,note)",
                     (session_id,[t["user_id"] for t in targets],[t.get("username") for t in targets],
                      [t["count"] for t in targets],[t["days_in_chat"] for t in targets],
                      [t["warns"] for t in targets],[t["required"] for t in targets],[t.get("tag") for t in targets],
                      [t.get("total") for t in targets],[t.get("note") or None for t in targets]))


async def lock_chat(db, chat_id: int) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (f"purge:{int(chat_id)}",))


async def delivery_failed(db, session_id: int, user_id: int, key: str, started_at, state: str, error: str) -> None:
    # A delayed failure must not replace a newer decision or human verification.
    await db.execute("UPDATE purge_targets SET decision_state=?,decision_error=? "
                     "WHERE session_id=? AND user_id=? AND decision_key=? AND decision_started_at=?::text::timestamptz "
                     "AND decision_state='sending' AND verdict IS NULL",
                     (state, error, session_id, user_id, key, started_at.isoformat()))


async def target_page(db, session_id: int, page: int, mode: str) -> list[dict]:
    condition = {"pending": "AND verdict IS NULL", "decided": "AND verdict IS NOT NULL", "all": ""}[mode]
    async with db.execute(f"SELECT t.*,a.user_tg_name AS verdict_by_name,a.user_tg_username AS verdict_by_username, "
                          "(t.decision_state='unknown' OR t.decision_started_at<CLOCK_TIMESTAMP()-INTERVAL '2 minutes') AS reconcile_ready "
                          "FROM purge_targets t LEFT JOIN users a ON a.user_tg_id=t.verdict_by "
                          f"WHERE session_id=? {condition} ORDER BY msg_count,user_id LIMIT 26 OFFSET ?",
                          (session_id, page * 25)) as cursor:
        return [dict(r) for r in await cursor.fetchall()]


async def reserve(db, session_id: int, user_id: int, action: str, actor: int, action_id: str):
    async with db.execute("UPDATE purge_targets SET decision_state='sending',decision_action=?,decision_actor=?,decision_key=?,"
                          "decision_error=NULL,decision_started_at=CLOCK_TIMESTAMP() WHERE session_id=? AND user_id=? RETURNING decision_started_at",
                          (action, actor, action_id, session_id, user_id)) as cursor:
        return (await cursor.fetchone())[0]


async def operation_state(db, session_id: int, user_id: int, state: str, error: str | None = None) -> None:
    await db.execute("UPDATE purge_targets SET decision_state=?,decision_error=? WHERE session_id=? AND user_id=?",
                     (state, error, session_id, user_id))


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


async def latest_finished(db, chat_id: int) -> dict | None:
    async with db.execute("SELECT id,norm,date_from,date_to,finished_at FROM purge_sessions "
                          "WHERE chat_id=? AND status='finished' ORDER BY id DESC LIMIT 1", (chat_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def start_receipt(db, chat_id: int, actor: int, request_key: str) -> dict | None:
    async with db.execute("SELECT * FROM purge_sessions WHERE chat_id=? AND initiator_id=? AND request_key=?",
                          (chat_id, actor, request_key)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def create(db: PGAdapter, chat_id: int, initiator_id: int, norm: int,
                 date_from: str, date_to: str, dest_chat_id: int, request_key: str | None = None) -> int:
    async with db.execute(
        "INSERT INTO purge_sessions (chat_id, initiator_id, norm, date_from, date_to, dest_chat_id, request_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (chat_id, initiator_id, norm, date_from, date_to, dest_chat_id, request_key),
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


async def unsent_targets(db, session_id: int, limit: int, skip: list[int] = ()) -> list[dict]:
    """Next dossiers to send, in the order of the start message: furthest below the norm first.
    Targets saved before total_messages existed take the chat's all-time count."""
    async with db.execute(
        "SELECT t.user_id, t.username, t.msg_count, t.required_norm, "
        "COALESCE(t.total_messages, s.user_messages_count_all_time, 0) AS total_messages, "
        "t.days_in_chat, t.warns, t.note, t.member_tag "
        "FROM purge_targets t JOIN purge_sessions p ON p.id = t.session_id "
        "LEFT JOIN user_chat_stats s ON s.chat_tg_id = p.chat_id AND s.user_tg_id = t.user_id "
        "WHERE t.session_id = ? AND NOT COALESCE(t.dossier_sent, FALSE) AND t.verdict IS NULL "
        "AND NOT (t.user_id = ANY(?::bigint[])) "
        "ORDER BY t.msg_count - COALESCE(t.required_norm, 0), t.msg_count, t.user_id LIMIT ?",
        (session_id, [int(u) for u in skip], limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def sessions_with_unsent(db) -> list[dict]:
    """Active purges whose dossier queue a previous process did not finish."""
    async with db.execute(
        "SELECT s.id, s.chat_id, s.dest_chat_id, COALESCE(c.chat_title, '') AS chat_title FROM purge_sessions s "
        "LEFT JOIN chat_settings c ON c.chat_id = s.chat_id WHERE s.status = 'active' AND EXISTS "
        "(SELECT 1 FROM purge_targets t WHERE t.session_id = s.id AND NOT COALESCE(t.dossier_sent, FALSE) AND t.verdict IS NULL) ORDER BY s.id"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def mark_sent(db, session_id: int, user_id: int, member_tag: str | None) -> None:
    await db.execute(
        "UPDATE purge_targets SET dossier_sent = TRUE, member_tag = ? WHERE session_id = ? AND user_id = ?",
        (member_tag, session_id, user_id),
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
        "COUNT(*) FILTER (WHERE verdict = 'mute') AS muted, "
        "COUNT(*) FILTER (WHERE decision_state IN ('sending','unknown') AND verdict IS NULL) AS blocked, "
        "COUNT(*) FILTER (WHERE verdict IN ('skip','forgive')) AS skipped "
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


async def finish(db: PGAdapter, session_id: int, status: str = "finished") -> None:
    await db.execute(
        "UPDATE purge_sessions SET status = ?, finished_at = NOW() WHERE id = ?",
        (status, session_id),
    )
