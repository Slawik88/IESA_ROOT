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
        # Стартовая тема: строгий минимализм, без декора — только чистые линии
        "name": "🌑 Тень", "rarity": "common", "source": "start",
        "top": "🌑 ПРОФИЛЬ 🌑\n━━━━━━━━━━━━━━━━━━━━",
        "sep": "━━━━━━━━━━━━━━━━━━━━",
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
    # ── БЛОК 7: Японские темы подняты до rare (были uncommon, слишком дёшевы) ──
    "theme_sakura": {
        "name": "🌸 Сакура", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
        "gacha": "standard",
        "top": "🌸🍃 ПРОФИЛЬ 🍃🌸\n═🌸═🍃═🌸═🍃═🌸═🍃═🌸═",
        "sep": "═🌸═🍃═🌸═🍃═🌸═🍃═🌸═",
        "bot": "🌸 Лепестки кружатся в воздухе…",
        "accent": "🌸",
        "desc": "Розовые лепестки, японские узоры. Японская классика.",
    },
    "theme_torii": {
        "name": "⛩️ Тории", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 90,
        "gacha": "standard",
        "top": "⛩️🏮 ПРОФИЛЬ 🏮⛩️\n═⛩️═🏮═⛩️═🏮═⛩️═🏮═⛩️═",
        "sep": "═⛩️═🏮═⛩️═🏮═⛩️═🏮═⛩️═",
        "bot": "⛩️ Врата открыты лишь для достойных…",
        "accent": "⛩️",
        "desc": "Красные врата синтоистского храма. Редкая японская тема.",
    },
    "theme_koi": {
        "name": "🎏 Карпы Кои", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 85,
        "gacha": "standard",
        # Кои + вода (🌊) — редкая японская тема, разделитель ═ как у rare
        "top": "🎏🌊 ПРОФИЛЬ 🌊🎏\n═🎏═🌊═🎏═🌊═🎏═🌊═🎏═",
        "sep": "═🎏═🌊═🎏═🌊═🎏═🌊═🎏═",
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
        # Дракон: огонь + сокровище (💎). ✨ не про дракона
        "top": "🐲🔥 ПРОФИЛЬ 🔥🐲\n═🐲═💎═🔥═💎═🐲═💎═🔥═",
        "sep": "═🐲═💎═🔥═💎═🐲═💎═🔥═",
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
        # Сияние = северное сияние = аврора. 🌈 — радуга, не аврора.
        # 🌌 (ночное небо) + 🌠 (падающая звезда/сияние) — точнее передают aurora borealis
        "name": "🌌 Сияние", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🌌🌠 СИЯНИЕ 🌠🌌\n✨ 🌌 ══════════ 🌌 ✨",
        "sep": "✨ 🌌 ══════════ 🌌 ✨",
        "bot": "🌌 Северное сияние не нуждается в объяснениях…",
        "accent": "🌠",
        "side": "✨",
        "desc": "Переливающееся северное сияние над ночным небом.",
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
        # Пустота = абсолютная темнота. 🌌 (галактика) — слишком красочный. Только ⚫🌑
        "name": "⚫ Пустота", "rarity": "mythic", "source": "event",
        "top": "⚫🌑 ПУСТОТА 🌑⚫\n⚫ 🌑 ⚫ 🌑 ⚫ 🌑 ⚫ 🌑 ⚫",
        "sep": "⚫ 🌑 ⚫ 🌑 ⚫ 🌑 ⚫ 🌑 ⚫",
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
    "theme_starlight": {
        "name": "🌌 Starlight", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 100,
        "premium_template": "starlight",
        # Минимальные поля для совместимости (рендер идёт через premium_template)
        "top": "⋆ ˚｡ 🌌 S T A R L I G H T ｡˚ ⋆",
        "sep": "╰┈➤ ☄️ ┄┄ ☄️ ┄┄",
        "bot": "🌟 Каждая звезда — чья-то мечта…",
        "accent": "🌌",
        "desc": "Космический дашборд: бортовые данные, экипаж-дроны, звёздная пыль.",
    },
    "theme_velvet": {
        "name": "🟪 Бархат", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 150,
        "premium_template": "velvet",
        "top": "🟪 ═【 🌹 БАРХАТ 🌹 】═ 🟪",
        "sep": "┄┄ 🌹 ┄┄ 🌹 ┄┄",
        "bot": "🟪 Бархат скрывает истинный характер…",
        "accent": "🟪",
        "desc": "Фиолетовый бархат, золотая вышивка.",
    },
    "theme_prism": {
        "name": "🌈 Призма", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 200,
        "premium_template": "prism",
        "top": "✧ ═【 💎 ПРИЗМА 💎 】═ ✧",
        "sep": "┄┄ 🌈 ┄┄ 🌈 ┄┄",
        "bot": "💎 Свет находит путь сквозь кристалл…",
        "accent": "💎",
        "desc": "Радужное преломление, кристальный блеск.",
    },
    "theme_celestial": {
        "name": "☀️ Небесный", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 250,
        "premium_template": "celestial",
        "top": "꧁ ━━ ☀️ НЕБЕСНЫЙ ☀️ ━━ ꧂",
        "sep": "┄┄ ☀️ ┄┄ ☀️ ┄┄",
        "bot": "☀️ Небо для тех, кто смотрит ввысь…",
        "accent": "☀️",
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

    # ══ БЛОК 8: Новые темы ══════════════════════════════════════════════════

    # ── 🟩 UNCOMMON (природные мотивы) ──────────────────────────────────────
    "theme_desert": {
        "name": "🏜️ Мираж", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 27,
        "gacha": "novice",
        "top": "🏜️☀️ ПРОФИЛЬ ☀️🏜️\n─🏜️─☀️─🏜️─☀️─🏜️─☀️─🏜️─",
        "sep": "─🏜️─☀️─🏜️─☀️─🏜️─☀️─🏜️─",
        "bot": "🏜️ В пустыне каждый видит то, что хочет…",
        "accent": "🏜️",
        "desc": "Миражи раскалённых песков.",
    },
    "theme_bamboo": {
        "name": "🎋 Дзен", "rarity": "uncommon", "source": "shop_diamond", "price_diamonds": 26,
        "gacha": "novice",
        "top": "🎋🍵 ПРОФИЛЬ 🍵🎋\n─🎋─🍵─🎋─🍵─🎋─🍵─🎋─",
        "sep": "─🎋─🍵─🎋─🍵─🎋─🍵─🎋─",
        "bot": "🎋 Гнись под ветром, но никогда не ломайся…",
        "accent": "🎋",
        "desc": "Бамбуковый лес, японский дзен.",
    },

    # ── 🟦 RARE (глубокие явления) ───────────────────────────────────────────
    "theme_abyss": {
        "name": "🐋 Бездна", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 92,
        "gacha": "standard",
        "top": "🐋🌊 ПРОФИЛЬ 🌊🐋\n═🐋═🌊═🐋═🌊═🐋═🌊═🐋═",
        "sep": "═🐋═🌊═🐋═🌊═🐋═🌊═🐋═",
        "bot": "🐋 На самом дне давление создаёт алмазы…",
        "accent": "🐋",
        "desc": "Глубокий океан, абсолютное давление.",
    },
    "theme_amethyst": {
        "name": "🔮 Аметист", "rarity": "rare", "source": "shop_diamond", "price_diamonds": 88,
        "gacha": "standard",
        "top": "🔮💎 ПРОФИЛЬ 💎🔮\n═🔮═💎═🔮═💎═🔮═💎═🔮═",
        "sep": "═🔮═💎═🔮═💎═🔮═💎═🔮═",
        "bot": "🔮 Грани кристалла отражают твои мысли…",
        "accent": "🔮",
        "desc": "Фиолетовые кристаллы, мистический камень.",
    },

    # ── 🟣 EPIC (технология и мистика) ──────────────────────────────────────
    "theme_clockwork": {
        "name": "⚙️ Механизм", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "⏳⚙️ ПРОФИЛЬ ⚙️⏳\n═⏳═⚙️═⏳═⚙️═⏳═⚙️═⏳═",
        "sep": "═⏳═⚙️═⏳═⚙️═⏳═⚙️═⏳═",
        "bot": "⏳ Время не лечит, оно просто идёт вперёд…",
        "accent": "⚙️",
        "desc": "Шестерни, пар и бронза — стимпанк эпоха.",
    },
    "theme_cyber": {
        "name": "👾 Глитч", "rarity": "epic", "source": "gacha_premium", "gacha": "premium",
        "top": "👾🔌 ПРОФИЛЬ 🔌👾\n═👾═🔌═👾═🔌═👾═🔌═👾═",
        "sep": "═👾═🔌═👾═🔌═👾═🔌═👾═",
        "bot": "👾 Система работает нормально… [ERR_404]",
        "accent": "👾",
        "desc": "Кибер-эстетика, цифровые помехи.",
    },

    # ── 🟡 LEGENDARY (мифология) ─────────────────────────────────────────────
    "theme_tarot": {
        "name": "🃏 Оракул", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🃏👁️ ОРАКУЛ 👁️🃏\n═🃏═👁️═✨═👁️═🃏═✨═",
        "sep": "═🃏═👁️═✨═👁️═🃏═✨═",
        "bot": "🃏 Карты говорят правду — но готов ли ты её услышать?",
        "accent": "🃏",
        "side": "🃏",
        "desc": "Таро, предсказания, мистика.",
    },
    "theme_valkyrie": {
        "name": "🕊️ Валькирия", "rarity": "legendary", "source": "gacha_diamond", "gacha": "diamond",
        "top": "🕊️⚔️ ВАЛЬКИРИЯ ⚔️🕊️\n═🕊️═⚔️═✨═⚔️═🕊️═✨═",
        "sep": "═🕊️═⚔️═✨═⚔️═🕊️═✨═",
        "bot": "🕊️ Слава достаётся тем, кто не боится падать…",
        "accent": "🕊️",
        "side": "⚔️",
        "desc": "Небесная воительница, северная мифология.",
    },

    # ── 🔴 MYTHIC ─────────────────────────────────────────────────────────────
    "theme_bloodmoon": {
        "name": "🩸 Кровавая Луна", "rarity": "mythic", "source": "event",
        "top": "🩸🌕 КРОВАВАЯ ЛУНА 🌕🩸\n🩸🌕🩸🌕🩸🌕🩸🌕🩸🌕🩸",
        "sep": "🩸🌕🩸🌕🩸🌕🩸🌕🩸🌕🩸",
        "bot": "🌕 Когда небеса багровеют, секреты выходят наружу…",
        "accent": "🩸",
        "desc": "Кровавое полнолуние. Ивентовая мифическая тема.",
    },

    # ── 🌑 SHADOW ─────────────────────────────────────────────────────────────
    "theme_reaper": {
        "name": "🪦 Жнец", "rarity": "shadow", "source": "dark", "price_dark": 350,
        "top": "🪦🥀 ЖНЕЦ 🥀🪦\n─🪦─🥀─🪦─🥀─🪦─🥀─🪦─",
        "sep": "─🪦─🥀─🪦─🥀─🪦─🥀─🪦─",
        "bot": "🪦 У каждого контракта есть своя цена…",
        "accent": "🪦",
        "desc": "Тёмный жнец, погост, цветы смерти.",
    },

    # ── ✨ ZARNIKI (Premium) ──────────────────────────────────────────────────
    "theme_glass": {
        "name": "💠 Витраж", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 300,
        "premium_template": "glass",
        "top": "💠 ═【 🕊️ ВИТРАЖ 🕊️ 】═ 💠",
        "sep": "┄┄ 💠 ┄┄ 💠 ┄┄",
        "bot": "💠 Каждый осколок — часть картины…",
        "accent": "💠",
        "desc": "Витражное стекло, переливающиеся цвета.",
    },
    "theme_gold": {
        "name": "⚜️ Аурум", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 350,
        "premium_template": "gold",
        "top": "⚜️ ═【 🪙 АУРУМ 🪙 】═ ⚜️",
        "sep": "┄┄ 🪙 ┄┄ 🪙 ┄┄",
        "bot": "💛 Золото молчит, но его слышат все…",
        "accent": "⚜️",
        "desc": "Жидкое золото, роскошь без границ.",
    },

    # ── 🗓 SEASONAL ───────────────────────────────────────────────────────────
    "theme_halloween": {
        "name": "🎃 Самайн", "rarity": "seasonal", "source": "event",
        "top": "🎃🦇 ПРОФИЛЬ 🦇🎃\n─🎃─🦇─🕸️─🦇─🎃─🦇─🕸️─",
        "sep": "─🎃─🦇─🕸️─🦇─🎃─🦇─🕸️─",
        "bot": "🎃 Сладость, жизнь или пара твоих монет?",
        "accent": "🎃",
        "desc": "Хэллоуин, тыквы, летучие мыши. Осенний ивент.",
    },
    "theme_spring": {
        "name": "💌 Цветение", "rarity": "seasonal", "source": "event",
        "top": "💌💘 ПРОФИЛЬ 💘💌\n─💌─💘─🌸─💘─💌─💘─🌸─",
        "sep": "─💌─💘─🌸─💘─💌─💘─🌸─",
        "bot": "💌 Настоящая магия начинается с одного слова…",
        "accent": "💌",
        "desc": "День влюблённых, весеннее цветение.",
    },
    "theme_luck": {
        "name": "🎰 Азарт", "rarity": "seasonal", "source": "event",
        "top": "🎰🃏 ПРОФИЛЬ 🃏🎰\n═♠️═♥️═♣️═♦️═♠️═♥️═",
        "sep": "═♠️═♥️═♣️═♦️═♠️═♥️═",
        "bot": "🎰 Ставьте всё. Банкир не прощает ошибок…",
        "accent": "🎰",
        "desc": "Казино, масти карт, удача против судьбы.",
    },
    # ══ БЛОК 10: Premium Zarniki — кастомный рендер профиля ════════════════

    "theme_system_override": {
        "name": "💻 System Override", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 400,
        "premium_template": "system_override", "it": True,
        # Минимальные поля для совместимости (рендер идёт через premium_template)
        "top": "▼ 💻 ＳＹＳＴＥＭ_ＯＶＥＲＲＩＤＥ 💻 ▼",
        "sep": "► ─────────────────",
        "bot": "*>_ Проснись, Нео. Ты всё ещё в чате… ▮* 🟢",
        "accent": "💻",
        "desc": "Взлом системы. Кибер-терминальный стиль с кодами доступа.",
    },
    "theme_wind_free": {
        "name": "🎐 Ветер Свободы", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 380,
        "premium_template": "wind_free",
        "top": "【 🎐 ‧̍̊˙· ВЕТЕР СВОБОДЫ ·˙‧̍̊ 🎐 】",
        "sep": "▽ 【 ───────────── 】",
        "bot": "*«Разве не прекрасно, когда ветер сам выбирает путь?»* 🍃",
        "accent": "🎐",
        "desc": "Японский стиль свободы. Тематическая терминология в духе природы.",
    },
    "theme_empire": {
        "name": "⚜️ Империя", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 420,
        "premium_template": "empire",
        "top": "🥂 ✧ ━━ ⚜️ ИМПЕРИЯ ⚜️ ━━ ✧ 🥂",
        "sep": "▼ 【 ────────────── 】",
        "bot": "🥂 ✧ ━━ 💳 ID: {id} ━━ ✧ 🥂\n*«У роскоши нет предела, есть только цена…»* 💸",
        "accent": "👑",
        "id_in_bot": True,
        "desc": "Имперская роскошь. Тематическая терминология элиты.",
    },

    # ══ Премиум-донат темы с кастомным рендером (Часть 3) ════════════════════
    "theme_linux": {
        "name": "🐧 Linux", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 350,
        "premium_template": "linux", "it": True,
        "top": "predvestnik@root:~/user/data#",
        "sep": ">_ ──────────────",
        "bot": "predvestnik@root:~/exit$ _",
        "accent": "🐧",
        "desc": "Kernel Shell — профиль как root-терминал Linux.",
    },
    "theme_hardcore": {
        "name": "🖥️ Hardcore Shell", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 350,
        "premium_template": "hardcore_shell", "it": True,
        "top": "┌──(user ㉿ predvestnik)",
        "sep": "---------------------------",
        "bot": "# «Система работает. Идеально.»",
        "accent": "🖥️",
        "desc": "Bash Profile — хардкорный шелл в стиле pentest-консоли.",
    },
    "theme_order": {
        "name": "🎭 Закрытый Орден", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 320,
        "premium_template": "order",
        "top": "🍷 ✧ ── 🎭 Л О Ж А 🎭 ── ✧ 🍷",
        "sep": "♱ ──────────────",
        "bot": "🟪 Мы видим то, что скрыто…",
        "accent": "🎭",
        "desc": "Мистический орден — тайные союзы и фонд ложи.",
    },
    "theme_prism_os": {
        "name": "💠 Prism OS", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 380,
        "premium_template": "prism_os", "it": True,
        "top": "[ 🪞 P R I S M _ O S 🪞 ]",
        "sep": "░░░ ──────────────",
        "bot": "💎 Свет находит путь сквозь кристалл…",
        "accent": "💠",
        "desc": "Призматическая ОС — дамп памяти и периферия в свете кристалла.",
    },
    "theme_avangard": {
        "name": "🕊️ Авангард", "rarity": "zarniki", "source": "zarniki", "price_zarniki": 300,
        "premium_template": "avangard",
        "top": "✧ ━━ 🕊️ АВАНГАРД 🕊️ ━━ ✧",
        "sep": "✧ ──────────────",
        "bot": "☀️ Сияй, пока можешь…",
        "accent": "🕊️",
        "desc": "Астральный свет — воздух, лёгкость и пространство.",
    },

    # ── 🗓 BATTLE PASS — эксклюзив платного трека сезона ──────────────────────
    "theme_bp_s1": {
        "name": "🎫 Предвестник Сезона", "rarity": "seasonal", "source": "battle_pass",
        "top": "🎫🏆 ПРОФИЛЬ 🏆🎫\n─🎫─🏆─⚡─🏆─🎫─🏆─⚡─",
        "sep": "─🎫─🏆─⚡─🏆─🎫─🏆─⚡─",
        "bot": "🏆 Этот путь прошли до конца лишь избранные… Сезон 1.",
        "accent": "🎫",
        "desc": "Эксклюзив Боевого пропуска: топ-награда платного трека Сезона 1. Больше не вернётся.",
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
