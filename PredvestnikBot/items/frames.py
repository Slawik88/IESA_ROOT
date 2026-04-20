"""
items/frames.py — рамки для профиля (декоративные предметы).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Рамки RARE ────────────────────────────────────────────────────────────────

register(ItemDef(
    key="frame_star", name="🖼️ Рамка «Звёздный»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="gold",
    sell_price=1000,
    emoji="🖼️", desc="Золотое свечение. Украшает профиль.",
    category="Frame", readable_category="Рамка", craft_mat="shard_starlight"
))

register(ItemDef(
    key="frame_sakura", name="🖼️ Рамка «Сакура»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="pink",
    sell_price=1000,
    emoji="🖼️", desc="Розовое свечение сакуры. Женский стиль.",
    category="Frame", readable_category="Рамка", craft_mat="shard_sakura"
))

register(ItemDef(
    key="frame_fire", name="🖼️ Рамка «Огненный»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="red",
    sell_price=1000,
    emoji="🖼️", desc="Огненное свечение. Боевой дух.",
    category="Frame", readable_category="Рамка", craft_mat="shard_flame"
))

register(ItemDef(
    key="frame_ocean", name="🖼️ Рамка «Океан»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="cyan",
    sell_price=1000,
    emoji="🖼️", desc="Бирюзовое свечение волн.",
    category="Frame", readable_category="Рамка", craft_mat="shard_ocean"
))

# ─── Рамки EPIC ────────────────────────────────────────────────────────────────

register(ItemDef(
    key="frame_diamond", name="💎 Рамка «Алмаз»", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    glow_color="blue",
    sell_price=3000,
    emoji="💎", desc="Ярко-синее свечение. Королевский стиль.",
    category="Frame", readable_category="Рамка"
))

register(ItemDef(
    key="frame_shadow", name="🖤 Рамка «Тень»", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    glow_color="purple",
    sell_price=3000,
    emoji="🖤", desc="Фиолетовое свечение. Мистический вид.",
    category="Frame", readable_category="Рамка"
))

register(ItemDef(
    key="frame_celestial", name="⭐ Рамка «Небеса»", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    glow_color="silver",
    sell_price=3000,
    emoji="⭐", desc="Серебристое свечение звёзд.",
    category="Frame", readable_category="Рамка"
))

# ─── Рамки LEGENDARY ───────────────────────────────────────────────────────────

register(ItemDef(
    key="frame_godly", name="✨ Рамка «Божественный»", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    glow_color="multicolor",
    sell_price=10000,
    emoji="✨", desc="Радужное свечение. Высочайший уровень.",
    category="Frame", readable_category="Рамка"
))

register(ItemDef(
    key="frame_void", name="🌌 Рамка «Пустота»", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    glow_color="black",
    sell_price=10000,
    emoji="🌌", desc="Чёрное свечение вселенной. Редкая и таинственная.",
    category="Frame", readable_category="Рамка"
))

# ─── Специальные сезонные рамки ────────────────────────────────────────────────

register(ItemDef(
    key="frame_christmas", name="🎄 Рамка «Рождество»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="red_green",
    sell_price=800,
    emoji="🎄", desc="Праздничное красно-зелёное свечение.",
    category="Frame", readable_category="Рамка"
))

register(ItemDef(
    key="frame_halloween", name="🎃 Рамка «Хэллоуин»", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    glow_color="orange",
    sell_price=800,
    emoji="🎃", desc="Жёлто-оранжевое свечение тыквы.",
    category="Frame", readable_category="Рамка"
))

register(ItemDef(
    key="frame_newYear", name="🎆 Рамка «Новый год»", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    glow_color="fireworks",
    sell_price=2500,
    emoji="🎆", desc="Анимированное свечение фейерверков.",
    category="Frame", readable_category="Рамка"
))
