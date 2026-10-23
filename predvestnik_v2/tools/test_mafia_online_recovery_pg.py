"""Scheduler-outage recovery, message replay integrity and host presence on real PG."""
import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game, mafia_online_chat as chat
from tools.test_mafia_online_pg import denied
from core.mafia_online import OnlineError


async def expired_lobby(db, uid):
    room = await game.create(db, {"id": uid})
    state = await repo.load(db, room)
    state["deadline"] = await repo.now(db) - 5
    await repo.save(db, state)
    return room


async def recovery(db):
    room = await expired_lobby(db, 100)
    assert (await game.hub(db, 100))["active"] is None
    assert (await repo.load(db, room))["phase"] == "cancelled"
    assert await db.connection.fetchval("SELECT count(*) FROM mafia_online_messages WHERE room_id=$1 AND body='Партия закрыта.'", room) == 1
    previous = await expired_lobby(db, 101)
    replacement = await game.create(db, {"id": 101})
    assert replacement != previous and await repo.current(db, 101) == replacement
    previous = await expired_lobby(db, 102)
    assert await game.quick(db, {"id": 102}) != previous
    previous = await expired_lobby(db, 103)
    assert await game.join(db, replacement, {"id": 103}) == replacement
    assert (await repo.load(db, previous))["phase"] == "cancelled"
    print("PASS hub/create/quick/join recover expired memberships without any scheduler tick")


async def opposite_expired_joins(a, b):
    rooms = [await expired_lobby(a, 600), await expired_lobby(b, 601)]
    actual = game.active_room
    ready = asyncio.Event()
    arrivals = 0

    async def reconciled(db, uid):
        nonlocal arrivals
        value = await actual(db, uid)
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await ready.wait()
        return value

    # Both requests finish their original-room recovery before either starts
    # joining the other's room. Recovery inside an outer join transaction would
    # retain A/B row locks and create the deterministic A→B / B→A cycle here.
    with patch.object(game, "active_room", side_effect=reconciled):
        outcomes = await asyncio.wait_for(asyncio.gather(
            game.join(a, rooms[1], {"id": 600}),
            game.join(b, rooms[0], {"id": 601}), return_exceptions=True), timeout=5)
    assert all(isinstance(result, OnlineError) and result.status == 409 for result in outcomes), outcomes
    assert await repo.current(a, 600) is None and await repo.current(b, 601) is None
    for room in rooms:
        assert (await repo.load(a, room))["phase"] == "cancelled"
    print("PASS opposite expired-room joins return closed-table errors without retaining a room-lock cycle")


async def messages(db):
    room = await game.create(db, {"id": 200})
    await game.join(db, room, {"id": 201})
    nonce = uuid.uuid4()
    first = await chat.send(db, room, 201, "table", "Привет", nonce)
    await denied(chat.send(db, room, 201, "table", "Другой текст", nonce), 409)
    await denied(chat.send(db, room, 201, "mafia", "Привет", nonce), 409)
    await denied(chat.send(db, room, 201, "table", "Привет", nonce, reply_to=first["id"]), 409)
    await game.control(db, room, 201, "leave")
    replay = await chat.send(db, room, 201, "table", "Привет", nonce)
    assert replay == {"id": first["id"], "replayed": True}
    assert await db.connection.fetchval("SELECT count(*) FROM mafia_online_messages WHERE room_id=$1 AND user_id=201", room) == 1
    await denied(chat.send(db, room, 201, "table", "Снова", uuid.uuid4()), 403)
    print("PASS frozen chat payload checked across body/channel/reply; lost-response retry after leaving inserts nothing")


async def presence(db):
    room = await game.create(db, {"id": 300})
    state = await repo.load(db, room)
    state["created"] -= 300
    state["players"][0]["seen"] = state["created"]
    await repo.save(db, state)
    await game.join(db, room, {"id": 301})
    joined = await repo.load(db, room)
    assert await repo.now(db) - joined["players"][1]["seen"] < 2
    await chat.send(db, room, 300, "table", "Я здесь", uuid.uuid4())
    await denied(game.control(db, room, 301, "claim"))
    # A host using a control, while polling is interrupted, is also present.
    state = await repo.load(db, room)
    state["players"][0]["seen"] -= 300
    await repo.save(db, state)
    await game.control(db, room, 300, "settings", seats=10)
    await denied(game.control(db, room, 301, "claim"))
    await game.join(db, room, {"id": 302})
    state = await repo.load(db, room)
    for person in state["players"]:
        person["seen"] -= 300
    await repo.save(db, state)
    await game.control(db, room, 300, "leave")
    assert (await repo.load(db, room))["host"] == 301
    await denied(game.control(db, room, 302, "claim"))
    print("PASS fresh joins, chat/control activity and automatic host transfer renew the presence lease")


async def automatic_roles(db):
    room = await game.create(db, {"id": 400}, seats=8, roles_auto=False, roles=["don"])
    await game.control(db, room, 400, "settings", seats=4, roles_auto=True, roles=["don"])
    for uid in range(401, 404):
        await game.join(db, room, {"id": uid})
    state = await repo.load(db, room)
    assert state["phase"] == "night"
    assert sum(p["role"] == "mafia" for p in state["players"]) == 1
    assert all(p["role"] in ("mafia", "citizen") for p in state["players"])
    host = next(p for p in state["players"] if p["id"] == 400)
    other = next(p for p in state["players"] if p["id"] != 400)
    state["created"] -= 300
    host["seen"] = state["created"]
    if host["role"] != "mafia":
        # Keep the existing deck/faction counts, only choose a deterministic host for this check.
        host = next(p for p in state["players"] if p["role"] == "mafia")
        state["host"] = host["id"]
        host["seen"] = state["created"]
        other = next(p for p in state["players"] if p["id"] != host["id"])
    await repo.save(db, state)
    await game.action(db, room, host["id"], 1, "mafia_target", other["id"])
    await denied(game.control(db, room, other["id"], "claim"))
    await denied(game.create(db, {"id": 404}, seats=4, roles_auto=False, roles=["don"]))
    print("PASS automatic four-seat deck ignores inactive manual Don; manual validation retained; role actions renew host presence")


async def main(dsn):
    schema = "mafia_online_recovery_" + uuid.uuid4().hex[:12]
    connection, second = [await asyncpg.connect(dsn) for _ in range(2)]
    await connection.execute(f'CREATE SCHEMA "{schema}"')
    try:
        await connection.execute(f'SET search_path TO "{schema}"')
        await second.execute(f'SET search_path TO "{schema}"')
        db = PGAdapter(connection)
        await repo.ensure_tables(db)
        await recovery(db)
        await opposite_expired_joins(db, PGAdapter(second))
        await messages(db)
        await presence(db)
        await automatic_roles(db)
    finally:
        await connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await connection.close()
        await second.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    asyncio.run(main(args.dsn))
