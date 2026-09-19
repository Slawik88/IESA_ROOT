"""PostgreSQL state and idempotency receipts for Harbinger Sky v1."""
from __future__ import annotations

import json
from typing import Any

from core.sky_v1 import DEFINITION_DIGEST, POLICY_VERSION, validate_allocated_state


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS harbinger_sky_v1 (
            user_id BIGINT PRIMARY KEY,
            policy_version TEXT NOT NULL,
            definition_digest TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
            allocated_json TEXT NOT NULL DEFAULT '[]',
            active_sigil TEXT NULL,
            eclipse_cycle_key TEXT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS harbinger_sky_actions_v1 (
            user_id BIGINT NOT NULL,
            action_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            definition_digest TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, action_id)
        )
    """)
    await db.execute("ALTER TABLE harbinger_sky_v1 ADD COLUMN IF NOT EXISTS definition_digest TEXT")
    await db.execute("ALTER TABLE harbinger_sky_v1 ADD COLUMN IF NOT EXISTS eclipse_cycle_key TEXT")
    await db.execute("ALTER TABLE harbinger_sky_actions_v1 ADD COLUMN IF NOT EXISTS definition_digest TEXT")
    await db.execute(
        "UPDATE harbinger_sky_v1 SET definition_digest=? WHERE definition_digest IS NULL AND policy_version=?",
        (DEFINITION_DIGEST, POLICY_VERSION),
    )
    await db.execute(
        "UPDATE harbinger_sky_actions_v1 SET definition_digest=? WHERE definition_digest IS NULL",
        (DEFINITION_DIGEST,),
    )
    async with db.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name='harbinger_sky_v1' "
        "AND column_name='eclipse_cycle_no'"
    ) as cursor:
        has_legacy_cycle = await cursor.fetchone()
    if has_legacy_cycle:
        await db.execute(
            "UPDATE harbinger_sky_v1 SET eclipse_cycle_key='scar-map-v1-2026-08-28:' || eclipse_cycle_no::text "
            "WHERE eclipse_cycle_key IS NULL AND eclipse_cycle_no IS NOT NULL"
        )
    await db.execute("ALTER TABLE harbinger_sky_v1 ALTER COLUMN definition_digest SET NOT NULL")
    await db.execute("ALTER TABLE harbinger_sky_actions_v1 ALTER COLUMN definition_digest SET NOT NULL")
    await db.commit()


def decode(row: dict[str, Any] | None) -> tuple[set[str], str | None, int, str | None]:
    if not row:
        return set(), None, 0, None
    if (str(row.get("policy_version") or "") != POLICY_VERSION or
            str(row.get("definition_digest") or "") != DEFINITION_DIGEST):
        raise RuntimeError("Harbinger Sky policy conflict")
    raw = json.loads(row.get("allocated_json") or "[]")
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise RuntimeError("Harbinger Sky state is malformed")
    allocated = set(raw)
    if len(allocated) != len(raw):
        raise RuntimeError("Harbinger Sky state is malformed")
    sigil = row.get("active_sigil")
    validate_allocated_state(allocated, sigil)
    cycle = row.get("eclipse_cycle_key")
    if cycle is not None and (not isinstance(cycle, str) or not cycle.strip()):
        raise RuntimeError("Harbinger Sky eclipse state is malformed")
    return allocated, sigil, int(row.get("revision") or 0), cycle


async def get_state(db, user_id: int) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM harbinger_sky_v1 WHERE user_id=?", (int(user_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def save_state(db, *, user_id: int, expected_revision: int, allocated: set[str],
                     active_sigil: str | None, eclipse_cycle_key: str | None) -> dict[str, Any]:
    validate_allocated_state(allocated, active_sigil)
    payload = json.dumps(sorted(allocated), separators=(",", ":"))
    async with db.execute(
        "INSERT INTO harbinger_sky_v1 "
        "(user_id,policy_version,definition_digest,revision,allocated_json,active_sigil,eclipse_cycle_key) "
        "VALUES (?,?,?,1,?,?,?) "
        "ON CONFLICT (user_id) DO UPDATE SET revision=harbinger_sky_v1.revision+1, "
        "allocated_json=excluded.allocated_json,active_sigil=excluded.active_sigil, "
        "eclipse_cycle_key=excluded.eclipse_cycle_key,updated_at=NOW() "
        "WHERE harbinger_sky_v1.revision=? AND harbinger_sky_v1.policy_version=? "
        "AND harbinger_sky_v1.definition_digest=? RETURNING *",
        (int(user_id), POLICY_VERSION, DEFINITION_DIGEST, payload, active_sigil, eclipse_cycle_key,
         int(expected_revision), POLICY_VERSION, DEFINITION_DIGEST),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("revision_conflict")
    return dict(row)


async def get_action(db, user_id: int, action_id: str) -> dict[str, str] | None:
    async with db.execute(
        "SELECT fingerprint,response_json,definition_digest FROM harbinger_sky_actions_v1 WHERE user_id=? AND action_id=?",
        (int(user_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if row and str(row[2]) != DEFINITION_DIGEST:
        raise RuntimeError("Harbinger Sky action definition conflict")
    return {"fingerprint": str(row[0]), "response_json": str(row[1])} if row else None


async def record_action(db, *, user_id: int, action_id: str, fingerprint: str,
                        response: dict[str, Any]) -> None:
    payload = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    await db.execute(
        "INSERT INTO harbinger_sky_actions_v1(user_id,action_id,fingerprint,response_json,definition_digest) VALUES (?,?,?,?,?)",
        (int(user_id), str(action_id), fingerprint, payload, DEFINITION_DIGEST),
    )
