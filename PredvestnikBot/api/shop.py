"""
api/shop.py — shop catalog and purchase operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_catalog(uid: int, chat_id: int) -> dict:
    """Return full shop catalog with ownership status and current balance.

    Returns {balance, frames, cosmetics, food, potions, has_vip, active_frame}.
    """
    from database.db import get_mora, get_user_owned_frames
    from database.postgres import postgres_connect
    from shared_prices import FRAMES_CATALOG, COSMETICS_CATALOG, FOOD_ITEMS, POTIONS_CATALOG, PET_COLOR_CATALOG

    mora = await get_mora(uid, chat_id)
    active_frame = mora["top_frame"] if mora else None
    has_vip = bool(mora["vip"]) if mora else False
    balance = mora["balance"] if mora else 0

    owned_frames = await get_user_owned_frames(uid, chat_id)

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT item_value FROM shop_items "
            "WHERE user_id=? AND chat_id=? AND item_type='cosmetic'",
            (uid, chat_id),
        ) as c:
            owned_cosmetics = {r[0] for r in await c.fetchall()}

        async with db.execute(
            "SELECT color_name FROM pets WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        ) as c:
            pet_row = await c.fetchone()
        current_color = pet_row[0] if pet_row else None

    frames = [
        {
            "key":    key,
            "emoji":  em,
            "name":   name,
            "price":  price,
            "owned":  key in owned_frames or key == "default",
            "active": key == (active_frame or "default"),
        }
        for key, em, name, price in FRAMES_CATALOG
    ]
    cosmetics = [
        {
            "key":   key,
            "emoji": em,
            "name":  name,
            "price": price,
            "desc":  desc,
            "owned": key in owned_cosmetics,
        }
        for key, em, name, price, desc in COSMETICS_CATALOG
    ]
    pet_colors = [
        {
            "key":    key,
            "label":  label,
            "price":  price,
            "active": current_color == key.replace("pet_color_", ""),
        }
        for key, label, price in PET_COLOR_CATALOG
    ]
    food_list = [
        {
            "key":     k,
            "name":    v["name"],
            "emoji":   v["emoji"],
            "price":   v["price"],
            "fatigue": v["fatigue"],
        }
        for k, v in FOOD_ITEMS.items()
    ]
    potions_list = [
        {
            "key":         k,
            "name":        v["name"],
            "emoji":       v["emoji"],
            "price":       v["price"],
            "buff_type":   v["buff_type"],
            "buff_amount": v["buff_amount"],
            "duration":    v["duration"],
            "desc":        v["desc"],
        }
        for k, v in POTIONS_CATALOG.items()
        if v["price"] > 0
    ]
    return {
        "balance":      balance,
        "frames":       frames,
        "cosmetics":    cosmetics,
        "pet_colors":   pet_colors,
        "current_color":current_color,
        "food":         food_list,
        "potions":      potions_list,
        "has_vip":      has_vip,
        "active_frame": active_frame or "default",
    }


async def buy_item(
    uid: int,
    chat_id: int,
    item_type: str,
    item_key: str,
    wallet_type: str = "personal",
    equip: bool = True,
) -> dict:
    """Purchase a frame, cosmetic, or vip from the shop.

    Raises ValueError with a Russian message on any error.
    Returns {ok, already_owned, equipped, item_type, item_key, price, balance}.
    balance is always the personal mora balance after the operation.
    """
    from database.db import (
        get_mora, has_shop_item, buy_shop_item,
        set_top_frame, set_vip, get_vip, get_family_wallet, add_to_family_wallet,
        get_marriage,
    )
    from shared_prices import FRAMES_CATALOG, COSMETICS_CATALOG, PRICE_VIP

    item_type = item_type.lower()
    item_key = item_key.lower()
    wallet_type = wallet_type.lower() if wallet_type.lower() in ("personal", "family") else "personal"

    # Determine price
    if item_type == "frame":
        frame_map = {f[0]: f for f in FRAMES_CATALOG}
        frame = frame_map.get(item_key)
        if not frame:
            raise ValueError("Неизвестная рамка")
        price = frame[3]
        if price == 0:
            raise ValueError("Рамка по умолчанию бесплатна")
    elif item_type == "cosmetic":
        cosm_map = {c[0]: c for c in COSMETICS_CATALOG}
        cosm = cosm_map.get(item_key)
        if not cosm:
            raise ValueError("Неизвестная косметика")
        price = cosm[3]
    elif item_type == "vip":
        price = PRICE_VIP
        # Check if user already has VIP
        current_vip = await get_vip(uid, chat_id)
        if current_vip:
            raise ValueError("У тебя уже есть VIP статус! 👑")
    elif item_type == "potion":
        from shared_prices import POTIONS_CATALOG
        pot = POTIONS_CATALOG.get(item_key)
        if not pot:
            raise ValueError("Неизвестное зелье")
        price = pot["price"]
        if price == 0:
            raise ValueError("Это зелье можно получить только из гачи")
    elif item_type == "pet_color":
        from shared_prices import PET_COLOR_CATALOG
        color_map = {c[0]: c for c in PET_COLOR_CATALOG}
        color_entry = color_map.get(item_key)
        if not color_entry:
            raise ValueError("Неизвестный цвет питомца")
        price = color_entry[2]
    else:
        raise ValueError("item_type должен быть frame/cosmetic/vip/potion/pet_color")

    # Check ownership (frame/cosmetic only) — equip if already owned
    if item_type in ("frame", "cosmetic"):
        already_owned = await has_shop_item(uid, chat_id, item_type, item_key)
        if already_owned:
            if item_type == "frame" and equip:
                await set_top_frame(uid, chat_id, item_key)
            return {
                "ok":            True,
                "already_owned": True,
                "equipped":      item_type == "frame" and equip,
            }
    if item_type == "pet_color":
        # Cannot buy the same color that is already active
        from database.postgres import postgres_connect as _pg
        async with _pg() as _db:
            async with _db.execute(
                "SELECT color_name FROM pets WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as _c:
                _pet_row = await _c.fetchone()
        if not _pet_row:
            raise ValueError("У тебя нет питомца — цвет применить не к чему")
        color_key = item_key.replace("pet_color_", "")
        if _pet_row[0] == color_key:
            raise ValueError("Этот цвет уже установлен у питомца")

    # Deduct payment
    if wallet_type == "family":
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        partner_id = marriage["partner_id"]
        my_fam     = await get_family_wallet(chat_id, uid)
        partner_fam = await get_family_wallet(chat_id, partner_id)
        total_fam  = my_fam + partner_fam
        if total_fam < price:
            raise ValueError(f"Недостаточно в семейном ({total_fam}/{price})")
        # Deduct from user's slot first, then partner's if needed
        deduct_me      = min(my_fam, price)
        deduct_partner = price - deduct_me
        await add_to_family_wallet(chat_id, uid, -deduct_me)
        if deduct_partner > 0:
            await add_to_family_wallet(chat_id, partner_id, -deduct_partner)
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    else:
        from database.postgres import postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
                (price, uid, chat_id, price),
            )
            if cursor.rowcount == 0:
                mora = await get_mora(uid, chat_id)
                bal = mora["balance"] if mora else 0
                raise ValueError(f"Недостаточно Моры ({bal}/{price})")
            await db.commit()
            async with db.execute(
                "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as c:
                row = await c.fetchone()
            new_bal = row[0] if row else 0

    # Record purchase and apply effects
    # 5% НДС from shop purchases → treasury
    from database.db import add_to_treasury
    shop_tax = max(1, int(price * 0.05))
    await add_to_treasury(chat_id, shop_tax, "shop", uid)

    if item_type in ("frame", "cosmetic"):
        await buy_shop_item(uid, chat_id, item_type, item_key)
        if item_type == "frame" and equip:
            await set_top_frame(uid, chat_id, item_key)
    elif item_type == "vip":
        await set_vip(uid, chat_id, 1)
    elif item_type == "pet_color":
        from database.postgres import postgres_connect as _pg2
        color_key = item_key.replace("pet_color_", "")
        async with _pg2() as _db2:
            await _db2.execute(
                "UPDATE pets SET color_name=? WHERE user_id=? AND chat_id=?",
                (color_key, uid, chat_id),
            )
            await _db2.commit()
    elif item_type == "potion":
        from shared_prices import POTIONS_CATALOG, ITEM_METADATA
        from database.db import add_gacha_item
        pot_data = POTIONS_CATALOG.get(item_key, {})
        meta = ITEM_METADATA.get(item_key, {})
        await add_gacha_item(
            uid, chat_id, item_key, pot_data.get("name", item_key), "common",
            atk=meta.get("atk", 0), def_val=meta.get("def_val", 0),
            hp=meta.get("hp", 0), crit_rate=meta.get("crit_rate", 0.0),
            slot=meta.get("slot"),
        )

    return {
        "ok":            True,
        "already_owned": False,
        "equipped":      item_type == "frame" and equip,
        "item_type":     item_type,
        "item_key":      item_key,
        "price":         price,
        "balance":       new_bal,
    }
