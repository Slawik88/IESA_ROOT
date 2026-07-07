# core/registry.py
# Single source of truth for all game data: items, pets, gacha rates, expeditions.
# Used by both the Bot and the Web panel. Never import platform-specific code here.
from typing import Dict, Any

from core.constants import SOUL_SHARDS_FOR_SUMMON_TOKEN


# ── Items (inventory, shop, consumables) ──────────────────────────────────────
ITEMS_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Materials
    "soul_shard": {
        "name": "💠 Осколок Души",
        "category": "material",
        "description": "Застывшая искра чужой души. Накопи 5 штук и собери из них 🎟 Жетон Призыва во вкладке «Крафт». Где взять: выпадает из круток Гачи, бывает в Акции дня.",
        "is_tradable": False,
    },
    "star_dust_s": {
        "name": "🌟 Звёздная пыль",
        "category": "material",
        "description": "Концентрат опыта питомцев: +1 дубликат любому питомцу (приближает его уровень). Применить: Зоопарк → карточка питомца → «Звёздная пыль».",
        "is_tradable": False,
        "dup_count": 1,
    },
    "star_dust_l": {
        "name": "✨ Небесная пыль",
        "category": "material",
        "description": "Щедрая горсть звёздной пыли — сразу +5 дубликатов выбранному питомцу. Применить: Зоопарк → карточка питомца → «Небесная пыль».",
        "is_tradable": False,
        "dup_count": 5,
    },
    # ── БЛОК21 #3: осколки косметик-крафта + сундуки-сюрпризы (за ✨ Зарники) ──
    "cosmetic_shard": {
        "name": "🔹 Осколок резонанса",
        "category": "material",
        "description": "Косметическая валюта-крафта. Падает из сундуков и дублей. Накопи и собери нужную косметику: Внешний вид → 🔹 Крафт.",
        "is_tradable": False,
    },
    "abyss_shard": {
        "name": "💠 Осколок Бездны",
        "category": "material",
        "description": "Клановый строительный ресурс (Rebuild 2.0). Добывается в Бездне клана и Вратах 2.0; на казну из осколков клан строит здания.",
        "is_tradable": False,
    },
    "chest_mini": {
        "name": "🎁 Мини-сюрприз",
        "category": "chest",
        "description": "Маленький сундук за ✨ Зарники: случайный расходник или осколки косметики. Открыть: Внешний вид → 🎁 Сюрпризы.",
        "is_tradable": False,
    },
    "chest_style": {
        "name": "🎁 Сундук Стиля",
        "category": "chest",
        "description": "Сундук за ✨ Зарники: косметика (common/rare/epic), дубль → осколки. Открыть: Внешний вид → 🎁 Сюрпризы.",
        "is_tradable": False,
    },
    # Gacha-exclusive items (не продаются в магазине)
    "treasure_map": {
        "name": "🗺 Карта Сокровищ",
        "category": "booster",
        "description": "Отметка богатого тайника. Сработает сама на следующей экспедиции: +50% к луту (разово). Где взять: гача и 8-часовые походы с Соколом Lv10.",
        "is_tradable": False,
    },
    "study_notes": {
        "name": "📚 Конспект",
        "category": "utility",
        "price_mora": 600,
        "description": "Шпаргалка для быстрой прокачки. Активируй командой «бот использовать, study_notes»: +50% XP от сообщений на 4 часа.",
        "is_tradable": False,
    },
    "lucky_charm": {
        "name": "🍀 Подкова Удачи",
        "category": "booster",
        "description": "Талисман везения. Сработает автоматически на следующей крутке гачи: +15% к шансу редкости. Где взять: гача и ивенты.",
        "is_tradable": False,
    },
    # Spin tokens (бесплатные спины из гачи) — единственный источник питомцев (яйца удалены, БЛОК19 Ч.2)
    "spin_token":          {"name": "🎟 Жетон Гачи",          "category": "spin_token", "spin_type": "mora",     "is_tradable": False, "description": "Один бесплатный спин гача-режима «Мора». Потратить: вкладка Гача. Где взять: круток, наград и квестов."},
    "spin_token_diamond":  {"name": "🎟 Алмазный Жетон",      "category": "spin_token", "spin_type": "diamond",  "is_tradable": False, "description": "Один бесплатный спин гача-режима «Алмаз» (выше шанс редких и легендарных питомцев). Потратить: вкладка Гача. Где взять: премиум-наград, квестов и лута."},
    # Food / consumables
    # Усталость растёт от экспедиций; корм её снимает, чтобы снова слать питомца в
    # поход. Везде кормить одинаково: Зоопарк → карточка питомца → «🍖 Покормить».
    # ── Корм (РЕБАЛАНС): чистая лестница −15/30/50/75/100, цена за очко плавно
    # падает 9.0→7.0 (эконом-масштаб: крупная пайка чуть выгоднее, имбы нет). ──
    "food_basic":   {
        "name": "🥩 Базовый корм",        "category": "food", "price_mora": 135,
        "fatigue_restore": 15,            "description": "Простая пайка: −15 усталости питомцу. Покормить: Зоопарк → карточка питомца.",
    },
    "food_fried": {
        "name": "🍗 Жаренное мясо",       "category": "food", "price_mora": 255,
        "fatigue_restore": 30,            "description": "Жареное мясо: −30 усталости питомцу. Покормить: Зоопарк → карточка питомца.",
    },
    "food_stew": {
        "name": "🍖 Тушёная Грудка",      "category": "food", "price_mora": 400,
        "fatigue_restore": 50,            "description": "Тушёная грудка: −50 усталости питомцу. Покормить: Зоопарк → карточка питомца.",
    },
    "food_elite":   {
        "name": "🍗 Элитный корм",        "category": "food", "price_mora": 560,
        "fatigue_restore": 75,            "description": "Сытный паёк: −75 усталости питомцу — выгоднее за очко. Покормить: Зоопарк → карточка питомца.",
    },
    "food_feast": {
        "name": "🍱 Праздничный паёк",    "category": "food", "price_mora": 700,
        "fatigue_restore": 100,           "description": "Праздничный паёк: −100 усталости — полностью снимает усталость одному питомцу. Покормить: Зоопарк → карточка питомца.",
    },
    # ── Спец-корм (утилита / AoE / премиум) ──
    "food_energy":  {
        "name": "⚡️ Энергетик",          "category": "food", "price_mora": 600,
        "fatigue_restore": 20,            "buff": "expedition_cd_reset",
        "description": "Бодрящий энергетик: −20 усталости и МГНОВЕННО завершает текущий поход — питомец сразу возвращается с лутом. Покормить: Зоопарк → карточка питомца.",
    },
    "food_super": {
        "name": "💊 Суперкорм",           "category": "food", "price_mora": 850,
        "fatigue_restore": 60,            "buff": "nursery_aoe_10",
        "description": "Суперкорм: −60 усталости активному питомцу и −10 ВСЕМ в питомнике сразу. Покормить: Зоопарк → карточка активного питомца.",
    },
    "food_diamond": {
        "name": "💎 Алмазное лакомство",  "category": "food", "price_diamonds": 12,
        "fatigue_restore": 100,           "buff": "nursery_full_rest",
        "description": "Деликатес за алмазы: ПОЛНОСТЬЮ снимает усталость активному питомцу И ВСЕМ в питомнике. Покормить: Зоопарк → карточка питомца.",
    },
    # NB: slot_expander удалён в Блоке 2 — слоты питомника теперь покупаются
    # напрямую за алмазы (прогрессивная цена), см. core/constants ZOO_SLOT_PRICES_DIAMONDS.
    # Player buffs (for player, not pet)
    "potion_luck_s": {
        "name": "🧪 Зелье Удачи (М)", "category": "booster", "price_mora": 400,
        "description": "Глоток везения. Применяется сам на следующей крутке гачи: +15% к шансу редких+ дропов. Купить: Магазин.",
        "is_tradable": False, "buff_type": "gacha_luck", "buff_value": 0.15, "buff_uses": 1,
    },
    "potion_luck_m": {
        "name": "🔮 Зелье Удачи (Б)", "category": "booster",
        "description": "Большой эликсир везения: +15% к шансу редких+ на следующие 3 крутки гачи (применяется сам).",
        "is_tradable": False, "buff_type": "gacha_luck", "buff_value": 0.15, "buff_uses": 3,
    },
    "potion_sprint": {
        "name": "⚡ Зелье Рывка", "category": "booster",
        "description": "Заряд бодрости для похода: +30% к луту следующей экспедиции (применяется сам). Где взять: гача.",
        "is_tradable": False, "buff_type": "expedition_loot", "buff_value": 0.30, "buff_uses": 1,
    },
    # Expedition time boosters (gacha-only)
    "exp_boost_1h": {
        "name": "⏩ Ускоритель (1ч)", "category": "booster",
        "description": "Подгоняет питомца домой: −1 час текущей экспедиции. Применить: Зоопарк → активная экспедиция → «Ускорить». Где взять: гача.",
        "is_tradable": False, "boost_hours": 1,
    },
    "exp_boost_2h": {
        "name": "⏩⏩ Ускоритель (2ч)", "category": "booster",
        "description": "−2 часа текущей активной экспедиции. Применить: Зоопарк → активная экспедиция → «Ускорить». Где взять: гача.",
        "is_tradable": False, "boost_hours": 2,
    },
    "exp_boost_4h": {
        "name": "🚀 Ускоритель (4ч)", "category": "booster",
        "description": "−4 часа текущей активной экспедиции. Применить: Зоопарк → активная экспедиция → «Ускорить». Где взять: гача.",
        "is_tradable": False, "boost_hours": 4,
    },

    # Donate shop (Implementation Block 1.4) — за Зарники ✨
    "zarniki_fatigue_reset": {
        "name": "✨ Эликсир бодрости", "category": "donate", "price_zarniki": 30,
        "fatigue_restore": 100, "is_tradable": False,
        "description": "Донат-эликсир за ✨: мгновенно снимает ВСЮ усталость питомца. Применить: Зоопарк → карточка питомца.",
    },
    "zarniki_cooldown_skip": {
        "name": "✨ Кристалл времени", "category": "donate", "price_zarniki": 50,
        "fatigue_restore": 50, "buff": "expedition_cd_reset", "is_tradable": False,
        "description": "Донат за ✨: −50 усталости и сброс кулдауна экспедиции (питомца сразу снова в поход). Применить: Зоопарк → карточка питомца.",
    },
    "zarniki_nickname_token": {
        "name": "✨ Жетон смены ника", "category": "donate", "price_zarniki": 20,
        "is_tradable": False,
        "description": "Донат за ✨: +1 к месячному лимиту смены ника. Срабатывает при следующей смене ника.",
    },
}


