# core/constants.py
# Single source of truth for every game number.
# Changing a value here automatically affects both Bot and Web.

# ── Leveling ──────────────────────────────────────────────────────────────────
XP_PER_MESSAGE: int = 10          # base XP awarded per chat message
XP_PER_LEVEL: int = 3_000         # XP needed for each level step
MORA_PER_LEVEL: float = 500.0     # Mora reward on level-up
DIAMONDS_PER_LEVEL: float = 1.0   # Diamond reward on level-up

# ── Economy ───────────────────────────────────────────────────────────────────
FAMILY_BANK_DEFAULT_CAP: float = 50_000.0

# ── Pet system base ──────────────────────────────────────────────────────────
PET_FATIGUE_WARN_THRESHOLD: int = 80     # fatigue level shown as warning in UI
PET_PLACEMENT_FATIGUE_RESTORE: int = 20  # fatigue cost when moving a pet
SOUL_SHARDS_FOR_SUMMON_EGG: int = 5      # shards required to craft egg_summon
PET_ACTIVE_FATIGUE_PER_DAY: int = 2      # daily fatigue gain for active-slot pets
PET_PASSIVE_FATIGUE_PER_DAY: int = 1     # daily fatigue gain for passive-slot pets
PET_MAX_FATIGUE_LAG_DAYS: int = 7        # max catch-up window for lazy decay

# ── Nursery slots (Implementation Block 2) ────────────────────────────────────
# 3 базовых (всем) + до 4 докупаемых за алмазы по прогрессивной цене.
# Хранимый max_slots = ZOO_BASE_SLOTS + (сколько докуплено). Потолок = 3+4 = 7.
# Сверху read-time бонус VIP (+1 для 3м/8м, +2 для 12м) — НЕ меняет хранимый max_slots.
ZOO_BASE_SLOTS: int = 3
ZOO_SLOT_PRICES_DIAMONDS: list[int] = [5, 15, 30, 50]  # цена 1-го/2-го/3-го/4-го докупаемого слота

# ── Pet level system (B1: duplicates-based) ──────────────────────────────────
PET_LEVEL_DUPLICATES: dict = {
    "common":    {2: 10, 3: 15, 4: 20, 5: 25, 6: 30, 7: 35, 8: 40, 9: 45, 10: 50},
    "rare":      {2: 5,  3: 10, 4: 15, 5: 20, 6: 25, 7: 30, 8: 35, 9: 40, 10: 45},
    "epic":      {2: 4,  3: 8,  4: 12, 5: 16, 6: 20, 7: 24, 8: 28, 9: 32, 10: 36},
    "legendary": {2: 2,  3: 4,  4: 6,  5: 8,  6: 10, 7: 13, 8: 16, 9: 20, 10: 25},
}
MAX_PET_COPIES: int = 3
DUPLICATE_OVERFLOW_MORA: dict = {"common": 60.0, "rare": 200.0, "epic": 450.0, "legendary": 1000.0}
DUPLICATE_OVERFLOW_STARDUST: dict = {"common": 0, "rare": 1, "epic": 1, "legendary": 2}

PET_LEVEL_MILESTONE_REWARDS: dict = {
    3:  {"mora": 800.0,  "diamonds": 0.0, "items": (),                                            "announce_chat": False},
    5:  {"mora": 2000.0, "diamonds": 0.0, "items": (("egg_silver", 1), ("spin_token_novice", 1)), "announce_chat": False},
    7:  {"mora": 4500.0, "diamonds": 0.0, "items": (("egg_gold", 1), ("spin_token_standard", 1)), "announce_chat": False},
    10: {"mora": 8000.0, "diamonds": 5.0, "items": (),                                            "announce_chat": True},
}


def get_total_duplicates_for_level(rarity: str, level: int) -> int:
    """Cumulative duplicates required to reach `level` from level 1."""
    table = PET_LEVEL_DUPLICATES.get(rarity, PET_LEVEL_DUPLICATES["common"])
    total = 0
    for lv in range(2, level + 1):
        total += table.get(lv, 0)
    return total


