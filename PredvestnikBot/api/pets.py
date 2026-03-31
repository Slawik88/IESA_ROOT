"""
api/pets.py — pet operations (walk, feed).

All functions are async; the mini app wraps them with async_to_sync.
"""


async def walk_pet(uid: int, chat_id: int) -> dict:
    """Start pet walk.

    Thin wrapper around database.db.start_pet_walk_full.
    Returns the same dict: {ok, error?, fatigue, fatigue_reduced, pet_name,
    pet_type, walk_mins, reward, mins_left}.
    """
    from database.db import start_pet_walk_full

    return await start_pet_walk_full(uid, chat_id)


async def feed_pet(
    uid: int,
    chat_id: int,
    food_key: str,
    wallet_type: str = "personal",
) -> dict:
    """Feed pet with a food item, deducting cost from personal mora or
    the user's own family wallet entry.

    Raises ValueError with a Russian message on any error.
    Returns {ok, fatigue, reduced, balance, pet_emoji, pet_name, food_name}.
    balance is always the personal mora balance after the operation.
    """
    from database.db import (
        get_pet, get_mora,
        get_family_wallet, add_to_family_wallet, get_marriage,
        reduce_pet_fatigue,
    )
    from shared_prices import FOOD_ITEMS

    food = FOOD_ITEMS.get(food_key)
    if not food:
        raise ValueError(f"Неизвестная еда: {food_key}")

    pet = await get_pet(uid, chat_id)
    if not pet:
        raise ValueError("У тебя нет питомца")

    ptype = pet["pet_type"]
    pname = pet.get("name") or "Питомец"
    fatigue = pet.get("fatigue") or 0

    if wallet_type == "family":
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        fam_bal = await get_family_wallet(chat_id, uid)
        if fam_bal < food["price"]:
            raise ValueError(f"Недостаточно в семейном ({fam_bal}/{food['price']})")
        await add_to_family_wallet(chat_id, uid, -food["price"])
        # Return personal mora balance
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    else:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        if bal < food["price"]:
            raise ValueError(f"Недостаточно Моры ({bal}/{food['price']})")
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                (food["price"], uid, food["price"]),
            )
            if cursor.rowcount == 0:
                raise ValueError("Не удалось списать Мору")
            await db.commit()
            async with db.execute(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                (uid,),
            ) as c:
                row = await c.fetchone()
            new_bal = row[0] if row else 0

    await reduce_pet_fatigue(uid, chat_id, food["fatigue"])
    new_fatigue = max(0, fatigue - food["fatigue"])

    emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
    return {
        "ok":        True,
        "fatigue":   new_fatigue,
        "reduced":   food["fatigue"],
        "balance":   new_bal,
        "pet_emoji": emoji,
        "pet_name":  pname,
        "food_name": food["name"],
    }
