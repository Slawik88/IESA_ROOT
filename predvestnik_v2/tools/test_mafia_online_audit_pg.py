"""2026-10-24 UX contract: roles, presence, channel metadata and chat recovery on real PG.

Uses a disposable schema and refuses non-loopback PostgreSQL. No local Mafia tables.
"""
import argparse
import asyncio
import json
import os
import random
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import httpx
from fastapi import FastAPI
from FastAPI.deps import get_db
from FastAPI.routers import mafia_online as api
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game, mafia_online_chat as chat
from core import mafia_online as rules
from FastAPI.routers.mafia_online import Control
from tools.test_mafia_online_pg import denied, expire


async def mutate(db, room, update):
    async with db.connection.transaction():
        state = await repo.load(db, room, lock=True)
        update(state)
        await repo.save(db, state, bump=False)


async def run(db):
    assert game.settings(seats=4, roles_auto=True, roles=["don"])["roles"] == [], "inactive manual controls cannot invalidate automatic roles"
    assert game.settings(seats=8, roles_auto=False, roles=["doctor", "doctor", "detective"])["roles"] == ["detective", "doctor"]
    try:
        game.settings(seats=4, roles_auto=False, roles=["don"])
    except rules.OnlineError as error:
        assert "8 мест" in str(error)
    else:
        raise AssertionError("manual Don cannot fit at four seats")
    room = await game.create(db, {"id": 1, "first_name": " \t \n", "username": "   "})
    host = (await repo.load(db, room))["players"][0]
    assert host["name"] == "Игрок 1", "whitespace-only signed names require a visible fallback"
    assert host["seen"] > 0, "creation and joining count as presence"
    await game.join(db, room, {"id": 2, "first_name": "Мария\x00  \n Иванова"})
    await game.join(db, room, {"id": 3, "first_name": "Маша"})
    snapshot = await game.get(db, room, 1)
    assert snapshot["players"][1]["name"] == "Мария Иванова"
    assert snapshot["online_count"] == 3 and snapshot["living_count"] == 3
    assert snapshot["me"]["seat"] == 1 and snapshot["host_online"]
    assert set(snapshot["channel_state"]) == {"table"}
    assert snapshot["channel_state"]["table"]["can_write"]
    assert not snapshot["me"]["can_act"] and not snapshot["me"]["action_targets"]
    assert snapshot["voting_progress"] is None
    assert snapshot["phase_started"] and snapshot["phase_duration"] == rules.LOBBY_TTL

    # Retry receipts identify the actual payload, including the channel and parent.
    nonce = uuid.uuid4()
    sent = await chat.send(db, room, 2, "table", "Исходный текст", nonce)
    assert (await chat.send(db, room, 2, "table", " Исходный текст ", nonce))["replayed"]
    await denied(chat.send(db, room, 2, "table", "Изменённый текст", nonce))
    await denied(chat.send(db, room, 2, "mafia", "Исходный текст", nonce))
    await denied(chat.send(db, room, 2, "table", "Исходный текст", nonce, sent["id"]))
    assert await db.connection.fetchval("SELECT COUNT(*) FROM mafia_online_messages WHERE nonce=$1", nonce) == 1
    reply = await repo.message(db, room, "table", "Ответ", user_id=3, name="Маша", reply_to=sent["id"])
    snapshot = await game.get(db, room, 1)
    assert snapshot["channel_state"]["table"]["latest_id"] == reply
    reply_row = next(m for m in snapshot["messages"] if m["id"] == reply)
    assert reply_row["can_reply"] and reply_row["can_report"] and reply_row["can_hide"]
    await chat.moderate(db, room, 1, "hide", message_id=sent["id"])
    hidden_version = (await repo.load(db, room))["version"]
    await chat.moderate(db, room, 1, "hide", message_id=sent["id"])
    assert (await repo.load(db, room))["version"] == hidden_version, "a hide retry must not reset chat caches again"
    snapshot = await game.get(db, room, 1)
    reply_row = next(m for m in snapshot["messages"] if m["id"] == reply)
    assert reply_row["reply_hidden"] and reply_row["reply_body"] == "Сообщение скрыто"
    await chat.moderate(db, room, 1, "hide", message_id=reply)
    snapshot = await game.get(db, room, 1)
    reply_row = next(m for m in snapshot["messages"] if m["id"] == reply)
    assert reply_row["reply_body"] is None and reply_row["reply_to"] is None
    assert not reply_row["can_reply"] and not reply_row["can_hide"]
    assert "Исходный текст" not in json.dumps(snapshot["messages"], ensure_ascii=False)

    transfer = uuid.uuid4()
    await denied(game.control(db, room, 2, "transfer", target=3), 403)
    await denied(game.control(db, room, 1, "transfer", target=1))
    await denied(game.control(db, room, 1, "transfer", target=999))
    Control(command="transfer", target=2)
    try:
        Control(command="transfer")
    except ValueError:
        pass
    else:
        raise AssertionError("transfer requires a target at the API boundary")
    await game.control(db, room, 1, "transfer", target=2, nonce=transfer)
    assert (await repo.load(db, room))["host"] == 2
    assert (await game.control(db, room, 1, "transfer", target=2, nonce=transfer))["replayed"]
    await denied(game.control(db, room, 1, "cancel"), 403)
    await game.control(db, room, 2, "transfer", target=1)
    # Presence has no exact last-seen leakage and does not reveal role/action activity.
    now = await repo.now(db)
    await mutate(db, room, lambda s: rules.player(s, 2).update(seen=now-80))
    snapshot = await game.get(db, room, 3)
    assert not next(p for p in snapshot["players"] if p["id"] == 2)["online"]
    assert all("seen" not in p for p in snapshot["players"])
    assert snapshot["claim_available_at"] > now and not snapshot["can_claim"]
    def absent_host(s):
        rules.player(s, 1).update(seen=now-100)
        s["host_since"] = now-100
    await mutate(db, room, absent_host)
    snapshot = await game.get(db, room, 3)
    assert snapshot["claim_available_at"] < now and snapshot["can_claim"]
    await game.get(db, room, 1)
    assert not (await game.get(db, room, 3))["can_claim"], "host returning immediately cancels takeover availability"

    for uid in range(4, 9):
        await game.join(db, room, {"id": uid, "first_name": f"Игрок {uid}"})
    state = await repo.load(db, room)
    mafia = [p for p in state["players"] if p["role"] in ("mafia", "don")]
    doctor = next(p for p in state["players"] if p["role"] == "doctor")
    detective = next(p for p in state["players"] if p["role"] == "detective")
    citizen = next(p for p in state["players"] if p["role"] == "citizen")
    views = {p["id"]: await game.get(db, room, p["id"]) for p in state["players"]}
    for p in state["players"]:
        view = views[p["id"]]
        assert view["voting_progress"] is None, "aggregate night actions could disclose presence of secret roles"
        assert not any("role" in public for public in view["players"])
        assert set(view["channel_state"]) == set(view["channels"])
        assert not view["channel_state"]["table"]["can_write"]
        assert view["channel_state"]["table"]["write_reason"]
        assert not view["host_online"] or view["online_count"] >= 1
    assert not views[citizen["id"]]["me"]["can_act"]
    assert views[doctor["id"]]["me"]["action_kind"] == "doctor_save"
    assert doctor["id"] in views[doctor["id"]]["me"]["action_targets"]
    assert detective["id"] not in views[detective["id"]]["me"]["action_targets"]
    assert not {p["id"] for p in mafia} & set(views[mafia[0]["id"]]["me"]["action_targets"])
    assert "mafia" not in views[citizen["id"]]["channel_state"]
    secret = await repo.message(db, room, "mafia", "Секрет", user_id=mafia[0]["id"], name=mafia[0]["name"])
    assert (await game.get(db, room, mafia[1]["id"]))["channel_state"]["mafia"]["latest_id"] == secret
    assert "mafia" not in (await game.get(db, room, citizen["id"]))["channel_state"]
    await game.control(db, room, 1, "pause")
    paused = await game.get(db, room, doctor["id"])
    assert paused["paused_phase"] == "night" and paused["phase_remaining"] > 0
    assert not paused["me"]["can_act"] and "паузы" in paused["me"]["write_reason"]
    await game.control(db, room, 1, "resume")
    await expire(db, room)
    await game.control(db, room, 1, "skip", (await repo.load(db, room))["phase_number"])
    state = await repo.load(db, room)
    await game.action(db, room, citizen["id"], state["phase_number"], "vote", None)
    view = await game.get(db, room, doctor["id"])
    assert view["votes"] == {}, "secret vote targets remain private while totals are public"
    assert view["voting_progress"] == {"submitted": 1, "total": 8}
    assert doctor["id"] not in view["me"]["action_targets"]
    await game.control(db, room, 1, "cancel")
    ended = await game.get(db, room, 1)
    assert ended["finished_at"] and ended["finish_reason"] == "host" and ended["phase_duration"] is None
    assert set(ended["channel_state"]) == {"table", "afterlife"}
    assert not any(c["can_write"] for c in ended["channel_state"].values())
    assert not await db.connection.fetchval("SELECT to_regclass('mafia_v1_matches')")
    print("PASS visible identity, presence privacy, nonce payload matching, channel ACL/metadata, redacted replies, explicit host transfer, actionable phases and secret-vote progress")


