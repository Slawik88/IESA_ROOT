#!/usr/bin/env python3
"""Real PostgreSQL proof for achievement terminal receipts and awards."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1 as repo
from infrastructure.repositories import economy_ledger
from services import achievements_v1 as achievements


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await repo.ensure_tables(db)
    await economy_ledger.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        user_id = 976401
        before = await achievements.overview(db, user_id=user_id)
        assert all(family["level"] == 0 for family in before["families"])
        assert before["summary"] == {"families": 5, "total_levels": 0, "claimed_mora": 0}
        assert all(len(family["milestones"]) == 6 for family in before["families"])

        first = await achievements.record_terminal(
            db, user_id=user_id, metric="rhythm_completed", source_event_id="run-a",
            source_snapshot={"run_id": "run-a"}, now=datetime(2026, 1, 5, tzinfo=timezone.utc),
        )
        assert first["level"] == 1 and first["active_weeks"] == 1
        assert first["awards"] == [{"level": 1, "amount_mora": 5, "operation_id": first["awards"][0]["operation_id"]}]

        replay = await achievements.record_terminal(
            db, user_id=user_id, metric="rhythm_completed", source_event_id="run-a",
            source_snapshot={"run_id": "run-a"}, now=datetime(2026, 1, 5, tzinfo=timezone.utc),
        )
        assert replay["idempotent_replay"] and replay["awards"] == []
        try:
            await achievements.record_terminal(
                db, user_id=user_id, metric="rhythm_completed", source_event_id="run-a",
                source_snapshot={"run_id": "altered"}, now=datetime(2026, 1, 5, tzinfo=timezone.utc),
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("a reused terminal identity with altered facts must fail")

        same_week = await achievements.record_terminal(
            db, user_id=user_id, metric="rhythm_completed", source_event_id="run-b",
            source_snapshot={"run_id": "run-b"}, now=datetime(2026, 1, 7, tzinfo=timezone.utc),
        )
        assert same_week["completed_events"] == 2 and same_week["active_weeks"] == 1

        try:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE achievement_v1_reward_receipts SET amount_mora=999 WHERE user_id=$1", user_id,
                )
        except asyncpg.PostgresError:
            pass
        else:
            raise AssertionError("achievement reward receipts must be append-only")

        async with db.execute(
            "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='achievement_reward'", (user_id,),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 1
        after = await achievements.overview(db, user_id=user_id)
        rhythm = next(family for family in after["families"] if family["id"] == "rhythm")
        assert rhythm["level"] == 1 and rhythm["claimed_levels"] == [1]
        assert rhythm["milestones"][0]["status"] == "claimed"
        assert rhythm["milestones"][-1]["events_required"] == 2400
        assert after["summary"] == {"families": 5, "total_levels": 1, "claimed_mora": 5}

        # The read model must report the immutable receipt amount, not recalculate
        # history through whatever reward policy happens to be current later.
        historic_user = user_id + 1
        await connection.execute(
            "INSERT INTO achievement_v1_progress(user_id,family,completed_events,active_weeks,level) "
            "VALUES($1,'rhythm',1,1,1)", historic_user,
        )
        await connection.execute(
            "INSERT INTO achievement_v1_reward_receipts(user_id,family,level,amount_mora,policy_version) "
            "VALUES($1,'rhythm',1,7,'historic-policy')", historic_user,
        )
        historic = await achievements.overview(db, user_id=historic_user)
        assert historic["summary"]["claimed_mora"] == 7
    finally:
        await transaction.rollback()
        await connection.close()
    print("OK: achievements v1 terminal receipts, replay, conflict, award and append-only proof")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    arguments = parser.parse_args()
    asyncio.run(run(arguments.dsn))
