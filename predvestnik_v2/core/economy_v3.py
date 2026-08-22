"""Pure owner-v3 economy policy.

The module intentionally has no database, FastAPI, Telegram or clock imports.
It can calculate a *shadow* decision, but it cannot credit a wallet.  Real
settlement stays disabled until server-time, anti-automation and migration gates
from ``GAME_ECONOMY_OWNER_V3.md`` are proven.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from types import MappingProxyType
from typing import Final, Literal, Mapping


POLICY_VERSION: Final = "owner-v3-provisional-1"
SETTLEMENT_MODE: Final = "shadow_only"
REAL_REWARDS_ENABLED: Final = False

ZARNIKI_TO_MORA_RATE: Final = 150
ZARNIKI_POSITIVE_SOURCE: Final = "stars_purchase"


@dataclass(frozen=True, slots=True)
class WalletPolicy:
    code: str
    label: str
    purpose: str
    acquisition: str
    lifecycle: str = "active"


WALLET_POLICIES: Final[tuple[WalletPolicy, ...]] = (
    WalletPolicy(
        "mora",
        "Мора",
        "оборотные игровые расходы",
        "валидная игра, торговля и необратимый обмен Зарников",
    ),
    WalletPolicy(
        "diamonds",
        "Алмазы",
        "редкие права выбора и исправления решения",
        "опубликованные испытания и сезонные рубежи",
    ),
    WalletPolicy(
        "zarniki",
        "Зарники",
        "косметика и сервис без боевой силы",
        "только подтверждённая покупка за Telegram Stars",
    ),
)
LEGACY_BALANCE_POLICIES: Final[tuple[WalletPolicy, ...]] = (
    WalletPolicy(
        "dark_mora",
        "Тёмная Мора",
        "исполнение уже существующих обязательств старого каталога",
        "новые начисления запрещены",
        lifecycle="legacy_spend_only",
    ),
)
ALLOWED_EXCHANGE_ROUTES: Final = (("zarniki", "mora"),)

UNIT_LEVEL_CAP: Final = 30
UNIT_BRANCH_LEVELS: Final = (5, 10, 15, 20, 25, 30)
SUPPORT_UNIT_XP_SHARE: Final = Decimal("0.60")
TAIL_UNIT_XP_SHARE: Final = Decimal("0.60")
MEANINGFUL_LOSS_MIN_ACCURACY: Final = Decimal("0.40")
SAME_SEED_LOSS_LIMIT: Final = 3

Outcome = Literal["won", "lost", "cancelled"]
RunKind = Literal["campaign", "practice"]


class EconomyV3PolicyError(ValueError):
    """The caller supplied a value outside the owner-v3 policy contract."""


@dataclass(frozen=True, slots=True)
class RewardTier:
    code: str
    first_ordinal: int
    last_ordinal: int | None
    win_mora: int
    meaningful_loss_mora: int
    unit_xp_share: Decimal


REWARD_TIERS: Final[tuple[RewardTier, ...]] = (
    RewardTier("full", 1, 35, 100, 35, Decimal("1.00")),
    RewardTier("sustained", 36, 105, 75, 26, Decimal("1.00")),
    RewardTier("long_session", 106, None, 50, 18, TAIL_UNIT_XP_SHARE),
)


@dataclass(frozen=True, slots=True)
class ShadowRewardDecision:
    policy_version: str
    settlement_mode: str
    eligible: bool
    reason: str
    outcome: Outcome
    accepted_result_ordinal: int | None
    tier: str | None
    mora: int
    lead_unit_xp: int
    support_unit_xp_each: int
    accuracy: Decimal | None
    provenance: str | None

    @property
    def can_settle(self) -> bool:
        """Remain false until the explicit production settlement gate changes."""
        return self.eligible and REAL_REWARDS_ENABLED


@dataclass(frozen=True, slots=True)
class UnitLevelProgress:
    level: int
    total_xp: int
    xp_in_level: int
    xp_to_next: int | None
    mastery_after_cap: int


@dataclass(frozen=True, slots=True)
class ZarnikiExchangeQuote:
    zarniki_spent: int
    mora_received: int
    rate: int
    provenance: str
    reversible: bool = False


def _integer(value: int, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomyV3PolicyError(f"{label} must be an integer.")
    if value < minimum:
        raise EconomyV3PolicyError(f"{label} must be >= {minimum}.")
    return value


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _tier_for_ordinal(ordinal: int) -> RewardTier:
    for tier in REWARD_TIERS:
        if ordinal >= tier.first_ordinal and (
            tier.last_ordinal is None or ordinal <= tier.last_ordinal
        ):
            return tier
    raise AssertionError(f"No reward tier for ordinal {ordinal}.")


def _zero_decision(
    *,
    outcome: Outcome,
    reason: str,
    accuracy: Decimal | None,
) -> ShadowRewardDecision:
    return ShadowRewardDecision(
        policy_version=POLICY_VERSION,
        settlement_mode=SETTLEMENT_MODE,
        eligible=False,
        reason=reason,
        outcome=outcome,
        accepted_result_ordinal=None,
        tier=None,
        mora=0,
        lead_unit_xp=0,
        support_unit_xp_each=0,
        accuracy=accuracy,
        provenance=None,
    )


def evaluate_reconstruction_reward_shadow(
    *,
    outcome: Outcome,
    run_kind: RunKind,
    accepted_results_last_7_days: int,
    server_terminal_confirmed: bool,
    first_branch_reached: bool,
    correct_signals: int,
    wrong_signals: int,
    missed_signals: int,
    aborted: bool = False,
    quarantined: bool = False,
    same_seed_eligible_losses_before: int = 0,
) -> ShadowRewardDecision:
    """Calculate a non-settleable Reconstruction reward decision.

    ``accepted_results_last_7_days`` is the count *before* this run.  Rejected,
    practice and cancelled runs do not consume an ordinal.  Accuracy follows the
    production UI contract: correct / (correct + wrong + missed), with no data
    represented by ``None`` rather than a fictional 100%.
    """
    if outcome not in ("won", "lost", "cancelled"):
        raise EconomyV3PolicyError("outcome must be won, lost or cancelled.")
    if run_kind not in ("campaign", "practice"):
        raise EconomyV3PolicyError("run_kind must be campaign or practice.")
    accepted_before = _integer(
        accepted_results_last_7_days,
        "accepted_results_last_7_days",
    )
    correct = _integer(correct_signals, "correct_signals")
    wrong = _integer(wrong_signals, "wrong_signals")
    missed = _integer(missed_signals, "missed_signals")
    repeated_losses = _integer(
        same_seed_eligible_losses_before,
        "same_seed_eligible_losses_before",
    )
    if not all(
        isinstance(value, bool)
        for value in (
            server_terminal_confirmed,
            first_branch_reached,
            aborted,
            quarantined,
        )
    ):
        raise EconomyV3PolicyError("Policy flags must be booleans.")

    resolved = correct + wrong + missed
    accuracy = Decimal(correct) / Decimal(resolved) if resolved else None

    if run_kind == "practice":
        return _zero_decision(outcome=outcome, reason="practice", accuracy=accuracy)
    if outcome == "cancelled" or aborted:
        return _zero_decision(outcome=outcome, reason="cancelled", accuracy=accuracy)
    if not server_terminal_confirmed:
        return _zero_decision(
            outcome=outcome,
            reason="terminal_not_confirmed",
            accuracy=accuracy,
        )
    if quarantined:
        return _zero_decision(outcome=outcome, reason="quarantined", accuracy=accuracy)
    if not first_branch_reached:
        return _zero_decision(
            outcome=outcome,
            reason="first_branch_not_reached",
            accuracy=accuracy,
        )
    if correct == 0:
        return _zero_decision(
            outcome=outcome,
            reason="no_correct_signals",
            accuracy=accuracy,
        )
    if outcome == "lost":
        if accuracy is None or accuracy < MEANINGFUL_LOSS_MIN_ACCURACY:
            return _zero_decision(
                outcome=outcome,
                reason="loss_below_accuracy_floor",
                accuracy=accuracy,
            )
        if repeated_losses >= SAME_SEED_LOSS_LIMIT:
            return _zero_decision(
                outcome=outcome,
                reason="same_seed_loss_limit",
                accuracy=accuracy,
            )

    ordinal = accepted_before + 1
    tier = _tier_for_ordinal(ordinal)
    base_xp = 100 if outcome == "won" else 45
    lead_xp = _round_half_up(Decimal(base_xp) * tier.unit_xp_share)
    support_xp = _round_half_up(Decimal(lead_xp) * SUPPORT_UNIT_XP_SHARE)
    mora = tier.win_mora if outcome == "won" else tier.meaningful_loss_mora
    return ShadowRewardDecision(
        policy_version=POLICY_VERSION,
        settlement_mode=SETTLEMENT_MODE,
        eligible=True,
        reason="eligible_shadow",
        outcome=outcome,
        accepted_result_ordinal=ordinal,
        tier=tier.code,
        mora=mora,
        lead_unit_xp=lead_xp,
        support_unit_xp_each=support_xp,
        accuracy=accuracy,
        provenance="earned_reconstruction",
    )


def unit_xp_to_next(level: int) -> int:
    """XP needed from ``level`` to ``level + 1`` under owner-v3."""
    current = _integer(level, "level", minimum=1)
    if current >= UNIT_LEVEL_CAP:
        raise EconomyV3PolicyError("Maximum level has no next-level XP cost.")
    index = current - 1
    raw = Decimal(220 + 35 * index) + Decimal(12) * Decimal(str(index**1.4))
    return _round_half_up(raw)


UNIT_XP_REQUIREMENTS: Final[tuple[int, ...]] = tuple(
    unit_xp_to_next(level) for level in range(1, UNIT_LEVEL_CAP)
)
UNIT_LEVEL_CAP_XP: Final = sum(UNIT_XP_REQUIREMENTS)


def unit_level_progress(total_xp: int) -> UnitLevelProgress:
    """Resolve a non-negative lifetime XP total into level and local progress."""
    total = _integer(total_xp, "total_xp")
    remaining = total
    for level, requirement in enumerate(UNIT_XP_REQUIREMENTS, start=1):
        if remaining < requirement:
            return UnitLevelProgress(
                level=level,
                total_xp=total,
                xp_in_level=remaining,
                xp_to_next=requirement,
                mastery_after_cap=0,
            )
        remaining -= requirement
    return UnitLevelProgress(
        level=UNIT_LEVEL_CAP,
        total_xp=total,
        xp_in_level=0,
        xp_to_next=None,
        mastery_after_cap=remaining,
    )


def quote_zarniki_to_mora(zarniki: int) -> ZarnikiExchangeQuote:
    """Return the irreversible owner-v3 quote without mutating a wallet."""
    amount = _integer(zarniki, "zarniki", minimum=1)
    return ZarnikiExchangeQuote(
        zarniki_spent=amount,
        mora_received=amount * ZARNIKI_TO_MORA_RATE,
        rate=ZARNIKI_TO_MORA_RATE,
        provenance="paid_exchange",
    )


def validate_positive_zarniki_source(source: str) -> str:
    """Allow positive Zarniki only from a confirmed Telegram Stars purchase."""
    normalized = str(source or "").strip().lower()
    if normalized != ZARNIKI_POSITIVE_SOURCE:
        raise EconomyV3PolicyError(
            "Positive Zarniki may only originate from a confirmed stars_purchase."
        )
    return normalized


def validate_exchange_route(source: str, target: str) -> tuple[str, str]:
    """Fail closed for every currency conversion not present in owner-v3."""
    route = (str(source or "").strip().lower(), str(target or "").strip().lower())
    if route not in ALLOWED_EXCHANGE_ROUTES:
        raise EconomyV3PolicyError(
            "Owner-v3 permits only the irreversible Zarniki-to-Mora exchange."
        )
    return route


def public_policy_manifest() -> dict[str, object]:
    """Return a JSON-safe manifest; exposing it never enables settlement."""
    return {
        "policy_version": POLICY_VERSION,
        "settlement_mode": SETTLEMENT_MODE,
        "real_rewards_enabled": REAL_REWARDS_ENABLED,
        "reward_tiers": [
            {
                "code": tier.code,
                "first_ordinal": tier.first_ordinal,
                "last_ordinal": tier.last_ordinal,
                "win_mora": tier.win_mora,
                "meaningful_loss_mora": tier.meaningful_loss_mora,
                "unit_xp_percent": int(tier.unit_xp_share * 100),
            }
            for tier in REWARD_TIERS
        ],
        "unit_level_cap": UNIT_LEVEL_CAP,
        "unit_level_cap_xp": UNIT_LEVEL_CAP_XP,
        "unit_branch_levels": list(UNIT_BRANCH_LEVELS),
        "zarniki_to_mora_rate": ZARNIKI_TO_MORA_RATE,
        "zarniki_positive_source": ZARNIKI_POSITIVE_SOURCE,
        "wallets": [
            {
                "code": wallet.code,
                "label": wallet.label,
                "purpose": wallet.purpose,
                "acquisition": wallet.acquisition,
                "lifecycle": wallet.lifecycle,
            }
            for wallet in WALLET_POLICIES
        ],
        "legacy_balances": [
            {
                "code": wallet.code,
                "label": wallet.label,
                "purpose": wallet.purpose,
                "acquisition": wallet.acquisition,
                "lifecycle": wallet.lifecycle,
            }
            for wallet in LEGACY_BALANCE_POLICIES
        ],
        "allowed_exchange_routes": [list(route) for route in ALLOWED_EXCHANGE_ROUTES],
    }


ECONOMY_V3_PUBLIC_CONTRACT: Final[Mapping[str, object]] = MappingProxyType({
    "policy_version": POLICY_VERSION,
    "settlement_mode": SETTLEMENT_MODE,
    "real_rewards_enabled": REAL_REWARDS_ENABLED,
    "reward_tiers": REWARD_TIERS,
    "unit_level_cap": UNIT_LEVEL_CAP,
    "unit_level_cap_xp": UNIT_LEVEL_CAP_XP,
    "unit_branch_levels": UNIT_BRANCH_LEVELS,
    "zarniki_to_mora_rate": ZARNIKI_TO_MORA_RATE,
    "zarniki_positive_source": ZARNIKI_POSITIVE_SOURCE,
    "wallets": WALLET_POLICIES,
    "legacy_balances": LEGACY_BALANCE_POLICIES,
    "allowed_exchange_routes": ALLOWED_EXCHANGE_ROUTES,
})


if UNIT_LEVEL_CAP_XP != 36_096:  # fail closed if Python/JS rounding ever diverges
    raise RuntimeError(f"Owner-v3 unit curve drifted to {UNIT_LEVEL_CAP_XP} XP.")