async def recovery_edges(db):
    room = await game.create(db, {"id": 200})
    for uid in range(201, 204):
        await game.join(db, room, {"id": uid})
    await game.control(db, room, 200, "start")
    state = await repo.load(db, room)
    phase = state["phase_number"]
    await expire(db, room)
    before = await repo.load(db, room)
    stale_nonce = uuid.uuid4()
    await denied(game.control(db, room, 200, "transfer", phase_number=phase, nonce=stale_nonce, target=201))
    assert (await repo.load(db, room))["host"] == 200
    assert not await repo.command_receipt(db, room, 200, stale_nonce), "a failed command must not reserve a nonce"
    now = await repo.now(db)
    await mutate(db, room, lambda s: rules.player(s, 201).update(seen=now-300))
    await game.control(db, room, 200, "transfer", phase_number=before["phase_number"], nonce=stale_nonce, target=201)
    assert (await repo.load(db, room))["host"] == 201
    view = await game.get(db, room, 203)
    assert not view["host_online"] and not view["can_claim"] and view["claim_available_at"] > now
    await denied(game.control(db, room, 203, "claim"))
    assert (await repo.load(db, room))["players"][1]["seen"] == now-300, "handoff must not fabricate online presence"
    # Receipt replay after a later handoff must never steal host privileges back.
    await game.control(db, room, 201, "transfer", target=202)
    assert (await game.control(db, room, 200, "transfer", phase_number=before["phase_number"], nonce=stale_nonce, target=201))["replayed"]
    assert (await repo.load(db, room))["host"] == 202
    await denied(game.get(db, room, 203, "unknown"), 403)
    await denied(chat.send(db, room, 203, "unknown", "Недоступный канал", uuid.uuid4()), 403)
    # A host leaving chooses someone alive and online, even if an earlier seat is dead.
    now = await repo.now(db)
    def prepare(s):
        rules.player(s, 200).update(alive=False, seen=now)
        rules.player(s, 201).update(alive=True, seen=now-200)
        rules.player(s, 203).update(alive=True, seen=now)
        # Keep the remaining game valid after the host's departure.
        rules.player(s, 201)["role"] = "mafia"
        rules.player(s, 203)["role"] = "citizen"
    await mutate(db, room, prepare)
    await game.control(db, room, 202, "leave")
    assert (await repo.load(db, room))["host"] == 203
    # An abandoned active table closes with a reason instead of awarding a phantom town win.
    lonely = await game.create(db, {"id": 300})
    for uid in range(301, 304):
        await game.join(db, lonely, {"id": uid})
    await game.control(db, lonely, 300, "start")
    def abandoned(s):
        for p in s["players"][1:]:
            p.update(left=True, alive=False)
    await mutate(db, lonely, abandoned)
    await game.control(db, lonely, 300, "leave")
    state = await repo.load(db, lonely)
    assert state["phase"] == "cancelled" and state["reason"] == "empty" and state["winner"] is None
    print("PASS stale transfer/failed nonce recovery/replay after later handoff, unknown channels, living-present successor and abandoned-table closure")


