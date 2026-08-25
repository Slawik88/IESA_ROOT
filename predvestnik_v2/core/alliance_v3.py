"""Pure policy for the shared Alliance cooperative layer.

The first release is deliberately shadow-only.  It proves participation,
caps and unlock gates without touching Mora, Diamonds, Zarniki or legacy clan
ownership.  Persistent adapters may call these functions, but cannot redefine
their economic meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final


POLICY_VERSION: Final = "alliance-v3-provisional-1"
SETTLEMENT_MODE: Final = "shadow_only"
REAL_REWARDS_ENABLED: Final = False
DAILY_SIGNAL_CAP: Final = 4
WEEKLY_SIGNAL_CAP: Final = 12
ACTIVE_MEMBER_DAYS_PER_WEEK: Final = 2
ACTIVE_MEMBER_WEEKS: Final = 4
PROJECT_MIN_ACTIVE_CLANS: Final = 3
COMPETITION_MIN_ACTIVE_CLANS: Final = 8
COMPETITION_MIN_ELIGIBLE_PER_CLAN: Final = 5
STAGE_PCTS: Final = (25, 60, 100)


@dataclass(frozen=True)
class ContributionQuote:
    requested: int
    accepted: int
    daily_after: int
    weekly_after: int
    reason: str
    settled: bool = False


def cycle_target(active_players_28d: int) -> int:
    """Reachable weekly target; sized to participation, not registered users."""
    active = max(0, int(active_players_28d))
    return min(1200, max(18, ceil(active * 6 * 0.55)))


def quote_contribution(
    *, outcome: str, meaningful: bool, practice: bool, quarantined: bool,
    daily_signals: int, weekly_signals: int,
) -> ContributionQuote:
    """Quote one terminal result without issuing currency or mutable rewards."""
    daily = max(0, int(daily_signals))
    weekly = max(0, int(weekly_signals))
    requested = 2 if outcome == "won" else 1 if outcome == "lost" and meaningful else 0
    if practice:
        return ContributionQuote(requested, 0, daily, weekly, "practice")
    if quarantined:
        return ContributionQuote(requested, 0, daily, weekly, "quarantined")
    if requested <= 0:
        return ContributionQuote(0, 0, daily, weekly, "not_meaningful")
    room = min(max(0, DAILY_SIGNAL_CAP - daily), max(0, WEEKLY_SIGNAL_CAP - weekly))
    accepted = min(requested, room)
    reason = "accepted" if accepted == requested else "cap_partial" if accepted else "cap_reached"
    return ContributionQuote(requested, accepted, daily + accepted, weekly + accepted, reason)


def stage_progress(total_signals: int, target: int) -> dict:
    safe_target = max(1, int(target))
    total = max(0, int(total_signals))
    pct = min(100, total / safe_target * 100)
    reached = [stage for stage in STAGE_PCTS if pct >= stage]
    next_stage = next((stage for stage in STAGE_PCTS if pct < stage), None)
    return {
        "signals": total, "target": safe_target, "percent": round(pct, 1),
        "stages_reached": reached, "next_stage_pct": next_stage,
        "complete": pct >= 100,
    }


def clan_feature_gates(active_clans: int, eligible_members_by_clan: list[int]) -> dict:
    clans = max(0, int(active_clans))
    competition_ready = sum(
        max(0, int(count)) >= COMPETITION_MIN_ELIGIBLE_PER_CLAN
        for count in eligible_members_by_clan
    )
    return {
        "projects": clans >= PROJECT_MIN_ACTIVE_CLANS,
        "competition": (
            clans >= COMPETITION_MIN_ACTIVE_CLANS
            and competition_ready >= COMPETITION_MIN_ACTIVE_CLANS
        ),
        "active_clans": clans,
        "competition_ready_clans": competition_ready,
    }


def public_manifest() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "mode": SETTLEMENT_MODE,
        "real_rewards_enabled": REAL_REWARDS_ENABLED,
        "caps": {"daily_signals": DAILY_SIGNAL_CAP, "weekly_signals": WEEKLY_SIGNAL_CAP},
        "active_member": {
            "meaningful_days_per_week": ACTIVE_MEMBER_DAYS_PER_WEEK,
            "consecutive_weeks": ACTIVE_MEMBER_WEEKS,
        },
        "clan_gates": {
            "projects": PROJECT_MIN_ACTIVE_CLANS,
            "competition": PROJECT_MIN_ACTIVE_CLANS + 5,
            "eligible_members_per_competing_clan": COMPETITION_MIN_ELIGIBLE_PER_CLAN,
        },
        "stages": list(STAGE_PCTS),
        "economic_reward": None,
        "legacy_clans_preserved": True,
    }
