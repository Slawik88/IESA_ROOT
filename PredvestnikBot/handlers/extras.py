from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import html as _html

from database.db import (
    add_filter, delete_filter, get_chat_members, get_chat_settings, get_filters,
    get_note, get_user_stats, is_group_allowed,
    set_chat_active, upsert_chat, upsert_user, upsert_user_stats,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import user_mention
from utils.ranks import rank_level

router = Router()


async def _register_member_in_chat(chat_id: int, member) -> None:
    """Register a chat member in DB without waiting for first text message."""
    if not member or member.is_bot:
        return
    await upsert_user(member.id, member.username or "", member.full_name or "")
    await upsert_user_stats(member.id, chat_id)


async def _sync_chat_administrators(bot, chat_id: int) -> int:
    """Best-effort initial sync for known members available via Bot API (admins)."""
    synced = 0
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return 0

    for admin_member in admins:
        user = getattr(admin_member, "user", None)
        if not user or user.is_bot:
            continue
        await _register_member_in_chat(chat_id, user)
        synced += 1
    return synced


@router.my_chat_member()
async def track_bot_chat_state(event: ChatMemberUpdated):
    old_status = getattr(event.old_chat_member, "status", "")
    new_status = getattr(event.new_chat_member, "status", "")

    _active_statuses = {"member", "administrator"}
    was_active = old_status in _active_statuses
    is_active = 1 if new_status in _active_statuses else 0

    await upsert_chat(
        event.chat.id,
        getattr(event.chat, "title", "") or getattr(event.chat, "full_name", ""),
        getattr(event.chat, "username", "") or "",
        event.chat.type,
        is_active,
    )

    if is_active and not was_active:
        # Бот только что добавлен — отправляем приветствие (только если группа разрешена)
        from database.db import is_group_allowed
        if is_group_allowed(event.chat.id):
            # Мгновенно синхронизируем известных участников (как минимум админов).
            await _sync_chat_administrators(event.bot, event.chat.id)
            try:
                from config import BOT_ADDED_MSG
                await event.bot.send_message(
                    event.chat.id,
                    BOT_ADDED_MSG,
                    parse_mode="HTML",
                )
            except Exception:
                pass
    elif not is_active:
        await set_chat_active(event.chat.id, 0)


@router.chat_member()
async def track_chat_member_state(event: ChatMemberUpdated):
    """Register users on membership updates (join/approve/unban/promote), before first message."""
    if event.chat.type not in ("group", "supergroup"):
        return
    if not is_group_allowed(event.chat.id):
        return

    member = getattr(event.new_chat_member, "user", None)
    if not member or member.is_bot:
        return

    new_status = getattr(event.new_chat_member, "status", "")
    active_statuses = {"member", "administrator", "creator", "restricted"}
    if new_status not in active_statuses:
        return

    await _register_member_in_chat(event.chat.id, member)


# ─── Управление фильтрами (авто-ответами) ─────────────────────────────────────

@router.message(BotCommand("автоответ", "фильтр", "filter"), RankFilter("moderator"))
async def cmd_add_filter(message: Message, cmd_args: str):
    # Синтаксис: бот фильтр слово | ответ
    if "|" not in cmd_args:
        await message.answer(
            "❌ Неверный формат.\n"
            "Пример: <code>бот автоответ привет | Привет! Как дела?</code>",
            parse_mode="HTML",
        )
        return

    parts = cmd_args.split("|", maxsplit=1)
    keyword = parts[0].strip().lower()
    response = parts[1].strip()

    if not keyword or not response:
        await message.answer(
            "❌ Укажи и ключевое слово, и ответ.\n"
            "Пример: <code>бот автоответ привет | Привет! Как дела?</code>",
            parse_mode="HTML",
        )
        return

    await add_filter(message.chat.id, keyword, response)
    await message.answer(
        f"✅ Фильтр добавлен:\n<code>{keyword}</code> → {response}",
        parse_mode="HTML",
    )


@router.message(BotCommand("автоответы", "фильтры", "filters"))
async def cmd_list_filters(message: Message, cmd_args: str):
    filters_list = await get_filters(message.chat.id)
    if not filters_list:
        await message.answer("📋 Фильтров нет.")
        return

    lines = ["📋 <b>Активные фильтры:</b>\n"]
    for f in filters_list:
        lines.append(f"▫️ <code>{f['keyword']}</code> → {f['response']}")

    # Кнопки удаления (для модераторов+)
    caller_stats = await get_user_stats(message.from_user.id, message.chat.id)
    caller_rank = caller_stats["rank"] if caller_stats else "user"
    kb = None
    if rank_level(caller_rank) >= rank_level("moderator"):
        buttons: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for f in filters_list:
            row.append(InlineKeyboardButton(
                text=f"❌ {f['keyword'][:20]}",
                callback_data=f"dfl:{f['keyword'][:40]}",
            ))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.message(BotCommand("убрать ответ", "удфильтр", "delfilter"), RankFilter("moderator"))
async def cmd_del_filter(message: Message, cmd_args: str):
    keyword = cmd_args.strip().lower()
    if not keyword:
        await message.answer(
            "❌ Укажи слово. Пример: <code>бот убрать ответ привет</code>",
            parse_mode="HTML",
        )
        return

    deleted = await delete_filter(message.chat.id, keyword)
    if deleted:
        await message.answer(f"✅ Фильтр <code>{keyword}</code> удалён.", parse_mode="HTML")
    else:
        await message.answer(f"❌ Фильтр <code>{keyword}</code> не найден.", parse_mode="HTML")


@router.callback_query(F.data.startswith("dfl:"))
async def cb_del_filter(callback: CallbackQuery):
    stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
    user_rank = stats["rank"] if stats else "user"
    if rank_level(user_rank) < rank_level("moderator"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return

    keyword = callback.data[4:]  # after "dfl:"
    deleted = await delete_filter(callback.message.chat.id, keyword)
    if not deleted:
        await callback.answer("❌ Фильтр не найден.", show_alert=True)
        return

    await callback.answer(f"✅ Фильтр «{keyword}» удалён")

    # Обновить список
    filters_list = await get_filters(callback.message.chat.id)
    if not filters_list:
        try:
            await callback.message.edit_text("📋 Фильтров нет.")
        except Exception:
            pass
        return

    lines = ["📋 <b>Активные фильтры:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for f in filters_list:
        lines.append(f"▫️ <code>{f['keyword']}</code> → {f['response']}")
        row.append(InlineKeyboardButton(
            text=f"❌ {f['keyword'][:20]}",
            callback_data=f"dfl:{f['keyword'][:40]}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass


# ─── Приветствие / прощание ───────────────────────────────────────────────────

@router.message(lambda m: m.new_chat_members is not None and len(m.new_chat_members) > 0)
async def on_join(message: Message):
    from config import DEFAULT_WELCOME_ENABLED, DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_CALL, BROADCAST_BATCH
    settings = await get_chat_settings(message.chat.id)
    custom_text = settings["welcome_text"] if settings else None

    # Use custom text if set; otherwise fall back to config defaults
    if not custom_text:
        if not DEFAULT_WELCOME_ENABLED:
            return
        custom_text = DEFAULT_WELCOME_TEXT or "добро пожаловать!"

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        # Проверяем бан в этом чате — автокик + уведомление админов
        stats = await get_user_stats(member.id, message.chat.id)
        if stats and stats["is_banned"]:
            try:
                await message.bot.ban_chat_member(message.chat.id, member.id)
                try:
                    await message.delete()
                except Exception:
                    pass
                # Уведомить admin+ 
                chat_title = _html.escape(getattr(message.chat, "title", "") or str(message.chat.id))
                from utils.helpers import notify_admins
                await notify_admins(
                    message.bot,
                    f"🚫 Забаненный пользователь {user_mention(member.id, member.full_name)} "
                    f"попытался войти в <b>{chat_title}</b> и был автоматически кикнут.",
                    source_chat_id=message.chat.id,
                )
            except Exception:
                pass
            continue

        safe_name = _html.escape(member.full_name)
        safe_username = f"@{member.username}" if member.username else safe_name
        safe_chat = _html.escape(message.chat.title or "")
        text = custom_text.replace(
            "{name}", safe_name
        ).replace(
            "{username}", safe_username
        ).replace(
            "{chat}", safe_chat
        )
        try:
            await message.answer(
                f"👋 {user_mention(member.id, member.full_name)}, {text}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Колл всех участников если включён
    call_enabled = (settings["welcome_call"] if settings else 0) or DEFAULT_WELCOME_CALL
    if call_enabled:
        members = await get_chat_members(message.chat.id)
        if members:
            for i in range(0, len(members), BROADCAST_BATCH):
                batch = members[i: i + BROADCAST_BATCH]
                mentions = " ".join(user_mention(u["user_id"], u["full_name"]) for u in batch)
                try:
                    await message.answer(mentions, parse_mode="HTML")
                except Exception:
                    pass


@router.message(lambda m: m.left_chat_member is not None)
async def on_leave(message: Message):
    from config import DEFAULT_FAREWELL_ENABLED, DEFAULT_FAREWELL_TEXT
    settings = await get_chat_settings(message.chat.id)
    custom_text = settings["farewell_text"] if settings else None

    if not custom_text:
        if not DEFAULT_FAREWELL_ENABLED:
            return
        custom_text = DEFAULT_FAREWELL_TEXT or "{name} покинул чат."

    member = message.left_chat_member
    if member.is_bot:
        return

    safe_name = _html.escape(member.full_name)
    safe_username = f"@{member.username}" if member.username else safe_name
    text = custom_text.replace(
        "{name}", safe_name
    ).replace(
        "{username}", safe_username
    )
    try:
        await message.answer(text, parse_mode="HTML")
    except Exception:
        pass


# ─── Шорткат #заметка и авто-фильтры (catch-all) ─────────────────────────────

@router.message()
async def catch_all(message: Message):
    if not message.text:
        return

    text = message.text.strip()
    chat_id = message.chat.id

    # Шорткат #имязаметки — показать заметку
    if text.startswith("#"):
        name = text[1:].split()[0].lower()
        if name:
            note = await get_note(chat_id, name)
            if note:
                await message.answer(note["content"])
        return

    # Авто-ответ по фильтрам
    text_lower = text.lower()
    filters_list = await get_filters(chat_id)
    for f in filters_list:
        if f["keyword"] in text_lower:
            await message.reply(f["response"])
            break
