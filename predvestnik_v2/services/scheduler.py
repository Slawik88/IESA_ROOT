# services/scheduler.py
# Background task: polls completed expeditions and distributes rewards.
import asyncio
import os
from loguru import logger
from aiogram import Bot

import random as _random
from services.expedition import calculate_reward
from services.daily_deal import ensure_deals_fresh
from infrastructure.repositories.zoo import get_species_level_placement
from infrastructure.repositories.notifications import is_enabled as _notif_enabled
from infrastructure.repositories.relics import get_expedition_mora_bonus as _relic_exp_bonus
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from datetime import datetime, timedelta, timezone
from core.constants import (
    CHEST_DURATION_SECONDS, CHEST_MIN_ACTIVE_USERS_24H,
    CHEST_MAX_CLAIMANTS, CHEST_REWARDS_BY_POSITION, DRAGON_BONUSES,
    FOX_BONUSES,
)
from infrastructure.repositories.chest_events import (
    get_qualifying_chats, create_chest, close_chest,
    get_expired_active, update_last_chest_at,
)
from infrastructure.repositories.economy import add_balance as _ab, add_item as _add_item
from services.achievements import increment_metric as _incr_ach
from services.quests import increment_metric as _incr_quest
from infrastructure.repositories.auction import get_expired_active_lots
from infrastructure.repositories.wallet_log import log_wallet as _lw
from services.auction import resolve_lot, flush_pending_announcements
from infrastructure.repositories.duel import get_expired_pending
from services.duel import decline_duel
from core.constants import (
    DUEL_TIMEOUT_SECONDS, VIP_EXPIRY_REMINDER_DAYS, BATTLE_PASS_SEASON_END_REMINDER_DAYS,
    PUSH_MIN_INTERVAL_SEC, PUSH_PRIORITIES, PUSH_EVENT_TTL_SEC,
)
from infrastructure.repositories import push as push_repo
from core.registry import VIP_TIERS
from services.battle_pass import get_active_season, refresh_seasons_cache as refresh_bp_seasons


async def _finish_expedition(bot: Bot, db, row) -> None:
    """Выдать награду за ОДНУ завершённую экспедицию + все уведомления (чат/WS)."""
    pet_id      = row["pet_id"]
    chat_id     = row["chat_id"]
    hours       = row["duration_hours"]
    pet_name    = row["name"]
    owner_id    = row["owner_id"]
    marriage_id = row["marriage_id"]
    species_id  = row["species_id"]
    species_level = row["pet_level"]
    owner_username = row.get("owner_username") or None

    # Collect levels + placements of nursery pets for bonus lookup.
    # Block 12: passive-питомцы дают вдвое слабее (экспедиционный — active).
    species_levels: dict[str, int] = {}
    species_placements: dict[str, str | None] = {}
    if owner_id:
        for _sp in ("owl", "falcon"):
            _lv, _plc = await get_species_level_placement(db, owner_id, _sp)
            species_levels[_sp] = _lv
            species_placements[_sp] = _plc
        species_levels[species_id] = species_level
        species_placements[species_id] = "active"

    relic_mora_pct = await _relic_exp_bonus(db, owner_id) if owner_id else 0.0
    from services.clans2 import academy_pct as _academy_pct
    _acad = await _academy_pct(db, owner_id) if owner_id else 0.0
    reward = calculate_reward(
        hours,
        species_id=species_id,
        species_levels=species_levels,
        species_placements=species_placements,
        relic_mora_pct=relic_mora_pct,
        academy_pct=_acad,
    )

    if reward["mora"] == 0 and reward["xp"] == 0:
        await db.execute(
            "DELETE FROM active_expeditions WHERE pet_id = ?", (pet_id,)
        )
        await db.commit()
        return

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

    # Notify WebSocket clients (same process). Если игрок офлайн —
    # сохраняем чек в web_notifications для показа при входе (Welcome Back).
    if owner_id:
        ws_payload = {
            "type": "expedition_done",
            "pet": pet_name,
            "mora": reward["mora"],
            "xp": reward["xp"],
            "diamonds": reward.get("diamonds", 0),
            "base_mora": reward.get("base_mora", reward["mora"]),
            "base_xp": reward.get("base_xp", reward["xp"]),
            "breakdown": reward.get("breakdown", []),
        }
        try:
            from FastAPI.notifications import notify as _ws_notify
            delivered = await _ws_notify(owner_id, ws_payload)
        except Exception:
            delivered = False
        if not delivered:
            try:
                from infrastructure.repositories import web_notifications as _wn
                await _wn.add(db, owner_id, ws_payload)
                await db.commit()
            except Exception:
                pass


