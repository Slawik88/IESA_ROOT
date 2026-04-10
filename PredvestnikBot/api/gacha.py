"""
api/gacha.py — unified gacha roll logic.

Called by both the Telegram bot handlers and the mini app views.
All public functions are async; the mini app wraps them with async_to_sync.
"""
import random

from shared_prices import (
    GACHA_SINGLE_PRICE,
    GACHA_MULTI_PRICE,
    GACHA_SINGLES_SINGLE,
    GACHA_SINGLES_MULTI,
    GACHA_PITY_MAX,
    ITEM_METADATA,
)
import logging
_log = logging.getLogger(__name__)

# ── Item pools (identical to handlers/gacha.py) ────────────────────────────────
_JUNK_ITEMS = [
    ("junk_stone",    "🪨 Камень Маслоу",       "Бесполезный хлам — продай кнопкой «Продать мусор»"),
    ("junk_stick",    "🪵 Палка путника",        "Сломанная палка, годится только на продажу"),
    ("junk_dust",     "💨 Пыль забвения",        "Пыль из неизвестного мира — никому не нужна"),
    ("junk_bone",     "🦴 Кость хиличурла",      "Древняя кость. Продай и забудь"),
    ("junk_mushroom", "🍄 Сомнительный гриб",    "Лучше не пробовать. Зато можно продать"),
    ("junk_feather",  "🪶 Перо Штормпиха",       "Перо химеры-штормпиха. Продай за 4 🪙"),
    ("junk_rope",     "🧵 Верёвка странника",    "Оборванная верёвка. Продай за 3 🪙"),
]

_COMMON_ITEMS = [
    ("cmn_sword",    "⚔️ Тупой клинок",        "Экипировка: +15 ATK"),
    ("cmn_bow",      "🏹 Кривой лук",           "Экипировка: +12 ATK"),
    ("cmn_book",     "📕 Потрёпанный дневник",  "Экипировка: +8 ATK, 3% крит"),
    ("cmn_ring",     "💍 Дешёвое кольцо",       "Экипировка: +15 DEF, +30 HP"),
    ("cmn_shield",   "🛡 Ржавый щит",           "Экипировка: +20 DEF"),
    ("str_potion",   "⚔️ Зелье Силы",          "Расходник: +15 ATK на 1 час"),
    ("def_potion",   "🛡️ Зелье Защиты",        "Расходник: +20 DEF на 1 час"),
    ("hp_potion",    "❤️ Зелье Здоровья",      "Расходник: +50 HP на 1.5 часа"),
    ("cmn_quill",    "✒️ Перо ученика",         "Экипировка: +8 ATK, +15 HP, 2% крит"),
    ("cmn_talisman", "🔮 Амулет удачи",         "Экипировка: +5 DEF, 1.5% крит"),    # Instant-grant consumables / coupons (were missing from pool)
    ("cmn_xp_shard",  "✨ Осколок Опыта",            "Мгновенно +25 XP"),
    ("cmn_herb",      "🌿 Трава Сесилии",            "Мгновенно +15 🪙"),
    ("exp_boost_sm",  "🗺️ Ускорение экспедиции S",  "−0 мин от текущей экспедиции"),
    ("quest_reroll",  "🔄 Купон реролла задания",    "Сбросить квест дня на новый"),]

