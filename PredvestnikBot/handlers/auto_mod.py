from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    add_blacklist_word, get_blacklist, get_locks, get_user_stats,
    remove_blacklist_word, set_lock,
    set_chat_setting, get_chat_settings,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter

router = Router()

LOCK_TYPES = {
    "ссылки": "links",
    "links": "links",
    "стикеры": "stickers",
    "stickers": "stickers",
    "гифки": "gifs",
    "gifs": "gifs",
    "пересылка": "forwards",
    "forwards": "forwards",
    "голос": "voice",
    "voice": "voice",
    "видео": "video",
    "video": "video",
    "фото": "photo",
    "photo": "photo",
    "аудио": "audio",
    "audio": "audio",
}

LOCK_LABELS = {
    "links": "🔗 Ссылки",
    "stickers": "🎭 Стикеры",
    "gifs": "🎬 Гифки",
    "forwards": "↩️ Пересылка",
    "voice": "🎤 Голосовые",
    "video": "🎥 Видео-кружочки",
    "photo": "🖼 Фото",
    "audio": "🎵 Аудио",
}


# ─── Замки ────────────────────────────────────────────────────────────────────

@router.message(BotCommand("замок", "lock", "заблокировать"), RankFilter("admin_junior"))
async def cmd_lock(message: Message, cmd_args: str):
    lock_key = LOCK_TYPES.get(cmd_args.lower())
    if not lock_key:
        types_list = ", ".join(LOCK_TYPES.keys())
        await message.answer(
            f"❌ Укажи тип для блокировки.\n\n"
            f"Пример: <code>бот замок ссылки</code>\n"
            f"Доступные: <code>{types_list}</code>",
            parse_mode="HTML",
        )
        return

    await set_lock(message.chat.id, lock_key, 1)
    await message.answer(f"🔒 {LOCK_LABELS[lock_key]} — заблокированы.")


@router.message(BotCommand("открыть", "unlock", "разблокировать"), RankFilter("admin_junior"))
async def cmd_unlock(message: Message, cmd_args: str):
    lock_key = LOCK_TYPES.get(cmd_args.lower())
    if not lock_key:
        types_list = ", ".join(LOCK_TYPES.keys())
        await message.answer(
            f"❌ Укажи тип для разблокировки.\n\n"
            f"Пример: <code>бот открыть ссылки</code>\n"
            f"Доступные: <code>{types_list}</code>",
            parse_mode="HTML",
        )
        return

    await set_lock(message.chat.id, lock_key, 0)
    await message.answer(f"🔓 {LOCK_LABELS[lock_key]} — разблокированы.")


