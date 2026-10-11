"""Страница админки. Документ отдаётся без проверки: initData появляется только в JS,
а каждый запрос к API проверяется отдельно.

Версия файлов (`?v=`) считается по содержимому, а не по времени изменения: на хостинге время файлов не меняется
от выкладки к выкладке, и «вечный» кеш Telegram держал самую первую админку при свежей странице
(экран «Загрузка…» без нижней панели). Файлы отдаются с проверкой по ETag: изменились — придут новые, нет — ответ 304."""
from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "bot-admin")
_BASE = os.getenv("ROOT_PATH", "").rstrip("/")
_TYPES = {"admin.js": "text/javascript; charset=utf-8", "admin.css": "text/css; charset=utf-8"}
router = APIRouter()

_PAGE = ""
_ASSETS: dict[str, tuple[str, bytes, str]] = {}   # имя -> (тип, содержимое, ETag)


def _digest(*chunks: bytes) -> str:
    h = hashlib.sha1()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()[:16]


def load(directory: str | None = None) -> None:
    """Читает страницу и файлы админки один раз: версия в адресах файлов и сами файлы всегда из одного снимка."""
    global _PAGE, _ASSETS
    directory = directory or _DIR
    raw = {}
    for name in ("index.html", *_TYPES):
        with open(os.path.join(directory, name), "rb") as f:
            raw[name] = f.read()
    ver = _digest(*(raw[n] for n in ("index.html", *_TYPES)))
    _PAGE = raw["index.html"].decode("utf-8").replace("{{BASE}}", _BASE).replace("{{VER}}", ver)
    _ASSETS = {name: (media, raw[name], f'"{_digest(raw[name])}"') for name, media in _TYPES.items()}


load()


@router.get("/bot-admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/bot-admin/{name}", include_in_schema=False)
async def admin_asset(name: str, request: Request):
    if name not in _ASSETS:
        return Response(status_code=404)
    media, body, etag = _ASSETS[name]
    headers = {"Cache-Control": "no-cache", "ETag": etag}
    sent = [t.strip().removeprefix("W/") for t in request.headers.get("if-none-match", "").split(",")]   # прокси делает ETag «слабым»
    if etag in sent:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type=media, headers=headers)
