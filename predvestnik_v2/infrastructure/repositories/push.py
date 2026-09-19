"""
infrastructure/repositories/push.py — очередь «Умного Пульса».

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
            lease_token TEXT NULL,
            lease_expires_at TIMESTAMPTZ NULL,
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            delivered_at TIMESTAMPTZ NULL,
            permanent_failure TEXT NULL,
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
    for column, definition in (
        ("lease_token", "TEXT NULL"), ("lease_expires_at", "TIMESTAMPTZ NULL"),
        ("delivery_attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("delivered_at", "TIMESTAMPTZ NULL"), ("permanent_failure", "TEXT NULL"),
    ):
        await db.execute(f"ALTER TABLE push_queue ADD COLUMN IF NOT EXISTS {column} {definition}")
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
        "WHERE q.sent = FALSE AND (q.lease_expires_at IS NULL OR q.lease_expires_at<NOW()) "
        "AND (u.last_push_at IS NULL "
        "OR u.last_push_at <= NOW() - INTERVAL '1 second' * ?)",
        (min_interval_sec,),
    ) as c:
        return [r[0] for r in await c.fetchall()]


async def pending_for_user(db, user_id: int) -> list[dict]:
    """Несент-события игрока, по убыванию приоритета (свежие раньше при равном).
    age_sec — возраст события (для TTL-фильтра протухших в smart_pulse_task)."""
    async with db.execute(
        "SELECT id, category, priority, payload_json, "
        "CAST(EXTRACT(EPOCH FROM (NOW() - created_at)) AS BIGINT) AS age_sec "
        "FROM push_queue "
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


async def lease_event(db, *, event_id: int, user_id: int, token: str) -> bool:
    """Atomically claim exactly one event before attempting its Telegram DM."""
    async with db.execute(
        "UPDATE push_queue SET lease_token=?,lease_expires_at=NOW()+INTERVAL '10 minutes',"
        "delivery_attempts=delivery_attempts+1 WHERE id=? AND user_id=? AND sent=FALSE "
        "AND (lease_expires_at IS NULL OR lease_expires_at<NOW()) RETURNING id",
        (str(token), int(event_id), int(user_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def mark_delivery_succeeded(db, *, event_id: int, user_id: int, token: str) -> bool:
    """Complete the leased event only after Telegram accepted the DM."""
    async with db.connection.transaction():
        async with db.execute(
            "UPDATE push_queue SET sent=TRUE,delivered_at=NOW(),lease_token=NULL,lease_expires_at=NULL "
            "WHERE id=? AND user_id=? AND sent=FALSE AND lease_token=? RETURNING id",
            (int(event_id), int(user_id), str(token)),
        ) as cursor:
            delivered = bool(await cursor.fetchone())
        if not delivered:
            return False
        await db.execute(
            "UPDATE push_queue SET sent=TRUE,lease_token=NULL,lease_expires_at=NULL "
            "WHERE user_id=? AND sent=FALSE AND id<>?", (int(user_id), int(event_id)),
        )
        await db.execute("UPDATE users SET last_push_at=NOW() WHERE user_tg_id=?", (int(user_id),))
        return True


async def release_transient_failure(db, *, event_id: int, user_id: int, token: str) -> bool:
    async with db.execute(
        "UPDATE push_queue SET lease_token=NULL,lease_expires_at=NULL WHERE id=? AND user_id=? "
        "AND sent=FALSE AND lease_token=? RETURNING id",
        (int(event_id), int(user_id), str(token)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def mark_permanent_failure(db, *, user_id: int, token: str, reason: str) -> int:
    """Stop retrying a user who cannot receive DMs; preserve audit evidence."""
    async with db.execute(
        "UPDATE push_queue SET sent=TRUE,permanent_failure=?,lease_token=NULL,lease_expires_at=NULL "
        "WHERE user_id=? AND sent=FALSE AND EXISTS (SELECT 1 FROM push_queue leased "
        "WHERE leased.user_id=? AND leased.sent=FALSE AND leased.lease_token=?) RETURNING id",
        (str(reason)[:200], int(user_id), int(user_id), str(token)),
    ) as cursor:
        return len(await cursor.fetchall())


async def discard_unavailable(db, user_id: int) -> None:
    """Discard opted-out/expired events without pretending a DM was sent."""
    await db.execute(
        "UPDATE push_queue SET sent = TRUE WHERE user_id = ? AND sent = FALSE",
        (user_id,),
    )
