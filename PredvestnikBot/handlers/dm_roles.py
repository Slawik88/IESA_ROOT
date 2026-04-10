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
    clear_pending_role,
    get_channel_type,
    get_chat_settings,
    get_community_roles,
    get_pending_role,
    get_user_community_roles,
    revoke_community_role,
    set_pending_role,
)
import logging
_log = logging.getLogger(__name__)

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
    """Строить клавиатуру выбора роли с актуальным статусом.
    ✅ моя  |  🕐 зарезервирована (ждёт чата)  |  🔴 занята  |  🟢 свободная
    """
    roles = await get_community_roles()
    user_roles = await get_user_community_roles(user_id)
    user_pending = await get_pending_role(user_id)  # ожидающая роль или None

    user_role_names = {r["name"].lower() for r in user_roles}
    pending_lower = user_pending.lower() if user_pending else None

    buttons: list[list[InlineKeyboardButton]] = []
    for r in roles:
        emoji = r.get("emoji") or ""
        name = r["name"]
        display = f"{emoji} {name}".strip()
        is_mine = name.lower() in user_role_names
        is_pending_mine = pending_lower == name.lower()
        is_taken = r.get("holder_count", 0) > 0

        if is_mine:
            btn_text = f"✅ {display}"
            cb = f"dr:info:{name[:60]}"
        elif is_pending_mine:
            btn_text = f"🕐 {display}"
            cb = f"dr:pending:{name[:60]}"
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
        "🟢 — свободная роль, нажми чтобы зарезервировать\n"
        "🕐 — зарезервирована тобой, зайди в основной чат\n"
        "🔴 — занята другим участником\n"
        "✅ — твоя текущая роль\n\n"
        "<i>Каждая роль принадлежит только одному человеку.\n"
        "Роль активируется автоматически после вступления в основной чат.</i>"
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
    except Exception as _e:
        _log.debug("%s", _e)
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
    except Exception as _e:
        _log.debug("%s", _e)  # Пользователь не админ или нет прав — тихо пропускаем


# ─── Handlers ────────────────────────────────────────────────────────────────

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start_dm(message: Message) -> None:
    """/start в личном чате — краткое приветствие с навигационным меню."""
    user = message.from_user
    await message.answer(
        f"👋 Привет, <b>{html.escape(user.first_name or '')}</b>!\n\n"
        "Я — бот-помощник для Telegram-сообщества. Помогаю управлять чатами, "
        "защищать их от флуда и спама, а также веду внутреннюю экономику.\n\n"
        "Выбери раздел 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📜 Правила и выбор роли", callback_data="dr:start_rules")],
            [InlineKeyboardButton(text="❓ Возможности бота",     callback_data="dr:features")],
            [InlineKeyboardButton(text="⚙️ Настройка для администратора", callback_data="dr:admin_guide")],
        ]),
    )


@router.callback_query(F.data == "dr:home")
async def cb_dm_home(callback: CallbackQuery) -> None:
    """Главное меню ЛС."""
    user = callback.from_user
    try:
        await callback.message.edit_text(
            f"👋 Привет, <b>{html.escape(user.first_name or '')}</b>!\n\n"
            "Выбери раздел 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📜 Правила и выбор роли", callback_data="dr:start_rules")],
                [InlineKeyboardButton(text="❓ Возможности бота",     callback_data="dr:features")],
                [InlineKeyboardButton(text="⚙️ Настройка для администратора", callback_data="dr:admin_guide")],
            ]),
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


@router.callback_query(F.data == "dr:start_rules")
async def cb_start_rules(callback: CallbackQuery) -> None:
    """Показывает правила сообщества и кнопку выбора роли."""
    rules = await _get_rules_text()
    try:
        await callback.message.edit_text(
            f"<b>📜 Правила сообщества:</b>\n\n"
            f"{html.escape(rules)}\n\n"
            "<i>Ознакомься с правилами и выбери себе роль 👇</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎭 Выбрать роль", callback_data="dr:list")],
                [InlineKeyboardButton(text="◀️ Назад",        callback_data="dr:home")],
            ]),
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


