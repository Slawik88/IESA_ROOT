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
    ("cmn_xp_shard", "✨ Осколок Опыта",        "Сразу даёт +25 XP"),
    ("cmn_herb",     "🌿 Трава Сесилии",        "Сразу даёт +15 🪙"),
    ("cmn_quill",    "✒️ Перо ученика",         "Экипировка: +8 ATK, +15 HP, 2% крит"),
    ("cmn_talisman", "🔮 Амулет удачи",         "Экипировка: +5 DEF, 1.5% крит"),
]

_RARE_ITEMS = [
    ("rare_crown",      "👑 Серебряная корона",       "Экипировка: +25 ATK, +15 DEF, 4% крит"),
    ("rare_catalyst",   "🔮 Магический катализатор",  "Экипировка: +30 ATK, 4% крит"),
    ("rare_cape",       "🧣 Алый плащ",               "Экипировка: +25 DEF, +80 HP"),
    ("rare_gem",        "💎 Сапфир полуночи",          "Экипировка: +20 DEF, 6% крит"),
    ("rare_xp_crystal", "💠 Кристалл Опыта XL",       "Сразу даёт +150 XP"),
    ("rare_mora_bag",   "💰 Мешок Моры",               "Сразу даёт +120 🪙"),
    ("rare_amulet",     "📿 Кармин змеи",              "Экипировка: +20 DEF, 8% крит"),
    ("rare_mora_chest", "🧧 Красный конверт",          "Сразу даёт +250 🪙"),
    ("rare_lance",      "⚡ Лазурное копьё",           "Экипировка: +35 ATK, 5% крит"),
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
        from database.db import get_marriage as _get_marriage
        marriage = await _get_marriage(uid, chat_id)
        if not marriage:
            raise ValueError("Нет семейного кошелька")
        partner_id  = marriage["partner_id"]
        my_fam      = await get_family_wallet(chat_id, uid)
        partner_fam = await get_family_wallet(chat_id, partner_id)
        total_fam   = my_fam + partner_fam
        if total_fam < price:
            raise ValueError(f"Недостаточно в семейном ({total_fam}/{price} 🪙)")
        from database.db import add_to_family_wallet as _add_fam
        deduct_me      = min(my_fam, price)
        deduct_partner = price - deduct_me
        await _add_fam(chat_id, uid, -deduct_me)
        if deduct_partner > 0:
            await _add_fam(chat_id, partner_id, -deduct_partner)
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
        elif key == "cmn_herb":
            await add_mora(uid, chat_id, 15)
        elif key == "rare_xp_crystal":
            await add_xp_in_chat(uid, chat_id, 150)
        elif key == "rare_mora_bag":
            await add_mora(uid, chat_id, 120)
        elif key == "rare_mora_chest":
            await add_mora(uid, chat_id, 250)
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
