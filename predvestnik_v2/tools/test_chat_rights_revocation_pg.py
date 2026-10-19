"""Two-connection proof: a queued Telegram write cannot undo web revocation."""
import asyncio,os,sys
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN','123456:offline-preprod-tests')

async def main():
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import chat_rank_rights as repo
    from services import chat_rank_admin as admin
    from bot.chat import ranks,rank_commands
    from types import SimpleNamespace
    from unittest.mock import AsyncMock,patch
    dsn=os.environ['DATABASE_URL']
    if urlparse(dsn).hostname not in ('localhost','127.0.0.1','::1') or ':55856/' not in dsn:
        raise SystemExit('Use isolated loopback 55856 cluster')
    schema='rights_revoke_'+uuid4().hex[:12]
    c=await asyncpg.connect(dsn);other=None;task=None
    try:
        await c.execute(f'CREATE SCHEMA "{schema}"')
        await c.execute(f'SET search_path TO "{schema}"')
        await c.execute("""CREATE TABLE chat_settings(chat_id BIGINT PRIMARY KEY,owner_id BIGINT,owner_override BIGINT);
            CREATE TABLE user_chat_stats(chat_tg_id BIGINT,user_tg_id BIGINT,chat_rank INT,is_left BOOLEAN DEFAULT FALSE,PRIMARY KEY(user_tg_id,chat_tg_id));
            CREATE TABLE chat_rank_rights(chat_id BIGINT,action TEXT,min_rank INT,updated_by BIGINT,
                updated_at TIMESTAMPTZ DEFAULT NOW(),PRIMARY KEY(chat_id,action));
            CREATE TABLE bot_admin_actions(actor_id BIGINT,action TEXT,chat_id BIGINT,user_id BIGINT,details JSONB);
            INSERT INTO chat_settings VALUES(-100,21,NULL);
            INSERT INTO user_chat_stats(chat_tg_id,user_tg_id,chat_rank) VALUES(-100,22,4);
            INSERT INTO chat_rank_rights(chat_id,action,min_rank,updated_by) VALUES(-100,'rights',4,21);""")
        db=PGAdapter(c)
        other=await asyncpg.connect(dsn);await other.execute(f'SET search_path TO "{schema}"')
        queued=PGAdapter(other)
        assert await ranks.can(queued,-100,22,'rights')
        async with c.transaction():
            await repo.lock(db,-100)
            task=asyncio.create_task(ranks.set_right(queued,-100,'ban',0,22))
            # Wait for a proven advisory-lock wait instead of assuming a sleep won.
            for _ in range(100):
                if await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",other.get_server_pid()):break
                await asyncio.sleep(.01)
            else:raise AssertionError('queued write never reached chat lock')
            await admin.update(db,{'id':24,'kind':'staff','rank':6},-100,
                changes={'rights':9},expected={'rights':4},reason='Revoke delegated control')
        try:await asyncio.wait_for(task,3)
        except PermissionError:pass
        else:raise AssertionError('revoked actor changed permissions')
        assert (await ranks.rights_map(db,-100))['ban']==6
        assert (await ranks.rights_map(db,-100))['rights']==9
        await ranks.set_right(db,-100,'ban',5,21)
        assert (await ranks.rights_map(db,-100))['ban']==5
        # Delegation restriction also belongs to the locked writer.
        await admin.update(db,{'id':24,'kind':'staff','rank':6},-100,
            changes={'rights':4},expected={'rights':9},reason='Restore delegated control')
        try:await ranks.set_right(queued,-100,'rights',0,22)
        except PermissionError:pass
        else:raise AssertionError('delegate handed control to everyone')
        # A rejected late check is shown as an alert, without editing success UI.
        call=SimpleNamespace(from_user=SimpleNamespace(id=22),answer=AsyncMock(),message=SimpleNamespace(edit_text=AsyncMock()))
        cb=rank_commands.RightsCB(uid=22,chat=-100,act='ban',val=0)
        with patch.object(ranks,'can',AsyncMock(return_value=True)),patch.object(ranks,'set_right',AsyncMock(side_effect=PermissionError('Revoked'))):
            await rank_commands.on_rights(call,cb,queued)
        call.answer.assert_awaited_once_with('Revoked',show_alert=True)
        call.message.edit_text.assert_not_awaited()
        await c.execute('UPDATE user_chat_stats SET chat_rank=7 WHERE user_tg_id=22')
        await c.execute('INSERT INTO user_chat_stats(chat_tg_id,user_tg_id,chat_rank) VALUES(-100,23,0)')
        async with c.transaction():
            await repo.lock(db,-100)
            task=asyncio.create_task(ranks.assign_rank(queued,-100,23,3,22,expected_rank=0))
            for _ in range(100):
                if await c.fetchval("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",other.get_server_pid()):break
                await asyncio.sleep(.01)
            else:raise AssertionError('rank writer did not queue')
            await admin.assign_member(db,{'id':24,'kind':'staff','rank':6},-100,22,rank=0,expected=7,reason='Revoke rank assignment')
        try:await asyncio.wait_for(task,3)
        except PermissionError:pass
        else:raise AssertionError('demoted actor assigned rank')
        assert await ranks.get_rank(db,-100,23)==0
        print('PASS: proven queued-write revocation, owner access, delegate boundary and late-denial alert')
    finally:
        if task and not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        if other:await other.close()
        await c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE');await c.close()

if __name__=='__main__':asyncio.run(main())
