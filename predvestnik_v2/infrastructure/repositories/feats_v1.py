"""Append-only receipts for terminal, non-economic Chronicle feats."""
from __future__ import annotations

import json
from typing import Any


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chronicle_feat_receipts_v1 (
            user_id BIGINT NOT NULL,
            feat_id TEXT NOT NULL,
            feat_version TEXT NOT NULL,
            definition_digest TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            achieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, feat_id)
        )
    """)
    await db.commit()


async def list_receipts(db, user_id: int) -> dict[str, dict[str, Any]]:
    async with db.execute(
        "SELECT feat_id,feat_version,definition_digest,evidence_json,achieved_at "
        "FROM chronicle_feat_receipts_v1 WHERE user_id=? ORDER BY feat_id",
        (int(user_id),),
    ) as cursor:
        rows = await cursor.fetchall()
    return {
        str(row[0]): {
            "feat_version": str(row[1]),
            "definition_digest": str(row[2]),
            "evidence": json.loads(row[3] or "{}"),
            "achieved_at": row[4],
        }
        for row in rows
    }


async def count_receipts(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM chronicle_feat_receipts_v1 WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0] or 0) if row else 0


async def record_receipt(db, *, user_id: int, feat_id: str, feat_version: str,
                         definition_digest: str, evidence: dict[str, Any]) -> bool:
    payload = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    async with db.execute(
        "INSERT INTO chronicle_feat_receipts_v1 "
        "(user_id,feat_id,feat_version,definition_digest,evidence_json) "
        "VALUES (?,?,?,?,?) ON CONFLICT (user_id,feat_id) DO NOTHING RETURNING feat_id",
        (int(user_id), feat_id, feat_version, definition_digest, payload),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return True
    async with db.execute(
        "SELECT definition_digest FROM chronicle_feat_receipts_v1 "
        "WHERE user_id=? AND feat_id=?",
        (int(user_id), feat_id),
    ) as cursor:
        existing = await cursor.fetchone()
    if not existing or str(existing[0]) != definition_digest:
        raise RuntimeError("Chronicle feat immutable definition conflict")
    return False
