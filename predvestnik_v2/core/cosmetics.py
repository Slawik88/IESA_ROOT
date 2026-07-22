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
  "bp" (также награда платного трека БП).
  Для всех source предмет ТАКЖЕ продаётся в магазине за зарники.
  ("reward" упразднён 2026-07-07: механизма особой выдачи не существовало,
  13 предметов переведены в "shop" — БЛОК 39.)

ID: строгий формат cos_{slot}_{имя} (рефакторинг 2026-07-07, БЛОК 39).
  Старые ID в БД игроков мигрируются АВТОМАТИЧЕСКИ при старте процесса
  (services/cosmetics.migrate_legacy_ids, one-shot через schema_migrations) —
  после прод-инцидента 2026-07-08, когда деплой без ручного прогона скрипта
  «спрятал» оплаченную косметику. Ручной скрипт остаётся: scripts/migrate_cosmetics_ids.py.

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
    "cos_name_glow_silver": {
        "name": "Серебряный ореол", "slot": "name_glow", "rarity": "common",
        "css": "glow-silver", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Мягкое серебристое свечение вокруг ника. Доступно всем.",
    },
    "cos_name_glow_gold": {
        "name": "Золотое сияние", "slot": "name_glow", "rarity": "rare",
        "css": "glow-gold", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тёплый золотой ореол. Знак статуса. Отображается при активной VIP.",
    },
    "cos_name_glow_crimson": {
        "name": "Багровое пламя", "slot": "name_glow", "rarity": "epic",
        "css": "glow-crimson", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Зловещее багровое свечение из глубин Бездны. Отображается при активной VIP.",
    },
    "cos_name_glow_ember": {
        "name": "Тлеющий уголь", "slot": "name_glow", "rarity": "epic",
        "css": "glow-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Спокойное тёплое тление букв. Отображается при активной VIP.",
    },
    "cos_name_glow_prism": {
        "name": "Призматический ореол", "slot": "name_glow", "rarity": "legendary",
        "css": "glow-prism", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 20,
        "desc": "Переливающийся спектр. Награда БП (уровень 20) или покупка за зарники.",
    },
    "cos_name_glow_rift": {
        "name": "Разлом Бездны", "slot": "name_glow", "rarity": "mythic",
        "css": "glow-rift", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Имя пылает разломом: фиолет–багрянец–золото. Особая награда или покупка за зарники.",
    },

    # ── Рамка аватара (CSS, веб) ─────────────────────────────────────────────
    "cos_avatar_frame_bronze": {
        "name": "Бронзовая оправа", "slot": "avatar_frame", "rarity": "common",
        "css": "frame-bronze", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Простая бронзовая рамка вокруг аватара.",
    },
    "cos_avatar_frame_neon": {
        "name": "Неоновый контур", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-neon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Пульсирующая неоновая обводка аватара. Отображается при активной VIP.",
    },
    "cos_avatar_frame_abyss": {
        "name": "Оправа Бездны", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Рамка из застывшей Тёмной Моры. Отображается при активной VIP.",
    },
    "cos_avatar_frame_iron": {
        "name": "Железная оправа", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-iron", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Прочная стальная окантовка. Отображается при активной VIP.",
    },
    "cos_avatar_frame_celestial": {
        "name": "Небесная оправа", "slot": "avatar_frame", "rarity": "legendary",
        "css": "frame-celestial", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 820}],
        "desc": "Светящаяся небесная рамка. Выдаётся с VIP или за зарники.",
    },
    "cos_avatar_frame_omen": {
        "name": "Оправа Предвестника", "slot": "avatar_frame", "rarity": "mythic",
        "css": "frame-omen", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Вращающийся ореол разлома вокруг аватара. Особая награда или за зарники.",
    },

    # ── Титул (текст, бот + веб) ─────────────────────────────────────────────
    "cos_title_wanderer": {
        "name": "Странник Пустошей", "slot": "title", "rarity": "common",
        "text": "Странник Пустошей", "css": "title-wanderer",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Текстовый титул под ником. Виден и в чате, и на сайте.",
    },
    "cos_title_patron": {
        "name": "Меценат", "slot": "title", "rarity": "rare",
        "text": "Меценат", "css": "title-patron",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Титул для щедрых покровителей. Отображается при активной VIP.",
    },
    "cos_title_abysswalker": {
        "name": "Покоритель Бездны", "slot": "title", "rarity": "epic",
        "text": "Покоритель Бездны", "css": "title-abysswalker",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Титул-награда или покупка за зарники. Отображается при активной VIP.",
    },
    "cos_title_legend": {
        "name": "Легенда Сезона", "slot": "title", "rarity": "legendary",
        "text": "Легенда Сезона", "css": "title-legend",
        "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 50,
        "desc": "Титул платного трека БП (макс. уровень) или за зарники.",
    },
    "cos_title_omen": {
        "name": "Предвестник", "slot": "title", "rarity": "mythic",
        "text": "Предвестник", "css": "title-omen",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Мифический титул. Особая награда или за зарники.",
    },

    # ── Гало вокруг аватара (CSS, веб) ───────────────────────────────────────
    "cos_avatar_halo_glow": {
        "name": "Тёплое гало", "slot": "avatar_halo", "rarity": "common",
        "css": "halo-glow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Мягкое тёплое свечение по контуру аватара. Доступно всем.",
    },
    "cos_avatar_halo_pulse": {
        "name": "Пульсирующий ореол", "slot": "avatar_halo", "rarity": "rare",
        "css": "halo-pulse", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Ритмично пульсирующее кольцо света вокруг аватара. Отображается при активной VIP.",
    },
    "cos_avatar_halo_runic": {
        "name": "Рунический круг", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-runic", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Вращающийся круг древних рун вокруг аватара. Отображается при активной VIP.",
    },
    "cos_avatar_halo_aurora": {
        "name": "Аврора", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-aurora", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 630}],
        "desc": "Переливы северного сияния. Выдаётся с VIP или за зарники.",
    },
    "cos_avatar_halo_celestial": {
        "name": "Небесный нимб", "slot": "avatar_halo", "rarity": "legendary",
        "css": "halo-celestial", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 30,
        "desc": "Золотой нимб с лучами. Награда БП (уровень 30) или за зарники.",
    },
    "cos_avatar_halo_void": {
        "name": "Кольцо Бездны", "slot": "avatar_halo", "rarity": "mythic",
        "css": "halo-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмное кольцо с багровыми всполохами. Особая награда или за зарники.",
    },

    # ── Фон / баннер карточки профиля (CSS, веб) ─────────────────────────────
    "cos_profile_bg_carbon": {
        "name": "Карбон", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-carbon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Строгий карбоновый фон карточки профиля.",
    },
    "cos_profile_bg_nebula": {
        "name": "Туманность", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-nebula", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Космическая туманность фоном за твоей карточкой. Отображается при активной VIP.",
    },
    "cos_profile_bg_abyss": {
        "name": "Бездна", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Глубокий фон Бездны с тёмным градиентом. Отображается при активной VIP.",
    },
    "cos_profile_bg_forest": {
        "name": "Изумрудный лес", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-forest", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Глубокий изумрудный лес туманным фоном карточки.",
    },
    "cos_profile_bg_ocean": {
        "name": "Морская бездна", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-ocean", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Холодные глубины океана за твоей карточкой.",
    },
    "cos_profile_bg_ember": {
        "name": "Тлеющий вулкан", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Раскалённые угли вулкана тлеют снизу карточки. Отображается при активной VIP.",
    },
    "cos_profile_bg_galaxy": {
        "name": "Спираль галактики", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-galaxy", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Фиолетово-синий рукав галактики со звёздной пылью. Отображается при активной VIP.",
    },
    "cos_profile_bg_dusk": {
        "name": "Сумерки", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-dusk", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Спокойный сумеречный градиент. Отображается при активной VIP.",
    },
    "cos_profile_bg_royal": {
        "name": "Королевский бархат", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-royal", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 630}],
        "desc": "Тёмно-пурпурный бархат с золотой каймой. Выдаётся с VIP или за зарники.",
    },
    "cos_profile_bg_sunrise": {
        "name": "Рассвет", "slot": "profile_bg", "rarity": "legendary",
        "css": "pbg-sunrise", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 40,
        "desc": "Тёплый градиент рассвета. Награда БП (уровень 40) или за зарники.",
    },
    "cos_profile_bg_legend": {
        "name": "Холст Легенды", "slot": "profile_bg", "rarity": "mythic",
        "css": "pbg-legend", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Живой золотисто-чёрный холст. Особая награда или за зарники.",
    },

    # ── Частицы поверх карточки (CSS-анимация, веб) ───────────────────────────
    "cos_card_fx_sparks": {
        "name": "Искры", "slot": "card_fx", "rarity": "common",
        "css": "cfx-sparks", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Лёгкие золотые искры, плавающие над карточкой.",
    },
    "cos_card_fx_snow": {
        "name": "Снегопад", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-snow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тихо падающие снежинки поверх профиля. Отображается при активной VIP.",
    },
    "cos_card_fx_petals": {
        "name": "Лепестки", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-petals", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тихо падающие лепестки сакуры. Отображается при активной VIP.",
    },
    "cos_card_fx_embers": {
        "name": "Угольки", "slot": "card_fx", "rarity": "rare",
        "css": "cfx-embers", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 440}],
        "desc": "Поднимающиеся тлеющие угольки. Выдаётся с VIP или за зарники.",
    },
    "cos_card_fx_stars": {
        "name": "Звездопад", "slot": "card_fx", "rarity": "epic",
        "css": "cfx-stars", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Мерцающие падающие звёзды над карточкой. Отображается при активной VIP.",
    },
    "cos_card_fx_fireflies": {
        "name": "Светлячки", "slot": "card_fx", "rarity": "legendary",
        "css": "cfx-fireflies", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}],
        "bp_level": 25,
        "desc": "Тёплые светлячки кружат над профилем. Награда БП (уровень 25) или за зарники.",
    },
    "cos_card_fx_void_storm": {
        "name": "Шторм Бездны", "slot": "card_fx", "rarity": "mythic",
        "css": "cfx-void-storm", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Багровые частицы Бездны в вихре. Особая награда или за зарники.",
    },

    # ── Новые: ореол имени ───────────────────────────────────────────────────
    "cos_name_glow_frost": {
        "name": "Ледяная вязь", "slot": "name_glow", "rarity": "rare",
        "css": "glow-frost", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хрустальное ледяное свечение вокруг ника. Отображается при активной VIP.",
    },
    "cos_name_glow_thunder": {
        "name": "Молния", "slot": "name_glow", "rarity": "epic",
        "css": "glow-thunder", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Нестабильные электрические разряды мерцают вокруг ника. Отображается при активной VIP.",
    },
    "cos_name_glow_solar": {
        "name": "Солнечная корона", "slot": "name_glow", "rarity": "legendary",
        "css": "glow-solar", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Раскалённая золотисто-белая корона звезды. Медленно пульсирует теплом.",
    },

    # ── Новые: рамка аватара ─────────────────────────────────────────────────
    "cos_avatar_frame_crystal": {
        "name": "Кристальная грань", "slot": "avatar_frame", "rarity": "rare",
        "css": "frame-crystal", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Чёткая ледяная кромка с ребристым блеском. Отображается при активной VIP.",
    },
    "cos_avatar_frame_arcane": {
        "name": "Аркана", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-arcane", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Мистическое кольцо аркан-энергии медленно меняет цвет. Отображается при активной VIP.",
    },
    "cos_avatar_frame_inferno": {
        "name": "Инферно", "slot": "avatar_frame", "rarity": "legendary",
        "css": "frame-inferno", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Живое пламя Инферно лижет края аватара — жар поднимается вверх.",
    },

    # ── Новые: гало аватара ──────────────────────────────────────────────────
    "cos_avatar_halo_ice": {
        "name": "Ледяной сполох", "slot": "avatar_halo", "rarity": "rare",
        "css": "halo-ice", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хрустальный ледяной ореол. Чистый и резкий. Отображается при активной VIP.",
    },
    "cos_avatar_halo_corona": {
        "name": "Солнечная корона", "slot": "avatar_halo", "rarity": "legendary",
        "css": "halo-corona", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Четырёхслойная солнечная корона бьёт светом. Пульсирующая звезда за спиной.",
    },

    # ── Новые: фон профиля ───────────────────────────────────────────────────
    "cos_profile_bg_midnight": {
        "name": "Полночь", "slot": "profile_bg", "rarity": "common",
        "css": "pbg-midnight", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Глубокий полночный синий. Спокойный и элегантный.",
    },
    "cos_profile_bg_crimson": {
        "name": "Багровый горизонт", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-crimson", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тёмно-красные тона закатного неба. Отображается при активной VIP.",
    },
    "cos_profile_bg_void_dark": {
        "name": "Тёмная Пустота", "slot": "profile_bg", "rarity": "epic",
        "css": "pbg-void-dark", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Медленно дышащие фиолетовые потоки в абсолютной тьме. Отображается при активной VIP.",
    },
    "cos_profile_bg_aurora": {
        "name": "Полярное сияние", "slot": "profile_bg", "rarity": "legendary",
        "css": "pbg-aurora", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Живое северное сияние: зелёные и синие волны медленно плывут по тёмному небу.",
    },

    # ── Новые: частицы карточки ──────────────────────────────────────────────
    "cos_card_fx_dust": {
        "name": "Пыль Странника", "slot": "card_fx", "rarity": "common",
        "css": "cfx-dust", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Нежные золотисто-серые пылинки медленно дрейфуют по карточке.",
    },
    "cos_card_fx_nova": {
        "name": "Вспышка Новой", "slot": "card_fx", "rarity": "legendary",
        "css": "cfx-nova", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Взрыв света из центра карточки — расширяется и гаснет. Повторяется снова.",
    },

    # ── Новые: титулы (с CSS-эффектами) ─────────────────────────────────────
    "cos_title_sentinel": {
        "name": "Часовой Пустоши", "slot": "title", "rarity": "rare",
        "text": "Часовой Пустоши", "css": "title-sentinel",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хладнокровный страж. Стальной акцент. Отображается при активной VIP.",
    },
    "cos_title_rift_walker": {
        "name": "Странник Разломов", "slot": "title", "rarity": "epic",
        "text": "Странник Разломов", "css": "title-rift-walker",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Бродит между мирами. Фиолетовый пульс. Отображается при активной VIP.",
    },
    "cos_title_apex": {
        "name": "Вершина Бездны", "slot": "title", "rarity": "legendary",
        "text": "Вершина Бездны", "css": "title-apex",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Золотой градиент-блик. Виден тем, кто добился вершины.",
    },
    "cos_title_harbinger": {
        "name": "Предвестник Конца", "slot": "title", "rarity": "mythic",
        "text": "Предвестник Конца", "css": "title-harbinger",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Мифический титул. Пурпурный шёпот. Особая награда или за зарники.",
    },

    # ── Расширение слотов (запрос 2026-07-02): закрываем пробелы common/mythic,
    # добавляем разнообразия в середине. Каждый эффект — свой характер, не клон
    # уже существующего (проверено визуально через cosmetics_preview.html). ──────

    # ── Ореол имени: +common, +rare, +mythic ────────────────────────────────
    "cos_name_glow_moon": {
        "name": "Лунный свет", "slot": "name_glow", "rarity": "common",
        "css": "glow-moon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Бледное холодное сияние ночного светила. Спокойная альтернатива серебру.",
    },
    "cos_name_glow_verdant": {
        "name": "Изумрудный шёпот", "slot": "name_glow", "rarity": "rare",
        "css": "glow-verdant", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Живая зелень леса в буквах имени. Отображается при активной VIP.",
    },
    "cos_name_glow_void": {
        "name": "Голос Пустоты", "slot": "name_glow", "rarity": "mythic",
        "css": "glow-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмно-фиолетовый шёпот с редкими вспышками на границах букв. Особая награда или за зарники.",
    },

    # ── Рамка аватара: +common, +epic, +mythic ──────────────────────────────
    "cos_avatar_frame_oak": {
        "name": "Дубовая оправа", "slot": "avatar_frame", "rarity": "common",
        "css": "frame-oak", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Тёплый деревянный кант вокруг аватара. Простая альтернатива бронзе.",
    },
    "cos_avatar_frame_tidal": {
        "name": "Приливная волна", "slot": "avatar_frame", "rarity": "epic",
        "css": "frame-tidal", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Бирюзовая волна перекатывается по кромке аватара. Отображается при активной VIP.",
    },
    "cos_avatar_frame_void": {
        "name": "Разлом Пустоты", "slot": "avatar_frame", "rarity": "mythic",
        "css": "frame-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Чёрная кромка с редкими фиолетовыми разрядами. Особая награда или за зарники.",
    },

    # ── Титул: +common, +rare, +epic ────────────────────────────────────────
    "cos_title_novice": {
        "name": "Новичок Бездны", "slot": "title", "rarity": "common",
        "text": "Новичок Бездны", "css": "title-novice",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Простой стартовый титул. Виден и в чате, и на сайте.",
    },
    "cos_title_keeper": {
        "name": "Хранитель Порога", "slot": "title", "rarity": "rare",
        "text": "Хранитель Порога", "css": "title-keeper",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Спокойная уверенность стража границы. Отображается при активной VIP.",
    },
    "cos_title_ember_born": {
        "name": "Рождённый Пеплом", "slot": "title", "rarity": "epic",
        "text": "Рождённый Пеплом", "css": "title-ember-born",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тлеющий оранжевый акцент. Отображается при активной VIP.",
    },

    # ── Гало аватара: +common, +epic, +mythic ───────────────────────────────
    "cos_avatar_halo_dust": {
        "name": "Пыльный нимб", "slot": "avatar_halo", "rarity": "common",
        "css": "halo-dust", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Тёплая золотистая дымка вокруг аватара. Мягкая альтернатива тёплому гало.",
    },
    "cos_avatar_halo_thorn": {
        "name": "Терновый венец", "slot": "avatar_halo", "rarity": "epic",
        "css": "halo-thorn", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёмно-изумрудные шипы вспыхивают по контуру. Отображается при активной VIP.",
    },
    "cos_avatar_halo_eclipse": {
        "name": "Затмение", "slot": "avatar_halo", "rarity": "mythic",
        "css": "halo-eclipse", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмный диск с тонкой пылающей короной по кромке. Особая награда или за зарники.",
    },

    # ── Фон профиля: +rare, +legendary, +mythic ─────────────────────────────
    "cos_profile_bg_amber": {
        "name": "Янтарь", "slot": "profile_bg", "rarity": "rare",
        "css": "pbg-amber", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тёплый застывший янтарный свет. Отображается при активной VIP.",
    },
    "cos_profile_bg_phoenix": {
        "name": "Феникс", "slot": "profile_bg", "rarity": "legendary",
        "css": "pbg-phoenix", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Огненные перья восходят снизу карточки, живое пламенное дыхание.",
    },
    "cos_profile_bg_starfall": {
        "name": "Звездопад Богов", "slot": "profile_bg", "rarity": "mythic",
        "css": "pbg-starfall", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Глубокий космос с падающими звёздами. Особая награда или за зарники.",
    },

    # ── Частицы карточки: +common, +epic, +mythic ───────────────────────────
    "cos_card_fx_leaves": {
        "name": "Листопад", "slot": "card_fx", "rarity": "common",
        "css": "cfx-leaves", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Осенние листья медленно кружат над карточкой.",
    },
    "cos_card_fx_moths": {
        "name": "Мотыльки", "slot": "card_fx", "rarity": "epic",
        "css": "cfx-moths", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёплые мотыльки плавно порхают над профилем. Отображается при активной VIP.",
    },
    "cos_card_fx_eclipse_ash": {
        "name": "Пепел Затмения", "slot": "card_fx", "rarity": "mythic",
        "css": "cfx-eclipse-ash", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмный пепел медленно оседает с редкими багровыми всполохами. Особая награда или за зарники.",
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


# ── БЛОК 39 hotfix: маппинг старых ID → новые (cos_{slot}_{name}) ────────────
# Единый источник для scripts/migrate_cosmetics_ids.py и авто-миграции на старте
# (services/cosmetics.migrate_legacy_ids). У игроков в БД могли остаться старые
# ID (купленная косметика «пропала» после деплоя без прогона скрипта) — стартовая
# миграция возвращает всё сама, без ручных действий на проде.
COSMETIC_LEGACY_ID_MAP: dict[str, str] = {
    "glow_silver": "cos_name_glow_silver",
    "glow_gold": "cos_name_glow_gold",
    "glow_crimson": "cos_name_glow_crimson",
    "glow_ember": "cos_name_glow_ember",
    "glow_prism": "cos_name_glow_prism",
    "glow_rift": "cos_name_glow_rift",
    "frame_bronze": "cos_avatar_frame_bronze",
    "frame_neon": "cos_avatar_frame_neon",
    "frame_abyss": "cos_avatar_frame_abyss",
    "frame_iron": "cos_avatar_frame_iron",
    "frame_celestial": "cos_avatar_frame_celestial",
    "frame_omen": "cos_avatar_frame_omen",
    "title_wanderer": "cos_title_wanderer",
    "title_patron": "cos_title_patron",
    "title_abysswalker": "cos_title_abysswalker",
    "title_legend": "cos_title_legend",
    "title_omen": "cos_title_omen",
    "halo_glow": "cos_avatar_halo_glow",
    "halo_pulse": "cos_avatar_halo_pulse",
    "halo_runic": "cos_avatar_halo_runic",
    "halo_aurora": "cos_avatar_halo_aurora",
    "halo_celestial": "cos_avatar_halo_celestial",
    "halo_void": "cos_avatar_halo_void",
    "pbg_carbon": "cos_profile_bg_carbon",
    "pbg_nebula": "cos_profile_bg_nebula",
    "pbg_abyss": "cos_profile_bg_abyss",
    "pbg_forest": "cos_profile_bg_forest",
    "pbg_ocean": "cos_profile_bg_ocean",
    "pbg_ember": "cos_profile_bg_ember",
    "pbg_galaxy": "cos_profile_bg_galaxy",
    "pbg_dusk": "cos_profile_bg_dusk",
    "pbg_royal": "cos_profile_bg_royal",
    "pbg_sunrise": "cos_profile_bg_sunrise",
    "pbg_legend": "cos_profile_bg_legend",
    "cfx_sparks": "cos_card_fx_sparks",
    "cfx_snow": "cos_card_fx_snow",
    "cfx_petals": "cos_card_fx_petals",
    "cfx_embers": "cos_card_fx_embers",
    "cfx_stars": "cos_card_fx_stars",
    "cfx_fireflies": "cos_card_fx_fireflies",
    "cfx_void_storm": "cos_card_fx_void_storm",
    "glow_frost": "cos_name_glow_frost",
    "glow_thunder": "cos_name_glow_thunder",
    "glow_solar": "cos_name_glow_solar",
    "frame_crystal": "cos_avatar_frame_crystal",
    "frame_arcane": "cos_avatar_frame_arcane",
    "frame_inferno": "cos_avatar_frame_inferno",
    "halo_ice": "cos_avatar_halo_ice",
    "halo_corona": "cos_avatar_halo_corona",
    "pbg_midnight": "cos_profile_bg_midnight",
    "pbg_crimson": "cos_profile_bg_crimson",
    "pbg_void_dark": "cos_profile_bg_void_dark",
    "pbg_aurora": "cos_profile_bg_aurora",
    "cfx_dust": "cos_card_fx_dust",
    "cfx_nova": "cos_card_fx_nova",
    "title_sentinel": "cos_title_sentinel",
    "title_rift_walker": "cos_title_rift_walker",
    "title_apex": "cos_title_apex",
    "title_harbinger": "cos_title_harbinger",
    "glow_moon": "cos_name_glow_moon",
    "glow_verdant": "cos_name_glow_verdant",
    "glow_void": "cos_name_glow_void",
    "frame_oak": "cos_avatar_frame_oak",
    "frame_tidal": "cos_avatar_frame_tidal",
    "frame_void": "cos_avatar_frame_void",
    "title_novice": "cos_title_novice",
    "title_keeper": "cos_title_keeper",
    "title_ember_born": "cos_title_ember_born",
    "halo_dust": "cos_avatar_halo_dust",
    "halo_thorn": "cos_avatar_halo_thorn",
    "halo_eclipse": "cos_avatar_halo_eclipse",
    "pbg_amber": "cos_profile_bg_amber",
    "pbg_phoenix": "cos_profile_bg_phoenix",
    "pbg_starfall": "cos_profile_bg_starfall",
    "cfx_leaves": "cos_card_fx_leaves",
    "cfx_moths": "cos_card_fx_moths",
    "cfx_eclipse_ash": "cos_card_fx_eclipse_ash",
}
