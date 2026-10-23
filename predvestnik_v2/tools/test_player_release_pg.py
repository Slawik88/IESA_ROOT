"""Rollback-only release: exact scope, atomic marker and operator pauses."""
import asyncio,os,sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch,AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN','123456:offline-preprod-tests')
async def main():
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import player_release as repo,system_flags
    from services import player_release as svc
    from core import player_release as policy
    c=await asyncpg.connect(os.environ['DATABASE_URL']);tx=c.transaction();await tx.start()
    try:
        await c.execute('SET LOCAL search_path TO predvestnik,public')
        db=PGAdapter(c);await repo.ensure_tables(db)
        before=dict(await c.fetch('SELECT key,enabled FROM system_flags'))
        rid='release-proof-'+uuid4().hex
        with patch.object(policy,'RELEASE_ID',rid):
            await svc.activate(db)
            for k in policy.FLAGS:assert await c.fetchval('SELECT enabled FROM system_flags WHERE key=$1',k)
            assert await c.fetchval('SELECT COUNT(*) FROM player_release_receipts WHERE id=$1',rid)==1
            await c.execute("UPDATE system_flags SET enabled=0 WHERE key='season_pass_v1'")
            await svc.activate(db)
            assert not await c.fetchval("SELECT enabled FROM system_flags WHERE key='season_pass_v1'")
        for key,value in before.items():
            if key not in (*policy.FLAGS,'coin_market_v2','game_mafia_online'):
                assert await c.fetchval('SELECT enabled FROM system_flags WHERE key=$1',key)==value
        # The newly approved interchat mode is activated once after its schema.
        if await c.fetchval("SELECT to_regclass('mafia_online_rooms') IS NOT NULL"):
            assert await c.fetchval("SELECT COUNT(*) FROM player_release_receipts WHERE id='owner-mafia-online-2026-10-23'") == 1
            await c.execute("UPDATE system_flags SET enabled=0 WHERE key='game_mafia_online'")
            await svc.activate(db)
            assert not await c.fetchval("SELECT enabled FROM system_flags WHERE key='game_mafia_online'")
        other='failed-'+uuid4().hex
        with patch.object(repo,'required_storage',AsyncMock(return_value=False)),patch.object(policy,'RELEASE_ID',other):
            try:await svc.activate(db)
            except RuntimeError:pass
            else:raise AssertionError('incomplete schema released')
        assert not await c.fetchval('SELECT 1 FROM player_release_receipts WHERE id=$1',other)
        # A missing flag cannot partially release the others or stamp success.
        await c.execute("UPDATE system_flags SET enabled=0 WHERE key='game_rhythm_v2'")
        try:await repo.apply_once(db,other,('game_rhythm_v2','no_such_flag'))
        except RuntimeError:pass
        else:raise AssertionError('missing flag accepted')
        assert not await c.fetchval("SELECT enabled FROM system_flags WHERE key='game_rhythm_v2'")
        assert not await c.fetchval('SELECT 1 FROM player_release_receipts WHERE id=$1',other)
        # An unlocked catalogue snapshot must never be reconciled as a book.
        from services import coin_market_v2 as market
        from infrastructure.repositories import coin_market_v2 as market_repo
        await c.execute("CREATE TEMP TABLE coin_market_v2_funding(id TEXT,mora NUMERIC,metadata JSONB) ON COMMIT DROP")
        await c.execute("INSERT INTO coin_market_v2_funding VALUES('initial-v2',120000000000,$1::jsonb)",'{"kind":"one_time_system_issuance","authorization":"project_owner:2026-10-17:explicit_120000_mora_one_time_issuance"}')
        spot_id='spot-proof-'+uuid4().hex
        async def reconcile_locked(db,row,book):
            assert db.connection.is_in_transaction() and book==100, 'stale unlocked book used'
        load=AsyncMock(return_value={'id':'orb','held':100})
        with patch.object(policy,'RELEASE_ID',spot_id),patch.object(market,'require',AsyncMock()),patch.object(market,'SYSTEM_COINS',(('orb',),)),patch.object(market_repo,'rows',AsyncMock(return_value=[{'id':'orb','held':0}])),patch.object(market_repo,'load',load),patch.object(market,'checked',side_effect=lambda row:(None,row['held'],None,None)),patch.object(market_repo,'reconcile',reconcile_locked):
            await svc.activate(db)
            load.assert_awaited_once_with(db,'orb',lock=True)
            await c.execute("UPDATE system_flags SET enabled=0 WHERE key='coin_market_v2'")
            with patch.object(market_repo,'rows',AsyncMock(side_effect=AssertionError('preflight repeated after receipt'))):
                await svc.activate(db)
            assert not await c.fetchval("SELECT enabled FROM system_flags WHERE key='coin_market_v2'")
        print('PASS release: approved scope only, ready storage, atomic flags/receipt, repeat preserves admin pause, missing flag rollback')
    finally:await tx.rollback();await c.close()
if __name__=='__main__':asyncio.run(main())
