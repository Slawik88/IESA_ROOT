"""Страница админки. Документ отдаётся без проверки: initData появляется только в JS,
а каждый запрос к API проверяется отдельно."""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "bot-admin")
_BASE = os.getenv("ROOT_PATH", "").rstrip("/")
router = APIRouter()


def _html() -> str:
    ver = str(int(max(os.path.getmtime(os.path.join(_DIR, n)) for n in ("index.html", "admin.js", "admin.css"))))
    with open(os.path.join(_DIR, "index.html"), encoding="utf-8") as f:
        return f.read().replace("{{BASE}}", _BASE).replace("{{VER}}", ver)


_PAGE = _html()


def _asset(name: str) -> bytes:
    with open(os.path.join(_DIR, name), "rb") as f:
        return f.read()


_ASSETS = {"admin.js": ("text/javascript; charset=utf-8", _asset("admin.js")),
           "admin.css": ("text/css; charset=utf-8", _asset("admin.css"))}


@router.get("/bot-admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/bot-admin/{name}", include_in_schema=False)
async def admin_asset(name: str):
    if name not in _ASSETS:
        return Response(status_code=404)
    media, body = _ASSETS[name]
    return Response(body, media_type=media, headers={"Cache-Control": "public, max-age=31536000, immutable"})
