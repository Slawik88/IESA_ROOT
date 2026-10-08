"""Pets v2 «Тропа»: чистые правила прокачки, энергии, риска и находок.

Без базы, сети и часов: модуль считает, но ничего не записывает и не выдаёт.
Источник чисел — docs/PETS_V2_DESIGN.md; те же числа проверяют симуляторы в tools/pets_v2_*_sim.py.
Награды в валютах (Мора, Алмазы, Эссенция) выдаёт отдельный писатель через существующие журналы.
"""
from __future__ import annotations

from math import floor
from typing import Final

POLICY_VERSION: Final = "pets-v2-2026-10-08"
MAX_LEVEL: Final = 30


class PetV2PolicyError(ValueError):
    """Недопустимое действие или вход; ничего не списывать и не начислять."""


# ── Следы и суточная норма ────────────────────────────────────────────────────
RARITY_COST: Final = {"common": 1.0, "uncommon": 1.1, "rare": 1.25, "epic": 1.5, "legendary": 1.8}
POOL_FULL: Final = 500        # Следов в сутки по полной ставке (на аккаунт)
SOFT_WIDTH: Final = 500       # следующие «сырые» Следы идут по SOFT_RATE
SOFT_RATE: Final = 0.25
DAILY_MAX: Final = POOL_FULL + int(SOFT_WIDTH * SOFT_RATE)       # 625
RUN_HOURS: Final = (3, 6, 9)
WATCH_HOURS: Final = (12, 24)
RUN_XP: Final = {3: 40, 6: 95, 9: 160}
WATCH_XP: Final = {12: 70, 24: 110}
EXPEDITION_MULT: Final = 1.2
REPEAT_DECAY: Final = 0.75
AFFINITY_BONUS: Final = 0.20      # любимый маршрут вида
SEAL_BONUS_PER_STAR: Final = 0.04  # Привязанность вида, до 5 звёзд
FEED_XP: Final = 10
DAILY_TASKS_XP: Final = 60
WIND_MULT: Final = 1.25            # «Попутный ветер»: к зачисляемым Следам, но не выше DAILY_MAX
ROUTES: Final = ("forest", "pass", "ruins", "swamp")
SLOTS: Final = 3                  # одновременных занятий на аккаунт

# ── Уровни, ступени, Связь ────────────────────────────────────────────────────
BOND_GATES: Final = ((5, 2), (10, 21), (15, 50), (20, 90), (25, 140), (30, 200))  # (потолок, дней Связи)
STAGE_ESSENCE: Final = {5: 5, 10: 10, 15: 15, 20: 20, 25: 30}                    # разовая Эссенция за пройденный потолок
SEAL_BOND_DAYS: Final = (10, 30, 60, 120, 240)                                   # суммарные дни Связи вида -> звёзды
DUPLICATE_BOND_GIFT_DAYS: Final = 3


def level_cost(level: int, rarity: str = "common") -> int:
    """Следов на переход level -> level+1."""
    if not 1 <= int(level) < MAX_LEVEL:
        raise PetV2PolicyError("Уровень вне диапазона 1–29.")
    if rarity not in RARITY_COST:
        raise PetV2PolicyError("Неизвестная редкость.")
    return round(40 * int(level) ** 1.7 * RARITY_COST[rarity])


def ceiling(bond_days: int) -> int:
    """Максимальный уровень при данной Связи (потолок ступени)."""
    if int(bond_days) < 0:
        raise PetV2PolicyError("Связь не может быть отрицательной.")
    out = 5
    for level, days in BOND_GATES:
        if int(bond_days) >= days:
            out = min(MAX_LEVEL, level + 5)
    return out


def seal_stars(total_bond_days: int) -> int:
    """Звёзды Привязанности вида по суммарным дням Связи всех его питомцев."""
    return sum(1 for need in SEAL_BOND_DAYS if int(total_bond_days) >= need)


