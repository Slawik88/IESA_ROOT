"""Приём запросов HTML-виджетов (Update.widget_query, Bot API 10.4) до маршрутизации aiogram.

aiogram 3.24 этого поля не знает: без перехвата обновление ушло бы в «Detected unknown update type» и осталось бы
без ответа, а виджет через 15 секунд показал бы «бот не ответил». Здесь на **каждый** запрос уходит ответ, даже
когда внутри что-то сломалось: ошибка пишется в журнал и в счётчики «Состояния», но приём остальных
обновлений не останавливает. Что ответить, решает services/widgets.
"""
from __future__ import annotations

import asyncio
import time

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Update
from loguru import logger
from pydantic import ValidationError

from core import widgets as rules
from infrastructure.telegram_widgets import AnswerWidgetQuery, WidgetQuery


def widget_payload(event: Update) -> tuple[str, dict] | None:
    """(тип, сырой запрос), если это обновление от виджета."""
    extra = event.model_extra or {}
    for kind in rules.UPDATE_TYPES:
        raw = extra.get(kind)
        if isinstance(raw, dict):
            return kind, raw
    return None


def _record(exc: BaseException, kind: str) -> None:
    try:
        from services import ops_health
        ops_health.record_bot_error(exc, kind)
    except Exception as monitor_exc:   # счётчик не должен менять судьбу обновления
        logger.warning(f"widget error monitor failed: {type(monitor_exc).__name__}")


async def _reply(bot, query_id: str, text: str, started: float) -> None:
    budget = max(0.5, rules.ANSWER_BUDGET_SEC - (time.monotonic() - started))
    try:
        # Stay in the DB-owning task: wait_for would move the call to a child task,
        # preventing DbReleaseMiddleware from returning this update's connection.
        async with asyncio.timeout(budget):
            await bot(AnswerWidgetQuery(widget_query_id=query_id, data=text))
    except (TimeoutError, TelegramAPIError) as exc:   # опоздали или Telegram отказал: виджет сам покажет ошибку
        logger.warning(f"widget answer not delivered: {type(exc).__name__}: {str(exc)[:160]}")
    except Exception as exc:
        _record(exc, "widget_answer")
        logger.opt(exception=exc).error("widget answer failed")


async def widget_query_middleware(handler, event: Update, data: dict):
    found = widget_payload(event)
    if found is None:
        return await handler(event, data)
    kind, raw = found
    started = time.monotonic()
    bot = data["bot"]
    query_id = raw.get("id")
    if not isinstance(query_id, str) or not query_id:
        logger.warning(f"{kind} without id ignored")
        return None
    if kind != "widget_query":   # пересылки общих виджетов: в проде их нет, а сами мы общих виджетов не шлём
        await _reply(bot, query_id, rules.error("Этот виджет работает только в личке с ботом."), started)
        return None
    state, target = None, None
    try:
        query = WidgetQuery.model_validate(raw)
        from services import widgets
        async with asyncio.timeout(rules.WORK_BUDGET_SEC):
            text, state = await widgets.answer(data["db"], query)
        if query.chat is not None and query.message_id is not None:
            target = (query.chat.id, query.message_id)
    except TimeoutError as exc:
        _record(exc, kind)
        logger.warning("widget handler timed out")
        text = rules.error("Бот сейчас занят. Попробуй ещё раз.")
    except ValidationError:
        logger.warning("widget_query with an unexpected shape")
        text = rules.error("Этот виджет устарел. Попроси новый.")
    except Exception as exc:
        _record(exc, kind)
        logger.opt(exception=exc).error("widget query failed")
        text = rules.error("Что-то пошло не так. Попробуй ещё раз.")
    await _reply(bot, query_id, text, started)
    if state is not None and target is not None:
        try:
            from services import widgets
            async with asyncio.timeout(rules.PERSIST_BUDGET_SEC):
                await widgets.persist(bot, *target, state)
        except Exception as exc:   # ответ виджет уже получил; не записалось только состояние сообщения
            _record(exc, kind)
            logger.warning(f"widget state not saved: {type(exc).__name__}: {str(exc)[:160]}")
    return None
