"""Private card security, legacy callback compatibility and interrupted delivery; no database."""

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
os.environ.setdefault("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import Message, Update
from bot import widget_cards as adapter
from core import widget_cards as rules, widgets
from core.widgets import profile
from infrastructure.repositories import widget_cards as repo
from infrastructure.telegram_widgets import SendWidget, WidgetQuery
from services import widget_cards as service


def row(**changes):
    return dict(
        token="abcdefghijklmnop",
        bot_id=123456,
        owner_id=10,
        chat_id=10,
        message_id=100,
        feature="pets",
        source="🐾 <b>Корм: 25 🪙</b>",
        parse_mode="HTML",
        revision=2,
        seen_revision=2,
        ready=True,
        **changes,
    )


def message(bot, *, widget=True, **changes):
    raw = dict(
        message_id=100,
        date=1,
        chat={"id": 10, "type": "private"},
        **{"from": {"id": 10, "is_bot": False, "first_name": "Тест"}},
    )
    if widget:
        raw["widget"] = {"chat_data": "{}"}
    return Message.model_validate({**raw, **changes}, context={"bot": bot})


def event(bot, *, action="pt:token", sender=10):
    return Update.model_validate(
        dict(
            update_id=1,
            callback_query=dict(
                id="cb",
                **{"from": {"id": sender, "is_bot": False, "first_name": "Тест"}},
                chat_instance="s",
                data=action,
                message=message(bot).model_dump(exclude_none=True),
            ),
        ),
        context={"bot": bot},
    )


class Pure(unittest.TestCase):
    def test_template_and_adversarial_payloads_fit(self):
        html = widgets.html("card")
        self.assertEqual(profile.problems(html), [])
        self.assertEqual(widgets.size_problems(html), [])
        self.assertLess(widgets.packed_size(html), widgets.PACKED_BUDGET)
        for source in (
            "Я" * 8000,
            "W" * 8000,
            "👩‍👩‍👦" * 500,
            '\\"' * 4000,
            "\n" * 500,
        ):
            saved = row()
            saved["source"] = source
            for page in range(len(rules.pages(source))):
                state = rules.snapshot(saved, page)
                self.assertLessEqual(sum(map(len, state["l"])), rules.PAGE_CHARS)
                self.assertLessEqual(len(state["l"]), rules.PAGE_LINES)
                self.assertLessEqual(len(widgets.encode(state).encode()), 1024)
            self.assertEqual("".join("".join(p) for p in rules.pages(source)), source)

    def test_hydration_keeps_utf16_links_and_bot_binding(self):
        bot = Bot("123456:SIM-TOKEN")
        value = adapter._message(
            message(bot),
            '😀 <b>Цена</b> <a href="https://example.org">сайт</a>',
            "HTML",
        )
        self.assertEqual(value.text, "😀 Цена сайт")
        self.assertEqual(value.entities[0].offset, 3)
        self.assertIn("<b>Цена</b>", value.html_text)
        self.assertIn('href="https://example.org"', value.html_text)
        self.assertIs(value.bot, bot)


class Delivery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Bot("123456:SIM-TOKEN")
        self.bot.session.make_request = AsyncMock(return_value=True)
        self.db = object()

    async def asyncTearDown(self):
        await self.bot.session.close()

    async def test_group_business_force_reply_keep_existing_text(self):
        for raw in (
            dict(chat={"id": -10, "type": "supergroup", "title": "чат"}),
            dict(business_connection_id="business"),
        ):
            with patch.object(service, "enabled", new=AsyncMock()) as check:
                await adapter.reply(
                    message(self.bot, widget=False, **raw),
                    self.db,
                    "pets",
                    "text",
                    parse_mode="HTML",
                )
                check.assert_not_called()
                self.assertEqual(
                    self.bot.session.make_request.await_args.args[1].__api_method__,
                    "sendMessage",
                )

    async def test_send_binds_real_message_and_bad_api_falls_back(self):
        calls = []

        async def send(bot, method, **kwargs):
            calls.append(method)
            return message(self.bot)

        self.bot.session.make_request.side_effect = send
        with (
            patch.object(service, "enabled", new=AsyncMock(return_value=True)),
            patch.object(repo, "create", new=AsyncMock(return_value=row())),
            patch.object(repo, "bind", new=AsyncMock()) as bind,
        ):
            result = await adapter.reply(
                message(self.bot, widget=False), self.db, "pets", "<b>Питомцы</b>"
            )
            self.assertIsInstance(calls[0], SendWidget)
            self.assertEqual(calls[0].reply_parameters.message_id, 100)
            self.assertEqual(result.html_text, "<b>Питомцы</b>")
            bind.assert_awaited_once_with(self.db, "abcdefghijklmnop", 100)
        self.bot.session.make_request.side_effect = [
            TelegramBadRequest(method=calls[0], message="unknown method"),
            message(self.bot),
        ]
        with (
            patch.object(repo, "create", new=AsyncMock(return_value=row())),
            patch.object(repo, "discard", new=AsyncMock()) as discard,
        ):
            await adapter._deliver(self.bot, self.db, 10, "pets", "text", "HTML", None)
            discard.assert_awaited_once()

    async def test_guard_rejects_unseen_unready_expired_foreign_and_blocked_before_domain(
        self,
    ):
        downstream = AsyncMock()
        for saved, sender, allowed in (
            (None, 10, True),
            (row(), 11, True),
            (row(), 10, False),
            ({**row(), "ready": False}, 10, True),
            ({**row(), "seen_revision": 1}, 10, True),
        ):
            with (
                patch.object(repo, "get", new=AsyncMock(return_value=saved)),
                patch.object(service, "available", new=AsyncMock(return_value=allowed)),
            ):
                await adapter.CardCallbacks()(
                    downstream,
                    event(self.bot, sender=sender),
                    {"bot": self.bot, "db": self.db},
                )
        downstream.assert_not_called()

    async def test_fallback_sends_exact_text_without_domain_buttons_and_acknowledges(
        self,
    ):
        downstream = AsyncMock()
        with (
            patch.object(repo, "get", new=AsyncMock(return_value=row())),
            patch.object(service, "available", new=AsyncMock(return_value=True)),
            patch.object(repo, "set_enabled", new=AsyncMock()) as preference,
            patch.object(repo, "acknowledge", new=AsyncMock()) as ack,
        ):
            await adapter.CardCallbacks()(
                downstream,
                event(self.bot, action=rules.PLAIN_CALLBACK),
                {"bot": self.bot, "db": self.db},
            )
            preference.assert_awaited_once_with(self.db, 10, False)
            ack.assert_awaited_once_with(self.db, "abcdefghijklmnop", 2)
            outgoing = self.bot.session.make_request.await_args_list[0].args[1]
            self.assertEqual(outgoing.text, row()["source"])
            self.assertIsNone(outgoing.reply_markup)
        downstream.assert_not_called()

    async def test_callbacks_serialize_in_same_task_and_release_context(self):
        middleware = adapter.CardCallbacks()
        trace = []

        async def handler(update, data):
            self.assertEqual(update.callback_query.message.text, "🐾 Корм: 25 🪙")
            self.assertIsNotNone(adapter._editing.get())
            trace.append("start")
            await asyncio.sleep(0.01)
            trace.append("end")

        with (
            patch.object(repo, "get", new=AsyncMock(return_value=row())),
            patch.object(service, "available", new=AsyncMock(return_value=True)),
        ):
            await asyncio.gather(
                *(
                    middleware(
                        handler, event(self.bot), {"bot": self.bot, "db": self.db}
                    )
                    for _ in range(2)
                )
            )
        self.assertEqual(trace, ["start", "end", "start", "end"])
        self.assertIsNone(adapter._editing.get())
        self.assertEqual(len(middleware._locks), 0)

    async def test_partial_edits_never_mark_ready_and_keep_recovery(self):
        for fail_at in (1, 2, 3, 4):
            seen = []

            async def transport(bot, method, **kwargs):
                seen.append(method)
                if len(seen) == fail_at:
                    raise RuntimeError("broken transport")
                return message(self.bot)

            self.bot.session.make_request.side_effect = transport
            token = adapter._editing.set(
                adapter._Editing(self.db, row(), message(self.bot))
            )
            try:
                with (
                    patch.object(repo, "replace", new=AsyncMock(return_value=row())),
                    patch.object(repo, "finish", new=AsyncMock()) as finish,
                ):
                    with self.assertRaises(RuntimeError):
                        await adapter.CardEdits()(
                            AsyncMock(),
                            self.bot,
                            EditMessageText(chat_id=10, message_id=100, text="new"),
                        )
                    finish.assert_not_called()
                    self.assertEqual(
                        seen[0].reply_markup.inline_keyboard[0][0].callback_data,
                        rules.PLAIN_CALLBACK,
                    )
            finally:
                adapter._editing.reset(token)

    async def test_not_modified_is_success_and_edit_returns_message(self):
        calls = []

        async def transport(bot, method, **kwargs):
            calls.append(method)
            raise TelegramBadRequest(method=method, message="message is not modified")

        self.bot.session.make_request.side_effect = transport
        token = adapter._editing.set(
            adapter._Editing(self.db, row(), message(self.bot))
        )
        try:
            with (
                patch.object(repo, "replace", new=AsyncMock(return_value=row())),
                patch.object(repo, "finish", new=AsyncMock()) as finish,
            ):
                result = await adapter.CardEdits()(
                    AsyncMock(),
                    self.bot,
                    EditMessageText(
                        chat_id=10, message_id=100, text="<b>new</b>", parse_mode="HTML"
                    ),
                )
                self.assertIsInstance(result, Message)
                self.assertEqual(result.message_id, 100)
                self.assertEqual(result.html_text, "<b>new</b>")
                finish.assert_awaited_once()
                self.assertEqual(len(calls), 4)
        finally:
            adapter._editing.reset(token)

    async def test_edit_releases_db_before_every_nested_telegram_call(self):
        from infrastructure import lazy_db
        from bot.middlewares.db import DbReleaseMiddleware

        pool = AsyncMock()
        pool.acquire.return_value = AsyncMock()
        self.bot.session.middleware(DbReleaseMiddleware())
        self.bot.session.middleware(adapter.CardEdits())
        async with lazy_db.lazy_connection(pool, source="widget-card-test") as db:

            async def replace(*args):
                await db.connection.fetchval("SELECT 1")
                return row()

            async def transport(bot, method, **kwargs):
                self.assertFalse(
                    db.holds_connection,
                    "nested widget edits must release the pool slot in its owning task",
                )
                return message(self.bot)

            self.bot.session.make_request.side_effect = transport
            token = adapter._editing.set(adapter._Editing(db, row(), message(self.bot)))
            try:
                with (
                    patch.object(repo, "replace", side_effect=replace),
                    patch.object(repo, "finish", new=AsyncMock()),
                ):
                    await self.bot(
                        EditMessageText(chat_id=10, message_id=100, text="new")
                    )
            finally:
                adapter._editing.reset(token)
        pool.release.assert_awaited_once()

    async def test_financial_caption_is_complete_for_every_client_and_revision(self):
        calls = []

        async def transport(bot, method, **kwargs):
            calls.append(method)
            return message(self.bot)

        self.bot.session.make_request.side_effect = transport
        with (
            patch.object(repo, "create", new=AsyncMock(return_value=row())),
            patch.object(repo, "bind", new=AsyncMock()),
        ):
            await adapter._deliver(
                self.bot, self.db, 10, "pets", row()["source"], "HTML", None
            )
        self.assertEqual(calls[0].caption, row()["source"])
        calls.clear()
        token = adapter._editing.set(
            adapter._Editing(self.db, row(), message(self.bot))
        )
        try:
            with (
                patch.object(repo, "replace", new=AsyncMock(return_value=row())),
                patch.object(repo, "finish", new=AsyncMock()),
            ):
                await adapter.CardEdits()(
                    AsyncMock(),
                    self.bot,
                    EditMessageText(
                        chat_id=10,
                        message_id=100,
                        text="Цена: 50 🪙",
                        parse_mode="HTML",
                    ),
                )
            captions = [
                call for call in calls if call.__api_method__ == "editMessageCaption"
            ]
            self.assertEqual(captions[0].caption, "Цена: 50 🪙")
            self.assertEqual(calls[-1].__api_method__, "editMessageReplyMarkup")
        finally:
            adapter._editing.reset(token)

    async def test_long_financial_confirmation_fails_closed_into_text(self):
        source = "Подтвердить покупку: " + "цена " * 300
        self.assertFalse(rules.caption_fits(source, "HTML"))
        token = adapter._editing.set(
            adapter._Editing(self.db, row(), message(self.bot))
        )
        try:
            with (
                patch.object(repo, "replace", new=AsyncMock(return_value=row())),
                patch.object(repo, "finish", new=AsyncMock()) as finish,
                patch.object(repo, "set_enabled", new=AsyncMock()) as preference,
            ):
                await adapter.CardEdits()(
                    AsyncMock(),
                    self.bot,
                    EditMessageText(
                        chat_id=10, message_id=100, text=source, parse_mode="HTML"
                    ),
                )
                finish.assert_not_called()
                preference.assert_awaited_once_with(self.db, 10, False)
                calls = [
                    call.args[1]
                    for call in self.bot.session.make_request.await_args_list
                ]
                self.assertEqual(
                    calls[0].reply_markup.inline_keyboard[0][0].callback_data,
                    rules.PLAIN_CALLBACK,
                )
                self.assertEqual(calls[1].text, source)
                self.assertIsNone(calls[1].reply_markup)
        finally:
            adapter._editing.reset(token)

    async def test_query_bound_to_bot_owner_token_and_revision(self):
        base = dict(
            id="q",
            **{"from": {"id": 10}},
            chat={"id": 10, "type": "private"},
            message_id=100,
            data="card:p:abcdefghijklmnop:0:2",
        )
        with (
            patch.object(repo, "get", new=AsyncMock(return_value=row())) as get,
            patch.object(service, "available", new=AsyncMock(return_value=True)),
            patch.object(repo, "acknowledge", new=AsyncMock()) as ack,
        ):
            result = json.loads(
                await service.answer(self.db, WidgetQuery.model_validate(base), 123456)
            )
            self.assertEqual(result["k"], "abcdefghijklmnop")
            get.assert_awaited_once_with(self.db, 123456, 10, 100)
            ack.assert_awaited_once_with(self.db, "abcdefghijklmnop", 2)
            for data in (
                "card:p:WRONG:0:2",
                "card:p:abcdefghijklmnop:-1:2",
                "card:p:abcdefghijklmnop:0",
                "card:p:x:0:999999999999999999999",
            ):
                self.assertIn(
                    "e",
                    json.loads(
                        await service.answer(
                            self.db,
                            WidgetQuery.model_validate({**base, "data": data}),
                            123456,
                        )
                    ),
                )


if __name__ == "__main__":
    unittest.main()
