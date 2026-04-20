"""
items/quest_rewards.py — награды за квесты (боевой лут).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Стандартные луты (COMMON) ─────────────────────────────────────────────────

register(ItemDef(
    key="loot_gold_pouch_sm", name="👛 Кошелёк золота (S)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="gold_pouch", gold_amount=100,
    sell_price=0,  # Не продаётся, конвертируется в золото
    emoji="👛", desc="100 золота. Автоматически откроется.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_gold_pouch_md", name="👜 Кошелёк золота (M)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="gold_pouch", gold_amount=500,
    sell_price=0,
    emoji="👜", desc="500 золота. Автоматически откроется.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_gold_pouch_lg", name="💰 Кошелёк золота (L)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="gold_pouch", gold_amount=2000,
    sell_price=0,
    emoji="💰", desc="2000 золота. Автоматически откроется.",
    category="QuestReward", readable_category="Лут квеста"
))

# ─── XP и боевые награды ───────────────────────────────────────────────────────

register(ItemDef(
    key="loot_exp_sm", name="📖 Свиток опыта (S)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="exp_scroll", xp_amount=500,
    sell_price=0,
    emoji="📖", desc="500 опыта. Активируется при нажатии.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_exp_md", name="📕 Свиток опыта (M)", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="exp_scroll", xp_amount=2000,
    sell_price=0,
    emoji="📕", desc="2000 опыта. Активируется при нажатии.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_exp_lg", name="📗 Свиток опыта (L)", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="exp_scroll", xp_amount=8000,
    sell_price=0,
    emoji="📗", desc="8000 опыта. Активируется при нажатии.",
    category="QuestReward", readable_category="Лут квеста"
))

# ─── Ящики с лутом ────────────────────────────────────────────────────────────

register(ItemDef(
    key="loot_chest_sm", name="📦 Простой ящик", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="loot_chest", chest_size="small",
    sell_price=0,
    emoji="📦", desc="Ящик с лутом. 100−500 золота или предмет.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_chest_md", name="🎁 Красивый ящик", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="loot_chest", chest_size="medium",
    sell_price=0,
    emoji="🎁", desc="Ящик с лутом. 500−2000 золота или предмет.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_chest_lg", name="🏺 Сокровищница", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="loot_chest", chest_size="large",
    sell_price=0,
    emoji="🏺", desc="Ящик с лутом. 2000−8000 золота или редкий предмет.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="loot_chest_epic", name="💎 Эпический ящик", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    reward_type="loot_chest", chest_size="epic",
    sell_price=0,
    emoji="💎", desc="Ящик с лутом. 5000−20000 золота или эпический предмет.",
    category="QuestReward", readable_category="Лут квеста"
))

# ─── Ключи для сундуков ───────────────────────────────────────────────────────

register(ItemDef(
    key="key_sm", name="🔑 Простой ключ", rarity=ItemRarity.COMMON, slot=ItemSlot.NONE,
    reward_type="chest_key", key_type="common",
    sell_price=50,
    emoji="🔑", desc="Ключ от простого ящика.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="key_rare", name="🔓 Редкий ключ", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="chest_key", key_type="rare",
    sell_price=200,
    emoji="🔓", desc="Ключ от редкого ящика.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="key_epic", name="🔐 Эпический ключ", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    reward_type="chest_key", key_type="epic",
    sell_price=800,
    emoji="🔐", desc="Ключ от эпического ящика.",
    category="QuestReward", readable_category="Лут квеста"
))

# ─── Специальные боевые награды ────────────────────────────────────────────────

register(ItemDef(
    key="reward_enchant_scroll", name="✨ Свиток чарования", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="enchant_scroll", enchant_level=1,
    sell_price=400,
    emoji="✨", desc="Зачарует оружие/броню +1 уровень.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="reward_enhance_gem", name="💎 Кристалл усиления", rarity=ItemRarity.EPIC, slot=ItemSlot.NONE,
    reward_type="enhance_stone", enhance_amount=5,
    sell_price=1200,
    emoji="💎", desc="Усилит предмет на +5 прочности.",
    category="QuestReward", readable_category="Лут квеста"
))

register(ItemDef(
    key="reward_stat_potion", name="🌟 Зелье статов", rarity=ItemRarity.RARE, slot=ItemSlot.NONE,
    reward_type="stat_booster",
    sell_price=600,
    emoji="🌟", desc="Случайно +3 к одному параметру (ATK/DEF/HP).",
    category="QuestReward", readable_category="Лут квеста"
))
