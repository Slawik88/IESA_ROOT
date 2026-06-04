# services/scheduler.py
# Background task: polls completed expeditions and distributes rewards.
import asyncio
from loguru import logger
from aiogram import Bot

import random as _random
from services.expedition import calculate_reward
from services.daily_deal import ensure_deals_fresh
from infrastructure.repositories.zoo import get_active_species_level
from infrastructure.repositories.exchange import (
    get_active_event as _get_active_exchange,
    get_scheduled_event as _get_scheduled_exchange,
    create_event as _create_exchange_event,
    activate_event as _activate_exchange_event,
    finish_event as _finish_exchange_event,
)
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from services.achievements import increment_metric as _incr_ach
from services.quests import increment_metric as _incr_quest
from infrastructure.repositories.auction import get_expired_active_lots
from services.auction import resolve_lot
from infrastructure.repositories.duel import get_expired_pending
from services.duel import decline_duel
from core.constants import DUEL_TIMEOUT_SECONDS


async def expedition_background_task(bot: Bot):
    logger.info("Фоновый процесс экспедиций запущен.")
    while True:
        await asyncio.sleep(60)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)
                async with db.execute(
                    "SELECT e.pet_id, e.chat_id, e.duration_hours, "
                    "p.name, p.owner_id, p.marriage_id, p.species_id, "
                    "COALESCE(p.pet_level, 1) AS pet_level, "
                    "u.user_tg_username AS owner_username "
                    "FROM active_expeditions e "
                    "JOIN pets p ON e.pet_id = p.id "
                    "LEFT JOIN users u ON u.user_tg_id = p.owner_id "
                    "WHERE e.ends_at <= CURRENT_TIMESTAMP"
                ) as cursor:
                    completed = await cursor.fetchall()

                for row in completed:
                    pet_id      = row["pet_id"]
                    chat_id     = row["chat_id"]
                    hours       = row["duration_hours"]
                    pet_name    = row["name"]
                    owner_id    = row["owner_id"]
                    marriage_id = row["marriage_id"]
                    species_id  = row["species_id"]
                    species_level = row["pet_level"]
                    owner_username = row.get("owner_username") or None

                    # Collect levels of all non-exhausted nursery pets for bonus lookup.
                    species_levels: dict[str, int] = {}
                    if owner_id:
                        species_levels["owl"] = await get_active_species_level(db, owner_id, "owl")
                        species_levels["falcon"] = await get_active_species_level(db, owner_id, "falcon")
                        species_levels[species_id] = species_level

                    reward = calculate_reward(
                        hours,
                        species_id=species_id,
                        species_levels=species_levels,
                    )

                    if reward["mora"] == 0 and reward["xp"] == 0:
                        await db.execute(
                            "DELETE FROM active_expeditions WHERE pet_id = ?", (pet_id,)
                        )
                        await db.commit()
                        continue

                    from infrastructure.repositories.wallet_log import log_wallet as _lw
                    if marriage_id:
                        await db.execute(
                            "UPDATE marriages SET family_balance = family_balance + ? WHERE id = ?",
                            (reward["mora"], marriage_id),
                        )
                    elif owner_id:
                        await db.execute(
                            "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                            (reward["mora"], owner_id),
                        )
                        if reward["mora"] > 0:
                            await _lw(db, owner_id, delta_mora=reward["mora"],
                                      source="expedition", chat_id=chat_id,
                                      note=f"{hours}h")

                    if reward["diamonds"] > 0 and owner_id:
                        await db.execute(
                            "UPDATE users SET user_balance_diamonds = user_balance_diamonds + ? "
                            "WHERE user_tg_id = ?",
                            (reward["diamonds"], owner_id),
                        )
                        await _lw(db, owner_id, delta_diamonds=reward["diamonds"],
                                  source="expedition", chat_id=chat_id,
                                  note=f"{hours}h_fox")

                    if owner_id:
                        await db.execute(
                            "UPDATE user_chat_stats SET user_xp = user_xp + ? "
                            "WHERE user_tg_id = ? AND chat_tg_id = ?",
                            (reward["xp"], owner_id, chat_id),
                        )

                    if owner_id:
                        for item_id, qty in reward.get("extras", []):
                            await db.execute(
                                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                                (owner_id, item_id, qty, qty),
                            )

                    # 🗺 Карта Сокровищ: +50% к морe если есть в инвентаре
                    treasure_bonus = ""
                    if owner_id:
                        try:
                            async with db.execute(
                                "SELECT quantity FROM inventory WHERE user_id = ? "
                                "AND item_id = 'treasure_map' AND quantity > 0",
                                (owner_id,),
                            ) as _tm:
                                _tm_row = await _tm.fetchone()
                            if _tm_row:
                                bonus = int(reward["mora"] * 0.5)
                                reward["mora"] += bonus
                                await db.execute(
                                    "UPDATE inventory SET quantity = quantity - 1 "
                                    "WHERE user_id = ? AND item_id = 'treasure_map'",
                                    (owner_id,),
                                )
                                await db.execute(
                                    "UPDATE users SET user_balance_mora = user_balance_mora + ? "
                                    "WHERE user_tg_id = ?",
                                    (bonus, owner_id),
                                )
                                treasure_bonus = f"\n🗺 <b>+{bonus} 🪙</b> <i>(Карта Сокровищ!)</i>"
                        except Exception:
                            pass

                    await db.execute(
                        "DELETE FROM active_expeditions WHERE pet_id = ?", (pet_id,)
                    )
                    await db.commit()

                    # Achievement + quest: expeditions
                    if owner_id:
                        try:
                            await _incr_ach(db, owner_id, "expeditions_done", delta=1.0)
                            await _incr_quest(db, owner_id, chat_id, "expeditions_today", delta=1.0)
                            await db.commit()
                        except Exception:
                            pass

                    # Build owner mention line
                    if owner_username:
                        owner_mention = f'<a href="tg://user?id={owner_id}">@{owner_username}</a>'
                    elif owner_id:
                        owner_mention = f'<a href="tg://user?id={owner_id}">Игрок</a>'
                    else:
                        owner_mention = "Игрок"

                    try:
                        text = (
                            f"🎉 {owner_mention}, <b>питомец вернулся!</b>\n"
                            f"🐾 <b>{pet_name}</b> завершил поход ({hours} ч.) и принёс:\n"
                            f"🪙 Мора: <b>+{reward['mora']}</b>\n"
                            f"💠 Опыт: <b>+{reward['xp']}</b>"
                            f"{reward['buff_message']}"
                            f"{treasure_bonus}"
                        )
                        await bot.send_message(chat_id, text, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Не удалось отправить уведомление в чат {chat_id}: {e}")

                    # Notify WebSocket clients (same process — no-op if user not connected)
                    if owner_id:
                        try:
                            from FastAPI.notifications import notify as _ws_notify
                            await _ws_notify(owner_id, {
                                "type": "expedition_done",
                                "pet": pet_name,
                                "mora": reward["mora"],
                                "xp": reward["xp"],
                            })
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"Ошибка в фоновом процессе экспедиций: {e}")
            await asyncio.sleep(30)  # backoff on error — avoid tight crash loops


