"""Фото в админке: подписанные ссылки, срок, кэш и плейсхолдер (ADM-03, без сети и БД).

1) Пропуск принимается только свой и только до срока; подмена uid ломает подпись.
2) Без BOT_TOKEN ссылок нет вовсе — фронт покажет инициал, а не битую картинку.
3) «Фото нет» кэшируется негативно, повторный запрос не идёт в Bot API.
4) Формат картинки определяется по байтам, а не по расширению.

Запуск: python tools/test_bot_admin_avatars.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "1:avatar-test")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import admin_avatars as av  # noqa: E402


def test_tokens() -> None:
    token = av.create_token(42)
    uid, expires, signature = token.split(":")
    assert token.count(":") == 2, token
    assert av.verify_token(token) == 42
    assert av.verify_token(f"43:{expires}:{signature}") is None      # чужой uid
    assert av.verify_token(f"{uid}:{expires}:deadbeef") is None      # чужая подпись
    assert av.verify_token("") is None and av.verify_token("мусор") is None
    assert av.verify_token(token + "x") is None

    real = av.time
    av.time = SimpleNamespace(time=lambda: 1_000_000)
    try:
        fresh = av.create_token(7)
        assert av.verify_token(fresh) == 7
        av.time = SimpleNamespace(time=lambda: 1_000_000 + av.TOKEN_TTL + 1)
        assert av.verify_token(fresh) is None, "просроченная ссылка должна отказывать"
    finally:
        av.time = real


def test_urls_and_attach() -> None:
    url = av.avatar_url(9)
    assert url and url.startswith("/bot-admin/avatar/9?t="), url
    assert av.avatar_url(0) is None and av.avatar_url(None) is None and av.avatar_url("abc") is None

    rows = [{"id": 9}, {"id": 0}]
    av.attach(rows)
    assert rows[0]["avatar"] == url and rows[1]["avatar"] is None
    assert av.attach([{"user": 5}], key="user", field="photo")[0]["photo"].startswith("/bot-admin/avatar/5?t=")

    old = os.environ.pop("BOT_TOKEN")
    try:
        assert av.create_token(9) == "" and av.avatar_url(9) is None
        assert av.verify_token(url.rsplit("t=", 1)[1]) is None, "без токена пропуск не принимается"
    finally:
        os.environ["BOT_TOKEN"] = old


def test_bytes_and_cache() -> None:
    calls = []

    async def fake(user_id):
        calls.append(user_id)
        return b"\x89PNG\r\n\x1a\nphoto" if user_id == 1 else None

    real = av._download
    av._download = fake
    av._CACHE.clear()
    try:
        assert asyncio.run(av.bytes_for(2)) is None
        assert asyncio.run(av.bytes_for(2)) is None
        assert calls == [2], "негативный кэш должен гасить повторный запрос"
        assert asyncio.run(av.bytes_for(1)).endswith(b"photo")
        assert av.image_mime(b"\x89PNG\r\n\x1a\n") == "image/png"
        assert av.image_mime(b"GIF89a") == "image/gif"
        assert av.image_mime(b"RIFF\0\0\0\0WEBP") == "image/webp"
        assert av.image_mime(b"\xff\xd8\xff") == "image/jpeg"
    finally:
        av._download = real
        av._CACHE.clear()

    placeholder = av.PLACEHOLDER
    assert placeholder.startswith(b"<svg") and "viewBox" in placeholder.decode()


def test_route_is_token_gated() -> None:
    """Картинку грузит браузер без заголовков входа: маршрут живёт вне /bot-admin/api,
    а доступ даёт только подписанный пропуск (его проверяет test_tokens)."""
    from fastapi.routing import APIRoute
    from FastAPI.routers import bot_admin

    def walk(router):
        for route in router.routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from walk(inner)
            else:
                yield route

    found = [r for r in walk(bot_admin.router) if isinstance(r, APIRoute) and r.path == "/bot-admin/avatar/{uid}"]
    assert len(found) == 1, found
    deps = []

    def collect(dependant):
        for dep in dependant.dependencies:
            deps.append(dep.call)
            collect(dep)

    collect(found[0].dependant)
    assert not any(getattr(dep, "admin_guard", False) for dep in deps), "картинка не может ждать заголовки входа"


def main() -> None:
    test_tokens()
    test_urls_and_attach()
    test_bytes_and_cache()
    test_route_is_token_gated()
    print("OK: фото админки — подпись, срок, негативный кэш, плейсхолдер и формат байтов")


main()
