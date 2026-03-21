"""
Онбординг в личных сообщениях (DM).

Поток:
  1. /start в ЛС → бот показывает правила сообщества + кнопку «Выбрать роль»
  2. Нажатие → список ролей: 🟢 свободная / 🔴 занята / ✅ твоя
  3. Выбор роли → блокировка (asyncio.Lock) → проверка → назначение
  4. Если роль уже занята (гонка) → сообщение + обновлённый список
  5. Если у пользователя уже была роль → уточнение замены
  6. После выбора → ссылка на основной чат
"""
import asyncio
import html

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    assign_community_role,
    get_channel_type,
    get_chat_settings,
    get_community_roles,
    get_user_community_roles,
    revoke_community_role,
)

router = Router()

# ─── Блокировки для защиты от гонки при выборе одной роли двумя людьми ─────
_role_locks: dict[str, asyncio.Lock] = {}


def _get_role_lock(role_name: str) -> asyncio.Lock:
    if role_name not in _role_locks:
        _role_locks[role_name] = asyncio.Lock()
    return _role_locks[role_name]


# ─── Вспомогательные функции ─────────────────────────────────────────────────

async def _get_rules_text() -> str:
    """Получить текст правил из канала типа 'rules'."""
    chat_id = await get_channel_type("rules")
    if chat_id:
        settings = await get_chat_settings(chat_id)
        if settings and settings.get("rules_text"):
            return settings["rules_text"]
    return "Правила сообщества ещё не установлены. Обратись к администратору."


