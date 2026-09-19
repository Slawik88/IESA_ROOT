"""Durable normalized state for the immutable Weekly Case catalog."""
from __future__ import annotations

from datetime import date
from typing import Any

CATALOG_VERSION = "weekly-catalog-v2-2026-08-27"

def _date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))

def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None

async def ensure_tables(db) -> None:
    # v1 stays intact as the immutable migration source.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_weekly_cases_v2 (
            user_id BIGINT NOT NULL, catalog_version TEXT NOT NULL,
            case_id TEXT NOT NULL, case_order INTEGER NOT NULL,
            policy_version TEXT NOT NULL, path_id TEXT NULL,
            definition_digest TEXT NULL,
            progress_days INTEGER NOT NULL DEFAULT 0,
            target_days INTEGER NOT NULL,
            finale_id TEXT NULL, assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            chosen_at TIMESTAMPTZ NULL, completed_at TIMESTAMPTZ NULL,
            PRIMARY KEY (user_id,catalog_version,case_id),
            UNIQUE (user_id,catalog_version,case_order),
            CHECK (target_days > 0 AND progress_days BETWEEN 0 AND target_days)
        )
    """)
    await db.execute(
        "ALTER TABLE reconstruction_weekly_cases_v2 "
        "ADD COLUMN IF NOT EXISTS definition_digest TEXT NULL"
    )
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_weekly_case_v2_one_active
        ON reconstruction_weekly_cases_v2(user_id,catalog_version)
        WHERE completed_at IS NULL
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_weekly_case_days_v2 (
            user_id BIGINT NOT NULL, catalog_version TEXT NOT NULL,
            day_key DATE NOT NULL, case_id TEXT NOT NULL,
            contract_id TEXT NOT NULL, category TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id,catalog_version,day_key),
            FOREIGN KEY (user_id,catalog_version,case_id)
              REFERENCES reconstruction_weekly_cases_v2(user_id,catalog_version,case_id)
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_weekly_case_day_global_v2
        ON reconstruction_weekly_case_days_v2(user_id,day_key)
    """)
    await db.commit()

async def has_catalog(db, user_id: int) -> bool:
    async with db.execute("SELECT 1 FROM reconstruction_weekly_cases_v2 WHERE user_id=? AND catalog_version=? LIMIT 1", (int(user_id),CATALOG_VERSION)) as c:
        return bool(await c.fetchone())

async def legacy_case(db, user_id: int, policy_version: str) -> dict | None:
    async with db.execute("SELECT * FROM reconstruction_weekly_cases WHERE user_id=? AND policy_version=?", (int(user_id),policy_version)) as c:
        return _row(await c.fetchone())

async def legacy_days(db, user_id: int, policy_version: str) -> list[dict]:
    async with db.execute("SELECT day_key,contract_id FROM reconstruction_weekly_case_days WHERE user_id=? AND policy_version=? ORDER BY day_key LIMIT 3", (int(user_id),policy_version)) as c:
        return [dict(row) for row in await c.fetchall()]

async def create_case(db, *, user_id: int, case_id: str, case_order: int,
                      policy_version: str, target_days: int, definition_digest: str,
                      path_id: str | None = None,
                      progress_days: int = 0, finale_id: str | None = None,
                      assigned_at=None, chosen_at=None, completed_at=None) -> dict:
    async with db.execute(
        "INSERT INTO reconstruction_weekly_cases_v2 "
        "(user_id,catalog_version,case_id,case_order,policy_version,definition_digest,target_days,path_id,progress_days,finale_id,assigned_at,chosen_at,completed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,COALESCE(?,NOW()),?,?) ON CONFLICT (user_id,catalog_version,case_id) DO NOTHING RETURNING *",
        (int(user_id),CATALOG_VERSION,case_id,int(case_order),policy_version,definition_digest,int(target_days),path_id,int(progress_days),finale_id,assigned_at,chosen_at,completed_at),
    ) as c:
        inserted = await c.fetchone()
    if inserted: return dict(inserted)
    async with db.execute("SELECT * FROM reconstruction_weekly_cases_v2 WHERE user_id=? AND catalog_version=? AND case_id=?", (int(user_id),CATALOG_VERSION,case_id)) as c:
        row=await c.fetchone()
    if not row: raise RuntimeError("Failed to create Weekly Case")
    return dict(row)

