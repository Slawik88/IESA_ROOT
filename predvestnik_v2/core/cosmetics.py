"""core/cosmetics.py — Косметика профиля (конструктор внешнего вида).

Только КОСМЕТИКА, без игрового преимущества. Без внешних зависимостей.

Модель цены гибкая:
  price = список ВАРИАНТОВ оплаты (OR). Каждый вариант — dict валюта→сумма (AND внутри).
    Валюты: "mora" 🪙 | "diamonds" 💎 | "dark_mora" 🌑 | "zarniki" ✨.
    price=None → в магазине не продаётся (выдаётся источником: VIP/БП/ачивка).
  vip_required: покупка в магазине доступна только при активной VIP.
  source: "shop" | "vip" (даётся с покупкой VIP) | "bp" (платный трек БП) | "reward" (ачивка/ивент).
  slot: "name_glow" (ореол ника, CSS) | "avatar_frame" (рамка аватара, CSS) | "title" (титул, ТЕКСТ — работает и в боте).

Визуальные слоты (name_glow/avatar_frame) рендерятся только на сайте (CSS).
Титул — текст, поэтому показывается и на сайте, и в карточке профиля бота.
"""

COSMETIC_SLOTS = ("name_glow", "avatar_frame", "title")

# Порядок редкостей для сортировки/цвета в UI
RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3, "mythic": 4}

COSMETICS: dict[str, dict] = {
    # ── Ореол имени (CSS, веб) ───────────────────────────────────────────────
    "glow_silver": {
        "name": "Серебряный ореол", "slot": "name_glow", "rarity": "common",
        "css": "glow-silver", "vip_required": False, "source": "shop",
        "price": [{"mora": 20000}, {"diamonds": 10}],
        "desc": "Мягкое серебристое свечение вокруг ника. Доступно всем.",
    },
    "glow_gold": {
        "name": "Золотое сияние", "slot": "name_glow", "rarity": "rare",
        "css": "glow-gold", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 120}, {"mora": 60000}],
        "desc": "Тёплый золотой ореол. Знак статуса.",
    },
    "glow_crimson": {
        "name": "Багровое пламя", "slot": "name_glow", "rarity": "epic",
        "css": "glow-crimson", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 180}, {"dark_mora": 900}],
        "desc": "Зловещее багровое свечение из глубин Бездны.",
    },
    "glow_prism": {
        "name": "Призматический ореол", "slot": "name_glow", "rarity": "legendary",
        "css": "glow-prism", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 20,
        "desc": "Переливающийся спектр. Награда платного трека БП (с 20 уровня).",
    },

    # ── Рамка аватара (CSS, веб) ─────────────────────────────────────────────
    "frame_bronze": {
        "name": "Бронзовая оправа", "slot": "avatar_frame", "rarity": "common",
        "css": "frame-bronze", "vip_required": False, "source": "shop",
        "price": [{"mora": 25000}],
        "desc": "Простая бронзовая рамка вокруг аватара.",
    },
    "frame_neon": {
        "name": "Неоновый контур", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-neon", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 150}, {"mora": 70000}],
        "desc": "Пульсирующая неоновая обводка аватара.",
    },
    "frame_abyss": {
        "name": "Оправа Бездны", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-abyss", "vip_required": True, "source": "shop",
        "price": [{"dark_mora": 1200, "diamonds": 12}],
        "desc": "Рамка из застывшей Тёмной Моры. Стоит 🌑 и 💎 одновременно.",
    },
    "frame_celestial": {
        "name": "Небесная оправа", "slot": "avatar_frame", "rarity": "legendary",
        "css": "frame-celestial", "vip_required": False, "source": "vip", "price": None,
        "desc": "Светящаяся небесная рамка. Выдаётся с покупкой VIP.",
    },

    # ── Титул (текст, бот + веб) ─────────────────────────────────────────────
    "title_wanderer": {
        "name": "Странник Пустошей", "slot": "title", "rarity": "common",
        "text": "Странник Пустошей", "vip_required": False, "source": "shop",
        "price": [{"mora": 15000}],
        "desc": "Текстовый титул под ником. Виден и в чате, и на сайте.",
    },
    "title_patron": {
        "name": "Меценат", "slot": "title", "rarity": "rare",
        "text": "Меценат", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 100}, {"mora": 40000}],
        "desc": "Титул для щедрых покровителей.",
    },
    "title_abysswalker": {
        "name": "Покоритель Бездны", "slot": "title", "rarity": "epic",
        "text": "Покоритель Бездны", "vip_required": False, "source": "reward", "price": None,
        "desc": "Титул-награда за достижения во Вратах Бездны.",
    },
    "title_legend": {
        "name": "Легенда Сезона", "slot": "title", "rarity": "legendary",
        "text": "Легенда Сезона", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 50,
        "desc": "Эксклюзивный титул платного трека БП (макс. уровень).",
    },
}


def cosmetics_by_slot(slot: str) -> dict[str, dict]:
    """Все косметики данного слота (id → entry)."""
    return {cid: c for cid, c in COSMETICS.items() if c["slot"] == slot}


# ── Приветственные анимации (вход / прелоадер) ──────────────────────────────────
# Выбор «режима» холодного старта. Каждый id → CSS-класс `plm-<id>` на #preloader.
# Дефолт (`scanner`) виден всем; остальные — только при активной VIP (vip_required).
# Чистая косметика, не P2W. Хранится в user_cosmetic_loadout (slot="welcome").
WELCOME_DEFAULT = "scanner"

WELCOME_ANIMATIONS: dict[str, dict] = {
    "scanner": {
        "name": "Сканер сигнатур", "rarity": "common", "vip_required": False,
        "desc": "Бегущие строки синхронизации и золотое проявление ника. Классика.",
    },
    "neon": {
        "name": "Неоновое проявление", "rarity": "rare", "vip_required": True,
        "desc": "Имя вспыхивает неоновым сиянием сквозь дымку.",
    },
    "ripple": {
        "name": "Водяная рябь", "rarity": "rare", "vip_required": True,
        "desc": "Круги расходятся по воде, имя всплывает из глубины.",
    },
    "glitch": {
        "name": "Глитч-портал", "rarity": "epic", "vip_required": True,
        "desc": "RGB-сбой и помехи: имя собирается из цифрового шума.",
    },
    "stardust": {
        "name": "Звёздная пыль", "rarity": "epic", "vip_required": True,
        "desc": "Мерцающая пыль оседает, складываясь в твоё имя.",
    },
}


def welcome_animation(anim_id: str) -> dict | None:
    """Запись приветственной анимации по id (или None)."""
    return WELCOME_ANIMATIONS.get(anim_id)