async def expedition_background_task(bot: Bot):
    """Каждую минуту: находит завершённые экспедиции и выдаёт награды."""
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
                    await _finish_expedition(bot, db, row)

        except Exception as e:
            logger.error(f"Ошибка в фоновом процессе экспедиций: {e}")
            await asyncio.sleep(30)  # backoff on error — avoid tight crash loops


_daily_gc_day: str | None = None


async def _daily_gc(db) -> None:
    """Ежедневная уборка (admin_audit C1a/B3), раз в календарные сутки UTC:
    - site_analytics: записи старше 180 дней (таблица росла бесконечно);
    - истёкшие срочные варны: списать из счётчиков по всем чатам."""
    global _daily_gc_day
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily_gc_day == today:
        return
    _daily_gc_day = today
    try:
        await db.execute(
            "DELETE FROM site_analytics WHERE visited_at < NOW() - INTERVAL '180 days'")
        await db.commit()
    except Exception as e:
        logger.warning(f"analytics GC error: {e}")
    try:
        from infrastructure.repositories.moderation import expire_due_warns
        n = await expire_due_warns(db, None)
        if n:
            logger.info(f"Срочные варны: сгорело {n}")
    except Exception as e:
        logger.warning(f"warn expiry GC error: {e}")


async def daily_deal_task():
    """Regenerate the daily deal at 00:00 UTC."""
    logger.info("Фоновая задача акции дня запущена.")
    while True:
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)
                await ensure_deals_fresh(db)
                await _daily_gc(db)
        except Exception as e:
            logger.error(f"Ошибка в задаче акции дня: {e}")
            await asyncio.sleep(30)
        await asyncio.sleep(600)


async def _expire_timed_out_duels(bot: Bot, db) -> None:
    """Отклонить дуэли, где вызванный не ответил вовремя (ставка возвращается)."""
    expired_duels = await get_expired_pending(db, DUEL_TIMEOUT_SECONDS)
    for duel in expired_duels:
        try:
            await decline_duel(db, duel["id"])
            await bot.send_message(
                duel["chat_id"],
                "⏰ Вызов на дуэль истёк — ставка возвращена.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Duel timeout error {duel['id']}: {e}")


async def _resolve_expired_auction_lots(bot: Bot, db) -> None:
    """Закрыть истёкшие лоты: выдать предмет/деньги + уведомить победителя и продавца."""
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


