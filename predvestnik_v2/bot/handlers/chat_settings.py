from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import chat as chat_repo
from services import roles

router = Router(name="chat_settings_router")


class ChatSettingsCB(CallbackData, prefix="cs"):
    action: str    # "menu" | "set_rank" | "toggle"
    key: str = ""
    value: str = ""


# Human-readable descriptions for each rank setting
_RANK_SETTINGS: dict = {
    "rank_warn":   ("⚠️", "Выдавать варны",    "rank_warn"),
    "rank_mute":   ("🔇", "Ставить мут",        "rank_mute"),
    "rank_kick":   ("👢", "Кикнуть из чата",    "rank_kick"),
    "rank_ban":    ("🔨", "Забанить навсегда",  "rank_ban"),
    "rank_shield": ("🛡", "Выдавать щит",       "rank_shield"),
    "rank_immune": ("🔰", "Давать иммунитет",   "rank_immune"),
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

    lines = ["⚙️ <b>НАСТРОЙКИ ЧАТА</b>\n"]

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


def _settings_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, (icon, desc, _key) in _RANK_SETTINGS.items():
        b.button(
            text=f"✏️ {icon} {desc}",
            callback_data=ChatSettingsCB(action="set_rank", key=key),
        )
    for key, (icon, desc) in _TOGGLE_SETTINGS.items():
        b.button(
            text=f"🔄 {icon} {desc}",
            callback_data=ChatSettingsCB(action="toggle", key=key),
        )
    b.button(
        text="✏️ 🏛 Минимальный ранг для аукциона",
        callback_data=ChatSettingsCB(action="set_rank", key="auction_min_rank"),
    )
    for key, (icon, name) in _MODULE_SETTINGS.items():
        b.button(
            text=f"🔄 {icon} {name}",
            callback_data=ChatSettingsCB(action="toggle", key=key),
        )
    b.adjust(1)
    return b.as_markup()


def _rank_picker_kb(key: str, current: int, label: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=f"🚫 Никому (заблокировать)" if key not in ("rank_warn",) else "Снять ограничение",
        callback_data=ChatSettingsCB(action="set_rank", key=key, value="99"),
    ) if False else None  # placeholder - not adding 99 rank

    for rank_id, rank_name in sorted(_RANK_NAMES.items()):
        mark = "✅ " if rank_id == current else ""
        b.button(
            text=f"{mark}{rank_name} и выше ({rank_id}+)",
            callback_data=ChatSettingsCB(action="set_rank", key=key, value=str(rank_id)),
        )
    b.button(text="⬅️ Назад к настройкам", callback_data=ChatSettingsCB(action="menu"))
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
    await message.answer(text, reply_markup=_settings_kb(), parse_mode="HTML")


@router.callback_query(ChatSettingsCB.filter(F.action == "menu"))
async def cb_settings_menu(query: types.CallbackQuery, db):
    text = await _build_menu_text(db, query.message.chat.id)
    await query.message.edit_text(text, reply_markup=_settings_kb(), parse_mode="HTML")
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "set_rank"))
async def cb_set_rank(query: types.CallbackQuery, callback_data: ChatSettingsCB, db):
    chat_id = query.message.chat.id
    key = callback_data.key

    if callback_data.value != "":
        new_val = int(callback_data.value)
        await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
        await db.commit()
        await query.answer("✅ Сохранено!", show_alert=False)
        text = await _build_menu_text(db, chat_id)
        await query.message.edit_text(text, reply_markup=_settings_kb(), parse_mode="HTML")
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
        reply_markup=_rank_picker_kb(key, current, label),
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(ChatSettingsCB.filter(F.action == "toggle"))
async def cb_toggle_setting(query: types.CallbackQuery, callback_data: ChatSettingsCB, db):
    chat_id = query.message.chat.id
    key = callback_data.key
    s = await mod_db.get_chat_settings(db, chat_id)
    new_val = 0 if s.get(key, 1) else 1
    await mod_db.update_chat_settings(db, chat_id, **{key: new_val})
    await db.commit()
    icon, desc = _TOGGLE_SETTINGS.get(key, ("", key))
    status = "включено" if new_val else "выключено"
    await query.answer(f"{icon} {desc} — {status}!", show_alert=False)
    text = await _build_menu_text(db, chat_id)
    await query.message.edit_text(text, reply_markup=_settings_kb(), parse_mode="HTML")
