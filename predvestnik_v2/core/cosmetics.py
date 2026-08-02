"""core/cosmetics.py — Косметика профиля (конструктор внешнего вида).

Только КОСМЕТИКА, без игрового преимущества. Без внешних зависимостей.

ЛИНЕЙКИ (редизайн 2026-07-29): группировка по редкости (common→artifact, 86
разрозненных предметов без общего стиля внутри яруса) заменена на тематические
"линеек" — коллекций с единым визуальным языком на все 6 слотов. Цена и VIP-гейт
теперь СВОЙСТВО ЛИНЕЙКИ (см. LINEUPS ниже), не отдельного предмета:
  Лесной Странник → 250✨, без VIP      Изморозь  → 440✨, с VIP
  Порог           → 440✨, с VIP        Инферно   → 630✨, с VIP
  Небесное Сияние → 820✨, с VIP        Бездна    → 1000✨, с VIP
  Артефакт        → 1500✨, с VIP
  Ханами          → 630✨, с VIP        Лунный Лотос → 1500✨, с VIP
  Прилив Рюдзина  → 1500✨, с VIP

Порядок действий при переходе (важно для истории): владелец сначала прогнал
scripts/cosmetics_lineup_wipe_refund.py — рефанд+снятие ВСЕЙ косметики у ВСЕХ
игроков по ценам, которые действовали ДО этого файла. Только после этого прайсы
здесь переписаны на новые — так рефанд не задело задним числом изменение цены.

`rarity` на каждом предмете — ТЕХНИЧЕСКОЕ поле (не показывается игроку как
"редкость"): совпадает с ценовым ярусом его линейки, продолжает управлять
VIP-гейтом (is_vip_locked) и пулом дропа в сундуках/крафте
(core/constants.py::COSMETIC_CHESTS/COSMETIC_DUPE_SHARDS/COSMETIC_CRAFT_SHARDS,
не трогал). Несколько линеек МОГУТ делить один ценовой ярус (Изморозь и Порог —
обе rare/440✨) — ярус общий, линейка — только тематическая витрина.
`lineup` — НОВОЕ поле, id записи в LINEUPS, для группировки в магазине.

56 из 86 старых предметов переприписаны в линейки (у части сменились
rarity/price — см. LINEUPS/комментарии по секциям), 78 — новые (для слотов,
где готового по теме не нашлось). Разрозненные предметы вне какой-либо линейки
удалены из каталога целиком (был полный wipe — владельцу принадлежать было
уже некому, терять было нечего).

VIP-гейт ТОЛЬКО на отображение (не на покупку):
  Все предметы выше Обычного показываются ТОЛЬКО при активной VIP.
  Покупка доступна без VIP — но до активации VIP косметика «спит».
  При обновлении VIP предмет возвращается без переэкипировки.

price: список вариантов оплаты. price=None → предмет не продаётся (выдаётся
  другим источником: VIP/БП). Все предметы можно купить за зарники.

source: "shop" | "vip" (также даётся при активной VIP, под VIP-гейтом показа) |
  "bp" (также награда платного трека БП).
  Для всех source предмет ТАКЖЕ продаётся в магазине за зарники.

ID: строгий формат cos_{slot}_{имя} (рефакторинг 2026-07-07, БЛОК 39). ID НЕ
  меняются при переходе на линейки — только метаданные (rarity/price/lineup) —
  владение в БД по ID, ничего не ломается при пересмотре группировки/цены
  задним числом. Старые ID мигрируются АВТОМАТИЧЕСКИ при старте процесса
  (services/cosmetics.migrate_legacy_ids, one-shot через schema_migrations).

vip_required: НЕ блокирует ПОКУПКУ, отдельное от is_vip_locked() (та смотрит
  на rarity/source) декоративное поле — исторически True только у Артефакта.

slot: "name_glow" | "avatar_frame" | "title" | "avatar_halo" | "profile_bg" | "card_fx"
Визуальные слоты — только веб. Титул (title) — веб + бот-карточка.
"""

COSMETIC_SLOTS = (
    "name_glow", "avatar_frame", "title",
    "avatar_halo", "profile_bg", "card_fx",
)

# Порядок редкостей для сортировки/цвета в UI + пул дропа сундуков/крафта.
RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3, "mythic": 4,
                "artifact": 5}

# ── Линейки — тематические коллекции (заменяют редкость как группировку витрины) ──
LINEUPS: dict[str, dict] = {
    "forest": {
        "name": "🌲 Лесной Странник", "rarity": "common",
        "price": [{"zarniki": 250}], "vip_required": False,
        "blurb": "Тёплое дерево и зелень леса — самая доступная линейка, видна всем без VIP.",
    },
    "threshold": {
        "name": "🔮 Порог", "rarity": "rare",
        "price": [{"zarniki": 440}], "vip_required": True,
        "blurb": "Фиолетовые разломы и спокойная бирюза стражей на границе Бездны.",
    },
    "frost": {
        "name": "❄️ Изморозь", "rarity": "rare",
        "price": [{"zarniki": 440}], "vip_required": True,
        "blurb": "Лёд, иней и морозная тишина.",
    },
    "inferno": {
        "name": "🔥 Инферно", "rarity": "epic",
        "price": [{"zarniki": 630}], "vip_required": True,
        "blurb": "Пламя, угли и раскалённый металл.",
    },
    "hanami": {
        "name": "🌸 Ханами", "rarity": "epic",
        "price": [{"zarniki": 630}], "vip_required": True,
        "blurb": "Сакура, тёплая тушь и сумеречная бумага васи — красота одного короткого цветения.",
    },
    "celestial": {
        "name": "✨ Небесное Сияние", "rarity": "legendary",
        "price": [{"zarniki": 820}], "vip_required": True,
        "blurb": "Рассвет, аврора и солнечная корона — тёплое золото на холодном небе.",
    },
    "void": {
        "name": "🌌 Бездна", "rarity": "mythic",
        "price": [{"zarniki": 1000}], "vip_required": True,
        "blurb": "Глубокий космос, разломы и тихое затмение.",
    },
    "artifact": {
        "name": "⚡ Артефакт", "rarity": "artifact",
        "price": [{"zarniki": 1500}], "vip_required": True,
        "blurb": "Голографическая энергия: циан+магента+золото, техно-язык.",
    },
    "moon_lotus": {
        "name": "🪷 Лунный Лотос", "rarity": "artifact",
        "price": [{"zarniki": 1500}], "vip_required": True,
        "blurb": "Перламутровый лотос на ночной воде: серебряный свет, тихая рябь и глубокий индиго.",
    },
    "ryujin_tide": {
        "name": "🐉 Прилив Рюдзина", "rarity": "artifact",
        "price": [{"zarniki": 1500}], "vip_required": True,
        "blurb": "Драконий поток в языке суми-э: штормовая вода, чёрный лак и прожилки кинцуги.",
    },
}