async def _send_vip_expiry_reminders(bot: Bot, db) -> None:
    """Block 4.5: напомнить об истечении VIP. Флаг expiry_notified — от повторов;
    ставится даже если игрок отключил уведомления (Block 15)."""
    async with db.execute(
        "SELECT user_id, tier, expires_at FROM vip_subscriptions "
        "WHERE expires_at BETWEEN NOW() AND NOW() + make_interval(days => ?) "
        "AND expiry_notified = FALSE",
        (VIP_EXPIRY_REMINDER_DAYS,),
    ) as _ec:
        _expiring = await _ec.fetchall()
    for _erow in _expiring:
        _euid, _etier, _eexp = _erow[0], _erow[1], _erow[2]
        _elabel = VIP_TIERS.get(_etier, {}).get("label", _etier)
        if await _notif_enabled(db, _euid, "vip_expiry"):
            try:
                await bot.send_message(
                    _euid,
                    f"⏳ Твой <b>{_elabel}</b> истекает {_eexp:%d.%m}. "
                    f"Продлить — «бот вип».",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await db.execute(
            "UPDATE vip_subscriptions SET expiry_notified = TRUE WHERE user_id = ?",
            (_euid,),
        )
    if _expiring:
        await db.commit()


async def _send_bp_season_end_reminders(bot: Bot, db) -> None:
    """Block 5.8: напомнить активным игрокам (level > 1) о конце сезона БП —
    один раз за сезон (флаг season_end_notified ставится даже при отключённых
    уведомлениях, Block 15)."""
    _bp_season = get_active_season()
    if not _bp_season:
        return
    _bp_ends = datetime.strptime(_bp_season["ends_at"], "%Y-%m-%d").date()
    _bp_days_left = (_bp_ends - datetime.now(timezone.utc).date()).days
    if not (0 <= _bp_days_left <= BATTLE_PASS_SEASON_END_REMINDER_DAYS):
        return
    async with db.execute(
        "SELECT user_id FROM battle_pass_progress "
        "WHERE season_id = ? AND level > 1 AND NOT season_end_notified",
        (_bp_season["id"],),
    ) as _bc:
        _bp_users = await _bc.fetchall()
    for _brow in _bp_users:
        if not await _notif_enabled(db, _brow[0], "bp_reminder"):
            continue
        try:
            await bot.send_message(
                _brow[0],
                f"🎫 Сезон «{_bp_season['label']}» Боевого пропуска заканчивается "
                f"через {_bp_days_left} дн.! Не забудь забрать награды — «бот бп».",
                parse_mode="HTML",
            )
        except Exception:
            pass
    if _bp_users:
        await db.execute(
            "UPDATE battle_pass_progress SET season_end_notified = TRUE "
            "WHERE season_id = ? AND level > 1 AND NOT season_end_notified",
            (_bp_season["id"],),
        )
        await db.commit()


async def _grant_weekly_top1_achievements(db) -> None:
    """Ачивка weekly_top1_count самому активному игроку недели в каждом чате.
    Сверяем реальное членство (см. services/membership.py) — иначе ачивку
    можно получить, набрав сообщений и уйдя из чата ещё до конца недели."""
    from services.membership import prune_ghosts
    async with db.execute("SELECT chat_id FROM chat_settings LIMIT 500") as _cc:
        _chats = [r[0] for r in await _cc.fetchall()]
    for _weekly_cid in _chats:
        async with db.execute(
            "SELECT user_id, SUM(message_count) AS wc "
            "FROM daily_user_stats "
            "WHERE chat_id = ? AND date >= CURRENT_DATE - INTERVAL '7 days' "
            "GROUP BY user_id ORDER BY wc DESC LIMIT 1",
            (_weekly_cid,),
        ) as _tc:
            _top = await _tc.fetchone()
        if _top and _top[0]:
            _left = await prune_ghosts(db, _weekly_cid, [_top[0]])
            if _top[0] not in _left:
                await _incr_ach(db, _top[0], "weekly_top1_count", delta=1.0)
    await db.commit()


async def _grant_weekly_dragon_bank(db) -> None:
    """Дракон Lv10 (не измотан): еженедельный грант Моры (weekly_bank_grant)."""
    async with db.execute(
        "SELECT DISTINCT owner_id, pet_level FROM pets "
        "WHERE species_id = 'dragon' AND placement IN ('active', 'passive') "
        "AND pet_level >= 10 AND fatigue < 100 AND owner_id IS NOT NULL"
    ) as _dc:
        _dragon_owners = await _dc.fetchall()
    for _drow in _dragon_owners:
        _uid = _drow[0]
        _lvl = min(10, max(1, int(_drow[1])))
        _grant = DRAGON_BONUSES.get(_lvl, {}).get("weekly_bank_grant", 0.0)
        if _grant > 0:
            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora + ? "
                "WHERE user_tg_id = ?",
                (_grant, _uid),
            )
            await _lw(db, _uid, delta_mora=_grant,
                      source="dragon_weekly", note="dragon_lv10_bank")
    await db.commit()


