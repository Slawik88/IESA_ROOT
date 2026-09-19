"""Approved pet progression rules, isolated from retired game systems.

The release rules must never influence Rune Rhythm, Minesweeper or Mafia.
They only describe long-term pet growth and future trek/expedition decisions.
Persistence and rewards deliberately live outside this pure module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Final


POLICY_VERSION: Final = "pets-v1-2026-09-13"
MAX_LEVEL: Final = 16
ENDURANCE_MIN: Final = 0
ENDURANCE_MAX: Final = 100
ENDURANCE_DRAIN_PER_DAY: Final = 10
# A five-point switch cost is deliberately meaningful but lower than a day's
# natural drain.  The server applies it atomically with an active-slot change.
ACTIVE_SLOT_SWAP_COST: Final = 5
TREK_AND_EXPEDITION_HOURS: Final = (3, 6, 9)
ACTIVITY_ENDURANCE_COST: Final = {3: 25, 6: 40, 9: 55}
PET_ACTIVITY_KINDS: Final = ("trek", "expedition")
EXPEDITION_DECISIONS: Final = ("careful", "steady", "bold")


class PetPolicyError(ValueError):
    """Raised before a pet writer receives an invalid state transition."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def endurance_after_elapsed(
    endurance: int, *, last_updated_at: datetime, now: datetime,
) -> tuple[int, int]:
    """Return (remaining_endurance, whole_points_drained).

    We debit only whole points.  A clock moving backwards or a repeated read in
    the same partial interval never restores or spends endurance.
    """
    if not ENDURANCE_MIN <= int(endurance) <= ENDURANCE_MAX:
        raise PetPolicyError("Выносливость питомца вне диапазона 0–100.")
    seconds = max(0.0, (_utc(now) - _utc(last_updated_at)).total_seconds())
    spent = int(seconds * ENDURANCE_DRAIN_PER_DAY // 86_400)
    return max(ENDURANCE_MIN, int(endurance) - spent), min(int(endurance), spent)


def apply_active_slot_swap(*, current_pet_id: int | None, next_pet_id: int, endurance: int) -> tuple[int, int]:
    """Validate an active-slot selection and return (next_id, endurance).

    Selecting the already active pet is a no-op.  Moving a different pet into
    the active slot consumes endurance, so temporary equip/use/unequip cycles
    cannot be free.  There is no client supplied price.
    """
    if int(next_pet_id) <= 0:
        raise PetPolicyError("Некорректный питомец.")
    if current_pet_id is not None and int(current_pet_id) == int(next_pet_id):
        return int(next_pet_id), int(endurance)
    if not ENDURANCE_MIN <= int(endurance) <= ENDURANCE_MAX:
        raise PetPolicyError("Выносливость питомца вне диапазона 0–100.")
    if int(endurance) < ACTIVE_SLOT_SWAP_COST:
        raise PetPolicyError("Недостаточно выносливости для смены активного питомца.")
    return int(next_pet_id), int(endurance) - ACTIVE_SLOT_SWAP_COST


def level_effects(level: int) -> dict:
    """Visible, expedition-only progress.  No combat/game stat is returned."""
    if not 1 <= int(level) <= MAX_LEVEL:
        raise PetPolicyError("Уровень питомца должен быть от 1 до 16.")
    level = int(level)
    stage = (
        "Начальный облик" if level <= 3 else
        "Развитый облик" if level <= 7 else
        "Опытный облик" if level <= 11 else
        "Выдающийся облик" if level <= 15 else
        "Максимальный облик"
    )
    # The effects are intentionally local: they affect only the future route
    # resolution and information layer of an expedition, never a game score or
    # paid certainty.  Caps make the full collection valuable without turning
    # level 16 into a guaranteed result.
    return {
        "level": level,
        "visual_stage": stage,
        "expedition_route_bonus_percent": min(15, level - 1),
        "expedition_hint_charges": 1 if level >= 4 else 0,
        "expedition_risk_guard_percent": 5 if level >= 8 else 0,
        "expedition_extra_option": level >= 12,
        "max_level_effect": level == MAX_LEVEL,
    }


def allowed_duration(hours: int) -> bool:
    return int(hours) in TREK_AND_EXPEDITION_HOURS


def validate_activity(kind: str, hours: int) -> tuple[str, int]:
    normalized = str(kind or "").strip().lower()
    if normalized not in PET_ACTIVITY_KINDS:
        raise PetPolicyError("Доступны только поход или экспедиция.")
    if not allowed_duration(hours):
        raise PetPolicyError("Длительность: только 3, 6 или 9 часов.")
    return normalized, int(hours)


def spend_activity_endurance(*, endurance: int, hours: int) -> tuple[int, int]:
    """Return ``(remaining, cost)`` for a server-authoritative activity start."""
    if not allowed_duration(hours):
        raise PetPolicyError("Длительность: только 3, 6 или 9 часов.")
    current = int(endurance)
    if not ENDURANCE_MIN <= current <= ENDURANCE_MAX:
        raise PetPolicyError("Выносливость питомца вне диапазона 0–100.")
    cost = ACTIVITY_ENDURANCE_COST[int(hours)]
    if current < cost:
        raise PetPolicyError(f"Для приключения на {int(hours)} ч нужно {cost} выносливости.")
    return current - cost, cost


def validate_expedition_decision(value: str) -> str:
    choice = str(value or "").strip().lower()
    if choice not in EXPEDITION_DECISIONS:
        raise PetPolicyError("Выбери осторожный, ровный или рискованный маршрут.")
    return choice
