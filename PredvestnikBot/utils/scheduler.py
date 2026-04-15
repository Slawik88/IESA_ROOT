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
    log.info("Scheduler: waiting 60s before first run...")
    await asyncio.sleep(60)  # дать боту полностью инициализироваться
    run_count = 0
    while True:
        run_count += 1
        log.info("Scheduler tick #%d starting", run_count)
        _tasks = [
            ("inactivity_warn",    _task_inactivity_warns),
            ("cleanup_reminder",   _task_cleanup_reminders),
            ("anniversary",        _task_marriage_anniversary),
            ("lottery",            _task_lottery_draw),
            ("singles_bonus",      _task_weekly_singles_bonus),
            ("chest_event",        _task_chest_event),
            ("expeditions",        _task_expedition_notifications),
            ("bond_prices",        _task_bond_price_update),
            ("diligence_event",    _task_diligence_event),
            ("cleanup_left_users", _task_cleanup_left_users),
            ("weekly_top_rewards", _task_weekly_top_rewards),
            ("dev_event_queue",    _task_dev_event_queue),
            ("auction_finalize",   _task_auction_finalize),
            ("archive_inactive",   _task_archive_inactive),
            ("archive_warnings",   _task_archive_warnings),
            ("flood_cleanup",      _task_flood_cleanup),
        ]
        for _name, _fn in _tasks:
            _t0 = asyncio.get_event_loop().time()
            try:
                log.debug("Scheduler [%s] start", _name)
                if _fn is _task_cleanup_left_users or _fn is _task_flood_cleanup:
                    await _fn()
                else:
                    await _fn(bot)
                _ms = int((asyncio.get_event_loop().time() - _t0) * 1000)
                log.debug("Scheduler [%s] done (%dms)", _name, _ms)
            except Exception as exc:
                _ms = int((asyncio.get_event_loop().time() - _t0) * 1000)
                log.error("Scheduler [%s] error (%dms): %s", _name, _ms, exc, exc_info=True)
        log.info("Scheduler tick #%d complete — sleeping 3600s", run_count)
        await asyncio.sleep(3600)


# ─── Flood data cleanup ───────────────────────────────────────────────────────

async def _task_flood_cleanup() -> None:
    from utils.flood import cleanup_flood_data
    cleanup_flood_data()


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

        # marriages_global хранит ДВЕ строки на пару (A→B и B→A).
        # Обрабатываем только одну из них, чтобы не начислить мору дважды.
        if uid >= partner_id:
            continue

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

        # Prefer real-time Telegram name over DB (which may be set from JSON import)
        async def _tg_name(tg_uid: int, db_user) -> str:
            try:
                chat_obj = await bot.get_chat(tg_uid)
                name = chat_obj.full_name or ""
                if name:
                    return html.escape(name)
            except Exception as _e:
                log.debug("%s", _e)
            if db_user:
                return html.escape(db_user["full_name"] or str(tg_uid))
            return str(tg_uid)

        u_name = await _tg_name(uid, user)
        p_name = await _tg_name(partner_id, partner)

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
    # Дедупликация по user_id — мора глобальна, начислять нужно ОДИН РАЗ,
    # независимо от того, сколько чатов у пользователя.
    seen_uids: set[int] = set()
    chats: dict[int, list[int]] = {}
    for su in singles:
        cid = su["chat_id"]
        uid = su["user_id"]
        if is_isolated_chat(cid):
            continue
        chats.setdefault(cid, [])
        if uid not in seen_uids:
            seen_uids.add(uid)
            await add_mora(uid, 0, SINGLES_WEEKLY_BONUS)  # chat_id=0 — глобальный
        chats[cid].append(uid)
    for chat_id, uids in chats.items():
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
        except (ValueError, TypeError) as _e:
            log.debug("%s", _e)

    from database.db import update_bond_prices, is_isolated_chat

    # Биржа глобальная — обновляем один раз с chat_id=0, не по каждому чату.
    await set_scheduler_state("bond_price_last_update", now.strftime("%Y-%m-%dT%H:%M"))
    await set_scheduler_state("bond_price_last_updated_at", now.strftime("%Y-%m-%dT%H:%M"))

    # Планируем следующее обновление через случайный интервал 1–3 часа
    delay_secs = random.randint(3600, 10800)
    next_time = now + timedelta(seconds=delay_secs)
    await set_scheduler_state("bond_price_next_update", next_time.strftime("%Y-%m-%dT%H:%M"))

    try:
        result = await update_bond_prices(0)
        trend = result.get("trend", "?") if isinstance(result, dict) else "?"
        log.info(
            "Bond prices updated (global) at %s UTC (next in %dm) | trend: %s",
            now.strftime("%H:%M"), delay_secs // 60, trend,
        )
    except Exception as exc:
        log.warning("Bond price update failed: %s", exc)


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
    try:
        async with postgres_connect() as db:
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


# ─── Этап 1: Архивация неактивных пользователей ───────────────────────────────

