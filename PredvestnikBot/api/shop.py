import logging
_log = logging.getLogger(__name__)
"""
api/shop.py — shop catalog and purchase operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_catalog(uid: int, chat_id: int) -> dict:
    """Return full shop catalog with ownership status and current balance.

    Returns {balance, frames, cosmetics, food, potions, has_vip, active_frame}.
    """
    from database.db import get_crystals, get_mora, get_user_owned_frames, is_user_single
    from database.postgres import connect as postgres_connect
    from shared_prices import FRAMES_CATALOG, COSMETICS_CATALOG, FOOD_ITEMS, POTIONS_CATALOG, PET_COLOR_CATALOG
    from shared_prices import (
        GACHA_SINGLE_PRICE, GACHA_MULTI_PRICE, GACHA_SINGLES_SINGLE, GACHA_SINGLES_MULTI,
        PRICE_VIP_CRYSTALS, VIP_DURATION_DAYS,
    )

    mora = await get_mora(uid, chat_id)
    active_frame = mora["top_frame"] if mora else None
    has_vip = bool(mora["vip"]) if mora else False
    balance = mora["balance"] if mora else 0
    crystals = await get_crystals(uid)

    # Gacha pricing: VIP and singles both get the cheaper price
    single = await is_user_single(uid, chat_id)
    use_cheap = single or has_vip
    gacha_p1  = GACHA_SINGLES_SINGLE if use_cheap else GACHA_SINGLE_PRICE
    gacha_p10 = GACHA_SINGLES_MULTI  if use_cheap else GACHA_MULTI_PRICE

    owned_frames = await get_user_owned_frames(uid, chat_id)

    async with postgres_connect() as db:
        rows = await db.fetch(
            "SELECT item_value FROM shop_items "
            "WHERE user_id=? AND item_type='cosmetic'",
            uid,
        )
        owned_cosmetics = {r["item_value"] for r in rows}

        # Pet color ownership
        rows_pc = await db.fetch(
            "SELECT item_value FROM shop_items "
            "WHERE user_id=? AND item_type='pet_color'",
            uid,
        )
        owned_pet_colors = {r["item_value"] for r in rows_pc}

        pet_row = await db.fetchone(
            "SELECT color_name FROM pets_global WHERE user_id=?",
            uid,
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
            "owned":  key in owned_pet_colors or current_color == key.replace("pet_color_", ""),
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
        "crystals":     crystals,
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
        "vip_price_crystals": PRICE_VIP_CRYSTALS,
        "vip_duration_days":  VIP_DURATION_DAYS,
        "themes":       await _get_themes_for_catalog(uid, chat_id),
    }


async def _get_themes_for_catalog(uid: int, chat_id: int) -> list:
    """Return all non-default profile themes with ownership status."""
    from config import PROFILE_THEMES
    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        rows = await db.fetch(
            "SELECT theme_key FROM user_themes WHERE user_id=?",
            uid,
        )
        owned_keys = {r["theme_key"] for r in rows}
        mora_row = await db.fetchone(
            "SELECT active_theme FROM user_mora WHERE user_id=? AND chat_id=?",
            uid, chat_id,
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
        buy_shop_item, deduct_family_pool, get_crystals, get_marriage,
        get_mora, get_vip, has_shop_item, set_top_frame, set_vip, spend_crystals,
    )
    from shared_prices import COSMETICS_CATALOG, FRAMES_CATALOG, PRICE_VIP_CRYSTALS, VIP_DURATION_DAYS

    item_type = item_type.lower()
    item_key = item_key.lower()
    wallet_type = wallet_type.lower() if wallet_type.lower() in ("personal", "family") else "personal"
    new_crystals: int | None = None

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
        price = PRICE_VIP_CRYSTALS
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

    # Block cosmetic/frame/vip purchases in isolated test chats
    from database.db import is_isolated_chat
    if item_type in ("frame", "cosmetic", "vip") and is_isolated_chat(chat_id):
        raise ValueError("В тестовых чатах нельзя покупать косметику, рамки и VIP")

    # Check ownership (frame/cosmetic only) — equip if already owned
    # Check both per-chat and global (chat_id=0) ownership
    if item_type in ("frame", "cosmetic"):
        already_owned = await has_shop_item(uid, chat_id, item_type, item_key)
        if not already_owned:
            already_owned = await has_shop_item(uid, 0, item_type, item_key)
        if already_owned:
            if item_type == "frame" and equip:
                await set_top_frame(uid, chat_id, item_key)
            return {
                "ok":            True,
                "already_owned": True,
                "equipped":      item_type == "frame" and equip,
            }
    if item_type == "pet_color":
        from database.postgres import connect as _pg
        async with _pg() as _db:
            _pet_row = await _db.fetchone(
                "SELECT color_name FROM pets_global WHERE user_id=?",
                uid,
            )
        if not _pet_row:
            raise ValueError("У тебя нет питомца — цвет применить не к чему")
        color_key = item_key.replace("pet_color_", "")
        if _pet_row["color_name"] == color_key:
            raise ValueError("Этот цвет уже установлен у питомца")
        # If already owned — re-apply for free (no payment)
        _already_owned_color = await has_shop_item(uid, 0, "pet_color", item_key)
        if _already_owned_color:
            async with _pg() as _db3:
                await _db3.execute(
                    "UPDATE pets_global SET color_name=? WHERE user_id=?",
                    (color_key, uid),
                )
            return {"ok": True, "already_owned": True, "equipped": True}

    if item_type == "profile_theme":
        # Check if already owned — if so, just activate
        from database.postgres import connect as _pgt
        async with _pgt() as _dbt:
            _theme_row = await _dbt.fetchone(
                "SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=? LIMIT 1",
                uid, item_key,
            )
        if _theme_row:
            if equip:
                from database.db import set_active_theme
                await set_active_theme(uid, chat_id, item_key)
            return {"ok": True, "already_owned": True, "equipped": equip}

    # Deduct payment
    new_family_bal: int | None = None
    _bonus_potion = False
    if item_type == "vip":
        if wallet_type == "family":
            raise ValueError("VIP покупается только за кристаллы")
        if not await spend_crystals(uid, price):
            bal = await get_crystals(uid)
            raise ValueError(f"Недостаточно кристаллов ({bal}/{price})")
        new_crystals = await get_crystals(uid)
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    elif wallet_type == "family":
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        partner_id = marriage["partner_id"]
        new_family_bal = await deduct_family_pool(chat_id, uid, partner_id, price)
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    else:
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            row = await db.fetchone(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                uid,
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
            # pet_color: apply color in the SAME transaction as payment
            if item_type == "pet_color":
                _color_key = item_key.replace("pet_color_", "")
                await db.execute(
                    "UPDATE pets_global SET color_name=? WHERE user_id=?",
                    (_color_key, uid),
                )
            row2 = await db.fetchone(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                uid,
            )
            new_bal = row2["balance"] if row2 else 0

    # Record purchase and apply effects
    # 5% НДС from shop purchases → treasury
    from database.db import add_to_treasury
    if item_type != "vip":
        shop_tax = max(1, int(price * 0.05))
        await add_to_treasury(chat_id, shop_tax, "shop", uid)

    if item_type in ("frame", "cosmetic"):
        await buy_shop_item(uid, chat_id, item_type, item_key)
        # Also track globally so ownership works cross-chat
        if chat_id != 0:
            try:
                await buy_shop_item(uid, 0, item_type, item_key)
            except Exception as _e:
                _log.debug("global shop row duplicate (expected): %s", _e)
        if item_type == "frame" and equip:
            await set_top_frame(uid, chat_id, item_key)
    elif item_type == "vip":
        await set_vip(uid, chat_id, 1, days=VIP_DURATION_DAYS)
    elif item_type == "pet_color":
        from database.postgres import connect as _pg2
        color_key = item_key.replace("pet_color_", "")
        # Color update already happened atomically in the payment block
        # Track ownership globally (chat_id=0) so color persists cross-chat
        await buy_shop_item(uid, 0, "pet_color", item_key)
        if chat_id != 0:
            try:
                await buy_shop_item(uid, chat_id, "pet_color", item_key)
            except Exception as _e:
                _log.debug("%s", _e)
    elif item_type == "potion":
        from shared_prices import POTIONS_CATALOG, ITEM_METADATA
        from database.db import add_gacha_item
        import random as _rnd
        pot_data = POTIONS_CATALOG.get(item_key, {})
        meta = ITEM_METADATA.get(item_key, {})
        await add_gacha_item(
            uid, chat_id, item_key, pot_data.get("name", item_key), "common",
            atk=meta.get("atk", 0), def_val=meta.get("def_val", 0),
            hp=meta.get("hp", 0), crit_rate=meta.get("crit_rate", 0.0),
            slot=meta.get("slot"),
        )
        # Талант: potion_luck — шанс получить бесплатное второе зелье
        try:
            from database.db import get_talent_effect as _gte
            _free_chance = await _gte(uid, "free_potion_chance")
            if _free_chance > 0 and _rnd.random() < _free_chance / 100.0:
                await add_gacha_item(
                    uid, chat_id, item_key, pot_data.get("name", item_key) + " (бонус)",
                    "common", atk=meta.get("atk", 0), def_val=meta.get("def_val", 0),
                    hp=meta.get("hp", 0), crit_rate=meta.get("crit_rate", 0.0),
                    slot=meta.get("slot"),
                )
                _bonus_potion = True
        except Exception as _e:
            _log.debug("potion_luck: %s", _e)
    elif item_type == "profile_theme":
        from database.db import add_user_theme, set_active_theme
        await add_user_theme(uid, chat_id, item_key, source="shop")
        # Store globally for cross-chat ownership
        if chat_id != 0:
            try:
                await add_user_theme(uid, 0, item_key, source="shop")
            except Exception as _e:
                _log.debug("%s", _e)
        if equip:
            await set_active_theme(uid, chat_id, item_key)

    # Log purchase to wallet ledger
    try:
        from api.economy import log_wallet_tx
        if price > 0 and item_type != "vip":
            await log_wallet_tx(uid, chat_id, "expense", price, "shop_buy",
                                f"{item_type}:{item_key}")
    except Exception as _e:
        _log.debug("%s", _e)

    return {
        "ok":              True,
        "already_owned":   False,
        "equipped":        equip,
        "item_type":       item_type,
        "item_key":        item_key,
        "price":           price,
        "balance":         new_bal,
        "crystals_balance": new_crystals,
        "family_balance":  new_family_bal,
        "bonus_potion":    _bonus_potion,
    }
