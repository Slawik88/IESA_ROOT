"""Append-only storage for versioned, meaningful gameplay events."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.gameplay_events import (
    GameplayEventConflict,
    GameplayEventError,
    canonical_event_payload,
)


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS gameplay_events (
            id                 BIGSERIAL PRIMARY KEY,
            user_id            BIGINT NOT NULL,
            event_name         TEXT NOT NULL,
            event_version      INTEGER NOT NULL,
            game_version       TEXT NOT NULL,
            balance_version    TEXT NOT NULL,
            run_id             BIGINT NULL,
            source             TEXT NOT NULL DEFAULT 'mini_app',
            payload_json       TEXT NOT NULL DEFAULT '{}',
            idempotency_key    TEXT NULL,
            event_fingerprint  TEXT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, idempotency_key)
        )
    """)
    await db.execute(
        "ALTER TABLE gameplay_events ADD COLUMN IF NOT EXISTS "
        "event_fingerprint TEXT NULL"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_gameplay_events_name_time "
        "ON gameplay_events(event_name, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_gameplay_events_user_time "
        "ON gameplay_events(user_id, created_at DESC)"
    )
    await db.commit()


def _fingerprint(
    *,
    event_name: str,
    event_version: int,
    game_version: str,
    balance_version: str,
    run_id: int | None,
    source: str,
    payload_json: str,
) -> str:
    semantic = json.dumps(
        {
            "event_name": event_name,
            "event_version": event_version,
            "game_version": game_version,
            "balance_version": balance_version,
            "run_id": run_id,
            "source": source,
            "payload": json.loads(payload_json),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(semantic.encode("utf-8")).hexdigest()


async def record_event(
    db,
    *,
    user_id: int,
    event_name: str,
    game_version: str,
    balance_version: str,
    run_id: int | None = None,
    source: str = "mini_app",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> bool:
    if int(user_id) <= 0:
        raise GameplayEventError("user_id must be positive")
    normalized_run_id = None if run_id is None else int(run_id)
    if normalized_run_id is not None and normalized_run_id <= 0:
        raise GameplayEventError("run_id must be positive when provided")
    source = str(source or "").strip()
    game_version = str(game_version or "").strip()
    balance_version = str(balance_version or "").strip()
    idempotency_key = str(idempotency_key).strip() if idempotency_key is not None else None
    if not source or len(source) > 32:
        raise GameplayEventError("source must be 1..32 characters")
    if not game_version or len(game_version) > 64:
        raise GameplayEventError("game_version must be 1..64 characters")
    if not balance_version or len(balance_version) > 64:
        raise GameplayEventError("balance_version must be 1..64 characters")
    if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 160):
        raise GameplayEventError("idempotency_key must be 1..160 characters")

    event_version, payload_json = canonical_event_payload(
        event_name,
        {} if payload is None else payload,
    )
    fingerprint = _fingerprint(
        event_name=event_name,
        event_version=event_version,
        game_version=game_version,
        balance_version=balance_version,
        run_id=normalized_run_id,
        source=source,
        payload_json=payload_json,
    )
    async with db.execute(
        "INSERT INTO gameplay_events "
        "(user_id, event_name, event_version, game_version, balance_version, run_id, "
        "source, payload_json, idempotency_key, event_fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, idempotency_key) DO NOTHING RETURNING id",
        (
            int(user_id), event_name, event_version, game_version, balance_version,
            normalized_run_id, source, payload_json, idempotency_key, fingerprint,
        ),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return True
    if idempotency_key is None:
        raise RuntimeError("gameplay event insert returned no row without an idempotency key")

    async with db.execute(
        "SELECT event_name, event_version, game_version, balance_version, run_id, "
        "source, payload_json, event_fingerprint FROM gameplay_events "
        "WHERE user_id = ? AND idempotency_key = ?",
        (int(user_id), idempotency_key),
    ) as cursor:
        existing = await cursor.fetchone()
    if not existing:
        raise RuntimeError("gameplay event idempotency row disappeared")
    existing_fingerprint = existing[7] or _fingerprint(
        event_name=str(existing[0]),
        event_version=int(existing[1]),
        game_version=str(existing[2]),
        balance_version=str(existing[3]),
        run_id=int(existing[4]) if existing[4] is not None else None,
        source=str(existing[5]),
        payload_json=str(existing[6]),
    )
    if existing_fingerprint == fingerprint:
        return False
    raise GameplayEventConflict(
        f"Idempotency key {idempotency_key!r} already belongs to a different gameplay event"
    )
