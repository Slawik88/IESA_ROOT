"""
shared_prices.py — единый источник цен для бота и Mini App.

Импортируется из:
  - PredvestnikBot/config.py           (бот)
  - IESA_ROOT/IESA_ROOT/miniapp_views.py  (Django API)
"""

# ─── Гача (Молитвы) ───────────────────────────────────────────────────────────
GACHA_SINGLE_PRICE   = 120   # обычная крутка (стандартный баннер) [РЕБАЛАНС: 160→120]
GACHA_MULTI_PRICE    = 1000  # ×10 со скидкой 20% [РЕБАЛАНС: 1440→1000]
GACHA_SINGLES_SINGLE = 110   # «одиночный» баннер ×1 [РЕБАЛАНС: 150→110]
GACHA_SINGLES_MULTI  = 950   # «одиночный» баннер ×10 [РЕБАЛАНС: 1350→950]
GACHA_PITY_MAX       = 40    # гарантия 5★ каждые N круток [РЕБАЛАНС: 50→40]

# ─── Магазин: VIP ─────────────────────────────────────────────────────────────
PRICE_VIP = 300  # [РЕБАЛАНС: 500→300]

# ─── Магазин: Рамки профиля ───────────────────────────────────────────────────
# Формат: (key, emoji, label, price) [РЕБАЛАНС: все цены снижены ~в 2 раза]
FRAMES_CATALOG = [
    ("default",  "🔰", "Стандарт",   0),
    ("warrior",  "⚔️", "Воин",        250),   # было 500
    ("king",     "👑", "Король",      500),   # было 1000
    ("moon",     "🌙", "Ночной",      400),   # было 800
    ("fire",     "🔥", "Огненный",    350),   # было 700
    ("diamond",  "💎", "Алмазный",    600),   # было 1200
    ("star",     "⭐", "Звёздный",    300),   # было 600
]

# ─── Магазин: Косметика ───────────────────────────────────────────────────────
# Формат: (key, emoji, label, price, description) [РЕБАЛАНС: цены снижены в 2-3 раза]
COSMETICS_CATALOG = [
    ("custom_title",     "🏷",  "Кастомный титул",       1200, "Текст рядом с ником"),        # было 3000
    ("pet_color",        "🎨",  "Цвет имени питомца",    800,  "Выбор из 6 цветов"),         # было 2000
    ("pet_emoji_status", "😎",  "Эмодзи-статус питомца", 600,  "Эмодзи рядом с именем"),     # было 1500
]

# ─── Еда для питомца ──────────────────────────────────────────────────────────
FOOD_ITEMS = {
    "краб":  {"name": "Золотой краб",  "emoji": "🦀", "price": 40, "fatigue": 40},  # было 50
    "лапша": {"name": "Лапша путника", "emoji": "🍜", "price": 20, "fatigue": 20},  # было 25
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

# ─── Узы (облигации) ─────────────────────────────────────────────────────────
# Формат: key → {name, base_price}
BOND_DEFAULTS = {
    "mondstadt": {"name": "🌸 Мондштадт", "base_price": 100},
    "inazuma":   {"name": "⚡ Инадзума",   "base_price": 150},
}

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
