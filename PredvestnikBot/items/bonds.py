"""
items/bonds.py — облигации/узы (биржевые инструменты, тип акций).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Облигации (💎 Узы / Биржа) ─────────────────────────────────────────────

# Blue chips (low volatility, 3× cap multiplier)
register(ItemDef(
    key="mondstadt", name="📜 Холодный Ветер (Мондштадт)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    base_price=100, volatility=0.08, cap_mult=3,
    emoji="📜", desc="Стабильная облигация Мондштадта.",
    category="Bond-BlueChip", readable_category="Облигация"
))

register(ItemDef(
    key="liyue", name="💎 Нефритовый Слиток (Ли Юэ)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    base_price=120, volatility=0.07, cap_mult=3,
    emoji="💎", desc="Надёжная облигация Ли Юэ.",
    category="Bond-BlueChip", readable_category="Облигация"
))

register(ItemDef(
    key="north_bank", name="🏦 Банк Северного Королевства", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    base_price=500, volatility=0.05, cap_mult=3,
    emoji="🏦", desc="Институциональная облигация.",
    category="Bond-BlueChip", readable_category="Облигация"
))

# Mid-caps (volatility 14-20%, 5× cap multiplier)
register(ItemDef(
    key="inazuma", name="⚡ Вишнёвый Гром (Инадзума)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    base_price=150, volatility=0.15, cap_mult=5,
    emoji="⚡", desc="Волатильная облигация Инадзумы.",
    category="Bond-MidCap", readable_category="Облигация"
))

register(ItemDef(
    key="sumeru", name="🌿 Зелёный Лист (Сумеру)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    base_price=90, volatility=0.18, cap_mult=5,
    emoji="🌿", desc="Растущая облигация Сумеру.",
    category="Bond-MidCap", readable_category="Облигация"
))

register(ItemDef(
    key="fontaine", name="💧 Хрустальный Поток (Фонтэн)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    base_price=200, volatility=0.14, cap_mult=5,
    emoji="💧", desc="Текучая облигация Фонтэна.",
    category="Bond-MidCap", readable_category="Облигация"
))

register(ItemDef(
    key="natlan", name="🔥 Пламенный Клык (Натлан)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    base_price=175, volatility=0.20, cap_mult=5,
    emoji="🔥", desc="Горячая облигация Натлана.",
    category="Bond-MidCap", readable_category="Облигация"
))

# High-risk (35% volatility, 8× cap multiplier)
register(ItemDef(
    key="naku_grass", name="🌾 Трава Наку", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    base_price=40, volatility=0.35, cap_mult=8,
    emoji="🌾", desc="Рискованная облигация Наку.",
    category="Bond-HighRisk", readable_category="Облигация"
))

# Meme coins (45-50% volatility, 15-20× cap multiplier)
register(ItemDef(
    key="itto_coin", name="🐂 Итто-Коин", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    base_price=10, volatility=0.50, cap_mult=20,
    emoji="🐂", desc="Мем-облигация Итто.",
    category="Bond-Meme", readable_category="Облигация"
))

register(ItemDef(
    key="dori_corp", name="💰 Дори-Инвестментс", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    base_price=25, volatility=0.45, cap_mult=15,
    emoji="💰", desc="Мем-облигация Дори.",
    category="Bond-Meme", readable_category="Облигация"
))
