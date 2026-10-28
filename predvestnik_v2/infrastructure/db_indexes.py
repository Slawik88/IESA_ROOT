"""Indexes for hot reads on big tables, built in the background after start-up (S04).

CREATE INDEX CONCURRENTLY does not block writes, but it cannot run inside a transaction and may take minutes
on a large table, so it never runs in init_db: the bot starts first, the indexes follow one by one on a direct
connection (not a pool slot). A failure is logged and skipped; a build interrupted by a deploy leaves an
INVALID index, which the next start drops and builds again. Nothing here deletes data or renames anything.
"""
from __future__ import annotations

import asyncpg
from loguru import logger

LOCK_TIMEOUT = "60s"   # how long a build may wait for its lock or for older transactions before it gives up until the next start

# (name, table and columns, extension it needs). Order: the cheapest first.
INDEXES = (
    # tops for a period across all chats: filter by date only, sum per player (index-only scan)
    ("idx_daily_stats_date_user", "daily_user_stats (date, user_id) INCLUDE (message_count)", None),
    # purge: last mute of every member of a chat; the admin journal of one player; the admin journal by period
    ("idx_mod_chat_user_action_at", "moderation_logs (chat_id, user_id, action, created_at)", None),
    ("idx_mod_user", "moderation_logs (user_id)", None),
    ("idx_mod_created_at", "moderation_logs (created_at)", None),
    # tab time: a minute of a visit is added to the last row of (player, session, tab); without it every write scanned the table
    ("idx_sa_user_session", "site_analytics (user_id, session_id, tab, visited_at)", None),
    # admin search by a part of a nick, name or chat tag; only where the extension is already installed
    ("idx_users_username_trgm", "users USING gin (user_tg_username gin_trgm_ops)", "pg_trgm"),
    ("idx_users_name_trgm", "users USING gin (user_tg_name gin_trgm_ops)", "pg_trgm"),
    ("idx_stats_member_tag_trgm", "user_chat_stats USING gin (member_tag gin_trgm_ops)", "pg_trgm"),
)


async def _state(connection: asyncpg.Connection, name: str) -> str:
    valid = await connection.fetchval(
        "SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
        "WHERE c.relname = $1 AND c.relnamespace = current_schema()::regnamespace", name)
    return "missing" if valid is None else ("ready" if valid else "invalid")


async def build_all(connection: asyncpg.Connection) -> dict[str, str]:
    """Build the missing indexes one by one; returns name -> ready / built / skipped / failed."""
    await connection.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    await connection.execute("SET statement_timeout = 0")
    installed = {row[0] for row in await connection.fetch("SELECT extname FROM pg_extension")}
    result: dict[str, str] = {}
    for name, target, extension in INDEXES:
        if extension and extension not in installed:
            result[name] = "skipped"
            continue
        state = await _state(connection, name)
        if state == "ready":
            result[name] = "ready"
            continue
        try:
            if state == "invalid":   # left by an interrupted build: it is never used by queries, only slows writes
                await connection.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            await connection.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}")
            result[name] = "built"
            logger.info("db index {} built", name)
        except (asyncpg.PostgresError, OSError) as error:
            result[name] = "failed"
            logger.warning("db index {} not built, next start retries: {}: {}", name, type(error).__name__, error)
    return result


async def run() -> None:
    """Background start-up step of the bot. Never fails the process: indexes only speed things up."""
    from infrastructure.database import connect_direct
    try:
        connection = await connect_direct(statement_timeout_ms=0)
    except (asyncpg.PostgresError, OSError) as error:
        logger.warning("db indexes postponed to the next start: no connection: {}: {}", type(error).__name__, error)
        return
    try:
        result = await build_all(connection)
        logger.info("db indexes: {}", ", ".join(f"{name}={state}" for name, state in result.items()))
    except (asyncpg.PostgresError, OSError) as error:
        logger.warning("db indexes stopped, next start retries: {}: {}", type(error).__name__, error)
    finally:
        await connection.close()
