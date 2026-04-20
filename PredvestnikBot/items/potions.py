"""
items/potions.py — зелья и расходники (consumables).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Зелья боевые ─────────────────────────────────────────────────────────────

register(ItemDef(
    key="str_potion", name="🥤 Зелье Силы", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="str_boost", effect_hours=1,
    sell_price=200,
    emoji="🥤", desc="+15 ATK на 1 час. Разовое.",
    category="Potion", readable_category="Зелье", craft_mat="shard_essence"
))

register(ItemDef(
    key="def_potion", name="⚗️ Зелье Защиты", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="def_boost", effect_hours=1,
    sell_price=200,
    emoji="⚗️", desc="+20 DEF на 1 час. Разовое.",
    category="Potion", readable_category="Зелье", craft_mat="shard_crystal"
))

register(ItemDef(
    key="heal_potion", name="🩹 Зелье здоровья", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    heal_amount=300,
    sell_price=150,
    emoji="🩹", desc="Восстанавливает 300 HP моментально.",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="mana_potion", name="💙 Зелье маны", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    mana_amount=200,
    sell_price=150,
    emoji="💙", desc="Восстанавливает 200 MP моментально.",
    category="Potion", readable_category="Зелье"
))

# ─── Зелья редкие ─────────────────────────────────────────────────────────────

register(ItemDef(
    key="grand_heal", name="🌟 Великое исцеление", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    heal_amount=800,
    sell_price=600,
    emoji="🌟", desc="Восстанавливает 800 HP. Редкое зелье.",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="crit_potion", name="✨ Зелье крита", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="crit_boost", effect_hours=2,
    sell_price=500,
    emoji="✨", desc="+20% CRIT на 2 часа.",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="stamina_potion", name="⚡ Зелье выносливости", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="stamina_boost", effect_hours=2,
    sell_price=500,
    emoji="⚡", desc="+15% скорость восстановления HP. 2 часа.",
    category="Potion", readable_category="Зелье"
))

# ─── Зелья эпические ──────────────────────────────────────────────────────────

register(ItemDef(
    key="phoenix_potion", name="🔥 Зелье Феникса", rarity=ItemRarity.EPIC, slot=ItemSlot.CONSUMABLE,
    effect="revive", revive_pct=50,
    sell_price=1500,
    emoji="🔥", desc="Возрождает с 50% HP если погибнешь. Действует 1 бой.",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="berserk_potion", name="💢 Берсерк", rarity=ItemRarity.EPIC, slot=ItemSlot.CONSUMABLE,
    effect="berserk", effect_hours=1,
    sell_price=1200,
    emoji="💢", desc="+50% ATK, −20% DEF на 1 час.",
    category="Potion", readable_category="Зелье"
))

# ─── Спецзелья (ночные бонусы) ────────────────────────────────────────────────

register(ItemDef(
    key="night_boost_small", name="🌙 Ночной бонус S", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="exp_boost_night", exp_bonus_pct=20, effect_hours=8,
    sell_price=100,
    emoji="🌙", desc="+20% опыт в ночных миссиях. 8 часов.",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="night_boost_large", name="🌙💎 Ночной бонус L", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="exp_boost_night", exp_bonus_pct=40, effect_hours=12,
    sell_price=600,
    emoji="🌙💎", desc="+40% опыт в ночных миссиях. 12 часов.",
    category="Potion", readable_category="Зелье"
))

# ─── Напитки (временные баффы) ────────────────────────────────────────────────

register(ItemDef(
    key="tea_strength", name="🍵 Чай Силы", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="str_tea", effect_hours=1,
    sell_price=80,
    emoji="🍵", desc="+8 ATK на 1 час (мягче, чем зелье).",
    category="Potion", readable_category="Зелье"
))

register(ItemDef(
    key="coffee_energy", name="☕ Энергетический кофе", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="energy", effect_hours=2,
    sell_price=120,
    emoji="☕", desc="+10% скорость атаки на 2 часа.",
    category="Potion", readable_category="Зелье"
))
