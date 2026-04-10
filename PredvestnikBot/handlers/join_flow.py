"""
Система вступления по тегам (Join Flow).

Для вступления:
  1. Администратор genеrирует ссылку командой: бот ссылка вступления
     → Возвращает: t.me/IIIPredvestnikIIIBot?start=join_{chat_id}
  2. Пользователь переходит по ссылке → открывается ЛС бота:
     → Бот уведомляет адмканал: «Пользователь X открыл ссылку»
     → Показывает правила + список тегов (свободные/занятые)
  3. Пользователь выбирает тег → подтверждает → создаётся join_request
     → Бот отправляет уведомление в адмканал с кнопками ✅ / ❌ / ⏳
  4. Администратор нажимает ✅ Принять:
     → Бот создаёт одноразовую ссылку (member_limit=1)
     → Отправляет ссылку пользователю в ЛС
     → Редактирует уведомление в адмканале → «✅ Одобрено»
  5. Администратор нажимает ❌ Отклонить:
     → Пользователь получает уведомление об отклонении
     → Уведомление в адмканале обновляется → «❌ Отклонено»
  6. Администратор нажимает ⏳ Отложить:
     → Уведомление в адмканале обновляется → «⏳ Отложено»
  7. Пользователь вступает по одноразовой ссылке:
     → on_join в extras.py присваивает тег автоматически
"""
import html
import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    create_join_request,
    get_chat_settings,
    get_join_request,
    get_tag_definitions,
    get_user_active_join_request,
    set_chat_tag,
    update_join_request,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import user_mention

router = Router()
log = logging.getLogger(__name__)

_JOIN_LINK_PREFIX = "join_"
_BOT_USERNAME = "IIIPredvestnikIIIBot"


# ─── Helper: build join deep link ────────────────────────────────────────────

def _make_join_link(chat_id: int) -> str:
    return f"https://t.me/{_BOT_USERNAME}?start={_JOIN_LINK_PREFIX}{chat_id}"


# ─── Helper: build tags keyboard ─────────────────────────────────────────────

