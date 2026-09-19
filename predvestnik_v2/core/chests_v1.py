"""Pure, versioned policy for the release chest catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable, Final, Mapping, Sequence


POLICY_VERSION: Final = "chests-v1-2026-09-12-paid-1"
CATALOG_VERSION: Final = "chests-mixed-s1-v2"
PAID_KEY_PRICE_ZARNIKI: Final = 10
PAID_KEY_DAILY_LIMIT: Final = 2
KEY_SOURCE_AMOUNTS: Final = {
    "quest_daily_set_complete": 1,
    "quest_weekly_set_complete": 1,
    "zarniki_purchase": 1,
    "pet_trek_complete": 1,
    "pet_expedition_complete": 1,
}
STAR_WEIGHTS: Final = {
    1: 3500, 2: 2700, 3: 1800, 4: 900, 5: 500,
    6: 300, 7: 150, 8: 80, 9: 40, 10: 30,
}

# Stable release IDs: five common, three uncommon, two rare, one epic and one legendary.
PET_SPECIES: Final = {
    "moss_cat": {"name": "Моховой кот", "rarity": "common", "icon": "🐈"},
    "stone_beetle": {"name": "Каменный жук", "rarity": "common", "icon": "🪲"},
    "ash_moth": {"name": "Пепельный мотылёк", "rarity": "common", "icon": "🦋"},
    "dusk_hare": {"name": "Сумеречный заяц", "rarity": "common", "icon": "🐇"},
    "rain_finch": {"name": "Дождевой вьюрок", "rarity": "common", "icon": "🐦"},
    "salt_fox": {"name": "Соляная лисица", "rarity": "uncommon", "icon": "🦊"},
    "reed_guardian": {"name": "Камышовый страж", "rarity": "uncommon", "icon": "🦦"},
    "lantern_gecko": {"name": "Фонарный геккон", "rarity": "uncommon", "icon": "🦎"},
    "mirror_owl": {"name": "Зеркальная сова", "rarity": "rare", "icon": "🦉"},
    "frost_stag": {"name": "Инейный олень", "rarity": "rare", "icon": "🦌"},
    "void_lynx": {"name": "Рысь Бездны", "rarity": "epic", "icon": "🐆"},
    "star_dragon": {"name": "Звёздный дракон", "rarity": "legendary", "icon": "🐉"},
}
FOODS: Final = {
    "food_basic": {"name": "Дорожный паёк", "restore": 15, "icon": "🥕"},
    "food_fried": {"name": "Тёплое жаркое", "restore": 30, "icon": "🍗"},
    "food_stew": {"name": "Звёздное рагу", "restore": 50, "icon": "🍲"},
    "food_elite": {"name": "Нектар авроры", "restore": 75, "icon": "🧃"},
    "food_feast": {"name": "Пир хранителя", "restore": 100, "icon": "🍱"},
}
JOKER_RARITIES: Final = ("common", "uncommon", "rare", "epic", "legendary")
MORA_RANGES: Final = {
    1: (18, 28), 2: (28, 42), 3: (45, 65), 4: (65, 95), 5: (95, 140),
    6: (140, 210), 7: (220, 320), 8: (340, 500), 9: (600, 900), 10: (1200, 1800),
}
DIAMOND_RANGES: Final = {5: (1, 1), 6: (1, 2), 7: (1, 2), 8: (2, 3), 9: (3, 5), 10: (5, 8)}
ZARNIKI_RANGES: Final = {9: (10, 30), 10: (30, 50)}
VIP_DAYS: Final = 4
VIP_COSMETIC_POOL: Final = (
    "cos_card_fx_embers",
    "cos_avatar_frame_celestial",
    "cos_avatar_halo_aurora",
)
VIP_COSMETIC_NAMES: Final = {
    "cos_card_fx_embers": "Угольки",
    "cos_avatar_frame_celestial": "Небесная оправа",
    "cos_avatar_halo_aurora": "Аврора",
}

# Conditional weights after star selection. Each row totals exactly 100.
REWARD_WEIGHTS: Final = {
    1: {"mora": 70, "food": 30},
    2: {"mora": 55, "food": 45},
    3: {"mora": 15, "food": 20, "pet_card": 65},
    4: {"mora": 15, "food": 10, "pet_card": 75},
    5: {"mora": 17, "diamonds": 8, "pet_card": 67, "joker": 8},
    6: {"mora": 15, "diamonds": 10, "pet_card": 66, "joker": 9},
    7: {"mora": 10, "diamonds": 10, "pet_card": 67, "joker": 13},
    8: {"mora": 8, "diamonds": 12, "pet_card": 68, "joker": 12},
    9: {"mora": 10, "diamonds": 15, "zarniki": 10, "pet_card": 50, "joker": 15},
    10: {"mora": 5, "diamonds": 10, "zarniki": 10, "pet_card": 50, "joker": 18, "vip_reward": 7},
}
CARD_RARITY_WEIGHTS: Final = {
    3: {"common": 77, "uncommon": 23},
    4: {"common": 54, "uncommon": 33, "rare": 13},
    5: {"common": 45, "uncommon": 30, "rare": 22, "epic": 3},
    6: {"common": 34, "uncommon": 30, "rare": 27, "epic": 9},
    7: {"common": 27, "uncommon": 27, "rare": 30, "epic": 15, "legendary": 1},
    8: {"common": 15, "uncommon": 22, "rare": 37, "epic": 22, "legendary": 4},
    9: {"common": 20, "uncommon": 20, "rare": 50, "legendary": 10},
    10: {"common": 10, "uncommon": 10, "rare": 30, "epic": 30, "legendary": 20},
}
JOKER_RARITY_WEIGHTS: Final = {
    5: {"common": 63, "uncommon": 37},
    6: {"common": 56, "uncommon": 33, "rare": 11},
    7: {"common": 31, "uncommon": 23, "rare": 23, "epic": 15, "legendary": 8},
    8: {"common": 25, "uncommon": 25, "rare": 25, "epic": 17, "legendary": 8},
    9: {"common": 27, "uncommon": 20, "rare": 20, "epic": 20, "legendary": 13},
    10: {"common": 11, "uncommon": 17, "rare": 28, "epic": 28, "legendary": 16},
}
FOOD_BY_STARS: Final = {
    1: ("food_basic",), 2: ("food_basic", "food_fried"),
    3: ("food_basic", "food_fried"), 4: ("food_fried", "food_stew"),
}
CARD_AMOUNTS: Final = {3: 550, 4: 1100, 5: 2200, 6: 4400, 7: 8800,
                       8: 13200, 9: 22000, 10: 33000}
JOKER_AMOUNTS: Final = {5: 1, 6: 2, 7: 3, 8: 5, 9: 8, 10: 12}


class ChestPolicyError(ValueError):
    """The proposed key/chest action is outside the approved policy."""


@dataclass(frozen=True, slots=True)
class KeyGrant:
    source_kind: str
    source_event_id: str
    amount: int
    source_snapshot: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ChestOutcome:
    roll: int
    stars: int
    reward_kind: str
    amount: int
    reward_ref: str | None = None
    rarity: str | None = None


def _identifier(value: object, field: str, *, max_length: int = 160) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_length or any(ord(char) < 32 for char in normalized):
        raise ChestPolicyError(f"{field} must contain 1..{max_length} printable characters.")
    return normalized


def canonical_snapshot_fingerprint(snapshot: Mapping[str, object]) -> str:
    if not isinstance(snapshot, Mapping):
        raise ChestPolicyError("source_snapshot must be a mapping.")
    try:
        encoded = json.dumps(dict(snapshot), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ChestPolicyError("source_snapshot must contain canonical JSON values.") from exc
    return sha256(encoded.encode("utf-8")).hexdigest()


def validate_key_grant(grant: KeyGrant) -> KeyGrant:
    source_kind = _identifier(grant.source_kind, "source_kind", max_length=64)
    if source_kind not in KEY_SOURCE_AMOUNTS:
        raise ChestPolicyError("Unsupported chest-key source.")
    source_event_id = _identifier(grant.source_event_id, "source_event_id")
    if isinstance(grant.amount, bool) or not isinstance(grant.amount, int):
        raise ChestPolicyError("amount must be an integer.")
    if grant.amount != KEY_SOURCE_AMOUNTS[source_kind]:
        raise ChestPolicyError("This chest-key source has a fixed amount.")
    snapshot = dict(grant.source_snapshot) if isinstance(grant.source_snapshot, Mapping) else grant.source_snapshot
    canonical_snapshot_fingerprint(snapshot)
    return KeyGrant(source_kind, source_event_id, grant.amount, snapshot)


def _weighted_choice(weights: Mapping[object, int], randbelow: Callable[[int], int]):
    total = sum(weights.values())
    cursor = randbelow(total)
    for value, weight in weights.items():
        if cursor < weight:
            return value
        cursor -= weight
    raise RuntimeError("Weighted chest catalogue has an uncovered range.")


def _choice(values: Sequence[str], randbelow: Callable[[int], int]) -> str:
    return values[randbelow(len(values))]


def _species_for_rarity(rarity: str) -> tuple[str, ...]:
    return tuple(species_id for species_id, row in PET_SPECIES.items() if row["rarity"] == rarity)


def catalog_payload() -> dict[str, object]:
    return {
        "catalog_version": CATALOG_VERSION, "star_weights": STAR_WEIGHTS,
        "reward_weights": REWARD_WEIGHTS, "card_rarity_weights": CARD_RARITY_WEIGHTS,
        "joker_rarity_weights": JOKER_RARITY_WEIGHTS, "mora_ranges": MORA_RANGES,
        "diamond_ranges": DIAMOND_RANGES, "zarniki_ranges": ZARNIKI_RANGES,
        "foods": FOODS, "food_by_stars": FOOD_BY_STARS, "pet_species": PET_SPECIES,
        "vip_days": VIP_DAYS, "vip_cosmetic_ids": VIP_COSMETIC_POOL,
        "vip_cosmetic_names": VIP_COSMETIC_NAMES,
        "card_amounts": CARD_AMOUNTS, "joker_amounts": JOKER_AMOUNTS,
        "paid_key_price_zarniki": PAID_KEY_PRICE_ZARNIKI,
        "paid_key_daily_limit": PAID_KEY_DAILY_LIMIT,
        "duplicate_compensation": "deferred_until_preproduction_release_review",
    }


def catalog_digest() -> str:
    return canonical_snapshot_fingerprint(catalog_payload())


def stars_for_roll(roll: int) -> int:
    if isinstance(roll, bool) or not isinstance(roll, int) or not 0 <= roll < 10_000:
        raise ChestPolicyError("roll must be an integer from 0 through 9999.")
    cursor = 0
    for stars, weight in STAR_WEIGHTS.items():
        cursor += weight
        if roll < cursor:
            return stars
    raise RuntimeError("Chest star weights do not cover the full roll space.")


def roll_outcome(randbelow: Callable[[int], int], *, vip_cosmetic_ids: Sequence[str] = ()) -> ChestOutcome:
    roll = randbelow(10_000)
    stars = stars_for_roll(roll)
    kind = str(_weighted_choice(REWARD_WEIGHTS[stars], randbelow))
    if kind == "mora":
        minimum, maximum = MORA_RANGES[stars]
        return ChestOutcome(roll, stars, kind, minimum + randbelow(maximum - minimum + 1))
    if kind == "diamonds":
        minimum, maximum = DIAMOND_RANGES[stars]
        return ChestOutcome(roll, stars, kind, minimum + randbelow(maximum - minimum + 1))
    if kind == "zarniki":
        minimum, maximum = ZARNIKI_RANGES[stars]
        return ChestOutcome(roll, stars, kind, minimum + randbelow(maximum - minimum + 1))
    if kind == "food":
        return ChestOutcome(roll, stars, kind, 1, _choice(FOOD_BY_STARS[stars], randbelow))
    if kind == "pet_card":
        rarity = str(_weighted_choice(CARD_RARITY_WEIGHTS[stars], randbelow))
        species_id = _choice(_species_for_rarity(rarity), randbelow)
        # Large-looking packs are required by the owner-fixed 89,586-card
        # Common/Rare L16 curve. At the maximum 22 keys/week a chosen Common
        # reaches that curve in roughly two years rather than decades.
        quantity = CARD_AMOUNTS[stars]
        return ChestOutcome(roll, stars, kind, quantity, species_id, rarity)
    if kind == "joker":
        rarity = str(_weighted_choice(JOKER_RARITY_WEIGHTS[stars], randbelow))
        quantity = JOKER_AMOUNTS[stars]
        return ChestOutcome(roll, stars, kind, quantity, rarity, rarity)
    if kind == "vip_reward":
        if vip_cosmetic_ids:
            return ChestOutcome(roll, stars, "vip_cosmetic", 1, _choice(tuple(vip_cosmetic_ids), randbelow), "vip")
        return ChestOutcome(roll, stars, "vip_days", VIP_DAYS)
    raise RuntimeError("Unknown reward kind in chest catalogue.")


def public_reward_rows() -> list[dict[str, object]]:
    labels = {
        "mora": "Мора", "food": "Еда питомца", "pet_card": "Карты питомцев",
        "diamonds": "Алмазы", "joker": "Джокеры", "zarniki": "Зарники",
        "vip_reward": "4 дня VIP / VIP-образ для активных VIP",
    }
    rows = []
    for stars, weights in REWARD_WEIGHTS.items():
        outcomes = []
        for kind, percent in weights.items():
            item: dict[str, object] = {"kind": kind, "label": labels[kind], "conditional_percent": percent}
            if kind == "mora":
                item["amount"] = {"min": MORA_RANGES[stars][0], "max": MORA_RANGES[stars][1]}
            elif kind == "diamonds":
                item["amount"] = {"min": DIAMOND_RANGES[stars][0], "max": DIAMOND_RANGES[stars][1]}
            elif kind == "zarniki":
                item["amount"] = {"min": ZARNIKI_RANGES[stars][0], "max": ZARNIKI_RANGES[stars][1]}
            elif kind == "food":
                item["amount"] = {"fixed": 1}
                item["pool"] = [{"id": food_id, "name": FOODS[food_id]["name"],
                                  "restore": FOODS[food_id]["restore"]} for food_id in FOOD_BY_STARS[stars]]
            elif kind == "pet_card":
                item["amount"] = {"fixed": CARD_AMOUNTS[stars]}
                item["rarity_odds"] = CARD_RARITY_WEIGHTS[stars]
                item["pool"] = [{"id": species_id, **PET_SPECIES[species_id]} for species_id in PET_SPECIES]
            elif kind == "joker":
                item["amount"] = {"fixed": JOKER_AMOUNTS[stars]}
                item["rarity_odds"] = JOKER_RARITY_WEIGHTS[stars]
            elif kind == "vip_reward":
                item["amount"] = {"fixed": VIP_DAYS, "unit": "vip_days"}
                item["pool"] = [{"id": cosmetic_id, "name": VIP_COSMETIC_NAMES[cosmetic_id]}
                                for cosmetic_id in VIP_COSMETIC_POOL]
                item["fallback"] = "4 дня VIP, если VIP не активен или весь пул уже принадлежит игроку"
            outcomes.append(item)
        rows.append({"stars": stars, "star_percent": STAR_WEIGHTS[stars] / 100, "outcomes": outcomes})
    return rows