def get_level_for_duplicates(rarity: str, duplicates: int) -> int:
    """Maximum level achievable with `duplicates` collected. Caps at 10."""
    table = PET_LEVEL_DUPLICATES.get(rarity, PET_LEVEL_DUPLICATES["common"])
    level = 1
    spent = 0
    for lv in range(2, 11):
        need = table.get(lv, 0)
        if spent + need <= duplicates:
            spent += need
            level = lv
        else:
            break
    return level


# ── B2: Pet stat curves by level ─────────────────────────────────────────────
# Each species has a {1..10: dict-of-stats} table. Stats grow per level;
# T2 unlocks at Lv4, T3 at Lv8, capstone at Lv10.
# Lookup via get_pet_bonus(species_id, level) -> dict.

HAMSTER_BONUSES: dict = {
    1:  {"mora_per_hour": 2.0, "cap": 100, "ignore_exhaustion": False, "double_chance": 0.0, "daily_diamond": 0.0},
    2:  {"mora_per_hour": 2.0, "cap": 110, "ignore_exhaustion": False, "double_chance": 0.0, "daily_diamond": 0.0},
    3:  {"mora_per_hour": 2.5, "cap": 120, "ignore_exhaustion": False, "double_chance": 0.0, "daily_diamond": 0.0},
    4:  {"mora_per_hour": 2.5, "cap": 130, "ignore_exhaustion": True,  "double_chance": 0.0, "daily_diamond": 0.0},
    5:  {"mora_per_hour": 3.0, "cap": 140, "ignore_exhaustion": True,  "double_chance": 0.0, "daily_diamond": 0.0},
    6:  {"mora_per_hour": 3.5, "cap": 160, "ignore_exhaustion": True,  "double_chance": 0.0, "daily_diamond": 0.0},
    7:  {"mora_per_hour": 4.0, "cap": 180, "ignore_exhaustion": True,  "double_chance": 0.0, "daily_diamond": 0.0},
    8:  {"mora_per_hour": 4.0, "cap": 200, "ignore_exhaustion": True,  "double_chance": 0.05, "daily_diamond": 0.0},
    9:  {"mora_per_hour": 4.5, "cap": 220, "ignore_exhaustion": True,  "double_chance": 0.05, "daily_diamond": 0.0},
    10: {"mora_per_hour": 5.0, "cap": 250, "ignore_exhaustion": True,  "double_chance": 0.05, "daily_diamond": 0.5},
}

# Owl: rate = how many messages between bonus-XP triggers (1 = every msg, 2 = every 2nd, 4 = every 4th).
# expedition_xp_bonus is the +% to expedition XP. weekend_double = true → ×2 XP on Sat/Sun.
# daily_free_spin_token = whether capstone grants 1 spin_token_novice per day.
OWL_BONUS_XP: float = 1.0   # Base extra XP per triggered message (used by leveling)
OWL_HALF_BONUS_XP: float = 0.5  # Used when value is 1.5 (i.e. +1 every msg and +0.5 alternating)

OWL_BONUSES: dict = {
    1:  {"trigger_every_n_msg": 4, "bonus_xp": 1.0, "expedition_xp_bonus": 0.0,  "weekend_double": False, "daily_free_spin_token": False},
    2:  {"trigger_every_n_msg": 3, "bonus_xp": 1.0, "expedition_xp_bonus": 0.0,  "weekend_double": False, "daily_free_spin_token": False},
    3:  {"trigger_every_n_msg": 2, "bonus_xp": 1.0, "expedition_xp_bonus": 0.0,  "weekend_double": False, "daily_free_spin_token": False},
    4:  {"trigger_every_n_msg": 2, "bonus_xp": 1.0, "expedition_xp_bonus": 0.10, "weekend_double": False, "daily_free_spin_token": False},
    5:  {"trigger_every_n_msg": 1, "bonus_xp": 1.0, "expedition_xp_bonus": 0.10, "weekend_double": False, "daily_free_spin_token": False},
    6:  {"trigger_every_n_msg": 1, "bonus_xp": 1.0, "expedition_xp_bonus": 0.15, "weekend_double": False, "daily_free_spin_token": False},
    7:  {"trigger_every_n_msg": 1, "bonus_xp": 1.5, "expedition_xp_bonus": 0.20, "weekend_double": False, "daily_free_spin_token": False},
    8:  {"trigger_every_n_msg": 1, "bonus_xp": 1.5, "expedition_xp_bonus": 0.20, "weekend_double": True,  "daily_free_spin_token": False},
    9:  {"trigger_every_n_msg": 1, "bonus_xp": 2.0, "expedition_xp_bonus": 0.25, "weekend_double": True,  "daily_free_spin_token": False},
    10: {"trigger_every_n_msg": 1, "bonus_xp": 2.0, "expedition_xp_bonus": 0.30, "weekend_double": True,  "daily_free_spin_token": True},
}

