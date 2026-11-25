"""Retire legacy wallet availability holds. Audit by default; no wallet credits.

The reserve was never debited from users. Clearing it changes availability only.
Apply requires the digest of an immediately reviewed audit and runs atomically.
Historical records remain queryable; new positive holds are blocked in PostgreSQL.
"""
import argparse
import asyncio
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infrastructure.database import create_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import admin_log
from services.auction import _restore_asset_escrow

REFERENCE = 'legacy_wallet_holds_retirement_v1'
ACTION = 'legacy_wallet_holds_retirement'


def encoded(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(',', ':'))


async def inventory(conn):
    reserves = [dict(r) for r in await conn.fetch(
        'SELECT user_id,reserved_mora FROM user_reserve WHERE reserved_mora IS DISTINCT FROM 0 ORDER BY user_id')]
    duels = [dict(r) for r in await conn.fetch(
        "SELECT * FROM duels WHERE status IN ('pending','processing') ORDER BY id")]
    lots = [dict(r) for r in await conn.fetch(
        "SELECT * FROM auction_lots WHERE status='active' ORDER BY id")]
    bids = [dict(r) for r in await conn.fetch(
        'SELECT * FROM auction_bids WHERE is_active=1 ORDER BY id')]
    ids = sorted({int(r['user_id']) for r in reserves} |
        {int(d[k]) for d in duels for k in ('challenger_id', 'challenged_id')} |
        {int(l['seller_id']) for l in lots} | {int(b['bidder_id']) for b in bids})
    users = [dict(r) for r in await conn.fetch(
        'SELECT user_tg_id,user_balance_mora,user_balance_zarniki,user_balance_diamonds,user_balance_dark_mora FROM users WHERE user_tg_id=ANY($1::bigint[]) ORDER BY user_tg_id', ids)]
    # Asset state is part of the reviewed digest, so changed/orphaned escrow
    # never silently creates items or takes a pet from another current owner.
    pets = [dict(r) for r in await conn.fetch(
        'SELECT id,owner_id,placement FROM pets WHERE id=ANY($1::bigint[]) ORDER BY id',
        [int(l['item_id_or_pet_id']) for l in lots if l['item_type']=='pet'])]
    lot_ids = [str(l['id']) for l in lots]
    settlements = [dict(r) for r in await conn.fetch(
        "SELECT id,user_id,reason_code,reference_id FROM economic_operations "
        "WHERE reference_type='auction_lot' AND reference_id=ANY($1::text[]) "
        "AND reason_code IN ('auction_buy','auction_sale') ORDER BY id", lot_ids)]
    settlement_logs = [dict(r) for r in await conn.fetch(
        "SELECT id,user_id,source,note FROM wallet_log WHERE source IN ('auction_buy','auction_sale') "
        "AND EXISTS (SELECT 1 FROM unnest($1::text[]) x WHERE note ~ ('lot='||x||'([^0-9]|$)')) ORDER BY id", lot_ids)]
    payload = dict(reserves=reserves, duels=duels, lots=lots, bids=bids,
                   wallets=users, pets=pets, settlements=settlements, settlement_logs=settlement_logs)
    return payload


def validate(payload):
    ids = {r['user_tg_id'] for r in payload['wallets']}
    pets = {r['id']: r for r in payload['pets']}
    if payload['settlements'] or payload['settlement_logs']:
        raise RuntimeError('Active lot has historical monetary settlement; investigate before asset return')
    for row in payload['reserves']:
        if row['reserved_mora'] is None:
            raise RuntimeError('NULL reserve requires explicit investigation')
        amount = Decimal(str(row['reserved_mora']))
        if not amount.is_finite() or amount < 0 or row['user_id'] not in ids:
            raise RuntimeError('Invalid/orphan reserve requires explicit investigation')
    for duel in payload['duels']:
        if duel['winner_id'] is not None or duel['resolved_at'] is not None or any(
            duel.get(k) not in (None, 0) for k in ('winner_gain', 'commission')):
            raise RuntimeError('Partially settled duel requires explicit investigation')
        if duel['challenger_id'] not in ids or duel['challenged_id'] not in ids:
            raise RuntimeError('Orphan duel participant')
    for lot in payload['lots']:
        if lot['seller_id'] not in ids:
            raise RuntimeError('Orphan auction seller')
        if lot['item_type'] == 'pet':
            pet = pets.get(lot['item_id_or_pet_id'])
            if not pet or pet['owner_id'] != lot['seller_id'] or pet['placement'] != 'auction':
                raise RuntimeError('Pet escrow ownership or placement mismatch')
        elif lot['item_type'] == 'inventory':
            parts = (lot['item_name'] or '').split('||', 1)
            if len(parts)!=2 or not parts[1].strip() or int(lot['quantity'] or 0)<=0:
                raise RuntimeError('Ambiguous item escrow: no reliable inventory identifier')
        else:
            raise RuntimeError('Unknown auction asset type')


