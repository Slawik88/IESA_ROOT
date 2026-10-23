"""Online Mafia on isolated PostgreSQL schema: full game, privacy, races, chat and recovery.

No Telegram calls, local Mafia tables or economic receipts. --dsn accepts loopback only.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game, mafia_online_chat as chat, mafia_online_scheduler as scheduler
from core.mafia_online import OnlineError


def user(uid):
    return {"id": uid, "first_name": f"Игрок {uid}"}


async def denied(coro, status=None):
    try:
        await coro
    except OnlineError as error:
        if status:
            assert error.status == status, str(error)
        return
    raise AssertionError("request must be rejected")


async def expire(db, room_id):
    async with db.connection.transaction():
        row = await repo.load(db, room_id, lock=True)
        row["deadline"] = await repo.now(db) - 1
        await repo.save(db, row)
    await scheduler.tick(db)


async def full_game(db):
    room = await game.create(db, user(1), seats=8, vote_mode="open")
    for uid in range(2, 9):
        await game.join(db, room, user(uid))
    row = await repo.load(db, room)
    assert row["phase"] == "night" and {p["role"] for p in row["players"]} >= {"mafia", "don", "doctor", "detective"}
    people = row["players"]
    mafia = [p for p in people if p["role"] in ("mafia", "don")]
    doctor = next(p for p in people if p["role"] == "doctor")
    detective = next(p for p in people if p["role"] == "detective")
    citizen = next(p for p in people if p["role"] == "citizen")
    view = await game.get(db, room, citizen["id"])
    assert all("role" not in p for p in view["players"])
    assert view["me"]["team"] == [] and "mafia" not in view["channels"]
    await denied(game.get(db, room, citizen["id"], "mafia"), 403)
    await denied(game.get(db, room, 999), 403)
    await denied(game.action(db, room, citizen["id"], 1, "mafia_target", detective["id"]), 403)
    await denied(chat.send(db, room, citizen["id"], "table", "Ночной спам", uuid.uuid4()), 403)
    await chat.send(db, room, mafia[0]["id"], "mafia", "Тайна команды", uuid.uuid4())
    team_view = await game.get(db, room, mafia[1]["id"], "mafia")
    assert any(m["body"] == "Тайна команды" for m in team_view["messages"])
    for p in mafia:
        await game.action(db, room, p["id"], 1, "mafia_target", citizen["id"])
    await game.action(db, room, doctor["id"], 1, "doctor_save", citizen["id"])
    await game.action(db, room, detective["id"], 1, "detective_check", mafia[0]["id"])
    await expire(db, room)
    morning = await game.get(db, room, detective["id"])
    assert morning["phase"] == "discussion" and morning["me"]["checks"][0]["mafia"]
    assert all(p["alive"] for p in morning["players"]), "doctor protected the target"
    await denied(game.get(db, room, mafia[0]["id"], "mafia"), 403)
    nonce = uuid.uuid4()
    first = await chat.send(db, room, citizen["id"], "table", "<img src=x onerror=alert(1)>", nonce)
    retry = await chat.send(db, room, citizen["id"], "table", "<img src=x onerror=alert(1)>", nonce)
    assert first["id"] == retry["id"] and retry["replayed"]
    await denied(chat.send(db, room, citizen["id"], "table", "Слишком быстро", uuid.uuid4()), 429)
    msg = await repo.get_message(db, first["id"])
    assert msg["body"].startswith("<img"), "stored as plain text, escaped by the UI"
    await chat.moderate(db, room, doctor["id"], "report", message_id=msg["id"])
    await denied(chat.moderate(db, room, 2, "mute", target=citizen["id"]), 403)  # Host is 1; roles are shuffled.
    await chat.moderate(db, room, 1, "mute", target=citizen["id"])
    assert not (await game.get(db, room, citizen["id"]))["me"]["can_write"]
    await chat.moderate(db, room, 1, "hide", message_id=msg["id"])
    assert (await game.get(db, room, doctor["id"]))["messages"][-1]["body"] == "Сообщение скрыто"
    await game.control(db, room, 1, "pause")
    assert (await game.get(db, room, 1))["phase"] == "paused"
    await game.control(db, room, 1, "resume")
    assert (await game.get(db, room, detective["id"]))["me"]["checks"] == morning["me"]["checks"]
    for target in mafia:
        await game.control(db, room, 1, "skip", (await repo.load(db, room))["phase_number"])
        row = await repo.load(db, room)
        for p in row["players"]:
            if p["alive"]:
                await game.action(db, room, p["id"], row["phase_number"], "vote", None if p["id"] == target["id"] else target["id"])
        assert (await game.get(db, room, 1))["votes"], "open votes are explicitly public"
        await expire(db, room)
        dead = await game.get(db, room, target["id"])
        assert not dead["me"]["alive"]
        if dead["phase"] != "finished":
            await denied(game.get(db, room, target["id"], "mafia"), 403)
            await db.connection.execute("UPDATE mafia_online_messages SET created_at=created_at-INTERVAL '2 seconds' WHERE user_id=$1", target["id"])
            await chat.send(db, room, target["id"], "afterlife", "Теперь наблюдаю", uuid.uuid4())
            await expire(db, room)
    result = await game.get(db, room, 1)
    assert result["phase"] == "finished" and result["winner"] == "town"
    assert all("role" in p for p in result["players"])
    assert await repo.current(db, 1) is None
    assert (await game.hub(db, 1))["history"][0]["id"] == room
    print("PASS full game, roles, doctor, detective, secret team, chat retry/mute/report/hide, pause, history")


async def races(dbs):
    a, b = dbs
    room = await game.create(a, user(21), seats=4)
    await game.join(a, room, user(22))
    await game.join(a, room, user(23))
    results = await asyncio.gather(game.join(a, room, user(24)), game.join(b, room, user(25)), return_exceptions=True)
    assert sum(isinstance(r, int) for r in results) == 1 and len((await repo.load(a, room))["players"]) == 4
    rooms = [await game.create(a, user(31)), await game.create(b, user(32))]
    results = await asyncio.gather(game.join(a, rooms[0], user(33)), game.join(b, rooms[1], user(33)), return_exceptions=True)
    assert sum(isinstance(r, int) for r in results) == 1
    assert await a.connection.fetchval("SELECT count(*) FROM mafia_online_seats WHERE user_id=33") == 1
    private = await game.create(a, user(41), visibility="invite")
    await denied(game.join(a, private, user(42)), 403)
    token = (await repo.load(a, private))["invite"]
    await game.join(a, private, user(42), token)
    assert private not in [r["id"] for r in (await game.hub(a, 99))["rooms"]]
    await game.control(a, private, 41, "settings", visibility="public")
    assert private in [r["id"] for r in (await game.hub(a, 99))["rooms"]]
    await game.control(a, private, 41, "settings", visibility="invite")
    assert private not in [r["id"] for r in (await game.hub(a, 99))["rooms"]]
    await game.control(a, private, 41, "leave")
    assert (await repo.load(a, private))["host"] == 42
    await denied(game.control(a, private, 41, "cancel"), 403)
    await game.control(a, private, 42, "leave")
    assert (await repo.load(a, private))["phase"] == "cancelled"
    with patch.object(repo, "candidates", new=AsyncMock(return_value=[private])):
        assert (await game.hub(a, 99))["rooms"] == [], "a lobby that closed during the list read is skipped"
    row = await repo.load(a, rooms[0])
    async with a.connection.transaction():
        row["created"] = await repo.now(a) - 200
        row["players"][0]["seen"] = row["created"]
        await repo.save(a, row)
    if any(p["id"] == 33 for p in row["players"]):
        await game.control(a, rooms[0], 33, "claim")
        assert (await repo.load(a, rooms[0]))["host"] == 33
    await expire(a, rooms[0])
    assert await repo.current(a, 31) is None
    assert not await a.connection.fetchval("SELECT to_regclass('mafia_v1_matches')"), "online game never creates/writes local tables"
    print("PASS last-seat race, one active membership, private invite, host transfer, expiry, local isolation")


async def main(dsn):
    schema = "mafia_online_qa_" + uuid.uuid4().hex[:12]
    connections = [await asyncpg.connect(dsn) for _ in range(2)]
    await connections[0].execute(f'CREATE SCHEMA "{schema}"')
    try:
        for conn in connections:
            await conn.execute(f'SET search_path TO "{schema}"')
        dbs = [PGAdapter(conn) for conn in connections]
        await repo.ensure_tables(dbs[0])
        await full_game(dbs[0])
        await races(dbs)
    finally:
        await connections[0].execute(f'DROP SCHEMA "{schema}" CASCADE')
        for conn in connections:
            await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    asyncio.run(main(args.dsn))