async def bind_definition(db, *, user_id: int, case_id: str, digest: str) -> dict:
    """Bind pre-digest rows once; reject any later definition drift."""
    async with db.execute(
        "UPDATE reconstruction_weekly_cases_v2 SET definition_digest=? "
        "WHERE user_id=? AND catalog_version=? AND case_id=? "
        "AND definition_digest IS NULL RETURNING *",
        (digest, int(user_id), CATALOG_VERSION, case_id),
    ) as c:
        updated = await c.fetchone()
    if updated:
        return dict(updated)
    async with db.execute(
        "SELECT * FROM reconstruction_weekly_cases_v2 "
        "WHERE user_id=? AND catalog_version=? AND case_id=?",
        (int(user_id), CATALOG_VERSION, case_id),
    ) as c:
        row = await c.fetchone()
    if not row or str(row["definition_digest"] or "") != digest:
        raise RuntimeError("Weekly Case immutable definition conflict")
    return dict(row)

async def import_day(db, *, user_id: int, day_key, case_id: str, contract_id: str, category: str) -> None:
    await db.execute("INSERT INTO reconstruction_weekly_case_days_v2 (user_id,catalog_version,day_key,case_id,contract_id,category) VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING", (int(user_id),CATALOG_VERSION,_date(day_key),case_id,contract_id,category))

async def active_case(db, user_id: int) -> dict | None:
    async with db.execute("SELECT * FROM reconstruction_weekly_cases_v2 WHERE user_id=? AND catalog_version=? AND completed_at IS NULL ORDER BY case_order LIMIT 1", (int(user_id),CATALOG_VERSION)) as c:
        return _row(await c.fetchone())

async def case_by_id(db, user_id: int, case_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM reconstruction_weekly_cases_v2 "
        "WHERE user_id=? AND catalog_version=? AND case_id=?",
        (int(user_id), CATALOG_VERSION, case_id),
    ) as c:
        return _row(await c.fetchone())

async def all_cases(db, user_id: int) -> list[dict]:
    async with db.execute("SELECT * FROM reconstruction_weekly_cases_v2 WHERE user_id=? AND catalog_version=? ORDER BY case_order", (int(user_id),CATALOG_VERSION)) as c:
        return [dict(row) for row in await c.fetchall()]

async def choose_path(db, user_id: int, case_id: str, path_id: str) -> dict | None:
    async with db.execute("UPDATE reconstruction_weekly_cases_v2 SET path_id=?,chosen_at=COALESCE(chosen_at,NOW()) WHERE user_id=? AND catalog_version=? AND case_id=? AND completed_at IS NULL AND (path_id IS NULL OR path_id=?) RETURNING *", (path_id,int(user_id),CATALOG_VERSION,case_id,path_id)) as c:
        return _row(await c.fetchone())

async def add_completed_day(db, *, user_id: int, case_id: str, day_key, contract_id: str, category: str) -> dict | None:
    async with db.execute(
        "INSERT INTO reconstruction_weekly_case_days_v2 "
        "(user_id,catalog_version,day_key,case_id,contract_id,category) "
        "SELECT ?,?,?,?,?,? WHERE EXISTS ("
        "SELECT 1 FROM reconstruction_weekly_cases_v2 "
        "WHERE user_id=? AND catalog_version=? AND case_id=? "
        "AND completed_at IS NULL AND progress_days<target_days) "
        "ON CONFLICT DO NOTHING RETURNING day_key",
        (int(user_id),CATALOG_VERSION,_date(day_key),case_id,contract_id,category,
         int(user_id),CATALOG_VERSION,case_id),
    ) as c:
        inserted=await c.fetchone()
    if not inserted: return None
    async with db.execute("UPDATE reconstruction_weekly_cases_v2 SET progress_days=LEAST(target_days,progress_days+1) WHERE user_id=? AND catalog_version=? AND case_id=? AND completed_at IS NULL RETURNING *", (int(user_id),CATALOG_VERSION,case_id)) as c:
        return _row(await c.fetchone())

async def complete_case(db, *, user_id: int, case_id: str, finale_id: str) -> dict | None:
    async with db.execute("UPDATE reconstruction_weekly_cases_v2 SET finale_id=?,completed_at=NOW() WHERE user_id=? AND catalog_version=? AND case_id=? AND completed_at IS NULL AND path_id IS NOT NULL AND progress_days>=target_days RETURNING *", (finale_id,int(user_id),CATALOG_VERSION,case_id)) as c:
        return _row(await c.fetchone())

async def categories_for_case(db, user_id: int, case_id: str) -> set[str]:
    async with db.execute("SELECT category FROM reconstruction_weekly_case_days_v2 WHERE user_id=? AND catalog_version=? AND case_id=? ORDER BY day_key", (int(user_id),CATALOG_VERSION,case_id)) as c:
        return {str(row[0]) for row in await c.fetchall()}
