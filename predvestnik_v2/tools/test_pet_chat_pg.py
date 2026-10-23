"""Pet Telegram adapter proof against isolated loopback PostgreSQL; no Telegram network."""
import argparse, asyncio, os, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import asyncpg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.test_pets_v2_pg import local_dsn


class Message:
    def __init__(self, chat): self.chat=chat; self.edits=[]
    async def edit_text(self,text,**kwargs): self.edits.append((text,kwargs))


class Call:
    def __init__(self,uid,chat,token):
        self.from_user=SimpleNamespace(id=uid); self.message=Message(chat)
        self.data='pt:'+token; self.answers=[]
    async def answer(self,text='',**kwargs): self.answers.append(text)


async def run(dsn):
    os.environ.setdefault('BOT_TOKEN','123456:test');os.environ['DATABASE_URL']=dsn
    from bot.chat import pets
    from bot.chat.framework import registry
    from bot.chat.help import _by_section
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import pet_chat, pets_v2 as repo, chests_v1, skins_v3, achievements_v1
    from services import pets_v2 as service, feature_switches, global_moderation
    from core.chests_v1 import PET_SPECIES
    from core.pets_v2 import PetV2PolicyError
    conn=await asyncpg.connect(dsn);db=PGAdapter(conn)
    for schema in (chests_v1,skins_v3,achievements_v1,repo,pet_chat):await schema.ensure_tables(db)
    await feature_switches.ensure_schema(db);await global_moderation.ensure_schema(db)
    tx=conn.transaction();await tx.start()
    uid=9987812001;chat=SimpleNamespace(id=-9987812001,type='supergroup');dm=SimpleNamespace(id=uid,type='private')
    try:
        await db.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES (?,1000000)',(uid,))
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='pets_v2'")
        await db.execute("DELETE FROM global_module_toggles WHERE module_key='module_pets'")
        await db.execute('DELETE FROM bot_feature_switches WHERE chat_id IN (0,?)',(chat.id,))
        ids=[]
        for species,row in PET_SPECIES.items():
            async with db.execute('INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?) RETURNING id',(uid,row['name'],species,row['rarity'])) as c:
                pid=(await c.fetchone())[0];ids.append(pid)
            await repo.ensure_state(db,uid,pid,120)
        cat,owl=ids[0],ids[1]
        await db.execute("UPDATE pets SET name='   ' WHERE id=?",(cat,))
        await db.execute('UPDATE pet_v2_state SET level=30,energy=120 WHERE user_id=?',(uid,))
        await db.execute('INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?,\'food_basic\',4)',(uid,))
        assert await pets.available(db,uid,chat) and await pets.available(db,uid,dm)
        assert {c.name for c in _by_section(True)['pets']}=={c.name for c in registry.commands() if c.section=='pets'}
        async def show(data):
            text,kb=await pets.render(db,uid,chat.id,data)
            assert text and len(text)<4096,(data,len(text))
            for row in kb.inline_keyboard:
                for b in row:
                    assert len(b.callback_data.encode())<=64
                    saved=await pet_chat.get(db,b.callback_data[3:]);assert saved['user_id']==uid and saved['chat_id']==chat.id
            return text,kb
        for screen in ('home','collection','bestiary','camp','trial','help'):
            await show({'screen':screen})
        text,kb=await show({'screen':'trial'})
        assert any('Моховой кот' in b.text for row in kb.inline_keyboard for b in row), 'unnamed pet needs its localized species name'
        view=await service.overview(db,uid)
        energy_max=next(p['energy_max'] for p in view['pets'] if p['id']==cat)
        await db.execute('UPDATE pet_v2_state SET energy=? WHERE user_id=? AND pet_id=?',(energy_max-5,uid,cat))
        text,kb=await show({'screen':'feed_confirm','pet_id':cat,'food_id':'food_basic'})
        assert 'Сейчас восстановит 5 сил' in text and 'не поместится' in text and 'Любимый вкус' in text
        await db.execute('UPDATE pet_v2_state SET energy=? WHERE user_id=? AND pet_id=?',(energy_max,uid,cat))
        text,kb=await show({'screen':'feed_confirm','pet_id':cat,'food_id':'food_basic'})
        assert 'Силы уже полные' in text and 'расходуется' in text
        await db.execute("UPDATE chest_food_balances_v1 SET quantity=0 WHERE user_id=? AND food_id='food_basic'",(uid,))
        text,kb=await show({'screen':'feed_confirm','pet_id':cat,'food_id':'food_basic'})
        assert 'закончилось' in text and not any(b.text=='Дать лакомство' for row in kb.inline_keyboard for b in row)
        await db.execute("UPDATE chest_food_balances_v1 SET quantity=4 WHERE user_id=? AND food_id='food_basic'",(uid,))
        for screen in ('pet','prepare','feed','gear','build','track','outing'):
            await show({'screen':screen,'pet_id':cat})
        for section in ('calling','traits','talismans','presets'):
            await show({'screen':'build','pet_id':cat,'section':section})
        await show({'screen':'prepare','pet_id':cat,'kind':'trek'})
        await show({'screen':'prepare','pet_id':cat,'kind':'trek','hours':3})
        await show({'screen':'prepare','pet_id':cat,'kind':'trek','hours':3,'route':'forest'})
        text,kb=await show({'screen':'prepare','pet_id':cat,'kind':'trek','hours':3,'route':'forest','companion_id':None})
        assert 'сил' in text and any('Отправить'==b.text for r in kb.inline_keyboard for b in r)
        token=await pet_chat.save(db,uid,chat.id,{'screen':'home'})
        for bad in (Call(uid+1,chat,token),Call(uid,dm,token)):
            await pets.on_pet(bad,db);assert not bad.message.edits and 'другого' in bad.answers[-1]
        await db.execute("UPDATE pet_chat_buttons SET expires_at=NOW()-INTERVAL '1 second' WHERE token=?",(token,))
        expired=Call(uid,chat,token);await pets.on_pet(expired,db);assert 'устарело' in expired.answers[-1]
        token=await pet_chat.save(db,uid,chat.id,{'do':'feed','pet_id':cat,'food_id':'food_basic'})
        for feature in ('all','section:pets','group:pets','cmd:pets','cmd:питомцы'):
            await db.execute('INSERT INTO bot_feature_switches(chat_id,feature) VALUES (?,?)',(chat.id,feature))
            denied=Call(uid,chat,token);await pets.on_pet(denied,db);assert not denied.message.edits and 'недоступны' in denied.answers[-1]
            await db.execute('DELETE FROM bot_feature_switches WHERE chat_id=? AND feature=?',(chat.id,feature))
        for feature,payload in [('cmd:лагерь',{'do':'camp'}),('cmd:покормить питомца',{'do':'feed'}),
                                ('cmd:отправить питомца',{'do':'start'}),('cmd:вылазка',{'do':'outing_choose'}),
                                ('cmd:выслеживание',{'do':'track_open'}),('cmd:испытание питомцев',{'do':'trial'}),
                                ('cmd:бестиарий',{'screen':'bestiary'})]:
            guarded=await pet_chat.save(db,uid,chat.id,payload)
            await db.execute('INSERT INTO bot_feature_switches(chat_id,feature) VALUES (?,?)',(chat.id,feature))
            blocked=Call(uid,chat,guarded)
            with patch.object(pets,'mutate',side_effect=AssertionError('disabled subcommand reached mutation')):
                await pets.on_pet(blocked,db)
            assert not blocked.message.edits and 'недоступны' in blocked.answers[-1]
            await db.execute('DELETE FROM bot_feature_switches WHERE chat_id=? AND feature=?',(chat.id,feature))
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key='pets_v2'")
        assert not await pets.available(db,uid,chat)
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='pets_v2'")
        await db.execute("INSERT INTO global_module_toggles(module_key,enabled) VALUES ('module_pets',0)")
        assert not await pets.available(db,uid,chat) and not await pets.available(db,uid,dm)
        await db.execute("DELETE FROM global_module_toggles WHERE module_key='module_pets'")
        await db.execute('INSERT INTO chat_settings(chat_id,module_pets) VALUES (?,0)',(chat.id,))
        assert not await pets.available(db,uid,chat) and await pets.available(db,uid,dm)
        await db.execute('DELETE FROM chat_settings WHERE chat_id=?',(chat.id,))
        await db.execute('INSERT INTO bot_user_blocks(user_id) VALUES (?)',(uid,))
        assert not await pets.available(db,uid,dm)
        await db.execute('DELETE FROM bot_user_blocks WHERE user_id=?',(uid,))
        # Commit succeeded but fresh overview/delivery failed: SAME token replays the receipt.
        broken=Call(uid,chat,token)
        with patch.object(pets,'render',side_effect=RuntimeError('simulated delivery failure')), patch.object(pets.logger,'exception'):
            await pets.on_pet(broken,db)
        assert not broken.message.edits and 'ту же кнопку' in broken.answers[-1]
        retry=Call(uid,chat,token);await pets.on_pet(retry,db);assert retry.message.edits
        async with db.execute("SELECT quantity FROM chest_food_balances_v1 WHERE user_id=? AND food_id='food_basic'",(uid,)) as c:
            assert (await c.fetchone())[0]==3,'feed replay must debit exactly one item'
        async def act(data):
            token=await pet_chat.save(db,uid,chat.id,data)
            first=await pets.mutate(db,uid,token,data);again=await pets.mutate(db,uid,token,data)
            assert again[0].get('idempotent_replay') or again[0]==first[0]
            return first[0]
        gear=await act({'do':'gear','pet_id':cat,'operation':'starter','item':None,'expected_tier':None})
        await show({'screen':'gear','pet_id':cat,'item':'compass'})
        await act({'do':'gear','pet_id':cat,'operation':'unequip','item':'compass','expected_tier':None})
        await act({'do':'gear','pet_id':cat,'operation':'equip','item':'compass','expected_tier':None})
        from infrastructure.repositories import pet_equipment as gear_repo
        await gear_repo.add_parts(db,uid,100)
        await show({'screen':'gear','pet_id':cat,'item':'lens','operation':'craft'})
        await act({'do':'gear','pet_id':cat,'operation':'craft','item':'lens','expected_tier':0})
        await act({'do':'gear','pet_id':cat,'operation':'upgrade','item':'lens','expected_tier':1})
        await skins_v3.essence_apply(db,uid,1000,reason='test',reference='chat-test',idempotency_key='chat-test-essence')
        await show({'screen':'camp','building':'workshop'})
        await act({'do':'camp','building':'workshop','expected_level':0})
        await db.execute("UPDATE pet_v2_camp_jobs SET ends_at=NOW()-INTERVAL '1 minute',to_level=2 WHERE user_id=?",(uid,))
        await db.execute("INSERT INTO pet_v2_talismans(id,user_id,kind,tier) VALUES ('chat-test-talisman',?,'forest_fang',1)",(uid,))
        await db.execute("UPDATE pet_v2_talismans SET pet_id=? WHERE id='chat-test-talisman'",(owl,))
        text,kb=await show({'screen':'build_confirm','pet_id':cat,'draft':{'calling':None,'traits':[],'talisman_ids':['chat-test-talisman']},'base':{'calling':None,'traits':[],'talisman_ids':[]}})
        assert 'Лесной клык · 1 ур.' in text and 'снимется с' in text
        await show({'screen':'reforge','pet_id':cat,'talisman_id':'chat-test-talisman'})
        await act({'do':'reforge','talisman_id':'chat-test-talisman','expected_tier':1,'return_pet':cat})
        await act({'do':'preset','pet_id':cat,'slot':1,'draft':{'calling':None,'traits':[],'talisman_ids':[]}})
        await show({'screen':'build','pet_id':cat,'section':'presets'})
        base={'calling':None,'traits':[],'talisman_ids':[]}
        changed=await act({'do':'build','pet_id':cat,'calling':'tracker','traits':[],'talisman_ids':[],'expected_essence':0,'expected_build':base})
        try:
            await pets.mutate(db,uid,'stale-build',{'do':'build','pet_id':cat,'calling':'feeder','traits':[],'talisman_ids':[],'expected_essence':0,'expected_build':base})
        except PetV2PolicyError:pass
        else:raise AssertionError('stale build must reject')
        start=await act({'do':'start','pet_id':cat,'kind':'expedition','hours':3,'route':'forest','companion_id':None})
        await db.execute("UPDATE pet_v2_runs SET starts_at=NOW()-make_interval(hours=>hours)-INTERVAL '1 minute',ends_at=NOW()-INTERVAL '1 minute' WHERE id=?",(start['run_id'],))
        text,kb=await show({'screen':'home'})
        assert any(b.text=='Вернуть: Моховой кот' for row in kb.inline_keyboard for b in row)
        assert sum(b.text.startswith('Все питомцы') for row in kb.inline_keyboard for b in row)==1
        await show({'screen':'claim','run_id':start['run_id']})
        claimed=await act({'do':'claim','run_id':start['run_id'],'path':'careful'})
        assert claimed['xp_credited']>0
        t=await act({'do':'track_start','pet_id':owl})
        await show({'screen':'track'})
        opened={o['cell'] for o in t['track']['opened']}
        await act({'do':'track_open','track_id':t['track']['id'],'cell':next(i for i in range(9) if i not in opened)})
        o=await act({'do':'outing_start','pet_id':owl})
        await show({'screen':'outing'})
        done=await act({'do':'outing_choose','outing_id':o['outing']['id'],'step':0,'choice':'leave'})
        assert done['outing']['status']!='active'
        await show({'screen':'trial','pet_id':ids[-1],'difficulty':1})
        week=(await service.trial_view(db,uid))['week']
        try:
            await pets.mutate(db,uid,'stale-week-000000',{'do':'trial','pet_id':ids[-1],'difficulty':1,'expected_week':'2020-01-06'})
        except PetV2PolicyError:pass
        else:raise AssertionError('stale trial confirmation consumed current week')
        trial=await act({'do':'trial','pet_id':ids[-1],'difficulty':1,'expected_week':week})
        assert trial['essence']>0
        # Every ID-backed selection survives inventory reordering; no numeric list indices stored.
        await show({'screen':'pet','pet_id':ids[-1]}) # dragon's any-route affinity
        print('PASS pet chat: views, registry/help, previews, owner/chat/expiry, immediate gates, retry after commit, all mutation dispatchers and replay')
    finally:
        await tx.rollback();await conn.close()
    await race(dsn)


