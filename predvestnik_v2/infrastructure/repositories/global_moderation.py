# infrastructure/repositories/global_moderation.py
# SQL для глобальных санкций (warn/restrict/ban) и апелляций (Implementation Block 6.2).

_ACTIVE_WHERE = "revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())"


async def get_sanction_by_id(db, sanction_id: int) -> dict | None:
    async with db.execute("SELECT * FROM global_sanctions WHERE id = ?", (sanction_id,)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_active_restriction(db, target_type: str, target_id: int) -> dict | None:
    """Активная restrict ИЛИ ban для цели (их не более одной — см. 6.1)."""
    async with db.execute(
        f"SELECT * FROM global_sanctions WHERE target_type = ? AND target_id = ? "
        f"AND sanction_type IN ('restrict','ban') AND {_ACTIVE_WHERE} "
        f"ORDER BY created_at DESC LIMIT 1",
        (target_type, target_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def issue_sanction(db, target_type: str, target_id: int, sanction_type: str, reason: str | None,
                          issued_by: int, expires_at=None) -> int:
    """revoke текущей активной restrict/ban той же цели (если sanction_type
    in ('restrict','ban')), затем INSERT новой. Возвращает id."""
    if sanction_type in ("restrict", "ban"):
        existing = await get_active_restriction(db, target_type, target_id)
        if existing:
            await db.execute(
                "UPDATE global_sanctions SET revoked_at = NOW(), revoked_by = ? WHERE id = ?",
                (issued_by, existing["id"]),
            )

    async with db.execute(
        "INSERT INTO global_sanctions (target_type, target_id, sanction_type, reason, issued_by, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (target_type, target_id, sanction_type, reason, issued_by, expires_at),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row[0] if row else 0


async def revoke_sanction(db, sanction_id: int, revoked_by: int) -> bool:
    async with db.execute(
        "UPDATE global_sanctions SET revoked_at = NOW(), revoked_by = ? "
        "WHERE id = ? AND revoked_at IS NULL RETURNING id",
        (revoked_by, sanction_id),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row is not None


async def list_sanctions(db, target_type: str, target_id: int, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM global_sanctions WHERE target_type = ? AND target_id = ?"
    if active_only:
        sql += f" AND {_ACTIVE_WHERE}"
    sql += " ORDER BY created_at DESC"
    async with db.execute(sql, (target_type, target_id)) as c:
        return [dict(row) for row in await c.fetchall()]


async def list_active(db, sanction_type: str | None = None) -> list[dict]:
    """Для сайта — 'список активных ограничений' (7.x)."""
    sql = f"SELECT * FROM global_sanctions WHERE {_ACTIVE_WHERE}"
    args: tuple = ()
    if sanction_type:
        sql += " AND sanction_type = ?"
        args = (sanction_type,)
    sql += " ORDER BY created_at DESC"
    async with db.execute(sql, args) as c:
        return [dict(row) for row in await c.fetchall()]


async def list_all(db, sanction_type: str | None = None) -> list[dict]:
    """Для сайта — общий журнал (7.1: GET /admin/global/log), включая снятые/истёкшие."""
    sql = "SELECT * FROM global_sanctions"
    args: tuple = ()
    if sanction_type:
        sql += " WHERE sanction_type = ?"
        args = (sanction_type,)
    sql += " ORDER BY created_at DESC"
    async with db.execute(sql, args) as c:
        return [dict(row) for row in await c.fetchall()]


async def get_user_chat_ids(db, user_id: int) -> list[int]:
    """Чаты, где есть этот пользователь — для рассылки уведомлений о санкциях."""
    async with db.execute(
        "SELECT DISTINCT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        return [row[0] for row in await c.fetchall()]


async def create_appeal(db, user_id: int, sanction_id: int, text: str) -> int:
    async with db.execute(
        "INSERT INTO sanction_appeals (user_id, sanction_id, text) VALUES (?, ?, ?) RETURNING id",
        (user_id, sanction_id, text),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row[0] if row else 0


async def get_active_sanction_for_user(db, user_id: int) -> dict | None:
    """Для 'бот апелляция' — есть ли вообще что оспаривать."""
    async with db.execute(
        f"SELECT * FROM global_sanctions WHERE target_type = 'user' AND target_id = ? "
        f"AND {_ACTIVE_WHERE} ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_appeal_by_id(db, appeal_id: int) -> dict | None:
    async with db.execute("SELECT * FROM sanction_appeals WHERE id = ?", (appeal_id,)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def list_appeals(db, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM sanction_appeals"
    args: tuple = ()
    if status:
        sql += " WHERE status = ?"
        args = (status,)
    sql += " ORDER BY created_at DESC"
    async with db.execute(sql, args) as c:
        return [dict(row) for row in await c.fetchall()]


async def resolve_appeal(db, appeal_id: int, status: str, resolved_by: int) -> None:
    await db.execute(
        "UPDATE sanction_appeals SET status = ?, resolved_by = ?, resolved_at = NOW() WHERE id = ?",
        (status, resolved_by, appeal_id),
    )
    await db.commit()
