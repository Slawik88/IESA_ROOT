"""Real PostgreSQL proof for assignments and atomic one-time quest rewards."""
from __future__ import annotations
import argparse, asyncio, pathlib, sys
from urllib.parse import urlparse
import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import quests_v1 as repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import system_flags
from services import quests_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {'postgres', 'postgresql'} or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise argparse.ArgumentTypeError('only a loopback PostgreSQL DSN is allowed')
    return value


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    await chest_repo.ensure_tables(db)
    await system_flags.ensure_table(db)
    tx = conn.transaction()
    await tx.start()
    try:
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='content_chests_v1'")
        bootstrap_sources = await quests_v1.available_sources(db, user_id=976298)
        assert 'chests' not in bootstrap_sources, "a player without a key must not receive a chest quest"
        user = 976201
        sources = frozenset({'rhythm', 'minesweeper'})
        unavailable = await quests_v1.overview(db, user_id=976299, vip_active=False, sources=frozenset())
        assert unavailable['daily']['quests'] == [] and unavailable['weekly']['quests'] == []
        assert unavailable['rerolls']['remaining'] == 0 and not unavailable['completion']['daily']
        initial = await quests_v1.overview(db, user_id=user, vip_active=False, sources=sources)
        assert len(initial['daily']['quests']) == 4 and len(initial['weekly']['quests']) == 5
        assert len({q['metric'] for q in initial['daily']['quests']}) == 4
        assert len({q['lane'] for q in initial['daily']['quests']}) == 4
        assert len({q['metric'] for q in initial['weekly']['quests']}) == 5
        assert all(q['source'] in {'any_game', 'rhythm', 'minesweeper'} for period in ('daily', 'weekly') for q in initial[period]['quests'])
        assert sum(q['source'] == 'any_game' for q in initial['daily']['quests']) == 1
        assert sum(q['source'] == 'any_game' for q in initial['weekly']['quests']) == 1
        assert max(sum(q['source'] == source for q in initial['weekly']['quests']) for source in sources) == 2
        assert initial['rerolls'] == {'used': 0, 'limit': 2, 'remaining': 2}
        first = initial['daily']['quests'][0]
        changed = await quests_v1.reroll(db, user_id=user, vip_active=False, period='daily', slot=first['slot'], action_id='daily-reroll-a', sources=sources)
        after = next(q for q in changed['daily']['quests'] if q['slot'] == first['slot'])
        assert after['id'] != first['id'] and changed['rerolls']['used'] == 1
        assert after['metric'] != first['metric'] and after['lane'] != first['lane']
        replay = await quests_v1.reroll(db, user_id=user, vip_active=False, period='daily', slot=first['slot'], action_id='daily-reroll-a', sources=sources)
        assert replay['idempotent_replay'] and replay['rerolls']['used'] == 1
        try:
            await quests_v1.reroll(db, user_id=user, vip_active=False, period='weekly', slot=0, action_id='daily-reroll-a', sources=sources)
        except quests_v1.QuestConflict:
            pass
        else:
            raise AssertionError('action id conflict must fail')
        await quests_v1.reroll(db, user_id=user, vip_active=False, period='weekly', slot=0, action_id='weekly-reroll-b', sources=sources)
        try:
            await quests_v1.reroll(db, user_id=user, vip_active=False, period='weekly', slot=1, action_id='weekly-reroll-c', sources=sources)
        except quests_v1.QuestConflict:
            pass
        else:
            raise AssertionError('standard reroll limit must fail closed')
        metric = changed['daily']['quests'][0]['metric']
        before = next(q for q in changed['daily']['quests'] if q['metric'] == metric)
        advanced = await quests_v1.record_metric(db, user_id=user, metric=metric, event_id='terminal-run-1', vip_active=False, sources=sources)
        progressed = next(q for q in advanced['daily']['quests'] if q['slot'] == before['slot'])
        assert progressed['progress'] == min(before['target'], before['progress'] + 1)
        duplicate = await quests_v1.record_metric(db, user_id=user, metric=metric, event_id='terminal-run-1', vip_active=False, sources=sources)
        replayed = next(q for q in duplicate['daily']['quests'] if q['slot'] == before['slot'])
        assert replayed['progress'] == progressed['progress']
        for period, key in (('daily', advanced['daily']['period_key']), ('weekly', advanced['weekly']['period_key'])):
            await db.execute('UPDATE quest_v1_assignments SET progress=target,completed_at=CLOCK_TIMESTAMP() WHERE user_id=? AND period=? AND period_key=?', (user, period, key))
        complete = await quests_v1.overview(db, user_id=user, vip_active=False, sources=sources)
        assert complete['completion'] == {'daily': True, 'weekly': True, 'combined': True}
        assert {kind: value['claimable'] for kind, value in complete['rewards']['items'].items()} == {
            'daily': True, 'weekly': True, 'combined': True,
        }
        daily_reward = await quests_v1.claim_reward(db, user_id=user, vip_active=False, kind='daily', sources=sources)
        weekly_reward = await quests_v1.claim_reward(db, user_id=user, vip_active=False, kind='weekly', sources=sources)
        combined_reward = await quests_v1.claim_reward(db, user_id=user, vip_active=False, kind='combined', sources=sources)
        assert daily_reward['reward_result']['amount_mora'] == 20
        assert weekly_reward['reward_result']['amount_mora'] == 100
        assert combined_reward['reward_result']['amount_mora'] == 75
        assert daily_reward['reward_result']['amount_keys'] == 1
        assert weekly_reward['reward_result']['amount_keys'] == 1
        assert combined_reward['reward_result']['amount_keys'] == 0
        assert await chest_repo.get_balance(db, user) == 2
        assert 'chests' in await quests_v1.available_sources(db, user_id=user)
        repeat = await quests_v1.claim_reward(db, user_id=user, vip_active=False, kind='combined', sources=sources)
        assert repeat['reward_result']['already_claimed']
        assert await chest_repo.get_balance(db, user) == 2
        async with db.execute('SELECT source_kind,source_event_id FROM chest_key_grants_v1 WHERE user_id=? ORDER BY source_kind', (user,)) as cursor:
            key_sources = [tuple(row) for row in await cursor.fetchall()]
        assert key_sources == [
            ('quest_daily_set_complete', f"daily:{complete['daily']['period_key']}"),
            ('quest_weekly_set_complete', f"weekly:{complete['weekly']['period_key']}"),
        ]
        async with db.execute('SELECT COUNT(*) FROM quest_v1_reward_receipts WHERE user_id=?', (user,)) as cursor:
            assert (await cursor.fetchone())[0] == 3
        async with db.execute("SELECT reward_id FROM quest_v1_reward_receipts WHERE user_id=? ORDER BY reward_id", (user,)) as cursor:
            reward_ids = [row[0] for row in await cursor.fetchall()]
        assert reward_ids == [
            f"combined:{complete['weekly']['period_key']}", f"daily:{complete['daily']['period_key']}",
            f"weekly:{complete['weekly']['period_key']}",
        ]
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == 195.0
        async with db.execute("SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='quest_reward'", (user,)) as cursor:
            assert (await cursor.fetchone())[0] == 3

        disabled_user = 976209
        disabled = await quests_v1.overview(db, user_id=disabled_user, vip_active=False, sources=sources)
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key='content_chests_v1'")
        await db.execute(
            'UPDATE quest_v1_assignments SET progress=target,completed_at=CLOCK_TIMESTAMP() '
            'WHERE user_id=? AND period=? AND period_key=?',
            (disabled_user, 'daily', disabled['daily']['period_key']),
        )
        disabled_reward = await quests_v1.claim_reward(
            db, user_id=disabled_user, vip_active=False, kind='daily', sources=sources,
        )
        assert disabled_reward['reward_result']['amount_keys'] == 0
        assert await chest_repo.get_balance(db, disabled_user) == 0
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key='content_chests_v1'")
        enabled_again = await quests_v1.overview(
            db, user_id=disabled_user, vip_active=False, sources=sources,
        )
        assert enabled_again['rewards']['items']['daily']['claimed']
        assert enabled_again['rewards']['items']['daily']['amount_keys'] == 0
        disabled_repeat = await quests_v1.claim_reward(
            db, user_id=disabled_user, vip_active=False, kind='daily', sources=sources,
        )
        assert disabled_repeat['reward_result']['already_claimed']
        assert await chest_repo.get_balance(db, disabled_user) == 0

        migration_user = 976202
        rhythm_only = frozenset({'rhythm'})
        seeded = await quests_v1.overview(db, user_id=migration_user, vip_active=False, sources=rhythm_only)
        assert len(seeded['weekly']['quests']) == 5
        await db.execute("UPDATE quest_v1_assignments SET definition_json=definition_json-'policy_version' WHERE user_id=?", (migration_user,))
        migrated = await quests_v1.overview(db, user_id=migration_user, vip_active=False, sources=rhythm_only)
        assert len({q['id'] for q in migrated['weekly']['quests']}) == 5
        assert len({q['lane'] for q in migrated['weekly']['quests']}) == 5
        assert all(q['source'] in {'any_game', 'rhythm'} for period in ('daily', 'weekly') for q in migrated[period]['quests'])

        partial_user = 976203
        partial = await quests_v1.overview(db, user_id=partial_user, vip_active=False, sources=sources)
        await db.execute("UPDATE quest_v1_assignments SET definition_json=definition_json-'policy_version' WHERE user_id=?", (partial_user,))
        await db.execute("UPDATE quest_v1_assignments SET progress=1 WHERE user_id=? AND period='daily' AND slot=0", (partial_user,))
        async with db.execute("SELECT period,slot,quest_id,definition_json::text FROM quest_v1_assignments WHERE user_id=? AND period='daily' ORDER BY period,slot", (partial_user,)) as cursor:
            before_partial = [tuple(row) for row in await cursor.fetchall()]
        await quests_v1.overview(db, user_id=partial_user, vip_active=False, sources=sources)
        async with db.execute("SELECT period,slot,quest_id,definition_json::text FROM quest_v1_assignments WHERE user_id=? AND period='daily' ORDER BY period,slot", (partial_user,)) as cursor:
            after_partial = [tuple(row) for row in await cursor.fetchall()]
        assert after_partial == before_partial, 'a partially progressed stale period must remain byte-for-byte intact'
    finally:
        await tx.rollback()
        await conn.close()
    print('OK: quests v1 assignments, rerolls, atomic rewards and weekly combined guard')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', type=local_dsn, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
