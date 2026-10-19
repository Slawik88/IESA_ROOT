"""Real query cancellation must release the connection and preserve outer work."""
import asyncio,os,sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN','123456:offline-preprod-tests')
async def main():
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from bot.chat import activity_graph as g
    dsn=os.environ['DATABASE_URL']
    if urlparse(dsn).hostname not in ('127.0.0.1','localhost','::1') or ':55856/' not in dsn:
        raise SystemExit('Use isolated loopback 55856 test cluster')
    c=await asyncpg.connect(dsn);db=PGAdapter(c)
    entered=asyncio.Event()
    async def slow_counts(db,*args):
        entered.set()
        async with db.execute('SELECT pg_sleep(2)') as cur:await cur.fetchone()
        raise AssertionError('query should have been cancelled')
    try:
        with patch.object(g,'daily_counts',slow_counts),patch.object(g,'RENDER_BUDGET_SEC',.1):
            assert await g.get_graph(db,99130001) is None
            assert entered.is_set(), 'real query was exercised'
            assert await c.fetchval('SELECT 1')==1
            assert not c.is_in_transaction()
            async with c.transaction():
                await c.execute('CREATE TEMP TABLE graph_budget_proof(value INT) ON COMMIT DROP')
                await c.execute('INSERT INTO graph_budget_proof VALUES(7)')
                assert await g.get_graph(db,99130002) is None
                assert c.is_in_transaction() and await c.fetchval('SELECT value FROM graph_budget_proof')==7
                entered.clear()
                task=asyncio.create_task(g.get_graph(db,99130003))
                await entered.wait();task.cancel()
                try:await task
                except asyncio.CancelledError:pass
                else:raise AssertionError('caller cancellation swallowed')
                assert await c.fetchval('SELECT value FROM graph_budget_proof')==7
        assert not g._pending and not c.is_in_transaction()
        print('PASS real PostgreSQL: slow query cancelled, connection reusable, outer write preserved, caller cancellation propagated, no SQL background task')
    finally:await c.close()
if __name__=='__main__':asyncio.run(main())