_RARE_ITEMS = [
    ("rare_crown",      "👑 Серебряная корона",       "Экипировка: +25 ATK, +15 DEF, 4% крит"),
    ("rare_catalyst",   "🔮 Магический катализатор",  "Экипировка: +30 ATK, 4% крит"),
    ("rare_cape",       "🧣 Алый плащ",               "Экипировка: +25 DEF, +80 HP"),
    ("rare_gem",        "💎 Сапфир полуночи",          "Экипировка: +20 DEF, 6% крит"),
    ("rare_xp_crystal", "💠 Кристалл Опыта XL",       "Сразу даёт +150 XP"),
    ("rare_amulet",     "📿 Кармин змеи",              "Экипировка: +20 DEF, 8% крит"),
    ("rare_lance",      "⚡ Лазурное копьё",           "Экипировка: +35 ATK, 5% крит"),    # Instant-grant consumables / coupons (were missing from pool)
    ("rare_mora_bag",   "💰 Мешок Моры",                   "Мгновенно +120 🪙"),
    ("rare_mora_chest", "🧧 Красный конверт",               "Мгновенно +250 🪙"),
    ("exp_boost_md",    "🗺️✨ Ускорение экспедиции M",     "−2 часа от текущей экспедиции"),
    ("pet_rename",      "✏️ Купон переименования питомца",  "Переименовать питомца 1 раз"),
    ("frame_warrior",   "⚔️ Рамка «Воин»",                 "Рамка профиля: боевой стиль"),
    ("frame_moon",      "🌙 Рамка «Ночной»",                "Рамка профиля: лунное сияние"),
    ("frame_fire",      "🔥 Рамка «Огненный»",              "Рамка профиля: огненное обрамление"),
    ("frame_star",      "⭐ Рамка «Звёздный»",              "Рамка профиля: звёздный блеск"),
]

_LEGENDARY_ITEMS = [
    ("lego_gnosis",    "✨ Гнозис Балладеера",        "Экипировка: уникальный символ Предвестника в профиле"),
    ("lego_scepter",   "🏛 Скипетр Дендро Архонта",  "Экипировка: могущественный скипетр в профиле"),
    ("lego_pantalone", "🎩 Маска Панталоне",           "Экипировка: таинственная маска дельца в профиле"),
    ("lego_abyss",     "🌀 Корона Бездны",             "Экипировка: корона из глубин Бездны в профиле"),
    ("lego_fatui",     "⚡ Перст Предвестника",        "Экипировка: эксклюзивный знак верности"),
    ("lego_flair_star",  "⭐ Звёздное Сияние",        "Косметика Mini App: золотой ореол рядом с именем"),
    ("lego_flair_void",  "🌌 Мерцание Бездны",        "Косметика Mini App: тёмно-мистический эффект имени"),
    ("lego_flair_flame", "🔥 Пламя Предвестника",     "Косметика Mini App: огненный эффект рядом с именем"),
    ("lego_flair_arch",  "🌸 Благодать Архонта",      "Косметика Mini App: нежный розовый ореол имени"),
    ("str_superior",   "⚔️✨ Зелье Силы Superior",    "Расходник: +30 ATK на 2 часа (редкое!)"),
    ("def_superior",   "🛡️✨ Зелье Защиты Superior",  "Расходник: +40 DEF на 2 часа (редкое!)"),
    ("lego_raiden",    "⚡ Клинок Ей",                "Экипировка: лучший ATK (+80), 12% крит"),
    ("lego_jade",      "🏯 Нефритовое зерцало",       "Экипировка: баланс ATK/DEF/CRIT (+20/+40/15%)"),
    # Instant-grant coupon (was missing from pool)
    ("exp_boost_lg",   "🗺️⚡ Ускорение экспедиции L", "Убирает 50% оставшегося времени"),
    # Gacha-exclusive frames
    ("frame_diamond",  "💎 Рамка «Алмазный»",          "Рамка профиля: элитный алмазный стиль"),
    ("frame_champion", "🏆 Рамка «Чемпион»",            "Рамка профиля: чемпионский кубок"),
    ("frame_sakura",   "🌸 Рамка «Сакура»",             "Рамка профиля: цветение сакуры"),
    ("frame_abyss",    "🌀 Рамка «Бездна»",             "Рамка профиля: тьма бездны"),
    # Gacha-exclusive themes
    ("theme_royal",    "👑 Тема «Королевский»",          "Тема профиля: королевская роскошь"),
    ("theme_abyss",    "🌀 Тема «Бездна»",               "Тема профиля: мрачная бездна"),
    ("theme_sakura",   "🌸 Тема «Сакура»",               "Тема профиля: нежная сакура"),
    ("theme_neon",     "💜 Тема «Неоновый»",             "Тема профиля: неоновое свечение"),
    ("theme_fuji",     "🗻 Тема «Гора Фудзи»",           "Тема профиля: величественная вершина"),
    ("theme_crane",    "🏯 Тема «Журавль»",              "Тема профиля: изящный журавль"),
]


