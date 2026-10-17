from aiogram import Bot, Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories import chat_module_audit
from infrastructure.repositories import chat_settings_audit, chat_settings_reset
from infrastructure.repositories import routing
from infrastructure.repositories.streak import get_chat_timezone, set_chat_timezone
from services import roles
from services.utils import check_callback_owner
from core.constants import CHAT_TIMEZONE_MIN, CHAT_TIMEZONE_MAX
from bot.keyboards.cta import answer_group_only
from core.chat_modules import CHAT_MODULES
from bot.handlers import _chat_module_ui as module_ui
from bot.middlewares.module_check_mw import bot_silence_invalidate

router = Router(name="chat_settings_router")


class ChatSettingsCB(CallbackData, prefix="cs"):
    action: str    # "menu" | "set_rank" | "toggle"
    key: str = ""
    value: str = ""
    user_id: int = 0


# Human-readable descriptions for each rank setting
_RANK_SETTINGS: dict = {
    "rank_warn":     ("⚠️",  "Выдавать варны",       "rank_warn"),
    "rank_mute":     ("🔇",  "Ставить мут",           "rank_mute"),
    "rank_kick":     ("👢",  "Кикнуть из чата",       "rank_kick"),
    "rank_ban":      ("🔨",  "Забанить навсегда",     "rank_ban"),
    "rank_shield":   ("🛡",  "Выдавать щит",          "rank_shield"),
    "rank_immune":   ("🔰",  "Давать иммунитет",      "rank_immune"),
    # rank_duel убран (UX_AUDIT Б12): чат-дуэли выпилены Боёвкой 3.0, настройка ни на что не влияла
    "rank_marriage": ("💍",  "Предлагать брак",        "rank_marriage"),
    "rank_give":     ("💸",  "Переводить мору/алмазы","rank_give"),
    "purge_action_rank": ("⚖️", "Кнопки вердикта в досье/чистке", "purge_action_rank"),
    "purge_write_rank": ("✍️", "Пишут во время чистки (0 = все)", "purge_write_rank"),
    "rank_chat_lock": ("🔒", "Открывать/закрывать чат (+чат/-чат)", "rank_chat_lock"),
}

_TOGGLE_SETTINGS: dict = {
    "nsfw_warps_allowed": ("🔞", "18+ варп-команды в чате"),
    "include_in_global_top": ("🏆", "Участие чата в глобальном топе"),
}

_MODULE_SETTINGS: dict = {
    key: (str(spec["icon"]), str(spec["name"])) for key, spec in CHAT_MODULES.items()
}

_RANK_NAMES = roles.LOCAL_RANKS_MAP


def _pack_cb(action: str, key: str = "", value: str = "", user_id: int = 0) -> str:
    """Фабрика отложенных кнопок для _chat_module_ui (без циклического импорта)."""
    return ChatSettingsCB(action=action, key=key, value=value, user_id=user_id).pack()


def _rank_label(rank_id: int) -> str:
    name = _RANK_NAMES.get(rank_id, f"Ранг {rank_id}")
    return f"{name} ({rank_id}+)"


async def _can_use_settings_callback(
    query: types.CallbackQuery,
    callback_data: ChatSettingsCB,
    db,
    bot: Bot,
    developer_id: int = 0,
) -> bool:
    """Re-check current local and Telegram authority for retained buttons."""
    if not await check_callback_owner(query, callback_data.user_id):
        return False
    message = query.message
    user = query.from_user
    if not message or not user or message.chat.type not in {"group", "supergroup"}:
        await query.answer("❌ Карточка настроек больше недействительна.", show_alert=True)
        return False
    if developer_id and int(user.id) == int(developer_id):
        return True

    stats = await chat_repo.get_chat_stats(db, user.id, message.chat.id)
    if int(stats.get("local_rank") or 0) < 5:
        await query.answer("❌ Ваш текущий ранг больше не позволяет менять настройки.", show_alert=True)
        return False
    try:
        member = await bot.get_chat_member(message.chat.id, user.id)
    except Exception:
        member = None
    if not member or not (
        member.status == "creator"
        or (member.status == "administrator" and bool(getattr(member, "can_manage_chat", False)))
    ):
        await query.answer("❌ Права Telegram-администратора больше не подтверждаются.", show_alert=True)
        return False
    return True


