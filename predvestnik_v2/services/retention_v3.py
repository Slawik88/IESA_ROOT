"""Application service for the Reconstruction Rhythm board."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from core.retention_v3 import (
    DAILY_CONTRACTS,
    WEEKLY_MEANINGFUL_DAY_TARGET,
    daily_offer_ids,
    public_manifest,
    terminal_contribution,
)
from infrastructure.repositories import gameplay_events as event_repo
from infrastructure.repositories import reconstruction as reconstruction_repo
from infrastructure.repositories import retention_v3 as repo
from services import weekly_case_v1 as weekly_case
from services import scar_map_v1 as scar_map


class RetentionError(ValueError):
    pass


class RetentionConflict(RetentionError):
    pass


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _week_start() -> str:
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def _contract_view(contract_id: str) -> dict[str, Any]:
    return {"id": contract_id, **dict(DAILY_CONTRACTS[contract_id])}


async def overview(db, user_id: int) -> dict[str, Any]:
    day_key = _today()
    offers = list(daily_offer_ids(user_id, day_key))
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, user_id)
        row = await repo.ensure_day(db, user_id, GAME_VERSION, day_key, offers)
        completed_days = await repo.count_completed_since(
            db, user_id, GAME_VERSION, _week_start()
        )
    selected = row.get("selected_contract_id")
    return {
        "policy": public_manifest(),
        "day_key": day_key,
        "offers": [_contract_view(contract_id) for contract_id in row["offer_ids"]],
        "selected_contract": _contract_view(selected) if selected else None,
        "progress": int(row.get("progress") or 0),
        "target": int(row.get("target") or (DAILY_CONTRACTS[selected]["target"] if selected else 0)),
        "completed": bool(row.get("completed")),
        "weekly_cadence": {
            "completed_days": completed_days,
            "target_days": WEEKLY_MEANINGFUL_DAY_TARGET,
            "complete": completed_days >= WEEKLY_MEANINGFUL_DAY_TARGET,
            "resets_on_miss": False,
        },
        "reward": {"settled": False, "kind": "shadow_choice_token", "amount": 1},
    }


async def choose_contract(db, user_id: int, contract_id: str, *, source: str = "mini_app") -> dict[str, Any]:
    contract_id = str(contract_id or "").strip()
    if contract_id not in DAILY_CONTRACTS:
        raise RetentionError("Неизвестный контракт Ритма.")
    day_key = _today()
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, user_id)
        offers = list(daily_offer_ids(user_id, day_key))
        day = await repo.ensure_day(db, user_id, GAME_VERSION, day_key, offers)
        if contract_id not in day["offer_ids"]:
            raise RetentionError("Этот контракт сегодня не предложен.")
        if day.get("selected_contract_id") not in (None, contract_id):
            raise RetentionConflict("Контракт на сегодня уже выбран.")
        updated = await repo.select_contract(
            db, user_id, GAME_VERSION, day_key, contract_id, DAILY_CONTRACTS[contract_id]["target"]
        )
        if not updated:
            raise RetentionConflict("Контракт уже изменился в другой вкладке.")
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="daily_contract_selected",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={
                "day_key": day_key,
                "contract_id": contract_id,
                "category": DAILY_CONTRACTS[contract_id]["category"],
                "offered_ids": day["offer_ids"],
                "target": DAILY_CONTRACTS[contract_id]["target"],
            },
            idempotency_key=f"rhythm:{GAME_VERSION}:{day_key}:selected",
        )
    return await overview(db, user_id)


async def apply_terminal_run(
    db,
    *,
    user_id: int,
    run_id: int,
    encounter_id: str,
    outcome: str,
    mastery: dict[str, Any],
    upgrades: list[str],
    meaningful: bool,
    source: str = "mini_app",
) -> dict[str, Any] | None:
    """Advance the chosen contract once per terminal run, inside caller transaction."""
    day_key = _today()
    # Keep the invariant local to this writer as well as its current caller:
    # future terminal paths must not be able to race contribution insertion and
    # progress capping merely because they forgot the outer user lock.
    await reconstruction_repo.lock_user(db, user_id)
    day = await repo.get_day(db, user_id, GAME_VERSION, day_key)
    contract_id = str((day or {}).get("selected_contract_id") or "")
    if not contract_id or bool(day.get("completed")):
        return None
    delta = terminal_contribution(
        contract_id,
        outcome=outcome,
        encounter_id=encounter_id,
        mastery=mastery,
        upgrades=upgrades,
        meaningful=meaningful,
    )
    if delta <= 0:
        return None
    inserted = await repo.record_contribution(
        db,
        user_id=user_id,
        game_version=GAME_VERSION,
        day_key=day_key,
        run_id=run_id,
        contract_id=contract_id,
        delta=delta,
    )
    if not inserted:
        return None
    updated = await repo.add_progress(db, user_id, GAME_VERSION, day_key, delta)
    if not updated:
        return None
    await event_repo.record_event(
        db,
        user_id=user_id,
        event_name="daily_contract_progressed",
        game_version=GAME_VERSION,
        balance_version=BALANCE_VERSION,
        run_id=run_id,
        source=source,
        payload={
            "day_key": day_key,
            "contract_id": contract_id,
            "delta": delta,
            "progress": int(updated["progress"]),
            "target": int(updated["target"]),
            "completed": bool(updated["completed"]),
        },
        idempotency_key=f"rhythm:{GAME_VERSION}:run:{run_id}",
    )
    if bool(updated["completed"]):
        await weekly_case.apply_completed_day(
            db, user_id=user_id, day_key=day_key,
            contract_id=contract_id, source=source,
        )
        await scar_map.apply_meaningful_day(
            db, user_id=user_id, day_key=day_key, source=source,
        )
    return updated