async def daily_deal_task():
    """Regenerate the daily deal at 00:00 UTC."""
    logger.info("Фоновая задача акции дня запущена.")
    while True:
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)
                await ensure_deals_fresh(db)
        except Exception as e:
            logger.error(f"Ошибка в задаче акции дня: {e}")
            await asyncio.sleep(30)
        await asyncio.sleep(600)


async def duel_and_auction_task(bot: Bot):
    """Every minute: expire timed-out duels + resolve expired auction lots."""
    logger.info("Фоновая задача дуэлей/аукциона запущена.")
    while True:
        await asyncio.sleep(60)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)

                # ── Expire timed-out duels ────────────────────────────────────
                expired_duels = await get_expired_pending(db, DUEL_TIMEOUT_SECONDS)
                for duel in expired_duels:
                    try:
                        await decline_duel(db, duel["id"])
                        await bot.send_message(
                            duel["chat_id"],
                            f"⏰ Вызов на дуэль истёк — ставка возвращена.",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Duel timeout error {duel['id']}: {e}")

                # ── Resolve expired auction lots ──────────────────────────────
                expired_lots = await get_expired_active_lots(db)
                for lot in expired_lots:
                    try:
                        result = await resolve_lot(db, lot["id"])
                        if not result:
                            continue
                        if result["status"] == "sold":
                            winner_id = result["winner_id"]
                            seller_id = lot["seller_id"]
                            price = result.get("final_price", 0)
                            item_name = lot.get("item_name", "?").split("||")[0]
                            # Achievement: dealer — metric name, not key
                            try:
                                await _incr_ach(db, seller_id, "auction_sales", delta=1.0)
                                await db.commit()
                            except Exception:
                                pass
                            # Notify winner
                            try:
                                await bot.send_message(
                                    winner_id,
                                    f"🏆 <b>Вы выиграли лот аукциона!</b>\n"
                                    f"Предмет: <b>{item_name}</b>\n"
                                    f"Цена: <code>{price:.0f} 🪙</code>\n"
                                    f"Предмет добавлен в ваш инвентарь.",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass
                            # Notify seller
                            try:
                                commission = price * 0.05
                                await bot.send_message(
                                    seller_id,
                                    f"✅ <b>Ваш лот продан!</b>\n"
                                    f"Предмет: <b>{item_name}</b>\n"
                                    f"Цена: <code>{price:.0f} 🪙</code> "
                                    f"(−{commission:.0f} комиссия)\n"
                                    f"Получено: <code>{price - commission:.0f} 🪙</code>",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass
                        else:
                            # Expired with no bids
                            try:
                                await bot.send_message(
                                    lot["seller_id"],
                                    f"⏰ Лот «{lot.get('item_name','?').split('||')[0]}» истёк без ставок. "
                                    f"Предмет возвращён.",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        logger.error(f"Auction resolve error lot {lot['id']}: {e}")

                # ── Weekly: achievement "star" (weekly_top1_count) ─────────────
                # Run once per Monday: check that this Monday hasn't been processed yet
                # using a sentinel row in player_buffs (buff_type='weekly_top1_done').
                from datetime import datetime, timezone as _tz
                _now = datetime.now(_tz.utc)
                _monday_date = (_now - __import__('datetime').timedelta(days=_now.weekday())).strftime("%Y-%m-%d")
                if _now.weekday() == 0 and _now.hour == 0:
                    try:
                        # Guard: only run once per Monday using a sentinel in player_buffs
                        async with db.execute(
                            "SELECT 1 FROM player_buffs WHERE user_id = 0 AND buff_type = ? LIMIT 1",
                            (f"weekly_top1_done_{_monday_date}",),
                        ) as _chk:
                            _already = await _chk.fetchone()
                        if _already:
                            pass  # Already processed this Monday
                        else:
                            # Mark as done first to prevent duplicates
                            await db.execute(
                                "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
                                "VALUES (0, ?, 1, NOW() + INTERVAL '8 days') "
                                "ON CONFLICT (user_id, buff_type) DO NOTHING",
                                (f"weekly_top1_done_{_monday_date}",),
                            )
                            await db.commit()
                            async with db.execute(
                                "SELECT chat_id FROM chat_settings LIMIT 500"
                            ) as _cc:
                                _chats = [r[0] for r in await _cc.fetchall()]
                            for _weekly_cid in _chats:
                                # Find user with most messages last week
                                async with db.execute(
                                    "SELECT user_id, SUM(message_count) AS wc "
                                    "FROM daily_user_stats "
                                    "WHERE chat_id = ? AND date >= CURRENT_DATE - INTERVAL '7 days' "
                                    "GROUP BY user_id ORDER BY wc DESC LIMIT 1",
                                    (_weekly_cid,),
                                ) as _tc:
                                    _top = await _tc.fetchone()
                                if _top and _top[0]:
                                    await _incr_ach(db, _top[0], "weekly_top1_count", delta=1.0)
                            await db.commit()
                    except Exception as _e:
                        logger.warning(f"weekly_top1 tracking error: {_e}")

        except Exception as e:
            logger.error(f"Ошибка в задаче дуэлей/аукциона: {e}")
            await asyncio.sleep(30)


async def chest_spawn_task(bot: Bot):
    """Every 5 minutes: spawn chests in qualifying chats + expire old ones."""
    logger.info("Фоновая задача сундуков запущена.")
    while True:
        await asyncio.sleep(300)
        try:
            from core.constants import (
                CHEST_DURATION_SECONDS, CHEST_MIN_ACTIVE_USERS_24H,
                CHEST_SPAWN_MIN_HOURS, CHEST_SPAWN_MAX_HOURS, CHEST_MAX_CLAIMANTS,
                CHEST_REWARDS_BY_POSITION,
            )
            from infrastructure.repositories.chest_events import (
                get_qualifying_chats, create_chest, close_chest,
                get_expired_active, get_claims, update_last_chest_at,
            )
            from infrastructure.repositories.economy import add_balance as _ab
            from infrastructure.repositories.wallet_log import log_wallet as _lw
            from datetime import datetime, timedelta, timezone

            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)

                # Close expired chests (rewards already paid immediately in events.py on click)
                expired = await get_expired_active(db)
                for chest in expired:
                    try:
                        await close_chest(db, chest["id"])
                        await update_last_chest_at(db, chest["chat_id"])
                        await db.commit()
                    except Exception as e:
                        logger.error(f"Chest expire error {chest['id']}: {e}")

                # Spawn new chests in qualifying chats
                qualifying = await get_qualifying_chats(db, CHEST_MIN_ACTIVE_USERS_24H)
                for chat_id in qualifying:
                    # Random spawn: not every qualifying chat gets one every cycle
                    if _random.random() > 0.3:
                        continue
                    try:
                        expires = (datetime.now(timezone.utc)
                                   + timedelta(seconds=CHEST_DURATION_SECONDS))
                        expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")
                        chest_id = await create_chest(db, chat_id, expires_str)
                        await db.commit()

                        from aiogram.utils.keyboard import InlineKeyboardBuilder
                        from aiogram.filters.callback_data import CallbackData

                        class _ChestCB(CallbackData, prefix="chest"):
                            chest_id: int

                        b = InlineKeyboardBuilder()
                        b.button(
                            text=f"👋 Забрать! (0/{CHEST_MAX_CLAIMANTS})",
                            callback_data=_ChestCB(chest_id=chest_id),
                        )
                        _r = CHEST_REWARDS_BY_POSITION
                        await bot.send_message(
                            chat_id,
                            "💰 <b>НАЙДЕН СУНДУК ПРЕДВЕСТНИКА!</b>\n\n"
                            f"🥇 1 место: <b>{int(_r.get(1,300))} 🪙</b> + 🎟 Жетон\n"
                            f"🥈 2 место: <b>{int(_r.get(2,260))} 🪙</b> + 🎟 Жетон\n"
                            f"🥉 3 место: <b>{int(_r.get(3,220))} 🪙</b> + 🎟 Жетон\n"
                            f"4–15 место: <b>{int(_r.get(15,30))}–{int(_r.get(4,190))} 🪙</b>\n\n"
                            "Нажми быстрее — чем раньше, тем больше! ⏳ 90 сек.",
                            reply_markup=b.as_markup(),
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Chest spawn error chat {chat_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка в задаче сундуков: {e}")
            await asyncio.sleep(30)


async def exchange_scheduler_task(bot: Bot):
    """Every 30 min: schedule/activate/finish exchange events.
    One random day per week has a 24h exchange window."""
    logger.info("Фоновая задача ивента обмена запущена.")
    while True:
        await asyncio.sleep(1800)
        try:
            from datetime import datetime, timedelta, timezone as tz
            now = datetime.now(tz.utc)
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")

            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)

                # Finish active events that have ended
                active = await _get_active_exchange(db)
                if active and active["ends_at"] <= now_str:
                    await _finish_exchange_event(db, active["id"])
                    await db.commit()
                    logger.info(f"Exchange event {active['id']} finished.")

                # Activate scheduled events that have started
                scheduled = await _get_scheduled_exchange(db)
                if scheduled and scheduled["starts_at"] <= now_str and scheduled["status"] == "scheduled":
                    await _activate_exchange_event(db, scheduled["id"])
                    await db.commit()
                    # Announce to qualifying chats
                    from infrastructure.repositories.chest_events import get_qualifying_chats
                    from core.constants import EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_DAILY_CAP_DIAMONDS
                    chats = await get_qualifying_chats(db, 1)
                    for chat_id in chats[:50]:  # limit broadcasts
                        try:
                            await bot.send_message(
                                chat_id,
                                f"💎 <b>ИВЕНТ: ОБМЕН МОРЫ → АЛМАЗЫ</b>\n\n"
                                f"В течение 24 часов обменивайте Мору!\n"
                                f"Курс: <code>{int(EXCHANGE_RATE_MORA_PER_DIAMOND)} 🪙 = 1 💎</code>\n"
                                f"Лимит: <code>{int(EXCHANGE_DAILY_CAP_DIAMONDS)} 💎/день</code>\n\n"
                                f"Команда: <code>бот обмен, [алмазов]</code>",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                # Schedule next event if none exists
                if not active and not scheduled:
                    # Pick random day next Mon-Sun
                    monday = now - timedelta(days=now.weekday())
                    rand_day = _random.randint(0, 6)
                    event_start = (monday + timedelta(days=rand_day)).replace(
                        hour=_random.randint(8, 20), minute=0, second=0, microsecond=0
                    )
                    if event_start < now:
                        event_start += timedelta(weeks=1)
                    event_end = event_start + timedelta(hours=24)
                    await _create_exchange_event(
                        db,
                        event_start.strftime("%Y-%m-%d %H:%M:%S"),
                        event_end.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    await db.commit()
                    logger.info(f"Exchange event scheduled for {event_start}")

        except Exception as e:
            logger.error(f"Ошибка в задаче обмена: {e}")
            await asyncio.sleep(30)
