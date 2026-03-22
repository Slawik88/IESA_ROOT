"""
Богатый сундук — случайный групповой ивент.

Появляется в чате раз в 4-8 часов (через scheduler).
Первые 3 кликнувших получают награды (50 / 25 / 10 мора).
Через CHEST_EVENT_DURATION секунд сундук исчезает.
"""

import asyncio
import random

from aiogram import Bot, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import (
    CHEST_EVENT_DURATION,
    CHEST_REWARDS,
)
from database.db import (
    add_mora,
    add_chest_click,
    create_chest_event,
    finish_chest_event,
    get_active_group_chat_ids,
    get_chest_click_count,
    set_chest_event_message,
    increment_tracker,
)

router = Router()

# Хранение активных ивентов {chat_id: event_id}
_active_events: dict[int, int] = {}

_PLACE_EMOJI = ["🥇", "🥈", "🥉"]


async def launch_chest_event(bot: Bot, chat_id: int):
    """Запускает ивент «Богатый сундук» в одном чате."""
    rewards_desc = " / ".join(f"{r} 🪙" for r in CHEST_REWARDS)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💰 Открыть сундук!",
            callback_data="chest:0",
        )],
    ])

    msg = await bot.send_message(
        chat_id,
        f"🎁 <b>БОГАТЫЙ СУНДУК!</b>\n\n"
        f"В чате появился сундук с сокровищами!\n"
        f"Первые {len(CHEST_REWARDS)} участника получат: <b>{rewards_desc}</b>\n\n"
        f"⏳ Время: <b>{CHEST_EVENT_DURATION} сек.</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )

    event_id = await create_chest_event(chat_id, CHEST_EVENT_DURATION)
    await set_chest_event_message(event_id, msg.message_id)
    _active_events[chat_id] = event_id

    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💰 Открыть сундук!",
            callback_data=f"chest:{event_id}",
        )],
    ])
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=msg.message_id, reply_markup=new_kb,
        )
    except Exception:
        pass

    asyncio.create_task(_finalize_after_delay(bot, chat_id, event_id, msg.message_id))


async def _finalize_after_delay(bot: Bot, chat_id: int, event_id: int, msg_id: int):
    """Ожидает CHEST_EVENT_DURATION, затем подводит итоги."""
    await asyncio.sleep(CHEST_EVENT_DURATION)

    await finish_chest_event(event_id)
    _active_events.pop(chat_id, None)

    # Собираем клики из памяти callback (они уже записаны в DB)
    # Просто обновляем сообщение
    try:
        await bot.edit_message_text(
            "🎁 <b>Сундук закрылся!</b>\n\nВсе награды розданы. До следующего раза!",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("chest:"))
async def cb_chest_click(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    if event_id == 0:
        await callback.answer("⏳ Подожди, сундук открывается...", show_alert=False)
        return

    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    count = await get_chest_click_count(event_id)
    position = count + 1

    if position > len(CHEST_REWARDS):
        await callback.answer("❌ Сундук уже пуст!", show_alert=False)
        return

    reward = CHEST_REWARDS[position - 1]
    ok = await add_chest_click(event_id, uid, position, reward)
    if not ok:
        await callback.answer("⚠️ Ты уже открывал!", show_alert=False)
        return

    await add_mora(uid, chat_id, reward)
    await increment_tracker(uid, chat_id, "chests_opened")

    emoji = _PLACE_EMOJI[position - 1] if position <= len(_PLACE_EMOJI) else f"#{position}"
    await callback.answer(f"{emoji} +{reward} 🪙!", show_alert=True)


async def run_chest_events_cycle(bot: Bot):
    """Запускает Rich Chest в случайном активном чате. Вызывается из scheduler."""
    chat_ids = await get_active_group_chat_ids()
    if not chat_ids:
        return
    chat_id = random.choice(chat_ids)
    if chat_id in _active_events:
        return
    await launch_chest_event(bot, chat_id)
