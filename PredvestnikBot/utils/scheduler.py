"""
Фоновый планировщик.
Запускается один раз при старте бота через asyncio.create_task(run_scheduler(bot)).
Задачи:
  • авто-варн за неактив (проверка каждый час)
  • напоминание о чистке за 2 дня (проверка каждый час)
  • юбилей брака +15 Моры каждые 7 дней (проверка каждый час)
  • розыгрыш лотереи по воскресеньям (проверка каждый час)
  • налоговая инспекция — случайный ивент каждые 4-8 часов
  • уведомления о завершённых экспедициях
"""

import asyncio
import html
import logging
import random
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# In-memory guards REMOVED — now using persistent DB to survive restarts


async def run_scheduler(bot) -> None:
    """Точка входа — запускается как фоновая задача в main.py."""
    await asyncio.sleep(60)  # дать боту полностью инициализироваться
    while True:
        try:
            await _task_inactivity_warns(bot)
        except Exception as exc:
            log.error("Scheduler [inactivity_warn] error: %s", exc, exc_info=True)
        try:
            await _task_cleanup_reminders(bot)
        except Exception as exc:
            log.error("Scheduler [cleanup_reminder] error: %s", exc, exc_info=True)
        try:
            await _task_marriage_anniversary(bot)
        except Exception as exc:
            log.error("Scheduler [anniversary] error: %s", exc, exc_info=True)
        try:
            await _task_lottery_draw(bot)
        except Exception as exc:
            log.error("Scheduler [lottery] error: %s", exc, exc_info=True)
        try:
            await _task_weekly_singles_bonus(bot)
        except Exception as exc:
            log.error("Scheduler [singles_bonus] error: %s", exc, exc_info=True)
        try:
            await _task_chest_event(bot)
        except Exception as exc:
            log.error("Scheduler [chest_event] error: %s", exc, exc_info=True)
        try:
            await _task_expedition_notifications(bot)
        except Exception as exc:
            log.error("Scheduler [expeditions] error: %s", exc, exc_info=True)
        try:
            await _task_bond_price_update(bot)
        except Exception as exc:
            log.error("Scheduler [bond_prices] error: %s", exc, exc_info=True)
        try:
            await _task_diligence_event(bot)
        except Exception as exc:
            log.error("Scheduler [diligence_event] error: %s", exc, exc_info=True)
        try:
            await _task_treasury_dividends(bot)
        except Exception as exc:
            log.error("Scheduler [treasury_dividends] error: %s", exc, exc_info=True)
        try:
            await _task_dev_event_queue(bot)
        except Exception as exc:
            log.error("Scheduler [dev_event_queue] error: %s", exc, exc_info=True)
        await asyncio.sleep(3600)  # следующий прогон через час


# ─── Авто-варн за неактив ─────────────────────────────────────────────────────

async def _task_inactivity_warns(bot) -> None:
    from database.db import (
        get_chats_with_inactivity_warn,
        get_inactive_users_for_warn,
        add_warn_in_chat,
        set_inactivity_warned,
        is_on_rest,
    )
    from utils.helpers import user_mention
    from config import MAX_WARNS

    chats = await get_chats_with_inactivity_warn()
    if not chats:
        return

    now = datetime.utcnow()
    for chat_row in chats:
        chat_id = chat_row["chat_id"]
        days     = chat_row.get("inactivity_warn_days") or 5
        cutoff   = (now - timedelta(days=days)).isoformat()

        users = await get_inactive_users_for_warn(chat_id, cutoff)
        if not users:
            continue

        warned_lines: list[str] = []
        for u in users:
            uid = u["user_id"]
            # Дополнительная проверка отдыха (is_on_rest делает отдельный запрос)
            if await is_on_rest(uid, chat_id):
                continue

            warns = await add_warn_in_chat(uid, chat_id)
            await set_inactivity_warned(uid, chat_id, now.isoformat())

            name = html.escape(u.get("full_name") or str(uid))
            warned_lines.append(
                f"  • {user_mention(uid, name)} — варн {warns}/{MAX_WARNS}"
            )

        if warned_lines:
            text = (
                f"⏰ <b>Авто-варн за неактивность ({days} дн.)</b>\n\n"
                + "\n".join(warned_lines)
            )
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML",
                                       disable_notification=True)
            except Exception as exc:
                log.warning("Cannot send inactivity warn to %s: %s", chat_id, exc)


# ─── Напоминание о запланированной чистке ─────────────────────────────────────

