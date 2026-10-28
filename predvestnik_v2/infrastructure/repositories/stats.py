# infrastructure/repositories/stats.py
import aiosqlite
from core.chat_inactivity import InactiveMember, InactivePage, PAGE_SIZE

# all_time still reads from the counter column; period-based reads from daily_user_stats
# so that stale lazy-reset counters can't show players who haven't written today.


def _ranked_chat(chat_column: str) -> str:
    if chat_column not in {"d.chat_id", "s.chat_tg_id"}:
        raise ValueError("unsupported chat ranking column")
    return ("COALESCE(c.include_in_global_top,1)=1 AND NOT EXISTS "
            f"(SELECT 1 FROM chat_links l WHERE l.admin_chat_id={chat_column})")


async def get_top_messages(
    db: aiosqlite.Connection, chat_id: int, period: str, limit: int = 500
) -> list[dict]:
    """all_time top — reads from the cumulative counter column."""
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, "
        "s.user_messages_count_all_time AS msg_count, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM user_chat_stats s "
        "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = s.user_tg_id AND v.expires_at > NOW() "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE "
        "AND s.user_messages_count_all_time > 0 "
        "ORDER BY s.user_messages_count_all_time DESC,s.user_tg_id ASC LIMIT ?",
        (chat_id, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_messages_for_dates(
    db: aiosqlite.Connection,
    chat_id: int,
    date_start: str,
    date_end: str,
    limit: int = 500,
) -> list[dict]:
    """Period-based top using daily_user_stats — accurate even for inactive days."""
    async with db.execute(
        "SELECT d.user_id AS user_tg_id, u.user_tg_username, "
        "SUM(d.message_count) AS msg_count, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM daily_user_stats d "
        "LEFT JOIN users u ON d.user_id = u.user_tg_id "
        "LEFT JOIN user_chat_stats s "
        "  ON s.user_tg_id = d.user_id AND s.chat_tg_id = d.chat_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = d.user_id AND v.expires_at > NOW() "
        "WHERE d.chat_id = ? AND d.date >= ? AND d.date <= ? "
        "AND NOT (s.is_left = TRUE) "
        "GROUP BY d.user_id, u.user_tg_username, v.user_id "
        "HAVING SUM(d.message_count) > 0 "
        "ORDER BY msg_count DESC,d.user_id ASC LIMIT ?",
        (chat_id, date_start, date_end, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_messages_global_for_dates(
    db: aiosqlite.Connection, date_start: str, date_end: str, limit: int = 500,
) -> list[dict]:
    """Aggregate one player across every chat for an exact calendar period."""
    async with db.execute(
        "SELECT d.user_id AS user_tg_id,u.user_tg_username,SUM(d.message_count) AS msg_count,"
        "(v.user_id IS NOT NULL) AS is_vip FROM daily_user_stats d "
        "LEFT JOIN users u ON u.user_tg_id=d.user_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id=d.user_id AND v.expires_at>NOW() "
        "WHERE d.date>=? AND d.date<=? "
        "GROUP BY d.user_id,u.user_tg_username,v.user_id HAVING SUM(d.message_count)>0 "
        "ORDER BY msg_count DESC,d.user_id ASC LIMIT ?",
        (date_start, date_end, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_messages_global_all_time(
    db: aiosqlite.Connection, limit: int = 500,
) -> list[dict]:
    async with db.execute(
        "SELECT s.user_tg_id,u.user_tg_username,SUM(s.user_messages_count_all_time) AS msg_count,"
        "(v.user_id IS NOT NULL) AS is_vip FROM user_chat_stats s "
        "LEFT JOIN users u ON u.user_tg_id=s.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id=s.user_tg_id AND v.expires_at>NOW() "
        "GROUP BY s.user_tg_id,u.user_tg_username,v.user_id "
        "HAVING SUM(s.user_messages_count_all_time)>0 "
        "ORDER BY msg_count DESC,s.user_tg_id ASC LIMIT ?",
        (limit,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_chats_for_dates(
    db: aiosqlite.Connection, date_start: str, date_end: str, limit: int = 500,
) -> list[dict]:
    async with db.execute(
        "SELECT d.chat_id,COALESCE(NULLIF(MAX(c.chat_title),''),'Чат') AS chat_title,"
        "SUM(d.message_count) AS msg_count,COUNT(DISTINCT d.user_id) AS active_users "
        "FROM daily_user_stats d LEFT JOIN chat_settings c ON c.chat_id=d.chat_id "
        f"WHERE d.date>=? AND d.date<=? AND {_ranked_chat('d.chat_id')} "
        "GROUP BY d.chat_id HAVING SUM(d.message_count)>0 "
        "ORDER BY msg_count DESC,d.chat_id ASC LIMIT ?",
        (date_start, date_end, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_top_chats_all_time(
    db: aiosqlite.Connection, limit: int = 500,
) -> list[dict]:
    async with db.execute(
        "SELECT s.chat_tg_id AS chat_id,COALESCE(NULLIF(MAX(c.chat_title),''),'Чат') AS chat_title,"
        "SUM(s.user_messages_count_all_time) AS msg_count,"
        "COUNT(DISTINCT s.user_tg_id) FILTER (WHERE s.user_messages_count_all_time>0) AS active_users "
        "FROM user_chat_stats s LEFT JOIN chat_settings c ON c.chat_id=s.chat_tg_id "
        f"WHERE {_ranked_chat('s.chat_tg_id')} "
        "GROUP BY s.chat_tg_id HAVING SUM(s.user_messages_count_all_time)>0 "
        "ORDER BY msg_count DESC,s.chat_tg_id ASC LIMIT ?",
        (limit,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def chat_top_page(db, date_start: str, date_end: str, *, page: int, page_size: int) -> dict:
    totals = ("SELECT d.chat_id,COALESCE(NULLIF(MAX(c.chat_title),''),'Чат') AS chat_title,SUM(d.message_count) AS msg_count "
              "FROM daily_user_stats d LEFT JOIN chat_settings c ON c.chat_id=d.chat_id "
              f"WHERE d.date>=? AND d.date<=? AND {_ranked_chat('d.chat_id')} "
              "GROUP BY d.chat_id HAVING SUM(d.message_count)>0")
    async with db.execute("SELECT COUNT(*) FROM ("+totals+") ranked", (date_start,date_end)) as cursor:
        total = int((await cursor.fetchone())[0])
    pages = max(1,(total+page_size-1)//page_size)
    page = max(0,min(page,pages-1))
    async with db.execute(totals+" ORDER BY msg_count DESC,d.chat_id ASC LIMIT ? OFFSET ?",
                          (date_start,date_end,page_size,page*page_size)) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    return {"items":rows,"page":page,"pages":pages,"total":total}


async def get_message_top_position(
    db: aiosqlite.Connection,
    *,
    scope: str,
    entity_id: int,
    chat_id: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    excluded_user_id: int | None = None,
) -> dict | None:
    """Return an exact deterministic position without a top-N cutoff."""
    if (date_start is None) != (date_end is None):
        raise ValueError("both period boundaries are required")
    period = date_start is not None
    excluded = int(excluded_user_id or 0)
    if scope == "local":
        if chat_id is None:
            raise ValueError("chat_id is required for local position")
        if period:
            totals_sql = (
                "SELECT d.user_id AS entity_id,SUM(d.message_count) AS msg_count "
                "FROM daily_user_stats d LEFT JOIN user_chat_stats s "
                "ON s.user_tg_id=d.user_id AND s.chat_tg_id=d.chat_id "
                "WHERE d.chat_id=? AND d.date>=? AND d.date<=? "
                "AND NOT (s.is_left=TRUE) AND d.user_id<>? GROUP BY d.user_id"
            )
            params = (chat_id, date_start, date_end, excluded)
        else:
            totals_sql = (
                "SELECT user_tg_id AS entity_id,user_messages_count_all_time AS msg_count "
                "FROM user_chat_stats WHERE chat_tg_id=? AND is_left=FALSE "
                "AND user_messages_count_all_time>0 AND user_tg_id<>?"
            )
            params = (chat_id, excluded)
    elif scope == "global":
        if period:
            totals_sql = (
                "SELECT user_id AS entity_id,SUM(message_count) AS msg_count "
                "FROM daily_user_stats WHERE date>=? AND date<=? AND user_id<>? GROUP BY user_id"
            )
            params = (date_start, date_end, excluded)
        else:
            totals_sql = (
                "SELECT user_tg_id AS entity_id,SUM(user_messages_count_all_time) AS msg_count "
                "FROM user_chat_stats WHERE user_tg_id<>? GROUP BY user_tg_id"
            )
            params = (excluded,)
    elif scope == "chats":
        privacy = _ranked_chat("d.chat_id" if period else "s.chat_tg_id")
        if period:
            totals_sql = (
                "SELECT d.chat_id AS entity_id,SUM(d.message_count) AS msg_count "
                "FROM daily_user_stats d LEFT JOIN chat_settings c ON c.chat_id=d.chat_id "
                f"WHERE d.date>=? AND d.date<=? AND {privacy} GROUP BY d.chat_id"
            )
            params = (date_start, date_end)
        else:
            totals_sql = (
                "SELECT s.chat_tg_id AS entity_id,SUM(s.user_messages_count_all_time) AS msg_count "
                "FROM user_chat_stats s LEFT JOIN chat_settings c ON c.chat_id=s.chat_tg_id "
                f"WHERE {privacy} GROUP BY s.chat_tg_id"
            )
            params = ()
    else:
        raise ValueError("unsupported top scope")
    sql = (
        "WITH totals AS (" + totals_sql + "), ranked AS ("
        "SELECT entity_id,msg_count,ROW_NUMBER() OVER (ORDER BY msg_count DESC,entity_id ASC) AS place,"
        "COUNT(*) OVER () AS total_count FROM totals WHERE msg_count>0) "
        "SELECT entity_id,msg_count,place,total_count FROM ranked WHERE entity_id=?"
    )
    async with db.execute(sql, (*params, int(entity_id))) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


# ── Extended tops (B17) ──────────────────────────────────────────────────────

_MIN_GLOBAL_MSGS = 100  # minimum all_time messages for global tops


async def _local_user_ids(db: aiosqlite.Connection, chat_id: int) -> list[int]:
    async with db.execute(
        "SELECT user_tg_id FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE",
        (chat_id,),
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def _global_user_ids(db: aiosqlite.Connection) -> list[int]:
    async with db.execute(
        "SELECT DISTINCT user_tg_id FROM user_chat_stats "
        f"WHERE user_messages_count_all_time >= {_MIN_GLOBAL_MSGS} AND is_left = FALSE"
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def get_top_mora(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT u.user_tg_id, u.user_tg_username, u.user_balance_mora AS value "
        f"FROM users u WHERE u.user_tg_id IN ({placeholders}) "
        f"ORDER BY u.user_balance_mora DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_diamonds(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT u.user_tg_id, u.user_tg_username, u.user_balance_diamonds AS value "
        f"FROM users u WHERE u.user_tg_id IN ({placeholders}) "
        f"ORDER BY u.user_balance_diamonds DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_pet_levels(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT p.owner_id AS user_tg_id, u.user_tg_username, "
        f"MAX(COALESCE(p.pet_level, 1)) AS value "
        f"FROM pets p LEFT JOIN users u ON p.owner_id = u.user_tg_id "
        f"WHERE p.owner_id IN ({placeholders}) AND COALESCE(p.pet_level, 1) >= 2 "
        f"GROUP BY p.owner_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_achievements(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT a.user_id AS user_tg_id, u.user_tg_username, "
        f"COUNT(*) AS value "
        f"FROM achievements a LEFT JOIN users u ON a.user_id = u.user_tg_id "
        f"WHERE a.user_id IN ({placeholders}) AND a.level > 0 "
        f"GROUP BY a.user_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_messages_global(db: aiosqlite.Connection, limit: int = 10) -> list[dict]:
    # PostgreSQL requires all non-aggregated columns in GROUP BY.
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, "
        "SUM(s.user_messages_count_all_time) AS value, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM user_chat_stats s LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = s.user_tg_id AND v.expires_at > NOW() "
        "WHERE s.is_left = FALSE "
        f"GROUP BY s.user_tg_id, u.user_tg_username, v.user_id "
        f"HAVING SUM(s.user_messages_count_all_time) >= {_MIN_GLOBAL_MSGS} "
        "ORDER BY value DESC LIMIT ?",
        (limit,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_streaks(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT dl.user_id AS user_tg_id, u.user_tg_username, MAX(dl.streak) AS value "
        f"FROM daily_login dl LEFT JOIN users u ON dl.user_id = u.user_tg_id "
        f"WHERE dl.user_id IN ({placeholders}) "
        f"GROUP BY dl.user_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_top_auction_sales(db: aiosqlite.Connection, chat_id: int | None, limit: int = 10) -> list[dict]:
    ids = await _local_user_ids(db, chat_id) if chat_id else await _global_user_ids(db)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT al.seller_id AS user_tg_id, u.user_tg_username, COUNT(*) AS value "
        f"FROM auction_lots al LEFT JOIN users u ON al.seller_id = u.user_tg_id "
        f"WHERE al.seller_id IN ({placeholders}) AND al.status = 'sold' "
        f"GROUP BY al.seller_id ORDER BY value DESC LIMIT ?",
        (*ids, limit),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_inactive_users(db, chat_id: int, seconds: int, page: int, *,
                             excluded_ids: list[int], timezone_seconds: int) -> InactivePage:
    """One snapshot for count, clamped page and members; timestamps are explicitly UTC.

    A join also sets last_message_at's default, so never-speakers use observed
    presence instead. A return resets the silence clock without changing history.
    If counters are missing, positive daily history proves a message. Its day-end
    is a conservative fallback: never declare someone silent before a full period.
    """
    async with db.execute(
        "WITH activity AS ("
        "SELECT s.user_tg_id,s.rejoined_at, "
        "(COALESCE(s.user_messages_count_all_time,0)=0 AND h.last_day IS NULL) AS never_spoke, "
        "CASE WHEN COALESCE(s.user_messages_count_all_time,0)>0 AND s.last_message_at IS NOT NULL "
        "THEN s.last_message_at AT TIME ZONE 'UTC' "
        "ELSE ((h.last_day::date+1)::timestamp AT TIME ZONE 'UTC') "
        "- make_interval(secs => ?::double precision) END AS last_message, "
        "LEAST(s.joined_at AT TIME ZONE 'UTC',s.membership_since) AS first_seen "
        "FROM user_chat_stats s LEFT JOIN LATERAL (SELECT MAX(d.date) AS last_day FROM daily_user_stats d "
        "WHERE d.chat_id=s.chat_tg_id AND d.user_id=s.user_tg_id AND d.message_count>0 "
        "AND (COALESCE(s.user_messages_count_all_time,0)=0 OR s.last_message_at IS NULL)) h ON TRUE "
        "WHERE s.chat_tg_id=? AND NOT COALESCE(s.is_left,FALSE) "
        "AND NOT (s.user_tg_id=ANY(?::bigint[])) AND NOT EXISTS "
        "(SELECT 1 FROM user_chat_stats b WHERE b.user_tg_id=s.user_tg_id AND COALESCE(b.is_bot,FALSE))), "
        "observed AS (SELECT user_tg_id,rejoined_at,last_message,never_spoke, "
        "GREATEST(rejoined_at,CASE WHEN never_spoke THEN first_seen ELSE last_message END) AS silent_since "
        "FROM activity), "
        "candidates AS (SELECT * FROM observed WHERE silent_since<=NOW()-make_interval(secs => ?::double precision)), "
        "counts AS (SELECT COUNT(*)::int AS total, "
        "(SELECT COUNT(*)::int FROM observed WHERE silent_since IS NULL) AS unknown FROM candidates), "
        "meta AS (SELECT total, unknown, GREATEST(1,(total+?-1)/?) AS pages, "
        "LEAST(?::int,GREATEST(0,(total-1)/?)) AS page FROM counts) "
        "SELECT m.total,m.unknown,m.pages,m.page,i.user_tg_id,u.user_tg_username,u.user_tg_name, "
        "FLOOR(EXTRACT(EPOCH FROM NOW()-i.silent_since))::bigint AS seconds,i.never_spoke, "
        "(i.rejoined_at IS NOT NULL AND (i.last_message IS NULL OR i.rejoined_at>i.last_message)) AS rejoined "
        "FROM meta m LEFT JOIN LATERAL (SELECT * FROM candidates ORDER BY silent_since,user_tg_id "
        "LIMIT ? OFFSET m.page*?) i ON TRUE LEFT JOIN users u ON u.user_tg_id=i.user_tg_id "
        "ORDER BY i.silent_since,i.user_tg_id",
        (timezone_seconds, chat_id, excluded_ids, seconds, PAGE_SIZE, PAGE_SIZE,
         page, PAGE_SIZE, PAGE_SIZE, PAGE_SIZE),
    ) as cursor:
        rows = await cursor.fetchall()
    meta = rows[0]
    items = tuple(InactiveMember(int(r[4]), r[5], r[6], int(r[7]), bool(r[8]), bool(r[9]))
                  for r in rows if r[4] is not None)
    return InactivePage(items, int(meta[0]), int(meta[1]), int(meta[3]), int(meta[2]))
