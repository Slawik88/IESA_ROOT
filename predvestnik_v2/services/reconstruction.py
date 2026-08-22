"""Application service первой вертикали Reconstruction 3.0."""
from __future__ import annotations

import copy
import secrets
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
from core.economy_v3 import (
    POLICY_VERSION,
    evaluate_reconstruction_reward_shadow,
    public_policy_manifest,
)
from core.reconstruction_progression import (
    branch_by_id,
    mastery_proofs_from_terminal,
    public_progression_manifest,
    unit_progress_view,
)
from infrastructure.repositories import gameplay_events as event_repo
from infrastructure.repositories import reconstruction as repo
from infrastructure.repositories import economy_shadow as shadow_repo
from infrastructure.repositories import reconstruction_units as unit_repo
from services import reconstruction_combat as combat
from services import reconstruction_integrity as integrity
from services import reconstruction_timing as timing


FIRST_ENCOUNTER = "e01_two_bells"
CHAPTER_ONE_PATH_GATE = "choose_chapter_1_path"
CHAPTER_ONE_PATHS = {"ink": "e03_ink_path", "ash": "e03_ash_path"}


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
        "timing_policy": timing.public_timing_manifest(),
        "integrity_policy": integrity.public_integrity_manifest(),
        "economy_policy": public_policy_manifest(),
        "unit_progression": public_progression_manifest(),
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


def _next_step(progress: dict[str, Any]) -> dict[str, Any]:
    pending = _pending_memory(progress)
    if pending:
        return {
            "type": "choose_memory",
            "title": "Сохрани Память первой победы",
            "description": "Выбор постоянный, бесплатный и не тратит валюту.",
            "encounter_id": pending["encounter_id"],
        }
    encounter_id = str(progress.get("current_encounter") or FIRST_ENCOUNTER)
    if encounter_id == CHAPTER_ONE_PATH_GATE:
        return {
            "type": "choose_chronicle_path",
            "title": "Выбери тропу первой главы",
            "description": "Чернила проверяют чтение ложных знаков; Пепел — контроль темпа и риска.",
            "choices": [
                {
                    "id": path_id,
                    "encounter_id": target,
                    "name": ENCOUNTERS[target]["name"],
                    "description": ENCOUNTERS[target]["objective"]["description"],
                    "mastery": ENCOUNTERS[target]["mastery"],
                }
                for path_id, target in CHAPTER_ONE_PATHS.items()
            ],
        }
    encounter = ENCOUNTERS.get(encounter_id)
    if encounter and encounter.get("implemented"):
        return {
            "type": "play_encounter",
            "title": encounter["name"],
            "description": encounter["objective"]["description"],
            "encounter_id": encounter_id,
            "practice": False,
        }
    completed = list(progress.get("completed") or [])
    return {
        "type": "development_gate",
        "title": "Первая глава Хроники пройдена",
        "description": "Следующая ветка ещё не включена; повтор доступен только в тренировке без наград.",
        "encounter_id": encounter_id,
        "practice_encounter_id": completed[-1] if completed else FIRST_ENCOUNTER,
        "practice": True,
    }


async def overview(db, user_id: int) -> dict[str, Any]:
    progress = await repo.get_progress(db, user_id, GAME_VERSION)
    active = await repo.get_active_run(db, user_id, GAME_VERSION)
    stats = await repo.get_stats(db, user_id, GAME_VERSION)
    stored_units = {
        item["unit_id"]: item
        for item in await unit_repo.list_progress(db, user_id, GAME_VERSION)
    }
    mastery_proofs = await unit_repo.get_mastery_proofs(db, user_id, GAME_VERSION)
    units = []
    for unit_id in STARTER_UNITS:
        progress_item = stored_units.get(unit_id) or unit_progress_view(unit_id, 0)
        units.append({
            **progress_item,
            "name": STARTER_UNITS[unit_id]["name"],
            "short_name": STARTER_UNITS[unit_id]["short_name"],
            "emoji": STARTER_UNITS[unit_id]["emoji"],
            "proven_challenges": sorted(
                challenge_id for challenge_id in mastery_proofs
                if any(
                    branch["mastery_challenge"] == challenge_id
                    for branches in public_progression_manifest()["branches"][unit_id].values()
                    for branch in branches
                )
            ),
        })
    if not progress:
        progress_view = {
            "started": False,
            "current_encounter": FIRST_ENCOUNTER,
            "completed": [],
            "memories": [],
            "pending_memory": None,
            "route_choices": {},
        }
    else:
        progress_view = {
            "started": True,
            "current_encounter": progress["current_encounter"],
            "completed": progress["completed"],
            "memories": progress["memories"],
            "pending_memory": _pending_memory(progress),
            "route_choices": progress.get("route_choices", {}),
        }
    progress_view["next_step"] = _next_step(progress_view)
    active_view = None
    if active:
        active_view = {
            "run_id": active["id"],
            "revision": active["revision"],
            **combat.public_state(active["state"]),
        }
    return {
        "content": content_manifest(),
        "progress": progress_view,
        "active_run": active_view,
        "stats": stats,
        "units": units,
    }


