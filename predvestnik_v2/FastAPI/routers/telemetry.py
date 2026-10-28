"""Anonymous Mini App error telemetry: JS errors, failed requests, missing Telegram SDK, start-up timing.

Works without authorization (login failures must be visible too) and stays open when the site is
switched off (services/feature_switches.SITE_ALWAYS_OPEN). Body size, events per request and rate per
IP, per random page id and globally are capped in services/ops_health.py; nothing identifying is stored.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import ops_health

router = APIRouter(tags=["telemetry"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")


async def _read_limited(request: Request) -> bytes | None:
    """The body, or None when it exceeds the cap (read in chunks: Content-Length can be absent or lie)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > ops_health.MAX_BODY_BYTES:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > ops_health.MAX_BODY_BYTES:
            return None
    return bytes(body)


@router.post("/telemetry")
async def telemetry(request: Request):
    body = await _read_limited(request)
    if body is None:
        return JSONResponse({"detail": "too large"}, status_code=413)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"detail": "bad json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"detail": "bad json"}, status_code=400)
    accepted, limited = ops_health.accept_client_events(_client_ip(request), payload)
    return JSONResponse({"accepted": accepted}, status_code=429 if limited and not accepted else 200,
                        headers={"Cache-Control": "no-store"})