async def long_games(db):
    rng = random.Random(24102026)
    games, phases = 0, 0
    for seats in (4, 6, 8, 12, 20):
        for repetition in range(3):
            base = 10000 + games * 100
            room = await game.create(db, {"id": base}, seats=seats, tempo=("fast", "normal", "slow")[repetition],
                                     vote_mode="open" if repetition % 2 else "secret")
            for uid in range(base+1, base+seats):
                await game.join(db, room, {"id": uid})
            for _ in range(95):
                state = await repo.load(db, room)
                if state["phase"] in rules.TERMINAL:
                    break
                phases += 1
                for p in state["players"]:
                    view = await game.get(db, room, p["id"])
                    assert set(view["channel_state"]) == set(rules.channels(state, p))
                    assert all("role" not in q and "seen" not in q for q in view["players"])
                    assert (view["voting_progress"] is not None) == (state["phase"] == "voting")
                    if view["me"]["can_act"]:
                        targets = view["me"]["action_targets"] + ([None] if state["phase"] == "voting" else [])
                        await game.action(db, room, p["id"], state["phase_number"], view["me"]["action_kind"], rng.choice(targets))
                if phases % 11 == 0:
                    await game.control(db, room, state["host"], "pause")
                    pause = await game.get(db, room, state["host"])
                    assert pause["paused_phase"] == state["phase"] and pause["phase_duration"] == rules.phase_seconds(state["tempo"], state["phase"])
                    await game.control(db, room, state["host"], "resume")
                await expire(db, room)
            else:
                raise AssertionError("game exceeded the supported 30-round lifecycle")
            end = await game.get(db, room, base)
            assert end["phase"] == "finished" and end["winner"] in ("town", "mafia", "draw")
            assert all("role" in q for q in end["players"])
            assert not await db.connection.fetchval("SELECT EXISTS(SELECT 1 FROM mafia_online_seats WHERE room_id=$1)", room)
            games += 1
    print(f"PASS {games} long games with seeded legal choices, {phases} phases, 4/6/8/12/20 seats, all tempos, open/secret votes, pause/resume and channel privacy")


