"""Immutable, server-owned difficulty plans for Reconstruction encounters.

Difficulty is a property of one run, never a mutable global balance setting.
The complete generated wave plan is persisted with the run, so a later content
change cannot alter an unfinished attempt or its reward calculation.
"""
from __future__ import annotations

import copy
import math
from types import MappingProxyType
from typing import Any, Final, Mapping

DIFFICULTY_POLICY_VERSION: Final = "difficulty-e01-v1"
DEFAULT_DIFFICULTY_ID: Final = "standard"
PILOT_ENCOUNTER_ID: Final = "e01_two_bells"


class ReconstructionDifficultyError(ValueError):
    """A requested difficulty is unknown or unavailable for this encounter."""


_PROFILES: Final = MappingProxyType({
    "support": MappingProxyType({
        "id": "support",
        "label": "Поддержка",
        "description": "Больше времени на чтение сигналов и менее плотные цели.",
        "hp_multiplier": 0.78,
        "duration_multiplier": 1.30,
        "signal_delta_ms": 220,
    }),
    "standard": MappingProxyType({
        "id": "standard",
        "label": "Обычный",
        "description": "Авторский темп встречи.",
        "hp_multiplier": 1.0,
        "duration_multiplier": 1.0,
        "signal_delta_ms": 0,
    }),
    "challenge": MappingProxyType({
        "id": "challenge",
        "label": "Испытание",
        "description": "Более плотные цели и короткие окна; без множителей наград.",
        "hp_multiplier": 1.18,
        "duration_multiplier": 0.90,
        "signal_delta_ms": -100,
    }),
})


def available_difficulties(encounter_id: str) -> tuple[str, ...]:
    """Return allowed ids; later encounters remain standard until authored."""
    return tuple(_PROFILES) if encounter_id == PILOT_ENCOUNTER_ID else (DEFAULT_DIFFICULTY_ID,)


def normalize_difficulty_id(encounter_id: str, difficulty_id: str | None) -> str:
    selected = str(difficulty_id or DEFAULT_DIFFICULTY_ID).strip().lower()
    if selected not in _PROFILES:
        raise ReconstructionDifficultyError("Неизвестный темп забега.")
    if selected not in available_difficulties(encounter_id):
        raise ReconstructionDifficultyError(
            "Для этой встречи пока доступен только обычный темп."
        )
    return selected


def profile_manifest(encounter_id: str) -> dict[str, Any]:
    allowed = set(available_difficulties(encounter_id))
    return {
        "policy_version": DIFFICULTY_POLICY_VERSION,
        "default_id": DEFAULT_DIFFICULTY_ID,
        "encounter_id": encounter_id,
        "profiles": [
            {
                "id": profile_id,
                "label": str(profile["label"]),
                "description": str(profile["description"]),
                "recommended": profile_id == DEFAULT_DIFFICULTY_ID,
            }
            for profile_id, profile in _PROFILES.items()
            if profile_id in allowed
        ],
    }


def build_wave_plan(
    encounter_id: str,
    difficulty_id: str | None,
    base_waves: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Copy and transform base waves without ever mutating shared content."""
    selected = normalize_difficulty_id(encounter_id, difficulty_id)
    if not base_waves:
        raise ReconstructionDifficultyError("Для встречи не задан набор волн.")
    profile = _PROFILES[selected]
    plan = copy.deepcopy(list(base_waves))
    for wave in plan:
        wave["hp"] = float(max(1, math.ceil(float(wave["hp"]) * float(profile["hp_multiplier"]))))
        wave["duration_ms"] = max(1, int(round(int(wave["duration_ms"]) * float(profile["duration_multiplier"]))))
        wave["signal_ms"] = max(620, int(wave["signal_ms"]) + int(profile["signal_delta_ms"]))
    return selected, plan


def state_difficulty_snapshot(
    encounter_id: str,
    difficulty_id: str | None,
    base_waves: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> dict[str, Any]:
    selected, plan = build_wave_plan(encounter_id, difficulty_id, base_waves)
    profile = _PROFILES[selected]
    return {
        "id": selected,
        "policy_version": DIFFICULTY_POLICY_VERSION,
        "label": str(profile["label"]),
        "wave_plan": plan,
    }
