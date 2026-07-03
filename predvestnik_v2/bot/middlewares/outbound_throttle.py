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
"""
import asyncio
import time
from typing import TYPE_CHECKING, Optional

from loguru import logger

from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods.base import TelegramType

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
# Периодическая чистка _next_allowed от давно неактивных чатов — иначе dict
# растёт вечно по числу когда-либо писавших чатов (утечка на долгом аптайме).
_PRUNE_EVERY_SEC = 120.0
_STALE_AFTER_SEC = 600.0


class OutboundThrottleMiddleware(BaseRequestMiddleware):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next_allowed: dict[int, float] = {}
        self._global_window_start = time.monotonic()
        self._global_count = 0
        self._last_prune = time.monotonic()

    async def _reserve_slot(self, chat_id: Optional[int]) -> float:
        """Резервирует ближайший разрешённый момент отправки (per-chat +
        глобальный кап) под одним lock'ом — без гонок за 'кто первый читает
        время последней отправки'. Возвращает, сколько секунд нужно подождать
        (сам sleep — вне lock'а, чтобы не сериализовать отправку в РАЗНЫЕ чаты)."""
        async with self._lock:
            now = time.monotonic()

            if now - self._last_prune > _PRUNE_EVERY_SEC:
                cutoff = now - _STALE_AFTER_SEC
                self._next_allowed = {
                    cid: t for cid, t in self._next_allowed.items() if t > cutoff
                }
                self._last_prune = now

            if now - self._global_window_start >= 1.0:
                self._global_window_start = now
                self._global_count = 0
            wait_global = (
                1.0 - (now - self._global_window_start)
                if self._global_count >= _GLOBAL_MAX_PER_SEC else 0.0
            )

            wait_chat = 0.0
            if chat_id is not None:
                wait_chat = max(0.0, self._next_allowed.get(chat_id, 0.0) - now)

            wait = max(wait_global, wait_chat)

            if chat_id is not None:
                self._next_allowed[chat_id] = now + wait + _MIN_INTERVAL_PER_CHAT_SEC
            self._global_count += 1

            return wait

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: "Bot",
        method: "TelegramMethod[TelegramType]",
    ):
        chat_id = getattr(method, "chat_id", None)

        wait = await self._reserve_slot(chat_id)
        if wait > 0:
            await asyncio.sleep(wait)

        attempt = 0
        while True:
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                attempt += 1
                if attempt > _MAX_RETRY_ATTEMPTS:
                    logger.warning(
                        f"[throttle] {type(method).__name__} chat={chat_id}: "
                        f"лимит повторов ({_MAX_RETRY_ATTEMPTS}) исчерпан, сдаюсь"
                    )
                    raise
                delay = e.retry_after + 0.5
                logger.warning(
                    f"[throttle] {type(method).__name__} chat={chat_id}: "
                    f"flood control, жду {delay:.1f}с (попытка {attempt}/{_MAX_RETRY_ATTEMPTS})"
                )
                await asyncio.sleep(delay)