# ── Pet species ───────────────────────────────────────────────────────────────
# desc — generic theme blurb. Concrete numbers come from the level curves
# (HAMSTER_BONUSES / OWL_BONUSES / ... in core/constants.py) via format_pet_bonus_short.
PET_SPECIES: Dict[str, Dict[str, Any]] = {
    # Common
    "hamster": {"name": "🐹 Хомяк-банкир",        "rarity": "common",    "default_role": "passive", "desc": "Накапливает Мору со временем. Lv4 — работает при 100 усталости, Lv8 — шанс ×2 при сборе, Lv10 — +💎/сутки."},
    "owl":     {"name": "🦉 Сова-студент",        "rarity": "common",    "default_role": "passive", "desc": "Бонус XP за сообщения. Lv4 — XP в экспедиции, Lv8 — ×2 в выходные, Lv10 — Жетон Крутки/сутки."},
    "dog":     {"name": "🐕 Дворовая Собака",     "rarity": "common",    "default_role": "active",  "desc": "Ускоряет экспедиции. Lv4 — собаке меньше усталости, Lv8 — шанс 0 усталости, Lv10 — −5% стоимость похода."},
    "squirrel":{"name": "🐿 Запасливая Белка",    "rarity": "common",    "default_role": "passive", "desc": "Грызун-бухгалтер: +% Моры к награде за КВЕСТЫ (держи в питомнике). Lv1 +5% → Lv10 +20%. В пассивном слоте — половина бонуса."},
    # Rare
    "turtle":  {"name": "🐢 Черепаха-торговец",   "rarity": "rare",      "default_role": "passive", "desc": "Скидка в магазине. Lv4 — скидка на экспедиции, Lv8 — скидка на крутку гачи, Lv10 — максимальные скидки."},
    "falcon":  {"name": "🦅 Охотничий Сокол",     "rarity": "rare",      "default_role": "active",  "desc": "+Мора из похода. Lv4 — +XP похода, Lv8 — шанс двойной добычи, Lv10 — гарант. Карта Сокровищ в 8ч поход."},
    # Epic
    "wolf":    {"name": "🐺 Снежный Волк",        "rarity": "epic",      "default_role": "passive", "desc": "Снижает усталость питомнику. Lv4 — корм +5 ед. в актив, Lv8 — раз в день восстанавливает 30, Lv10 — иммунитет перемещений."},
    "fox":     {"name": "🦊 Огненная Лиса",       "rarity": "epic",      "default_role": "active",  "desc": "Шанс 💎 в походе. Lv4 — +Common-дубликаты из гачи, Lv8 — гарант. 💎/нед, Lv10 — шанс 🎟 Алмазного Жетона из похода."},
    # Legendary
    "dragon":  {"name": "🐉 Дракон Хранитель",    "rarity": "legendary", "default_role": "passive", "desc": "Поднимает кап семейного банка. Lv4 — бесплатный корм, Lv8 — Мора при сборе хомяков, Lv10 — +500/нед в банк."},
    "unicorn": {"name": "🦄 Астральный Единорог", "rarity": "legendary", "default_role": "passive", "desc": "−% к суточной усталости всех. Lv4 — раз в день иммунитет, Lv8 — актив восстанавливается, Lv10 — авто-восст. при 100."},
}


