"""core/cosmetics.py — Косметика профиля (конструктор внешнего вида).

Только КОСМЕТИКА, без игрового преимущества. Без внешних зависимостей.

Модель цены гибкая:
  price = список ВАРИАНТОВ оплаты (OR). Каждый вариант — dict валюта→сумма (AND внутри).
    Валюты: "mora" 🪙 | "diamonds" 💎 | "dark_mora" 🌑 | "zarniki" ✨.
    price=None → в магазине не продаётся (выдаётся источником: VIP/БП/ачивка).
  vip_required: покупка в магазине доступна только при активной VIP.
  source: "shop" | "vip" (даётся с покупкой VIP) | "bp" (платный трек БП) | "reward" (ачивка/ивент).
  slot: "name_glow" (ореол ника, CSS) | "avatar_frame" (рамка аватара, CSS) | "title" (титул, ТЕКСТ — работает и в боте)
        | "avatar_halo" (гало/свечение вокруг аватара, CSS) | "profile_bg" (фон/баннер карточки, CSS)
        | "card_fx" (анимированные частицы поверх карточки, CSS).

Визуальные слоты (name_glow/avatar_frame/avatar_halo/profile_bg/card_fx) рендерятся
только на сайте (CSS). Титул — текст, поэтому показывается и на сайте, и в карточке профиля бота.
"""

COSMETIC_SLOTS = (
    "name_glow", "avatar_frame", "title",
    "avatar_halo", "profile_bg", "card_fx",
)

# Порядок редкостей для сортировки/цвета в UI
RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3, "mythic": 4}

