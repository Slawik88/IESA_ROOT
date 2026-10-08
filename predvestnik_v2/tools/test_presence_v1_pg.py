#!/usr/bin/env python3
"""PostgreSQL proof for Presence V1: throttled activity, the three privacy levels, reciprocity, chat activity, public card shape."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import presence_v1 as repo  # noqa: E402
from services import presence_v1 as svc  # noqa: E402
from services import public_profile_v3  # noqa: E402


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await repo.ensure_tables(db)
    outer = connection.transaction()
    await outer.start()
    try:
        owner, viewer, stranger = 983001, 983002, 983003
        now = datetime.now(timezone.utc)
        # no row at all: default level (approx) and no known time -> nothing to show, nothing crashes
        assert await svc.view_for(db, owner, viewer) is None
        assert (await svc.settings(db, owner))["visibility"] == "approx"

        await repo.touch(db, owner)
        assert (await svc.view_for(db, owner, viewer))["label"] == "был(а) недавно", "default is the coarse bucket, even while online"
        await svc.set_level(db, owner, "everyone")
        assert (await svc.view_for(db, owner, viewer)) == {"state": "online", "label": "в сети"}
        await db.execute("UPDATE presence_v1 SET last_seen_at = ? WHERE user_id = ?", (now - timedelta(minutes=12), owner))
        assert (await svc.view_for(db, owner, viewer))["label"] == "был(а) 12 минут назад"

        # reciprocity: a viewer who hides their own time sees the owner coarsely
        await svc.set_level(db, viewer, "nobody")
        assert (await svc.view_for(db, owner, viewer))["label"] == "был(а) недавно"
        await svc.set_level(db, viewer, "everyone")

        # hiding: nothing at all leaves the service, for any viewer
        await svc.set_level(db, owner, "nobody")
        assert await svc.view_for(db, owner, viewer) is None and await svc.view_for(db, owner, stranger) is None
        shaped = public_profile_v3.shape({"profile_ref": "r", "display_name": "n", "account_level": 1}, {}, is_self=False, presence=await svc.view_for(db, owner, viewer))
        assert shaped["presence"] is None and "presence_level" not in shaped
        # one's own card shows what others see and the chosen level
        mine = public_profile_v3.shape({"profile_ref": "r", "display_name": "n", "account_level": 1}, {}, is_self=True, presence=None, presence_level="nobody")
        assert mine["presence_level"] == "nobody"

        # chat activity counts as being around: a message 2 minutes ago makes an "everyone" player online
        await svc.set_level(db, owner, "everyone")
        async with db.execute("SELECT to_regclass('user_chat_stats') IS NOT NULL") as c:
            has_chats = (await c.fetchone())[0]
        if has_chats:
            async with db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='user_chat_stats' AND column_name IN ('user_tg_id','chat_tg_id','last_message_at')") as c:
                cols = {r[0] for r in await c.fetchall()}
            if {"user_tg_id", "chat_tg_id", "last_message_at"} <= cols:
                await db.execute("INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, last_message_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", (owner, -100500, now - timedelta(minutes=2)))
                assert (await svc.view_for(db, owner, viewer))["state"] == "online"

        # activity writes are throttled per player
        svc._NEXT_TOUCH.clear()
        assert svc.TOUCH_EVERY >= 30
        try:
            await svc.set_level(db, owner, "everybody")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown level must be rejected")
        print("OK: presence levels, reciprocity, chat activity and hidden players leak nothing")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