def lineup_items(lineup_id: str) -> dict[str, dict]:
    """Все косметики данной линейки (id → entry)."""
    return {cid: c for cid, c in COSMETICS.items() if c.get("lineup") == lineup_id}


COSMETICS: dict[str, dict] = {
    # ═══════════════════ 🌲 ЛЕСНОЙ СТРАННИК (250✨, без VIP) — 13 предметов ═══════
    # 7 уже существовали (glow-verdant репрайснут rare→common — цена/редкость
    # были единственным барьером, тема "лес" совпадает идеально), 6 новых.
    "cos_name_glow_moon": {
        "name": "Лунный свет", "slot": "name_glow", "rarity": "common", "lineup": "forest",
        "css": "glow-moon", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Бледное холодное сияние ночного светила.",
    },
    "cos_name_glow_verdant": {
        "name": "Изумрудный шёпот", "slot": "name_glow", "rarity": "common", "lineup": "forest",
        "css": "glow-verdant", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Живая зелень леса в буквах имени.",
    },
    "cos_avatar_frame_oak": {
        "name": "Дубовая оправа", "slot": "avatar_frame", "rarity": "common", "lineup": "forest",
        "css": "frame-oak", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Тёплый деревянный кант вокруг аватара.",
    },
    "cos_avatar_frame_vine": {
        "name": "Плетёная лоза", "slot": "avatar_frame", "rarity": "common", "lineup": "forest",
        "css": "frame-vine", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Живая лоза оплетает край аватара, мягко покачиваясь.",
    },
    "cos_avatar_halo_dust": {
        "name": "Пыльный нимб", "slot": "avatar_halo", "rarity": "common", "lineup": "forest",
        "css": "halo-dust", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Тёплая золотистая дымка вокруг аватара.",
    },
    "cos_avatar_halo_dappled": {
        "name": "Блики сквозь листву", "slot": "avatar_halo", "rarity": "common", "lineup": "forest",
        "css": "halo-dappled", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Пятна света мерцают, будто сквозь листву древесной кроны.",
    },
    "cos_profile_bg_forest": {
        "name": "Изумрудный лес", "slot": "profile_bg", "rarity": "common", "lineup": "forest",
        "css": "pbg-forest", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Глубокий изумрудный лес туманным фоном карточки.",
    },
    "cos_profile_bg_misty_glade": {
        "name": "Туманная поляна", "slot": "profile_bg", "rarity": "common", "lineup": "forest",
        "css": "pbg-misty-glade", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Тихая лесная поляна, укрытая утренним туманом.",
    },
    "cos_card_fx_leaves": {
        "name": "Листопад", "slot": "card_fx", "rarity": "common", "lineup": "forest",
        "css": "cfx-leaves", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Осенние листья медленно кружат над карточкой.",
    },
    "cos_card_fx_dust": {
        "name": "Пыль Странника", "slot": "card_fx", "rarity": "common", "lineup": "forest",
        "css": "cfx-dust", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Нежные золотисто-серые пылинки медленно дрейфуют по карточке.",
    },
    "cos_card_fx_pollen": {
        "name": "Пыльца", "slot": "card_fx", "rarity": "common", "lineup": "forest",
        "css": "cfx-pollen", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Золотистая цветочная пыльца медленно кружит над карточкой.",
    },
    "cos_title_forest_wanderer": {
        "name": "Лесной Странник", "slot": "title", "rarity": "common", "lineup": "forest",
        "text": "🌲 Лесной Странник", "css": "title-forest-wanderer",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Титул для тех, кто выбрал путь леса.",
    },
    "cos_title_thicket_child": {
        "name": "Дитя Чащи", "slot": "title", "rarity": "common", "lineup": "forest",
        "text": "Дитя Чащи", "css": "title-thicket-child",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 250}],
        "desc": "Рождённый в самой гуще леса.",
    },

    # ═══════════════════════ 🔮 ПОРОГ (440✨, с VIP) — 14 предметов ═══════════
    # 8 уже существовали (frame-abyss/pbg-abyss/pbg-void-dark/title-abysswalker/
    # title-rift-walker репрайснуты epic→rare — "Бездна" забрала себе только
    # mythic-тир этой же смысловой темы, это младшая родня), 6 новых.
    "cos_name_glow_riftwhisper": {
        "name": "Шёпот Разлома", "slot": "name_glow", "rarity": "rare", "lineup": "threshold",
        "css": "glow-riftwhisper", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Фиолетовое эхо разлома мерцает вокруг ника. Отображается при активной VIP.",
    },
    "cos_name_glow_thresholdshade": {
        "name": "Тень Порога", "slot": "name_glow", "rarity": "rare", "lineup": "threshold",
        "css": "glow-thresholdshade", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Спокойная бирюзовая тень на границе миров. Отображается при активной VIP.",
    },
    "cos_avatar_frame_abyss": {
        "name": "Оправа Бездны", "slot": "avatar_frame", "rarity": "rare", "lineup": "threshold",
        "css": "frame-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Рамка из застывшей Тёмной Моры. Отображается при активной VIP.",
    },
    "cos_avatar_frame_rift_edge": {
        "name": "Кромка Разлома", "slot": "avatar_frame", "rarity": "rare", "lineup": "threshold",
        "css": "frame-rift-edge", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Пульсирующая фиолетовая кромка разлома. Отображается при активной VIP.",
    },
    "cos_avatar_halo_pulse": {
        "name": "Пульсирующий ореол", "slot": "avatar_halo", "rarity": "rare", "lineup": "threshold",
        "css": "halo-pulse", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Ритмично пульсирующее кольцо света вокруг аватара. Отображается при активной VIP.",
    },
    "cos_avatar_halo_threshold_flicker": {
        "name": "Мерцание Порога", "slot": "avatar_halo", "rarity": "rare", "lineup": "threshold",
        "css": "halo-threshold-flicker", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Бирюзовое мерцание стража на границе. Отображается при активной VIP.",
    },
    "cos_profile_bg_abyss": {
        "name": "Бездна", "slot": "profile_bg", "rarity": "rare", "lineup": "threshold",
        "css": "pbg-abyss", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Глубокий фон Бездны с тёмным градиентом. Отображается при активной VIP.",
    },
    "cos_profile_bg_void_dark": {
        "name": "Тёмная Пустота", "slot": "profile_bg", "rarity": "rare", "lineup": "threshold",
        "css": "pbg-void-dark", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Медленно дышащие фиолетовые потоки в абсолютной тьме. Отображается при активной VIP.",
    },
    "cos_card_fx_rift_dust": {
        "name": "Пыль Разлома", "slot": "card_fx", "rarity": "rare", "lineup": "threshold",
        "css": "cfx-rift-dust", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Фиолетовая пыль разлома медленно дрейфует над карточкой. Отображается при активной VIP.",
    },
    "cos_card_fx_void_echo": {
        "name": "Эхо Пустоты", "slot": "card_fx", "rarity": "rare", "lineup": "threshold",
        "css": "cfx-void-echo", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Кольца эха расходятся из центра карточки и гаснут. Отображается при активной VIP.",
    },
    "cos_title_abysswalker": {
        "name": "Покоритель Бездны", "slot": "title", "rarity": "rare", "lineup": "threshold",
        "text": "Покоритель Бездны", "css": "title-abysswalker",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Титул-награда или покупка за зарники. Отображается при активной VIP.",
    },
    "cos_title_rift_walker": {
        "name": "Странник Разломов", "slot": "title", "rarity": "rare", "lineup": "threshold",
        "text": "Странник Разломов", "css": "title-rift-walker",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Бродит между мирами. Фиолетовый пульс. Отображается при активной VIP.",
    },
    "cos_title_sentinel": {
        "name": "Часовой Пустоши", "slot": "title", "rarity": "rare", "lineup": "threshold",
        "text": "Часовой Пустоши", "css": "title-sentinel",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хладнокровный страж. Стальной акцент. Отображается при активной VIP.",
    },
    "cos_title_keeper": {
        "name": "Хранитель Порога", "slot": "title", "rarity": "rare", "lineup": "threshold",
        "text": "Хранитель Порога", "css": "title-keeper",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Спокойная уверенность стража границы. Отображается при активной VIP.",
    },

    # ═══════════════════════ ❄️ ИЗМОРОЗЬ (440✨, с VIP) — 12 предметов ════════
    # 5 уже существовали (pbg-midnight репрайснут common→rare — тёмно-синяя
    # полночь визуально ближе к зиме, чем что-либо оставшееся в common), 7 новых
    # (icy-тема в старом каталоге была тоньше остальных).
    "cos_name_glow_frost": {
        "name": "Ледяная вязь", "slot": "name_glow", "rarity": "rare", "lineup": "frost",
        "css": "glow-frost", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хрустальное ледяное свечение вокруг ника. Отображается при активной VIP.",
    },
    "cos_name_glow_frostbreath": {
        "name": "Морозное дыхание", "slot": "name_glow", "rarity": "rare", "lineup": "frost",
        "css": "glow-frostbreath", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Ледяной пар мягко пульсирует вокруг ника. Отображается при активной VIP.",
    },
    "cos_avatar_frame_crystal": {
        "name": "Кристальная грань", "slot": "avatar_frame", "rarity": "rare", "lineup": "frost",
        "css": "frame-crystal", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Чёткая ледяная кромка с ребристым блеском. Отображается при активной VIP.",
    },
    "cos_avatar_frame_icespikes": {
        "name": "Ледяные шипы", "slot": "avatar_frame", "rarity": "rare", "lineup": "frost",
        "css": "frame-icespikes", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Острые кристаллы льда потрескивают по кромке аватара. Отображается при активной VIP.",
    },
    "cos_avatar_halo_ice": {
        "name": "Ледяной сполох", "slot": "avatar_halo", "rarity": "rare", "lineup": "frost",
        "css": "halo-ice", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Хрустальный ледяной ореол. Чистый и резкий. Отображается при активной VIP.",
    },
    "cos_avatar_halo_snowcrown": {
        "name": "Снежная корона", "slot": "avatar_halo", "rarity": "rare", "lineup": "frost",
        "css": "halo-snowcrown", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Яркая снежно-белая вспышка венцом вокруг аватара. Отображается при активной VIP.",
    },
    "cos_profile_bg_midnight": {
        "name": "Полночь", "slot": "profile_bg", "rarity": "rare", "lineup": "frost",
        "css": "pbg-midnight", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Глубокий полночный синий. Спокойный и элегантный. Отображается при активной VIP.",
    },
    "cos_profile_bg_snowpeak": {
        "name": "Снежная вершина", "slot": "profile_bg", "rarity": "rare", "lineup": "frost",
        "css": "pbg-snowpeak", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Заснеженная горная вершина в морозной дымке. Отображается при активной VIP.",
    },
    "cos_card_fx_snow": {
        "name": "Снегопад", "slot": "card_fx", "rarity": "rare", "lineup": "frost",
        "css": "cfx-snow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Тихо падающие снежинки поверх профиля. Отображается при активной VIP.",
    },
    "cos_card_fx_frostbite": {
        "name": "Изморозь", "slot": "card_fx", "rarity": "rare", "lineup": "frost",
        "css": "cfx-frostbite", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Иней наступает по углам карточки. Отображается при активной VIP.",
    },
    "cos_title_frostchild": {
        "name": "Дитя Стужи", "slot": "title", "rarity": "rare", "lineup": "frost",
        "text": "Дитя Стужи", "css": "title-frostchild",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Рождённый среди вечных льдов. Отображается при активной VIP.",
    },
    "cos_title_icekeeper": {
        "name": "Хранитель Льда", "slot": "title", "rarity": "rare", "lineup": "frost",
        "text": "Хранитель Льда", "css": "title-icekeeper",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 440}],
        "desc": "Страж ледяных пределов. Отображается при активной VIP.",
    },

    # ═══════════════════════ 🔥 ИНФЕРНО (630✨, с VIP) — 12 предметов ═════════
    # 7 уже существовали (frame-inferno legendary→epic, pbg-ember/pbg-crimson/
    # cfx-embers rare→epic — все были УЖЕ огненными по имени, просто другой
    # ценовой ярус), 5 новых (гало не было ни одного огненного).
    "cos_name_glow_crimson": {
        "name": "Багровое пламя", "slot": "name_glow", "rarity": "epic", "lineup": "inferno",
        "css": "glow-crimson", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Зловещее багровое свечение из глубин Бездны. Отображается при активной VIP.",
    },
    "cos_name_glow_ember": {
        "name": "Тлеющий уголь", "slot": "name_glow", "rarity": "epic", "lineup": "inferno",
        "css": "glow-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Спокойное тёплое тление букв. Отображается при активной VIP.",
    },
    "cos_avatar_frame_inferno": {
        "name": "Инферно", "slot": "avatar_frame", "rarity": "epic", "lineup": "inferno",
        "css": "frame-inferno", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Живое пламя Инферно лижет края аватара — жар поднимается вверх.",
    },
    "cos_avatar_frame_coal": {
        "name": "Угольная кираса", "slot": "avatar_frame", "rarity": "epic", "lineup": "inferno",
        "css": "frame-coal", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тлеющие угли по кромке аватара, редкие яркие вспышки. Отображается при активной VIP.",
    },
    "cos_avatar_halo_flame_crown": {
        "name": "Пламенный венец", "slot": "avatar_halo", "rarity": "epic", "lineup": "inferno",
        "css": "halo-flame-crown", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Живое пламя венцом пляшет вокруг аватара. Отображается при активной VIP.",
    },
    "cos_avatar_halo_smolder": {
        "name": "Тлеющее ядро", "slot": "avatar_halo", "rarity": "epic", "lineup": "inferno",
        "css": "halo-smolder", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Ровное тление тёмно-красного жара. Отображается при активной VIP.",
    },
    "cos_profile_bg_ember": {
        "name": "Тлеющий вулкан", "slot": "profile_bg", "rarity": "epic", "lineup": "inferno",
        "css": "pbg-ember", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Раскалённые угли вулкана тлеют снизу карточки. Отображается при активной VIP.",
    },
    "cos_profile_bg_crimson": {
        "name": "Багровый горизонт", "slot": "profile_bg", "rarity": "epic", "lineup": "inferno",
        "css": "pbg-crimson", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёмно-красные тона закатного неба. Отображается при активной VIP.",
    },
    "cos_card_fx_embers": {
        "name": "Угольки", "slot": "card_fx", "rarity": "epic", "lineup": "inferno",
        "css": "cfx-embers", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 630}],
        "desc": "Поднимающиеся тлеющие угольки. Выдаётся с VIP или за зарники.",
    },
    "cos_card_fx_ash": {
        "name": "Пепел", "slot": "card_fx", "rarity": "epic", "lineup": "inferno",
        "css": "cfx-ash", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Серый пепел медленно оседает поверх карточки. Отображается при активной VIP.",
    },
    "cos_title_ember_born": {
        "name": "Рождённый Пеплом", "slot": "title", "rarity": "epic", "lineup": "inferno",
        "text": "Рождённый Пеплом", "css": "title-ember-born",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тлеющий оранжевый акцент. Отображается при активной VIP.",
    },
    "cos_title_flame_eater": {
        "name": "Пожиратель Пламени", "slot": "title", "rarity": "epic", "lineup": "inferno",
        "text": "🔥 Пожиратель Пламени", "css": "title-flame-eater",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тот, кто питается огнём Инферно. Отображается при активной VIP.",
    },

    # ═══════════════════ ✨ НЕБЕСНОЕ СИЯНИЕ (820✨, с VIP) — 13 предметов ═════
    # 8 уже существовали (halo-aurora epic→legendary — тот же небесный
    # словарь, просто другой ярус), 5 новых.
    "cos_name_glow_solar": {
        "name": "Солнечная корона", "slot": "name_glow", "rarity": "legendary", "lineup": "celestial",
        "css": "glow-solar", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Раскалённая золотисто-белая корона звезды. Медленно пульсирует теплом.",
    },
    "cos_name_glow_starwhisper": {
        "name": "Звёздный шёпот", "slot": "name_glow", "rarity": "legendary", "lineup": "celestial",
        "css": "glow-starwhisper", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Прохладное бело-голубое мерцание, редкие вспышки звёзд. Отображается при активной VIP.",
    },
    "cos_avatar_frame_celestial": {
        "name": "Небесная оправа", "slot": "avatar_frame", "rarity": "legendary", "lineup": "celestial",
        "css": "frame-celestial", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 820}],
        "desc": "Светящаяся небесная рамка. Выдаётся с VIP или за зарники.",
    },
    "cos_avatar_frame_dawn_disc": {
        "name": "Диск Зари", "slot": "avatar_frame", "rarity": "legendary", "lineup": "celestial",
        "css": "frame-dawn-disc", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Тёплый пульсирующий диск цвета рассветного неба. Отображается при активной VIP.",
    },
    "cos_avatar_halo_celestial": {
        "name": "Небесный нимб", "slot": "avatar_halo", "rarity": "legendary", "lineup": "celestial",
        "css": "halo-celestial", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}], "bp_level": 30,
        "desc": "Золотой нимб с лучами. Награда БП (уровень 30) или за зарники.",
    },
    "cos_avatar_halo_corona": {
        "name": "Солнечная корона", "slot": "avatar_halo", "rarity": "legendary", "lineup": "celestial",
        "css": "halo-corona", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Четырёхслойная солнечная корона бьёт светом. Пульсирующая звезда за спиной.",
    },
    "cos_avatar_halo_aurora": {
        "name": "Аврора", "slot": "avatar_halo", "rarity": "legendary", "lineup": "celestial",
        "css": "halo-aurora", "vip_required": False, "source": "vip",
        "price": [{"zarniki": 820}],
        "desc": "Переливы северного сияния. Выдаётся с VIP или за зарники.",
    },
    "cos_profile_bg_sunrise": {
        "name": "Рассвет", "slot": "profile_bg", "rarity": "legendary", "lineup": "celestial",
        "css": "pbg-sunrise", "vip_required": False, "source": "bp",
        "price": [{"zarniki": 820}], "bp_level": 40,
        "desc": "Тёплый градиент рассвета. Награда БП (уровень 40) или за зарники.",
    },
    "cos_profile_bg_aurora": {
        "name": "Полярное сияние", "slot": "profile_bg", "rarity": "legendary", "lineup": "celestial",
        "css": "pbg-aurora", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Живое северное сияние: зелёные и синие волны медленно плывут по тёмному небу.",
    },
    "cos_card_fx_nova": {
        "name": "Вспышка Новой", "slot": "card_fx", "rarity": "legendary", "lineup": "celestial",
        "css": "cfx-nova", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Взрыв света из центра карточки — расширяется и гаснет. Повторяется снова.",
    },
    "cos_card_fx_solar_wind": {
        "name": "Солнечный Ветер", "slot": "card_fx", "rarity": "legendary", "lineup": "celestial",
        "css": "cfx-solar-wind", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Тёплые частицы солнечного ветра дрейфуют над карточкой. Отображается при активной VIP.",
    },
    "cos_title_dawnchild": {
        "name": "Дитя Зари", "slot": "title", "rarity": "legendary", "lineup": "celestial",
        "text": "Дитя Зари", "css": "title-dawnchild",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Рождённый на рассвете. Отображается при активной VIP.",
    },
    "cos_title_skykeeper": {
        "name": "Хранитель Небес", "slot": "title", "rarity": "legendary", "lineup": "celestial",
        "text": "Хранитель Небес", "css": "title-skykeeper",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 820}],
        "desc": "Страж высот. Отображается при активной VIP.",
    },

    # ═══════════════════════ 🌌 БЕЗДНА (1000✨, с VIP) — 12 предметов ═════════
    # 100% уже существовали (12 из 12, 0 новых) — все уже были mythic/1000✨,
    # просто никогда не продавались одним сетом.
    "cos_name_glow_rift": {
        "name": "Разлом Бездны", "slot": "name_glow", "rarity": "mythic", "lineup": "void",
        "css": "glow-rift", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Имя пылает разломом: фиолет–багрянец–золото. Особая награда или покупка за зарники.",
    },
    "cos_name_glow_void": {
        "name": "Голос Пустоты", "slot": "name_glow", "rarity": "mythic", "lineup": "void",
        "css": "glow-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмно-фиолетовый шёпот с редкими вспышками на границах букв. Особая награда или за зарники.",
    },
    "cos_avatar_frame_void": {
        "name": "Разлом Пустоты", "slot": "avatar_frame", "rarity": "mythic", "lineup": "void",
        "css": "frame-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Чёрная кромка с редкими фиолетовыми разрядами. Особая награда или за зарники.",
    },
    "cos_avatar_frame_omen": {
        "name": "Оправа Предвестника", "slot": "avatar_frame", "rarity": "mythic", "lineup": "void",
        "css": "frame-omen", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Вращающийся ореол разлома вокруг аватара. Особая награда или за зарники.",
    },
    "cos_avatar_halo_eclipse": {
        "name": "Затмение", "slot": "avatar_halo", "rarity": "mythic", "lineup": "void",
        "css": "halo-eclipse", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмный диск с тонкой пылающей короной по кромке. Особая награда или за зарники.",
    },
    "cos_avatar_halo_void": {
        "name": "Кольцо Бездны", "slot": "avatar_halo", "rarity": "mythic", "lineup": "void",
        "css": "halo-void", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмное кольцо с багровыми всполохами. Особая награда или за зарники.",
    },
    "cos_profile_bg_legend": {
        "name": "Холст Легенды", "slot": "profile_bg", "rarity": "mythic", "lineup": "void",
        "css": "pbg-legend", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Живой золотисто-чёрный холст. Особая награда или за зарники.",
    },
    "cos_profile_bg_starfall": {
        "name": "Звездопад Богов", "slot": "profile_bg", "rarity": "mythic", "lineup": "void",
        "css": "pbg-starfall", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Глубокий космос с падающими звёздами. Особая награда или за зарники.",
    },
    "cos_card_fx_void_storm": {
        "name": "Шторм Бездны", "slot": "card_fx", "rarity": "mythic", "lineup": "void",
        "css": "cfx-void-storm", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Багровые частицы Бездны в вихре. Особая награда или за зарники.",
    },
    "cos_card_fx_eclipse_ash": {
        "name": "Пепел Затмения", "slot": "card_fx", "rarity": "mythic", "lineup": "void",
        "css": "cfx-eclipse-ash", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Тёмный пепел медленно оседает с редкими багровыми всполохами. Особая награда или за зарники.",
    },
    "cos_title_omen": {
        "name": "Предвестник", "slot": "title", "rarity": "mythic", "lineup": "void",
        "text": "Предвестник", "css": "title-omen",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Мифический титул. Особая награда или за зарники.",
    },
    "cos_title_harbinger": {
        "name": "Предвестник Конца", "slot": "title", "rarity": "mythic", "lineup": "void",
        "text": "Предвестник Конца", "css": "title-harbinger",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 1000}],
        "desc": "Мифический титул. Пурпурный шёпот. Особая награда или за зарники.",
    },

    # ══════════════════════ ⚡ АРТЕФАКТ (1500✨, с VIP) — 13 предметов ════════
    # 9 уже существовали (единственная линейка, которая УЖЕ была отдельным
    # премиум-ярусом — просто добавили разнообразия), 4 новых.
    "cos_name_glow_neon": {
        "name": "Неоновая трубка", "slot": "name_glow", "rarity": "artifact", "lineup": "artifact",
        "css": "glow-neon-tube", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Ник светится как неоновая вывеска: чёткая обводка букв и ровное дыхание сияния. Показывается при активной VIP.",
    },
    "cos_name_glow_electro": {
        "name": "Электро-разряд", "slot": "name_glow", "rarity": "artifact", "lineup": "artifact",
        "css": "glow-electro", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "По контуру ника пробегают резкие электрические разряды — живой нервный ток. Показывается при активной VIP.",
    },
    "cos_name_glow_plasma": {
        "name": "Плазменный контур", "slot": "name_glow", "rarity": "artifact", "lineup": "artifact",
        "css": "glow-plasma", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Обводка ника медленно переливается всеми цветами плазмы. Показывается при активной VIP.",
    },
    "cos_name_glow_hologram": {
        "name": "Голограмма", "slot": "name_glow", "rarity": "artifact", "lineup": "artifact",
        "css": "glow-hologram", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Голографический раскол цвета по краям букв — как дорогая голограмма. Показывается при активной VIP.",
    },
    "cos_avatar_frame_artifact": {
        "name": "Энергокольцо", "slot": "avatar_frame", "rarity": "artifact", "lineup": "artifact",
        "css": "frame-artifact", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Аватар в кольце живой циан-магента энергии, которое пульсирует. Показывается при активной VIP.",
    },
    "cos_avatar_frame_artifact_data": {
        "name": "Кольцо Данных", "slot": "avatar_frame", "rarity": "artifact", "lineup": "artifact",
        "css": "frame-artifact-data", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Рваное вращающееся кольцо данных вокруг аватара. Показывается при активной VIP.",
    },
    "cos_avatar_halo_artifact": {
        "name": "Ореол Артефакта", "slot": "avatar_halo", "rarity": "artifact", "lineup": "artifact",
        "css": "halo-artifact", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Голографический ореол вокруг аватара — циановое ядро с магента-отсветом. Показывается при активной VIP.",
    },
    "cos_avatar_halo_artifact_grid": {
        "name": "Сетка Сингулярности", "slot": "avatar_halo", "rarity": "artifact", "lineup": "artifact",
        "css": "halo-artifact-grid", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Вращающаяся радиальная решётка энергии. Показывается при активной VIP.",
    },
    "cos_profile_bg_artifact": {
        "name": "Голо-поле", "slot": "profile_bg", "rarity": "artifact", "lineup": "artifact",
        "css": "pbg-artifact", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Фон карточки — живое голографическое энергополе: диагональные лучи света дрейфуют по тёмной глубине. Показывается при активной VIP.",
    },
    "cos_profile_bg_artifact_matrix": {
        "name": "Тёмная Матрица", "slot": "profile_bg", "rarity": "artifact", "lineup": "artifact",
        "css": "pbg-artifact-matrix", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Падающий вертикальный код на тёмном фоне. Показывается при активной VIP.",
    },
    "cos_card_fx_artifact": {
        "name": "Сканлайны", "slot": "card_fx", "rarity": "artifact", "lineup": "artifact",
        "css": "cfx-artifact", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Поверх всей карточки — голографические сканлайны и поднимающиеся частицы энергии, наклон+фольга по пальцу/гироскопу. Показывается при активной VIP.",
    },
    "cos_title_artifact": {
        "name": "Артефакт (титул)", "slot": "title", "rarity": "artifact", "lineup": "artifact",
        "text": "⚡ Артефакт", "css": "title-artifact",
        "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Титул с голографическим расколом цвета — под стать всему сету. Показывается при активной VIP.",
    },
    "cos_title_artifact_glitch": {
        "name": "Скол Реальности", "slot": "title", "rarity": "artifact", "lineup": "artifact",
        "text": "⟁ Скол Реальности", "css": "title-artifact-glitch",
        "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "RGB-сбой текста титула — на грани реальности. Показывается при активной VIP.",
    },

    # ═══════════════════════ 🌸 ХАНАМИ (630✨, с VIP) — 15 предметов ════════
    "cos_name_glow_hanami_ink": {
        "name": "Сакура в туши", "slot": "name_glow", "rarity": "epic", "lineup": "hanami",
        "css": "glow-hanami-ink", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёплая тушь и розовый свет проходят по краю букв, как цветение на свитке.",
    },
    "cos_name_glow_hanami_lantern": {
        "name": "Свет бумажного фонаря", "slot": "name_glow", "rarity": "epic", "lineup": "hanami",
        "css": "glow-hanami-lantern", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёплый янтарный блик проходит по имени сквозь розовую дымку вечернего сада.",
    },
    "cos_name_glow_hanami_dew": {
        "name": "Роса на сакуре", "slot": "name_glow", "rarity": "epic", "lineup": "hanami",
        "css": "glow-hanami-dew", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Светлая капля росы проходит по буквам поверх спокойного сливового контура.",
    },
    "cos_avatar_frame_hanami_branches": {
        "name": "Ветви ханами", "slot": "avatar_frame", "rarity": "epic", "lineup": "hanami",
        "css": "frame-hanami-branches", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тонкая тёмная оправа с редкими лепестками сакуры — выразительно, но без тяжёлого сияния.",
    },
    "cos_avatar_frame_hanami_lacquer": {
        "name": "Лак и сакура", "slot": "avatar_frame", "rarity": "epic", "lineup": "hanami",
        "css": "frame-hanami-lacquer", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Гладкая сливовая оправа с тонким перламутровым кантом, будто роспись на тёмном лаке.",
    },
    "cos_avatar_frame_hanami_goldleaf": {
        "name": "Золотой лист на лаке", "slot": "avatar_frame", "rarity": "epic", "lineup": "hanami",
        "css": "frame-hanami-goldleaf", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёмно-сливовый лак с редкими фрагментами сусального золота и розовым внутренним бликом.",
    },
    "cos_avatar_halo_hanami_petals": {
        "name": "Венец лепестков", "slot": "avatar_halo", "rarity": "epic", "lineup": "hanami",
        "css": "halo-hanami-petals", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Мягкий розовый ореол будто удерживает вокруг аватара несколько падающих лепестков.",
    },
    "cos_avatar_halo_hanami_afterglow": {
        "name": "Послесвечение цветения", "slot": "avatar_halo", "rarity": "epic", "lineup": "hanami",
        "css": "halo-hanami-afterglow", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Тёплое сливово-золотое свечение остаётся вокруг аватара, как закат после ханами.",
    },
    "cos_profile_bg_hanami_washi": {
        "name": "Сад на васи", "slot": "profile_bg", "rarity": "epic", "lineup": "hanami",
        "css": "pbg-hanami-washi", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Угольная бумага васи, дымчатая сакура и тёплый свет далёкого фонаря.",
    },
    "cos_profile_bg_hanami_lanterns": {
        "name": "Аллея фонарей", "slot": "profile_bg", "rarity": "epic", "lineup": "hanami",
        "css": "pbg-hanami-lanterns", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Глубокие сливовые сумерки и несколько тёплых огней между цветущими деревьями.",
    },
    "cos_profile_bg_hanami_rain": {
        "name": "Весенний дождь на васи", "slot": "profile_bg", "rarity": "epic", "lineup": "hanami",
        "css": "pbg-hanami-rain", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Прохладный дождь проступает поверх тёмной бумаги, а вдали теплеет один фонарь.",
    },
    "cos_card_fx_hanami_drift": {
        "name": "Тихий листопад", "slot": "card_fx", "rarity": "epic", "lineup": "hanami",
        "css": "cfx-hanami-drift", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Редкие лепестки медленно пересекают карточку и не закрывают важную информацию.",
    },
    "cos_card_fx_hanami_ink_bloom": {
        "name": "Цветение туши", "slot": "card_fx", "rarity": "epic", "lineup": "hanami",
        "css": "cfx-hanami-ink-bloom", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Полупрозрачное чернильное пятно медленно распускается у края карточки, как ветвь на свитке.",
    },
    "cos_card_fx_hanami_moths": {
        "name": "Мотыльки у фонаря", "slot": "card_fx", "rarity": "epic", "lineup": "hanami",
        "css": "cfx-hanami-moths", "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Три крошечных золотистых мотылька неспешно кружат у тёплого края карточки.",
    },
    "cos_title_hanami_witness": {
        "name": "Свидетель Ханами", "slot": "title", "rarity": "epic", "lineup": "hanami",
        "text": "Свидетель Ханами", "css": "title-hanami-witness",
        "vip_required": False, "source": "shop",
        "price": [{"zarniki": 630}],
        "desc": "Титул того, кто умеет заметить красоту, пока она не исчезла.",
    },

    # ══════════════════ 🪷 ЛУННЫЙ ЛОТОС (1500✨, с VIP) — 15 предметов ══════
    "cos_name_glow_moon_lotus": {
        "name": "Перламутр луны", "slot": "name_glow", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "glow-moon-lotus", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Перламутровый блик скользит по имени, сохраняя чёткий светлый контур букв.",
    },
    "cos_name_glow_lotus_reflection": {
        "name": "Серебро на воде", "slot": "name_glow", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "glow-lotus-reflection", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Холодное серебро дробится по буквам на тонкие отражения спокойной воды.",
    },
    "cos_name_glow_lotus_pearl": {
        "name": "Жемчужная дорожка", "slot": "name_glow", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "glow-lotus-pearl", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Розово-серебряный блик медленно собирается на имени в одну чистую лунную дорожку.",
    },
    "cos_avatar_frame_moon_lotus": {
        "name": "Жемчужный лотос", "slot": "avatar_frame", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "frame-moon-lotus", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Перламутровая оправа раскрывается вокруг аватара подобно лепесткам ночного лотоса.",
    },
    "cos_avatar_frame_lotus_silver": {
        "name": "Серебряная орбита", "slot": "avatar_frame", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "frame-lotus-silver", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Два тонких серебряных кольца расходятся вокруг аватара подобно отражению полной луны.",
    },
    "cos_avatar_frame_lotus_petal_orbit": {
        "name": "Орбита лепестков", "slot": "avatar_frame", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "frame-lotus-petal-orbit", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Тонкие лепестковые сегменты бесшумно обходят перламутровый край аватара.",
    },
    "cos_avatar_halo_moon_ripple": {
        "name": "Лунная рябь", "slot": "avatar_halo", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "halo-moon-ripple", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Серебряная водяная орбита дышит вокруг аватара, как круги под полной луной.",
    },
    "cos_avatar_halo_lotus_moonwake": {
        "name": "След полной луны", "slot": "avatar_halo", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "halo-lotus-moonwake", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Широкое перламутровое свечение оставляет за аватаром спокойный след на ночной воде.",
    },
    "cos_profile_bg_moon_lotus": {
        "name": "Озеро полнолуния", "slot": "profile_bg", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "pbg-moon-lotus", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Глубокое индиго, далёкая луна и тонкие серебряные отражения на чёрной воде.",
    },
    "cos_profile_bg_lotus_sanctuary": {
        "name": "Святилище зеркальной воды", "slot": "profile_bg", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "pbg-lotus-sanctuary", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Затопленное лунным светом святилище: вода, туман и едва заметные силуэты лотосов.",
    },
    "cos_profile_bg_lotus_eclipse": {
        "name": "Сад во время затмения", "slot": "profile_bg", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "pbg-lotus-eclipse", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Серебряный серп, фиолетовая тень и редкие лотосы на почти неподвижной чёрной воде.",
    },
    "cos_card_fx_moon_lotus": {
        "name": "Отражение лотоса", "slot": "card_fx", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "cfx-moon-lotus", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Свет луны преломляется на воде; редкий перламутровый лотос проявляется и снова уходит в глубину.",
    },
    "cos_card_fx_lotus_caustics": {
        "name": "Жемчужная каустика", "slot": "card_fx", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "cfx-lotus-caustics", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Очень тонкие световые узоры движутся по нижней части карточки, как лунные блики под водой.",
    },
    "cos_card_fx_lotus_fireflies": {
        "name": "Светлячки над водой", "slot": "card_fx", "rarity": "artifact", "lineup": "moon_lotus",
        "css": "cfx-lotus-fireflies", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Редкие жемчужные огни поднимаются над водой и гаснут, оставляя короткие круги на поверхности.",
    },
    "cos_title_moon_lotus": {
        "name": "Хранитель Лунного Лотоса", "slot": "title", "rarity": "artifact", "lineup": "moon_lotus",
        "text": "Хранитель Лунного Лотоса", "css": "title-moon-lotus",
        "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Редкий перламутровый титул хранителя ночного озера.",
    },

    # ══════════════════ 🐉 ПРИЛИВ РЮДЗИНА (1500✨, с VIP) — 15 предметов ════
    "cos_name_glow_ryujin_ink": {
        "name": "Грозовая каллиграфия", "slot": "name_glow", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "glow-ryujin-ink", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Холодная водяная тушь проходит по имени, а золотой импульс вспыхивает подобно молнии в облаках.",
    },
    "cos_name_glow_ryujin_gold": {
        "name": "Золото в прибое", "slot": "name_glow", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "glow-ryujin-gold", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Тёмный водяной контур и тонкая золотая кромка создают эффект надписи на чёрном лаке.",
    },
    "cos_name_glow_ryujin_foam": {
        "name": "Пена драконьей волны", "slot": "name_glow", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "glow-ryujin-foam", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Белый гребень прибоя на секунду высветляет холодный синий контур имени.",
    },
    "cos_avatar_frame_ryujin_kintsugi": {
        "name": "Кинцуги Рюдзина", "slot": "avatar_frame", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "frame-ryujin-kintsugi", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Чёрная лаковая оправа прорезана тонкими золотыми жилами и холодным светом прибоя.",
    },
    "cos_avatar_frame_ryujin_scale": {
        "name": "Чешуя морского дракона", "slot": "avatar_frame", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "frame-ryujin-scale", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Слоистая сине-чёрная оправа переливается, как мокрая чешуя в свете грозы.",
    },
    "cos_avatar_frame_ryujin_torii": {
        "name": "Врата в шторм", "slot": "avatar_frame", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "frame-ryujin-torii", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Строгая лаковая рамка с золотыми углами напоминает врата, стоящие перед морской бурей.",
    },
    "cos_avatar_halo_ryujin_tide": {
        "name": "Драконий прилив", "slot": "avatar_halo", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "halo-ryujin-tide", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Глубокая синяя орбита собирается вокруг аватара в движение драконьей волны.",
    },
    "cos_avatar_halo_ryujin_eye": {
        "name": "Око тайфуна", "slot": "avatar_halo", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "halo-ryujin-eye", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Холодный круг шторма собирается вокруг спокойного золотого центра.",
    },
    "cos_profile_bg_ryujin_storm": {
        "name": "Чернила шторма", "slot": "profile_bg", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "pbg-ryujin-storm", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Суми-э шторм движется в глубине чёрного лака, оставляя золотой след Рюдзина.",
    },
    "cos_profile_bg_ryujin_tempest": {
        "name": "Храм перед бурей", "slot": "profile_bg", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "pbg-ryujin-tempest", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Дальний силуэт храма растворяется между дождём, морской пеной и тяжёлым грозовым небом.",
    },
    "cos_profile_bg_ryujin_palace": {
        "name": "Дворец под приливом", "slot": "profile_bg", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "pbg-ryujin-palace", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Затонувшие золотые врата едва видны в глубоком синем потоке дворца морского дракона.",
    },
    "cos_card_fx_ryujin_current": {
        "name": "Течение Рюдзина", "slot": "card_fx", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "cfx-ryujin-current", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Чернильное течение огибает содержимое карточки; по гребню волны изредка проходит золотая молния.",
    },
    "cos_card_fx_ryujin_lightning": {
        "name": "Молния над морем", "slot": "card_fx", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "cfx-ryujin-lightning", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Редкая золотая вспышка прорезает холодный дождь и сразу оставляет карточку в спокойной темноте.",
    },
    "cos_card_fx_ryujin_ink_serpent": {
        "name": "Живые чернила Рюдзина", "slot": "card_fx", "rarity": "artifact", "lineup": "ryujin_tide",
        "css": "cfx-ryujin-ink-serpent", "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Тонкий драконий силуэт рождается из чернильного потока у нижнего края и снова растворяется в воде.",
    },
    "cos_title_ryujin_heir": {
        "name": "Наследник Рюдзина", "slot": "title", "rarity": "artifact", "lineup": "ryujin_tide",
        "text": "Наследник Рюдзина", "css": "title-ryujin-heir",
        "vip_required": True, "source": "shop",
        "price": [{"zarniki": 1500}],
        "desc": "Титул наследника морского дракона — тёмная сталь, вода и тонкое золото.",
    },
}