async def _grant_weekly_fox_diamond(db) -> None:
    """Лиса Lv8+ (не измотана): еженедельный гарантированный алмаз."""
    async with db.execute(
        "SELECT DISTINCT owner_id, pet_level FROM pets "
        "WHERE species_id = 'fox' AND placement IN ('active', 'passive') "
        "AND pet_level >= 8 AND fatigue < 100 AND owner_id IS NOT NULL"
    ) as _fc:
        _fox_owners = await _fc.fetchall()
    for _frow in _fox_owners:
        _uid = _frow[0]
        _lvl = min(10, max(1, int(_frow[1])))
        if FOX_BONUSES.get(_lvl, {}).get("weekly_guaranteed_diamond", False):
            await db.execute(
                "UPDATE users SET user_balance_diamonds = user_balance_diamonds + 1 "
                "WHERE user_tg_id = ?",
                (_uid,),
            )
            await _lw(db, _uid, delta_diamonds=1,
                      source="fox_weekly", note="fox_lv8_diamond")
    await db.commit()


async def _grant_weekly_vip_items(bot: Bot, db) -> None:
    """Block 4.4: еженедельные VIP-пробники по тарифу + уведомление в ЛС."""
    async with db.execute(
        "SELECT user_id, tier FROM vip_subscriptions WHERE expires_at > NOW()"
    ) as _vc:
        _vip_rows = await _vc.fetchall()
    for _vrow in _vip_rows:
        _vuid, _vtier = _vrow[0], _vrow[1]
        _weekly_items = VIP_TIERS.get(_vtier, {}).get("weekly", ())
        for _item_id, _qty in _weekly_items:
            await _add_item(db, _vuid, _item_id, _qty)
        if _weekly_items:
            await db.commit()
            try:
                await bot.send_message(
                    _vuid,
                    "🎁 <b>Еженедельный VIP-бонус начислен!</b> Загляни в инвентарь.",
                    parse_mode="HTML",
                )
            except Exception:
                pass


async def _run_weekly_monday_jobs(bot: Bot, db) -> None:
    """Еженедельные начисления (Пн 00:xx UTC): топ-1 ачивки, Дракон/Лиса, VIP-пробники.
    Sentinel-строка в player_buffs гарантирует один запуск за понедельник."""
    _now = datetime.now(timezone.utc)
    if not (_now.weekday() == 0 and _now.hour == 0):
        return
    _monday_date = (_now - timedelta(days=_now.weekday())).strftime("%Y-%m-%d")
    async with db.execute(
        "SELECT 1 FROM player_buffs WHERE user_id = 0 AND buff_type = ? LIMIT 1",
        (f"weekly_top1_done_{_monday_date}",),
    ) as _chk:
        if await _chk.fetchone():
            return  # Already processed this Monday
    # Mark as done first to prevent duplicates
    await db.execute(
        "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
        "VALUES (0, ?, 1, NOW() + INTERVAL '8 days') "
        "ON CONFLICT (user_id, buff_type) DO NOTHING",
        (f"weekly_top1_done_{_monday_date}",),
    )
    await db.commit()

    await _grant_weekly_top1_achievements(db)
    try:
        await _grant_weekly_dragon_bank(db)
    except Exception as _de:
        logger.warning(f"dragon weekly grant error: {_de}")
    try:
        await _grant_weekly_fox_diamond(db)
    except Exception as _fe:
        logger.warning(f"fox weekly diamond error: {_fe}")
    try:
        await _grant_weekly_vip_items(bot, db)
    except Exception as _ve:
        logger.warning(f"VIP weekly probniki error: {_ve}")


