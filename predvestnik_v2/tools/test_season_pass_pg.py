#!/usr/bin/env python3
"""Real PostgreSQL proof of the season pass: dark flag, no daily cap, receipts, claims, season edges."""
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
from infrastructure.repositories import rhythm_v2 as rhythm_repo
from infrastructure.repositories import season_pass as repo
from infrastructure.repositories import skins_v3 as skins_repo
from infrastructure.repositories import system_flags
from services import season_pass as service
from services import skins_v3 as skins_service

USER, OTHER = 978001, 978002
NEWBIE, NO_RECORD = 978010, 978011


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
    await rhythm_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        s1_start, s1_end = seasons.season_bounds(1)
        noon = lambda day: s1_start + timedelta(days=day, hours=12)

        # Chat records decide account age (ensure the two tables exist; the test rolls back).
        await db.execute("CREATE TABLE IF NOT EXISTS user_chat_stats (user_tg_id BIGINT, chat_tg_id BIGINT, "
                         "joined_at TIMESTAMP DEFAULT NOW(), membership_since TIMESTAMPTZ DEFAULT NOW(), "
                         "PRIMARY KEY (user_tg_id, chat_tg_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS daily_user_stats (user_id BIGINT, chat_id BIGINT, date TEXT, "
                         "message_count INTEGER DEFAULT 1, PRIMARY KEY (user_id, chat_id, date))")

        async def seen_in_chat(user: int, when: datetime) -> None:
            await db.execute("INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, joined_at, membership_since) "
                             "VALUES (?, 1, ?, ?) ON CONFLICT DO NOTHING",
                             (user, when.replace(tzinfo=None), when))

        for old in (USER, OTHER):
            await seen_in_chat(old, s1_start - timedelta(days=60))

        async def play(n: int, day: int, *, user: int = USER, tag: str = "g") -> int:
            return sum([await service.record_game(db, user_id=user, source="rhythm", event_id=f"{tag}{day}-{i}",
                                                   points=10, occurred_at=noon(day)) for i in range(n)])

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
        assert await service.record_game(db, user_id=USER, source="rhythm", event_id="dark", points=10, occurred_at=noon(1)) == 0
        assert await points_of(USER) == 0
        assert await service.status(db, user_id=USER, now=noon(1)) == {"enabled": False}
        try:
            await service.claim(db, user_id=USER, season=1, now=noon(1))
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("claim must be refused while the pass is dark")
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (rules.FLAG,))

        # 2. No daily cap, one receipt per game: the 11th game of a day still counts, a replay adds nothing.
        assert await play(10, 1) == 100 and await points_of(USER) == 100
        assert await play(1, 1, tag="extra") == 10 and await points_of(USER) == 110
        assert await service.record_game(db, user_id=USER, source="rhythm", event_id="g1-0", points=10,
                                         occurred_at=noon(1)) == 0
        assert await points_of(USER) == 110
        async with db.execute("SELECT COUNT(*),COALESCE(SUM(points),0) FROM season_pass_receipts WHERE user_id=?", (USER,)) as cursor:
            assert tuple(await cursor.fetchone()) == (11, 110)
        assert await repo.day_points(db, user_id=USER, season=1, day=noon(1).date()) == 110
        # A long run pays by its score in one go.
        assert await service.record_game(db, user_id=USER, source="rhythm", event_id="long", occurred_at=noon(2),
                                         points=rules.rhythm_points(70_000)) == 831
        assert await points_of(USER) == 941
        assert await service.record_game(db, user_id=OTHER, source="minesweeper", event_id="m1", points=10, occurred_at=noon(1)) == 10

        # 3. Unknown sources are rejected loudly (a programming error, not a game failure).
        try:
            await service.record_game(db, user_id=USER, source="mafia", event_id="x", points=10)
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
            assert await service.record_game(db, user_id=USER, source="rhythm", event_id="boom", points=10, occurred_at=noon(9)) == 0
        finally:
            repo.insert_receipt = real
        assert await repo.day_points(db, user_id=USER, season=1, day=noon(9).date()) == 0

        # 5. Reach a few levels and claim: Mora + Essence once, in one transaction.
        for day in range(4, 14):
            await play(10, day)
        total = await points_of(USER)
        view = (await service.status(db, user_id=USER, now=noon(13)))["seasons"][0]
        assert view["points"] == total and view["level"] == total // 300 and view["current"] is True, view
        level = view["level"]
        assert view["claimable"] == {"mora": level * 40, "essence": level * 10}, view
        assert "points_today" not in view and "points_per_game" not in view, "the rule of points stays hidden"
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
        assert await service.record_game(db, user_id=OTHER, source="rhythm", event_id="edge1", points=10,
                                         occurred_at=s1_end - timedelta(seconds=1)) == 10
        assert await service.record_game(db, user_id=OTHER, source="rhythm", event_id="edge2", points=10, occurred_at=s1_end) == 10
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

        # 11a. Account age: 14 days in the bot are needed to claim; points still accrue, no record = new.
        await seen_in_chat(NEWBIE, noon(5))
        await play(10, 6, user=NEWBIE)
        await play(10, 7, user=NEWBIE)
        await play(10, 8, user=NEWBIE, tag="n")
        await db.execute("UPDATE season_pass_progress SET points=900 WHERE user_id=? AND season=1", (NEWBIE,))
        view = await service.status(db, user_id=NEWBIE, now=noon(10))
        assert view["account"]["eligible"] is False and view["account"]["min_days"] == 14, view
        assert view["seasons"][0]["points"] == 900 and view["seasons"][0]["claimable_levels"] == 3
        try:
            await service.claim(db, user_id=NEWBIE, season=1, now=noon(18))     # 13 days: still too new
        except service.SeasonPassError as error:
            assert "14 дней" in str(error)
        else:
            raise AssertionError("an account under 14 days must not claim")
        assert await mora_of(NEWBIE) == 0
        edge = await service.claim(db, user_id=NEWBIE, season=1, now=noon(19))  # exactly 14 days after
        assert edge["mora"] == 120 and await mora_of(NEWBIE) == 120
        # An earlier first-day record in the daily stats counts too (old players lack a good joined_at).
        await db.execute("INSERT INTO daily_user_stats(user_id, chat_id, date) VALUES (?, 1, ?)",
                         (NEWBIE, (noon(5) - timedelta(days=40)).date().isoformat()))
        assert (await service.status(db, user_id=NEWBIE, now=noon(10)))["account"]["eligible"] is True
        # No chat record at all: new by definition.
        await service.record_game(db, user_id=NO_RECORD, source="rhythm", event_id="x", points=10, occurred_at=noon(2))
        await db.execute("UPDATE season_pass_progress SET points=300 WHERE user_id=? AND season=1", (NO_RECORD,))
        assert (await service.status(db, user_id=NO_RECORD, now=noon(30)))["account"] == \
            {"eligible": False, "eligible_from": None, "min_days": 14}
        try:
            await service.claim(db, user_id=NO_RECORD, season=1, now=noon(30))
        except service.SeasonPassError:
            pass
        else:
            raise AssertionError("an account without a chat record must not claim")

        # 11b. A flag read that fails with a SQL error must not poison the caller's transaction.
        real_enabled = system_flags.is_enabled

        async def broken_flag(db_, key):
            await db_.execute("SELECT 1 FROM no_such_flags_table")

        system_flags.is_enabled = broken_flag
        try:
            async with db.connection.transaction():
                assert await service.record_game(db, user_id=USER, source="rhythm", event_id="flag-down", points=10,
                                                 occurred_at=noon(2)) == 0
                async with db.execute("SELECT 1") as cursor:
                    assert (await cursor.fetchone())[0] == 1, "the outer transaction must stay usable"
        finally:
            system_flags.is_enabled = real_enabled

        # 11c. A manually cleared Rhythm run counts for the pass like an automatically clear one.
        from uuid import uuid4
        from services import rhythm_v2 as rhythm_game
        reviewed = 978004
        run_id = str(uuid4())
        await db.connection.execute(
            "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,"
            "integrity_status,correct_taps,created_at,finished_at) VALUES ($1,$2,'normal','test',$3,'[]'::jsonb,"
            "'finished',0,900,'review_required',25,$4,$4)", run_id, reviewed, b"x" * 32, noon(3))
        from unittest.mock import patch
        from services import quests_v1 as quests
        async def quest_conflict(*args, **kwargs):
            raise quests.QuestConflict("fault: quest sources unavailable")
        with patch.object(quests, "available_sources", quest_conflict):
            await rhythm_game.review_run(db, reviewer_id=1, run_id=run_id, review_id=f"rv-{run_id}",
                                         decision="clear", reason="проверено вручную: честный забег")
        assert await db.connection.fetchval("SELECT integrity_status FROM rhythm_v2_runs WHERE run_id=$1", run_id) == 'clear'
        assert await points_of(reviewed) == rules.rhythm_points(900) == 27, "a manual 'clear' must earn the pass points"

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
        assert await points_of(third) == rules.rhythm_points(900) == 27, "a run pays by its score"
        await rhythm_v2._record_completed_quest(db, user_id=third, run_id="r-ok", mode="normal", score=900,
                                                integrity_status="clear", correct_taps=20, finished_at=noon(30))
        assert await points_of(third) == 27, "the same run counts once"
        current = seasons.season_number(datetime.now(timezone.utc))   # Minesweeper points land "now"
        before = await points_of(third, current)
        await minesweeper_v2._record_completed_quest(db, user_id=third, run_id="m-lost", difficulty="easy", won=False)
        assert await points_of(third, current) == before, "a lost game earns nothing"
        await minesweeper_v2._record_completed_quest(db, user_id=third, run_id="m-won", difficulty="easy", won=True)
        assert await points_of(third, current) == before + rules.MINESWEEPER_POINTS, "a won game earns points"
        # Real SQL aborts at lookup and after a first metric must only roll back
        # the complete optional quest block, preserving pass and game settlement.
        await db.execute("CREATE TEMP TABLE pass_quest_fault_probe (n INTEGER)")
        for game in ("rhythm", "minesweeper"):
            for phase in ("lookup", "late_metric"):
                start_points = await points_of(third, current)
                calls = []
                async def sources(db_, **kwargs):
                    if phase == "lookup":
                        await db_.execute("SELECT 1 FROM no_such_quest_source")
                    return {}
                async def metric(db_, **kwargs):
                    calls.append(kwargs["metric"])
                    await db_.execute("INSERT INTO pass_quest_fault_probe VALUES (1)")
                    if len(calls) == 2:
                        await db_.execute("SELECT 1 FROM no_such_late_quest_metric")
                with patch.object(quests, "available_sources", sources), patch.object(quests, "record_metric", metric):
                    if game == "rhythm":
                        await rhythm_v2._record_completed_quest(db, user_id=third, run_id=f"fault-{game}-{phase}", mode="normal", score=900,
                            integrity_status="clear", correct_taps=20)
                    else:
                        await minesweeper_v2._record_completed_quest(db, user_id=third, run_id=f"fault-{game}-{phase}", difficulty="easy", won=True)
                assert await points_of(third, current) == start_points + (rules.rhythm_points(900) if game == "rhythm" else rules.MINESWEEPER_POINTS)
                assert await db.connection.fetchval("SELECT COUNT(*) FROM pass_quest_fault_probe") == 0
                assert await db.connection.fetchval("SELECT 1") == 1

    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("season pass: PostgreSQL dark flag, no daily cap, receipts, atomic claims, season edges OK")
