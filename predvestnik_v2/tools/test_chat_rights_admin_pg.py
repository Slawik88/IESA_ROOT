"""Rollback-only proof: web changes affect actual bot authorization immediately."""
import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN','123456:offline-preprod-tests')
async def main():
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from services import chat_rank_admin as svc
    from bot.chat import ranks
    c=await asyncpg.connect(os.environ['DATABASE_URL']);tx=c.transaction();await tx.start()
    try:
        await c.execute('SET LOCAL search_path TO predvestnik,public')
        cid=-991212111;other=-991212112;uid=991212113
        for chat in [cid,other]:
            await c.execute('INSERT INTO chat_settings(chat_id,chat_title) VALUES($1,$2)',chat,'Rights proof')
        await c.execute('UPDATE chat_settings SET owner_id=$2 WHERE chat_id=$1',cid,uid+1)
        db=PGAdapter(c);actor={'id':uid,'rank':6,'kind':'staff'}
        original=await ranks.rights_map(db,cid)
        assert original['mute']==4
        await svc.update(db,actor,cid,changes={'mute':0,'rights':9},expected={'mute':4,'rights':9},reason='review proof')
        assert await ranks.can(db,cid,uid,'mute')
        assert not await ranks.can(db,other,uid,'mute')
        assert (await ranks.rights_map(db,cid))['rights']==9
        await ranks.set_right(db,cid,'mute',6,uid+1)
        assert not await ranks.can(db,cid,uid,'mute')
        snap=await svc.snapshot(db,cid)
        assert snap['values']['mute']==6 and len(snap['actions'])==20
        try: await svc.update(db,actor,cid,changes={'mute':0},expected={'mute':4},reason='stale attempt')
        except svc.StaleRights:pass
        else:raise AssertionError('lost update allowed')
        for who in [{'id':uid,'rank':4,'kind':'staff'},{'id':uid,'rank':9,'kind':'owner'}]:
            try:await svc.update(db,who,cid,changes={'mute':0},expected={'mute':6},reason='denied proof')
            except svc.Denied:pass
            else:raise AssertionError('unauthorized update')
        for changes,expected,reason in [({'unknown':0},{'unknown':0},'bad key'),({'mute':10},{'mute':6},'bad rank'),({'mute':True},{'mute':6},'bad type'),({'mute':0},{'mute':6},'')]:
            try:await svc.update(db,actor,cid,changes=changes,expected=expected,reason=reason)
            except svc.RightsError:pass
            else:raise AssertionError('invalid update allowed')
        assert await c.fetchval("SELECT COUNT(*) FROM bot_admin_actions WHERE chat_id=$1 AND action='chat_rights'",cid)==1
        assert await ranks.rights_map(db,other)==original
        # Audit failure must undo the permission write in the same savepoint.
        from unittest.mock import patch,AsyncMock
        with patch.object(svc.repo,'audit',AsyncMock(side_effect=RuntimeError('audit offline'))):
            try:await svc.update(db,actor,cid,changes={'mute':0},expected={'mute':6},reason='atomic proof')
            except RuntimeError:pass
            else:raise AssertionError('audit failure hidden')
        assert (await ranks.rights_map(db,cid))['mute']==6
        await c.execute('INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,chat_rank) VALUES($1,$2,0)',uid,cid)
        await svc.assign_member(db,actor,cid,uid,rank=4,expected=0,reason='Promote moderator')
        assert await ranks.get_rank(db,cid,uid)==4
        try:await svc.assign_member(db,actor,cid,uid,rank=7,expected=0,reason='Stale form')
        except svc.StaleRights:pass
        else:raise AssertionError('stale rank allowed')
        try:await svc.assign_member(db,actor,cid,uid+1,rank=0,expected=0,reason='Demote owner')
        except svc.RightsError:pass
        else:raise AssertionError('owner demoted')
        assert await c.fetchval("SELECT COUNT(*) FROM bot_admin_actions WHERE chat_id=$1 AND action='chat_rank'",cid)==1
        print('PASS: shared bot/web rights; scope, staff guard, input, stale update and atomic audit')
    finally:await tx.rollback();await c.close()
if __name__=='__main__':asyncio.run(main())
