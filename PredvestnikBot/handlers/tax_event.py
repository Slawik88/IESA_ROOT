"""
Налоговая инспекция — случайный групповой ивент.

Кнопка появляется в чате раз в 4-8 часов (через scheduler).
Первый кликнувший получает приз, последний — штраф.
Минимум TAX_EVENT_MIN_PLAYERS участников для штрафа.

Также содержит callback-обработчик для кнопки.
"""

import asyncio
import random
from datetime import datetime

from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import (
    TAX_EVENT_DURATION,
    TAX_EVENT_MIN_PLAYERS,
    TAX_EVENT_PENALTY_PCT,
    TAX_EVENT_PRIZE_MAX,
    TAX_EVENT_PRIZE_MIN,
)
from database.db import (
    add_mora,
    add_tax_click,
    create_tax_event,
    deduct_mora,
    finish_tax_event,
    get_active_group_chat_ids,
    get_mora,
    get_tax_event_clicks,
    get_tax_event_prize,
)

router = Router()

# Хранение активных ивентов {chat_id: event_id}
_active_events: dict[int, int] = {}


async def launch_tax_event(bot: Bot, chat_id: int):
    """Запускает налоговый ивент в одном чате (вызывается из scheduler)."""
    prize = random.randint(TAX_EVENT_PRIZE_MIN, TAX_EVENT_PRIZE_MAX)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📋 Явиться в налоговую!",
            callback_data="tax:0",  # placeholder, will update
        )],
    ])

    msg = await bot.send_message(
        chat_id,
        f"🏛 <b>НАЛОГОВАЯ ИНСПЕКЦИЯ!</b>\n\n"
        f"Инспектор Фатуи требует проверки!\n"
        f"Первый получит награду <b>{prize} 🪙</b>,\n"
        f"а последний заплатит штраф <b>{int(TAX_EVENT_PENALTY_PCT * 100)}%</b> своего баланса!\n\n"
        f"⏳ Время: <b>{TAX_EVENT_DURATION} сек.</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )

    # Create event in DB with real message_id
    event_id = await create_tax_event(
        chat_id, msg.message_id, prize,
        TAX_EVENT_PENALTY_PCT, TAX_EVENT_DURATION,
    )
    _active_events[chat_id] = event_id

    # Update button with real event_id
    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📋 Явиться в налоговую!",
            callback_data=f"tax:{event_id}",
        )],
    ])
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=msg.message_id, reply_markup=new_kb
        )
    except Exception:
        pass

    # Таймер завершения
    asyncio.create_task(_finalize_after_delay(bot, chat_id, event_id, msg.message_id))


async def _finalize_after_delay(bot: Bot, chat_id: int, event_id: int, msg_id: int):
    """Ожидает TAX_EVENT_DURATION, затем подводит итоги."""
    await asyncio.sleep(TAX_EVENT_DURATION)

    clicks = await get_tax_event_clicks(event_id)
    await finish_tax_event(event_id)
    _active_events.pop(chat_id, None)

    if not clicks:
        try:
            await bot.edit_message_text(
                "🏛 <b>Налоговая инспекция завершена.</b>\n\n"
                "Никто не явился. Инспектор ушёл ни с чем.",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # Первый — приз
    first = clicks[0]
    first_uid = first["user_id"]
    prize = await get_tax_event_prize(event_id)

    lines = [
        "🏛 <b>Налоговая инспекция — итоги!</b>\n",
        f"👆 Участников: <b>{len(clicks)}</b>\n",
    ]

    # Первый — уже получил приз в callback
    try:
        first_user = await bot.get_chat_member(chat_id, first_uid)
        first_name = first_user.user.first_name
    except Exception:
        first_name = f"ID {first_uid}"
    lines.append(f"🥇 Первый: <b>{first_name}</b> → +{prize} 🪙")

    # Последний — штраф (если >= MIN_PLAYERS)
    if len(clicks) >= TAX_EVENT_MIN_PLAYERS:
        last = clicks[-1]
        last_uid = last["user_id"]
        mora_data = await get_mora(last_uid, chat_id)
        bal = mora_data["balance"] if mora_data else 0
        penalty = max(1, int(bal * TAX_EVENT_PENALTY_PCT))
        await deduct_mora(last_uid, chat_id, penalty)
        try:
            last_user = await bot.get_chat_member(chat_id, last_uid)
            last_name = last_user.user.first_name
        except Exception:
            last_name = f"ID {last_uid}"
        lines.append(f"😰 Последний: <b>{last_name}</b> → -{penalty} 🪙 штраф")
    else:
        lines.append(f"\n<i>Менее {TAX_EVENT_MIN_PLAYERS} участников — штрафа нет.</i>")

    try:
        await bot.edit_message_text(
            "\n".join(lines),
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── Callback: нажатие на кнопку ─────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("tax:"))
async def cb_tax_click(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    position = await add_tax_click(event_id, uid)
    if position is None:
        await callback.answer("⚠️ Ты уже нажимал!", show_alert=False)
        return

    if position == 1:
        # Первый — получает приз
        prize = await get_tax_event_prize(event_id)
        await add_mora(uid, chat_id, prize)
        await callback.answer(f"🥇 Ты первый! +{prize} 🪙", show_alert=True)
    else:
        await callback.answer(f"📋 Ты #{position}. Жди итогов!", show_alert=False)


async def run_tax_events_cycle(bot: Bot):
    """Запускает налоговый ивент в случайном активном чате.
    Вызывается из scheduler."""
    chat_ids = await get_active_group_chat_ids()
    if not chat_ids:
        return
    chat_id = random.choice(chat_ids)
    # Не запускаем, если в чате уже есть активный ивент
    if chat_id in _active_events:
        return
    await launch_tax_event(bot, chat_id)
