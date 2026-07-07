import re
import logging
from datetime import timedelta, datetime
from aiogram import Router, types, Bot
from aiogram.types import ChatPermissions
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from services.utils import resolve_target, safe_html, resolve_display_name
from services.formatting import parse_dt
from services import moderation as mod_service
from services import roles
from services.membership import prune_ghosts
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import routing
from infrastructure.repositories import chat as chat_repo




router = Router(name="moderation_router")
logger = logging.getLogger(__name__)

async def _check_target_rights(db, chat_id, admin_id, target_id, min_rank,
                               developer_id, bot_id):
    """admin_audit B2: анти-пир для действий над целью (нельзя трогать равного/
    старшего по рангу), но применение к САМОМУ СЕБЕ разрешено при наличии ранга —
    рест/иммунитет себе были легальны и остаются."""
    if target_id == admin_id:
        return await mod_service.check_admin_rights(
            db, chat_id, admin_id, min_rank, developer_id=developer_id, bot_id=bot_id)
    return await mod_service.check_mod_rights(
        db, chat_id, admin_id, target_id, min_rank,
        developer_id=developer_id, bot_id=bot_id)


class WarnAction(CallbackData, prefix="warn_act"):
    action: str
    target_id: int
    chat_id: int

def parse_time(time_str: str) -> timedelta | None:
    match = re.match(r"^(\d+)([смчдsmhd])$", time_str.lower())
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit in ["с", "s"]:
        return timedelta(seconds=val)
    if unit in ["м", "m"]:
        return timedelta(minutes=val)
    if unit in ["ч", "h"]:
        return timedelta(hours=val)
    if unit in ["д", "d"]:
        return timedelta(days=val)
    return None


async def notify_action(
    bot: Bot,
    db,
    main_chat: types.Chat,
    initiator_link: str,
    text_detailed: str,
    text_short: str,
):
    admin_chat_id = await routing.get_admin_chat(db, main_chat.id)
    if admin_chat_id:
        try:
            admin_report = (
                f"🚨 <b>СИСТЕМА МОДЕРАЦИИ</b>\n"
                f"🏘 <b>Источник:</b> {main_chat.title} (<code>{main_chat.id}</code>)\n"
                f"👮‍♂️ <b>Модератор:</b> {initiator_link}\n\n"
                f"{text_detailed}"
            )
            await bot.send_message(admin_chat_id, admin_report, parse_mode="HTML")
            if text_short:
                await bot.send_message(main_chat.id, text_short, parse_mode="HTML")
            return
        except Exception:
            pass
    await bot.send_message(main_chat.id, text_detailed, parse_mode="HTML")


