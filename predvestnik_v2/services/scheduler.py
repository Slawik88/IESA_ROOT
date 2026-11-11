"""Background jobs that belong to the current product surface."""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger

from infrastructure import lazy_db
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter


async def player_exchange_match_task() -> None:
    """Batch-match enabled player markets on the approved 15-second cadence."""
    logger.info("Player exchange matcher started.")
    while True:
        await asyncio.sleep(15)
        try:
            from infrastructure.repositories import player_exchange_v1 as repo, system_flags
            from services import player_exchange_v1 as exchange
            # Lazy: the slot is taken per market and given back between them
            # (one fill per transaction inside match_market), not for the whole round.
            async with lazy_db.lazy_connection(get_pool(), source="background") as db:
                if not await system_flags.is_enabled(db, "economy_player_exchange_v1"):
                    continue
                for coin_id in await repo.active_market_ids(db):
                    try:
                        await exchange.match_market(db, coin_id=coin_id, max_trades=100)
                    except Exception as market_error:
                        logger.exception(
                            f"Player exchange market {coin_id} failed: {market_error}"
                        )
                    await db.release_if_idle()
        except Exception as exc:
            logger.exception(f"Player exchange matcher error: {exc}")


async def coin_market_v2_task() -> None:
    from services.coin_market_v2 import maintenance
    while True:
        await asyncio.sleep(15)
        try:
            async with lazy_db.lazy_connection(get_pool(), source="background") as db:
                await maintenance(db)
        except Exception:
            logger.exception('Coin market v2 maintenance failed; stale trading stays closed')


# UTC day of the last SUCCESSFUL run of each daily job (audit A12). A failed job
# is retried on the next maintenance pass (every 10 minutes), not the next day,
# but at most _DAILY_MAX_ATTEMPTS times per UTC day: the job batches (LIMIT 50
# warnings/deletions) were sized for one run a day.
_daily_done: dict[str, str] = {}
_daily_attempts: dict[str, tuple[str, int]] = {}
_DAILY_MAX_ATTEMPTS = 6


async def _analytics_gc(db) -> None:
    await db.execute(
        "DELETE FROM site_analytics "
        "WHERE visited_at < NOW() - INTERVAL '180 days'"
    )
    await db.commit()


async def _account_deletion_tick(db) -> None:
    from services.account_deletion import daily_tick

    await daily_tick(db)


_DAILY_JOBS = (
    ("analytics GC", _analytics_gc),
    ("account deletion tick", _account_deletion_tick),
)


