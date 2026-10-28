"""The one Dispatcher setup shared by production (bot/__main__.py) and the Telegram simulator (tools/mafia_sim).

Both must see the same middlewares and the same error monitor, otherwise a simulated
handler failure would never reach the health counters.
"""
from aiogram import Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import ErrorEvent
from loguru import logger

from bot.handlers import main_router
from bot.middlewares.config_mw import config_middleware
from bot.middlewares.db import DbReleaseMiddleware, db_middleware
from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware
from bot.middlewares.preprod_gate_mw import preprod_gate_middleware
from services import ops_health


async def note_handler_error(event: ErrorEvent):
    """Count the failure per handler (health panel, owner alert), then let aiogram handle it as before."""
    try:
        ops_health.record_bot_error(event.exception, event.update.event_type)
    except Exception as exc:   # monitoring must never change what happens to the update
        logger.warning(f"bot error monitor failed: {type(exc).__name__}: {exc}")
    return UNHANDLED   # the original exception is re-raised and logged by aiogram unchanged


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(config_middleware)
    # Keep non-allowlisted users outside DB and business middleware when the
    # temporary Cloudflare-backed test bot is publicly reachable.
    dp.update.middleware(preprod_gate_middleware)
    dp.update.middleware(db_middleware)
    dp.errors.register(note_handler_error)
    dp.include_router(main_router)
    return dp


def attach_outbound(session, *, throttle: bool = True) -> None:
    """Outbound middlewares of the bot client, outermost first: give back the idle DB connection, then wait
    for the Telegram send slot. The simulator passes throttle=False (its Telegram has no rate limit)."""
    session.middleware(DbReleaseMiddleware())
    if throttle:
        session.middleware(OutboundThrottleMiddleware())
