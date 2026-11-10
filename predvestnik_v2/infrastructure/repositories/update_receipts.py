"""Short-lived Telegram delivery receipts. No chat or message contents are stored."""


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS telegram_update_receipts (
            bot_id BIGINT NOT NULL,
            update_id BIGINT NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (bot_id, update_id)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS telegram_update_receipts_received_at_idx
        ON telegram_update_receipts (received_at)
    """)


async def seen(db, bot_id: int, update_id: int) -> bool:
    return bool(await db.connection.fetchval(
        "SELECT 1 FROM telegram_update_receipts WHERE bot_id = $1 AND update_id = $2", bot_id, update_id,
    ))


async def claim(db, bot_id: int, update_id: int) -> bool:
    return bool(await db.connection.fetchval(
        "INSERT INTO telegram_update_receipts (bot_id, update_id) VALUES ($1, $2) "
        "ON CONFLICT DO NOTHING RETURNING 1", bot_id, update_id,
    ))


async def cleanup(db) -> None:
    # Telegram retains pending updates for up to 24 hours and can reset IDs after a week of inactivity.
    await db.execute("DELETE FROM telegram_update_receipts WHERE received_at < NOW() - INTERVAL '3 days'")
