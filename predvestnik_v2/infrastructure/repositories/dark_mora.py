"""
infrastructure/repositories/dark_mora.py
SQL functions for Тёмная Мора (dark mora) currency and cooldowns.
"""
from datetime import datetime, timezone
from infrastructure.pg_adapter import PGAdapter


async def get_dark_mora_balance(db: PGAdapter, user_id: int) -> float:
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.execute(
        "SELECT COALESCE(user_balance_dark_mora, 0) FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return float(row[0]) if row else 0.0


async def add_dark_mora(db: PGAdapter, user_id: int, amount: float, source: str, note: str | None = None):
    """Add (or deduct if negative) dark mora. Logs to wallet_log."""
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.connection.transaction():
        await db.execute(
            "UPDATE users SET user_balance_dark_mora = GREATEST(0, COALESCE(user_balance_dark_mora,0) + ?) "
            "WHERE user_tg_id = ?",
            (amount, user_id),
        )
        async with db.execute(
            "SELECT COALESCE(user_balance_dark_mora,0), COALESCE(user_balance_mora,0), "
            "COALESCE(user_balance_diamonds,0) FROM users WHERE user_tg_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
        dark_after = float(row[0]) if row else 0.0
        mora_after = float(row[1]) if row else 0.0
        dia_after = float(row[2]) if row else 0.0
        await db.execute(
            """
            INSERT INTO wallet_log
              (user_id, delta_mora, delta_diamonds, delta_dark_mora,
               balance_mora_after, balance_diamonds_after, balance_dark_mora_after,
               source, note)
            VALUES (?, 0, 0, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, amount, mora_after, dia_after, dark_after, source, note),
        )


async def spend_dark_mora(db: PGAdapter, user_id: int, amount: float, source: str, note: str | None = None) -> tuple[bool, str]:
    """Deduct dark mora atomically. Returns (True, '') or (False, error)."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT COALESCE(user_balance_dark_mora,0), COALESCE(user_balance_mora,0), "
                "COALESCE(user_balance_diamonds,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            dark_bal = float(row[0]) if row else 0.0
            mora_bal = float(row[1]) if row else 0.0
            dia_bal = float(row[2]) if row else 0.0
            if dark_bal < amount:
                raise ValueError(f"Недостаточно Тёмной Моры ({dark_bal:.0f} < {amount:.0f}).")
            dark_after = dark_bal - amount
            await db.execute(
                "UPDATE users SET user_balance_dark_mora = ? WHERE user_tg_id = ?",
                (dark_after, user_id),
            )
            await db.execute(
                """
                INSERT INTO wallet_log
                  (user_id, delta_mora, delta_diamonds, delta_dark_mora,
                   balance_mora_after, balance_diamonds_after, balance_dark_mora_after,
                   source, note)
                VALUES (?, 0, 0, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, -amount, mora_bal, dia_bal, dark_after, source, note),
            )
        return True, ""
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Ошибка: {e}"


async def get_cooldown(db: PGAdapter, user_id: int, action: str) -> datetime | None:
    """Returns when the cooldown expires, or None if no cooldown."""
    async with db.execute(
        "SELECT available_from FROM dark_mora_cooldowns WHERE user_id = ? AND action = ?",
        (user_id, action),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    val = row[0]
    if isinstance(val, str):
        val = datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val


async def set_cooldown(db: PGAdapter, user_id: int, action: str, available_from: datetime):
    await db.execute(
        "INSERT INTO dark_mora_cooldowns (user_id, action, available_from) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, action) DO UPDATE SET available_from = EXCLUDED.available_from",
        (user_id, action, available_from.strftime("%Y-%m-%d %H:%M:%S")),
    )