async def _build_role_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Строить клавиатуру выбора роли с актуальным статусом (свободна / занята / моя)."""
    roles = await get_community_roles()
    user_roles = await get_user_community_roles(user_id)
    user_role_names = {r["name"].lower() for r in user_roles}

    buttons: list[list[InlineKeyboardButton]] = []
    for r in roles:
        emoji = r.get("emoji") or ""
        name = r["name"]
        display = f"{emoji} {name}".strip()
        is_mine = name.lower() in user_role_names
        is_taken = r.get("holder_count", 0) > 0

        if is_mine:
            btn_text = f"✅ {display}"
            cb = f"dr:info:{name[:60]}"
        elif is_taken:
            btn_text = f"🔴 {display}"
            cb = f"dr:taken:{name[:60]}"
        else:
            btn_text = f"🟢 {display}"
            cb = f"dr:pick:{name[:60]}"

        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=cb)])

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="dr:refresh"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _roles_caption(first_name: str) -> str:
    return (
        f"🎭 <b>Выбор роли, {html.escape(first_name)}</b>\n\n"
        "🟢 — свободная роль, нажми чтобы взять\n"
        "🔴 — занята другим участником\n"
        "✅ — твоя текущая роль\n\n"
        "<i>Каждая роль принадлежит только одному человеку.\n"
        "Нажми «Обновить список» чтобы увидеть актуальный статус.</i>"
    )


async def _main_chat_button(bot: Bot) -> list[InlineKeyboardButton] | None:
    """Создать кнопку перехода в основной чат (если настроен channel_type = 'main')."""
    chat_id = await get_channel_type("main")
    if not chat_id:
        return None
    try:
        chat = await bot.get_chat(chat_id)
        url = None
        if getattr(chat, "invite_link", None):
            url = chat.invite_link
        elif getattr(chat, "username", None):
            url = f"https://t.me/{chat.username}"
        if url:
            return [InlineKeyboardButton(text="💬 Перейти в основной чат", url=url)]
    except Exception:
        pass
    return None


async def _try_set_custom_title(bot: Bot, user_id: int, title: str) -> None:
    """Попробовать установить роль как custom title в основном чате.
    Работает только если пользователь — администратор чата.
    """
    chat_id = await get_channel_type("main")
    if not chat_id:
        return
    title_short = title[:16]  # Telegram limit
    try:
        await bot.set_chat_administrator_custom_title(chat_id, user_id, title_short)
    except Exception:
        pass  # Пользователь не админ или нет прав — тихо пропускаем


# ─── Handlers ────────────────────────────────────────────────────────────────

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start_dm(message: Message) -> None:
    """/start в личном чате — показывает правила и кнопку выбора роли."""
    user = message.from_user
    rules = await _get_rules_text()

    await message.answer(
        f"👋 Привет, <b>{html.escape(user.first_name or '')}</b>!\n\n"
        f"<b>📜 Правила нашего сообщества:</b>\n\n"
        f"{html.escape(rules)}\n\n"
        "<i>Ознакомься с правилами и выбери себе роль 👇</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎭 Выбрать роль", callback_data="dr:list"),
        ]]),
    )


@router.callback_query(F.data == "dr:list")
async def cb_role_list(callback: CallbackQuery) -> None:
    roles = await get_community_roles()
    if not roles:
        await callback.answer(
            "Роли ещё не созданы. Обратись к администратору.", show_alert=True
        )
        return

    kb = await _build_role_keyboard(callback.from_user.id)
    first_name = callback.from_user.first_name or str(callback.from_user.id)
    try:
        await callback.message.edit_text(_roles_caption(first_name), reply_markup=kb)
    except Exception:
        await callback.message.answer(_roles_caption(first_name), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "dr:refresh")
async def cb_role_refresh(callback: CallbackQuery) -> None:
    kb = await _build_role_keyboard(callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer("✅ Список обновлён")
    except Exception:
        await callback.answer("Список уже актуален")


@router.callback_query(F.data.startswith("dr:taken:"))
async def cb_role_taken(callback: CallbackQuery) -> None:
    role_name = callback.data.split(":", 2)[2]
    await callback.answer(
        f"❌ Роль «{role_name}» уже занята другим участником.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("dr:info:"))
async def cb_role_mine(callback: CallbackQuery) -> None:
    role_name = callback.data.split(":", 2)[2]
    await callback.answer(f"✅ «{role_name}» — это твоя роль.", show_alert=True)


@router.callback_query(F.data.startswith("dr:pick:"))
async def cb_role_pick(callback: CallbackQuery, bot: Bot) -> None:
    user = callback.from_user
    role_name = callback.data.split(":", 2)[2]

    # Если у пользователя уже есть роль — спросить подтверждение замены
    current_roles = await get_user_community_roles(user.id)
    if current_roles:
        current_display = ", ".join(
            f"{r.get('emoji', '')} {r['name']}".strip() for r in current_roles
        )
        safe_curr = html.escape(current_display)
        safe_new = html.escape(role_name)
        try:
            await callback.message.edit_text(
                f"⚠️ <b>У тебя уже есть роль: {safe_curr}</b>\n\n"
                f"Заменить на <b>{safe_new}</b>?\n\n"
                f"<i>Старая роль освободится и станет доступна другим.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Да, заменить",
                            callback_data=f"dr:confirm:{role_name[:60]}",
                        ),
                        InlineKeyboardButton(text="❌ Оставить", callback_data="dr:list"),
                    ],
                ]),
            )
        except Exception:
            pass
        await callback.answer()
        return

    await _do_assign_role(callback, bot, role_name)


@router.callback_query(F.data.startswith("dr:confirm:"))
async def cb_role_confirm(callback: CallbackQuery, bot: Bot) -> None:
    user = callback.from_user
    role_name = callback.data.split(":", 2)[2]

    # Снять все текущие роли перед заменой
    current_roles = await get_user_community_roles(user.id)
    for r in current_roles:
        await revoke_community_role(user.id, r["name"])

    await _do_assign_role(callback, bot, role_name)


async def _do_assign_role(callback: CallbackQuery, bot: Bot, role_name: str) -> None:
    """Назначить роль с блокировкой от гонки условий."""
    user = callback.from_user
    lock = _get_role_lock(role_name)

    async with lock:
        result = await assign_community_role(user.id, role_name)

    first_name = user.first_name or str(user.id)

    if result == "not_found":
        await callback.answer("❌ Роль не найдена — список мог измениться.", show_alert=True)
        kb = await _build_role_keyboard(user.id)
        try:
            await callback.message.edit_text(_roles_caption(first_name), reply_markup=kb)
        except Exception:
            pass
        return

    if result == "taken":
        # Гонка условий — роль взяли пока ты выбирал
        await callback.answer(
            f"⚡ Роль «{role_name}» только что заняли! Выбери другую.",
            show_alert=True,
        )
        kb = await _build_role_keyboard(user.id)
        try:
            await callback.message.edit_text(_roles_caption(first_name), reply_markup=kb)
        except Exception:
            pass
        return

    # Успешно назначено (result == 'ok' or 'already')
    safe_role = html.escape(role_name)
    main_btn = await _main_chat_button(bot)
    rows: list[list[InlineKeyboardButton]] = []
    if main_btn:
        rows.append(main_btn)
    rows.append([InlineKeyboardButton(text="🔄 Сменить роль", callback_data="dr:list")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(
            f"✅ <b>Ты выбрал роль: {safe_role}!</b>\n\n"
            f"Добро пожаловать в сообщество 🎉\n\n"
            f"<i>Чтобы сменить роль — нажми кнопку ниже.</i>",
            reply_markup=kb,
        )
    except Exception:
        pass

    # Попробовать установить роль как Telegram custom title (если пользователь — админ чата)
    await _try_set_custom_title(bot, user.id, role_name)
    await callback.answer(f"✅ Роль «{role_name}» выбрана!")