# ==========================================
# ВАРНЫ (ПРЕДУПРЕЖДЕНИЯ)
# ==========================================
@router.message(TextCmd(["варн", "пред", "предупреждение"]))
async def cmd_warn(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    if message.chat.type == "private":
        return

    target_id, target_name, reason = await resolve_target(message, db, text_args)

    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот варн, @юзер [причина]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML"
        )

    cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(db, message.chat.id, message.from_user.id, target_id, cs.get("rank_warn", 2), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    # 3. Выдача варна в базу
    warns_count = await mod_db.add_warn(db, message.chat.id, target_id, message.from_user.id, reason)
    settings = await mod_db.get_chat_settings(db, message.chat.id)
    max_warns = settings["max_warnings"]

    # 5. Формируем и отправляем ответ
    target_name = await resolve_display_name(db, target_id, message.chat.id, target_name)
    target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
    reason_text = f"\n📝 <b>Причина:</b> {safe_html(reason)}" if reason else ""
    
    await message.answer(
        f"⚠️ <b>ВЫДАНО ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        f"👤 {target_link} получает варн <b>[{warns_count}/{max_warns}]</b>.{reason_text}\n\n"
        f"<i>Снять: <code>бот снять варн, @юзер</code> · Лимит: <code>бот лимит варнов</code></i>",
        parse_mode="HTML"
    )

    # 6. Если лимит превышен — запускаем Суд Присяжных
    if warns_count >= max_warns:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🔨 Бан", 
            callback_data=WarnAction(action="ban", target_id=target_id, chat_id=message.chat.id)
        )
        builder.button(
            text="👢 Кик", 
            callback_data=WarnAction(action="kick", target_id=target_id, chat_id=message.chat.id)
        )
        builder.button(
            text="🕊 Простить", 
            callback_data=WarnAction(action="forgive", target_id=target_id, chat_id=message.chat.id)
        )
        builder.adjust(2, 1)

        court_text = (
            f"⚖️ <b>СУД ПРИСЯЖНЫХ</b>\n\n"
            f"Пользователь {target_name} достиг лимита варнов (<b>{warns_count}/{max_warns}</b>).\n"
            f"Выберите меру пресечения:"
        )
        
        # Проверяем, есть ли привязанный админ-чат для вынесения вердиктов
        admin_chat = await routing.get_admin_chat(db, message.chat.id)
        target_chat = admin_chat if admin_chat else message.chat.id
        
        try:
            await bot.send_message(
                target_chat, 
                court_text, 
                reply_markup=builder.as_markup(), 
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки в админ-чат: {e}")
            await message.answer(court_text, reply_markup=builder.as_markup(), parse_mode="HTML")



@router.message(TextCmd(["снять варн", "снять пред"]))
async def cmd_unwarn(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот снять варн, @юзер [кол-во]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )

    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_warn", 2), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    count = 1
    if extra_args:
        parts = extra_args.split()
        if parts and parts[0].isdigit():
            count = max(1, int(parts[0]))

    warns = await mod_db.remove_warn(db, message.chat.id, target_id, count)
    settings = await mod_db.get_chat_settings(db, message.chat.id)
    removed_text = f"{count} варн{'а' if count in (2,3,4) else 'ов' if count >= 5 else ''}" if count > 1 else "предупреждение"
    await message.answer(
        f"✅ У <b>{target_name}</b> снято {removed_text}.\n"
        f"Текущий статус: <b>{warns}/{settings['max_warnings']}</b>",
        parse_mode="HTML",
    )


@router.callback_query(WarnAction.filter())
async def process_warn_action(
    callback: types.CallbackQuery, callback_data: WarnAction, db, bot: Bot, developer_id: int = 0
):
    target_id = callback_data.target_id
    chat_id = callback_data.chat_id
    action = callback_data.action

    # Пороги вердиктов (admin_audit B1): «Бан» = rank_ban, «Кик» = rank_kick,
    # «Простить»/«Варн» = purge_action_rank — кнопки больше не обходят пороги команд.
    _settings = await mod_db.get_chat_settings(db, chat_id)
    if action == "ban":
        _req_rank = _settings.get("rank_ban", 2)
    elif action == "kick":
        _req_rank = _settings.get("rank_kick", 1)
    else:
        _req_rank = _settings.get("purge_action_rank", 2)
    can_mod, err = await mod_service.check_mod_rights(
        db, chat_id, callback.from_user.id, target_id, _req_rank, developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await callback.answer(
            "У вас нет прав для этого вердикта!", show_alert=True
        )

    target_link = f'<a href="tg://user?id={target_id}">Нарушитель</a>'
    admin_link = f'<a href="tg://user?id={callback.from_user.id}">{safe_html(callback.from_user.first_name)}</a>'

    try:
        if action == "ban":
            await bot.ban_chat_member(chat_id, target_id)
            await mod_db.clear_warns(db, chat_id, target_id)
            text = f"🔨 {admin_link} вынес приговор: <b>БАН</b> для {target_link}."
        elif action == "kick":
            await bot.ban_chat_member(chat_id, target_id)
            await bot.unban_chat_member(chat_id, target_id)
            await mod_db.clear_warns(db, chat_id, target_id)
            text = (
                f"👢 {admin_link} вынес приговор: <b>ИСКЛЮЧЕНИЕ</b> для {target_link}."
            )
        elif action == "forgive":
            await mod_db.clear_warns(db, chat_id, target_id)
            text = f"🕊 {admin_link} вынес приговор: <b>ПРОСТИТЬ</b>. Варны {target_link} обнулены."
        elif action == "warn_only":
            warns_count = await mod_db.add_warn(db, chat_id, target_id, callback.from_user.id, "Из досье /purge")
            settings = await mod_db.get_chat_settings(db, chat_id)
            text = (
                f"⚠️ {admin_link} выдал <b>ВАРН</b> для {target_link} "
                f"<b>[{warns_count}/{settings['max_warnings']}]</b>."
            )
        else:
            return await callback.answer("❓ Неизвестное действие.", show_alert=True)

        await callback.message.edit_text(text, parse_mode="HTML")
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception:
        await callback.answer(
            "Ошибка API (возможно нет прав в основном чате).", show_alert=True
        )


# ==========================================
# ИММУНИТЕТ (ЩИТЫ)
# ==========================================
@router.message(TextCmd(["иммунитет"]))
async def cmd_immune(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, resolve_extra = await resolve_target(message, db, text_args)
    if resolve_extra == "error_user_not_found":
        uname = (text_args or "").split()[0]
        return await message.answer(
            f"❌ Пользователь <code>{safe_html(uname)}</code> не найден. "
            "Он должен написать хоть одно сообщение в этом чате.",
            parse_mode="HTML",
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот иммунитет, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )

    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await _check_target_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_immune", 5), developer_id, bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    stats = await chat_repo.get_chat_stats(db, target_id, message.chat.id)
    new_status = not bool(stats.get("is_immune", False))
    await mod_db.set_immunity(db, message.chat.id, target_id, new_status, None)

    if new_status:
        await message.answer(
            f"🛡 <b>{target_name}</b> получил абсолютный иммунитет от чистки.\n"
            f"<i>Все защищённые: <code>бот кто рест</code> · Снять: повторите команду</i>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ С <b>{target_name}</b> снят абсолютный иммунитет.", parse_mode="HTML"
        )


@router.message(TextCmd(["рест", "отдых", "защита", "защитить"]))
async def cmd_protect(
    message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        uname = (text_args or "").split()[0]
        return await message.answer(
            f"❌ Пользователь <code>{safe_html(uname)}</code> не найден. "
            "Он должен написать хоть одно сообщение в этом чате.",
            parse_mode="HTML",
        )
    if not target_id or not extra_args:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот рест, @юзер [5д/1ч]</code>\n"
            "Например: <code>бот рест, @username 14д</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )

    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id,
        _cs.get("rank_shield", 4), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    td = parse_time(extra_args.split()[0])
    if not td:
        return await message.answer(
            "❌ Неверный формат времени! Используйте: 10м, 5ч, 3д.", parse_mode="HTML"
        )

    # Сохраняем текущий is_immune — нельзя временным щитом перебить постоянный иммунитет.
    stats = await chat_repo.get_chat_stats(db, target_id, message.chat.id)
    keep_immune = bool(stats.get("is_immune", False))

    until_dt = datetime.now() + td
    await mod_db.set_immunity(
        db, message.chat.id, target_id, keep_immune, until_dt.strftime("%Y-%m-%d %H:%M:%S")
    )
    await message.answer(
        f"🔰 <b>{target_name}</b> защищён от чистки на <b>{extra_args.split()[0]}</b>.\n"
        f"<i>Все защищённые: <code>бот кто рест</code> · Снять: <code>бот снять рест, @юзер</code></i>",
        parse_mode="HTML",
    )


@router.message(TextCmd(["снять рест", "снять защиту", "убрать щит", "убрать рест", "конец реста"]))
async def cmd_unprotect(
    message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0
):
    if message.chat.type == "private":
        return
    target_id, target_name, resolve_extra = await resolve_target(message, db, text_args)
    if resolve_extra == "error_user_not_found":
        uname = (text_args or "").split()[0]
        return await message.answer(
            f"❌ Пользователь <code>{safe_html(uname)}</code> не найден.",
            parse_mode="HTML",
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот снять рест, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )

    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await _check_target_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_shield", 4), developer_id, bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    await mod_db.set_immunity(db, message.chat.id, target_id, 0, None)
    await message.answer(
        f"❌ Защитный щит с <b>{target_name}</b> снят.", parse_mode="HTML"
    )


@router.message(TextCmd(["кто рест", "ресты", "кто в ресте", "список ресты"]))
async def cmd_who_rested(message: types.Message, db):
    if message.chat.type == "private":
        return
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.is_immune, s.immune_until "
        "FROM user_chat_stats s "
        "LEFT JOIN users u ON s.user_tg_id = u.user_tg_id "
        "WHERE s.chat_tg_id = ? AND s.is_left = FALSE "
        "AND (s.is_immune IS TRUE OR (s.immune_until IS NOT NULL AND s.immune_until > ?))",
        (message.chat.id, now_str),
    ) as cursor:
        rows = [dict(r) for r in await cursor.fetchall()]

    if rows:
        left_ids = await prune_ghosts(db, message.chat.id, [r["user_tg_id"] for r in rows])
        if left_ids:
            rows = [r for r in rows if r["user_tg_id"] not in left_ids]

    if not rows:
        return await message.answer("✅ Никто не в ресте и без иммунитета.", parse_mode="HTML")

    immune_lines, rested_lines = [], []
    for r in rows:
        uid = r["user_tg_id"]
        uname = safe_html(r["user_tg_username"] or f"ID {uid}")
        link = f'<a href="tg://user?id={uid}">{uname}</a>'
        if r["is_immune"]:
            immune_lines.append(f"├ 🛡 {link} — иммунитет ∞")
        else:
            dt = parse_dt(r["immune_until"])
            until_str = dt.strftime("%d.%m %H:%M") if dt else "?"
            rested_lines.append(f"├ 🕐 {link} — рест до {until_str}")

    lines = immune_lines + rested_lines
    if lines:
        lines[-1] = lines[-1].replace("├", "└")

    await message.answer(
        f"🛡 <b>Защита от чистки ({len(rows)}):</b>\n" + "\n".join(lines),
        parse_mode="HTML",
    )


# ==========================================
# НАСТРОЙКИ ЧАТА
# ==========================================
@router.message(TextCmd(["настройка щита", "щит новичка"]))
async def cmd_setshield(
    message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0
):
    if message.chat.type == "private":
        return
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 5, developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    args = text_args
    if not args or not args.isdigit():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот настройка щита, [дни]</code>\n"
            "└ <code>0</code> — выключить щит, <code>1+</code> — дней иммунитета для новичков",
            parse_mode="HTML",
        )

    days = int(args)
    await mod_db.update_chat_settings(db, message.chat.id, shield_duration_days=days)
    if days > 0:
        await message.answer(
            f"🔰 <b>Щит новичка включен!</b>\nИммунитет на {days} дней.",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ <b>Щит новичка выключен.</b>", parse_mode="HTML")


@router.message(TextCmd(["настройка чистки", "ранг чистки"]))
async def cmd_set_purge_rank(
    message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0
):
    if message.chat.type == "private":
        return
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 5, developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    args = text_args
    if not args or not args.isdigit():
        settings = await mod_db.get_chat_settings(db, message.chat.id)
        current = settings.get("purge_min_rank", 4)
        return await message.answer(
            f"ℹ️ <b>Настройка прав во время чистки</b>\n\n"
            f"Текущий минимальный ранг: <b>{roles.LOCAL_RANKS_MAP.get(current, current)}</b> ({current})\n\n"
            f"<code>бот настройка чистки, [ранг 0-6]</code>\n"
            f"└ Пользователи с рангом ≥ указанного сохраняют право писать во время чистки.\n"
            f"<i>Нельзя запретить писать тем, чей ранг выше вашего.</i>",
            parse_mode="HTML",
        )

    new_rank = int(args)
    if new_rank not in roles.LOCAL_RANKS_MAP:
        return await message.answer("❌ Ранг должен быть числом от 0 до 6.", parse_mode="HTML")

    initiator_stats = await chat_repo.get_chat_stats(db, message.from_user.id, message.chat.id)
    initiator_rank = initiator_stats.get("local_rank", 0)
    if message.from_user.id != developer_id and new_rank > initiator_rank:
        return await message.answer(
            "❌ Нельзя задать ранг выше вашего собственного.", parse_mode="HTML"
        )

    await mod_db.update_chat_settings(db, message.chat.id, purge_min_rank=new_rank)
    rank_name = roles.LOCAL_RANKS_MAP.get(new_rank, new_rank)
    await message.answer(
        f"✅ <b>Настройка обновлена!</b>\n"
        f"Во время чистки могут писать: <b>{rank_name}</b> и выше.",
        parse_mode="HTML",
    )


@router.message(TextCmd(["лимит варнов", "макс варнов"]))
async def cmd_setwarns(
    message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0
):
    if message.chat.type == "private":
        return
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 5, developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    args = text_args
    if not args or not args.isdigit():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот лимит варнов, [число]</code>",
            parse_mode="HTML",
        )

    limit = int(args)
    if limit < 1:
        return await message.answer("❌ Лимит должен быть больше 0.")
    await mod_db.update_chat_settings(db, message.chat.id, max_warnings=limit)
    await message.answer(
        f"⚠️ <b>Лимит обновлен!</b> Суд Присяжных после {limit} варнов.",
        parse_mode="HTML",
    )


# ==========================================
# КЛАССИЧЕСКАЯ МОДЕРАЦИЯ (БАНЫ, МУТЫ И СПИСКИ)
# ==========================================
@router.message(TextCmd(["бан", "заблокировать"]))
async def cmd_ban(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Ошибка:</b> Пользователь не найден в базе.", parse_mode="HTML"
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот бан, @юзер [причина]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_ban", 2), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await mod_db.log_moderation_action(
            db, message.chat.id, target_id, message.from_user.id, "ban"
        )
        target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
        initiator_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
        reason_text = (
            f"\n📝 <b>Причина:</b> {safe_html(extra_args)}" if extra_args else ""
        )
        detailed = f"🔨 <b>ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН</b>\n\n👤 {target_link} занесен в черный список.{reason_text}"
        short = f"✅ <b>{target_name}</b> заблокирован."
        await notify_action(bot, db, message.chat, initiator_link, detailed, short)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "❌ <b>Ошибка API:</b> Не могу заблокировать администратора.",
            parse_mode="HTML",
        )


@router.message(TextCmd(["разбан", "разблокировать"]))
async def cmd_unban(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Ошибка:</b> Пользователь не найден в базе.", parse_mode="HTML"
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот разбан, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_ban", 2), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        await mod_db.remove_ban_log(db, message.chat.id, target_id)
        target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
        initiator_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
        detailed = f"🕊 <b>ПОЛЬЗОВАТЕЛЬ РАЗБЛОКИРОВАН</b>\n\n👤 {target_link} исключен из черного списка."
        short = f"✅ <b>{target_name}</b> разблокирован."
        await notify_action(bot, db, message.chat, initiator_link, detailed, short)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "❌ <b>Ошибка API:</b> Не удалось разблокировать пользователя.",
            parse_mode="HTML",
        )


@router.message(TextCmd(["кик", "выгнать"]))
async def cmd_kick(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Ошибка:</b> Пользователь не найден.", parse_mode="HTML"
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот кик, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML"
        )
    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_kick", 1), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        await bot.ban_chat_member(message.chat.id, target_id)
        await bot.unban_chat_member(message.chat.id, target_id)
        await mod_db.log_moderation_action(
            db, message.chat.id, target_id, message.from_user.id, "kick"
        )
        target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
        initiator_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
        reason_text = (
            f"\n📝 <b>Причина:</b> {safe_html(extra_args)}" if extra_args else ""
        )
        detailed = f"👢 <b>ПОЛЬЗОВАТЕЛЬ ИСКЛЮЧЕН</b>\n\n👤 {target_link} был выгнан из чата.{reason_text}"
        short = f"✅ <b>{target_name}</b> исключен из чата."
        await notify_action(bot, db, message.chat, initiator_link, detailed, short)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "❌ <b>Ошибка API:</b> Не могу выгнать администратора.", parse_mode="HTML"
        )


