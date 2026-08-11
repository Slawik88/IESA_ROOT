"""Local-only HTTP bridge to the real Reconstruction 3.0 Python engine.

The Node preview server proxies ``/__reconstruction/*`` here, so the browser lab
tests the same pure engine as the backend instead of a JavaScript mock.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import reconstruction, reconstruction_combat  # noqa: E402


PORT = int(os.environ.get("RECON_PREVIEW_PORT", "8403"))
_LOCK = threading.RLock()
_STATES = {}


def _new_state():
    return reconstruction_combat.new_encounter(seed=20260811)


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
            state = _new_state()
            _STATES[key] = state
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
                return self._send(200, reconstruction_combat.public_state(state))
        if self.path == "/action":
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"detail": "Ожидался JSON-объект действия."})
            with _LOCK:
                state = self._state()
                turn = reconstruction_combat.apply_action(state, body)
                if not turn.get("ok"):
                    # Dev-вкладка могла пережить hot reload или конец забега. Возврат
                    # актуального state останавливает старый клиент без бесконечного
                    # цикла 400; production-сервис по-прежнему отклоняет такой action.
                    return self._send(200, {
                        "turn": turn,
                        "rejected": True,
                        "state": reconstruction_combat.public_state(state),
                    })
                return self._send(200, {
                    "turn": turn,
                    "state": reconstruction_combat.public_state(state),
                })
        return self._send(404, {"detail": "Локальный маршрут не найден."})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
