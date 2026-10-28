"""Request time and 4xx/5xx per route template for the health panel (services/ops_health.py).

A plain ASGI wrapper rather than ``@app.middleware("http")``: it runs on every request,
static files included, so it must not add a BaseHTTPMiddleware hop.
"""
import time

from core import ops_metrics


class RequestMetrics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 500

        async def send_and_note_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
        finally:
            name = route_name(scope)
            ops_metrics.observe("http", name, (time.perf_counter() - started) * 1000)
            if status >= 500:
                ops_metrics.count("http_5xx", name)
            elif status >= 400:
                ops_metrics.count("http_4xx", name)


def route_name(scope) -> str:
    """"GET /profile/{user_id}" — the template, never the concrete path (ids stay out of metrics)."""
    method = scope.get("method", "GET")
    template = getattr(scope.get("route"), "path", None)
    if scope.get("path", "").startswith("/static/"):
        return f"{method} /static/*"
    return f"{method} {template}" if template else f"{method} (unmatched)"
