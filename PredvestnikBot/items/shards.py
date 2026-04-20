"""
items/shards.py — осколки для крафта (шарды).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Осколки оборудования ──────────────────────────────────────────────────────

register(ItemDef(
    key="shard_sword", name="Осколок клинка", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_into="rare_lance", craft_amount=10,
    emoji="🗡️", desc="Фрагмент клинка. 10 шт. → 🚪 Лазурное копьё (+35 ATK).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_gem", name="Осколок самоцвета", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_into="rare_gem", craft_amount=10,
    emoji="🔷", desc="Обломок кристалла. 10 шт. → 🔷 Сапфир полуночи (+20 DEF, +6% CRIT).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_cloth", name="Осколок ткани", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_into="rare_cape", craft_amount=10,
    emoji="🧵", desc="Зачарованная ткань. 10 шт. → 🧥 Алый плащ (+25 DEF, +80 HP).",
    category="Shard", readable_category="Осколок"
))

# ─── Осколки зелий ────────────────────────────────────────────────────────────

register(ItemDef(
    key="shard_essence", name="Капля эссенции", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_into="str_potion", craft_amount=5,
    emoji="🟡", desc="Магическая эссенция. 5 шт. → 🥤 Зелье Силы (+15 ATK на 1 час).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_crystal", name="Кристалл духа", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_into="def_potion", craft_amount=5,
    emoji="🔮", desc="Духовный кристалл. 5 шт. → ⚗️ Зелье Защиты (+20 DEF на 1 час).",
    category="Shard", readable_category="Осколок"
))

# ─── Осколки купонов ──────────────────────────────────────────────────────────

register(ItemDef(
    key="shard_scroll", name="Обрывок свитка", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_into="quest_reroll", craft_amount=8,
    emoji="📜", desc="Магический пергамент. 8 шт. → 🎯 Переброска квеста.",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_compass", name="Стрелка компаса", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    craft_into="exp_boost_sm", craft_amount=6,
    emoji="🧭", desc="Зачарованная стрелка. 6 шт. → 🗺️ Ускорение экспедиции S (−30 мин).",
    category="Shard", readable_category="Осколок"
))

# ─── Осколки рамок ────────────────────────────────────────────────────────────

register(ItemDef(
    key="shard_starlight", name="Фрагмент звезды", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_frame="star", craft_amount=15,
    emoji="🌟", desc="Звёздный осколок. 15 шт. → 🖼️ Рамка «Звёздный» (золотое свечение).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_sakura", name="Лепесток сакуры", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_frame="sakura", craft_amount=20,
    emoji="🌸", desc="Магический лепесток. 20 шт. → 🖼️ Рамка «Сакура» (розовое свечение).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_flame", name="Искра пламени", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_frame="fire", craft_amount=12,
    emoji="🔥", desc="Огненная искра. 12 шт. → 🖼️ Рамка «Огненный» (огненное свечение).",
    category="Shard", readable_category="Осколок"
))

register(ItemDef(
    key="shard_ocean", name="Капля океана", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    craft_frame="ocean", craft_amount=18,
    emoji="🌊", desc="Океанская капля. 18 шт. → 🖼️ Рамка «Океан» (бирюзовое свечение).",
    category="Shard", readable_category="Осколок"
))
