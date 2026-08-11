"""Application service первой вертикали Reconstruction 3.0."""
from __future__ import annotations

import copy
from typing import Any

from core.reconstruction import (
    BALANCE_VERSION,
    CLICKER_UPGRADES,
    ENCOUNTERS,
    FEATURE_FLAG_KEY,
    GAME_VERSION,
    MEMORIES,
    STARTER_UNITS,
)
from infrastructure.repositories import reconstruction as repo
from services import reconstruction_combat as combat


FIRST_ENCOUNTER = "e01_two_bells"


class ReconstructionError(ValueError):
    pass


class ReconstructionConflict(ReconstructionError):
    pass


def content_manifest() -> dict[str, Any]:
    """Публичный, версионированный контракт контента для mini app."""
    encounters = []
    for encounter_id, encounter in sorted(
        ENCOUNTERS.items(), key=lambda pair: (pair[1]["order"], pair[0])
    ):
        encounters.append({
            "id": encounter_id,
            "order": encounter["order"],
            "branch": encounter.get("branch"),
            "name": encounter["name"],
            "implemented": bool(encounter.get("implemented")),
            "objective": copy.deepcopy(encounter["objective"]),
            "teaches": list(encounter.get("teaches", ())),
            "mastery": encounter.get("mastery"),
            "phases": copy.deepcopy(encounter.get("phases", ())),
        })
    units = []
    for unit_id, unit in STARTER_UNITS.items():
        units.append({
            "id": unit_id,
            "name": unit["name"],
            "short_name": unit["short_name"],
            "emoji": unit["emoji"],
            "role": unit["role"],
            "element": unit["element"],
            "stats": copy.deepcopy(unit["stats"]),
            "basic": copy.deepcopy(unit["basic"]),
            "skill": copy.deepcopy(unit["skill"]),
            "mastery": unit["mastery"],
            "counterplay": unit["counterplay"],
        })
    return {
        "game_version": GAME_VERSION,
        "balance_version": BALANCE_VERSION,
        "feature_flag": FEATURE_FLAG_KEY,
        "mode": "advanced_clicker",
        "starter_units": units,
        "clicker_upgrades": [
            {"id": upgrade_id, **copy.deepcopy(upgrade)}
            for upgrade_id, upgrade in CLICKER_UPGRADES.items()
        ],
        "encounters": encounters,
    }


def _pending_memory(progress: dict[str, Any]) -> dict[str, Any] | None:
    if FIRST_ENCOUNTER not in progress["completed"]:
        return None
    choices = ENCOUNTERS[FIRST_ENCOUNTER].get("reward_choice", ())
    if any(memory_id in progress["memories"] for memory_id in choices):
        return None
    return {
        "encounter_id": FIRST_ENCOUNTER,
        "choices": [{"id": memory_id, **copy.deepcopy(MEMORIES[memory_id])} for memory_id in choices],
    }


async def overview(db, user_id: int) -> dict[str, Any]:
    progress = await repo.get_progress(db, user_id, GAME_VERSION)
    active = await repo.get_active_run(db, user_id, GAME_VERSION)
    if not progress:
        progress_view = {
            "started": False,
            "current_encounter": FIRST_ENCOUNTER,
            "completed": [],
            "memories": [],
            "pending_memory": None,
        }
    else:
        progress_view = {
            "started": True,
            "current_encounter": progress["current_encounter"],
            "completed": progress["completed"],
            "memories": progress["memories"],
            "pending_memory": _pending_memory(progress),
        }
    active_view = None
    if active:
        active_view = {
            "run_id": active["id"],
            "revision": active["revision"],
            **combat.public_state(active["state"]),
        }
    return {"content": content_manifest(), "progress": progress_view, "active_run": active_view}


async def start_encounter(
    db, user_id: int, encounter_id: str = FIRST_ENCOUNTER, *, source: str = "mini_app"
) -> dict[str, Any]:
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        progress = await repo.ensure_progress(db, user_id, GAME_VERSION, FIRST_ENCOUNTER)
        active = await repo.get_active_run(db, user_id, GAME_VERSION)
        if active:
            if active["encounter_id"] != encounter_id:
                raise ReconstructionConflict("Сначала заверши текущую встречу.")
            return {
                "run_id": active["id"],
                "revision": active["revision"],
                "resumed": True,
                **combat.public_state(active["state"]),
            }
        if progress["current_encounter"] != encounter_id:
            raise ReconstructionError("Эта встреча ещё не является следующим шагом кампании.")
        encounter = ENCOUNTERS.get(encounter_id)
        if not encounter:
            raise ReconstructionError("Неизвестная встреча.")
        if not encounter.get("implemented"):
            raise ReconstructionError("Следующая встреча ещё не включена в dev-срез.")
        state = combat.new_encounter(encounter_id, seed=(int(user_id) ^ 0x5EED) & 0x7FFFFFFF)
        run_id = await repo.create_run(
            db, user_id, GAME_VERSION, BALANCE_VERSION, encounter_id, combat.dumps(state)
        )
        await repo.record_event(
            db,
            user_id=user_id,
            event_name="encounter_started",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            run_id=run_id,
            source=source,
            payload={"encounter_id": encounter_id},
            idempotency_key=f"run:{run_id}:started",
        )
        return {
            "run_id": run_id,
            "revision": 0,
            "resumed": False,
            **combat.public_state(state),
        }


