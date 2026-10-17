"""Offline operator release. Default is read-only; never run at app startup.

One-time capital issuance is explicitly approved by the owner on 2026-10-17.
No player wallet is debited. Further trading has no automatic funding writer.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.coin_market_v2 import MORA, RULES_VERSION
from infrastructure.database import create_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import coin_market_v2 as repo, system_flags
from services import coin_market_v2 as service

AUTHORIZATION = "project_owner:2026-10-17:explicit_120000_mora_one_time_issuance"


async def verify(db):
    _, secret_id = service.configuration()
    funding = await db.connection.fetchrow(
        "SELECT source,mora,metadata FROM coin_market_v2_funding WHERE id='initial-v2'"
    )
    if not funding or int(funding['mora']) != 120000 * MORA:
        raise RuntimeError('Missing exact initial issuance')
    metadata = repo.decode(funding['metadata'])
    if metadata.get('kind') != 'one_time_system_issuance' or metadata.get('authorization') != AUTHORIZATION:
        raise RuntimeError('Initial issuance authorization does not match owner approval')
    rows = await repo.rows(db, 0)
    expected = {c[0] for c in service.SYSTEM_COINS}
    if not expected.issubset({r['id'] for r in rows}):
        raise RuntimeError('Missing system coins')
    for row in rows:
        if row['secret_id'] != secret_id or row['rules'] != RULES_VERSION:
            raise RuntimeError('Market secret/rules mismatch')
        _, book, _, _ = service.checked(row)
        await repo.reconcile(db, row, book)
    if not await repo.peek_fund(db):
        raise RuntimeError('Conversion fund missing')
    return {'coins': len(rows), 'initial_issuance_mora': '120000',
            'authorization': AUTHORIZATION, 'secret_id': secret_id}


async def run(args):
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            db = PGAdapter(conn)
            if args.prepare:
                if args.authorize_system_issuance_mora != 120000:
                    raise RuntimeError('Preparation requires explicit --authorize-system-issuance-mora 120000')
                service.configuration()  # Never initialize a market without its persistent secret.
                await repo.ensure_tables(db)
                await system_flags.ensure_table(db)
                if not await conn.fetchval("SELECT 1 FROM coin_market_v2_funding WHERE id='initial-v2'"):
                    await service.bootstrap(db, source='owner_authorized_initial_system_issuance',
                                            issuance_authorization=AUTHORIZATION)
            async with conn.transaction():
                await repo.catalogue_lock(db)
                status = await verify(db)
                if args.enable:
                    # One transaction: entry and shorts become available together.
                    expected = {'coin_market_v2': True, 'coin_market_v2_shorts': True,
                        'economy_player_exchange_v1': False, 'economy_player_exchange_shorts_v1': False}
                    rows = await conn.fetch("SELECT key,enabled FROM system_flags WHERE key=ANY($1::text[]) FOR UPDATE", list(expected))
                    if {row['key'] for row in rows} != set(expected):
                        raise RuntimeError('Missing release flags; run --prepare first')
                    await conn.execute("UPDATE system_flags SET enabled=1 WHERE key IN ('coin_market_v2','coin_market_v2_shorts')")
                    await conn.execute("UPDATE system_flags SET enabled=0 WHERE key IN ('economy_player_exchange_v1','economy_player_exchange_shorts_v1')")
                    for key, value in expected.items():
                        if await system_flags.is_enabled(db, key) != value:
                            raise RuntimeError('Release flag verification failed')
                status['enabled'] = await system_flags.is_enabled(db, 'coin_market_v2')
                status['shorts_enabled'] = await system_flags.is_enabled(db, 'coin_market_v2_shorts')
            print(json.dumps(status, ensure_ascii=False))
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--authorize-system-issuance-mora', type=int)
    parser.add_argument('--enable', action='store_true')
    asyncio.run(run(parser.parse_args()))
