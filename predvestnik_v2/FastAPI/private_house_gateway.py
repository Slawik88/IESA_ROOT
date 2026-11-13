"""Отдельный loopback-сервис; его маршруты не регистрируются в игровом API."""
import importlib.util
from pathlib import Path

import httpx

MAX_BODY_BYTES = 3 * 1024 * 1024


def _private_prefix() -> str:
    module_path = Path(__file__).resolve().parents[2] / "domovoy" / "core" / "private_entry.py"
    spec = importlib.util.spec_from_file_location("house_private_entry", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.private_path(module.entry_token())


class PrivateHouseGateway:
    def __init__(self, app, *, prefix: str | None = None, transport=None):
        self.app = app
        self.prefix = _private_prefix() if prefix is None else prefix
        self.transport = transport

    @staticmethod
    async def _reply(send, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"cache-control", b"no-store"),
            (b"x-robots-tag", b"noindex, nofollow, noarchive"),
        ]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        matched = self.prefix and (path == self.prefix or path.startswith(self.prefix + "/"))
        if not matched:
            if scope["type"] == "http" and path.startswith("/_h/"):
                return await self._reply(send, 404, b'{"detail":"Not Found"}')
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["method"] not in ("GET", "POST"):
            return await self._reply(send, 404, b'{"detail":"Not Found"}')
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY_BYTES:
                return await self._reply(send, 413, b'{"detail":"File too large"}')
            if not message.get("more_body"):
                break
        relative = path[len(self.prefix):] or "/"
        if ".." in relative or "\\" in relative or "//" in relative:
            return await self._reply(send, 404, b'{"detail":"Not Found"}')
        headers = {name.decode("latin1"): value.decode("latin1") for name, value in scope["headers"]
                   if name.lower() in (b"authorization", b"content-type")}
        try:
            async with httpx.AsyncClient(timeout=20, transport=self.transport, trust_env=False) as client:
                response = await client.request(scope["method"], "http://127.0.0.1:8011" + relative,
                                                params=scope.get("query_string", b"").decode("ascii"),
                                                headers=headers, content=bytes(body))
        except httpx.HTTPError:
            return await self._reply(send, 503, b'{"detail":"Temporarily unavailable"}')
        safe_headers = [(name.encode("latin1"), value.encode("latin1")) for name, value in response.headers.items()
                        if name.lower() in {"content-type", "content-disposition", "cache-control", "x-robots-tag",
                                            "referrer-policy", "content-security-policy", "x-content-type-options"}]
        await send({"type": "http.response.start", "status": response.status_code, "headers": safe_headers})
        await send({"type": "http.response.body", "body": response.content})
