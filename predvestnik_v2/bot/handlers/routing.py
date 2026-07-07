from aiogram import Router, types, Bot

from infrastructure.repositories import routing
from infrastructure.repositories import chat as chat_db
from infrastructure.repositories.streak import get_chat_timezone
from bot.filters.text_commands import TextCmd
from services import moderation as mod_service
from services import roles
from services.utils import safe_html

router = Router(name="routing_router")


# ==========================================
# ШАГ 1: ГЕНЕРАЦИЯ КОДА (В основном чате)
# ==========================================
@router.message(TextCmd(["привязать админ чат", "связать", "привязать"]))
async def cmd_bind_admin(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return await message.answer("❌ Эта команда только для групп.")

    can_mod, err = await mod_service.check_admin_rights(
        db, message.chat.id, message.from_user.id, 5, developer_id=developer_id
    )
    if not can_mod:
        return await message.answer(err, parse_mode="HTML")

    token = await routing.create_bind_token(db, message.chat.id, message.chat.title)
    command_to_copy = f"бот принять связь, {token}"

    text = (
        f"🔗 <b>ПРИВЯЗКА ЧАТА АДМИНИСТРАЦИИ</b>\n\n"
        f"Чтобы все отчёты о модерации отправлялись в админский чат, "
        f"скопируйте команду ниже и просто отправьте её туда:\n\n"
        f"<code>{command_to_copy}</code>\n\n"
        f"<i>⏳ Команда является одноразовой.</i>"
    )
    await message.answer(text, parse_mode="HTML")


# ==========================================
# ШАГ 2: ПРИЕМ КОДА (В Админ-чате)
# ==========================================
@router.message(TextCmd(["принять связь", "accept bind"]))
async def cmd_accept_bind(message: types.Message, db, bot: Bot, text_args: str = None):
    if message.chat.type == "private":
        return await message.answer("❌ Чат администрации должен быть группой.")

    token = (text_args or "").strip()
    if not token:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот принять связь, [код]</code>",
            parse_mode="HTML",
        )

    bind_data = await routing.get_and_delete_token(db, token)
    if not bind_data:
        return await message.answer(
            "❌ <b>Ошибка:</b> Код недействителен или уже был использован.",
            parse_mode="HTML",
        )

    main_chat_id = bind_data['main_chat_id']
    main_chat_title = bind_data['main_chat_title']
    admin_chat_id = message.chat.id

    await routing.bind_admin_chat(db, main_chat_id, admin_chat_id)

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
        return

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
