"""Контракт глобальной балансировки цен косметики по визуальному весу слота."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import COSMETICS, COSMETIC_SLOT_PRICES, LINEUPS, lineup_items
from services.cosmetics import lineup_buy_quote


EXPECTED_SLOT_ORDER = (
    "title", "avatar_halo", "avatar_frame", "name_glow", "profile_bg", "card_fx",
)
EXPECTED_LINEUP_TOTALS = {
    "forest": 3400,
    "threshold": 5980,
    "frost": 5360,
    "inferno": 7700,
    "hanami": 10130,
    "celestial": 10700,
    "void": 12200,
    "artifact": 16350,
    "moon_lotus": 20250,
    "ryujin_tide": 20250,
}

assert len(COSMETICS) == 134
assert set(COSMETIC_SLOT_PRICES) == {250, 440, 630, 820, 1000, 1500}

for base, prices in COSMETIC_SLOT_PRICES.items():
    ordered = [prices[slot] for slot in EXPECTED_SLOT_ORDER]
    assert ordered == sorted(ordered), f"{base}: нарушена иерархия слотов {ordered}"
    assert len(set(ordered)) == len(ordered), f"{base}: цены слотов не должны совпадать"

assert COSMETIC_SLOT_PRICES[1500]["title"] == 800
assert COSMETIC_SLOT_PRICES[1500]["profile_bg"] == 1500

for lineup_id, meta in LINEUPS.items():
    base = int(meta["price"][0]["zarniki"])
    matrix = COSMETIC_SLOT_PRICES[base]
    items = lineup_items(lineup_id)
    assert items, f"{lineup_id}: пустая линейка"
    for cosmetic_id, item in items.items():
        actual = int(item["price"][0]["zarniki"])
        assert actual == matrix[item["slot"]], (
            f"{cosmetic_id}: {actual} != {matrix[item['slot']]} для {item['slot']}"
        )
    quote = lineup_buy_quote(lineup_id, set())
    assert quote is not None
    assert quote["total"] == EXPECTED_LINEUP_TOTALS[lineup_id]
    assert quote["price_min"] == min(matrix.values())
    assert quote["price_max"] == max(matrix.values())

old_uniform_total = sum(
    int(LINEUPS[item["lineup"]]["price"][0]["zarniki"])
    for item in COSMETICS.values()
)
new_total = sum(int(item["price"][0]["zarniki"]) for item in COSMETICS.values())
delta = new_total / old_uniform_total - 1
assert -0.06 <= delta <= 0, f"каталог должен стать не дороже и не дешевле >6%: {delta:.2%}"

print(
    "OK: 134 предмета следуют единой иерархии title < halo < frame < name < "
    f"background < card-fx; полный каталог {old_uniform_total}→{new_total}✨ ({delta:.1%})"
)
