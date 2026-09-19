"""Background jobs that belong to the current product surface."""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter


async def mafia_phase_task(bot: Bot) -> None:
    """Durably close enabled Mafia phases from PostgreSQL deadlines."""
    logger.info("Mafia phase scheduler started.")
    while True:
        await asyncio.sleep(5)
        try:
            from bot.handlers.mafia_v1 import notify_phase_transition, publish_phase
            from infrastructure.repositories import mafia_v1 as repo
            from infrastructure.repositories import system_flags
            from services import mafia_v1 as mafia

            async with get_pool().acquire() as conn:
                db = PGAdapter(conn)
                if not await system_flags.is_enabled(db, "game_mafia_v1"):
                    continue
                for match_id in await repo.due_match_ids(db):
                    event = await mafia.advance_due_match(db, match_id=match_id)
                    if event:
                        await notify_phase_transition(bot, db, event)
                for row in await repo.timed_matches(db):
                    view = await mafia.current_view(db, match_id=int(row["id"]))
                    if view:
                        await publish_phase(bot, db, view)
        except Exception as exc:
            logger.exception(f"Mafia phase scheduler error: {exc}")


_daily_gc_day: str | None = None


async def _daily_gc(db) -> None:
    """Run the retained operational cleanup once per UTC day."""
    global _daily_gc_day
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily_gc_day == today:
        return
    _daily_gc_day = today
    try:
        await db.execute(
            "DELETE FROM site_analytics "
            "WHERE visited_at < NOW() - INTERVAL '180 days'"
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"analytics GC error: {exc}")
    try:
        from infrastructure.repositories.moderation import expire_due_warns

        expired = await expire_due_warns(db, None)
        if expired:
            logger.info(f"Срочные варны: сгорело {expired}")
    except Exception as exc:
        logger.warning(f"warn expiry GC error: {exc}")
    try:
        from services.account_deletion import daily_tick

        await daily_tick(db)
    except Exception as exc:
        logger.warning(f"account deletion tick error: {exc}")


async def maintenance_task() -> None:
    """Keep operational maintenance alive without reviving retired systems."""
    logger.info("Фоновая задача обслуживания запущена.")
    while True:
        try:
            async with get_pool().acquire() as connection:
                await _daily_gc(PGAdapter(connection))
        except Exception as exc:
            logger.error(f"Ошибка в задаче обслуживания: {exc}")
            await asyncio.sleep(30)
        await asyncio.sleep(600)
