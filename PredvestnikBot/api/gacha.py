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

# ── Item pools (identical to handlers/gacha.py) ────────────────────────────────
_JUNK_ITEMS = [
    ("junk_stone",    "🪨 Камень Маслоу",       "Бесполезный хлам — продай кнопкой «Продать мусор»"),
    ("junk_stick",    "🪵 Палка путника",        "Сломанная палка, годится только на продажу"),
    ("junk_dust",     "💨 Пыль забвения",        "Пыль из неизвестного мира — никому не нужна"),
    ("junk_bone",     "🦴 Кость хиличурла",      "Древняя кость. Продай и забудь"),
    ("junk_mushroom", "🍄 Сомнительный гриб",    "Лучше не пробовать. Зато можно продать"),
]

_COMMON_ITEMS = [
    ("cmn_sword",  "⚔️ Тупой клинок",        "Разовый бонус: +5 XP при получении"),
    ("cmn_bow",    "🏹 Кривой лук",           "Разовый бонус: +3 Моры при получении"),
    ("cmn_book",   "📕 Потрёпанный дневник",   "Разовый бонус: +8 XP при получении"),
    ("cmn_ring",   "💍 Дешёвое кольцо",        "Разовый бонус: +4 Моры при получении"),
    ("cmn_shield", "🛡 Ржавый щит",            "Разовый бонус: +6 XP при получении"),
    ("str_potion", "⚔️ Зелье Силы",           "Расходник: +15 ATK на 1 час"),
    ("def_potion", "🛡️ Зелье Защиты",         "Расходник: +20 DEF на 1 час"),
    ("hp_potion",  "❤️ Зелье Здоровья",       "Расходник: +50 HP на 1.5 часа"),
    ("cmn_xp_shard", "✨ Осколок Опыта",       "Сразу даёт +25 XP"),
]

_RARE_ITEMS = [
    ("rare_crown",    "👑 Серебряная корона",        "Косметика: элегантная корона для профиля"),
    ("rare_catalyst", "🔮 Магический катализатор",   "Косметика: мистический атрибут мага"),
    ("rare_cape",     "🧣 Алый плащ",                "Косметика: плащ героя ветров"),
    ("rare_gem",      "💎 Сапфир полуночи",           "Косметика: сверкающий камень ночи"),
    ("rare_xp_crystal", "💠 Кристалл Опыта XL",    "Сразу даёт +150 XP"),
    ("rare_mora_bag",   "💰 Мешок Моры",             "Сразу даёт +120 🪙"),
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
]


def roll_one(pity: int) -> tuple[str, str, str, str]:
    """Single gacha roll. Returns (item_key, item_name, rarity, description)."""
    if pity >= GACHA_PITY_MAX - 1:
        key, name, desc = random.choice(_LEGENDARY_ITEMS)
        return key, name, "legendary", desc

    r = random.random()
    if r < 0.03:
        key, name, desc = random.choice(_LEGENDARY_ITEMS)
        return key, name, "legendary", desc
    elif r < 0.10:
        key, name, desc = random.choice(_RARE_ITEMS)
        return key, name, "rare", desc
    elif r < 0.30:
        key, name, desc = random.choice(_COMMON_ITEMS)
        return key, name, "common", desc
    else:
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
        add_gacha_item, add_mora, deduct_mora,
        get_family_wallet, get_gacha_pity, get_mora, is_user_single,
        get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat,
    )
    from utils.helpers import bot_today

    if count not in (1, 10):
        raise ValueError("count must be 1 or 10")

    single = await is_user_single(uid, chat_id)
    price  = (GACHA_SINGLES_SINGLE if count == 1 else GACHA_SINGLES_MULTI) if single else (
             GACHA_SINGLE_PRICE    if count == 1 else GACHA_MULTI_PRICE)

    # ── Deduct cost ────────────────────────────────────────────────────────────
    if wallet_type == "family":
        if single:
            raise ValueError("Нет семейного кошелька")
        fam_balance = await get_family_wallet(chat_id, uid)  # returns int
        if fam_balance < price:
            raise ValueError(f"Недостаточно в семейном ({fam_balance}/{price} 🪙)")
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            await db.execute(
                "UPDATE family_wallet SET balance=balance-? WHERE chat_id=? AND user_id=? AND balance>=?",
                (price, chat_id, uid, price),
            )
            await db.commit()
        mora_row = await get_mora(uid, chat_id)
        new_bal  = mora_row["balance"] if mora_row else 0
    else:
        ok, new_bal = await deduct_mora(uid, chat_id, price)
        if not ok:
            mora_row = await get_mora(uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Недостаточно Моры ({bal}/{price} 🪙)")

    # ── Roll ───────────────────────────────────────────────────────────────────
    pity    = await get_gacha_pity(uid, chat_id)
    results = []
    for _ in range(count):
        key, name, rarity, desc = roll_one(pity)
        meta = ITEM_METADATA.get(key, {})
        await add_gacha_item(
            uid, chat_id, key, name, rarity,
            atk=meta.get("atk", 0),
            def_val=meta.get("def_val", 0),
            hp=meta.get("hp", 0),
            crit_rate=meta.get("crit_rate", 0.0),
            slot=meta.get("slot"),
        )
        # Instant-grant items — apply effect immediately
        if key == "cmn_xp_shard":
            await add_xp_in_chat(uid, chat_id, 25)
        elif key == "rare_xp_crystal":
            await add_xp_in_chat(uid, chat_id, 150)
        elif key == "rare_mora_bag":
            await add_mora(uid, chat_id, 120)
        pity = 0 if rarity == "legendary" else pity + 1
        results.append({"key": key, "name": name, "rarity": rarity, "desc": desc})

    # ── Quest tick ─────────────────────────────────────────────────────────────
    quest_done = quest_xp = quest_mora = 0
    try:
        today = bot_today()
        quest = await get_user_quest(uid, chat_id, today)
        if quest.get("type") == "gacha":
            _new_p, _goal, just_done = await quest_tick(uid, chat_id, today, quest["type"], quest["goal"])
            if just_done:
                quest_mora = quest.get("mora", 5)
                quest_xp   = quest.get("xp", 10)
                await add_xp_in_chat(uid, chat_id, quest_xp)
                await add_mora(uid, chat_id, quest_mora)
                await mark_quest_rewarded(uid, chat_id, today)
                quest_done = 1
    except Exception:
        pass

    return {
        "ok":          True,
        "items":       results,
        "new_balance": new_bal,
        "pity":        pity,
        "spent":       price,
        "is_single":   single,
        "quest_done":  bool(quest_done),
        "quest_xp":    int(quest_xp),
        "quest_mora":  int(quest_mora),
    }
