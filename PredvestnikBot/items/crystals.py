"""
items/crystals.py — кристальные паки (Telegram Stars → Кристаллы 💎).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Telegram Stars → Кристаллы (💎 Crystal Packs) ──────────────────────────

register(ItemDef(
    key="crystal_starter", name="💎 Стартовый пак", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    stars=50, crystals=100, bonus_pct=0,
    emoji="💎", desc="50⭐ → 100💎 (без бонуса).",
    category="CrystalPack", readable_category="Пак кристаллов"
))

register(ItemDef(
    key="crystal_basic", name="💎 Базовый пак", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    stars=150, crystals=330, bonus_pct=10,
    emoji="💎", desc="150⭐ → 330💎 (+10% бонус).",
    category="CrystalPack", readable_category="Пак кристаллов"
))

register(ItemDef(
    key="crystal_advanced", name="💎 Продвинутый пак", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    stars=500, crystals=1200, bonus_pct=20,
    emoji="💎", desc="500⭐ → 1200💎 (+20% бонус).",
    category="CrystalPack", readable_category="Пак кристаллов"
))

register(ItemDef(
    key="crystal_premium", name="💎 Премиум пак", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    stars=1000, crystals=2600, bonus_pct=30,
    emoji="💎", desc="1000⭐ → 2600💎 (+30% бонус).",
    category="CrystalPack", readable_category="Пак кристаллов"
))

register(ItemDef(
    key="crystal_ultimate", name="💎 Легендарный пак", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    stars=2500, crystals=7000, bonus_pct=40,
    emoji="💎", desc="2500⭐ → 7000💎 (+40% бонус).",
    category="CrystalPack", readable_category="Пак кристаллов"
))
