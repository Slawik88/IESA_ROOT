"""
core/themes.py
Каталог тем профиля. В текстовом боте «тема» = декоративная рамка + акцентный
эмодзи, применяемые к карточке профиля (бот я / бот профиль).

Поля темы:
  name      — отображаемое имя
  rarity    — common|uncommon|rare|epic|legendary|mythic|shadow|zarniki|seasonal
  source    — start|shop_mora|shop_diamond|gacha_*|dark|zarniki|event|auction
  gacha     — тип крутки, из которой может выпасть (novice/standard/premium/diamond)
  price_*   — цена в соответствующей валюте
  top/bot   — декоративные строки рамки
  accent    — эмодзи рядом с именем
"""
from typing import Dict, Any

THEME_RARITY_META = {
    "common":    {"badge": "⬜", "name": "Обычная"},
    "uncommon":  {"badge": "🟩", "name": "Необычная"},
    "rare":      {"badge": "🟦", "name": "Редкая"},
    "epic":      {"badge": "🟣", "name": "Эпическая"},
    "legendary": {"badge": "🟡", "name": "Легендарная"},
    "mythic":    {"badge": "🔴", "name": "Мифическая"},
    "shadow":    {"badge": "🌑", "name": "Теневая"},
    "zarniki":   {"badge": "✨", "name": "Зарниковая"},
    "seasonal":  {"badge": "🗓", "name": "Сезонная"},
}

# Порядок редкостей для вкладок/сортировки
RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary",
                "mythic", "shadow", "zarniki", "seasonal"]

