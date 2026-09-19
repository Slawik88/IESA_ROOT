"""Pure policy proof for the mixed release chest catalogue."""
from __future__ import annotations

from collections import Counter
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import core.chests_v1 as chest_rules

from core.chests_v1 import (
    CARD_RARITY_WEIGHTS, CATALOG_VERSION, FOODS, FOOD_BY_STARS,
    JOKER_RARITIES, JOKER_RARITY_WEIGHTS, PAID_KEY_DAILY_LIMIT,
    PAID_KEY_PRICE_ZARNIKI, PET_SPECIES, REWARD_WEIGHTS, STAR_WEIGHTS,
    VIP_COSMETIC_POOL, ChestPolicyError, KeyGrant, catalog_digest, canonical_snapshot_fingerprint,
    public_reward_rows, roll_outcome, stars_for_roll, validate_key_grant,
)


snapshot = {"reward_id": "daily:2026-09-12", "period": "daily"}
valid = validate_key_grant(KeyGrant("quest_daily_set_complete", "daily:2026-09-12", 1, snapshot))
assert valid.amount == 1
purchase = validate_key_grant(KeyGrant("zarniki_purchase", "purchase-1", 1, {"price": 10}))
assert purchase.amount == 1
for bad in (
    KeyGrant("client", "x", 1, snapshot), KeyGrant("quest_daily_set_complete", "x", 2, snapshot),
    KeyGrant("quest_daily_set_complete", "x", True, snapshot),
    KeyGrant("quest_daily_set_complete", "", 1, snapshot),
    KeyGrant("quest_daily_set_complete", "x", 1, {"bad": float("nan")}),
):
    try:
        validate_key_grant(bad)
    except ChestPolicyError:
        pass
    else:
        raise AssertionError(f"invalid key grant must fail closed: {bad!r}")

assert sum(STAR_WEIGHTS.values()) == 10_000
counts = Counter(stars_for_roll(roll) for roll in range(10_000))
assert dict(counts) == STAR_WEIGHTS and counts[10] == 30
assert all(sum(row.values()) == 100 for row in REWARD_WEIGHTS.values())
assert all(sum(row.values()) == 100 for row in CARD_RARITY_WEIGHTS.values())
assert all(sum(row.values()) == 100 for row in JOKER_RARITY_WEIGHTS.values())
assert len(PET_SPECIES) == 12
assert Counter(row["rarity"] for row in PET_SPECIES.values()) == {
    "common": 5, "uncommon": 3, "rare": 2, "epic": 1, "legendary": 1,
}
assert set(FOOD_BY_STARS) == {1, 2, 3, 4}
assert all(food_id in FOODS for ids in FOOD_BY_STARS.values() for food_id in ids)
assert set(JOKER_RARITIES) == {"common", "uncommon", "rare", "epic", "legendary"}
assert PAID_KEY_PRICE_ZARNIKI == 10 and PAID_KEY_DAILY_LIMIT == 2
assert len(catalog_digest()) == 64 and catalog_digest() == catalog_digest()
assert canonical_snapshot_fingerprint({"a": 1}) != canonical_snapshot_fingerprint({"a": 2})
full_pool_digest = catalog_digest()
original_vip_pool = chest_rules.VIP_COSMETIC_POOL
try:
    chest_rules.VIP_COSMETIC_POOL = original_vip_pool[:1]
    assert catalog_digest() != full_pool_digest, "the actual ordered VIP outcome pool must be digest-pinned"
finally:
    chest_rules.VIP_COSMETIC_POOL = original_vip_pool
public_rows = public_reward_rows()
assert len(public_rows) == 10
assert all(row["star_percent"] == STAR_WEIGHTS[row["stars"]] / 100 for row in public_rows)
assert all(sum(item["conditional_percent"] for item in row["outcomes"]) == 100 for row in public_rows)
assert any(item.get("rarity_odds") for row in public_rows for item in row["outcomes"])
vip_public = next(item for row in public_rows for item in row["outcomes"] if item["kind"] == "vip_reward")
assert {item["id"] for item in vip_public["pool"]} == set(VIP_COSMETIC_POOL)
assert vip_public["fallback"]

# Seeded catalogue walk proves that every stored reference resolves and that no
# compensation reward exists. This intentionally tests policy, not statistical luck.
rng = random.Random(917_2026)
seen = Counter()
for _ in range(250_000):
    outcome = roll_outcome(rng.randrange, vip_cosmetic_ids=("cos_card_fx_embers",))
    seen[outcome.reward_kind] += 1
    assert outcome.amount > 0
    assert "compens" not in outcome.reward_kind and "echo" not in outcome.reward_kind
    if outcome.reward_kind == "food":
        assert outcome.reward_ref in FOODS and outcome.stars <= 4
    elif outcome.reward_kind == "pet_card":
        assert outcome.reward_ref in PET_SPECIES
        assert PET_SPECIES[outcome.reward_ref]["rarity"] == outcome.rarity
    elif outcome.reward_kind == "joker":
        assert outcome.reward_ref in JOKER_RARITIES
    elif outcome.reward_kind == "vip_cosmetic":
        assert outcome.stars == 10 and outcome.reward_ref == "cos_card_fx_embers"
assert {"mora", "food", "pet_card", "diamonds", "joker", "zarniki", "vip_cosmetic"} <= set(seen)
assert CATALOG_VERSION

print("OK: mixed chest catalogue, exact odds, 12 species, references and no compensation")
