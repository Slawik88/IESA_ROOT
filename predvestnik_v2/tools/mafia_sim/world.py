"""In-memory Telegram: a real ``aiogram.Bot`` whose HTTP session is replaced.

The session answers every Bot API method the way Telegram would, including the
rejections that bite real bots (blocked DMs, 200-char callback alerts, 64-byte
callback data, malformed HTML, editing a deleted message).  Anything the game
sends is therefore validated against Telegram's limits without a real group.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, AsyncGenerator, Callable

from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError

BOT_ID = 123456
BOT_USERNAME = "predvestnik_test_bot"
NETWORK_FAULT = 599  # TgError code that surfaces as aiogram's TelegramNetworkError
_ENTITY_TYPES = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline", "ins": "underline",
                 "s": "strikethrough", "strike": "strikethrough", "del": "strikethrough", "code": "code", "pre": "pre",
                 "a": "text_link", "tg-spoiler": "spoiler", "blockquote": "blockquote"}


class _HtmlParse(HTMLParser):
    """Telegram's view of an HTML message: visible text plus entities in UTF-16 units."""

    def __init__(self) -> None:
        super().__init__()
        self.plain: list[str] = []
        self.length = 0
        self.stack: list[tuple[str, int, dict]] = []
        self.entities: list[dict] = []
        self.error: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag not in _ENTITY_TYPES:
            self.error = f"unsupported tag <{tag}>"
        self.stack.append((tag, self.length, dict(attrs)))

    def handle_data(self, data):
        self.plain.append(data)
        self.length += len(data.encode("utf-16-le")) // 2

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            self.error = f"unbalanced </{tag}>"
            return
        _, start, attrs = self.stack.pop()
        entity = {"type": _ENTITY_TYPES[tag], "offset": start, "length": self.length - start}
        if tag == "a":
            entity["url"] = attrs.get("href", "")
        self.entities.append(entity)


def parse_html(source: str) -> tuple[str, list[dict], str | None]:
    """(visible text, entities, problem) exactly as Telegram would split an HTML message."""
    parser = _HtmlParse()
    parser.feed(source)
    parser.close()
    problem = parser.error or (f"unclosed <{parser.stack[-1][0]}>" if parser.stack else None)
    return "".join(parser.plain).rstrip(), sorted(parser.entities, key=lambda e: (e["offset"], -e["length"])), problem


def html_problem(source: str) -> str | None:
    """Why Telegram would reject this HTML, or None when it is valid."""
    return parse_html(source)[2]


class TgError(Exception):
    def __init__(self, code: int, description: str, retry_after: int | None = None) -> None:
        super().__init__(description)
        self.code, self.description, self.retry_after = code, description, retry_after


@dataclass
class StoredMessage:
    chat_id: int
    message_id: int
    text: str
    markup: dict | None
    parse_mode: str | None = None
    deleted: bool = False
    edits: int = 0
    topic_id: int | None = None
    html: str = ""
    entities: list = field(default_factory=list)

    def buttons(self) -> list[dict]:
        rows = (self.markup or {}).get("inline_keyboard", [])
        return [button for row in rows for button in row]


