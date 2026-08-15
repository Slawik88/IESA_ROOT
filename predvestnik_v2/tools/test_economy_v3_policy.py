#!/usr/bin/env python3
"""Deterministic contract tests for the owner-v3 shadow economy policy."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.economy_v3 import (  # noqa: E402
    ECONOMY_V3_PUBLIC_CONTRACT,
    EconomyV3PolicyError,
    REAL_REWARDS_ENABLED,
    REWARD_TIERS,
    SETTLEMENT_MODE,
    UNIT_BRANCH_LEVELS,
    UNIT_LEVEL_CAP_XP,
    UNIT_XP_REQUIREMENTS,
    evaluate_reconstruction_reward_shadow,
    quote_zarniki_to_mora,
    public_policy_manifest,
    unit_level_progress,
    unit_xp_to_next,
    validate_positive_zarniki_source,
)


def decision(**overrides):
    payload = {
        "outcome": "won",
        "run_kind": "campaign",
        "accepted_results_last_7_days": 0,
        "server_terminal_confirmed": True,
        "first_branch_reached": True,
        "correct_signals": 12,
        "wrong_signals": 2,
        "missed_signals": 1,
        "aborted": False,
        "quarantined": False,
        "same_seed_eligible_losses_before": 0,
    }
    payload.update(overrides)
    return evaluate_reconstruction_reward_shadow(**payload)


def assert_reward_boundaries():
    expected = {
        0: (1, "full", 100, 100, 60),
        34: (35, "full", 100, 100, 60),
        35: (36, "sustained", 75, 100, 60),
        104: (105, "sustained", 75, 100, 60),
        105: (106, "long_session", 50, 60, 36),
        10_000: (10_001, "long_session", 50, 60, 36),
    }
    for accepted_before, values in expected.items():
        result = decision(accepted_results_last_7_days=accepted_before)
        assert (
            result.accepted_result_ordinal,
            result.tier,
            result.mora,
            result.lead_unit_xp,
            result.support_unit_xp_each,
        ) == values
        assert result.eligible and not result.can_settle

    losses = {
        0: ("full", 35, 45, 27),
        35: ("sustained", 26, 45, 27),
        105: ("long_session", 18, 27, 16),
    }
    for accepted_before, values in losses.items():
        result = decision(
            outcome="lost",
            accepted_results_last_7_days=accepted_before,
            correct_signals=4,
            wrong_signals=3,
            missed_signals=3,
        )
        assert (
            result.tier,
            result.mora,
            result.lead_unit_xp,
            result.support_unit_xp_each,
        ) == values
        assert result.accuracy == Decimal("0.4")


def assert_fail_closed_rules():
    rejected = [
        (decision(run_kind="practice"), "practice"),
        (decision(outcome="cancelled"), "cancelled"),
        (decision(aborted=True), "cancelled"),
        (decision(server_terminal_confirmed=False), "terminal_not_confirmed"),
        (decision(quarantined=True), "quarantined"),
        (decision(first_branch_reached=False), "first_branch_not_reached"),
        (decision(correct_signals=0, wrong_signals=0, missed_signals=0), "no_correct_signals"),
        (
            decision(outcome="lost", correct_signals=3, wrong_signals=4, missed_signals=3),
            "loss_below_accuracy_floor",
        ),
        (
            decision(outcome="lost", same_seed_eligible_losses_before=3),
            "same_seed_loss_limit",
        ),
    ]
    for result, reason in rejected:
        assert not result.eligible and result.reason == reason
        assert result.mora == result.lead_unit_xp == result.support_unit_xp_each == 0
        assert result.accepted_result_ordinal is None and not result.can_settle

    for bad in (
        {"accepted_results_last_7_days": -1},
        {"correct_signals": True},
        {"wrong_signals": -1},
        {"same_seed_eligible_losses_before": -1},
        {"server_terminal_confirmed": 1},
        {"outcome": "draw"},
        {"run_kind": "ranked"},
    ):
        try:
            decision(**bad)
        except EconomyV3PolicyError:
            pass
        else:
            raise AssertionError(f"Invalid shadow input accepted: {bad}")


def assert_unit_curve():
    assert len(UNIT_XP_REQUIREMENTS) == 29
    assert UNIT_LEVEL_CAP_XP == 36_096
    assert UNIT_XP_REQUIREMENTS[:5] == (220, 267, 322, 381, 444)
    assert all(left < right for left, right in zip(UNIT_XP_REQUIREMENTS, UNIT_XP_REQUIREMENTS[1:]))
    assert UNIT_BRANCH_LEVELS == (5, 10, 15, 20, 25, 30)
    assert unit_xp_to_next(1) == 220
    assert unit_level_progress(0).level == 1
    boundary = unit_level_progress(220)
    assert (boundary.level, boundary.xp_in_level, boundary.xp_to_next) == (2, 0, 267)
    capped = unit_level_progress(UNIT_LEVEL_CAP_XP)
    assert (capped.level, capped.xp_to_next, capped.mastery_after_cap) == (30, None, 0)
    prestige = unit_level_progress(UNIT_LEVEL_CAP_XP + 777)
    assert (prestige.level, prestige.mastery_after_cap) == (30, 777)


def assert_zarniki_contract():
    quote = quote_zarniki_to_mora(7)
    assert (quote.zarniki_spent, quote.mora_received, quote.rate) == (7, 1050, 150)
    assert quote.provenance == "paid_exchange" and not quote.reversible
    assert validate_positive_zarniki_source("stars_purchase") == "stars_purchase"
    for invalid in ("promo", "gameplay_reward", "refund", "", None):
        try:
            validate_positive_zarniki_source(invalid)
        except EconomyV3PolicyError:
            pass
        else:
            raise AssertionError(f"Invalid positive Zarniki source accepted: {invalid!r}")
    for invalid_amount in (0, -1, True, 1.5):
        try:
            quote_zarniki_to_mora(invalid_amount)
        except EconomyV3PolicyError:
            pass
        else:
            raise AssertionError(f"Invalid Zarniki exchange accepted: {invalid_amount!r}")


def assert_public_gate():
    assert SETTLEMENT_MODE == "shadow_only"
    assert REAL_REWARDS_ENABLED is False
    assert ECONOMY_V3_PUBLIC_CONTRACT["real_rewards_enabled"] is False
    assert ECONOMY_V3_PUBLIC_CONTRACT["zarniki_positive_source"] == "stars_purchase"
    manifest = public_policy_manifest()
    assert manifest["settlement_mode"] == "shadow_only"
    assert manifest["real_rewards_enabled"] is False
    assert manifest["unit_level_cap_xp"] == 36_096
    assert manifest["zarniki_positive_source"] == "stars_purchase"
    assert [tier["unit_xp_percent"] for tier in manifest["reward_tiers"]] == [100, 100, 60]
    assert [(tier.first_ordinal, tier.last_ordinal) for tier in REWARD_TIERS] == [
        (1, 35), (36, 105), (106, None),
    ]


assert_reward_boundaries()
assert_fail_closed_rules()
assert_unit_curve()
assert_zarniki_contract()
assert_public_gate()
print("economy_v3_policy: rewards+levels+zarniki shadow contract  OK")
