"""Independent web lifecycle: games progress even after every browser closes."""
import asyncio
from loguru import logger

from infrastructure.database import connect_direct, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online_phases as engine


async def tick(db):
    # A finite horizon avoids chasing newly created rooms under continuous traffic.
    horizon, after = await repo.latest_id(db), 0
    while True:
        batch = await repo.due(db, after, horizon)
        for room_id in batch:
            try:
                async with db.connection.transaction():
                    state = await repo.load(db, room_id, lock=True, skip_locked=True)
                    if state:
                        await engine.advance(db, state, await repo.now(db))
            except Exception:
                logger.exception("Online Mafia room {} failed; continuing other rooms", room_id)
        if len(batch) < 100:
            return
        after = batch[-1]


async def run():
    """Wait for the nearest durable deadline or a committed change to that deadline.

    LISTEN uses its own connection, never a permanently borrowed pool slot.
    A 30-second rescan covers lost events; a failed listener retries after at most
    two seconds. Clear the wake-up before querying to avoid a lost early deadline.
    """
    listener = None
    wake = asyncio.Event()
    try:
        while True:
            if listener is None:
                try:
                    listener = await asyncio.wait_for(connect_direct(), timeout=2.0)
                    listener.add_termination_listener(lambda _conn: wake.set())
                    await asyncio.wait_for(
                        listener.add_listener(repo.SCHEDULE_CHANNEL, lambda *_args: wake.set()), timeout=2.0)
                except Exception:
                    logger.exception("Online Mafia deadline listener unavailable; using fallback")
                    if listener is not None and not listener.is_closed():
                        listener.terminate()
                    listener = None
            wake.clear()
            try:
                async with get_pool().acquire() as connection:
                    db = PGAdapter(connection)
                    await tick(db)
                    delay = await repo.next_delay(db, maximum=30.0 if listener else 2.0)
            except Exception:
                logger.exception("Online Mafia scheduler failed; will retry")
                delay = 2.0
            if listener is not None and listener.is_closed():
                listener = None
                delay = min(delay, 2.0)
            try:
                await asyncio.wait_for(wake.wait(), timeout=delay)
            except TimeoutError:
                pass
    finally:
        if listener is not None and not listener.is_closed():
            listener.terminate()
