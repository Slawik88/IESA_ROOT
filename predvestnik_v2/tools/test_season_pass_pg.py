#!/usr/bin/env python3
"""Real PostgreSQL proof of the season pass: dark flag, daily cap, receipts, claims, season edges."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import asyncpg

from core import season_pass as rules
from core import seasons
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import season_pass as repo
from infrastructure.repositories import skins_v3 as skins_repo
from infrastructure.repositories import system_flags
from services import season_pass as service
from services import skins_v3 as skins_service

USER, OTHER = 978001, 978002


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await economy_ledger.ensure_tables(db)
    await skins_repo.ensure_tables(db)
    await system_flags.ensure_table(db)
    await repo.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        s1_start, s1_end = seasons.season_bounds(1)
        noon = lambda day: s1_start + timedelta(days=day, hours=12)

        async def play(n: int, day: int, *, user: int = USER, tag: str = "g") -> int:
            return sum([await service.record_game(db, user_id=user, source="rhythm", event_id=f"{tag}{day}-{i}",
                                                   occurred_at=noon(day)) for i in range(n)])

        async def mora_of(user: int) -> int:
            async with db.execute("SELECT COALESCE(SUM(delta),0) FROM economic_ledger "
                                  "WHERE user_id=? AND currency='mora' AND reason_code='season_pass'", (user,)) as cursor:
                return int((await cursor.fetchone())[0])

        async def essence_of(user: int) -> int:
            async with db.execute("SELECT COALESCE(SUM(delta),0) FROM skins_v3_essence_ledger "
                                  "WHERE user_id=? AND reason='season_pass'", (user,)) as cursor:
                return int((await cursor.fetchone())[0])

        async def points_of(user: int, season: int = 1) -> int:
            progress = await repo.progress(db, user_id=user, season=season)
            return int(progress["points"]) if progress else 0

        # 1. Dark by default: no points, no rows, no claim.
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (rules.FLAG,))
        assert await service.record_game(db, user_id=USER, source="rhythm", event_id="dark", occurred_at=noon(1)) == 0
        assert await points_of(USER) == 0
        assert await service.status(db, user_id=USER, now=noon(1)) == {"enabled": False}
        try:
            await service.claim(db, user_id=USER, season=1, now=noon(1))
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("claim must be refused while the pass is dark")
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (rules.FLAG,))

        # 2. Daily cap and receipts: 10 games fill the day, the 11th adds nothing; a replay adds nothing.
        assert await play(10, 1) == 100 and await points_of(USER) == 100
        assert await play(1, 1, tag="extra") == 0 and await points_of(USER) == 100
        assert await service.record_game(db, user_id=USER, source="rhythm", event_id="g1-0", occurred_at=noon(1)) == 0
        assert await points_of(USER) == 100
        async with db.execute("SELECT COUNT(*),COALESCE(SUM(points),0) FROM season_pass_receipts WHERE user_id=?", (USER,)) as cursor:
            assert tuple(await cursor.fetchone()) == (11, 100), "the capped game still leaves a receipt (zero points)"
        assert await play(10, 2) == 100 and await points_of(USER) == 200
        # An overlapping day cap: 95 points earned, the next game grants only 5.
        assert await play(9, 3, tag="a") == 90 and await play(1, 3, tag="b") == 10 and await play(1, 3, tag="c") == 0
        assert await service.record_game(db, user_id=OTHER, source="minesweeper", event_id="m1", occurred_at=noon(1)) == 10

        # 3. Unknown sources are rejected loudly (a programming error, not a game failure).
        try:
            await service.record_game(db, user_id=USER, source="mafia", event_id="x")
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("mafia is not a point source yet")

        # 4. A failing points write never breaks the game and leaves no partial rows.
        real = repo.insert_receipt

        async def broken(*args, **kwargs):
            raise RuntimeError("receipts table hiccup")

        repo.insert_receipt = broken
        try:
            assert await service.record_game(db, user_id=USER, source="rhythm", event_id="boom", occurred_at=noon(9)) == 0
        finally:
            repo.insert_receipt = real
        assert await repo.day_points(db, user_id=USER, season=1, day=noon(9).date()) == 0

        # 5. Reach level 10 (3000 points) and claim: 400 Mora + 100 Essence once, in one transaction.
        for day in range(4, 14):
            await play(10, day)
        total = await points_of(USER)
        view = (await service.status(db, user_id=USER, now=noon(13)))["seasons"][0]
        assert view["points"] == total and view["level"] == total // 300 and view["current"] is True, view
        level = view["level"]
        assert view["claimable"] == {"mora": level * 40, "essence": level * 10}, view
        assert view["points_today"] == 100 and view["points_today_cap"] == 100
        result = await service.claim(db, user_id=USER, season=1, now=noon(13))
        assert result == {"season": 1, "claimed_levels": f"1-{level}", "mora": level * 40, "essence": level * 10,
                          "claimed_level": level}, result
        assert await mora_of(USER) == level * 40 and await essence_of(USER) == level * 10
        try:
            await service.claim(db, user_id=USER, season=1, now=noon(13))
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("nothing new to claim")

        # 6. Defence in depth: even if the claimed marker were lost, the ledger keys replay as no-ops.
        await repo.set_claimed_level(db, user_id=USER, season=1, level=0)
        again = await service.claim(db, user_id=USER, season=1, now=noon(13))
        assert again["claimed_levels"] == f"1-{level}"
        assert await mora_of(USER) == level * 40 and await essence_of(USER) == level * 10, "no double credit"

        # 7. A failing Essence grant rolls the whole claim back; the retry then succeeds once.
        await db.execute("UPDATE season_pass_progress SET points=points+600 WHERE user_id=? AND season=1", (USER,))
        before_mora, before_ess = await mora_of(USER), await essence_of(USER)
        real_grant = skins_service.grant_essence_in_transaction

        async def flaky(*args, **kwargs):
            raise RuntimeError("essence hiccup")

        skins_service.grant_essence_in_transaction = flaky
        try:
            await service.claim(db, user_id=USER, season=1, now=noon(13))
        except RuntimeError:
            pass
        else:
            raise AssertionError("the failure must surface")
        finally:
            skins_service.grant_essence_in_transaction = real_grant
        assert await mora_of(USER) == before_mora and await essence_of(USER) == before_ess, "Mora and Essence fail together"
        assert (await repo.progress(db, user_id=USER, season=1))["claimed_level"] == level
        done = await service.claim(db, user_id=USER, season=1, now=noon(13))
        assert done["mora"] == 2 * 40 and done["essence"] == 2 * 10, done

        # 8. The track ends at 30 levels: the budget is exactly 1200 Mora + 300 Essence.
        await db.execute("UPDATE season_pass_progress SET points=100000 WHERE user_id=? AND season=1", (USER,))
        await service.claim(db, user_id=USER, season=1, now=noon(13))
        assert await mora_of(USER) == 1200 and await essence_of(USER) == 300, (await mora_of(USER), await essence_of(USER))
        try:
            await service.claim(db, user_id=USER, season=1, now=noon(13))
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("the track is complete")

        # 9. Season edges: the last second belongs to season 1, the end instant to season 2.
        assert await service.record_game(db, user_id=OTHER, source="rhythm", event_id="edge1",
                                         occurred_at=s1_end - timedelta(seconds=1)) == 10
        assert await service.record_game(db, user_id=OTHER, source="rhythm", event_id="edge2", occurred_at=s1_end) == 10
        assert await points_of(OTHER, 1) == 20 and await points_of(OTHER, 2) == 10

        # 10. Claim window: season 1 stays claimable 30 days after its end, then lapses.
        await db.execute("UPDATE season_pass_progress SET points=300, claimed_level=0 WHERE user_id=? AND season=1", (OTHER,))
        try:
            await service.claim(db, user_id=OTHER, season=1, now=s1_end + timedelta(days=31))
        except service.SeasonPassError as error:
            assert "истёк" in str(error)
        else:
            raise AssertionError("lapsed")
        late = await service.claim(db, user_id=OTHER, season=1, now=s1_end + timedelta(days=29))
        assert late["mora"] == 40 and late["essence"] == 10
        status = await service.status(db, user_id=OTHER, now=s1_end + timedelta(days=29))
        assert [row["season"] for row in status["seasons"]] == [1, 2], status
        status = await service.status(db, user_id=OTHER, now=s1_end + timedelta(days=31))
        assert [row["season"] for row in status["seasons"]] == [2], status

        # 11. The game hooks feed the pass only for qualifying games.
        from services import minesweeper_v2, rhythm_v2
        third = 978003
        await rhythm_v2._record_completed_quest(db, user_id=third, run_id="r-short", mode="normal", score=900,
                                                integrity_status="clear", correct_taps=19, finished_at=noon(30))
        await rhythm_v2._record_completed_quest(db, user_id=third, run_id="r-review", mode="normal", score=900,
                                                integrity_status="review_required", correct_taps=99, finished_at=noon(30))
        assert await points_of(third) == 0
        await rhythm_v2._record_completed_quest(db, user_id=third, run_id="r-ok", mode="normal", score=900,
                                                integrity_status="clear", correct_taps=20, finished_at=noon(30))
        assert await points_of(third) == 10
        await rhythm_v2._record_completed_quest(db, user_id=third, run_id="r-ok", mode="normal", score=900,
                                                integrity_status="clear", correct_taps=20, finished_at=noon(30))
        assert await points_of(third) == 10, "the same run counts once"
        current = seasons.season_number(datetime.now(timezone.utc))   # Minesweeper points land "now"
        before = await points_of(third, current)
        await minesweeper_v2._record_completed_quest(db, user_id=third, run_id="m-lost", difficulty="easy", won=False)
        assert await points_of(third, current) == before, "a lost game earns nothing"
        await minesweeper_v2._record_completed_quest(db, user_id=third, run_id="m-won", difficulty="easy", won=True)
        assert await points_of(third, current) == before + 10, "a won game earns points"
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("season pass: PostgreSQL dark flag, daily cap, receipts, atomic claims, season edges OK")
