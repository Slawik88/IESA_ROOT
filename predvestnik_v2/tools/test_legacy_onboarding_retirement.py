#!/usr/bin/env python3
"""Static contract: account registration cannot mint old starter rewards."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    onboarding = read("services/onboarding.py")
    users = read("infrastructure/repositories/users.py")
    middleware = read("bot/middlewares/db.py")
    reconstruction = read("services/reconstruction.py")

    for forbidden in (
        "STARTER_MORA",
        "STARTER_DIAMONDS",
        "STARTER_SPIN_TOKENS",
        "add_balance(",
        "add_item(",
        "grant_duplicate(",
        "random.choice",
    ):
        assert forbidden not in onboarding

    assert "VALUES (?, ?, TRUE, FALSE)" in users
    assert "onboarded = TRUE" in users
    assert "grant_starter_kit" not in middleware
    assert "_notify_starter_kit" not in middleware

    # The replacement onboarding records meaningful steps without wallet writes.
    assert '"step": "first_encounter_started"' in reconstruction
    assert '"step": "first_encounter_completed"' in reconstruction
    assert '"step": "first_reward_chosen"' in reconstruction

    print("legacy onboarding retirement contract: OK")


if __name__ == "__main__":
    main()
