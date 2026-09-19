from aiogram import Router, types, Bot

from infrastructure.repositories import routing
from infrastructure.repositories import chat as chat_db
from infrastructure.repositories.streak import get_chat_timezone
from bot.filters.text_commands import TextCmd
from services import moderation as mod_service
from services import roles
from services.utils import safe_html
from bot.keyboards.cta import answer_group_only

router = Router(name="routing_router")


async def _live_admin(bot: Bot, chat_id: int, user_id: int, developer_id: int = 0) -> bool:
    if developer_id and int(user_id) == int(developer_id):
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in {"creator", "administrator"} and (
        member.status == "creator" or bool(getattr(member, "can_manage_chat", False))
    )


async def _bot_can_serve(bot: Bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception:
        return False
    return member.status in {"creator", "administrator"}


# ==========================================
# ШАГ 1: ГЕНЕРАЦИЯ КОДА (В основном чате)
# ==========================================
@router.message(TextCmd(["привязать админ чат", "связать", "привязать"]))
async def cmd_bind_admin(message: types.Message, db, bot: Bot, developer_id: int = 0):
    if message.chat.type not in {"group", "supergroup"}:
        return await answer_group_only(message)

    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 5, developer_id=developer_id
    )
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")
    if not await _live_admin(bot, message.chat.id, message.from_user.id, developer_id):
        return await message.answer("❌ Нужны актуальные Telegram-права администратора в этом чате.")

    nonce = await routing.create_bind_request(db, message.chat.id, message.chat.title, message.from_user.id)
    command_to_copy = f"бот принять связь, {nonce}"

    text = (
        f"🔗 <b>ПРИВЯЗКА ЧАТА АДМИНИСТРАЦИИ</b>\n\n"
        f"Чтобы все отчёты о модерации отправлялись в админский чат, "
        f"скопируйте команду ниже и просто отправьте её туда:\n\n"
        f"<code>{command_to_copy}</code>\n\n"
        f"<i>⏳ Запрос действует 10 минут и подтвердить его может только создавший модератор.</i>"
    )
    await message.answer(text, parse_mode="HTML")


# ==========================================
# ШАГ 2: ПРИЕМ КОДА (В Админ-чате)
# ==========================================
@router.message(TextCmd(["принять связь", "accept bind"]))
async def cmd_accept_bind(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    if message.chat.type not in {"group", "supergroup"}:
        return await message.answer("❌ Чат администрации должен быть группой.")

    token = (text_args or "").strip()
    if not token:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот принять связь, [код]</code>",
            parse_mode="HTML",
        )

    if not await _live_admin(bot, message.chat.id, message.from_user.id, developer_id):
        return await message.answer("❌ Нужны актуальные Telegram-права администратора в этом чате.")
    if not await _bot_can_serve(bot, message.chat.id):
        return await message.answer("❌ Боту нужны права администратора в этом чате.")
    try:
        pending = await routing.peek_bind_request(
            db, nonce=token, creator_id=message.from_user.id,
        )
        if pending.main_chat_id == message.chat.id:
            return await message.answer("❌ Основной и админ-чат должны быть разными.")
        if not await _live_admin(bot, pending.main_chat_id, message.from_user.id, developer_id):
            return await message.answer("❌ Права в основном чате больше не подтверждены.")
        # Repository verifies creator identity and atomically writes the route.
        request = await routing.consume_bind_request(
            db, nonce=token, creator_id=message.from_user.id, admin_chat_id=message.chat.id,
        )
    except routing.BindRequestError as exc:
        return await message.answer(f"❌ <b>Ошибка:</b> {safe_html(str(exc))}", parse_mode="HTML")
    main_chat_id = request.main_chat_id
    main_chat_title = request.main_chat_title

    await message.answer(
        f"✅ <b>СИСТЕМА УСПЕШНО НАСТРОЕНА!</b>\n\n"
        f"Этот чат теперь является пунктом модерации для:\n"
        f"🏘 <b>{main_chat_title}</b>\n\n"
        f"<i>Теперь все баны и отчёты будут поступать сюда.</i>",
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            main_chat_id,
            "🛡 <b>БЕЗОПАСНОСТЬ УСИЛЕНА!</b>\n\nЧат администрации успешно привязан. Журналы логирования перенаправлены.",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ==========================================
# ЧАСОВОЙ ПОЯС ЧАТА — ПЕРЕЕХАЛ (БЛОК 36.4)
# ==========================================
# Дубль-хендлер удалён 2026-07-07: команда живёт в bot/handlers/chat_settings.py
# (cmd_set_timezone), алиасы «часовой пояс чата»/«timezone чата»/«пояс чата»
# перенесены туда же. Здесь остался только вывод текущего пояса в «инфо чата».


# ==========================================
# ИНФОРМАЦИЯ О ПРИВЯЗКЕ
# ==========================================
@router.message(TextCmd(["инфо чата", "привязки"]))
async def cmd_chat_info(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)

    admin_chat_id = await routing.get_admin_chat(db, message.chat.id)
    status = f"✅ Привязан (ID: <code>{admin_chat_id}</code>)" if admin_chat_id else "❌ Не привязан"

    admins = await chat_db.get_chat_admins(db, message.chat.id)
    member_count = await chat_db.get_chat_member_count(db, message.chat.id)

    rank_groups: dict[int, list[str]] = {}
    for a in admins:
        name = safe_html(a['user_tg_username'] or f"ID {a['user_tg_id']}")
        link = f"""<a href="tg://user?id={a['user_tg_id']}">{name}</a>"""
        rank_groups.setdefault(a['local_rank'], []).append(link)

    admin_lines = []
    for rank_id in sorted(rank_groups.keys(), reverse=True):
        rank_name = roles.LOCAL_RANKS_MAP.get(rank_id, f"Ранг {rank_id}")
        admin_lines.append(f"├ {rank_name}: {' · '.join(rank_groups[rank_id])}")
    if admin_lines:
        admin_lines[-1] = admin_lines[-1].replace("├", "└", 1)
    admin_section = "\n".join(admin_lines) if admin_lines else "└ <i>Не назначены</i>"

    tz_offset = await get_chat_timezone(db, message.chat.id)
    tz_sign = "+" if tz_offset >= 0 else ""

    text = (
        f"ℹ️ <b>ИНФОРМАЦИЯ О ЧАТЕ</b>\n\n"
        f"Название: <b>{message.chat.title}</b>\n"
        f"ID: <code>{message.chat.id}</code>\n\n"
        f"🕐 <b>Часовой пояс:</b> <code>UTC{tz_sign}{tz_offset}</code>\n"
        f"<i>Изменить: бот часовой пояс чата, UTC±N</i>\n\n"
        f"🛡 <b>Отчёты модерации:</b>\n"
        f"└ {status}\n\n"
        f"👑 <b>Администрация:</b>\n"
        f"{admin_section}\n\n"
        f"👥 <b>Обычных участников:</b> <code>{member_count}</code>"
    )
    await message.answer(text, parse_mode="HTML")
