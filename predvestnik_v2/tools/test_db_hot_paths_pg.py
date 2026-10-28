"""S04 on real PostgreSQL: no DDL per season-pass read, SQL budget of /profile/me and of the tops, the profile snapshot
and its ETag, tab time in one batch, identity rows not rewritten per message, the purge entry check, background indexes.

Run on an EMPTY loopback database:
    DSN=$(bash docs/roadmap/env-setup.sh --fresh-db pv_test_db_hot_paths)   # from the repository root
    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_db_hot_paths_pg.py --dsn "$DSN"
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "990000001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg  # noqa: E402

# Budgets: the cold own profile is the full set of reads (S04: 32 -> 30 for this player, the three game results merged);
# a snapshot hit only checks that the account is active.
PROFILE_COLD_MAX, PROFILE_WARM_MAX = 30, 1
PLAYER, OTHER, CHAT = 990000101, 990000102, -1009900001

_counting = contextvars.ContextVar("counting", default=False)
_statements: list[str] = []


def _install_counter() -> None:
    connection = asyncpg.connection.Connection
    for name in ("fetch", "fetchrow", "fetchval", "execute", "executemany"):
        original = getattr(connection, name)

        def counted(self, query, *rest, __original=original, **kwargs):
            if _counting.get() and not str(query).startswith("SELECT pg_advisory_unlock_all()"):   # pool reset on release
                _statements.append(" ".join(str(query).split()))
            return __original(self, query, *rest, **kwargs)
        setattr(connection, name, counted)


@contextmanager
def counting():
    _statements.clear()
    token = _counting.set(True)
    try:
        yield _statements
    finally:
        _counting.reset(token)


async def season_pass_reads_without_ddl(client, headers) -> None:
    await client.get("/season-pass/me", headers=headers)
    with counting() as sql:
        response = await client.get("/season-pass/me", headers=headers)
    assert response.status_code == 200, response.text
    assert not [s for s in sql if s.upper().startswith(("CREATE", "ALTER"))], sql


async def own_profile_snapshot(client, headers) -> None:
    from FastAPI import notifications, profile_snapshot
    await client.get("/profile/me", headers=headers)   # one-time schema checks of the process, then normal use
    profile_snapshot.reset()
    with counting() as sql:
        cold = await client.get("/profile/me", headers=headers)
    assert cold.status_code == 200, cold.text
    assert len(sql) <= PROFILE_COLD_MAX, (len(sql), sql)
    cold_count = len(sql)
    etag = cold.headers["etag"]
    assert cold.headers["cache-control"] == "private, no-cache"

    with counting() as sql:
        warm = await client.get("/profile/me", headers=headers)
    assert warm.json() == cold.json() and len(sql) <= PROFILE_WARM_MAX, sql
    warm_count = len(sql)
    unchanged = await client.get("/profile/me", headers={**headers, "if-none-match": etag})
    assert unchanged.status_code == 304 and not unchanged.content and unchanged.headers["etag"] == etag

    # A write of the player ends the snapshot: the next read sees the change at once.
    await client.post("/analytics/tab", headers=headers, json={"tab": "profile", "session_id": "s04"})
    with counting() as sql:
        await client.get("/profile/me", headers=headers)
    assert len(sql) == cold_count, (len(sql), cold_count)

    # So does a live event about the player (bot-side change: balance, data_changed, activity).
    from infrastructure.database import get_pool
    async with get_pool().acquire() as connection:
        await connection.execute("UPDATE users SET user_balance_mora = user_balance_mora + 5 WHERE user_tg_id = $1", PLAYER)
    await notifications.notify(PLAYER, {"type": "balance_changed"})
    fresh = await client.get("/profile/me", headers=headers)
    assert fresh.json()["mora"] == cold.json()["mora"] + 5 and fresh.headers["etag"] != etag

    # A read that started before a write never stores what it read for later readers.
    stale_key = profile_snapshot.key(PLAYER)
    profile_snapshot.forget(PLAYER)
    profile_snapshot.put(stale_key, b"{}")
    assert profile_snapshot.get(profile_snapshot.key(PLAYER)) is None
    print(f"/profile/me SQL statements: cold {cold_count}, snapshot hit {warm_count}")


async def tops_from_memory(client, headers) -> None:
    from services import leaderboards_v1
    leaderboards_v1._BOARDS.clear()
    leaderboards_v1._PLACES.clear()
    first = await client.get("/leaderboards/messages?period=week", headers=headers)
    assert first.status_code == 200, first.text
    with counting() as sql:
        again = await client.get("/leaderboards/messages?period=week", headers=headers)
    assert again.json()["top"] == first.json()["top"]
    ranking = lambda statements: [s for s in statements if "FROM daily_user_stats d" in s or "FROM user_chat_stats s" in s
                                  or "ROW_NUMBER()" in s]   # the board and the own place; decoration of 10 rows stays
    assert not ranking(sql), sql
    with counting() as sql:
        await client.get("/leaderboards/messages?period=all_time", headers=headers)   # another board: its own key
    assert ranking(sql), sql
    full = await client.get("/leaderboards/messages/full?scope=global&period=week", headers=headers)
    assert full.status_code == 200 and full.json()["personal"]["place"] == 1, full.text


async def tab_time_in_one_batch(client, headers) -> None:
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from services import tab_time
    await client.post("/analytics/tab", headers=headers, json={"tab": "top", "session_id": "s04"})
    with counting() as sql:
        for _ in range(3):
            response = await client.post("/analytics/tab-duration", headers=headers,
                                         json={"tab": "top", "session_id": "s04", "delta_sec": 60})
            assert response.status_code == 200
        await client.post("/analytics/tab-duration", headers=headers,
                          json={"tab": "top", "session_id": "s04", "delta_sec": 100000})   # clamped to 120
    assert not [s for s in sql if "site_analytics" in s], sql
    async with get_pool().acquire() as connection:
        with counting() as sql:
            assert await tab_time.flush(PGAdapter(connection)) == 1
        assert len(sql) == 1, sql
        total = await connection.fetchval(
            "SELECT duration_sec FROM site_analytics WHERE user_id=$1 AND tab='top' AND session_id='s04' "
            "ORDER BY visited_at DESC LIMIT 1", PLAYER)
    assert total == 3 * 60 + 120, total
    for n in range(tab_time.MAX_PENDING_PER_PLAYER + 5):   # one player inventing sessions fills only their own share
        tab_time.add(OTHER, "top", f"fake-{n}", 60)
    tab_time.add(PLAYER, "top", "s04", 60)
    assert len(tab_time._pending) == tab_time.MAX_PENDING_PER_PLAYER + 1
    tab_time._pending.clear()
    tab_time._per_player.clear()


async def identity_rows_kept(db) -> None:
    from bot.chat.tracking import record_message

    def message(title: str, username: str) -> SimpleNamespace:
        return SimpleNamespace(from_user=SimpleNamespace(id=OTHER, is_bot=False, username=username, full_name="Второй"),
                               chat=SimpleNamespace(id=CHAT, type="supergroup", title=title))

    async def versions() -> tuple:
        return (await db.connection.fetchval("SELECT xmin::text FROM users WHERE user_tg_id=$1", OTHER),
                await db.connection.fetchval("SELECT xmin::text FROM chat_settings WHERE chat_id=$1", CHAT))

    await record_message(db, message("Чат", "second"))
    before = await versions()
    await record_message(db, message("Чат", "second"))
    assert await versions() == before, "the same nick and title must not rewrite the rows"
    counts = await db.connection.fetchrow(
        "SELECT s.user_messages_count_all_time AS total, d.message_count AS today FROM user_chat_stats s "
        "JOIN daily_user_stats d ON d.user_id=s.user_tg_id AND d.chat_id=s.chat_tg_id WHERE s.user_tg_id=$1 AND s.chat_tg_id=$2",
        OTHER, CHAT)
    assert (counts["total"], counts["today"]) == (2, 2), dict(counts)
    await record_message(db, message("Новое название", "renamed"))
    after = await versions()
    assert after[0] != before[0] and after[1] != before[1]
    assert await db.connection.fetchval("SELECT user_tg_username FROM users WHERE user_tg_id=$1", OTHER) == "renamed"
    await db.execute("UPDATE chat_settings SET bot_left_at = NOW() WHERE chat_id = ?", (CHAT,))
    await record_message(db, message("Новое название", "renamed"))
    assert await db.connection.fetchval("SELECT bot_left_at FROM chat_settings WHERE chat_id=$1", CHAT) is None


async def purge_entry(client, headers, db) -> None:
    from infrastructure.repositories import moderation_chats
    assert (await client.get("/purge-v1/access", headers=headers)).json() == {"available": False}
    await db.execute("UPDATE chat_settings SET owner_id = ? WHERE chat_id = ?", (PLAYER, CHAT))
    assert (await client.get("/purge-v1/access", headers=headers)).json() == {"available": True}
    listing = await moderation_chats.listing(db, user_id=PLAYER, purge_only=True)
    assert [item["id"] for item in listing["items"]] == [CHAT]
    await db.execute("UPDATE chat_settings SET bot_left_at = NOW() WHERE chat_id = ?", (CHAT,))   # the bot left: nothing to purge
    assert not await moderation_chats.has_purge_access(db, user_id=PLAYER)


async def background_indexes(dsn: str) -> None:
    from infrastructure import db_indexes
    builder = await asyncpg.connect(dsn)
    writer = await asyncpg.connect(dsn)
    try:
        await writer.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) "
                             "SELECT i % 5000, -1 - i % 40, to_char(DATE '2026-01-01' + i % 300, 'YYYY-MM-DD'), 1 "
                             "FROM generate_series(1, 400000) i ON CONFLICT DO NOTHING")
        build = asyncio.create_task(db_indexes.build_all(builder))
        await asyncio.sleep(0.05)
        # Writes go on while the indexes are built (CONCURRENTLY): a short lock timeout proves nothing waits.
        await writer.execute("SET lock_timeout = '300ms'")
        for i in range(20):
            await writer.execute("INSERT INTO daily_user_stats (user_id, chat_id, date) VALUES ($1, -7, '2026-10-28') "
                                 "ON CONFLICT DO NOTHING", 7_000_000 + i)
            await writer.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (-7, $1, 1, 'warn')", i)
        first = await build
        assert {first[name] for name, _, ext in db_indexes.INDEXES if not ext} == {"built"}, first
        assert {first[name] for name, _, ext in db_indexes.INDEXES if ext} == {"skipped"}, first   # no pg_trgm here
        assert set((await db_indexes.build_all(builder)).values()) <= {"ready", "skipped"}

        # A build cut by a deploy leaves an INVALID index: the next start drops and builds it again (local superuser fakes it).
        await builder.execute("UPDATE pg_index SET indisvalid = false WHERE indexrelid = 'idx_mod_user'::regclass")
        assert (await db_indexes.build_all(builder))["idx_mod_user"] == "built"
        assert await builder.fetchval("SELECT indisvalid FROM pg_index WHERE indexrelid = 'idx_mod_user'::regclass")

        # With the extension installed the search indexes are built too.
        await builder.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        third = await db_indexes.build_all(builder)
        assert {third[name] for name, _, ext in db_indexes.INDEXES if ext} == {"built"}, third

        await builder.execute("SET enable_seqscan = off")   # tiny test tables: prove the index CAN serve the hot query
        plan = "\n".join(r[0] for r in await builder.fetch(
            "EXPLAIN SELECT user_id, SUM(message_count) FROM daily_user_stats WHERE date >= '2026-10-01' AND date <= '2026-10-07' GROUP BY user_id"))
        assert "idx_daily_stats_date_user" in plan, plan
        plan = "\n".join(r[0] for r in await builder.fetch(
            "EXPLAIN SELECT id FROM moderation_logs WHERE created_at > (NOW() - make_interval(days => 7))::timestamp"))
        assert "idx_mod_created_at" in plan, plan
    finally:
        await builder.close()
        await writer.close()


async def main() -> None:
    import httpx
    from FastAPI.auth import create_session_token
    import FastAPI.main as web
    from bot.chat.schema import ensure_chat_schema
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import season_pass

    pool = await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_runtime_schema(pool)
    async with pool.acquire() as connection:
        db = PGAdapter(connection)
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, 'hot_paths') ON CONFLICT DO NOTHING", (PLAYER,))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time) VALUES (?, ?, 5) "
                         "ON CONFLICT DO NOTHING", (PLAYER, CHAT))
        await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) "
                         "VALUES (?, ?, to_char(CURRENT_DATE, 'YYYY-MM-DD'), 5) ON CONFLICT DO NOTHING", (PLAYER, CHAT))
        await season_pass.ensure_tables(db)
    _install_counter()

    headers = {"x-session-token": create_session_token(PLAYER)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://test") as client:
        await season_pass_reads_without_ddl(client, headers)
        await own_profile_snapshot(client, headers)
        await tops_from_memory(client, headers)
        await tab_time_in_one_batch(client, headers)
        async with get_pool().acquire() as connection:
            db = PGAdapter(connection)
            await identity_rows_kept(db)
            await purge_entry(client, headers, db)
    await background_indexes(args.dsn)
    await get_pool().close()
    print("OK: season pass without DDL, /profile/me budget, snapshot and ETag, tops from memory, tab time in one batch, "
          "identity rows kept, purge entry check, indexes built CONCURRENTLY while writes go on")


if __name__ == "__main__":
    asyncio.run(main())
