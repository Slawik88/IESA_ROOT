"""Star dust wallets and immutable income/VIP receipts, separate from tradable currencies."""
import json


async def ensure_tables(db):
    async with db.execute("SELECT to_regclass('star_dust_pet_coverage') IS NOT NULL AND EXISTS(SELECT 1 FROM pg_constraint WHERE conname='star_dust_vip_days_positive')") as c:
        if (await c.fetchone())[0]:return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('schema:star-dust-v1',0))")
        await db.execute('''CREATE TABLE IF NOT EXISTS star_dust_accounts(
            user_id BIGINT PRIMARY KEY, balance BIGINT NOT NULL DEFAULT 0 CHECK(balance>=0),
            pet_remainder BIGINT NOT NULL DEFAULT 0 CHECK(pet_remainder>=0 AND pet_remainder<18000000000),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
        await db.execute('''CREATE TABLE IF NOT EXISTS star_dust_income(
            user_id BIGINT NOT NULL, source_kind TEXT NOT NULL CHECK(source_kind IN ('chat','pet')),
            source_id TEXT NOT NULL, day DATE NOT NULL, amount INTEGER NOT NULL CHECK(amount>=0),
            raw_amount INTEGER NOT NULL CHECK(raw_amount>=amount), luck_micros INTEGER,
            snapshot JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id,source_kind,source_id),
            CHECK(luck_micros IS NULL OR luck_micros BETWEEN 0 AND 1000000))''')
        await db.execute('CREATE INDEX IF NOT EXISTS star_dust_income_day ON star_dust_income(user_id,day,source_kind)')
        await db.execute('''CREATE TABLE IF NOT EXISTS star_dust_vip_receipts(
            id TEXT PRIMARY KEY,user_id BIGINT NOT NULL,action_id TEXT NOT NULL,
            days INTEGER NOT NULL CHECK(days>0), cost BIGINT NOT NULL CHECK(cost>0),
            expires_before TIMESTAMPTZ,expires_after TIMESTAMPTZ NOT NULL,
            policy_version TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(user_id,action_id))''')
        await db.execute('ALTER TABLE star_dust_accounts ADD COLUMN IF NOT EXISTS pet_remainder BIGINT NOT NULL DEFAULT 0 CHECK(pet_remainder>=0 AND pet_remainder<18000000000)')
        await db.execute('ALTER TABLE star_dust_vip_receipts DROP CONSTRAINT IF EXISTS star_dust_vip_receipts_days_check')
        await db.execute('ALTER TABLE star_dust_vip_receipts ALTER COLUMN cost TYPE BIGINT')
        await db.execute("""DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='star_dust_vip_days_positive' AND conrelid='star_dust_vip_receipts'::regclass) THEN
            ALTER TABLE star_dust_vip_receipts ADD CONSTRAINT star_dust_vip_days_positive CHECK(days>0); END IF; END $$""")
        await db.execute('''CREATE TABLE IF NOT EXISTS star_dust_pet_coverage(
            user_id BIGINT NOT NULL,run_id TEXT NOT NULL,starts_at TIMESTAMPTZ NOT NULL,ends_at TIMESTAMPTZ NOT NULL,
            rate INTEGER NOT NULL CHECK(rate IN (1,10)),units BIGINT NOT NULL CHECK(units>=0),
            PRIMARY KEY(user_id,run_id),CHECK(ends_at>=starts_at))''')
        await db.execute('CREATE INDEX IF NOT EXISTS star_dust_pet_overlap ON star_dust_pet_coverage(user_id,ends_at,starts_at)')
        await db.execute('CREATE INDEX IF NOT EXISTS star_dust_vip_window ON star_dust_vip_receipts(user_id,created_at)')
        await db.execute("""CREATE OR REPLACE FUNCTION reject_star_dust_receipt_rewrite() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Star dust receipts are append-only'; END $$""")
        for table,name in (('star_dust_income','star_dust_income_append_only'),('star_dust_vip_receipts','star_dust_vip_append_only'),('star_dust_pet_coverage','star_dust_pet_append_only')):
            await db.execute(f"""DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='{name}' AND tgrelid='{table}'::regclass) THEN
                CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_star_dust_receipt_rewrite();
                END IF; END $$""")


async def clock(db):
    async with db.execute("SELECT NOW() AS now,(NOW() AT TIME ZONE 'UTC')::date AS day") as c:return dict(await c.fetchone())


async def lock_user(db,uid):
    await db.execute('SELECT pg_advisory_xact_lock(?)',(int(uid),))
    await db.execute('INSERT INTO star_dust_accounts(user_id) VALUES(?) ON CONFLICT DO NOTHING',(int(uid),))
    async with db.execute('SELECT balance FROM star_dust_accounts WHERE user_id=? FOR UPDATE',(int(uid),)) as c:return int((await c.fetchone())[0])


async def balance(db,uid):
    async with db.execute('SELECT balance FROM star_dust_accounts WHERE user_id=?',(int(uid),)) as c:
        row=await c.fetchone()
    return int(row[0]) if row else 0


async def income(db,uid,kind,source_id):
    async with db.execute('SELECT * FROM star_dust_income WHERE user_id=? AND source_kind=? AND source_id=?',(int(uid),kind,source_id)) as c:
        row=await c.fetchone()
    return dict(row) if row else None


async def pet_today(db,uid,day):
    async with db.execute("SELECT COALESCE(SUM(amount),0) FROM star_dust_income WHERE user_id=? AND source_kind='pet' AND day=?",(int(uid),day)) as c:return int((await c.fetchone())[0])


async def grant(db,*,uid,kind,source_id,day,amount,raw,luck=None,snapshot=None):
    await db.execute('INSERT INTO star_dust_income(user_id,source_kind,source_id,day,amount,raw_amount,luck_micros,snapshot) VALUES(?,?,?,?,?,?,?,?::jsonb)',
                     (int(uid),kind,source_id,day,int(amount),int(raw),luck,json.dumps(snapshot or {},ensure_ascii=False)))
    await db.execute('UPDATE star_dust_accounts SET balance=balance+?,updated_at=NOW() WHERE user_id=?',(int(amount),int(uid)))


async def vip_receipt(db,uid,action_id):
    async with db.execute('SELECT * FROM star_dust_vip_receipts WHERE user_id=? AND action_id=?',(int(uid),action_id)) as c:
        row=await c.fetchone()
    return dict(row) if row else None


async def debit(db,uid,cost):
    async with db.execute('UPDATE star_dust_accounts SET balance=balance-?,updated_at=NOW() WHERE user_id=? AND balance>=? RETURNING balance',(cost,int(uid),cost)) as c:
        row=await c.fetchone()
    return int(row[0]) if row else None


async def save_vip(db,*,receipt_id,uid,action_id,days,cost,before,after,version):
    await db.execute('INSERT INTO star_dust_vip_receipts(id,user_id,action_id,days,cost,expires_before,expires_after,policy_version) VALUES(?,?,?,?,?,?::text::timestamptz,?::text::timestamptz,?)',
                     (receipt_id,int(uid),action_id,days,cost,before.isoformat() if before else None,after.isoformat(),version))


async def pet_remainder(db,uid):
    async with db.execute('SELECT pet_remainder FROM star_dust_accounts WHERE user_id=?',(int(uid),)) as c:
        r=await c.fetchone()
    return int(r[0]) if r else 0


async def overlaps(db,uid,start,end):
    async with db.execute('''SELECT starts_at,ends_at,rate FROM star_dust_pet_coverage
        WHERE user_id=? AND starts_at<?::text::timestamptz AND ends_at>?::text::timestamptz''',
        (int(uid),end.isoformat(),start.isoformat())) as c:return [dict(r) for r in await c.fetchall()]


async def save_coverage(db,uid,run_id,start,end,rate,units,remainder):
    await db.execute('INSERT INTO star_dust_pet_coverage(user_id,run_id,starts_at,ends_at,rate,units) VALUES(?,?,?::text::timestamptz,?::text::timestamptz,?,?)',
                     (int(uid),str(run_id),start.isoformat(),end.isoformat(),int(rate),int(units)))
    await db.execute('UPDATE star_dust_accounts SET pet_remainder=? WHERE user_id=?',(int(remainder),int(uid)))
