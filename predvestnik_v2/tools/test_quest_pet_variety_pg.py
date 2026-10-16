"""Real terminal claims, frozen UTC periods and atomic secondary progress."""
from __future__ import annotations
import argparse, asyncio, pathlib, random, sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from urllib.parse import urlparse
import asyncpg
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import quests_v1 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import quests_v1 as repo, pets_v2 as pet_repo, achievements_v1, chests_v1, vip_v2
from services import quests_v1 as quests, pets_v2 as pets


async def seed_assignments(db, uid, keys, daily='pet_trek_1', weekly='pet_activity_2'):
    for period, ids in [('daily',[daily,'rhythm_runs_3','minesweeper_plays_2','any_game_4']),
                        ('weekly',[weekly,'rhythm_runs_10','minesweeper_plays_8','any_game_18','minesweeper_easy_wins_3'])]:
        await db.execute('DELETE FROM quest_v1_assignments WHERE user_id=? AND period=? AND period_key=?',(uid,period,keys[period]))
        for slot,qid in enumerate(ids):
            await repo.create_assignment(db,user_id=uid,period=period,period_key=keys[period],slot=slot,
                                         definition={**rules.definition(qid),'policy_version':rules.POLICY_VERSION})


async def run(dsn):
    conn=await asyncpg.connect(dsn)
    await conn.execute('SET search_path TO predvestnik,public')
    db=PGAdapter(conn)
    tx=conn.transaction(); await tx.start()
    try:
        for module in (repo,pet_repo,achievements_v1,chests_v1,vip_v2):await module.ensure_tables(db)
        owner,other=98763001,98763002
        for uid in (owner,other):await db.execute('INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING',(uid,))
        for flag in ('pets_v2','game_rhythm_v2','game_minesweeper_v2'):
            await db.execute('INSERT INTO system_flags(key,enabled) VALUES (?,1) ON CONFLICT(key) DO UPDATE SET enabled=1',(flag,))
        assert not any(s.startswith('pets_v2') for s in await quests.available_sources(db,user_id=other))
        pids=[]
        for species in ('moss_cat','mirror_owl','salt_fox','stone_beetle','ash_moth'):
            async with db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,'common') RETURNING id",(owner,species,species)) as c:
                pids.append(int((await c.fetchone())[0]))
        sources=await quests.available_sources(db,user_id=owner)
        assert 'pets_v2' in sources
        assert await conn.fetchval('SELECT COUNT(*) FROM pet_v2_state WHERE user_id=$1',owner)==0
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key='pets_v2'")
        assert not any(s.startswith('pets_v2') for s in await quests.available_sources(db,user_id=owner))
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='pets_v2'")
        keys=quests.period_keys()
        await seed_assignments(db,owner,keys)
        for i,kind in enumerate(('trek','expedition','watch')):
            await repo.replace_assignment(db,user_id=owner,period='daily',period_key=keys['daily'],slot=0,
                definition={**rules.definition({'trek':'pet_trek_1','expedition':'pet_expedition_1','watch':'pet_watch_1'}[kind]),'policy_version':rules.POLICY_VERSION},generation=0)
            options=dict(user_id=owner,pet_id=pids[i*2 if i<2 else 3],kind=kind,hours=12 if kind=='watch' else 3,
                         route=None if kind=='watch' else 'forest')
            if i==0:options['companion_id']=pids[1]
            await pets.preview_run(db,**options)
            before=int(await conn.fetchval('SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=$1',owner))
            started=await pets.start_run(db,**options,action_id=f'start-{i}')
            rid=started['run_id']
            assert int(await conn.fetchval('SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=$1',owner))==before
            await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE id=?",(rid,))
            args=dict(user_id=owner,run_id=rid,action_id=f'claim-{i}',path='careful' if kind=='expedition' else None,rng=random.Random(5))
            result=await pets.claim_run(db,**args)
            assert (await pets.claim_run(db,**args))['idempotent_replay']
            try:await pets.claim_run(db,**{**args,'action_id':f'other-claim-{i}'})
            except pets.PetV2Conflict:pass
            else:raise AssertionError('a new key must not reclaim a finished job')
            receipts=await conn.fetch('SELECT metric FROM quest_v1_metric_receipts WHERE user_id=$1 AND event_id=$2 ORDER BY metric',owner,rid)
            assert {r['metric'] for r in receipts}=={'pet_activity_completed',f'pet_{kind}_completed'}
            assert await conn.fetchval('SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=$1 AND source_event_id=$2',owner,rid)==1
            daily=await repo.list_assignments(db,user_id=owner,period='daily',period_key=keys['daily'])
            assert daily[0]['quest_id']=={'trek':'pet_trek_1','expedition':'pet_expedition_1','watch':'pet_watch_1'}[kind]
            assert daily[0]['completed_at'] is not None and int(daily[0]['progress'])==1
        weekly=await repo.list_assignments(db,user_id=owner,period='weekly',period_key=keys['weekly'])
        assert weekly[0]['quest_id']=='pet_activity_2' and int(weekly[0]['progress'])==2
        assert not await conn.fetchval('SELECT COUNT(*) FROM quest_v1_reward_receipts WHERE user_id=$1',owner)

        # A new catalog must not reshuffle an already-issued, available set.
        stable=await quests.overview(db,user_id=owner,vip_active=False,sources=await quests.available_sources(db,user_id=owner))
        again=await quests.overview(db,user_id=owner,vip_active=False,sources=await quests.available_sources(db,user_id=owner))
        assert stable['weekly']['quests']==again['weekly']['quests'] and len(stable['daily']['quests'])==4

        # A Sunday claim must not split generic and typed metrics into Monday.
        sunday=datetime(2026,10,18,23,59,59,tzinfo=timezone.utc)
        frozen=quests.period_keys(sunday)
        await seed_assignments(db,other,frozen,daily='pet_activity_1',weekly='pet_treks_3')
        original_keys=quests.period_keys
        event={'id':'boundary-claim','kind':'trek','hours':3,'pet_id':pids[0]}
        with patch.object(quests,'period_keys',side_effect=lambda now=None:original_keys(now or sunday+timedelta(seconds=2))):
            await pets._record_progress_inner(db,other,event,occurred_at=sunday)
        daily=await repo.list_assignments(db,user_id=other,period='daily',period_key=frozen['daily'])
        weekly=await repo.list_assignments(db,user_id=other,period='weekly',period_key=frozen['weekly'])
        assert int(daily[0]['progress'])==1 and int(weekly[0]['progress'])==1
        assert not await conn.fetchval("SELECT COUNT(*) FROM quest_v1_assignments WHERE user_id=$1 AND period_key='2026-10-19'",other)

        # A second metric failure rolls back the entire secondary block while
        # keeping the terminal pet reward and its receipt safely committed.
        started=await pets.start_run(db,user_id=owner,pet_id=pids[4],kind='trek',hours=3,route='forest',action_id='error-start')
        rid=started['run_id'];await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE id=?",(rid,))
        original=quests.record_metric
        async def fail_second(db,**kwargs):
            if kwargs['metric']=='pet_trek_completed':raise RuntimeError('simulated secondary failure')
            return await original(db,**kwargs)
        with patch.object(quests,'record_metric',side_effect=fail_second):
            result=await pets.claim_run(db,user_id=owner,run_id=rid,action_id='error-claim',rng=random.Random(2))
        assert result['xp_credited']>=0
        assert await conn.fetchval('SELECT status FROM pet_v2_runs WHERE id=$1',rid)=='claimed'
        assert not await conn.fetchval('SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=$1 AND event_id=$2',owner,rid)
        assert (await pets.claim_run(db,user_id=owner,run_id=rid,action_id='error-claim'))['idempotent_replay']
        print('OK: real pet claims, type isolation, old assignments, replay, UTC boundary and secondary rollback')
    finally:
        await tx.rollback();await conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dsn',required=True);args=parser.parse_args()
    if urlparse(args.dsn).hostname not in {'localhost','127.0.0.1','::1'}:raise SystemExit('loopback only')
    asyncio.run(run(args.dsn))
