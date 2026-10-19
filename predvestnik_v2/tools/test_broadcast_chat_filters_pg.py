"""Rollback-only recipient filtering proof; never creates/sends a broadcast."""
import argparse,asyncio,os,sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

async def run(dsn):
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from services import broadcasts
    c=await asyncpg.connect(dsn)
    tx=c.transaction();await tx.start()
    try:
        await c.execute('SET LOCAL search_path TO predvestnik, public')
        ids=[-990181001,-990181002,-990181003,-990181004]
        main,admin,unlinked,left=ids
        for i in ids:await c.execute('INSERT INTO chat_settings(chat_id,chat_title) VALUES($1,$2)',i,'Filter proof')
        await c.execute('UPDATE chat_settings SET bot_left_at=NOW() WHERE chat_id=$1',left)
        await c.execute('INSERT INTO chat_links(main_chat_id,admin_chat_id) VALUES($1,$2)',main,admin)
        db=PGAdapter(c)
        async def targets(kind='',**kw):
            segment=broadcasts.normalize_segment({'kind':'chats','chats':ids,'chat_kind':kind,**kw})
            return set(await broadcasts.recipients(db,segment))
        assert await targets()=={main,admin,unlinked}
        assert await targets('main')=={main,unlinked}
        assert await targets('admin')=={admin}
        assert await targets('admin',chats=[main,unlinked])==set()
        assert await targets('main',target_ids=[admin])==set()
        assert await targets('admin',target_ids=[admin,left])=={admin}
        assert await targets('admin',chats=[left])==set()
        from bot.chat.tracking import local_now
        from datetime import timedelta
        today=local_now().date()
        await c.execute('INSERT INTO daily_user_stats(user_id,chat_id,date) VALUES($1,$2,$3)',990181999,admin,today.isoformat())
        await c.execute('INSERT INTO daily_user_stats(user_id,chat_id,date) VALUES($1,$2,$3)',990181999,unlinked,(today-timedelta(days=10)).isoformat())
        assert await targets('admin',active_days=1)=={admin}
        assert await targets('main',active_days=1)==set()
        assert await targets(active_days=1)=={admin}
        try:broadcasts.normalize_segment({'kind':'chats','chat_kind':'invalid'})
        except broadcasts.BroadcastError:pass
        else:raise AssertionError('invalid kind accepted')
        assert 'только админ' in broadcasts.describe_segment({'kind':'chats','chat_kind':'admin'}).lower()
        print('PASS: linked admin vs ordinary/unlinked; selection and retry intersections; bot-left exclusion; invalid kind; no messages sent')
    finally:
        await tx.rollback();await c.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--dsn',required=True);args=ap.parse_args()
    if urlparse(args.dsn).hostname not in ('127.0.0.1','localhost','::1'):raise SystemExit('Loopback test database required')
    os.environ['DATABASE_URL']=args.dsn;os.environ.setdefault('BOT_TOKEN','123456:offline-preprod-tests')
    asyncio.run(run(args.dsn))
