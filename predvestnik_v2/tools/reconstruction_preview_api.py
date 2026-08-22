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


def _new_state(
    encounter_id: str = reconstruction.FIRST_ENCOUNTER,
    unit_branches: dict[str, str | list[str]] | None = None,
    companion_role_id: str | None = None,
):
    # У каждой вкладки и каждого reset свой run key: локальная статистика может
    # надёжно дедуплицировать завершение, а тестировщики не делят один seed.
    state = reconstruction_combat.new_encounter(
        seed=secrets.randbelow(2**31 - 1) + 1,
        encounter_id=encounter_id,
        unit_branches=unit_branches,
        companion_role_id=companion_role_id,
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
                "unlocked_roles": ["lantern", "guardian", "rhythm_keeper"],
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

    def do_GET(self):
        if self.path == "/manifest":
            return self._send(200, reconstruction.content_manifest())
        if self.path == "/state":
            with _LOCK:
                return self._send(200, reconstruction_combat.public_state(self._state()))
        if self.path == "/companions":
            return self._send(200, self._companion_overview())
        return self._send(404, {"detail": "Локальный маршрут не найден."})

    def do_POST(self):
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
                            return self._send(409, {"detail": "Следующий выбор откроется на 15 meaningful-дне."})
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
                try:
                    state = _new_state(encounter_id, unit_branches, companion_role_id)
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
                _save_states()
                return self._send(200, {
                    "turn": turn,
                    "state": reconstruction_combat.public_state(state),
                })
        return self._send(404, {"detail": "Локальный маршрут не найден."})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
