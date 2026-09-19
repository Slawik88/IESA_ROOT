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
        frozenset({"difficulty_profile", "difficulty_policy_version"}),
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
            "branch_results", "difficulty_profile", "difficulty_policy_version",
        }),
    ),
    "battle_upgrade": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "round", "upgrade_id", "offered_ids"}),
        frozenset({"server_revision", "difficulty_profile", "difficulty_policy_version"}),
    ),
    "battle_branch_action": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "round", "branch_id", "command", "result"}),
        frozenset({"damage", "server_revision", "difficulty_profile", "difficulty_policy_version"}),
    ),
    "battle_end": EventSpec(
        1,
        frozenset({"mode", "encounter_id", "result", "rounds", "metrics"}),
        frozenset({
            "outcome_reason", "terminal_result", "shadow_reward", "branches",
            "difficulty_profile", "difficulty_policy_version", "signals_resolved",
            "companion_role_id", "upgrades", "exit_wave_elapsed_ms",
        }),
    ),
    "progression_upgrade": EventSpec(
        1,
        frozenset({"entity", "from_value", "to_value", "resource_cost", "trigger"}),
    ),
    "daily_contract_selected": EventSpec(
        1,
        frozenset({"day_key", "contract_id", "category", "offered_ids", "target"}),
    ),
    "daily_contract_progressed": EventSpec(
        1,
        frozenset({"day_key", "contract_id", "delta", "progress", "target", "completed"}),
    ),
    "weekly_case_path_chosen": EventSpec(
        1,
        frozenset({"policy_version", "case_id", "path_id"}),
    ),
    "weekly_case_progressed": EventSpec(
        1,
        frozenset({
            "policy_version", "case_id", "path_id", "day_key",
            "progress", "target", "completed",
        }),
    ),
    "weekly_case_completed": EventSpec(
        1,
        frozenset({
            "policy_version", "case_id", "path_id", "finale_id",
            "completion_trigger",
        }),
    ),
    "chat_echo_started": EventSpec(
        1,
        frozenset({"event_id", "policy_version", "target", "quorum", "active_members_7d"}),
    ),
    "chat_echo_contributed": EventSpec(
        1,
        frozenset({"event_id", "policy_version", "symbol_id", "total", "target", "completed"}),
    ),
    "chat_echo_completed": EventSpec(
        1,
        frozenset({"event_id", "policy_version", "finale_id", "total", "target"}),
    ),
    "chat_echo_opt_changed": EventSpec(
        1,
        frozenset({"enabled"}),
    ),
    "store_offer_viewed": EventSpec(
        1,
        frozenset({"surface", "offer_id", "offer_type", "price_stars"}),
        frozenset({"owned", "eligibility", "placement"}),
    ),
    "store_purchase_result": EventSpec(
        1,
        frozenset({"offer_id", "offer_type", "price_stars", "result"}),
        frozenset({"operation_id", "failure_code", "entitlement_ids"}),
    ),
    "product_surface_opened": EventSpec(
        1,
        frozenset({"surface_id"}),
    ),
    "player_preference_changed": EventSpec(
        1,
        frozenset({"preference", "enabled"}),
    ),
    "companion_care": EventSpec(
        1,
        frozenset({"pet_id", "action", "scene_id", "bond_points"}),
        frozenset({"care_bank"}),
    ),
    "companion_skin_selected": EventSpec(
        1,
        frozenset({"skin_id", "skin_version"}),
    ),
    "expedition_started": EventSpec(
        1,
        frozenset({"contract_id", "pet_id", "duration_hours", "route_id", "projected_mora"}),
        frozenset({"discovery_id", "archive_version", "archive_set_id"}),
    ),
    "expedition_claimed": EventSpec(
        1,
        frozenset({"claimed_count", "projected_mora_total", "contract_ids", "discovery_ids"}),
    ),
    "archive_progressed": EventSpec(
        1,
        frozenset({
            "archive_version", "contract_ids", "new_discovery_ids",
            "duplicate_discovery_ids", "completed_set_ids", "found_total",
        }),
    ),
    "scar_map_started": EventSpec(
        1,
        frozenset({"policy_version", "cycle_no", "duration_days", "final_required"}),
    ),
    "scar_map_progressed": EventSpec(
        1,
        frozenset({
            "policy_version", "cycle_no", "trigger_type", "unlocked_node_ids",
            "unlocked_count", "final_required",
        }),
    ),
    "scar_map_completed": EventSpec(
        1,
        frozenset({"policy_version", "cycle_no", "unlocked_count", "final_required"}),
    ),
    "sky_node_allocated": EventSpec(
        1,
        frozenset({"policy_version", "node_id", "branch", "allocated_count", "path_slots"}),
    ),
    "sky_sigil_selected": EventSpec(
        1,
        frozenset({"policy_version", "node_id"}),
    ),
    "sky_eclipse_used": EventSpec(
        1,
        frozenset({"policy_version", "cycle_no"}),
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