def _next_after(encounter_id: str) -> str:
    if encounter_id == FIRST_ENCOUNTER:
        return "e02_shattered_causeway"
    return encounter_id


async def apply_run_action(
    db,
    user_id: int,
    run_id: int,
    action_id: str,
    action: dict[str, Any],
    *,
    source: str = "mini_app",
) -> dict[str, Any]:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise ReconstructionError("action_id обязателен и не должен превышать 96 символов.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        run = await repo.get_run(db, run_id, user_id)
        if not run:
            raise ReconstructionError("Встреча не найдена.")
        # Ownership проверяется до idempotency-кэша: run_id/action_id не должны
        # позволять прочитать ответ другого игрока при угадывании идентификаторов.
        cached = await repo.get_action_response(db, run_id, action_id)
        if cached is not None:
            cached["idempotent_replay"] = True
            return cached
        if run["status"] != "active":
            raise ReconstructionConflict("Встреча уже завершена.")
        if run["game_version"] != GAME_VERSION:
            raise ReconstructionConflict("Встреча создана несовместимой версией игры.")

        state = run["state"]
        result = combat.apply_action(state, action)
        if not result.get("ok"):
            raise ReconstructionError(str(result.get("error") or "Действие отклонено."))
        # Межволновый выбор — часть незавершённого забега. В БД такой run остаётся
        # active, иначе частичный unique-index и optimistic UPDATE сочтут его
        # завершённым и не дадут принять выбранное усиление.
        storage_status = state["status"] if state["status"] in ("won", "lost") else "active"
        new_revision = await repo.save_run_state(
            db, run_id, int(run["revision"]), combat.dumps(state), storage_status
        )
        if new_revision is None:
            raise ReconstructionConflict("Состояние уже изменилось в другой вкладке. Обновляю бой.")

        await repo.record_event(
            db,
            user_id=user_id,
            event_name="combat_action",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            run_id=run_id,
            source=source,
            payload={
                "encounter_id": run["encounter_id"],
                "round": state["round"],
                "action_type": action.get("type"),
                "challenge_id": action.get("challenge_id"),
                "target_slot": action.get("target_slot"),
                "upgrade_id": action.get("upgrade_id"),
                "strike_correct": (result.get("strike") or {}).get("correct"),
                "result_phase": result.get("phase"),
            },
            idempotency_key=f"run:{run_id}:action:{action_id}",
        )

        pending_memory = None
        if state["status"] in ("won", "lost"):
            await repo.record_event(
                db,
                user_id=user_id,
                event_name="encounter_completed",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                run_id=run_id,
                source=source,
                payload={
                    "encounter_id": run["encounter_id"],
                    "outcome": state["status"],
                    "outcome_reason": state.get("outcome_reason"),
                    "rounds": state["round"],
                    "mastery": state["mastery"],
                },
                idempotency_key=f"run:{run_id}:completed",
            )
            if state["status"] == "won":
                progress = await repo.ensure_progress(db, user_id, GAME_VERSION, FIRST_ENCOUNTER)
                completed = list(dict.fromkeys([*progress["completed"], run["encounter_id"]]))
                await repo.save_progress(
                    db,
                    user_id,
                    GAME_VERSION,
                    current_encounter=_next_after(run["encounter_id"]),
                    completed=completed,
                    memories=progress["memories"],
                )
                pending_memory = {
                    "encounter_id": run["encounter_id"],
                    "choices": [
                        {"id": memory_id, **copy.deepcopy(MEMORIES[memory_id])}
                        for memory_id in ENCOUNTERS[run["encounter_id"]].get("reward_choice", ())
                    ],
                }

        response = {
            "run_id": run_id,
            "revision": new_revision,
            "turn": result,
            "pending_memory": pending_memory,
            "idempotent_replay": False,
            **combat.public_state(state),
        }
        await repo.save_action_response(db, run_id, action_id, action, response)
        return response


async def choose_memory(
    db, user_id: int, memory_id: str, *, source: str = "mini_app"
) -> dict[str, Any]:
    if memory_id not in MEMORIES:
        raise ReconstructionError("Неизвестная память.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        progress = await repo.get_progress(db, user_id, GAME_VERSION)
        if not progress:
            raise ReconstructionError("Сначала начни кампанию.")
        pending = _pending_memory(progress)
        if not pending:
            if memory_id in progress["memories"]:
                return {"ok": True, "memory_id": memory_id, "idempotent_replay": True}
            raise ReconstructionError("Сейчас нет незавершённого выбора памяти.")
        allowed = {choice["id"] for choice in pending["choices"]}
        if memory_id not in allowed:
            raise ReconstructionError("Эта память не относится к текущей награде.")
        memories = [*progress["memories"], memory_id]
        await repo.save_progress(
            db,
            user_id,
            GAME_VERSION,
            current_encounter=progress["current_encounter"],
            completed=progress["completed"],
            memories=memories,
        )
        await repo.record_event(
            db,
            user_id=user_id,
            event_name="memory_chosen",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={"memory_id": memory_id, "after_encounter": FIRST_ENCOUNTER},
            idempotency_key=f"memory:{GAME_VERSION}:{FIRST_ENCOUNTER}",
        )
        return {
            "ok": True,
            "memory_id": memory_id,
            "memory": copy.deepcopy(MEMORIES[memory_id]),
            "idempotent_replay": False,
        }
