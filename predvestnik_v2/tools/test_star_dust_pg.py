"""Dust policy, real PostgreSQL atomicity/concurrency, pets and chat gates. Loopback only."""
import argparse
import asyncio
import os
import random
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import asyncpg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import star_dust as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import star_dust as repo, system_flags, vip_v2, pet_chat, pets_v2
from services import star_dust as service
from tools.test_pets_v2_pg import local_dsn


async def refused(call, text=''):
    try: await call
    except rules.DustError as e: assert text in str(e), str(e)
    else: raise AssertionError('unexpected acceptance')


async def run(dsn):
    os.environ.setdefault('BOT_TOKEN','123456:offline-tests');os.environ['DATABASE_URL']=dsn
    from bot.chat import star_dust as chat
    from bot.chat.help import _by_section
    from services import pets_v2 as pets
    from tools.test_pet_chat_pg import Call
    conn=await asyncpg.connect(dsn,server_settings={'search_path':'predvestnik,public'});db=PGAdapter(conn)
    base=9950000000+uuid4().int%1000000;uids=[base+i for i in range(20)]
    for schema in (repo,vip_v2,pet_chat,pets_v2):await schema.ensure_tables(db)
    await system_flags.ensure_table(db);await system_flags.set_flag(db,'star_dust_v1',True)
    for uid in uids:await conn.execute('INSERT INTO users(user_tg_id) VALUES($1)',uid)
    uid=uids[0]
    async def fund(user,value):
        async with conn.transaction():
            await repo.lock_user(db,user)
            await conn.execute('UPDATE star_dust_accounts SET balance=$2 WHERE user_id=$1',user,value)
    async def buy(user,days,key=None):
        return await service.buy_vip(db,user_id=user,days=days,action_id=key or uuid4().hex,expected_cost=days*100)
    async def parallel(factory):
        connections=[await asyncpg.connect(dsn,server_settings={'search_path':'predvestnik,public'}) for _ in range(2)]
        try:return await asyncio.gather(*(factory(PGAdapter(c)) for c in connections))
        finally:
            for c in connections:await c.close()
    try:
        assert rules.chat_reward(0)==0 and rules.chat_reward(1)==24
        assert all(rules.chat_reward(i/1000)<=rules.chat_reward((i+1)/1000) for i in range(1000))
        for value in (True,-1,1.01,float('nan'),float('inf')):
            try:rules.chat_reward(value)
            except rules.DustError:pass
            else:raise AssertionError(value)
        assert rules.luck_view(0,0)['stars']==0 and rules.luck_view(1,24)['stars']==5
        # Zero is still a durable daily result; no reroll on retry/other chat.
        with patch.object(service.secrets,'randbelow',return_value=0):r=await service.search(db,user_id=uid)
        assert r['amount']==0 and r['luck']['stars']==0
        with patch.object(service.secrets,'randbelow',side_effect=AssertionError('reroll')):
            assert (await service.search(db,user_id=uid))['already_claimed']
        with patch.object(service.secrets,'randbelow',return_value=rules.LUCK_STEPS):
            race=await parallel(lambda d:service.search(d,user_id=uids[1]))
        assert sorted(r['already_claimed'] for r in race)==[False,True]
        assert await repo.balance(db,uids[1])==24
        await fund(uids[2],5000)
        with patch.object(service.secrets,'randbelow',return_value=rules.LUCK_STEPS):r=await service.search(db,user_id=uids[2])
        assert (r['amount'],r['raw_amount'],r['balance'],r['luck']['stars'])==(24,24,5024,5)
        # Shared continuous source: overlaps cannot multiply elapsed sky time.
        now=(await repo.clock(db))['now'];start=now-timedelta(hours=12)
        run={'id':uuid4().hex,'user_id':uid,'pet_id':1,'kind':'watch','hours':12,'starts_at':start,'ends_at':now}
        async def grant(r):
            async with conn.transaction():return await service.grant_pet_in_transaction(db,user_id=uid,run=r)
        assert (await grant(run))['amount']==2
        assert (await grant(run))['idempotent_replay']
        active={**run,'id':uuid4().hex,'kind':'trek','hours':3,'ends_at':start+timedelta(hours=3)}
        assert (await grant(active))['amount']==5
        assert (await grant({**active,'id':uuid4().hex}))['amount']==0
        assert await repo.balance(db,uid)==7
        assert (await repo.pet_remainder(db,uid))*5==rules.UNITS_PER_DUST*4
        await refused(grant({**run,'id':uuid4().hex,'user_id':uid+1}),'Чужое')
        # Reverse collection order produces the same total and fractional carry.
        reverse=uids[9]
        async with conn.transaction():
            await service.grant_pet_in_transaction(db,user_id=reverse,run={**active,'user_id':reverse})
            await service.grant_pet_in_transaction(db,user_id=reverse,run={**run,'user_id':reverse})
        assert await repo.balance(db,reverse)==7 and await repo.pet_remainder(db,reverse)==await repo.pet_remainder(db,uid)
        before=await repo.balance(db,uid);carry=await repo.pet_remainder(db,uid)
        try:
            async with conn.transaction():
                await service.grant_pet_in_transaction(db,user_id=uid,run={**active,'id':uuid4().hex,'starts_at':start+timedelta(hours=3),'ends_at':start+timedelta(hours=6)})
                raise RuntimeError('after grant')
        except RuntimeError:pass
        assert await repo.balance(db,uid)==before and await repo.pet_remainder(db,uid)==carry
        # Exact integer microseconds; partitioning never destroys fractions.
        u=rules.UNITS_PER_DUST
        assert rules.new_coverage_units(0,u//10,10,[])==u
        assert rules.new_coverage_units(0,u//10,10,[(0,u//10,10)])==0
        assert rules.new_coverage_units(0,u//10,10,[(0,u//10,1)])==u*9//10
        overlap_owner=uids[10]
        async def parallel_grant(d):
            async with d.connection.transaction():
                return await service.grant_pet_in_transaction(d,user_id=overlap_owner,
                    run={**active,'id':uuid4().hex,'user_id':overlap_owner})
        race=await parallel(parallel_grant)
        assert sorted(r['amount'] for r in race)==[0,6]
        assert await repo.balance(db,overlap_owner)==6
        assert {c.name for c in _by_section(True)['stars']}=={'звездопад','пыль','вип за пыль'}
        # Atomic single purchase, immutable receipt and exact replay from two connections.
        uid=uids[3];await fund(uid,1400);key=uuid4().hex
        async def exchange(d):return await service.buy_vip(d,user_id=uid,days=2,expected_cost=200,action_id=key)
        race=await parallel(exchange)
        assert sorted(r['replayed'] for r in race)==[False,True]
        assert await repo.balance(db,uid)==1200
        expiry=await conn.fetchval('SELECT expires_at FROM vip_subscriptions WHERE user_id=$1',uid)
        expected_expiry=(await service._instant(db,expiry)).isoformat()
        assert all(r['expires_at']==expected_expiry for r in race), (race,expiry)
        await refused(buy(uid,1,key),'другого')
        await refused(service.buy_vip(db,user_id=uid,days=1,expected_cost=1,action_id=uuid4().hex),'Цена')
        assert await repo.balance(db,uid)==1200
        for fn in ('extend_subscription','save_vip'):
            target=service.vip_repo if fn=='extend_subscription' else repo
            with patch.object(target,fn,side_effect=RuntimeError('fault after debit')):
                try:await buy(uid,1)
                except RuntimeError:pass
                else:raise AssertionError('fault did not fire')
            assert await repo.balance(db,uid)==1200
            assert await conn.fetchval('SELECT expires_at FROM vip_subscriptions WHERE user_id=$1',uid)==expiry
        for table in ('star_dust_income','star_dust_pet_coverage','star_dust_vip_receipts'):
            try:await conn.execute(f'DELETE FROM {table} WHERE user_id=$1',uids[0] if table in ('star_dust_income','star_dust_pet_coverage') else uid)
            except asyncpg.RaiseError:pass
            else:raise AssertionError('mutable receipt')
        # No calendar, future or stock limits. Extend paid VIP and buy >14 at once.
        paid=uids[4];await fund(paid,5000)
        await vip_v2.extend_subscription(db,user_id=paid,days=30)
        paid_expiry=await conn.fetchval('SELECT expires_at FROM vip_subscriptions WHERE user_id=$1',paid)
        assert (await buy(paid,20))['days']==20
        after=await conn.fetchval('SELECT expires_at FROM vip_subscriptions WHERE user_id=$1',paid)
        assert after>paid_expiry+timedelta(days=19) and await repo.balance(db,paid)==3000
        assert (await service.overview(db,paid))['vip']['max_days']==30
        assert (await buy(paid,30))['days']==30 and await repo.balance(db,paid)==0
        await refused(buy(paid,1),'Не хватает')
        # True pet claim writes dust inside the same transaction and its durable result.
        owner=uids[6]
        pet=await conn.fetchval("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES($1,'Пруф','moss_cat','common') RETURNING id",owner)
        start=await pets.start_run(db,user_id=owner,pet_id=pet,kind='trek',hours=3,route='forest',action_id=uuid4().hex)
        run_id=start['run']['id'] if 'run' in start else start['run_id']
        await conn.execute("UPDATE pet_v2_runs SET starts_at=NOW()-make_interval(hours=>hours)-INTERVAL '1 minute',ends_at=NOW()-INTERVAL '1 minute' WHERE id=$1",run_id)
        claim_key=uuid4().hex
        with patch.object(pets_v2,'finish_run',side_effect=RuntimeError('fault after dust')):
            try:await pets.claim_run(db,user_id=owner,run_id=run_id,action_id=claim_key,rng=random.Random(7))
            except RuntimeError:pass
            else:raise AssertionError('fault not fired')
        assert await repo.balance(db,owner)==0 and not await repo.income(db,owner,'pet',run_id)
        r=await pets.claim_run(db,user_id=owner,run_id=run_id,action_id=claim_key,rng=random.Random(7))
        assert r['star_dust']['amount']==6 and await repo.balance(db,owner)==6
        assert (await pets.claim_run(db,user_id=owner,run_id=run_id,action_id=claim_key))['star_dust']['amount']==6
        assert await repo.balance(db,owner)==6
        # Real callback gates and lost post-commit delivery: stable token does not respend.
        user=uids[7];await fund(user,600);group=SimpleNamespace(id=-user,type='supergroup')
        assert await chat.available(db,user,group)
        token=await pet_chat.save(db,user,group.id,{'scope':'star_dust','do':'vip','days':1,'cost':100})
        def call(who=user,where=group):
            c=Call(who,where,token);c.data='sd:'+token;return c
        wrong=call(user+1);await chat.on_dust(wrong,db);assert not wrong.message.edits
        wrong_chat=call(where=SimpleNamespace(id=user,type='private'));await chat.on_dust(wrong_chat,db);assert not wrong_chat.message.edits
        with patch.object(chat,'render',side_effect=RuntimeError('lost delivery')),patch.object(chat.logger,'exception'):
            lost=call();await chat.on_dust(lost,db)
        assert await repo.balance(db,user)==500
        retry=call();await chat.on_dust(retry,db);assert retry.message.edits and await repo.balance(db,user)==500
        for feature in ('all','section:stars','group:star_dust','cmd:звездопад','cmd:пыль','cmd:вип за пыль'):
            await conn.execute('INSERT INTO bot_feature_switches(chat_id,feature) VALUES($1,$2)',group.id,feature)
            assert not await chat.available(db,user,group,feature[4:] if feature.startswith('cmd:') else 'пыль')
            if feature=='cmd:вип за пыль':
                blocked=call();await chat.on_dust(blocked,db);assert not blocked.message.edits
                assert await chat.available(db,user,group,'звездопад')
            await conn.execute('DELETE FROM bot_feature_switches WHERE chat_id=$1 AND feature=$2',group.id,feature)
        await conn.execute('INSERT INTO bot_user_blocks(user_id) VALUES($1)',user)
        assert not await chat.available(db,user,group)
        await conn.execute('DELETE FROM bot_user_blocks WHERE user_id=$1',user)
        await conn.execute('UPDATE users SET deleted_at=NOW() WHERE user_tg_id=$1',user)
        assert not await chat.available(db,user,group)
        await system_flags.set_flag(db,'star_dust_v1',False)
        await refused(service.search(db,user_id=uid),'недоступна')
        assert (await service.grant_pet_in_transaction(db,user_id=owner,run=run))['disabled']
        print('PASS: dust policy, daily roll, sources, immutable receipts, VIP race/replay/rollback, paid VIP, unrestricted exchange, overlap integral, real pet claim and chat/help/gates')
    finally:
        await system_flags.set_flag(db,'star_dust_v1',True)
        await conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',required=True,type=local_dsn)
    asyncio.run(run(p.parse_args().dsn))
