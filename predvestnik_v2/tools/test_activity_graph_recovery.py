"""Deterministic proof of the graph's latency, freshness and concurrency bounds."""
import asyncio
import os
from pathlib import Path
import sys
import time
import threading
from datetime import date
from unittest.mock import AsyncMock, patch
from contextlib import asynccontextmanager
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('BOT_TOKEN', '1:offline')
os.environ.setdefault('DATABASE_URL', 'postgresql://offline@127.0.0.1:1/offline')
from bot.chat import activity_graph as g


async def main():
    calls = []
    @asynccontextmanager
    async def transaction():
        yield
    db=SimpleNamespace(connection=SimpleNamespace(transaction=transaction))
    def render(counts, start, **kwargs):
        calls.append(list(counts))
        time.sleep(.05)
        return b'png' + str(counts[-1]).encode()
    async def counts(*args):
        await asyncio.sleep(0)  # reproduce concurrent misses during SQL
        return date(2026, 1, 1), [1, 2, 3]
    g._cache.clear(); g._cached_at.clear()
    with patch.object(g, 'daily_counts', counts), patch.object(g, 'render', render), patch.object(g, 'RENDER_BUDGET_SEC', .5):
        results = await asyncio.gather(*(g.get_graph(db, 10, days=3) for _ in range(6)))
        assert results == [b'png3'] * 6 and len(calls) == 1
        key = next(iter(g._cache))
        g._cached_at[key] -= 61
        with patch.object(g, 'daily_counts', AsyncMock(return_value=(date(2026,1,1), [1,2,9]))):
            assert await g.get_graph(db, 10, days=3) == b'png3', 'stale photo served while refreshing'
            await asyncio.gather(*g._pending.values())
            assert await g.get_graph(db, 10, days=3) == b'png9'
        with patch.object(g, 'RENDER_BUDGET_SEC', .005):
            started = time.monotonic()
            assert await g.get_graph(db, 11, days=3) is None
            assert time.monotonic() - started < .1
            assert g._pending, 'timeout does not cancel rendering'
            with patch.object(g, 'MAX_PENDING_RENDERS', 1):
                assert await g.get_graph(db, 12, days=3) is None
                assert len(g._pending) == 1, 'queue bounded'
            await asyncio.gather(*g._pending.values())
            assert await g.get_graph(db, 11, days=3) == b'png3'
        loop=asyncio.get_running_loop();entered=asyncio.Event();release=threading.Event()
        def held_render(counts,start,**kwargs):
            loop.call_soon_threadsafe(entered.set)
            release.wait(2)
            return render(counts,start,**kwargs)
        with patch.object(g,'render',held_render):
            waiter = asyncio.create_task(g.get_graph(db, 13, days=3))
            try:
                await asyncio.wait_for(entered.wait(),1)
                waiter.cancel()
                try:await waiter
                except asyncio.CancelledError:pass
                assert g._pending, 'one cancelled caller does not cancel shared renderer'
            finally:release.set()
            await asyncio.gather(*g._pending.values())
        assert await g.get_graph(db, 13, days=3) == b'png3'
        await g.get_graph(db, 10, -999, days=3)
        assert len(calls) == 5, 'chat scope has its own cache'
        with patch.object(g, 'render', side_effect=RuntimeError('renderer unavailable')):
            assert await g.get_graph(db, 14, days=3) is None
        await asyncio.sleep(0)
        assert not g._pending
        assert await g.get_graph(db, 14, days=3) == b'png3', 'failure remains retryable'
    # Slow history reads are cancelled before returning the borrowed connection.
    cleaned=asyncio.Event()
    async def slow_counts(*args):
        try:await asyncio.sleep(10)
        finally:cleaned.set()
    with patch.object(g,'daily_counts',slow_counts),patch.object(g,'RENDER_BUDGET_SEC',.02):
        started=time.monotonic()
        assert await g.get_graph(db,1001) is None
        assert cleaned.is_set() and not g._pending
        assert time.monotonic()-started<.15
        cleaned.clear()
        key=(1002,0,g.DAYS,g.DEFAULT_THEME,g.local_now().date().isoformat())
        g._cache[key]=b'old';g._cached_at[key]=0
        assert await g.get_graph(db,1002)==b'old'
        assert cleaned.is_set()
    # SQL and render share one budget; fast queries don't grant a second budget.
    async def delayed_counts(*args):
        await asyncio.sleep(.04)
        return date(2026,1,1),[1,2,3]
    wait_render=AsyncMock(return_value=None)
    with patch.object(g,'daily_counts',delayed_counts),patch.object(g,'render',render),patch.object(g,'RENDER_BUDGET_SEC',.2),patch.object(g,'_wait_render',wait_render):
        assert await g.get_graph(db,1003) is None
        remaining=wait_render.call_args.kwargs['budget_sec']
        assert 0<remaining<.19, remaining
        await asyncio.gather(*g._pending.values())
    print('activity graph recovery: dedup, freshness, latency, bounded queue, cancellation and failure OK')


if __name__ == '__main__':
    asyncio.run(main())