async def _build_menu_text(db, chat_id: int) -> str:
    tz_offset = await get_chat_timezone(db, chat_id)
    tz_sign = "+" if tz_offset >= 0 else ""
    tz_label = f"UTC{tz_sign}{tz_offset}"

    lines = ["⚙️ <b>УПРАВЛЕНИЕ ЧАТОМ</b>",
             f"🕐 Периоды активности: <b>{tz_label}</b>", "",
             "Настройки разделены по задачам — выберите нужный раздел.",
             "Изменения доступны только действующему Telegram-администратору."]
    return "\n".join(lines)


def _settings_kb(user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in (("moderation", "🛡 Модерация и наказания"),
                       ("permissions", "👑 Ранги и права"),
                       ("features", "🧩 Функции чата"),
                       ("activity", "🏆 Активность и время"),
                       ("routing", "🔗 Админ-чат и журналы"),
                       ("audit", "📜 Изменения")):
        b.button(text=label, callback_data=ChatSettingsCB(action="section", key=key, user_id=user_id))
    b.adjust(1)
    return b.as_markup()


def _section_keys(section: str) -> tuple[str, ...]:
    return {
        "moderation": ("rank_warn", "rank_mute", "rank_kick", "rank_ban", "rank_shield", "rank_immune"),
        "permissions": ("purge_action_rank", "purge_write_rank", "rank_chat_lock", "rank_marriage"),
    }.get(section, ())


def _actor_tag(name, actor_id) -> str:
    return f"@{name}" if name else f"ID {actor_id}"


def _fmt_value(value) -> str:
    return "—" if value is None or value == "" else str(value)


async def _recent_changes(db, chat_id: int, limit: int = 10) -> list[str]:
    """Строки журнала «📜 Изменения»: модули + скалярные настройки, свежие сверху."""
    entries: list[tuple[str, str]] = []
    modules = await chat_module_audit.recent(db, scope="chat", chat_id=chat_id, limit=limit)
    for row in modules:
        state = "включён" if row["after_enabled"] else "выключен"
        entries.append((
            str(row["created_at"]),
            f"{row['module']['icon']} {row['module']['name']} — <b>{state}</b> · "
            f"{_actor_tag(row.get('actor_name'), row['actor_id'])} · {row['created_at']}",
        ))
    settings_rows = await chat_settings_audit.recent(db, chat_id=chat_id, limit=limit)
    for row in settings_rows:
        entries.append((
            str(row["created_at"]),
            f"{row['label']}: {_fmt_value(row['before_value'])} → "
            f"<b>{_fmt_value(row['after_value'])}</b> · "
            f"{_actor_tag(row.get('actor_name'), row['actor_id'])} · {row['created_at']}",
        ))
    entries.sort(key=lambda item: item[0], reverse=True)
    return [line for _, line in entries[:limit]]


async def _section_view(db, chat_id: int, section: str, user_id: int):
    settings = await mod_db.get_chat_settings(db, chat_id)
    b = InlineKeyboardBuilder()
    labels = {"moderation": "🛡 МОДЕРАЦИЯ", "permissions": "👑 РАНГИ И ПРАВА",
              "features": "🧩 ФУНКЦИИ", "activity": "🏆 АКТИВНОСТЬ",
              "routing": "🔗 АДМИН-ЧАТ", "audit": "📜 ИЗМЕНЕНИЯ"}
    lines = [f"<b>{labels.get(section, 'НАСТРОЙКИ')}</b>", ""]
    if section in {"moderation", "permissions"}:
        for key in _section_keys(section):
            icon, desc, _ = _RANK_SETTINGS[key]
            lines.append(f"{icon} {desc}: <b>{_rank_label(int(settings.get(key, 0)))}</b>")
            b.button(text=f"{icon} {desc}", callback_data=ChatSettingsCB(action="set_rank", key=key, user_id=user_id))
    elif section == "features":
        return module_ui.features_view(
            settings, user_id, _pack_cb, _TOGGLE_SETTINGS,
            global_states=await chat_module_audit.global_states(db),
        )
    elif section == "activity":
        tz = await get_chat_timezone(db, chat_id)
        lines.extend([f"Часовой пояс локальных топов: <b>UTC{tz:+d}</b>",
                      "Глобальные топы используют UTC для всех чатов.", "",
                      "Меняется кнопками ниже или командой <code>бот часовой пояс, +3</code>."])
        b.button(text="➖ Минус час", callback_data=ChatSettingsCB(action="tz", value="-1", user_id=user_id))
        b.button(text="➕ Плюс час", callback_data=ChatSettingsCB(action="tz", value="1", user_id=user_id))
        if tz != 0:
            b.button(text="🌐 UTC±0", callback_data=ChatSettingsCB(action="tz", value="reset", user_id=user_id))
    elif section == "audit":
        lines.extend(await _recent_changes(db, chat_id) or ["Изменений ещё не было."])
    else:
        admin_chat_id = await routing.get_admin_chat(db, chat_id)
        if admin_chat_id:
            lines.extend([f"✅ Админ-чат привязан: <code>{admin_chat_id}</code>",
                          "Отчёты модерации и журнал уходят туда.",
                          "Перенести можно новым кодом привязки.", ""])
            b.button(text="❌ Отвязать админ-чат",
                     callback_data=ChatSettingsCB(action="route_unlink", user_id=user_id))
        else:
            lines.extend(["❌ Админ-чат не привязан.",
                          "Привязка отделяет публичный чат от журнала модерации:",
                          "код создаётся здесь, а подтверждается в чате администрации.", ""])
        b.button(text="🔗 Получить код привязки",
                 callback_data=ChatSettingsCB(action="route_code", user_id=user_id))
    b.button(text="⬅️ Все настройки", callback_data=ChatSettingsCB(action="menu", user_id=user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


async def _context_view(db, chat_id: int, context: str, user_id: int):
    """Вернуть админа на экран, откуда он переключил чекбокс.

    context = "features" | "grp:<группа>" | "" (старая карточка → главное меню).
    """
    if context.startswith("grp:"):
        settings = await mod_db.get_chat_settings(db, chat_id)
        view = module_ui.group_view(
            settings, context[4:], user_id, _pack_cb, _TOGGLE_SETTINGS,
            global_states=await chat_module_audit.global_states(db),
        )
        if view is not None:
            return view
    if context:
        settings = await mod_db.get_chat_settings(db, chat_id)
        return module_ui.features_view(
            settings, user_id, _pack_cb, _TOGGLE_SETTINGS,
            global_states=await chat_module_audit.global_states(db),
        )
    text = await _build_menu_text(db, chat_id)
    return text, _settings_kb(user_id=user_id)


def _context_cb_args(context: str) -> dict:
    """Параметры ChatSettingsCB для кнопки «вернуться на экран context»."""
    if context.startswith("grp:"):
        return {"action": "fgroup", "key": context[4:]}
    if context:
        return {"action": "section", "key": "features"}
    return {"action": "menu"}


def _rank_picker_kb(key: str, current: int, label: str, user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for rank_id, rank_name in sorted(_RANK_NAMES.items()):
        mark = "✅ " if rank_id == current else ""
        b.button(
            text=f"{mark}{rank_name} и выше ({rank_id}+)",
            callback_data=ChatSettingsCB(action="set_rank", key=key, value=str(rank_id), user_id=user_id),
        )
    b.button(text="⬅️ Назад к настройкам", callback_data=ChatSettingsCB(action="menu", user_id=user_id))
    b.adjust(1)
    return b.as_markup()


@router.message(TextCmd(["настройки чата", "настройка чата", "settings"]))
async def cmd_chat_settings(message: types.Message, db, bot: Bot, developer_id: int = 0):
    if message.chat.type == "private":
        return await answer_group_only(message)

    admin_stats = await chat_repo.get_chat_stats(db, message.from_user.id, message.chat.id)
    admin_rank = admin_stats.get("local_rank", 0)

    if not (developer_id and message.from_user.id == developer_id) and admin_rank < 5:
        return await message.answer(
            "❌ <b>Отказ:</b> Требуется ранг <b>Совладелец</b> (5) или выше.",
            parse_mode="HTML",
        )
    if not (developer_id and message.from_user.id == developer_id):
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        except Exception:
            member = None
        if not member or not (
            member.status == "creator"
            or (member.status == "administrator" and bool(getattr(member, "can_manage_chat", False)))
        ):
            return await message.answer(
                "❌ Нужны актуальные права Telegram-администратора с разрешением управлять чатом."
            )

    text = await _build_menu_text(db, message.chat.id)
    await message.answer(text, reply_markup=_settings_kb(user_id=message.from_user.id), parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "menu"))
async def cb_settings_menu(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    text = await _build_menu_text(db, query.message.chat.id)
    uid = callback_data.user_id
    await query.message.edit_text(text, reply_markup=_settings_kb(user_id=uid), parse_mode="HTML")
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "section"))
async def cb_settings_section(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    if callback_data.key not in {"moderation", "permissions", "features", "activity", "routing", "audit"}:
        return await query.answer("Раздел больше не используется.", show_alert=True)
    text, keyboard = await _section_view(db, query.message.chat.id, callback_data.key, callback_data.user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "fgroup"))
async def cb_feature_group(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    """Страница одной группы модулей: точечные переключатели."""
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    settings = await mod_db.get_chat_settings(db, query.message.chat.id)
    view = module_ui.group_view(
        settings, callback_data.key, callback_data.user_id, _pack_cb, _TOGGLE_SETTINGS,
        global_states=await chat_module_audit.global_states(db),
    )
    if view is None:
        return await query.answer("Раздел больше не используется.", show_alert=True)
    text, keyboard = view
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "set_rank"))
async def cb_set_rank(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    key = callback_data.key
    uid = callback_data.user_id

    # Both callback stages must use the same allowlist.  A retained or crafted
    # legacy button may not turn an arbitrary database column into a rank setting.
    if key not in _RANK_SETTINGS:
        return await query.answer("❌ Эта старая настройка больше не используется.", show_alert=True)

    if callback_data.value != "":
        try:
            new_val = int(callback_data.value)
        except (ValueError, TypeError):
            return await query.answer("❌ Некорректное значение.", show_alert=True)
        # Validate rank is within the allowed range to prevent crafted callbacks
        valid_ranks = set(roles.LOCAL_RANKS_MAP.keys())
        if new_val not in valid_ranks:
            return await query.answer("❌ Недопустимый ранг.", show_alert=True)
        settings = await mod_db.get_chat_settings(db, chat_id)
        before = int(settings.get(key, 0) or 0)
        if before != new_val:
            await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
            await chat_settings_audit.record(
                db, chat_id=chat_id, setting_key=key, before=before, after=new_val,
                actor_id=int(query.from_user.id), source="telegram_chat_settings",
            )
            await db.commit()
        await query.answer("✅ Сохранено!", show_alert=False)
        text = await _build_menu_text(db, chat_id)
        await query.message.edit_text(text, reply_markup=_settings_kb(user_id=uid), parse_mode="HTML")
        return

    s = await mod_db.get_chat_settings(db, chat_id)
    current = s.get(key, 0)

    icon, desc, _ = _RANK_SETTINGS[key]
    label = f"{icon} {desc}"

    await query.message.edit_text(
        f"✏️ <b>{label}</b>\n\n"
        f"Выберите минимальный ранг, начиная с которого разрешено это действие:\n"
        f"<i>Текущее: {_rank_label(current)}</i>",
        reply_markup=_rank_picker_kb(key, current, label, user_id=uid),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "toggle"))
async def cb_toggle_setting(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    key = callback_data.key
    uid = callback_data.user_id
    # Whitelist: key уходит именем колонки в UPDATE (f-string в update_chat_settings) —
    # крафтовый callback с произвольным key не должен туда долетать.
    if key not in {**_TOGGLE_SETTINGS, **_MODULE_SETTINGS}:
        return await query.answer("❌ Эта старая настройка больше не используется.", show_alert=True)
    s = await mod_db.get_chat_settings(db, chat_id)
    new_val = 0 if s.get(key, 1) else 1
    context = callback_data.value
    if key in _MODULE_SETTINGS and not new_val:
        icon, name = _MODULE_SETTINGS[key]
        warn = (
            "Бот замолчит на все команды в этом чате, пока модуль не вернут.\n"
            if key == "module_bot"
            else "Он сразу перестанет работать в этом чате.\n"
        )
        b = InlineKeyboardBuilder()
        b.button(
            text=f"Отключить {icon} {name}",
            callback_data=ChatSettingsCB(action="confirm_off", key=key, value=context, user_id=uid),
        )
        b.button(
            text="Отмена",
            callback_data=ChatSettingsCB(user_id=uid, **_context_cb_args(context)),
        )
        b.adjust(1)
        await query.message.edit_text(
            f"⚠️ <b>Отключить модуль «{name}»?</b>\n\n"
            f"{warn}Действие сохранится в журнале.",
            reply_markup=b.as_markup(), parse_mode="HTML",
        )
        return await query.answer()
    if key in _MODULE_SETTINGS:
        await chat_module_audit.set_chat_module(
            db, chat_id=chat_id, module_key=key, enabled=bool(new_val),
            actor_id=int(query.from_user.id), source="telegram_chat_settings",
        )
        bot_silence_invalidate(chat_id)
    else:
        await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
        await chat_settings_audit.record(
            db, chat_id=chat_id, setting_key=key,
            before=int(bool(s.get(key, 1))), after=int(bool(new_val)),
            actor_id=int(query.from_user.id), source="telegram_chat_settings",
        )
    if key in _TOGGLE_SETTINGS:
        icon, desc = _TOGGLE_SETTINGS[key]
    else:
        icon, name = _MODULE_SETTINGS.get(key, ("🧩", key))
        desc = f"Модуль «{name}»"
    status = "включено" if new_val else "выключено"
    await query.answer(f"{icon} {desc} — {status}!", show_alert=not new_val)
    text, keyboard = await _context_view(db, chat_id, context, uid)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "confirm_off"))
