"""Equipment and outing SQL. Schema is installed with pets_v2.ensure_tables."""
import json


def _row(row):
    if not row: return None
    r = dict(row)
    if isinstance(r['state'], str): r['state'] = json.loads(r['state'])
    return r


async def active_outing(db, user_id):
    async with db.execute('SELECT * FROM pet_v2_outings WHERE user_id=? AND active', (int(user_id),)) as c:
        return _row(await c.fetchone())


async def latest_closed(db, user_id):
    async with db.execute('SELECT * FROM pet_v2_outings WHERE user_id=? AND NOT active ORDER BY created_at DESC,id DESC LIMIT 1', (int(user_id),)) as c:
        return _row(await c.fetchone())


async def get_outing(db, user_id, outing_id):
    async with db.execute('SELECT * FROM pet_v2_outings WHERE user_id=? AND id=? FOR UPDATE', (int(user_id), outing_id)) as c:
        return _row(await c.fetchone())


async def outings_today(db, user_id, day):
    async with db.execute('SELECT COUNT(*) AS n FROM pet_v2_outings WHERE user_id=? AND day=?', (int(user_id),day)) as c:
        return int((await c.fetchone())['n'])


async def parts(db, user_id):
    async with db.execute('SELECT amount FROM pet_v2_parts WHERE user_id=?', (int(user_id),)) as c:
        r = await c.fetchone(); return int(r['amount']) if r else 0


async def add_parts(db, user_id, amount):
    await db.execute('INSERT INTO pet_v2_parts(user_id,amount) VALUES (?,0) ON CONFLICT DO NOTHING',(int(user_id),))
    await db.execute('UPDATE pet_v2_parts SET amount=amount+? WHERE user_id=?',(int(amount),int(user_id)))


async def save_gear(db, user_id, pet_id, value):
    await db.execute('UPDATE pet_v2_state SET equipment=?::jsonb WHERE user_id=? AND pet_id=?', (json.dumps(value),int(user_id),int(pet_id)))


async def create_outing(db, user_id, pet_id, outing_id, day, state):
    await db.execute('INSERT INTO pet_v2_outings(id,user_id,pet_id,day,state) VALUES (?,?,?,?,?::jsonb)',
                     (outing_id,int(user_id),int(pet_id),day,json.dumps(state)))


async def save_outing(db, outing_id, state):
    await db.execute('UPDATE pet_v2_outings SET state=?::jsonb,active=? WHERE id=?',
                     (json.dumps(state),state['status']=='active',outing_id))
