"""Local-only HTTP bridge to the real Reconstruction 3.0 Python engine.

The Node preview server proxies ``/__reconstruction/*`` here, so the browser lab
tests the same pure engine as the backend instead of a JavaScript mock.
"""
from __future__ import annotations

import json
import os
import pathlib
import secrets
import sys
import threading
import copy
import time
import hashlib
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import (  # noqa: E402
    reconstruction,
    reconstruction_combat,
    reconstruction_integrity,
    reconstruction_timing,
    companions_v3,
)


PORT = int(os.environ.get("RECON_PREVIEW_PORT", "8403"))
MAX_PREVIEW_SESSIONS = 256
STATE_FILE = pathlib.Path(
    os.environ.get(
        "RECON_PREVIEW_STATE_FILE",
        f"/tmp/predvestnik-reconstruction-preview-{PORT}.json",
    )
)
_LOCK = threading.RLock()


def _load_states() -> dict[str, dict]:
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    states = {}
    for key, state in payload.items():
        if (
            isinstance(key, str)
            and isinstance(state, dict)
            and state.get("game_version") == reconstruction.GAME_VERSION
            and state.get("balance_version") == reconstruction.BALANCE_VERSION
        ):
            states[key] = state
    return states


def _save_states() -> None:
    temporary = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(_STATES, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(STATE_FILE)
    except OSError as exc:
        sys.stderr.write(f"[reconstruction-preview] state snapshot failed: {exc}\n")


_STATES = _load_states()
_COMPANION_STATES: dict[str, dict] = {}
# This is deliberately separate from the raw ``/_state`` lab state.  The
# public preview has to exercise FastAPI's production HTTP contract, while the
# raw endpoint remains a narrowly scoped harness for the pure combat engine.
_PRODUCTION_SESSIONS: dict[str, dict] = {}
_NEXT_PRODUCTION_RUN_ID = 1


def _new_state(
    encounter_id: str = reconstruction.FIRST_ENCOUNTER,
    unit_branches: dict[str, str | list[str]] | None = None,
    companion_role_id: str | None = None,
    difficulty_id: str | None = None,
):
    # У каждой вкладки и каждого reset свой run key: локальная статистика может
    # надёжно дедуплицировать завершение, а тестировщики не делят один seed.
    state = reconstruction_combat.new_encounter(
        seed=secrets.randbelow(2**31 - 1) + 1,
        encounter_id=encounter_id,
        unit_branches=unit_branches,
        companion_role_id=companion_role_id,
        difficulty_id=difficulty_id,
    )
    reconstruction_timing.attach_server_clock(state)
    return state


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "PredvestnikReconstructionPreview/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("[reconstruction-preview] " + fmt % args + "\n")
        sys.stdout.flush()

    def _send(self, status: int, value) -> None:
        body = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(size) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return None

    def _session_key(self) -> str:
        value = str(self.headers.get("X-Reconstruction-Session") or "default").strip()
        if not value or len(value) > 80 or not all(char.isalnum() or char in "-_" for char in value):
            return "default"
        return value

    def _state(self):
        key = self._session_key()
        state = _STATES.get(key)
        if state is None:
            if len(_STATES) >= MAX_PREVIEW_SESSIONS:
                _STATES.pop(next(iter(_STATES)))
            state = _new_state()
            _STATES[key] = state
            _save_states()
        return state

    def _companion_state(self):
        key = self._session_key()
        value = _COMPANION_STATES.get(key)
        if value is None:
            if len(_COMPANION_STATES) >= MAX_PREVIEW_SESSIONS:
                _COMPANION_STATES.pop(next(iter(_COMPANION_STATES)))
            value = {
                "active_pet_id": 901,
                "unlocked_roles": ["lantern", "guardian", "rhythm_keeper", "echo", "navigator", "archivist"],
                "selected_role_id": "lantern",
                "care": {"901": {"points": 6, "bank": 3, "last": "play"}},
                "actions": {},
                "contracts": [],
                "next_contract_id": 1,
            }
            _COMPANION_STATES[key] = value
        return value

    def _companion_overview(self):
        overview = companions_v3.preview_overview()
        saved = self._companion_state()
        overview["active_pet_id"] = saved["active_pet_id"]
        overview["unlocked_roles"] = list(saved["unlocked_roles"])
        overview["selected_role_id"] = saved["selected_role_id"]
        for pet in overview["pets"]:
            pet["active_companion"] = pet["id"] == saved["active_pet_id"]
            care = saved["care"].get(str(pet["id"]))
            if care:
                pet["bond"] = companions_v3.bond_progress(care["points"])
                pet["care_bank"] = care["bank"]
                pet["last_care_action"] = care["last"]
        now = time.time()
        for contract in saved["contracts"]:
            if contract["status"] == "active" and contract["ends_epoch"] <= now:
                contract["status"] = "ready"
        visible = []
        for contract in saved["contracts"]:
            if contract["status"] not in ("active", "ready", "claimed"):
                continue
            visible.append({
                "id": contract["id"], "pet_id": contract["pet_id"],
                "duration_hours": contract["duration_hours"], "route_id": contract["route_id"],
                "fixed_mora": contract["fixed_mora"], "discovery_id": contract["discovery_id"],
                "status": contract["status"],
                "remaining_sec": max(0, int(contract["ends_epoch"] - now)),
            })
        open_count = sum(item["status"] in ("active", "ready") for item in visible)
        reserved = sum(item["fixed_mora"] for item in visible)
        overview["expeditions"].update({
            "start_enabled": open_count < overview["expeditions"]["slots"],
            "open_slots": max(0, overview["expeditions"]["slots"] - open_count),
            "weekly_reserved_mora": reserved,
            "options": [
                asdict(companions_v3.quote_expedition(hours, reserved))
                for hours in companions_v3.EXPEDITION_OPTIONS
            ],
            "contracts": visible,
            "ready_count": sum(item["status"] == "ready" for item in visible),
        })
        return overview

    def _production_session(self) -> dict:
        """Return one local-only analogue of the authenticated server profile."""
        key = self._session_key()
        value = _PRODUCTION_SESSIONS.get(key)
        if value is None:
            if len(_PRODUCTION_SESSIONS) >= MAX_PREVIEW_SESSIONS:
                _PRODUCTION_SESSIONS.pop(next(iter(_PRODUCTION_SESSIONS)))
            value = {
                "run_id": None,
                "state": None,
                "active": False,
                "revision": 0,
                "known_runs": set(),
                "run_status": {},
                "actions": {},
                "cancel_responses": {},
                "progress": {
                    "started": False,
                    "current_encounter": reconstruction.FIRST_ENCOUNTER,
                    "completed": [],
                    "memories": [],
                    "route_choices": {},
                    "last_difficulty_profile": "standard",
                },
                "stats": {
                    "runs_started": 0, "runs_won": 0, "runs_lost": 0,
                    "correct_taps": 0, "total_taps": 0, "mistakes": 0,
                    "missed_signals": 0, "best_combo": 0,
                    "fastest_win_ms": None, "total_play_ms": 0, "upgrades": {},
                },
                "units": self._fresh_production_units(),
            }
            _PRODUCTION_SESSIONS[key] = value
        return value

    @staticmethod
    def _fresh_production_units() -> list[dict]:
        units = []
        for unit_id, unit in reconstruction.STARTER_UNITS.items():
            units.append({
                **reconstruction.unit_progress_view(unit_id, 0),
                "name": unit["name"],
                "short_name": unit["short_name"],
                "emoji": unit["emoji"],
                "proven_challenges": [],
            })
        return units

    @staticmethod
    def _production_progress_view(session: dict) -> dict:
        progress = session["progress"]
        return {
            **copy.deepcopy(progress),
            "pending_memory": reconstruction._pending_memory(progress),
            "next_step": reconstruction._next_step(progress),
        }

    @staticmethod
    def _production_run_view(session: dict) -> dict | None:
        state = session.get("state")
        if not session.get("active") or not state:
            return None
        return {
            "run_id": session["run_id"],
            "revision": session["revision"],
            **reconstruction_combat.public_state(state),
        }

    def _production_overview(self) -> dict:
        session = self._production_session()
        return {
            "content": reconstruction.content_manifest(),
            "progress": self._production_progress_view(session),
            "active_run": self._production_run_view(session),
            "stats": copy.deepcopy(session["stats"]),
            "units": copy.deepcopy(session["units"]),
        }

    @staticmethod
    def _record_preview_run_completion(session: dict, state: dict) -> dict:
        """Mirror public career counters without issuing a wallet mutation."""
        stats = session["stats"]
        mastery = state.get("mastery") or {}
        stats["runs_won"] += int(state.get("status") == "won")
        stats["runs_lost"] += int(state.get("status") == "lost")
        stats["correct_taps"] += max(0, int(mastery.get("correct_taps", 0)))
        stats["total_taps"] += max(0, int(mastery.get("total_taps", 0)))
        stats["mistakes"] += max(0, int(mastery.get("mistakes", 0)))
        stats["missed_signals"] += max(0, int(mastery.get("missed_signals", 0)))
        stats["best_combo"] = max(stats["best_combo"], int((state.get("combo") or {}).get("max", 0)))
        elapsed = max(0, int(mastery.get("elapsed_ms", 0)))
        stats["total_play_ms"] += elapsed
        if state.get("status") == "won":
            current = stats.get("fastest_win_ms")
            stats["fastest_win_ms"] = elapsed if current is None else min(int(current), elapsed)
        for upgrade_id in state.get("upgrades") or []:
            stats["upgrades"][upgrade_id] = int(stats["upgrades"].get(upgrade_id, 0)) + 1
        return copy.deepcopy(stats)

    @staticmethod
    def _preview_shadow_reward(state: dict, terminal: dict) -> dict:
        """Return the same public shadow-decision shape without a database write."""
        mastery = state.get("mastery") or {}
        progress_ratio, first_wave_ratio, completed_wave_count = reconstruction._reward_progress(state)
        evaluated = reconstruction.evaluate_reconstruction_reward_shadow(
            outcome=terminal["outcome"],
            run_kind=("practice" if state.get("run_kind") == "practice" else "campaign"),
            accepted_results_last_7_days=0,
            server_terminal_confirmed=True,
            first_branch_reached=completed_wave_count >= 1,
            correct_signals=max(0, int(mastery.get("correct_taps", 0))),
            wrong_signals=max(0, int(mastery.get("mistakes", 0))),
            missed_signals=max(0, int(mastery.get("missed_signals", 0))),
            aborted=terminal["outcome"] == "cancelled",
            quarantined=bool(terminal["integrity"]["review_required"]),
            same_seed_eligible_losses_before=0,
            reward_progress_ratio=progress_ratio,
            first_rewardable_progress_ratio=first_wave_ratio,
        )
        accuracy_percent = (
            round(float(evaluated.accuracy) * 100, 1)
            if evaluated.accuracy is not None else None
        )
        return {
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
            "progress": {
                "ratio": round(float(evaluated.progress_ratio or 0), 6),
                "completed_waves": completed_wave_count,
                "first_rewardable_ratio": round(float(first_wave_ratio), 6),
            },
            "loss_reward_factor": (
                round(float(evaluated.loss_reward_factor), 6)
                if evaluated.loss_reward_factor is not None else None
            ),
        }

    def _production_start(self, body: dict | None) -> None:
        global _NEXT_PRODUCTION_RUN_ID
        session = self._production_session()
        body = body or {}
        encounter_id = str(body.get("encounter_id") or reconstruction.FIRST_ENCOUNTER)
        practice = bool(body.get("practice"))
        requested_difficulty = body.get("difficulty_id")
        progress = session["progress"]
        current = str(progress.get("current_encounter") or reconstruction.FIRST_ENCOUNTER)
        active = self._production_run_view(session)
        if active:
            if active["encounter_id"] != encounter_id:
                return self._send(409, {"detail": "Сначала заверши текущую встречу."})
            if requested_difficulty is not None and requested_difficulty != active.get("difficulty", {}).get("id"):
                return self._send(409, {"detail": "Темп нельзя менять внутри незавершённого забега."})
            return self._send(200, {"resumed": True, **active})
        if current != encounter_id:
            replay_allowed = practice and encounter_id in progress.get("completed", [])
            if not replay_allowed:
                return self._send(400, {"detail": "Эта встреча ещё не является следующим шагом кампании."})
            if reconstruction._pending_memory(progress):
                return self._send(400, {"detail": "Сначала выбери постоянную Память за первую победу."})
        encounter = reconstruction.ENCOUNTERS.get(encounter_id)
        if not encounter or not encounter.get("implemented"):
            return self._send(400, {"detail": "Эта встреча ещё не доступна в local preview."})
        selected_difficulty = requested_difficulty or progress.get("last_difficulty_profile") or "standard"
        if selected_difficulty not in reconstruction.available_difficulties(encounter_id):
            selected_difficulty = "standard"
        try:
            selected_difficulty = reconstruction.normalize_difficulty_id(encounter_id, selected_difficulty)
        except ValueError as exc:
            return self._send(400, {"detail": str(exc)})
        selected_branches = {
            unit["unit_id"]: list(unit.get("branch_choices", {}).values())
            for unit in session["units"] if unit.get("branch_choices")
        }
        state = _new_state(
            encounter_id,
            selected_branches,
            self._companion_state()["selected_role_id"],
            selected_difficulty,
        )
        state["run_kind"] = "practice" if practice else "campaign"
        session["run_id"] = _NEXT_PRODUCTION_RUN_ID
        _NEXT_PRODUCTION_RUN_ID += 1
        session["known_runs"].add(session["run_id"])
        session["run_status"][session["run_id"]] = "active"
        session["state"] = state
        session["active"] = True
        session["revision"] = 0
        progress["started"] = True
        progress["last_difficulty_profile"] = selected_difficulty
        session["stats"]["runs_started"] += 1
        self._send(200, {
            "resumed": False,
            "career_stats": copy.deepcopy(session["stats"]),
            **self._production_run_view(session),
        })

    def _production_action(self, path: str, body: dict | None) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "runs" or parts[2] != "actions":
            return self._send(404, {"detail": "Локальный маршрут не найден."})
        try:
            run_id = int(parts[1])
        except ValueError:
            return self._send(404, {"detail": "Забег не найден."})
        session = self._production_session()
        state = session.get("state")
        body = body or {}
        action_id = str(body.get("action_id") or "").strip()
        if not action_id or len(action_id) > 96:
            return self._send(400, {"detail": "action_id обязателен и не должен превышать 96 символов."})
        if run_id not in session["known_runs"]:
            return self._send(400, {"detail": "Встреча не найдена."})
        cached = session["actions"].get((run_id, action_id))
        if cached is not None:
            replay = copy.deepcopy(cached)
            replay["idempotent_replay"] = True
            return self._send(200, replay)
        if (not session.get("active") or not state or run_id != session["run_id"]
                or session["run_status"].get(run_id) != "active"):
            return self._send(409, {"detail": "Встреча уже завершена."})
        expected_revision = body.get("expected_revision")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            return self._send(400, {"detail": "expected_revision должен быть неотрицательным числом."})
        if expected_revision != session["revision"]:
            return self._send(409, {"detail": "Забег уже изменился в другой вкладке. Обнови состояние боя."})
        action = {
            key: value for key, value in body.items()
            if key not in {"action_id", "expected_revision"} and value is not None
        }
        now_ms = None
        if self.headers.get("X-Reconstruction-Test-Clock") == "fixed-step-100":
            clock = state.get(reconstruction_timing.CLOCK_STATE_KEY) or {}
            now_ms = int(clock.get("last_server_ms", reconstruction_timing.server_now_ms())) + 100
        timed_action, timing_result = reconstruction_timing.server_timed_action(state, action, now_ms=now_ms)
        turn = reconstruction_combat.apply_action(state, timed_action)
        if not turn.get("ok"):
            return self._send(400, {"detail": str(turn.get("error") or "Действие отклонено.")})
        reconstruction_integrity.record_strike(state, turn.get("strike"))
        turn["timing"] = timing_result
        turn["integrity"] = reconstruction_integrity.verdict(state)
        session["revision"] += 1
        turn["server_revision"] = session["revision"]
        pending_memory = None
        next_step = None
        career_stats = None
        mastery_proofs = None
        terminal_result = None
        shadow_reward = None
        if state.get("status") in ("won", "lost"):
            progress = session["progress"]
            if state["status"] == "won" and state.get("run_kind") != "practice":
                completed = list(dict.fromkeys([*progress["completed"], state["encounter_id"]]))
                progress["completed"] = completed
                progress["current_encounter"] = reconstruction._next_after(state["encounter_id"])
                pending_memory = reconstruction._pending_memory(progress)
                next_step = reconstruction._next_step(progress)
                proofs = reconstruction.mastery_proofs_from_terminal(state)
                mastery_proofs = sorted(proofs)
                for unit in session["units"]:
                    unit["proven_challenges"] = sorted(set(unit["proven_challenges"]) | set(proofs))
            else:
                next_step = reconstruction._next_step(progress)
            career_stats = self._record_preview_run_completion(session, state)
            terminal_result = reconstruction_integrity.terminal_result(
                run_id=run_id,
                revision=session["revision"],
                outcome=state["status"],
                state=state,
            )
            shadow_reward = self._preview_shadow_reward(state, terminal_result)
            session["run_status"][run_id] = state["status"]
            session["active"] = False
        response = {
            "run_id": run_id,
            "revision": session["revision"],
            "turn": turn,
            "terminal_result": terminal_result,
            "shadow_reward": shadow_reward,
            "mastery_proofs": mastery_proofs,
            "next_step": next_step,
            "pending_memory": pending_memory,
            "career_stats": career_stats,
            "idempotent_replay": False,
            **reconstruction_combat.public_state(state),
        }
        session["actions"][(run_id, action_id)] = copy.deepcopy(response)
        self._send(200, response)

    def _production_cancel(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "runs" or parts[2] != "cancel":
            return self._send(404, {"detail": "Локальный маршрут не найден."})
        try:
            run_id = int(parts[1])
        except ValueError:
            return self._send(404, {"detail": "Забег не найден."})
        session = self._production_session()
        if run_id not in session["known_runs"]:
            return self._send(400, {"detail": "Забег не найден."})
        cached = session["cancel_responses"].get(run_id)
        if cached is not None:
            replay = copy.deepcopy(cached)
            replay["idempotent_replay"] = True
            return self._send(200, replay)
        if (not session.get("active") or run_id != session["run_id"]
                or session["run_status"].get(run_id) != "active"):
            return self._send(409, {"detail": "Завершённый забег нельзя отменить."})
        state = session["state"]
        session["revision"] += 1
        terminal_result = reconstruction_integrity.terminal_result(
            run_id=run_id,
            revision=session["revision"],
            outcome="cancelled",
            state=state,
        )
        response = {
            "ok": True, "run_id": run_id, "revision": session["revision"],
            "terminal_result": terminal_result,
            "shadow_reward": self._preview_shadow_reward(state, terminal_result),
            "idempotent_replay": False,
        }
        session["active"] = False
        session["run_status"][run_id] = "cancelled"
        session["cancel_responses"][run_id] = copy.deepcopy(response)
        self._send(200, response)

    def _production_memory(self, body: dict | None) -> None:
        session = self._production_session()
        memory_id = str((body or {}).get("memory_id") or "")
        progress = session["progress"]
        pending = reconstruction._pending_memory(progress)
        if memory_id not in reconstruction.MEMORIES:
            return self._send(400, {"detail": "Неизвестная память."})
        if not pending:
            if memory_id in progress["memories"]:
                return self._send(200, {"ok": True, "memory_id": memory_id, "idempotent_replay": True})
            return self._send(400, {"detail": "Сейчас нет незавершённого выбора памяти."})
        if memory_id not in {choice["id"] for choice in pending["choices"]}:
            return self._send(400, {"detail": "Эта память не относится к текущей награде."})
        progress["memories"].append(memory_id)
        self._send(200, {
            "ok": True, "memory_id": memory_id,
            "memory": copy.deepcopy(reconstruction.MEMORIES[memory_id]),
            "next_step": reconstruction._next_step(progress), "idempotent_replay": False,
        })

    def _production_unit_branch(self, body: dict | None) -> None:
        body = body or {}
        unit_id = str(body.get("unit_id") or "")
        branch_id = str(body.get("branch_id") or "")
        found = reconstruction.branch_by_id(branch_id)
        if not found or found[0] != unit_id:
            return self._send(400, {"detail": "Эта ветвь не принадлежит выбранному юниту."})
        session = self._production_session()
        unit = next((item for item in session["units"] if item["unit_id"] == unit_id), None)
        if not unit or int(unit["level"]) < found[1]:
            return self._send(400, {"detail": "Ветвь ещё не открыта уровнем."})
        if found[2]["mastery_challenge"] not in unit["proven_challenges"]:
            return self._send(400, {"detail": "Сначала пройди испытание мастерства."})
        current = unit["branch_choices"].get(str(found[1]))
        if current and current != branch_id:
            return self._send(400, {"detail": "Ветвь этого уровня уже выбрана."})
        unit["branch_choices"][str(found[1])] = branch_id
        self._send(200, {
            "ok": True, "unit_id": unit_id, "branch_id": branch_id,
            "progress": copy.deepcopy(unit), "idempotent_replay": bool(current),
        })

    def _production_chronicle_path(self, body: dict | None) -> None:
        path_id = str((body or {}).get("path_id") or "")
        target = reconstruction.CHAPTER_ONE_PATHS.get(path_id)
        if not target:
            return self._send(400, {"detail": "Неизвестная тропа Хроники."})
        session = self._production_session()
        progress = session["progress"]
        existing = progress["route_choices"].get("chapter_1")
        if existing:
            if existing != path_id:
                return self._send(400, {"detail": "Тропа первой главы уже выбрана."})
            return self._send(200, {
                "ok": True, "path_id": path_id, "encounter_id": target,
                "next_step": reconstruction._next_step(progress), "idempotent_replay": True,
            })
        if progress["current_encounter"] != reconstruction.CHAPTER_ONE_PATH_GATE:
            return self._send(400, {"detail": "Сейчас нет незавершённого выбора тропы."})
        progress["route_choices"]["chapter_1"] = path_id
        progress["current_encounter"] = target
        self._send(200, {
            "ok": True, "path_id": path_id, "encounter_id": target,
            "next_step": reconstruction._next_step(progress), "idempotent_replay": False,
        })

    def _production_post(self, path: str, body: dict | None) -> None:
        if path == "/start":
            return self._production_start(body)
        if path.startswith("/runs/") and path.endswith("/actions"):
            return self._production_action(path, body)
        if path.startswith("/runs/") and path.endswith("/cancel"):
            return self._production_cancel(path)
        if path == "/memory":
            return self._production_memory(body)
        if path == "/units/branch":
            return self._production_unit_branch(body)
        if path == "/chronicle/path":
            return self._production_chronicle_path(body)
        return self._send(404, {"detail": "Локальный маршрут не найден."})

    def do_GET(self):
        if self.path == "/production":
            with _LOCK:
                return self._send(200, self._production_overview())
        if self.path == "/manifest":
            return self._send(200, reconstruction.content_manifest())
        if self.path == "/state":
            with _LOCK:
                return self._send(200, reconstruction_combat.public_state(self._state()))
        if self.path == "/companions":
            with _LOCK:
                return self._send(200, self._companion_overview())
        return self._send(404, {"detail": "Локальный маршрут не найден."})

    def do_POST(self):
        if self.path.startswith("/production/"):
            body = self._body()
            if body is None:
                return self._send(400, {"detail": "Ожидался JSON-объект действия."})
            # The live service takes a user lock and applies optimistic
            # revisions.  The local bridge has in-memory session state, so
            # serialize its read-modify-write path explicitly.
            with _LOCK:
                return self._production_post(self.path[len("/production"):], body)
        if self.path.startswith("/companions/"):
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"detail": "Ожидался JSON-объект действия."})
            with _LOCK:
                state = self._companion_state()
                overview = self._companion_overview()
                pet_ids = {pet["id"] for pet in overview["pets"]}
                if self.path == "/companions/active":
                    pet_id = body.get("pet_id")
                    if pet_id not in pet_ids:
                        return self._send(400, {"detail": "Питомец не найден."})
                    state["active_pet_id"] = pet_id
                    return self._send(200, self._companion_overview())
                if self.path == "/companions/role":
                    role_id = str(body.get("role_id") or "")
                    valid = {role["id"] for role in overview["policy"]["roles"]}
                    if role_id not in valid:
                        return self._send(400, {"detail": "Неизвестная роль."})
                    if role_id not in state["unlocked_roles"]:
                        if len(state["unlocked_roles"]) >= overview["role_slots"]:
                            next_day = overview.get("next_role_day")
                            return self._send(409, {"detail": f"Следующий выбор откроется на {next_day}-й день активной игры."})
                        state["unlocked_roles"].append(role_id)
                    state["selected_role_id"] = role_id
                    return self._send(200, self._companion_overview())
                if self.path == "/companions/care":
                    pet_id = body.get("pet_id")
                    action = str(body.get("action") or "")
                    action_id = str(body.get("action_id") or "")
                    if pet_id not in pet_ids or action not in companions_v3.CARE_ACTIONS:
                        return self._send(400, {"detail": "Действие заботы отклонено."})
                    if action_id in state["actions"]:
                        return self._send(200, state["actions"][action_id])
                    care = state["care"].setdefault(str(pet_id), {"points": 0, "bank": 1, "last": None})
                    if care["bank"] <= 0:
                        return self._send(409, {"detail": "Запас заботы пуст. Возможность вернётся через 48 часов."})
                    care["bank"] -= 1
                    care["points"] += 1
                    care["last"] = action
                    response = {"ok": True, "economic_reward": None}
                    state["actions"][action_id] = response
                    return self._send(200, response)
                if self.path == "/companions/expeditions/start":
                    pet_id = body.get("pet_id")
                    hours = body.get("duration_hours")
                    action_id = str(body.get("action_id") or "")
                    if action_id in state["actions"]:
                        return self._send(200, state["actions"][action_id])
                    if pet_id not in pet_ids or hours not in companions_v3.EXPEDITION_OPTIONS:
                        return self._send(400, {"detail": "Контракт разведки отклонён."})
                    open_contracts = [
                        item for item in state["contracts"] if item["status"] in ("active", "ready")
                    ]
                    if len(open_contracts) >= overview["expeditions"]["slots"]:
                        return self._send(409, {"detail": "Все слоты разведки заняты."})
                    if any(item["pet_id"] == pet_id for item in open_contracts):
                        return self._send(409, {"detail": "Этот спутник уже в разведке."})
                    quote = companions_v3.quote_expedition(hours, overview["expeditions"]["weekly_reserved_mora"])
                    digest = hashlib.sha256(f"{self._session_key()}:{action_id}".encode()).hexdigest()
                    contract = {
                        "id": state["next_contract_id"], "pet_id": pet_id,
                        "duration_hours": hours, "route_id": quote.route,
                        "fixed_mora": quote.projected_mora,
                        "discovery_id": companions_v3.expedition_discovery(digest, hours),
                        "status": "active",
                        "ends_epoch": time.time() + {2: 8, 6: 14, 12: 20}[hours],
                    }
                    state["next_contract_id"] += 1
                    state["contracts"].append(contract)
                    response = {"ok": True, "contract_id": contract["id"], "settled": False,
                                "economic_reward": None}
                    state["actions"][action_id] = response
                    return self._send(200, response)
                if self.path == "/companions/expeditions/claim":
                    action_id = str(body.get("action_id") or "")
                    if action_id in state["actions"]:
                        return self._send(200, state["actions"][action_id])
                    now = time.time()
                    ready = []
                    for contract in state["contracts"]:
                        if contract["status"] == "active" and contract["ends_epoch"] <= now:
                            contract["status"] = "ready"
                        if contract["status"] == "ready":
                            contract["status"] = "claimed"
                            ready.append(contract)
                    if not ready:
                        return self._send(409, {"detail": "Готовых походов пока нет."})
                    response = {
                        "ok": True, "claimed": [item["id"] for item in ready],
                        "projected_mora_total": sum(item["fixed_mora"] for item in ready),
                        "settled": False, "economic_reward": None,
                    }
                    state["actions"][action_id] = response
                    return self._send(200, response)
        if self.path == "/reset":
            with _LOCK:
                body = self._body()
                encounter_id = str((body or {}).get("encounter_id") or reconstruction.FIRST_ENCOUNTER)
                encounter = reconstruction.ENCOUNTERS.get(encounter_id)
                if not encounter or not encounter.get("implemented"):
                    return self._send(400, {"detail": "Эта встреча ещё не доступна в dev-стенде."})
                unit_branches = (body or {}).get("unit_branches")
                if unit_branches is not None and not isinstance(unit_branches, dict):
                    return self._send(400, {"detail": "unit_branches должен быть объектом."})
                companion_role_id = (body or {}).get("companion_role_id")
                if companion_role_id is not None and not isinstance(companion_role_id, str):
                    return self._send(400, {"detail": "companion_role_id должен быть строкой."})
                difficulty_id = (body or {}).get("difficulty_id")
                if difficulty_id is not None and not isinstance(difficulty_id, str):
                    return self._send(400, {"detail": "difficulty_id должен быть строкой."})
                try:
                    state = _new_state(encounter_id, unit_branches, companion_role_id, difficulty_id)
                except ValueError as exc:
                    return self._send(400, {"detail": str(exc)})
                _STATES[self._session_key()] = state
                _save_states()
                return self._send(200, reconstruction_combat.public_state(state))
        if self.path == "/action":
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"detail": "Ожидался JSON-объект действия."})
            with _LOCK:
                state = self._state()
                state_before = copy.deepcopy(state)
                # Browser regression tests need deterministic short runs.  This
                # bridge is local-only and never settles rewards; production has
                # no equivalent header or fixed-step branch.
                fixed_step = self.headers.get("X-Reconstruction-Test-Clock") == "fixed-step-100"
                now_ms = None
                if fixed_step:
                    clock = state.get(reconstruction_timing.CLOCK_STATE_KEY) or {}
                    now_ms = int(clock.get("last_server_ms", reconstruction_timing.server_now_ms())) + 100
                timed_body, timing_result = reconstruction_timing.server_timed_action(
                    state,
                    body,
                    now_ms=now_ms,
                )
                turn = reconstruction_combat.apply_action(state, timed_body)
                if not turn.get("ok"):
                    _STATES[self._session_key()] = state_before
                    # Dev-вкладка могла пережить hot reload или конец забега. Возврат
                    # актуального state останавливает старый клиент без бесконечного
                    # цикла 400; production-сервис по-прежнему отклоняет такой action.
                    return self._send(200, {
                        "turn": turn,
                        "rejected": True,
                        "state": reconstruction_combat.public_state(state_before),
                    })
                reconstruction_integrity.record_strike(state, turn.get("strike"))
                turn["timing"] = timing_result
                turn["integrity"] = reconstruction_integrity.verdict(state)
                terminal_result = None
                shadow_reward = None
                if state.get("status") in ("won", "lost"):
                    terminal_result = reconstruction_integrity.terminal_result(
                        run_id=1,
                        revision=0,
                        outcome=state["status"],
                        state=state,
                    )
                    shadow_reward = self._preview_shadow_reward(state, terminal_result)
                _save_states()
                return self._send(200, {
                    "turn": turn,
                    "state": reconstruction_combat.public_state(state),
                    "terminal_result": terminal_result,
                    "shadow_reward": shadow_reward,
                })
        return self._send(404, {"detail": "Локальный маршрут не найден."})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
