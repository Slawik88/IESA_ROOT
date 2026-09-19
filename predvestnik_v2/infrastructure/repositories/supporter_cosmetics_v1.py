"""Orders, paid entitlements and refund outbox for direct Stars cosmetics."""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from core.supporter_cosmetics_v1 import OFFER_BY_ID, OFFER_DIGEST_BY_ID, POLICY_VERSION


async def ensure_tables(db) -> None:
    await db.execute("""
      CREATE TABLE IF NOT EXISTS stars_cosmetic_schema_v1 (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
        schema_version INTEGER NOT NULL, ready_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    """)
    await db.execute("""
      CREATE TABLE IF NOT EXISTS stars_cosmetic_orders_v1 (
        order_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
        payer_user_id BIGINT NOT NULL, beneficiary_user_id BIGINT NOT NULL,
        offer_id TEXT NOT NULL, cosmetic_id TEXT NOT NULL, stars_amount INTEGER NOT NULL CHECK(stars_amount>0),
        currency TEXT NOT NULL CHECK(currency='XTR'), policy_version TEXT NOT NULL,
        definition_digest TEXT NOT NULL, offer_snapshot_json JSONB NOT NULL,
        invoice_payload TEXT NOT NULL UNIQUE,
        invoice_link TEXT NULL,
        precheckout_query_id TEXT NULL UNIQUE, precheckout_at TIMESTAMPTZ NULL,
        telegram_charge_id TEXT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN
          ('invoice_created','precheckout_ok','paid','entitled','refund_requested','refund_pending','refunded','review','cancelled')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), paid_at TIMESTAMPTZ NULL,
        entitled_at TIMESTAMPTZ NULL, refunded_at TIMESTAMPTZ NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(payer_user_id,request_id)
      )
    """)
    # A partially deployed pre-release table may exist. Never invent a frozen
    # commercial snapshot for old rows; NULL makes validation fail closed.
    await db.execute("ALTER TABLE stars_cosmetic_orders_v1 ADD COLUMN IF NOT EXISTS offer_snapshot_json JSONB")
    await db.execute("ALTER TABLE stars_cosmetic_orders_v1 ADD COLUMN IF NOT EXISTS invoice_link TEXT")
    await db.execute("ALTER TABLE stars_cosmetic_orders_v1 ALTER COLUMN offer_snapshot_json SET NOT NULL")
    await db.execute("DROP INDEX IF EXISTS uq_stars_cosmetic_lifetime_offer")
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stars_cosmetic_live_offer "
        "ON stars_cosmetic_orders_v1(beneficiary_user_id,cosmetic_id) "
        "WHERE status NOT IN ('refunded','cancelled')"
    )
    await db.execute("""
      CREATE TABLE IF NOT EXISTS stars_cosmetic_charges_v1 (
        telegram_charge_id TEXT PRIMARY KEY, order_id TEXT NOT NULL,
        payer_user_id BIGINT NOT NULL, invoice_payload TEXT NOT NULL,
        currency TEXT NOT NULL CHECK(currency='XTR'), stars_amount INTEGER NOT NULL CHECK(stars_amount>0),
        status TEXT NOT NULL CHECK(status IN
          ('received','entitled','refund_pending','refunded','review')),
        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    """)
    await db.execute("""
      CREATE TABLE IF NOT EXISTS stars_cosmetic_entitlements_v1 (
        entitlement_id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES stars_cosmetic_orders_v1(order_id),
        payer_user_id BIGINT NOT NULL, beneficiary_user_id BIGINT NOT NULL, cosmetic_id TEXT NOT NULL,
        grant_type TEXT NOT NULL CHECK(grant_type='stars_purchase'),
        status TEXT NOT NULL CHECK(status IN ('active','frozen','revoked','refunded')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), revoked_at TIMESTAMPTZ NULL,
        UNIQUE(beneficiary_user_id,cosmetic_id)
      )
    """)
    await db.execute("""
      CREATE TABLE IF NOT EXISTS stars_cosmetic_refund_attempts_v1 (
        attempt_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES stars_cosmetic_orders_v1(order_id),
        request_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN
          ('queued','sending','confirmed','failed','ambiguous')),
        error_code TEXT NULL, lease_token TEXT NULL, lease_until TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    """)
    await db.execute("ALTER TABLE stars_cosmetic_refund_attempts_v1 ADD COLUMN IF NOT EXISTS lease_token TEXT")
    await db.execute("ALTER TABLE stars_cosmetic_refund_attempts_v1 ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ")
    await db.execute("""
      CREATE TABLE IF NOT EXISTS supporter_profile_v1 (
        user_id BIGINT PRIMARY KEY, active_entitlement_id TEXT NULL
          REFERENCES stars_cosmetic_entitlements_v1(entitlement_id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL DEFAULT 0 CHECK(revision>=0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    """)
    await db.execute(
        "INSERT INTO stars_cosmetic_schema_v1(singleton,schema_version,ready_at) VALUES (TRUE,2,NOW()) "
        "ON CONFLICT(singleton) DO UPDATE SET schema_version=EXCLUDED.schema_version,ready_at=EXCLUDED.ready_at"
    )