def _build_tags_keyboard(chat_id: int, tags: list[dict]) -> InlineKeyboardMarkup:
    """Free tags are clickable; occupied tags are shown as disabled."""
    buttons: list[list[InlineKeyboardButton]] = []
    for tag in tags:
        holder = tag.get("holder_user_id")
        emoji = (tag.get("emoji") or "").strip()
        name = tag["name"]
        tag_id = tag["id"]
        color_dot = "🔴" if holder else "🟢"
        label = f"{color_dot} {emoji} {name}".strip()
        if holder:
            label += " (занят)"
            buttons.append([InlineKeyboardButton(text=label, callback_data="jf:noop")])
        else:
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"jf:pick:{tag_id}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"jf:cancel:{chat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Chat command: бот ссылка вступления (co_owner+) ─────────────────────────

@router.message(BotCommand("ссылка вступления"), RankFilter("co_owner"))
async def cmd_join_link(message: Message):
    """Сгенерировать ссылку вступления для текущего чата."""
    link = _make_join_link(message.chat.id)
    await message.answer(
        f"🔗 <b>Ссылка для вступления в чат:</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Поделитесь этой ссылкой с желающими вступить. "
        "Бот покажет им правила и доступные теги.",
        parse_mode="HTML",
    )


# ─── Deep link: /start join_{chat_id} ────────────────────────────────────────

def _is_join_payload(message: Message) -> bool:
    """Pre-filter: only fire for /start join_{digits} deep links."""
    if not message.text:
        return False
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return False
    return parts[1].startswith(_JOIN_LINK_PREFIX)


@router.message(CommandStart(), F.chat.type == "private", _is_join_payload)
async def cmd_start_join(message: Message, bot: Bot) -> None:
    """Handle /start join_{chat_id} deep link in DM."""
    payload = message.text.split(maxsplit=1)[1]
    try:
        chat_id = int(payload[len(_JOIN_LINK_PREFIX):])
    except ValueError:
        return  # malformed payload

    user = message.from_user
    user_id = user.id

    # Check if user is already a member
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in ("left", "kicked", "banned"):
            await message.answer(
                "✅ Ты уже состоишь в этом сообществе!\n\n"
                "Возвращайся в чат — ждём тебя 😊",
            )
            return
    except Exception:
        pass  # Can't check — proceed anyway

    # Notify admin channel that user opened the link
    from database.db import get_admin_chat_for
    admin_chat_id = get_admin_chat_for(chat_id)
    if admin_chat_id:
        try:
            chat_info = await bot.get_chat(chat_id)
            chat_title = html.escape(getattr(chat_info, "title", "") or str(chat_id))
        except Exception:
            chat_title = str(chat_id)
        try:
            await bot.send_message(
                admin_chat_id,
                f"🔔 <b>Открыта ссылка вступления</b>\n\n"
                f"👤 {user_mention(user_id, user.full_name)} открыл(а) ссылку вступления "
                f"в <b>{chat_title}</b>.\n"
                f"Заявка ещё не отправлена.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Check existing active request
    existing = await get_user_active_join_request(user_id, chat_id)
    if existing:
        status_map = {
            "pending":   "⏳ Ожидает рассмотрения",
            "accepted":  "✅ Одобрена! Проверь эти личные сообщения — там должна быть ссылка.",
            "postponed": "🕐 Отложена. Ожидай решения администраторов.",
        }
        status_text = status_map.get(existing["status"], existing["status"])
        await message.answer(
            f"ℹ️ <b>У тебя уже есть заявка на вступление</b>\n\n"
            f"Статус: {status_text}\n\n"
            "Дождись решения по текущей заявке перед подачей новой.",
            parse_mode="HTML",
        )
        return

    # Fetch tag definitions and rules
    tags = await get_tag_definitions(chat_id)
    free_tags = [t for t in tags if not t.get("holder_user_id")]

    try:
        settings = await get_chat_settings(chat_id)
        rules_text = (settings and settings.get("rules_text")) or "Правила сообщества ещё не установлены."
    except Exception:
        rules_text = "Правила сообщества ещё не установлены."

    rules_block = f"📜 <b>Правила сообщества:</b>\n\n{html.escape(rules_text)}\n\n"

    if not tags:
        await message.answer(
            rules_block + "К сожалению, в этом сообществе нет тегов. Обратись к администратору.",
            parse_mode="HTML",
        )
        return

    if not free_tags:
        await message.answer(
            rules_block + "Сейчас все теги заняты. Попробуй позже или обратись к администратору.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        rules_block
        + "Ниже показаны все теги сообщества. 🟢 свободен, 🔴 занят.\n"
        "Выбери тег, который хочешь занять при вступлении 👇",
        parse_mode="HTML",
        reply_markup=_build_tags_keyboard(chat_id, tags),
    )


# ─── jf:noop — click on occupied tag ─────────────────────────────────────────

@router.callback_query(F.data == "jf:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer("Этот тег уже занят.", show_alert=False)


# ─── jf:cancel:{chat_id} ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jf:cancel:"))
async def cb_cancel(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text("❌ Вступление отменено.")
    except Exception:
        pass
    await callback.answer()


# ─── jf:pick:{tag_def_id} ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jf:pick:"))
async def cb_pick_tag(callback: CallbackQuery) -> None:
    tag_def_id = int(callback.data.split(":")[2])

    # Find this tag among all definitions
    # We need chat_id — get it from the message context or by looking up all defs.
    # Easiest: scan tag definitions by id via a targeted lookup.
    from database.db import postgres_connect
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT d.*, ct.user_id AS holder_user_id FROM chat_tag_definitions d "
            "LEFT JOIN chat_tags ct ON ct.tag = d.name AND ct.chat_id = d.chat_id "
            "WHERE d.id = ?",
            (tag_def_id,),
        ) as c:
            tag = await c.fetchone()

    if not tag:
        await callback.answer("Тег не найден.", show_alert=True)
        return

    tag = dict(tag)
    chat_id = tag["chat_id"]

    if tag.get("holder_user_id"):
        # Tag was claimed while the user was looking
        tags = await get_tag_definitions(chat_id)
        await callback.answer("Этот тег уже занят. Выбери другой.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_build_tags_keyboard(chat_id, tags)
            )
        except Exception:
            pass
        return

    emoji = (tag.get("emoji") or "").strip()
    name = tag["name"]
    description = (tag.get("description") or "").strip()
    desc_line = f"\n📝 {html.escape(description)}" if description else ""

    await callback.message.edit_text(
        f"Ты выбрал(а) тег: <b>{emoji} {html.escape(name)}</b>{desc_line}\n\n"
        "Подтверди выбор — заявка будет отправлена администраторам на рассмотрение.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"jf:confirm:{tag_def_id}")],
            [InlineKeyboardButton(text="◀️ К списку тегов", callback_data=f"jf:back:{chat_id}")],
        ]),
    )
    await callback.answer()


# ─── jf:back:{chat_id} ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jf:back:"))
async def cb_back_to_tags(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":")[2])
    tags = await get_tag_definitions(chat_id)
    try:
        await callback.message.edit_text(
            "Ниже показаны все теги сообщества. 🟢 свободен, 🔴 занят.\n"
            "Выбери тег, который хочешь занять при вступлении 👇",
            reply_markup=_build_tags_keyboard(chat_id, tags),
        )
    except Exception:
        pass
    await callback.answer()


