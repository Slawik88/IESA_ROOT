"""
api/shop.py — shop catalog and purchase operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_catalog(uid: int, chat_id: int) -> dict:
    """Return full shop catalog with ownership status and current balance.

    Returns {balance, frames, cosmetics, food, potions, has_vip, active_frame}.
    """
    from database.db import get_mora, get_user_owned_frames, is_user_single
    from database.postgres import postgres_connect
    from shared_prices import FRAMES_CATALOG, COSMETICS_CATALOG, FOOD_ITEMS, POTIONS_CATALOG, PET_COLOR_CATALOG
    from shared_prices import GACHA_SINGLE_PRICE, GACHA_MULTI_PRICE, GACHA_SINGLES_SINGLE, GACHA_SINGLES_MULTI

    mora = await get_mora(uid, chat_id)
    active_frame = mora["top_frame"] if mora else None
    has_vip = bool(mora["vip"]) if mora else False
    balance = mora["balance"] if mora else 0

    # Gacha pricing: VIP and singles both get the cheaper price
    single = await is_user_single(uid, chat_id)
    use_cheap = single or has_vip
    gacha_p1  = GACHA_SINGLES_SINGLE if use_cheap else GACHA_SINGLE_PRICE
    gacha_p10 = GACHA_SINGLES_MULTI  if use_cheap else GACHA_MULTI_PRICE

    owned_frames = await get_user_owned_frames(uid, chat_id)

    async with postgres_connect() as db:
        rows = await db.fetch(
            "SELECT item_value FROM shop_items "
            "WHERE user_id=? AND chat_id=? AND item_type='cosmetic'",
            (uid, chat_id),
        )
        owned_cosmetics = {r["item_value"] for r in rows}

        pet_row = await db.fetchone(
            "SELECT color_name FROM pets_global WHERE user_id=?",
            (uid,),
        )
        current_color = pet_row["color_name"] if pet_row else None

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
        "gacha_p1":     gacha_p1,
        "gacha_p10":    gacha_p10,
        "themes":       await _get_themes_for_catalog(uid, chat_id),
    }


async def _get_themes_for_catalog(uid: int, chat_id: int) -> list:
    """Return all non-default profile themes with ownership status."""
    from config import PROFILE_THEMES
    from database.postgres import postgres_connect
    async with postgres_connect() as db:
        rows = await db.fetch(
            "SELECT theme_key FROM user_themes WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        )
        owned_keys = {r["theme_key"] for r in rows}
        mora_row = await db.fetchone(
            "SELECT active_theme FROM user_mora WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        )
    active = (mora_row["active_theme"] if mora_row else None) or "default"
    return [
        {
            "key":    key,
            "name":   info["name"],
            "source": info.get("source", "shop"),
            "price":  info.get("price", 0),
            "tier":   info.get("tier", "common"),
            "owned":  key in owned_keys,
            "active": key == active,
        }
        for key, info in PROFILE_THEMES.items()
        if key != "default"
    ]


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
        get_marriage, deduct_family_pool,
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
            # Default/free frame — just equip it directly without charging
            await set_top_frame(uid, chat_id, item_key)
            return {"ok": True, "already_owned": True, "equipped": True}
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
    elif item_type == "profile_theme":
        from config import PROFILE_THEMES
        theme_info = PROFILE_THEMES.get(item_key)
        if not theme_info:
            raise ValueError("Неизвестная тема профиля")
        if theme_info.get("source") != "shop":
            raise ValueError("Эта тема доступна только через гачу")
        price = theme_info["price"]
    else:
        raise ValueError("item_type должен быть frame/cosmetic/vip/potion/pet_color/profile_theme")

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
            _pet_row = await _db.fetchone(
                "SELECT color_name FROM pets_global WHERE user_id=?",
                (uid,),
            )
        if not _pet_row:
            raise ValueError("У тебя нет питомца — цвет применить не к чему")
        color_key = item_key.replace("pet_color_", "")
        if _pet_row["color_name"] == color_key:
            raise ValueError("Этот цвет уже установлен у питомца")

    if item_type == "profile_theme":
        # Check if already owned — if so, just activate
        from database.postgres import postgres_connect as _pgt
        async with _pgt() as _dbt:
            _theme_row = await _dbt.fetchone(
                "SELECT 1 FROM user_themes WHERE user_id=? AND chat_id=? AND theme_key=?",
                (uid, chat_id, item_key),
            )
        if _theme_row:
            if equip:
                from database.db import set_active_theme
                await set_active_theme(uid, chat_id, item_key)
            return {"ok": True, "already_owned": True, "equipped": equip}

    # Deduct payment
    if wallet_type == "family":
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        partner_id = marriage["partner_id"]
        await deduct_family_pool(chat_id, uid, partner_id, price)
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    else:
        from database.postgres import postgres_connect
        async with postgres_connect() as db:
            row = await db.fetchone(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                (uid,),
            )
            bal = row["balance"] if row else 0
            if bal < price:
                raise ValueError(f"Недостаточно Моры ({bal}/{price})")
            cursor = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND COALESCE(balance, 0) >= ?",
                (price, uid, price),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Недостаточно Моры")
            row2 = await db.fetchone(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                (uid,),
            )
            new_bal = row2["balance"] if row2 else 0

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
                "UPDATE pets_global SET color_name=? WHERE user_id=?",
                (color_key, uid),
            )
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
    elif item_type == "profile_theme":
        from database.db import add_user_theme, set_active_theme
        await add_user_theme(uid, chat_id, item_key, source="shop")
        if equip:
            await set_active_theme(uid, chat_id, item_key)

    # Log purchase to wallet ledger
    try:
        from api.economy import log_wallet_tx
        if price > 0:
            await log_wallet_tx(uid, chat_id, "expense", price, "shop_buy",
                                f"{item_type}:{item_key}")
    except Exception:
        pass

    return {
        "ok":            True,
        "already_owned": False,
        "equipped":      equip,
        "item_type":     item_type,
        "item_key":      item_key,
        "price":         price,
        "balance":       new_bal,
    }
