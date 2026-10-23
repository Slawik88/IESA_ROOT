"""Real local PostgreSQL proof: distinct casino pools, legacy principal and atomic cashout.

Uses synthetic owners only. Run after bootstrap_test_db.py with --dsn on loopback.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg
from core import casino_v1 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import casino_v1 as repo
from services import casino_v1 as casino


async def refused(coro, message=''):
    try:
        await coro
    except casino.CasinoError as error:
        assert message in str(error), error
    else:
        raise AssertionError('unexpected successful mutation')


async def connect(dsn):
    conn = await asyncpg.connect(dsn, server_settings={'search_path': 'predvestnik,public'})
    return conn, PGAdapter(conn)


async def run(dsn):
    assert urlparse(dsn).hostname in {'127.0.0.1', 'localhost', '::1'}
    conn, db = await connect(dsn)
    base = 993_000_000 + uuid4().int % 100_000
    owners = [base + i for i in range(20)]

    async def money(uid):
        return await conn.fetchval('SELECT user_balance_mora FROM users WHERE user_tg_id=$1', uid)

    async def reset(uid, chips, real):
        await fixture_write('INSERT INTO casino_v1_wallets(user_id,chips,redeemable_chips,wallet_version) '
                           'VALUES($1,$2,$3,2) ON CONFLICT(user_id) DO UPDATE '
                           'SET chips=$2,redeemable_chips=$3,wallet_version=2', uid, chips, real)

    async def state(uid):
        row = await repo.wallet(db, uid)
        if row:
            assert 0 <= row['redeemable_chips'] <= row['chips'], row
        return casino._wallet_view(row, await repo.today(db))

    async def snapshot(uid):
        return (tuple(await conn.fetchrow('SELECT chips,redeemable_chips FROM casino_v1_wallets WHERE user_id=$1', uid)),
                await money(uid),
                await conn.fetchval('SELECT COUNT(*) FROM economic_operations WHERE user_id=$1', uid),
                await conn.fetchval('SELECT COUNT(*) FROM casino_v1_withdrawals WHERE user_id=$1', uid))

    async def parallel(calls):
        pool = [await connect(dsn) for _ in calls]
        try:
            return await asyncio.gather(*(call(adb) for call, (_, adb) in zip(calls, pool)), return_exceptions=True)
        finally:
            for connection, _ in pool:
                await connection.close()

    async def fixture_write(sql, *args):
        async with conn.transaction():
            await conn.execute("SELECT set_config('predvestnik.casino_wallet_version','2',true)")
            return await conn.execute(sql, *args)

    try:
        await repo.ensure_tables(db)
        initialized = await parallel([repo.ensure_tables, repo.ensure_tables])
        assert initialized == [None, None], initialized
        for uid in owners:
            await conn.execute('INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,100000)', uid)
        uid = owners[0]
        gift = await casino.claim_gift(db, uid)
        assert gift['wallet']['bonus'] == 1000 and gift['wallet']['redeemable'] == 0
        # A bonus jackpot is still bonus. It cannot be converted by switching modes.
        with patch('services.casino_v1.secrets.randbelow', return_value=28):
            bonus = await casino.play(db, uid, game='slots', stake=100, params={}, action_id='bonus-jackpot')
        assert bonus['round']['mult'] == 30000 and bonus['wallet']['bonus'] == 30900
        assert bonus['wallet']['redeemable'] == 0 and await money(uid) == 100000
        await refused(casino.withdraw(db, uid, chips=1, action_id='free-withdraw'), 'с выводом')
        await refused(casino.play(db, uid, game='dice', stake=100, params={'chance': 50},
                                  funds='redeemable', action_id='free-real-bet'), 'выбранном балансе')
        buy = await casino.buy_chips(db, uid, mora=500, action_id='fresh-purchase')
        assert buy['chips'] == 500 and buy['wallet']['redeemable'] == 500 and buy['wallet']['bonus'] == 30900
        assert await money(uid) == 99500
        with patch('services.casino_v1.secrets.randbelow', return_value=1):
            real = await casino.play(db, uid, game='wheel', stake=100, params={},
                                     funds='redeemable', action_id='real-wheel-win')
        assert real['wallet']['redeemable'] == 550 and real['wallet']['bonus'] == 30900
        with patch('services.casino_v1.secrets.randbelow', return_value=0):
            lost = await casino.play(db, uid, game='wheel', stake=100, params={}, action_id='bonus-wheel-loss')
        assert lost['wallet']['redeemable'] == 550 and lost['wallet']['bonus'] == 30800
        replay = await casino.play(db, uid, game='wheel', stake=100, params={},
                                   funds='redeemable', action_id='real-wheel-win')
        assert replay['replayed'] and replay['round'] == real['round']
        await refused(casino.play(db, uid, game='wheel', stake=100, params={},
                                  action_id='real-wheel-win'), 'другой ставки')
        await reset(uid, 1000, 1000)
        await refused(casino.play(db, uid, game='wheel', stake=100, params={},
                                  action_id='no-bonus-fallback'), 'выбранном балансе')
        assert (await state(uid))['redeemable'] == 1000
        # During rolling replacement an obsolete worker cannot debit Mora or
        # mutate either pool. Its failed wallet write rolls the whole tx back.
        legacy_conn, _ = await connect(dsn)
        before_legacy = await snapshot(uid)
        try:
            for sql in ("UPDATE casino_v1_wallets SET chips=chips+1000 WHERE user_id=$1",
                        "INSERT INTO casino_v1_wallets(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING"):
                try:
                    async with legacy_conn.transaction():
                        await legacy_conn.execute('UPDATE users SET user_balance_mora=user_balance_mora-100 WHERE user_tg_id=$1', uid)
                        await legacy_conn.execute(sql, uid)
                except asyncpg.ObjectNotInPrerequisiteStateError:
                    pass
                else:
                    raise AssertionError('obsolete casino writer crossed the cashout migration fence')
                assert await snapshot(uid) == before_legacy
            # A modern transaction must not leave permission on a pooled session.
            await casino.buy_chips(db, uid, mora=100, action_id='writer-fence-modern')
            try:
                await conn.execute('UPDATE casino_v1_wallets SET chips=chips+1 WHERE user_id=$1', uid)
            except asyncpg.ObjectNotInPrerequisiteStateError:
                pass
            else:
                raise AssertionError('writer permission leaked outside its transaction')
            before_rollback = await snapshot(uid)
            try:
                async with conn.transaction():
                    await repo.lock_wallet(db, uid)
                    raise RuntimeError('injected transaction rollback')
            except RuntimeError:
                pass
            assert await snapshot(uid) == before_rollback
            try:
                await conn.execute('UPDATE casino_v1_wallets SET chips=chips+1 WHERE user_id=$1', uid)
            except asyncpg.ObjectNotInPrerequisiteStateError:
                pass
            else:
                raise AssertionError('writer permission leaked after rollback')
            await reset(uid, 1000, 1000)
        finally:
            await legacy_conn.close()
        # Withdraw is a transfer: replay works even after spending the remaining balance.
        before = await money(uid)
        withdrawal = await casino.withdraw(db, uid, chips=1000, action_id='withdraw-once')
        again = await casino.withdraw(db, uid, chips=1000, action_id='withdraw-once')
        assert withdrawal['wallet']['chips'] == 0 and again['replayed'] and again['mora'] == 1000
        assert await money(uid) == before + 1000
        await refused(casino.withdraw(db, uid, chips=500, action_id='withdraw-once'), 'другой суммы')
        for bad in (0, -1, True, 1.0, '1', rules.MAX_EXCHANGE + 1):
            await refused(casino.withdraw(db, uid, chips=bad, action_id='invalid-amount'), 'положительное')
        await reset(uid, 1000, 1000)
        # Faults before ledger credit and after ledger credit must roll back every write.
        original = await snapshot(uid)
        for target in ('services.casino_v1.economy_ledger.apply_balance_change',
                       'services.casino_v1.repo.insert_withdrawal'):
            with patch(target, side_effect=RuntimeError('injected cashout failure')):
                try:
                    await casino.withdraw(db, uid, chips=250, action_id='rollback-cashout')
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('fault did not reach outer transaction')
            assert await snapshot(uid) == original, target
        await casino.withdraw(db, uid, chips=250, action_id='rollback-cashout')
        assert await money(uid) == original[1] + 250
        # Legacy projection is read-only; migration is finite, one-time and preserves total chips.
        for index, (chips, paid, expected) in enumerate(((1000, 0, 0), (0, 100, 0), (9, 100, 0),
                                                       (105, 100, 10), (1000, 100, 100), (10000, 100, 100)), 1):
            legacy = owners[index]
            await fixture_write('INSERT INTO casino_v1_wallets(user_id,chips,wallet_version) VALUES($1,$2,1)', legacy, chips)
            if paid:
                await repo.insert_purchase(db, purchase_id=uuid4().hex, user_id=legacy, action_id='old-purchase',
                                           mora=paid, chips=paid * 10, operation_id='historical-ledger')
            view = await state(legacy)
            assert (view['chips'], view['redeemable'], view['bonus']) == (chips, expected, chips - expected)
            assert await conn.fetchval('SELECT wallet_version FROM casino_v1_wallets WHERE user_id=$1', legacy) == 1
            async with conn.transaction():
                migrated = await repo.lock_wallet(db, legacy)
            assert migrated['wallet_version'] == 2 and migrated['redeemable_chips'] == expected
            await fixture_write('UPDATE casino_v1_wallets SET chips=chips+10000 WHERE user_id=$1', legacy)
            async with conn.transaction():
                still = await repo.lock_wallet(db, legacy)
            assert still['redeemable_chips'] == expected and still['chips'] == chips + 10000
            if paid:
                before = await snapshot(legacy)
                old = await casino.buy_chips(db, legacy, mora=paid, action_id='old-purchase')
                assert old['replayed'] and old['chips'] == paid * 10
                assert await snapshot(legacy) == before, 'old purchase replay must never be repriced or recredited'
        legacy = owners[5]
        await casino.withdraw(db, legacy, chips=100, action_id='legacy-principal')
        await casino.claim_gift(db, legacy)
        assert (await state(legacy))['redeemable'] == 0, 'cashout and a new gift must never reset migration compensation'
        # Old receipt without funds remains bonus; changing its mode/chance is a conflict.
        legacy = owners[1]
        await repo.insert_round(db, round_id=uuid4().hex, user_id=legacy, action_id='old-dice-receipt', game='dice',
                                stake=10, mult=106, payout=10, detail={'roll': 1, 'chance': 90},
                                chips_after=1000, policy_version='casino-v1-2026-10-22')
        old = await casino.play(db, legacy, game='dice', stake=10, params={'chance': 90}, action_id='old-dice-receipt')
        assert old['replayed']
        await refused(casino.play(db, legacy, game='dice', stake=10, params={'chance': 90},
                                  funds='redeemable', action_id='old-dice-receipt'), 'другой ставки')
        await refused(casino.play(db, legacy, game='dice', stake=10, params={'chance': 75},
                                  action_id='old-dice-receipt'), 'другой ставки')
        # First concurrent buyers migrate once, then add 1:1 paid funds exactly once per ID.
        racing = owners[8]
        await fixture_write('INSERT INTO casino_v1_wallets(user_id,chips,wallet_version) VALUES($1,1000,1)', racing)
        await repo.insert_purchase(db, purchase_id=uuid4().hex, user_id=racing, action_id='old-purchase',
                                   mora=100, chips=1000, operation_id='historical-ledger')
        results = await parallel([lambda adb: casino.buy_chips(adb, racing, mora=100, action_id='first-buyer-1'),
                                  lambda adb: casino.buy_chips(adb, racing, mora=100, action_id='first-buyer-2'),
                                  lambda adb: casino.buy_chips(adb, racing, mora=100, action_id='first-buyer-1')])
        assert all(isinstance(r, dict) for r in results), results
        view = await state(racing)
        assert (view['chips'], view['redeemable'], view['bonus']) == (1200, 300, 900)
        assert await money(racing) == 99800
        # Fresh first-use writers also do not accidentally enter the legacy migration.
        fresh = owners[9]
        results = await parallel([lambda adb: casino.claim_gift(adb, fresh),
                                  lambda adb: casino.buy_chips(adb, fresh, mora=100, action_id='fresh-first-buy')])
        assert all(isinstance(r, dict) for r in results), results
        assert (await state(fresh))['redeemable'] == 100 and (await state(fresh))['bonus'] == 1000
        # Buy then redeem without gambling conserves Mora and does not create a rate arbitrage.
        roundtrip = owners[10]
        before = await money(roundtrip)
        await casino.buy_chips(db, roundtrip, mora=1000, action_id='roundtrip-purchase')
        results = await parallel([lambda adb: casino.withdraw(adb, roundtrip, chips=1000, action_id='same-cashout'),
                                  lambda adb: casino.withdraw(adb, roundtrip, chips=1000, action_id='same-cashout')])
        assert all(isinstance(r, dict) for r in results) and sum(r['replayed'] for r in results) == 1, results
        assert await money(roundtrip) == before and (await state(roundtrip))['chips'] == 0
        # Concurrent withdrawals cannot spend the same funded chips twice.
        await reset(racing, 1000, 1000)
        before = await money(racing)
        results = await parallel([lambda adb: casino.withdraw(adb, racing, chips=750, action_id='withdraw-race-1'),
                                  lambda adb: casino.withdraw(adb, racing, chips=750, action_id='withdraw-race-2')])
        assert sum(isinstance(r, dict) for r in results) == 1 and sum(isinstance(r, casino.CasinoError) for r in results) == 1
        assert (await state(racing))['redeemable'] == 250 and await money(racing) == before + 750
        # Race buy, real bet and withdraw: total chips + Mora differs solely by the actual round net.
        await reset(racing, 1000, 1000)
        before = await money(racing)
        with patch('services.casino_v1.secrets.randbelow', return_value=0):
            results = await parallel([lambda adb: casino.withdraw(adb, racing, chips=1000, action_id='mixed-withdraw'),
                                      lambda adb: casino.buy_chips(adb, racing, mora=500, action_id='mixed-buy'),
                                      lambda adb: casino.play(adb, racing, game='wheel', stake=100, params={},
                                                              funds='redeemable', action_id='mixed-play')])
        assert all(isinstance(r, (dict, casino.CasinoError)) for r in results), results
        net = sum(r['round']['payout'] - r['round']['stake'] for r in results if isinstance(r, dict) and 'round' in r)
        view = await state(racing)
        assert view['chips'] == view['redeemable'] and view['bonus'] == 0
        assert await money(racing) + view['chips'] == before + 1000 + net
    finally:
        for table in ('casino_v1_rounds', 'casino_v1_purchases', 'casino_v1_withdrawals', 'casino_v1_wallets'):
            await conn.execute(f'DELETE FROM {table} WHERE user_id=ANY($1::bigint[])', owners)
        await conn.close()
    print('OK: casino cashout PostgreSQL — isolated pools, bonus jackpots noncashable, 1:1/replay, faults/rollback, '
          'legacy projection/principal/migration, concurrent first writers and withdraw/buy/play races')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', required=True)
    asyncio.run(run(parser.parse_args().dsn))
