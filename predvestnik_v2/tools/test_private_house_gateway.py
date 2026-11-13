"""Изоляция loopback-сервиса от маршрутов и авторизации игры."""
import importlib.util
from pathlib import Path

import httpx
import pytest

from fastapi import FastAPI

pytestmark = pytest.mark.asyncio

def gateway_class():
    filename = Path(__file__).resolve().parents[1] / "FastAPI/private_house_gateway.py"
    spec = importlib.util.spec_from_file_location("private_gateway_test", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PrivateHouseGateway


async def test_gateway_preserves_parent_and_strips_cookies():
    parent = FastAPI()

    @parent.get("/health")
    async def health():
        return {"service": "existing"}

    captured = []

    async def upstream(request):
        captured.append(request)
        return httpx.Response(200, json={"ok": True}, headers={"Set-Cookie": "bad=1", "Cache-Control": "no-store"})

    gateway = gateway_class()(parent, prefix="/_h/opaque", transport=httpx.MockTransport(upstream))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://test") as client:
        assert (await client.get("/health")).json() == {"service": "existing"}
        assert (await client.get("/openapi.json")).status_code == 200
        result = await client.get("/_h/opaque/api/houses", headers={"Cookie": "pred-session=secret",
                                                                   "Authorization": "tma signed"})
        assert result.status_code == 200 and "set-cookie" not in result.headers
        assert "cookie" not in captured[0].headers
        assert captured[0].url.path == "/api/houses"
        assert captured[0].headers["authorization"] == "tma signed"
        assert (await client.get("/_h/unknown/api/houses")).status_code == 404
        assert "opaque" not in (await client.get("/openapi.json")).text


async def test_gateway_backend_failure_is_generic():
    async def failed(request):
        raise httpx.ConnectError("private internal failure", request=request)

    gateway = gateway_class()(FastAPI(), prefix="/_h/opaque", transport=httpx.MockTransport(failed))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://test") as client:
        response = await client.get("/_h/opaque/")
        assert response.status_code == 503
        assert "private internal failure" not in response.text and "Домовой" not in response.text


async def test_existing_prefix_still_routes_both_services():
    prefix_file = Path(__file__).resolve().parents[1] / "FastAPI/prefix.py"
    spec = importlib.util.spec_from_file_location("existing_prefix", prefix_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parent = FastAPI()

    @parent.get("/health")
    async def health():
        return {"ok": True}

    async def upstream(request):
        assert request.url.path == "/api/houses"
        return httpx.Response(200, json={"isolated": True})

    gateway = gateway_class()(parent, prefix="/_h/opaque", transport=httpx.MockTransport(upstream))
    app = module.strip_prefix_middleware(gateway, "/predvestnik")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/predvestnik/health")).status_code == 200
        assert (await client.get("/predvestnik/_h/opaque/api/houses")).json() == {"isolated": True}
        assert (await client.get("/_h/opaque/api/houses")).status_code == 404


async def test_gateway_limits_body_without_contacting_upstream():
    async def upstream(request):
        raise AssertionError("oversized request reached upstream")

    gateway = gateway_class()(FastAPI(), prefix="/_h/opaque", transport=httpx.MockTransport(upstream))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://test") as client:
        response = await client.post("/_h/opaque/api/import", content=b"a" * (3 * 1024 * 1024 + 1))
        assert response.status_code == 413
