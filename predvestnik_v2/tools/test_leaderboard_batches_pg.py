"""Real PG batch-reference races/collisions and season ranking equivalence."""
import argparse,asyncio,secrets,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import asyncpg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import public_profiles_v1 as profiles, minesweeper_v2 as mines
from tools.test_pets_v2_pg import local_dsn


async def run(dsn):
    c=await asyncpg.connect(dsn);db=PGAdapter(c)
    await mines.ensure_tables(db)
    ids=list(range(99774001,99774021));extra=99774099
    try:
        # A private disposable schema proves two first requests can install the
        # reference table safely, without touching the application's table.
        schema='leaderboard_batch_probe_'+uuid4().hex
        await c.execute(f'CREATE SCHEMA {schema}')
        try:
            async def cold():
                conn=await asyncpg.connect(dsn)
                try:
                    await conn.execute(f'SET search_path TO {schema}')
                    return await profiles.ensure_references(PGAdapter(conn),ids)
                finally:await conn.close()
            cold_a,cold_b=await asyncio.gather(cold(),cold())
            assert cold_a==cold_b
        finally:await c.execute(f'DROP SCHEMA {schema} CASCADE')
        async def allocate(order):
            conn=await asyncpg.connect(dsn)
            try:return await profiles.ensure_references(PGAdapter(conn),order)
            finally:await conn.close()
        a,b=await asyncio.gather(allocate(ids),allocate(list(reversed(ids))))
        assert a==b and len(set(a.values()))==20
        invalid=['x','я'*24,'A'*15,'A'*65,'/'*24,'_'*24]
        resolved=await profiles.resolve_references(db,[*a.values(),*invalid])
        assert resolved=={v:k for k,v in a.items()}
        token=secrets.token_urlsafe;attempts=[]
        def collide(n):
            attempts.append(n);return a[ids[0]] if len(attempts)==1 else token(n)
        with patch.object(profiles.secrets,'token_urlsafe',side_effect=collide):
            created=await profiles.ensure_references(db,[extra])
        assert len(attempts)==2 and created[extra] not in a.values()
        assert await profiles.ensure_references(db,[])=={}
        tx=c.transaction();await tx.start()
        try:
            start=datetime(2099,1,1);end=start+timedelta(days=1);finished=start+timedelta(hours=1)
            await c.execute("""INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,elapsed_ms,finished_at)
                SELECT 'batch-rank-'||g,99773000+g,'normal','minesweeper-v2',decode(repeat('00',32),'hex'),'won',2,
                CASE WHEN g<=2 THEN 1000 ELSE 1000+g END,$1 FROM generate_series(1,25) g""",finished.replace(tzinfo=timezone.utc))
            await c.execute("""INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,elapsed_ms,finished_at)
                VALUES ('batch-zero',99773001,'normal','minesweeper-v1',decode(repeat('00',32),'hex'),'won',1,0,$1),
                ('batch-end',99773025,'normal','minesweeper-v2',decode(repeat('00',32),'hex'),'won',2,1,$2)""",finished.replace(tzinfo=timezone.utc),end.replace(tzinfo=timezone.utc))
            board=await mines.leaderboard(db,user_id=99773025,difficulty='normal',starts_at=start,ends_at=end)
            assert len(board['top'])==20 and board['personal']['place']==25, (len(board['top']),board['personal'])
            assert [r['place'] for r in board['top'][:3]]==[1,1,3]
            assert board['personal']['best_elapsed_ms']==1025
            assert all('user_id' not in row and 'user_id' not in row['player'] for row in board['top'])
            best=await mines.season_standings(db,difficulty='normal',starts_at=start,ends_at=end)
            assert best[-1]['place']==board['personal']['place'] and best[-1]['best_elapsed_ms']==board['personal']['best_elapsed_ms']
        finally:await tx.rollback()
        print('PASS: bulk refs race/collision/validation, tied ranks, personal beyond top20, unranked zero and exclusive season end')
    finally:
        await c.execute('DELETE FROM public_profile_v1_refs WHERE user_id=ANY($1::bigint[])',ids+[extra]);await c.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',type=local_dsn,required=True)
    asyncio.run(run(p.parse_args().dsn))
