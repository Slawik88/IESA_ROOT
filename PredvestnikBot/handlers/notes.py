from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import delete_note, get_user_stats, list_notes, save_note
from utils.ranks import rank_level
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
import logging
_log = logging.getLogger(__name__)

router = Router()


@router.message(BotCommand("заметка", "сохранить", "addnote"), RankFilter("co_owner"))
async def cmd_save_note(message: Message, cmd_args: str):
    # Синтаксис: бот сохранить <имя> <текст>  или ответом (текст = содержимое ответа)
    parts = cmd_args.split(maxsplit=1) if cmd_args else []
    if not parts:
        await message.answer(
            "❌ Укажи имя заметки.\n"
            "Пример: <code>бот заметка правила Текст правил...</code>\n"
            "Или ответом на сообщение: <code>бот заметка правила</code>",
            parse_mode="HTML",
        )
        return

    name = parts[0].lower()

    if len(parts) > 1:
        content = parts[1]
    elif message.reply_to_message and message.reply_to_message.text:
        content = message.reply_to_message.text
    elif message.reply_to_message and message.reply_to_message.caption:
        content = message.reply_to_message.caption
    else:
        await message.answer(
            "❌ Укажи текст заметки или ответь на сообщение.\n"
            "Пример: <code>бот заметка правила Тут правила чата</code>",
            parse_mode="HTML",
        )
        return

    await save_note(message.chat.id, name, content)
    await message.answer(f"✅ Заметка <code>#{name}</code> сохранена.", parse_mode="HTML")


@router.message(BotCommand("заметки", "notes"))
async def cmd_list_notes(message: Message, cmd_args: str):
    notes = await list_notes(message.chat.id)
    if not notes:
        await message.answer("📝 Нет сохранённых заметок.")
        return

    names = " | ".join(f"<code>#{n['name']}</code>" for n in notes)

    # Кнопки удаления (только для модераторов+)
    caller_stats = await get_user_stats(message.from_user.id, message.chat.id)
    caller_rank = caller_stats["rank"] if caller_stats else "user"
    kb = None
    if rank_level(caller_rank) >= rank_level("moderator"):
        buttons: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for n in notes:
            row.append(InlineKeyboardButton(
                text=f"❌ #{n['name'][:20]}",
                callback_data=f"dn:{n['name'][:40]}",
            ))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"📝 <b>Заметки чата:</b>\n\n{names}\n\n"
        f"<i>Вызов: напиши <code>#название</code> или <code>бот #название</code></i>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(BotCommand("убрать заметку", "удзаметку", "delnote"), RankFilter("co_owner"))
async def cmd_del_note(message: Message, cmd_args: str):
    name = cmd_args.strip().lower().lstrip("#")
    if not name:
        await message.answer("❌ Укажи имя: <code>бот убрать заметку правила</code>", parse_mode="HTML")
        return

    deleted = await delete_note(message.chat.id, name)
    if deleted:
        await message.answer(f"✅ Заметка <code>#{name}</code> удалена.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Заметка <code>#{name}</code> не найдена.", parse_mode="HTML")


@router.callback_query(F.data.startswith("dn:"))
async def cb_del_note(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
    user_rank = stats["rank"] if stats else "user"
    if rank_level(user_rank) < rank_level("moderator"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return

    name = callback.data[3:]  # after "dn:"
    deleted = await delete_note(callback.message.chat.id, name)
    if not deleted:
        await callback.answer("❌ Заметка не найдена.", show_alert=True)
        return

    await callback.answer(f"✅ #{name} удалена")

    # Обновить список
    notes = await list_notes(callback.message.chat.id)
    if not notes:
        try:
            await callback.message.edit_text("📝 Нет сохранённых заметок.")
        except Exception as _e:
            _log.debug("%s", _e)
        return

    names = " | ".join(f"<code>#{n['name']}</code>" for n in notes)
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in notes:
        row.append(InlineKeyboardButton(
            text=f"❌ #{n['name'][:20]}",
            callback_data=f"dn:{n['name'][:40]}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        await callback.message.edit_text(
            f"📝 <b>Заметки чата:</b>\n\n{names}\n\n"
            f"<i>Вызов: напиши <code>#название</code> или <code>бот #название</code></i>",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as _e:
        _log.debug("%s", _e)
