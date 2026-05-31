from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
from aiogram import Bot

from infrastructure.repositories import streak as streak_repo
from infrastructure.repositories import economy as eco_repo
from services.streak import get_today_in_tz, process_daily_login
from services.utils import format_currency


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
                tz_offset = await streak_repo.get_chat_timezone(db, chat_obj.id)
                today = get_today_in_tz(tz_offset)

                streak_row = await streak_repo.get_streak(db, user.id, chat_obj.id)
                result = process_daily_login(streak_row, today)

                if result["is_new_day"] and not result["already_notified"]:
                    reward = result["reward"]
                    from services.streak import calc_recovery_cost
                    recovery_cost = calc_recovery_cost(result["recovery_missed_days"])
                    result["_recovery_cost"] = recovery_cost

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
                            (user.id, "spin_token_novice"),
                        )

                    await streak_repo.upsert_streak(
                        db, user.id, chat_obj.id,
                        streak=result["new_streak"],
                        today=today,
                        recovery_streak=result["recovery_streak"],
                        recovery_missed_days=result["recovery_missed_days"],
                        recovery_expires=result["recovery_expires"],
                    )
                    await db.commit()

                    # Achievement: max_streak_ever (uses SET-max semantics)
                    try:
                        from services.achievements import increment_metric as _incr_ach
                        from infrastructure.repositories.achievements import get_achievement, upsert_achievement
                        ach = await get_achievement(db, user.id, "persistent")
                        prev_max = ach["progress"] if ach else 0.0
                        new_streak_val = float(result["new_streak"])
                        if new_streak_val > prev_max:
                            await upsert_achievement(
                                db, user.id, "persistent",
                                level=(ach["level"] if ach else 0),
                                progress=new_streak_val,
                            )
                            await _incr_ach(db, user.id, "persistent", delta=new_streak_val - prev_max)
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
