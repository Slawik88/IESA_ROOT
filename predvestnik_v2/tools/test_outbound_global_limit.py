#!/usr/bin/env python3
"""Global Telegram quota and per-chat spacing under overload, with a controlled clock."""
import asyncio
import sys
import time
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.methods import GetChatMember, SendMessage  # noqa: E402
from aiogram.exceptions import TelegramRetryAfter  # noqa: E402
from bot.middlewares import outbound_throttle as outbound  # noqa: E402


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleepers = []

    async def sleep(self, delay):
        future = asyncio.get_running_loop().create_future()
        self.sleepers.append((self.now + delay, future))
        await future

    async def advance(self, seconds):
        self.now += seconds
        for deadline, future in self.sleepers:
            if deadline <= self.now and not future.done():
                future.set_result(None)
        await self.settle()

    async def settle(self):
        for _ in range(6):
            await asyncio.sleep(0)


class GlobalLimit(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = Clock()
        self.enterContext(patch.object(outbound, "time", SimpleNamespace(
            monotonic=lambda: self.clock.now, perf_counter=time.perf_counter)))
        self.enterContext(patch.object(outbound, "asyncio", SimpleNamespace(
            sleep=self.clock.sleep, create_task=asyncio.create_task,
            get_running_loop=asyncio.get_running_loop, CancelledError=asyncio.CancelledError)))
        self.throttle = outbound.OutboundThrottleMiddleware()
        self.enterContext(patch.object(outbound, "logger", SimpleNamespace(warning=lambda *args: None)))
        self.sent = []
        self.tasks = []
        self.limit = outbound._GLOBAL_MAX_PER_SEC

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        pumps = [lane.pump for lane in self.throttle._lanes.values() if lane.pump]
        for task in pumps:
            task.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)

    async def record(self, bot, method):
        self.sent.append((self.clock.now, getattr(method, "text", "read")))
        return True

    def request(self, method=None, make_request=None):
        task = asyncio.create_task(self.throttle(
            make_request or self.record, None, method or GetChatMember(chat_id=-1, user_id=1)))
        self.tasks.append(task)
        return task

    async def test_hundred_reads_respect_each_global_window(self):
        for _ in range(self.limit * 4):
            self.request()
        await self.clock.settle()
        self.assertEqual(len(self.sent), self.limit)
        for window in range(1, 4):
            await self.clock.advance(1)
            self.assertEqual(len(self.sent), self.limit * (window + 1))
        self.assertTrue(all(task.done() for task in self.tasks))
        self.assertEqual(Counter(moment for moment, _ in self.sent), {window: self.limit for window in range(4)})

    async def test_cancelled_global_waiters_do_not_consume_next_window(self):
        for _ in range(self.limit * 2):
            self.request()
        await self.clock.settle()
        for task in self.tasks[self.limit:]:
            task.cancel()
        await self.clock.settle()
        await self.clock.advance(1)
        for _ in range(self.limit):
            self.request()
        await self.clock.settle()
        self.assertEqual(len(self.sent), self.limit * 2)

    async def test_wait_is_rechecked_after_an_early_wakeup(self):
        for _ in range(self.limit + 1):
            self.request()
        await self.clock.settle()
        # A sleeper returning early must not grant a slot before the window expires.
        self.clock.now = 0.5
        for _, future in self.clock.sleepers:
            if not future.done():
                future.set_result(None)
        await self.clock.settle()
        self.assertEqual(len(self.sent), self.limit)
        await self.clock.advance(0.5)
        self.assertEqual(len(self.sent), self.limit + 1)

    async def test_chat_messages_keep_spacing_after_several_full_windows(self):
        for _ in range(self.limit * 3):
            self.request()
        await self.clock.settle()
        self.request(SendMessage(chat_id=-100, text="first"))
        self.request(SendMessage(chat_id=-100, text="second"))
        await self.clock.settle()
        for _ in range(3):
            await self.clock.advance(1)
        await self.clock.advance(outbound._MIN_INTERVAL_PER_CHAT_SEC)
        self.assertTrue(all(task.done() for task in self.tasks))
        messages = [moment for moment, text in self.sent if text != "read"]
        self.assertEqual(len(messages), 2)
        self.assertGreaterEqual(messages[1] - messages[0] + 1e-9, outbound._MIN_INTERVAL_PER_CHAT_SEC)
        self.assertLessEqual(max(Counter(int(moment) for moment, _ in self.sent).values()), self.limit)

    async def test_cancelled_chat_waiter_does_not_spend_global_quota(self):
        for _ in range(self.limit):
            self.request()
        await self.clock.settle()
        cancelled = self.request(SendMessage(chat_id=-100, text="cancelled"))
        await self.clock.settle()
        cancelled.cancel()
        await self.clock.settle()
        await self.clock.advance(1)
        for _ in range(self.limit):
            self.request()
        await self.clock.settle()
        self.assertEqual(len(self.sent), self.limit * 2)
        self.assertNotIn("cancelled", [text for _, text in self.sent])

    async def test_urgent_chat_message_keeps_priority_while_global_quota_is_full(self):
        for _ in range(self.limit):
            self.request()
        await self.clock.settle()
        self.request(SendMessage(chat_id=-100, text="ordinary"))
        await self.clock.settle()
        with outbound.urgent():
            self.request(SendMessage(chat_id=-100, text="urgent"))
        await self.clock.settle()
        await self.clock.advance(1)
        await self.clock.advance(outbound._MIN_INTERVAL_PER_CHAT_SEC)
        self.assertEqual([text for _, text in self.sent if text != "read"], ["urgent", "ordinary"])

    async def test_retries_also_wait_for_global_quota(self):
        attempted = set()

        async def retry_once(bot, method):
            await self.record(bot, method)
            if method.user_id not in attempted:
                attempted.add(method.user_id)
                raise TelegramRetryAfter(method=method, message="retry", retry_after=0)
            return True

        for uid in range(self.limit):
            self.request(GetChatMember(chat_id=-1, user_id=uid), make_request=retry_once)
        await self.clock.settle()
        await self.clock.advance(0.5)
        self.assertEqual(len(self.sent), self.limit, "retries bypassed the full global window")
        await self.clock.advance(0.5)
        self.assertEqual(len(self.sent), self.limit * 2)
        self.assertTrue(all(task.done() and task.result() for task in self.tasks))

    async def test_message_retry_keeps_chat_spacing(self):
        async def retry_once(bot, method):
            await self.record(bot, method)
            if len(self.sent) == 1:
                raise TelegramRetryAfter(method=method, message="retry", retry_after=0)
            return True

        task = self.request(SendMessage(chat_id=-100, text="retry"), make_request=retry_once)
        await self.clock.settle()
        await self.clock.advance(0.5)
        self.assertEqual(len(self.sent), 1)
        await self.clock.advance(outbound._MIN_INTERVAL_PER_CHAT_SEC - 0.5)
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(task.done() and task.result())

    async def test_cancellation_during_retry_delay_does_not_send_again(self):
        async def always_retry(bot, method):
            await self.record(bot, method)
            raise TelegramRetryAfter(method=method, message="retry", retry_after=0)

        task = self.request(make_request=always_retry)
        await self.clock.settle()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await self.clock.advance(1)
        for _ in range(self.limit):
            self.request()
        await self.clock.settle()
        self.assertEqual(len(self.sent), self.limit + 1)

    async def test_retry_limit_still_stops_after_three_retries(self):
        async def always_retry(bot, method):
            await self.record(bot, method)
            raise TelegramRetryAfter(method=method, message="retry", retry_after=0)

        task = self.request(make_request=always_retry)
        await self.clock.settle()
        for _ in range(outbound._MAX_RETRY_ATTEMPTS):
            await self.clock.advance(0.5)
        with self.assertRaises(TelegramRetryAfter):
            await task
        self.assertEqual(len(self.sent), outbound._MAX_RETRY_ATTEMPTS + 1)


if __name__ == "__main__":
    unittest.main()
