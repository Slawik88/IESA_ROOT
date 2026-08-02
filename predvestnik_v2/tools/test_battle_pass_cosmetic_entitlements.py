#!/usr/bin/env python3
"""Regression checks: BP cosmetics must become fitting-room entitlements."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.battle_pass_rewards import (  # noqa: E402
    grant_reward_items,
    normalize_configured_reward_items,
    reward_cosmetics_error,
    reward_short_text,
)


class RecordingDB:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, args=()):
        self.calls.append((" ".join(sql.split()), args))


async def check_grants() -> None:
    db = RecordingDB()
    await grant_reward_items(
        db, 42,
        (("cos_avatar_halo_celestial", 1), ("spin_token", 2)),
    )
    assert len(db.calls) == 2
    assert "INSERT INTO user_cosmetics" in db.calls[0][0]
    assert db.calls[0][1] == (42, "cos_avatar_halo_celestial")
    assert "INSERT INTO inventory" in db.calls[1][0]
    assert db.calls[1][1] == (42, "spin_token", 2, 2)


def main() -> None:
    valid = (("cos_avatar_halo_celestial", 1),)
    missing = (("cos_removed_reward", 1),)
    stacked = (("cos_avatar_halo_celestial", 2),)
    assert reward_cosmetics_error(valid) is None
    assert "не определена" in reward_cosmetics_error(missing)
    assert "одно право владения" in reward_cosmetics_error(stacked)
    assert "Некорректное описание" in reward_cosmetics_error((("broken",),))
    assert "одно право владения" in reward_cosmetics_error((("cos_avatar_halo_celestial", "many"),))
    assert "Небесный нимб" in reward_short_text({"items": valid})
    assert normalize_configured_reward_items([["spin_token", "2"], [valid[0][0], 1]]) == [
        ["spin_token", 2], [valid[0][0], 1]
    ]
    for invalid in (
        [["cos_avatar_halo_celestial", 2]],
        [["cos_removed_reward", 1]],
        [["spin_token", 0]],
        [["spin_token"]],
    ):
        try:
            normalize_configured_reward_items(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid reward items accepted: {invalid}")
    asyncio.run(check_grants())
    print("ALL BATTLE PASS COSMETIC ENTITLEMENT CHECKS PASSED")


if __name__ == "__main__":
    main()
