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
  • авто-удаление данных вышедших + неактивных 7+ дней (проверка каждый час)
"""

import asyncio
import html
import logging
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")

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
            await _task_cleanup_left_users()
        except Exception as exc:
            log.error("Scheduler [cleanup_left_users] error: %s", exc, exc_info=True)
        try:
            await _task_weekly_top_rewards(bot)
        except Exception as exc:
            log.error("Scheduler [weekly_top_rewards] error: %s", exc, exc_info=True)
        try:
            await _task_dev_event_queue(bot)
        except Exception as exc:
            log.error("Scheduler [dev_event_queue] error: %s", exc, exc_info=True)
        try:
            await _task_auction_finalize(bot)
        except Exception as exc:
            log.error("Scheduler [auction_finalize] error: %s", exc, exc_info=True)
        await asyncio.sleep(3600)  # следующий прогон через час


# ─── Авто-варн за неактив ─────────────────────────────────────────────────────

async def _task_inactivity_warns(bot) -> None:
    from database.db import (
        get_chats_with_inactivity_warn,
        get_inactive_users_for_warn,
        add_warn_in_chat,
        set_inactivity_warned,
        is_on_rest, is_isolated_chat,
    )
    from utils.helpers import user_mention
    from config import MAX_WARNS

    chats = await get_chats_with_inactivity_warn()
    if not chats:
        return

    now = datetime.now(timezone.utc)
    for chat_row in chats:
        chat_id = chat_row["chat_id"]
        if is_isolated_chat(chat_id):
            continue
        days     = chat_row.get("inactivity_warn_days") or 5
        cutoff   = now - timedelta(days=days)

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
            await set_inactivity_warned(uid, chat_id, now)

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
    from database.db import get_chats_with_scheduled_cleanup, set_cleanup_reminder_sent, get_shield_map, is_isolated_chat

    now = datetime.now(timezone.utc)
    chats = await get_chats_with_scheduled_cleanup()
    for row in chats:
        chat_id      = row["chat_id"]
        if is_isolated_chat(chat_id):
            continue
        scheduled    = row.get("next_cleanup_at")
        already_sent = row.get("cleanup_reminder_sent", 0)
        warn_hours   = int(row.get("cleanup_warn_hours") or 48)
        msg_norm     = int(row.get("cleanup_message_norm") or 70)

        if not scheduled:
            continue

        try:
            if isinstance(scheduled, str):
                dt = datetime.fromisoformat(scheduled)
            else:
                dt = scheduled  # asyncpg returns datetime object for TIMESTAMPTZ
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        delta = dt - now
        # Очищаем устаревшую дату (чистка уже прошла > 1 дня назад)
        if delta.total_seconds() < -86400:
            from database.db import set_chat_setting
            await set_chat_setting(chat_id, "next_cleanup_at", None)
            await set_cleanup_reminder_sent(chat_id, 0)
            continue

        # Напоминание: за warn_hours до чистки, один раз
        warn_seconds = warn_hours * 3600
        if 0 <= delta.total_seconds() <= warn_seconds and not already_sent:
            dt_zurich = dt.astimezone(ZURICH)
            date_str = dt_zurich.strftime("%d.%m.%Y %H:%M (Цюрих)")
            days_left = int(delta.total_seconds() // 86400)
            hours_left = int((delta.total_seconds() % 86400) // 3600)
            time_label = f"{days_left}д {hours_left}ч" if days_left else f"{hours_left}ч"

            # Проверяем щит новичка
            shield_map = await get_shield_map(chat_id)
            shield_note = ""
            if shield_map:
                shield_note = (
                    f"\n🛡 <b>Щит новичка</b>: {len(shield_map)} участн. защищены — "
                    f"они не попадут под чистку."
                )

            text = (
                f"🔔 <b>Напоминание о чистке!</b>\n\n"
                f"📅 Дата чистки: <b>{date_str}</b>\n"
                f"⏳ Осталось: <b>{time_label}</b>\n"
                f"📊 Норма активности: <b>{msg_norm} сообщений</b> за неделю"
                f"{shield_note}\n\n"
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
        is_isolated_chat,
    )
    from utils.helpers import user_mention, bot_today

    today_str = bot_today()

    marriages = await get_all_marriages_for_anniversary()
    for row in marriages:
        uid        = row["user_id"]
        partner_id = row["partner_id"]
        chat_id    = row["chat_id"]   # may be None if no common chat found
        married_at = row.get("married_at", "")

        if not married_at:
            continue
        if chat_id and is_isolated_chat(chat_id):
            continue

        if isinstance(married_at, str):
            try:
                dt = datetime.fromisoformat(married_at)
            except ValueError:
                continue
        else:
            dt = married_at  # asyncpg returns datetime from TIMESTAMPTZ
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        days = (datetime.now(timezone.utc) - dt).days
        # Award every 7 days (after at least 7 days), once per calendar day
        if days < 7 or days % 7 != 0:
            continue

        # Persistent DB guard — survives restarts (uid-based, chat-agnostic)
        if await is_anniversary_awarded(uid, 0, today_str):
            continue
        await mark_anniversary_awarded(uid, 0, today_str)

        # Mora is global (chat_id=0 bypasses isolation guard intentionally)
        await add_mora(uid, 0, ANNIVERSARY_MORA)
        await add_mora(partner_id, 0, ANNIVERSARY_MORA)

        user = await get_user(uid)
        partner = await get_user(partner_id)
        u_name = html.escape(user["full_name"]) if user else str(uid)
        p_name = html.escape(partner["full_name"]) if partner else str(partner_id)

        weeks = days // 7
        if chat_id:
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
        add_mora, add_to_treasury,
        get_all_lottery_chats_week, get_all_lottery_participants, get_user,
        is_lottery_drawn, mark_lottery_drawn, is_isolated_chat,
    )
    from utils.helpers import user_mention

    # Розыгрыш по воскресеньям по Цюрихскому времени
    now = datetime.now(ZURICH)
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
        if is_isolated_chat(chat_id):
            continue

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
                if winnings >= 50:
                    lottery_tax = max(1, int(winnings * 0.08))
                    net_winnings = winnings - lottery_tax
                    await add_to_treasury(chat_id, lottery_tax, "lottery", uid)
                else:
                    net_winnings = winnings
                    lottery_tax = 0
                await add_mora(uid, chat_id, net_winnings)
                user = await get_user(uid)
                name = html.escape(user["full_name"]) if user else str(uid)
                tax_note = f", налог −{lottery_tax}🏦" if lottery_tax else ""
                winner_lines.append(
                    f"  🏆 {user_mention(uid, name)} выиграл {net_winnings}🪙! ({tickets} билет(ов){tax_note})"
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
        is_isolated_chat,
    )
    from utils.helpers import user_mention, bot_today

    now = datetime.now(timezone.utc)
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
    # Group by chat — one notification per chat, not per user
    chats: dict[int, list[int]] = {}
    for su in singles:
        cid = su["chat_id"]
        if is_isolated_chat(cid):
            continue
        chats.setdefault(cid, []).append(su["user_id"])
    for chat_id, uids in chats.items():
        for uid in uids:
            await add_mora(uid, chat_id, SINGLES_WEEKLY_BONUS)
        try:
            count = len(uids)
            text = (
                f"💎 <b>Еженедельный бонус одиночки!</b>\n\n"
                f"🪙 <b>+{SINGLES_WEEKLY_BONUS} Мора</b> получили <b>{count}</b> одиноких Предвестников\n"
                f"<i>Каждое воскресенье — бонус за независимость! 🕊</i>"
            )
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as exc:
            log.warning("Cannot send singles bonus to %s: %s", chat_id, exc)


# ─── Богатый сундук (раз в 4-8 часов) ──────────────────────────────────────


async def _task_chest_event(bot) -> None:
    from config import CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX
    from database.db import get_scheduler_state, set_scheduler_state

    raw = await get_scheduler_state("chest_next_hour")
    next_hour = int(raw) if raw else random.randint(CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX)

    next_hour -= 1
    if next_hour > 0:
        await set_scheduler_state("chest_next_hour", str(next_hour))
        return
    next_hour = random.randint(CHEST_EVENT_INTERVAL_MIN, CHEST_EVENT_INTERVAL_MAX)
    await set_scheduler_state("chest_next_hour", str(next_hour))

    from handlers.tax_event import run_chest_events_cycle
    await run_chest_events_cycle(bot)


# ─── Уведомления о завершённых экспедициях ─────────────────────────────────────

async def _task_expedition_notifications(bot) -> None:
    from database.db import (
        add_mora, finish_expedition, get_all_finished_expeditions,
        get_pets_batch, get_marriages_batch, is_isolated_chat,
    )
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
    if not finished:
        return

    # Batch-fetch pets and marriages (2 queries instead of 2*N)
    pairs = [(exp["user_id"], exp["chat_id"]) for exp in finished]
    pets_map = await get_pets_batch(pairs)
    marriages_map = await get_marriages_batch(pairs)

    for exp in finished:
        uid = exp["user_id"]
        chat_id = exp["chat_id"]
        if is_isolated_chat(chat_id):
            await finish_expedition(uid, chat_id)
            continue
        reward = random.randint(exp["reward_min"], exp["reward_max"])
        try:
            # Начисляем мору владельцу питомца
            await add_mora(uid, chat_id, reward)
            await finish_expedition(uid, chat_id)

            pet = pets_map.get((uid, chat_id))
            pet_emoji = _PET_EMOJI.get(pet["pet_type"], "🐾") if pet else "🐾"
            pet_name  = pet["name"] if (pet and pet.get("name")) else "Питомец"
            exp_label = _label_by_h.get(exp["duration_h"], f"{exp['duration_h']}ч")
            loot      = _loot_flavor(reward)

            # Проверяем брак и начисляем мору партнёру тоже
            marriage = marriages_map.get((uid, chat_id))
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


# ─── Обновление цен облигаций каждые 1-3 часа (случайно) ───────────────────


async def _task_bond_price_update(bot) -> None:
    """Обновляет цены облигаций для всех чатов раз в 1-3 часа (случайный интервал).
    Gaussian walk + mean reversion + bull/bear trend + volatility spikes."""
    from database.db import get_scheduler_state, set_scheduler_state
    now = datetime.now(timezone.utc)

    # Пропускаем, пока не настало следующее запланированное время обновления
    next_update_str = await get_scheduler_state("bond_price_next_update")
    if next_update_str:
        try:
            next_update = datetime.fromisoformat(next_update_str)
            if next_update.tzinfo is None:
                next_update = next_update.replace(tzinfo=timezone.utc)
            if now < next_update:
                return
        except (ValueError, TypeError):
            pass

    from database.db import update_bond_prices, is_isolated_chat
    from database.postgres import connect as postgres_connect

    # Получаем все активные chat_id из chat_settings (исключая изолированные)
    async with postgres_connect() as db:
        async with db.execute("SELECT chat_id FROM chat_settings") as c:
            rows = await c.fetchall()

    chat_ids = [r["chat_id"] for r in rows if not is_isolated_chat(r["chat_id"])]

    # Запоминаем время последнего обновления (используется в mini app для обнаружения изменений)
    await set_scheduler_state("bond_price_last_update", now.strftime("%Y-%m-%dT%H:%M"))
    await set_scheduler_state("bond_price_last_updated_at", now.strftime("%Y-%m-%dT%H:%M"))

    # Планируем следующее обновление через случайный интервал 1–3 часа
    delay_secs = random.randint(3600, 10800)
    next_time = now + timedelta(seconds=delay_secs)
    await set_scheduler_state("bond_price_next_update", next_time.strftime("%Y-%m-%dT%H:%M"))

    trend_summary: dict[str, str] = {}
    for chat_id in chat_ids:
        try:
            result = await update_bond_prices(chat_id)
            if isinstance(result, dict):
                trend_summary[str(chat_id)] = result.get("trend", "?")
        except Exception as exc:
            log.warning("Bond price update for chat %s: %s", chat_id, exc)

    if chat_ids:
        trends = ", ".join(f"{cid}:{t}" for cid, t in trend_summary.items()) or "—"
        log.info(
            "Bond prices updated for %d chats at %s UTC (next in %dm) | trends: %s",
            len(chat_ids), now.strftime("%H:%M"), delay_secs // 60, trends,
        )
    else:
        log.info("Bond price update: no chats in chat_settings yet")


# ─── Пятница 20:00 Zurich — Дилижанс ─────────────────────────────────────────


async def _task_diligence_event(bot) -> None:
    """Запускает Дилижанс по пятницам в 20:00 (Europe/Zurich)."""
    from database.db import get_scheduler_state, set_scheduler_state
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
    last_sent = await get_scheduler_state("diligence_last_date")
    if last_sent == today_str:
        return
    await set_scheduler_state("diligence_last_date", today_str)

    from database.db import get_all_active_chats
    from handlers.diligence import _launch_diligence
    chat_ids = await get_all_active_chats()
    for cid in chat_ids:
        try:
            await _launch_diligence(bot, cid)
        except Exception as exc:
            log.warning("Diligence launch in %s: %s", cid, exc)
    log.info("Diligence event triggered for %d chats", len(chat_ids))


# ─── Dev event queue (Mini App → bot) ────────────────────────────────────────

async def _task_dev_event_queue(bot) -> None:
    """Process pending dev_event_queue rows left by the Mini App's /api/dev/trigger_event."""
    from database.postgres import connect as postgres_connect
    from config import DEVELOPER_ID
    try:
        async with postgres_connect() as db:
            # Ensure table exists (may not yet if Django hasn't created it)
            await db.execute(
                "CREATE TABLE IF NOT EXISTS dev_event_queue ("
                "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
                "chat_id BIGINT NOT NULL, event_type TEXT NOT NULL, "
                "requested_by BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), processed INTEGER DEFAULT 0)"
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
                    elif etype == "boss_reset":
                        from handlers.boss import _boss_hp, BOSS_MAX_HP
                        _boss_hp[cid] = BOSS_MAX_HP
                        log.info("Dev event: boss reset for chat %s", cid)
                    else:
                        log.info("Dev event queue: unknown type %r for chat %s", etype, cid)
                except Exception as exc:
                    log.warning("Dev event queue item %s (%s / %s) failed: %s", ev_id, cid, etype, exc)
                # Mark processed regardless (prevent retry storms)
                await db.execute("UPDATE dev_event_queue SET processed=1 WHERE id=?", (ev_id,))
            await db.commit()
    except Exception as exc:
        log.warning("_task_dev_event_queue: %s", exc)


# ─── Авто-удаление данных вышедших + неактивных 7+ дней ──────────────────────

async def _task_cleanup_left_users() -> None:
    """Удаляет user_stats и user_mora для пользователей, покинувших чат 7+ дней назад."""
    from database.db import cleanup_left_inactive_users
    cleaned = await cleanup_left_inactive_users(cutoff_days=7)
    if cleaned:
        log.info("Scheduler [cleanup_left_users]: cleaned %d (user_id, chat_id) pairs", cleaned)

# ─── Еженедельные награды топ-10 по сообщениям ───────────────────────────────────

async def _task_weekly_top_rewards(bot) -> None:
    """Начисляет награды топ-10 по сообщениям в 00:00 понедельника по Цюрихскому времени.
    Чествует прошлую неделю (get_prev_weekly_top), т.к. на момент запуска недель уже сменилась.
    """
    from database.db import (
        get_active_chats, get_prev_weekly_top,
        is_weekly_top_rewarded, record_weekly_top_rewards,
        WEEKLY_TOP_REWARDS, is_isolated_chat,
    )
    from utils.helpers import user_mention

    now = datetime.now(ZURICH)
    # Запуск только по понедельникам в промежутке 00:00–02:00
    if now.weekday() != 0:   # 0 = понедельник
        return
    if now.hour >= 2:        # даём 2 часа окна на случай запоздало|перезапустился
        return

    # Ключ ПРОШЛОЙ недели (bot уже на новой)
    prev_iso = (now - timedelta(days=7)).isocalendar()
    prev_week_key = f"{prev_iso.year}-W{prev_iso.week:02d}"

    chats = await get_active_chats()
    for chat_row in chats:
        chat_id = chat_row["chat_id"]

        if is_isolated_chat(chat_id):
            continue

        if await is_weekly_top_rewarded(chat_id, prev_week_key):
            continue

        top = await get_prev_weekly_top(chat_id, 10)
        if not top:
            continue

        rewards: list[tuple[int, int, int, str]] = []
        lines: list[str] = []
        _MEDALS = ["🥇", "🥈", "🥉"]

        for i, row in enumerate(top[:10]):
            place  = i + 1
            uid    = row["user_id"]
            fname  = row.get("full_name") or str(uid)
            amount = WEEKLY_TOP_REWARDS.get(place, 0)
            if amount <= 0:
                continue
            rewards.append((uid, place, amount, fname))
            medal = _MEDALS[i] if i < 3 else f"{place}."
            lines.append(f"{medal} {user_mention(uid, html.escape(fname))} — <b>+{amount} 🪙</b>")

        if not rewards:
            continue

        await record_weekly_top_rewards(chat_id, prev_week_key, rewards)

        text = (
            f"🏆 <b>Награды за топ-10 активных недели {prev_week_key}!</b>\n\n"
            + "\n".join(lines)
            + "\n\nНарады выдаются еженедельно по понедельникам в 00:00 Цюрих — пиши больше!"
        )
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as exc:
            log.warning("weekly_top_rewards: cannot send to %s: %s", chat_id, exc)


# ─── Финализация истёкших аукционов ──────────────────────────────────────────

async def _task_auction_finalize(bot) -> None:
    """Закрыть все истёкшие аукционы. Запускается каждый час."""
    try:
        from api.auction import finalize_expired_auctions
        finalized = await finalize_expired_auctions(bot=bot)
        if finalized:
            log.info("Scheduler [auction_finalize]: finalized %d auctions", len(finalized))
    except Exception as exc:
        log.warning("_task_auction_finalize error: %s", exc)