@router.callback_query(F.data == "dr:features")
async def cb_features(callback: CallbackQuery) -> None:
    """Описание возможностей бота."""
    try:
        await callback.message.edit_text(
            "🤖 <b>Возможности бота</b>\n\n"
            "💰 <b>Экономика Мора</b>\n"
            "  Зарабатывай внутреннюю валюту за активность в чате: ежедневные "
            "бонусы, стрики, повышение уровня. Переводи Мору другим участникам, "
            "создавай займы, участвуй в аукционах.\n\n"
            "📈 <b>Облигации и биржа</b>\n"
            "  Покупай и продавай виртуальные ценные бумаги. Цены меняются каждые "
            "1–3 часа на основе случайного блуждания с возвратом к среднему. "
            "Прогрессивный налог на прибыль уходит в казну чата.\n\n"
            "🎰 <b>Казино и рулетка</b>\n"
            "  Ставки на красное/чёрное, чётное/нечётное, конкретные числа. "
            "Система pity: после 3+ проигрышей подряд вероятность выигрыша растёт.\n\n"
            "🛡 <b>Антифлуд 2.0</b>\n"
            "  Три уровня доверия (Новичок / Обычный / Доверенный) с раздельными "
            "лимитами для текста, медиа, стикеров и общей скорости. "
            "Настраивается прямо из мини-приложения без перезапуска бота.\n\n"
            "💑 <b>Социальная система</b>\n"
            "  Браки, питомцы, экспедиции, рейды на боссов. Сезонные рейтинги "
            "по Море, активности и рангу с таблицами лидеров.\n\n"
            "🎭 <b>Роли сообщества</b>\n"
            "  Уникальные роли (каждую может занять только один участник). "
            "Выбираются через это ЛС и автоматически активируются при вступлении в чат.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎭 Выбрать роль", callback_data="dr:list")],
                [InlineKeyboardButton(text="◀️ Назад",        callback_data="dr:home")],
            ]),
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


@router.callback_query(F.data == "dr:admin_guide")
async def cb_admin_guide(callback: CallbackQuery) -> None:
    """Краткая инструкция по настройке бота для администраторов."""
    try:
        await callback.message.edit_text(
            "⚙️ <b>Настройка бота — инструкция для администратора</b>\n\n"
            "<b>1. Добавь бота в группу</b>\n"
            "Пригласи бота в чат и выдай права администратора: "
            "<i>удаление сообщений</i> и <i>ограничение участников</i> (мьют).\n\n"
            "<b>2. Назначь владельца бота</b>\n"
            "В чате отправь команду:\n"
            "<code>/setrank @username Владелец</code>\n"
            "Только владелец видит полную панель управления.\n\n"
            "<b>3. Открой панель управления</b>\n"
            "Нажми кнопку бота под полем ввода → <b>⚙️ Панель</b>.\n"
            "Там доступны все настройки: Антифлуд, магазин, экономика, роли.\n\n"
            "<b>4. Настрой Антифлуд 2.0</b>\n"
            "Панель → <b>🛡 Антифлуд 2.0</b>.\n"
            "Выставь лимиты сообщений и время мьюта для каждого уровня доверия. "
            "По умолчанию используются безопасные значения — можно не трогать.\n\n"
            "<b>5. Настрой экономику</b>\n"
            "Панель → <b>💰 Магазин</b> — добавь предметы с ценами.\n"
            "Панель → <b>⚙️ Настройки</b> — множители Моры, бонусы за уровень.\n\n"
            "<b>6. Настрой роли (опционально)</b>\n"
            "Панель → <b>🎭 Роли</b> — создай роли с эмодзи и названиями. "
            "Участники выберут их через это ЛС бота.\n\n"
            "📌 <b>Полезные команды в чате:</b>\n"
            "  <code>/help</code> — список всех команд\n"
            "  <code>/mora</code> — баланс Моры\n"
            "  <code>/top</code> — таблица лидеров\n"
            "  <code>/stats</code> — статистика чата",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="dr:home")],
            ]),
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


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
    await callback.answer(f"✅ «{role_name}» — это твоя активная роль.", show_alert=True)


