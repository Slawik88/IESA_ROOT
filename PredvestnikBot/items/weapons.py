"""
items/weapons.py — оружие (RARE и выше).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── RARE Оружие ──────────────────────────────────────────────────────────────

register(ItemDef(
    key="rare_lance", name="🚪 Лазурное копьё", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=35, crit_pct=5,
    sell_price=1500,
    emoji="🚪", desc="Острое копьё из небесного азурита. +35 ATK, +5% CRIT.",
    category="Weapon", readable_category="Оружие", craft_mat="shard_sword"
))

register(ItemDef(
    key="rare_axe", name="🪓 Боевой топор", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=40, hp=50,
    sell_price=1500,
    emoji="🪓", desc="Тяжёлый топор для сокрушительных ударов. +40 ATK, +50 HP.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="rare_bow", name="🏹 Ледяной лук", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=32, crit_pct=8,
    sell_price=1500,
    emoji="🏹", desc="Лук, стреливший ледяными стрелами. +32 ATK, +8% CRIT.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="rare_staff", name="🔱 Посох Арктики", rarity=ItemRarity.RARE, slot=ItemSlot.WEAPON,
    atk=28, mp=100,
    sell_price=1500,
    emoji="🔱", desc="Магический посох. +28 ATK, +100 MP.",
    category="Weapon", readable_category="Оружие"
))

# ─── EPIC Оружие ──────────────────────────────────────────────────────────────

register(ItemDef(
    key="epic_sword", name="⚔️ Меч судьбы", rarity=ItemRarity.EPIC, slot=ItemSlot.WEAPON,
    atk=55, crit_pct=12, crit_dmg=30,
    sell_price=4000,
    emoji="⚔️", desc="Легендарный меч. +55 ATK, +12% CRIT, +30% CRIT DMG.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="epic_mace", name="🔨 Молот божества", rarity=ItemRarity.EPIC, slot=ItemSlot.WEAPON,
    atk=60, hp=150,
    sell_price=4000,
    emoji="🔨", desc="Божественный молот. +60 ATK, +150 HP.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="epic_rapier", name="⚜️ Рапира аристократа", rarity=ItemRarity.EPIC, slot=ItemSlot.WEAPON,
    atk=48, crit_pct=15,
    sell_price=4000,
    emoji="⚜️", desc="Грациозная рапира. +48 ATK, +15% CRIT.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="epic_spell", name="🪄 Жезл маяка", rarity=ItemRarity.EPIC, slot=ItemSlot.WEAPON,
    atk=45, mp=200,
    sell_price=4000,
    emoji="🪄", desc="Мощный магический жезл. +45 ATK, +200 MP.",
    category="Weapon", readable_category="Оружие"
))

# ─── LEGENDARY Оружие ─────────────────────────────────────────────────────────

register(ItemDef(
    key="legendary_excalibur", name="✨ Экскалибур", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=80, crit_pct=20, crit_dmg=50,
    sell_price=10000,
    emoji="✨", desc="Королевский меч легенд. +80 ATK, +20% CRIT, +50% CRIT DMG.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="legendary_yfvtyr", name="🌙 Ифвтир (Ночной)", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=75, crit_pct=18, crit_dmg=40,
    sell_price=10000,
    emoji="🌙", desc="Ночное оружие. +75 ATK, +18% CRIT, +40% CRIT DMG.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="legendary_solaris", name="☀️ Соларис", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=78, hp=200,
    sell_price=10000,
    emoji="☀️", desc="Солнечный артефакт. +78 ATK, +200 HP.",
    category="Weapon", readable_category="Оружие"
))

register(ItemDef(
    key="legendary_grimoire", name="📖 Гримуар вечности", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.WEAPON,
    atk=70, mp=300,
    sell_price=10000,
    emoji="📖", desc="Волшебный гримуар. +70 ATK, +300 MP.",
    category="Weapon", readable_category="Оружие"
))
