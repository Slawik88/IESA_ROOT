"""
api/user.py — leaderboard operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_leaderboard(
    chat_id: int,
    lb_type: str = "xp",
    uid: int | None = None,
    limit: int = 20,
) -> dict:
    """Return leaderboard for a chat.

    lb_type: 'xp' | 'messages' | 'boss' | 'mora'

    If uid is provided and the user is not in the top entries, adds a
    user_rank key with {rank, score}.

    Returns {type, entries, uid, user_rank?}.
    entries is a list of {rank, user_id, name, score}.
    """
    from database.db import (
        get_leaderboard_xp,
        get_leaderboard_messages,
        get_boss_leaderboard,
    )

    if lb_type == "solo_boss":
        # MED-004: Solo boss leaderboard — max boss level completed per user in chat
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            async with db.execute(
                """SELECT p.user_id, u.full_name, MAX(p.max_level) AS max_level
                   FROM solo_boss_progress p
                   LEFT JOIN users u ON u.user_id = p.user_id
                   WHERE p.max_level > 0
                   GROUP BY p.user_id, u.full_name
                   ORDER BY max_level DESC LIMIT ?""" if not chat_id else
                """SELECT p.user_id, u.full_name, COALESCE(p.max_level, 0) AS max_level
                   FROM solo_boss_progress p
                   LEFT JOIN users u ON u.user_id = p.user_id
                   WHERE p.chat_id = ? AND p.max_level > 0
                   ORDER BY p.max_level DESC LIMIT ?""",
                (limit,) if not chat_id else (chat_id, limit),
            ) as c:
                rows = await c.fetchall()
        entries = [
            {
                "rank":       i + 1,
                "user_id":    r["user_id"],
                "name":       r["full_name"] or f"user_{r['user_id']}",
                "score":      r["max_level"] or 0,
                "color_name": "",
                "vip":        False,
            }
            for i, r in enumerate(rows)
        ]
        resp: dict = {"type": lb_type, "entries": entries, "uid": uid}
        return resp

    elif lb_type == "messages":
        rows = await get_leaderboard_messages(chat_id, limit=limit)
        entries = [
            {
                "rank":         i + 1,
                "user_id":      r["user_id"],
                "name":         r["full_name"] or f"user_{r['user_id']}",
                "score":        r["message_count"] or 0,
                "color_name":   r.get("color_name") or "",
                "vip":          bool(r.get("vip")),
                "active_theme": r.get("active_theme") or "",
                "level":        r.get("level") or 0,
            }
            for i, r in enumerate(rows)
        ]

    elif lb_type == "boss":
        rows = await get_boss_leaderboard(chat_id, limit=limit)
        entries = [
            {
                "rank":       i + 1,
                "user_id":    r["user_id"],
                "name":       r["full_name"] or f"user_{r['user_id']}",
                "score":      r["total_damage"] or 0,
                "color_name": "",
                "vip":        False,
            }
            for i, r in enumerate(rows)
        ]

    elif lb_type == "mora":
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            async with db.execute(
                """SELECT u.user_id, u.full_name, COALESCE(u.balance,0) AS balance,
                          COALESCE(um.vip,0) AS vip,
                          CASE WHEN si.user_id IS NOT NULL THEN 1 ELSE 0 END AS has_stealth_mode
                   FROM users u
                   LEFT JOIN user_mora um ON um.user_id=u.user_id AND um.chat_id=?
                   LEFT JOIN shop_items si ON si.user_id=u.user_id
                                          AND si.item_type='cosmetic'
                                          AND si.item_value='stealth_mode'
                   WHERE u.balance IS NOT NULL ORDER BY u.balance DESC LIMIT ?""",
                (chat_id, limit),
            ) as c:
                rows = await c.fetchall()
        entries = [
            {
                "rank":       i + 1,
                "user_id":    r["user_id"],
                "name":       r["full_name"] or f"user_{r['user_id']}",
                # Скрываем баланс только если у игрока куплен «Режим тени»
                "score":      None if r["has_stealth_mode"] else (r["balance"] or 0),
                "color_name": "",
                "vip":        bool(r["vip"]),
            }
            for i, r in enumerate(rows)
        ]

    else:  # xp (default)
        rows = await get_leaderboard_xp(chat_id, limit=limit)
        entries = [
            {
                "rank":         i + 1,
                "user_id":      r["user_id"],
                "name":         r["full_name"] or f"user_{r['user_id']}",
                "score":        r["xp"] or 0,
                "color_name":   r.get("color_name") or "",
                "vip":          bool(r.get("vip")),
                "active_theme": r.get("active_theme") or "",
                "level":        r.get("level") or 0,
            }
            for i, r in enumerate(rows)
        ]

    resp: dict = {"type": lb_type, "entries": entries, "uid": uid}

    # Append user rank if they are not in the top
    if uid and lb_type != "boss":
        user_in_top = any(e["user_id"] == uid for e in entries)
        if not user_in_top:
            user_rank_data = await _get_user_rank(uid, chat_id, lb_type)
            if user_rank_data:
                resp["user_rank"] = user_rank_data

    return resp


async def _get_user_rank(uid: int, chat_id: int, lb_type: str) -> dict | None:
    """Return {rank, score} for uid in the given leaderboard type.
    Returns None for boss type (GROUP BY rank is too expensive here).
    """
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        if lb_type == "messages":
            async with db.execute(
                "SELECT COUNT(*)+1 FROM user_stats WHERE chat_id=? AND message_count > "
                "COALESCE((SELECT message_count FROM user_stats "
                "          WHERE user_id=? AND chat_id=?), 0)",
                (chat_id, uid, chat_id),
            ) as c:
                rank_row = await c.fetchone()
            async with db.execute(
                "SELECT COALESCE(message_count, 0) FROM user_stats "
                "WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as c:
                score_row = await c.fetchone()

        elif lb_type == "mora":
            async with db.execute(
                "SELECT COUNT(*)+1 FROM users WHERE balance IS NOT NULL AND balance > "
                "COALESCE((SELECT balance FROM users WHERE user_id=?), 0)",
                (uid,),
            ) as c:
                rank_row = await c.fetchone()
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users "
                "WHERE user_id=?",
                (uid,),
            ) as c:
                score_row = await c.fetchone()

        else:  # xp
            async with db.execute(
                "SELECT COUNT(*)+1 FROM user_stats WHERE chat_id=? AND xp > "
                "COALESCE((SELECT xp FROM user_stats "
                "          WHERE user_id=? AND chat_id=?), 0)",
                (chat_id, uid, chat_id),
            ) as c:
                rank_row = await c.fetchone()
            async with db.execute(
                "SELECT COALESCE(xp, 0) FROM user_stats "
                "WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as c:
                score_row = await c.fetchone()

    if rank_row and score_row:
        return {"rank": rank_row[0], "score": score_row[0]}
    return None
