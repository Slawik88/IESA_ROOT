# core/registry.py
# Single source of truth for all game data: items, pets, gacha rates, expeditions.
# Used by both the Bot and the Web panel. Never import platform-specific code here.
from typing import Dict, Any

from core.constants import SOUL_SHARDS_FOR_SUMMON_EGG


# ── Items (inventory, shop, consumables) ──────────────────────────────────────
ITEMS_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Materials
    "soul_shard": {
        "name": "💠 Осколок Души",
        "category": "material",
        "description": "Используется для крафта Яйца Призыва. Добывается при распылении питомцев.",
        "is_tradable": False,
    },
    "star_dust_s": {
        "name": "🌟 Звёздная пыль",
        "category": "material",
        "description": "+1 дубликат к выбранному питомцу. Используйте через «бот зоопарк».",
        "is_tradable": False,
    },
    "star_dust_l": {
        "name": "✨ Небесная пыль",
        "category": "material",
        "description": "+5 дубликатов к выбранному питомцу. Используйте через «бот зоопарк».",
        "is_tradable": False,
    },
    # Gacha-exclusive items (не продаются в магазине)
    "treasure_map": {
        "name": "🗺 Карта Сокровищ",
        "category": "booster",
        "description": "Следующая экспедиция: +50% к максимуму лута. Разовый предмет.",
        "is_tradable": False,
    },
    "study_notes": {
        "name": "📚 Конспект",
        "category": "utility",
        "price_mora": 600,
        "description": "+50% XP от сообщений на 4 часа.",
        "is_tradable": False,
    },
    "lucky_charm": {
        "name": "🍀 Подкова Удачи",
        "category": "booster",
        "description": "+15% к шансу редкости в следующем открытом яйце.",
        "is_tradable": False,
    },
    # Spin tokens (bесплатные спины из гачи)
    "spin_token_novice":   {"name": "🎟 Жетон Ученической",   "category": "spin_token", "spin_type": "novice",   "is_tradable": False, "description": "Один бесплатный спин Ученической крутки."},
    "spin_token_standard": {"name": "🎟 Жетон Стандартной",   "category": "spin_token", "spin_type": "standard", "is_tradable": False, "description": "Один бесплатный спин Стандартной крутки."},
    "spin_token_premium":  {"name": "🎟 Жетон Премиум",       "category": "spin_token", "spin_type": "premium",  "is_tradable": False, "description": "Один бесплатный спин Премиум крутки."},
    "spin_token_diamond":  {"name": "🎟 Жетон Алмазной",      "category": "spin_token", "spin_type": "diamond",  "is_tradable": False, "description": "Один бесплатный спин Алмазной крутки."},
    # Eggs (gacha)
    "egg_basic":   {"name": "🥚 Базовое Яйцо",      "category": "egg", "price_mora": 8000,      "description": "80% Common / 19% Rare / 1% Epic"},
    "egg_summon":  {"name": "🔮 Яйцо Призыва",      "category": "egg",                          "description": "Крафтится из 5 Осколков. Не даёт осколков при распылении."},
    "egg_silver":  {"name": "🥈 Серебряное Яйцо",   "category": "egg", "price_mora": 28000,     "description": "50% Common / 40% Rare / 10% Epic"},
    "egg_gold":    {"name": "🪙 Золотое Яйцо",      "category": "egg", "price_diamonds": 250, "price_mora": 120000, "description": "75% Rare / 25% Epic"},
    "egg_mythic":  {"name": "💎 Мифическое Яйцо",   "category": "egg", "price_diamonds": 500,   "description": "40% Rare / 60% Epic"},
    "egg_unity":   {"name": "💖 Яйцо Единства",     "category": "egg",                          "description": "100% Legendary. Только для Семей."},
    "egg_crystal": {"name": "🔷 Кристальное Яйцо",  "category": "egg",                          "description": "30% Epic / 70% Legendary. Только из гачи."},
    "egg_daily":   {"name": "🎁 Яйцо Дня",          "category": "egg",                          "description": "70% Common / 29% Rare / 1% Epic. Бесплатно 1 раз в день."},
    # Food / consumables
    "food_basic":   {
        "name": "🥩 Базовый корм",        "category": "food", "price_mora": 120,
        "fatigue_restore": 15,            "description": "Снижает 15 усталости.",
    },
    "food_elite":   {
        "name": "🍗 Элитный корм",        "category": "food", "price_mora": 450,
        "fatigue_restore": 50,            "description": "Снижает 50 усталости.",
    },
    "food_energy":  {
        "name": "⚡️ Энергетик",          "category": "food", "price_mora": 750,
        "fatigue_restore": 20,            "buff": "expedition_cd_reset",
        "description": "Снижает 20 усталости + сброс КД экспедиции.",
    },
    "food_super": {
        "name": "💊 Суперкорм",           "category": "food", "price_mora": 1100,
        "fatigue_restore": 60,            "description": "Снижает 60 усталости активному питомцу + 5 всем питомцам в питомнике.",
    },
    "food_diamond": {
        "name": "💎 Алмазное лакомство",  "category": "food", "price_diamonds": 12,
        "fatigue_restore": 100,           "buff": "efficiency_20", "duration_hours": 24,
        "description": "Полностью снимает усталость + 20% к эффективности на 24ч.",
    },
    # Utility (shop + deal)
    "slot_expander": {
        "name": "🏡 Расширитель слота", "category": "utility", "price_diamonds": 15,
        "description": "Постоянно +1 слот в питомнике (макс 6).", "is_tradable": False,
    },
    # Player buffs (for player, not pet)
    "potion_luck_s": {
        "name": "🧪 Зелье Удачи (М)", "category": "booster", "price_mora": 400,
        "description": "Следующий спин гачи: +15% к шансу ред.+ (разовый).",
        "is_tradable": False, "buff_type": "gacha_luck", "buff_value": 0.15, "buff_uses": 1,
    },
    "potion_luck_m": {
        "name": "🔮 Зелье Удачи (Б)", "category": "booster",
        "description": "Следующие 3 спина гачи: +15% к шансу ред.+ (разовый).",
        "is_tradable": False, "buff_type": "gacha_luck", "buff_value": 0.15, "buff_uses": 3,
    },
    "potion_sprint": {
        "name": "⚡ Зелье Рывка", "category": "booster",
        "description": "Следующая экспедиция: +30% к луту (разовый).",
        "is_tradable": False, "buff_type": "expedition_loot", "buff_value": 0.30, "buff_uses": 1,
    },
    # Expedition time boosters (gacha-only)
    "exp_boost_1h": {
        "name": "⏩ Ускоритель (1ч)", "category": "booster",
        "description": "Сокращает текущую активную экспедицию на 1 час.",
        "is_tradable": False, "boost_hours": 1,
    },
    "exp_boost_2h": {
        "name": "⏩⏩ Ускоритель (2ч)", "category": "booster",
        "description": "Сокращает текущую активную экспедицию на 2 часа.",
        "is_tradable": False, "boost_hours": 2,
    },
    "exp_boost_4h": {
        "name": "🚀 Ускоритель (4ч)", "category": "booster",
        "description": "Сокращает текущую активную экспедицию на 4 часа.",
        "is_tradable": False, "boost_hours": 4,
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
    # Rare
    "turtle":  {"name": "🐢 Черепаха-торговец",   "rarity": "rare",      "default_role": "passive", "desc": "Скидка в магазине. Lv4 — скидка на экспедиции, Lv8 — скидка на крутку, Lv10 — шанс ×2 яйца."},
    "falcon":  {"name": "🦅 Охотничий Сокол",     "rarity": "rare",      "default_role": "active",  "desc": "+Мора из похода. Lv4 — +XP похода, Lv8 — шанс двойной добычи, Lv10 — гарант. Карта Сокровищ в 8ч поход."},
    # Epic
    "wolf":    {"name": "🐺 Снежный Волк",        "rarity": "epic",      "default_role": "passive", "desc": "Снижает усталость питомнику. Lv4 — корм +5 ед. в актив, Lv8 — раз в день восстанавливает 30, Lv10 — иммунитет перемещений."},
    "fox":     {"name": "🦊 Огненная Лиса",       "rarity": "epic",      "default_role": "active",  "desc": "Шанс 💎 в походе. Lv4 — +Common-дубликаты из гачи, Lv8 — гарант. 💎/нед, Lv10 — шанс Кристального яйца."},
    # Legendary
    "dragon":  {"name": "🐉 Дракон Хранитель",    "rarity": "legendary", "default_role": "passive", "desc": "Поднимает кап семейного банка. Lv4 — бесплатный корм, Lv8 — Мора при сборе хомяков, Lv10 — +500/нед в банк."},
    "unicorn": {"name": "🦄 Астральный Единорог", "rarity": "legendary", "default_role": "passive", "desc": "−% к суточной усталости всех. Lv4 — раз в день иммунитет, Lv8 — актив восстанавливается, Lv10 — авто-восст. при 100."},
}