@router.message(TextCmd(["мут", "заглушить"]))
async def cmd_mute(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Ошибка:</b> Пользователь не найден.", parse_mode="HTML"
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот мут, @юзер [10м/2ч/1д] [причина]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_mute", 1), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    mute_until, time_display, reason = None, "Навсегда", extra_args
    if extra_args:
        parts = extra_args.split(maxsplit=1)
        td = parse_time(parts[0])
        if td:
            mute_until = datetime.now() + td
            time_display = parts[0]
            reason = parts[1] if len(parts) > 1 else None

    try:
        permissions = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(
            message.chat.id, target_id, permissions=permissions, until_date=mute_until
        )
        await mod_db.log_moderation_action(
            db, message.chat.id, target_id, message.from_user.id, "mute"
        )
        target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
        initiator_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
        reason_text = f"\n📝 <b>Причина:</b> {safe_html(reason)}" if reason else ""
        detailed = f"🤐 <b>ПОЛЬЗОВАТЕЛЬ ЗАГЛУШЕН</b>\n\n👤 {target_link} теперь не может писать.\n⏳ <b>Срок:</b> {time_display}{reason_text}"
        short = f"✅ <b>{target_name}</b> заглушен ({time_display})."
        await notify_action(bot, db, message.chat, initiator_link, detailed, short)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "❌ <b>Ошибка API:</b> Не могу замутить администратора.", parse_mode="HTML"
        )