async def duel_and_auction_task(bot: Bot):
    """Минутный тик «всякой всячины»: истёкшие дуэли и лоты, дайджест аукциона,
    кэш сезонов БП, напоминания (VIP/БП) и еженедельные начисления по понедельникам.
    Каждый шаг изолирован своим try — сбой одного не рушит остальные."""
    logger.info("Фоновая задача дуэлей/аукциона запущена.")
    while True:
        await asyncio.sleep(60)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)

                await _expire_timed_out_duels(bot, db)

                # Дайджест новых лотов (накопленных за последнюю минуту)
                try:
                    await flush_pending_announcements(bot, db)
                except Exception as e:
                    logger.error(f"Auction digest flush error: {e}")

                await _resolve_expired_auction_lots(bot, db)

                # БЛОК 36.4: авто-закрытие просроченных клановых рейдов (48ч, босс жив) —
                # раньше висели 'active' навсегда и блокировали запуск нового рейда.
                try:
                    from infrastructure.repositories import raids as _raids_repo
                    _n_exp = await _raids_repo.close_expired(db)
                    if _n_exp:
                        logger.info(f"Клановые рейды: закрыто просроченных — {_n_exp}")
                except Exception as _re:
                    logger.warning(f"raid expiry error: {_re}")

                # Battle Pass: подхват сезонов, созданных через Консоль на сайте
                try:
                    await refresh_bp_seasons(db)
                except Exception as _se:
                    logger.warning(f"BP seasons cache refresh error: {_se}")

                try:
                    await _send_vip_expiry_reminders(bot, db)
                except Exception as _ee:
                    logger.warning(f"VIP expiry reminder error: {_ee}")

                try:
                    await _send_bp_season_end_reminders(bot, db)
                except Exception as _bpe:
                    logger.warning(f"Battle Pass season-end reminder error: {_bpe}")

                try:
                    await _run_weekly_monday_jobs(bot, db)
                except Exception as _e:
                    logger.warning(f"weekly_top1 tracking error: {_e}")

                # R5/R6: «перебит, финал через ~10 мин» → в очередь Умного Пульса
                try:
                    await _enqueue_auction_final_pushes(db)
                except Exception as _pe:
                    logger.warning(f"auction final push enqueue error: {_pe}")

                # R3: войны за узлы — автозакрытие просроченных + суточный доход
                try:
                    await _war_daily_jobs(db)
                except Exception as _we:
                    logger.warning(f"war daily jobs error: {_we}")

        except Exception as e:
            logger.error(f"Ошибка в задаче дуэлей/аукциона: {e}")
            await asyncio.sleep(30)


async def _war_daily_jobs(db) -> None:
    """R3: закрыть войны с истёкшим 24ч-окном (стена выстояла — взнос сгорел)
    и начислить суточный доход узлов в 🪙-казну кланов-владельцев (заодно
    закрывает старую дыру «нет автозакрытия по таймеру» из БЛОК 36)."""
    from infrastructure.repositories import clans2 as c2_repo
    from core.constants import WAR_NODE_INCOME_MORA_PER_DAY
    for war in await c2_repo.expired_wars(db):
        await c2_repo.finish_war(db, war["id"], "lost")
        await c2_repo.abyss_log(db, war["attacker_clan_id"], 0,
                                "🕊 Война проиграна — стена выстояла 24ч, взнос сгорел.")
    for node in await c2_repo.nodes_due_income(db):
        income = WAR_NODE_INCOME_MORA_PER_DAY
        # Казна L: +5%/ур к доходу узлов
        t_lvl = await c2_repo.building_level(db, node["owner_clan_id"], "treasury")
        income = income * (1.0 + 0.05 * t_lvl)
        await c2_repo.add_treasury(db, node["owner_clan_id"], mora=income)
        await c2_repo.mark_income(db, node["id"])
    await db.commit()


async def _enqueue_auction_final_pushes(db) -> None:
    """Лоты, входящие в окно «~10 минут до конца»: всем перебитым ставившим —
    событие bid_outbid_final в push_queue. Окно (9;10] минут при минутном тике
    ловится ровно один раз на лот; дубли дополнительно гасятся ритмом Пульса."""
    async with db.execute(
        "SELECT l.id, l.item_name FROM auction_lots l "
        "WHERE l.status = 'active' "
        "AND l.ends_at > NOW() + INTERVAL '9 minutes' "
        "AND l.ends_at <= NOW() + INTERVAL '10 minutes'",
    ) as c:
        lots = [dict(r) for r in await c.fetchall()]
    for lot in lots:
        title = (lot["item_name"] or "Лот").split("||")[0]
        # Перебитые = ставили на лот, но их ставка уже не активна и не топ
        async with db.execute(
            "SELECT DISTINCT b.bidder_id FROM auction_bids b "
            "WHERE b.lot_id = ? AND b.is_active = 0 "
            "AND b.bidder_id NOT IN ("
            "  SELECT bidder_id FROM auction_bids WHERE lot_id = ? AND is_active = 1"
            ")",
            (lot["id"], lot["id"]),
        ) as c:
            outbid = [r[0] for r in await c.fetchall()]
        for uid in outbid:
            await push_repo.enqueue(
                db, uid, "bid_outbid_final",
                PUSH_PRIORITIES.get("bid_outbid_final", 100),
                {"lot_id": lot["id"], "title": title},
            )


