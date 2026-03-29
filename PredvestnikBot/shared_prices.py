"""
shared_prices.py — единый источник цен для бота и Mini App.

Импортируется из:
  - PredvestnikBot/config.py           (бот)
  - IESA_ROOT/IESA_ROOT/miniapp_views.py  (Django API)
"""

# ─── Гача (Молитвы) ───────────────────────────────────────────────────────────
GACHA_SINGLE_PRICE   = 80    # обычная крутка (стандартный баннер) [РЕБАЛАНС: 120→80]
GACHA_MULTI_PRICE    = 700   # ×10 со скидкой [РЕБАЛАНС: 1000→700]
GACHA_SINGLES_SINGLE = 70    # «одиночный» баннер ×1 [РЕБАЛАНС: 110→70]
GACHA_SINGLES_MULTI  = 650   # «одиночный» баннер ×10 [РЕБАЛАНС: 950→650]
GACHA_PITY_MAX       = 40    # гарантия 5★ каждые N круток [РЕБАЛАНС: 50→40]

# ─── Магазин: VIP ─────────────────────────────────────────────────────────────
PRICE_VIP = 2000  # [РЕБАЛАНС: 300→2000 — истинно премиальный статус]

# ─── Пропуск чистки ──────────────────────────────────────────────────────────
CLEANUP_PASS_PRICE = 1500  # Откуп от 1 чистки (требует одобрения владельца)

# ─── Магазин: Рамки профиля ───────────────────────────────────────────────────
# Формат: (key, emoji, label, price) [РЕБАЛАНС: все цены снижены ~в 2 раза]
FRAMES_CATALOG = [
    ("default",   "🔰",  "Стандарт",     0),
    ("warrior",   "⚔️",  "Воин",          250),   # было 500
    ("king",      "👑",  "Король",        500),   # было 1000
    ("moon",      "🌙",  "Ночной",        400),   # было 800
    ("fire",      "🔥",  "Огненный",      350),   # было 700
    ("diamond",   "💎",  "Алмазный",      600),   # было 1200
    ("star",      "⭐",  "Звёздный",      300),   # было 600
    ("sakura",    "🌸",  "Сакура",        1200),
    ("abyss",     "🌀",  "Бездна",        1500),
    ("fatui",     "⚡",  "Предвестник",   1800),
    ("angel",     "🕊️",  "Крылья ветра",  2200),
    ("champion",  "🏆",  "Чемпион",       2800),
    ("celestia",  "🏰",  "Целестия",      3500),
]

# ─── Магазин: Косметика ───────────────────────────────────────────────────────
# Формат: (key, emoji, label, price, description) [РЕБАЛАНС: цены снижены в 2-3 раза]
COSMETICS_CATALOG = [
    ("custom_title",      "🏷",  "Кастомный титул",         1200, "Текст рядом с ником"),        # было 3000
    ("pet_emoji_status",  "😎",  "Эмодзи-статус питомца",   600,  "Эмодзи рядом с именем"),     # было 1500
    ("xp_boost_24h",      "🔮",  "Форсированное обучение",  1200, "×2 XP на 24 часа"),
    ("streak_guard",      "🛡️",  "Хранитель стрика",        500,  "Защита стрика от разрыва 1 раз"),
    ("expedition_boost",  "🗺️",  "Экспедиционный допинг",   200,  "+20% к наградам экспедиции (3 использования)"),
    ("mora_shield",       "💰",  "Щит Моры",                350,  "Не терять мору при первой потере в казино за день"),
    ("lucky_sign",        "🍀",  "Знак удачи",              1500, "Порог пити −5 на 7 дней"),
    ("name_glow",         "✨",  "Свечение имени",           900,  "Ореол вокруг имени в Mini App"),
]

# ─── Магазин: Цвета питомца ───────────────────────────────────────────────────
# Формат: (key, emoji+label, price) — покупка меняет pets.color_name
PET_COLOR_CATALOG = [
    ("pet_color_red",    "❤️ Алый",         800),
    ("pet_color_blue",   "💙 Синий",        800),
    ("pet_color_gold",   "💛 Золотой",      1000),
    ("pet_color_green",  "💚 Зелёный",      800),
    ("pet_color_purple", "💜 Фиолетовый",   1000),
    ("pet_color_white",  "🤍 Белый",        600),
]

