"""Fail-closed audit helpers for the global one-marriage rule.

This module intentionally does not reconcile historical rows.  A duplicate
marriage is a social/financial ownership conflict and must be resolved by an
administrator with the affected players, never by a startup migration.
"""
from __future__ import annotations

from typing import Any


async def _scalar(db: Any, sql: str) -> int:
    async with db.execute(sql) as cursor:
        row = await cursor.fetchone()
    return int(row[0] if row else 0)


async def find_duplicate_marriage_members(
    db: Any, *, active_only: bool = False
) -> list[dict[str, int]]:
    """Return every account referenced by more than one relevant marriage row.

    The default deliberately works on the pre-lifecycle legacy schema.  The
    migration calls the active-only variant only after adding ``ended_at``.
    """
    ended_filter = " AND ended_at IS NULL" if active_only else ""
    async with db.execute(
        "SELECT user_id, COUNT(*) AS marriage_count FROM ("
        f"SELECT user1_id AS user_id FROM marriages WHERE user1_id IS NOT NULL{ended_filter} "
        "UNION ALL "
        f"SELECT user2_id AS user_id FROM marriages WHERE user2_id IS NOT NULL{ended_filter}"
        ") members GROUP BY user_id HAVING COUNT(*) > 1 ORDER BY user_id"
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def assert_one_marriage_per_account(db: Any, *, active_only: bool = False) -> None:
    """Raise before a migration/writer if historical data already conflicts."""
    duplicates = await find_duplicate_marriage_members(db, active_only=active_only)
    if duplicates:
        ids = ", ".join(str(row["user_id"]) for row in duplicates[:10])
        suffix = "…" if len(duplicates) > 10 else ""
        raise RuntimeError(
            "Marriage integrity audit failed; duplicate memberships for user IDs: "
            f"{ids}{suffix}. No automatic repair was applied."
        )


async def audit_family_migration_readiness(
    db: Any, *, active_only: bool = False
) -> dict[str, int]:
    """Return aggregate-only blockers before the family-ledger migration.

    This is deliberately read-only and exposes counts rather than player data.
    A non-zero result means that an operator has to investigate before any DDL,
    backfill or wallet writer is allowed to run.
    """
    ended_filter = " AND ended_at IS NULL" if active_only else ""
    duplicate_members = await _scalar(
        db,
        "SELECT COUNT(*) FROM ("
        "SELECT user_id FROM ("
            f"SELECT user1_id AS user_id FROM marriages WHERE user1_id IS NOT NULL{ended_filter} "
            f"UNION ALL SELECT user2_id FROM marriages WHERE user2_id IS NOT NULL{ended_filter}"
        ") members GROUP BY user_id HAVING COUNT(*) > 1"
        ") duplicates",
    )
    return {
        "duplicate_members": duplicate_members,
        "self_pairs": await _scalar(
            db, f"SELECT COUNT(*) FROM marriages WHERE user1_id = user2_id{ended_filter}"
        ),
        "negative_family_balances": await _scalar(
            db,
            "SELECT COUNT(*) FROM marriages WHERE family_balance < 0 "
            "OR COALESCE(family_balance_diamonds, 0) < 0 "
            "OR COALESCE(family_balance_dark_mora, 0) < 0 "
            "OR COALESCE(family_balance_zarniki, 0) < 0",
        ),
        "non_finite_family_balances": await _scalar(
            db,
            "SELECT COUNT(*) FROM marriages WHERE family_balance::text IN ('NaN', 'Infinity', '-Infinity') "
            "OR COALESCE(family_balance_diamonds, 0)::text IN ('NaN', 'Infinity', '-Infinity') "
            "OR COALESCE(family_balance_dark_mora, 0)::text IN ('NaN', 'Infinity', '-Infinity') "
            "OR COALESCE(family_balance_zarniki, 0)::text IN ('NaN', 'Infinity', '-Infinity')",
        ),
        "orphan_family_pets": await _scalar(
            db,
            "SELECT COUNT(*) FROM pets p LEFT JOIN marriages m ON m.id = p.marriage_id "
            "WHERE p.marriage_id IS NOT NULL AND m.id IS NULL",
        ),
    }


def migration_is_safe(audit: dict[str, int]) -> bool:
    """A future writer/migration must not proceed while any blocker is non-zero."""
    return all(int(value) == 0 for value in audit.values())


async def install_membership_registry(db: Any) -> None:
    """Install and exactly backfill the one-marriage-per-account registry.

    Call this only inside an operator-controlled transaction after the read-only
    audit.  It never chooses a winner between conflicting historical marriages.
    The registry is intentionally installed before writers are switched over.
    """
    # A closed marriage is immutable history.  Its two members must be free to
    # create a later marriage, while ledger rows can still safely reference the
    # original marriage ID.  Add the column before the audit because existing
    # installations predate this lifecycle state.
    await db.execute(
        "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ NULL"
    )
    audit = await audit_family_migration_readiness(db, active_only=True)
    if not migration_is_safe(audit):
        raise RuntimeError(f"family migration blocked: {audit}")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS marriage_members (
            user_id BIGINT PRIMARY KEY,
            marriage_id INTEGER NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (marriage_id, user_id)
        )
    """)
    await db.execute(
        "INSERT INTO marriage_members (user_id, marriage_id) "
        "SELECT user1_id, id FROM marriages WHERE user1_id IS NOT NULL AND ended_at IS NULL "
        "UNION ALL SELECT user2_id, id FROM marriages WHERE user2_id IS NOT NULL AND ended_at IS NULL "
        "ON CONFLICT (user_id) DO NOTHING"
    )
    async with db.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT id AS marriage_id, user1_id AS user_id FROM marriages WHERE user1_id IS NOT NULL AND ended_at IS NULL "
        "UNION ALL SELECT id, user2_id FROM marriages WHERE user2_id IS NOT NULL AND ended_at IS NULL"
        ") expected LEFT JOIN marriage_members actual "
        "ON actual.user_id = expected.user_id AND actual.marriage_id = expected.marriage_id "
        "WHERE actual.user_id IS NULL"
    ) as cursor:
        missing = int((await cursor.fetchone())[0])
    if missing:
        raise RuntimeError(
            "family migration backfill did not exactly match marriages; transaction must roll back"
        )
    async with db.execute(
        "SELECT COUNT(*) FROM marriage_members actual LEFT JOIN ("
        "SELECT id AS marriage_id, user1_id AS user_id FROM marriages WHERE user1_id IS NOT NULL AND ended_at IS NULL "
        "UNION ALL SELECT id, user2_id FROM marriages WHERE user2_id IS NOT NULL AND ended_at IS NULL"
        ") expected ON expected.user_id = actual.user_id AND expected.marriage_id = actual.marriage_id "
        "WHERE expected.user_id IS NULL"
    ) as cursor:
        extra = int((await cursor.fetchone())[0])
    if extra:
        raise RuntimeError(
            "family migration found a stale membership mapping; transaction must roll back"
        )