async def choose_unit_branch(
    db, user_id: int, unit_id: str, branch_id: str
) -> dict[str, Any]:
    found = branch_by_id(branch_id)
    if not found or found[0] != unit_id:
        raise ReconstructionError("Эта ветвь не принадлежит выбранному юниту.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        try:
            result = await unit_repo.choose_branch(
                db,
                user_id=user_id,
                game_version=GAME_VERSION,
                unit_id=unit_id,
                branch_id=branch_id,
            )
        except ValueError as exc:
            raise ReconstructionError(str(exc)) from exc
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="progression_upgrade",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source="mini_app",
            payload={
                "entity": f"unit:{unit_id}:branch:{found[1]}",
                "from_value": "unselected",
                "to_value": branch_id,
                "resource_cost": {"mora": 0, "diamonds": 0, "zarniki": 0},
                "trigger": f"mastery:{found[2]['mastery_challenge']}",
            },
            idempotency_key=f"unit-branch:{GAME_VERSION}:{unit_id}:{found[1]}",
        )
        return result


async def start_encounter(
    db,
    user_id: int,
    encounter_id: str = FIRST_ENCOUNTER,
    *,
    practice: bool = False,
    source: str = "mini_app",
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
            replay_allowed = practice and encounter_id in progress["completed"]
            if not replay_allowed:
                raise ReconstructionError("Эта встреча ещё не является следующим шагом кампании.")
            if _pending_memory(progress):
                raise ReconstructionError("Сначала выбери постоянную Память за первую победу.")
        encounter = ENCOUNTERS.get(encounter_id)
        if not encounter:
            raise ReconstructionError("Неизвестная встреча.")
        if not encounter.get("implemented"):
            raise ReconstructionError("Следующая встреча ещё не включена в dev-срез.")
        # Новый забег обязан получать новый непредсказуемый seed. Привязка seed к
        # user_id делала все повторы одного игрока одинаковыми и превращала
        # записанный макрос в готовое решение будущих забегов.
        unit_progress = await unit_repo.list_progress(db, user_id, GAME_VERSION)
        selected_branches = {
            item["unit_id"]: list(item["branch_choices"].values())
            for item in unit_progress
            if item["branch_choices"]
        }
        state = combat.new_encounter(
            encounter_id,
            seed=secrets.randbelow(2**31 - 1) + 1,
            unit_branches=selected_branches,
        )
        timing.attach_server_clock(state)
        state["run_kind"] = "practice" if practice else "campaign"
        run_id = await repo.create_run(
            db, user_id, GAME_VERSION, BALANCE_VERSION, encounter_id, combat.dumps(state)
        )
        stats = await repo.record_run_started(db, user_id, GAME_VERSION)
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="battle_start",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            run_id=run_id,
            source=source,
            payload={
                "mode": (
                    "reconstruction_practice" if practice
                    else "reconstruction_clicker"
                ),
                "encounter_id": encounter_id,
                "squad": list(STARTER_UNITS),
                "levels": {
                    unit_id: next(
                        (
                            int(item["level"])
                            for item in unit_progress
                            if item["unit_id"] == unit_id
                        ),
                        1,
                    )
                    for unit_id in STARTER_UNITS
                },
                # У стартового отряда Reconstruction пока нет канонического CP.
                # None честнее выдуманного числа и явно показывает пробел модели.
                "combat_power": None,
                "modifiers": sorted(
                    branch_id
                    for branch_ids in selected_branches.values()
                    for branch_id in branch_ids
                ),
            },
            idempotency_key=f"run:{run_id}:started",
        )
        if not practice and encounter_id == FIRST_ENCOUNTER:
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="game_onboarding_step",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                source=source,
                payload={
                    "step": "first_encounter_started",
                    "result": "completed",
                    "encounter_id": encounter_id,
                },
                idempotency_key=f"onboarding:{GAME_VERSION}:first_encounter_started",
            )
        return {
            "run_id": run_id,
            "revision": 0,
            "resumed": False,
            "career_stats": stats,
            **combat.public_state(state),
        }


