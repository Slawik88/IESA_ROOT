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