def _locks_text_and_kb(locks) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["🔐 <b>Статус замков:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for col, label in LOCK_LABELS.items():
        is_locked = bool(locks and locks[col])
        state = "🔒" if is_locked else "🔓"
        lines.append(f"{label}: {state}")
        emoji = "🔓" if is_locked else "🔒"
        short = label.split(" ", 1)[1]
        row.append(InlineKeyboardButton(text=f"{emoji} {short}", callback_data=f"lk:{col}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(BotCommand("замки", "locks", "локи"), RankFilter("moderator"))
async def cmd_locks(message: Message, cmd_args: str):
    locks = await get_locks(message.chat.id)
    text, kb = _locks_text_and_kb(locks)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ─── Чёрный список слов ───────────────────────────────────────────────────────

@router.message(BotCommand("блок", "block", "чсдобавить"), RankFilter("moderator"))
async def cmd_block(message: Message, cmd_args: str):
    word = cmd_args.lower().strip()
    if not word:
        await message.answer(
            "❌ Укажи слово. Пример: <code>бот блок плохоеслово</code>",
            parse_mode="HTML",
        )
        return

    added = await add_blacklist_word(message.chat.id, word)
    if added:
        await message.answer(f"✅ Слово <code>{word}</code> добавлено в чёрный список.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Слово <code>{word}</code> уже в чёрном списке.", parse_mode="HTML")


@router.message(BotCommand("разблок", "unblock", "чсубрать"), RankFilter("moderator"))
async def cmd_unblock(message: Message, cmd_args: str):
    word = cmd_args.lower().strip()
    if not word:
        await message.answer(
            "❌ Укажи слово. Пример: <code>бот разблок слово</code>",
            parse_mode="HTML",
        )
        return

    removed = await remove_blacklist_word(message.chat.id, word)
    if removed:
        await message.answer(f"✅ Слово <code>{word}</code> убрано из чёрного списка.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Слово <code>{word}</code> не найдено в чёрном списке.", parse_mode="HTML")


def _blacklist_text_and_kb(words, enabled: int) -> tuple[str, InlineKeyboardMarkup]:
    status = "🟢 Включён" if enabled else "🔴 Отключён"
    toggle_text = "🔴 Выключить" if enabled else "🟢 Включить"
    toggle_val = 0 if enabled else 1
    if not words:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=toggle_text, callback_data=f"blt:{toggle_val}"),
        ]])
        return f"📝 Чёрный список слов пуст. Статус: {status}", kb
    word_list = " | ".join(f"<code>{w['word']}</code>" for w in words)
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for w in words:
        row.append(InlineKeyboardButton(
            text=f"❌ {w['word'][:15]}",
            callback_data=f"dbw:{w['word'][:30]}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=toggle_text, callback_data=f"blt:{toggle_val}")])
    return (
        f"🚫 <b>Чёрный список слов:</b>  ({status})\n\n{word_list}",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(BotCommand("чёрныйсписок", "черныйсписок", "чслова", "чс", "blacklist", "blocklist"), RankFilter("moderator"))
async def cmd_blacklist(message: Message, cmd_args: str):
    words = await get_blacklist(message.chat.id)
    settings = await get_chat_settings(message.chat.id)
    enabled = settings["blacklist_enabled"] if settings and settings["blacklist_enabled"] is not None else 1
    text, kb = _blacklist_text_and_kb(words, enabled)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(BotCommand("фильтрмат", "матфильтр", "блоксловавкл"), RankFilter("admin_junior"))
async def cmd_blacklist_toggle(message: Message, cmd_args: str):
    """Включить / отключить фильтр слов из чёрного списка для этого чата."""
    arg = (cmd_args or "").strip().lower()
    if arg in ("вкл", "on", "включить", "1"):
        await set_chat_setting(message.chat.id, "blacklist_enabled", 1)
        await message.answer(
            "🟢 Фильтр чёрного списка слов <b>включён</b>.\n"
            "<i>Сообщения с запрещёнными словами будут удаляться.</i>",
            parse_mode="HTML",
        )
    elif arg in ("выкл", "off", "отключить", "0"):
        await set_chat_setting(message.chat.id, "blacklist_enabled", 0)
        await message.answer(
            "🔴 Фильтр чёрного списка слов <b>отключён</b>.\n"
            "<i>Маты и запрещённые слова разрешены.</i>",
            parse_mode="HTML",
        )
    else:
        settings = await get_chat_settings(message.chat.id)
        enabled = settings["blacklist_enabled"] if settings and settings["blacklist_enabled"] is not None else 1
        status = "🟢 Включён" if enabled else "🔴 Отключён"
        await message.answer(
            f"📋 <b>Фильтр слов:</b> {status}\n\n"
            f"🟢 Включить: <code>бот фильтрмат вкл</code>\n"
            f"🔴 Отключить: <code>бот фильтрмат выкл</code>",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("lk:"))
async def cb_lock_toggle(callback: CallbackQuery):
    from utils.ranks import rank_level, is_developer
    if not is_developer(callback.from_user.id):
        stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
        user_rank = stats["rank"] if stats else "user"
        if rank_level(user_rank) < rank_level("admin_junior"):
            await callback.answer("❌ Недостаточно прав.", show_alert=True)
            return

    lock_type = callback.data.split(":")[1]
    if lock_type not in LOCK_LABELS:
        await callback.answer("❌ Неизвестный тип.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    locks = await get_locks(chat_id)
    current = bool(locks and locks[lock_type])
    new_val = 0 if current else 1
    await set_lock(chat_id, lock_type, new_val)

    locks = await get_locks(chat_id)
    text, kb = _locks_text_and_kb(locks)
    action = "🔒 Заблокировано" if new_val else "🔓 Разблокировано"
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"{action}: {LOCK_LABELS[lock_type]}")


@router.callback_query(F.data.startswith("dbw:"))
async def cb_del_blacklist_word(callback: CallbackQuery):
    from utils.ranks import rank_level, is_developer
    if not is_developer(callback.from_user.id):
        stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
        user_rank = stats["rank"] if stats else "user"
        if rank_level(user_rank) < rank_level("moderator"):
            await callback.answer("❌ Недостаточно прав.", show_alert=True)
            return

    word = callback.data[4:]
    removed = await remove_blacklist_word(callback.message.chat.id, word)
    if not removed:
        await callback.answer("❌ Слово не найдено.", show_alert=True)
        return

    await callback.answer(f"✅ «{word}» удалено")

    words = await get_blacklist(callback.message.chat.id)
    settings = await get_chat_settings(callback.message.chat.id)
    enabled = settings["blacklist_enabled"] if settings and settings["blacklist_enabled"] is not None else 1
    text, kb = _blacklist_text_and_kb(words, enabled)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("blt:"))
async def cb_blacklist_toggle(callback: CallbackQuery):
    from utils.ranks import rank_level, is_developer
    if not is_developer(callback.from_user.id):
        stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
        user_rank = stats["rank"] if stats else "user"
        if rank_level(user_rank) < rank_level("admin_junior"):
            await callback.answer("❌ Недостаточно прав.", show_alert=True)
            return

    new_val = int(callback.data.split(":")[1])
    await set_chat_setting(callback.message.chat.id, "blacklist_enabled", new_val)
    status = "🟢 Включён" if new_val else "🔴 Отключён"
    await callback.answer(f"Фильтр: {status}")

    words = await get_blacklist(callback.message.chat.id)
    text, kb = _blacklist_text_and_kb(words, new_val)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