async def _task_archive_inactive(bot) -> None:
    """
    Переводит в архив пользователей, которые:
      • не состоят ни в одном чате с ботом (нет записей в user_chats)
      • неактивны дольше ARCHIVE_AFTER_DAYS дней (last_active устарел или NULL)

    Запускается каждый час, но фактически срабатывает не часто — только
    когда находит новых кандидатов.
    """
    try:
        from database.db import get_users_for_archiving, archive_user, ARCHIVE_AFTER_DAYS

        candidates = await get_users_for_archiving()
        if not candidates:
            return

        for user in candidates:
            uid = user["user_id"]
            try:
                await archive_user(uid)
                log.info(
                    "archive_inactive: archived user %d (@%s, last_active=%s)",
                    uid, user.get("username"), user.get("last_active"),
                )
            except Exception as exc:
                log.warning("archive_inactive: failed to archive user %d: %s", uid, exc)

        log.info(
            "Scheduler [archive_inactive]: archived %d users (threshold=%dd)",
            len(candidates), ARCHIVE_AFTER_DAYS,
        )
    except Exception as exc:
        log.error("_task_archive_inactive error: %s", exc, exc_info=True)


# ─── Этап 2: Предупреждения и хард-удаление из архива ─────────────────────────

async def _task_archive_warnings(bot) -> None:
    """
    Для каждого архивированного пользователя:
      1. Если осталось ≤ N дней до удаления и предупреждение ещё не отправлялось —
         отправить уведомление в личку (N ∈ {20, 10, 5, 1}).
      2. Если days_until_delete ≤ 0 — выполнить hard_delete_user().
    """
    try:
        from database.db import (
            get_archived_users_for_warnings,
            set_archive_warn,
            hard_delete_user,
            unarchive_user,
        )

        entries = await get_archived_users_for_warnings()
        if not entries:
            return

        deleted = 0
        warned = 0

        for entry in entries:
            uid         = entry["user_id"]
            uname       = entry.get("username") or ""
            fname       = entry.get("full_name") or str(uid)
            days_left   = entry["days_until_delete"]
            should_del  = entry["should_delete"]
            warn_days   = entry["warn_needed"]

            # ── Хард-удаление ────────────────────────────────────────────────
            if should_del:
                try:
                    await hard_delete_user(uid)
                    deleted += 1
                    log.info(
                        "archive_warnings: hard-deleted user %d (@%s) — past deadline",
                        uid, uname,
                    )
                    # Финальное уведомление в личку (best effort)
                    try:
                        await bot.send_message(
                            uid,
                            "⚰️ <b>Ваши данные удалены.</b>\n\n"
                            "Вы не состояли ни в одном чате бота и не проявляли активность "
                            "в течение длительного времени.\n\n"
                            "Если вы вернётесь в один из чатов с ботом, "
                            "ваш аккаунт будет создан заново.",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass  # пользователь мог заблокировать бота — это нормально
                except Exception as exc:
                    log.error("archive_warnings: hard_delete_user(%d) failed: %s", uid, exc)
                continue  # не отправляем предупреждение уже удалённому

            # ── Предупреждение ────────────────────────────────────────────────
            if warn_days is not None:
                _TEXTS = {
                    20: (
                        "⚠️ <b>Предупреждение об архивации</b>\n\n"
                        "Вы не состоите ни в одном чате с нашим ботом уже давно.\n"
                        f"Ваш аккаунт будет <b>удалён через ~{int(days_left)} дней</b>.\n\n"
                        "Вступите в любой чат с ботом, чтобы отменить удаление."
                    ),
                    10: (
                        "⚠️ <b>Ваши данные будут удалены через ~10 дней</b>\n\n"
                        "Последний шанс сохранить аккаунт — вступите в чат с ботом."
                    ),
                    5: (
                        "🚨 <b>Удаление через ~5 дней!</b>\n\n"
                        "Вступите в чат с ботом, чтобы не потерять данные."
                    ),
                    1: (
                        "🚨🚨 <b>УДАЛЕНИЕ ЗАВТРА!</b>\n\n"
                        "Это последнее предупреждение. Аккаунт будет удалён менее чем через сутки.\n"
                        "Вступите в любой чат с ботом прямо сейчас, чтобы отменить удаление."
                    ),
                }
                text = _TEXTS.get(warn_days, f"⚠️ Ваши данные будут удалены через {int(days_left)} дней.")
                try:
                    await bot.send_message(uid, text, parse_mode="HTML")
                    await set_archive_warn(uid, warn_days)
                    warned += 1
                    log.info(
                        "archive_warnings: sent %dd-warn to user %d (@%s)",
                        warn_days, uid, uname,
                    )
                except Exception as exc:
                    # Пользователь заблокировал бота — отмечаем предупреждение отправленным,
                    # чтобы не спамить при каждом тике
                    log.debug(
                        "archive_warnings: cannot DM user %d (%s) — marking warn_%d sent anyway",
                        uid, exc, warn_days,
                    )
                    try:
                        await set_archive_warn(uid, warn_days)
                    except Exception:
                        pass

        if deleted or warned:
            log.info(
                "Scheduler [archive_warnings]: warned=%d, hard-deleted=%d",
                warned, deleted,
            )

    except Exception as exc:
        log.error("_task_archive_warnings error: %s", exc, exc_info=True)
