#!/usr/bin/env python3
"""Rollback proof: a Stars refund signal cannot debit a spouse or mint a result.

The first safe stage is a durable receipt review.  It validates the exact
Telegram charge/payer/Stars amount, changes state once, and deliberately leaves
the player's Zarniki untouched until payer-specific custody lots are available.
"""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.economy_ledger import apply_balance_change
from infrastructure.repositories.star_payments_v1 import (
    get,
    reconcile_authoritative_refund_review,
    record_credit,
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        user_id, charge_id = 950000000001, "refund-review-charge-950001"
        credit = await apply_balance_change(
            db, user_id, {"zarniki": 200},
            reason_code="stars_purchase", idempotency_key="refund-review-credit",
            source_type="payment", reference_type="stars_payment", reference_id=charge_id,
        )
        await record_credit(
            db, charge_id=charge_id, user_id=user_id, stars=20, zarniki=200,
            payload="zarniki:v1:c:20:200", payload_version="v1", operation_id=credit.operation_id,
        )
        try:
            await reconcile_authoritative_refund_review(
                db, charge_id=charge_id, user_id=user_id, amount=-19,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("wrong Stars amount must not alter the receipt")
        before = await get(db, charge_id)
        assert before and before["status"] == "credited"

        reviewed, changed = await reconcile_authoritative_refund_review(
            db, charge_id=charge_id, user_id=user_id, amount=-20,
        )
        assert changed and reviewed["status"] == "review" and reviewed["review_required"]
        replay, changed = await reconcile_authoritative_refund_review(
            db, charge_id=charge_id, user_id=user_id, amount=-20,
        )
        assert not changed and replay["status"] == "review"
        async with db.execute(
            "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (user_id,)
        ) as cursor:
            assert str((await cursor.fetchone())[0]) == "200.0"
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Stars Zarniki refund review: real PostgreSQL rollback proof OK")
