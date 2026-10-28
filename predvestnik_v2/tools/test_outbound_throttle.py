#!/usr/bin/env python3
"""Outbound Telegram throttler (roadmap S03), without a database or network.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_outbound_throttle.py

1. Read and moderation calls (getChatMember, deleteMessage, banChatMember, sendChatAction) take no chat slot.
2. sendMessage/edit*/forward*/copy* still keep 1 message per second per chat; other chats are independent.
3. A waiting call that is cancelled frees its place: the next call goes on the first free slot.
4. Calls inside ``urgent()`` (admin actions) overtake ordinary replies waiting in the same chat.
5. A flood-control answer (retry_after) is still waited out and retried.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import (BanChatMember, CopyMessage, DeleteMessage, EditMessageText, ForwardMessage,
                             GetChatMember, SendChatAction, SendMessage)

from bot.middlewares import outbound_throttle
from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware

CHAT, OTHER = -100, -200
SLOT = outbound_throttle._MIN_INTERVAL_PER_CHAT_SEC


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, float]] = []
        self.origin = time.monotonic()

    async def __call__(self, bot, method):
        label = getattr(method, "text", None) or type(method).__name__
        self.sent.append((label, time.monotonic() - self.origin))
        return True

    def at(self, label: str) -> float:
        return next(t for name, t in self.sent if name == label)


async def read_calls_take_no_slot() -> None:
    throttle, rec = OutboundThrottleMiddleware(), Recorder()
    await throttle(rec, None, SendMessage(chat_id=CHAT, text="first"))
    calls = [GetChatMember(chat_id=CHAT, user_id=n) for n in range(10)]
    calls += [DeleteMessage(chat_id=CHAT, message_id=1), BanChatMember(chat_id=CHAT, user_id=5),
              SendChatAction(chat_id=CHAT, action="typing")]
    await asyncio.gather(*(throttle(rec, None, c) for c in calls))
    assert max(t for _, t in rec.sent) < 0.2, rec.sent
    print("  read/moderation calls and «typing…» go at once next to a fresh message")


async def messages_keep_one_per_second() -> None:
    throttle, rec = OutboundThrottleMiddleware(), Recorder()
    methods = [SendMessage(chat_id=CHAT, text="a"), EditMessageText(chat_id=CHAT, message_id=1, text="b"),
               ForwardMessage(chat_id=CHAT, from_chat_id=OTHER, message_id=1),
               CopyMessage(chat_id=CHAT, from_chat_id=OTHER, message_id=2), SendMessage(chat_id=OTHER, text="z")]
    await asyncio.gather(*(throttle(rec, None, m) for m in methods))
    in_chat = sorted(t for name, t in rec.sent if name != "z")
    gaps = [b - a for a, b in zip(in_chat, in_chat[1:])]
    assert len(in_chat) == 4 and min(gaps) >= SLOT - 0.02, gaps
    assert rec.at("z") < 0.2, "another chat waited for this chat's queue"
    print(f"  send/edit/forward/copy in one chat: gaps {[round(g, 2) for g in gaps]} s; other chat at once")


async def cancelled_waiter_frees_its_place() -> None:
    throttle, rec = OutboundThrottleMiddleware(), Recorder()
    await throttle(rec, None, SendMessage(chat_id=CHAT, text="first"))
    doomed = [asyncio.create_task(throttle(rec, None, SendMessage(chat_id=CHAT, text=f"x{n}"))) for n in range(3)]
    await asyncio.sleep(0.1)
    for task in doomed:
        task.cancel()
    await asyncio.gather(*doomed, return_exceptions=True)
    await throttle(rec, None, SendMessage(chat_id=CHAT, text="next"))
    assert [n for n, _ in rec.sent] == ["first", "next"], rec.sent
    assert rec.at("next") < SLOT + 0.15, f"cancelled calls still held slots: next went at {rec.at('next'):.2f} s"
    print(f"  three cancelled waiters cost nothing: next message at {rec.at('next'):.2f} s")


async def urgent_overtakes_ordinary() -> None:
    throttle, rec = OutboundThrottleMiddleware(), Recorder()
    await throttle(rec, None, SendMessage(chat_id=CHAT, text="first"))
    ordinary = [asyncio.create_task(throttle(rec, None, SendMessage(chat_id=CHAT, text=f"reply{n}"))) for n in range(2)]
    await asyncio.sleep(0.05)

    async def admin():
        with outbound_throttle.urgent():
            await throttle(rec, None, SendMessage(chat_id=CHAT, text="admin"))
    await asyncio.gather(admin(), *ordinary)
    order = [n for n, _ in rec.sent]
    assert order == ["first", "admin", "reply0", "reply1"], order
    assert outbound_throttle._priority.get() == outbound_throttle.NORMAL
    print(f"  admin message overtakes queued replies: {order}")


async def flood_control_is_retried() -> None:
    throttle, attempts = OutboundThrottleMiddleware(), []

    async def flaky(bot, method):
        attempts.append(time.monotonic())
        if len(attempts) == 1:
            raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=0)
        return True
    assert await throttle(flaky, None, SendMessage(chat_id=CHAT, text="x")) is True
    assert len(attempts) == 2 and attempts[1] - attempts[0] >= 0.45
    print("  retry_after is waited out and the call repeated")


async def main() -> None:
    for test in (read_calls_take_no_slot, messages_keep_one_per_second, cancelled_waiter_frees_its_place,
                 urgent_overtakes_ordinary, flood_control_is_retried):
        await test()
    print("OK: outbound throttler — chat slot only for messages, cancellation, priority, flood retry")


if __name__ == "__main__":
    asyncio.run(main())