def pool_credit(before_raw: float, raw: float) -> float:
    """Сколько Следов зачтётся, если сегодня уже набрано before_raw «сырых»."""
    if before_raw < 0 or raw < 0:
        raise PetV2PolicyError("Следы не могут быть отрицательными.")
    full = max(0.0, min(raw, POOL_FULL - before_raw))
    soft_before = max(0.0, before_raw - POOL_FULL)
    soft = max(0.0, min(raw - full, SOFT_WIDTH - soft_before))
    return full + soft * SOFT_RATE


def run_xp_raw(hours: int, *, expedition: bool = False, repeats_today: int = 0,
               favorite_route: bool = False, stars: int = 0, trait_mult: float = 1.0, repeat_decay: float = REPEAT_DECAY) -> float:
    """«Сырые» Следы похода до суточной нормы."""
    if hours not in RUN_XP:
        raise PetV2PolicyError("Поход: только 3, 6 или 9 часов.")
    if repeats_today < 0 or not 0 <= stars <= 5:
        raise PetV2PolicyError("Некорректные повторы или звёзды.")
    value = RUN_XP[hours] * (repeat_decay ** repeats_today) * trait_mult
    if expedition:
        value *= EXPEDITION_MULT
    value *= 1 + (AFFINITY_BONUS if favorite_route else 0) + SEAL_BONUS_PER_STAR * stars
    return value


def watch_xp_raw(hours: int) -> float:
    if hours not in WATCH_XP:
        raise PetV2PolicyError("Дозор: только 12 или 24 часа.")
    return float(WATCH_XP[hours])


def apply_wind(credited: float, credited_today: float) -> float:
    """«Попутный ветер»: +25 % к зачисляемому, но суточный максимум остаётся общим."""
    return max(0.0, min(credited * WIND_MULT, DAILY_MAX - credited_today))


# ── Виды и энергия ────────────────────────────────────────────────────────────
# (редкость, любимый маршрут, бонус запаса, бонус отдыха, категория находок с ростом шанса)
SPECIES: Final = {
    "moss_cat":      ("common", "forest", 0, 0, "treat"),
    "stone_beetle":  ("common", "pass", 10, -1, "talisman"),
    "ash_moth":      ("common", "swamp", -10, 1, "diamond"),
    "dusk_hare":     ("common", "forest", -5, 2, "mora"),
    "rain_finch":    ("common", "ruins", -10, 1, "bonus_xp"),
    "salt_fox":      ("uncommon", "pass", 0, 1, "mora"),
    "reed_guardian": ("uncommon", "swamp", 15, -1, "talisman"),
    "lantern_gecko": ("uncommon", "ruins", 5, 1, "mora"),
    "mirror_owl":    ("rare", "ruins", 0, 1, "essence"),
    "frost_stag":    ("rare", "pass", 20, -1, "mora"),
    "void_lynx":     ("epic", "swamp", 5, 2, "diamond"),
    "star_dragon":   ("legendary", "any", 20, 2, "mora"),
}
ACTIVITY_ENERGY: Final = {("run", 3): 15, ("run", 6): 30, ("run", 9): 45, ("watch", 12): 20, ("watch", 24): 30}
PAIR_ENERGY: Final = 10


def _species(species_id: str) -> tuple:
    row = SPECIES.get(species_id)
    if not row:
        raise PetV2PolicyError("Неизвестный вид питомца.")
    return row


def energy_max(level: int, species_id: str, bonus: int = 0) -> int:
    """Запас сил: 70 + 2×уровень + бонус вида (+ бонус черты)."""
    if not 1 <= int(level) <= MAX_LEVEL:
        raise PetV2PolicyError("Уровень вне диапазона 1–30.")
    return 70 + 2 * int(level) + _species(species_id)[2] + int(bonus)


