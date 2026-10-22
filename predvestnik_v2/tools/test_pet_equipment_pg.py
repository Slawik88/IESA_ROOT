"""Real loopback PostgreSQL: receipts, actual trip effects, restoration and races."""
import argparse,asyncio,json,random,sys
from pathlib import Path
import asyncpg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import pets_v2 as pr, pet_equipment as gr, chests_v1
from services import pets_v2 as pets, pet_equipment as gear
from core.pets_v2 import PetV2PolicyError
from tools.test_pets_v2_pg import local_dsn

USER,OTHER=99771001,99771002


async def denied(job):
    try:await job
    except PetV2PolicyError:return
    raise AssertionError('expected gameplay conflict')


async def run(dsn):
    conn=await asyncpg.connect(dsn);db=PGAdapter(conn)
    try:
        await chests_v1.ensure_tables(db);await pr.ensure_tables(db)
        await db.execute('INSERT INTO users(user_tg_id) VALUES (?),(?) ON CONFLICT DO NOTHING',(USER,OTHER))
        await db.execute('INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)',(USER,'Gear probe','moss_cat','common'))
        async with db.execute('SELECT id FROM pets WHERE owner_id=? ORDER BY id DESC LIMIT 1',(USER,)) as c:pet=int((await c.fetchone())[0])
        await db.commit()
        bare=await pets.preview_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest')
        first=await gear.change(db,user_id=USER,pet_id=pet,operation='starter',item=None,expected_tier=0,action_id='gear-first')
        assert len(first['equipment']['equipped'])==5 and first['spent']==0
        replay=await gear.change(db,user_id=USER,pet_id=pet,operation='starter',item=None,expected_tier=0,action_id='gear-first')
        assert replay['equipment']==first['equipment'] and replay['idempotent_replay']
        await denied(gear.change(db,user_id=OTHER,pet_id=pet,operation='starter',item=None,expected_tier=0,action_id='other'))
        quote=await pets.preview_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest')
        assert quote['base_raw']>bare['base_raw'] and quote['factors']['build']==1.0712, 'gear must affect actual current-trip preview'
        await gr.add_parts(db,USER,100);await db.commit()
        craft=await gear.change(db,user_id=USER,pet_id=pet,operation='craft',item='lens',expected_tier=0,action_id='craft')
        assert craft['parts']==92 and craft['spent']==8
        upgrade=await gear.change(db,user_id=USER,pet_id=pet,operation='upgrade',item='compass',expected_tier=1,action_id='upgrade')
        assert upgrade['parts']==80 and upgrade['equipment']['items']['compass']==2
        await denied(gear.change(db,user_id=USER,pet_id=pet,operation='upgrade',item='compass',expected_tier=1,action_id='stale'))
        # One energy settlement at the OLD rate/cap, then cap change, no refill.
        await db.execute("UPDATE pet_v2_state SET energy=20,energy_at=NOW()-INTERVAL '2 hours' WHERE user_id=? AND pet_id=?",(USER,pet))
        await db.commit()
        equip=await gear.change(db,user_id=USER,pet_id=pet,operation='equip',item='lens',expected_tier=1,action_id='equip')
        assert 20<equip['energy']<50
        run=await pets.start_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest',action_id='trip')
        await denied(gear.change(db,user_id=USER,pet_id=pet,operation='unequip',item='lens',expected_tier=1,action_id='trip-gear'))
        await denied(gear.start(db,user_id=USER,pet_id=pet,action_id='trip-outing'))
        # Real current-trip claim uses the equipped gear, not just its preview.
        before_claim=await pets.preview_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest')
        await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE id=?",(run['run_id'],));await db.commit()
        claimed=await pets.claim_run(db,user_id=USER,run_id=run['run_id'],action_id='claim-geared-trip',rng=random.Random(7))
        assert claimed['xp_raw']>=before_claim['base_raw'] and claimed['daily_credited']<=625
        await db.execute("UPDATE pet_v2_runs SET status='claimed' WHERE id=?",(run['run_id'],));await db.commit()
        # Restore/callback projection has no hidden deck or future events.
        start=await gear.start(db,user_id=USER,pet_id=pet,action_id='outing',rng=random.Random(13))
        o=start['outing'];assert len(o['choices'])==3 and 'deck' not in o and o['step']==0
        overview=await pets.overview(db,USER)
        assert overview['equipment']['open']==o and next(p for p in overview['pets'] if p['id']==pet)['outing']
        assert not (await pets.preview_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest'))['can_start']
        await denied(pets.start_run(db,user_id=USER,pet_id=pet,kind='trek',hours=3,route='forest',action_id='outing-trip'))
        await denied(gear.change(db,user_id=USER,pet_id=pet,operation='unequip',item='lens',expected_tier=1,action_id='outing-gear'))
        # Two separate DB connections submit the SAME choice concurrently.
        async def act(key,choice=1,step=0):
            c=await asyncpg.connect(dsn)
            try:return await gear.choose(PGAdapter(c),user_id=USER,outing_id=o['id'],step=step,choice=choice,action_id=key,rng=random.Random(0))
            finally:await c.close()
        a,b=await asyncio.gather(act('race'),act('race'))
        assert a['outing']==b['outing'] and a['idempotent_replay']!=b['idempotent_replay']
        await denied(act('stale-step'))
        before=await gr.parts(db,USER)
        # Distinct leave actions race: exactly one reward can be credited.
        results=await asyncio.gather(act('leave-a','leave',1),act('leave-b','leave',1),return_exceptions=True)
        success=[v for v in results if isinstance(v,dict)]
        assert len(success)==1 and sum(isinstance(v,PetV2PolicyError) for v in results)==1
        assert await gr.parts(db,USER)==before+success[0]['outing']['reward']
        assert await gr.active_outing(db,USER) is None
        assert not next(p for p in (await pets.overview(db,USER))['pets'] if p['id']==pet)['outing']
        await db.execute('UPDATE pet_v2_state SET energy=60 WHERE user_id=? AND pet_id=?',(USER,pet));await db.commit()
        for n in range(2):
            start=await gear.start(db,user_id=USER,pet_id=pet,action_id=f'limit-{n}')
            await gear.choose(db,user_id=USER,outing_id=start['outing']['id'],step=0,choice='leave',action_id=f'leave-{n}')
        await denied(gear.start(db,user_id=USER,pet_id=pet,action_id='fourth'))
        assert (await gear.summary(db,USER,(await pr.clock(db))['day']))['attempts_left']==0
        print('PASS: five slots, prices/rest, current-trip previews, ownership, busy/resume, concurrent choice/reward receipts and 3/day limit')
    finally:
        # Only this loopback test's explicitly reserved identities are removed.
        for table in ('pet_v2_actions','pet_v2_outings','pet_v2_parts','pet_v2_runs','pet_v2_state','pet_v2_daily','pet_v2_bond_days','pet_v2_stage_rewards'):
            await db.execute(f'DELETE FROM {table} WHERE user_id IN (?,?)',(USER,OTHER))
        await db.execute('DELETE FROM pets WHERE owner_id IN (?,?)',(USER,OTHER));await db.commit();await conn.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',required=True,type=local_dsn)
    asyncio.run(run(p.parse_args().dsn))
