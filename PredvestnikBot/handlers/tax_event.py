"""
Богатый сундук — случайный групповой ивент.

Появляется в чате раз в 4-8 часов (через scheduler).
Первые 6 кликнувших получают награды (60/50/40/30/20/10 мора).
Через CHEST_EVENT_DURATION секунд сундук исчезает.

ВАЖНО: финализация ивента выполняется двумя путями:
  1. asyncio.create_task(_finalize_after_delay) — для живых процессов (60 сек)
  2. finalize_expired_chest_events() — вызывается из scheduler каждый час,
     подбирает любые протухшие ивенты после перезапуска процесса.
"""

import asyncio
import html
import logging
import random

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
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
    get_chest_event_winners,
    get_expired_unfinished_chest_events,
    set_chest_event_message,
    increment_tracker,
)

log = logging.getLogger(__name__)
from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())


# Хранение активных ивентов {chat_id: event_id}
_active_events: dict[int, int] = {}

_PLACE_EMOJI = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]


async def _build_results_text(event_id: int, total_clicks: int) -> str:
    """Собрать финальный текст с победителями из БД."""
    winners = await get_chest_event_winners(event_id)
    lines = [
        f"🎁 <b>Богатый сундук закрыт!</b>",
        f"Всего попытались открыть: <b>{total_clicks}</b> чел.",
    ]
    if winners:
        lines.append("\n🏆 <b>Победители:</b>")
        for w in winners:
            pos = w.get("position") or 0
            emoji = _PLACE_EMOJI[pos - 1] if 1 <= pos <= len(_PLACE_EMOJI) else f"#{pos}"
            username = w.get("username")
            name = html.escape(w.get("full_name") or "")
            uname = f"@{username}" if username else name or f"[id{w['user_id']}]"
            lines.append(f"{emoji} {uname} — <b>{w.get('reward', 0)} 🪙</b>")
    else:
        lines.append("\n<i>Никто не успел открыть сундук 😢</i>")
    return "\n".join(lines)


