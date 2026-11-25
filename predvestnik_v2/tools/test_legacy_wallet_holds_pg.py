"""Loopback PostgreSQL proof of lossless legacy wallet hold retirement."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.retire_legacy_wallet_holds import retire
from infrastructure.pg_adapter import PGAdapter
from services import auction

DSN='postgresql://predvestnik_preprod@127.0.0.1:55438/predvestnik_preprod'
SCHEMA='hold_retirement_test_'+uuid4().hex[:12]

async def rejects(kind, coro):
    try: await coro
    except kind: return
    raise AssertionError(f'Expected {kind}')

async def connect():
    c=await asyncpg.connect(DSN)
    await c.execute(f'SET search_path TO "{SCHEMA}"')
    return c

async def main():
    c=await asyncpg.connect(DSN)
    try:
        await c.execute(f'CREATE SCHEMA "{SCHEMA}"; SET search_path TO "{SCHEMA}"')
        await c.execute('''
        CREATE TABLE users(user_tg_id BIGINT PRIMARY KEY,user_balance_mora NUMERIC(24,6),user_balance_zarniki NUMERIC(24,6),user_balance_diamonds NUMERIC(24,6),user_balance_dark_mora NUMERIC(24,6));
        INSERT INTO users VALUES(21,1094.000013,100,2,3),(22,189,50,1,4);
        CREATE TABLE user_reserve(user_id BIGINT PRIMARY KEY,reserved_mora NUMERIC(24,6));
        INSERT INTO user_reserve VALUES(21,200),(22,25);
        CREATE TABLE duels(id BIGINT PRIMARY KEY,challenger_id BIGINT,challenged_id BIGINT,status TEXT,stake NUMERIC,winner_id BIGINT,resolved_at TIMESTAMP,winner_gain NUMERIC,commission NUMERIC);
        INSERT INTO duels VALUES(3,21,22,'processing',200,NULL,NULL,NULL,NULL);
        CREATE TABLE auction_lots(id BIGINT PRIMARY KEY,seller_id BIGINT,status TEXT,item_type TEXT,item_id_or_pet_id BIGINT,quantity INT,item_name TEXT);
        INSERT INTO auction_lots VALUES(1,22,'active','inventory',0,2,'Potion||potion'),(2,21,'active','pet',9,1,'Companion');
        CREATE TABLE auction_bids(id BIGINT PRIMARY KEY,lot_id BIGINT,bidder_id BIGINT,amount NUMERIC,is_active INT);
        INSERT INTO auction_bids VALUES(1,1,21,25,1),(2,2,22,25,1);
        CREATE TABLE inventory(user_id BIGINT,item_id TEXT,quantity INT,PRIMARY KEY(user_id,item_id));
        INSERT INTO inventory VALUES(22,'potion',1);
        CREATE TABLE pets(id BIGINT PRIMARY KEY,owner_id BIGINT,placement TEXT);
        INSERT INTO pets VALUES(9,21,'auction');
        CREATE TABLE admin_grant_log(id SERIAL PRIMARY KEY,admin_id BIGINT,target_id BIGINT,action TEXT,detail TEXT,amount DOUBLE PRECISION,reason TEXT,before_val DOUBLE PRECISION,after_val DOUBLE PRECISION);
        CREATE TABLE economic_operations(id TEXT,user_id BIGINT,reason_code TEXT,reference_type TEXT,reference_id TEXT);
        CREATE TABLE wallet_log(id BIGINT,user_id BIGINT,source TEXT,note TEXT);
        CREATE TABLE coin_market_v2_shorts(id TEXT,collateral BIGINT);
        INSERT INTO coin_market_v2_shorts VALUES('protected',50000000);
        CREATE TABLE player_coin_orders_v1(id TEXT,reserved_mora NUMERIC);
        INSERT INTO player_coin_orders_v1 VALUES('unrelated-debited-escrow',100);
        ''')
        first=await retire(c)
        assert first['reserve_released']=='225.000000' and not first['applied']
        assert await c.fetchval('SELECT quantity FROM inventory')==1
        await rejects(RuntimeError,retire(c,apply=True,expected_digest='wrong'))
        for invalid in (None, -1):
            await c.execute('UPDATE user_reserve SET reserved_mora=$1 WHERE user_id=21', invalid)
            assert (await retire(c))['blocked_reason']
            await rejects(RuntimeError,retire(c,apply=True,expected_digest=first['digest']))
        await c.execute('UPDATE user_reserve SET reserved_mora=200 WHERE user_id=21')
        await c.execute('UPDATE pets SET owner_id=22')
        assert (await retire(c))['blocked_reason']
        await rejects(RuntimeError,retire(c,apply=True,expected_digest=first['digest']))
        await c.execute('UPDATE pets SET owner_id=21')
        await c.execute('UPDATE duels SET winner_gain=30')
        assert (await retire(c))['blocked_reason']
        await rejects(RuntimeError,retire(c,apply=True,expected_digest=first['digest']))
        await c.execute('UPDATE duels SET winner_gain=NULL')
        await c.execute("INSERT INTO wallet_log VALUES(1,21,'auction_buy','lot=1')")
        assert (await retire(c))['blocked_reason']
        await rejects(RuntimeError,retire(c,apply=True,expected_digest=first['digest']))
        assert not (await auction.cancel_lot(PGAdapter(c),1,22))[0]
        assert not await auction.resolve_lot(PGAdapter(c),1)
        assert await c.fetchval('SELECT quantity FROM inventory')==1
        assert await c.fetchval('SELECT sum(reserved_mora) FROM user_reserve')==225
        await c.execute('DELETE FROM wallet_log')
        with patch('tools.retire_legacy_wallet_holds.admin_log.add',side_effect=RuntimeError('audit down')):
            await rejects(RuntimeError,retire(c,apply=True,expected_digest=first['digest']))
        assert await c.fetchval('SELECT quantity FROM inventory')==1
        assert await c.fetchval("SELECT placement FROM pets")=='auction'
        assert await c.fetchval('SELECT sum(reserved_mora) FROM user_reserve')==225
        assert await c.fetchval("SELECT status FROM duels")=='processing'
        async def attempt():
            other=await connect()
            try:return await retire(other,apply=True,expected_digest=first['digest'])
            finally:await other.close()
        results=await asyncio.gather(attempt(),attempt())
        assert sum(r['applied'] for r in results)==1 and sum(r['replayed'] for r in results)==1
        applied = next(r for r in results if r['applied'])
        assert applied['global_wallet_totals_before'] == applied['global_wallet_totals_after']
        assert applied['global_wallet_totals_before']['users']==2
        assert str(applied['global_wallet_totals_before']['mora'])=='1283.000013'

        assert await c.fetchval('SELECT quantity FROM inventory')==3
        assert await c.fetchval("SELECT placement FROM pets")=='storage'
        assert await c.fetchval('SELECT sum(reserved_mora) FROM user_reserve')==0
        assert await c.fetchval("SELECT status FROM duels")=='declined'
        assert await c.fetchval('SELECT count(*) FROM auction_bids WHERE is_active=1')==0
        assert str(await c.fetchval('SELECT user_balance_mora FROM users WHERE user_tg_id=21'))=='1094.000013'
        assert await c.fetchval('SELECT collateral FROM coin_market_v2_shorts')==50000000
        assert await c.fetchval('SELECT reserved_mora FROM player_coin_orders_v1')==100
        assert await c.fetchval('SELECT count(*) FROM admin_grant_log')==1
        await rejects(asyncpg.CheckViolationError,c.execute('UPDATE user_reserve SET reserved_mora=1'))
        await rejects(RuntimeError,auction.add_reserve(PGAdapter(c),21,1))
        assert not (await auction.place_bid(PGAdapter(c),1,21,50))['ok']
        assert not (await auction.create_auction_lot(PGAdapter(c),21,'item','inventory',1,1,'x',10,None))[0]
        assert (await retire(c,apply=True,expected_digest='unused-on-replay'))['replayed']
        print('PASS: dry-run, stale digest, ambiguous escrow, partial settlement refusal, full rollback, parallel replay, once-only asset return, no wallet credits, DB hold prohibition, v1/v2 escrow unchanged')
    finally:
        await c.execute(f'DROP SCHEMA "{SCHEMA}" CASCADE')
        await c.close()

asyncio.run(main())
