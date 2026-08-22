"""Application-service contract without PostgreSQL: locks/idempotency/progress."""
from __future__ import annotations

import asyncio
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.reconstruction import GAME_VERSION
from services import reconstruction as service


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Connection:
    def transaction(self):
        return _Transaction()


class _DB:
    connection = _Connection()


class MemoryRepo:
    def __init__(self):
        self.progress = None
        self.runs = {}
        self.actions = {}
        self.events = {}
        self.shadow_decisions = {}
        self.shadow_rows = []
        self.mastery_proofs = {}
        self.unit_branches = {}
        self.unit_progress_rows = []
        self.stats = service.repo.empty_stats()
        self.next_id = 1

    async def lock_user(self, _db, _user_id):
        return None

    async def get_progress(self, _db, user_id, game_version):
        if not self.progress:
            return None
        return copy.deepcopy(self.progress)

    async def ensure_progress(self, _db, user_id, game_version, first_encounter):
        if not self.progress:
            self.progress = {
                "user_id": user_id,
                "game_version": game_version,
                "current_encounter": first_encounter,
                "completed": [],
                "memories": [],
                "route_choices": {},
            }
        return copy.deepcopy(self.progress)

    async def save_progress(self, _db, user_id, game_version, **values):
        self.progress.update(copy.deepcopy(values))

    async def get_active_run(self, _db, user_id, game_version):
        row = next((run for run in self.runs.values() if run["status"] == "active"), None)
        return copy.deepcopy(row)

    async def get_run(self, _db, run_id, user_id):
        run = self.runs.get(run_id)
        if not run or run["user_id"] != user_id:
            return None
        return copy.deepcopy(run)

    async def create_run(self, _db, user_id, game_version, balance_version, encounter_id, state_json):
        from services.reconstruction_combat import loads
        run_id = self.next_id
        self.next_id += 1
        self.runs[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "game_version": game_version,
            "balance_version": balance_version,
            "encounter_id": encounter_id,
            "state": loads(state_json),
            "status": "active",
            "revision": 0,
        }
        return run_id

    async def save_run_state(self, _db, run_id, expected_revision, state_json, status):
        from services.reconstruction_combat import loads
        run = self.runs[run_id]
        if run["revision"] != expected_revision or run["status"] != "active":
            return None
        run["revision"] += 1
        run["state"] = loads(state_json)
        run["status"] = status
        return run["revision"]

    async def get_action_response(self, _db, run_id, action_id):
        value = self.actions.get((run_id, action_id))
        return copy.deepcopy(value)

    async def save_action_response(self, _db, run_id, action_id, request, response):
        self.actions.setdefault((run_id, action_id), copy.deepcopy(response))

    async def record_event(self, _db, **event):
        key = (event["user_id"], event.get("idempotency_key"))
        if key in self.events:
            return False
        self.events[key] = copy.deepcopy(event)
        return True

    async def get_shadow_decision(self, _db, terminal_result_id):
        return copy.deepcopy(self.shadow_decisions.get(terminal_result_id))

    async def count_accepted_last_7_days(self, _db, user_id, policy_version):
        return sum(
            1 for row in self.shadow_rows
            if row["user_id"] == user_id
            and row["policy_version"] == policy_version
            and row["eligible"]
        )

    async def count_same_seed_eligible_losses(self, _db, user_id, fingerprint):
        return sum(
            1 for row in self.shadow_rows
            if row["user_id"] == user_id
            and row["fingerprint"] == fingerprint
            and row["outcome"] == "lost"
            and row["eligible"]
        )

    async def save_shadow_decision(self, _db, **values):
        terminal_id = values["terminal_result_id"]
        decision = copy.deepcopy(dict(values["decision"]))
        existing = self.shadow_decisions.get(terminal_id)
        if existing is not None:
            assert existing == decision
            return copy.deepcopy(existing)
        self.shadow_decisions[terminal_id] = decision
        self.shadow_rows.append(copy.deepcopy(values))
        return copy.deepcopy(decision)

    async def get_stats(self, _db, user_id, game_version):
        return copy.deepcopy(self.stats)

    async def record_run_started(self, _db, user_id, game_version):
        self.stats["runs_started"] += 1
        return copy.deepcopy(self.stats)

    async def record_run_completed(
        self, _db, user_id, game_version, *, outcome, mastery, best_combo, upgrades
    ):
        self.stats["runs_won"] += int(outcome == "won")
        self.stats["runs_lost"] += int(outcome == "lost")
        for key in (
            "total_taps", "correct_taps", "mistakes", "missed_signals",
            "critical_taps", "discharges",
        ):
            self.stats[key] += int(mastery.get(key, 0))
        self.stats["best_combo"] = max(self.stats["best_combo"], int(best_combo))
        self.stats["total_play_ms"] += int(mastery.get("elapsed_ms", 0))
        if outcome == "won":
            elapsed = int(mastery.get("elapsed_ms", 0))
            fastest = self.stats["fastest_win_ms"]
            self.stats["fastest_win_ms"] = elapsed if fastest is None else min(fastest, elapsed)
        for upgrade_id in upgrades:
            self.stats["upgrades"][upgrade_id] = self.stats["upgrades"].get(upgrade_id, 0) + 1
        attempts = self.stats["correct_taps"] + self.stats["mistakes"] + self.stats["missed_signals"]
        self.stats["accuracy"] = round(self.stats["correct_taps"] / attempts * 100, 1) if attempts else None
        return copy.deepcopy(self.stats)

    async def list_unit_progress(self, _db, _user_id, _game_version):
        return copy.deepcopy(self.unit_progress_rows)

    async def get_mastery_proofs(self, _db, _user_id, _game_version):
        return copy.deepcopy(self.mastery_proofs)

    async def record_mastery_proofs(
        self, _db, *, terminal_result_id, encounter_id, challenge_ids, **_values
    ):
        for challenge_id in challenge_ids:
            self.mastery_proofs.setdefault(challenge_id, {
                "terminal_result_id": terminal_result_id,
                "encounter_id": encounter_id,
                "proven_at": "2026-08-22T00:00:00Z",
            })
        return copy.deepcopy(self.mastery_proofs)

    async def choose_unit_branch(
        self, _db, *, unit_id, branch_id, **_values
    ):
        key = (unit_id, 5)
        prior = self.unit_branches.get(key)
        if prior and prior != branch_id:
            raise ValueError("This milestone already has a branch; use the respec contract.")
        self.unit_branches[key] = branch_id
        return {
            "applied": prior is None,
            "progress": service.unit_progress_view(unit_id, 1190, {"5": branch_id}),
        }