def _next_after(encounter_id: str) -> str:
    return {
        FIRST_ENCOUNTER: "e02_shattered_causeway",
        "e02_shattered_causeway": CHAPTER_ONE_PATH_GATE,
        "e03_ink_path": "e04_drowned_names",
        "e03_ash_path": "e04_drowned_names",
        "e04_drowned_names": "e05_mirror_courtyard",
        "e05_mirror_courtyard": "e06_archivist",
        "e06_archivist": "chapter_2_gate",
    }.get(encounter_id, encounter_id)


async def _record_shadow_reward(
    db,
    *,
    user_id: int,
    run_id: int,
    encounter_id: str,
    state: dict[str, Any],
    terminal: dict[str, Any],
) -> dict[str, Any]:
    """Persist one auditable projection; never mutate a player wallet."""
    existing = await shadow_repo.get_decision(db, terminal["id"])
    if existing is not None:
        return existing
    fingerprint = shadow_repo.seed_fingerprint(
        GAME_VERSION, encounter_id, int(state.get("seed", 0))
    )
    accepted_before = await shadow_repo.count_accepted_last_7_days(
        db, user_id, POLICY_VERSION
    )
    repeated_losses = await shadow_repo.count_same_seed_eligible_losses(
        db, user_id, fingerprint
    )
    mastery = state.get("mastery") or {}
    inputs = {
        "outcome": terminal["outcome"],
        "run_kind": "practice" if state.get("run_kind") == "practice" else "campaign",
        "accepted_results_last_7_days": accepted_before,
        "server_terminal_confirmed": True,
        "first_branch_reached": int(state.get("round", 0)) > 1 or bool(state.get("upgrades")),
        "correct_signals": max(0, int(mastery.get("correct_taps", 0))),
        "wrong_signals": max(0, int(mastery.get("mistakes", 0))),
        "missed_signals": max(0, int(mastery.get("missed_signals", 0))),
        "aborted": terminal["outcome"] == "cancelled",
        "quarantined": bool(terminal["integrity"]["review_required"]),
        "same_seed_eligible_losses_before": repeated_losses,
    }
    evaluated = evaluate_reconstruction_reward_shadow(**inputs)
    accuracy_percent = (
        round(float(evaluated.accuracy) * 100, 1)
        if evaluated.accuracy is not None else None
    )
    public = {
        "policy_version": evaluated.policy_version,
        "settlement_mode": evaluated.settlement_mode,
        "settled": False,
        "eligible": evaluated.eligible,
        "reason": evaluated.reason,
        "accepted_result_ordinal": evaluated.accepted_result_ordinal,
        "tier": evaluated.tier,
        "projected": {
            "mora": evaluated.mora,
            "lead_unit_xp": evaluated.lead_unit_xp,
            "support_unit_xp_each": evaluated.support_unit_xp_each,
        },
        "accuracy_percent": accuracy_percent,
        "provenance": evaluated.provenance,
    }
    return await shadow_repo.save_decision(
        db,
        terminal_result_id=terminal["id"],
        user_id=user_id,
        run_id=run_id,
        game_version=GAME_VERSION,
        balance_version=BALANCE_VERSION,
        policy_version=POLICY_VERSION,
        outcome=terminal["outcome"],
        run_kind=inputs["run_kind"],
        fingerprint=fingerprint,
        eligible=evaluated.eligible,
        reason=evaluated.reason,
        accepted_result_ordinal=evaluated.accepted_result_ordinal,
        decision=public,
        inputs=inputs,
    )


