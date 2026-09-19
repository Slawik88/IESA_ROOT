"""Real PostgreSQL proof for the internal, append-only Echo Shard foundation."""
from __future__ import annotations
import argparse, asyncio, pathlib, sys
from urllib.parse import urlparse
import asyncpg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.echo_shards_v1 import EchoShardPolicyError, MaxDuplicateCompensation
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import echo_shards_v1 as repo
from services.echo_shards_v1 import EchoShardConflict, compensate_max_duplicate


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn); db = PGAdapter(conn)
    transaction = conn.transaction(); await transaction.start()
    try:
        async def must_reject(sql: str, args: tuple, message: str) -> None:
            try:
                async with db.connection.transaction():
                    await db.execute(sql, args)
            except Exception:
                return
            raise AssertionError(message)

        await repo.ensure_tables(db)
        event = MaxDuplicateCompensation(
            source_kind="pet_v1_max_duplicate", source_event_id="pet-terminal-run-1", source_line_id=0,
            collectible_kind="pet", collectible_id="pet:42", observed_level=16, observed_cap=16,
            amount=1, source_snapshot={"pet_policy_version": "pets-v1-2026-09-05", "terminal": True},
        )
        first = await compensate_max_duplicate(db, user_id=976301, event=event)
        assert first.applied and (first.amount, first.balance_before, first.balance_after) == (1, 0, 1)
        replay = await compensate_max_duplicate(db, user_id=976301, event=event)
        assert not replay.applied and replay.compensation_id == first.compensation_id and replay.balance_after == 1
        altered = MaxDuplicateCompensation(
            source_kind=event.source_kind, source_event_id=event.source_event_id, source_line_id=0,
            collectible_kind=event.collectible_kind, collectible_id=event.collectible_id,
            observed_level=16, observed_cap=16, amount=1, source_snapshot={"pet_policy_version": "tampered"},
        )
        try:
            await compensate_max_duplicate(db, user_id=976301, event=altered)
        except EchoShardConflict:
            pass
        else:
            raise AssertionError("altered source facts must conflict")
        try:
            await compensate_max_duplicate(db, user_id=976301, event=MaxDuplicateCompensation(
                source_kind="pet_v1_max_duplicate", source_event_id="not-capped", source_line_id=1,
                collectible_kind="pet", collectible_id="pet:42", observed_level=15, observed_cap=16,
                amount=1, source_snapshot={},
            ))
        except EchoShardPolicyError:
            pass
        else:
            raise AssertionError("non-max collectible must not be compensated")
        async with db.execute("SELECT balance FROM echo_shard_accounts_v1 WHERE user_id=?", (976301,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 1
        async with db.execute("SELECT COUNT(*) FROM echo_shard_ledger_v1 WHERE user_id=?", (976301,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 1
        await must_reject(
            "UPDATE echo_shard_ledger_v1 SET delta=99 WHERE compensation_id=?", (first.compensation_id,),
            "append-only ledger rewrite must fail",
        )
        for column, value in (("user_id", 1), ("amount", 99), ("source_snapshot_hash", "0" * 64)):
            await must_reject(
                f"UPDATE echo_shard_compensations_v1 SET {column}=? WHERE id=?", (value, first.compensation_id),
                f"compensation receipt {column} must be append-only",
            )
        second_user = await compensate_max_duplicate(db, user_id=976302, event=event)
        assert second_user.applied and second_user.balance_after == 1, "source ids are per-user"
        for field, value in (("source_line_id", 0.5), ("observed_level", 16.0), ("amount", 1.0)):
            payload = dict(event.__dict__) if hasattr(event, "__dict__") else {
                "source_kind": event.source_kind, "source_event_id": f"float-{field}", "source_line_id": event.source_line_id,
                "collectible_kind": event.collectible_kind, "collectible_id": event.collectible_id,
                "observed_level": event.observed_level, "observed_cap": event.observed_cap,
                "amount": event.amount, "source_snapshot": event.source_snapshot,
            }
            payload[field] = value
            try:
                await compensate_max_duplicate(db, user_id=976301, event=MaxDuplicateCompensation(**payload))
            except EchoShardPolicyError:
                pass
            else:
                raise AssertionError(f"{field} must reject coercion")
    finally:
        await transaction.rollback(); await conn.close()
    print("OK: Echo Shards v1 internal compensation, replay, cap and append-only ledger")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
