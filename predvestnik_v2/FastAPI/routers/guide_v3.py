"""Путеводитель игрока: темы, словарь и быстрые ответы одним файлом данных (static/guide-v3.json).

Файл читается при старте. Отдаётся сжатым без пробелов и с ETag: приложение каждый раз спрашивает, не изменился ли он,
и получает 304, пока текст тот же. Правила текстов — docs/PLAYER_COPY.md.
"""
import hashlib
import json
import os

from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["guide"])

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "guide-v3.json")


def _load() -> tuple[bytes, str]:
    with open(_PATH, encoding="utf-8") as source:
        body = json.dumps(json.load(source), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return body, '"' + hashlib.sha1(body).hexdigest()[:16] + '"'


_BODY, _ETAG = _load()
_HEADERS = {"ETag": _ETAG, "Cache-Control": "no-cache"}


@router.get("/guide-v3.json")
async def guide_data(request: Request) -> Response:
    if request.headers.get("if-none-match") == _ETAG:
        return Response(status_code=304, headers=_HEADERS)
    return Response(_BODY, media_type="application/json; charset=utf-8", headers=_HEADERS)
