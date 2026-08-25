"""FastAPI/prefix.py — ASGI middleware that strips a path prefix before routing."""

from urllib.parse import urlsplit, urlunsplit


class _StripPrefix:
    """Strips `prefix` from the request path so FastAPI routes at '/' work
    even when DigitalOcean routes /predvestnik/* to this service."""

    def __init__(self, app, prefix: str):
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            if not (path == self.prefix or path.startswith(f"{self.prefix}/")):
                # A rooted deployment must never expose an alternate unprefixed
                # API surface when a proxy/tunnel is misconfigured.
                if scope["type"] == "http":
                    await send({
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [(b"content-type", b"application/json")],
                    })
                    await send({"type": "http.response.body", "body": b'{"detail":"Not Found"}'})
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
            scope = dict(scope)
            scope["root_path"] = scope.get("root_path", "") + self.prefix
            scope["path"] = path[len(self.prefix):] or "/"
            scope["raw_path"] = scope["path"].encode()
            if scope["type"] == "http":
                stripped_path = scope["path"]
                public_prefix = scope["root_path"].rstrip("/")
                request_host = next(
                    (value.decode("latin-1") for name, value in scope.get("headers", [])
                     if name.lower() == b"host"),
                    "",
                )

                async def send_with_prefixed_redirect(message):
                    """Restore a prefix only in FastAPI's automatic slash redirect."""
                    if (
                        message.get("type") != "http.response.start"
                        or message.get("status") != 307
                        or not stripped_path.endswith("/")
                    ):
                        return await send(message)
                    headers = list(message.get("headers", []))
                    rewritten = []
                    changed = False
                    for name, value in headers:
                        if name.lower() != b"location":
                            rewritten.append((name, value))
                            continue
                        location = value.decode("latin-1")
                        try:
                            parsed = urlsplit(location)
                        except ValueError:
                            rewritten.append((name, value))
                            continue
                        same_origin = not parsed.netloc or parsed.netloc == request_host
                        automatic_slash_target = parsed.path == stripped_path[:-1]
                        path_without_prefix = parsed.path and not (
                            parsed.path == public_prefix or parsed.path.startswith(f"{public_prefix}/")
                        )
                        if same_origin and automatic_slash_target and path_without_prefix:
                            location = urlunsplit((
                                parsed.scheme, parsed.netloc, f"{public_prefix}{parsed.path}",
                                parsed.query, parsed.fragment,
                            ))
                            value = location.encode("latin-1")
                            changed = True
                        rewritten.append((name, value))
                    if changed:
                        message = {**message, "headers": rewritten}
                    await send(message)

                return await self.app(scope, receive, send_with_prefixed_redirect)
        await self.app(scope, receive, send)


def strip_prefix_middleware(app, prefix: str):
    return _StripPrefix(app, prefix)
