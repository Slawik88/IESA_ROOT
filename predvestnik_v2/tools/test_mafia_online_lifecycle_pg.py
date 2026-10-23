"""Real-PG lifecycle failures: re-entry, disappearing targets, restart and competing schedulers."""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

os.environ.setdefault('BOT_TOKEN', '1:x')
os.environ.setdefault('DATABASE_URL', 'postgresql://unused/unused')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game, mafia_online_chat as chat, mafia_online_phases as engine, mafia_online_scheduler as scheduler
from tools.test_mafia_online_pg import denied, expire


async def reentry(db):
    room = await game.create(db, {'id':100}, visibility='invite')
    token = (await repo.load(db, room))['invite']
    await denied(game.join(db, room, {'id':101}, 'я'), 403)
    await game.join(db, room, {'id':101}, token)
    for staff, actor in ((False,100),(True,999)):
        await chat.moderate(db, room, actor, 'mute', target=101, staff=staff)
        await game.control(db, room, 101, 'leave')
        await game.join(db, room, {'id':101}, token)
        assert not (await game.get(db, room, 101))['me']['can_write'], 're-entry must not remove room mute'
        if staff:
            await denied(chat.moderate(db, room, 100, 'unmute', target=101), 403)
        await game.control(db, room, 101, 'leave')
        await chat.moderate(db, room, actor, 'unmute', target=101, staff=staff)
        await game.join(db, room, {'id':101}, token)
        assert (await game.get(db, room, 101))['me']['can_write']
    # A newly claimed host gets a fresh presence lease in the same transaction.
    await game.join(db, room, {'id':102}, token)
    state = await repo.load(db, room)
    state['created'] -= 200
    for p in state['players']:
        p['seen'] = state['created']
    await repo.save(db, state)
    await game.control(db, room, 101, 'claim')
    await denied(game.control(db, room, 102, 'claim'))
    assert (await repo.load(db, room))['host'] == 101
    print('PASS Unicode invitation, persistent host/staff mutes through leave/rejoin, absent-player unmute, host presence lease')


async def targets(db):
    room = await game.create(db, {'id':200})
    for uid in range(201,208):
        await game.join(db, room, {'id':uid})
    state = await repo.load(db, room)
    victims = [p['id'] for p in state['players'] if p['role']=='citizen' and p['id']!=200]
    mafia = next(p['id'] for p in state['players'] if p['role']=='mafia')
    await game.action(db, room, mafia, state['phase_number'], 'mafia_target', victims[0])
    await game.control(db, room, victims[0], 'leave')
    view = await game.get(db, room, mafia)
    assert view['me']['choice_reset'] and not view['me']['action']
    assert all(p['target'] is None for p in view['me']['team_choices'])
    await expire(db, room)
    await game.control(db, room, 200, 'skip', (await repo.load(db, room))['phase_number'])
    state = await repo.load(db, room)
    phase = state['phase_number']
    victim = victims[1]
    for person in state['players']:
        if person['alive']:
            await game.action(db, room, person['id'], phase, 'vote', victim if person['id']!=victim else None)
    # All votes shortened the phase. The selected player leaves during that grace period.
    state = await repo.load(db, room)
    now = await repo.now(db)
    state.update(phase_started=now-20, deadline=now+2, phase_deadline=now+60)
    await repo.save(db, state)
    await game.control(db, room, victim, 'leave')
    state = await repo.load(db, room)
    assert state['deadline'] >= now+14 and state['deadline']<=now+60
    voter = next(p['id'] for p in state['players'] if p['alive'])
    view = await game.get(db, room, voter)
    assert view['me']['choice_reset'] and view['me']['action'] is None
    assert all(a['target']!=victim for a in state['actions'].values())
    remaining_target = next(p['id'] for p in state['players'] if p['alive'] and p['id']!=voter)
    await game.action(db, room, voter, phase, 'vote', remaining_target)
    assert not (await game.get(db, room, voter))['me']['choice_reset']
    await game.control(db, room, 200, 'pause')
    await game.control(db, room, remaining_target, 'leave')
    state = await repo.load(db, room)
    # This may finish the game if the leaving player was the last living mafioso.
    if state['phase']=='paused':
        assert 14<=state['remaining']<=state['phase_remaining']
        host = state['host']
        await game.control(db, room, host, 'resume')
        state = await repo.load(db, room)
        assert state['deadline']<=state['phase_deadline']
    print('PASS disappearing night/day targets reset accepted choices; grace capped by original phase budget; pause/resume')