# Кураторские образы — серверный источник готовых сочетаний, а не клиентская
# имитация. Каждый образ обязан содержать ровно один реальный предмет на каждый
# визуальный слот. UI получает только эти стабильные ID и строит примерку из
# обычного каталога, поэтому цены, владение и VIP-правила остаются едиными.
CURATED_LOOKS: dict[str, dict] = {
    "hanami_washi_dawn": {
        "name": "Рассвет на васи", "lineup": "hanami",
        "mood": "Тихий сад, живая тушь и первый лепесток.",
        "items": {
            "name_glow": "cos_name_glow_hanami_ink",
            "avatar_frame": "cos_avatar_frame_hanami_branches",
            "avatar_halo": "cos_avatar_halo_hanami_petals",
            "title": "cos_title_hanami_witness",
            "profile_bg": "cos_profile_bg_hanami_washi",
            "card_fx": "cos_card_fx_hanami_drift",
        },
    },
    "hanami_lantern_rain": {
        "name": "Фонари после дождя", "lineup": "hanami",
        "mood": "Тёплый свет, мокрый лак и мотыльки в сумерках.",
        "items": {
            "name_glow": "cos_name_glow_hanami_lantern",
            "avatar_frame": "cos_avatar_frame_hanami_goldleaf",
            "avatar_halo": "cos_avatar_halo_hanami_afterglow",
            "title": "cos_title_hanami_witness",
            "profile_bg": "cos_profile_bg_hanami_rain",
            "card_fx": "cos_card_fx_hanami_moths",
        },
    },
    "lotus_full_moon": {
        "name": "Тишина полнолуния", "lineup": "moon_lotus",
        "mood": "Перламутровый цветок и круги на неподвижной воде.",
        "items": {
            "name_glow": "cos_name_glow_moon_lotus",
            "avatar_frame": "cos_avatar_frame_moon_lotus",
            "avatar_halo": "cos_avatar_halo_moon_ripple",
            "title": "cos_title_moon_lotus",
            "profile_bg": "cos_profile_bg_moon_lotus",
            "card_fx": "cos_card_fx_moon_lotus",
        },
    },
    "lotus_eclipse_garden": {
        "name": "Сад затмения", "lineup": "moon_lotus",
        "mood": "Жемчужная дорожка, тёмная луна и живые огни.",
        "items": {
            "name_glow": "cos_name_glow_lotus_pearl",
            "avatar_frame": "cos_avatar_frame_lotus_petal_orbit",
            "avatar_halo": "cos_avatar_halo_lotus_moonwake",
            "title": "cos_title_moon_lotus",
            "profile_bg": "cos_profile_bg_lotus_eclipse",
            "card_fx": "cos_card_fx_lotus_fireflies",
        },
    },
    "ryujin_storm_ink": {
        "name": "Чернила шторма", "lineup": "ryujin_tide",
        "mood": "Суми-э поток, морская чешуя и короткая золотая вспышка.",
        "items": {
            "name_glow": "cos_name_glow_ryujin_ink",
            "avatar_frame": "cos_avatar_frame_ryujin_scale",
            "avatar_halo": "cos_avatar_halo_ryujin_tide",
            "title": "cos_title_ryujin_heir",
            "profile_bg": "cos_profile_bg_ryujin_storm",
            "card_fx": "cos_card_fx_ryujin_lightning",
        },
    },
    "ryujin_sunken_palace": {
        "name": "Дворец под приливом", "lineup": "ryujin_tide",
        "mood": "Затонувшие врата, око тайфуна и след живого дракона.",
        "items": {
            "name_glow": "cos_name_glow_ryujin_foam",
            "avatar_frame": "cos_avatar_frame_ryujin_torii",
            "avatar_halo": "cos_avatar_halo_ryujin_eye",
            "title": "cos_title_ryujin_heir",
            "profile_bg": "cos_profile_bg_ryujin_palace",
            "card_fx": "cos_card_fx_ryujin_ink_serpent",
        },
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
# Отдельная система от линеек выше — свой слот "welcome" без записи владения.
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
# (services/cosmetics.migrate_legacy_ids). Исторический — оставлен как есть,
# переход на линейки 2026-07-29 ID не переименовывал, только метаданные.
# Часть значений здесь указывает на ID, которых больше нет в COSMETICS (были
# орфанами вне какой-либо линейки, удалены при полном wipe) — это НЕ баг: миграция
# просто переименует старый формат в новый, а get_catalog()/_owned() и так
# игнорируют ID, отсутствующие в текущем реестре.
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