# ─── Еда для питомца ──────────────────────────────────────────────────────────
FOOD_ITEMS = {
    "краб":       {"name": "Золотой краб",      "emoji": "🦀", "price": 40, "fatigue": 40},  # было 50
    "лапша":      {"name": "Лапша путника",     "emoji": "🍜", "price": 20, "fatigue": 20},  # было 25
    "деликатес":  {"name": "Морской деликатес", "emoji": "🦞", "price": 80, "fatigue": 80},
    "гриб":       {"name": "Гриб Слепого Ка",   "emoji": "🍄", "price": 35, "fatigue": 35},
}

# ─── Зелья (Расходники) ───────────────────────────────────────────────────────
# Формат: key → {name, emoji, price, buff_type, buff_amount, duration_minutes, description}
POTIONS_CATALOG = {
    "str_potion":     {"name": "Зелье Силы",          "emoji": "⚔️", "price": 120,  "buff_type": "atk", "buff_amount": 15, "duration": 60,  "desc": "+15 ATK на 1 час"},        # было 200
    "def_potion":     {"name": "Зелье Защиты",        "emoji": "🛡️", "price": 90,   "buff_type": "def", "buff_amount": 20, "duration": 60,  "desc": "+20 DEF на 1 час"},        # было 150
    "hp_potion":      {"name": "Зелье Здоровья",      "emoji": "❤️", "price": 100,  "buff_type": "hp",  "buff_amount": 50, "duration": 90,  "desc": "+50 HP на 1.5 часа"},      # было 180
    "str_superior":   {"name": "Зелье Силы Superior", "emoji": "⚔️✨", "price": 0,    "buff_type": "atk", "buff_amount": 30, "duration": 120, "desc": "+30 ATK на 2 часа (только из гачи)"},
    "def_superior":   {"name": "Зелье Защиты Superior","emoji": "🛡️✨", "price": 0,   "buff_type": "def", "buff_amount": 40, "duration": 120, "desc": "+40 DEF на 2 часа (только из гачи)"},
}

# ─── Узы (облигации / биржа) ─────────────────────────────────────────────────
# Формат: key → {name, base_price, volatility, cap_mult}
BOND_DEFAULTS = {
    # Blue chips (low vol, 3× cap)
    "mondstadt":  {"name": "📜 Холодный Ветер (Мондштадт)", "base_price": 100, "volatility": 0.08, "cap_mult": 3},
    "liyue":      {"name": "💎 Нефритовый Слиток (Ли Юэ)",  "base_price": 120, "volatility": 0.07, "cap_mult": 3},
    "north_bank": {"name": "🏦 Банк Северного Королевства",  "base_price": 500, "volatility": 0.05, "cap_mult": 3},
    # Mid-caps (vol 14-20%, 5× cap)
    "inazuma":    {"name": "⚡ Вишнёвый Гром (Инадзума)",    "base_price": 150, "volatility": 0.15, "cap_mult": 5},
    "sumeru":     {"name": "🌿 Зелёный Лист (Сумеру)",       "base_price":  90, "volatility": 0.18, "cap_mult": 5},
    "fontaine":   {"name": "💧 Хрустальный Поток (Фонтэн)",  "base_price": 200, "volatility": 0.14, "cap_mult": 5},
    "natlan":     {"name": "🔥 Пламенный Клык (Натлан)",     "base_price": 175, "volatility": 0.20, "cap_mult": 5},
    # High-risk (35% vol, 8× cap)
    "naku_grass": {"name": "🌾 Трава Наку",                   "base_price":  40, "volatility": 0.35, "cap_mult": 8},
    # Meme coins (vol 45-50%, 15-20× cap)
    "itto_coin":  {"name": "🐂 Итто-Коин",                    "base_price":  10, "volatility": 0.50, "cap_mult": 20},
    "dori_corp":  {"name": "💰 Дори-Инвестментс",              "base_price":  25, "volatility": 0.45, "cap_mult": 15},
}

