"""
infrastructure/repositories/web_notifications.py
Отложенные веб-уведомления (Welcome Back, БЛОК 3.3).

Когда фоновое событие (завершение похода) случается, пока игрок офлайн, его чек
сохраняется здесь и показывается при следующем входе на сайт. payload — JSON того
же события, что уходит по WebSocket (FastAPI.notifications.notify).
"""
import json


async def ensure_table(db) -> None:
    """Создать таблицу, если её ещё нет (веб-процесс может стартовать раньше бота,
    а init_db гоняется только в процессе бота — см. FastAPI/main.py lifespan)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS web_notifications (
            id          SERIAL PRIMARY KEY,
            user_id     BIGINT,
            payload     TEXT,
            seen        INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)


async def add(db, user_id: int, payload: dict) -> None:
    """Сохранить отложенное уведомление (no commit — вызывающий коммитит)."""
    await db.execute(
        "INSERT INTO web_notifications (user_id, payload) VALUES (?, ?)",
        (user_id, json.dumps(payload, ensure_ascii=False)),
    )


async def get_unseen(db, user_id: int, limit: int = 20) -> list[dict]:
    """Непросмотренные уведомления игрока, старые первыми."""
    async with db.execute(
        "SELECT id, payload FROM web_notifications "
        "WHERE user_id = ? AND seen = 0 ORDER BY id ASC LIMIT ?",
        (user_id, limit),
    ) as c:
        rows = await c.fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r[1])
        except Exception:
            payload = {}
        out.append({"id": r[0], "payload": payload})
    return out


async def mark_seen(db, user_id: int, ids: list[int]) -> None:
    """Пометить указанные уведомления просмотренными (only own rows)."""
    ids = [int(i) for i in (ids or [])]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    await db.execute(
        f"UPDATE web_notifications SET seen = 1 "
        f"WHERE user_id = ? AND id IN ({placeholders})",
        (user_id, *ids),
    )
