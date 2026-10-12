#!/usr/bin/env python3
"""Real PostgreSQL proof of the season settlement: frozen places, qualification,
one payout per player, atomic Mora+Essence, resumable and idempotent passes."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from core import seasons as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import game_seasons as repo
from infrastructure.repositories import rhythm_v2 as rhythm_repo
from infrastructure.repositories import skins_v3 as skins_repo
from services import game_seasons, rhythm_v2
from services import skins_v3 as skins_service

PLAYERS = tuple(range(977001, 977015))      # 977001..977012 qualify; 977013, 977014 do not
OUTSIDER_RUNS, OUTSIDER_DAYS = 977013, 977014


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    other = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await economy_ledger.ensure_tables(db)
    await rhythm_repo.ensure_tables(db)
    await skins_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        async def clear_run(user_id: int, when: datetime, score: int, status: str = "clear") -> str:
            run_id = str(uuid4())
            await connection.execute(
                "INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,"
                "integrity_status,created_at,finished_at) VALUES ($1,$2,'normal','test',$3,'[]'::jsonb,'finished',0,$4,$5,$6,$6)",
                run_id, user_id, b"x" * 32, score, status, when)
            return run_id

        s1_start, s1_end = rules.season_bounds(1)
        s2_start, s2_end = rules.season_bounds(2)
        # 12 qualified players: score falls with the number; 5 runs on 3 days each.
        for index, user_id in enumerate(PLAYERS[:12]):
            for run_no in range(5):
                await clear_run(user_id, s1_start + timedelta(days=10 + run_no % 3, hours=run_no),
                                score=10_000 - index * 100 - run_no)
        # Highest score of all, but 4 runs only / only 2 days: never ranked, never paid.
        for run_no in range(4):
            await clear_run(OUTSIDER_RUNS, s1_start + timedelta(days=20 + run_no, hours=1), score=99_999)
        for run_no in range(5):
            await clear_run(OUTSIDER_DAYS, s1_start + timedelta(days=30 + run_no % 2, hours=run_no), score=99_998)
        await clear_run(PLAYERS[11], s1_start + timedelta(days=40), score=99_000, status="review_required")  # not clear
        await clear_run(PLAYERS[11], s2_start + timedelta(hours=1), score=99_000)                           # next season

        boards = {("rhythm", "normal"): rhythm_v2.season_standings}

        async def mora_of(user_id: int) -> int:
            async with db.execute("SELECT COALESCE(SUM(delta),0) FROM economic_ledger "
                                  "WHERE user_id=? AND currency='mora' AND reason_code='season_reward'", (user_id,)) as cursor:
                return int((await cursor.fetchone())[0])

        async def essence_of(user_id: int) -> int:
            async with db.execute("SELECT COALESCE(SUM(delta),0) FROM skins_v3_essence_ledger "
                                  "WHERE user_id=? AND reason='season_reward'", (user_id,)) as cursor:
                return int((await cursor.fetchone())[0])

        # 1. Inside the delay nothing happens: pending integrity verdicts may still resolve.
        early = await game_seasons.settle_due(db, boards=boards, now=s1_end + rules.SETTLEMENT_DELAY - timedelta(hours=1))
        assert early == {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}, early
        assert await mora_of(PLAYERS[0]) == 0

        # 2. A failing Essence grant rolls back that player's Mora too; the rest are paid.
        now = s1_end + rules.SETTLEMENT_DELAY + timedelta(hours=1)
        real_grant = skins_service.grant_essence_in_transaction
        victim = PLAYERS[2]

        async def flaky(db_, user_id, amount, *, reason, reference):
            if user_id == victim:
                raise RuntimeError("essence table hiccup")
            return await real_grant(db_, user_id, amount, reason=reason, reference=reference)

        skins_service.grant_essence_in_transaction = flaky
        try:
            first = await game_seasons.settle_due(db, boards=boards, now=now, batch=5)
        finally:
            skins_service.grant_essence_in_transaction = real_grant
        assert first == {"snapshots": 1, "paid": 11, "failed": 1, "closed": 0}, first
        assert await mora_of(victim) == 0 and await essence_of(victim) == 0, "Mora and Essence must fail together"
        assert not await repo.is_closed(db, season=1)

        # 3. The retry pays only the missing player, then the season closes.
        second = await game_seasons.settle_due(db, boards=boards, now=now, batch=5)
        assert second == {"snapshots": 0, "paid": 1, "failed": 0, "closed": 1}, second
        third = await game_seasons.settle_due(db, boards=boards, now=now)
        assert third == {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}, third

        # 4. Places: only qualified players are ranked; a 12-player board pays the podium and participation.
        expected = {0: (800, 200), 1: (600, 150), 2: (450, 120)}
        for index, user_id in enumerate(PLAYERS[:12]):
            mora, essence = expected.get(index, (40, 10))   # 12 players: no 4-10 tier (needs 20)
            assert (await mora_of(user_id), await essence_of(user_id)) == (mora, essence), (user_id, mora, essence)
        for user_id in (OUTSIDER_RUNS, OUTSIDER_DAYS):
            assert await mora_of(user_id) == 0 and await essence_of(user_id) == 0
            assert await game_seasons.last_result(db, game="rhythm", board="normal", user_id=user_id) is None
        last = await game_seasons.last_result(db, game="rhythm", board="normal", user_id=PLAYERS[0])
        assert last["season"] == 1 and last["place"] == 1 and last["reward_mora"] == 800 and last["reward_essence"] == 200, last
        # PLAYERS[11]'s review_required and next-season runs are not counted: still 12th with 5 runs.
        assert (await game_seasons.last_result(db, game="rhythm", board="normal", user_id=PLAYERS[11]))["result"]["runs"] == 5

        async with db.execute("SELECT players,mora_total,essence_total FROM game_season_closed WHERE season=1") as cursor:
            closed = dict(await cursor.fetchone())
        assert closed == {"players": 12, "mora_total": 800 + 600 + 450 + 9 * 40, "essence_total": 200 + 150 + 120 + 9 * 10}, closed

        # 5. Frozen places: a later integrity change cannot move paid results or pay again.
        await connection.execute("UPDATE rhythm_v2_runs SET integrity_status='quarantined' WHERE user_id=$1", PLAYERS[0])
        assert await game_seasons.settle_due(db, boards=boards, now=now) == {"snapshots": 0, "paid": 0, "failed": 0, "closed": 0}
        assert await mora_of(PLAYERS[0]) == 800

        # 6. A player on two paying boards is paid once, for the better reward (never the sum).
        async def minesweeper(db_, start, end):
            return [{"user_id": PLAYERS[5], "place": 1, "runs": 9, "days": 9},
                    {"user_id": PLAYERS[6], "place": 2, "runs": 9, "days": 9}]

        for index, user_id in enumerate(PLAYERS[:12]):
            for run_no in range(5):
                await clear_run(user_id, s2_start + timedelta(days=10 + run_no % 3, hours=run_no), score=5_000 + index * 10 - run_no)
        rules.PAYING_BOARDS = (("rhythm", "normal"), ("minesweeper", "easy"))
        try:
            later = s2_end + rules.SETTLEMENT_DELAY + timedelta(hours=1)
            both = {**boards, ("minesweeper", "easy"): minesweeper}
            result = await game_seasons.settle_due(db, boards=both, now=later)
            assert result["snapshots"] == 2 and result["paid"] == 12 and result["closed"] == 1, result
            async with db.execute("SELECT COUNT(*),COUNT(DISTINCT user_id) FROM game_season_payouts WHERE season=2") as cursor:
                assert tuple(await cursor.fetchone()) == (12, 12)
            # PLAYERS[5] is 6th on rhythm (participation 40) but 1st on minesweeper (board of 2: participation 40).
            # PLAYERS[0] is 1st on rhythm only: the podium.
            async with db.execute("SELECT SUM(delta) FROM economic_ledger WHERE user_id=? AND reason_code='season_reward'",
                                  (PLAYERS[5],)) as cursor:
                assert int((await cursor.fetchone())[0]) == 40 + 40, "season 1 payment plus ONE season 2 payment"
            try:
                await game_seasons.settle_due(db, boards=boards, now=later)
            except rules.SeasonRuleError:
                pass
            else:
                raise AssertionError("a paying board without standings must refuse to settle")
        finally:
            rules.PAYING_BOARDS = (("rhythm", "normal"),)

        # 7. Minesweeper does not pay and shows no reward table.
        view = game_seasons.season_view(game="minesweeper", board="hard")
        assert view["paying"] is False and view["rewards"] == [], view
        view = game_seasons.season_view(game="rhythm", board="normal")
        assert view["paying"] is True and view["rewards"] and view["terms"]["min_runs"] == 5, view

        # 8. One worker settles a season at a time (session lock visible from another connection).
        assert await repo.try_lock_season(db, season=77)
        assert not await repo.try_lock_season(PGAdapter(other), season=77)
        await repo.unlock_season(db, season=77)
        assert await repo.try_lock_season(PGAdapter(other), season=77)
        await repo.unlock_season(PGAdapter(other), season=77)
    finally:
        await transaction.rollback()
        await other.close()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("game seasons: PostgreSQL qualification, one payout, atomic Mora+Essence, resume and lock OK")
