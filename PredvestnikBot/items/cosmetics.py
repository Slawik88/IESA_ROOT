"""
items/cosmetics.py — косметические предметы (рамки, фlair, платные тема/статусы).
"""

from items.registry import ItemDef, ItemRarity, ItemSlot, register

# ─── Рамки профиля (🖼️ Frames) ──────────────────────────────────────────────

register(ItemDef(
    key="frame_default", name="Стандартная рамка", rarity=ItemRarity.COMMON, slot=ItemSlot.FRAME,
    emoji="🔰", price=0, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_bronze", name="Бронзовая рамка", rarity=ItemRarity.COMMON, slot=ItemSlot.FRAME,
    emoji="🥉", price=150, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_silver", name="Серебряная рамка", rarity=ItemRarity.COMMON, slot=ItemSlot.FRAME,
    emoji="🥈", price=200, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_copper", name="Медная рамка", rarity=ItemRarity.COMMON, slot=ItemSlot.FRAME,
    emoji="🔶", price=100, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_warrior", name="Рамка Воина", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    emoji="⚔️", price=250, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_king", name="Королевская рамка", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    emoji="👑", price=500, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_diamond", name="Алмазная рамка", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    emoji="💎", price=600, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_star", name="Звёздная рамка", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    emoji="⭐", price=300, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_sakura", name="Рамка Сакура", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    emoji="🌸", price=1200, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_abyss", name="Рамка Бездны", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    emoji="🌀", price=1500, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_fatui", name="Рамка Предвестника", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    emoji="⚡", price=1800, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_celestia", name="Рамка Целестия", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    emoji="🏰", price=3500, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_void", name="Рамка Пустота", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    emoji="🌌", price=4000, category="frame", readable_category="Рамка профиля", sell_price=0
))

# ─── Эксклюзивные рамки (только за кристаллы) ─────────────────────────────────

register(ItemDef(
    key="frame_divine", name="Божественная рамка", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    emoji="🔱", price=0, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_rainbow", name="Радужная рамка", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FRAME,
    emoji="🌈", price=0, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_first_topup", name="Рамка первого пополнения", rarity=ItemRarity.RARE, slot=ItemSlot.FRAME,
    emoji="🌟", price=0, category="frame", readable_category="Рамка профиля", sell_price=0
))

register(ItemDef(
    key="frame_bp_gold", name="Золотая БП рамка", rarity=ItemRarity.EPIC, slot=ItemSlot.FRAME,
    emoji="🏅", price=0, category="frame", readable_category="Рамка профиля", sell_price=0
))

# ─── Косметические flair (✨ Статус рядом с именем) ────────────────────────────

register(ItemDef(
    key="lego_flair_star", name="Золотой ореол", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FLAIR,
    crit_rate=0.03, emoji="⭐", desc="⭐ Золотой ореол рядом с именем (+3% крит).",
    sell_price=0, category="Косметика-Ореол", readable_category="Ореол имени"
))

register(ItemDef(
    key="lego_flair_void", name="Тёмный ореал", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FLAIR,
    atk=8, emoji="🌌", desc="🌌 Тёмно-мистический эффект имени (+8 АТК).",
    sell_price=0, category="Косметика-Мистика", readable_category="Ореол имени"
))

register(ItemDef(
    key="lego_flair_flame", name="Огненный ореал", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FLAIR,
    emoji="🔥", desc="🔥 Огненный ореал рядом с именем.",
    sell_price=0, category="Косметика-Огонь", readable_category="Ореол имени"
))

register(ItemDef(
    key="lego_flair_arch", name="Архейский ореал", rarity=ItemRarity.LEGENDARY, slot=ItemSlot.FLAIR,
    emoji="🌸", desc="🌸 Нежный розовый ореал имени.",
    sell_price=0, category="Косметика-Природа", readable_category="Ореол имени"
))

