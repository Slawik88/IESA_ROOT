"""PostgreSQL proof for commit-only, user-scoped live player events."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if (urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost"}):
    raise SystemExit("Only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn


async def main() -> None:
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import balance_events

    listener = await asyncpg.connect(args.dsn, server_settings={"search_path": "predvestnik,public"})
    writer = await asyncpg.connect(args.dsn, server_settings={"search_path": "predvestnik,public"})
    db = PGAdapter(writer)
    await balance_events.ensure_schema(db)
    events: asyncio.Queue[dict] = asyncio.Queue()

    def receive(_conn, _pid, _channel, payload: str) -> None:
        events.put_nowait(json.loads(payload))

    await listener.add_listener(balance_events.CHANNEL, receive)
    user_id = 990000077
    await writer.execute(
        "INSERT INTO users(user_tg_id,user_tg_username) VALUES($1,'balance_event') ON CONFLICT DO NOTHING",
        user_id,
    )
    await writer.execute(
        "INSERT INTO skins_v3_essence_accounts(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id
    )
    await writer.execute(
        "INSERT INTO echo_shard_accounts_v1(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id
    )

    tx = writer.transaction()
    await tx.start()
    await writer.execute(
        "UPDATE users SET user_balance_mora=user_balance_mora+17, "
        "user_balance_zarniki=user_balance_zarniki+2 WHERE user_tg_id=$1",
        user_id,
    )
    try:
        await asyncio.wait_for(events.get(), timeout=0.15)
        raise AssertionError("NOTIFY escaped before COMMIT")
    except asyncio.TimeoutError:
        pass
    await tx.commit()
    event = await asyncio.wait_for(events.get(), timeout=2)
    assert event["type"] == "balance_changed" and event["user_id"] == user_id
    assert float(event["mora"]) >= 17 and float(event["zarniki"]) >= 2

    await writer.execute("UPDATE users SET user_tg_username='live_profile' WHERE user_tg_id=$1", user_id)
    profile_event = await asyncio.wait_for(events.get(), timeout=2)
    assert profile_event == {"type": "data_changed", "user_id": user_id, "scope": "profile"}

    await writer.execute(
        "INSERT INTO web_notifications(user_id,payload) VALUES($1,'{}')", user_id
    )
    pending_event = await asyncio.wait_for(events.get(), timeout=2)
    assert pending_event == {"type": "notification_pending", "user_id": user_id}

    await writer.execute(
        "UPDATE skins_v3_essence_accounts SET balance=balance+5 WHERE user_id=$1", user_id
    )
    assert (await asyncio.wait_for(events.get(), timeout=2))["essence"] >= 5
    await writer.execute("UPDATE echo_shard_accounts_v1 SET balance=balance+3 WHERE user_id=$1", user_id)
    assert (await asyncio.wait_for(events.get(), timeout=2))["echo_shards"] >= 3

    # The application bridge forwards the database event to the authenticated
    # user's existing WebSocket queue without another profile read.
    from FastAPI import notifications
    ws_queue: asyncio.Queue[dict] = asyncio.Queue()
    notifications.register(user_id, ws_queue)
    await notifications.ensure_balance_listener()
    await writer.execute("UPDATE users SET user_balance_diamonds=user_balance_diamonds+1 WHERE user_tg_id=$1", user_id)
    bridged = await asyncio.wait_for(ws_queue.get(), timeout=2)
    assert bridged["type"] == "balance_changed" and float(bridged["diamonds"]) >= 1
    notifications.unregister(user_id)

    await listener.remove_listener(balance_events.CHANNEL, receive)
    await listener.close()
    await writer.close()
    print("OK: live player events are scoped, transactional and polling-free")


if __name__ == "__main__":
    asyncio.run(main())
