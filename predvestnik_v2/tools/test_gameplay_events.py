#!/usr/bin/env python3
"""Contract and idempotency checks for meaningful gameplay telemetry."""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.gameplay_events import GameplayEventConflict, GameplayEventError, canonical_event_payload
from infrastructure.repositories.gameplay_events import record_event


class Cursor:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def execute(self, sql, args=()):
        if sql.startswith("INSERT INTO gameplay_events"):
            key = (int(args[0]), args[8])
            if args[8] is not None and key in self.rows:
                return Cursor(None)
            row_id = self.next_id
            self.next_id += 1
            if args[8] is not None:
                self.rows[key] = (
                    args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[9],
                )
            return Cursor((row_id,))
        if sql.startswith("SELECT event_name"):
            return Cursor(self.rows.get((int(args[0]), args[1])))
        raise AssertionError(f"Unexpected SQL: {sql}")


def battle_start_payload():
    return {
        "mode": "reconstruction_clicker",
        "encounter_id": "e01_two_bells",
        "squad": ["guardian", "striker", "controller"],
        "levels": {"guardian": 1, "striker": 1, "controller": 1},
        "combat_power": None,
        "modifiers": [],
    }


async def main():
    version, payload_json = canonical_event_payload("battle_start", battle_start_payload())
    assert version == 1 and '"combat_power":null' in payload_json

    _, action_json = canonical_event_payload("battle_action", {
        "mode": "reconstruction_clicker",
        "encounter_id": "e01_two_bells",
        "round": 1,
        "action": "resolve_signal",
        "accepted": True,
        "correct": True,
        "legal_options_count": 3,
        "reaction_ms": 143,
        "server_delta_ms": 101,
        "server_revision": 9,
        "integrity_status": "clear",
    })
    assert '"reaction_ms":143' in action_json and '"server_revision":9' in action_json

    _, terminal_json = canonical_event_payload("battle_end", {
        "mode": "reconstruction_clicker",
        "encounter_id": "e01_two_bells",
        "result": "won",
        "rounds": 3,
        "metrics": {"correct_taps": 12},
        "terminal_result": {
            "id": "reconstruction:41:terminal",
            "outcome": "won",
            "server_revision": 23,
            "integrity": {"status": "clear", "automatic_ban": False},
        },
        "signals_resolved": 12,
        "companion_role_id": "lantern",
        "upgrades": ["heavy_echo"],
        "exit_wave_elapsed_ms": 4312,
    })
    assert '"reconstruction:41:terminal"' in terminal_json
    assert '"exit_wave_elapsed_ms":4312' in terminal_json

    _, rhythm_json = canonical_event_payload("daily_contract_selected", {
        "day_key": "2026-08-26",
        "contract_id": "steady_hand",
        "category": "mastery",
        "offered_ids": ["steady_hand", "charged_bell", "living_build"],
        "target": 1,
    })
    assert '"contract_id":"steady_hand"' in rhythm_json

    _, surface_json = canonical_event_payload(
        "product_surface_opened", {"surface_id": "inventory"}
    )
    _, preference_json = canonical_event_payload(
        "player_preference_changed", {"preference": "vip_expiry", "enabled": False}
    )
    assert '"surface_id":"inventory"' in surface_json
    assert '"enabled":false' in preference_json
    _, care_json = canonical_event_payload("companion_care", {
        "pet_id": 11, "action": "play", "scene_id": "bell_game",
        "bond_points": 1, "care_bank": 0,
    })
    assert '"scene_id":"bell_game"' in care_json
    _, expedition_start_json = canonical_event_payload("expedition_started", {
        "contract_id": 3, "pet_id": 11, "duration_hours": 6,
        "route_id": "story_clue", "projected_mora": 145,
        "archive_version": "companion-archive-v1-2026-08-27",
        "archive_set_id": "lost_names",
    })
    _, expedition_claim_json = canonical_event_payload("expedition_claimed", {
        "claimed_count": 1, "projected_mora_total": 145,
        "contract_ids": [3], "discovery_ids": ["ash_map"],
    })
    assert '"duration_hours":6' in expedition_start_json
    assert '"claimed_count":1' in expedition_claim_json
    _, archive_json = canonical_event_payload("archive_progressed", {
        "archive_version": "companion-archive-v1-2026-08-27",
        "contract_ids": [3], "new_discovery_ids": ["ink_trace"],
        "duplicate_discovery_ids": [], "completed_set_ids": [], "found_total": 1,
    })
    assert '"found_total":1' in archive_json
    assert '"discovery_id"' not in expedition_start_json
    _, weekly_json = canonical_event_payload("weekly_case_progressed", {
        "policy_version": "weekly-case-v1-2026-08-27", "case_id": "bell_beneath_water",
        "path_id": "follow_bell", "day_key": "2026-08-27",
        "progress": 1, "target": 3, "completed": False,
    })
    assert '"progress":1' in weekly_json
    _, weekly_done_json = canonical_event_payload("weekly_case_completed", {
        "policy_version": "weekly-case-v1-2026-08-27", "case_id": "bell_beneath_water",
        "path_id": "follow_bell", "finale_id": "many_voices",
        "completion_trigger": "meaningful_day",
    })
    assert '"finale_id":"many_voices"' in weekly_done_json
    _, echo_json = canonical_event_payload("chat_echo_contributed", {
        "event_id": 9, "policy_version": "chat-echo-v1-2026-08-27",
        "symbol_id": "bell", "total": 2, "target": 3, "completed": False,
    })
    assert '"symbol_id":"bell"' in echo_json

    for invalid in (
        {**battle_start_payload(), "username": "private"},
        {key: value for key, value in battle_start_payload().items() if key != "squad"},
        {**battle_start_payload(), "modifiers": [{"message_text": "private"}]},
    ):
        try:
            canonical_event_payload("battle_start", invalid)
        except GameplayEventError:
            pass
        else:
            raise AssertionError(f"Invalid telemetry payload was accepted: {invalid}")

    try:
        canonical_event_payload("unknown_event", {})
    except GameplayEventError:
        pass
    else:
        raise AssertionError("Unknown gameplay event was accepted")

    try:
        canonical_event_payload("battle_start", [])
    except GameplayEventError:
        pass
    else:
        raise AssertionError("Non-object telemetry payload was accepted")

    db = FakeDB()
    kwargs = {
        "user_id": 7001,
        "event_name": "battle_start",
        "game_version": "3.0.0-alpha.3",
        "balance_version": "test-balance",
        "run_id": 41,
        "source": "mini_app",
        "payload": battle_start_payload(),
        "idempotency_key": "run:41:started",
    }
    assert await record_event(db, **kwargs) is True
    assert await record_event(db, **kwargs) is False
    try:
        await record_event(
            db,
            **{
                **kwargs,
                "payload": {**battle_start_payload(), "combat_power": 999},
            },
        )
    except GameplayEventConflict:
        pass
    else:
        raise AssertionError("Conflicting replay was silently accepted")

    # A user-level milestone is intentionally independent from a particular run.
    # Retrying it after a lost run must stay an exact idempotent replay.
    milestone = {
        "user_id": 7001,
        "event_name": "game_onboarding_step",
        "game_version": "3.0.0-alpha.3",
        "balance_version": "test-balance",
        "source": "mini_app",
        "payload": {
            "step": "first_encounter_started",
            "result": "completed",
            "encounter_id": "e01_two_bells",
        },
        "idempotency_key": "onboarding:3.0.0-alpha.3:first_encounter_started",
    }
    assert await record_event(db, **milestone) is True
    assert await record_event(db, **milestone) is False

print("OK: gameplay events validate schema/PII and reject conflicting replays")


asyncio.run(main())
