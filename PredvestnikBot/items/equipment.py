"""
items/equipment.py — регистрация первых предметов через новый реестр.

Значения ATK/DEF/HP/CRIT дублируют shared_prices.ITEM_METADATA до тех пор,
пока миграция не завершится и ITEM_METADATA не начнёт читаться из реестра.

Добавляй сюда новые предметы по одному, чтобы поддерживать единый источник
истины вместо dict-литерала в shared_prices.py.
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Обычное оружие ───────────────────────────────────────────────────────────

register(ItemDef(
    key="cmn_sword",
    name="Обычный меч",
    rarity=ItemRarity.COMMON,
    slot=ItemSlot.WEAPON,
    atk=15,
    crit_rate=0.02,
    emoji="⚔️",
    desc="Простой железный меч. Начало любого пути.",
    sell_price=20,
    in_gacha=True,
    category="weapon",
    readable_category="Оружие",
))

register(ItemDef(
    key="cmn_bow",
    name="Простой лук",
    rarity=ItemRarity.COMMON,
    slot=ItemSlot.WEAPON,
    atk=12,
    crit_rate=0.02,
    emoji="🏹",
    desc="Деревянный лук охотника. Лёгкий, но ненадёжный.",
    sell_price=18,
    in_gacha=True,
    category="weapon",
    readable_category="Оружие",
))

register(ItemDef(
    key="cmn_book",
    name="Гримуар начинающего",
    rarity=ItemRarity.COMMON,
    slot=ItemSlot.ARTIFACT,
    atk=8,
    crit_rate=0.03,
    emoji="📜",
    desc="Истрёпанный гримуар. Дарует крупицу магической силы.",
    sell_price=22,
    in_gacha=True,
    category="artifact",
    readable_category="Артефакт",
))

# ─── Легендарное оружие ───────────────────────────────────────────────────────

register(ItemDef(
    key="lego_gnosis",
    name="Гнозис бездны",
    rarity=ItemRarity.LEGENDARY,
    slot=ItemSlot.WEAPON,
    atk=60,
    crit_rate=0.08,
    emoji="🌌",
    desc="Оружие, вобравшее знание самой бездны. Редчайший трофей.",
    sell_price=0,
    in_gacha=True,
    category="weapon",
    readable_category="Оружие",
))

register(ItemDef(
    key="lego_fatui",
    name="Клинок Фатуи",
    rarity=ItemRarity.LEGENDARY,
    slot=ItemSlot.WEAPON,
    atk=55,
    hp=150,
    crit_rate=0.10,
    emoji="☝️",
    desc="Оружие агентов Фатуи. Смертоносно в умелых руках.",
    sell_price=0,
    in_gacha=True,
    category="weapon",
    readable_category="Оружие",
))
