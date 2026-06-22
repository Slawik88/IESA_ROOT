from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from aiogram import Bot

from infrastructure.repositories import streak as streak_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.zoo import get_active_species_level
from services.streak import get_today_in_tz, process_daily_login
from services.achievements import increment_metric as _ach_incr
from services.utils import format_currency
from core.constants import OWL_BONUSES, STREAK_TIMEZONE_OFFSET


def _build_streak_notification(result: dict, user_name: str, chat_id: int) -> str:
    streak = result["new_streak"]
    reward = result["reward"]
    mora_str = format_currency(reward["mora"])
    dia_str = format_currency(reward["diamonds"])

    day_in_block = reward["day_in_block"]
    is_block_end = reward["is_block_end"]

    # Progress bar: filled blocks for days in current block
    filled = "🔥" * day_in_block + "⬜" * (7 - day_in_block)

    penalty_text = ""
    if result["penalty_applied"]:
        old_streak = result["recovery_streak"]
        missed = result["missed_days"]
        cost = result.get("_recovery_cost", {})
        penalty_text = (
            f"\n\n⚠️ <b>Пропущено {missed} дн.!</b> Стрик снижен с {old_streak} до {streak - 1}.\n"
            f"Восстановить: <code>бот стрик восстановить</code>\n"
            f"<i>Стоимость: {format_currency(cost.get('diamonds', 0))} 💎 "
            f"или {format_currency(cost.get('mora', 0))} 🪙</i>"
        )

    block_text = ""
    if is_block_end:
        cycle = reward["cycle"]
        block_text = f"\n🎉 <b>Блок #{cycle + 1} завершён!</b> Бонусная награда!"

    return (
        f'🔥 <b>ЕЖЕДНЕВНЫЙ ВХОД</b> — <a href="tg://user?id={chat_id}">{user_name}</a>\n\n'
        f"🗓 Стрик: <b>{streak} дней</b>{block_text}\n"
        f"{filled}\n\n"
        f"🎁 Награда:\n"
        f"├ 🪙 Мора: <code>+{mora_str}</code>\n"
        f"└ 💎 Алмазы: <code>+{dia_str}</code>"
        f"{penalty_text}"
    )