def _push_text_and_link(category: str, payload: dict) -> tuple[str, str]:
    """Текст DM + секция мини-аппа (startapp=...) для категории события Пульса."""
    if category == "bid_outbid_final":
        title = payload.get("title", "лот")
        return (
            f"🔨 <b>Твоя ставка перебита!</b>\n"
            f"Финал лота «{title}» — примерно через 10 минут. Успей вернуть себе лот!",
            "auction",
        )
    return "🔔 У тебя есть непрочитанные игровые события.", ""


async def smart_pulse_task(bot: Bot):
    """R6 «Умный Пульс»: каждые 5 минут выбирает игроков с несент-событиями,
    у которых прошло ≥2ч с последнего DM, и шлёт ОДНО самое приоритетное
    (с учётом персональных настроек уведомлений). Остальная пачка «сгорает» —
    события видны на сайте при заходе."""
    logger.info("Фоновая задача «Умный Пульс» запущена.")
    bot_username = os.getenv("BOT_USERNAME", "")
    while True:
        await asyncio.sleep(300)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)
                user_ids = await push_repo.users_ready_for_push(db, PUSH_MIN_INTERVAL_SEC)
                for uid in user_ids:
                    try:
                        pending = await push_repo.pending_for_user(db, uid)
                        chosen = None
                        for ev in pending:
                            # Протухшее событие (игрок был в 2ч-кулдауне, лот уже
                            # закрыт) — пропускаем, оно пометится sent ниже.
                            ttl = PUSH_EVENT_TTL_SEC.get(ev["category"], 0)
                            if ttl and int(ev.get("age_sec") or 0) > ttl:
                                continue
                            if await _notif_enabled(db, uid, ev["category"]):
                                chosen = ev
                                break
                        # Всю пачку помечаем sent в любом случае (выключенные
                        # категории не должны копиться вечно)
                        await push_repo.mark_all_sent(db, uid)
                        if not chosen:
                            continue
                        text, section = _push_text_and_link(chosen["category"], chosen["payload"])
                        kb = None
                        if section and bot_username:
                            from aiogram.types import (
                                InlineKeyboardMarkup, InlineKeyboardButton,
                            )
                            kb = InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(
                                    text="🚀 Открыть",
                                    url=f"https://t.me/{bot_username}?startapp={section}",
                                )
                            ]])
                        await bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
                    except Exception as _ue:
                        logger.debug(f"pulse: пропуск {uid}: {_ue}")  # ЛС закрыта/бот заблокирован
        except Exception as e:
            logger.error(f"Ошибка «Умного Пульса»: {e}")
            await asyncio.sleep(60)


async def chest_spawn_task(bot: Bot):
    """Every 5 minutes: spawn chests in qualifying chats + expire old ones."""
    logger.info("Фоновая задача сундуков запущена.")
    while True:
        await asyncio.sleep(300)
        try:

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


