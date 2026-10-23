"""Independent web lifecycle: games progress even after every browser closes."""
import asyncio
from loguru import logger

from infrastructure.database import get_pool
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
    while True:
        await asyncio.sleep(2)
        try:
            async with get_pool().acquire() as connection:
                await tick(PGAdapter(connection))
        except Exception:
            logger.exception("Online Mafia scheduler failed; will retry")
