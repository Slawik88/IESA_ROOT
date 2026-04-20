"""
items/junk.py — мусорные предметы без ценности (низкие статы, низкая цена).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Мусор (🗄️ Хлам) ─────────────────────────────────────────────────────────

register(ItemDef(
    key="junk_stone", name="Камень хиличурла", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🪨", desc="Камень из кармана хиличурла.",
    sell_price=5, category="Хлам", readable_category="Мусор"
))

register(ItemDef(
    key="junk_stick", name="Кривая палка", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🌿", desc="Кривая палка путника.",
    sell_price=3, category="Хлам", readable_category="Мусор"
))

register(ItemDef(
    key="junk_dust", name="Пыль заклинаний", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="💫", desc="Пыль от забытых заклинаний.",
    sell_price=2, category="Хлам", readable_category="Мусор"
))

register(ItemDef(
    key="junk_bone", name="Кость хиличурла", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🦴", desc="Кость, выброшенная хиличурлом.",
    sell_price=4, category="Хлам", readable_category="Мусор"
))

register(ItemDef(
    key="junk_mushroom", name="Неизвестный гриб", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🍄", desc="Не ешь. Серьёзно.",
    sell_price=3, category="Хлам", readable_category="Мусор"
))

register(ItemDef(
    key="junk_feather", name="Перо химеры", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🪶", desc="Перо химеры-штормпиха.",
    sell_price=4, category="Хлам-Перо", readable_category="Мусор"
))

register(ItemDef(
    key="junk_rope", name="Оборванная верёвка", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🪢", desc="Оборванная верёвка странника.",
    sell_price=3, category="Хлам-Верёвка", readable_category="Мусор"
))
