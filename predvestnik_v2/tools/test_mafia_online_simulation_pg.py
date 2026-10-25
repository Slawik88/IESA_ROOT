"""Seeded complete games for every supported size: real services/SQL, role privacy and departures."""
import argparse
import asyncio
import os
import random
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault('BOT_TOKEN','1:x')
os.environ.setdefault('DATABASE_URL','postgresql://unused/unused')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import asyncpg
from core import mafia_online as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game
from tools.test_mafia_online_pg import expire


async def check(db):
    rng=random.Random(20261023)
    moves=phases=departures=pauses=0
    for index,(size,auto) in enumerate((n,a) for n in range(4,21) for a in (True,False)):
        first=10000+index*100
        roles=[r for r in ('doctor','detective','don') if (r!='don' or size>=8) and rng.random()<.7]
        room=await game.create(db,{'id':first,'first_name':'Одинаковое имя'},seats=size,
            tempo=('fast','normal','slow')[index%3],roles_auto=auto,roles=roles,
            vote_mode='open' if index%2 else 'secret')
        for uid in range(first+1,first+size):
            await game.join(db,room,{'id':uid,'first_name':'Одинаковое имя'})
        previous_number=0
        for turn in range(95):
            state=await repo.load(db,room)
            if state['phase'] in rules.TERMINAL:break
            phases+=1
            assert state['phase_number']>=previous_number
            previous_number=state['phase_number']
            assert rules.player(state,state['host']) is not None
            assert len({p['seat'] for p in state['players']})==size
            if rng.random()<.16:
                await game.control(db,room,state['host'],'pause')
                paused=await repo.load(db,room)
                assert paused['phase']=='paused'
                await game.control(db,room,state['host'],'resume')
                pauses+=1
            if len([p for p in state['players'] if p['alive']])>4 and rng.random()<.22:
                departing=rng.choice([p for p in state['players'] if p['alive'] and not p.get('left')])
                await game.control(db,room,departing['id'],'leave')
                assert await repo.current(db,departing['id']) is None
                departures+=1
                state=await repo.load(db,room)
                if state['phase'] in rules.TERMINAL:break
            for p in state['players']:
                view=await game.get(db,room,p['id'])
                assert all('role' not in x for x in view['players']), 'no unrevealed identities in any player projection'
                assert view['me']['role']==p['role']
                if p['role'] not in ('mafia','don') or not p['alive'] or state['phase']!='night':
                    assert 'team_choices' not in view['me']
                if state['vote_mode']=='secret':assert view['votes']=={}
                if not p['alive'] or p.get('left'):continue
                kind='vote' if state['phase']=='voting' else rules.night_action_for(p['role']) if state['phase']=='night' else None
                if not kind or rng.random()<.1:continue
                choices=[x['id'] for x in state['players'] if x['alive']
                    and (kind=='doctor_save' or x['id']!=p['id'])
                    and (kind!='mafia_target' or x['role'] not in ('mafia','don'))]
                if kind=='vote':choices.append(None)
                if choices:
                    await game.action(db,room,p['id'],state['phase_number'],kind,rng.choice(choices));moves+=1
            await expire(db,room)
        else:raise AssertionError(f'game stalled: size={size} auto={auto}')
        result=await repo.load(db,room)
        assert result['phase']=='finished' and result['winner'] in ('town','mafia','draw')
        for p in result['players']:
            assert await repo.current(db,p['id']) is None
            assert all('role' in x for x in (await game.get(db,room,p['id']))['players'])
        assert not await db.connection.fetchval("SELECT to_regclass('mafia_v1_matches')")
    print(f'PASS 34 complete PG games, sizes4..20, auto/manual roles, three tempos, open/secret votes: {phases} phases, {moves} moves, {departures} departures, {pauses} pauses; no role leaks or held seats')


async def main(dsn):
    c=await asyncpg.connect(dsn);schema='mafia_sim_'+uuid.uuid4().hex[:12]
    await c.execute(f'CREATE SCHEMA "{schema}"')
    try:
        await c.execute(f'SET search_path TO "{schema}"')
        db=PGAdapter(c);await repo.ensure_tables(db);await check(db)
    finally:
        await c.execute(f'DROP SCHEMA "{schema}" CASCADE');await c.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dsn',required=True);args=parser.parse_args()
    if urlparse(args.dsn).hostname not in ('localhost','127.0.0.1','::1'):raise SystemExit('loopback PostgreSQL required')
    asyncio.run(main(args.dsn))
