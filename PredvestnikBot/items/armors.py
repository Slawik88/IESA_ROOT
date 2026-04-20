"""
items/armors.py — броня (RARE и выше).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── RARE Броня ────────────────────────────────────────────────────────────────

register(ItemDef(
    key="rare_gem", name="🔷 Сапфир полуночи", rarity=ItemRarity.RARE, slot=ItemSlot.ARMOR,
    def_val=20, crit_pct=6,
    sell_price=1500,
    emoji="🔷", desc="Синий самоцвет. +20 DEF, +6% CRIT.",
    category="Armor", readable_category="Броня", craft_mat="shard_gem"
))

register(ItemDef(
    key="rare_cape", name="🧥 Алый плащ", rarity=ItemRarity.RARE, slot=ItemSlot.ARMOR,
    def_val=25, hp=80,
    sell_price=1500,
    emoji="🧥", desc="Алый боевой плащ. +25 DEF, +80 HP.",
    category="Armor", readable_category="Броня", craft_mat="shard_cloth"
))

register(ItemDef(
    key="rare_shield", name="🛡️ Щит камня", rarity=ItemRarity.RARE, slot=ItemSlot.ARMOR,
    def_val=30, hp=100,
    sell_price=1500,
    emoji="🛡️", desc="Каменный щит. +30 DEF, +100 HP.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="rare_ring", name="💍 Кольцо силы", rarity=ItemRarity.RARE, slot=ItemSlot.ARMOR,
    def_val=15, atk=10,
    sell_price=1500,
    emoji="💍", desc="Волшебное кольцо. +15 DEF, +10 ATK.",
    category="Armor", readable_category="Броня"
))

# ─── EPIC Броня ────────────────────────────────────────────────────────────────

register(ItemDef(
    key="epic_armor", name="🛠️ Броня палладина", rarity=ItemRarity.EPIC, slot=ItemSlot.ARMOR,
    def_val=50, hp=250,
    sell_price=4000,
    emoji="🛠️", desc="Святая броня. +50 DEF, +250 HP.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="epic_cloak", name="👔 Плащ теней", rarity=ItemRarity.EPIC, slot=ItemSlot.ARMOR,
    def_val=45, crit_pct=10,
    sell_price=4000,
    emoji="👔", desc="Плащ ассасина. +45 DEF, +10% CRIT.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="epic_robe", name="🧙 Мантия мудреца", rarity=ItemRarity.EPIC, slot=ItemSlot.ARMOR,
    def_val=40, mp=200,
    sell_price=4000,
    emoji="🧙", desc="Магическая мантия. +40 DEF, +200 MP.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="epic_crown", name="👑 Корона властелина", rarity=ItemRarity.EPIC, slot=ItemSlot.ARMOR,
    def_val=35, atk=15,
    sell_price=4000,
    emoji="👑", desc="Королевская корона. +35 DEF, +15 ATK.",
    category="Armor", readable_category="Броня"
))

# ─── LEGENDARY Броня ──────────────────────────────────────────────────────────

register(ItemDef(
    key="legendary_godarmor", name="⚡ Доспехи Одина", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARMOR,
    def_val=70, hp=400, atk=20,
    sell_price=10000,
    emoji="⚡", desc="Боевые доспехи. +70 DEF, +400 HP, +20 ATK.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="legendary_darkplate", name="🖤 Тёмные пластины", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARMOR,
    def_val=75, crit_pct=15,
    sell_price=10000,
    emoji="🖤", desc="Чёрные доспехи. +75 DEF, +15% CRIT.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="legendary_mooncloak", name="🌙 Плащ луны", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARMOR,
    def_val=68, mp=250,
    sell_price=10000,
    emoji="🌙", desc="Лунный плащ. +68 DEF, +250 MP.",
    category="Armor", readable_category="Броня"
))

register(ItemDef(
    key="legendary_suncrown", name="☀️ Корона солнца", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.ARMOR,
    def_val=72, hp=300,
    sell_price=10000,
    emoji="☀️", desc="Солнечная корона. +72 DEF, +300 HP.",
    category="Armor", readable_category="Броня"
))
