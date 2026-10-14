"""Pure contract tests for pet level-ups paid with currencies (ECO-04, P7)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.pet_levels_v1 import (
    CARDS_PER_STEP, CARDS_TOTAL_COMMON, ESSENCE_ON_ENTERING, MORA_PER_STEP, level_up_cost, total_cost,
)
from core.pets_v1 import MAX_LEVEL, PetPolicyError


def must_fail(callable_):
    try:
        callable_()
    except PetPolicyError:
        return
    raise AssertionError("Expected PetPolicyError")


def main() -> None:
    assert len(CARDS_PER_STEP) == MAX_LEVEL - 1 == len(MORA_PER_STEP)
    assert sum(CARDS_PER_STEP) == CARDS_TOTAL_COMMON == 89_586          # owner-fixed number
    assert sum(MORA_PER_STEP) == 3_000
    assert list(CARDS_PER_STEP) == sorted(CARDS_PER_STEP)                # every next step costs more
    assert ESSENCE_ON_ENTERING == {5: 20, 10: 60, 15: 150}
    first = level_up_cost(1, "common")
    assert (first.cards, first.mora, first.essence) == (70, 6, 0) and first.level_after == 2
    entering_five = level_up_cost(4, "common")
    assert entering_five.essence == 20 and entering_five.level_after == 5
    assert level_up_cost(14, "common").essence == 150 and level_up_cost(15, "common").essence == 0
    for rarity in ("common", "uncommon", "rare"):
        assert total_cost(rarity).cards == CARDS_TOTAL_COMMON           # owner fixed Common/Rare, same for Uncommon
    assert total_cost("common").essence == 230
    assert total_cost("legendary").cards < total_cost("epic").cards < total_cost("common").cards
    assert total_cost("legendary").mora > total_cost("common").mora
    must_fail(lambda: level_up_cost(MAX_LEVEL, "common"))
    must_fail(lambda: level_up_cost(0, "common"))
    must_fail(lambda: level_up_cost(True, "common"))
    must_fail(lambda: level_up_cost(3, "mythic"))
    print("OK: pet level-up costs (89586 cards, 3000 Mora, 230 Essence on stages) and bounds")


if __name__ == "__main__":
    main()
