"""
items/coupons.py — купоны для квестов и специальных действий.
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Переброски квестов ────────────────────────────────────────────────────────

register(ItemDef(
    key="quest_reroll", name="🎯 Переброска квеста", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="reroll_quest",
    sell_price=250,
    emoji="🎯", desc="Переброски текущий квест на новый.",
    category="Coupon", readable_category="Купон", craft_mat="shard_scroll"
))

register(ItemDef(
    key="quest_reroll_3x", name="🎯🎯🎯 Тройная переброска", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="reroll_quest_3x",
    sell_price=650,
    emoji="🎯🎯🎯", desc="3 переброски квестов.",
    category="Coupon", readable_category="Купон"
))

# ─── Ускорения экспедиций ──────────────────────────────────────────────────────

register(ItemDef(
    key="exp_boost_sm", name="🗺️ Ускорение S", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="exp_speedup_sm", speedup_minutes=30,
    sell_price=200,
    emoji="🗺️", desc="−30 мин. на текущую экспедицию.",
    category="Coupon", readable_category="Купон", craft_mat="shard_compass"
))

register(ItemDef(
    key="exp_boost_md", name="🗺️🗺️ Ускорение M", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="exp_speedup_md", speedup_minutes=60,
    sell_price=350,
    emoji="🗺️🗺️", desc="−1 час на текущую экспедицию.",
    category="Coupon", readable_category="Купон"
))

register(ItemDef(
    key="exp_boost_lg", name="🗺️🗺️🗺️ Ускорение L", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="exp_speedup_lg", speedup_minutes=120,
    sell_price=600,
    emoji="🗺️🗺️🗺️", desc="−2 часа на текущую экспедицию.",
    category="Coupon", readable_category="Купон"
))

# ─── Приватные комнаты ─────────────────────────────────────────────────────────

register(ItemDef(
    key="private_room_1h", name="🏠 Приватная комната (1ч)", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="private_room", duration_hours=1,
    sell_price=400,
    emoji="🏠", desc="Личная комната на 1 час. Без спама.",
    category="Coupon", readable_category="Купон"
))

register(ItemDef(
    key="private_room_24h", name="🏰 Приватная комната (24ч)", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="private_room", duration_hours=24,
    sell_price=1500,
    emoji="🏰", desc="Личная комната на 24 часа. Без спама.",
    category="Coupon", readable_category="Купон"
))

# ─── Премиум абонементы ────────────────────────────────────────────────────────

register(ItemDef(
    key="vip_day", name="👑 VIP на день", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="vip_boost", duration_hours=24,
    sell_price=2000,
    emoji="👑", desc="+20% опыт, +15% золото. 24 часа.",
    category="Coupon", readable_category="Купон"
))

register(ItemDef(
    key="vip_week", name="👑👑 VIP на неделю", rarity=ItemRarity.EPIC, slot=ItemSlot.CONSUMABLE,
    effect="vip_boost", duration_hours=168,
    sell_price=11000,
    emoji="👑👑", desc="+25% опыт, +20% золото. 7 дней.",
    category="Coupon", readable_category="Купон"
))

# ─── Лотерейные билеты ─────────────────────────────────────────────────────────

register(ItemDef(
    key="lottery_ticket", name="🎰 Лотерейный билет", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="lottery_draw",
    sell_price=150,
    emoji="🎰", desc="Сыграйте в лотерею. Приз: 100−10000 золота.",
    category="Coupon", readable_category="Купон"
))

register(ItemDef(
    key="crystal_lottery", name="💎 Кристальная лотерея", rarity=ItemRarity.RARE, slot=ItemSlot.CONSUMABLE,
    effect="crystal_lottery",
    sell_price=1000,
    emoji="💎", desc="Лотерея кристаллов. Приз: 50−500 💎.",
    category="Coupon", readable_category="Купон"
))

# ─── Чит-коды / инвайты ────────────────────────────────────────────────────────

register(ItemDef(
    key="invite_friend", name="📨 Приглашение друга", rarity=ItemRarity.COMMON, slot=ItemSlot.CONSUMABLE,
    effect="send_invite",
    sell_price=0,  # Не продаётся
    emoji="📨", desc="Отправьте приглашение другу.",
    category="Coupon", readable_category="Купон"
))

register(ItemDef(
    key="season_pass", name="🎫 Сезонный пропуск", rarity=ItemRarity.EPIC, slot=ItemSlot.CONSUMABLE,
    effect="season_pass", duration_hours=2592000,  # 30 дней
    sell_price=5000,
    emoji="🎫", desc="Сезонные привилегии на 30 дней.",
    category="Coupon", readable_category="Купон"
))
