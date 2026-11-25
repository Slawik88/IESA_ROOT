"""The one Dispatcher setup shared by production (bot/__main__.py) and the Telegram simulator (tools/mafia_sim).

Both must see the same middlewares and the same error monitor, otherwise a simulated
handler failure would never reach the health counters.
"""
from datetime import datetime, timezone

from aiogram import Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import ErrorEvent, Update
from loguru import logger

from bot.handlers import main_router
from core import ops_metrics
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.db import DbReleaseMiddleware, db_middleware
from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware
from bot.middlewares.polling_delivery import PollingDelivery
from bot.middlewares.preprod_gate_mw import preprod_gate_middleware
from bot.middlewares.widget_query import widget_payload, widget_query_middleware
from core import widgets
from services import ops_health


def update_kind(update: Update) -> str:
    """Тип обновления для счётчиков; запрос виджета aiogram 3.24 не знает, и event_type на нём бросает исключение."""
    found = widget_payload(update)
    if found is not None:
        return found[0]
    try:
        return update.event_type
    except LookupError:
        return "unknown"


def allowed_updates(dp: Dispatcher) -> list[str]:
    """Что просить у Telegram: всё, на что есть обработчики, плюс запросы виджетов (у них нет обработчиков aiogram)."""
    return sorted({*dp.resolve_used_update_types(), *widgets.UPDATE_TYPES})


async def note_handler_error(event: ErrorEvent):
    """Count the failure per handler (health panel, owner alert), then let aiogram handle it as before."""
    try:
        ops_health.record_bot_error(event.exception, update_kind(event.update))
    except Exception as exc:   # monitoring must never change what happens to the update
        logger.warning(f"bot error monitor failed: {type(exc).__name__}: {exc}")
    return UNHANDLED   # the original exception is re-raised and logged by aiogram unchanged


async def measure_update_delivery(handler, event: Update, data):
    # Callback and edit payloads can refer to arbitrarily old messages.
    if event.message is not None:
        age_ms = (datetime.now(timezone.utc) - event.message.date).total_seconds() * 1000
        ops_metrics.observe("telegram_delivery", event.message.chat.type, max(0, age_ms))
        if age_ms >= ops_health.TELEGRAM_DELIVERY_SLOW_MS:
            ops_metrics.count("telegram_delayed", "message")
    return await handler(event, data)


def build_dispatcher(delivery: PollingDelivery | None = None) -> Dispatcher:
    dp = Dispatcher()
    if delivery is not None:
        dp.update.outer_middleware(delivery.update)
        dp.message.middleware(delivery.message)
    dp.update.middleware(config_middleware)
    # Keep non-allowlisted users outside DB and business middleware when the
    # temporary Cloudflare-backed test bot is publicly reachable.
    dp.update.middleware(preprod_gate_middleware)
    dp.update.middleware(db_middleware)
    if delivery is not None:
        dp.update.middleware(delivery.admit)
    dp.update.middleware(widget_query_middleware)   # после учёта доставки: повтор того же запроса не обработается дважды
    dp.update.middleware(measure_update_delivery)
    dp.errors.register(note_handler_error)
    dp.include_router(main_router)
    return dp


def attach_outbound(session, *, throttle: bool = True, delivery: PollingDelivery | None = None) -> None:
    """Outbound middlewares of the bot client, outermost first: give back the idle DB connection, then wait
    for the Telegram send slot. The simulator passes throttle=False (its Telegram has no rate limit)."""
    session.middleware(DbReleaseMiddleware())
    if delivery is not None:
        session.middleware(delivery)
    if throttle:
        session.middleware(OutboundThrottleMiddleware())