# ── Gacha rates ───────────────────────────────────────────────────────────────
# УДАЛЕНО (БЛОК19 Ч.2): яйца вырезаны, питомцы добываются ТОЛЬКО через Гачу.
# Честные шансы крутки берутся из GACHA_TABLES (см. /gacha/odds).


# ── Gacha spin tables (B3) ────────────────────────────────────────────────────
# Entry types:
#   mora         – random mora in [min, max]
#   item         – specific item (id, qty)
#   combo        – multiple items at once (items: [{id, qty}, ...])
#   diamond      – diamonds (qty)
#   pet_dup      – random pet dup of `rarity`
# "valuable": True  → weight doubled on soft pity

# Block 8: единая гача — 2 режима. "mora" (~600🪙) объединяет бывшие
# novice/standard/premium (common→epic питомцы, мора, расходники, малый шанс 💎).
# "diamond" (~8💎) — выше шанс редкого лута + шире диапазон (epic→legendary,
# редкие жетоны (🎟 Алмазный Жетон), легендарные питомцы, гарантии алмазов).
GACHA_TABLES: Dict[str, list] = {
    "mora": [
        {"weight": 22, "type": "mora",    "min": 40,  "max": 120},
        {"weight": 14, "type": "item",    "id": "food_basic",    "qty": 2},
        {"weight": 11, "type": "item",    "id": "star_dust_s",   "qty": 1},
        {"weight": 10, "type": "item",    "id": "soul_shard",    "qty": 2},
        {"weight": 9,  "type": "pet_dup", "rarity": "common",    "valuable": True},
        {"weight": 8,  "type": "mora",    "min": 200, "max": 320},
        {"weight": 7,  "type": "combo",   "items": [{"id": "soul_shard", "qty": 2}, {"id": "star_dust_s", "qty": 1}]},
        {"weight": 6,  "type": "item",    "id": "food_elite",    "qty": 1},
        {"weight": 5,  "type": "pet_dup", "rarity": "rare",      "valuable": True},
        {"weight": 4,  "type": "item",    "id": "star_dust_l",   "qty": 1},
        {"weight": 3,  "type": "item",    "id": "potion_luck_s", "qty": 1},
        {"weight": 3,  "type": "item",    "id": "exp_boost_1h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "spin_token",    "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "exp_boost_2h",  "qty": 1, "valuable": True},
        {"weight": 1.5,"type": "item",    "id": "spin_token",    "qty": 1, "valuable": True},
        {"weight": 0.8,"type": "diamond", "qty": 2,              "valuable": True},
        {"weight": 0.4,"type": "pet_dup", "rarity": "epic",      "valuable": True},
        {"weight": 0.2,"type": "item",    "id": "spin_token_diamond", "qty": 1, "valuable": True},
    ],
    "diamond": [
        {"weight": 22, "type": "item",    "id": "spin_token_diamond", "qty": 1, "valuable": True},
        {"weight": 15, "type": "item",    "id": "spin_token_diamond", "qty": 1, "valuable": True},
        {"weight": 13, "type": "combo",   "items": [{"id": "spin_token", "qty": 1}], "diamond_bonus": 2, "valuable": True},
        {"weight": 12, "type": "pet_dup", "rarity": "epic",      "valuable": True},
        {"weight": 9,  "type": "combo",   "items": [{"id": "treasure_map", "qty": 3}], "valuable": True},
        {"weight": 8,  "type": "item",    "id": "spin_token_diamond", "qty": 1, "valuable": True},
        {"weight": 6,  "type": "diamond", "qty": 5,              "valuable": True},
        {"weight": 4,  "type": "item",    "id": "exp_boost_4h",  "qty": 1, "valuable": True},
        {"weight": 3,  "type": "combo",   "items": [{"id": "exp_boost_2h", "qty": 1}, {"id": "potion_sprint", "qty": 1}], "valuable": True},
        {"weight": 3,  "type": "pet_dup", "rarity": "legendary", "valuable": True},
        {"weight": 2,  "type": "item",    "id": "spin_token_diamond", "qty": 2, "valuable": True},
        {"weight": 1,  "type": "pet_dup_multi", "rarity": "legendary", "count": 2, "valuable": True},
    ],
}

