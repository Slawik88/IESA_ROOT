"""Application service for the fair 28-day Scar Map."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from core.scar_map_v1 import FINAL_REQUIRED, POLICY_VERSION, public_view, unlocked_node_ids
from infrastructure.repositories import gameplay_events as event_repo
from infrastructure.repositories import reconstruction as reconstruction_repo
from infrastructure.repositories import scar_map_v1 as repo


async def _ensure_active(db, user_id: int) -> tuple[dict[str, Any], bool]:
    await repo.archive_if_expired(db, user_id)
    row = await repo.active(db, user_id)
    if row:
        return row, False
    return await repo.create_cycle(db, user_id), True


async def _start_event(db, user_id: int, row: dict[str, Any], source: str) -> None:
    await event_repo.record_event(
        db, user_id=user_id, event_name="scar_map_started",
        game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
        payload={"policy_version": POLICY_VERSION, "cycle_no": int(row["cycle_no"]),
                 "duration_days": 28, "final_required": FINAL_REQUIRED},
        idempotency_key=f"scar-map:{POLICY_VERSION}:{user_id}:{row['cycle_no']}:started",
    )


def _event_reference(reference_id: str) -> str:
    return hashlib.sha256(str(reference_id).encode("utf-8")).hexdigest()[:20]


def _fingerprint(*, trigger_type: str, counter_deltas: dict[str, int] | None,
                 counter_max: dict[str, int] | None, encounter_id: str | None) -> str:
    canonical = json.dumps({
        "trigger_type": trigger_type,
        "counter_deltas": counter_deltas or {},
        "counter_max": counter_max or {},
        "encounter_id": encounter_id,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def overview(db, user_id: int, *, source: str = "mini_app") -> dict[str, Any]:
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, user_id)
        row, created = await _ensure_active(db, user_id)
        if created:
            await _start_event(db, user_id, row, source)
        counters, encounters = repo.decode_state(row)
        return public_view(row, counters, encounters)


async def _apply(db, *, user_id: int, trigger_type: str, reference_id: str,
                 counter_deltas: dict[str, int] | None = None,
                 counter_max: dict[str, int] | None = None,
                 encounter_id: str | None = None, source: str) -> dict[str, Any] | None:
    await reconstruction_repo.lock_user(db, user_id)
    row, created = await _ensure_active(db, user_id)
    if created:
        await _start_event(db, user_id, row, source)
    inserted = await repo.record_contribution(
        db, user_id=user_id, cycle_no=int(row["cycle_no"]),
        trigger_type=trigger_type, reference_id=str(reference_id)[:96],
        fingerprint=_fingerprint(
            trigger_type=trigger_type, counter_deltas=counter_deltas,
            counter_max=counter_max, encounter_id=encounter_id,
        ),
    )
    if not inserted:
        return None
    counters, encounters = repo.decode_state(row)
    before = set(unlocked_node_ids(counters, encounters))
    for key, delta in (counter_deltas or {}).items():
        counters[key] = max(0, int(counters.get(key, 0)) + max(0, int(delta)))
    for key, value in (counter_max or {}).items():
        counters[key] = max(int(counters.get(key, 0)), max(0, int(value)))
    if encounter_id:
        encounters.add(str(encounter_id))
    after = set(unlocked_node_ids(counters, encounters))
    completed = len(after) >= FINAL_REQUIRED
    updated = await repo.save_state(
        db, user_id=user_id, cycle_no=int(row["cycle_no"]), counters=counters,
        encounters=encounters, completed=completed,
    )
    new_nodes = sorted(after - before)
    await event_repo.record_event(
        db, user_id=user_id, event_name="scar_map_progressed",
        game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
        payload={"policy_version": POLICY_VERSION, "cycle_no": int(row["cycle_no"]),
                 "trigger_type": trigger_type, "unlocked_node_ids": new_nodes,
                 "unlocked_count": len(after), "final_required": FINAL_REQUIRED},
        idempotency_key=f"scar-map:{POLICY_VERSION}:{user_id}:{row['cycle_no']}:{trigger_type}:{_event_reference(reference_id)}",
    )
    if completed and len(before) < FINAL_REQUIRED:
        await event_repo.record_event(
            db, user_id=user_id, event_name="scar_map_completed",
            game_version=GAME_VERSION, balance_version=BALANCE_VERSION, source=source,
            payload={"policy_version": POLICY_VERSION, "cycle_no": int(row["cycle_no"]),
                     "unlocked_count": len(after), "final_required": FINAL_REQUIRED},
            idempotency_key=f"scar-map:{POLICY_VERSION}:{user_id}:{row['cycle_no']}:completed",
        )
    return public_view(updated, counters, encounters)


async def apply_battle_end(db, *, user_id: int, run_id: str, encounter_id: str,
                           outcome: str, mastery: dict[str, Any], meaningful: bool,
                           source: str) -> dict[str, Any] | None:
    if not meaningful:
        return None
    mistakes = int(mastery.get("mistakes") or 0)
    missed = int(mastery.get("missed_signals") or 0)
    total = int(mastery.get("correct_taps") or 0) + mistakes + missed
    accuracy = round(int(mastery.get("correct_taps") or 0) * 100 / total) if total else 0
    won = outcome == "won"
    return await _apply(
        db, user_id=user_id, trigger_type="battle_end", reference_id=run_id,
        counter_deltas={
            "terminal_runs": 1,
            "discharges": int(mastery.get("discharges") or 0),
            "recovery_wins": int(won and mistakes > 0),
            "flawless_wins": int(won and mistakes == 0 and missed == 0),
        },
        counter_max={"max_accuracy": accuracy if won else 0,
                     "max_combo": int(mastery.get("max_combo") or 0)},
        encounter_id=encounter_id, source=source,
    )


async def apply_meaningful_day(db, *, user_id: int, day_key: str, source: str) -> dict[str, Any] | None:
    return await _apply(
        db, user_id=user_id, trigger_type="meaningful_day", reference_id=day_key,
        counter_deltas={"meaningful_days": 1}, source=source,
    )


async def apply_archive_claim(db, *, user_id: int, action_id: str,
                              new_discovery_count: int, source: str) -> dict[str, Any] | None:
    if new_discovery_count <= 0:
        return None
    return await _apply(
        db, user_id=user_id, trigger_type="archive_claim", reference_id=action_id,
        counter_deltas={"archive_discoveries": int(new_discovery_count)}, source=source,
    )