@router.callback_query(F.data.startswith("dr:pending:"))
async def cb_role_pending(callback: CallbackQuery) -> None:
    role_name = callback.data.split(":", 2)[2]
    await callback.answer(
        f"⏳ Роль «{role_name}» зарезервирована!\n"
        "Зайди в основной чат — она активируется автоматически.",
        show_alert=True,
    )


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
        except Exception as _e:
            _log.debug("%s", _e)
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
    """Назначить или зарезервировать роль.

    Если основной чат настроен и пользователь ещё не в нём — роль становится
    «ожидающей» (pending) и активируется автоматически при вступлении в чат.
    Если пользователь уже в основном чате — прямое назначение.
    Если основного чата нет — всегда прямое назначение.
    """
    user = callback.from_user
    first_name = user.first_name or str(user.id)

    # Сбросить старую pending-запись (если есть) перед новым выбором
    await clear_pending_role(user.id)

    main_chat_id = await get_channel_type("main")

    # Проверить, нахожится ли пользователь уже в основном чате
    already_in_chat = False
    if main_chat_id:
        try:
            cm = await bot.get_chat_member(main_chat_id, user.id)
            if cm.status in ("member", "administrator", "creator", "restricted"):
                already_in_chat = True
        except Exception as _e:
            _log.debug("%s", _e)

    # ─── Прямое назначение (в чате или основного чата нет) ───────────────
    if not main_chat_id or already_in_chat:
        lock = _get_role_lock(role_name)
        async with lock:
            result = await assign_community_role(user.id, role_name)

        if result == "not_found":
            await callback.answer("❌ Роль не найдена — список мог измениться.", show_alert=True)
            kb = await _build_role_keyboard(user.id)
            try:
                await callback.message.edit_text(_roles_caption(first_name), reply_markup=kb)
            except Exception as _e:
                _log.debug("%s", _e)
            return

        if result == "taken":
            await callback.answer(
                f"⚡ Роль «{role_name}» только что заняли! Выбери другую.",
                show_alert=True,
            )
            kb = await _build_role_keyboard(user.id)
            try:
                await callback.message.edit_text(_roles_caption(first_name), reply_markup=kb)
            except Exception as _e:
                _log.debug("%s", _e)
            return

        # Успешно назначено
        safe_role = html.escape(role_name)
        main_btn = await _main_chat_button(bot)
        rows: list[list[InlineKeyboardButton]] = []
        if main_btn:
            rows.append(main_btn)
        rows.append([InlineKeyboardButton(text="🔄 Сменить роль", callback_data="dr:list")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        try:
            await callback.message.edit_text(
                f"✅ <b>Роль «{safe_role}» активна!</b>\n\n"
                f"Добро пожаловать в сообщество 🎉",
                reply_markup=kb,
            )
        except Exception as _e:
            _log.debug("%s", _e)
        await _try_set_custom_title(bot, user.id, role_name)
        await callback.answer(f"✅ Роль «{role_name}» активирована!")
        return

    # ─── Ожидающее назначение (пользователь ещё не в основном чате) ──────
    await set_pending_role(user.id, role_name)
    safe_role = html.escape(role_name)
    main_btn = await _main_chat_button(bot)
    rows_p: list[list[InlineKeyboardButton]] = []
    if main_btn:
        rows_p.append(main_btn)
    rows_p.append([InlineKeyboardButton(text="🔄 Выбрать другую роль", callback_data="dr:list")])
    kb_p = InlineKeyboardMarkup(inline_keyboard=rows_p)
    try:
        await callback.message.edit_text(
            f"⏳ <b>Роль «{safe_role}» зарезервирована!</b>\n\n"
            "Зайди в основной чат — я автоматически активирую её для тебя.\n\n"
            "<i>Пока не зайдёшь в чат, роль видна другим как свободная.\n"
            "Первый вступивший в чат получает её.</i>",
            reply_markup=kb_p,
        )
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer(f"⏳ Роль «{role_name}» зарезервирована — зайди в чат!")
