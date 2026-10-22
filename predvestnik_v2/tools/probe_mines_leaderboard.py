"""Loopback-only SQL round-trip and lock probe. Fixtures always roll back."""
import argparse,asyncio,json,sys,time
from pathlib import Path
import asyncpg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter, _pg_sql, _coerce_args
from infrastructure.repositories import minesweeper_v2 as repo, game_seasons, public_profiles_v1 as profiles
from services import minesweeper_v2 as service
from tools.test_pets_v2_pg import local_dsn


class Trace:
    def __init__(self,db):self.db=db;self.sql=[];self.connection=db.connection
    def execute(self,sql,args=()):self.sql.append(sql);return self.db.execute(sql,args)
    async def commit(self):return await self.db.commit()


async def run(dsn,rows=20,check=False):
    conn=await asyncpg.connect(dsn);db=PGAdapter(conn)
    await repo.ensure_tables(db);await game_seasons.ensure_tables(db)
    tx=conn.transaction();await tx.start()
    try:
        await conn.execute("""INSERT INTO minesweeper_v2_runs(run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,elapsed_ms,finished_at)
            SELECT 'latency-probe-'||g,99772001+(g-1)%2000,'normal','minesweeper-v2',decode(repeat('01',32),'hex'),
            CASE WHEN g<=20 OR g%20=0 THEN 'won' ELSE 'lost' END,2,1000+g,NOW() FROM generate_series(1,$1::int) g""",rows)
        await profiles.ensure_references(db,range(99772001,99772021))
        trace=Trace(db);at=time.perf_counter()
        board=await service.rankings(trace,user_id=99772001,difficulty='normal')
        ms=(time.perf_counter()-at)*1000
        result={'rows':len(board['top']),'sql_round_trips':len(trace.sql),'ddl_round_trips':sum(s.lstrip().upper().startswith(('CREATE','ALTER')) for s in trace.sql),
                'loopback_ms':round(ms,2),'latency_budget_at_100ms_rtt':round(len(trace.sql)*.1,2),'fixture_runs':rows}
        if rows>20:
            from services import game_seasons as seasons
            start,end=service.season_rules.season_bounds(seasons.season_view()['number'])
            plan=await conn.fetchval(_pg_sql('EXPLAIN (ANALYZE,FORMAT JSON) '+repo._SEASON_BEST+'SELECT * FROM ranked ORDER BY place,user_id LIMIT 20'),*_coerce_args(['normal',start,end]))
            if isinstance(plan,str):plan=json.loads(plan)
            result['ranking_explain']=plan
    finally:await tx.rollback()
    lock=await asyncpg.connect(dsn);hold=lock.transaction();await hold.start()
    try:
        await lock.execute('LOCK TABLE minesweeper_v2_runs IN ROW EXCLUSIVE MODE')
        await conn.execute("SET lock_timeout='200ms'")
        try:await repo.ensure_tables(db);result['schema_blocked_by_writer']=False
        except asyncpg.LockNotAvailableError:result['schema_blocked_by_writer']=True
    finally:
        await hold.rollback();await lock.close();await conn.close()
    print(json.dumps(result,indent=2))
    if check:
        assert result['rows']==20 and result['sql_round_trips']<=17 and result['ddl_round_trips']==0 and not result['schema_blocked_by_writer']


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',type=local_dsn,required=True);p.add_argument('--rows',type=int,choices=range(20,300001),default=20);p.add_argument('--check',action='store_true')
    args=p.parse_args();asyncio.run(run(args.dsn,args.rows,args.check))
