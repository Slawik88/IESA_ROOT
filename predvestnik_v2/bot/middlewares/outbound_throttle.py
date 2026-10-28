"""bot/middlewares/outbound_throttle.py — глобальный троттлинг исходящих
Telegram-запросов (aiogram request middleware, а не update middleware).

Зачем: без этого при высокой активности в одном чате бот шлёт ответы так же
быстро, как приходят апдейты (каждое сообщение "бот"/варп-команда/"бот я" →
мгновенный message.answer()), упирается в лимит Telegram по чату
(~1 SendMessage/сек) и дальше это превращается в снежный ком: retry_after
растёт от вызова к вызову (30с → 33с → 37с → 40с → 42с в реальном инциденте
2026-07-03), пока не было throttling — каждый следующий ответ тоже
отправлялся немедленно и тоже падал. Итог в проде: десятки апдейтов подряд
"is not handled", пользователи не получают ответ на команды без единой
подсказки почему.

Регистрируется ОДИН раз на Bot.session (не на Dispatcher!) — это единственная
точка, через которую проходят ВСЕ исходящие вызовы Telegram Bot API
(message.answer/reply, bot.send_message, callback.answer и т.д.), поэтому
троттлинг здесь работает для всего бота сразу, без правок в хендлерах.

Слот «1 сообщение в секунду на чат» нужен только методам, которые публикуют или меняют сообщения
(send*/edit*/forward*/copy*). Чтение и модерация (getChatMember, deleteMessage, banChatMember, …)
идут сразу: раньше они стояли в той же очереди, и «Чистка» ждала по секунде на каждую проверку прав.
Очередь чата — честная куча с приоритетом: ожидающий вызов, который отменили, слот не тратит, а
вызовы внутри ``urgent()`` (действия админки) проходят раньше обычных ответов того же чата.
"""
import asyncio
import contextlib
import heapq
import itertools
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from loguru import logger

from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods.base import TelegramType

from core import ops_metrics

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.methods import TelegramMethod

# Telegram: гарантированно безопасно — не больше 1 сообщения/сек в один чат.
# Берём небольшой запас (1.05с), т.к. Telegram считает окно на своей стороне.
_MIN_INTERVAL_PER_CHAT_SEC = 1.05
# Общий кап на все чаты разом (документированный лимит Telegram — 30/сек).
_GLOBAL_MAX_PER_SEC = 25
# Если, несмотря на троттлинг, всё же прилетел TelegramRetryAfter (гонка,
# соседний процесс бота, разница в подсчёте на стороне Telegram) — ждём
# ровно столько, сколько просит Telegram, и повторяем. Без этого одно
# исключение теряет ответ пользователю насовсем.
_MAX_RETRY_ATTEMPTS = 3
# Периодическая чистка очередей давно неактивных чатов — иначе dict
# растёт вечно по числу когда-либо писавших чатов (утечка на долгом аптайме).
_PRUNE_EVERY_SEC = 120.0
_STALE_AFTER_SEC = 600.0

# Методы, которые публикуют или меняют сообщение в чате: только им нужен слот чата.
_CHAT_SLOT_PREFIXES = ("Send", "Edit", "Forward", "Copy")
# «Печатает…» не сообщение: не должен отодвигать настоящий ответ на секунду.
_NO_CHAT_SLOT = frozenset({"SendChatAction"})

URGENT, NORMAL = 0, 1
_priority: ContextVar[int] = ContextVar("outbound_priority", default=NORMAL)


@contextlib.contextmanager
def urgent():
    """Вызовы Telegram внутри блока обгоняют обычные ответы в очереди своего чата."""
    token = _priority.set(URGENT)
    try:
        yield
    finally:
        _priority.reset(token)


def needs_chat_slot(method_name: str) -> bool:
    return method_name.startswith(_CHAT_SLOT_PREFIXES) and method_name not in _NO_CHAT_SLOT


@dataclass
class _ChatLane:
    next_free: float = 0.0
    waiters: list = field(default_factory=list)   # куча (приоритет, порядок, future)
    pump: Optional[asyncio.Task] = None


class OutboundThrottleMiddleware(BaseRequestMiddleware):
    def __init__(self) -> None:
        self._lanes: dict[int, _ChatLane] = {}
        self._order = itertools.count()
        self._global_window_start = time.monotonic()
        self._global_count = 0
        self._last_prune = time.monotonic()

    def _prune(self, now: float) -> None:
        if now - self._last_prune <= _PRUNE_EVERY_SEC:
            return
        cutoff = now - _STALE_AFTER_SEC
        self._lanes = {cid: lane for cid, lane in self._lanes.items()
                       if lane.waiters or lane.next_free > cutoff}
        self._last_prune = now

    async def _chat_slot(self, chat_id: int) -> None:
        """Ждёт своей очереди в чате. Слот берётся в момент выдачи, а не постановки в очередь."""
        now = time.monotonic()
        self._prune(now)
        lane = self._lanes.setdefault(chat_id, _ChatLane())
        if not lane.waiters and now >= lane.next_free:
            lane.next_free = now + _MIN_INTERVAL_PER_CHAT_SEC
            return
        granted = asyncio.get_running_loop().create_future()
        heapq.heappush(lane.waiters, (_priority.get(), next(self._order), granted))
        if lane.pump is None or lane.pump.done():
            lane.pump = asyncio.create_task(self._pump(lane), name=f"predvestnik:throttle:{chat_id}")
        try:
            await granted
        except asyncio.CancelledError:
            if granted.done() and not granted.cancelled():
                lane.next_free = time.monotonic()   # слот выдан, но не использован: вернуть сразу
            raise

    async def _pump(self, lane: _ChatLane) -> None:
        while lane.waiters:
            delay = lane.next_free - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
                continue
            *_, granted = heapq.heappop(lane.waiters)
            if granted.done():          # ожидавший вызов отменили: слот достаётся следующему
                continue
            lane.next_free = time.monotonic() + _MIN_INTERVAL_PER_CHAT_SEC
            granted.set_result(None)

    def _global_wait(self) -> float:
        now = time.monotonic()
        if now - self._global_window_start >= 1.0:
            self._global_window_start = now
            self._global_count = 0
        wait = 1.0 - (now - self._global_window_start) if self._global_count >= _GLOBAL_MAX_PER_SEC else 0.0
        self._global_count += 1
        return wait

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: "Bot",
        method: "TelegramMethod[TelegramType]",
    ):
        chat_id = getattr(method, "chat_id", None)
        name = type(method).__name__

        started = time.perf_counter()
        if chat_id is not None and needs_chat_slot(name):
            await self._chat_slot(chat_id)
        wait = self._global_wait()
        if wait > 0:
            await asyncio.sleep(wait)
        # Measurement only: how long this call waited for its slot, per Bot API method.
        ops_metrics.observe("throttle_wait", name, (time.perf_counter() - started) * 1000)

        attempt = 0
        while True:
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                attempt += 1
                if attempt > _MAX_RETRY_ATTEMPTS:
                    logger.warning(
                        f"[throttle] {name} chat={chat_id}: "
                        f"лимит повторов ({_MAX_RETRY_ATTEMPTS}) исчерпан, сдаюсь"
                    )
                    raise
                delay = e.retry_after + 0.5
                logger.warning(
                    f"[throttle] {name} chat={chat_id}: "
                    f"flood control, жду {delay:.1f}с (попытка {attempt}/{_MAX_RETRY_ATTEMPTS})"
                )
                await asyncio.sleep(delay)
