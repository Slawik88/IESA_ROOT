"""
shared_prices.py — единый источник цен для бота и Mini App.

Импортируется из:
  - PredvestnikBot/config.py           (бот)
  - IESA_ROOT/IESA_ROOT/miniapp_views.py  (Django API)
"""

# ─── Гача (Молитвы) ───────────────────────────────────────────────────────────
GACHA_SINGLE_PRICE   = 160   # обычная крутка (стандартный баннер)
GACHA_MULTI_PRICE    = 1440  # ×10 со скидкой ~10%
GACHA_SINGLES_SINGLE = 150   # «одиночный» баннер ×1
GACHA_SINGLES_MULTI  = 1350  # «одиночный» баннер ×10
GACHA_PITY_MAX       = 50    # гарантия 5★ каждые N круток

# ─── Магазин: VIP ─────────────────────────────────────────────────────────────
PRICE_VIP = 500

# ─── Магазин: Рамки профиля ───────────────────────────────────────────────────
# Формат: (key, emoji, label, price)
FRAMES_CATALOG = [
    ("default",  "🔰", "Стандарт",   0),
    ("warrior",  "⚔️", "Воин",        500),
    ("king",     "👑", "Король",      1000),
    ("moon",     "🌙", "Ночной",      800),
    ("fire",     "🔥", "Огненный",    700),
    ("diamond",  "💎", "Алмазный",    1200),
    ("star",     "⭐", "Звёздный",    600),
]

# ─── Магазин: Косметика ───────────────────────────────────────────────────────
# Формат: (key, emoji, label, price, description)
COSMETICS_CATALOG = [
    ("custom_title",     "🏷",  "Кастомный титул",       3000, "Текст рядом с ником"),
    ("pet_color",        "🎨",  "Цвет имени питомца",    2000, "Выбор из 6 цветов"),
    ("pet_emoji_status", "😎",  "Эмодзи-статус питомца", 1500, "Эмодзи рядом с именем"),
]

# ─── Еда для питомца ──────────────────────────────────────────────────────────
FOOD_ITEMS = {
    "краб":  {"name": "Золотой краб",  "emoji": "🦀", "price": 50, "fatigue": 40},
    "лапша": {"name": "Лапша путника", "emoji": "🍜", "price": 25, "fatigue": 20},
}

# ─── Зелья (Расходники) ───────────────────────────────────────────────────────
# Формат: key → {name, emoji, price, buff_type, buff_amount, duration_minutes, description}
POTIONS_CATALOG = {
    "str_potion":     {"name": "Зелье Силы",          "emoji": "⚔️", "price": 200,  "buff_type": "atk", "buff_amount": 15, "duration": 60,  "desc": "+15 ATK на 1 час"},
    "def_potion":     {"name": "Зелье Защиты",        "emoji": "🛡️", "price": 150,  "buff_type": "def", "buff_amount": 20, "duration": 60,  "desc": "+20 DEF на 1 час"},
    "hp_potion":      {"name": "Зелье Здоровья",      "emoji": "❤️", "price": 180,  "buff_type": "hp",  "buff_amount": 50, "duration": 90,  "desc": "+50 HP на 1.5 часа"},
    "str_superior":   {"name": "Зелье Силы Superior", "emoji": "⚔️✨", "price": 0,    "buff_type": "atk", "buff_amount": 30, "duration": 120, "desc": "+30 ATK на 2 часа (только из гачи)"},
    "def_superior":   {"name": "Зелье Защиты Superior","emoji": "🛡️✨", "price": 0,   "buff_type": "def", "buff_amount": 40, "duration": 120, "desc": "+40 DEF на 2 часа (только из гачи)"},
}

# ─── Узы (облигации) ─────────────────────────────────────────────────────────
# Формат: key → {name, base_price}
BOND_DEFAULTS = {
    "mondstadt": {"name": "🌸 Мондштадт", "base_price": 100},
    "inazuma":   {"name": "⚡ Инадзума",   "base_price": 150},
}