# ── Gacha rates (egg opening) ────────────────────────────────────────────────
GACHA_RATES: Dict[str, Dict[str, int]] = {
    "egg_basic":   {"common": 80, "rare": 19, "epic": 1,   "legendary": 0},
    "egg_summon":  {"common": 80, "rare": 19, "epic": 1,   "legendary": 0},
    "egg_silver":  {"common": 50, "rare": 40, "epic": 10,  "legendary": 0},
    "egg_gold":    {"common": 0,  "rare": 75, "epic": 25,  "legendary": 0},
    "egg_mythic":  {"common": 0,  "rare": 40, "epic": 60,  "legendary": 0},
    "egg_unity":   {"common": 0,  "rare": 0,  "epic": 0,   "legendary": 100},
    "egg_crystal": {"common": 0,  "rare": 0,  "epic": 30,  "legendary": 70},
    "egg_daily":   {"common": 70, "rare": 29, "epic": 1,   "legendary": 0},
}


# ── Gacha spin tables (B3) ────────────────────────────────────────────────────
# Entry types:
#   mora         – random mora in [min, max]
#   item         – specific item (id, qty)
#   combo        – multiple items at once (items: [{id, qty}, ...])
#   diamond      – diamonds (qty)
#   pet_dup      – random pet dup of `rarity`
# "valuable": True  → weight doubled on soft pity

