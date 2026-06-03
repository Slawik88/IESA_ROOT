"""
core/themes.py
Каталог тем профиля.

Поля темы:
  name        — отображаемое имя
  rarity      — common|uncommon|rare|epic|legendary|mythic|shadow|zarniki|seasonal
  source      — start|shop_mora|shop_diamond|gacha_*|dark|zarniki|event|auction
  gacha       — тип крутки (novice/standard/premium/diamond)
  price_*     — цена в соответствующей валюте
  top         — шапка: «Заголовок\\nразделитель» для обычных тем;
                просто рамка ╔…╗ для zarniki
  sep         — разделитель между секциями профиля
  bot         — подвал: тематическая фраза; для zarniki «╚…{id}…╝\\nфраза»
  accent      — эмодзи рядом с именем
  side        — (legendary only) эмодзи-префикс перед именем и рангом
  prefix      — (zarniki only) символ левой «боковой линии» (┊ или │)
  id_in_bot   — (zarniki only) True → ID вставляется в bot вместо отдельной строки
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

RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary",
                "mythic", "shadow", "zarniki", "seasonal"]

THEMES: Dict[str, Dict[str, Any]] = {

    # ── СТАРТОВАЯ ────────────────────────────────────────────────────────────
    "theme_shadow": {
        # Тень: темнота, минимализм — 🌑 (чёрная луна/тень) + 🖤 (чёрное)
        "name": "🌑 Тень", "rarity": "common", "source": "start",
        "top": "🌑🖤 ПРОФИЛЬ 🖤🌑\n─🌑─🖤─🌑─🖤─🌑─🖤─🌑─",
        "sep": "─🌑─🖤─🌑─🖤─🌑─🖤─🌑─",
        "bot": "🌑 В тени рождается что-то настоящее…",
        "accent": "🌑",
        "desc": "Стартовая тёмная тема. Минимализм.",
    },

    # ── ⬜ COMMON ─────────────────────────────────────────────────────────────
    "theme_dawn": {
        "name": "🌅 Рассвет", "rarity": "common", "source": "shop_mora", "price_mora": 2500,
        "top": "🌅🌤 ПРОФИЛЬ 🌤🌅\n─🌅─🌤─🌅─🌤─🌅─🌤─🌅─",
        "sep": "─🌅─🌤─🌅─🌤─🌅─🌤─🌅─",
        "bot": "🌅 На рассвете всё возможно…",
        "accent": "🌅",
        "desc": "Тёплые оранжево-золотые тона.",
    },
    "theme_dusk": {
        "name": "🌆 Закат", "rarity": "common", "source": "shop_mora", "price_mora": 2500,
        "top": "🌇🌆 ПРОФИЛЬ 🌆🌇\n─🌇─🌆─🌇─🌆─🌇─🌆─🌇─",
        "sep": "─🌇─🌆─🌇─🌆─🌇─🌆─🌇─",
        "bot": "🌇 Солнце уходит, но оставляет краски…",
        "accent": "🌆",
        "desc": "Сиреневые тона вечернего неба.",
    },
    "theme_stone": {
        "name": "🪨 Камень", "rarity": "common", "source": "shop_mora", "price_mora": 1800,
        "top": "🪨⛰️ ПРОФИЛЬ ⛰️🪨\n─🪨─⛰️─🪨─⛰️─🪨─⛰️─🪨─",
        "sep": "─🪨─⛰️─🪨─⛰️─🪨─⛰️─🪨─",
        "bot": "🪨 Камень не сломить, он просто ждёт…",
        "accent": "🪨",
        "desc": "Грубые тяжёлые рамки.",
    },
    "theme_leaf": {
        "name": "🍃 Лист", "rarity": "common", "source": "shop_mora", "price_mora": 2000,
        "top": "🍃🌿 ПРОФИЛЬ 🌿🍃\n─🍃─🌿─🍃─🌿─🍃─🌿─🍃─",
        "sep": "─🍃─🌿─🍃─🌿─🍃─🌿─🍃─",
        "bot": "🍃 Листья всегда помнят ветер…",
        "accent": "🍃",
        "desc": "Свежая зелёная листва.",
    },

    # ── 🟩 UNCOMMON ───────────────────────────────────────────────────────────
    "theme_sakura": {
        "name": "🌸 Сакура", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
        "gacha": "novice",
        "top": "🌸🍃 ПРОФИЛЬ 🍃🌸\n─🌸─🍃─🌸─🍃─🌸─🍃─🌸─",
        "sep": "─🌸─🍃─🌸─🍃─🌸─🍃─🌸─",
        "bot": "🌸 Лепестки кружатся в воздухе…",
        "accent": "🌸",
        "desc": "Розовые лепестки, японские узоры.",
    },
    "theme_torii": {
        "name": "⛩️ Тории", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 28,
        "gacha": "novice",
        "top": "⛩️🏮 ПРОФИЛЬ 🏮⛩️\n─⛩️─🏮─⛩️─🏮─⛩️─🏮─⛩️─",
        "sep": "─⛩️─🏮─⛩️─🏮─⛩️─🏮─⛩️─",
        "bot": "⛩️ Врата открыты лишь для достойных…",
        "accent": "⛩️",
        "desc": "Красные врата синтоистского храма.",
    },
    "theme_koi": {
        "name": "🎏 Карпы Кои", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 26,
        "gacha": "novice",
        "top": "🎏💧 ПРОФИЛЬ 💧🎏\n─🎏─💧─🎏─💧─🎏─💧─🎏─",
        "sep": "─🎏─💧─🎏─💧─🎏─💧─🎏─",
        "bot": "🎏 Течение — лишь повод плыть сильнее…",
        "accent": "🎏",
        "desc": "Плывущие карпы, японский вымпел.",
    },
    "theme_autumn": {
        "name": "🍂 Осень", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
        "gacha": "novice",
        "top": "🍂🍁 ПРОФИЛЬ 🍁🍂\n─🍂─🍁─🍂─🍁─🍂─🍁─🍂─",
        "sep": "─🍂─🍁─🍂─🍁─🍂─🍁─🍂─",
        "bot": "🍂 Осень не плачет — она прощается…",
        "accent": "🍂",
        "desc": "Оранжево-красные листья.",
    },
    "theme_ocean": {
        "name": "🌊 Океан", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
        "gacha": "novice",
        "top": "🌊🐚 ПРОФИЛЬ 🐚🌊\n─🌊─🐚─🌊─🐚─🌊─🐚─🌊─",
        "sep": "─🌊─🐚─🌊─🐚─🌊─🐚─🌊─",
        "bot": "🌊 Настоящая глубина всегда спокойна…",
        "accent": "🌊",
        "desc": "Синие волны, пенные завитки.",
    },
    "theme_snow": {
        "name": "❄️ Снег", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 25,
        "gacha": "novice",
        "top": "❄️🌨️ ПРОФИЛЬ 🌨️❄️\n─❄️─🌨️─❄️─🌨️─❄️─🌨️─❄️─",
        "sep": "─❄️─🌨️─❄️─🌨️─❄️─🌨️─❄️─",
        "bot": "❄️ Каждая снежинка — уникальная история…",
        "accent": "❄️",
        "desc": "Снежинки, ледяные кристаллы.",
    },

    # ── 🟦 RARE ───────────────────────────────────────────────────────────────
    "theme_fuji": {
        "name": "🗻 Фудзи", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 95,
        "gacha": "standard",
        "top": "🗻🌸 ПРОФИЛЬ 🌸🗻\n═🗻═🌸═🗻═🌸═🗻═🌸═",
        "sep": "═🗻═🌸═🗻═🌸═🗻═🌸═",
        "bot": "🗻 Истинное величие кроется в спокойствии…",
        "accent": "🗻",
        "desc": "Священная гора в облаках.",
    },
    "theme_fire": {
        "name": "🔥 Пламя", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
        "gacha": "standard",
        "top": "🔥💥 ПРОФИЛЬ 💥🔥\n═🔥═💥═🔥═💥═🔥═💥═🔥═",
        "sep": "═🔥═💥═🔥═💥═🔥═💥═🔥═",
        "bot": "🔥 Огонь не спрашивает разрешения…",
        "accent": "🔥",
        "desc": "Языки огня, пульсирующий оранжевый.",
    },
    "theme_ice": {
        "name": "🧊 Лёд", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
        "gacha": "standard",
        "top": "🧊❄️ ПРОФИЛЬ ❄️🧊\n═🧊═❄️═🧊═❄️═🧊═❄️═🧊═",
        "sep": "═🧊═❄️═🧊═❄️═🧊═❄️═🧊═",
        "bot": "🧊 Холод кристаллизует истину…",
        "accent": "🧊",
        "desc": "Острые ледяные узоры.",
    },
    "theme_storm": {
        "name": "⚡ Буря", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 90,
        "gacha": "standard",
        "top": "⚡🌩️ ПРОФИЛЬ 🌩️⚡\n═⚡═🌩️═⚡═🌩️═⚡═🌩️═⚡═",
        "sep": "═⚡═🌩️═⚡═🌩️═⚡═🌩️═⚡═",
        "bot": "⚡ После сильной грозы небо всегда чище…",
        "accent": "⚡",
        "desc": "Молнии по контуру, грозовое небо.",
    },
    "theme_moon": {
        "name": "🌙 Лунная", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
        "gacha": "standard",
        "top": "🌙⭐ ПРОФИЛЬ ⭐🌙\n═🌙═⭐═🌙═⭐═🌙═⭐═🌙═",
        "sep": "═🌙═⭐═🌙═⭐═🌙═⭐═🌙═",
        "bot": "🌙 Луна видит всё, но предпочитает молчать…",
        "accent": "🌙",
        "desc": "Полумесяц и звёзды, серебро.",
    },
    "theme_cherry": {
        # Алая Вишня: алый цветок + вишня — 🌺 (алый гибискус) + 🍒 (вишня)
        "name": "🌺 Алая Вишня", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 95,
        "gacha": "standard",
        "top": "🌺🍒 ПРОФИЛЬ 🍒🌺\n═🌺═🍒═🌺═🍒═🌺═🍒═🌺═",
        "sep": "═🌺═🍒═🌺═🍒═🌺═🍒═🌺═",
        "bot": "🌺 Сладость с отчётливым привкусом опасности…",
        "accent": "🌺",
        "desc": "Глубокий красный, японская каллиграфия.",
    },

    # ── 🟣 EPIC ───────────────────────────────────────────────────────────────
    "theme_geisha": {
        "name": "🪭 Гейша", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "👘🪭 ПРОФИЛЬ 🪭👘\n═👘═🪭═👘═🪭═👘═🪭═👘═",
        "sep": "═👘═🪭═👘═🪭═👘═🪭═👘═",
        "bot": "👘 Искусство скрыто в каждом движении…",
        "accent": "🪭",
        "desc": "Веер, шёлк, восточная грация.",
    },
    "theme_cosmos": {
        "name": "🌌 Космос", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "🌌🪐 ПРОФИЛЬ 🪐🌌\n═🌌═🪐═🌌═🪐═🌌═🪐═🌌═",
        "sep": "═🌌═🪐═🌌═🪐═🌌═🪐═🌌═",
        "bot": "🌌 Вселенная слишком велика, чтобы быть одному…",
        "accent": "🌌",
        "desc": "Галактика, туманности, звёзды.",
    },
    "theme_dragon": {
        "name": "🐲 Дракон", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "🐲🔥 ПРОФИЛЬ 🔥🐲\n═🐲═✨═🔥═✨═🐲═✨═🔥═",
        "sep": "═🐲═✨═🔥═✨═🐲═✨═🔥═",
        "bot": "🐲 Дракон не просит. Он просто берёт своё…",
        "accent": "🐲",
        "desc": "Чешуйчатые узоры, огненный акцент.",
    },
    "theme_neon": {
        # Неон: неоновое свечение — 💜 (неоновый фиолетовый) + ⚡ (электрический разряд = buzz неона)
        "name": "💜 Неон", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "💜⚡ ПРОФИЛЬ ⚡💜\n═💜═⚡═💜═⚡═💜═⚡═💜═",
        "sep": "═💜═⚡═💜═⚡═💜═⚡═💜═",
        "bot": "💜 Этот город никогда не спит…",
        "accent": "💜",
        "desc": "Яркие неоновые контуры на тёмном.",
    },
    "theme_jade": {
        # Нефрит: зелёный камень — 💚 (нефритово-зелёный цвет) + 🪷 (лотос, буддийский символ нефрита)
        "name": "🪷 Нефрит", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "💚🪷 ПРОФИЛЬ 🪷💚\n═💚═🪷═💚═🪷═💚═🪷═💚═",
        "sep": "═💚═🪷═💚═🪷═💚═🪷═💚═",
        "bot": "💚 Нефрит — холодный камень вечности…",
        "accent": "💚",
        "desc": "Зелёный камень, восточные орнаменты.",
    },

    # ── 🟡 LEGENDARY ──────────────────────────────────────────────────────────
    # side= эмодзи перед именем и рангами (отличает legendary от других)
    "theme_herald": {
        "name": "🔮 Предвестник", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🔮✨ ПРЕДВЕСТНИК ✨🔮\n═🔮═✨═💜═✨═🔮═✨═💜═",
        "sep": "═🔮═✨═💜═✨═🔮═✨═💜═",
        "bot": "🔮 Судьба предречена, но её чернила ещё не высохли…",
        "accent": "🔮",
        "side": "💜",
        "desc": "Лоровая тема: пурпур, светящиеся руны.",
    },
    "theme_phoenix": {
        "name": "🦅 Феникс", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🦅🔥 ФЕНИКС 🔥🦅\n═🦅═🔥═✨═🔥═🦅═🔥═",
        "sep": "═🦅═🔥═✨═🔥═🦅═🔥═",
        "bot": "🦅 Сгореть дотла, чтобы снова обнять небо…",
        "accent": "🦅",
        "side": "🔥",
        "desc": "Огненная птица, пепельные крылья.",
    },
    "theme_royal": {
        "name": "👑 Королевский", "rarity": "legendary", "source": "auction",
        "top": "👑💎 КОРОЛЕВСКИЙ 💎👑\n═👑═💎═🌟═💎═👑═💎═",
        "sep": "═👑═💎═🌟═💎═👑═💎═",
        "bot": "👑 Корона не делает короля — она его подтверждает…",
        "accent": "👑",
        "side": "💎",
        "desc": "Золото, пурпур, корона.",
    },
    "theme_aurora": {
        "name": "🌈 Сияние", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🌈✨ СИЯНИЕ ✨🌈\n═🌈═✨═💫═✨═🌈═✨═",
        "sep": "═🌈═✨═💫═✨═🌈═✨═",
        "bot": "🌈 Северное сияние не нуждается в объяснениях…",
        "accent": "🌈",
        "side": "✨",
        "desc": "Переливающееся северное сияние.",
    },

    # ── 🔴 MYTHIC ─────────────────────────────────────────────────────────────
    "theme_eclipsed": {
        "name": "🌑🌟 Затмение", "rarity": "mythic", "source": "event",
        "top": "🌑🌟 ЗАТМЕНИЕ 🌟🌑\n🌑🌟🌑🌟🌑🌟🌑🌟🌑🌟🌑",
        "sep": "🌑🌟🌑🌟🌑🌟🌑🌟🌑🌟🌑",
        "bot": "🌟 Тьма не победила — она просто пришла в гости…",
        "accent": "🌟",
        "desc": "Солнечное затмение. Топ-1 чат мирового события.",
    },
    "theme_void": {
        "name": "⚫ Пустота", "rarity": "mythic", "source": "event",
        "top": "⚫🌑 ПУСТОТА 🌑⚫\n⚫🌌⚫🌌⚫🌌⚫🌌⚫🌌⚫",
        "sep": "⚫🌌⚫🌌⚫🌌⚫🌌⚫🌌⚫",
        "bot": "⚫ Здесь нет ничего. И именно поэтому — здесь есть всё.",
        "accent": "⚫",
        "desc": "Абсолютный ноль. Лунное затмение (5%).",
    },

    # ── 🌑 SHADOW ─────────────────────────────────────────────────────────────
    "theme_dark_trade": {
        "name": "💀 Теневой Торговец", "rarity": "shadow", "source": "dark", "price_dark": 100,
        "top": "💀🖤 ТЕНЕВОЙ РЫНОК 🖤💀\n─💀─🖤─☠️─🖤─💀─🖤─",
        "sep": "─💀─🖤─☠️─🖤─💀─🖤─",
        "bot": "💀 Добро пожаловать на наш чёрный рынок…",
        "accent": "💀",
        "desc": "Силуэт торговца Чёрного рынка.",
    },
    "theme_forbidden": {
        "name": "🔒 Запретный", "rarity": "shadow", "source": "dark", "price_dark": 180,
        "top": "🔒⛓️ ЗАПРЕТНЫЙ ⛓️🔒\n─🔒─⛓️─🔒─⛓️─🔒─⛓️─",
        "sep": "─🔒─⛓️─🔒─⛓️─🔒─⛓️─",
        "bot": "🔒 Запретное всегда манит вдвое сильнее…",
        "accent": "🔒",
        "desc": "Цепи и замки по рамке.",
    },
    "theme_banished": {
        "name": "👁 Изгнанник", "rarity": "shadow", "source": "dark", "price_dark": 280,
        "top": "👁🌑 ИЗГНАННИК 🌑👁\n─👁─🌑─👁─🌑─👁─🌑─",
        "sep": "─👁─🌑─👁─🌑─👁─🌑─",
        "bot": "👁 Изгнанник видит то, от чего другие отворачиваются…",
        "accent": "👁",
        "desc": "Красный глаз, сломанные рамки.",
    },

    # ── ✨ ZARNIKI ─────────────────────────────────────────────────────────────
    # prefix= символ левой стороны профиля (┊ или │)
    # id_in_bot= True → ID вставляется в bot через {id}, отдельная строка не нужна
    "theme_starlight": {
        "name": "🌟 Звёздный Свет", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 100,
        "top": "╔══ ≪ 🌟 ЗВЁЗДНЫЙ СВЕТ 🌟 ≫ ══╗",
        "sep": "╠═══ ✧ ════ ✧ ════ ✧ ═══╣",
        "bot": "╚════ ≪ 🌟 ID: {id} 🌟 ≫ ════╝\n🌟 Каждая звезда в этом небе — чья-то сбывшаяся мечта…",
        "accent": "🌟",
        "prefix": "┊ ",
        "id_in_bot": True,
        "desc": "Золотые звёзды, мягкое сияние.",
    },
    "theme_velvet": {
        "name": "🟪 Бархат", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 150,
        "top": "🟪 ═【 🌹 БАРХАТ 🌹 】═ 🟪",
        "sep": "┠ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┨",
        "bot": "🟪 ═【 🌹 ID: {id} 🌹 】═ 🟪\n🟪 Тёмный бархат скрывает всё, кроме истинного характера…",
        "accent": "🟪",
        "prefix": "│ ",
        "id_in_bot": True,
        "desc": "Фиолетовый бархат, золотая вышивка.",
    },
    "theme_prism": {
        "name": "🌈 Призма", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 200,
        "top": "✧ ═【 💎 СИЯНИЕ ПРИЗМЫ 💎 】═ ✧",
        "sep": "╠════ 🌈 ════ 🌈 ════╣",
        "bot": "✧ ═【 💎 ID: {id} 💎 】═ ✧\n💎 Свет всегда находит свой путь сквозь кристалл…",
        "accent": "🔆",
        "prefix": "│ ",
        "id_in_bot": True,
        "desc": "Радужное преломление, кристальный блеск.",
    },
    "theme_celestial": {
        "name": "☀️ Небесный", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 250,
        "top": "꧁ ━━ 🕊️ НЕБЕСНАЯ ВЫСЬ 🕊️ ━━ ꧂",
        "sep": "┠ ┈┈ ☀️ ┈┈ ☀️ ┈┈ ☀️ ┈┈ ┨",
        "bot": "꧁ ━━ 🕊️ ID: {id} 🕊️ ━━ ꧂\n☀️ Небо принадлежит лишь тем, кто смеет смотреть вверх…",
        "accent": "☀️",
        "prefix": "┊ ",
        "id_in_bot": True,
        "desc": "Солнечные лучи, ангельские крылья.",
    },

    # ── 🗓 SEASONAL ───────────────────────────────────────────────────────────
    "theme_newyear": {
        "name": "🎆 Новый Год", "rarity": "seasonal", "source": "event",
        "top": "🎄🎇 ПРОФИЛЬ 🎇🎄\n─✨─🎄─🎇─🎄─✨─🎄─🎇─",
        "sep": "─✨─🎄─🎇─🎄─✨─🎄─🎇─",
        "bot": "🎇 Новый год — это всегда чистый лист…",
        "accent": "🎆",
        "desc": "Зимний фестиваль, декабрь.",
    },
    "theme_summer": {
        "name": "🌻 Солнцестояние", "rarity": "seasonal", "source": "event",
        "top": "☀️🌻 ПРОФИЛЬ 🌻☀️\n─☀️─🌻─🌊─🌻─☀️─🌻─",
        "sep": "─☀️─🌻─🌊─🌻─☀️─🌻─",
        "bot": "🌻 Солнце на пике своей силы, забирай её себе…",
        "accent": "🌻",
        "desc": "День солнца, июнь.",
    },
}


# Какие темы могут выпасть в гаче (по типу крутки)
THEME_GACHA_DROPS: Dict[str, list] = {
    "novice":   [t for t, d in THEMES.items() if d.get("gacha") == "novice"],
    "standard": [t for t, d in THEMES.items() if d.get("gacha") == "standard"],
    "premium":  [t for t, d in THEMES.items() if d.get("gacha") == "premium"],
    "diamond":  [t for t, d in THEMES.items() if d.get("gacha") == "diamond"],
}

DEFAULT_THEME = "theme_shadow"
