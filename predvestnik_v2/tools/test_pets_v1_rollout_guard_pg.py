"""Loopback PostgreSQL proof of the Pets V1 -> Trail rollout boundary."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import pets_v1 as repo, system_flags
from services import pets_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    tx = conn.transaction()
    await tx.start()
    try:
        await repo.ensure_tables(db)
        await system_flags.ensure_table(db)
        await system_flags.set_flag(db, "pets_v2", False)
        # Keep this boundary proof free of wallet/key awards, even in the test DB.
        await system_flags.set_flag(db, "content_chests_v1", False)
        user = 977301
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
        async with db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?, 'Rollout pet', 'moss_cat', 'common') RETURNING id",
            (user,),
        ) as cur:
            pet_id = int((await cur.fetchone())[0])
        await pets_v1.select_active_pet(db, user, pet_id, "rollout-select")
        old = await pets_v1.start_activity(db, user_id=user, kind="trek", hours=3, action_id="rollout-before")
        old_id = old["activity"]["id"]
        await db.execute("UPDATE pet_v1_runs SET ends_at=NOW()-INTERVAL '1 second' WHERE id=?", (old_id,))
        await system_flags.set_flag(db, "pets_v2", True)
        async with db.execute("SELECT COUNT(*) FROM pet_v1_runs WHERE user_id=?", (user,)) as cur:
            before_count = int((await cur.fetchone())[0])
        try:
            await pets_v1.start_activity(db, user_id=user, kind="trek", hours=3, action_id="rollout-blocked")
        except pets_v1.PetConflict as exc:
            assert "Троп" in str(exc), "the stale client must be told to open the Trail"
        else:
            raise AssertionError("an enabled Trail must reject fresh V1 activities, including after a due legacy trek")
        async with db.execute("SELECT COUNT(*) FROM pet_v1_runs WHERE user_id=?", (user,)) as cur:
            assert int((await cur.fetchone())[0]) == before_count
        state = await repo.get_state(db, user, pet_id)
        assert int(state["endurance"]) == 75, "rejecting a stale client must not charge endurance"
        replay = await pets_v1.start_activity(db, user_id=user, kind="trek", hours=3, action_id="rollout-before")
        assert replay["idempotent_replay"] and replay["activity"]["id"] == old_id
        legacy = await pets_v1.overview(db, user)
        assert legacy["activity"] is None, "pre-rollout treks must still finish while the Trail is enabled"
        async with db.execute("SELECT status FROM pet_v1_runs WHERE id=?", (old_id,)) as cur:
            assert (await cur.fetchone())[0] == "claimed"
        await system_flags.set_flag(db, "pets_v2", False)
        resumed = await pets_v1.start_activity(db, user_id=user, kind="trek", hours=3, action_id="rollout-after-disable")
        assert resumed["activity"]["status"] == "active", "disabling the Trail restores the classic start path"
    finally:
        await tx.rollback()
        await conn.close()
    print("OK: Trail rollout blocks fresh V1 runs, preserves retries and old settlement, and restores V1 when disabled")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