async def _daily_gc(db) -> None:
    """Run each retained operational job once per UTC day, counting only successes."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for name, job in _DAILY_JOBS:
        if _daily_done.get(name) == today:
            continue
        day, attempts = _daily_attempts.get(name, (today, 0))
        attempts = attempts if day == today else 0
        if attempts >= _DAILY_MAX_ATTEMPTS:
            continue
        _daily_attempts[name] = (today, attempts + 1)
        try:
            await job(db)
        except Exception as exc:
            if attempts + 1 >= _DAILY_MAX_ATTEMPTS:
                logger.error(f"{name} failed {attempts + 1} times today, next try tomorrow: {exc}")
            else:
                logger.warning(f"{name} error, retrying on the next maintenance pass: {exc}")
            continue
        _daily_done[name] = today


async def maintenance_task(bot: Bot) -> None:
    """Keep operational maintenance alive without reviving retired systems."""
    logger.info("Фоновая задача обслуживания запущена.")
    while True:
        try:
            # Lazy: the VIP and onboarding reminders below call Telegram; the connection is not held meanwhile.
            async with lazy_db.lazy_connection(get_pool(), source="background") as db:
                await _daily_gc(db)
                try:
                    from services.support_reports import storage as support_storage
                    await support_storage.prepare(db)
                except Exception as support_error:
                    logger.warning("Support report retention failed: {}",type(support_error).__name__)
                from services.player_exchange_v1 import (
                    execute_due_emissions, execute_due_liquidity_withdrawals, run_short_risk_maintenance,
                    settle_due_auctions,
                )
                for settlement in await settle_due_auctions(db, limit=20):
                    if settlement.get("error"):
                        logger.error(
                            "Player exchange auction settlement failed: coin={} error={}",
                            settlement.get("coin_id"), settlement.get("error"),
                        )
                        continue
                    logger.info(
                        "Player exchange auction settled: coin={} success={} sold={}",
                        settlement.get("coin_id"), settlement.get("success"),
                        settlement.get("sold_units"),
                    )
                await db.release_if_idle()   # короткие порции: слот пула свободен между группами
                for emission in await execute_due_emissions(db, limit=20):
                    if emission.get("error"):
                        logger.error("Player exchange emission failed: {}", emission)
                    elif emission:
                        logger.info("Player exchange emission executed: emission={} coin={} units={}",
                                    emission.get("id"), emission.get("coin_id"), emission.get("requested_units"))
                for withdrawal in await execute_due_liquidity_withdrawals(db, limit=20):
                    if withdrawal.get("error"):
                        logger.error("Player exchange liquidity withdrawal failed: {}", withdrawal)
                    elif withdrawal:
                        logger.info("Player exchange liquidity withdrawal executed: withdrawal={} coin={} mora={}",
                                    withdrawal.get("id"), withdrawal.get("coin_id"), withdrawal.get("amount_mora"))
                for short_result in await run_short_risk_maintenance(db, limit=50):
                    if short_result.get("error"):
                        logger.error("Short risk maintenance failed: {}", short_result)
                    elif short_result.get("marked"):
                        logger.warning("Short risk marked for player liquidation: {}", short_result)
                await db.release_if_idle()   # и перед сезонными итогами: дальше только свои порции
                try:   # итоги сезонов: снимок мест и выплаты порциями (возобновляемо, повтор безопасен)
                    from services import game_seasons, rhythm_v2
                    season_summary = await game_seasons.settle_due(
                        db, boards={("rhythm", "normal"): rhythm_v2.season_standings})
                    if any(season_summary.values()):
                        logger.info("Game season settlement: {}", season_summary)
                except Exception as season_error:
                    logger.exception(f"game season settlement failed: {season_error}")
                try:   # напоминание тем, кто добавил бота в чат и не выдал права (через час и через сутки)
                    from bot.chat import onboarding
                    await onboarding.send_reminders(bot, db)
                except Exception as onboarding_error:
                    logger.warning(f"onboarding reminders failed: {onboarding_error}")
                try:   # игры вдвоём в переписках: брошенные на сутки закрыть и вернуть жетоны (S29a)
                    from bot.chat import pair_cards
                    await pair_cards.expire(bot, db)
                except Exception as pair_error:
                    logger.warning(f"pair games expiry failed: {pair_error}")
                try:   # «Гонка за Пропуском»: место, о котором владельцу ещё не написали (запасной путь к фоновой отправке)
                    from services import pass_race
                    await pass_race.announce_pending(db)
                except Exception as race_error:
                    logger.warning(f"pass race announce failed: {race_error}")
                try:   # напоминание про VIP-поручение: в общую очередь уведомлений (согласие, тихие часы, лимит, пауза)
                    from services import dm_push_events
                    await dm_push_events.vip_daily_reminders(db)
                except Exception as reminder_error:
                    logger.warning(f"VIP reminders failed: {reminder_error}")
        except Exception as exc:
            logger.error(f"Ошибка в задаче обслуживания: {exc}")
            await asyncio.sleep(30)
        await asyncio.sleep(600)


async def mafia_tick(bot: Bot) -> None:
    """One scheduler pass for chat Mafia (see bot.chat.mafia_delivery.tick)."""
    from bot.chat.mafia_delivery import tick

    pool = get_pool()
    async with lazy_db.lazy_connection(pool, source="background") as db:
        await tick(bot, db, pool)


async def mafia_phase_task(bot: Bot) -> None:
    """Durably close enabled Mafia phases from PostgreSQL deadlines."""
    logger.info("Mafia phase scheduler started.")
    while True:
        await asyncio.sleep(2)
        try:
            await mafia_tick(bot)
        except Exception as exc:
            logger.exception(f"Mafia phase scheduler error: {exc}")


async def dm_push_task(bot: Bot) -> None:
    """Уведомления в личку: раз в 5 минут собрать события согласившихся игроков, раз в минуту доставить очередь."""
    from bot.chat.notify import markup_for
    from services import dm_push, dm_push_events
    logger.info("Доставка уведомлений в личку запущена.")
    tick = 0
    while True:
        wait = 60
        try:
            async with lazy_db.lazy_connection(get_pool(), source="background") as db:
                if tick % 5 == 0:
                    collected = await dm_push_events.collect(db)
                    if any(collected.values()):
                        logger.info(f"dm push: события в очередь {collected}")
                stats = await dm_push.deliver_due(bot, db, markup=markup_for)
                if stats["sent"] or stats["unreachable"] or stats["failed"]:
                    logger.info(f"dm push: {stats}")
                wait = max(wait, stats["retry_after"])   # Telegram попросил притормозить — ждём, не повторяем сразу
                if tick % 1440 == 0:
                    from infrastructure.repositories import dm_push as dm_push_repo
                    await dm_push_repo.gc(db)
                    await db.commit()
        except Exception as exc:
            logger.warning(f"dm push loop error: {type(exc).__name__}: {exc}")
        tick += 1
        await asyncio.sleep(wait)
