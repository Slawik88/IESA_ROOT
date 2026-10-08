#!/usr/bin/env python3
"""PostgreSQL proof for marks: hand-given marks (grant, revoke, log, guards), composition with staff and earned marks, list rows."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import marks_v1 as repo  # noqa: E402
from infrastructure.repositories import skins_v3 as skins_repo  # noqa: E402
from services import marks_v1 as marks  # noqa: E402


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def conflict(coro, fragment: str) -> None:
    try:
        await coro
    except marks.MarkConflict as exc:
        assert fragment in str(exc), (fragment, str(exc))
    else:
        raise AssertionError(f"expected conflict: {fragment}")


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await repo.ensure_tables(db)
    await skins_repo.ensure_tables(db)
    outer = connection.transaction()
    await outer.start()
    try:
        admin, player, helper, nobody = 983001, 983002, 983003, 983004
        for uid, rank in ((admin, 3), (player, 0), (helper, 1), (nobody, 0)):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username,global_rank) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET global_rank=EXCLUDED.global_rank", (uid, f"m{uid}", rank))

        # guards: only hand-given marks, only with a reason, only for a real player
        await conflict(marks.grant(db, player, "helper", admin, "x"), "идёт вместе с рангом")
        await conflict(marks.grant(db, player, "veteran", admin, "x"), "считается сама")
        await conflict(marks.grant(db, player, "nope", admin, "x"), "Такой метки нет")
        await conflict(marks.grant(db, player, "tester", admin, "  "), "причину")
        await conflict(marks.grant(db, 999_999_999, "tester", admin, "x"), "Такого игрока нет")

        # grant is a change once; a repeat does nothing and writes no second log row
        assert await marks.grant(db, player, "tester", admin, "первая волна тестов") == "Тестер"
        await conflict(marks.grant(db, player, "tester", admin, "ещё раз"), "уже есть")
        assert await marks.grant(db, player, "founder", admin, "с первого дня") == "Основатель"
        view = await marks.admin_view(db, player)
        assert [m["id"] for m in view["given"]] == ["tester", "founder"] and [h["action"] for h in view["history"]] == ["grant", "grant"]
        assert view["history"][1]["reason"] == "первая волна тестов" and view["history"][0]["actor_id"] == admin and "partner" in {g["id"] for g in view["grantable"]}

        # composition: staff by rank, granted from the table, earned from facts (a season skin counts)
        await skins_repo.grant(db, player, "pumpkin_lantern")
        await skins_repo.grant(db, player, "forest")
        worn = await marks.marks_for(db, player, global_rank=0, streak=31, joined="2020-01-01T00:00:00", messages=20_000)
        assert [m["id"] for m in worn] == ["founder", "tester", "streak30", "veteran", "chatter", "halloween"], worn
        assert [m["id"] for m in await marks.marks_for(db, helper, global_rank=1)] == ["helper"]
        assert await marks.marks_for(db, nobody, global_rank=0) == []
        with mock.patch.dict(os.environ, {"DEVELOPER_ID": str(nobody)}):
            assert [m["id"] for m in await marks.marks_for(db, nobody, global_rank=0)] == ["developer"], "the developer id wears the developer mark"

        # the sheet: what is worn and what is still ahead, with progress
        sheet = await marks.sheet(db, player, global_rank=0, streak=12, joined="2020-01-01T00:00:00", messages=100)
        ahead = {a["id"]: a for a in sheet["ahead"]}
        assert [m["id"] for m in sheet["marks"]] == ["founder", "tester", "veteran", "halloween"] and ahead["streak30"]["have"] == 12 and ahead["streak30"]["need"] == 30
        assert "new_year" in ahead and "halloween" not in ahead and all("how" in a for a in ahead.values())

        # list rows: staff and hand-given marks only, heaviest one
        batch = await marks.top_mark_batch(db, [admin, player, helper, nobody])
        with mock.patch.dict(os.environ, {"DEVELOPER_ID": ""}):
            batch = await marks.top_mark_batch(db, [admin, player, helper, nobody])
        assert batch[admin]["id"] == "developer" and batch[player]["id"] == "founder" and batch[helper]["id"] == "helper" and nobody not in batch
        assert set(batch[player]) == {"id", "title", "glyph", "tone"}

        # revoke: only a given mark, with a reason, once; the log keeps both sides
        await conflict(marks.revoke(db, player, "helper", admin, "x"), "выданную вручную")
        await conflict(marks.revoke(db, player, "partner", admin, "ошибка"), "нет такой метки")
        await conflict(marks.revoke(db, player, "tester", admin, ""), "причину")
        assert await marks.revoke(db, player, "tester", admin, "выдана по ошибке") == "Тестер"
        assert [h["action"] for h in await repo.history(db, player)] == ["revoke", "grant", "grant"]
        assert await repo.granted(db, player) == ["founder"]
        print("OK: marks v1 grant, revoke, log, guards, composition and list rows")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
