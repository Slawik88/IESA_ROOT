"""
infrastructure/repositories/admin_log.py
Журнал действий разработчика (БЛОК 4.2): выдача/изъятие валюты и предметов с
причиной и балансом «до/после». Источник правды для вкладки «Журнал» дев-консоли.
"""


async def ensure_table(db) -> None:
    """Создать таблицу, если её нет (веб-процесс стартует раньше бота — см.
    FastAPI/main.py lifespan; init_db гоняется только в процессе бота)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_grant_log (
            id          SERIAL PRIMARY KEY,
            admin_id    BIGINT,
            target_id   BIGINT,
            action      TEXT,
            detail      TEXT,
            amount      FLOAT8,
            reason      TEXT,
            before_val  FLOAT8,
            after_val   FLOAT8,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)


async def add(db, admin_id: int, target_id: int, action: str, detail: str,
              amount: float, reason: str, before_val: float, after_val: float) -> None:
    """Записать одно действие. No commit — вызывающий коммитит вместе с самой операцией."""
    await db.execute(
        "INSERT INTO admin_grant_log "
        "(admin_id, target_id, action, detail, amount, reason, before_val, after_val) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (admin_id, target_id, action, detail, amount, (reason or "").strip(),
         before_val, after_val),
    )


async def recent(db, limit: int = 50) -> list[dict]:
    """Последние записи журнала с никами админа и цели."""
    async with db.execute(
        "SELECT l.id, l.admin_id, l.target_id, l.action, l.detail, l.amount, "
        "l.reason, l.before_val, l.after_val, l.created_at, "
        "ua.user_tg_username AS admin_name, ut.user_tg_username AS target_name "
        "FROM admin_grant_log l "
        "LEFT JOIN users ua ON ua.user_tg_id = l.admin_id "
        "LEFT JOIN users ut ON ut.user_tg_id = l.target_id "
        "ORDER BY l.id DESC LIMIT ?",
        (limit,),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        r["created_at"] = str(r["created_at"]) if r.get("created_at") else None
    return rows