# ─── Кастомный титул ─────────────────────────────────────────────────────────
CUSTOM_TITLE_PRICE = 10_000  # мора за установку/смену кастомного титула

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
    # Обычные (⚔️ Снаряжение)
    "cmn_sword":      {"slot": "weapon",   "atk": 10, "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Тупой, но вполне годится",                "sell": 20},
    "cmn_bow":        {"slot": "weapon",   "atk": 8,  "def_val": 0,  "hp": 0,   "crit_rate": 0.01, "desc": "Стреляет куда-то туда",                   "sell": 18},
    "cmn_book":       {"slot": "artifact", "atk": 5,  "def_val": 0,  "hp": 0,   "crit_rate": 0.02, "desc": "Потрёпанный, с заклинанием на удачу",     "sell": 22},
    "cmn_ring":       {"slot": "armor",    "atk": 0,  "def_val": 10, "hp": 20,  "crit_rate": 0.0,  "desc": "Дешёвый, но надёжный",                    "sell": 20},
    "cmn_shield":     {"slot": "armor",    "atk": 0,  "def_val": 15, "hp": 0,   "crit_rate": 0.0,  "desc": "Ржавый, но блокирует удары",              "sell": 25},
    # Редкие (🎨 Кастомизация)
    "rare_crown":     {"slot": "artifact", "atk": 15, "def_val": 10, "hp": 0,   "crit_rate": 0.0,  "desc": "Позолоченная корона — власть и сила",     "sell": 100},
    "rare_catalyst":  {"slot": "weapon",   "atk": 20, "def_val": 0,  "hp": 0,   "crit_rate": 0.03, "desc": "Магический катализатор с рунами",         "sell": 90},
    "rare_cape":      {"slot": "armor",    "atk": 0,  "def_val": 20, "hp": 50,  "crit_rate": 0.0,  "desc": "Алый плащ с защитными чарами",            "sell": 95},
    "rare_gem":       {"slot": "artifact", "atk": 0,  "def_val": 15, "hp": 0,   "crit_rate": 0.05, "desc": "Сапфир полуночи — усиливает крит",        "sell": 80},
    # Легендарные (⚔️ Снаряжение — лучшее)
    "lego_gnosis":    {"slot": "weapon",   "atk": 50, "def_val": 0,  "hp": 0,   "crit_rate": 0.05, "desc": "Гнозис Балладеера — мощь Архонта",        "sell": 0},
    "lego_scepter":   {"slot": "weapon",   "atk": 60, "def_val": 10, "hp": 0,   "crit_rate": 0.0,  "desc": "Скипетр Дендро Архонта",                  "sell": 0},
    "lego_pantalone": {"slot": "armor",    "atk": 0,  "def_val": 50, "hp": 200, "crit_rate": 0.0,  "desc": "Маска Панталоне — абсолютная защита",     "sell": 0},
    "lego_abyss":     {"slot": "artifact", "atk": 30, "def_val": 0,  "hp": 0,   "crit_rate": 0.10, "desc": "Корона Бездны — усиливает крит",          "sell": 0},
    "lego_fatui":     {"slot": "weapon",   "atk": 45, "def_val": 0,  "hp": 100, "crit_rate": 0.08, "desc": "Перст Предвестника — несёт смерть врагам","sell": 0},
    # Зелья (🧪 Расходники)
    "str_potion":     {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Силы: +15 ATK на 1 час",           "sell": 50},
    "def_potion":     {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Защиты: +20 DEF на 1 час",        "sell": 40},
    "hp_potion":      {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Здоровья: +50 HP на 1.5 часа",     "sell": 45},
    "str_superior":   {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Силы Superior: +30 ATK на 2 часа",  "sell": 100},
    "def_superior":   {"slot": "potion",    "atk": 0,  "def_val": 0,  "hp": 0,   "crit_rate": 0.0,  "desc": "Зелье Защиты Superior: +40 DEF на 2 часа","sell": 80},
}

# ─── Ежедневный чекин ────────────────────────────────────────────────────────
# День (1-20) → награда в мора
CHECKIN_REWARDS = {
    1: 30,  2: 30,  3: 35,  4: 35,  5: 60,
    6: 40,  7: 40,  8: 45,  9: 45,  10: 80,
    11: 50, 12: 50, 13: 55, 14: 55, 15: 100,
    16: 60, 17: 60, 18: 70, 19: 70, 20: 150,
}
# Дни-чекпоинты (стрик сохраняется при пропуске)
CHECKIN_CHECKPOINTS = {5, 10, 15, 20}