def roll_one(pity: int, pity_max: int = GACHA_PITY_MAX) -> tuple[str, str, str, str]:
    """Single gacha roll. Returns (item_key, item_name, rarity, description)."""
    if pity >= pity_max - 1:
        key, name, desc = random.choice(_LEGENDARY_ITEMS)
        return key, name, "legendary", desc

    r = random.random()
    if r < 0.02:   # 2% legendary (was 3%)
        key, name, desc = random.choice(_LEGENDARY_ITEMS)
        return key, name, "legendary", desc
    elif r < 0.08:  # 6% rare (was 7%)
        key, name, desc = random.choice(_RARE_ITEMS)
        return key, name, "rare", desc
    elif r < 0.25:  # 17% common (was 20%)
        key, name, desc = random.choice(_COMMON_ITEMS)
        return key, name, "common", desc
    else:           # 75% junk (was 70%)
        key, name, desc = random.choice(_JUNK_ITEMS)
        return key, name, "junk", desc


async def gacha_roll(uid: int, chat_id: int, count: int,
                     wallet_type: str = "personal") -> dict:
    """
    Perform gacha roll(s): deduct cost, save items with stats, tick quest.

    Returns:
        {ok, items[{key,name,rarity,desc}], new_balance, pity, spent,
         is_single, quest_done, quest_xp, quest_mora}

    Raises ValueError with a Russian message on error.
    """
    from database.db import (
        add_gacha_item, add_mora, add_to_treasury,
        get_gacha_pity, get_mora, get_vip, is_user_single,
        get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat,
    )
    from utils.helpers import bot_today

    if count not in (1, 10, 50):
        raise ValueError("count must be 1, 10, or 50")

    single = await is_user_single(uid, chat_id)
    is_vip = bool(await get_vip(uid, chat_id))
    # VIP users get the cheaper singles pricing even if married
    use_cheap_price = single or is_vip
    if count == 50:
        price = (GACHA_SINGLES_MULTI * 5) if use_cheap_price else (GACHA_MULTI_PRICE * 5)
    elif count == 10:
        price = GACHA_SINGLES_MULTI if use_cheap_price else GACHA_MULTI_PRICE
    else:
        price = GACHA_SINGLES_SINGLE if use_cheap_price else GACHA_SINGLE_PRICE

    # ── Deduct cost ────────────────────────────────────────────────────────────
    new_family_bal: int | None = None
    if wallet_type == "family":
        if single:
            raise ValueError("Нет семейного кошелька")
        from database.db import get_marriage as _get_marriage, deduct_family_pool as _deduct_fam
        marriage = await _get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        partner_id = marriage["partner_id"]
        new_family_bal = await _deduct_fam(chat_id, uid, partner_id, price)
        mora_row = await get_mora(uid, chat_id)
        new_bal  = mora_row["balance"] if mora_row else 0
    else:
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                (price, uid, price),
            )
            if cursor.rowcount == 0:
                mora_row = await get_mora(uid, chat_id)
                bal = mora_row["balance"] if mora_row else 0
                raise ValueError(f"Недостаточно Моры ({bal}/{price} 🪙)")
            await db.commit()
            async with db.execute(
                "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
                (uid,),
            ) as c:
                row = await c.fetchone()
            new_bal = row[0] if row else 0

    # ── Roll ───────────────────────────────────────────────────────────────────
    # 5% НДС from gacha purchases → treasury
    gacha_tax = max(1, int(price * 0.05))
    await add_to_treasury(chat_id, gacha_tax, "gacha", uid)

    # Block 3: Check guarantee scroll for ×10 pulls
    use_guarantee = False
    if count == 10:
        from database.db import get_guarantee_scrolls, use_guarantee_scroll
        guarantee_scrolls = await get_guarantee_scrolls(uid)
        if guarantee_scrolls > 0:
            use_guarantee = True
            await use_guarantee_scroll(uid)

    pity    = await get_gacha_pity(uid, chat_id)
    # Talent: pity_memory reduces the guaranteed legendary threshold
    pity_max = GACHA_PITY_MAX
    try:
        from database.db import get_talent_effect as _gte
        _pity_red = await _gte(uid, "gacha_pity_reduction")
        if _pity_red > 0:
            pity_max = max(10, GACHA_PITY_MAX - _pity_red)
    except Exception as _e:
        _log.debug("%s", _e)
    results = []
    guaranteed_rare_used = False
    for i in range(count):
        # Block 3: Guarantee rare+ on ×10 if scroll used and no rare+ yet
        if (use_guarantee and count == 10 and i == count - 1 and 
            not guaranteed_rare_used and 
            not any(r.get("rarity") in ["rare", "legendary"] for r in results)):
            # Force at least rare on last roll
            key, name, desc = random.choice(_RARE_ITEMS)
            rarity = "rare"
            guaranteed_rare_used = True
        else:
            key, name, rarity, desc = roll_one(pity, pity_max)
            if rarity in ["rare", "legendary"]:
                guaranteed_rare_used = True
        
        meta = ITEM_METADATA.get(key, {})
        if key.startswith("frame_"):
            # Frames go to shop_items (type='frame'), strip prefix to get frame key
            frame_key = key[len("frame_"):]
            from database.postgres import connect as _pg_connect
            async with _pg_connect() as _db:
                existing = await _db.fetchone(
                    "SELECT id FROM shop_items WHERE user_id=? AND item_type='frame' AND item_value=? LIMIT 1",
                    (uid, frame_key),
                )
                if not existing:
                    await _db.execute(
                        "INSERT INTO shop_items (user_id, item_type, item_value, chat_id, purchased_at, active) VALUES (?,?,?,?,NOW(),1)",
                        (uid, "frame", frame_key, chat_id),
                    )
                else:
                    comp = random.randint(20, 200)
                    await add_mora(uid, chat_id, comp)
                    results.append({
                        "key": key, "name": name, "rarity": rarity, "desc": desc,
                        "atk": 0, "def_val": 0, "hp": 0, "crit_rate": 0.0,
                        "slot": None, "sell": 0,
                        "duplicate": True, "comp_mora": comp,
                    })
                    pity = 0 if rarity == "legendary" else pity + 1
                    continue
        elif key.startswith("theme_"):
            # Themes go to user_themes table, strip prefix to get theme key
            theme_key = key[len("theme_"):]
            from database.postgres import connect as _pg_connect
            async with _pg_connect() as _db:
                existing = await _db.fetchone(
                    "SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=? LIMIT 1",
                    (uid, theme_key),
                )
                if not existing:
                    await _db.execute(
                        "INSERT INTO user_themes (user_id, chat_id, theme_key, source, obtained_at) VALUES (?,?,?,?,NOW())",
                        (uid, chat_id, theme_key, "gacha"),
                    )
                else:
                    comp = random.randint(20, 200)
                    await add_mora(uid, chat_id, comp)
                    results.append({
                        "key": key, "name": name, "rarity": rarity, "desc": desc,
                        "atk": 0, "def_val": 0, "hp": 0, "crit_rate": 0.0,
                        "slot": None, "sell": 0,
                        "duplicate": True, "comp_mora": comp,
                    })
                    pity = 0 if rarity == "legendary" else pity + 1
                    continue
        else:
            # For lego_flair_* items: check for duplicates and pay compensation.
            # These are zero-stat cosmetic items; owning multiple copies is pointless.
            if key.startswith("lego_flair_"):
                from database.postgres import connect as _pg_connect
                async with _pg_connect() as _db:
                    _existing_flair = await _db.fetchone(
                        "SELECT id FROM gacha_inventory WHERE user_id=? AND item_key=? LIMIT 1",
                        (uid, key),
                    )
                if _existing_flair:
                    comp = random.randint(50, 400)
                    await add_mora(uid, chat_id, comp)
                    results.append({
                        "key": key, "name": name, "rarity": rarity, "desc": desc,
                        "atk": 0, "def_val": 0, "hp": 0, "crit_rate": 0.0,
                        "slot": meta.get("slot"), "sell": meta.get("sell", 0),
                        "duplicate": True, "comp_mora": comp,
                    })
                    pity = 0 if rarity == "legendary" else pity + 1
                    continue
            await add_gacha_item(
                uid, chat_id, key, name, rarity,
                atk=meta.get("atk", 0),
                def_val=meta.get("def_val", 0),
                hp=meta.get("hp", 0),
                crit_rate=meta.get("crit_rate", 0.0),
                slot=meta.get("slot"),
            )
        # Consume-slot items stay in inventory; user activates from inventory tab.
        pity = 0 if rarity == "legendary" else pity + 1
        results.append({
            "key": key, "name": name, "rarity": rarity, "desc": desc,
            "atk": meta.get("atk", 0), "def_val": meta.get("def_val", 0),
            "hp": meta.get("hp", 0), "crit_rate": meta.get("crit_rate", 0.0),
            "slot": meta.get("slot"), "sell": meta.get("sell", 0),
        })

    # ── Quest tick ─────────────────────────────────────────────────────────────
    quest_done = quest_xp = quest_mora = 0
    try:
        today = bot_today()
        quest = await get_user_quest(uid, chat_id, today)
        if quest.get("type") == "gacha":
            for _ in range(count):
                _new_p, _goal, just_done = await quest_tick(uid, chat_id, today, quest["type"], quest["goal"])
                if just_done:
                    quest_mora = quest.get("mora", 5)
                    quest_xp   = quest.get("xp", 10)
                    await add_xp_in_chat(uid, chat_id, quest_xp)
                    await add_mora(uid, chat_id, quest_mora)
                    await mark_quest_rewarded(uid, chat_id, today)
                    quest_done = 1
                    break  # quest complete, stop ticking
    except Exception:
        logging.getLogger(__name__).warning("quest_tick failed uid=%s chat=%s", uid, chat_id, exc_info=True)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        label = f"Гача ×{count}" if count > 1 else "Гача ×1"
        await log_wallet_tx(uid, chat_id, "expense", price, "gacha", label)
    except Exception as _e:
        _log.debug("%s", _e)
    # Increment gacha roll counter & check achievements (fire-and-forget)
    try:
        from database.db import postgres_connect as _pg
        async with _pg() as _db:
            await _db.execute(
                "UPDATE user_mora SET total_gacha_rolls = COALESCE(total_gacha_rolls,0) + ? WHERE user_id=? AND chat_id=?",
                (count, uid, chat_id)
            )
            row = await _db.fetchone("SELECT total_gacha_rolls FROM user_mora WHERE user_id=? AND chat_id=?", (uid, chat_id))
            total_rolls = int(row["total_gacha_rolls"] or 0) if row else count
        from api.achievements import check_and_award as _ach
        await _ach(uid, chat_id, "gacha_rolls", total_rolls)
    except Exception as _e:
        _log.debug("%s", _e)

    return {
        "ok":              True,
        "items":           results,
        "new_balance":     new_bal,
        "new_family_bal":  new_family_bal,
        "pity":            pity,
        "spent":           price,
        "is_single":       single,
        "quest_done":      bool(quest_done),
        "quest_xp":        int(quest_xp),
        "quest_mora":      int(quest_mora),
    }