@router.message(TextCmd(["размут", "снять мут"]))
async def cmd_unmute(
    message: types.Message,
    db,
    bot: Bot,
    text_args: str = None,
    developer_id: int = 0,
):
    if message.chat.type == "private":
        return
    target_id, target_name, extra_args = await resolve_target(message, db, text_args)
    if extra_args == "error_user_not_found":
        return await message.answer(
            "❌ <b>Ошибка:</b> Пользователь не найден.", parse_mode="HTML"
        )
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот размут, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    _cs = await mod_db.get_chat_settings(db, message.chat.id)
    can_mod, err = await mod_service.check_mod_rights(
        db, message.chat.id, message.from_user.id, target_id,
        _cs.get("rank_mute", 1), developer_id=developer_id, bot_id=bot.id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
        )
        await bot.restrict_chat_member(
            message.chat.id, target_id, permissions=permissions
        )
        target_link = f'<a href="tg://user?id={target_id}">{target_name}</a>'
        initiator_link = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
        detailed = (
            f"🗣 <b>ПРАВА ВОССТАНОВЛЕНЫ</b>\n\n👤 {target_link} снова может общаться."
        )
        short = f"✅ С <b>{target_name}</b> снят мут."
        await notify_action(bot, db, message.chat, initiator_link, detailed, short)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "❌ <b>Ошибка API:</b> Не удалось восстановить права.", parse_mode="HTML"
        )