THEMES: Dict[str, Dict[str, Any]] = {
    # ── СТАРТОВАЯ (выдаётся всем бесплатно) ──
    "theme_shadow": {"name": "🌑 Тень", "rarity": "common", "source": "start",
                     "accent": "🌑",
                     "top": "🌑▪️▪️▪️▪️▪️▪️▪️▪️🌑",
                     "sep": "▪️▫️▪️▫️▪️▫️▪️",
                     "bot": "🌑▪️▪️▪️▪️▪️▪️▪️▪️🌑",
                     "desc": "Стартовая тёмная тема. Минимализм."},
    # ── ⬜ ОБЫЧНЫЕ (магазин, Мора) ──
    "theme_dawn":  {"name": "🌅 Рассвет", "rarity": "common", "source": "shop_mora", "price_mora": 2500,
                    "accent": "🌅",
                    "top": "🌅✦━━━━━━━━━✦🌅",
                    "sep": "✦━━━━━━━━━✦",
                    "bot": "🌅✦━━━━━━━━━✦🌅",
                    "desc": "Тёплые оранжево-золотые тона."},
    "theme_dusk":  {"name": "🌆 Закат", "rarity": "common", "source": "shop_mora", "price_mora": 2500,
                    "accent": "🌆",
                    "top": "🌆✧━━━━━━━━━✧🌆",
                    "sep": "✧━━━━━━━━━✧",
                    "bot": "🌆✧━━━━━━━━━✧🌆",
                    "desc": "Сиреневые тона вечернего неба."},
    "theme_stone": {"name": "🪨 Камень", "rarity": "common", "source": "shop_mora", "price_mora": 1800,
                    "accent": "🪨",
                    "top": "🪨▰▰▰▰▰▰▰▰🪨",
                    "sep": "▰▱▰▱▰▱▰▱▰",
                    "bot": "🪨▰▰▰▰▰▰▰▰🪨",
                    "desc": "Грубые тяжёлые рамки."},
    "theme_leaf":  {"name": "🍃 Лист", "rarity": "common", "source": "shop_mora", "price_mora": 2000,
                    "accent": "🍃",
                    "top": "🍃〰〰〰〰〰〰🍃",
                    "sep": "〰〰〰〰〰〰",
                    "bot": "🍃〰〰〰〰〰〰🍃",
                    "desc": "Свежая зелёная листва."},
    # ── 🟩 НЕОБЫЧНЫЕ (магазин Алмазы / Обычная гача) — японские + природа ──
    "theme_sakura": {"name": "🌸 Сакура", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
                     "gacha": "novice", "accent": "🌸", "top": "🌸❀✿❀✿❀✿❀✿🌸", "bot": "❀✿❀✿❀✿❀✿❀✿", "desc": "Розовые лепестки, японские узоры."},
    "theme_torii":  {"name": "⛩ Тории", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 28,
                     "gacha": "novice", "accent": "⛩", "top": "⛩━━━━━━━━⛩", "bot": "🏮━━━━━━━━🏮", "desc": "Красные врата синтоистского храма."},
    "theme_koi":    {"name": "🎏 Карпы Кои", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 26,
                     "gacha": "novice", "accent": "🎏", "top": "🎏〰〰〰〰〰〰🎏", "bot": "〰〰〰〰〰〰〰〰", "desc": "Плывущие карпы, японский вымпел."},
    "theme_autumn": {"name": "🍂 Осень", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
                     "gacha": "novice", "accent": "🍂", "top": "🍂🍁🍂🍁🍂🍁🍂🍁", "bot": "🍁🍂🍁🍂🍁🍂🍁🍂", "desc": "Оранжево-красные листья."},
    "theme_ocean":  {"name": "🌊 Океан", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
                     "gacha": "novice", "accent": "🌊", "top": "🌊≈≈≈≈≈≈≈≈🌊", "bot": "≈≈≈≈≈≈≈≈≈≈", "desc": "Синие волны, пенные завитки."},
    "theme_snow":   {"name": "❄️ Снег", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
                     "gacha": "novice", "accent": "❄️", "top": "❄️•❄️•❄️•❄️•❄️", "bot": "•❄️•❄️•❄️•❄️•", "desc": "Снежинки, ледяные кристаллы."},
    # ── 🟦 РЕДКИЕ (магазин Алмазы / Стандартная гача) ──
    "theme_fuji":   {"name": "🗻 Фудзи", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 95,
                     "gacha": "standard", "accent": "🗻", "top": "🗻▲△▲△▲△▲△🗻", "bot": "△▲△▲△▲△▲△▲", "desc": "Священная гора в облаках."},
    "theme_fire":   {"name": "🔥 Пламя", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
                     "gacha": "standard", "accent": "🔥", "top": "🔥◢◣◢◣◢◣◢◣🔥", "bot": "◣◢◣◢◣◢◣◢◣◢", "desc": "Языки огня, пульсирующий оранжевый."},
    "theme_ice":    {"name": "🧊 Лёд", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
                     "gacha": "standard", "accent": "🧊", "top": "🧊◇◆◇◆◇◆◇◆🧊", "bot": "◆◇◆◇◆◇◆◇◆◇", "desc": "Острые ледяные узоры."},
    "theme_storm":  {"name": "⚡ Буря", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 90,
                     "gacha": "standard", "accent": "⚡", "top": "⚡╱╲╱╲╱╲╱╲⚡", "bot": "╲╱╲╱╲╱╲╱╲╱", "desc": "Молнии по контуру, грозовое небо."},
    "theme_moon":   {"name": "🌙 Лунная", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
                     "gacha": "standard", "accent": "🌙", "top": "🌙✦˚✦˚✦˚✦˚🌙", "bot": "˚✦˚✦˚✦˚✦˚✦", "desc": "Полумесяц и звёзды, серебро."},
    "theme_cherry": {"name": "🌺 Алая Вишня", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 95,
                     "gacha": "standard", "accent": "🌺", "top": "🌺❁❀❁❀❁❀❁❀🌺", "bot": "❀❁❀❁❀❁❀❁❀❁", "desc": "Глубокий красный, японская каллиграфия."},
    # ── 🟣 ЭПИЧЕСКИЕ (Премиум гача / Аукцион) ──
    "theme_geisha": {"name": "🪭 Гейша", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
                     "accent": "🪭", "top": "🪭✦❉✦❉✦❉✦❉🪭", "bot": "❉✦❉✦❉✦❉✦❉✦", "desc": "Веер, шёлк, восточная грация."},
    "theme_cosmos": {"name": "🌌 Космос", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
                     "accent": "🌌", "top": "🌌✦∗･ﾟ✦∗･ﾟ🌌", "bot": "∗･ﾟ✦∗･ﾟ✦∗･", "desc": "Галактика, туманности, звёзды."},
    "theme_dragon": {"name": "🐲 Дракон", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
                     "accent": "🐲", "top": "🐲〆〆〆〆〆〆〆🐲", "bot": "〆〆〆〆〆〆〆〆〆", "desc": "Чешуйчатые узоры, огненный акцент."},
    "theme_neon":   {"name": "💜 Неон", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
                     "accent": "💜", "top": "💜▮▯▮▯▮▯▮▯💜", "bot": "▯▮▯▮▯▮▯▮▯▮", "desc": "Яркие неоновые контуры на тёмном."},
    "theme_jade":   {"name": "🪷 Нефрит", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
                     "accent": "🪷", "top": "🪷❖❖❖❖❖❖❖🪷", "bot": "❖❖❖❖❖❖❖❖❖", "desc": "Зелёный камень, восточные орнаменты."},
    # ── 🟡 ЛЕГЕНДАРНЫЕ (Алмазная гача / Легенд. аукцион) ──
    "theme_herald":  {"name": "🔮 Предвестник", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
                      "accent": "🔮", "top": "🔮༄˚✦༄˚✦༄˚🔮", "bot": "༄˚✦༄˚✦༄˚✦", "desc": "Лоровая тема: пурпур, светящиеся руны."},
    "theme_phoenix": {"name": "🦅 Феникс", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
                      "accent": "🦅", "top": "🦅♨彡♨彡♨彡♨🦅", "bot": "彡♨彡♨彡♨彡♨彡", "desc": "Огненная птица, пепельные крылья."},
    "theme_royal":   {"name": "👑 Королевский", "rarity": "legendary", "source": "auction",
                      "accent": "👑", "top": "👑♛♔♛♔♛♔♛♔👑", "bot": "♔♛♔♛♔♛♔♛♔♛", "desc": "Золото, пурпур, корона."},
    "theme_aurora":  {"name": "🌈 Сияние", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
                      "accent": "🌈", "top": "🌈∼∽∼∽∼∽∼∽🌈", "bot": "∽∼∽∼∽∼∽∼∽∼", "desc": "Переливающееся северное сияние."},
    # ── 🔴 МИФИЧЕСКИЕ (ивенты) ──
    "theme_eclipsed": {"name": "🌑🌟 Затмение", "rarity": "mythic", "source": "event",
                       "accent": "🌟", "top": "🌑✦☀✦☀✦☀✦☀🌑", "bot": "☀✦☀✦☀✦☀✦☀✦", "desc": "Солнечное затмение. Топ-1 чат мирового события."},
    "theme_void":     {"name": "⚫ Пустота", "rarity": "mythic", "source": "event",
                       "accent": "⚫", "top": "⚫⠂⠂⠂⠂⠂⠂⠂⠂⚫", "bot": "⠂⠂⠂⠂⠂⠂⠂⠂⠂⠂", "desc": "Абсолютный ноль. Лунное затмение (5%)."},
    # ── 🌑 ТЕНЕВЫЕ (Тёмная Мора / Чёрный рынок) ──
    "theme_dark_trade": {"name": "💀 Теневой Торговец", "rarity": "shadow", "source": "dark", "price_dark": 100,
                         "accent": "💀", "top": "💀†☠†☠†☠†☠💀", "bot": "†☠†☠†☠†☠†☠", "desc": "Силуэт торговца Чёрного рынка."},
    "theme_forbidden":  {"name": "🔒 Запретный", "rarity": "shadow", "source": "dark", "price_dark": 180,
                         "accent": "🔒", "top": "🔒⛓⛓⛓⛓⛓⛓⛓🔒", "bot": "⛓⛓⛓⛓⛓⛓⛓⛓⛓", "desc": "Цепи и замки по рамке."},
    "theme_banished":   {"name": "👁 Изгнанник", "rarity": "shadow", "source": "dark", "price_dark": 280,
                         "accent": "👁", "top": "👁▚▞▚▞▚▞▚▞👁", "bot": "▞▚▞▚▞▚▞▚▞▚", "desc": "Красный глаз, сломанные рамки."},
    # ── ✨ ЗАРНИКОВЫЕ (донат) ──
    "theme_starlight":  {"name": "🌟 Звёздный Свет", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 100,
                         "accent": "🌟", "top": "🌟⋆｡˚⋆｡˚⋆｡˚🌟", "bot": "｡˚⋆｡˚⋆｡˚⋆｡˚", "desc": "Золотые звёзды, мягкое сияние."},
    "theme_velvet":     {"name": "🟪 Бархат", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 150,
                         "accent": "🟪", "top": "🟪❧❦❧❦❧❦❧❦🟪", "bot": "❦❧❦❧❦❧❦❧❦❧", "desc": "Фиолетовый бархат, золотая вышивка."},
    "theme_prism":      {"name": "🌈 Призма", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 200,
                         "accent": "🔆", "top": "🔆◳◰◲◱◳◰◲◱🔆", "bot": "◰◲◱◳◰◲◱◳◰◲", "desc": "Радужное преломление, кристальный блеск."},
    "theme_celestial":  {"name": "☀️ Небесный", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 250,
                         "accent": "☀️", "top": "☀️☁⛅☁⛅☁⛅☁☀️", "bot": "☁⛅☁⛅☁⛅☁⛅☁", "desc": "Солнечные лучи, ангельские крылья."},
    # ── 🗓 СЕЗОННЫЕ (ивенты в сезон) ──
    "theme_newyear":    {"name": "🎆 Новый Год", "rarity": "seasonal", "source": "event",
                         "accent": "🎆", "top": "🎆🎄✦🎄✦🎄✦🎄🎆", "bot": "✦🎄✦🎄✦🎄✦🎄✦", "desc": "Зимний фестиваль, декабрь."},
    "theme_summer":     {"name": "🌻 Солнцестояние", "rarity": "seasonal", "source": "event",
                         "accent": "🌻", "top": "🌻☀🌻☀🌻☀🌻☀🌻", "bot": "☀🌻☀🌻☀🌻☀🌻☀", "desc": "День солнца, июнь."},
}