async def apply_run_action(
    db,
    user_id: int,
    run_id: int,
    action_id: str,
    expected_revision: int,
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
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ReconstructionError("expected_revision должен быть неотрицательным числом.")
        if expected_revision != int(run["revision"]):
            raise ReconstructionConflict(
                "Забег уже изменился в другой вкладке. Обнови состояние боя."
            )

        state = run["state"]
        run_mode = (
            "reconstruction_practice"
            if state.get("run_kind") == "practice"
            else "reconstruction_clicker"
        )
        action_type = str(action.get("type") or "")
        round_before = int(state.get("round", 0))
        challenge_before = copy.deepcopy(state.get("challenge") or {})
        offered_before = [
            str(option.get("id"))
            for option in state.get("reward_options", [])
            if option.get("id")
        ]
        timed_action, timing_result = timing.server_timed_action(state, action)
        result = combat.apply_action(state, timed_action)
        if not result.get("ok"):
            raise ReconstructionError(str(result.get("error") or "Действие отклонено."))
        result["timing"] = timing_result
        integrity.record_strike(state, result.get("strike"))
        # Межволновый выбор — часть незавершённого забега. В БД такой run остаётся
        # active, иначе частичный unique-index и optimistic UPDATE сочтут его
        # завершённым и не дадут принять выбранное усиление.
        storage_status = state["status"] if state["status"] in ("won", "lost") else "active"
        new_revision = await repo.save_run_state(
            db, run_id, int(run["revision"]), combat.dumps(state), storage_status
        )
        if new_revision is None:
            raise ReconstructionConflict("Состояние уже изменилось в другой вкладке. Обновляю бой.")
        result["server_revision"] = new_revision

        strike = result.get("strike")
        if isinstance(strike, dict):
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="battle_action",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                run_id=run_id,
                source=source,
                payload={
                    "mode": run_mode,
                    "encounter_id": run["encounter_id"],
                    "round": round_before,
                    "action": "resolve_signal",
                    "challenge_id": action.get("challenge_id"),
                    "target_slot": action.get("target_slot"),
                    "accepted": bool(strike.get("accepted")),
                    "correct": bool(strike.get("correct")),
                    "critical": bool(strike.get("critical", False)),
                    "damage": strike.get("damage"),
                    "discharged": bool(strike.get("discharged", False)),
                    "reason": strike.get("reason"),
                    "reaction_ms": strike.get("reaction_ms"),
                    "server_delta_ms": timing_result["applied_ms"],
                    "server_revision": new_revision,
                    "integrity_status": integrity.verdict(state)["status"],
                    "legal_options_count": len(challenge_before.get("options") or []),
                    "branch_results": {
                        key: strike[key]
                        for key in ("seam_result", "forbidden_result")
                        if strike.get(key) is not None
                    },
                },
                idempotency_key=f"run:{run_id}:action:{action_id}",
            )
        elif action_type == "choose_upgrade":
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="battle_upgrade",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                run_id=run_id,
                source=source,
                payload={
                    "mode": run_mode,
                    "encounter_id": run["encounter_id"],
                    "round": round_before,
                    "upgrade_id": str(action.get("upgrade_id") or ""),
                    "offered_ids": offered_before,
                    "server_revision": new_revision,
                },
                idempotency_key=f"run:{run_id}:action:{action_id}",
            )
        elif action_type == "branch_action":
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="battle_branch_action",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                run_id=run_id,
                source=source,
                payload={
                    "mode": run_mode,
                    "encounter_id": run["encounter_id"],
                    "round": round_before,
                    "branch_id": str(result.get("branch") or ""),
                    "command": str(action.get("command") or ""),
                    "result": str(result.get("result") or ""),
                    "damage": result.get("damage"),
                    "server_revision": new_revision,
                },
                idempotency_key=f"run:{run_id}:action:{action_id}",
            )

        pending_memory = None
        career_stats = None
        terminal = None
        shadow_reward = None
        mastery_proofs = None
        next_step = None
        if state["status"] in ("won", "lost"):
            terminal = integrity.terminal_result(
                run_id=run_id,
                revision=new_revision,
                outcome=state["status"],
                state=state,
            )
            shadow_reward = await _record_shadow_reward(
                db,
                user_id=user_id,
                run_id=run_id,
                encounter_id=run["encounter_id"],
                state=state,
                terminal=terminal,
            )
            if state["status"] == "won" and state.get("run_kind") != "practice":
                recorded_proofs = await unit_repo.record_mastery_proofs(
                    db,
                    user_id=user_id,
                    game_version=GAME_VERSION,
                    terminal_result_id=terminal["id"],
                    encounter_id=run["encounter_id"],
                    challenge_ids=mastery_proofs_from_terminal(state),
                )
                mastery_proofs = sorted(recorded_proofs)
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="battle_end",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                run_id=run_id,
                source=source,
                payload={
                    "mode": run_mode,
                    "encounter_id": run["encounter_id"],
                    "result": state["status"],
                    "outcome_reason": state.get("outcome_reason"),
                    "rounds": state["round"],
                    "metrics": state["mastery"],
                    "terminal_result": terminal,
                    "shadow_reward": shadow_reward,
                    "branches": sorted(
                        branch_id
                        for raw in (state.get("unit_branches") or {}).values()
                        for branch_id in (raw if isinstance(raw, list) else [raw])
                    ),
                },
                idempotency_key=f"run:{run_id}:ended",
            )
            # Проигрыш остаётся battle_end попытки, но не закрывает шаг онбординга.
            # Иначе фиксированный ключ шага запомнит `lost`, а последующая победа
            # справедливо станет idempotency-конфликтом с другим payload.
            if (
                state["status"] == "won"
                and state.get("run_kind") != "practice"
                and run["encounter_id"] == FIRST_ENCOUNTER
            ):
                await event_repo.record_event(
                    db,
                    user_id=user_id,
                    event_name="game_onboarding_step",
                    game_version=GAME_VERSION,
                    balance_version=BALANCE_VERSION,
                    source=source,
                    payload={
                        "step": "first_encounter_completed",
                        "result": "completed",
                        "encounter_id": run["encounter_id"],
                        "elapsed_ms": max(0, int(state["mastery"].get("elapsed_ms", 0))),
                    },
                    idempotency_key=f"onboarding:{GAME_VERSION}:first_encounter_completed",
                )
            career_stats = await repo.record_run_completed(
                db,
                user_id,
                GAME_VERSION,
                outcome=state["status"],
                mastery=state["mastery"],
                best_combo=int(state["combo"]["max"]),
                upgrades=list(state["upgrades"]),
            )
            if state["status"] == "won" and state.get("run_kind") != "practice":
                progress = await repo.ensure_progress(db, user_id, GAME_VERSION, FIRST_ENCOUNTER)
                completed = list(dict.fromkeys([*progress["completed"], run["encounter_id"]]))
                await repo.save_progress(
                    db,
                    user_id,
                    GAME_VERSION,
                    current_encounter=_next_after(run["encounter_id"]),
                    completed=completed,
                    memories=progress["memories"],
                    route_choices=progress.get("route_choices", {}),
                )
                refreshed = await repo.get_progress(db, user_id, GAME_VERSION)
                if refreshed:
                    pending_memory = _pending_memory(refreshed)
                    next_step = _next_step(refreshed)
            elif state["status"] == "lost":
                current = await repo.get_progress(db, user_id, GAME_VERSION)
                if current:
                    next_step = _next_step(current)

        response = {
            "run_id": run_id,
            "revision": new_revision,
            "turn": result,
            "terminal_result": terminal,
            "shadow_reward": shadow_reward,
            "mastery_proofs": mastery_proofs,
            "next_step": next_step,
            "pending_memory": pending_memory,
            "career_stats": career_stats,
            "idempotent_replay": False,
            **combat.public_state(state),
        }
        await repo.save_action_response(db, run_id, action_id, action, response)
        return response