async def streak_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    db = data.get("db")
    user = data.get("event_from_user")
    chat_obj = data.get("event_chat")
    bot: Bot = data.get("bot")

    # Only fire for real text messages, not callback_query button clicks.
    # At dp.update level: callback_query updates have Update.message=None but
    # Update.callback_query set. Extra guard prevents any edge-case double firing.
    is_message_event = (
        db and user and chat_obj
        and getattr(event, "message", None)
        and not getattr(event, "callback_query", None)
    )
    if is_message_event:
        if event.message.chat.type != "private":
            try:
                # Стрик ЕДИНЫЙ на все чаты: единая таймзона (граница «дня» одна для всех)
                # и одна глобальная строка (chat_id=0). Первое сообщение дня в ЛЮБОМ чате
                # забирает день атомарно → одна награда в день независимо от числа чатов.
                today = get_today_in_tz(STREAK_TIMEZONE_OFFSET)

                streak_row = await streak_repo.get_global_streak(db, user.id)
                result = process_daily_login(streak_row, today)

                if result["is_new_day"] and not result["already_notified"]:
                    reward = result["reward"]
                    from services.streak import calc_recovery_cost
                    recovery_cost = calc_recovery_cost(result["recovery_missed_days"])
                    result["_recovery_cost"] = recovery_cost

                    # Atomically claim the day (на глобальной строке chat_id=0): защищает
                    # от двойной награды при сообщениях в разных чатах в один день.
                    claimed = await streak_repo.upsert_global_streak(
                        db, user.id,
                        streak=result["new_streak"],
                        today=today,
                        recovery_streak=result["recovery_streak"],
                        recovery_missed_days=result["recovery_missed_days"],
                        recovery_expires=result["recovery_expires"],
                    )
                    if not claimed:
                        return await handler(event, data)

                    streak_source = "streak_block_end" if reward.get("is_block_end") else "streak_daily"
                    await eco_repo.add_balance(
                        db, user.id,
                        mora=reward["mora"],
                        diamonds=reward["diamonds"],
                        commit=False,
                        source=streak_source,
                        chat_id=chat_obj.id,
                        note=f"streak={result['new_streak']}",
                    )

                    # Выдаём жетон за день-7 каждого блока (block_end)
                    if reward.get("is_block_end"):
                        await db.execute(
                            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, 1) "
                            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + 1",
                            (user.id, "spin_token"),
                        )

                    # Owl Lv10: daily free spin token
                    try:
                        owl_sentinel = f"owl_spin_{today}"
                        async with db.execute(
                            "SELECT 1 FROM player_buffs WHERE user_id = ? AND buff_type = ? LIMIT 1",
                            (user.id, owl_sentinel),
                        ) as _oc:
                            _owl_done = await _oc.fetchone()
                        if not _owl_done:
                            owl_level = await get_active_species_level(db, user.id, "owl")
                            owl_bonus = OWL_BONUSES.get(max(1, min(10, owl_level)), {})
                            if owl_bonus.get("daily_free_spin_token", False):
                                await db.execute(
                                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, 'spin_token', 1) "
                                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + 1",
                                    (user.id,),
                                )
                                await db.execute(
                                    "INSERT INTO player_buffs (user_id, buff_type, uses_left, expires_at) "
                                    "VALUES (?, ?, 1, NOW() + INTERVAL '2 days') "
                                    "ON CONFLICT (user_id, buff_type) DO UPDATE SET expires_at = NOW() + INTERVAL '2 days'",
                                    (user.id, owl_sentinel),
                                )
                    except Exception:
                        pass

                    await db.commit()

                    # Achievement: marriage_days_total (vow_keeper) — daily increment
                    try:
                        async with db.execute(
                            "SELECT id FROM marriages WHERE user1_id = ? OR user2_id = ? LIMIT 1",
                            (user.id, user.id),
                        ) as _mc:
                            _married = await _mc.fetchone()
                        if _married:
                            await _ach_incr(db, user.id, "marriage_days_total", delta=1.0)
                            await db.commit()
                    except Exception:
                        pass

                    # Achievement: max_streak_ever (set-max semantics: only track growth)
                    # Read MAX across ALL chats so multi-chat users don't get stuck.
                    try:
                        from infrastructure.repositories.achievements import get_achievement  # noqa: PLC0415
                        ach = await get_achievement(db, user.id, "persistent")
                        prev_max = ach["progress"] if ach else 0.0
                        async with db.execute(
                            "SELECT MAX(streak) FROM daily_login WHERE user_id = ?",
                            (user.id,),
                        ) as _sc:
                            _srow = await _sc.fetchone()
                        new_streak_val = float(_srow[0]) if _srow and _srow[0] else float(result["new_streak"])
                        if new_streak_val > prev_max:
                            delta = new_streak_val - prev_max
                            await _ach_incr(db, user.id, "max_streak_ever", delta=delta)
                            await db.commit()
                    except Exception:
                        pass

                    # Achievements: peak_mora_balance (Магнат) + peak_diamonds_balance (Сокровищница)
                    # Checked once per day — set-max semantics, no recursion risk
                    try:
                        from infrastructure.repositories.achievements import get_achievement  # noqa: PLC0415
                        bal = await eco_repo.get_balance(db, user.id)
                        cur_mora = float(bal.get("user_balance_mora", 0) or 0)
                        cur_dia  = float(bal.get("user_balance_diamonds", 0) or 0)
                        mora_ach = await get_achievement(db, user.id, "magnate")
                        dia_ach  = await get_achievement(db, user.id, "treasury")
                        prev_mora = mora_ach["progress"] if mora_ach else 0.0
                        prev_dia  = dia_ach["progress"]  if dia_ach  else 0.0
                        if cur_mora > prev_mora:
                            await _ach_incr(db, user.id, "peak_mora_balance", delta=cur_mora - prev_mora)
                        if cur_dia > prev_dia:
                            await _ach_incr(db, user.id, "peak_diamonds_balance", delta=cur_dia - prev_dia)
                        await db.commit()
                    except Exception:
                        pass

                    from services.utils import resolve_display_name
                    user_name = await resolve_display_name(
                        db, user.id, chat_obj.id, user.first_name or f"ID{user.id}"
                    )
                    text = _build_streak_notification(result, user_name, user.id)
                    if bot:
                        try:
                            await bot.send_message(
                                chat_obj.id,
                                text,
                                parse_mode="HTML",
                                disable_notification=True,
                            )
                        except Exception:
                            pass
                elif result["is_new_day"] and result["already_notified"]:
                    # Already notified today but streak row needs today's last_login
                    pass

            except Exception:
                pass

    return await handler(event, data)
