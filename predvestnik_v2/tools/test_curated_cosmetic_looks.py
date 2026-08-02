"""Static contract checks for server-backed curated cosmetic looks."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import COSMETICS, COSMETIC_SLOTS, CURATED_LOOKS
from services.cosmetics import _curated_looks


expected_slots = set(COSMETIC_SLOTS)
expected_lineups = {"hanami", "moon_lotus", "ryujin_tide"}

assert len(CURATED_LOOKS) == 6, "expected two curated looks per Japanese lineup"
assert {look["lineup"] for look in CURATED_LOOKS.values()} == expected_lineups

for look_id, look in CURATED_LOOKS.items():
    items = look["items"]
    assert set(items) == expected_slots, f"{look_id}: look must fill all six slots"
    assert look["name"].strip() and look["mood"].strip(), f"{look_id}: editorial copy is required"
    for slot, cosmetic_id in items.items():
        cosmetic = COSMETICS.get(cosmetic_id)
        assert cosmetic, f"{look_id}: unknown cosmetic {cosmetic_id}"
        assert cosmetic["slot"] == slot, f"{look_id}: {cosmetic_id} belongs to {cosmetic['slot']}, not {slot}"
        assert cosmetic["lineup"] == look["lineup"], f"{look_id}: mixed lineup is not declared"

empty_catalog = _curated_looks(set())
assert all(look["owned_count"] == 0 and look["total_count"] == 6 for look in empty_catalog)
assert all(look["missing_price"] > 0 and not look["fully_owned"] for look in empty_catalog)

first = empty_catalog[0]
fully_owned_catalog = _curated_looks(set(first["items"].values()))
fully_owned = next(look for look in fully_owned_catalog if look["id"] == first["id"])
assert fully_owned["owned_count"] == 6
assert fully_owned["missing_price"] == 0
assert fully_owned["fully_owned"] is True

print("OK: curated looks are real six-slot server compositions with derived ownership and prices")