async def _do_finalize(bot: Bot, chat_id: int, event_id: int, msg_id: int):
    """Финализирует ивент: помечает в БД, обновляет сообщение."""
    changed = await finish_chest_event(event_id)
    if not changed:
        # Another concurrent call already finalized this event
        return
    _active_events.pop(chat_id, None)

    try:
        total = await get_chest_click_count(event_id)
        result_text = await _build_results_text(event_id, total)
        await bot.edit_message_text(
            result_text,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        log.warning("Chest finalize edit failed (message gone?) (%s/%s): %s", chat_id, event_id, exc)
    except Exception as exc:
        log.warning("Chest finalize edit failed (%s/%s): %s", chat_id, event_id, exc)


async def launch_chest_event(bot: Bot, chat_id: int) -> int | None:
    """Запускает ивент «Богатый сундук» в одном чате.

    Возвращает event_id при успехе, иначе None.
    """
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
    if event_id is None:
        log.error("create_chest_event returned None for chat %s — aborting", chat_id)
        try:
            await bot.delete_message(chat_id, msg.message_id)
        except TelegramBadRequest as _e:
            log.debug("%s", _e)
        return None
    await set_chest_event_message(event_id, msg.message_id)
    _active_events[chat_id] = event_id

    # Обновляем кнопку — теперь с реальным event_id (защита от chest:0 до создания)
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
    except Exception as _e:
        log.debug("%s", _e)

    # Таймер в памяти (для нормального процесса)
    asyncio.create_task(_finalize_after_delay(bot, chat_id, event_id, msg.message_id))
    return event_id


async def _finalize_after_delay(bot: Bot, chat_id: int, event_id: int, msg_id: int):
    """Ждёт CHEST_EVENT_DURATION секунд, затем подводит итоги."""
    await asyncio.sleep(CHEST_EVENT_DURATION)
    await _do_finalize(bot, chat_id, event_id, msg_id)


async def finalize_expired_chest_events(bot: Bot):
    """Финализирует все протухшие ивенты (перезапуск процесса, упавший таймер).
    Вызывается из scheduler каждый час."""
    expired = await get_expired_unfinished_chest_events()
    for ev in expired:
        event_id = ev["id"]
        chat_id  = ev["chat_id"]
        msg_id   = ev["message_id"]
        if not msg_id:
            # Сообщение неизвестно — просто закрываем в БД
            await finish_chest_event(event_id)
            _active_events.pop(chat_id, None)
            continue
        log.info("Finalizing expired chest event %s in chat %s", event_id, chat_id)
        await _do_finalize(bot, chat_id, event_id, msg_id)


@router.callback_query(lambda c: c.data and c.data.startswith("chest:"))
async def cb_chest_click(callback: CallbackQuery):
    raw_id = callback.data.split(":")[1]
    try:
        event_id = int(raw_id)
    except (ValueError, TypeError):
        log.warning("cb_chest_click: bad callback_data=%r", callback.data)
        await callback.answer("⚠️ Ошибка данных, попробуй ещё раз.", show_alert=False)
        return
    if event_id == 0:
        await callback.answer("⏳ Подожди, сундук открывается...", show_alert=False)
        return

    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    # Атомарная проверка: позицию назначаем в самом INSERT (через триггер COUNT)
    count = await get_chest_click_count(event_id)
    count = count if count is not None else 0
    if count >= len(CHEST_REWARDS):
        await callback.answer("❌ Сундук уже пуст!", show_alert=False)
        return

    position = count + 1
    # Защита от IndexError при гонках (position может обогнать len при параллельных кликах)
    if position > len(CHEST_REWARDS):
        await callback.answer("❌ Сундук уже пуст!", show_alert=False)
        return
    reward = CHEST_REWARDS[position - 1]

    ok = await add_chest_click(event_id, uid, position, reward)
    if not ok:
        await callback.answer("⚠️ Ты уже открывал!", show_alert=False)
        return

    # Начисляем мору атомарно
    await add_mora(uid, chat_id, reward)
    await increment_tracker(uid, chat_id, "chests_opened")
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "income", reward, "event", "💰 Богатый сундук")
    except Exception as _e:
        log.debug("%s", _e)

    emoji = _PLACE_EMOJI[position - 1] if position <= len(_PLACE_EMOJI) else f"#{position}"
    name = html.escape(callback.from_user.full_name or "")
    try:
        await callback.answer(f"{emoji} {name}, ты получил +{reward} 🪙!", show_alert=True)
    except TelegramBadRequest as _e:
        log.debug("%s", _e)

    # Если последний слот — сразу закрываем не дожидаясь таймера
    if position >= len(CHEST_REWARDS):
        msg_id = callback.message.message_id
        asyncio.create_task(_do_finalize(callback.bot, chat_id, event_id, msg_id))


async def run_chest_events_cycle(bot: Bot):
    """Запускает Rich Chest в случайном активном чате. Вызывается из scheduler."""
    # Сначала закрываем протухшие ивенты (защита после перезапуска)
    await finalize_expired_chest_events(bot)

    chat_ids = await get_active_group_chat_ids()
    if not chat_ids:
        return

    # Фильтруем чаты, где random_events или chest отключён
    from database.db import get_chat_settings
    eligible = []
    for cid in chat_ids:
        s = await get_chat_settings(cid)
        if s is None or not hasattr(s, "__getitem__"):
            eligible.append(cid)
            continue
        try:
            flag = s["feat_random_events"]
        except (KeyError, IndexError):
            flag = 1
        try:
            chest_flag = s["feat_chest"]
        except (KeyError, IndexError):
            chest_flag = 1
        if flag != 0 and chest_flag != 0:
            eligible.append(cid)

    if not eligible:
        return
    chat_id = random.choice(eligible)
    if chat_id in _active_events:
        return
    await launch_chest_event(bot, chat_id)
