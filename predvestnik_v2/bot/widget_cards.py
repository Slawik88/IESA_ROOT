"""Opt-in private menu delivery and compatibility with existing native callbacks.

Only callbacks from a registered card enter the edit adapter. No callback is invented
from widget input; widget queries can only read another page of the saved view.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from weakref import WeakValueDictionary

from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageReplyMarkup, EditMessageText
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    ReplyParameters,
)
from core import widget_cards as rules
from core import widgets
from infrastructure.repositories import widget_cards as repo
from infrastructure.telegram_widgets import EditMessageWidgetData, SendWidget, widget_of
from loguru import logger
from services import widget_cards as service


@dataclass
class _Editing:
    db: object
    row: dict
    message: Message


_editing: ContextVar[_Editing | None] = ContextVar("widget_card_editing", default=None)


def _markup(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    rows = [list(row) for row in markup.inline_keyboard] if markup else []
    if not any(
        button.callback_data == rules.PLAIN_CALLBACK for row in rows for button in row
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text="Текстовый режим", callback_data=rules.PLAIN_CALLBACK
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _message(message: Message, source: str, parse_mode: str | None) -> Message:
    view = rules.text_view(source, parse_mode)
    return message.model_copy(
        update={
            "text": view.text,
            "entities": [
                MessageEntity.model_validate(entity) for entity in view.entities
            ],
            "caption": None,
            "caption_entities": None,
        }
    ).as_(message.bot)


async def reply(
    message: Message, db, feature: str, text: str, *, as_reply: bool = True, **kwargs
):
    """Explicit player menu only. Groups, Business deliveries and input prompts keep text."""
    mode = kwargs.get("parse_mode", "HTML")
    markup = kwargs.get("reply_markup")
    supported = {
        "parse_mode",
        "reply_markup",
        "disable_web_page_preview",
        "disable_notification",
    }
    own_dm = (
        message.chat.type == "private"
        and message.from_user is not None
        and message.chat.id == message.from_user.id
        and not message.business_connection_id
    )
    if (
        feature not in rules.FEATURES
        or not own_dm
        or mode not in ("HTML", None)
        or (markup is not None and not isinstance(markup, InlineKeyboardMarkup))
        or set(kwargs) - supported
        or len(text.encode("utf-8")) > rules.MAX_SOURCE_BYTES
        or (feature in rules.CAPTION_FEATURES and not rules.caption_fits(text, mode))
        or not await service.enabled(db, message.chat.id)
    ):
        send = message.reply if as_reply else message.answer
        return await send(text, **kwargs)
    return await _deliver(
        message.bot,
        db,
        message.chat.id,
        feature,
        text,
        mode,
        markup,
        ReplyParameters(message_id=message.message_id) if as_reply else None,
        kwargs.get("disable_notification"),
    )


async def send(bot, db, owner_id: int, feature: str, text: str, *, reply_markup=None):
    """Explicit owner DM (for the Business remote), never a Business peer delivery."""
    if not await service.enabled(db, owner_id) or (
        feature in rules.CAPTION_FEATURES and not rules.caption_fits(text, "HTML")
    ):
        return await bot.send_message(
            owner_id,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    return await _deliver(bot, db, owner_id, feature, text, "HTML", reply_markup)


async def _deliver(
    bot,
    db,
    owner_id,
    feature,
    text,
    mode,
    markup,
    reply_parameters=None,
    disable_notification=None,
):
    row = await repo.create(db, bot.id, owner_id, feature, text, mode)
    try:
        result = await bot(
            SendWidget(
                chat_id=owner_id,
                html=widgets.html("card"),
                chat_data=widgets.encode(rules.snapshot(row)),
                allow_queries=True,
                caption=text
                if feature in rules.CAPTION_FEATURES
                else "Меню Предвестника · Если карточка не видна, нажми «Текстовый режим».",
                parse_mode=mode if feature in rules.CAPTION_FEATURES else None,
                reply_markup=_markup(markup),
                disable_notification=disable_notification,
                reply_parameters=reply_parameters,
            )
        )
    except TelegramBadRequest as error:
        # Old/self-hosted Bot API servers can reject the new media method.
        logger.warning("player widget rejected, using text: {}", str(error)[:160])
        await repo.discard(db, row["token"])
        return await bot.send_message(
            owner_id,
            text,
            parse_mode=mode,
            reply_markup=markup,
            reply_parameters=reply_parameters,
            disable_notification=disable_notification,
            disable_web_page_preview=True,
        )
    await repo.bind(db, row["token"], result.message_id)
    return _message(result, text, mode)


async def _callback(handler, event, data):
    call = event.callback_query
    message = call.message if call else None
    if not isinstance(message, Message) or not widget_of(message):
        return await handler(event, data)
    db, bot = data["db"], data["bot"]
    row = await repo.get(db, bot.id, message.chat.id, message.message_id)
    if (
        not row
        or message.chat.type != "private"
        or call.from_user.id != message.chat.id
        or row["owner_id"] != call.from_user.id
        or not await service.available(db, call.from_user.id)
    ):
        await call.answer(
            "Это меню больше недоступно. Открой его заново командой.", show_alert=True
        )
        return None
    if call.data == rules.PLAIN_CALLBACK:
        await repo.set_enabled(db, call.from_user.id, False)
        # Keep signed native callbacks on their original message_id. The copy is read-only.
        await message.answer(
            row["source"], parse_mode=row["parse_mode"], disable_web_page_preview=True
        )
        await repo.acknowledge(db, row["token"], row["revision"])
        await call.answer(
            "Текстовый режим включён. Новые меню будут текстом.", show_alert=True
        )
        return None
    if not row["ready"] or row["seen_revision"] != row["revision"]:
        await call.answer(
            "Сначала дождись карточки или нажми «Текстовый режим». Если меню не обновилось, открой его заново.",
            show_alert=True,
        )
        return None
    hydrated = _message(message, row["source"], row["parse_mode"])
    token = _editing.set(_Editing(db, row, hydrated))
    try:
        return await handler(
            event.model_copy(
                update={"callback_query": call.model_copy(update={"message": hydrated})}
            ),
            data,
        )
    finally:
        _editing.reset(token)


class CardCallbacks:
    """One in-flight handler per menu; idle locks have no retained per-user memory."""

    def __init__(self):
        self._locks: WeakValueDictionary[tuple, asyncio.Lock] = WeakValueDictionary()

    async def __call__(self, handler, event, data):
        call = event.callback_query
        message = call.message if call else None
        if not isinstance(message, Message) or not widget_of(message):
            return await handler(event, data)
        key = (data["bot"].id, message.chat.id, message.message_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        from infrastructure.lazy_db import release_current

        await release_current()
        async with lock:
            return await _callback(handler, event, data)


async def _edit(bot, method):
    try:
        return await bot(method)
    except TelegramBadRequest as error:
        if "not modified" not in str(error).lower():
            raise
        return None


class CardEdits(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        current = _editing.get()
        if (
            not current
            or not isinstance(method, EditMessageText)
            or method.chat_id != current.row["chat_id"]
            or method.message_id != current.row["message_id"]
            or bot.id != current.row["bot_id"]
        ):
            return await make_request(bot, method)
        mode = "HTML" if isinstance(method.parse_mode, Default) else method.parse_mode
        if mode not in (None, "HTML") or method.entities:
            raise ValueError("widget card edit requires HTML or plain text")
        row = await repo.replace(current.db, current.row["token"], method.text, mode)
        if row is None:
            raise ValueError("widget card expired during callback")
        # Telegram has no atomic state+keyboard edit. Hide old actions first, so an
        # interrupted edit never leaves a new purchase description over old buttons.
        await _edit(
            bot,
            EditMessageReplyMarkup(
                chat_id=method.chat_id,
                message_id=method.message_id,
                reply_markup=_markup(None),
            ),
        )
        if row["feature"] in rules.CAPTION_FEATURES:
            if not rules.caption_fits(method.text, mode):
                # Never attach opaque purchase actions to an unsupported-media caption.
                # Reopening in text re-renders its own signed buttons normally.
                await repo.set_enabled(current.db, row["owner_id"], False)
                await bot.send_message(
                    row["chat_id"],
                    method.text,
                    parse_mode=mode,
                    disable_web_page_preview=True,
                )
                await bot.send_message(
                    row["chat_id"],
                    "Это меню показано текстом. Открой его заново командой: новые меню будут текстом.",
                )
                return _message(current.message, method.text, mode)
            await _edit(
                bot,
                EditMessageCaption(
                    chat_id=method.chat_id,
                    message_id=method.message_id,
                    caption=method.text,
                    parse_mode=mode,
                ),
            )
        await _edit(
            bot,
            EditMessageWidgetData(
                chat_id=method.chat_id,
                message_id=method.message_id,
                chat_data=widgets.encode(rules.snapshot(row)),
            ),
        )
        result = await _edit(
            bot,
            EditMessageReplyMarkup(
                chat_id=method.chat_id,
                message_id=method.message_id,
                reply_markup=_markup(method.reply_markup),
            ),
        )
        await repo.finish(current.db, row["token"], row["revision"])
        current.row = row
        current.message = _message(
            result if isinstance(result, Message) else current.message,
            method.text,
            mode,
        )
        return current.message
