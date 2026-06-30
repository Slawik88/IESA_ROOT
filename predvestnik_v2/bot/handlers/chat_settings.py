from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import chat as chat_repo
from infrastructure.repositories.streak import get_chat_timezone, set_chat_timezone
from services import roles
from services.utils import check_callback_owner
from core.constants import CHAT_TIMEZONE_MIN, CHAT_TIMEZONE_MAX

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
    "rank_duel":     ("⚔️",  "Начинать дуэли",        "rank_duel"),
    "rank_marriage": ("💍",  "Предлагать брак",        "rank_marriage"),
    "rank_give":     ("💸",  "Переводить мору/алмазы","rank_give"),
    "purge_action_rank": ("⚖️", "Кнопки вердикта в досье/чистке", "purge_action_rank"),
    "rank_chat_lock": ("🔒", "Открывать/закрывать чат (+чат/-чат)", "rank_chat_lock"),
}

_TOGGLE_SETTINGS: dict = {
    "events_enabled":     ("🎁", "Сундуки и случайные события"),
    "nsfw_warps_allowed": ("🔞", "18+ варп-команды в чате"),
}

_MODULE_SETTINGS: dict = {
    "module_shop":        ("🛒", "Магазин"),
    "module_gacha":       ("🎰", "Гача"),
    "module_expeditions": ("🗺", "Экспедиции"),
    "module_auction":     ("🏛", "Аукцион"),
    "module_games":       ("🎲", "Мини-игры"),
    "module_exchange":    ("💱", "Конвертер"),
    "module_quests":      ("📋", "Квесты"),
    "module_zoo":         ("🐾", "Зоопарк"),
    "module_warps":       ("🤝", "Варп-команды"),
    "module_daily_deal":  ("🏷", "Акция дня"),
}

_RANK_NAMES = roles.LOCAL_RANKS_MAP


def _rank_label(rank_id: int) -> str:
    name = _RANK_NAMES.get(rank_id, f"Ранг {rank_id}")
    return f"{name} ({rank_id}+)"


async def _build_menu_text(db, chat_id: int) -> str:
    s = await mod_db.get_chat_settings(db, chat_id)
    tz_offset = await get_chat_timezone(db, chat_id)
    tz_sign = "+" if tz_offset >= 0 else ""
    tz_label = f"UTC{tz_sign}{tz_offset}"

    lines = [f"⚙️ <b>НАСТРОЙКИ ЧАТА</b>\n🕐 <b>Часовой пояс:</b> <code>{tz_label}</code>  "
             f"<i>— бот часовой пояс, +3</i>\n"]

    # Rank permissions section
    lines.append("🛡 <b>Кто может выполнять действия:</b>")
    rank_items = list(_RANK_SETTINGS.items())
    for i, (key, (icon, desc, _key)) in enumerate(rank_items):
        val = s.get(key, 0)
        prefix = "└" if i == len(rank_items) - 1 else "├"
        lines.append(f"{prefix} {icon} {desc}: <b>{_rank_label(val)}</b>")

    lines.append("")

    # Toggle section
    lines.append("⚡ <b>Функции чата:</b>")
    toggle_items = list(_TOGGLE_SETTINGS.items())
    for i, (key, (icon, desc)) in enumerate(toggle_items):
        val = s.get(key, 1)
        status = "✅ Включено" if val else "❌ Выключено"
        prefix = "├"
        lines.append(f"{prefix} {icon} {desc}: {status}")

    auc_rank = s.get("auction_min_rank", 0)
    auc_rank_label = _rank_label(auc_rank) if auc_rank > 0 else "Все участники (0)"
    lines.append(f"└ 🏛 Выставлять на аукцион: <b>{auc_rank_label}</b>")

    lines.append("")
    lines.append("🧩 <b>Модули чата:</b>")
    mod_items = list(_MODULE_SETTINGS.items())
    for i, (key, (icon, name)) in enumerate(mod_items):
        val = s.get(key, 1)
        status = "✅" if val else "❌"
        prefix = "└" if i == len(mod_items) - 1 else "├"
        lines.append(f"{prefix} {icon} {name}: {status}")

    lines.append("\n<i>Нажмите кнопку ниже, чтобы изменить настройку.</i>")
    return "\n".join(lines)


