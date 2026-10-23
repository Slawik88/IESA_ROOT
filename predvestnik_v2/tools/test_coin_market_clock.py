"""Fast-tick switch: continuity of tick indices, wall-clock mapping and order rebase.

Pure part always runs; the PostgreSQL part runs when PG_TEST_DSN is set
(disposable schema, dropped afterwards).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.coin_market_clock import (Clock, DAY_SECONDS, LEGACY_SECONDS, TICK_SECONDS,
                                    rebased_expiry, tick_at, tick_of, ticks_back)


def pure() -> None:
    base = 5_920_000
    clock = Clock(base * LEGACY_SECONDS, base)
    switch = clock.switch_epoch
    assert tick_of(switch - 1, clock) == base - 1
    assert tick_of(switch, clock) == base == switch // LEGACY_SECONDS
    assert tick_of(switch + TICK_SECONDS, clock) == base + 1
    # Every second after the switch maps to a tick whose start is not later than it.
    previous = tick_of(switch - 600, clock)
    for second in range(switch - 600, switch + 3_600):
        tick = tick_of(second, clock)
        assert tick in (previous, previous + 1), "ticks never jump or go back"
        assert tick_at(tick, clock) <= second < tick_at(tick + 1, clock)
        previous = tick
    # Twice as many ticks per hour after the switch, same as before it.
    assert tick_of(switch + 3_600, clock) - tick_of(switch, clock) == 24
    assert tick_of(switch, clock) - tick_of(switch - 3_600, clock) == 12
    # A 24h window straddling the switch starts exactly one day earlier.
    now = tick_of(switch + 7_200, clock)
    start = ticks_back(now, DAY_SECONDS, clock)
    assert tick_at(start, clock) == tick_at(now, clock) - DAY_SECONDS
    # Pending orders keep their wall-clock deadline.
    old_expiry = base + 100
    assert tick_at(rebased_expiry(old_expiry, clock), clock) == old_expiry * LEGACY_SECONDS
    assert rebased_expiry(base - 5, clock) == base - 5
    assert tick_of(1_000, None) == 1_000 // LEGACY_SECONDS
    try:
        Clock(switch + 1, base)
    except ValueError:
        pass
    else:
        raise AssertionError("misaligned switch must be rejected")


async def database(dsn: str) -> None:
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import coin_market_v2 as repo

    schema = "cm2_clock_" + uuid4().hex[:10]
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        await conn.execute("""CREATE TABLE coin_market_v2_orders(
            id TEXT PRIMARY KEY, status TEXT NOT NULL, created_tick BIGINT NOT NULL,
            expires_tick BIGINT NOT NULL)""")
        legacy = await conn.fetchval("SELECT FLOOR(EXTRACT(EPOCH FROM clock_timestamp())/300)::bigint")
        await conn.executemany(
            "INSERT INTO coin_market_v2_orders VALUES($1,$2,$3,$4)",
            [("pending", "pending", legacy - 10, legacy + 8_000),
             ("filled", "filled", legacy - 10, legacy + 8_000),
             ("old", "pending", legacy - 10, legacy)],
        )
        db = PGAdapter(conn)
        repo._clock = None
        await repo.ensure_clock(db)
        await repo.ensure_clock(db)  # second start must not stretch again
        clock = await repo.clock(db)
        assert clock.base_tick == legacy + 1
        rows = dict(await conn.fetch("SELECT id,expires_tick FROM coin_market_v2_orders"))
        assert rows["pending"] == rebased_expiry(legacy + 8_000, clock)
        assert rows["filled"] == legacy + 8_000 and rows["old"] == legacy
        now = await repo.current_tick(db)
        assert now == legacy or now == legacy + 1, "no jump at deployment"
        await conn.execute("UPDATE coin_market_v2_clock SET switch_epoch=switch_epoch-3600, base_tick=base_tick-12")
        # Switch an hour ago: legacy pace would be at ~legacy, the fast pace is ~12 ticks ahead.
        assert legacy + 10 <= await repo.current_tick(db) <= legacy + 13
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()
        repo._clock = None


if __name__ == "__main__":
    pure()
    dsn = os.environ.get("PG_TEST_DSN")
    if dsn:
        asyncio.run(database(dsn))
    print("PASS: coin market clock — continuous ticks, 24/hour after switch, day windows, order deadlines"
          + (" and PostgreSQL switch" if dsn else ""))
