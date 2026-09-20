"""Public path gateway for the co-hosted IESA and Predvestnik services.

The two applications intentionally run in separate processes because both have
a top-level Python package named ``core``.  Keeping the interpreters isolated
also prevents either application's startup state from leaking into the other.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask


PREFIX = "/predvestnik"
SITE_UPSTREAM = os.getenv("IESA_SITE_UPSTREAM", "http://127.0.0.1:18081")
MINIAPP_UPSTREAM = os.getenv("PREDVESTNIK_UPSTREAM", "http://127.0.0.1:18082")
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))
    try:
        yield
    finally:
        await app.state.client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def upstream_target(path: str) -> tuple[str, str, str]:
    if path == PREFIX or path.startswith(f"{PREFIX}/"):
        return MINIAPP_UPSTREAM, path[len(PREFIX):] or "/", PREFIX
    return SITE_UPSTREAM, path or "/", ""


def forwarded_headers(headers, *, prefix: str) -> dict[str, str]:
    result = {
        key: value for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP and key.lower() not in {"host", "content-length"}
    }
    if prefix:
        result["x-forwarded-prefix"] = prefix
    return result


def public_location(value: str, *, prefix: str) -> str:
    if not prefix:
        return value
    parsed = urlsplit(value)
    if parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith(prefix):
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, f"{prefix}{parsed.path}", parsed.query, parsed.fragment))


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_http(request: Request, path: str):
    public_path = f"/{path}"
    base, upstream_path, prefix = upstream_target(public_path)
    query = request.url.query
    url = f"{base}{upstream_path}" + (f"?{query}" if query else "")
    upstream_request = request.app.state.client.build_request(
        request.method,
        url,
        headers=forwarded_headers(request.headers, prefix=prefix),
        content=await request.body(),
    )
    response = await request.app.state.client.send(upstream_request, stream=True)
    headers = {
        key: public_location(value, prefix=prefix) if key.lower() == "location" else value
        for key, value in response.headers.items()
        if key.lower() not in HOP_BY_HOP and key.lower() != "content-length"
    }
    return StreamingResponse(
        response.aiter_raw(),
        status_code=response.status_code,
        headers=headers,
        background=BackgroundTask(response.aclose),
    )


@app.websocket("/{path:path}")
async def proxy_websocket(client: WebSocket, path: str):
    public_path = f"/{path}"
    base, upstream_path, prefix = upstream_target(public_path)
    if not prefix:
        await client.close(code=1008)
        return
    ws_base = base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    query = client.url.query
    target = f"{ws_base}{upstream_path}" + (f"?{query}" if query else "")
    headers = forwarded_headers(client.headers, prefix=prefix)
    try:
        async with websockets.connect(target, additional_headers=headers) as upstream:
            await client.accept()

            async def to_upstream():
                while True:
                    message = await client.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def to_client():
                async for message in upstream:
                    if isinstance(message, bytes):
                        await client.send_bytes(message)
                    else:
                        await client.send_text(message)

            tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except Exception:
        await client.close(code=1011)
