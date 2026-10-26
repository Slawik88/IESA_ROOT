"""Bounded chat discovery by membership and ownership, independent of display names."""
from core.chat_rank_policy import ACTION_BY_KEY


async def listing(db, *, user_id: int, offset: int = 0, purge_only: bool = False, developer: bool = False) -> dict:
    scope = "(COALESCE(c.owner_override,c.owner_id)=? OR (s.user_tg_id IS NOT NULL AND NOT COALESCE(s.is_left,FALSE)))"
    params = [user_id, user_id]
    if purge_only:
        scope += " AND c.bot_left_at IS NULL AND (? OR COALESCE(c.owner_override,c.owner_id)=? OR COALESCE(s.chat_rank,0)>=COALESCE(r.min_rank,?))"
        params.extend((developer, user_id, ACTION_BY_KEY["purge"].default))
    source = (" FROM chat_settings c LEFT JOIN user_chat_stats s ON s.chat_tg_id=c.chat_id AND s.user_tg_id=? "
              "LEFT JOIN chat_rank_rights r ON r.chat_id=c.chat_id AND r.action='purge' WHERE c.chat_id<0 AND " + scope)
    async with db.execute("SELECT COUNT(*)" + source, tuple(params)) as cursor:
        total = int((await cursor.fetchone())[0])
    limit = 50
    offset = min(max(0, offset), max(0, (total-1)//limit)*limit)
    async with db.execute(
        "SELECT c.chat_id,c.chat_title,COALESCE(c.owner_override,c.owner_id)=? AS owned,COALESCE(s.chat_rank,0) AS rank,"
        "c.is_purging,c.bot_left_at,"
        "(SELECT COUNT(*) FROM user_chat_stats m WHERE m.chat_tg_id=c.chat_id AND NOT COALESCE(m.is_left,FALSE)) AS members"
        + source + " ORDER BY owned DESC NULLS LAST,rank DESC,c.chat_title,c.chat_id LIMIT ? OFFSET ?",
        (user_id, *params, limit, offset)) as cursor:
        rows = await cursor.fetchall()
    return {"items": [{"id": int(r[0]), "title": r[1] or f"Чат {r[0]}", "owned": bool(r[2]), "rank": int(r[3]),
                       "purging": bool(r[4]), "bot_left": r[5] is not None, "members": int(r[6])} for r in rows],
            "total": total, "offset": offset, "next_offset": offset+limit if offset+limit<total else None}
