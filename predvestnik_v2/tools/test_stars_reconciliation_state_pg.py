#!/usr/bin/env python3
"""Real PostgreSQL proof for Stars history recovery coordination."""
from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlparse

import asyncpg

os.environ.setdefault("BOT_TOKEN", "123456:offline-stars-recovery-proof")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:55432/offline")

from bot.handlers import payments
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.star_payments_v1 import (
    acquire_reconciliation_lease,
    ensure_tables,
    finish_reconciliation_run,
    record_reconciliation_observation,
    resolve_reconciliation_alert,
    upsert_reconciliation_alert,
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    first = await asyncpg.connect(dsn)
    second = await asyncpg.connect(dsn)
    try:
        db1, db2 = PGAdapter(first), PGAdapter(second)
        await ensure_tables(db1)
        assert await acquire_reconciliation_lease(db1, "stars-proof-a")
        assert not await acquire_reconciliation_lease(db2, "stars-proof-b")
        assert await finish_reconciliation_run(
            db1, token="stars-proof-a", complete=True, stable_head=True,
            head_id="head-a", scanned=101,
        )
        assert await acquire_reconciliation_lease(db2, "stars-proof-b")
        await upsert_reconciliation_alert(
            db2, key="stars-history-recovery-unhealthy", severity="critical",
            detail="proof: page limit reached",
        )
        assert await finish_reconciliation_run(
            db2, token="stars-proof-b", complete=False, stable_head=True,
            head_id="head-b", scanned=300, detail="page limit reached",
        )
        async with db2.execute(
            "SELECT consecutive_complete_scans,last_complete_at FROM stars_reconciliation_state_v1 WHERE singleton=TRUE"
        ) as cursor:
            state = await cursor.fetchone()
        assert int(state["consecutive_complete_scans"]) == 0 and state["last_complete_at"] is not None
        await resolve_reconciliation_alert(db2, "stars-history-recovery-unhealthy")
        async with db2.execute(
            "SELECT resolved_at FROM stars_reconciliation_alerts_v1 WHERE alert_key=?",
            ("stars-history-recovery-unhealthy",),
        ) as cursor:
            assert (await cursor.fetchone())["resolved_at"] is not None

        class BrokenTelegram:
            async def get_star_transactions(self, **_kwargs):
                raise RuntimeError("Telegram history unavailable")

        try:
            await payments._run_star_history_scan(BrokenTelegram(), db2, max_pages=1)
        except RuntimeError as error:
            assert "Telegram history unavailable" in str(error)
        else:
            raise AssertionError("Telegram failure must escape so the scheduler retries")
        async with db2.execute(
            "SELECT lease_token,consecutive_complete_scans FROM stars_reconciliation_state_v1 WHERE singleton=TRUE"
        ) as cursor:
            failed_state = await cursor.fetchone()
        assert failed_state["lease_token"] is None and int(failed_state["consecutive_complete_scans"]) == 0
        async with db2.execute(
            "SELECT severity,resolved_at FROM stars_reconciliation_alerts_v1 WHERE alert_key=?",
            ("stars-history-recovery-unhealthy",),
        ) as cursor:
            alert = await cursor.fetchone()
        assert alert["severity"] == "critical" and alert["resolved_at"] is None

        await record_reconciliation_observation(
            db2, charge_id="observation-charge-a", event_kind="incoming_payment", amount=20,
            telegram_date=None, source_user_id=930000001, receiver_user_id=None,
            invoice_payload="zarniki:v1:c:20:200", fingerprint="same-history-row",
            disposition="failed", failure_detail="temporary database outage",
        )
        await record_reconciliation_observation(
            db2, charge_id="observation-charge-a", event_kind="incoming_payment", amount=20,
            telegram_date=None, source_user_id=930000001, receiver_user_id=None,
            invoice_payload="zarniki:v1:c:20:200", fingerprint="same-history-row",
            disposition="processed",
        )
        try:
            await record_reconciliation_observation(
                db2, charge_id="observation-charge-a", event_kind="incoming_payment", amount=20,
                telegram_date=None, source_user_id=930000001, receiver_user_id=None,
                invoice_payload="zarniki:v1:c:20:200", fingerprint="changed-history-row",
                disposition="failed", failure_detail="must not overwrite immutable evidence",
            )
        except RuntimeError as error:
            assert "immutable observation conflict" in str(error)
        else:
            raise AssertionError("changed Telegram history row must not overwrite the journal")
    finally:
        await first.close()
        await second.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Stars reconciliation state: real PostgreSQL coordination proof OK")