async def main():
    memory = MemoryRepo()
    original = {}
    original_randbelow = service.secrets.randbelow
    original_server_now_ms = service.timing.server_now_ms
    fake_clock = {"now": 1_000_000}

    def server_now_ms():
        fake_clock["now"] += 100
        return fake_clock["now"]

    service.timing.server_now_ms = server_now_ms
    seeded_runs = iter((101, 202, 303, 404, 505, 606))
    service.secrets.randbelow = lambda _upper: next(seeded_runs)
    for name in (
        "lock_user", "get_progress", "ensure_progress", "save_progress",
        "get_active_run", "get_run", "create_run", "save_run_state",
        "get_action_response", "save_action_response",
        "get_stats", "record_run_started", "record_run_completed",
    ):
        original[name] = getattr(service.repo, name)
        setattr(service.repo, name, getattr(memory, name))
    original_event_writer = service.event_repo.record_event
    service.event_repo.record_event = memory.record_event
    original_units = {}
    for name, replacement in (
        ("list_progress", memory.list_unit_progress),
        ("get_mastery_proofs", memory.get_mastery_proofs),
        ("record_mastery_proofs", memory.record_mastery_proofs),
        ("choose_branch", memory.choose_unit_branch),
    ):
        original_units[name] = getattr(service.unit_repo, name)
        setattr(service.unit_repo, name, replacement)
    original_shadow = {}
    for name, replacement in (
        ("get_decision", memory.get_shadow_decision),
        ("count_accepted_last_7_days", memory.count_accepted_last_7_days),
        ("count_same_seed_eligible_losses", memory.count_same_seed_eligible_losses),
        ("save_decision", memory.save_shadow_decision),
    ):
        original_shadow[name] = getattr(service.shadow_repo, name)
        setattr(service.shadow_repo, name, replacement)
    try:
        db = _DB()
        user_id = 7001
        started = await service.start_encounter(db, user_id)
        resumed = await service.start_encounter(db, user_id)
        assert started["run_id"] == resumed["run_id"] and resumed["resumed"] is True
        assert started["seed"] == 102
        run_id = started["run_id"]

        try:
            await service.apply_run_action(
                db,
                user_id + 1,
                run_id,
                "foreign",
                0,
                {"type": "frame", "delta_ms": 100},
            )
            raise AssertionError("чужой пользователь получил доступ к run")
        except service.ReconstructionError as exc:
            assert str(exc) == "Встреча не найдена."

        counter = 0

        async def apply(action):
            nonlocal counter
            counter += 1
            return await service.apply_run_action(
                db,
                user_id,
                run_id,
                f"a{counter}",
                memory.runs[run_id]["revision"],
                action,
            )

        # Открываем первый одноразовый сигнал и проверяем idempotency на ударе.
        while not memory.runs[run_id]["state"]["challenge"]["active"]:
            await apply({"type": "frame", "delta_ms": 100})
        assert not any(
            event["event_name"] == "battle_action" for event in memory.events.values()
        ), "служебные frame-тики попали в meaningful telemetry"
        state = memory.runs[run_id]["state"]
        challenge = state["challenge"]
        slot = next(
            option["slot"] for option in challenge["options"]
            if option["symbol"] == challenge["target_symbol"]
        )
        action_id = f"a{counter + 1}"
        first = await service.apply_run_action(
            db, user_id, run_id, action_id,
            memory.runs[run_id]["revision"],
            {
                "type": "frame", "delta_ms": 100,
                "challenge_id": challenge["id"], "target_slot": slot,
            },
        )
        counter += 1
        replay = await service.apply_run_action(
            db, user_id, run_id, action_id,
            first["revision"],
            {"type": "strike", "challenge_id": challenge["id"], "target_slot": "left"},
        )
        assert replay["idempotent_replay"] is True
        assert replay["revision"] == first["revision"]
        assert memory.runs[run_id]["state"]["mastery"]["correct_taps"] == 1
        try:
            await service.apply_run_action(
                db, user_id + 1, run_id, action_id,
                first["revision"],
                {"type": "strike", "challenge_id": challenge["id"], "target_slot": slot},
            )
            raise AssertionError("idempotency-кэш раскрыл чужой run")
        except service.ReconstructionError as exc:
            assert str(exc) == "Встреча не найдена."

        snapshot = copy.deepcopy(memory.runs[run_id])
        try:
            await service.apply_run_action(
                db,
                user_id,
                run_id,
                "stale-revision",
                first["revision"] - 1,
                {"type": "frame", "delta_ms": 100},
            )
            raise AssertionError("устаревшая вкладка изменила run")
        except service.ReconstructionConflict as exc:
            assert "другой вкладке" in str(exc)
        assert memory.runs[run_id] == snapshot

        # Полный забег проходит через два межволновых reward-state, которые в БД
        # обязаны оставаться active до финальной победы.
        result = first
        guard = 0
        while memory.runs[run_id]["state"]["status"] not in {"won", "lost"} and guard < 500:
            guard += 1
            state = memory.runs[run_id]["state"]
            if state["status"] == "reward":
                result = await apply({
                    "type": "choose_upgrade",
                    "upgrade_id": state["reward_options"][0]["id"],
                })
                assert memory.runs[run_id]["status"] == "active"
                continue
            challenge = state["challenge"]
            if not challenge["active"]:
                result = await apply({"type": "frame", "delta_ms": 100})
                continue
            slot = next(
                option["slot"] for option in challenge["options"]
                if option["symbol"] == challenge["target_symbol"]
            )
            result = await apply({
                "type": "strike", "challenge_id": challenge["id"], "target_slot": slot,
            })
        assert result and result["status"] == "won"
        assert result["accuracy"] == 100.0
        assert memory.progress["completed"] == [service.FIRST_ENCOUNTER]
        assert memory.progress["current_encounter"] == "e02_shattered_causeway"
        completed_events = [event for event in memory.events.values() if event["event_name"] == "battle_end"]
        assert len(completed_events) == 1
        terminal = result["terminal_result"]
        assert terminal["id"] == f"reconstruction:{run_id}:terminal"
        assert terminal["outcome"] == "won"
        assert terminal["server_revision"] == result["revision"]
        assert terminal["integrity"]["automatic_ban"] is False
        shadow = result["shadow_reward"]
        assert shadow["settlement_mode"] == "shadow_only" and shadow["settled"] is False
        assert shadow["eligible"] is True and shadow["accepted_result_ordinal"] == 1
        assert shadow["projected"] == {
            "mora": 100, "lead_unit_xp": 100, "support_unit_xp_each": 60,
        }
        assert len(memory.shadow_rows) == 1
        assert completed_events[0]["payload"]["terminal_result"] == terminal
        assert completed_events[0]["payload"]["shadow_reward"] == shadow
        action_events = [event for event in memory.events.values() if event["event_name"] == "battle_action"]
        upgrade_events = [event for event in memory.events.values() if event["event_name"] == "battle_upgrade"]
        assert len(action_events) == memory.stats["total_taps"]
        assert len(upgrade_events) == 2
        assert all(event["payload"]["server_revision"] >= 1 for event in upgrade_events)
        assert all(event["payload"]["legal_options_count"] == 3 for event in action_events)
        assert all(event["payload"]["reaction_ms"] >= 0 for event in action_events)
        assert all(event["payload"]["server_revision"] >= 1 for event in action_events)
        assert memory.stats["runs_started"] == 1
        assert memory.stats["runs_won"] == 1 and memory.stats["runs_lost"] == 0
        assert memory.stats["accuracy"] == 100.0
        assert memory.stats["best_combo"] == result["combo"]["max"]
        assert sum(memory.stats["upgrades"].values()) == 2
        overview = await service.overview(db, user_id)
        assert overview["stats"]["runs_won"] == 1
        assert len(overview["units"]) == 3
        assert all(unit["level"] == 1 for unit in overview["units"])
        selected_branch = await service.choose_unit_branch(
            db, user_id, "r_oath_bell", "bell_broken_vow"
        )
        selected_branch_again = await service.choose_unit_branch(
            db, user_id, "r_oath_bell", "bell_broken_vow"
        )
        assert selected_branch["applied"] is True
        assert selected_branch_again["applied"] is False
        economy_policy = overview["content"]["economy_policy"]
        assert economy_policy["settlement_mode"] == "shadow_only"
        assert economy_policy["real_rewards_enabled"] is False
        assert economy_policy["unit_level_cap_xp"] == 36_096
        unit_progression = overview["content"]["unit_progression"]
        assert unit_progression["implemented_branch_levels"] == [5]
        assert unit_progression["paid_xp_allowed"] is False
        assert all(
            len(milestones["5"]) == 2
            for milestones in unit_progression["branches"].values()
        )
        timing_policy = overview["content"]["timing_policy"]
        assert timing_policy["mode"] == "server_wall_clock"
        assert timing_policy["client_delta_ms_ignored"] is True
        integrity_policy = overview["content"]["integrity_policy"]
        assert integrity_policy["mode"] == "shadow_review"
        assert integrity_policy["automatic_ban"] is False

        chosen = await service.choose_memory(db, user_id, "m_mobile_oath")
        chosen_again = await service.choose_memory(db, user_id, "m_mobile_oath")
        assert chosen["idempotent_replay"] is False
        assert chosen_again["idempotent_replay"] is True
        assert chosen["next_step"]["type"] == "play_encounter"
        assert chosen["next_step"]["encounter_id"] == "e02_shattered_causeway"
        assert memory.progress["memories"] == ["m_mobile_oath"]
        assert memory.progress["game_version"] == GAME_VERSION
        assert any(
            event["event_name"] == "progression_upgrade" for event in memory.events.values()
        )
        onboarding_steps = {
            event["payload"]["step"]
            for event in memory.events.values()
            if event["event_name"] == "game_onboarding_step"
        }
        assert onboarding_steps == {
            "first_encounter_started", "first_encounter_completed", "first_reward_chosen",
        }

        second = await service.start_encounter(db, user_id, "e02_shattered_causeway")
        assert second["run_kind"] == "campaign" and second["resumed"] is False
        assert second["seed"] == 203
        run_id = second["run_id"]
        result = second
        guard = 0
        while memory.runs[run_id]["state"]["status"] not in {"won", "lost"} and guard < 900:
            guard += 1
            state = memory.runs[run_id]["state"]
            if state["status"] == "reward":
                result = await apply({
                    "type": "choose_upgrade",
                    "upgrade_id": state["reward_options"][0]["id"],
                })
                continue
            challenge = state["challenge"]
            if not challenge["active"]:
                result = await apply({"type": "frame", "delta_ms": 100})
                continue
            slot = next(
                option["slot"] for option in challenge["options"]
                if option["symbol"] == challenge["target_symbol"]
            )
            result = await apply({
                "type": "strike", "challenge_id": challenge["id"], "target_slot": slot,
            })
        assert result["status"] == "won"
        assert result["outcome_reason"] == "lantern_delivered"
        assert result["pending_memory"] is None
        assert result["next_step"]["type"] == "choose_chronicle_path"
        assert {choice["id"] for choice in result["next_step"]["choices"]} == {"ink", "ash"}
        assert memory.progress["completed"] == [
            service.FIRST_ENCOUNTER, "e02_shattered_causeway",
        ]
        assert memory.progress["current_encounter"] == service.CHAPTER_ONE_PATH_GATE
        overview = await service.overview(db, user_id)
        assert overview["progress"]["next_step"]["type"] == "choose_chronicle_path"
        assert overview["stats"]["runs_started"] == 2
        assert overview["stats"]["runs_won"] == 2

        chosen_path = await service.choose_chronicle_path(db, user_id, "ash")
        chosen_path_again = await service.choose_chronicle_path(db, user_id, "ash")
        assert chosen_path["idempotent_replay"] is False
        assert chosen_path_again["idempotent_replay"] is True
        assert chosen_path["next_step"]["type"] == "play_encounter"
        assert chosen_path["next_step"]["encounter_id"] == "e03_ash_path"
        assert memory.progress["current_encounter"] == "e03_ash_path"
        assert memory.progress["route_choices"] == {"chapter_1": "ash"}
        try:
            await service.choose_chronicle_path(db, user_id, "ink")
        except service.ReconstructionError as exc:
            assert "уже выбрана" in str(exc)
        else:
            raise AssertionError("Chronicle path changed after confirmation")

        memory.unit_progress_rows = [
            service.unit_progress_view(
                "r_red_seam", 1190, {"5": "seam_forbidden_repeat"}
            )
        ]
        third = await service.start_encounter(db, user_id, "e03_ash_path")
        assert third["seed"] == 304
        assert third["objective_state"]["kind"] == "ash_fire"
        run_id = third["run_id"]
        result = third
        guard = 0
        while memory.runs[run_id]["state"]["status"] not in {"won", "lost"} and guard < 1800:
            guard += 1
            state = memory.runs[run_id]["state"]
            if state["status"] == "reward":
                result = await apply({
                    "type": "choose_upgrade",
                    "upgrade_id": state["reward_options"][0]["id"],
                })
                continue
            challenge = state["challenge"]
            if not challenge["active"]:
                result = await apply({"type": "frame", "delta_ms": 100})
                continue
            slot = next(
                option["slot"] for option in challenge["options"]
                if option["symbol"] == challenge["target_symbol"]
            )
            result = await apply({
                "type": "strike", "challenge_id": challenge["id"], "target_slot": slot,
            })
        assert result["status"] == "won" and result["outcome_reason"] == "fire_carried"
        assert result["next_step"]["type"] == "play_encounter"
        assert result["next_step"]["encounter_id"] == "e04_drowned_names"
        assert memory.progress["current_encounter"] == "e04_drowned_names"

        fourth = await service.start_encounter(db, user_id, "e04_drowned_names")
        assert fourth["seed"] == 405
        assert fourth["objective_state"]["kind"] == "drowned_sequence"
        assert "sequence" not in fourth["objective_state"]
        run_id = fourth["run_id"]
        result = fourth
        guard = 0
        while memory.runs[run_id]["state"]["status"] not in {"won", "lost"} and guard < 1800:
            guard += 1
            state = memory.runs[run_id]["state"]
            if state["status"] == "reward":
                result = await apply({
                    "type": "choose_upgrade",
                    "upgrade_id": state["reward_options"][0]["id"],
                })
                continue
            challenge = state.get("challenge")
            if not challenge or not challenge["active"]:
                result = await apply({"type": "frame", "delta_ms": 100})
                continue
            slot = next(
                option["slot"] for option in challenge["options"]
                if option["symbol"] == challenge["target_symbol"]
            )
            result = await apply({
                "type": "strike", "challenge_id": challenge["id"], "target_slot": slot,
            })
        assert result["status"] == "won"
        assert result["outcome_reason"] == "drowned_names_released"
        assert result["next_step"]["type"] == "play_encounter"
        assert result["next_step"]["encounter_id"] == "e05_mirror_courtyard"
        assert memory.progress["current_encounter"] == "e05_mirror_courtyard"

        fifth = await service.start_encounter(db, user_id, "e05_mirror_courtyard")
        assert fifth["seed"] == 506
        assert fifth["objective_state"]["kind"] == "mirror_rule"
        run_id = fifth["run_id"]
        result = fifth
        guard = 0
        while memory.runs[run_id]["state"]["status"] not in {"won", "lost"} and guard < 1800:
            guard += 1
            state = memory.runs[run_id]["state"]
            if state["status"] == "reward":
                result = await apply({
                    "type": "choose_upgrade",
                    "upgrade_id": state["reward_options"][0]["id"],
                })
                continue
            challenge = state.get("challenge")
            if not challenge or not challenge["active"]:
                result = await apply({"type": "frame", "delta_ms": 100})
                continue
            slot = next(
                option["slot"] for option in challenge["options"]
                if option["symbol"] == challenge["target_symbol"]
            )
            result = await apply({
                "type": "strike", "challenge_id": challenge["id"], "target_slot": slot,
            })
        assert result["status"] == "won" and result["outcome_reason"] == "courtyard_crossed"
        assert result["next_step"]["type"] == "development_gate"
        assert result["next_step"]["practice_encounter_id"] == "e05_mirror_courtyard"
        assert memory.progress["current_encounter"] == "e06_archivist"

        practice = await service.start_encounter(
            db, user_id, "e03_ash_path", practice=True
        )
        assert practice["run_kind"] == "practice" and practice["resumed"] is False
        assert practice["seed"] == 607
        practice_id = practice["run_id"]
        assert practice["unit_branches"] == {"r_red_seam": ["seam_forbidden_repeat"]}
        toggled = await service.apply_run_action(
            db, user_id, practice_id, "branch-toggle", 0,
            {"type": "branch_action", "command": "forbidden_toggle", "enabled": True},
        )
        assert toggled["branch_state"]["forbidden_mode"] is True
        assert any(
            event["event_name"] == "battle_branch_action"
            and event["payload"]["branch_id"] == "seam_forbidden_repeat"
            for event in memory.events.values()
        )
        cancelled = await service.cancel_run(db, user_id, practice_id)
        cancelled_again = await service.cancel_run(db, user_id, practice_id)
        assert cancelled["idempotent_replay"] is False
        assert cancelled_again["idempotent_replay"] is True
        assert cancelled_again["terminal_result"] == cancelled["terminal_result"]
        assert cancelled_again["shadow_reward"] == cancelled["shadow_reward"]
        assert cancelled["terminal_result"]["outcome"] == "cancelled"
        assert cancelled["shadow_reward"]["eligible"] is False
        assert cancelled["shadow_reward"]["reason"] == "practice"
        assert cancelled["shadow_reward"]["projected"]["mora"] == 0
        assert len(memory.shadow_rows) == 6
        assert memory.runs[practice_id]["status"] == "cancelled"
        cancel_events = [
            event for event in memory.events.values()
            if event["event_name"] == "battle_end"
            and event["payload"].get("result") == "cancelled"
        ]
        assert len(cancel_events) == 1
    finally:
        service.secrets.randbelow = original_randbelow
        service.timing.server_now_ms = original_server_now_ms
        for name, value in original.items():
            setattr(service.repo, name, value)
        service.event_repo.record_event = original_event_writer
        for name, value in original_shadow.items():
            setattr(service.shadow_repo, name, value)
        for name, value in original_units.items():
            setattr(service.unit_repo, name, value)

    print("reconstruction_service: terminal+shadow-reward+idempotency+progress  OK")


asyncio.run(main())
