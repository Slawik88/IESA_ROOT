"""
items/consumables.py — предметы, которые можно использовать/съесть.

Включает: зелья боевые, еду для питомца, опыт/мору расходники.
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Зелья для боя (🥤 Зелья) ─────────────────────────────────────────────────

register(ItemDef(
    key="str_potion", name="Зелье Силы", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    buff_type="atk", buff_amount=15, duration_minutes=60,
    emoji="🥤", desc="Зелье Силы: +15 ATK на 1 час.",
    price=120, sell_price=50, category="Зелье Силы", readable_category="Зелье"
))

register(ItemDef(
    key="def_potion", name="Зелье Защиты", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    buff_type="def", buff_amount=20, duration_minutes=60,
    emoji="⚗️", desc="Зелье Защиты: +20 DEF на 1 час.",
    price=90, sell_price=40, category="Зелье Защиты", readable_category="Зелье"
))

register(ItemDef(
    key="hp_potion", name="Зелье Здоровья", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    buff_type="hp", buff_amount=50, duration_minutes=90,
    emoji="❤️", desc="Зелье Здоровья: +50 HP на 1.5 часа.",
    price=100, sell_price=45, category="Зелье Здоровья", readable_category="Зелье"
))

register(ItemDef(
    key="str_superior", name="Зелье Силы Superior", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    buff_type="atk", buff_amount=30, duration_minutes=120,
    emoji="🧪", desc="Зелье Силы Superior: +30 ATK на 2 часа (только из гачи).",
    price=0, sell_price=100, category="Зелье Премиум", readable_category="Зелье"
))

register(ItemDef(
    key="def_superior", name="Зелье Защиты Superior", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    buff_type="def", buff_amount=40, duration_minutes=120,
    emoji="🧫", desc="Зелье Защиты Superior: +40 DEF на 2 часа (только из гачи).",
    price=0, sell_price=80, category="Зелье Премиум", readable_category="Зелье"
))

# ─── Еда для питомца (🍽️ Еда) ───────────────────────────────────────────────

register(ItemDef(
    key="краб", name="Золотой краб", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    fatigue=40, emoji="🦀", desc="Краб для питомца. Восстанавливает 40 ед. усталости.",
    price=40, sell_price=20, category="Еда", readable_category="Еда для питомца"
))

register(ItemDef(
    key="лапша", name="Лапша путника", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    fatigue=20, emoji="🍜", desc="Лапша для питомца. Восстанавливает 20 ед. усталости.",
    price=20, sell_price=10, category="Еда", readable_category="Еда для питомца"
))

register(ItemDef(
    key="деликатес", name="Морской деликатес", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    fatigue=80, emoji="🦞", desc="Деликатес для питомца. Восстанавливает 80 ед. усталости.",
    price=80, sell_price=40, category="Еда", readable_category="Еда для питомца"
))

register(ItemDef(
    key="гриб", name="Гриб Слепого Ка", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    fatigue=35, emoji="🍄", desc="Гриб для питомца. Восстанавливает 35 ед. усталости.",
    price=35, sell_price=18, category="Еда", readable_category="Еда для питомца"
))

# ─── Мгновенный опыт / мора (🎁 Расходники) ─────────────────────────────────

register(ItemDef(
    key="cmn_xp_shard", name="Осколок опыта", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="✨", desc="Осколок опыта: мгновенно +25 XP.",
    sell_price=15, category="Опыт-Осколок", readable_category="Расходник"
))

register(ItemDef(
    key="rare_xp_crystal", name="Кристалл опыта", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    emoji="💫", desc="Кристалл опыта: мгновенно +150 XP.",
    sell_price=60, category="Опыт-Кристалл", readable_category="Расходник"
))

register(ItemDef(
    key="rare_mora_bag", name="Мешок Моры", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    emoji="🎒", desc="Мешок Моры: мгновенно +120 🪙.",
    sell_price=55, category="Мора-Мешок", readable_category="Расходник"
))

register(ItemDef(
    key="cmn_herb", name="Трава Сесилии", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    emoji="🌿", desc="Трава Сесилии: мгновенно +15 🪙.",
    sell_price=8, category="Расходник-Трава", readable_category="Расходник"
))

register(ItemDef(
    key="vip_lottery_ticket", name="VIP-билет лотереи", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.NONE,
    emoji="🎟️", desc="VIP-билет недельной лотереи: +3 участия за один билет. Розыгрыш каждое воскресенье!",
    price=0, sell_price=0, category="VIP-Билет", readable_category="Билет"
))
