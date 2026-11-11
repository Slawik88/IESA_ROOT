"""Widget limits, creator access and bounded failure handling; no database or real Telegram."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_TOKEN", "123456:SIM-TOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:1/widgets_contract")

from aiogram.types import Update
from bot.middlewares import widget_query as adapter
from core import widgets as rules
from core.widgets import profile
from infrastructure.telegram_widgets import AnswerWidgetQuery, SendWidget, WidgetQuery
from services import widgets


def query(**changes) -> Update:
    raw = {"id": "test-query", "from": {"id": 1}, "chat": {"id": 1, "type": "private"},
           "message_id": 10, "type": {"type": "data"}, "data": "ping:s"}
    raw.update(changes)
    return Update.model_validate({"update_id": 1, "widget_query": raw})


class Limits(unittest.TestCase):
    def test_templates_and_sample_states_fit_profile(self):
        for key in rules.REGISTRY:
            with self.subTest(key=key):
                source = rules.html(key)
                self.assertEqual(rules.size_problems(source), [])
                self.assertLessEqual(rules.packed_size(source), rules.PACKED_BUDGET)
                self.assertEqual(profile.problems(source), [])
                rules.encode({**widgets.module(key).SAMPLE, "r": 9999999999999})

    def test_utf8_limits_and_bad_queries(self):
        for data in (None, "", "ping", "unknown:s", "ping:", "ping:s:" + "я" * 30):
            self.assertIsNone(rules.parse_query(data))
        self.assertEqual(rules.parse_query("ping:s"), ("ping", "s", []))
        with self.assertRaises(ValueError):
            rules.encode({"t": "я" * 1024})
        self.assertTrue(rules.size_problems("x" * (rules.MAX_HTML_BYTES + 1)))
        self.assertTrue(rules.size_problems("a\x00b"))

    def test_api_serialization_keeps_unknown_fields(self):
        self.assertEqual(adapter.widget_payload(query())[0], "widget_query")
        parsed = WidgetQuery.model_validate(query().model_extra["widget_query"])
        self.assertTrue(parsed.in_own_dm)
        self.assertFalse(parsed.model_copy(update={"inline_message_id": "forward"}).in_own_dm)
        self.assertEqual(SendWidget(chat_id=1, html="<b>x</b>").__api_method__, "sendWidget")


class Failures(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_calls_release_the_db_owning_task(self):
        from infrastructure import lazy_db

        connection = AsyncMock()
        pool = AsyncMock()
        pool.acquire.return_value = connection
        calls = []
        async with lazy_db.lazy_connection(pool, source="widget-contract") as db:
            # PollingDelivery.admit already takes a connection before this middleware.
            await db.connection.fetchval("SELECT 1")

            async def answer(actual_db, _query):
                await actual_db.connection.fetchval("SELECT 1")
                return '{}', '{}'

            async def outbound(method):
                await lazy_db.release_current()
                self.assertFalse(db.holds_connection, "Telegram must not hold the update's pool slot")
                calls.append(method.__api_method__)
                return True

            with patch.object(widgets, "answer", side_effect=answer):
                await adapter.widget_query_middleware(AsyncMock(), query(), {"bot": outbound, "db": db})
        self.assertEqual(calls, ["answerWidgetQuery", "editMessageWidgetData"])
        self.assertEqual(pool.release.await_count, 1)

    async def test_http_requires_creator_and_uses_only_own_dm(self):
        import httpx
        from fastapi import FastAPI
        from types import SimpleNamespace
        from FastAPI.deps import get_db
        from FastAPI.routers.bot_admin import auth, widgets as routes
        from services.admin_access import staff_principal

        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: object()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/bot-admin/api/widgets")).status_code, 401)
            for rank in range(1, 6):
                app.dependency_overrides[auth.staff_user] = lambda rank=rank: staff_principal(2, rank, {"section:widgets": 1})
                self.assertEqual((await client.get("/bot-admin/api/widgets")).status_code, 403)
                self.assertEqual((await client.post("/bot-admin/api/widgets/send", json={"key": "ping"})).status_code, 403)
            app.dependency_overrides[auth.staff_user] = lambda: staff_principal(1, 6)
            with patch.object(widgets, "switched_off", new=AsyncMock(return_value=False)):
                response = await client.get("/bot-admin/api/widgets")
            self.assertEqual(response.status_code, 200)
            self.assertEqual({item["key"] for item in response.json()["items"]}, set(rules.REGISTRY))
            bot = object()
            with patch.object(routes, "get_bot", return_value=bot), \
                 patch.object(widgets, "send", new=AsyncMock(return_value=SimpleNamespace(message_id=1))) as send, \
                 patch.object(routes.admin_people, "audit", new_callable=AsyncMock):
                response = await client.post("/bot-admin/api/widgets/send", json={"key": "ping", "user_id": 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(send.await_args.args[2:], (1, "ping"))
            cancelled = asyncio.Event()

            async def stalled_send(*_):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            with patch.object(routes, "get_bot", return_value=bot), patch.object(widgets, "send", side_effect=stalled_send), \
                 patch.object(rules, "ANSWER_BUDGET_SEC", .01):
                response = await client.post("/bot-admin/api/widgets/send", json={"key": "ping"})
            self.assertEqual(response.status_code, 504)
            self.assertTrue(cancelled.is_set())

    async def invoke(self, event=None, bot=None):
        downstream = AsyncMock(return_value="ordinary-command")
        bot = bot or AsyncMock()
        result = await adapter.widget_query_middleware(downstream, event or query(), {"bot": bot, "db": object()})
        return result, bot, downstream

    async def test_ordinary_update_still_reaches_handlers(self):
        result, _, downstream = await self.invoke(Update(update_id=2))
        self.assertEqual(result, "ordinary-command")
        downstream.assert_awaited_once()

    async def test_service_checks_creator_before_db_or_telegram(self):
        bot = AsyncMock()
        with patch.object(widgets, "may_use", return_value=False), patch.object(widgets, "switched_off", new_callable=AsyncMock) as switch:
            with self.assertRaises(widgets.Refused):
                await widgets.send(bot, object(), 2, "ping")
        switch.assert_not_awaited()
        bot.assert_not_awaited()

    async def test_stalled_handler_is_cancelled_and_answered(self):
        cancelled = asyncio.Event()

        async def stalled(*_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(widgets, "answer", side_effect=stalled), patch.object(rules, "WORK_BUDGET_SEC", .01):
            _, bot, downstream = await asyncio.wait_for(self.invoke(), .5)
        self.assertTrue(cancelled.is_set())
        self.assertIn("занят", json.loads(bot.await_args.args[0].data)["e"])
        downstream.assert_not_awaited()
        await self.test_ordinary_update_still_reaches_handlers()

    async def test_crashing_handler_is_answered(self):
        with patch.object(widgets, "answer", side_effect=RuntimeError("widget failure")):
            _, bot, _ = await self.invoke()
        self.assertIsInstance(bot.await_args.args[0], AnswerWidgetQuery)
        self.assertIn("пошло не так", json.loads(bot.await_args.args[0].data)["e"])

    async def test_stalled_persist_is_cancelled_after_answer(self):
        cancelled = asyncio.Event()

        async def stalled(*_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(widgets, "answer", new=AsyncMock(return_value=('{}', '{}'))), \
             patch.object(widgets, "persist", side_effect=stalled), patch.object(rules, "PERSIST_BUDGET_SEC", .01):
            _, bot, _ = await asyncio.wait_for(self.invoke(), .5)
        self.assertTrue(cancelled.is_set())
        bot.assert_awaited_once()

    async def test_failed_answer_transport_does_not_escape(self):
        with patch.object(widgets, "answer", new=AsyncMock(return_value=('{}', None))):
            await self.invoke(bot=AsyncMock(side_effect=RuntimeError("transport failure")))

    async def test_shutdown_cancellation_propagates(self):
        with patch.object(widgets, "answer", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.invoke()

    async def test_malformed_query_is_answered_without_service(self):
        with patch.object(widgets, "answer", new_callable=AsyncMock) as answer:
            _, bot, _ = await self.invoke(query(**{"from": None}))
        answer.assert_not_awaited()
        self.assertIn("устарел", json.loads(bot.await_args.args[0].data)["e"])


if __name__ == "__main__":
    unittest.main()