# Auto-compute sep for themes that don't define it explicitly.
# sep = section separator shown between profile blocks.
_SEP_DEFAULTS: Dict[str, str] = {
    "theme_sakura": "❀✿❀✿❀✿❀✿",  "theme_torii": "⛩━━━━━━━━⛩",
    "theme_koi": "〰〰〰〰〰〰",     "theme_autumn": "🍁🍂🍁🍂🍁🍂",
    "theme_ocean": "≈≈≈≈≈≈≈≈",    "theme_snow": "•❄️•❄️•❄️•",
    "theme_fuji": "▲△▲△▲△▲",       "theme_fire": "◢◣◢◣◢◣◢",
    "theme_ice": "◇◆◇◆◇◆◇",        "theme_storm": "╱╲╱╲╱╲╱",
    "theme_moon": "✦˚✦˚✦˚✦",        "theme_cherry": "❁❀❁❀❁❀❁",
    "theme_geisha": "✦❉✦❉✦❉✦",      "theme_cosmos": "∗･ﾟ✦∗･ﾟ✦",
    "theme_dragon": "〆〆〆〆〆〆〆", "theme_neon": "▮▯▮▯▮▯▮",
    "theme_jade": "❖❖❖❖❖❖❖",        "theme_herald": "༄˚✦༄˚✦",
    "theme_phoenix": "♨彡♨彡♨彡",   "theme_royal": "♛♔♛♔♛♔♛",
    "theme_aurora": "∼∽∼∽∼∽∼",      "theme_eclipsed": "✦☀✦☀✦☀✦",
    "theme_void": "⠂⠂⠂⠂⠂⠂⠂⠂",     "theme_dark_trade": "†☠†☠†☠†",
    "theme_forbidden": "⛓⛓⛓⛓⛓⛓", "theme_banished": "▚▞▚▞▚▞▚",
    "theme_starlight": "⋆｡˚⋆｡˚⋆",   "theme_velvet": "❧❦❧❦❧❦❧",
    "theme_prism": "◳◰◲◱◳◰◲◱",       "theme_celestial": "☁⛅☁⛅☁⛅",
    "theme_newyear": "🎄✦🎄✦🎄✦",    "theme_summer": "☀🌻☀🌻☀🌻",
}
for _tid, _tdata in THEMES.items():
    if "sep" not in _tdata:
        _tdata["sep"] = _SEP_DEFAULTS.get(_tid, "─" * 8)


# Какие темы могут выпасть в гаче (по типу крутки)
THEME_GACHA_DROPS: Dict[str, list] = {
    "novice":   [t for t, d in THEMES.items() if d.get("gacha") == "novice"],
    "standard": [t for t, d in THEMES.items() if d.get("gacha") == "standard"],
    "premium":  [t for t, d in THEMES.items() if d.get("gacha") == "premium"],
    "diamond":  [t for t, d in THEMES.items() if d.get("gacha") == "diamond"],
}

DEFAULT_THEME = "theme_shadow"