async def cancel_run(
    db, user_id: int, run_id: int, *, source: str = "mini_app"
) -> dict[str, Any]:
    """Cancel an owned active run without rewards or a recorded defeat."""
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        run = await repo.get_run(db, run_id, user_id)
        if not run:
            raise ReconstructionError("Забег не найден.")
        if run["status"] == "cancelled":
            terminal = integrity.terminal_result(
                run_id=run_id,
                revision=int(run["revision"]),
                outcome="cancelled",
                state=run["state"],
            )
            return {
                "ok": True,
                "run_id": run_id,
                "revision": int(run["revision"]),
                "terminal_result": terminal,
                "shadow_reward": await shadow_repo.get_decision(db, terminal["id"]),
                "idempotent_replay": True,
            }
        if run["status"] != "active":
            raise ReconstructionConflict("Завершённый забег нельзя отменить.")
        state = run["state"]
        new_revision = await repo.save_run_state(
            db,
            run_id,
            int(run["revision"]),
            combat.dumps(state),
            "cancelled",
        )
        if new_revision is None:
            raise ReconstructionConflict("Забег уже изменился в другой вкладке.")
        terminal = integrity.terminal_result(
            run_id=run_id,
            revision=new_revision,
            outcome="cancelled",
            state=state,
        )
        shadow_reward = await _record_shadow_reward(
            db,
            user_id=user_id,
            run_id=run_id,
            encounter_id=run["encounter_id"],
            state=state,
            terminal=terminal,
        )
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="battle_end",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            run_id=run_id,
            source=source,
            payload={
                "mode": (
                    "reconstruction_practice"
                    if state.get("run_kind") == "practice"
                    else "reconstruction_clicker"
                ),
                "encounter_id": run["encounter_id"],
                "result": "cancelled",
                "outcome_reason": "player_restart",
                "rounds": int(state.get("round", 0)),
                "metrics": state.get("mastery", {}),
                "terminal_result": terminal,
                "shadow_reward": shadow_reward,
            },
            idempotency_key=f"run:{run_id}:ended",
        )
        return {
            "ok": True,
            "run_id": run_id,
            "revision": new_revision,
            "terminal_result": terminal,
            "shadow_reward": shadow_reward,
            "idempotent_replay": False,
        }


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
            route_choices=progress.get("route_choices", {}),
        )
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="progression_upgrade",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={
                "entity": "memory",
                "from_value": None,
                "to_value": memory_id,
                "resource_cost": {},
                "trigger": f"reward:{FIRST_ENCOUNTER}",
            },
            idempotency_key=f"progression:{GAME_VERSION}:memory:{FIRST_ENCOUNTER}",
        )
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="game_onboarding_step",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={
                "step": "first_reward_chosen",
                "result": "completed",
                "encounter_id": FIRST_ENCOUNTER,
            },
            idempotency_key=f"onboarding:{GAME_VERSION}:first_reward_chosen",
        )
        return {
            "ok": True,
            "memory_id": memory_id,
            "memory": copy.deepcopy(MEMORIES[memory_id]),
            "next_step": _next_step({**progress, "memories": memories}),
            "idempotent_replay": False,
        }


