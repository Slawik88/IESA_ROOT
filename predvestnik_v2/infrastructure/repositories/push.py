"""
infrastructure/repositories/push.py — очередь «Умного Пульса» (R6, GDD_REBUILD_PLAN.md).

Единый ритм DM-уведомлений: источники кладут события в push_queue, задача
smart_pulse_task (services/scheduler.py) раз в 5 минут выбирает для каждого
игрока САМОЕ приоритетное несент-событие и шлёт ОДИН DM — не чаще, чем раз
в PUSH_MIN_INTERVAL_SEC (2 часа). Остальные события пачки помечаются sent
(«сгорают» — игрок увидит их в web_notifications при заходе на сайт).
"""
import json


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS push_queue (
            id           SERIAL PRIMARY KEY,
            user_id      BIGINT NOT NULL,
            category     TEXT NOT NULL,
            priority     INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            sent         BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_push_queue_pending ON push_queue(user_id, sent)"
    )
    try:
        await db.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_push_at TIMESTAMP DEFAULT NULL"
        )
    except Exception:
        pass
    await db.commit()


async def enqueue(db, user_id: int, category: str, priority: int, payload: dict | None = None) -> None:
    """Положить событие в очередь. Ошибки глотаем — пуш не должен ронять игровую логику."""
    try:
        await db.execute(
            "INSERT INTO push_queue (user_id, category, priority, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (user_id, category, priority, json.dumps(payload or {}, ensure_ascii=False)),
        )
        await db.commit()
    except Exception:
        pass


async def users_ready_for_push(db, min_interval_sec: int) -> list[int]:
    """Игроки с несент-событиями, у которых прошло ≥ min_interval_sec с последнего пуша."""
    async with db.execute(
        "SELECT DISTINCT q.user_id FROM push_queue q "
        "JOIN users u ON u.user_tg_id = q.user_id "
        "WHERE q.sent = FALSE AND (u.last_push_at IS NULL "
        "OR u.last_push_at <= NOW() - INTERVAL '1 second' * ?)",
        (min_interval_sec,),
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def pending_for_user(db, user_id: int) -> list[dict]:
    """Несент-события игрока, по убыванию приоритета (свежие раньше при равном)."""
    async with db.execute(
        "SELECT id, category, priority, payload_json FROM push_queue "
        "WHERE user_id = ? AND sent = FALSE ORDER BY priority DESC, id DESC",
        (user_id,),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload_json"] or "{}")
        except Exception:
            r["payload"] = {}
    return rows


async def mark_all_sent(db, user_id: int) -> None:
    await db.execute(
        "UPDATE push_queue SET sent = TRUE WHERE user_id = ? AND sent = FALSE",
        (user_id,),
    )
    await db.execute(
        "UPDATE users SET last_push_at = NOW() WHERE user_tg_id = ?", (user_id,)
    )
    await db.commit()