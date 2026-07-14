"""
infrastructure/repositories/global_permissions.py
Оверрайды прав глобальных рангов (БЛОК 21.2): реестр прав живёт в
core/admin_permissions.py, здесь — только отклонения от дефолтов + список штата.
"""


async def ensure_table(db) -> None:
    """Веб-процесс стартует раньше бота (см. FastAPI/main.py lifespan) —
    у таблицы свой ensure_table, зарегистрированный в обоих процессах."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS global_rank_permissions (
            rank        SMALLINT NOT NULL,
            perm_key    TEXT NOT NULL,
            allowed     BOOLEAN NOT NULL,
            updated_at  TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (rank, perm_key)
        )
    """)


async def get_overrides(db, rank: int) -> dict[str, bool]:
    async with db.execute(
        "SELECT perm_key, allowed FROM global_rank_permissions WHERE rank = ?",
        (rank,),
    ) as c:
        return {r["perm_key"]: bool(r["allowed"]) for r in await c.fetchall()}


async def get_all_overrides(db) -> dict[int, dict[str, bool]]:
    async with db.execute(
        "SELECT rank, perm_key, allowed FROM global_rank_permissions", ()
    ) as c:
        out: dict[int, dict[str, bool]] = {}
        for r in await c.fetchall():
            out.setdefault(r["rank"], {})[r["perm_key"]] = bool(r["allowed"])
        return out


async def set_override(db, rank: int, perm_key: str, allowed: bool) -> None:
    await db.execute(
        "INSERT INTO global_rank_permissions (rank, perm_key, allowed) VALUES (?, ?, ?) "
        "ON CONFLICT (rank, perm_key) DO UPDATE SET allowed = EXCLUDED.allowed, updated_at = NOW()",
        (rank, perm_key, allowed),
    )
    await db.commit()


async def clear_override(db, rank: int, perm_key: str) -> None:
    """Удалить оверрайд — право возвращается к дефолту реестра."""
    await db.execute(
        "DELETE FROM global_rank_permissions WHERE rank = ? AND perm_key = ?",
        (rank, perm_key),
    )
    await db.commit()


async def list_staff(db) -> list[dict]:
    """Штат: все с global_rank >= 1 + активность за 30 дней (санкции выданы /
    апелляции решены). Разработчик (3) включён — он видит и себя."""
    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.global_rank,0) AS global_rank, "
        "(SELECT COUNT(*) FROM global_sanctions gs WHERE gs.issued_by = u.user_tg_id "
        "   AND gs.created_at > NOW() - INTERVAL '30 days') AS sanctions_30d, "
        "(SELECT COUNT(*) FROM sanction_appeals sa WHERE sa.resolved_by = u.user_tg_id "
        "   AND sa.resolved_at > NOW() - INTERVAL '30 days') AS appeals_30d, "
        "(SELECT MAX(gs2.created_at) FROM global_sanctions gs2 WHERE gs2.issued_by = u.user_tg_id) "
        "   AS last_sanction_at "
        "FROM users u WHERE COALESCE(u.global_rank,0) >= 1 "
        "ORDER BY u.global_rank DESC, u.user_tg_username",
        (),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        r["last_sanction_at"] = str(r["last_sanction_at"]) if r.get("last_sanction_at") else None
    return rows
