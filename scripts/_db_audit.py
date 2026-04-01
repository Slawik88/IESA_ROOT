import asyncio, os, sys
sys.path.insert(0, 'PredvestnikBot')
DB_URL = os.environ.get('PREDVESTNIK_DATABASE_URL') or os.environ.get('DATABASE_URL') or ''
if not DB_URL:
    print('ERROR: DB_URL not set'); sys.exit(1)

import asyncpg

async def check():
    c = await asyncpg.connect(DB_URL)

    cols = await c.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name='user_mora' ORDER BY ordinal_position"
    )
    print('=== user_mora columns ===')
    for r in cols:
        print(f'  {r["column_name"]:20} {r["data_type"]}')

    rows = await c.fetch(
        'SELECT user_id, chat_id, balance, total_earned FROM user_mora WHERE balance > 0 LIMIT 15'
    )
    print(f'\nuser_mora rows with balance>0: {len(rows)} (first 15 shown)')
    for r in rows:
        print(f'  uid={r["user_id"]} chat={r["chat_id"]} bal={r["balance"]} earned={r["total_earned"]}')

    cnt = await c.fetchval('SELECT COUNT(*) FROM wallet_ledger')
    oldest = await c.fetchval('SELECT MIN(created_at) FROM wallet_ledger')
    newest = await c.fetchval('SELECT MAX(created_at) FROM wallet_ledger')
    print(f'\nwallet_ledger: {cnt} rows | oldest={oldest} | newest={newest}')

    adm = await c.fetch('SELECT chat_id FROM admin_groups')
    tst = await c.fetch('SELECT chat_id FROM test_chats')
    print(f'\nadmin_groups: {[r[0] for r in adm]}')
    print(f'test_chats:   {[r[0] for r in tst]}')

    users_cnt = await c.fetchval('SELECT COUNT(*) FROM users WHERE balance > 0')
    top = await c.fetch('SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 5')
    print(f'\nusers with balance>0: {users_cnt}')
    print('Top-5 balances:')
    for r in top:
        print(f'  uid={r["user_id"]} bal={r["balance"]}')

    await c.close()

asyncio.run(check())