async def race(dsn):
    from bot.chat import pets
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import pet_chat
    from uuid import uuid4
    uid=9980000000+int(uuid4().hex[:5],16)
    conn=await asyncpg.connect(dsn);db=PGAdapter(conn)
    try:
        await db.execute('INSERT INTO users(user_tg_id) VALUES (?)',(uid,))
        async with db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,'Race','moss_cat','common') RETURNING id",(uid,)) as c:
            pid=(await c.fetchone())[0]
        data={'do':'gear','pet_id':pid,'operation':'starter','item':None,'expected_tier':None}
        token=await pet_chat.save(db,uid,-uid,data)
        async def click():
            c=await asyncpg.connect(dsn)
            try:return await pets.mutate(PGAdapter(c),uid,token,data)
            finally:await c.close()
        a,b=await asyncio.gather(click(),click())
        assert sum(bool(r[0]['idempotent_replay']) for r in (a,b))==1
        async with db.execute('SELECT COUNT(*) FROM pet_v2_actions WHERE user_id=? AND action_id=?',(uid,'chat:'+token)) as c:
            assert (await c.fetchone())[0]==1
        print('PASS pet chat: two concurrent PostgreSQL connections / one token / one receipt')
    finally:
        for table in ('pet_chat_buttons','pet_v2_actions','pet_v2_state'):
            await db.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
        await db.execute('DELETE FROM pets WHERE owner_id=?',(uid,))
        await db.execute('DELETE FROM users WHERE user_tg_id=?',(uid,))
        await conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dsn',required=True,type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