# ==========================================
# ОТКРЫТЬ / ЗАКРЫТЬ ЧАТ ЦЕЛИКОМ (бот +чат / бот -чат)
# ==========================================
_OPEN_PERMS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True,
)


@router.message(TextCmd(["-чат", "закрыть чат", "чат закрыть"]))
async def cmd_close_chat(message: types.Message, db, bot: Bot, developer_id: int = 0):
    """Закрывает чат: писать смогут только админы Telegram. Порог — rank_chat_lock."""
    if message.chat.type == "private":
        return
    settings = await mod_db.get_chat_settings(db, message.chat.id)
    req_rank = settings.get("rank_chat_lock", 4)
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, req_rank, developer_id=developer_id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
    except Exception:
        return await message.answer(
            "❌ Не удалось закрыть чат. Проверьте, что бот — администратор с правом «Изменение профиля чата».",
            parse_mode="HTML")
    actor = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
    await message.answer(
        f"🔒 <b>Чат закрыт</b> ({actor}).\nПисать могут только администраторы.\n"
        f"Открыть обратно: <code>бот +чат</code>",
        parse_mode="HTML")


@router.message(TextCmd(["+чат", "открыть чат", "чат открыть"]))
async def cmd_open_chat(message: types.Message, db, bot: Bot, developer_id: int = 0):
    """Открывает чат: возвращает всем право писать. Порог — rank_chat_lock."""
    if message.chat.type == "private":
        return
    settings = await mod_db.get_chat_settings(db, message.chat.id)
    req_rank = settings.get("rank_chat_lock", 4)
    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, req_rank, developer_id=developer_id)
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    try:
        await bot.set_chat_permissions(message.chat.id, _OPEN_PERMS)
    except Exception:
        return await message.answer(
            "❌ Не удалось открыть чат. Проверьте, что бот — администратор с правом «Изменение профиля чата».",
            parse_mode="HTML")
    actor = f'<a href="tg://user?id={message.from_user.id}">{safe_html(message.from_user.first_name)}</a>'
    await message.answer(
        f"🔓 <b>Чат открыт</b> ({actor})! Все снова могут писать. 🎉",
        parse_mode="HTML")


