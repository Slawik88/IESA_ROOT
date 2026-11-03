"""Small helpers shared by the whole-bot scenarios (scn_bot_*.py)."""
from __future__ import annotations

import os

os.environ.setdefault("MINIAPP_URL", "https://miniapp.example/predvestnik/")   # read when the bot modules are imported
os.environ.setdefault("MINIAPP_SHORT_NAME", "app")
os.environ.setdefault("BOT_USERNAME", "predvestnik_test_bot")   # links into the DM (t.me/<bot>?start=...)

from tools.mafia_sim.harness import Harness, SimUser  # noqa: E402
from tools.mafia_sim.registry import ok  # noqa: E402
from tools.mafia_sim.world import StoredMessage, parse_html  # noqa: E402

OUTGOING = {"SendMessage", "SendPhoto", "SendAnimation", "SendDocument", "EditMessageText", "EditMessageCaption"}


def plain(params: dict) -> str:
    text = params.get("text") or params.get("caption") or ""
    return parse_html(text)[0] if params.get("parse_mode") == "HTML" else text


async def say(h: Harness, user: SimUser, chat: int, text: str, **kw) -> list[tuple[str, dict]]:
    """The player writes ``text``; returns the (method, params) of everything the bot sent in reply."""
    start = len(h.world.calls)
    await h.say(user, chat, text, **kw)
    return [(n, p) for n, p in h.world.calls[start:] if n in OUTGOING]


def said(sent: list[tuple[str, dict]]) -> str:
    return "\n".join(plain(p) for _, p in sent)


def last_message(h: Harness, chat: int, contains: str = "") -> StoredMessage:
    message = h.world.last(chat, contains)
    ok(message is not None, f"expected a message containing {contains!r} in chat; got {[m.text[:40] for m in h.world.live(chat)][-3:]}")
    return message


def button(message: StoredMessage, label: str = "", data_prefix: str = "") -> dict:
    found = [b for b in message.buttons() if label in b.get("text", "") and (b.get("callback_data") or "").startswith(data_prefix)]
    ok(found, f"no button {label!r}/{data_prefix!r}; buttons: {[b.get('text') for b in message.buttons()]}")
    return found[0]


def sim_friends(h: Harness, count: int, *, chat_members: bool = True) -> tuple[list[SimUser], int]:
    """``count`` players in one new group chat."""
    users = [h.user(f"Игрок{i + 1}") for i in range(count)]
    return users, h.new_chat(users)


class TemporaryHandlers:
    """``with TemporaryHandlers(h.dp):`` handlers registered inside are removed again (the harness is shared by all scenarios)."""

    def __init__(self, dispatcher) -> None:
        self.observers = list(dispatcher.observers.values())

    def __enter__(self) -> "TemporaryHandlers":
        self.saved = [(o, list(o.handlers)) for o in self.observers]
        return self

    def __exit__(self, *exc) -> None:
        for observer, handlers in self.saved:
            observer.handlers[:] = handlers