# ─── Банк (вклады) ────────────────────────────────────────────────────────────
BANK_MIN_DEPOSIT = 100
BANK_MAX_DEPOSIT = 10_000
BANK_EARLY_PENALTY_PCT = 0.01   # 1% от суммы при досрочном снятии

BANK_PLANS = {
    "short":  {"days": 3,  "rate": 0.015, "label": "📅 3 дня  — 1.5%"},
    "medium": {"days": 7,  "rate": 0.04,  "label": "📆 7 дней — 4%"},
    "long":   {"days": 14, "rate": 0.10,  "label": "📋 14 дней — 10%"},
}

# ─── Рулетка ─────────────────────────────────────────────────────────────────
ROULETTE_MIN_BET = 10
ROULETTE_MAX_BET = 500
ROULETTE_TAX     = 0.05   # 5% комиссия с выигрыша в казну
ROULETTE_ITEM_CHANCE = 0.18  # 18% шанс бонусного предмета при выигрыше

# Призовой пул рулетки: (item_key, item_name, item_type, weight)
# item_type: "food" | "coupon" | "buff" | "cosmetic"
ROULETTE_PRIZE_POOL = [
    ("лапша",        "🍜 Лапша путника",               "food",    30),
    ("гриб",         "🍄 Гриб Слепого Ка",             "food",    20),
    ("краб",         "🦀 Золотой краб",                "food",    10),
    ("деликатес",    "🦞 Морской деликатес",            "food",     5),
    ("exp_boost_sm", "🗺️ Ускорение экспедиции S",      "coupon",  25),
    ("quest_reroll", "🔄 Купон реролла задания",        "coupon",  18),
    ("exp_boost_md", "🗺️✨ Ускорение экспедиции M",    "coupon",   8),
    ("pet_rename",   "✏️ Купон переименования питомца", "coupon",   5),
    ("str_potion",   "⚔️ Зелье Силы",                  "buff",    20),
    ("def_potion",   "🛡️ Зелье Защиты",               "buff",    20),
    ("hp_potion",    "❤️ Зелье Здоровья",             "buff",    20),
    ("cmn_xp_shard", "✨ Осколок Опыта",               "consume", 15),
    ("cmn_herb",     "🌿 Трава Сесилии",               "consume", 12),
    ("rare_mora_bag","💰 Мешок Моры",                  "consume",  6),
]

# ─── Кастомный титул ─────────────────────────────────────────────────────────
CUSTOM_TITLE_PRICE = 4_000  # мора за установку/смену кастомного титула [РЕБАЛАНС: 10,000→4,000]

