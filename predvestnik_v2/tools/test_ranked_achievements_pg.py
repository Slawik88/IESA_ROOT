"""Reproduce four real ranked Rhythm completions at zero, restore, then count both modes."""
import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse
from unittest.mock import AsyncMock,patch
from uuid import uuid4

import asyncpg
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import league_v1 as league_repo,achievements_v1 as achievement_repo
from services import league_v1 as league,achievements_v1 as achievements,achievement_games
from core import league_v1 as rules


async def finish_rhythm(db,uid):
    packet=await league.start(db,user_id=uid,game="rhythm",level=1)
    actions=[{"kind":"tap","signal_no":n,"rune":r,"elapsed_ms":260+n*37%90} for n,r in enumerate(packet["runes"],1)]
    for draft in range(len(packet["drafts"]),0,-1):
        actions.insert(draft*rules.RHYTHM_CHUNK,{"kind":"pick","perk_id":None})
    await db.execute("UPDATE league_demo_runs SET started_at=started_at-INTERVAL '2 minutes' WHERE run_id=?",(packet["run_id"],))
    result=await league.rhythm_finish(db,user_id=uid,run_id=packet["run_id"],actions=actions)
    assert result["stars"]==3,result
    assert (await league.rhythm_finish(db,user_id=uid,run_id=packet["run_id"],actions=actions))["replay"]
    return result


async def run(dsn):
    conn=await asyncpg.connect(dsn);await conn.execute("SET search_path TO predvestnik,public")
    db=PGAdapter(conn)
    await league_repo.ensure_tables(db);await achievement_repo.ensure_tables(db)
    transaction=conn.transaction();await transaction.start()
    uid=99677101
    try:
        await db.execute("INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,'ranked_achievement_qa')",(uid,))
        with patch.object(league,"_season",lambda now=None:"s2"):
            # Exactly the production defect: ranked results existed, but the bridge was absent.
            with patch.object(achievement_games,"record_ranked",AsyncMock()):
                for _ in range(4):await finish_rhythm(db,uid)
            assert await conn.fetchval("SELECT COUNT(*) FROM league_demo_runs WHERE user_id=$1 AND status='finished'",uid)==4
            before={f["id"]:f for f in (await achievements.overview(db,user_id=uid))["families"]}
            assert before["rhythm"]["completed_events"]==0
            restored=await achievements.reconcile_history(db,user_id=uid)
            assert restored["games_restored"]==4 and not restored["games_pending"],restored
            view={f["id"]:f for f in (await achievements.overview(db,user_id=uid))["families"]}
            assert view["rhythm"]["completed_events"]==4 and view["rhythm"]["level"]==1
            money=await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=$1",uid)
            assert (await achievements.reconcile_history(db,user_id=uid))["games_restored"]==0
            assert await conn.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=$1",uid)==money
            await finish_rhythm(db,uid)
            assert await conn.fetchval("SELECT completed_events FROM achievement_v1_progress WHERE user_id=$1 AND family='rhythm'",uid)==5
            # A failed final result save must roll back the new achievement receipt too.
            with patch.object(league_repo,"update_run",AsyncMock(side_effect=RuntimeError("result write failed"))):
                try:
                    await finish_rhythm(db,uid)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("expected result-save failure")
            assert await conn.fetchval("SELECT completed_events FROM achievement_v1_progress WHERE user_id=$1 AND family='rhythm'",uid)==5
            # Casual finished terminals share the family, with their original receipt identity.
            for status,integrity in (("finished","clear"),("cancelled","clear"),("finished","quarantined")):
                rid='qa-'+uuid4().hex
                await db.execute("INSERT INTO rhythm_v2_runs(run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,integrity_status,finished_at) VALUES (?,?,'normal','qa',?,'[]'::jsonb,?,0,?,CLOCK_TIMESTAMP())",(rid,uid,b'qa',status,integrity))
            assert (await achievements.reconcile_history(db,user_id=uid))["games_restored"]==1
            assert await conn.fetchval("SELECT completed_events FROM achievement_v1_progress WHERE user_id=$1 AND family='rhythm'",uid)==6
            assert await conn.fetchval("SELECT COUNT(*) FROM achievement_v1_reward_receipts WHERE user_id=$1 AND family='rhythm'",uid)==1
            # Ranked Minesweeper counts a finished loss as a completion, like casual play.
            attempt=await league.start(db,user_id=uid,game="minesweeper",level=1)
            row=await league_repo.lock_run(db,run_id=attempt["run_id"],user_id=uid)
            board=league_repo.load(row["board_json"])
            mine=next(iter(board["mines"]))
            end=await league.mines_act(db,user_id=uid,run_id=attempt["run_id"],revision=attempt["revision"],kind="open",cell=mine)
            assert end["status"]=="lost"
            assert await conn.fetchval("SELECT completed_events FROM achievement_v1_progress WHERE user_id=$1 AND family='minesweeper'",uid)==1
        with patch.object(league,"_season",lambda now=None:rules.DEMO_SEASON):
            await finish_rhythm(db,uid)
        assert await conn.fetchval("SELECT completed_events FROM achievement_v1_progress WHERE user_id=$1 AND family='rhythm'",uid)==6
        assert (await achievements.reconcile_history(db,user_id=uid))["games_restored"]==0
        print("PASS: four verified ranked runs restored from zero; live ranked + casual share progress; retry/reconcile never duplicate; cancellations/quarantine/demo excluded; ranked Minesweeper completion counted")
    finally:
        await transaction.rollback();await conn.close()


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--dsn",required=True);args=p.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost","127.0.0.1","::1"}:raise SystemExit("loopback database required")
    asyncio.run(run(args.dsn))
