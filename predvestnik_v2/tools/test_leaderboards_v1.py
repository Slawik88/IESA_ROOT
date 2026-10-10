#!/usr/bin/env python3
"""Leaderboards service: period maths, paging, membership gate and bot exclusion (no database needed)."""
import asyncio
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    import aiosqlite  # noqa: F401
except ImportError:
    stub = types.ModuleType("aiosqlite")
    stub.Connection = object
    sys.modules["aiosqlite"] = stub

from services import leaderboards_v1 as lb  # noqa: E402

THURSDAY = datetime(2026, 10, 8, tzinfo=timezone.utc)
assert lb.period_bounds(THURSDAY, "day") == ("2026-10-08", "2026-10-08")
assert lb.period_bounds(THURSDAY, "week") == ("2026-10-05", "2026-10-08")
assert lb.period_bounds(THURSDAY, "month") == ("2026-10-01", "2026-10-08")
assert lb.period_bounds(THURSDAY, "all_time") is None
assert lb.previous_bounds(("2026-10-05", "2026-10-08"))[1] == "2026-10-04"
assert lb.previous_bounds(None) is None


class Cursor:
    def __init__(self, rows): self.rows = rows
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def fetchall(self): return self.rows


class Db:
    def execute(self, sql, params=()): return Cursor([{"chat_id": 7, "title": "Друзья"}])


async def fake_global_dates(db, start, end, limit=500):
    return [{"user_tg_id": i, "msg_count": 100 - i, "is_vip": i == 1} for i in range(1, 26)] + [{"user_tg_id": 999, "msg_count": 1}]


async def fake_position(db, **kwargs):
    return {"place": 3, "msg_count": 98, "total_count": 26}


async def fake_players(db, user_ids):
    return {int(u): {"display_name": f"P{u}", "profile_ref": f"r{u}"} for u in user_ids}


async def fake_tz(db, chat_id): return 3


lb.stats_repo.get_top_messages_global_for_dates = fake_global_dates
lb.stats_repo.get_top_messages_global_all_time = lambda db, limit=500: fake_global_dates(db, None, None)
lb.stats_repo.get_message_top_position = fake_position
lb.public_profiles.player_projection = lambda db, user_ids: fake_players(db, user_ids)
lb.stats_repo.get_top_messages_for_dates = lambda db, chat_id, start, end, limit=500: fake_global_dates(db, start, end)
lb.stats_repo.get_top_messages = lambda db, chat_id, period, limit=500: fake_global_dates(db, None, None)
lb.get_chat_timezone = fake_tz
lb.bot_tg_id = lambda: 999


async def fake_styles(db, ids):
    return {1: {"id": "forest", "name": "Лесной Странник", "tier": "D", "ceiling": "D", "pal": ["#6fdc98", "#2e9a68", "#d9c28f"], "kinds": {"name": "grad"}, "sig": None, "title": "t"}}


lb.appearance_public_v3.nick_styles = fake_styles


async def main() -> None:
    db = Db()
    page0 = await lb.message_top_page(db, user_id=3, scope="global", period="week", page=0, now=THURSDAY)
    assert page0["pages"] == 3 and len(page0["items"]) == 10 and page0["items"][0]["place"] == 1
    assert all(item["name"] != "P999" for item in page0["items"]), "bot account must be excluded"
    assert page0["items"][2]["is_me"] and page0["items"][0]["is_vip"]
    assert page0["items"][0]["look"]["tier"] == "D" and page0["items"][1]["look"] is None
    assert page0["items"][0]["ref"] == "r1"
    assert page0["personal"]["place"] == 3 and "delta" in page0["personal"]
    page_last = await lb.message_top_page(db, user_id=3, scope="global", period="all_time", page=99, now=THURSDAY)
    assert page_last["page"] == 2 and page_last["items"][0]["place"] == 21
    try:
        await lb.message_top_page(db, user_id=3, scope="local", period="week", chat_id=555, now=THURSDAY)
    except lb.NotAMember:
        pass
    else:
        raise AssertionError("non-member must not read a local board")
    ok = await lb.message_top_page(db, user_id=3, scope="local", period="day", chat_id=7, now=THURSDAY)
    assert ok["chat_id"] == 7 and ok["chats"][0]["title"] == "Друзья"
    try:
        await lb.message_top_page(db, user_id=3, scope="bogus", period="week")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown scope must be rejected")
    compact = await lb.message_top(db, user_id=3, period="week", now=THURSDAY)
    assert compact["top"][0]["place"] == 1 and compact["personal"]["place"] == 3


asyncio.run(main())
print("OK: leaderboards periods, paging, bot exclusion and membership gate")
