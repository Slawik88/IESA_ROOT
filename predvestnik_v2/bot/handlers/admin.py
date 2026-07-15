from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from infrastructure.repositories import users, chat
from services import roles
from services.utils import safe_html, resolve_target as smart_resolve
from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only

router = Router(name="admin_router")

class RankConfirmData(CallbackData, prefix="rank_conf"):
    target_id: int
    new_rank_id: int
    initiator_id: int


# ==========================================
# КОМАНДА: /setrankbot (Глобальные ранги)
# ==========================================
@router.message(TextCmd(["ранг глобал", "глобал ранг"]))
async def cmd_setrankbot(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    if message.from_user.id != developer_id:
        return

    target_id, target_name, rank_arg = await smart_resolve(message, db, text_args)

    if rank_arg == "error_user_not_found":
         return await message.answer("❌ <b>Ошибка:</b> Пользователь не найден в базе.", parse_mode="HTML")

    if not target_id or not rank_arg:
        ranks_list = roles.get_global_ranks_list_text()
        return await message.answer(
            f"🌌 <b>ГЛОБАЛЬНЫЕ РАНГИ (DEV ONLY)</b>\n\n"
            f"ℹ️ <b>Как использовать:</b>\n"
            f"├ <code>бот ранг глобал, @юзер [ранг]</code>\n"
            f"└ <i>или ответом:</i> <code>бот ранг глобал, [ранг]</code>\n\n"
            f"📋 <b>Доступные ранги:</b>\n{ranks_list}",
            parse_mode="HTML"
        )

    try:
        rank_id = int(rank_arg)
        if rank_id not in roles.GLOBAL_RANKS_MAP:
            raise ValueError
    except ValueError:
        max_r = max(r for r in roles.GLOBAL_RANKS_MAP if r != roles.DEVELOPER_GLOBAL_RANK)
        return await message.answer(
            f"❌ <b>Ошибка:</b> Ранг должен быть числом от 0 до {max_r}.",
            parse_mode="HTML",
        )

    # Rank DEVELOPER_GLOBAL_RANK cannot be manually assigned to others — system auto-grants it
    if rank_id == roles.DEVELOPER_GLOBAL_RANK and target_id != message.from_user.id:
        return await message.answer(
            "❌ <b>Ранг «Главный разработчик» нельзя выдать другому игроку.</b>\n"
            "<i>Он присваивается системой автоматически.</i>",
            parse_mode="HTML",
        )

    await users.set_global_rank(db, target_id, rank_id)
    rank_name = roles.GLOBAL_RANKS_MAP[rank_id]
    
    initiator_link = f'<a href="tg://user?id={message.from_user.id}">Главный Разработчик</a>'
    target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'

    text = (
        f"✅ <b>ГЛОБАЛЬНЫЙ РАНГ УСТАНОВЛЕН!</b>\n\n"
        f"👤 <b>Кому:</b> {target_link} <code>(ID: {target_id})</code>\n"
        f"🌌 <b>Новый статус:</b> {rank_name}\n"
        f"🛠 <b>Выдал:</b> {initiator_link}"
    )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# КОМАНДА: /setrank (Локальные ранги)
# ==========================================
@router.message(TextCmd(["выдать ранг", "дать ранг", "сет ранг", "ранг"]))
async def cmd_setrank(message: types.Message, db, text_args: str = None, developer_id: int = 0):
    initiator_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == "private":
        return await answer_group_only(message)

    target_id, target_name, rank_arg = await smart_resolve(message, db, text_args)

    if rank_arg == "error_user_not_found":
         return await message.answer("❌ <b>Ошибка:</b> Пользователь не найден в базе. Пусть напишет сообщение в чат.", parse_mode="HTML")

    if not target_id or not rank_arg:
        ranks_list = roles.get_local_ranks_list_text()
        return await message.answer(
            f"🏘️ <b>ЛОКАЛЬНЫЕ РАНГИ</b>\n\n"
            f"ℹ️ <b>Как использовать:</b>\n"
            f"├ <code>бот ранг, @юзер [ранг]</code>\n"
            f"└ <i>или ответом:</i> <code>бот ранг, [ранг]</code>\n\n"
            f"📋 <b>Доступные ранги:</b>\n{ranks_list}",
            parse_mode="HTML"
        )

    if target_id == initiator_id:
        return await message.answer("❌ <b>Ошибка:</b> Ранг самому себе выдать нельзя.", parse_mode="HTML")
        
    if target_id == message.bot.id:
        return await message.answer("🤖 <b>Ошибка:</b> Ботам не нужны ранги!", parse_mode="HTML")

    try:
        new_rank_id = int(rank_arg)
        if new_rank_id not in roles.LOCAL_RANKS_MAP:
            raise ValueError
    except ValueError:
        return await message.answer("❌ <b>Ошибка:</b> Ранг должен быть числом от 0 до 6!", parse_mode="HTML")

    initiator_stats = await chat.get_chat_stats(db, initiator_id, chat_id)
    initiator_rank = initiator_stats.get('local_rank', 0)
    
    target_stats = await chat.get_chat_stats(db, target_id, chat_id)
    target_current_rank = target_stats.get('local_rank', 0)
    
    can_assign, error_msg = roles.can_assign_local_rank(initiator_id, initiator_rank, target_current_rank, new_rank_id, developer_id=developer_id)
    if not can_assign:
        return await message.answer(error_msg, parse_mode="HTML")

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить выдачу", 
        callback_data=RankConfirmData(target_id=target_id, new_rank_id=new_rank_id, initiator_id=initiator_id)
    )
    
    rank_name = roles.LOCAL_RANKS_MAP[new_rank_id]
    target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
    initiator_link = f'<a href="tg://user?id={initiator_id}">{safe_html(message.from_user.first_name)}</a>'

    text = (
        f"⏳ <b>ЗАПРОС НА ПОВЫШЕНИЕ</b>\n\n"
        f"📤 <b>От:</b> {initiator_link}\n"
        f"📥 <b>Кому:</b> {target_link} <code>(ID: {target_id})</code>\n"
        f"🎖️ <b>Новый ранг:</b> {rank_name}\n\n"
        f"<i>⚠️ Требуется одобрение Владельца или Совладельца чата</i>"
    )
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ==========================================
# ОБРАБОТЧИК КНОПКИ ПОДТВЕРЖДЕНИЯ (ОДИН РАЗ!)
# ==========================================
@router.callback_query(RankConfirmData.filter())
async def process_rank_confirmation(callback: types.CallbackQuery, callback_data: RankConfirmData, db, developer_id: int = 0):
    approver_id = callback.from_user.id
    chat_id = callback.message.chat.id

    approver_stats = await chat.get_chat_stats(db, approver_id, chat_id)
    approver_rank = approver_stats.get('local_rank', 0)

    if not roles.can_confirm_rank(approver_id, approver_rank, developer_id=developer_id):
        return await callback.answer("❌ У вас нет прав для подтверждения ранга!", show_alert=True)

    await chat.set_local_rank(db, callback_data.target_id, chat_id, callback_data.new_rank_id)
    
    approver_name = safe_html(callback.from_user.first_name)
    approver_link = f'<a href="tg://user?id={approver_id}">{approver_name}</a>'
    rank_name = roles.LOCAL_RANKS_MAP[callback_data.new_rank_id]
    
    initiator_link = f'<a href="tg://user?id={callback_data.initiator_id}">Инициатор (ID: {callback_data.initiator_id})</a>'
    target_link = f'<a href="tg://user?id={callback_data.target_id}">Пользователь (ID: {callback_data.target_id})</a>'

    text = (
        f"✅ <b>ЛОКАЛЬНЫЙ РАНГ УСПЕШНО ВЫДАН!</b>\n\n"
        f"👤 <b>Кому:</b> {target_link}\n"
        f"🎖️ <b>Новый статус:</b> {rank_name}\n\n"
        f"📤 <b>Запросил:</b> {initiator_link}\n"
        f"✍️ <b>Подтвердил:</b> {approver_link}"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer("✅ Ранг успешно применен!", show_alert=False)

# ==========================================
# САМОВОССТАНОВЛЕНИЕ ПРАВ (UX_AUDIT Б17)
# ==========================================
@router.message(TextCmd(["обновить права", "синх права", "восстановить права"]))
async def cmd_sync_rank(message: types.Message, db, developer_id: int = 0):
    """Сверка с фактическим статусом Telegram: creator → ранг 6, admin → 4.
    Только повышает. Закрывает тупик Б17: раньше авто-ранг получал ТОЛЬКО
    «creator» при добавлении бота — если создатель чата неактивен, реальные
    админы не могли настроить бота вообще (setrank требует ранг ≥5)."""
    if message.chat.type == "private":
        return await answer_group_only(message)
    uid = message.from_user.id
    try:
        member = await message.bot.get_chat_member(message.chat.id, uid)
        status = getattr(member, "status", None)
    except Exception:
        status = None
    target = 6 if status == "creator" else 4 if status == "administrator" else None
    if target is None:
        return await message.answer(
            "🌫 По данным Telegram вы не администратор этого чата — ранг не положен.\n"
            "Ранги внутри игры выдают старшие: <code>бот ранг, @юзер [ранг]</code>.",
            parse_mode="HTML")
    stats = await chat.get_chat_stats(db, uid, message.chat.id)
    current = stats.get("local_rank", 0)
    if current >= target:
        return await message.answer(
            f"✅ У вас уже <b>{roles.LOCAL_RANKS_MAP.get(current, current)}</b> — "
            "не ниже, чем даёт ваш статус Telegram. Всё в порядке.",
            parse_mode="HTML")
    await users.update_user(db, uid, message.from_user.username)
    await db.execute(
        "INSERT OR IGNORE INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?)",
        (uid, message.chat.id))
    await chat.set_local_rank(db, uid, message.chat.id, target)
    await db.commit()
    await message.answer(
        f"🎖 Статус Telegram подтверждён: вам выдан ранг "
        f"<b>{roles.LOCAL_RANKS_MAP[target]}</b>.",
        parse_mode="HTML")
