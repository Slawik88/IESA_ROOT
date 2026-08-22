"""Versioned contract for meaningful gameplay telemetry.

The registry intentionally excludes render/frame heartbeats. An event must
represent a player decision, a progression boundary or a completed outcome.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final


MAX_PAYLOAD_BYTES: Final = 8_192
MAX_STRING_LENGTH: Final = 512
MAX_COLLECTION_LENGTH: Final = 64
MAX_NESTING_DEPTH: Final = 5
_FORBIDDEN_KEY_PARTS: Final = (
    "username", "first_name", "last_name", "phone", "email", "message_text",
    "init_data", "auth_data", "token", "password", "photo_url",
)


class GameplayEventError(ValueError):
    pass


class GameplayEventConflict(GameplayEventError):
    pass


@dataclass(frozen=True)
class EventSpec:
    version: int
    required: frozenset[str]
    optional: frozenset[str] = frozenset()

    @property
    def allowed(self) -> frozenset[str]:
        return self.required | self.optional


GAMEPLAY_EVENT_SPECS: Final[dict[str, EventSpec]] = {
    "game_onboarding_step": EventSpec(
        1,
        frozenset({"step", "result"}),
        frozenset({"encounter_id", "elapsed_ms"}),
    ),
    "battle_start": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "squad", "levels", "combat_power", "modifiers"}),
    ),
    "battle_action": EventSpec(
        1,
        frozenset({
            "mode", "encounter_id", "round", "action", "accepted", "correct",
            "legal_options_count",
        }),
        frozenset({
            "challenge_id", "target_slot", "critical", "damage", "discharged", "reason",
            "reaction_ms", "server_delta_ms", "server_revision", "integrity_status",
        }),
    ),
    "battle_upgrade": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "round", "upgrade_id", "offered_ids"}),
        frozenset({"server_revision"}),
    ),
    "battle_end": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "result", "rounds", "metrics"}),
        frozenset({"outcome_reason", "terminal_result", "shadow_reward"}),
    ),
    "progression_upgrade": EventSpec(
        1,
        frozenset({"entity", "from_value", "to_value", "resource_cost", "trigger"}),
    ),
}


def _validate_value(value: Any, path: str, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise GameplayEventError(f"{path}: telemetry nesting is too deep")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise GameplayEventError(f"{path}: non-finite number is forbidden")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise GameplayEventError(f"{path}: string exceeds {MAX_STRING_LENGTH} characters")
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_LENGTH:
            raise GameplayEventError(f"{path}: list exceeds {MAX_COLLECTION_LENGTH} items")
        for index, item in enumerate(value):
            _validate_value(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_LENGTH:
            raise GameplayEventError(f"{path}: object exceeds {MAX_COLLECTION_LENGTH} keys")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise GameplayEventError(f"{path}: invalid object key")
            lowered = key.casefold()
            if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
                raise GameplayEventError(f"{path}.{key}: personal/auth data is forbidden")
            _validate_value(item, f"{path}.{key}", depth + 1)
        return
    raise GameplayEventError(f"{path}: unsupported value type {type(value).__name__}")


def canonical_event_payload(event_name: str, payload: dict[str, Any]) -> tuple[int, str]:
    spec = GAMEPLAY_EVENT_SPECS.get(str(event_name))
    if spec is None:
        raise GameplayEventError(f"Unknown gameplay event: {event_name!r}")
    if not isinstance(payload, dict):
        raise GameplayEventError("Gameplay event payload must be an object")
    missing = sorted(spec.required - payload.keys())
    extra = sorted(payload.keys() - spec.allowed)
    if missing:
        raise GameplayEventError(f"{event_name}: missing fields: {', '.join(missing)}")
    if extra:
        raise GameplayEventError(f"{event_name}: unknown fields: {', '.join(extra)}")
    _validate_value(payload, event_name)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise GameplayEventError(
            f"{event_name}: payload exceeds {MAX_PAYLOAD_BYTES} bytes"
        )
    return spec.version, serialized