register(ItemDef(
    key="pet_rename", name="Переименовать питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="📝", desc="Переименовать питомца бесплатно 1 раз.",
    price=0, sell_price=0, category="Косметика-Питомец", readable_category="Сервис"
))

# ─── Платная косметика (косметика лавок) ─────────────────────────────────────

register(ItemDef(
    key="xp_boost_24h", name="Форсированное обучение", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="🔮", desc="×2 XP на 24 часа.",
    price=15000, category="Косметика-Ускорение", readable_category="Бонус"
))

register(ItemDef(
    key="streak_guard", name="Хранитель стрика", rarity=ItemRarity.COMMON, slot=ItemSlot.FLAIR,
    emoji="🛡️", desc="Защита стрика от разрыва 1 раз.",
    price=500, category="Косметика-Защита", readable_category="Бонус"
))

register(ItemDef(
    key="mora_shield", name="Щит Моры", rarity=ItemRarity.COMMON, slot=ItemSlot.FLAIR,
    emoji="💰", desc="Не терять мору при первой потере в казино за день.",
    price=350, category="Косметика-Щит", readable_category="Бонус"
))

register(ItemDef(
    key="lucky_sign", name="Знак удачи", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="🍀", desc="Порог пити −5 на 7 дней.",
    price=1500, category="Косметика-Удача", readable_category="Бонус"
))

# ─── Платная косметика за кристаллы (CRYSTAL_COSMETICS) ─────────────────────────

register(ItemDef(
    key="shadow_mode", name="Режим тени", rarity=ItemRarity.EPIC, slot=ItemSlot.FLAIR,
    emoji="🕶️", desc="Скрыть баланс Моры от других в таблице лидеров.",
    crystals=180, category="Косметика-Режим", readable_category="Кристальная косметика", sell_price=0
))

register(ItemDef(
    key="name_glow", name="Свечение имени", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="✨", desc="Ореал вокруг имени в Mini App.",
    crystals=200, category="Косметика-Свечение", readable_category="Кристальная косметика", sell_price=0
))

register(ItemDef(
    key="pet_emoji_status", name="Эмодзи-статус питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="😎", desc="Эмодзи рядом с именем питомца.",
    crystals=150, category="Косметика-Эмодзи", readable_category="Кристальная косметика", sell_price=0
))

# ─── Цвета питомца (PET_COLOR_CATALOG) ────────────────────────────────────────

register(ItemDef(
    key="pet_color_red", name="Алый цвет питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="❤️", desc="Покрасить питомца в алый цвет.",
    price=800, category="Косметика-Питомец", readable_category="Цвет питомца"
))

register(ItemDef(
    key="pet_color_blue", name="Синий цвет питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="💙", desc="Покрасить питомца в синий цвет.",
    price=800, category="Косметика-Питомец", readable_category="Цвет питомца"
))

register(ItemDef(
    key="pet_color_gold", name="Золотой цвет питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="💛", desc="Покрасить питомца в золотой цвет.",
    price=1000, category="Косметика-Питомец", readable_category="Цвет питомца"
))

register(ItemDef(
    key="pet_color_green", name="Зелёный цвет питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="💚", desc="Покрасить питомца в зелёный цвет.",
    price=800, category="Косметика-Питомец", readable_category="Цвет питомца"
))

register(ItemDef(
    key="pet_color_purple", name="Фиолетовый цвет питомца", rarity=ItemRarity.RARE, slot=ItemSlot.FLAIR,
    emoji="💜", desc="Покрасить питомца в фиолетовый цвет.",
    price=1000, category="Косметика-Питомец", readable_category="Цвет питомца"
))

register(ItemDef(
    key="pet_color_white", name="Белый цвет питомца", rarity=ItemRarity.COMMON, slot=ItemSlot.FLAIR,
    emoji="🤍", desc="Покрасить питомца в белый цвет.",
    price=600, category="Косметика-Питомец", readable_category="Цвет питомца"
))