async def schema_ready(db) -> bool:
    try:
        async with db.execute(
            "SELECT schema_version FROM stars_cosmetic_schema_v1 WHERE singleton=TRUE",
        ) as cursor:
            row = await cursor.fetchone()
        return bool(row and int(row[0]) >= 2)
    except Exception:
        return False


def _fingerprint(payer: int, beneficiary: int, offer_id: str) -> str:
    raw = json.dumps({"payer": int(payer), "beneficiary": int(beneficiary),
                      "offer_id": offer_id, "policy": POLICY_VERSION,
                      "digest": OFFER_DIGEST_BY_ID.get(offer_id, "")}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_order(db, *, payer_user_id: int, beneficiary_user_id: int,
                       offer_id: str, request_id: str, payload_builder) -> tuple[dict, bool]:
    offer = OFFER_BY_ID.get(offer_id)
    if not offer:
        raise ValueError("unknown_offer")
    key = str(request_id).strip()
    if not 8 <= len(key) <= 120:
        raise ValueError("invalid_request_id")
    fingerprint = _fingerprint(payer_user_id, beneficiary_user_id, offer_id)
    async with db.execute(
        "SELECT * FROM stars_cosmetic_orders_v1 WHERE payer_user_id=? AND request_id=?",
        (int(payer_user_id), key),
    ) as cursor:
        existing = await cursor.fetchone()
    if existing:
        row = dict(existing)
        if row["request_fingerprint"] != fingerprint:
            raise RuntimeError("order_request_conflict")
        return row, False
    order_id = uuid4().hex
    payload = payload_builder(order_id)
    async with db.execute(
        "INSERT INTO stars_cosmetic_orders_v1(order_id,request_id,request_fingerprint,payer_user_id,"
        "beneficiary_user_id,offer_id,cosmetic_id,stars_amount,currency,policy_version,definition_digest,"
        "offer_snapshot_json,invoice_payload,status) VALUES (?,?,?,?,?,?,?,?, 'XTR',?,?,?::jsonb,?,'invoice_created') RETURNING *",
        (order_id, key, fingerprint, int(payer_user_id), int(beneficiary_user_id), offer_id,
         offer["cosmetic_id"], int(offer["stars"]), POLICY_VERSION, OFFER_DIGEST_BY_ID[offer_id],
         json.dumps(offer, ensure_ascii=False, sort_keys=True, separators=(",", ":")), payload),
    ) as cursor:
        return dict(await cursor.fetchone()), True


async def get_order(db, order_id: str) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM stars_cosmetic_orders_v1 WHERE order_id=?", (order_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_order_by_request(db, payer_user_id: int, request_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM stars_cosmetic_orders_v1 WHERE payer_user_id=? AND request_id=?",
        (int(payer_user_id), str(request_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_order_by_cosmetic(db, beneficiary_user_id: int, cosmetic_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM stars_cosmetic_orders_v1 WHERE beneficiary_user_id=? AND cosmetic_id=? "
        "AND status NOT IN ('refunded','cancelled')",
        (int(beneficiary_user_id), cosmetic_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def record_charge(db, *, charge_id: str, order_id: str, payer_user_id: int,
                        payload: str, currency: str, amount: int) -> tuple[dict, bool]:
    """Persist Telegram's paid fact before projecting any entitlement."""
    async with db.execute(
        "INSERT INTO stars_cosmetic_charges_v1(telegram_charge_id,order_id,payer_user_id,"
        "invoice_payload,currency,stars_amount,status) VALUES (?,?,?,?,?,?,'received') "
        "ON CONFLICT(telegram_charge_id) DO NOTHING RETURNING *",
        (charge_id, order_id, int(payer_user_id), payload, currency, int(amount)),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return dict(inserted), True
    async with db.execute(
        "SELECT * FROM stars_cosmetic_charges_v1 WHERE telegram_charge_id=?", (charge_id,),
    ) as cursor:
        prior = await cursor.fetchone()
    if not prior:
        raise RuntimeError("charge_receipt_missing_after_conflict")
    row = dict(prior)
    expected = (order_id, int(payer_user_id), payload, currency, int(amount))
    actual = (row["order_id"], int(row["payer_user_id"]), row["invoice_payload"],
              row["currency"], int(row["stars_amount"]))
    if actual != expected:
        raise RuntimeError("charge_receipt_conflict")
    return row, False


async def set_charge_status(db, charge_id: str, status: str) -> None:
    if status not in {"entitled", "refund_pending", "refunded", "review"}:
        raise ValueError("invalid_charge_status")
    allowed_from = {
        "entitled": ("received", "entitled"),
        "refund_pending": ("received", "entitled", "review", "refund_pending"),
        "refunded": ("received", "entitled", "review", "refund_pending", "refunded"),
        "review": ("received", "entitled", "refund_pending", "review"),
    }[status]
    placeholders = ",".join("?" for _ in allowed_from)
    async with db.execute(
        f"UPDATE stars_cosmetic_charges_v1 SET status=?,updated_at=NOW() "
        f"WHERE telegram_charge_id=? AND status IN ({placeholders}) RETURNING status",
        (status, charge_id, *allowed_from),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("charge_status_conflict")


async def store_invoice_link(db, order_id: str, link: str) -> dict:
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET invoice_link=COALESCE(invoice_link,?),updated_at=NOW() "
        "WHERE order_id=? AND status='invoice_created' RETURNING *", (link, order_id),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("invoice_link_order_conflict")
    return dict(row)


async def get_charge(db, charge_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM stars_cosmetic_charges_v1 WHERE telegram_charge_id=?", (charge_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def confirm_authoritative_refund(db, *, charge_id: str) -> tuple[dict, bool]:
    """Project an outgoing refund observed in Telegram's transaction history."""
    charge = await get_charge(db, charge_id)
    if not charge:
        raise ValueError("unknown_charge")
    order = await get_order(db, str(charge["order_id"]))
    if not order or order.get("telegram_charge_id") != charge_id:
        raise RuntimeError("refund_charge_order_conflict")
    if order["status"] == "refunded":
        return order, False
    await db.execute(
        "UPDATE stars_cosmetic_entitlements_v1 SET status='refunded',revoked_at=COALESCE(revoked_at,NOW()) "
        "WHERE order_id=? AND status IN ('active','frozen')", (order["order_id"],),
    )
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET status='refunded',refunded_at=COALESCE(refunded_at,NOW()),"
        "updated_at=NOW() WHERE order_id=? AND status IN "
        "('paid','entitled','refund_requested','refund_pending','review') RETURNING *",
        (order["order_id"],),
    ) as cursor:
        changed = await cursor.fetchone()
    if not changed:
        raise RuntimeError("authoritative_refund_state_conflict")
    await set_charge_status(db, charge_id, "refunded")
    await db.execute(
        "UPDATE stars_cosmetic_refund_attempts_v1 SET status='confirmed',lease_token=NULL,lease_until=NULL,"
        "updated_at=NOW() WHERE order_id=? AND status<>'confirmed'", (order["order_id"],),
    )
    return dict(changed), True


def validate_order(row: dict, *, payer_user_id: int, currency: str, amount: int) -> None:
    snapshot = row.get("offer_snapshot_json")
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    digest = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest() if isinstance(snapshot, dict) else ""
    if (not row.get("policy_version") or row.get("definition_digest") != digest or
            int(row.get("payer_user_id", 0)) != int(payer_user_id) or currency != "XTR" or
            int(row.get("stars_amount", 0)) != int(amount) or
            row.get("cosmetic_id") != snapshot.get("cosmetic_id") or
            int(row.get("stars_amount", 0)) != int(snapshot.get("stars", 0))):
        raise RuntimeError("cosmetic_order_contract_conflict")


async def claim_precheckout(db, *, order_id: str, query_id: str) -> dict:
    row = await get_order(db, order_id)
    if not row:
        raise ValueError("unknown_order")
    if row["status"] == "precheckout_ok" and row.get("precheckout_query_id") == query_id:
        return row
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET status='precheckout_ok',precheckout_query_id=?,"
        "precheckout_at=NOW(),updated_at=NOW() WHERE order_id=? AND status='invoice_created' RETURNING *",
        (query_id, order_id),
    ) as cursor:
        claimed = await cursor.fetchone()
    if not claimed:
        raise RuntimeError("order_already_claimed")
    return dict(claimed)


async def grant_paid(db, *, order_id: str, payer_user_id: int, charge_id: str,
                     currency: str, amount: int) -> tuple[dict, bool]:
    row = await get_order(db, order_id)
    if not row:
        raise ValueError("unknown_order")
    validate_order(row, payer_user_id=payer_user_id, currency=currency, amount=amount)
    if row["status"] == "entitled":
        if row.get("telegram_charge_id") != charge_id:
            raise RuntimeError("order_charge_conflict")
        return row, False
    if row["status"] not in {"invoice_created", "precheckout_ok"}:
        raise RuntimeError("order_state_conflict")
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET telegram_charge_id=?,status='paid',paid_at=NOW(),updated_at=NOW() "
        "WHERE order_id=? AND status IN ('invoice_created','precheckout_ok') RETURNING *", (charge_id, order_id),
    ) as cursor:
        paid = await cursor.fetchone()
    if not paid:
        raise RuntimeError("order_state_conflict")
    entitlement_id = uuid4().hex
    try:
        await db.execute(
            "INSERT INTO stars_cosmetic_entitlements_v1(entitlement_id,order_id,payer_user_id,"
            "beneficiary_user_id,cosmetic_id,grant_type,status) VALUES (?,?,?,?,?,'stars_purchase','active')",
            (entitlement_id, order_id, int(payer_user_id), int(row["beneficiary_user_id"]), row["cosmetic_id"]),
        )
    except Exception:
        await db.execute("UPDATE stars_cosmetic_orders_v1 SET status='review',updated_at=NOW() WHERE order_id=?", (order_id,))
        raise
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET status='entitled',entitled_at=NOW(),updated_at=NOW() "
        "WHERE order_id=? AND status='paid' RETURNING *", (order_id,),
    ) as cursor:
        return dict(await cursor.fetchone()), True


async def link_failed_projection(db, *, order_id: str, charge_id: str) -> None:
    """Make a durable paid receipt refundable when entitlement projection failed."""
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET telegram_charge_id=COALESCE(telegram_charge_id,?),"
        "status='review',paid_at=COALESCE(paid_at,NOW()),updated_at=NOW() WHERE order_id=? "
        "AND status IN ('invoice_created','precheckout_ok','paid','review') "
        "AND (telegram_charge_id IS NULL OR telegram_charge_id=?) RETURNING order_id",
        (charge_id, order_id, charge_id),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("failed_projection_link_conflict")


async def active_entitlements(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM stars_cosmetic_entitlements_v1 WHERE beneficiary_user_id=? AND status='active' "
        "ORDER BY created_at", (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def latest_orders(db, user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT order_id,offer_id,stars_amount,status,created_at FROM stars_cosmetic_orders_v1 "
        "WHERE payer_user_id=? ORDER BY created_at DESC LIMIT ?",
        (int(user_id), min(20, max(1, int(limit)))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def prepare_refund(db, *, order_id: str, request_id: str) -> tuple[dict, dict, bool]:
    row = await get_order(db, order_id)
    if not row:
        raise ValueError("unknown_order")
    async with db.execute(
        "SELECT * FROM stars_cosmetic_refund_attempts_v1 WHERE request_id=?", (request_id,),
    ) as cursor:
        prior = await cursor.fetchone()
    if prior:
        attempt = dict(prior)
        if attempt["order_id"] != order_id:
            raise RuntimeError("refund_request_conflict")
        if row["status"] == "review":
            async with db.execute(
                "UPDATE stars_cosmetic_orders_v1 SET status='refund_pending',updated_at=NOW() "
                "WHERE order_id=? AND status='review' RETURNING order_id", (order_id,),
            ) as cursor:
                if not await cursor.fetchone():
                    raise RuntimeError("refund_retry_conflict")
            row = await get_order(db, order_id)
        if row["status"] not in {"refund_pending", "refunded"}:
            raise RuntimeError("refund_retry_state_conflict")
        return row, attempt, False
    if row["status"] == "refunded":
        raise ValueError("already_refunded")
    if row["status"] not in {"entitled", "review"} or not row.get("telegram_charge_id"):
        raise RuntimeError("order_not_refundable")
    attempt_id = uuid4().hex
    await db.execute(
        "UPDATE stars_cosmetic_entitlements_v1 SET status='frozen' WHERE order_id=? AND status='active'",
        (order_id,),
    )
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET status='refund_pending',updated_at=NOW() "
        "WHERE order_id=? AND status IN ('entitled','review') RETURNING order_id", (order_id,),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("refund_state_conflict")
    await db.execute(
        "INSERT INTO stars_cosmetic_refund_attempts_v1(attempt_id,order_id,request_id,status) "
        "VALUES (?,?,?,'queued')", (attempt_id, order_id, request_id),
    )
    await set_charge_status(db, str(row["telegram_charge_id"]), "refund_pending")
    return await get_order(db, order_id), {
        "attempt_id": attempt_id, "order_id": order_id, "request_id": request_id,
        "status": "queued",
    }, True


async def acquire_refund_lease(db, attempt_id: str, lease_token: str) -> bool:
    async with db.execute(
        "UPDATE stars_cosmetic_refund_attempts_v1 SET status='sending',lease_token=?,"
        "lease_until=NOW()+INTERVAL '180 seconds',updated_at=NOW() WHERE attempt_id=? AND "
        "(status IN ('queued','ambiguous','failed') OR (status='sending' AND lease_until<NOW())) "
        "RETURNING attempt_id", (lease_token, attempt_id),
    ) as cursor:
        return bool(await cursor.fetchone())


async def mark_attempt(db, attempt_id: str, status: str, lease_token: str,
                       error_code: str | None = None) -> None:
    if status not in {"confirmed", "failed", "ambiguous"}:
        raise ValueError("invalid_refund_attempt_status")
    async with db.execute(
        "UPDATE stars_cosmetic_refund_attempts_v1 SET status=?,error_code=?,updated_at=NOW() "
        "WHERE attempt_id=? AND status='sending' AND lease_token=? RETURNING attempt_id",
        (status, error_code[:120] if error_code else None, attempt_id, lease_token),
    ) as cursor:
        if not await cursor.fetchone():
            raise RuntimeError("refund_lease_lost")


async def finalize_refund(db, order_id: str, attempt_id: str, lease_token: str) -> None:
    await db.execute(
        "UPDATE stars_cosmetic_entitlements_v1 SET status='refunded',revoked_at=COALESCE(revoked_at,NOW()) "
        "WHERE order_id=? AND status IN ('active','frozen')", (order_id,),
    )
    async with db.execute(
        "UPDATE stars_cosmetic_orders_v1 SET status='refunded',refunded_at=COALESCE(refunded_at,NOW()),"
        "updated_at=NOW() WHERE order_id=? AND status IN ('entitled','refund_pending','review') RETURNING order_id",
        (order_id,),
    ) as cursor:
        changed = await cursor.fetchone()
    current = await get_order(db, order_id)
    if not changed and (not current or current["status"] != "refunded"):
        raise RuntimeError("refund_finalize_conflict")
    if current and current.get("telegram_charge_id"):
        await set_charge_status(db, str(current["telegram_charge_id"]), "refunded")
    await mark_attempt(db, attempt_id, "confirmed", lease_token)


async def mark_refund_review(db, order_id: str, attempt_id: str, error_code: str,
                             lease_token: str, *, ambiguous: bool) -> None:
    await mark_attempt(db, attempt_id, "ambiguous" if ambiguous else "failed", lease_token, error_code)
    if not ambiguous:
        await db.execute(
            "UPDATE stars_cosmetic_orders_v1 SET status='review',updated_at=NOW() "
            "WHERE order_id=? AND status='refund_pending'", (order_id,),
        )
        row = await get_order(db, order_id)
        if row and row.get("telegram_charge_id"):
            await set_charge_status(db, str(row["telegram_charge_id"]), "review")


async def pending_refund_order_ids(db, limit: int = 50) -> list[str]:
    async with db.execute(
        "SELECT DISTINCT o.order_id FROM stars_cosmetic_orders_v1 o "
        "JOIN stars_cosmetic_refund_attempts_v1 a ON a.order_id=o.order_id "
        "WHERE o.status='refund_pending' AND a.status IN ('queued','sending','ambiguous') "
        "ORDER BY o.order_id LIMIT ?", (min(200, max(1, int(limit))),),
    ) as cursor:
        return [str(row[0]) for row in await cursor.fetchall()]