async def clocks(a,b,dsn,schema):
    rooms = [await game.create(a, {'id':uid}) for uid in (300,301)]
    for room in rooms:
        state = await repo.load(a, room)
        state['deadline'] = await repo.now(a)-10
        await repo.save(a, state)
    actual = engine.advance
    async def fail_one(db,state,now):
        if state['id']==rooms[0]:
            # Failure happens after seat release inside finish, so it tests actual rollback.
            with patch.object(repo,'message',side_effect=RuntimeError('injected notice failure')):
                return await actual(db,state,now)
        return await actual(db,state,now)
    with patch.object(engine,'advance',side_effect=fail_one), patch.object(scheduler.logger,'exception'):
        await scheduler.tick(b)
    assert (await repo.load(a, rooms[0]))['phase']=='lobby'
    assert await repo.current(a,300)==rooms[0]
    assert (await repo.load(a, rooms[1]))['phase']=='cancelled', 'poison room must not stop other clocks'
    healthy = await game.create(a, {'id':302})
    state = await repo.load(a,healthy);state['deadline']=await repo.now(a)-10;await repo.save(a,state)
    async with a.connection.transaction():
        await repo.load(a, rooms[0],lock=True)
        await asyncio.wait_for(scheduler.tick(b),timeout=2)
        assert (await repo.load(b,healthy))['phase']=='cancelled', 'locked room must not block other clocks'
    # Simulate a fresh worker: no in-memory timer state, same committed deadlines.
    await asyncio.gather(scheduler.tick(a),scheduler.tick(b))
    assert (await repo.load(a,rooms[0]))['phase']=='cancelled'
    assert await a.connection.fetchval("SELECT count(*) FROM mafia_online_messages WHERE room_id=$1 AND body='Партия закрыта.'",rooms[0])==1
    extra = await game.create(a, {'id':303})
    state=await repo.load(a,extra);state['deadline']=await repo.now(a)-10;await repo.save(a,state)
    with patch.object(engine,'advance',side_effect=asyncio.CancelledError):
        try:
            await scheduler.tick(b)
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('scheduler cancellation must propagate')
    # A genuinely fresh Python worker must recover committed deadlines without parent memory.
    source="""import asyncio,asyncpg,sys
from infrastructure.pg_adapter import PGAdapter
from services.mafia_online_scheduler import tick
async def main():
    c=await asyncpg.connect(sys.argv[1],server_settings={'search_path':sys.argv[2]})
    try: await tick(PGAdapter(c))
    finally: await c.close()
asyncio.run(main())
"""
    child=await asyncio.create_subprocess_exec(sys.executable,'-c',source,dsn,schema,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    stdout,stderr=await asyncio.wait_for(child.communicate(),timeout=15)
    assert child.returncode==0, stderr.decode(errors='replace')[-1000:]
    assert (await repo.load(a,extra))['phase']=='cancelled'
    assert await repo.current(a,303) is None
    print('PASS poisoned/locked room isolation, seat+notice rollback, fresh-worker recovery, two-worker exactly-once close, cancellation')


async def receipts(db):
    room=await game.create(db,{'id':2000})
    nonce=uuid.uuid4()
    previous=await repo.load(db,room)
    count=await db.connection.fetchval('SELECT count(*) FROM mafia_online_messages WHERE room_id=$1',room)
    with patch.object(repo,'remember_command',side_effect=RuntimeError('injected receipt failure')):
        try:
            await game.control(db,room,2000,'settings',nonce=nonce,seats=10)
        except RuntimeError:
            pass
        else:
            raise AssertionError('receipt failure injection did not execute')
    assert await repo.load(db,room)==previous
    assert await db.connection.fetchval('SELECT count(*) FROM mafia_online_messages WHERE room_id=$1',room)==count
    assert not await repo.command_receipt(db,room,2000,nonce)
    assert not (await game.control(db,room,2000,'settings',nonce=nonce,seats=10))['replayed']
    assert (await game.control(db,room,2000,'settings',nonce=nonce,seats=10))['replayed']
    assert (await repo.load(db,room))['version']==previous['version']+1
    print('PASS failed receipt atomically rolls back the command; exact retry applies once')


async def fairness(a,b):
    locked_rooms=[]
    for uid in range(1000,1100):
        room=await game.create(a,{'id':uid})
        state=await repo.load(a,room);state['deadline']=await repo.now(a)-10;await repo.save(a,state)
        locked_rooms.append(room)
    healthy=await game.create(a,{'id':1100})
    state=await repo.load(a,healthy);state['deadline']=await repo.now(a)-10;await repo.save(a,state)
    async with a.connection.transaction():
        await a.connection.fetch('SELECT id FROM mafia_online_rooms WHERE id=ANY($1::bigint[]) FOR UPDATE',locked_rooms)
        await asyncio.wait_for(scheduler.tick(b),timeout=4)
        assert (await repo.load(b,healthy))['phase']=='cancelled', '101st room must advance past a whole locked batch'
    healthy=await game.create(a,{'id':1101})
    state=await repo.load(a,healthy);state['deadline']=await repo.now(a)-10;await repo.save(a,state)
    actual=engine.advance
    async def fail_batch(db,state,now):
        if state['id'] in locked_rooms:
            raise RuntimeError('injected poison room')
        return await actual(db,state,now)
    with patch.object(engine,'advance',side_effect=fail_batch),patch.object(scheduler.logger,'exception'):
        await asyncio.wait_for(scheduler.tick(b),timeout=4)
    assert (await repo.load(a,healthy))['phase']=='cancelled', 'poisoned batch must not starve next page'
    print('PASS healthy 101st room beyond 100 locked rooms and 100 poisoned rooms')


async def pause_floor(db):
    from core import mafia_online as rules
    room=await game.create(db,{'id':400})
    for uid in range(401,408):
        await game.join(db,room,{'id':uid})
    state=await repo.load(db,room)
    base=state['phase_started']
    clock=[base+1]
    async def now(_db):return clock[0]
    with patch.object(repo,'now',side_effect=now):
        await game.control(db,room,400,'pause')
        clock[0]=base+601
        await game.control(db,room,400,'resume')
        clock[0]=base+602
        target=next(p['id'] for p in state['players'] if p['role']=='citizen')
        for p in state['players']:
            kind=rules.night_action_for(p['role'])
            if kind:
                await game.action(db,room,p['id'],1,kind,target)
    state=await repo.load(db,room)
    assert state['deadline']>=base+615, 'paused wall time must not consume the minimum active phase duration'
    assert state['deadline']<=state['phase_deadline']
    print('PASS ten-minute pause preserves the minimum 15 active seconds when all role actions arrive')


async def full_lobbies(db):
    full=[]
    for index in range(40):
        host=3000+index*8
        room=await game.create(db,{'id':host},seats=20)
        for uid in range(host+1,host+8):
            await game.join(db,room,{'id':uid})
        # Shrinking to the current count creates a full lobby awaiting manual start.
        await game.control(db,room,host,'settings',seats=8)
        full.append(room)
    available=await game.create(db,{'id':5000})
    candidates=await repo.candidates(db)
    assert available in candidates and not any(r in candidates for r in full)
    assert await game.quick(db,{'id':5001})==available, '40 full lobbies must not hide the joinable 41st table'
    print('PASS public matchmaking filters full/expired lobbies before its 40-room limit')


async def main(dsn):
    schema='mafia_lifecycle_'+uuid.uuid4().hex[:12]
    connections=[await asyncpg.connect(dsn) for _ in range(2)]
    await connections[0].execute(f'CREATE SCHEMA "{schema}"')
    try:
        for c in connections:
            await c.execute(f'SET search_path TO "{schema}"')
        a,b=[PGAdapter(c) for c in connections]
        await repo.ensure_tables(a)
        await reentry(a);await targets(a);await clocks(a,b,dsn,schema);await fairness(a,b);await pause_floor(a);await full_lobbies(a);await receipts(a)
        assert not await a.connection.fetchval("SELECT to_regclass('mafia_v1_matches')")
    finally:
        await connections[0].execute(f'DROP SCHEMA "{schema}" CASCADE')
        for c in connections:
            await c.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dsn',required=True);args=parser.parse_args()
    if urlparse(args.dsn).hostname not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('loopback PostgreSQL required')
    asyncio.run(main(args.dsn))