GACHA_TABLES: Dict[str, list] = {
    "novice": [
        {"weight": 26, "type": "mora",    "min": 20,  "max": 50},
        {"weight": 16, "type": "item",    "id": "food_basic",    "qty": 1},
        {"weight": 12, "type": "item",    "id": "star_dust_s",   "qty": 1},
        {"weight": 10, "type": "item",    "id": "soul_shard",    "qty": 1},
        {"weight": 8,  "type": "mora",    "min": 60,  "max": 90},
        {"weight": 8,  "type": "pet_dup", "rarity": "common",    "valuable": True},
        {"weight": 7,  "type": "combo",   "items": [{"id": "food_basic", "qty": 2}, {"id": "star_dust_s", "qty": 1}]},
        {"weight": 4,  "type": "item",    "id": "food_energy",   "qty": 1},
        {"weight": 4,  "type": "item",    "id": "potion_luck_s", "qty": 1},
        {"weight": 2,  "type": "item",    "id": "exp_boost_1h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "egg_basic",     "qty": 1, "valuable": True},
        {"weight": 0.8,"type": "pet_dup", "rarity": "common",    "valuable": True},
        {"weight": 0.2,"type": "diamond", "qty": 1,              "valuable": True},
    ],
    "standard": [
        {"weight": 20, "type": "mora",    "min": 60,  "max": 150},
        {"weight": 13, "type": "item",    "id": "food_elite",    "qty": 1},
        {"weight": 12, "type": "pet_dup", "rarity": "rare",      "valuable": True},
        {"weight": 10, "type": "combo",   "items": [{"id": "soul_shard", "qty": 2}, {"id": "star_dust_s", "qty": 1}]},
        {"weight": 10, "type": "pet_dup", "rarity": "common"},
        {"weight": 8,  "type": "mora",    "min": 200, "max": 280},
        {"weight": 7,  "type": "item",    "id": "star_dust_l",   "qty": 1},
        {"weight": 5,  "type": "combo",   "items": [{"id": "egg_basic", "qty": 1}, {"id": "study_notes", "qty": 1}]},
        {"weight": 4,  "type": "item",    "id": "egg_silver",    "qty": 1, "valuable": True},
        {"weight": 3,  "type": "item",    "id": "treasure_map",  "qty": 1},
        {"weight": 3,  "type": "item",    "id": "exp_boost_1h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "exp_boost_2h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "potion_luck_s", "qty": 1},
        {"weight": 0.8,"type": "diamond", "qty": 2,              "valuable": True},
        {"weight": 0.2,"type": "item",    "id": "egg_mythic",    "qty": 1, "valuable": True},
    ],
    "premium": [
        {"weight": 16, "type": "mora",    "min": 150, "max": 400},
        {"weight": 13, "type": "item",    "id": "egg_silver",    "qty": 1},
        {"weight": 12, "type": "pet_dup", "rarity": "epic",      "valuable": True},
        {"weight": 10, "type": "combo",   "items": [{"id": "soul_shard", "qty": 3}, {"id": "star_dust_l", "qty": 2}]},
        {"weight": 9,  "type": "pet_dup", "rarity": "rare"},
        {"weight": 8,  "type": "mora",    "min": 500, "max": 750},
        {"weight": 8,  "type": "item",    "id": "egg_gold",      "qty": 1, "valuable": True},
        {"weight": 6,  "type": "combo",   "items": [{"id": "treasure_map", "qty": 1}, {"id": "lucky_charm", "qty": 1}]},
        {"weight": 5,  "type": "combo",   "items": [{"id": "egg_basic", "qty": 1}], "diamond_bonus": 2, "valuable": True},
        {"weight": 4,  "type": "item",    "id": "egg_mythic",    "qty": 1, "valuable": True},
        {"weight": 3,  "type": "item",    "id": "exp_boost_2h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "exp_boost_4h",  "qty": 1, "valuable": True},
        {"weight": 2,  "type": "item",    "id": "potion_luck_m", "qty": 1},
        {"weight": 2,  "type": "pet_dup", "rarity": "epic",      "valuable": True},
        {"weight": 1.5,"type": "diamond", "qty": 4,              "valuable": True},
        {"weight": 0.4,"type": "item",    "id": "egg_crystal",   "qty": 1, "valuable": True},
        {"weight": 0.1,"type": "pet_dup", "rarity": "legendary", "valuable": True},
    ],
    "diamond": [
        {"weight": 23, "type": "item",    "id": "egg_gold",      "qty": 1, "valuable": True},
        {"weight": 16, "type": "item",    "id": "egg_mythic",    "qty": 1, "valuable": True},
        {"weight": 14, "type": "combo",   "items": [{"id": "egg_silver", "qty": 1}], "diamond_bonus": 2, "valuable": True},
        {"weight": 12, "type": "pet_dup", "rarity": "epic",      "valuable": True},
        {"weight": 10, "type": "combo",   "items": [{"id": "treasure_map", "qty": 3}], "valuable": True},
        {"weight": 8,  "type": "item",    "id": "egg_crystal",   "qty": 1, "valuable": True},
        {"weight": 6,  "type": "diamond", "qty": 4,              "valuable": True},
        {"weight": 4,  "type": "item",    "id": "exp_boost_4h",  "qty": 1, "valuable": True},
        {"weight": 3,  "type": "combo",   "items": [{"id": "exp_boost_2h", "qty": 1}, {"id": "potion_sprint", "qty": 1}], "valuable": True},
        {"weight": 3,  "type": "pet_dup", "rarity": "legendary", "valuable": True},
        {"weight": 2,  "type": "item",    "id": "egg_unity",     "qty": 1, "valuable": True},
        {"weight": 1,  "type": "pet_dup_multi", "rarity": "legendary", "count": 2, "valuable": True},
    ],
}

PITY_HARD_REWARD: Dict[str, dict] = {
    "novice":   {"type": "pet_dup", "rarity": "common"},
    "standard": {"type": "pet_dup", "rarity": "rare"},
    "premium":  {"type": "pet_dup", "rarity": "epic"},
    "diamond":  {"type": "pet_dup", "rarity": "legendary"},
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
    {"item_id": "food_basic",          "qty_range": (1, 5), "base_price_mora": 120},
    {"item_id": "food_elite",          "qty_range": (1, 3), "base_price_mora": 450},
    {"item_id": "food_energy",         "qty_range": (1, 3), "base_price_mora": 750},
    {"item_id": "food_super",          "qty_range": (1, 2), "base_price_mora": 1100},
    {"item_id": "spin_token_novice",   "qty_range": (1, 3), "base_price_mora": 350},
    {"item_id": "spin_token_standard", "qty_range": (1, 2), "base_price_mora": 1000},
    {"item_id": "spin_token_premium",  "qty_range": (1, 1), "base_price_mora": 2800},
    {"item_id": "egg_basic",           "qty_range": (1, 2), "base_price_mora": 8000},
    {"item_id": "egg_silver",          "qty_range": (1, 1), "base_price_mora": 28000},
    {"item_id": "treasure_map",        "qty_range": (1, 2), "base_price_mora": 900},
    {"item_id": "lucky_charm",         "qty_range": (1, 2), "base_price_mora": 900},
    {"item_id": "study_notes",         "qty_range": (1, 2), "base_price_mora": 600},
    {"item_id": "soul_shard",          "qty_range": (3, 10), "base_price_mora": 100},
    {"item_id": "star_dust_s",         "qty_range": (2, 5), "base_price_mora": 700},
    {"item_id": "star_dust_l",         "qty_range": (1, 2), "base_price_mora": 3000},
]

DAILY_DEAL_POOL_DIAMOND: list = [
    {"item_id": "food_diamond",       "qty_range": (1, 3), "base_price_dia": 12},
    {"item_id": "spin_token_diamond", "qty_range": (1, 2), "base_price_dia": 5},
    {"item_id": "egg_mythic",         "qty_range": (1, 1), "base_price_dia": 500},
    {"item_id": "slot_expander",      "qty_range": (1, 1), "base_price_dia": 15},
    {"item_id": "egg_crystal",        "qty_range": (1, 1), "base_price_dia": 35},
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
    {"id": "open_egg",   "metric": "eggs_opened_today",             "target": 1,  "reward": {"items": [("soul_shard", 1)]},                   "weight": 3},
    {"id": "warp_3",     "metric": "warps_to_distinct_users_today", "target": 3,  "reward": {"mora": 200.0},                                  "weight": 3},
    {"id": "auction_bid","metric": "auction_bids_today",            "target": 1,  "reward": {"mora": 200.0},                                  "weight": 2},
    # Hard
    {"id": "exped_4",    "metric": "expeditions_today",             "target": 4,  "reward": {"mora": 1000.0},                                 "weight": 2},
    {"id": "gacha_10",   "metric": "gacha_spins_today",             "target": 10, "reward": {"mora": 600.0, "items": [("spin_token_novice", 1)]}, "weight": 2},
    {"id": "hug_5",      "metric": "warps_hug_distinct_today",      "target": 5,  "reward": {"mora": 300.0},                                  "weight": 2},
    {"id": "rare_dup",   "metric": "rare_or_better_pet_dups_today", "target": 1,  "reward": {"mora": 800.0},                                  "weight": 1},
    {"id": "level_pet",  "metric": "pet_level_ups_today",           "target": 1,  "reward": {"mora": 500.0},                                  "weight": 1},
]

# ── Achievements (B11) ────────────────────────────────────────────────────────
ACHIEVEMENTS: Dict[str, Dict] = {
    "egg_opener": {
        "icon": "🥚", "name": "Яйцелов",
        "metric": "eggs_opened",
        "thresholds": [10, 30, 75, 150, 300, 600, 1200, 2500, 5000, 10000],
    },
    "gacha_addict": {
        "icon": "🎰", "name": "Завсегдатай Гачи",
        "metric": "gacha_spins",
        "thresholds": [10, 50, 150, 400, 1000, 2500, 5000, 10000, 25000, 50000],
    },
    "collector": {
        "icon": "🐾", "name": "Коллекционер",
        "metric": "distinct_species_owned",
        "thresholds": [3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
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
        "thresholds": [7, 30, 90, 180, 365, 540, 730, 1095, 1460, 1825],
    },
    "patron": {
        "icon": "🛒", "name": "Меценат",
        "metric": "total_mora_spent_shop",
        "thresholds": [500, 2000, 5000, 15000, 50000, 150000, 500000, 1500000, 5000000, 15000000],
    },
    "magnate": {
        "icon": "💰", "name": "Магнат",
        "metric": "peak_mora_balance",
        "thresholds": [1000, 5000, 25000, 100000, 500000, 1500000, 5000000, 15000000, 50000000, 150000000],
    },
    "treasury": {
        "icon": "💎", "name": "Сокровищница",
        "metric": "peak_diamonds_balance",
        "thresholds": [5, 25, 100, 500, 1500, 5000, 15000, 50000, 150000, 500000],
    },
    "dealer": {
        "icon": "🏛", "name": "Делец Аукциона",
        "metric": "auction_sales",
        "thresholds": [1, 5, 15, 40, 100, 250, 600, 1500, 3500, 8000],
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
}

ACHIEVEMENT_LEVEL_REWARDS: Dict[int, Dict] = {
    1:  {"mora": 100.0,   "diamonds": 0.0, "items": ()},
    2:  {"mora": 200.0,   "diamonds": 0.0, "items": ()},
    3:  {"mora": 400.0,   "diamonds": 0.0, "items": (("spin_token_novice", 1),)},
    4:  {"mora": 800.0,   "diamonds": 0.0, "items": (("spin_token_novice", 1),)},
    5:  {"mora": 1500.0,  "diamonds": 0.0, "items": (("spin_token_standard", 1),)},
    6:  {"mora": 3000.0,  "diamonds": 1.0, "items": ()},
    7:  {"mora": 6000.0,  "diamonds": 2.0, "items": (("spin_token_premium", 1),)},
    8:  {"mora": 12000.0, "diamonds": 5.0, "items": (("spin_token_premium", 1),)},
    9:  {"mora": 25000.0, "diamonds": 10.0, "items": (("egg_mythic", 1),)},
    10: {"mora": 50000.0, "diamonds": 25.0, "items": (("spin_token_diamond", 3), ("egg_crystal", 1))},
}


# ── Craft Recipes ─────────────────────────────────────────────────────────────
# Each recipe: result_item, result_qty, ingredients [(item_id, qty), ...], name, desc.
# Ingredient quantities reference constants — no raw numbers here.
CRAFT_RECIPES: Dict[str, Dict[str, Any]] = {
    "egg_summon": {
        "result_item": "egg_summon",
        "result_qty": 1,
        "ingredients": [("soul_shard", SOUL_SHARDS_FOR_SUMMON_EGG)],
        "name": "🔮 Яйцо Призыва",
        "desc": (
            f"Яйцо, которое нельзя купить — только скрафтить. "
            f"Требует {SOUL_SHARDS_FOR_SUMMON_EGG}× 💠 Осколков Души.\n"
            "Шансы: 80% Common / 19% Rare / 1% Epic. "
            "При распылении питомца из этого яйца осколок не возвращается."
        ),
    },
}
