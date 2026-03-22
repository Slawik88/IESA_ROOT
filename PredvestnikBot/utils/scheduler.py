"""
Фоновый планировщик.
Запускается один раз при старте бота через asyncio.create_task(run_scheduler(bot)).
Задачи:
  • авто-варн за неактив (проверка каждый час)
  • напоминание о чистке за 2 дня (проверка каждый час)
  • юбилей брака +15 Моры каждые 7 дней (проверка каждый час)
  • розыгрыш лотереи по воскресеньям (проверка каждый час)
"""

import asyncio
import html
import logging
import random
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# In-memory guards to avoid double-awarding per hour run
_anniversary_awarded: set[tuple[int, int, str]] = set()  # (user_id, chat_id, date_str)
_lottery_drawn_weeks: set[str] = set()                    # week keys already drawn


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
    from database.db import add_mora, get_all_marriages_for_anniversary, get_user
    from utils.helpers import user_mention

    today_str = datetime.utcnow().date().isoformat()

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

        guard_key = (uid, chat_id, today_str)
        if guard_key in _anniversary_awarded:
            continue
        _anniversary_awarded.add(guard_key)

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

    # Prune guard set to avoid unbounded growth
    if len(_anniversary_awarded) > 10000:
        _anniversary_awarded.clear()


# ─── Еженедельный розыгрыш лотереи (по воскресеньям) ─────────────────────────

async def _task_lottery_draw(bot) -> None:
    from config import LOTTERY_WIN_CHANCE, LOTTERY_WIN_MIN, LOTTERY_WIN_MAX
    from database.db import add_mora, get_all_lottery_chats_week, get_all_lottery_participants, get_user
    from utils.helpers import user_mention

    now = datetime.utcnow()
    # Only draw on Sundays
    if now.weekday() != 6:
        return

    year, week, _ = now.isocalendar()
    week_key = f"{year}-W{week:02d}"

    if week_key in _lottery_drawn_weeks:
        return
    _lottery_drawn_weeks.add(week_key)

    WIN_CHANCE = LOTTERY_WIN_CHANCE
    WIN_MIN    = LOTTERY_WIN_MIN
    WIN_MAX    = LOTTERY_WIN_MAX

    chats = await get_all_lottery_chats_week(week_key)
    for chat_row in chats:
        chat_id = chat_row["chat_id"]
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