async def cb_confirm_module_off(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    key = callback_data.key
    if key not in _MODULE_SETTINGS:
        return await query.answer("❌ Эта настройка больше не используется.", show_alert=True)
    chat_id = query.message.chat.id
    settings = await mod_db.get_chat_settings(db, chat_id)
    if not bool(settings.get(key, 1)):
        return await query.answer("Модуль уже выключен.", show_alert=True)
    await chat_module_audit.set_chat_module(
        db, chat_id=chat_id, module_key=key, enabled=False,
        actor_id=int(query.from_user.id), source="telegram_chat_settings",
    )
    bot_silence_invalidate(chat_id)
    icon, name = _MODULE_SETTINGS[key]
    text, keyboard = await _context_view(db, chat_id, callback_data.value, callback_data.user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await query.answer(f"{icon} {name} — выключено", show_alert=True)


# ── Timezone command ─────────────────────────────────────────────────────────

@router.message(TextCmd(["часовой пояс", "timezone", "часовойпояс",
                         # алиасы из удалённого дубль-хендлера routing.py (БЛОК 36.4)
                         "часовой пояс чата", "timezone чата", "пояс чата"]))
async def cmd_set_timezone(message: types.Message, db, developer_id: int = 0, text_args: str = None):
    """бот часовой пояс        → показать текущий
    бот часовой пояс, +3   → установить UTC+3
    бот часовой пояс, -5   → установить UTC-5"""
    if message.chat.type == "private":
        return await answer_group_only(message)

    admin_stats = await chat_repo.get_chat_stats(db, message.from_user.id, message.chat.id)
    admin_rank = admin_stats.get("local_rank", 0)
    is_dev = developer_id and message.from_user.id == developer_id

    if not is_dev and admin_rank < 5:
        return await message.answer(
            "❌ <b>Отказ:</b> Требуется ранг <b>Совладелец</b> (5) или выше.",
            parse_mode="HTML",
        )

    current_tz = await get_chat_timezone(db, message.chat.id)
    tz_sign = "+" if current_tz >= 0 else ""
    current_label = f"UTC{tz_sign}{current_tz}"

    raw = (text_args or "").strip()
    if not raw:
        return await message.answer(
            f"🕐 <b>ЧАСОВОЙ ПОЯС ЧАТА</b>\n\n"
            f"Текущий: <code>{current_label}</code>\n\n"
            f"Чтобы изменить:\n"
            f"<code>бот часовой пояс, +3</code>\n"
            f"<code>бот часовой пояс, -5</code>\n\n"
            f"<i>Диапазон: UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}</i>",
            parse_mode="HTML",
        )

    # Parse offset like "+3", "-5", "3", "UTC+3", "UTC-5"
    raw_clean = raw.upper().replace("UTC", "").replace(" ", "")
    try:
        offset = int(raw_clean)
    except ValueError:
        return await message.answer(
            "❌ <b>Отказ:</b> Неверный формат. Пример: <code>бот часовой пояс, +3</code>",
            parse_mode="HTML",
        )

    if offset < CHAT_TIMEZONE_MIN or offset > CHAT_TIMEZONE_MAX:
        return await message.answer(
            f"❌ <b>Отказ:</b> Диапазон UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}.",
            parse_mode="HTML",
        )

    await set_chat_timezone(db, message.chat.id, offset)
    await chat_settings_audit.record(
        db, chat_id=message.chat.id, setting_key="timezone",
        before=current_tz, after=offset,
        actor_id=int(message.from_user.id), source="telegram_chat_settings",
    )
    new_sign = "+" if offset >= 0 else ""
    new_label = f"UTC{new_sign}{offset}"
    await message.answer(
        f"✅ Часовой пояс чата изменён: <code>{current_label}</code> → <code>{new_label}</code>\n\n"
        f"<i>Теперь все счётчики активности, стрик и квесты сбрасываются по полуночи "
        f"{new_label}.</i>",
        parse_mode="HTML",
    )


# ── Кнопочные действия: часовой пояс, админ-чат, сброс к стандарту ────────────

@router.callback_query(ChatSettingsCB.filter(F.action == "tz"))
async def cb_set_timezone(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    """Сдвиг часового пояса кнопками −/+ в разделе «Активность»."""
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    current = await get_chat_timezone(db, chat_id)
    if callback_data.value == "reset":
        target = 0
    else:
        try:
            delta = int(callback_data.value)
        except (ValueError, TypeError):
            return await query.answer("❌ Некорректное значение.", show_alert=True)
        target = max(CHAT_TIMEZONE_MIN, min(CHAT_TIMEZONE_MAX, current + delta))
    if target == current:
        await query.answer(
            f"Диапазон: UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}.", show_alert=True,
        )
    else:
        await set_chat_timezone(db, chat_id, target)
        await chat_settings_audit.record(
            db, chat_id=chat_id, setting_key="timezone", before=current, after=target,
            actor_id=int(query.from_user.id), source="telegram_chat_settings",
        )
        await query.answer(f"🕓 Часовой пояс: UTC{target:+d}")
    text, keyboard = await _section_view(db, chat_id, "activity", callback_data.user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "route_code"))
async def cb_route_code(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    """Шаг 1 привязки админ-чата: код, который подтверждают в чате администрации."""
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    title = query.message.chat.title or str(chat_id)
    nonce = await routing.create_bind_request(db, chat_id, title, int(query.from_user.id))
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Админ-чат", callback_data=ChatSettingsCB(
        action="section", key="routing", user_id=callback_data.user_id))
    b.button(text="⬅️ Все настройки", callback_data=ChatSettingsCB(
        action="menu", user_id=callback_data.user_id))
    b.adjust(1)
    await query.message.edit_text(
        "🔗 <b>ПРИВЯЗКА АДМИН-ЧАТА</b>\n\n"
        "Отправьте эту команду в чате администрации:\n\n"
        f"<code>бот принять связь, {nonce}</code>\n\n"
        "<i>⏳ Код действует 10 минут и подтверждается только его создателем.</i>",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "route_unlink"))
