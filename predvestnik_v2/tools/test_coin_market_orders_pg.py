"""Conditional order PG proof, using the disposable exchange regression schema."""
import asyncio,os,sys
from pathlib import Path
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services import coin_market_v2 as s
from infrastructure.repositories import coin_market_v2 as repo,coin_market_orders as orders,system_flags
from core.coin_market_v2 import MORA,MarketError
from core.economy_contract import IdempotencyConflict

async def rejects(error,coro):
    try:await coro
    except error:return
    raise AssertionError('Expected '+error.__name__)

async def proof(db,c,connect):
    await system_flags.set_flag(db,'coin_market_v2',True)
    await c.execute("INSERT INTO vip_subscriptions(user_id,expires_at) SELECT generate_series(1,19),NOW()+INTERVAL '1 day' ON CONFLICT(user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at")
    cid=(await repo.maintenance_coin_ids(db))[0]
    await s.advance(db,cid)
    row=await repo.load(db,cid);coin,book,state,_=s.checked(row)
    base=state.tick
    direction='below' if state.price>coin.floor+20 else 'above'
    sign=-1 if direction=='below' else 1
    threshold=state.price+sign
    def tick(coin,old,**kw):return replace(old,tick=old.tick+1,price=old.price+sign*5)
    async def place(uid,aid,side='buy',units=0):
        return await s.place_order(db,uid,cid,side,direction,threshold,
            amount=10*MORA if side=='buy' else 0,units=units,action_id=aid)
    with patch.object(repo,'current_tick',AsyncMock(return_value=base)):
        await rejects(MarketError,place(20,'orders_non_vip'))
        await rejects(MarketError,s.place_order(db,18,cid,'buy',direction,threshold,amount=MORA,action_id='orders_below_min'))
        await rejects(MarketError,s.place_order(db,18,cid,'sell',direction,threshold,amount=MORA,units=1,action_id='orders_bad_sell'))
        before=await repo.balances(db,18)
        made=await place(18,'orders_same_key')
        assert (await place(18,'orders_same_key'))['replayed']
        assert await repo.balances(db,18)==before,'placement does not debit or reserve'
        await rejects(IdempotencyConflict,s.place_order(db,18,cid,'buy',direction,threshold,amount=11*MORA,action_id='orders_same_key'))
        await rejects(MarketError,s.place_order(db,18,cid,'buy',direction,state.price,amount=10*MORA,action_id='orders_already_met'))
        # Cancellation is owner-only and idempotent even without VIP or entry flag.
        await rejects(MarketError,s.cancel_order(db,19,made['order_id']))
        cancel=await place(19,'orders_cancel_key')
        await system_flags.set_flag(db,'coin_market_v2',False)
        assert (await s.cancel_order(db,19,cancel['order_id']))['status']=='cancelled'
        assert (await s.cancel_order(db,19,cancel['order_id']))['status']=='cancelled'
        await system_flags.set_flag(db,'coin_market_v2',True)
        failed=await place(17,'orders_no_money')
        await c.execute('UPDATE users SET user_balance_mora=0 WHERE user_tg_id=17')
        expiredvip=await place(16,'orders_expired_vip')
        await c.execute("UPDATE vip_subscriptions SET expires_at=NOW()-INTERVAL '1 second' WHERE user_id=16")
        for n in range(10):await place(15,'orders_limit_'+str(n))
        await rejects(MarketError,place(15,'orders_limit_over'))
        # Receipt insertion failure rolls back order creation.
        from unittest.mock import patch as patched
        count=await orders.active_count(db,14)
        with patched.object(repo,'receipt',AsyncMock(side_effect=RuntimeError('receipt fail'))):
            await rejects(RuntimeError,place(14,'orders_atomic_key'))
        assert await orders.active_count(db,14)==count
    # Two server workers race the same tick: exactly one execution per order.
    async def worker():
        conn,adapter=await connect()
        try:return await s.advance(adapter,cid,target_tick=base+1)
        finally:await conn.close()
    with patch.object(s.rules,'next_price',tick):
        await asyncio.wait_for(asyncio.gather(worker(),worker()),15)
    filled=await orders.get(db,made['order_id'],18)
    assert filled['status']=='filled'
    result=repo.decode(filled['result'])
    assert s.money(result['price'])==state.price+sign*5 and s.money(result['price'])!=threshold
    assert (await orders.get(db,failed['order_id'],17))['status']=='failed'
    assert (await orders.get(db,expiredvip['order_id'],16))['status']=='failed'
    assert await c.fetchval("SELECT COUNT(*) FROM coin_market_v2_receipts WHERE action_id=$1",'order-fill:'+made['order_id'])==1
    assert (await s.cancel_order(db,18,made['order_id']))['status']=='filled'
    held,_=await repo.account(db,cid,18)
    assert held>0
    row=await repo.load(db,cid);_,_,state,_=s.checked(row);base=state.tick;threshold=state.price+sign
    with patch.object(repo,'current_tick',AsyncMock(return_value=base)):
        sell=await place(18,'orders_sell_key','sell',held)
        stale=await place(18,'orders_sell_again','sell',held)
        timeout=await place(14,'orders_expiry_key')
        await c.execute('UPDATE coin_market_v2_orders SET expires_tick=$2 WHERE id=$1',timeout['order_id'],base+1)
    with patch.object(s.rules,'next_price',tick):await s.advance(db,cid,target_tick=base+1)
    assert (await orders.get(db,sell['order_id'],18))['status']=='filled'
    assert (await orders.get(db,stale['order_id'],18))['status']=='failed'
    assert (await orders.get(db,timeout['order_id'],14))['status']=='expired'
    assert (await repo.account(db,cid,18))[0]==0
    row=await repo.load(db,cid);_,book,_,_=s.checked(row);await repo.reconcile(db,row,book)
    # No-op quote/advance must not lock the entire order participant set.
    row=await repo.load(db,cid)
    same_tick=int(repo.decode(row['price_state'])['tick'])
    with patch.object(orders,'lock_participants',AsyncMock(side_effect=AssertionError('noop lock'))):
        await s.advance(db,cid,target_tick=same_tick)
    # Feature switch pauses already-created automation without deleting it.
    base+=1;threshold=int(repo.decode(row['price_state'])['price'])+sign
    with patch.object(repo,'current_tick',AsyncMock(return_value=base)):
        paused=await place(13,'orders_paused_key')
    await system_flags.set_flag(db,'coin_market_v2',False)
    with patch.object(s.rules,'next_price',tick):await s.advance(db,cid,target_tick=base+1)
    assert (await orders.get(db,paused['order_id'],13))['status']=='pending'
    assert (await s.availability(db,13))['visible']
    assert any(o['id']==paused['order_id'] for o in (await s.market(db,13))['orders'])
    await system_flags.set_flag(db,'coin_market_v2',True)
    with patch.object(s.rules,'next_price',tick):await s.advance(db,cid,target_tick=base+2)
    assert (await orders.get(db,paused['order_id'],13))['status']=='filled'
    # Savepoint failure during automatic execution: no partial money, account or tick.
    row=await repo.load(db,cid);_,_,state,_=s.checked(row);base=state.tick;threshold=state.price+sign
    with patch.object(repo,'current_tick',AsyncMock(return_value=base)):
        atomic=await place(12,'orders_fill_atomic')
        raced=await place(11,'orders_cancel_race')
    wallet_before=await repo.balances(db,12);account_before=await repo.account(db,cid,12)
    with patch.object(s.rules,'next_price',tick),patch.object(repo,'receipt',AsyncMock(side_effect=RuntimeError('fill receipt fail'))):
        await rejects(RuntimeError,s.advance(db,cid,target_tick=base+1))
    assert await repo.balances(db,12)==wallet_before and await repo.account(db,cid,12)==account_before
    assert (await orders.get(db,atomic['order_id'],12))['status']=='pending'
    assert int(repo.decode((await repo.load(db,cid))['price_state'])['tick'])==base
    async def cancel_worker():
        conn,adapter=await connect()
        try:return await s.cancel_order(adapter,11,raced['order_id'])
        finally:await conn.close()
    with patch.object(s.rules,'next_price',tick):
        await asyncio.wait_for(asyncio.gather(worker(),cancel_worker()),15)
    assert (await orders.get(db,atomic['order_id'],12))['status']=='filled'
    terminal=(await orders.get(db,raced['order_id'],11))['status']
    assert terminal in ('filled','cancelled')
    count=await c.fetchval('SELECT COUNT(*) FROM coin_market_v2_receipts WHERE action_id=$1','order-fill:'+raced['order_id'])
    assert count==(1 if terminal=='filled' else 0)
    # Two coins with overlapping users and opposite creation order cannot deadlock.
    othercid=(await repo.maintenance_coin_ids(db))[1]
    pair=[]
    await c.execute('UPDATE users SET deleted_at=NULL WHERE user_tg_id IN(9,10)')
    for key,uids in [(cid,[9,10]),(othercid,[10,9])]:
        r=await repo.load(db,key);cc,_,st,_=s.checked(r)
        direct='below' if st.price>cc.floor+20 else 'above';sgn=-1 if direct=='below' else 1
        with patch.object(repo,'current_tick',AsyncMock(return_value=st.tick)):
            for uid in uids:
                await s.place_order(db,uid,key,'buy',direct,st.price+sgn,amount=10*MORA,action_id='cross_order_'+key+'_'+str(uid))
        pair.append((key,st.tick+1,sgn))
    def step(cc,old,**kw):
        sgn=next(sgn for key,_,sgn in pair if cc.key==key)
        return replace(old,tick=old.tick+1,price=old.price+sgn*5)
    async def advance_worker(key,target):
        conn,adapter=await connect()
        try:await s.advance(adapter,key,target_tick=target)
        finally:await conn.close()
    with patch.object(s.rules,'next_price',step):
        await asyncio.wait_for(asyncio.gather(*(advance_worker(key,target) for key,target,_ in pair)),15)
    for uid in [9,10]:
        assert all(o['status']=='filled' for o in await orders.listing(db,uid))
    print('PASS VIP orders: creation/replay/conflict, no reserve, max10, owner cancel, two-worker fill once, actual price, failed funds/VIP/holdings, expiry and flag pause')

if __name__=='__main__':
    import tools.test_coin_market_v2_pg as baseline
    baseline.DSN=os.environ['DATABASE_URL']
    baseline.Decimal=Decimal
    if ':55856/' not in baseline.DSN:raise SystemExit('Use isolated 55856 test cluster')
    asyncio.run(baseline.run())
