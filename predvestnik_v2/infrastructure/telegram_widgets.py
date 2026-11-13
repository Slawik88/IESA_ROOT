"""Методы и типы Bot API 10.4 для HTML-виджетов поверх aiogram 3.24 (он знает Bot API 9.3).

Классы названы ровно как методы API: имитация Telegram ищет `_m_<ИмяКласса>`, а ограничитель отправки даёт
слот чата методам на Send/Edit (editMessageWidgetData Telegram считает отправленным сообщением).
Запрос виджета приходит в Update лишним полем (`update.model_extra["widget_query"]`), его разбирает WidgetQuery.

Пустая строка в состоянии aiogram не отправляет вовсе (пустые поля формы пропускаются), поэтому «очистить
состояние» этими методами нельзя: вместо очистки пишем новое состояние.
"""
from __future__ import annotations

from aiogram.methods.base import TelegramMethod
from aiogram.types import InlineKeyboardMarkup, Message
from pydantic import BaseModel, ConfigDict, Field


class SendWidget(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendWidget"

    chat_id: int
    html: str
    width: int | None = None
    height: int | None = None
    chat_data: str | None = None
    public_data: str | None = None
    caption: str | None = None
    parse_mode: str | None = None
    show_caption_above_media: bool | None = None
    allow_queries: bool | None = None
    is_shared: bool | None = None
    disable_notification: bool | None = None
    message_thread_id: int | None = None
    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageWidgetData(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "editMessageWidgetData"

    chat_id: int
    message_id: int
    chat_data: str | None = None
    public_data: str | None = None


class AnswerWidgetQuery(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "answerWidgetQuery"

    widget_query_id: str
    data: str | None = None


class _Peer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    type: str = ""
    first_name: str = ""


class _QueryType(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str = "data"


class WidgetQuery(BaseModel):
    """Запрос виджета (Update.widget_query). `from` подделать нельзя; `data` — недоверенный ввод."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    sender: _Peer = Field(alias="from")
    chat: _Peer | None = None
    message_id: int | None = None
    inline_message_id: str | None = None
    widget_id: str | None = None
    type: _QueryType = Field(default_factory=_QueryType)
    data: str = ""

    @property
    def in_own_dm(self) -> bool:
        """Виджет в личке этого же игрока с ботом (в проде других мест у виджетов пока нет)."""
        return (self.chat is not None and self.chat.type == "private" and self.chat.id == self.sender.id
                and self.message_id is not None and self.inline_message_id is None)


def widget_of(message: Message) -> dict | None:
    """Поле `widget` отправленного сообщения (aiogram его не знает и кладёт в model_extra)."""
    extra = message.model_extra or {}
    found = extra.get("widget")
    return found if isinstance(found, dict) else None
