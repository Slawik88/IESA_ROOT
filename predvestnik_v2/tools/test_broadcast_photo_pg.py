#!/usr/bin/env python3
"""Broadcast with a picture (S28, owner 06.11.2026) on real PostgreSQL with a fake Telegram: nothing reaches real players.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_broadcast_photo_pg.py --dsn postgresql://…@127.0.0.1:…/<disposable db>

Proves: a picture is stored once (same bytes — same number), only JPEG/PNG/WebP up to 5 MB; with a picture the text is a
caption and is limited by visible characters (tags do not count); the broadcast goes out as photos, the file is uploaded
once and then reused by file_id (also after a restart); a template and «повтор недоставленным» keep the picture; a text
broadcast still goes out as a message.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x01" * 64
ACTOR = 984001
PLAYERS = [984101, 984102, 984103]
BLOCKED = 984104


class FakeBot:
    def __init__(self) -> None:
        self.photos: list[tuple[int, object, str]] = []
        self.messages: list[tuple[int, str]] = []

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        if int(chat_id) == BLOCKED:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.photos.append((int(chat_id), photo, caption))
        return SimpleNamespace(photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="tg-file-1")])

    async def send_message(self, chat_id, text, **_):
        self.messages.append((int(chat_id), text))
        return SimpleNamespace(photo=None)


async def proof() -> None:
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from services import broadcasts as bc

    @asynccontextmanager
    async def pool_db():
        async with get_pool().acquire() as conn:
            yield PGAdapter(conn)

    async with pool_db() as db:
        await bc.ensure_schema(db)
        for uid in [ACTOR, *PLAYERS, BLOCKED]:
            await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (uid,))

        # 1. Storage: once per picture, only real images, size limit.
        first = await bc.save_media(db, ACTOR, PNG)
        assert await bc.save_media(db, ACTOR, PNG) == first, "the same picture is stored once"
        assert await bc.save_media(db, ACTOR, JPEG) != first
        for bad in (b"GIF89a" + b"\x00" * 20, b"", PNG + b"\x00" * bc.MAX_MEDIA_BYTES):
            try:
                await bc.save_media(db, ACTOR, bad)
            except bc.BroadcastError:
                pass
            else:
                raise AssertionError("a non-image or a too large file must be refused")
        assert (await bc.media(db, first))["mime"] == "image/png"
        print("PASS a picture is stored once; only JPEG/PNG/WebP up to 5 MB")

        # 2. The caption limit counts what the player sees, not the markup.
        long_html = "<b>" + "а" * bc.MAX_CAPTION + "</b>"
        bc.check_text(long_html, True, None)                      # without a picture: an ordinary message
        bc.check_text("<b>" + "а" * (bc.MAX_CAPTION - 1) + "&amp;</b>", True, first)
        try:
            bc.check_text(long_html + "!", True, first)
        except bc.BroadcastError as exc:
            assert "1024" in str(exc)
        else:
            raise AssertionError("a caption over 1024 visible characters must be refused")
        try:
            await bc.create(db, ACTOR, None, "x", segment={"kind": "players", "players": PLAYERS}, media_id=999_999_999)
        except bc.BroadcastError:
            pass
        else:
            raise AssertionError("an unknown picture number must be refused")
        print("PASS the caption limit counts visible characters; an unknown picture is refused")

        # 3. A template keeps its picture.
        tid = await bc.save_template(db, ACTOR, "Гонка", "🏁 <b>Гонка</b>", True, None, first)
        assert next(t for t in await bc.templates(db) if t["id"] == tid)["media_id"] == first
        print("PASS a template keeps its picture")

        made = await bc.create(db, ACTOR, None, "🏁 <b>Гонка за Пропуском</b>", "photo-1", True,
                               segment={"kind": "players", "players": [*PLAYERS, BLOCKED]}, media_id=first)
        assert (await bc.get(db, made.id))["media_id"] == first

    # 4. Sending: photos with the caption; the file goes to Telegram once, then its file_id.
    bot = FakeBot()
    bc.PAUSE["players"] = 0
    await bc.run(bot, pool_db, made.id, "players", "🏁 <b>Гонка за Пропуском</b>", True, None, first)
    assert sorted(c for c, *_ in bot.photos) == sorted(PLAYERS) and not bot.messages
    payloads = [p for _, p, _ in bot.photos]
    assert not isinstance(payloads[0], str) and all(p == "tg-file-1" for p in payloads[1:]), payloads
    assert all(cap == "🏁 <b>Гонка за Пропуском</b>" for *_, cap in bot.photos)
    async with pool_db() as db:
        assert (await bc.media(db, first))["file_id"] == "tg-file-1", "the file_id is kept for later sends"
        report = await bc.get(db, made.id)
        assert report["sent"] == len(PLAYERS) and report["failed"] == 1 and report["status"] == "done", report
    print("PASS the broadcast goes out as photos; the file is uploaded once, then sent by file_id")

    # 5. «Повтор недоставленным» keeps the picture and already uses the stored file_id.
    async with pool_db() as db:
        again = await bc.retry_failed(db, ACTOR, made.id)
        assert (await bc.get(db, again.id))["media_id"] == first
    bot2 = FakeBot()
    await bc.run(bot2, pool_db, again.id, "players", "🏁 <b>Гонка за Пропуском</b>", True, None, first)
    assert not bot2.photos and not bot2.messages, "the only failed target is still blocked"
    print("PASS a retry keeps the picture")

    # 6. Without a picture nothing changes: a text message.
    async with pool_db() as db:
        plain = await bc.create(db, ACTOR, None, "Просто текст", "plain-1", False, segment={"kind": "players", "players": PLAYERS[:1]})
    bot3 = FakeBot()
    await bc.run(bot3, pool_db, plain.id, "players", "Просто текст", False, None, None)
    assert bot3.messages == [(PLAYERS[0], "Просто текст")] and not bot3.photos
    print("PASS a broadcast without a picture is an ordinary message")


async def run(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    from bot.core.database import init_db
    from infrastructure.database import create_pool
    await create_pool()
    await init_db()
    await proof()
    print("PASS broadcast with a picture on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    asyncio.run(run(args.dsn))
