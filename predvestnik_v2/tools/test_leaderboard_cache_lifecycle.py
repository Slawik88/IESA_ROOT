#!/usr/bin/env python3
"""Concurrent top reads: cancellation isolation, shared failures and pool ownership, without PostgreSQL."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ttl_cache import TtlCache  # noqa: E402
from infrastructure import lazy_db  # noqa: E402
from services import leaderboards_v1 as boards  # noqa: E402


class Connection:
    async def fetchval(self, sql):
        await asyncio.sleep(0)
        return 1


class Pool:
    def __init__(self):
        self.acquired = 0
        self.released = 0

    async def acquire(self, *, timeout):
        self.acquired += 1
        return Connection()

    async def release(self, conn):
        self.released += 1


class CacheLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = TtlCache(45, max_entries=10)
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.loads = 0

    async def asyncTearDown(self):
        self.assertFalse(boards._INFLIGHT, "completed requests left a shared load behind")

    async def load(self):
        self.loads += 1
        self.started.set()
        await self.finish.wait()
        return [1]

    def request(self, load=None, key=("board",)):
        return asyncio.create_task(boards._cached(self.cache, key, load or self.load))

    async def test_cancel_waiter_does_not_cancel_other_readers(self):
        leader = self.request()
        await self.started.wait()
        cancelled = self.request()
        survivor = self.request()
        await asyncio.sleep(0)
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        self.finish.set()
        self.assertEqual(await asyncio.wait_for(asyncio.gather(leader, survivor), 1), [[1], [1]])
        self.assertEqual(self.loads, 1)

    async def test_cancel_leader_elects_one_replacement(self):
        leader = self.request()
        await self.started.wait()
        readers = [self.request() for _ in range(20)]
        await asyncio.sleep(0)
        leader.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await leader
        self.finish.set()
        self.assertEqual(await asyncio.wait_for(asyncio.gather(*readers), 1), [[1]] * 20)
        self.assertEqual(self.loads, 2, "replacement readers duplicated the reload")
        self.assertEqual(self.cache.get(("board",)), [1])

    async def test_all_readers_cancel_leave_no_background_load(self):
        leader = self.request()
        await self.started.wait()
        readers = [self.request() for _ in range(5)]
        await asyncio.sleep(0)
        for task in [leader, *readers]:
            task.cancel()
        results = await asyncio.gather(leader, *readers, return_exceptions=True)
        self.assertTrue(all(isinstance(result, asyncio.CancelledError) for result in results))
        self.assertIsNone(self.cache.get(("board",)))
        self.assertEqual(self.loads, 1)

    async def test_simultaneous_leader_and_waiter_cancellation_keeps_survivor(self):
        leader = self.request()
        await self.started.wait()
        cancelled = self.request()
        survivor = self.request()
        await asyncio.sleep(0)
        leader.cancel()
        cancelled.cancel()
        self.finish.set()
        results = await asyncio.wait_for(asyncio.gather(leader, cancelled, survivor, return_exceptions=True), 1)
        self.assertTrue(all(isinstance(result, asyncio.CancelledError) for result in results[:2]))
        self.assertEqual(results[2], [1])
        self.assertEqual(self.loads, 2)

    async def test_previously_handled_cancellation_does_not_prevent_takeover(self):
        leader = self.request()
        await self.started.wait()
        waiting = asyncio.Event()

        async def survivor():
            task = asyncio.current_task()
            task.cancel()
            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                pass   # simulate a caller that handled an earlier cancellation without uncancel()
            self.assertGreater(task.cancelling(), 0)
            waiting.set()
            return await boards._cached(self.cache, ("board",), self.load)

        waiter = asyncio.create_task(survivor())
        await waiting.wait()
        leader.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await leader
        self.finish.set()
        self.assertEqual(await asyncio.wait_for(waiter, 1), [1])

    async def test_failure_is_shared_once_and_next_request_can_retry(self):
        error = RuntimeError("database unavailable")

        async def broken():
            self.loads += 1
            self.started.set()
            await self.finish.wait()
            raise error

        leader = self.request(broken)
        await self.started.wait()
        readers = [self.request(broken) for _ in range(20)]
        await asyncio.sleep(0)
        self.finish.set()
        results = await asyncio.wait_for(asyncio.gather(leader, *readers, return_exceptions=True), 1)
        self.assertTrue(all(result is error for result in results))
        self.assertEqual(self.loads, 1, "one failed reload triggered a retry storm")
        self.assertIsNone(self.cache.get(("board",)))
        self.assertEqual(await self.request(), [1])

    async def test_owner_can_release_database_before_waiting_for_telegram(self):
        pool = Pool()
        async with lazy_db.lazy_connection(pool, source="cache-test") as db:
            async def load():
                return await db.connection.fetchval("SELECT 1")

            self.assertEqual(await boards._cached(self.cache, ("board",), load), 1)
            self.assertTrue(await lazy_db.release_current(), "shared loader stole the request's connection ownership")
            self.assertEqual((pool.acquired, pool.released), (1, 1))
            self.assertFalse(db.holds_connection)
        self.assertEqual(lazy_db.held_connections().get("cache-test", 0), 0)

    async def test_replacement_uses_its_own_database_handle(self):
        pool = Pool()
        tasks = []

        async def request(is_leader):
            async with lazy_db.lazy_connection(pool, source="cache-cancel-test") as db:
                async def load():
                    tasks.append(asyncio.current_task())
                    value = await db.connection.fetchval("SELECT 1")
                    if is_leader:
                        self.started.set()
                        await self.finish.wait()
                    return value
                return await boards._cached(self.cache, ("board",), load)

        leader = asyncio.create_task(request(True))
        await self.started.wait()
        waiter = asyncio.create_task(request(False))
        await asyncio.sleep(0)
        leader.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await leader
        self.assertEqual(await asyncio.wait_for(waiter, 1), 1)
        self.assertEqual(tasks, [leader, waiter], "SQL ran outside the owning request")
        self.assertEqual((pool.acquired, pool.released), (2, 2))
        self.assertEqual(lazy_db.held_connections().get("cache-cancel-test", 0), 0)

    async def test_keys_and_caches_do_not_block_each_other(self):
        slow = self.request()
        await self.started.wait()

        async def quick():
            return [2]

        self.assertEqual(await self.request(quick, key=("other",)), [2])
        other_cache = TtlCache(45, max_entries=10)
        self.assertEqual(await boards._cached(other_cache, ("board",), quick), [2])
        self.finish.set()
        self.assertEqual(await slow, [1])

    async def test_cached_empty_result_does_not_reload(self):
        async def empty():
            self.loads += 1
            return []

        self.assertEqual(await self.request(empty), [])
        self.assertEqual(await self.request(empty), [])
        self.assertEqual(self.loads, 1)


if __name__ == "__main__":
    unittest.main()
