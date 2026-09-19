"""Immutable Stars receipts and recoverable refund state."""
from __future__ import annotations

from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stars_payment_receipts_v1 (
            telegram_charge_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            currency TEXT NOT NULL CHECK (currency='XTR'),
            stars_amount INTEGER NOT NULL CHECK (stars_amount>0),
            zarniki_amount INTEGER NOT NULL CHECK (zarniki_amount>0),
            invoice_payload TEXT NOT NULL,
            payload_version TEXT NOT NULL,
            credit_operation_id TEXT NOT NULL UNIQUE
              REFERENCES economic_operations(id) ON DELETE RESTRICT,
            status TEXT NOT NULL CHECK (status IN
              ('credited','refund_requested','refunded','review')),
            refund_request_id TEXT NULL UNIQUE,
            refund_operation_id TEXT NULL UNIQUE
              REFERENCES economic_operations(id) ON DELETE RESTRICT,
            review_required BOOLEAN NOT NULL DEFAULT FALSE,
            credited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            refund_requested_at TIMESTAMPTZ NULL,
            refunded_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_stars_receipts_user_time "
        "ON stars_payment_receipts_v1(user_id,credited_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stars_transaction_observations_v1 (
            telegram_charge_id TEXT NOT NULL,
            event_kind TEXT NOT NULL CHECK (event_kind IN ('incoming_payment','outgoing_refund')),
            amount INTEGER NOT NULL,
            telegram_date TIMESTAMPTZ NULL,
            source_user_id BIGINT NULL,
            receiver_user_id BIGINT NULL,
            invoice_payload TEXT NULL,
            payload_fingerprint TEXT NOT NULL,
            disposition TEXT NOT NULL CHECK (disposition IN
              ('seen','processed','replayed','review','invalid','failed','orphan_refund')),
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ NULL,
            failure_detail TEXT NULL,
            PRIMARY KEY (telegram_charge_id, event_kind)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stars_reconciliation_state_v1 (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            lease_token TEXT NULL,
            lease_expires_at TIMESTAMPTZ NULL,
            active_run_started_at TIMESTAMPTZ NULL,
            last_complete_at TIMESTAMPTZ NULL,
            last_head_id TEXT NULL,
            last_scanned_count INTEGER NOT NULL DEFAULT 0,
            consecutive_complete_scans INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stars_reconciliation_alerts_v1 (
            id BIGSERIAL PRIMARY KEY,
            alert_key TEXT NOT NULL UNIQUE,
            severity TEXT NOT NULL CHECK (severity IN ('warning','critical')),
            detail TEXT NOT NULL,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ NULL
        )
    """)


async def acquire_reconciliation_lease(db, token: str) -> bool:
    """Claim the one global history reader, or return false without waiting.

    A second bot process must never concurrently declare a bounded historical
    scan healthy. Expiry is intentional: a killed process cannot leave
    recovery permanently disabled.
    """
    if not isinstance(token, str) or not token:
        raise ValueError("reconciliation lease token is required")
    async with db.connection.transaction():
        await db.execute(
            "INSERT INTO stars_reconciliation_state_v1(singleton) VALUES (TRUE) "
            "ON CONFLICT (singleton) DO NOTHING"
        )
        async with db.execute(
            "UPDATE stars_reconciliation_state_v1 SET lease_token=?,"
            "lease_expires_at=NOW() + INTERVAL '15 minutes',"
            "active_run_started_at=NOW(),updated_at=NOW() WHERE singleton=TRUE "
            "AND (lease_expires_at IS NULL OR lease_expires_at<NOW() OR lease_token=?) "
            "RETURNING singleton",
            (token, token),
        ) as cursor:
            return bool(await cursor.fetchone())


async def finish_reconciliation_run(
    db, *, token: str, complete: bool, stable_head: bool, head_id: str | None,
    scanned: int, detail: str | None = None,
) -> bool:
    """Persist an outcome only for the process that owns the active lease."""
    if not isinstance(token, str) or not token:
        raise ValueError("reconciliation lease token is required")
    healthy = bool(complete and stable_head and not detail)
    async with db.execute(
        "UPDATE stars_reconciliation_state_v1 SET lease_token=NULL,lease_expires_at=NULL,"
        "last_complete_at=CASE WHEN ? THEN NOW() ELSE last_complete_at END,"
        "last_head_id=?,last_scanned_count=?,"
        "consecutive_complete_scans=CASE WHEN ? THEN consecutive_complete_scans+1 ELSE 0 END,"
        "updated_at=NOW() WHERE singleton=TRUE AND lease_token=? RETURNING singleton",
        (healthy, head_id, max(0, int(scanned)), healthy, token),
    ) as cursor:
        return bool(await cursor.fetchone())


async def upsert_reconciliation_alert(db, *, key: str, severity: str, detail: str) -> None:
    if severity not in {"warning", "critical"}:
        raise ValueError("invalid Stars reconciliation alert severity")
    await db.execute(
        "INSERT INTO stars_reconciliation_alerts_v1(alert_key,severity,detail) VALUES (?,?,?) "
        "ON CONFLICT (alert_key) DO UPDATE SET severity=EXCLUDED.severity,detail=EXCLUDED.detail,"
        "last_seen_at=NOW(),resolved_at=NULL",
        (str(key), severity, str(detail)[:2000]),
    )


async def resolve_reconciliation_alert(db, key: str) -> None:
    await db.execute(
        "UPDATE stars_reconciliation_alerts_v1 SET resolved_at=COALESCE(resolved_at,NOW()),"
        "last_seen_at=NOW() WHERE alert_key=?",
        (str(key),),
    )


async def record_reconciliation_observation(
    db, *, charge_id: str, event_kind: str, amount: int, telegram_date, source_user_id: int | None,
    receiver_user_id: int | None, invoice_payload: str | None, fingerprint: str,
    disposition: str, failure_detail: str | None = None,
) -> None:
    """Journal one immutable Telegram history row and reject changed replays."""
    if event_kind not in {"incoming_payment", "outgoing_refund"}:
        raise ValueError("invalid Stars transaction event kind")
    if disposition not in {"seen", "processed", "replayed", "review", "invalid", "failed", "orphan_refund"}:
        raise ValueError("invalid Stars transaction disposition")
    async with db.connection.transaction():
        async with db.execute(
            "SELECT payload_fingerprint FROM stars_transaction_observations_v1 "
            "WHERE telegram_charge_id=? AND event_kind=? FOR UPDATE",
            (str(charge_id), event_kind),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing and str(existing["payload_fingerprint"]) != str(fingerprint):
            raise RuntimeError("Stars history immutable observation conflict")
        await db.execute(
            "INSERT INTO stars_transaction_observations_v1 "
            "(telegram_charge_id,event_kind,amount,telegram_date,source_user_id,receiver_user_id,"
            "invoice_payload,payload_fingerprint,disposition,processed_at,failure_detail) "
            "VALUES (?,?,?,?,?,?,?,?,?,CASE WHEN ? IN ('processed','replayed','review') THEN NOW() ELSE NULL END,?) "
            "ON CONFLICT (telegram_charge_id,event_kind) DO UPDATE SET "
            "last_seen_at=NOW(),disposition=EXCLUDED.disposition,"
            "processed_at=COALESCE(stars_transaction_observations_v1.processed_at,EXCLUDED.processed_at),"
            "failure_detail=EXCLUDED.failure_detail",
            (str(charge_id), event_kind, int(amount), telegram_date, source_user_id, receiver_user_id,
             invoice_payload, str(fingerprint), disposition, disposition, failure_detail),
        )


async def record_credit(db, *, charge_id: str, user_id: int, stars: int,
                        zarniki: int, payload: str, payload_version: str,
                        operation_id: str) -> None:
    async with db.execute(
        "INSERT INTO stars_payment_receipts_v1 "
        "(telegram_charge_id,user_id,currency,stars_amount,zarniki_amount,invoice_payload,"
        "payload_version,credit_operation_id,status) VALUES (?,?, 'XTR',?,?,?,?,?,'credited') "
        "ON CONFLICT (telegram_charge_id) DO NOTHING RETURNING telegram_charge_id",
        (charge_id, int(user_id), int(stars), int(zarniki), payload,
         payload_version, operation_id),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return
    row = await get(db, charge_id)
    expected = (int(user_id), int(stars), int(zarniki), payload, payload_version, operation_id)
    actual = (int(row["user_id"]), int(row["stars_amount"]), int(row["zarniki_amount"]),
              str(row["invoice_payload"]), str(row["payload_version"]),
              str(row["credit_operation_id"])) if row else None
    if actual != expected:
        raise RuntimeError("Stars charge immutable receipt conflict")


async def get(db, charge_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM stars_payment_receipts_v1 WHERE telegram_charge_id=?",
        (str(charge_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def latest_for_user(db, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT telegram_charge_id,stars_amount,zarniki_amount,status,credited_at "
        "FROM stars_payment_receipts_v1 WHERE user_id=? ORDER BY credited_at DESC LIMIT ?",
        (int(user_id), min(20, max(1, int(limit)))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def has_open_premium_hold(db, user_id: int) -> bool:
    """Fail closed while a Stars receipt is in a manual-review lifecycle state."""
    async with db.execute(
        "SELECT 1 FROM stars_payment_receipts_v1 WHERE user_id=? "
        "AND status IN ('refund_requested','review') LIMIT 1",
        (int(user_id),),
    ) as cursor:
        return bool(await cursor.fetchone())


async def mark_refund_requested(db, charge_id: str, request_id: str) -> bool:
    async with db.execute(
        "UPDATE stars_payment_receipts_v1 SET status='refund_requested',refund_request_id=?,"
        "refund_requested_at=COALESCE(refund_requested_at,NOW()),updated_at=NOW() "
        "WHERE telegram_charge_id=? AND status IN ('credited','review') RETURNING telegram_charge_id",
        (request_id, charge_id),
    ) as cursor:
        return bool(await cursor.fetchone())


async def mark_review(db, charge_id: str) -> None:
    await db.execute(
        "UPDATE stars_payment_receipts_v1 SET status='review',review_required=TRUE,updated_at=NOW() "
        "WHERE telegram_charge_id=? AND status IN ('credited','refund_requested')", (charge_id,)
    )


async def reconcile_authoritative_refund_review(
    db, *, charge_id: str, user_id: int, amount: int,
) -> tuple[dict[str, Any], bool] | None:
    """Quarantine a matching outgoing Stars refund without touching Zarniki.

    Telegram history proves that Stars left the project, but it cannot prove
    which exact paid units remain in a player's personal/family custody.  Until
    the payer-specific lot service has settled that question, reporting this as
    ``refunded`` would be dishonest and an automatic debit could charge a
    spouse.  The durable ``review`` state freezes the future premium-custody
    path and gives support one immutable receipt to investigate.
    """
    async with db.connection.transaction():
        receipt = await get(db, charge_id)
        if not receipt:
            return None
        if int(receipt["user_id"]) != int(user_id) or int(amount) != -int(receipt["stars_amount"]):
            raise RuntimeError("authoritative_zarniki_refund_contract_conflict")
        if receipt["status"] == "refunded":
            return receipt, False
        if receipt["status"] not in {"credited", "refund_requested", "review"}:
            raise RuntimeError("authoritative_zarniki_refund_state_conflict")
        changed = receipt["status"] != "review" or not bool(receipt.get("review_required"))
        await mark_review(db, charge_id)
        current = await get(db, charge_id)
        if not current or current["status"] != "review" or not current.get("review_required"):
            raise RuntimeError("authoritative_zarniki_refund_review_conflict")
        return current, changed


async def mark_refunded(db, charge_id: str, operation_id: str, *, review_required: bool) -> None:
    async with db.execute(
        "UPDATE stars_payment_receipts_v1 SET status='refunded',refund_operation_id=?,"
        "review_required=?,refunded_at=COALESCE(refunded_at,NOW()),updated_at=NOW() "
        "WHERE telegram_charge_id=? AND status='refund_requested' RETURNING telegram_charge_id",
        (operation_id, bool(review_required), charge_id),
    ) as cursor:
        if not await cursor.fetchone():
            row = await get(db, charge_id)
            if not row or row.get("status") != "refunded" or row.get("refund_operation_id") != operation_id:
                raise RuntimeError("Stars refund state conflict")