async def http_contract(db):
    app = FastAPI()
    app.include_router(api.router)
    actor = {"id": 500, "first_name": "Хозяин"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[api.participant] = lambda: actor
    app.dependency_overrides[api.router.dependencies[0].dependency] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/mafia-online/rooms", json={"seats": 8})
        assert created.status_code == 200, created.text
        room = created.json()["room_id"]
        automatic = await client.post(f"/mafia-online/rooms/{room}/control", json={"command": "settings", "settings": {"seats": 4, "roles_auto": True, "roles": ["don"]}})
        assert automatic.status_code == 200, automatic.text
        assert (await repo.load(db, room))["roles"] == []
        actor["id"] = 501
        assert (await client.post(f"/mafia-online/rooms/{room}/join", json={})).status_code == 200
        actor["id"] = 500
        path = f"/mafia-online/rooms/{room}"
        for channel in ("unknown", "MAFIA", ""):
            assert (await client.get(path, params={"channel": channel})).status_code == 422
        assert (await client.get(path, params={"channel": "mafia"})).status_code == 403
        assert (await client.post(path+"/control", json={"command": "transfer"})).status_code == 422
        payload = {"command": "transfer", "target": 501, "nonce": str(uuid.uuid4()), "phase_number": 99}
        assert (await client.post(path+"/control", json=payload)).status_code == 409
        payload["phase_number"] = 0
        assert (await client.post(path+"/control", json=payload)).status_code == 200
        assert (await client.post(path+"/control", json=payload)).json()["replayed"]
        payload["target"] = 500
        assert (await client.post(path+"/control", json=payload)).status_code == 409
        # One batched query, even for snapshots with multiple authorized channels.
        with patch.object(repo, "channel_latest", wraps=repo.channel_latest) as latest:
            view = (await client.get(path)).json()
            assert latest.call_count == 1 and latest.call_args.args[2] == ["table"]
        assert view["host_id"] == 501 and view["channel_state"]["table"]["latest_id"]
    print("PASS real HTTP transfer/target/nonce/phase validation, unknown-channel status codes and one batched metadata query")


async def main(dsn):
    schema = "mafia_online_audit_" + uuid.uuid4().hex[:12]
    conn = await asyncpg.connect(dsn)
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    try:
        await conn.execute(f'SET search_path TO "{schema}"')
        db = PGAdapter(conn)
        await repo.ensure_tables(db)
        await run(db)
        await recovery_edges(db)
        await long_games(db)
        await http_contract(db)
    finally:
        await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    asyncio.run(main(args.dsn))
