import aiosqlite


async def get_promocode(db: aiosqlite.Connection, code: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM promocodes WHERE code = ?", (code.upper(),)
    ) as c:
        row = await c.fetchone()
        return dict(row) if row else None


async def has_user_redeemed(db: aiosqlite.Connection, code: str, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM promocode_redemptions WHERE code = ? AND user_id = ?",
        (code.upper(), user_id),
    ) as c:
        return (await c.fetchone()) is not None


async def redeem_promocode(
    db: aiosqlite.Connection, code: str, user_id: int, chat_id: int | None = None
):
    code = code.upper()
    await db.execute(
        "INSERT INTO promocode_redemptions (code, user_id, chat_id) VALUES (?, ?, ?)",
        (code, user_id, chat_id),
    )
    await db.execute(
        "UPDATE promocodes SET activations_count = activations_count + 1 WHERE code = ?",
        (code,),
    )
    await db.commit()


async def create_promocode(
    db: aiosqlite.Connection,
    code: str,
    description: str,
    mora: float,
    diamonds: float,
    dark_mora: float,
    items_json: str,
    max_activations: int,
    valid_from: str | None,
    valid_until: str | None,
    created_by: int,
    allowed_users_json: str = "[]",
    allowed_chats_json: str = "[]",
) -> bool:
    try:
        await db.execute(
            "INSERT INTO promocodes "
            "(code, description, reward_mora, reward_diamonds, reward_dark_mora, "
            "reward_items_json, max_activations, valid_from, valid_until, created_by, "
            "allowed_users_json, allowed_chats_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code.upper(), description, mora, diamonds, dark_mora, items_json,
                max_activations, valid_from, valid_until, created_by,
                allowed_users_json, allowed_chats_json,
            ),
        )
        await db.commit()
        return True
    except Exception:
        return False


async def list_promocodes(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT * FROM promocodes ORDER BY created_at DESC"
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def get_promo_activators(db: aiosqlite.Connection, code: str, limit: int = 20) -> list[dict]:
    """Return list of {user_id, chat_id, redeemed_at} for a given code."""
    async with db.execute(
        "SELECT user_id, chat_id, redeemed_at FROM promocode_redemptions "
        "WHERE code = ? ORDER BY redeemed_at DESC LIMIT ?",
        (code.upper(), limit),
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def deactivate_promocode(db: aiosqlite.Connection, code: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM promocodes WHERE code = ?", (code.upper(),)
    ) as c:
        if not await c.fetchone():
            return False
    await db.execute(
        "UPDATE promocodes SET is_active = 0 WHERE code = ?", (code.upper(),)
    )
    await db.commit()
    return True


async def activate_promocode_record(db: aiosqlite.Connection, code: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM promocodes WHERE code = ?", (code.upper(),)
    ) as c:
        if not await c.fetchone():
            return False
    await db.execute(
        "UPDATE promocodes SET is_active = 1 WHERE code = ?", (code.upper(),)
    )
    await db.commit()
    return True


async def delete_promocode(db: aiosqlite.Connection, code: str) -> bool:
    await db.execute("DELETE FROM promocode_redemptions WHERE code = ?", (code.upper(),))
    async with db.execute(
        "DELETE FROM promocodes WHERE code = ?", (code.upper(),)
    ) as c:
        await db.commit()
        return c.rowcount > 0


async def get_redemption_count(db: aiosqlite.Connection, code: str) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM promocode_redemptions WHERE code = ?", (code.upper(),)
    ) as c:
        row = await c.fetchone()
        return row[0] if row else 0