async def anniversary_task(bot: Bot):
    """Раз в час: празднуем годовщины браков (Implementation Block 14).
    Веха (100 дней / каждый год) даётся ОБОИМ супругам один раз + анонс в чате."""
    from services.marriage import anniversary_due, anniversary_reward
    logger.info("Фоновая задача годовщин брака запущена.")
    while True:
        await asyncio.sleep(3600)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)
                async with db.execute(
                    "SELECT id, user1_id, user1_name, user2_id, user2_name, chat_id, "
                    "(NOW()::date - marriage_date::date) AS days, "
                    "COALESCE(last_anniversary, 0) AS last_anni FROM marriages"
                ) as c:
                    rows = [dict(r) for r in await c.fetchall()]

                for m in rows:
                    days = int(m["days"] or 0)
                    milestone = anniversary_due(days, int(m["last_anni"] or 0))
                    if milestone is None:
                        continue
                    mora, dia, label = anniversary_reward(milestone)
                    for uid in (m["user1_id"], m["user2_id"]):
                        if uid:
                            await _ab(db, uid, mora=mora, diamonds=dia, commit=False,
                                      source="marriage_anniversary", note=f"{milestone}d")
                    await db.execute(
                        "UPDATE marriages SET last_anniversary = ? WHERE id = ?",
                        (milestone, m["id"]),
                    )
                    await db.commit()

                    if m["chat_id"]:
                        try:
                            u1 = f'<a href="tg://user?id={m["user1_id"]}">{m["user1_name"] or "?"}</a>'
                            u2 = f'<a href="tg://user?id={m["user2_id"]}">{m["user2_name"] or "?"}</a>'
                            await bot.send_message(
                                m["chat_id"],
                                f"💞 <b>ГОДОВЩИНА!</b>\n\n{u1} ❤️ {u2} — <b>{label}</b>!\n"
                                f"🎁 Каждому: +{mora} 🪙 +{dia} 💎\n\n<i>Совет да любовь! 🥂</i>",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Ошибка в задаче годовщин: {e}")
            await asyncio.sleep(30)


async def shadow_merchant_task(bot: Bot):
    """БЛОК 13.X/24.A: ивент «Теневой Торговец» — реанимация мёртвого кода.

    Каждые 10 минут: (1) закрывает истёкшие пророчества (анонс слова в чат);
    (2) если нигде нет активного ивента и с последнего прошло
    ≥ DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS — с шансом 25%/тик публикует
    новое пророчество в случайный активный чат (те же критерии, что у сундуков).
    Ответы игроков принимает «бот слово, X» (bot/handlers/dark_mora.py)."""
    from core.constants import (
        DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS as _SM_CD_DAYS,
        DARK_MORA_SHADOW_MERCHANT_ACTIVE_MINUTES as _SM_MINUTES,
        DARK_MORA_SHADOW_MERCHANT_WINNERS as _SM_WINNERS,
    )
    from infrastructure.repositories import shadow_merchant as _sm_repo
    from services import shadow_merchant as _sm

    logger.info("Фоновая задача «Теневой Торговец» запущена.")
    while True:
        await asyncio.sleep(600)
        try:
            async with get_pool().acquire() as _conn:
                db = PGAdapter(_conn)

                # 1) закрыть истёкшие
                for ev in await _sm_repo.get_expired_active(db):
                    try:
                        n_win = await _sm_repo.winners_count(db, ev["id"])
                        await _sm_repo.close_event(db, ev["id"], "expired")
                        await db.commit()
                        await bot.send_message(
                            ev["chat_id"], _sm.expired_text(ev["keyword"], n_win),
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning(f"shadow merchant expire {ev['id']}: {e}")

                # 2) спавн нового
                if await _sm_repo.any_active(db):
                    continue
                last = await _sm_repo.last_posted_at(db)
                if last and (datetime.now(timezone.utc) - last) < timedelta(days=_SM_CD_DAYS):
                    continue
                if _random.random() > 0.25:   # размазываем момент появления
                    continue
                qualifying = await get_qualifying_chats(db, CHEST_MIN_ACTIVE_USERS_24H)
                if not qualifying:
                    continue
                chat_id = _random.choice(qualifying)
                keyword = _sm.pick_keyword()
                event_id = await _sm_repo.create_event(db, chat_id, keyword, _SM_MINUTES)
                await db.commit()
                masked = _sm.mask_keyword(keyword, seed=str(event_id))
                await bot.send_message(
                    chat_id, _sm.prophecy_text(masked, _SM_MINUTES, _SM_WINNERS),
                    parse_mode="HTML",
                )
                logger.info(f"Теневой Торговец: пророчество в чате {chat_id} (event {event_id})")
        except Exception as e:
            logger.error(f"Ошибка задачи Теневого Торговца: {e}")
            await asyncio.sleep(60)