PITY_HARD_REWARD: Dict[str, dict] = {
    "mora":    {"type": "pet_dup", "rarity": "epic"},
    "diamond": {"type": "pet_dup", "rarity": "legendary"},
}


# ── Expedition data ───────────────────────────────────────────────────────────
EXPEDITIONS_DATA: Dict[int, Dict[str, int]] = {
    2: {"cost":   0, "min_m":  55, "max_m":  85, "min_xp":  15, "max_xp":  15, "fatigue": 10},
    4: {"cost":  40, "min_m": 130, "max_m": 175, "min_xp":  30, "max_xp":  55, "fatigue": 20},
    6: {"cost":  60, "min_m": 270, "max_m": 380, "min_xp":  70, "max_xp":  95, "fatigue": 30},
    8: {"cost": 100, "min_m": 430, "max_m": 620, "min_xp": 100, "max_xp": 140, "fatigue": 40},
}


# ── Daily Deal pools (B5) ─────────────────────────────────────────────────────
# Each entry: item_id, qty_range (min, max), base_price_mora (per unit, for discount calc).
# base_price_dia is used for diamond-slot items.
# The actual slot price = round(qty × base_price × (1 - discount)).

DAILY_DEAL_POOL_MORA: list = [
    {"item_id": "food_basic",          "qty_range": (1, 5), "base_price_mora": 135},
    {"item_id": "food_elite",          "qty_range": (1, 3), "base_price_mora": 560},
    {"item_id": "food_energy",         "qty_range": (1, 3), "base_price_mora": 600},
    {"item_id": "food_super",          "qty_range": (1, 2), "base_price_mora": 850},
    {"item_id": "spin_token",          "qty_range": (1, 3), "base_price_mora": 600},
    {"item_id": "treasure_map",        "qty_range": (1, 2), "base_price_mora": 900},
    {"item_id": "lucky_charm",         "qty_range": (1, 2), "base_price_mora": 900},
    {"item_id": "study_notes",         "qty_range": (1, 2), "base_price_mora": 600},
    {"item_id": "soul_shard",          "qty_range": (3, 10), "base_price_mora": 100},
    {"item_id": "star_dust_s",         "qty_range": (2, 5), "base_price_mora": 700},
    {"item_id": "star_dust_l",         "qty_range": (1, 2), "base_price_mora": 3000},
]