# Dog: speed_reduction = % less time on expedition; self_fatigue_reduction = % less fatigue for the dog itself on expeditions;
# zero_fatigue_chance = 5% chance the expedition gives 0 fatigue (capstone Lv10); expedition_cost_reduction = -5% cost at capstone.
DOG_BONUSES: dict = {
    1:  {"speed_reduction": 0.03, "self_fatigue_reduction": 0.0,  "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    2:  {"speed_reduction": 0.04, "self_fatigue_reduction": 0.0,  "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    3:  {"speed_reduction": 0.05, "self_fatigue_reduction": 0.0,  "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    4:  {"speed_reduction": 0.05, "self_fatigue_reduction": 0.10, "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    5:  {"speed_reduction": 0.07, "self_fatigue_reduction": 0.10, "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    6:  {"speed_reduction": 0.08, "self_fatigue_reduction": 0.10, "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    7:  {"speed_reduction": 0.10, "self_fatigue_reduction": 0.15, "zero_fatigue_chance": 0.0, "expedition_cost_reduction": 0.0},
    8:  {"speed_reduction": 0.10, "self_fatigue_reduction": 0.15, "zero_fatigue_chance": 0.05, "expedition_cost_reduction": 0.0},
    9:  {"speed_reduction": 0.12, "self_fatigue_reduction": 0.20, "zero_fatigue_chance": 0.05, "expedition_cost_reduction": 0.0},
    10: {"speed_reduction": 0.15, "self_fatigue_reduction": 0.25, "zero_fatigue_chance": 0.05, "expedition_cost_reduction": 0.05},
}

# Turtle: shop_discount, expedition_discount, gacha_daily_discount, double_egg_chance.
TURTLE_BONUSES: dict = {
    1:  {"shop_discount": 0.02, "expedition_discount": 0.0,  "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    2:  {"shop_discount": 0.03, "expedition_discount": 0.0,  "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    3:  {"shop_discount": 0.03, "expedition_discount": 0.0,  "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    4:  {"shop_discount": 0.04, "expedition_discount": 0.05, "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    5:  {"shop_discount": 0.05, "expedition_discount": 0.05, "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    6:  {"shop_discount": 0.06, "expedition_discount": 0.07, "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    7:  {"shop_discount": 0.07, "expedition_discount": 0.08, "gacha_daily_discount": 0.0,  "double_egg_chance": 0.0},
    8:  {"shop_discount": 0.07, "expedition_discount": 0.10, "gacha_daily_discount": 0.10, "double_egg_chance": 0.0},
    9:  {"shop_discount": 0.09, "expedition_discount": 0.12, "gacha_daily_discount": 0.10, "double_egg_chance": 0.0},
    10: {"shop_discount": 0.10, "expedition_discount": 0.15, "gacha_daily_discount": 0.10, "double_egg_chance": 0.05},
}

# Falcon: mora_bonus, xp_bonus (+% expedition reward), double_loot_chance, capstone_8h_treasure_map (guaranteed map on 8h trip)
FALCON_BONUSES: dict = {
    1:  {"mora_bonus": 0.05, "xp_bonus": 0.0,  "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    2:  {"mora_bonus": 0.07, "xp_bonus": 0.0,  "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    3:  {"mora_bonus": 0.09, "xp_bonus": 0.0,  "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    4:  {"mora_bonus": 0.10, "xp_bonus": 0.10, "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    5:  {"mora_bonus": 0.12, "xp_bonus": 0.12, "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    6:  {"mora_bonus": 0.13, "xp_bonus": 0.13, "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    7:  {"mora_bonus": 0.14, "xp_bonus": 0.14, "double_loot_chance": 0.0,  "capstone_8h_treasure_map": False},
    8:  {"mora_bonus": 0.15, "xp_bonus": 0.15, "double_loot_chance": 0.05, "capstone_8h_treasure_map": False},
    9:  {"mora_bonus": 0.17, "xp_bonus": 0.17, "double_loot_chance": 0.07, "capstone_8h_treasure_map": False},
    10: {"mora_bonus": 0.20, "xp_bonus": 0.20, "double_loot_chance": 0.10, "capstone_8h_treasure_map": True},
}

# Wolf: passive_reduction (in passive slot), active_reduction (in active slot, T2 from Lv4),
# food_extra (active wolf food restore bonus, from T2), daily_restore_uses (T3 from Lv8),
# movement_immunity (capstone Lv10 → free moves).
# NOTE: cap on combined reduction is 0.50 (handled at call site).
WOLF_BONUSES: dict = {
    1:  {"passive_reduction": 0.03, "active_reduction": 0.00, "food_extra": 0, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    2:  {"passive_reduction": 0.04, "active_reduction": 0.00, "food_extra": 0, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    3:  {"passive_reduction": 0.05, "active_reduction": 0.00, "food_extra": 0, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    4:  {"passive_reduction": 0.05, "active_reduction": 0.10, "food_extra": 5, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    5:  {"passive_reduction": 0.07, "active_reduction": 0.12, "food_extra": 5, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    6:  {"passive_reduction": 0.08, "active_reduction": 0.13, "food_extra": 5, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    7:  {"passive_reduction": 0.10, "active_reduction": 0.14, "food_extra": 5, "daily_restore_uses": 0, "daily_restore_amount": 0, "movement_immunity": False},
    8:  {"passive_reduction": 0.10, "active_reduction": 0.15, "food_extra": 5, "daily_restore_uses": 1, "daily_restore_amount": 30, "movement_immunity": False},
    9:  {"passive_reduction": 0.13, "active_reduction": 0.17, "food_extra": 5, "daily_restore_uses": 1, "daily_restore_amount": 30, "movement_immunity": False},
    10: {"passive_reduction": 0.15, "active_reduction": 0.20, "food_extra": 5, "daily_restore_uses": 2, "daily_restore_amount": 30, "movement_immunity": True},
}
WOLF_REDUCTION_CAP: float = 0.50  # safety cap on combined wolf reductions

# Fox: diamond_chance_per_2h,
# common_dup_bonus (T2 Lv4: +% common duplicates from gacha — handled in gacha service),
# weekly_guaranteed_diamond (T3 Lv8), crystal_egg_chance (capstone Lv10: % chance of crystal egg from expedition).
FOX_BONUSES: dict = {
    1:  {"diamond_chance_per_2h": 0.02, "common_dup_bonus": 0.0, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    2:  {"diamond_chance_per_2h": 0.03, "common_dup_bonus": 0.0, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    3:  {"diamond_chance_per_2h": 0.03, "common_dup_bonus": 0.0, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    4:  {"diamond_chance_per_2h": 0.04, "common_dup_bonus": 0.10, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    5:  {"diamond_chance_per_2h": 0.04, "common_dup_bonus": 0.12, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    6:  {"diamond_chance_per_2h": 0.05, "common_dup_bonus": 0.15, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    7:  {"diamond_chance_per_2h": 0.05, "common_dup_bonus": 0.18, "weekly_guaranteed_diamond": False, "crystal_egg_chance": 0.0},
    8:  {"diamond_chance_per_2h": 0.05, "common_dup_bonus": 0.20, "weekly_guaranteed_diamond": True,  "crystal_egg_chance": 0.0},
    9:  {"diamond_chance_per_2h": 0.06, "common_dup_bonus": 0.22, "weekly_guaranteed_diamond": True,  "crystal_egg_chance": 0.0},
    10: {"diamond_chance_per_2h": 0.07, "common_dup_bonus": 0.25, "weekly_guaranteed_diamond": True,  "crystal_egg_chance": 0.05},
}

# Dragon: family bank boost (mora), free_food_chance, hamster_collect_bonus, weekly_bank_grant.
DRAGON_BONUSES: dict = {
    1:  {"bank_bonus": 10000.0, "free_food_chance": 0.0,  "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    2:  {"bank_bonus": 15000.0, "free_food_chance": 0.0,  "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    3:  {"bank_bonus": 20000.0, "free_food_chance": 0.0,  "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    4:  {"bank_bonus": 25000.0, "free_food_chance": 0.05, "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    5:  {"bank_bonus": 30000.0, "free_food_chance": 0.07, "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    6:  {"bank_bonus": 35000.0, "free_food_chance": 0.08, "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    7:  {"bank_bonus": 40000.0, "free_food_chance": 0.09, "hamster_collect_bonus": 0.0,  "weekly_bank_grant": 0.0},
    8:  {"bank_bonus": 45000.0, "free_food_chance": 0.10, "hamster_collect_bonus": 25.0, "weekly_bank_grant": 0.0},
    9:  {"bank_bonus": 48000.0, "free_food_chance": 0.11, "hamster_collect_bonus": 35.0, "weekly_bank_grant": 0.0},
    10: {"bank_bonus": 50000.0, "free_food_chance": 0.12, "hamster_collect_bonus": 50.0, "weekly_bank_grant": 500.0},
}

# Unicorn: daily_fatigue_reduction, immunity_uses (T2 Lv4 once-per-day), immunity_hours,
# active_recovery_per_hour (T3 Lv8), capstone_auto_recover_threshold (auto-restore on 100 fatigue every 3 days).
UNICORN_BONUSES: dict = {
    1:  {"daily_fatigue_reduction": 0.15, "immunity_uses": 0, "immunity_hours": 0, "active_recovery_per_hour": 0, "auto_recover": False},
    2:  {"daily_fatigue_reduction": 0.20, "immunity_uses": 0, "immunity_hours": 0, "active_recovery_per_hour": 0, "auto_recover": False},
    3:  {"daily_fatigue_reduction": 0.25, "immunity_uses": 0, "immunity_hours": 0, "active_recovery_per_hour": 0, "auto_recover": False},
    4:  {"daily_fatigue_reduction": 0.30, "immunity_uses": 1, "immunity_hours": 4, "active_recovery_per_hour": 0, "auto_recover": False},
    5:  {"daily_fatigue_reduction": 0.35, "immunity_uses": 1, "immunity_hours": 4, "active_recovery_per_hour": 0, "auto_recover": False},
    6:  {"daily_fatigue_reduction": 0.40, "immunity_uses": 1, "immunity_hours": 4, "active_recovery_per_hour": 0, "auto_recover": False},
    7:  {"daily_fatigue_reduction": 0.45, "immunity_uses": 1, "immunity_hours": 6, "active_recovery_per_hour": 0, "auto_recover": False},
    8:  {"daily_fatigue_reduction": 0.48, "immunity_uses": 1, "immunity_hours": 6, "active_recovery_per_hour": 2, "auto_recover": False},
    9:  {"daily_fatigue_reduction": 0.50, "immunity_uses": 1, "immunity_hours": 8, "active_recovery_per_hour": 3, "auto_recover": False},
    10: {"daily_fatigue_reduction": 0.50, "immunity_uses": 1, "immunity_hours": 12, "active_recovery_per_hour": 5, "auto_recover": True},
}
UNICORN_REDUCTION_CAP: float = 0.80  # safety cap on combined unicorn reduction


_PET_BONUS_TABLES: dict = {
    "hamster": HAMSTER_BONUSES,
    "owl":     OWL_BONUSES,
    "dog":     DOG_BONUSES,
    "turtle":  TURTLE_BONUSES,
    "falcon":  FALCON_BONUSES,
    "wolf":    WOLF_BONUSES,
    "fox":     FOX_BONUSES,
    "dragon":  DRAGON_BONUSES,
    "unicorn": UNICORN_BONUSES,
}


def get_pet_bonus(species_id: str, level: int) -> dict:
    """Look up the level-specific bonus dict for a species. Returns {} if unknown."""
    table = _PET_BONUS_TABLES.get(species_id)
    if not table:
        return {}
    return table.get(max(1, min(10, level)), {})


# ── Daily Deal (B5) ──────────────────────────────────────────────────────────
DAILY_DEAL_DISCOUNT_RANGE: tuple = (0.20, 0.40)   # 20-40% off base price
DAILY_DEAL_MORA_SLOTS: int = 6                      # mora slots per day
DAILY_DEAL_DIAMOND_SLOTS: int = 1                   # diamond slot per day

# ── Gacha (B3) ───────────────────────────────────────────────────────────────
SPIN_COSTS: dict = {
    "novice":   {"mora": 350.0,  "diamonds": 0.0},
    "standard": {"mora": 1000.0, "diamonds": 0.0},
    "premium":  {"mora": 2800.0, "diamonds": 0.0},
    "diamond":  {"mora": 0.0,    "diamonds": 5.0},
}
SPIN_MULTI_DISCOUNT: float = 0.10  # 10% off for 10× multi-pull
SPIN_MULTI_COUNT: int = 10
PITY_SOFT: dict = {"novice": 30, "standard": 25, "premium": 20, "diamond": 15}
PITY_HARD: dict = {"novice": 60, "standard": 50, "premium": 40, "diamond": 30}

SPIN_TYPE_LABELS: dict = {
    "novice":   "🎲 Ученическая",
    "standard": "💫 Стандартная",
    "premium":  "🌟 Премиум",
    "diamond":  "💎 Алмазная",
}
SPIN_TOKEN_IDS: dict = {
    "novice": "spin_token_novice",
    "standard": "spin_token_standard",
    "premium": "spin_token_premium",
    "diamond": "spin_token_diamond",
}

# ── Moderation ────────────────────────────────────────────────────────────────
DEFAULT_MAX_WARNINGS: int = 3
DEFAULT_SHIELD_DURATION_DAYS: int = 7

# ── Purge system ──────────────────────────────────────────────────────────────
DEFAULT_PURGE_NORM: int = 50        # minimum messages per period to stay in chat
DEFAULT_PURGE_PERIOD_DAYS: int = 7  # evaluation window for purge activity check

# ── Chat timezone ────────────────────────────────────────────────────────────
CHAT_TIMEZONE_MIN: int = -12
CHAT_TIMEZONE_MAX: int = 14

# ── Daily Streak (§21) ────────────────────────────────────────────────────────
STREAK_BLOCK_SIZE: int = 7
STREAK_RECOVERY_DIAMONDS: float = 1.5
STREAK_RECOVERY_MORA: float = 100.0
STREAK_BASE_MORA_REWARD: float = 70.0
STREAK_BASE_DIAMONDS_REWARD: float = 0.15
STREAK_BLOCK_BONUS_MULT: float = 4.0
STREAK_RECOVERY_WINDOW_HOURS: int = 48

# ── Stats ──────────────────────────────────────────────────────────────────────
INACTIVE_THRESHOLD_DAYS: int = 4

# ── PvP Duels (B12) ──────────────────────────────────────────────────────────
DUEL_MIN_BET: float = 200.0
DUEL_MAX_BET: float = 15000.0
DUEL_COMMISSION: float = 0.05    # 5% commission from winner's pot (goes to sink)
DUEL_COOLDOWN_HOURS: int = 24
DUEL_TIMEOUT_SECONDS: int = 60
DUEL_PET_FATIGUE_COST: int = 15  # both pets get this fatigue after duel
RARITY_POWER: dict = {"common": 1.0, "rare": 2.5, "epic": 5.0, "legendary": 10.0}

# ── Chest Events (B14) ───────────────────────────────────────────────────────
CHEST_REWARDS_BY_POSITION: dict = {
    1: 300.0, 2: 260.0, 3: 220.0, 4: 190.0, 5: 160.0,
    6: 130.0, 7: 110.0, 8:  90.0, 9:  70.0, 10: 55.0,
    11: 40.0, 12: 35.0, 13: 30.0, 14:  30.0, 15: 30.0,
}
CHEST_TOP3_BONUS_ITEM: str = "spin_token_novice"
CHEST_DURATION_SECONDS: int = 90
CHEST_MIN_ACTIVE_USERS_24H: int = 2
CHEST_MAX_CLAIMANTS: int = 15
CHEST_SPAWN_MIN_HOURS: int = 4
CHEST_SPAWN_MAX_HOURS: int = 8

# ── Auction (B13) ─────────────────────────────────────────────────────────────
AUCTION_DURATION_HOURS: int = 24
AUCTION_MAX_ACTIVE_LOTS: int = 5
AUCTION_MAX_LOTS_PER_WEEK: int = 30
AUCTION_MIN_BID: float = 10.0
AUCTION_MIN_BID_RAISE: float = 0.05
AUCTION_COMMISSION: float = 0.05
AUCTION_MAX_BID: float = 1_000_000.0

# ── Chat settings defaults (B19) ─────────────────────────────────────────────
CHAT_RANK_WARN: int = 2      # minimum local rank to issue a warn
CHAT_RANK_MUTE: int = 3      # minimum local rank to mute
CHAT_RANK_KICK: int = 4      # minimum local rank to kick
CHAT_RANK_BAN: int = 5       # minimum local rank to ban
CHAT_RANK_SHIELD: int = 4    # minimum rank to grant shield
CHAT_RANK_IMMUNE: int = 5    # minimum rank to grant immunity
CHAT_EVENTS_ENABLED: int = 1      # chests/events on by default
CHAT_NSFW_WARPS_ALLOWED: int = 1  # 18+ warps on by default
CHAT_AUCTION_MIN_RANK: int = 0    # any user can post to auction

# ── Exchange Event (B15) ──────────────────────────────────────────────────────
EXCHANGE_RATE_MORA_PER_DIAMOND: float = 3000.0
EXCHANGE_DAILY_CAP_DIAMONDS: float = 300.0
EXCHANGE_MIN_DIAMONDS_PER_REQUEST: float = 5.0

# ── Зарники: донат-экономика (Implementation Block 1) ─────────────────────────
ZARNIKI_PER_STAR: int = 10              # 1⭐ = 10✨

# (stars, base_zarniki, bonus_zarniki) — итого = base + bonus
STARS_PACKAGES: list[tuple[int, int, int]] = [
    (20,  200,  15),
    (50,  500,  50),
    (100, 1000, 100),   # MOST POPULAR
    (200, 2000, 200),
    (300, 3000, 300),
    (400, 4000, 400),
]
STARS_MOST_POPULAR: int = 100           # пакет со звёздочкой "самое популярное"

ZARNIKI_TO_MORA_RATE: float = 3.0       # 1✨ = 3🪙
ZARNIKI_TO_DIAMONDS_RATE: float = 0.05  # 1✨ = 0.05💎 (20✨ = 1💎)

# ── Mini-games (B16) ─────────────────────────────────────────────────────────
GAMES: dict = {
    "dice":     {"cooldown_min": 20, "min_bet": 100.0, "max_bet": 3000.0, "multiplier": 2.0},
    "coin":     {"cooldown_min": 20, "min_bet": 100.0, "max_bet": 3000.0, "multiplier": 1.9},
    "number":   {"cooldown_min": 30, "min_bet": 100.0, "max_bet": 1500.0, "multiplier": 8.0},
    "roulette": {"cooldown_min": 60, "min_bet": 200.0, "max_bet": 6000.0, "multiplier": 1.9},
}
GAMBLE_DAILY_CAP: float = 15000.0
ROULETTE_RED_NUMBERS: frozenset = frozenset({
    1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36
})

# ── Dark Mora (Тёмная Мора) ───────────────────────────────────────────────────
# Контрабанда
DARK_MORA_CONTRABANDA_COOLDOWN_DAYS: int = 7
DARK_MORA_CONTRABANDA_CATCH_PENALTY_DAYS: int = 4
DARK_MORA_CONTRABANDA_MIN_STAKE: float = 100.0
DARK_MORA_CONTRABANDA_MAX_STAKE: float = 5000.0
DARK_MORA_CONTRABANDA_SUCCESS_CHANCE: float = 0.40   # 40% success
DARK_MORA_CONTRABANDA_FAIL_CHANCE: float = 0.35      # 35% fail (total 75%, rest is catch)
DARK_MORA_CONTRABANDA_MORA_PER_DARK: float = 600.0   # mora per 1 dark mora gained

# Культ Бездны — 23:00–01:00 UTC (window crosses midnight)
DARK_MORA_CULT_HOUR_START: int = 23
DARK_MORA_CULT_HOUR_END: int = 1
DARK_MORA_CULT_STREAK_MIN: int = 7
DARK_MORA_CULT_LEVEL_MIN: int = 6
DARK_MORA_CULT_PETS_MIN: int = 3
DARK_MORA_CULT_COOLDOWN_DAYS: int = 30
DARK_MORA_CULT_REWARD_MIN: int = 10
DARK_MORA_CULT_REWARD_MAX: int = 20

# Теневой Торговец
DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS: int = 3
DARK_MORA_SHADOW_MERCHANT_WINNERS: int = 3
DARK_MORA_SHADOW_MERCHANT_REWARD_MIN: int = 5
DARK_MORA_SHADOW_MERCHANT_REWARD_MAX: int = 15
DARK_MORA_SHADOW_MERCHANT_ACTIVE_MINUTES: int = 120  # окно ответа 2 часа

# Предательство
DARK_MORA_BETRAYAL_REWARD: int = 3
DARK_MORA_BETRAYAL_TOP_STREAK: int = 2    # недель в топ-3 подряд
DARK_MORA_BETRAYAL_SILENCE_DAYS: int = 3  # дней молчания после

# ── Artifacts & Relics ────────────────────────────────────────────────────────
ARTIFACT_TOP_MONTH_MIN_MESSAGES: int = 3000
ARTIFACT_TOP_MONTH_COUNT: int = 5
RELIC_TOP_GLOBAL_MIN_MESSAGES: int = 4000
RELIC_TOP_GLOBAL_CHAT_COUNT: int = 3
RELIC_TOP_GLOBAL_USERS_PER_CHAT: int = 5

# ── VIP perks (Implementation Block 4) ─────────────────────────────────────────
NICKNAME_FREE_CHANGES_PER_MONTH: int = 5  # non-VIP nickname changes per chat per calendar month
VIP_EXPIRY_REMINDER_DAYS: int = 3         # send "VIP expiring soon" reminder this many days before expiry

# ── Battle Pass (Implementation Block 5) ───────────────────────────────────────
BATTLE_PASS_XP_PER_LEVEL: int = 100  # линейная шкала; подбирается при балансировке
BATTLE_PASS_MAX_LEVEL: int = 50
BATTLE_PASS_SEASON_END_REMINDER_DAYS: int = 3  # напомнить активным игрокам о скором конце сезона

# metric_name (как в вызовах services.achievements.increment_metric) -> XP за единицу delta
BATTLE_PASS_XP_WEIGHTS: dict[str, int] = {
    "duel_wins": 10,
    "eggs_opened": 5,
    "expeditions_done": 8,
    "gacha_spins": 3,
    "auction_sales": 12,
    "gamble_wins": 4,
    "marriage_days_total": 2,
    "legendary_gacha_drops": 50,
    "weekly_top1_count": 100,
}
