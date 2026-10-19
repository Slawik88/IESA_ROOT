"""Conditional order persistence; caller owns coin/user locks and transaction."""
import json

async def ensure_tables(db):
    await db.connection.execute("""
    CREATE TABLE IF NOT EXISTS coin_market_v2_orders(
      id TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_tg_id),
      coin_id TEXT NOT NULL REFERENCES coin_market_v2_coins(id),
      side TEXT NOT NULL CHECK(side IN ('buy','sell')),
      direction TEXT NOT NULL CHECK(direction IN ('below','above')),
      threshold NUMERIC(30,0) NOT NULL CHECK(threshold>0),
      amount NUMERIC(30,0) NOT NULL CHECK(amount>=0),units BIGINT NOT NULL CHECK(units>=0),
      created_tick BIGINT NOT NULL,expires_tick BIGINT NOT NULL CHECK(expires_tick>created_tick),
      status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','filled','cancelled','failed','expired')),
      result JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
      CHECK((side='buy' AND amount>0 AND units=0) OR (side='sell' AND amount=0 AND units>0))
    );
    CREATE INDEX IF NOT EXISTS cm2_orders_pending_coin ON coin_market_v2_orders(coin_id,created_at,id) WHERE status='pending';
    CREATE INDEX IF NOT EXISTS cm2_orders_user ON coin_market_v2_orders(user_id,created_at DESC);
    """)

async def insert(db, oid, uid, cid, side, direction, threshold, amount, units, tick, expires):
    await db.connection.execute("INSERT INTO coin_market_v2_orders(id,user_id,coin_id,side,direction,threshold,amount,units,created_tick,expires_tick) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",oid,uid,cid,side,direction,threshold,amount,units,tick,expires)

async def active_count(db, uid):
    return await db.connection.fetchval("SELECT COUNT(*) FROM coin_market_v2_orders WHERE user_id=$1 AND status='pending'",uid)

async def get(db, oid, uid):
    row=await db.connection.fetchrow('SELECT * FROM coin_market_v2_orders WHERE id=$1 AND user_id=$2',oid,uid)
    return dict(row) if row else None

async def listing(db, uid):
    return [dict(r) for r in await db.connection.fetch("SELECT * FROM coin_market_v2_orders WHERE user_id=$1 ORDER BY (status='pending') DESC,created_at DESC,id LIMIT 50",uid)]

async def candidates(db, cid, tick, price):
    return [dict(r) for r in await db.connection.fetch("""SELECT * FROM coin_market_v2_orders WHERE coin_id=$1 AND status='pending' AND created_tick<$2
      AND (expires_tick<=$2 OR (direction='below' AND threshold>=$3) OR (direction='above' AND threshold<=$3))
      ORDER BY created_at,id""",cid,tick,price)]

async def finish(db, oid, status, result):
    await db.connection.execute("UPDATE coin_market_v2_orders SET status=$2,result=$3::jsonb WHERE id=$1 AND status='pending'",oid,status,json.dumps(result,ensure_ascii=False))


async def lock_participants(db, cid):
    # One coin may settle orders for many users. Acquire their advisory locks in
    # a global order before any per-user write, including automatic shorts.
    rows=await db.connection.fetch("""SELECT user_id FROM coin_market_v2_orders WHERE coin_id=$1 AND status='pending'
      UNION SELECT user_id FROM coin_market_v2_shorts WHERE coin_id=$1 AND closed_tick IS NULL ORDER BY user_id""",cid)
    for r in rows:
        await db.connection.execute('SELECT pg_advisory_xact_lock($1::bigint)',int(r['user_id']))