def _settings_kb(user_id: int = 0) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, (icon, desc, _key) in _RANK_SETTINGS.items():
        b.button(
            text=f"✏️ {icon} {desc}",
            callback_data=ChatSettingsCB(action="set_rank", key=key, user_id=user_id),
        )
    for key, (icon, desc) in _TOGGLE_SETTINGS.items():
        b.button(
            text=f"🔄 {icon} {desc}",
            callback_data=ChatSettingsCB(action="toggle", key=key, user_id=user_id),
        )
    b.button(
        text="✏️ 🏛 Минимальный ранг для аукциона",
        callback_data=ChatSettingsCB(action="set_rank", key="auction_min_rank", user_id=user_id),
    )
    for key, (icon, name) in _MODULE_SETTINGS.items():
        b.button(
            text=f"🔄 {icon} {name}",
            callback_data=ChatSettingsCB(action="toggle", key=key, user_id=user_id),
        )
    b.adjust(1)
    return b.as_markup()


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
async def cmd_chat_settings(message: types.Message, db, developer_id: int = 0):
    if message.chat.type == "private":
        return

    admin_stats = await chat_repo.get_chat_stats(db, message.from_user.id, message.chat.id)
    admin_rank = admin_stats.get("local_rank", 0)

    if not (developer_id and message.from_user.id == developer_id) and admin_rank < 5:
        return await message.answer(
            "❌ <b>Отказ:</b> Требуется ранг <b>Совладелец</b> (5) или выше.",
            parse_mode="HTML",
        )

    text = await _build_menu_text(db, message.chat.id)
    await message.answer(text, reply_markup=_settings_kb(user_id=message.from_user.id), parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "menu"))
async def cb_settings_menu(query: types.CallbackQuery, callback_data: ChatSettingsCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text = await _build_menu_text(db, query.message.chat.id)
    uid = callback_data.user_id
    await query.message.edit_text(text, reply_markup=_settings_kb(user_id=uid), parse_mode="HTML")
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "set_rank"))
async def cb_set_rank(query: types.CallbackQuery, callback_data: ChatSettingsCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    chat_id = query.message.chat.id
    key = callback_data.key
    uid = callback_data.user_id

    if callback_data.value != "":
        try:
            new_val = int(callback_data.value)
        except (ValueError, TypeError):
            return await query.answer("❌ Некорректное значение.", show_alert=True)
        # Validate rank is within the allowed range to prevent crafted callbacks
        valid_ranks = set(roles.LOCAL_RANKS_MAP.keys())
        if new_val not in valid_ranks:
            return await query.answer("❌ Недопустимый ранг.", show_alert=True)
        await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
        await db.commit()
        await query.answer("✅ Сохранено!", show_alert=False)
        text = await _build_menu_text(db, chat_id)
        await query.message.edit_text(text, reply_markup=_settings_kb(user_id=uid), parse_mode="HTML")
        return

    s = await mod_db.get_chat_settings(db, chat_id)
    current = s.get(key, 0)

    if key in _RANK_SETTINGS:
        icon, desc, _ = _RANK_SETTINGS[key]
        label = f"{icon} {desc}"
    else:
        label = "🏛 Аукцион — минимальный ранг"

    await query.message.edit_text(
        f"✏️ <b>{label}</b>\n\n"
        f"Выберите минимальный ранг, начиная с которого разрешено это действие:\n"
        f"<i>Текущее: {_rank_label(current)}</i>",
        reply_markup=_rank_picker_kb(key, current, label, user_id=uid),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "toggle"))
async def cb_toggle_setting(query: types.CallbackQuery, callback_data: ChatSettingsCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    chat_id = query.message.chat.id
    key = callback_data.key
    uid = callback_data.user_id
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

@router.message(TextCmd(["часовой пояс", "timezone", "часовойпояс"]))
async def cmd_set_timezone(message: types.Message, db, developer_id: int = 0, text_args: str = None):
    """бот часовой пояс        → показать текущий
    бот часовой пояс, +3   → установить UTC+3
    бот часовой пояс, -5   → установить UTC-5"""
    if message.chat.type == "private":
        return

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
