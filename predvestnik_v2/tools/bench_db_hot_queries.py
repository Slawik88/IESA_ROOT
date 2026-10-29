"""Time the hot read paths of S04 (tops, admin search and journal, purge entry, purge violators) on synthetic volume.

Seeds an EMPTY loopback database once (~1M rows in daily_user_stats, 150k user_chat_stats, 500k moderation_logs),
then calls the real service functions and prints the median time of each, cold (no process cache):

    DSN=$(bash docs/roadmap/env-setup.sh --fresh-db pv_s04_bench)      # from the repository root
    BOT_TOKEN=1:x PYTHONPATH=. python tools/bench_db_hot_queries.py --dsn "$DSN" [--indexes] [--users 100000]

--indexes first builds the background indexes (infrastructure/db_indexes.py) the way production does.
--users sets how many players to seed (default 30 000; S10 measures the admin search on 100 000) — use a fresh database per size.
Run the same command with PYTHONPATH of an older checkout to compare before/after on the same data.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

USERS, CHATS, CHATS_PER_USER, DAYS_PER_CHAT, LOG_ROWS = 30_000, 300, 5, 7, 500_000
FIRST_CHAT = -1_000_000_000_000


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


def seed_sql(users: int) -> tuple[str, ...]:
    return tuple(sql.replace(str(USERS), str(users)) for sql in SEED)


SEED = (
    f"INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) "
    f"SELECT i, 'player_' || i, 'Игрок ' || i FROM generate_series(1, {USERS}) i ON CONFLICT DO NOTHING",
    f"INSERT INTO chat_settings (chat_id, chat_title) "
    f"SELECT {FIRST_CHAT} - i, 'Чат ' || i FROM generate_series(1, {CHATS}) i ON CONFLICT DO NOTHING",
    f"INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, last_message_at, is_left) "
    f"SELECT u, {FIRST_CHAT} - 1 - ((u * 7 + k * 13) % {CHATS}), (u * k) % 900 + 1, "
    f"NOW() - make_interval(mins => (u * 37 + k * 101) % 200000), FALSE "
    f"FROM generate_series(1, {USERS}) u, generate_series(1, {CHATS_PER_USER}) k ON CONFLICT DO NOTHING",
    f"INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) "
    f"SELECT s.user_tg_id, s.chat_tg_id, to_char(CURRENT_DATE - ((s.user_tg_id * 31 + d * 17 + s.chat_tg_id) % 120)::int, 'YYYY-MM-DD'), "
    f"(s.user_tg_id + d) % 60 + 1 FROM user_chat_stats s, generate_series(1, {DAYS_PER_CHAT}) d ON CONFLICT DO NOTHING",
    f"INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason, created_at) "
    f"SELECT {FIRST_CHAT} - 1 - (i % {CHATS}), i % {USERS} + 1, 7000000 + i % 5, "
    f"(ARRAY['mute','warn','ban','unmute','kick','purge_start'])[i % 6 + 1], 'synthetic', "
    f"NOW() - make_interval(mins => i % 525600) FROM generate_series(1, {LOG_ROWS}) i",
)


async def seed(db, users: int) -> None:
    async with db.execute("SELECT COUNT(*) FROM moderation_logs") as cursor:
        if int((await cursor.fetchone())[0]) >= LOG_ROWS:
            return
    await db.execute("SET statement_timeout = 0")   # 100k players take longer than the app's 30 s limit to seed
    for sql in seed_sql(users):
        await db.execute(sql)
    for table in ("users", "chat_settings", "user_chat_stats", "daily_user_stats", "moderation_logs"):
        await db.execute(f"ANALYZE {table}")
    await db.execute("RESET statement_timeout")


async def timed(label: str, call, runs: int = 5) -> None:
    from services import leaderboards_v1
    samples = []
    for _ in range(runs):
        for name in ("_BOARDS", "_PLACES"):
            cache = getattr(leaderboards_v1, name, None)
            if cache is not None:
                cache.clear()
        started = time.perf_counter()
        await call()
        samples.append((time.perf_counter() - started) * 1000)
    print(f"{label:<44} {statistics.median(samples):8.1f} ms")


async def run(dsn: str, build_indexes: bool, users: int) -> None:
    os.environ["DATABASE_URL"] = dsn
    from bot.chat.purge import Plan, find_violators
    from bot.chat.schema import ensure_chat_schema
    from bot.core.database import init_db
    from bot.startup_schema import ensure_runtime_schema
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import moderation_chats
    from services import admin_people, leaderboards_v1

    pool = await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_runtime_schema(pool)
    async with pool.acquire() as connection:
        db = PGAdapter(connection)
        await seed(db, users)
        if build_indexes:
            from infrastructure import db_indexes
            await db_indexes.build_all(connection)
        async with db.execute("SELECT COUNT(*) FROM daily_user_stats") as cursor:
            print(f"daily_user_stats rows: {(await cursor.fetchone())[0]}")
        user, chat = 12_345, FIRST_CHAT - 1 - (12_345 * 7 + 13) % CHATS
        today = datetime.now(timezone.utc).date()
        await timed("top home: week", lambda: leaderboards_v1.message_top(db, user_id=user, period="week"))
        await timed("top home: all time", lambda: leaderboards_v1.message_top(db, user_id=user, period="all_time"))
        await timed("top full: global month", lambda: leaderboards_v1.message_top_page(db, user_id=user, scope="global", period="month"))
        await timed("top full: chats week", lambda: leaderboards_v1.message_top_page(db, user_id=user, scope="chats", period="week"))
        await timed("top full: local week", lambda: leaderboards_v1.message_top_page(db, user_id=user, scope="local", period="week", chat_id=chat))
        await timed("admin: search by name part", lambda: admin_people.search(db, "player_1234"))
        await timed("admin: search empty (recent)", lambda: admin_people.search(db, ""))
        if "paged" in admin_people.search.__code__.co_varnames:   # S10: pages, status and new filters
            await timed("admin: search name part, paged", lambda: admin_people.search(db, "player_1234", paged=True))
            await timed("admin: filter idle:30, paged", lambda: admin_people.search(db, "", flt="idle:30", paged=True))
            await timed("admin: filter active:7, paged", lambda: admin_people.search(db, "", flt="active:7", paged=True))
            await timed("admin: filter silent, paged", lambda: admin_people.search(db, "", flt="silent", paged=True))
            await timed("admin: filter idle:30, page 50", lambda: admin_people.search(db, "", flt="idle:30", offset=1500, paged=True))
            await timed("admin: player wallet", lambda: admin_people.wallet(db, user))
        await timed("admin: journal 7 days", lambda: admin_people.feed(db, days=7))
        await timed("admin: player history", lambda: admin_people.history(db, user_id=user))
        await timed("more: purge entry (chat listing)", lambda: moderation_chats.listing(db, user_id=user, purge_only=True))
        if hasattr(moderation_chats, "has_purge_access"):
            await timed("more: purge entry (access check)", lambda: moderation_chats.has_purge_access(db, user_id=user))
        plan = Plan(norm=1, start=today - timedelta(days=7), end=today - timedelta(days=1))
        await timed("purge: find violators of one chat", lambda: find_violators(db, chat, plan))
    await get_pool().close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    parser.add_argument("--indexes", action="store_true")
    parser.add_argument("--users", type=int, default=USERS)
    args = parser.parse_args()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    asyncio.run(run(args.dsn, args.indexes, args.users))


if __name__ == "__main__":
    main()