# ─── jf:confirm:{tag_def_id} ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jf:confirm:"))
async def cb_confirm_tag(callback: CallbackQuery, bot: Bot) -> None:
    tag_def_id = int(callback.data.split(":")[2])

    from database.db import postgres_connect
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT d.*, ct.user_id AS holder_user_id FROM chat_tag_definitions d "
            "LEFT JOIN chat_tags ct ON ct.tag = d.name AND ct.chat_id = d.chat_id "
            "WHERE d.id = ?",
            (tag_def_id,),
        ) as c:
            tag = await c.fetchone()

    if not tag:
        await callback.answer("Тег не найден.", show_alert=True)
        return

    tag = dict(tag)
    chat_id = tag["chat_id"]
    tag_name = tag["name"]
    user = callback.from_user
    user_id = user.id

    # Duplicate request guard
    existing = await get_user_active_join_request(user_id, chat_id)
    if existing:
        await callback.answer("У тебя уже есть активная заявка в это сообщество.", show_alert=True)
        return

    if tag.get("holder_user_id"):
        # Race: tag was taken
        tags = await get_tag_definitions(chat_id)
        await callback.answer("Тег занят — выбери другой.", show_alert=True)
        try:
            await callback.message.edit_text(
                "Упс, этот тег заняли пока ты думал(а) 😅\nВыбери другой:",
                parse_mode="HTML",
                reply_markup=_build_tags_keyboard(chat_id, tags),
            )
        except Exception:
            pass
        return

    # Create the join request
    req_id = await create_join_request(chat_id, user_id, tag_name)

    # Confirm to user
    emoji = (tag.get("emoji") or "").strip()
    try:
        await callback.message.edit_text(
            f"✅ <b>Заявка отправлена!</b>\n\n"
            f"Тег: <b>{emoji} {html.escape(tag_name)}</b>\n\n"
            "Администраторы рассмотрят заявку и пришлют ответ в этот чат.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Заявка отправлена!")

    # Build admin notification
    from database.db import get_admin_chat_for
    admin_chat_id = get_admin_chat_for(chat_id) or chat_id

    try:
        chat_info = await bot.get_chat(chat_id)
        chat_title = html.escape(getattr(chat_info, "title", "") or str(chat_id))
    except Exception:
        chat_title = str(chat_id)

    username_str = f"@{user.username}" if user.username else "нет @username"
    admin_text = (
        f"📋 <b>Новая заявка на вступление</b>\n\n"
        f"👤 {user_mention(user_id, user.full_name)} ({username_str})\n"
        f"🏷 Тег: <b>{emoji} {html.escape(tag_name)}</b>\n"
        f"🏠 Чат: <b>{chat_title}</b>\n"
        f"🕐 {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        f"Заявка #{req_id}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять",   callback_data=f"jfadm:accept:{req_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"jfadm:reject:{req_id}"),
        ],
        [InlineKeyboardButton(text="⏳ Отложить", callback_data=f"jfadm:postpone:{req_id}")],
    ])

    try:
        await bot.send_message(
            admin_chat_id,
            admin_text,
            parse_mode="HTML",
            reply_markup=admin_kb,
        )
    except Exception as exc:
        log.warning("join_flow: could not send admin notification for req #%d: %s", req_id, exc)


