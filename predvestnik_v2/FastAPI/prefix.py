"""FastAPI/prefix.py — ASGI middleware that strips a path prefix before routing."""


class _StripPrefix:
    """Strips `prefix` from the request path so FastAPI routes at '/' work
    even when DigitalOcean routes /predvestnik/* to this service."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            if path.startswith(self.prefix):
                scope = dict(scope)
                scope["root_path"] = scope.get("root_path", "") + self.prefix
                scope["path"] = path[len(self.prefix):] or "/"
                scope["raw_path"] = scope["path"].encode()
        await self.app(scope, receive, send)


def strip_prefix_middleware(app, prefix: str):
    return _StripPrefix(app, prefix)
