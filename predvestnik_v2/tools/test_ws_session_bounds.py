#!/usr/bin/env python3
"""Offline proof (audit A03, A07): the shared WS session keeps bounded memory.

- arbitrary client commands (the retired lot-room protocol) store nothing;
- a client that stops reading is closed with 1013 once its queue is full,
  and the backlog never exceeds WS_QUEUE_MAXSIZE;
- two tabs of one account: closing one keeps delivery to the other.
No network or database: the player-event listener is stubbed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from FastAPI import notifications


class Disconnect(Exception):
    pass


class FakeSocket:
    def __init__(self, *, stalled: bool = False) -> None:
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed_code: int | None = None
        self.stalled = stalled

    async def send_json(self, event: dict) -> None:
        if self.stalled:
            await asyncio.Future()   # never returns: reader stopped consuming
        self.sent.append(event)

    async def receive_text(self) -> str:
        raw = await self.inbox.get()
        if raw is None:
            raise Disconnect()
        return raw

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code


async def no_listener() -> bool:
    return False


async def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


async def run_session(socket: FakeSocket, user_id: int) -> asyncio.Task:
    task = asyncio.create_task(notifications.ws_session(socket, user_id))
    await wait_until(lambda: user_id in notifications._queues)
    return task


async def junk_commands_store_nothing() -> None:
    socket = FakeSocket()
    task = await run_session(socket, 1)
    for lot_id in range(1, 5001):
        for kind in ("lot_react", "sub_lot"):
            socket.inbox.put_nowait(json.dumps({"type": kind, "lot_id": lot_id}))
    socket.inbox.put_nowait("ping")
    await wait_until(lambda: socket.inbox.empty())
    assert not hasattr(notifications, "_lot_rooms") and not hasattr(notifications, "_react_last")
    socket.inbox.put_nowait(None)   # disconnect
    try:
        await asyncio.wait_for(task, 2)
    except Disconnect:
        pass
    assert 1 not in notifications._queues, "closed session must unregister"


async def stalled_reader_is_dropped() -> None:
    socket = FakeSocket(stalled=True)
    task = await run_session(socket, 2)
    max_backlog = 0
    for i in range(notifications.WS_QUEUE_MAXSIZE * 3):
        await notifications.notify(2, {"type": "data_changed", "n": i})
        for q in notifications._queues.get(2, ()):
            max_backlog = max(max_backlog, q.qsize())
    await asyncio.wait_for(task, 2)
    assert socket.closed_code == 1013, socket.closed_code
    assert max_backlog <= notifications.WS_QUEUE_MAXSIZE, max_backlog
    assert 2 not in notifications._queues
    assert await notifications.notify(2, {"type": "data_changed"}) is False, "dropped client is offline"


async def second_tab_survives_first_close() -> None:
    for close_first in ("a", "b"):
        a, b = FakeSocket(), FakeSocket()
        ta = await run_session(a, 3)
        tb = asyncio.create_task(notifications.ws_session(b, 3))
        await wait_until(lambda: len(notifications._queues.get(3, ())) == 2)
        gone, kept, gone_task, kept_task = (a, b, ta, tb) if close_first == "a" else (b, a, tb, ta)
        gone.inbox.put_nowait(None)
        try:
            await asyncio.wait_for(gone_task, 2)
        except Disconnect:
            pass
        assert await notifications.notify(3, {"type": "data_changed", "probe": close_first})
        await wait_until(lambda: any(e.get("probe") == close_first for e in kept.sent))
        kept.inbox.put_nowait(None)
        try:
            await asyncio.wait_for(kept_task, 2)
        except Disconnect:
            pass
        assert 3 not in notifications._queues


async def main() -> None:
    notifications.ensure_balance_listener = no_listener
    await junk_commands_store_nothing()
    await stalled_reader_is_dropped()
    await second_tab_survives_first_close()


asyncio.run(main())
print("ws session bounds: OK")
