"""Real independent connections: stale maintenance candidates cannot beat cancel/activity."""
import argparse
import asyncio
import time
from urllib.parse import urlparse
from unittest.mock import patch
from core.constants import ACCOUNT_DELETE_PHRASE

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from services import account_deletion as service


async def run(dsn):
    assert urlparse(dsn).hostname in {'127.0.0.1','localhost','::1'}
    first,second=await asyncpg.connect(dsn),await asyncpg.connect(dsn)
    db=PGAdapter(first);worker=PGAdapter(second)
    base=940_100_000_000+int(time.time_ns()%1_000_000)*10
    ids=list(range(base,base+10))
    async def seed(uid,source='self'):
        await first.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,1000)',uid)
        await first.execute("INSERT INTO account_deletions(user_id,source,status,cooling_until,warned_at) VALUES($1,$2,$3,NOW()-INTERVAL '1 hour',NOW()-INTERVAL '20 days')",uid,source,'cooling' if source=='self' else 'confirming')
        if source=='inactivity':
            await first.execute("INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,last_message_at) VALUES($1,-1,NOW()-INTERVAL '400 days')",uid)
    try:
        for uid in ids[:3]:await seed(uid)
        # The scheduler has already selected this account. Cancellation owns
        # the lifecycle lock first, and must remain successful after it returns.
        tx=first.transaction();await tx.start()
        await first.execute('SELECT pg_advisory_xact_lock($1)',ids[0])
        deleting=asyncio.create_task(service._mark_deleted(worker,ids[0]))
        await asyncio.sleep(.1);assert not deleting.done()
        ok,_=await service.cancel_deletion(db,ids[0]);assert ok
        await tx.commit();assert await deleting is False
        assert await first.fetchval('SELECT deleted_at IS NULL FROM users WHERE user_tg_id=$1',ids[0])
        assert await first.fetchval('SELECT status FROM account_deletions WHERE user_id=$1',ids[0])=='cancelled'

        # The inverse ordering must never report a successful late cancel.
        tx=first.transaction();await tx.start()
        assert await service._mark_deleted(db,ids[1])
        cancelling=asyncio.create_task(service.cancel_deletion(worker,ids[1]))
        await asyncio.sleep(.1);assert not cancelling.done()
        await tx.commit();assert not (await cancelling)[0]
        assert await first.fetchval('SELECT status FROM account_deletions WHERE user_id=$1',ids[1])=='pending_restore'

        # A later cooldown or refreshed request invalidates the old selection.
        await first.execute("UPDATE account_deletions SET cooling_until=NOW()+INTERVAL '1 hour' WHERE user_id=$1",ids[2])
        assert not await service._mark_deleted(worker,ids[2])
        await first.execute("UPDATE account_deletions SET status='confirming',confirm_code='123456' WHERE user_id=$1",ids[2])
        assert not await service._mark_deleted(worker,ids[2])

        for uid in ids[3:6]:await seed(uid,'inactivity')
        # Activity/settings commit after candidate selection, before mark.
        await first.execute('UPDATE user_chat_stats SET last_message_at=NOW() WHERE user_tg_id=$1',ids[3])
        assert not await service._mark_deleted(worker,ids[3])
        await first.execute('UPDATE users SET delete_after_days=730 WHERE user_tg_id=$1',ids[4])
        assert not await service._mark_deleted(worker,ids[4])
        assert await service._mark_deleted(worker,ids[5]),'a still-due inactive account must keep working'
        async def fake_tg(*args,**kwargs):return {'ok':True}
        # A warning candidate selected before the player's new request must
        # wait for the same lifecycle lock and never replace that request.
        for uid,confirm in ((ids[6],False),(ids[7],True)):
            await seed(uid,'inactivity')
            await first.execute("UPDATE account_deletions SET status='cancelled',warned_at=NULL WHERE user_id=$1",uid)
            assert await service._warning_candidates(db,uid)
            tx=first.transaction();await tx.start()
            await first.execute('SELECT pg_advisory_xact_lock($1)',uid)
            warning=asyncio.create_task(service._warn_inactive(worker,uid))
            await asyncio.sleep(.1);assert not warning.done()
            with patch.object(service,'_tg',fake_tg):
                assert (await service.request_deletion(db,uid))[0]
                code=await first.fetchval('SELECT confirm_code FROM account_deletions WHERE user_id=$1',uid)
                if confirm:assert (await service.confirm_deletion(db,uid,code,ACCOUNT_DELETE_PHRASE))[0]
            await tx.commit();assert not await warning
            row=await first.fetchrow('SELECT source,status,confirm_code FROM account_deletions WHERE user_id=$1',uid)
            assert row['source']=='self' and row['status']==('cooling' if confirm else 'confirming')
            assert confirm or row['confirm_code']==code
        for uid in ids[8:]:
            await seed(uid,'inactivity')
            await first.execute("UPDATE account_deletions SET status='cancelled',warned_at=NULL WHERE user_id=$1",uid)
            assert await service._warning_candidates(db,uid)
        assert await service._warn_inactive(worker,ids[8])
        await first.execute('UPDATE user_chat_stats SET last_message_at=NOW() WHERE user_tg_id=$1',ids[9])
        assert not await service._warn_inactive(worker,ids[9])
        print('OK: cancellation/deletion in both lock orders, stale cooldown/request, new activity and retention setting; valid inactivity still deletes; stale warnings preserve new codes/cooling/activity')
    finally:
        if first.is_in_transaction():await first.execute('ROLLBACK')
        await second.close()
        for sql in ('DELETE FROM account_deletions WHERE user_id=ANY($1::bigint[])',
                    'DELETE FROM user_chat_stats WHERE user_tg_id=ANY($1::bigint[])',
                    'DELETE FROM users WHERE user_tg_id=ANY($1::bigint[])'):
            await first.execute(sql,ids)
        await first.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',required=True);asyncio.run(run(p.parse_args().dsn))
