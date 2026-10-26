"""Admin destinations never occupy public chat ranks, pages or podium slots."""
import argparse
import asyncio
import os
import pathlib
import sys
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

os.environ.setdefault("BOT_TOKEN","123456:local-test")
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import stats


async def run(dsn):
    connection = await asyncpg.connect(dsn)
    await connection.execute("SET search_path TO predvestnik,public")
    db = PGAdapter(connection)
    transaction = connection.transaction()
    await transaction.start()
    try:
        main = -int(uuid4().int % 1000000000 + 9000000000)
        admin,other,private = main-1,main-2,main-3
        uid = 98659901
        for cid,title,count,visible in [(main,"QA-main",10,1),(admin,"QA-admin",999,1),(other,"QA-public",20,1),(private,"QA-private",888,0)]:
            await db.execute("INSERT INTO chat_settings(chat_id,chat_title,include_in_global_top) VALUES (?,?,?)",(cid,title,visible))
            await db.execute("INSERT INTO daily_user_stats(chat_id,user_id,date,message_count) VALUES (?,?,'2199-01-05',?)",(cid,uid,count))
            await db.execute("INSERT INTO user_chat_stats(chat_tg_id,user_tg_id,user_messages_count_all_time) VALUES (?,?,?)",(cid,uid,count))
        await db.execute("INSERT INTO chat_links(main_chat_id,admin_chat_id) VALUES (?,?)",(main,admin))
        dates = await stats.get_top_chats_for_dates(db,"2199-01-05","2199-01-05")
        assert [r["chat_id"] for r in dates]==[other,main],dates
        first = await stats.chat_top_page(db,"2199-01-05","2199-01-05",page=0,page_size=1)
        last = await stats.chat_top_page(db,"2199-01-05","2199-01-05",page=99,page_size=1)
        assert first["total"]==2 and first["pages"]==2 and first["items"][0]["chat_id"]==other
        assert last["page"]==1 and last["items"][0]["chat_id"]==main
        for date_start,date_end in [(None,None),("2199-01-05","2199-01-05")]:
            assert await stats.get_message_top_position(db,scope="chats",entity_id=admin,date_start=date_start,date_end=date_end) is None
            position = await stats.get_message_top_position(db,scope="chats",entity_id=other,date_start=date_start,date_end=date_end)
            assert position is not None
            if date_start:
                assert position["place"]==1 and position["total_count"]==2
        all_time = await stats.get_top_chats_all_time(db,limit=100000)
        assert not {admin,private}&{r["chat_id"] for r in all_time}
        await db.execute("DELETE FROM chat_links WHERE main_chat_id=?",(main,))
        unlinked = await stats.get_top_chats_for_dates(db,"2199-01-05","2199-01-05",limit=1)
        assert unlinked[0]["chat_id"]==admin, "unbinding restores normal eligibility; historical activity is preserved"
        assert await connection.fetchval("SELECT message_count FROM daily_user_stats WHERE chat_id=$1 AND date='2199-01-05'",admin)==999
        print("PASS: linked admin chats excluded before LIMIT, period/all-time ranks and totals agree, pagination clamps, unbinding preserves history")
    finally:
        await transaction.rollback()
        await connection.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--dsn",required=True)
    args=parser.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost","127.0.0.1","::1"}:
        raise SystemExit("loopback database required")
    asyncio.run(run(args.dsn))
