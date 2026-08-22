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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import (  # noqa: E402
    reconstruction,
    reconstruction_combat,
    reconstruction_integrity,
    reconstruction_timing,
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


def _new_state():
    # У каждой вкладки и каждого reset свой run key: локальная статистика может
    # надёжно дедуплицировать завершение, а тестировщики не делят один seed.
    state = reconstruction_combat.new_encounter(seed=secrets.randbelow(2**31 - 1) + 1)
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

    def do_GET(self):
        if self.path == "/manifest":
            return self._send(200, reconstruction.content_manifest())
        if self.path == "/state":
            with _LOCK:
                return self._send(200, reconstruction_combat.public_state(self._state()))
        return self._send(404, {"detail": "Локальный маршрут не найден."})

    def do_POST(self):
        if self.path == "/reset":
            with _LOCK:
                state = _new_state()
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
