from aiogram import Bot, Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories.streak import get_chat_timezone, set_chat_timezone
from services import roles
from services.utils import check_callback_owner
from core.constants import CHAT_TIMEZONE_MIN, CHAT_TIMEZONE_MAX
from bot.keyboards.cta import answer_group_only
from core.chat_modules import CHAT_MODULES

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
    s = await mod_db.get_chat_settings(db, chat_id)
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
                       ("routing", "🔗 Админ-чат и журналы")):
        b.button(text=label, callback_data=ChatSettingsCB(action="section", key=key, user_id=user_id))
    b.adjust(1)
    return b.as_markup()


def _section_keys(section: str) -> tuple[str, ...]:
    return {
        "moderation": ("rank_warn", "rank_mute", "rank_kick", "rank_ban", "rank_shield", "rank_immune"),
        "permissions": ("purge_action_rank", "purge_write_rank", "rank_chat_lock", "rank_marriage"),
        "features": tuple(_TOGGLE_SETTINGS) + tuple(_MODULE_SETTINGS),
    }.get(section, ())


async def _section_view(db, chat_id: int, section: str, user_id: int):
    settings = await mod_db.get_chat_settings(db, chat_id)
    b = InlineKeyboardBuilder()
    labels = {"moderation": "🛡 МОДЕРАЦИЯ", "permissions": "👑 РАНГИ И ПРАВА",
              "features": "🧩 ФУНКЦИИ", "activity": "🏆 АКТИВНОСТЬ",
              "routing": "🔗 АДМИН-ЧАТ"}
    lines = [f"<b>{labels.get(section, 'НАСТРОЙКИ')}</b>", ""]
    if section in {"moderation", "permissions"}:
        for key in _section_keys(section):
            icon, desc, _ = _RANK_SETTINGS[key]
            lines.append(f"{icon} {desc}: <b>{_rank_label(int(settings.get(key, 0)))}</b>")
            b.button(text=f"{icon} {desc}", callback_data=ChatSettingsCB(action="set_rank", key=key, user_id=user_id))
    elif section == "features":
        for key in _section_keys(section):
            icon, desc = (_TOGGLE_SETTINGS | _MODULE_SETTINGS)[key]
            enabled = bool(settings.get(key, 1))
            lines.append(f"{icon} {desc}: <b>{'включено' if enabled else 'выключено'}</b>")
            b.button(text=f"{'✅' if enabled else '❌'} {desc}", callback_data=ChatSettingsCB(action="toggle", key=key, user_id=user_id))
    elif section == "activity":
        tz = await get_chat_timezone(db, chat_id)
        lines.extend([f"Часовой пояс локальных топов: <b>UTC{tz:+d}</b>",
                      "Глобальные топы используют UTC для всех чатов.", "",
                      "Изменить: <code>бот часовой пояс, +3</code>"])
    else:
        lines.extend(["Привязка отделяет публичный чат от журнала модерации.", "",
                      "Создать: <code>бот привязать админ чат</code>",
                      "Проверить: <code>бот инфо чата</code>"])
    b.button(text="⬅️ Все настройки", callback_data=ChatSettingsCB(action="menu", user_id=user_id))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


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
    if callback_data.key not in {"moderation", "permissions", "features", "activity", "routing"}:
        return await query.answer("Раздел больше не используется.", show_alert=True)
    text, keyboard = await _section_view(db, query.message.chat.id, callback_data.key, callback_data.user_id)
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
        updates = {key: new_val}
        if key == "module_echo":
            updates["echo_events_enabled"] = new_val
        await mod_db.update_chat_settings(db, chat_id, **updates)
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
    await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
    await db.commit()
    if key in _TOGGLE_SETTINGS:
        icon, desc = _TOGGLE_SETTINGS[key]
    else:
        icon, name = _MODULE_SETTINGS.get(key, ("🧩", key))
        desc = f"Модуль «{name}»"
    status = "включено" if new_val else "выключено"
    await query.answer(f"{icon} {desc} — {status}!", show_alert=not new_val)
    text = await _build_menu_text(db, chat_id)
    await query.message.edit_text(text, reply_markup=_settings_kb(user_id=uid), parse_mode="HTML")


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
    new_sign = "+" if offset >= 0 else ""
    new_label = f"UTC{new_sign}{offset}"
    await message.answer(
        f"✅ Часовой пояс чата изменён: <code>{current_label}</code> → <code>{new_label}</code>\n\n"
        f"<i>Теперь все счётчики активности, стрик и квесты сбрасываются по полуночи "
        f"{new_label}.</i>",
        parse_mode="HTML",
    )