async def wallet_totals(conn):
    return dict(await conn.fetchrow(
        "SELECT count(*) AS users,COALESCE(sum(user_balance_mora::numeric),0) AS mora,"
        "COALESCE(sum(user_balance_zarniki::numeric),0) AS zarniki,"
        "COALESCE(sum(user_balance_diamonds::numeric),0) AS diamonds,"
        "COALESCE(sum(user_balance_dark_mora::numeric),0) AS dark_mora FROM users"))


async def retire(conn, *, apply=False, expected_digest=None):
    async with conn.transaction(readonly=not apply, isolation='repeatable_read'):
        if apply:
            # Global order excludes old schedulers, callbacks, ordinary wallet
            # spends and asset changes throughout snapshot/return/assertions.
            await conn.execute("SET LOCAL lock_timeout='5s'")
            await conn.execute('LOCK TABLE auction_lots,auction_bids,duels,user_reserve,users,pets,inventory,admin_grant_log IN SHARE ROW EXCLUSIVE MODE')
        receipt = await conn.fetchrow(
            'SELECT id,reason FROM admin_grant_log WHERE action=$1 AND detail=$2 ORDER BY id', ACTION, REFERENCE)
        payload = await inventory(conn)
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        result = dict(applied=False, replayed=bool(receipt), digest=digest,
            wallet_credits='0', reserve_released=str(sum((Decimal(str(r['reserved_mora'])) if r['reserved_mora'] is not None else Decimal('NaN') for r in payload['reserves']), Decimal(0))),
            reserve_rows=len(payload['reserves']), open_duels=len(payload['duels']),
            active_lots=len(payload['lots']), active_bids=len(payload['bids']), inventory=payload)
        if receipt:
            if any(payload[k] for k in ('reserves','duels','lots','bids')):
                raise RuntimeError('Retirement receipt exists but new legacy liabilities appeared')
            return result
        try:
            validate(payload)
        except RuntimeError as exc:
            if apply:
                raise
            result['blocked_reason'] = str(exc)
            return result
        if not apply:
            return result
        if expected_digest != digest:
            raise RuntimeError('Audit changed: review a fresh read-only audit before apply')
        totals_before = await wallet_totals(conn)
        db = PGAdapter(conn)
        for lot in payload['lots']:
            await _restore_asset_escrow(db, lot)
        await conn.execute("UPDATE auction_lots SET status='cancelled' WHERE status='active'")
        await conn.execute('UPDATE auction_bids SET is_active=0 WHERE is_active=1')
        await conn.execute("UPDATE duels SET status='declined',resolved_at=NOW() WHERE status IN ('pending','processing')")
        await conn.execute('UPDATE user_reserve SET reserved_mora=0 WHERE reserved_mora IS DISTINCT FROM 0')
        # Keep rows as an archive for old audit tools; no active reader depends
        # on them. A check constraint also blocks forgotten writers/old workers.
        await conn.execute('ALTER TABLE user_reserve ADD CONSTRAINT legacy_wallet_holds_retired CHECK (reserved_mora IS NOT NULL AND reserved_mora=0)')
        await admin_log.add(db, 0, 0, ACTION, REFERENCE, 0,
            encoded(dict(owner_authorized=True, digest=digest, before=payload, global_wallet_totals=totals_before,
                         policy='cancel_unsettled_wagers_return_assets_no_wallet_credit')), 0, 0)
        after = await inventory(conn)
        if any(after[k] for k in ('reserves','duels','lots','bids')):
            # No open liabilities remain, so inventory() has no ids to select.
            raise RuntimeError('Legacy liabilities remain after retirement')
        wallets = [dict(r) for r in await conn.fetch(
            'SELECT user_tg_id,user_balance_mora,user_balance_zarniki,user_balance_diamonds,user_balance_dark_mora FROM users WHERE user_tg_id=ANY($1::bigint[]) ORDER BY user_tg_id',
            [r['user_tg_id'] for r in payload['wallets']])]
        if encoded(wallets) != encoded(payload['wallets']):
            raise RuntimeError('Unexpected wallet mutation: rollback retirement')
        totals_after = await wallet_totals(conn)
        if encoded(totals_before) != encoded(totals_after):
            raise RuntimeError('Global wallet conservation failed: rollback retirement')
        result['global_wallet_totals_before'] = totals_before
        result['global_wallet_totals_after'] = totals_after
        result['applied'] = True
        return result


async def main(args):
    pool = await create_pool()
    try:
        async with pool.acquire() as conn:
            print(encoded(await retire(conn, apply=args.apply, expected_digest=args.expected_digest)))
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-digest')
    args = parser.parse_args()
    if args.apply and not args.expected_digest:
        parser.error('--apply requires the reviewed --expected-digest')
    asyncio.run(main(args))