async def choose_chronicle_path(
    db, user_id: int, path_id: str, *, source: str = "mini_app"
) -> dict[str, Any]:
    target = CHAPTER_ONE_PATHS.get(str(path_id))
    if not target:
        raise ReconstructionError("Неизвестная тропа Хроники.")
    if not ENCOUNTERS[target].get("implemented"):
        raise ReconstructionError("Эта тропа ещё не включена в dev-срез.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        progress = await repo.get_progress(db, user_id, GAME_VERSION)
        if not progress:
            raise ReconstructionError("Сначала начни кампанию.")
        route_choices = dict(progress.get("route_choices") or {})
        existing = route_choices.get("chapter_1")
        if existing:
            if existing != path_id:
                raise ReconstructionError("Тропа первой главы уже выбрана.")
            return {
                "ok": True, "path_id": path_id, "encounter_id": target,
                "next_step": _next_step(progress), "idempotent_replay": True,
            }
        if progress["current_encounter"] != CHAPTER_ONE_PATH_GATE:
            raise ReconstructionError("Сейчас нет незавершённого выбора тропы.")
        if await repo.get_active_run(db, user_id, GAME_VERSION):
            raise ReconstructionConflict("Сначала заверши текущую встречу.")
        route_choices["chapter_1"] = path_id
        await repo.save_progress(
            db,
            user_id,
            GAME_VERSION,
            current_encounter=target,
            completed=progress["completed"],
            memories=progress["memories"],
            route_choices=route_choices,
        )
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="progression_upgrade",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={
                "entity": "chronicle:chapter_1:path",
                "from_value": "unselected",
                "to_value": path_id,
                "resource_cost": {},
                "trigger": "chronicle:e02:first_clear",
            },
            idempotency_key=f"chronicle-path:{GAME_VERSION}:chapter_1",
        )
        next_progress = {
            **progress,
            "current_encounter": target,
            "route_choices": route_choices,
        }
        return {
            "ok": True, "path_id": path_id, "encounter_id": target,
            "next_step": _next_step(next_progress), "idempotent_replay": False,
        }
