"""Concurrent matchmaking, durable command receipts and atomic staff decisions on real PG."""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

os.environ.setdefault('BOT_TOKEN', '1:x')
os.environ.setdefault('DATABASE_URL', 'postgresql://unused/unused')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game, mafia_online_chat as chat
from FastAPI.routers.bot_admin import mafia_online as admin
from tools.test_mafia_online_pg import denied


async def check(dbs):
    db = dbs[0]
    rooms = await asyncio.gather(*(game.quick(d, {'id': 1000+i}) for i, d in enumerate(dbs)))
    assert sorted(rooms.count(r) for r in set(rooms)) == [4, 8], rooms
    assert await game.quick(db, {'id': 1000}) == rooms[0]
    full = next(r for r in rooms if rooms.count(r) == 8)
    state = await repo.load(db, full)
    assert len({p['name'] for p in state['players']}) == 8
    assert len({p['seat'] for p in state['players']}) == 8
    host = state['host']
    nonce = uuid.uuid4()
    payload = dict(nonce=nonce, phase_number=state['phase_number'], expected_version=state['version'])
    assert not (await game.control(db, full, host, 'pause', **payload))['replayed']
    await game.control(db, full, host, 'resume', nonce=uuid.uuid4())
    assert (await game.control(db, full, host, 'pause', **payload))['replayed']
    assert (await repo.load(db, full))['phase'] == 'night', 'replaying old pause must not pause again'
    await denied(game.control(db, full, host, 'resume', **payload))
    mafia = [p for p in state['players'] if p['role'] in ('mafia', 'don')]
    town = next(p for p in state['players'] if p['role'] == 'citizen')
    await game.action(db, full, mafia[0]['id'], state['phase_number'], 'mafia_target', town['id'])
    chosen = await repo.load(db, full)
    await game.action(db, full, mafia[0]['id'], state['phase_number'], 'mafia_target', town['id'])
    assert (await repo.load(db, full))['actions'] == chosen['actions'], 'retry preserves the accepted tie-break timestamp'
    view = await game.get(db, full, mafia[1]['id'])
    assert next(p for p in view['me']['team_choices'] if p['id'] == mafia[0]['id'])['target'] == town['id']
    assert 'team_choices' not in (await game.get(db, full, town['id']))['me']

    room = await game.create(db, {'id': 2000})
    await game.join(db, room, {'id': 2001})
    await game.join(db, room, {'id': 2002})
    version = (await repo.load(db, room))['version']
    await game.join(db, room, {'id': 2003})
    await denied(game.control(db, room, 2000, 'settings', expected_version=version, seats=4))
    assert (await repo.load(db, room))['seats'] == 8
    with patch.object(repo, 'candidates', new=AsyncMock(return_value=[room])):
        await game.control(db, room, 2000, 'settings', visibility='invite')
        assert (await game.hub(db, 9999))['rooms'] == [], 'visibility changed after candidate query'
    leaving = uuid.uuid4()
    await game.control(db, room, 2003, 'leave', nonce=leaving)
    assert (await game.control(db, room, 2003, 'leave', nonce=leaving))['replayed']
    token = (await repo.load(db, room))['invite']
    await game.join(db, room, {'id': 2003}, token)
    assert next(p for p in (await repo.load(db, room))['players'] if p['id'] == 2003)['seat'] == 5
    await db.connection.execute('CREATE TABLE users (user_tg_id BIGINT PRIMARY KEY, nickname TEXT)')
    await db.connection.execute("INSERT INTO users VALUES(2004,'Имя из профиля')")
    await game.join(db, room, {'id': 2004}, token)
    assert next(p for p in (await repo.load(db, room))['players'] if p['id'] == 2004)['name'] == 'Имя из профиля'
    post = await chat.send(db, room, 2001, 'table', 'Проверка модерации', uuid.uuid4())
    inserted = [await repo.message(db, room, 'table', f'Поток {i}', user_id=2002, name='Одинаковое имя', seat=3) for i in range(101)]
    first = await repo.messages(db, room, 'table', post['id'])
    second = await repo.messages(db, room, 'table', first[-1]['id'])
    assert [m['id'] for m in first+second] == inserted, 'new-message pages must never skip the middle of a burst'
    await chat.moderate(db, room, 2002, 'report', message_id=post['id'])
    await chat.moderate(db, room, 9999, 'mute', target=2001, staff=True)
    await denied(chat.moderate(db, room, 2000, 'unmute', target=2001), 403)
    assert not (await game.get(db, room, 2001))['me']['can_write']
    await chat.moderate(db, room, 9999, 'unmute', target=2001, staff=True)
    assert (await game.get(db, room, 2001))['me']['can_write']
    # Fail after the nested moderation transaction: all mutations must roll back together.
    for failing in ('audit', 'resolve_report'):
        target = admin.admin_people if failing == 'audit' else repo
        with patch.object(target, failing, new=AsyncMock(side_effect=RuntimeError('injected failure'))):
            try:
                await admin.decide(post['id'], admin.Decision(kind='hide'), user={'id':9999}, db=db)
            except RuntimeError:
                pass
            else:
                raise AssertionError('failure injection did not execute')
        assert not (await repo.get_message(db, post['id']))['hidden']
        assert not await db.connection.fetchval('SELECT resolved FROM mafia_online_reports WHERE message_id=$1', post['id'])
    with patch.object(admin.admin_people, 'audit', new=AsyncMock()):
        await admin.decide(post['id'], admin.Decision(kind='hide'), user={'id':9999}, db=db)
    assert (await repo.get_message(db, post['id']))['hidden']
    assert await db.connection.fetchval('SELECT resolved FROM mafia_online_reports WHERE message_id=$1', post['id'])
    assert not await db.connection.fetchval("SELECT to_regclass('mafia_v1_matches')")
    print('PASS 12 parallel arrivals -> 8+4 seats; durable controls/actions, stale settings, stable names/seats, team privacy, 101-message burst, staff authority, atomic moderation')


async def main(dsn):
    schema = 'mafia_online_resilience_' + uuid.uuid4().hex[:12]
    connections = [await asyncpg.connect(dsn) for _ in range(12)]
    await connections[0].execute(f'CREATE SCHEMA "{schema}"')
    try:
        for conn in connections:
            await conn.execute(f'SET search_path TO "{schema}"')
        dbs = [PGAdapter(conn) for conn in connections]
        await repo.ensure_tables(dbs[0])
        await check(dbs)
    finally:
        await connections[0].execute(f'DROP SCHEMA "{schema}" CASCADE')
        for conn in connections:
            await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise SystemExit('loopback PostgreSQL required')
    asyncio.run(main(args.dsn))
