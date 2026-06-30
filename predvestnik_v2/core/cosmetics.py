"""core/cosmetics.py — Косметика профиля (конструктор внешнего вида).

Только КОСМЕТИКА, без игрового преимущества. Без внешних зависимостей.

ЦЕНОВАЯ ИЕРАРХИЯ (только ✨ зарники):
  Обычный    → 250 ✨    Редкий    → 440 ✨    Эпический  → 630 ✨
  Легендарный → 820 ✨    Мифический → 1000 ✨

VIP-гейт ТОЛЬКО на отображение (не на покупку):
  Все предметы выше Обычного показываются ТОЛЬКО при активной VIP.
  Покупка доступна без VIP — но до активации VIP косметика «спит».
  При обновлении VIP предмет возвращается без переэкипировки.

price: список вариантов оплаты. price=None → предмет не продаётся (выдаётся
  другим источником: VIP/БП). Все предметы можно купить за зарники.

source: "shop" | "vip" (также даётся при активации VIP, под VIP-гейтом показа) |
  "bp" (также награда платного трека БП) | "reward" (ивент/особое).
  Для всех source предмет ТАКЖЕ продаётся в магазине за зарники.

vip_required: НЕ блокирует ПОКУПКУ. Управляет только is_vip_locked() — показывается
  ли предмет без VIP. Покупателю без VIP показывается предупреждение.

slot: "name_glow" | "avatar_frame" | "title" | "avatar_halo" | "profile_bg" | "card_fx"
Визуальные слоты — только веб. Титул (title) — веб + бот-карточка.
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
        "price": [{"zarniki": 250}],
        "desc": "Мягкое серебристое свечение вокруг ника. Доступно всем.",
    },
    "glow_gold": {
        "name": "Золотое сияние", "slot": "name_glow", "rarity": "rare",
        "css": "glow-gold", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тёплый золотой ореол. Знак статуса. Отображается при активной VIP.",
    },
    "glow_crimson": {
        "name": "Багровое пламя", "slot": "name_glow", "rarity": "epic",
        "css": "glow-crimson", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Зловещее багровое свечение из глубин Бездны. Отображается при активной VIP.",
    },
    "glow_ember": {
        "name": "Тлеющий уголь", "slot": "name_glow", "rarity": "epic",
        "css": "glow-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Спокойное тёплое тление букв. Отображается при активной VIP.",
    },
    "glow_prism": {
        "name": "Призматический ореол", "slot": "name_glow", "rarity": "legendary",
        "css": "glow-prism", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 20,
        "desc": "Переливающийся спектр. Награда БП (уровень 20) или покупка за зарники.",
    },
    "glow_rift": {
        "name": "Разлом Бездны", "slot": "name_glow", "rarity": "mythic",
        "css": "glow-rift", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Имя пылает разломом: фиолет–багрянец–золото. Особая награда или покупка за зарники.",
    },

    # ── Рамка аватара (CSS, веб) ─────────────────────────────────────────────
    "frame_bronze": {
        "name": "Бронзовая оправа", "slot": "avatar_frame", "rarity": "common",
        "css": "frame-bronze", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Простая бронзовая рамка вокруг аватара.",
    },
    "frame_neon": {
        "name": "Неоновый контур", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-neon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Пульсирующая неоновая обводка аватара. Отображается при активной VIP.",
    },
    "frame_abyss": {
        "name": "Оправа Бездны", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Рамка из застывшей Тёмной Моры. Отображается при активной VIP.",
    },
    "frame_iron": {
        "name": "Железная оправа", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-iron", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Прочная стальная окантовка. Отображается при активной VIP.",
    },
    "frame_celestial": {
        "name": "Небесная оправа", "slot": "avatar_frame", "rarity": "legendary",
        "css": "frame-celestial", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 820}],
        "desc": "Светящаяся небесная рамка. Выдаётся с VIP или за зарники.",
    },
    "frame_omen": {
        "name": "Оправа Предвестника", "slot": "avatar_frame", "rarity": "mythic",
        "css": "frame-omen", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Вращающийся ореол разлома вокруг аватара. Особая награда или за зарники.",
    },

    # ── Титул (текст, бот + веб) ─────────────────────────────────────────────
    "title_wanderer": {
        "name": "Странник Пустошей", "slot": "title", "rarity": "common",
        "text": "Странник Пустошей", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Текстовый титул под ником. Виден и в чате, и на сайте.",
    },
    "title_patron": {
        "name": "Меценат", "slot": "title", "rarity": "rare",
        "text": "Меценат", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Титул для щедрых покровителей. Отображается при активной VIP.",
    },
    "title_abysswalker": {
        "name": "Покоритель Бездны", "slot": "title", "rarity": "epic",
        "text": "Покоритель Бездны", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 630}],
        "desc": "Титул-награда или покупка за зарники. Отображается при активной VIP.",
    },
    "title_legend": {
        "name": "Легенда Сезона", "slot": "title", "rarity": "legendary",
        "text": "Легенда Сезона", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 50,
        "desc": "Титул платного трека БП (макс. уровень) или за зарники.",
    },
    "title_omen": {
        "name": "Предвестник", "slot": "title", "rarity": "mythic",
        "text": "Предвестник", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Мифический титул. Особая награда или за зарники.",
    },

    # ── Гало вокруг аватара (CSS, веб) ───────────────────────────────────────
    "halo_glow": {
        "name": "Тёплое гало", "slot": "avatar_halo", "rarity": "common",
        "css": "halo-glow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Мягкое тёплое свечение по контуру аватара. Доступно всем.",
    },
    "halo_pulse": {
        "name": "Пульсирующий ореол", "slot": "avatar_halo", "rarity": "rare",
        "css": "halo-pulse", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Ритмично пульсирующее кольцо света вокруг аватара. Отображается при активной VIP.",
    },
    "halo_runic": {
        "name": "Рунический круг", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-runic", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Вращающийся круг древних рун вокруг аватара. Отображается при активной VIP.",
    },
    "halo_aurora": {
        "name": "Аврора", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-aurora", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 630}],
        "desc": "Переливы северного сияния. Выдаётся с VIP или за зарники.",
    },
    "halo_celestial": {
        "name": "Небесный нимб", "slot": "avatar_halo", "rarity": "legendary",
        "css": "halo-celestial", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 30,
        "desc": "Золотой нимб с лучами. Награда БП (уровень 30) или за зарники.",
    },
    "halo_void": {
        "name": "Кольцо Бездны", "slot": "avatar_halo", "rarity": "mythic",
        "css": "halo-void", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмное кольцо с багровыми всполохами. Особая награда или за зарники.",
    },

    # ── Фон / баннер карточки профиля (CSS, веб) ─────────────────────────────
    "pbg_carbon": {
        "name": "Карбон", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-carbon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Строгий карбоновый фон карточки профиля.",
    },
    "pbg_nebula": {
        "name": "Туманность", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-nebula", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Космическая туманность фоном за твоей карточкой. Отображается при активной VIP.",
    },
    "pbg_abyss": {
        "name": "Бездна", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Глубокий фон Бездны с тёмным градиентом. Отображается при активной VIP.",
    },
    "pbg_forest": {
        "name": "Изумрудный лес", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-forest", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Глубокий изумрудный лес туманным фоном карточки.",
    },
    "pbg_ocean": {
        "name": "Морская бездна", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-ocean", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Холодные глубины океана за твоей карточкой.",
    },
    "pbg_ember": {
        "name": "Тлеющий вулкан", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Раскалённые угли вулкана тлеют снизу карточки. Отображается при активной VIP.",
    },
    "pbg_galaxy": {
        "name": "Спираль галактики", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-galaxy", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Фиолетово-синий рукав галактики со звёздной пылью. Отображается при активной VIP.",
    },
    "pbg_dusk": {
        "name": "Сумерки", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-dusk", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Спокойный сумеречный градиент. Отображается при активной VIP.",
    },
    "pbg_royal": {
        "name": "Королевский бархат", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-royal", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 630}],
        "desc": "Тёмно-пурпурный бархат с золотой каймой. Выдаётся с VIP или за зарники.",
    },
    "pbg_sunrise": {
        "name": "Рассвет", "slot": "profile_bg", "rarity": "legendary",
        "css": "pbg-sunrise", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 40,
        "desc": "Тёплый градиент рассвета. Награда БП (уровень 40) или за зарники.",
    },
    "pbg_legend": {
        "name": "Холст Легенды", "slot": "profile_bg", "rarity": "mythic",
        "css": "pbg-legend", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Живой золотисто-чёрный холст. Особая награда или за зарники.",
    },

    # ── Частицы поверх карточки (CSS-анимация, веб) ───────────────────────────
    "cfx_sparks": {
        "name": "Искры", "slot": "card_fx", "rarity": "common",
        "css": "cfx-sparks", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Лёгкие золотые искры, плавающие над карточкой.",
    },
    "cfx_snow": {
        "name": "Снегопад", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-snow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тихо падающие снежинки поверх профиля. Отображается при активной VIP.",
    },
    "cfx_petals": {
        "name": "Лепестки", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-petals", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тихо падающие лепестки сакуры. Отображается при активной VIP.",
    },
    "cfx_embers": {
        "name": "Угольки", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-embers", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 440}],
        "desc": "Поднимающиеся тлеющие угольки. Выдаётся с VIP или за зарники.",
    },
    "cfx_stars": {
        "name": "Звездопад", "slot": "card_fx", "rarity": "epic",
        "css": "cfx-stars", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Мерцающие падающие звёзды над карточкой. Отображается при активной VIP.",
    },
    "cfx_fireflies": {
        "name": "Светлячки", "slot": "card_fx", "rarity": "legendary",
        "css": "cfx-fireflies", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 25,
        "desc": "Тёплые светлячки кружат над профилем. Награда БП (уровень 25) или за зарники.",
    },
    "cfx_void_storm": {
        "name": "Шторм Бездны", "slot": "card_fx", "rarity": "mythic",
        "css": "cfx-void-storm", "vip_required": False, "source": "reward",
        "price": [{"zarniki": 1000}],
        "desc": "Багровые частицы Бездны в вихре. Особая награда или за зарники.",
    },
}


def cosmetics_by_slot(slot: str) -> dict[str, dict]:
    """Все косметики данного слота (id → entry)."""
    return {cid: c for cid, c in COSMETICS.items() if c["slot"] == slot}


def is_vip_locked(cos: dict) -> bool:
    """True если ОТОБРАЖЕНИЕ этой косметики требует активную VIP.
    Правило: всё выше «common» спит без VIP, plus VIP-автогрант-предметы.
    Покупку НЕ блокирует — только видимость на профиле."""
    return cos.get("rarity", "common") != "common" or cos.get("source") == "vip"


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