# ─── jfadm:accept:{req_id} ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jfadm:accept:"))
async def cb_admin_accept(callback: CallbackQuery, bot: Bot) -> None:
    req_id = int(callback.data.split(":")[2])
    req = await get_join_request(req_id)
    if not req:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    if req["status"] != "pending":
        await callback.answer(f"Заявка уже обработана: {req['status']}.", show_alert=True)
        return

    admin = callback.from_user
    chat_id = req["chat_id"]
    user_id = req["user_id"]
    tag_name = req.get("tag_name", "")

    # Create one-time invite link
    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id,
            member_limit=1,
            name=f"join_req_{req_id}",
        )
        invite_link = link_obj.invite_link
    except Exception as exc:
        log.warning("join_flow: invite link creation failed for req #%d: %s", req_id, exc)
        await callback.answer("Не удалось создать ссылку-приглашение.", show_alert=True)
        return

    # Update DB
    await update_join_request(req_id, "accepted", admin.id, invite_link=invite_link)

    # Send invite to user in DM
    try:
        await bot.send_message(
            user_id,
            f"🎉 <b>Ваша заявка одобрена!</b>\n\n"
            f"Тег: <b>{html.escape(tag_name)}</b>\n\n"
            f"Вступайте по ссылке (только для вас, одноразовая):\n"
            f"<a href=\"{invite_link}\">{invite_link}</a>\n\n"
            "После вступления тег будет присвоен автоматически.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.warning("join_flow: could not DM invite to user %d: %s", user_id, exc)

    # Update admin notification
    admin_name = html.escape(admin.full_name or "Администратор")
    try:
        old = html.escape(callback.message.text or "")
        await callback.message.edit_text(old + f"\n\n✅ <b>Одобрено</b> — {admin_name}", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("✅ Заявка одобрена, ссылка отправлена пользователю.")


# ─── jfadm:reject:{req_id} ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jfadm:reject:"))
async def cb_admin_reject(callback: CallbackQuery, bot: Bot) -> None:
    req_id = int(callback.data.split(":")[2])
    req = await get_join_request(req_id)
    if not req:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    if req["status"] != "pending":
        await callback.answer(f"Заявка уже обработана: {req['status']}.", show_alert=True)
        return

    admin = callback.from_user
    await update_join_request(req_id, "rejected", admin.id)

    # Notify user
    tag_name = req.get("tag_name", "")
    try:
        await bot.send_message(
            req["user_id"],
            f"❌ <b>Ваша заявка отклонена.</b>\n\n"
            f"Тег: <b>{html.escape(tag_name)}</b>\n\n"
            "Если есть вопросы — свяжитесь с администратором сообщества.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    admin_name = html.escape(admin.full_name or "Администратор")
    try:
        old = html.escape(callback.message.text or "")
        await callback.message.edit_text(old + f"\n\n❌ <b>Отклонено</b> — {admin_name}", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("❌ Заявка отклонена.")


# ─── jfadm:postpone:{req_id} ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("jfadm:postpone:"))
async def cb_admin_postpone(callback: CallbackQuery, bot: Bot) -> None:
    req_id = int(callback.data.split(":")[2])
    req = await get_join_request(req_id)
    if not req:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    if req["status"] != "pending":
        await callback.answer(f"Заявка уже обработана: {req['status']}.", show_alert=True)
        return

    admin = callback.from_user
    await update_join_request(req_id, "postponed", admin.id)

    admin_name = html.escape(admin.full_name or "Администратор")
    # Keep Accept/Reject buttons, remove Postpone
    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять",   callback_data=f"jfadm:accept:{req_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"jfadm:reject:{req_id}"),
        ],
    ])
    try:
        old = html.escape(callback.message.text or "")
        await callback.message.edit_text(old + f"\n\n⏳ <b>Отложено</b> — {admin_name}", parse_mode="HTML", reply_markup=new_kb)
    except Exception:
        pass
    await callback.answer("⏳ Заявка отложена.")
