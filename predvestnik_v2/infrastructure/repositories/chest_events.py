from infrastructure.pg_adapter import PGAdapter


async def get_active_chest(db: PGAdapter, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM chest_events WHERE chat_id = ? AND status = 'active' LIMIT 1",
        (chat_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_chest(db: PGAdapter, chat_id: int, expires_at: str) -> int:
    async with db.execute(
        "INSERT INTO chest_events (chat_id, expires_at) VALUES (?, ?) RETURNING id",
        (chat_id, expires_at),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def close_chest(db: PGAdapter, chest_id: int) -> None:
    await db.execute("UPDATE chest_events SET status = 'closed' WHERE id = ?", (chest_id,))


async def get_claims(db: PGAdapter, chest_id: int) -> list[dict]:
    async with db.execute(
        "SELECT user_id, position FROM chest_claims WHERE chest_id = ? ORDER BY position",
        (chest_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_expired_active(db: PGAdapter) -> list[dict]:
    """Return active chests that have passed their expires_at."""
    async with db.execute(
        "SELECT * FROM chest_events WHERE status = 'active' AND expires_at <= NOW()"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_qualifying_chats(db: PGAdapter, min_users: int) -> list[int]:
    """Chats with enough active users in the last 24h without an active chest."""
    async with db.execute(
        """SELECT DISTINCT s.chat_tg_id
           FROM user_chat_stats s
           JOIN (
               SELECT chat_tg_id, COUNT(*) AS cnt
               FROM user_chat_stats
               WHERE last_message_at >= NOW() - INTERVAL '1 day'
               GROUP BY chat_tg_id
           ) active_counts ON active_counts.chat_tg_id = s.chat_tg_id
           LEFT JOIN chat_settings cs ON cs.chat_id = s.chat_tg_id
           WHERE active_counts.cnt >= ?
             AND COALESCE(cs.is_purging, FALSE) = FALSE
             AND COALESCE(cs.events_enabled, 1) = 1
             AND NOT EXISTS (
                 SELECT 1 FROM chest_events ce
                 WHERE ce.chat_id = s.chat_tg_id AND ce.status = 'active'
             )
             AND (cs.last_chest_at IS NULL
                  OR cs.last_chest_at <= NOW() - INTERVAL '4 hours')""",
        (min_users,),
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def update_last_chest_at(db: PGAdapter, chat_id: int) -> None:
    await db.execute(
        "UPDATE chat_settings SET last_chest_at = NOW() WHERE chat_id = ?", (chat_id,)
    )


async def get_dormant_chats(db: PGAdapter, quiet_days: float) -> list[int]:
    """Growth-полиш 2026-07-13 («реактивация тихого чата», находка 05): чаты,
    где ВООБЩЕ никто не писал ≥ quiet_days (порог настраивается дев-консолью,
    infrastructure/repositories/dev_settings.py) — вместо полного молчания
    получают редкий сундук.

    Кулдаун и защита от повтора переиспользуют ту же механику, что у обычных
    сундуков (chat_settings.last_chest_at + активный chest_events закрывает
    чат от повторного отбора, пока сундук жив) — отдельного состояния не заводим.

    Верхняя граница 60 дней: совсем заброшенные чаты не тревожим бесконечно."""
    async with db.execute(
        """SELECT s.chat_tg_id
           FROM user_chat_stats s
           LEFT JOIN chat_settings cs ON cs.chat_id = s.chat_tg_id
           WHERE COALESCE(cs.is_purging, FALSE) = FALSE
             AND COALESCE(cs.events_enabled, 1) = 1
             AND NOT EXISTS (
                 SELECT 1 FROM chest_events ce
                 WHERE ce.chat_id = s.chat_tg_id AND ce.status = 'active'
             )
             AND (cs.last_chest_at IS NULL
                  OR cs.last_chest_at <= NOW() - make_interval(days => ?))
           GROUP BY s.chat_tg_id
           HAVING MAX(s.last_message_at) <= NOW() - make_interval(days => ?)
              AND MAX(s.last_message_at) >= NOW() - INTERVAL '60 days'""",
        (quiet_days, quiet_days),
    ) as c:
        return [r[0] for r in await c.fetchall()]
