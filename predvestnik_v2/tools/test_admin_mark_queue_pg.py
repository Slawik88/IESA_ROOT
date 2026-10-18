"""Real PostgreSQL proof for bounded, paged mark review queues."""
import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN', '1:offline-test')
os.environ.setdefault('DATABASE_URL', 'postgresql://offline@127.0.0.1:1/offline')
import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import marks_v1
from services import admin_people


async def run(dsn):
    assert urlparse(dsn).hostname in {'localhost', '127.0.0.1', '::1'}
    conn = await asyncpg.connect(dsn)
    await conn.execute('SET search_path TO predvestnik, public')
    tx = conn.transaction()
    await tx.start()
    try:
        db = PGAdapter(conn)
        await marks_v1.ensure_tables(db)
        for i in range(37):
            await db.execute('INSERT INTO users(user_tg_id,user_tg_username,bot_rank,deleted_at) VALUES (?,?,?,?)',
                             (984100 + i, f'regalia_qof_{i}', 1 if i == 35 else 3, datetime(2026, 1, 1) if i == 36 else None))
        one = await admin_people.search(db, 'regalia_qof_', flt='needs_staff_mark')
        two = await admin_people.search(db, 'regalia_qof_', flt='needs_staff_mark', offset=one['next_offset'])
        assert one['total'] == 35 and len(one['players']) == 30 and len(two['players']) == 5
        assert two['next_offset'] is None
        assert not {p['id'] for p in one['players']} & {p['id'] for p in two['players']}
        await marks_v1.grant(db, 984100, 'helper', 1, 'reviewed')
        await marks_v1.grant(db, 984101, 'founder', 1, 'reviewed')
        assert (await admin_people.search(db, 'regalia_qof_', flt='needs_staff_mark'))['total'] == 34
        assert (await admin_people.search(db, 'regalia_qof_', flt='manual_marks'))['total'] == 2
        assert (await admin_people.search(db, 'regalia_qof_', flt='no_manual_marks'))['total'] == 34
        held = await admin_people.search(db, 'regalia_qof_', flt='marked:founder')
        assert [p['id'] for p in held['players']] == [984101]
        missing = await admin_people.search(db, 'regalia_qof_', flt='missing:founder')
        assert missing['total'] == 35
        assert (await admin_people.search(db, '984101', flt='marked:founder'))['total'] == 1
        assert (await admin_people.search(db, 'regalia_qof_%', flt='manual_marks'))['total'] == 0, 'wildcards remain literal'
        assert not admin_people.is_mark_filter("marked:founder' OR TRUE --")
        assert not admin_people.is_mark_filter('marked:veteran'), 'manual queue catalog excludes earned marks'
        print('admin mark queue: roles, deleted users, mark filters, literal search and pagination OK')
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', required=True)
    asyncio.run(run(parser.parse_args().dsn))