@dataclass
class World:
    """All state of the fake Telegram universe plus an audit log of API calls."""

    messages: dict[tuple[int, int], StoredMessage] = field(default_factory=dict)
    calls: list[tuple[str, dict]] = field(default_factory=list)
    statuses: dict[tuple[int, int], dict] = field(default_factory=dict)
    dm_open: set[int] = field(default_factory=set)
    failures: list[tuple[Callable[[str, dict], bool], TgError, list[int]]] = field(default_factory=list)
    next_id: int = 1000
    answers: list[dict] = field(default_factory=list)
    chaos: Callable[[str, dict], "TgError | None"] | None = None  # random fault injection (stress scenarios)

    # ── configuration helpers ───────────────────────────────────────────────
    def set_member(self, chat_id: int, user_id: int, status: str = "member", **flags: Any) -> None:
        self.statuses[(chat_id, user_id)] = {"status": status, **flags}

    def fail(self, when: Callable[[str, dict], bool], error: TgError, times: int = 1) -> None:
        self.failures.append((when, error, [times]))

    # ── query helpers for assertions ────────────────────────────────────────
    def live(self, chat_id: int) -> list[StoredMessage]:
        return [m for (c, _), m in sorted(self.messages.items()) if c == chat_id and not m.deleted]

    def last(self, chat_id: int, contains: str = "") -> StoredMessage | None:
        found = [m for m in self.live(chat_id) if contains in m.text]
        return found[-1] if found else None

    def api(self, method: str) -> list[dict]:
        return [params for name, params in self.calls if name == method]

    # ── request dispatch ────────────────────────────────────────────────────
    def handle(self, name: str, params: dict) -> Any:
        self.calls.append((name, params))
        for when, error, left in list(self.failures):
            if left[0] > 0 and when(name, params):
                left[0] -= 1
                raise error
        if self.chaos is not None:
            fault = self.chaos(name, params)
            if fault is not None:
                raise fault
        handler = getattr(self, f"_m_{name}", None)
        return handler(params) if handler else True

    def _user(self, user_id: int) -> dict:
        return {"id": user_id, "is_bot": user_id == BOT_ID, "first_name": f"U{user_id}"}

    def _chat(self, chat_id: int) -> dict:
        return {"id": chat_id, "type": "private" if chat_id > 0 else "supergroup", "title": None if chat_id > 0 else "Sim"}

    def _require_dm(self, chat_id: int) -> None:
        if chat_id > 0 and chat_id not in self.dm_open:
            raise TgError(403, "Forbidden: bot can't initiate conversation with a user")

    def _visible(self, text: str | None, parse_mode: str | None) -> tuple[str, list[dict]]:
        """Validate like Telegram does and return (visible text, entities)."""
        if not text:
            raise TgError(400, "Bad Request: message text is empty")
        plain, entities = (text, [])
        if parse_mode == "HTML":
            plain, entities, problem = parse_html(text)
            if problem:
                raise TgError(400, f"Bad Request: can't parse entities: {problem}")
        if not plain.strip():
            raise TgError(400, "Bad Request: message text is empty")
        if len(plain) > 4096:
            raise TgError(400, "Bad Request: message is too long")
        return plain, entities

    def _check_markup(self, markup: dict | None) -> None:
        if not markup:
            return
        rows = markup.get("inline_keyboard", [])
        if sum(len(row) for row in rows) > 100:
            raise TgError(400, "Bad Request: too many buttons")
        for row in rows:
            if len(row) > 8:
                raise TgError(400, "Bad Request: too many buttons in a row")
            for button in row:
                if not button.get("text"):
                    raise TgError(400, "Bad Request: button text is empty")
                data = button.get("callback_data")
                if data is not None and not 1 <= len(data.encode()) <= 64:
                    raise TgError(400, "Bad Request: BUTTON_DATA_INVALID")

    def _message_json(self, stored: StoredMessage) -> dict:
        data = {"message_id": stored.message_id, "date": int(time.time()), "chat": self._chat(stored.chat_id),
                "from": self._user(BOT_ID), "text": stored.text}
        if stored.markup:
            data["reply_markup"] = stored.markup
        if stored.entities:
            data["entities"] = stored.entities
        if stored.topic_id:
            data.update(message_thread_id=stored.topic_id, is_topic_message=True)
        return data

    def _dump_markup(self, markup: Any) -> dict | None:
        return markup.model_dump(exclude_none=True, mode="json") if markup is not None else None

    # ── Bot API methods ─────────────────────────────────────────────────────
    def _m_GetMe(self, params: dict) -> dict:
        return {"id": BOT_ID, "is_bot": True, "first_name": "Sim", "username": BOT_USERNAME}

    def _m_SendMessage(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        self._require_dm(chat_id)
        plain, entities = self._visible(params.get("text"), params.get("parse_mode"))
        markup = self._dump_markup(params.get("reply_markup"))
        self._check_markup(markup)
        self.next_id += 1
        stored = StoredMessage(chat_id, self.next_id, plain, markup, params.get("parse_mode"),
                               topic_id=params.get("message_thread_id"), html=params["text"], entities=entities)
        self.messages[(chat_id, stored.message_id)] = stored
        return self._message_json(stored)

    def _m_EditMessageText(self, params: dict) -> dict:
        key = (int(params["chat_id"]), int(params["message_id"]))
        stored = self.messages.get(key)
        if stored is None or stored.deleted:
            raise TgError(400, "Bad Request: message to edit not found")
        plain, entities = self._visible(params.get("text"), params.get("parse_mode"))
        markup = self._dump_markup(params.get("reply_markup"))
        self._check_markup(markup)
        if stored.html == params["text"] and stored.markup == markup:
            raise TgError(400, "Bad Request: message is not modified: specified new message content and reply markup are exactly the same")
        stored.text, stored.html, stored.entities = plain, params["text"], entities
        stored.markup, stored.edits = markup, stored.edits + 1
        return self._message_json(stored)

    def _m_EditMessageReplyMarkup(self, params: dict) -> dict:
        stored = self.messages.get((int(params["chat_id"]), int(params["message_id"])))
        if stored is None or stored.deleted:
            raise TgError(400, "Bad Request: message to edit not found")
        markup = self._dump_markup(params.get("reply_markup"))
        self._check_markup(markup)
        if stored.markup == markup:
            raise TgError(400, "Bad Request: message is not modified: specified new message content and reply markup are exactly the same")
        stored.markup, stored.edits = markup, stored.edits + 1
        return self._message_json(stored)

    def _m_DeleteMessage(self, params: dict) -> bool:
        stored = self.messages.get((int(params["chat_id"]), int(params["message_id"])))
        if stored is None or stored.deleted:
            raise TgError(400, "Bad Request: message to delete not found")
        stored.deleted = True
        return True

    def _m_SendChatAction(self, params: dict) -> bool:
        self._require_dm(int(params["chat_id"]))
        return True

    def _m_AnswerCallbackQuery(self, params: dict) -> bool:
        text = params.get("text") or ""
        if len(text) > 200:
            raise TgError(400, "Bad Request: MESSAGE_TOO_LONG (callback answer is limited to 200 characters)")
        self.answers.append({"text": text, "alert": bool(params.get("show_alert")), "url": params.get("url")})
        return True

    def _m_GetChatMember(self, params: dict) -> dict:
        status = self.statuses.get((int(params["chat_id"]), int(params["user_id"])))
        if status is None:
            return {"status": "left", "user": self._user(int(params["user_id"]))}
        user, kind = self._user(int(params["user_id"])), status["status"]
        if kind in {"administrator", "creator"}:
            full = {key: False for key in (
                "can_be_edited", "is_anonymous", "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
                "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users", "can_post_stories",
                "can_edit_stories", "can_delete_stories")}
            full.update({k: v for k, v in status.items() if k != "status"})
            return {"status": kind, "user": user, **({"is_anonymous": False} if kind == "creator" else full)}
        if kind == "restricted":
            perms = {k: False for k in (
                "can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos",
                "can_send_video_notes", "can_send_voice_notes", "can_send_polls", "can_send_other_messages",
                "can_add_web_page_previews", "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics")}
            perms.update({k: v for k, v in status.items() if k != "status"})
            return {"status": "restricted", "user": user, "is_member": True, "until_date": 0, **perms}
        return {"status": kind, "user": user}


class FakeSession(BaseSession):
    """Routes every aiogram method through :class:`World` and real response parsing."""

    def __init__(self, world: World) -> None:
        super().__init__()
        self.world = world

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    async def stream_content(self, *args, **kwargs) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        params = {key: getattr(method, key) for key in type(method).model_fields if getattr(method, key, None) is not None}
        try:
            result = self.world.handle(name, params)
            status, body = 200, {"ok": True, "result": result}
        except TgError as error:
            if error.code == NETWORK_FAULT:
                raise TelegramNetworkError(method=method, message="simulated network failure") from error
            status = error.code
            body = {"ok": False, "error_code": error.code, "description": error.description}
            if error.retry_after:
                body["parameters"] = {"retry_after": error.retry_after}
        response = self.check_response(bot=bot, method=method, status_code=status, content=json.dumps(body))
        return response.result
