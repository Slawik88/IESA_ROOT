"""Owner/chat-bound immutable button payloads. Expired buttons refuse; successful actions replay in pets_v2."""
import json
from uuid import uuid4


async def ensure_tables(db):
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('schema:pet-chat-v1',0))")
        await db.execute('''CREATE TABLE IF NOT EXISTS pet_chat_buttons (
            token TEXT PRIMARY KEY, user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
            payload JSONB NOT NULL, expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '72 hours')''')
        await db.execute('CREATE INDEX IF NOT EXISTS pet_chat_buttons_expiry ON pet_chat_buttons(user_id,expires_at)')


async def save(db, user_id, chat_id, payload):
    token = uuid4().hex[:24]
    await db.execute('INSERT INTO pet_chat_buttons(token,user_id,chat_id,payload) VALUES(?,?,?,?::jsonb)',
                     (token,int(user_id),int(chat_id),json.dumps(payload,ensure_ascii=False)))
    return token


async def get(db, token):
    async with db.execute('SELECT *,expires_at>NOW() AS valid FROM pet_chat_buttons WHERE token=?',(token,)) as cur:
        row = await cur.fetchone()
    if not row: return None
    row = dict(row)
    if isinstance(row['payload'],str): row['payload'] = json.loads(row['payload'])
    return row


async def expire(db, user_id):
    await db.execute('DELETE FROM pet_chat_buttons WHERE user_id=? AND expires_at<NOW()',(int(user_id),))