# ─── Метаданные предметов гачи ────────────────────────────────────────────────
# Формат: item_key → {slot, atk, def_val, hp, crit_rate, desc, sell}
# slot: "weapon" | "armor" | "artifact" | None
# sell: цена утилизации (0 = легендарку нельзя продать)
ITEM_METADATA = {
    # Мусор (📦 Разное)
    "junk_stone":     {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Камень из кармана хиличурла",             "sell": 5},
    "junk_stick":     {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Кривая палка путника",                    "sell": 3},
    "junk_dust":      {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Пыль от забытых заклинаний",              "sell": 2},
    "junk_bone":      {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Кость, выброшенная хиличурлом",           "sell": 4},
    "junk_mushroom":  {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Не ешь. Серьёзно.",                       "sell": 3},
    # Обычные (⚔️ Снаряжение) [РЕБАЛАНС: статы увеличены для лучшего прогресса]
    "cmn_sword":      {"slot": "weapon",   "atk": 15, "def_val": 0,  "hp": 0,   "crit_rate": 0.02, "desc": "Тупой, но вполне годится",                "sell": 20},  # было: 10 ATK, 0 CRIT
    "cmn_bow":        {"slot": "weapon",   "atk": 12, "def_val": 0,  "hp": 0,   "crit_rate": 0.02, "desc": "Стреляет куда-то туда",                   "sell": 18},  # было: 8 ATK, 1% CRIT
    "cmn_book":       {"slot": "artifact", "atk": 8,  "def_val": 0,  "hp": 0,   "crit_rate": 0.03, "desc": "Потрёпанный, с заклинанием на удачу",     "sell": 22},  # было: 5 ATK, 2% CRIT
    "cmn_ring":       {"slot": "armor",    "atk": 0,  "def_val": 15, "hp": 30,  "crit_rate": 0.0,  "desc": "Дешёвый, но надёжный",                    "sell": 20},  # было: 10 DEF, 20 HP
    "cmn_shield":     {"slot": "armor",    "atk": 0,  "def_val": 20, "hp": 0,   "crit_rate": 0.0,  "desc": "Ржавый, но блокирует удары",              "sell": 25},  # было: 15 DEF
    # Редкие (🎨 Кастомизация) [РЕБАЛАНС: статы увеличены для значимого прыжка в силе]
    "rare_crown":     {"slot": "artifact", "atk": 25, "def_val": 15, "hp": 0,   "crit_rate": 0.04, "desc": "Позолоченная корона — власть и сила",     "sell": 100}, # было: 15 ATK, 10 DEF
    "rare_catalyst":  {"slot": "weapon",   "atk": 30, "def_val": 0,  "hp": 0,   "crit_rate": 0.04, "desc": "Магический катализатор с рунами",         "sell": 90},  # было: 20 ATK, 3% CRIT
    "rare_cape":      {"slot": "armor",    "atk": 0,  "def_val": 25, "hp": 80,  "crit_rate": 0.0,  "desc": "Алый плащ с защитными чарами",            "sell": 95},  # было: 20 DEF, 50 HP
    "rare_gem":       {"slot": "artifact", "atk": 0,  "def_val": 20, "hp": 0,   "crit_rate": 0.06, "desc": "Сапфир полуночи — усиливает крит",        "sell": 80},  # было: 15 DEF, 5% CRIT
    # Легендарные (⚔️ Снаряжение — лучшее) [РЕБАЛАНС: конечная мощь для эндгейма]
    "lego_gnosis":    {"slot": "weapon",   "atk": 60, "def_val": 0,  "hp": 0,   "crit_rate": 0.08, "desc": "Гнозис Балладеера — мощь Архонта",        "sell": 0},  # было: 50 ATK, 5% CRIT
    "lego_scepter":   {"slot": "weapon",   "atk": 70, "def_val": 15, "hp": 0,   "crit_rate": 0.06, "desc": "Скипетр Дендро Архонта",                  "sell": 0},  # было: 60 ATK, 10 DEF
    "lego_pantalone": {"slot": "armor",    "atk": 0,  "def_val": 60, "hp": 300, "crit_rate": 0.0,  "desc": "Маска Панталоне — абсолютная защита",     "sell": 0},  # было: 50 DEF, 200 HP
    "lego_abyss":     {"slot": "artifact", "atk": 45, "def_val": 0,  "hp": 0,   "crit_rate": 0.12, "desc": "Корона Бездны — усиливает крит",          "sell": 0},  # было: 30 ATK, 10% CRIT
    "lego_fatui":     {"slot": "weapon",   "atk": 55, "def_val": 0,  "hp": 150, "crit_rate": 0.10, "desc": "Перст Предвестника — несёт смерть врагам","sell": 0},  # было: 45 ATK, 100 HP, 8% CRIT
    # Зелья (🧪 Расходники)
    "str_potion":     {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Силы: +15 ATK на 1 час",           "sell": 50},
    "def_potion":     {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Защиты: +20 DEF на 1 час",        "sell": 40},
    "hp_potion":      {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Здоровья: +50 HP на 1.5 часа",     "sell": 45},
    "str_superior":   {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Силы Superior: +30 ATK на 2 часа",  "sell": 100},
    "def_superior":   {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Защиты Superior: +40 DEF на 2 часа","sell": 80},
    # Мгновенный опыт / мора (📦 Расходники — XP/🪙)
    "cmn_xp_shard":   {"slot": "consume",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Осколок опыта: мгновенно +25 XP",         "sell": 15},
    "rare_xp_crystal":{"slot": "consume",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Кристалл опыта: мгновенно +150 XP",       "sell": 60},
    "rare_mora_bag":  {"slot": "consume",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Мешок Моры: мгновенно +120 🪙",            "sell": 55},
    # Косметика Mini App (🎨 Flair)
    "lego_flair_star": {"slot": "flair",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "⭐ Золотой ореол рядом с именем",          "sell": 0},
    "lego_flair_void": {"slot": "flair",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "🌌 Тёмно-мистический эффект имени",        "sell": 0},
    "lego_flair_flame":{"slot": "flair",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "🔥 Огненный ореол рядом с именем",         "sell": 0},
    "lego_flair_arch": {"slot": "flair",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "🌸 Нежный розовый ореол имени",            "sell": 0},
    # Новые предметы гачи
    "junk_feather":    {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Перо химеры-штормпиха",                   "sell": 4},
    "junk_rope":       {"slot": None,       "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Оборванная верёвка странника",             "sell": 3},
    "cmn_herb":        {"slot": "consume",  "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Трава Сесилии: мгновенно +15 🪙",          "sell": 8},
    "cmn_quill":       {"slot": "artifact", "atk": 8,  "def_val": 0,  "hp": 15,  "crit_rate": 0.02, "desc": "Перо ученика с магическими чарами",        "sell": 20},
    "cmn_talisman":    {"slot": "artifact", "atk": 0,  "def_val": 5,  "hp": 0,   "crit_rate": 0.015,"desc": "Амулет с рунами удачи",                    "sell": 18},
    "rare_amulet":     {"slot": "artifact", "atk": 0,  "def_val": 20, "hp": 0,   "crit_rate": 0.08, "desc": "Кармин змеи — усиливает криты",            "sell": 85},
    "rare_mora_chest": {"slot": "consume",  "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Красный конверт: мгновенно +250 🪙",       "sell": 90},
    "rare_lance":      {"slot": "weapon",   "atk": 35, "def_val": 0,  "hp": 0,   "crit_rate": 0.05, "desc": "Лазурное копьё воина ветров",              "sell": 85},
    "lego_raiden":     {"slot": "weapon",   "atk": 80, "def_val": 0,  "hp": 0,   "crit_rate": 0.12, "desc": "Клинок Ей — мощь Инадзумы",               "sell": 0},
    "lego_jade":       {"slot": "artifact", "atk": 20, "def_val": 40, "hp": 0,   "crit_rate": 0.15, "desc": "Нефритовое зерцало Архонта",               "sell": 0},
    # Блок 5: купоны ускорения и переименования
    "exp_boost_sm":    {"slot": "coupon",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Ускорение экспедиции −30 мин",             "sell": 15,  "boost_minutes": 30},
    "exp_boost_md":    {"slot": "coupon",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Ускорение экспедиции −2 часа",             "sell": 60,  "boost_minutes": 120},
    "exp_boost_lg":    {"slot": "coupon",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Ускорение экспедиции −50% времени",        "sell": 200, "boost_pct": 0.5},
    "quest_reroll":    {"slot": "coupon",   "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Сбросить и получить новый квест",          "sell": 25},
    "pet_rename":      {"slot": "flair",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Переименовать питомца бесплатно 1 раз",    "sell": 0},
}

# ─── Ежедневный чекин ────────────────────────────────────────────────────────
# День (1-20) → награда в мора [РЕБАЛАНС: увеличены в 3-4 раза для сбалансированной экономики]
CHECKIN_REWARDS = {
    1: 100, 2: 110, 3: 120, 4: 130, 5: 300,    # было: 30,30,35,35,60
    6: 140, 7: 150, 8: 160, 9: 170, 10: 500,   # было: 40,40,45,45,80
    11: 180, 12: 190, 13: 200, 14: 210, 15: 700,   # было: 50,50,55,55,100
    16: 220, 17: 250, 18: 280, 19: 320, 20: 1000,   # было: 60,60,70,70,150
}
# Дни-чекпоинты (стрик сохраняется при пропуске)
CHECKIN_CHECKPOINTS = {5, 10, 15, 20}