async def _task_cleanup_reminders(bot) -> None:
    from database.db import get_chats_with_scheduled_cleanup, set_cleanup_reminder_sent

    now = datetime.utcnow()
    chats = await get_chats_with_scheduled_cleanup()
    for row in chats:
        chat_id     = row["chat_id"]
        scheduled   = row.get("next_cleanup_at")
        already_sent = row.get("cleanup_reminder_sent", 0)

        if not scheduled:
            continue

        try:
            dt = datetime.fromisoformat(scheduled)
        except (ValueError, TypeError):
            continue

        delta = dt - now
        # Очищаем устаревшую дату (чистка уже прошла > 1 дня назад)
        if delta.total_seconds() < -86400:
            from database.db import set_chat_setting
            await set_chat_setting(chat_id, "next_cleanup_at", None)
            await set_cleanup_reminder_sent(chat_id, 0)
            continue

        # Напоминание: от 48ч до 0ч до чистки, один раз
        if 0 <= delta.total_seconds() <= 172800 and not already_sent:
            from zoneinfo import ZoneInfo
            from datetime import timezone as _tz
            dt_zurich = dt.replace(tzinfo=_tz.utc).astimezone(ZoneInfo("Europe/Zurich"))
            date_str = dt_zurich.strftime("%d.%m.%Y %H:%M (Цюрих)")
            days_left = int(delta.total_seconds() // 86400)
            hours_left = int((delta.total_seconds() % 86400) // 3600)
            time_label = f"{days_left}д {hours_left}ч" if days_left else f"{hours_left}ч"
            text = (
                f"🔔 <b>Напоминание о чистке!</b>\n\n"
                f"📅 Дата чистки: <b>{date_str}</b>\n"
                f"⏳ Осталось: <b>{time_label}</b>\n\n"
                f"Подготовьтесь — участники с низкой активностью будут отмечены.\n"
                f"<code>бот чистка</code> — запустить досрочно\n"
                f"<code>бот чистка дата</code> — показать/изменить дату"
            )
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML")
                await set_cleanup_reminder_sent(chat_id, 1)
            except Exception as exc:
                log.warning("Cannot send cleanup reminder to %s: %s", chat_id, exc)


# ─── Юбилей брака +15 Моры каждые 7 дней ─────────────────────────────────────

async def _task_marriage_anniversary(bot) -> None:
    from config import ANNIVERSARY_MORA
    from database.db import (
        add_mora, get_all_marriages_for_anniversary, get_user,
        is_anniversary_awarded, mark_anniversary_awarded,
    )
    from utils.helpers import user_mention, bot_today

    today_str = bot_today()

    marriages = await get_all_marriages_for_anniversary()
    for row in marriages:
        uid        = row["user_id"]
        partner_id = row["partner_id"]
        chat_id    = row["chat_id"]
        married_at = row.get("married_at", "")

        if not married_at:
            continue

        try:
            dt = datetime.fromisoformat(married_at)
        except (ValueError, TypeError):
            continue

        days = (datetime.utcnow() - dt).days
        # Award every 7 days (after at least 7 days), once per calendar day
        if days < 7 or days % 7 != 0:
            continue

        # Persistent DB guard — survives restarts
        if await is_anniversary_awarded(uid, chat_id, today_str):
            continue
        await mark_anniversary_awarded(uid, chat_id, today_str)

        await add_mora(uid, chat_id, ANNIVERSARY_MORA)
        await add_mora(partner_id, chat_id, ANNIVERSARY_MORA)

        user = await get_user(uid)
        partner = await get_user(partner_id)
        u_name = html.escape(user["full_name"]) if user else str(uid)
        p_name = html.escape(partner["full_name"]) if partner else str(partner_id)

        weeks = days // 7
        try:
            await bot.send_message(
                chat_id,
                f"💍 <b>Юбилей!</b> {user_mention(uid, u_name)} и {user_mention(partner_id, p_name)} "
                f"вместе уже <b>{weeks} нед.</b> ({days} дн.)\n"
                f"Каждый получает <b>+{ANNIVERSARY_MORA} 🪙</b> в подарок! 🎁",
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("Cannot send anniversary to %s: %s", chat_id, exc)


# ─── Еженедельный розыгрыш лотереи (по воскресеньям) ─────────────────────────

async def _task_lottery_draw(bot) -> None:
    from config import LOTTERY_WIN_CHANCE, LOTTERY_WIN_MIN, LOTTERY_WIN_MAX
    from database.db import (
        add_mora, get_all_lottery_chats_week, get_all_lottery_participants, get_user,
        is_lottery_drawn, mark_lottery_drawn,
    )
    from utils.helpers import user_mention

    now = datetime.utcnow()
    # Only draw on Sundays
    if now.weekday() != 6:
        return

    year, week, _ = now.isocalendar()
    week_key = f"{year}-W{week:02d}"

    # Persistent DB guard — survives restarts
    if await is_lottery_drawn(week_key):
        return
    await mark_lottery_drawn(week_key)

    WIN_CHANCE = LOTTERY_WIN_CHANCE
    WIN_MIN    = LOTTERY_WIN_MIN
    WIN_MAX    = LOTTERY_WIN_MAX

    chats = await get_all_lottery_chats_week(week_key)
    for chat_id in chats:
        participants = await get_all_lottery_participants(chat_id, week_key)

        if not participants:
            continue

        winner_lines: list[str] = []
        for p in participants:
            uid     = p["user_id"]
            tickets = p["tickets"]
            # Each ticket is an independent draw
            winnings = sum(
                random.randint(WIN_MIN, WIN_MAX)
                for _ in range(tickets)
                if random.random() < WIN_CHANCE
            )
            if winnings > 0:
                await add_mora(uid, chat_id, winnings)
                user = await get_user(uid)
                name = html.escape(user["full_name"]) if user else str(uid)
                winner_lines.append(
                    f"  🏆 {user_mention(uid, name)} — <b>+{winnings} 🪙</b> ({tickets} билет(ов))"
                )

        if winner_lines:
            text = (
                f"🎟 <b>Итоги лотереи</b> (неделя {week_key})\n\n"
                + "\n".join(winner_lines)
                + "\n\n<i>Купить билет: <code>бот купить лотерею</code></i>"
            )
        else:
            text = (
                f"🎟 <b>Итоги лотереи</b> (неделя {week_key})\n\n"
                f"На этой неделе победителей нет. Удачи в следующий раз!\n"
                f"<i>Купить билет: <code>бот купить лотерею</code></i>"
            )

        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as exc:
            log.warning("Cannot send lottery results to %s: %s", chat_id, exc)


# ─── Еженедельный бонус для одиночек ──────────────────────────────────────────

async def _task_weekly_singles_bonus(bot) -> None:
    from config import SINGLES_WEEKLY_BONUS
    from database.db import (
        add_mora, get_all_singles_for_weekly_bonus, get_user,
        is_singles_bonus_awarded, mark_singles_bonus_awarded,
    )
    from utils.helpers import user_mention, bot_today

    now = datetime.utcnow()
    # Only award on Sundays
    if now.weekday() != 6:
        return

    today_str = bot_today()
    year, week, _ = now.isocalendar()
    week_key = f"{year}-W{week:02d}"

    # Persistent DB guard — survives restarts
    if await is_singles_bonus_awarded(week_key):
        return
    await mark_singles_bonus_awarded(week_key)

    singles = await get_all_singles_for_weekly_bonus()
    for single_user in singles:
        uid = single_user["user_id"] 
        chat_id = single_user["chat_id"]
        
        # Award the bonus
        await add_mora(uid, chat_id, SINGLES_WEEKLY_BONUS)
        
        # Try to send notification
        try:
            user = await get_user(uid)
            name = html.escape(user["full_name"]) if user else str(uid)
            text = (
                f"💎 <b>Еженедельный бонус одиночки!</b>\n\n"
                f"🪙 <b>+{SINGLES_WEEKLY_BONUS} Мора</b> за активность без пары\n"
                f"<i>Каждое воскресенье — бонус за независимость! 🕊</i>"
            )
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as exc:
            log.warning("Cannot send singles bonus to %s/%s: %s", chat_id, uid, exc)


# ─── Богатый сундук (раз в 4-8 часов) ──────────────────────────────────────

_next_chest_hour: int | None = None


async def _task_chest_event(bot) -> None:
    global _next_chest_hour
    from config import CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX
    if _next_chest_hour is None:
        _next_chest_hour = random.randint(CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX)

    _next_chest_hour -= 1
    if _next_chest_hour > 0:
        return
    _next_chest_hour = random.randint(CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX)

    from handlers.tax_event import run_chest_events_cycle
    await run_chest_events_cycle(bot)


# ─── Уведомления о завершённых экспедициях ─────────────────────────────────────

async def _task_expedition_notifications(bot) -> None:
    from database.db import add_mora, finish_expedition, get_all_finished_expeditions, get_pet, get_marriage
    from config import EXPEDITION_OPTIONS
    _PET_EMOJI = {"cat": "🐱", "dog": "🐶"}

    # Build a lookup: duration_h -> expedition label
    _label_by_h = {opt["hours"]: opt["label"] for opt in EXPEDITION_OPTIONS.values()}

    # Flavor text: what the pet found, by reward tier
    def _loot_flavor(reward: int) -> str:
        if reward <= 25:
            return "немного монет и старые тряпки 👜"
        elif reward <= 50:
            return "мешочек с монетами и редкие травы 🌿"
        elif reward <= 75:
            return "ценные артефакты и полные карманы моры 💎"
        else:
            return "сокровища из заброшенных руин! 🏺✨"

    finished = await get_all_finished_expeditions()
    for exp in finished:
        uid = exp["user_id"]
        chat_id = exp["chat_id"]
        reward = random.randint(exp["reward_min"], exp["reward_max"])
        try:
            # Начисляем мору владельцу питомца
            await add_mora(uid, chat_id, reward)
            await finish_expedition(uid, chat_id)

            pet = await get_pet(uid, chat_id)
            pet_emoji = _PET_EMOJI.get(pet["pet_type"], "🐾") if pet else "🐾"
            pet_name  = pet["name"] if (pet and pet.get("name")) else "Питомец"
            exp_label = _label_by_h.get(exp["duration_h"], f"{exp['duration_h']}ч")
            loot      = _loot_flavor(reward)

            # Проверяем брак и начисляем мору партнёру тоже
            marriage = await get_marriage(uid, chat_id)
            partner_tag = ""
            if marriage:
                partner_id = marriage["partner_id"]
                # Начисляем мору партнёру
                await add_mora(partner_id, chat_id, reward)
                try:
                    partner_member = await bot.get_chat_member(chat_id, partner_id)
                    if partner_member.user.username:
                        partner_tag = f"\n👋 @{partner_member.user.username} тоже получил <b>{reward} 🪙</b>"
                    else:
                        partner_tag = f"\n👋 [Партнёр](tg://user?id={partner_id}) тоже получил <b>{reward} 🪙</b>"
                except Exception:
                    # Fallback если не можем получить данные партнёра
                    partner_tag = f"\n👋 [Партнёр](tg://user?id={partner_id}) тоже получил <b>{reward} 🪙</b>"

            await bot.send_message(
                chat_id,
                f"🏕 <b>Экспедиция завершена!</b>\n\n"
                f"{pet_emoji} <b>{pet_name}</b> вернулся из похода <b>{exp_label}</b>\n"
                f"и принёс {loot}\n\n"
                f"💰 <b>+{reward} 🪙</b>{partner_tag}",
                parse_mode="HTML",
            )
        except Exception as exc:
            log.warning("Expedition notify %s/%s: %s", chat_id, uid, exc)


# ─── Обновление цен облигаций каждые 6 часов ─────────────────────────────────

_bond_price_last_update: "datetime | None" = None
_BOND_UPDATE_INTERVAL_HOURS = 6


async def _task_bond_price_update(bot) -> None:
    """Обновляет цены облигаций для всех чатов раз в 6 часов.
    Использует внутренний таймер вместо жёсткой привязки к UTC-часу,
    чтобы не пропускать обновления после перезапуска бота."""
    global _bond_price_last_update
    now = datetime.utcnow()

    # Пропускаем, если прошло меньше 6 часов с последнего обновления
    if _bond_price_last_update is not None:
        elapsed = (now - _bond_price_last_update).total_seconds()
        if elapsed < _BOND_UPDATE_INTERVAL_HOURS * 3600:
            return

    from database.db import update_bond_prices
    import aiosqlite
    from database.db import DATABASE_PATH

    # Получаем все активные chat_id из chat_settings
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT chat_id FROM chat_settings") as c:
            rows = await c.fetchall()

    chat_ids = [r["chat_id"] for r in rows]
    _bond_price_last_update = now  # обновляем метку времени до цикла, чтобы не было двойного запуска

    for chat_id in chat_ids:
        try:
            await update_bond_prices(chat_id)
        except Exception as exc:
            log.warning("Bond price update for chat %s: %s", chat_id, exc)

    if chat_ids:
        log.info("Bond prices updated for %d chats at %s UTC", len(chat_ids), now.strftime("%H:%M"))
    else:
        log.info("Bond price update: no chats in chat_settings yet")


# ─── Пятница 20:00 Zurich — Дилижанс ─────────────────────────────────────────

_diligence_last_sent_date: str | None = None


async def _task_diligence_event(bot) -> None:
    """Запускает Дилижанс по пятницам в 20:00 (Europe/Zurich)."""
    global _diligence_last_sent_date
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Zurich")
    except Exception:
        return
    now = datetime.now(tz)
    if now.weekday() != 4:  # 4 = пятница
        return
    if now.hour != 20:
        return
    today_str = now.strftime("%Y-%m-%d")
    if _diligence_last_sent_date == today_str:
        return
    _diligence_last_sent_date = today_str

    from database.db import get_all_active_chats
    from handlers.diligence import _launch_diligence
    chat_ids = await get_all_active_chats()
    for cid in chat_ids:
        try:
            await _launch_diligence(bot, cid)
        except Exception as exc:
            log.warning("Diligence launch in %s: %s", cid, exc)
    log.info("Diligence event triggered for %d chats", len(chat_ids))


# ─── Суббота 18:00 Zurich — Дивиденды из казны ───────────────────────────────

_dividend_last_sent_date: str | None = None


async def _task_treasury_dividends(bot) -> None:
    """Раздаёт дивиденды из казны каждую субботу в 18:00 (Europe/Zurich).
    40% — VIP-участникам, 60% — топ-10 активных за неделю.
    """
    global _dividend_last_sent_date
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Zurich")
    except Exception:
        return
    now = datetime.now(tz)
    if now.weekday() != 5:  # 5 = суббота
        return
    if now.hour != 18:
        return
    today_str = now.strftime("%Y-%m-%d")
    if _dividend_last_sent_date == today_str:
        return
    _dividend_last_sent_date = today_str

    from database.db import (
        add_mora,
        get_all_active_chats,
        get_treasury,
        get_vip_users,
        get_weekly_top_users,
        reset_treasury,
    )
    chat_ids = await get_all_active_chats()
    for cid in chat_ids:
        try:
            treasury = await get_treasury(cid)
            if treasury < 10:
                continue

            vip_pool   = int(treasury * 0.40)
            top_pool   = treasury - vip_pool
            vip_users  = await get_vip_users(cid)
            top_users  = await get_weekly_top_users(cid, limit=10)

            lines = [f"📊 <b>Дивиденды казны!</b>\n\n💰 Казна: <b>{treasury} 🪙</b>"]

            if vip_users:
                per_vip = max(1, vip_pool // len(vip_users))
                for uid in vip_users:
                    await add_mora(uid, cid, per_vip)
                lines.append(f"\n⭐ VIP ({len(vip_users)} чел.): по <b>{per_vip} 🪙</b> каждому")
            else:
                top_pool += vip_pool  # Переносим VIP-долю в топ если VIP нет

            if top_users:
                per_top = max(1, top_pool // len(top_users))
                for uid in top_users:
                    await add_mora(uid, cid, per_top)
                lines.append(f"🏆 Топ-10 актива: по <b>{per_top} 🪙</b> каждому")

            await reset_treasury(cid)
            lines.append("\n🏦 Казна обнулена до следующей субботы.")
            await bot.send_message(cid, "\n".join(lines), parse_mode="HTML")
        except Exception as exc:
            log.warning("Treasury dividends in %s: %s", cid, exc)


# ─── Dev event queue (Mini App → bot) ────────────────────────────────────────

async def _task_dev_event_queue(bot) -> None:
    """Process pending dev_event_queue rows left by the Mini App's /api/dev/trigger_event."""
    import aiosqlite
    from config import DATABASE_PATH, DEVELOPER_ID
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            # Ensure table exists (may not yet if Django hasn't created it)
            await db.execute(
                "CREATE TABLE IF NOT EXISTS dev_event_queue ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "chat_id INTEGER NOT NULL, event_type TEXT NOT NULL, "
                "requested_by INTEGER NOT NULL, created_at TEXT NOT NULL, processed INTEGER DEFAULT 0)"
            )
            async with db.execute(
                "SELECT id, chat_id, event_type FROM dev_event_queue WHERE processed=0 ORDER BY id LIMIT 20"
            ) as cur:
                rows = await cur.fetchall()
            for row in rows:
                ev_id, cid, etype = row["id"], row["chat_id"], row["event_type"].lower().strip()
                try:
                    if etype in ("chest", "сундук"):
                        from handlers.tax_event import launch_chest_event
                        await launch_chest_event(bot, cid)
                    elif etype in ("дилижанс", "diligence"):
                        from handlers.diligence import _launch_diligence
                        await _launch_diligence(bot, cid)
                    else:
                        log.info("Dev event queue: unknown type %r for chat %s", etype, cid)
                except Exception as exc:
                    log.warning("Dev event queue item %s (%s / %s) failed: %s", ev_id, cid, etype, exc)
                # Mark processed regardless (prevent retry storms)
                await db.execute("UPDATE dev_event_queue SET processed=1 WHERE id=?", (ev_id,))
            await db.commit()
    except Exception as exc:
        log.warning("_task_dev_event_queue: %s", exc)