async def cb_route_unlink(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="❌ Да, отвязать", callback_data=ChatSettingsCB(
        action="route_unlink_do", user_id=callback_data.user_id))
    b.button(text="Отмена", callback_data=ChatSettingsCB(
        action="section", key="routing", user_id=callback_data.user_id))
    b.adjust(1)
    await query.message.edit_text(
        "⚠️ <b>Отвязать админ-чат?</b>\n\n"
        "Отчёты модерации и журнал перестанут уходить в чат администрации.\n"
        "Снятие попадёт в журнал настроек; повторная привязка — новым кодом.",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "route_unlink_do"))
async def cb_route_unlink_do(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    try:
        previous = await routing.unbind_admin_chat(
            db, main_chat_id=chat_id, actor_id=int(query.from_user.id),
            source="telegram_chat_settings",
        )
    except routing.BindRequestError as exc:
        await query.answer(f"❌ {exc}", show_alert=True)
        return
    if previous is None:
        await query.answer("Админ-чат уже не привязан.", show_alert=True)
    else:
        await query.answer(f"Админ-чат {previous} отвязан.", show_alert=True)
    text, keyboard = await _section_view(db, chat_id, "routing", callback_data.user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "reset_confirm"))
async def cb_reset_confirm(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="♻️ Да, вернуть стандарт", callback_data=ChatSettingsCB(
        action="reset_do", user_id=callback_data.user_id))
    b.button(text="Отмена", callback_data=ChatSettingsCB(
        action="section", key="features", user_id=callback_data.user_id))
    b.adjust(1)
    await query.message.edit_text(
        "♻️ <b>Вернуть стандартные настройки чата?</b>\n\n"
        "Модули вернутся к заводским значениям, пороги рангов и тумблеры — к стандарту. "
        "Каждое изменение попадёт в журнал «📜 Изменения».",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "reset_do"))
async def cb_reset_do(
    query: types.CallbackQuery, callback_data: ChatSettingsCB, db,
    bot: Bot, developer_id: int = 0,
):
    """Откат настроек к реестру/дефолтам; чеки пишутся штатными каналами."""
    if not await _can_use_settings_callback(query, callback_data, db, bot, developer_id):
        return
    chat_id = query.message.chat.id
    result = await chat_settings_reset.reset_chat_settings_to_defaults(
        db, chat_id=chat_id, actor_id=int(query.from_user.id),
        source="telegram_chat_settings",
    )
    bot_silence_invalidate(chat_id)
    if result["modules_changed"] or result["settings_changed"]:
        await query.answer(
            f"♻️ Стандарт: модулей {result['modules_changed']}, "
            f"настроек {result['settings_changed']}.",
            show_alert=True,
        )
    else:
        await query.answer("Все настройки уже стандартные.", show_alert=True)
    text, keyboard = await _context_view(db, chat_id, "features", callback_data.user_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