DAILY_DEAL_POOL_DIAMOND: list = [
    {"item_id": "food_diamond",       "qty_range": (1, 3), "base_price_dia": 12},
    {"item_id": "spin_token",         "qty_range": (1, 2), "base_price_dia": 5},
    {"item_id": "spin_token_diamond", "qty_range": (1, 2), "base_price_dia": 8},
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_item(item_id: str) -> Dict | None:
    return ITEMS_REGISTRY.get(item_id)


def get_species(species_id: str) -> Dict | None:
    return PET_SPECIES.get(species_id)


# ── Daily Quests (B20) ───────────────────────────────────────────────────────
DAILY_QUESTS: list = [
    # Easy
    {"id": "msg_15",     "metric": "messages_in_chat_today",        "target": 15, "reward": {"mora": 200.0},                                  "weight": 5},
    {"id": "msg_30",     "metric": "messages_in_chat_today",        "target": 30, "reward": {"mora": 400.0},                                  "weight": 4},
    {"id": "feed_pet",   "metric": "pet_feeds_today",               "target": 1,  "reward": {"mora": 150.0},                                  "weight": 5},
    {"id": "gacha_3",    "metric": "gacha_spins_today",             "target": 3,  "reward": {"items": [("star_dust_s", 1)]},                  "weight": 4},
    # Medium
    {"id": "exped_2",    "metric": "expeditions_today",             "target": 2,  "reward": {"mora": 500.0},                                  "weight": 3},
    {"id": "warp_3",     "metric": "warps_to_distinct_users_today", "target": 3,  "reward": {"mora": 200.0},                                  "weight": 3},
    {"id": "auction_bid","metric": "auction_bids_today",            "target": 1,  "reward": {"mora": 200.0},                                  "weight": 2},
    # Hard
    {"id": "exped_4",    "metric": "expeditions_today",             "target": 4,  "reward": {"mora": 1000.0},                                 "weight": 2},
    {"id": "gacha_10",   "metric": "gacha_spins_today",             "target": 10, "reward": {"mora": 600.0, "items": [("spin_token", 1)]}, "weight": 2},
    {"id": "hug_5",      "metric": "warps_hug_distinct_today",      "target": 5,  "reward": {"mora": 300.0},                                  "weight": 2},
    {"id": "rare_dup",   "metric": "rare_or_better_pet_dups_today", "target": 1,  "reward": {"mora": 800.0},                                  "weight": 1},
    {"id": "level_pet",  "metric": "pet_level_ups_today",           "target": 1,  "reward": {"mora": 500.0},                                  "weight": 1},
]

# ── Недельные квесты (БЛОК 5) ─────────────────────────────────────────────────
# Фиксированный набор на неделю. Прогресс копится всю неделю (та же таблица
# daily_quests, ключ date = "WYYYY-NN"). Метрики — КРОСС-ПЛАТФОРМЕННЫЕ (и бот, и
# сайт инкрементят их в одних и тех же местах), поэтому весь набор и супер-бонус
# закрываются с обеих сторон. Метрики переиспользуют дневные (суффикс «_today» —
# это идентификатор действия, не «за сегодня»: недельная строка живёт всю неделю).
WEEKLY_QUESTS: list = [
    {"id": "w_gourmet",    "metric": "pet_feeds_today",    "target": 20, "reward": {"mora": 2500.0},                                 "name": "🥗 Гурман"},
    {"id": "w_patron",     "metric": "gacha_spins_today",  "target": 40, "reward": {"mora": 3000.0, "items": [("spin_token", 1)]},   "name": "🤑 Безумный меценат"},
    {"id": "w_rescuer",    "metric": "expeditions_today",  "target": 15, "reward": {"mora": 4000.0},                                 "name": "🚑 Спасатель пустошей"},
    {"id": "w_geneticist", "metric": "gacha_spins_today",  "target": 12, "reward": {"diamonds": 12.0},                               "name": "🧬 Генетический эксперимент"},
    {"id": "w_cardinal",   "metric": "auction_bids_today", "target": 6,  "reward": {"mora": 2500.0},                                 "name": "⚖️ Серый Кардинал"},
]

# ── Achievements (B11) ────────────────────────────────────────────────────────
ACHIEVEMENTS: Dict[str, Dict] = {
    "gacha_addict": {
        "icon": "🎰", "name": "Завсегдатай Гачи",
        "metric": "gacha_spins",
        "thresholds": [10, 50, 150, 400, 1000, 2500, 5000, 10000, 25000, 50000],
    },
    "trainer": {
        "icon": "👑", "name": "Воспитатель",
        "metric": "pets_at_level_10",
        "thresholds": [1, 2, 3, 5, 7, 10, 13, 16, 20, 25],
    },
    "wanderer": {
        "icon": "🗺", "name": "Странник",
        "metric": "expeditions_done",
        "thresholds": [10, 30, 75, 150, 300, 600, 1200, 2500, 5000, 10000],
    },
    "persistent": {
        "icon": "🔥", "name": "Постоянство",
        "metric": "max_streak_ever",
        "thresholds": [7, 14, 30, 60, 100, 180, 270, 365, 540, 730],
    },
    "vow_keeper": {
        "icon": "💍", "name": "Хранитель уз",
        "metric": "marriage_days_total",
        # Суммарное кол-во дней в браке (накапливается каждый день пока состоишь в браке)
        "thresholds": [7, 30, 90, 180, 365, 540, 730, 1095, 1460, 1825],
        "desc": "Пробудьте в браке суммарно N дней. Счётчик идёт каждый день пока вы женаты.",
    },
    "collector": {
        "icon": "🐾", "name": "Коллекционер",
        "metric": "distinct_species_owned",
        "thresholds": [3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
        "desc": "Получите N уникальных видов питомцев. Каждый новый вид из гачи засчитывается.",
    },
    "patron": {
        "icon": "🛒", "name": "Меценат",
        "metric": "total_mora_spent_shop",
        "thresholds": [500, 2000, 5000, 15000, 50000, 150000, 500000, 1500000, 5000000, 15000000],
        "desc": "Потратьте суммарно N 🪙 Моры в магазине (бот магазин). Накапливается со всех покупок.",
    },
    "magnate": {
        "icon": "💰", "name": "Магнат",
        "metric": "peak_mora_balance",
        "thresholds": [1000, 5000, 25000, 100000, 500000, 1500000, 5000000, 15000000, 50000000, 150000000],
        "desc": "Накопите N 🪙 Моры одновременно на балансе. Трекается максимальный баланс за всё время.",
    },
    "treasury": {
        "icon": "💎", "name": "Сокровищница",
        "metric": "peak_diamonds_balance",
        "thresholds": [5, 25, 100, 500, 1500, 5000, 15000, 50000, 150000, 500000],
        "desc": "Накопите N 💎 Алмазов одновременно на балансе. Трекается максимальный баланс.",
    },
    "dealer": {
        "icon": "🏛", "name": "Делец Аукциона",
        "metric": "auction_sales",
        "thresholds": [1, 5, 15, 40, 100, 250, 600, 1500, 3500, 8000],
        "desc": "Продайте N лотов на аукционе. Засчитывается только успешная продажа (кто-то купил).",
    },
    "lucky_one": {
        "icon": "🎲", "name": "Везунчик",
        "metric": "gamble_wins",
        "thresholds": [5, 25, 75, 200, 500, 1200, 3000, 7500, 18000, 40000],
    },
    "duelist": {
        "icon": "⚔️", "name": "Дуэлянт",
        "metric": "duel_wins",
        "thresholds": [1, 3, 8, 20, 50, 120, 280, 600, 1200, 2500],
    },
    "talker": {
        "icon": "💬", "name": "Собеседник",
        "metric": "messages_total_global",
        "thresholds": [100, 500, 2000, 7500, 25000, 75000, 200000, 500000, 1200000, 3000000],
    },
    "star": {
        "icon": "🌟", "name": "Звезда чата",
        "metric": "weekly_top1_count",
        "thresholds": [1, 3, 7, 15, 30, 60, 100, 150, 220, 365],
    },
    "star_gacha": {
        "icon": "🌠", "name": "Звёздная Гача",
        "metric": "legendary_gacha_drops",
        "thresholds": [1, 3, 7, 15, 30, 60, 120, 250, 500, 1000],
        "desc": "Получите N легендарных+ питомцев из гачи. Считаются legendary и mythic.",
    },
}

ACHIEVEMENT_LEVEL_REWARDS: Dict[int, Dict] = {
    1:  {"mora": 100.0,   "diamonds": 0.0, "items": ()},
    2:  {"mora": 200.0,   "diamonds": 0.0, "items": ()},
    3:  {"mora": 400.0,   "diamonds": 0.0, "items": (("spin_token", 1),)},
    4:  {"mora": 800.0,   "diamonds": 0.0, "items": (("spin_token", 1),)},
    5:  {"mora": 1500.0,  "diamonds": 0.0, "items": (("spin_token", 1),)},
    6:  {"mora": 3000.0,  "diamonds": 1.0, "items": ()},
    7:  {"mora": 6000.0,  "diamonds": 2.0, "items": (("spin_token", 1),)},
    8:  {"mora": 12000.0, "diamonds": 5.0, "items": (("spin_token", 1),)},
    9:  {"mora": 25000.0, "diamonds": 10.0, "items": (("spin_token_diamond", 1),)},
    10: {"mora": 50000.0, "diamonds": 25.0, "items": (("spin_token", 3), ("spin_token_diamond", 1))},
}


# ── Battle Pass (Implementation Block 5) ────────────────────────────────────
BATTLE_PASS_SEASONS: dict[str, dict] = {
    "s1": {
        "label": "Сезон 1",
        "starts_at": "2026-07-01",
        "ends_at": "2026-08-10",   # +40 дней
        "max_level": 50,
    },
}

# Награды по уровням: free — доступны всем, paid — только при активном VIP
# (services.vip.is_vip_active). mora/diamonds выдаются через add_balance,
# items — той же вставкой в inventory, что и награды ачивок.
BATTLE_PASS_REWARDS: Dict[int, Dict] = {
    1:  {"free": {"mora": 50,  "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("spin_token", 1),)}},
    2:  {"free": {"mora": 0,   "diamonds": 0, "items": (("food_basic", 1),)},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    3:  {"free": {"mora": 60,  "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    4:  {"free": {"mora": 70,  "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("potion_luck_s", 1),)}},
    5:  {"free": {"mora": 0,   "diamonds": 0, "items": (("spin_token", 1),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    6:  {"free": {"mora": 90,  "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    7:  {"free": {"mora": 100, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("food_elite", 1),)}},
    8:  {"free": {"mora": 110, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    9:  {"free": {"mora": 120, "diamonds": 0, "items": (("food_basic", 2),)},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    10: {"free": {"mora": 200, "diamonds": 1, "items": (("spin_token", 1),)},
         "paid": {"mora": 0,   "diamonds": 5, "items": (("spin_token", 1),)}},

    11: {"free": {"mora": 140, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    12: {"free": {"mora": 0,   "diamonds": 0, "items": (("food_elite", 1),)},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    13: {"free": {"mora": 150, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("potion_sprint", 1),)}},
    14: {"free": {"mora": 160, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    15: {"free": {"mora": 0,   "diamonds": 0, "items": (("spin_token", 1),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": (("exp_boost_1h", 1),)}},
    16: {"free": {"mora": 170, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    17: {"free": {"mora": 180, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    18: {"free": {"mora": 190, "diamonds": 0, "items": (("star_dust_s", 1),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    19: {"free": {"mora": 200, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("food_diamond", 1),)}},
    20: {"free": {"mora": 300, "diamonds": 2, "items": (("food_super", 1),)},
         "paid": {"mora": 0,   "diamonds": 7, "items": (("spin_token", 1), ("exp_boost_2h", 1))}},

    21: {"free": {"mora": 220, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    22: {"free": {"mora": 0,   "diamonds": 0, "items": (("potion_luck_s", 1),)},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    23: {"free": {"mora": 230, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    24: {"free": {"mora": 240, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": (("exp_boost_2h", 1),)}},
    25: {"free": {"mora": 0,   "diamonds": 0, "items": (("spin_token", 1), ("food_basic", 2))},
         "paid": {"mora": 0,   "diamonds": 3, "items": (("potion_luck_m", 1),)}},
    26: {"free": {"mora": 250, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    27: {"free": {"mora": 260, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    28: {"free": {"mora": 270, "diamonds": 0, "items": (("star_dust_l", 1),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": (("food_diamond", 1),)}},
    29: {"free": {"mora": 280, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 1, "items": ()}},
    30: {"free": {"mora": 400, "diamonds": 3, "items": (("spin_token", 2),)},
         "paid": {"mora": 0,   "diamonds": 10, "items": (("spin_token_diamond", 1),)}},

    31: {"free": {"mora": 300, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    32: {"free": {"mora": 0,   "diamonds": 0, "items": (("food_super", 1),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    33: {"free": {"mora": 310, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": (("exp_boost_4h", 1),)}},
    34: {"free": {"mora": 320, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    35: {"free": {"mora": 0,   "diamonds": 0, "items": (("spin_token", 1),)},
         "paid": {"mora": 0,   "diamonds": 4, "items": (("food_diamond", 1),)}},
    36: {"free": {"mora": 330, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    37: {"free": {"mora": 340, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    38: {"free": {"mora": 350, "diamonds": 0, "items": (("star_dust_l", 1),)},
         "paid": {"mora": 0,   "diamonds": 3, "items": (("potion_luck_m", 1),)}},
    39: {"free": {"mora": 360, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    40: {"free": {"mora": 500, "diamonds": 4, "items": (("spin_token", 2),)},
         "paid": {"mora": 0,   "diamonds": 12, "items": (("spin_token_diamond", 1),)}},

    41: {"free": {"mora": 400, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 3, "items": ()}},
    42: {"free": {"mora": 0,   "diamonds": 0, "items": (("food_super", 2),)},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    43: {"free": {"mora": 420, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 3, "items": (("exp_boost_4h", 1),)}},
    44: {"free": {"mora": 440, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 2, "items": ()}},
    45: {"free": {"mora": 0,   "diamonds": 0, "items": (("spin_token", 2),)},
         "paid": {"mora": 0,   "diamonds": 5, "items": (("food_diamond", 2),)}},
    46: {"free": {"mora": 460, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 3, "items": ()}},
    47: {"free": {"mora": 480, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 3, "items": ()}},
    48: {"free": {"mora": 0,   "diamonds": 1, "items": (("star_dust_l", 2),)},
         "paid": {"mora": 0,   "diamonds": 4, "items": (("potion_luck_m", 1),)}},
    49: {"free": {"mora": 490, "diamonds": 0, "items": ()},
         "paid": {"mora": 0,   "diamonds": 5, "items": ()}},
    50: {"free": {"mora": 500, "diamonds": 0, "items": (("spin_token", 2),)},
         # theme — сезонная тема из core/themes.py (rarity "seasonal"), выдаётся
         # grant_theme'ом в services/battle_pass.claim_reward. Топ платного трека.
         "paid": {"mora": 0,   "diamonds": 10, "items": (("spin_token", 1),),
                  "theme": "theme_bp_s1"}},
}


# ── VIP Tiers (Implementation Block 2.2) ────────────────────────────────────
# Универсальные перки VIP (одинаковы для всех тарифов) — продающая подача
# (Implementation Block 3). Формат-нейтральные строки: бот оборачивает в HTML,
# сайт рендерит как список. Без разметки внутри.
VIP_PERKS_PITCH: list[str] = [
    "👑 Корона рядом с именем — во всех чатах, топах, на аукционе и в профиле",
    "🖼 Живая аватарка из Telegram на сайте вместо обычной заглушки",
    "🎰 Еженедельные жетоны на крутки — новые питомцы каждую неделю, бесплатно",
    "🎫 Платный трек Боевого пропуска — заметно больше наград за весь сезон",
    "✏️ Смена ника без месячного лимита — меняй хоть каждый день",
    "💬 Особые VIP-реакции у варп-команд — ярче, чем у всех остальных",
    "🎁 Разовый подарок сразу при оформлении — остаётся у тебя навсегда",
]

VIP_TIERS: dict[str, dict] = {
    "1m": {
        "label": "VIP-1М", "duration_days": 30, "price_zarniki": 150,
        "tagline": "Знакомство с VIP — попробовать вкус привилегий",
        "base_price_zarniki": 200,  # для отображения экономии
        "gift": {"mora": 200, "diamonds": 1,
                 "items": (("spin_token", 2), ("food_basic", 1))},
        "weekly": (("spin_token", 1),),
        "extra_slots": 0,
    },
    "2m": {
        "label": "VIP-2М", "duration_days": 60, "price_zarniki": 250,
        "tagline": "Вдвое дольше и заметно выгоднее старта",
        "base_price_zarniki": 400,  # экономия 150
        "gift": {"mora": 250, "diamonds": 2,
                 "items": (("spin_token", 3), ("food_basic", 3))},
        "weekly": (("spin_token", 1),),
        "extra_slots": 0,
    },
    "3m": {
        "label": "VIP-3М", "duration_days": 90, "price_zarniki": 400,
        "tagline": "Появляется +1 слот питомника и сильный старт сезона",
        "base_price_zarniki": 600,  # экономия 200
        "gift": {"mora": 300, "diamonds": 2,
                 "items": (("spin_token", 1), ("spin_token", 1), ("food_basic", 5))},
        "weekly": (("spin_token", 2),),
        "extra_slots": 1,
    },
    "8m": {
        "label": "VIP-8М", "duration_days": 240, "price_zarniki": 1200,
        "tagline": "Длинная дистанция — максимум еженедельных бонусов",
        "base_price_zarniki": 1600,  # экономия 400
        "gift": {"mora": 500, "diamonds": 5,
                 "items": (("spin_token", 2), ("spin_token", 1), ("food_basic", 5))},
        "weekly": (("spin_token", 1), ("spin_token", 1)),
        "extra_slots": 1,
    },
    "12m": {
        "label": "VIP-12М", "duration_days": 365, "price_zarniki": 1700,
        "tagline": "Год привилегий: всё по максимуму и +2 слота питомника",
        "base_price_zarniki": 2400,  # экономия 700
        "gift": {"mora": 500, "diamonds": 10,
                 "items": (("spin_token", 3), ("spin_token", 3),
                           ("spin_token", 3), ("spin_token", 5),
                           ("food_basic", 15), ("soul_shard", 5), ("exp_boost_2h", 4))},
        "weekly": (("spin_token", 1),),
        "extra_slots": 2,
    },
}


# ── Relics (Implementation Block 13) — сток для Тёмной Моры ──────────────────
# Уникальные коллекционные предметы (владеешь раз). Цена комбинирует валюты,
# обязательно включает 🌑 Тёмную Мору. Эффект: суммарный +% к моро-награде
# экспедиций (интегрируется в services/expedition.calculate_reward — одна точка).
RELIC_RARITY_META: dict[str, dict] = {
    "common": {"badge": "🟫", "name": "Обычная", "power": 1},
    "rare":   {"badge": "🟪", "name": "Редкая",   "power": 3},
    "epic":   {"badge": "🟧", "name": "Эпическая","power": 7},
}

RELICS: dict[str, dict] = {
    "relic_coin": {
        "name": "🪙 Древняя Монета", "rarity": "common",
        "price": {"mora": 500, "dark_mora": 30}, "exp_mora_pct": 0.03,
        "desc": "Монета забытой империи. Чуть щедрее делает походы.",
    },
    "relic_compass": {
        "name": "🧭 Ржавый Компас", "rarity": "common",
        "price": {"mora": 800, "dark_mora": 45}, "exp_mora_pct": 0.04,
        "desc": "Стрелка всё ещё чует поживу.",
    },
    "relic_idol": {
        "name": "🗿 Идол Торговца", "rarity": "common",
        "price": {"mora": 1200, "dark_mora": 60}, "exp_mora_pct": 0.05,
        "desc": "Покровитель сделок и тёмной наживы.",
    },
    "relic_chalice": {
        "name": "🏆 Кубок Бездны", "rarity": "rare",
        "price": {"diamonds": 100, "dark_mora": 150}, "exp_mora_pct": 0.10,
        "desc": "Из него пьют те, кто вернулся с того берега.",
    },
    "relic_crown": {
        "name": "👑 Корона Падших", "rarity": "rare",
        "price": {"diamonds": 150, "dark_mora": 220}, "exp_mora_pct": 0.12,
        "desc": "Венец, что носили владыки руин.",
    },
    "relic_heart": {
        "name": "💟 Сердце Тьмы", "rarity": "epic",
        "price": {"mora": 5000, "diamonds": 300, "dark_mora": 400}, "exp_mora_pct": 0.20,
        "desc": "Пульсирует в такт твоей жадности. Лучшая реликвия.",
    },
}


# ── Partner gifts (Implementation Block 5.4) ────────────────────────────────
# Подарки партнёру: дешёвые косметические (флавор, видны в карточке брака) +
# средние/дорогие бафф-подарки (накладывают study_xp на ПАРТНЁРА — реальный
# баф, потребляется в services/leveling.py). Оплата — с личного баланса дарителя.
PARTNER_GIFTS: dict[str, dict] = {
    "rose":    {"name": "🌹 Роза",            "price_mora": 300,     "kind": "cosmetic",
                "msg": "подарил(а) розу 🌹"},
    "teddy":   {"name": "🧸 Плюшевый мишка",  "price_mora": 800,     "kind": "cosmetic",
                "msg": "подарил(а) плюшевого мишку 🧸"},
    "choco":   {"name": "🍫 Коробка конфет",  "price_diamonds": 15,  "kind": "cosmetic",
                "msg": "подарил(а) коробку конфет 🍫"},
    "inspire": {"name": "📚 Вдохновение",     "price_mora": 2000,    "kind": "buff",
                "buff_value": 0.25, "buff_hours": 6,
                "msg": "вдохновил(а) партнёра 📚 — +25% XP на 6ч"},
    "ring":    {"name": "💍 Кольцо Музы",     "price_diamonds": 40,  "kind": "buff",
                "buff_value": 0.5,  "buff_hours": 12,
                "msg": "подарил(а) Кольцо Музы 💍 — +50% XP на 12ч"},
    "crown":   {"name": "👑 Корона Любви",    "price_zarniki": 150,  "kind": "buff",
                "buff_value": 0.5,  "buff_hours": 24,
                "msg": "короновал(а) партнёра 👑 — +50% XP на 24ч"},
}


# ── Craft Recipes ─────────────────────────────────────────────────────────────
# Single source of truth for all craftable items. Ingredient quantities from constants.
CRAFT_RECIPES: Dict[str, Dict[str, Any]] = {
    "summon_token": {
        "result_item": "spin_token",
        "result_qty": 1,
        "ingredients": [("soul_shard", SOUL_SHARDS_FOR_SUMMON_TOKEN)],
        "name": "🎟 Жетон Призыва",
        "category": "spin_token",
        # How to get soul_shards
        "ingredient_tip": "💠 Осколки Души — выпадают из круток Гачи, бывают в Акции дня",
        # What the result does
        "what_is": "Жетон гачи, который нельзя купить — только скрафтить из Осколков. Даёт бесплатную крутку мора-режима.",
        "gacha_rates": "Честные шансы крутки — во вкладке Гача (кнопка «Шансы»)",
        "how_use": "Перейдите во вкладку Гача и потратьте жетон на бесплатную крутку.",
        "how_to_get_ingredients": f"Осколки падают из круток Гачи и продаются в Акции дня. Нужно {SOUL_SHARDS_FOR_SUMMON_TOKEN} Осколков.",
    },
}
