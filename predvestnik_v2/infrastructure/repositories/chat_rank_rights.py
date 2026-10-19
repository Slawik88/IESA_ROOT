"""The single chat permission store, shared by Telegram and the web editor."""
import json
from core.chat_rank_policy import ACTIONS

async def lock(db, chat_id):
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('chat-rights:' || ?::bigint::text, 0))", (chat_id,))

async def read(db, chat_id):
    result={a.key:a.default for a in ACTIONS}
    async with db.execute("SELECT action,min_rank FROM chat_rank_rights WHERE chat_id=?",(chat_id,)) as cur:
        for key,value in await cur.fetchall():
            if key in result: result[key]=int(value)
    return result

async def exists(db, chat_id):
    async with db.execute("SELECT 1 FROM chat_settings WHERE chat_id=?",(chat_id,)) as cur:
        return bool(await cur.fetchone())

async def write(db, chat_id, changes, actor_id):
    for key,value in changes.items():
        await db.execute("INSERT INTO chat_rank_rights(chat_id,action,min_rank,updated_by) VALUES(?,?,?,?) ON CONFLICT(chat_id,action) DO UPDATE SET min_rank=EXCLUDED.min_rank,updated_by=EXCLUDED.updated_by,updated_at=NOW()",(chat_id,key,value,actor_id))

async def audit(db, actor_id, chat_id, before, after, reason):
    await db.execute("INSERT INTO bot_admin_actions(actor_id,action,chat_id,details) VALUES(?,'chat_rights',?,?::jsonb)",(actor_id,chat_id,json.dumps({'before':before,'after':after,'reason':reason},ensure_ascii=False)))


async def member(db, chat_id, user_id):
    async with db.execute("SELECT COALESCE(owner_override,owner_id) FROM chat_settings WHERE chat_id=?",(chat_id,)) as c:
        row=await c.fetchone()
    if row and row[0] and int(row[0])==user_id:return {'owner':True}
    async with db.execute("SELECT COALESCE(chat_rank,0),COALESCE(is_left,FALSE) FROM user_chat_stats WHERE chat_tg_id=? AND user_tg_id=? FOR UPDATE",(chat_id,user_id)) as c:
        row=await c.fetchone()
    return None if not row else {'rank':int(row[0]),'left':bool(row[1])}

async def write_member(db, chat_id, user_id, rank):
    await db.execute('UPDATE user_chat_stats SET chat_rank=? WHERE chat_tg_id=? AND user_tg_id=?',(rank,chat_id,user_id))

async def audit_member(db, actor_id, chat_id, user_id, before, after, reason):
    await db.execute("INSERT INTO bot_admin_actions(actor_id,action,chat_id,user_id,details) VALUES(?,'chat_rank',?,?,?::jsonb)",(actor_id,chat_id,user_id,json.dumps({'before':before,'after':after,'reason':reason},ensure_ascii=False)))


async def store_member(db, chat_id, user_id, rank):
    await db.execute("INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,chat_rank) VALUES(?,?,?) ON CONFLICT(user_tg_id,chat_tg_id) DO UPDATE SET chat_rank=EXCLUDED.chat_rank",(user_id,chat_id,rank))

async def owner_override(db, chat_id, user_id):
    await db.execute("INSERT INTO chat_settings(chat_id,owner_override) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET owner_override=EXCLUDED.owner_override",(chat_id,user_id))
