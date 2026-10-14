"""Readiness state shared by the co-hosted bot and the standalone Mini App (audit A04).

`/api/health` is liveness: the process answers. `/api/ready` additionally needs
the owning startup path to have finished its schema work AND the tables every
first request depends on to exist. A bare `predvestnik` namespace is not enough.
Operator migrations (e.g. the marriage registry) are intentionally not checked
here: they are applied by hand and readiness must not apply or demand them.
"""
from __future__ import annotations

REQUIRED_TABLES = (
    "users",
    "user_chat_stats",
    "chat_settings",
    "global_module_toggles",
    "account_deletions",
    "web_notifications",
    "system_flags",
    "economic_operations",
)

_startup_complete = False


def mark_startup_complete() -> None:
    global _startup_complete
    _startup_complete = True


def startup_complete() -> bool:
    return _startup_complete


async def missing_tables(conn) -> list[str]:
    """Names from REQUIRED_TABLES absent in the `predvestnik` schema (asyncpg connection)."""
    rows = await conn.fetch(
        "SELECT name FROM unnest($1::text[]) AS name "
        "WHERE to_regclass('predvestnik.' || name) IS NULL",
        list(REQUIRED_TABLES),
    )
    return [row["name"] for row in rows]
