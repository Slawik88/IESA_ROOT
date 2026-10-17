"""Narrow operator recovery of an interrupted retired duel; read-only by default.

No wallet credits/debits. Refuse ambiguous holds instead of clearing all reserves.
"""
import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.database import create_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import admin_log


async def recover(conn, *, duel_id, challenger_id, challenged_id, expected_reserve, apply=False):
    expected = Decimal(str(expected_reserve))
    if not expected.is_finite() or expected <= 0:
        raise ValueError('Expected reserve must be positive')
    reference = f'legacy_duel:{duel_id}:challenger_reserve:{challenger_id}'
    async with conn.transaction(readonly=not apply):
        suffix = ' FOR UPDATE' if apply else ''
        duel = await conn.fetchrow('SELECT * FROM duels WHERE id=$1' + suffix, duel_id)
        if not duel or (duel['challenger_id'],duel['challenged_id']) != (challenger_id,challenged_id):
            raise RuntimeError('Duel participants do not match')
        if Decimal(str(duel['stake'])) != expected:
            raise RuntimeError('Stake differs from the reviewed reserve')
        old = await conn.fetchrow("SELECT id FROM admin_grant_log WHERE action='legacy_duel_reserve_release' AND target_id=$1 AND detail=$2",challenger_id,reference)
        if old:
            if duel['status'] != 'declined':
                raise RuntimeError('Recovery receipt and duel status disagree')
            return {'applied':False,'replayed':True,'audit_id':old['id'],'duel_id':duel_id}
        if duel['status'] != 'processing' or duel['winner_id'] is not None or duel['resolved_at'] is not None:
            raise RuntimeError('Duel is not an unresolved interrupted processing duel')
        if any(duel.get(key) not in (None,0) for key in ('winner_gain','commission')):
            raise RuntimeError('Partial duel result requires manual review')
        if not await conn.fetchval("SELECT created_at < NOW()-INTERVAL '30 days' FROM duels WHERE id=$1",duel_id):
            raise RuntimeError('Duel is too recent for legacy recovery')
        ids=sorted([challenger_id,challenged_id])
        users=await conn.fetch('SELECT user_tg_id,user_balance_mora FROM users WHERE user_tg_id=ANY($1::bigint[]) ORDER BY user_tg_id'+suffix,ids)
        if len(users)!=2:
            raise RuntimeError('Both participants must exist')
        wallets={r['user_tg_id']:str(r['user_balance_mora']) for r in users}
        reserves=await conn.fetch('SELECT user_id,reserved_mora FROM user_reserve WHERE user_id=ANY($1::bigint[]) ORDER BY user_id'+suffix,ids)
        held={r['user_id']:Decimal(str(r['reserved_mora'])) for r in reserves}
        if held.get(challenger_id,Decimal(0)) != expected or held.get(challenged_id,Decimal(0)) != 0:
            raise RuntimeError('Ambiguous participant reserves; manual review required')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM duels WHERE id<>$1 AND status IN ('pending','processing') AND (challenger_id=ANY($2::bigint[]) OR challenged_id=ANY($2::bigint[])))",duel_id,ids):
            raise RuntimeError('Another unresolved duel exists')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM auction_bids b JOIN auction_lots l ON l.id=b.lot_id WHERE b.bidder_id=ANY($1::bigint[]) AND b.is_active=1 AND l.status='active')",ids):
            raise RuntimeError('Active auction liabilities exist')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM wallet_log WHERE user_id=ANY($1::bigint[]) AND source IN ('duel_win','duel_loss') AND created_at BETWEEN $2::timestamp-INTERVAL '1 day' AND $2::timestamp+INTERVAL '1 day')",ids,duel['created_at']):
            raise RuntimeError('Historical duel wallet settlement requires manual review')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM economic_operations WHERE user_id=ANY($1::bigint[]) AND (source_type='duel' OR reason_code IN ('duel_win','duel_loss')) AND created_at BETWEEN $2::timestamp-INTERVAL '1 day' AND $2::timestamp+INTERVAL '1 day')",ids,duel['created_at']):
            raise RuntimeError('Historical economic settlement requires manual review')
        result={'applied':False,'duel_id':duel_id,'challenger_id':challenger_id,'reserve_before':str(expected),'reserve_after':'0','wallets_unchanged':wallets}
        if apply:
            changed=await conn.fetchval('UPDATE user_reserve SET reserved_mora=reserved_mora-$2 WHERE user_id=$1 AND reserved_mora=$2 RETURNING user_id',challenger_id,float(expected))
            if changed != challenger_id:
                raise RuntimeError('Reviewed reserve changed')
            await conn.execute("UPDATE duels SET status='declined',resolved_at=NOW() WHERE id=$1",duel_id)
            await admin_log.add(PGAdapter(conn),0,challenger_id,'legacy_duel_reserve_release',reference,float(expected),json.dumps({'reason':'owner_reported_wallet_exchange_mismatch','duel_created_at':str(duel['created_at']),'wallets_before':wallets,'other_participant_reserve':'0','no_active_auction_or_other_duel':True}),float(expected),0)
            after=await conn.fetch('SELECT user_tg_id,user_balance_mora FROM users WHERE user_tg_id=ANY($1::bigint[]) ORDER BY user_tg_id',ids)
            if {r['user_tg_id']:str(r['user_balance_mora']) for r in after} != wallets:
                raise RuntimeError('Unexpected wallet mutation')
            result['applied']=True
        return result


async def main(args):
    pool=await create_pool()
    try:
        async with pool.acquire() as conn:
            print(json.dumps(await recover(conn,duel_id=args.duel_id,challenger_id=args.challenger_id,challenged_id=args.challenged_id,expected_reserve=args.expected_reserve,apply=args.apply)))
    finally:
        await pool.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duel-id',type=int,required=True)
    parser.add_argument('--challenger-id',type=int,required=True)
    parser.add_argument('--challenged-id',type=int,required=True)
    parser.add_argument('--expected-reserve',required=True)
    parser.add_argument('--apply',action='store_true')
    asyncio.run(main(parser.parse_args()))