COSMETICS: dict[str, dict] = {
    # ── Ореол имени (CSS, веб) ───────────────────────────────────────────────
    "glow_silver": {
        "name": "Серебряный ореол", "slot": "name_glow", "rarity": "common",
        "css": "glow-silver", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Мягкое серебристое свечение вокруг ника. Доступно всем.",
    },
    "glow_gold": {
        "name": "Золотое сияние", "slot": "name_glow", "rarity": "rare",
        "css": "glow-gold", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Тёплый золотой ореол. Знак статуса.",
    },
    "glow_crimson": {
        "name": "Багровое пламя", "slot": "name_glow", "rarity": "epic",
        "css": "glow-crimson", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 280, "diamonds": 9}],
        "desc": "Зловещее багровое свечение из глубин Бездны.",
    },
    "glow_prism": {
        "name": "Призматический ореол", "slot": "name_glow", "rarity": "legendary",
        "css": "glow-prism", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 20,
        "desc": "Переливающийся спектр. Награда платного трека БП (с 20 уровня).",
    },
    "glow_rift": {
        "name": "Разлом Бездны", "slot": "name_glow", "rarity": "mythic",
        "css": "glow-rift", "vip_required": False, "source": "reward", "price": None,
        "desc": "Имя пылает разломом: фиолет–багрянец–золото в вечном течении. Награда за достижения.",
    },

    # ── Рамка аватара (CSS, веб) ─────────────────────────────────────────────
    "frame_bronze": {
        "name": "Бронзовая оправа", "slot": "avatar_frame", "rarity": "common",
        "css": "frame-bronze", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Простая бронзовая рамка вокруг аватара.",
    },
    "frame_neon": {
        "name": "Неоновый контур", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-neon", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Пульсирующая неоновая обводка аватара.",
    },
    "frame_abyss": {
        "name": "Оправа Бездны", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-abyss", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 280, "diamonds": 9}],
        "desc": "Рамка из застывшей Тёмной Моры — нестабильная энергия Бездны.",
    },
    "frame_celestial": {
        "name": "Небесная оправа", "slot": "avatar_frame", "rarity": "legendary",
        "css": "frame-celestial", "vip_required": False, "source": "vip", "price": None,
        "desc": "Светящаяся небесная рамка. Выдаётся с покупкой VIP.",
    },
    "frame_omen": {
        "name": "Оправа Предвестника", "slot": "avatar_frame", "rarity": "mythic",
        "css": "frame-omen", "vip_required": False, "source": "reward", "price": None,
        "desc": "Вращающийся ореол разлома вокруг аватара. Награда за достижения.",
    },

    # ── Титул (текст, бот + веб) ─────────────────────────────────────────────
    "title_wanderer": {
        "name": "Странник Пустошей", "slot": "title", "rarity": "common",
        "text": "Странник Пустошей", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 40, "mora": 3000}],
        "desc": "Текстовый титул под ником. Виден и в чате, и на сайте.",
    },
    "title_patron": {
        "name": "Меценат", "slot": "title", "rarity": "rare",
        "text": "Меценат", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 110, "diamonds": 5}],
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
    "title_omen": {
        "name": "Предвестник", "slot": "title", "rarity": "mythic",
        "text": "Предвестник", "vip_required": False, "source": "reward", "price": None,
        "desc": "Мифический титул для тех, кто прошёл весь путь. Награда за достижения.",
    },

    # ── Гало вокруг аватара (CSS, веб) ───────────────────────────────────────
    "halo_glow": {
        "name": "Тёплое гало", "slot": "avatar_halo", "rarity": "common",
        "css": "halo-glow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Мягкое тёплое свечение по контуру аватара. Доступно всем.",
    },
    "halo_pulse": {
        "name": "Пульсирующий ореол", "slot": "avatar_halo", "rarity": "rare",
        "css": "halo-pulse", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Ритмично пульсирующее кольцо света вокруг аватара.",
    },
    "halo_runic": {
        "name": "Рунический круг", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-runic", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 280, "diamonds": 9}],
        "desc": "Вращающийся круг древних рун вокруг аватара.",
    },
    "halo_aurora": {
        "name": "Аврора", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-aurora", "vip_required": False, "source": "vip", "price": None,
        "desc": "Переливы северного сияния вокруг аватара. Даётся с покупкой VIP.",
    },
    "halo_celestial": {
        "name": "Небесный нимб", "slot": "avatar_halo", "rarity": "legendary",
        "css": "halo-celestial", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 30,
        "desc": "Золотой нимб с лучами. Награда платного трека БП (с 30 уровня).",
    },
    "halo_void": {
        "name": "Кольцо Бездны", "slot": "avatar_halo", "rarity": "mythic",
        "css": "halo-void", "vip_required": False, "source": "reward", "price": None,
        "desc": "Тёмное кольцо с багровыми всполохами. Награда за достижения.",
    },

    # ── Фон / баннер карточки профиля (CSS, веб) ─────────────────────────────
    "pbg_carbon": {
        "name": "Карбон", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-carbon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Строгий карбоновый фон карточки профиля.",
    },
    "pbg_nebula": {
        "name": "Туманность", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-nebula", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Космическая туманность фоном за твоей карточкой.",
    },
    "pbg_abyss": {
        "name": "Бездна", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-abyss", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 280, "diamonds": 9}],
        "desc": "Глубокий фон Бездны с тёмным градиентом.",
    },
    "pbg_forest": {
        "name": "Изумрудный лес", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-forest", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Глубокий изумрудный лес туманным фоном карточки.",
    },
    "pbg_ocean": {
        "name": "Морская бездна", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-ocean", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Холодные глубины океана за твоей карточкой.",
    },
    "pbg_ember": {
        "name": "Тлеющий вулкан", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Раскалённые угли вулкана тлеют снизу карточки.",
    },
    "pbg_galaxy": {
        "name": "Спираль галактики", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-galaxy", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Фиолетово-синий рукав галактики со звёздной пылью.",
    },
    "pbg_royal": {
        "name": "Королевский бархат", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-royal", "vip_required": False, "source": "vip", "price": None,
        "desc": "Тёмно-пурпурный бархат с золотой каймой. Даётся с покупкой VIP.",
    },
    "pbg_sunrise": {
        "name": "Рассвет", "slot": "profile_bg", "rarity": "legendary",
        "css": "pbg-sunrise", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 40,
        "desc": "Тёплый градиент рассвета. Награда платного трека БП (с 40 уровня).",
    },
    "pbg_legend": {
        "name": "Холст Легенды", "slot": "profile_bg", "rarity": "mythic",
        "css": "pbg-legend", "vip_required": False, "source": "reward", "price": None,
        "desc": "Живой золотисто-чёрный холст. Награда за достижения.",
    },

    # ── Частицы поверх карточки (CSS-анимация, веб) ───────────────────────────
    "cfx_sparks": {
        "name": "Искры", "slot": "card_fx", "rarity": "common",
        "css": "cfx-sparks", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 50, "mora": 4000}],
        "desc": "Лёгкие золотые искры, плавающие над карточкой.",
    },
    "cfx_snow": {
        "name": "Снегопад", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-snow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 140, "diamonds": 6}],
        "desc": "Тихо падающие снежинки поверх профиля.",
    },
    "cfx_embers": {
        "name": "Угольки", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-embers", "vip_required": False, "source": "vip", "price": None,
        "desc": "Поднимающиеся тлеющие угольки. Даётся с покупкой VIP.",
    },
    "cfx_stars": {
        "name": "Звездопад", "slot": "card_fx", "rarity": "epic",
        "css": "cfx-stars", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 280, "diamonds": 9}],
        "desc": "Мерцающие падающие звёзды над карточкой.",
    },
    "cfx_fireflies": {
        "name": "Светлячки", "slot": "card_fx", "rarity": "legendary",
        "css": "cfx-fireflies", "vip_required": False, "source": "bp", "price": None,
        "bp_level": 25,
        "desc": "Тёплые светлячки кружат над профилем. Награда БП (с 25 уровня).",
    },
    "cfx_void_storm": {
        "name": "Шторм Бездны", "slot": "card_fx", "rarity": "mythic",
        "css": "cfx-void-storm", "vip_required": False, "source": "reward", "price": None,
        "desc": "Багровые частицы Бездны в вихре. Награда за достижения.",
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
