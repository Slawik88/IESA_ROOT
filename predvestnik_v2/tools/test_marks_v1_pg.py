#!/usr/bin/env python3
"""PostgreSQL proof for marks: hand-given marks (grant, revoke, log, guards), earned marks awarded once and kept (retroactive, sticky), list rows."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
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
        admin, player, helper, nobody, late, old_chat, quiet = 983001, 983002, 983003, 983004, 983005, 983006, 983007
        for uid, rank in ((admin, 3), (player, 0), (helper, 1), (nobody, 0), (late, 0), (old_chat, 0), (quiet, 0)):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username,global_rank) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET global_rank=EXCLUDED.global_rank", (uid, f"m{uid}", rank))

        # guards: only what the console may give, only with a reason, only for a real player; earned marks are the server's alone
        await conflict(marks.grant(db, player, "veteran", admin, "x"), "сервер выдаёт сам")
        await conflict(marks.grant(db, player, "nope", admin, "x"), "Такой метки нет")
        await conflict(marks.grant(db, player, "tester", admin, "  "), "причину")
        await conflict(marks.grant(db, 999_999_999, "tester", admin, "x"), "Такого игрока нет")

        # the bot rank gives no badge by itself: admin marks are manual
        assert await marks.marks_for(db, helper) == [] and await marks.marks_for(db, admin) == []
        assert (await marks.admin_view(db, helper))["rank_hint"]["id"] == "helper" and (await marks.admin_view(db, admin))["rank_hint"]["id"] == "developer"
        assert (await marks.admin_view(db, player))["rank_hint"] is None
        assert await marks.grant(db, helper, "helper", admin, "назначен хелпером") == "Хелпер"
        assert await marks.grant(db, admin, "developer", admin, "разработчик проекта") == "Разработчик"
        assert (await marks.admin_view(db, helper))["rank_hint"] is None, "the hint disappears once the badge is given"
        assert [m["id"] for m in await marks.marks_for(db, helper)] == ["helper"]

        # grant is a change once; a repeat does nothing and writes no second log row
        assert await marks.grant(db, player, "tester", admin, "первая волна тестов") == "Тестер"
        await conflict(marks.grant(db, player, "tester", admin, "ещё раз"), "уже есть")
        assert await marks.grant(db, player, "founder", admin, "с первого дня") == "Основатель"
        view = await marks.admin_view(db, player)
        assert [m["id"] for m in view["given"]] == ["tester", "founder"] and [h["action"] for h in view["history"]] == ["grant", "grant"] and view["earned"] == []
        assert view["history"][1]["reason"] == "первая волна тестов" and view["history"][0]["actor_id"] == admin and {"partner", "helper"} <= {g["id"] for g in view["grantable"]}
        assert "veteran" not in {g["id"] for g in view["grantable"]}

        # earned marks are awarded on sight, stored once (actor 0, «auto»), logged once, and kept when the facts later drop
        await skins_repo.grant(db, player, "pumpkin_lantern")
        await skins_repo.grant(db, player, "forest")
        worn = await marks.marks_for(db, player, streak=31, joined="2020-01-01T00:00:00", messages=20_000)
        assert [m["id"] for m in worn] == ["founder", "tester", "streak30", "veteran", "chatter", "halloween"], worn
        stored = set(await repo.held(db, player))
        assert {"streak30", "veteran", "chatter", "halloween"} <= stored
        again = await marks.marks_for(db, player, streak=2, joined="2020-01-01T00:00:00", messages=100)
        assert [m["id"] for m in again] == [m["id"] for m in worn], "a streak that broke takes nothing away"
        autos = [h for h in await repo.history(db, player) if h["reason"] == "auto"]
        assert len(autos) == 4 and all(h["actor_id"] == 0 and h["action"] == "grant" for h in autos), "each earned mark is logged exactly once"
        assert {m["id"] for m in (await marks.admin_view(db, player))["earned"]} == {"streak30", "veteran", "chatter", "halloween"}

        # retroactive: the best streak ever counts. Legacy «Постоянство» progress, the old per-chat streak rows and the streak lost at a break
        await db.execute("INSERT INTO achievements(user_id, achievement_id, level, progress) VALUES (?, 'persistent', 3, 45) ON CONFLICT (user_id, achievement_id) DO UPDATE SET progress=45", (nobody,))
        assert [m["id"] for m in await marks.marks_for(db, nobody, streak=1)] == ["streak30"], "legacy best streak 45 earns the mark with a streak of 1 today"
        await db.execute("INSERT INTO daily_login(user_id, chat_id, streak, recovery_streak) VALUES (?, 0, 4, 33) ON CONFLICT (user_id, chat_id) DO UPDATE SET streak=4, recovery_streak=33", (late,))
        assert [m["id"] for m in await marks.marks_for(db, late, streak=4)] == ["streak30"], "the streak lost at the last break counts"
        await db.execute("INSERT INTO daily_login(user_id, chat_id, streak) VALUES (?, -100500, 36) ON CONFLICT (user_id, chat_id) DO UPDATE SET streak=36", (old_chat,))
        assert [m["id"] for m in await marks.marks_for(db, old_chat, streak=0)] == ["streak30"], "an old per-chat streak row counts too"
        assert await marks.marks_for(db, quiet, streak=29) == [], "29 days is not 30"

        # the sheet: what is worn and what is still ahead, with progress
        sheet = await marks.sheet(db, quiet, streak=12, joined="2020-01-01T00:00:00", messages=100)
        ahead = {a["id"]: a for a in sheet["ahead"]}
        assert [m["id"] for m in sheet["marks"]] == ["veteran"] and ahead["streak30"]["have"] == 12 and ahead["streak30"]["need"] == 30
        assert "new_year" in ahead and "halloween" in ahead and "veteran" not in ahead and all("how" in a for a in ahead.values()) and sheet["name"] == "Регалии"

        # list rows: the heaviest stored mark, one per player
        batch = await marks.top_mark_batch(db, [admin, player, helper, nobody, quiet, 999_999_998])
        assert batch[admin]["id"] == "developer" and batch[player]["id"] == "founder" and batch[helper]["id"] == "helper" and batch[nobody]["id"] == "streak30"
        assert batch[quiet]["id"] == "veteran" and 999_999_998 not in batch and set(batch[player]) == {"id", "title", "glyph", "tone"}

        # revoke: only what the console may give, with a reason, once; the log keeps both sides
        await conflict(marks.revoke(db, player, "veteran", admin, "x"), "выданную вручную")
        await conflict(marks.revoke(db, player, "partner", admin, "ошибка"), "нет такой метки")
        await conflict(marks.revoke(db, player, "tester", admin, ""), "причину")
        assert await marks.revoke(db, player, "tester", admin, "выдана по ошибке") == "Тестер"
        assert [h["action"] for h in await repo.history(db, player)][0] == "revoke"
        assert "tester" not in await repo.held(db, player) and "founder" in await repo.held(db, player)
        assert await marks.revoke(db, helper, "helper", admin, "больше не хелпер") == "Хелпер" and await marks.marks_for(db, helper) == []
        print("OK: marks v1 grant, revoke, log, guards, retroactive and sticky earned marks, list rows")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