def energy_regen_per_hour(level: int, species_id: str, *, camp_bonus: float = 0.0, delta: float = 0.0) -> float:
    """Отдых в час: 4 + бонус вида + 0.5 за каждые 10 уровней (+ Лежанка до +20 %)."""
    if not 1 <= int(level) <= MAX_LEVEL or not 0.0 <= camp_bonus <= 0.2:
        raise PetV2PolicyError("Некорректный уровень или бонус Лагеря.")
    return max(1.0, 4 + delta + _species(species_id)[3] + 0.5 * (int(level) // 10)) * (1 + camp_bonus)


def energy_after_rest(energy: float, *, hours: float, level: int, species_id: str, camp_bonus: float = 0.0,
                      bonus: int = 0, delta: float = 0.0) -> float:
    cap = energy_max(level, species_id, bonus)
    if energy < 0 or hours < 0:
        raise PetV2PolicyError("Некорректная энергия или время.")
    return min(float(cap), energy + hours * energy_regen_per_hour(level, species_id, camp_bonus=camp_bonus, delta=delta))


def spend_energy(energy: float, kind: str, hours: int) -> float:
    cost = ACTIVITY_ENERGY.get((kind, int(hours)))
    if cost is None:
        raise PetV2PolicyError("Неизвестное занятие.")
    if energy < cost:
        raise PetV2PolicyError(f"Нужно {cost} энергии.")
    return energy - cost


# ── Решения экспедиции: Выдержка, шанс, исход, подсказка ──────────────────────
PATHS: Final = {  # сдвиг разрыва, награда: успех / частично / провал, потеря энергии при провале
    "careful": (+8, (0.8, 0.6, 0.4), 0),
    "steady": (0, (1.1, 0.7, 0.25), 0),
    "bold": (-8, (1.8, 0.7, 0.0), 15),
}
PARTIAL_BAND: Final = 25
PITY_STEP: Final = 5
PITY_MAX: Final = 15


def event_difficulty(hours: int) -> int:
    """Сложность события экспедиции: 3 ч — 17, 6 ч — 20, 9 ч — 23."""
    if hours not in RUN_XP:
        raise PetV2PolicyError("Экспедиция: только 3, 6 или 9 часов.")
    return 14 + 3 * (int(hours) // 3)


def resilience(level: int, energy: float, species_id: str, *, terrain_match: bool = False,
               guardian: bool = False, favorite_treat: bool = False, energy_bonus: int = 0, extra: float = 0.0) -> float:
    """Выдержка R = 10 + уровень + 10 × доля энергии + склонность(3) + Хранитель(2) + любимое лакомство(2) (+ черты)."""
    cap = energy_max(level, species_id, energy_bonus)
    if not 0 <= energy <= cap:
        raise PetV2PolicyError("Энергия вне запаса питомца.")
    return 10 + int(level) + 10 * (energy / cap) + (3 if terrain_match else 0) + (2 if guardian else 0) + (2 if favorite_treat else 0) + extra


def path_chance(resilience_value: float, difficulty: float, path: str, *, pity: int = 0, bonus: float = 0.0) -> float:
    """Шанс успеха пути, % (5…95). pity — подряд невезений (0–3)."""
    if path not in PATHS:
        raise PetV2PolicyError("Выбери осторожный, ровный или рискованный путь.")
    gap = resilience_value - difficulty
    chance = 50 + 3.5 * (gap + PATHS[path][0]) + min(PITY_MAX, PITY_STEP * max(0, int(pity))) + bonus
    return max(5.0, min(95.0, chance))


def decide_outcome(chance: float, roll: float) -> str:
    """roll — равномерное число 0 ≤ roll < 100, бросается сервером один раз."""
    if not 0 <= roll < 100:
        raise PetV2PolicyError("Бросок вне 0–100.")
    partial = min(PARTIAL_BAND, 100 - chance)
    if roll < chance:
        return "success"
    if roll < chance + partial:
        return "partial"
    return "fail"


def outcome_reward_mult(path: str, outcome: str, *, guardian: bool = False) -> float:
    if path not in PATHS or outcome not in ("success", "partial", "fail"):
        raise PetV2PolicyError("Неизвестный путь или исход.")
    value = PATHS[path][1][("success", "partial", "fail").index(outcome)]
    if guardian and outcome == "fail":
        value *= 1.25   # Хранитель смягчает неудачу
    return value


def next_pity(streak: int, chance: float, outcome: str) -> int:
    """Мягкая защита: провал на пути со шансом ≥ 40 % копит +5 % (до +15 %)."""
    if outcome == "success":
        return 0
    if outcome == "fail" and chance >= 40:
        return min(PITY_MAX // PITY_STEP, int(streak) + 1)
    return int(streak)


def chance_sign(chance: float) -> str:
    return ("Надёжно" if chance >= 85 else "Скорее удастся" if chance >= 65 else
            "Как повезёт" if chance >= 40 else "Рискованно" if chance >= 20 else "Отчаянно")


def hint_detail(level: int, species_id: str) -> str:
    """Что показывать игроку: sign → factors (с 4) → range (с 8) → exact (с 12 и у совы)."""
    if species_id == "mirror_owl" or int(level) >= 12:
        return "exact"
    return "range" if int(level) >= 8 else "factors" if int(level) >= 4 else "sign"


def chance_range(chance: float) -> tuple[int, int]:
    lo = max(0, 5 * floor((chance - 10) / 5))
    hi = min(100, 5 * -(-int(round(chance + 10)) // 5))
    return lo, hi


# ── Находки (только реальные валюты и предметы питомцев) ──────────────────────
FIND_WEIGHTS: Final = {"mora": 62, "treat": 14, "talisman": 6, "diamond": 2, "essence": 3, "bonus_xp": 13}
FIND_CAP_MULT: Final = 2.5
FIND_VALUE: Final = {"mora": 6, "diamond": 1, "essence": 3}
FIND_DAILY_CAP: Final = {"mora": 60, "diamond": 1, "essence": 4}
FIND_WEEKLY_CAP: Final = {"diamond": 2}
RARE_FIND_MIN_LEVEL: Final = 8       # Алмаз и Эссенция только с этого уровня питомца
ROLLS: Final = {("run", 3): 1, ("run", 6): 2, ("run", 9): 3, ("watch", 12): 2, ("watch", 24): 3}
SPECIES_FIND_BONUS: Final = 1.4      # множитель категории, к которой склонен вид


def find_shares(mods: dict[str, float] | None = None, *, species_id: str | None = None, level: int = 1) -> dict[str, float]:
    """Доли категорий находки. Любой бонус одной категории автоматически делает остальные реже."""
    mods = dict(mods or {})
    if species_id:
        favored = _species(species_id)[4]
        mods[favored] = mods.get(favored, 1.0) * SPECIES_FIND_BONUS
    weights = {}
    for key, base in FIND_WEIGHTS.items():
        if key in ("diamond", "essence") and int(level) < RARE_FIND_MIN_LEVEL:
            weights[key] = 0.0
            continue
        weights[key] = base * min(FIND_CAP_MULT, mods.get(key, 1.0))
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def cap_find(category: str, amount: float, *, today: float, this_week: float = 0.0) -> float:
    """Урезать находку по суточному и недельному потолку."""
    allowed = amount
    if category in FIND_DAILY_CAP:
        allowed = min(allowed, FIND_DAILY_CAP[category] - today)
    if category in FIND_WEEKLY_CAP:
        allowed = min(allowed, FIND_WEEKLY_CAP[category] - this_week)
    return max(0.0, allowed)


# ── Лагерь и траты Эссенции ───────────────────────────────────────────────────
CAMP_BUILDINGS: Final = ("lounge", "markers", "workshop")
CAMP_COST_MORA: Final = (100, 200, 400, 700, 1200)
CAMP_COST_ESSENCE: Final = (20, 40, 70, 110, 170)
CAMP_HOURS: Final = (6, 12, 24, 36, 48)
TRAIT_SWAP_ESSENCE: Final = 10
CALLING_SWAP_ESSENCE: Final = 15
REFORGE_ESSENCE: Final = {1: 10, 2: 20, 3: 40}


def camp_upgrade_cost(building: str, to_level: int) -> dict:
    if building not in CAMP_BUILDINGS or not 1 <= int(to_level) <= 5:
        raise PetV2PolicyError("Неизвестная постройка или уровень.")
    i = int(to_level) - 1
    return {"mora": CAMP_COST_MORA[i], "essence": CAMP_COST_ESSENCE[i], "hours": CAMP_HOURS[i]}


def camp_bonus(building: str, level: int) -> float:
    """Бонус постройки: ≈5 % за уровень; Лежанка даёт до +20 % отдыха (4 % за уровень, максимум 5 уровней = 20 %)."""
    if building not in CAMP_BUILDINGS or not 0 <= int(level) <= 5:
        raise PetV2PolicyError("Неизвестная постройка или уровень.")
    return round(0.04 * int(level), 2) if building == "lounge" else round(0.05 * int(level), 2)


def markers_decay(level: int) -> float:
    """Указатели: повтор маршрута дешевеет слабее (×0.75 → ×0.85 на 5 уровне)."""
    if not 0 <= int(level) <= 5:
        raise PetV2PolicyError("Уровень постройки 0–5.")
    return REPEAT_DECAY + 0.02 * int(level)


def workshop_max_tier(level: int) -> int:
    """Мастерская: тир талисманов I–III (II с 2 уровня, III с 4)."""
    if not 0 <= int(level) <= 5:
        raise PetV2PolicyError("Уровень постройки 0–5.")
    return min(3, 1 + int(level) // 2)


def reforge_cost(from_tier: int) -> int:
    """Эссенция за перековку талисмана на тир выше."""
    if from_tier not in (1, 2):
        raise PetV2PolicyError("Перековать можно тир I или II.")
    return REFORGE_ESSENCE[from_tier]


# ── Выслеживание: сетка 3×3 ──────────────────────────────────────────────────
TRACK_DAILY: Final = 2
TRACK_FREE_CLUES: Final = 3
TRACK_ROLLS: Final = 2


def track_points(level: int, species_id: str) -> int:
    """Очки внимания на открытие клеток: 3, +1 с 8 уровня, +1 с 16, сова +1."""
    _species(species_id)
    return 3 + (int(level) >= 8) + (int(level) >= 16) + (species_id == "mirror_owl")


def track_heat(hidden: int, cell: int) -> str:
    """Подсказка клетки: найдено / тепло (рядом, включая диагональ) / холодно."""
    if not (0 <= hidden < 9 and 0 <= cell < 9):
        raise PetV2PolicyError("Клетка вне сетки 3×3.")
    if hidden == cell:
        return "found"
    return "warm" if max(abs(hidden // 3 - cell // 3), abs(hidden % 3 - cell % 3)) == 1 else "cold"


# ── Испытание недели ─────────────────────────────────────────────────────────
TRIAL_XP: Final = 300
TRIAL_ESSENCE: Final = {1: 5, 2: 12, 3: 20}   # награда по сложности; сложность = число совпавших тегов


def weekly_trial(week_ordinal: int) -> dict:
    """Теги недели: маршрут, темп (3 или 9 ч) и стиль решений. Одинаковы у всех игроков недели."""
    import random
    rng = random.Random(f"pets-v2-trial-{int(week_ordinal)}")
    return {"route": rng.choice(ROUTES), "tempo": rng.choice((3, 9)), "style": rng.choice(("careful", "bold"))}


def trial_matches(trial: dict, favorite_route: str, traits: tuple[str, ...], talismans: tuple[tuple[str, int], ...] = ()) -> int:
    """Сколько тегов закрывает питомец: любимый маршрут или талисман маршрута; черта темпа; черта стиля."""
    count = 0
    if favorite_route in (trial["route"], "any") or any(TALISMANS[kind][0] == trial["route"] for kind, _ in talismans if kind in TALISMANS):
        count += 1
    if ("night_walk" if trial["tempo"] == 9 else "sprinter") in traits:
        count += 1
    if ("careful" if trial["style"] == "careful" else "reckless") in traits:
        count += 1
    return count


# ── Призвания и черты (данные; применение — в писателе занятий) ───────────────
CALLINGS: Final = ("tracker", "feeder", "guardian", "seeker")
TRAIT_SLOT_LEVELS: Final = (5, 15, 25)
TRAITS: Final = {
    "night_walk": ("9 ч: +15 % Следов", "3 ч: −15 %"),
    "sprinter": ("3 ч: +15 % Следов", "9 ч: −15 %"),
    "reckless": ("рискованный путь +5 % шанса", "осторожный −5 %"),
    "careful": ("осторожный путь +10 % награды", "рискованный −10 % шанса"),
    "picky": ("с любимым лакомством редкие находки ×1.2", "без него Следы −10 %"),
    "hoarder": ("лакомства ×1.5", "Выдержка −1"),
    "piggybank": ("Мора ×1.3", "лакомства ×0.8"),
    "meticulous": ("Алмаз и Эссенция ×1.8", "бонус Следов ×0.7"),
    "hardy": ("запас сил +15", "отдых −1/ч"),
    "nose": ("шанс доп. ключа 10 → 18 %", "Следы −5 %"),
    "lunatic": ("болота +25 % Следов", "лес −15 %"),
    "loner": ("без спутника +10 % Следов", "в Паре −10 %"),
}


def trait_xp_multiplier(traits: tuple[str, ...], hours: int) -> float:
    """Часть эффектов черт, меняющая Следы похода (остальные считаются в писателе находок/решений)."""
    mult = 1.0
    if "night_walk" in traits:
        mult *= 1.15 if hours == 9 else 0.85 if hours == 3 else 1.0
    if "sprinter" in traits:
        mult *= 1.15 if hours == 3 else 0.85 if hours == 9 else 1.0
    if "nose" in traits:
        mult *= 0.95
    return mult


def trait_slots(level: int) -> int:
    return sum(1 for need in TRAIT_SLOT_LEVELS if int(level) >= need)


# ── Применение билда: призвание, черты, талисманы ─────────────────────────────
CALLING_MIN_LEVEL: Final = 10
CALLING_MODS: Final = {  # множители категорий находок; tracker ждёт ключей сундуков
    "feeder": {"treat": 2.0, "mora": 0.85},
    "seeker": {"diamond": 1.8, "essence": 1.8, "mora": 0.85},
}
AVAILABLE_CALLINGS: Final = ("feeder", "guardian", "seeker")
AVAILABLE_TRAITS: Final = tuple(t for t in TRAITS if t not in ("picky", "nose", "loner"))  # их плюс зависит от ещё не готовых механик
TALISMANS: Final = {  # вид: (маршрут плюса, маршрут минуса)
    "forest_fang": ("forest", "swamp"), "pass_stone": ("pass", "ruins"),
    "ruin_lens": ("ruins", "pass"), "swamp_lamp": ("swamp", "forest"),
}
TALISMAN_PLUS: Final = {1: 0.10, 2: 0.15, 3: 0.20}
TALISMAN_MINUS: Final = 0.10
TALISMAN_SET_BONUS: Final = 0.05
TALISMAN_SLOTS: Final = 2
FREE_SWAP_DAYS: Final = 7


def build_effects(calling: str | None, traits: tuple[str, ...], talismans: tuple[tuple[str, int], ...] = (),
                  *, hours: int = 3, route: str | None = None) -> dict:
    """Сводка билда: множитель Следов, множители находок, поправки Выдержки, шанса и награды путей."""
    if calling is not None and calling not in CALLINGS:
        raise PetV2PolicyError("Неизвестное призвание.")
    if len(set(traits)) != len(traits) or any(t not in TRAITS for t in traits):
        raise PetV2PolicyError("Неизвестная или повторяющаяся черта.")
    mods: dict[str, float] = {}

    def mul(key: str, value: float) -> None:
        mods[key] = mods.get(key, 1.0) * value

    for key, value in CALLING_MODS.get(calling or "", {}).items():
        mul(key, value)
    xp = trait_xp_multiplier(tuple(t for t in traits if t != "nose"), hours)
    resilience_extra, energy_bonus, regen_delta = 0.0, 0, 0.0
    chance = {"careful": 0.0, "steady": 0.0, "bold": 0.0}
    reward = {"careful": 1.0, "steady": 1.0, "bold": 1.0}
    for trait in traits:
        if trait == "reckless":
            chance["bold"] += 5; chance["careful"] -= 5
        elif trait == "careful":
            reward["careful"] *= 1.10; chance["bold"] -= 10
        elif trait == "hoarder":
            mul("treat", 1.5); resilience_extra -= 1
        elif trait == "piggybank":
            mul("mora", 1.3); mul("treat", 0.8)
        elif trait == "meticulous":
            mul("diamond", 1.8); mul("essence", 1.8); mul("bonus_xp", 0.7)
        elif trait == "hardy":
            energy_bonus += 15; regen_delta -= 1
        elif trait == "lunatic" and route:
            xp *= 1.25 if route == "swamp" else 0.85 if route == "forest" else 1.0
    for kind, tier in talismans:
        if kind not in TALISMANS or tier not in TALISMAN_PLUS:
            raise PetV2PolicyError("Неизвестный талисман.")
        plus, minus = TALISMANS[kind]
        if route == plus:
            xp *= 1 + TALISMAN_PLUS[tier]
        elif route == minus:
            xp *= 1 - TALISMAN_MINUS
    kinds = [kind for kind, _ in talismans]
    for kind in set(kinds):
        if kinds.count(kind) >= 2 and route == TALISMANS[kind][0]:
            xp *= 1 + TALISMAN_SET_BONUS
    return {"xp_mult": xp, "find_mods": mods, "resilience_extra": resilience_extra, "energy_bonus": energy_bonus,
            "regen_delta": regen_delta, "chance_bonus": chance, "reward_mult": reward, "guardian": calling == "guardian"}


def validate() -> None:
    if DAILY_MAX != 625:
        raise PetV2PolicyError("Суточная норма изменилась: обновить документ и симуляторы.")
    if abs(sum(find_shares(level=MAX_LEVEL).values()) - 1.0) > 1e-9:
        raise PetV2PolicyError("Доли находок не складываются в 100 %.")
    if set(ROUTES) - {row[1] for row in SPECIES.values()} - {"any"}:
        raise PetV2PolicyError("У маршрута нет питомца со склонностью.")
    for species_id, row in SPECIES.items():
        if row[0] not in RARITY_COST or row[1] not in (*ROUTES, "any") or row[4] not in FIND_WEIGHTS:
            raise PetV2PolicyError(f"Описание вида {species_id} некорректно.")
        if energy_max(1, species_id) < ACTIVITY_ENERGY[("run", 9)]:
            raise PetV2PolicyError("Слабейший питомец должен тянуть 9-часовой поход.")
    for trait, (plus, minus) in TRAITS.items():
        if not plus or not minus:
            raise PetV2PolicyError(f"У черты {trait} должны быть плюс и минус.")
    if [g for g in BOND_GATES if g[0] % 5] or sorted(BOND_GATES) != list(BOND_GATES):
        raise PetV2PolicyError("Ступени заданы неверно.")