async def build_mod_list(
    db, chat_id: int, action: str, title: str, empty_text: str
) -> str:
    users_list = await mod_db.get_moderation_list(db, chat_id, action)
    if not users_list:
        return empty_text
    lines = [f"📋 <b>{title}</b>\n"]
    for u in users_list:
        name = safe_html(u["user_tg_username"] or f"ID {u['user_id']}")
        lines.append(f"""├ <a href="tg://user?id={u['user_id']}">{name}</a>""")
    if len(lines) > 1:
        lines[-1] = lines[-1].replace("├", "└")
    return "\n".join(lines)


@router.message(TextCmd(["баны", "черный список", "кто в бане"]))
async def cmd_bans_list(message: types.Message, db):
    await message.answer(
        await build_mod_list(
            db, message.chat.id, "ban", "ЧЕРНЫЙ СПИСОК (БАНЫ)", "🕊 Черный список пуст."
        ),
        parse_mode="HTML",
    )


@router.message(TextCmd(["кики", "выгнанные", "кто в кике"]))
async def cmd_kicks_list(message: types.Message, db):
    await message.answer(
        await build_mod_list(
            db,
            message.chat.id,
            "kick",
            "ИСТОРИЯ ИСКЛЮЧЕНИЙ (КИКИ)",
            "🕊 История киков пуста.",
        ),
        parse_mode="HTML",
    )


@router.message(TextCmd(["ушли", "вышли"]))
async def cmd_left_list(message: types.Message, db):
    left_users = await mod_db.get_left_users(db, message.chat.id)
    if not left_users:
        return await message.answer(
            "✅ В этом чате никто не покидал ряды!", parse_mode="HTML"
        )
    lines = ["🚶‍♂️ <b>ТЕ, КТО ПОКИНУЛ НАС</b>\n"]
    for u in left_users:
        name = safe_html(u["user_tg_username"] or f"ID {u['user_tg_id']}")
        lines.append(f"""├ <a href="tg://user?id={u['user_tg_id']}">{name}</a>""")
    if len(lines) > 1:
        lines[-1] = lines[-1].replace("├", "└")
    await message.answer("\n".join(lines), parse_mode="HTML")
