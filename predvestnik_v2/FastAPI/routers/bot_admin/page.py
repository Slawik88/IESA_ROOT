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
# Порядок важен: разделы (lists) опираются на помощники из admin.js, а старт (boot) — на все разделы.
_TYPES = {"admin.js": "text/javascript; charset=utf-8", "admin-lists.js": "text/javascript; charset=utf-8",
          "admin-purge.js": "text/javascript; charset=utf-8", "admin-live.js": "text/javascript; charset=utf-8",   # «Чистка» и живые обновления (S10)
          "admin-diagnostics.js": "text/javascript; charset=utf-8",
          "admin-patchnotes.js": "text/javascript; charset=utf-8", "admin-patchnotes-edit.js": "text/javascript; charset=utf-8",
          "admin-patchnotes-actions.js": "text/javascript; charset=utf-8",
          "admin-guide.js": "text/javascript; charset=utf-8",   # Путеводитель администрации (S09; темы — только по роли: /bot-admin/api/guide)
          "guide-host.js": "text/javascript; charset=utf-8",   # Путеводитель администрации слоем (S09b): страница guide.html
          "admin-boot.js": "text/javascript; charset=utf-8", "admin.css": "text/css; charset=utf-8"}
# Путеводитель администрации — тот же экран, что у игрока: его стили и скрипты берутся из Mini App как есть (без копий)
# и входят в версию страниц админки (новая выкладка Mini App = новые адреса здесь).
_SHARED = {"shell-v3.css": "text/css; charset=utf-8", "shell-v3-home.css": "text/css; charset=utf-8", "guide-v3.css": "text/css; charset=utf-8",
           "app.20.js": "text/javascript; charset=utf-8", "app.57.js": "text/javascript; charset=utf-8"}
router = APIRouter()

_PAGE = ""
_GUIDE_PAGE = ""
_ASSETS: dict[str, tuple[str, bytes, str]] = {}   # имя -> (тип, содержимое, ETag)


def _digest(*chunks: bytes) -> str:
    h = hashlib.sha1()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()[:16]


def load(directory: str | None = None) -> None:
    """Читает страницу и файлы админки один раз: версия в адресах файлов и сами файлы всегда из одного снимка."""
    global _PAGE, _GUIDE_PAGE, _ASSETS
    directory = directory or _DIR
    raw = {}
    for name in ("index.html", "guide.html", *_TYPES):
        with open(os.path.join(directory, name), "rb") as f:
            raw[name] = f.read()
    for name in _SHARED:   # всегда из Mini App: у админки своей копии нет
        with open(os.path.join(_DIR, "..", name), "rb") as f:
            raw[name] = f.read()
    ver = _digest(*raw.values())
    _PAGE = raw["index.html"].decode("utf-8").replace("{{BASE}}", _BASE).replace("{{VER}}", ver)
    _GUIDE_PAGE = raw["guide.html"].decode("utf-8").replace("{{BASE}}", _BASE).replace("{{VER}}", ver)
    _ASSETS = {name: (media, raw[name], f'"{_digest(raw[name])}"') for name, media in {**_TYPES, **_SHARED}.items()}


load()


@router.get("/bot-admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/bot-admin/guide", response_class=HTMLResponse, include_in_schema=False)
async def admin_guide_page():
    """Экран Путеводителя администрации (слой поверх админки). Без проверки, как и сама админка: темы отдаёт /bot-admin/api/guide по роли."""
    return HTMLResponse(_GUIDE_PAGE, headers={"Cache-Control": "no-store"})


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
