from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from infrastructure.repositories import stats
from services.utils import safe_html, format_currency
from bot.filters.text_commands import TextCmd
from core.constants import INACTIVE_THRESHOLD_DAYS

router = Router(name="stats_router")

# Фабрика кнопок для переключения периодов в ТОПе
class TopPeriodData(CallbackData, prefix="top"):
    period: str

# Человекочитаемые названия периодов
PERIOD_NAMES = {
    "day": "За сегодня",
    "week": "За эту неделю",
    "all_time": "За всё время",
    "last_day": "За вчера",
    "last_week": "За прошлую неделю"
}

# Синонимы для текстовых команд ("бот топ день")
TEXT_PERIOD_MAP = {
    "день": "day", "сегодня": "day",
    "неделя": "week", "эту неделю": "week",
    "все время": "all_time", "всё время": "all_time",
    "вчера": "last_day", "прошлый день": "last_day",
    "прошлая неделя": "last_week", "прошлую неделю": "last_week"
}

def generate_top_keyboard(current_period: str) -> types.InlineKeyboardMarkup:
    """Генерирует кнопки, помечая текущую галочкой."""
    builder = InlineKeyboardBuilder()
    
    # Кнопки периодов
    periods = ["day", "week", "all_time", "last_day", "last_week"]
    for p in periods:
        text = f"✅ {PERIOD_NAMES[p]}" if p == current_period else PERIOD_NAMES[p]
        builder.button(text=text, callback_data=TopPeriodData(period=p))
    
    # Расставляем кнопки: 2 в ряд, последняя на всю ширину
    builder.adjust(2, 2, 1)
    return builder.as_markup()

async def build_top_text(db, chat_id: int, period: str) -> str:
    """Собирает красивый текст лидерборда."""
    top_users = await stats.get_top_messages(db, chat_id, period)
    period_name = PERIOD_NAMES.get(period, "За всё время")
    
    if not top_users:
        return f"🏆 <b>ТОП АКТИВНОСТИ</b>\n└ <i>{period_name} сообщений нет.</i>"

    text = f"🏆 <b>ТОП АКТИВНОСТИ</b>\n📅 <b>Период:</b> {period_name}\n\n"
    
    for idx, user in enumerate(top_users, 1):
        # Медали для первых трех мест
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏅" if idx <= 10 else f"{idx}."
        
        name = safe_html(user['user_tg_username'] or f"Пользователь {user['user_tg_id']}")
        link = f"""<a href="tg://user?id={user['user_tg_id']}">{name}</a>"""
        count = user['msg_count']
        
        text += f"{medal} {link} — <code>{count}</code>\n"

    return text

# ==========================================
# КОМАНДА: /top
# ==========================================
@router.message(TextCmd(["топ", "лидеры"]))
async def cmd_top(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await message.answer("❌ <b>Ошибка:</b> Топы доступны только в группах.", parse_mode="HTML")

    # Support both "бот топ, день" (comma, TextCmd arg) and "бот топ день" (no comma)
    period = "all_time"
    search_text = (text_args or "").strip().lower()
    if not search_text:
        # Try to extract period keyword from full message text (no-comma variant)
        search_text = message.text.lower().strip()
    for keyword, p in sorted(TEXT_PERIOD_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in search_text:
            period = p
            break

    text = await build_top_text(db, message.chat.id, period)
    keyboard = generate_top_keyboard(period)
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# Обработчик кнопок ТОПа
@router.callback_query(TopPeriodData.filter())
async def process_top_period(callback: types.CallbackQuery, callback_data: TopPeriodData, db):
    text = await build_top_text(db, callback.message.chat.id, callback_data.period)
    keyboard = generate_top_keyboard(callback_data.period)
    
    # Отлавливаем только ошибку неизмененного сообщения, остальные ошибки бот должен показать!
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        pass
        
    await callback.answer()


# ══════════════════════════════════════════════════════════
# B17 — Расширенные топы: локальные + глобальные
# ══════════════════════════════════════════════════════════

class TopCatCB(CallbackData, prefix="topcat"):
    cat: str    # mora | diamonds | pets | levels | achievements | msgs | streaks | auction
    mode: str   # local | global


_CAT_LABELS = {
    "mora":         "🪙 По Море",
    "diamonds":     "💎 По Алмазам",
    "pets":         "🐾 По питомцам (Ур.)",
    "achievements": "🏆 По достижениям",
    "msgs":         "💬 По сообщениям",
    "streaks":      "🔥 По стрику",
    "auction":      "🏛 По аукциону",
}

_UNIT_LABELS = {
    "mora":         "🪙",
    "diamonds":     "💎",
    "pets":         "Lv",
    "achievements": "ачив.",
    "msgs":         "сообщ.",
    "streaks":      "дн.",
    "auction":      "продаж",
}


def _top_cat_kb(active_cat: str, active_mode: str) -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat, label in _CAT_LABELS.items():
        mark = "· " if cat == active_cat else ""
        b.button(text=f"{mark}{label}", callback_data=TopCatCB(cat=cat, mode=active_mode))
    mode_lbl = "🌍 Глобально" if active_mode == "local" else "🏘 Локально"
    next_mode = "global" if active_mode == "local" else "local"
    b.button(text=mode_lbl, callback_data=TopCatCB(cat=active_cat, mode=next_mode))
    b.button(text="📊 Активность (периоды)", callback_data=TopCatCB(cat="activity", mode=active_mode))
    b.adjust(1, 1, 1, 1, 1, 1, 1, 1, 2)
    return b.as_markup()


async def _build_cat_top(db, chat_id: int, cat: str, mode: str) -> str:
    is_local = (mode == "local")
    cid = chat_id if is_local else None
    mode_label = "🏘 Локально" if is_local else "🌍 Глобально"
    label = _CAT_LABELS.get(cat, cat)
    unit = _UNIT_LABELS.get(cat, "")

    rows = []
    if cat == "mora":
        rows = await stats.get_top_mora(db, cid)
    elif cat == "diamonds":
        rows = await stats.get_top_diamonds(db, cid)
    elif cat == "pets":
        rows = await stats.get_top_pet_levels(db, cid)
    elif cat == "achievements":
        rows = await stats.get_top_achievements(db, cid)
    elif cat == "msgs":
        rows = await stats.get_top_messages_global(db) if not is_local else \
               await stats.get_top_messages(db, chat_id, "all_time")
        if is_local:
            for r in rows:
                r["value"] = r.get("msg_count", 0)
    elif cat == "streaks":
        rows = await stats.get_top_streaks(db, cid)
    elif cat == "auction":
        rows = await stats.get_top_auction_sales(db, cid)

    if not rows:
        return f"{label} ({mode_label})\n\n<i>Данных пока нет.</i>"

    text = f"{label} — {mode_label}\n\n"
    for idx, row in enumerate(rows[:10], 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏅" if idx <= 10 else f"{idx}."
        uid = row.get("user_tg_id", 0)
        name = safe_html(row.get("user_tg_username") or f"ID{uid}")
        link = f'<a href="tg://user?id={uid}">{name}</a>'
        val = row.get("value", row.get("msg_count", 0))
        if cat in ("mora", "diamonds"):
            val_str = format_currency(float(val))
        else:
            val_str = str(int(val))
        text += f"{medal} {link} — <code>{val_str} {unit}</code>\n"

    return text.rstrip()


@router.callback_query(TopCatCB.filter(F.cat != "activity"))
async def cb_top_cat(query: types.CallbackQuery, callback_data: TopCatCB, db):
    text = await _build_cat_top(db, query.message.chat.id, callback_data.cat, callback_data.mode)
    kb = _top_cat_kb(callback_data.cat, callback_data.mode)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await query.answer()


@router.callback_query(TopCatCB.filter(F.cat == "activity"))
async def cb_top_activity(query: types.CallbackQuery, callback_data: TopCatCB, db):
    text = await build_top_text(db, query.message.chat.id, "all_time")
    kb = generate_top_keyboard("all_time")
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await query.answer()


@router.message(TextCmd(["топ мора", "топ алмазы", "топ питомцев", "топ достижений",
                          "топ стрик", "топ аукцион", "топ сообщений"]))
async def cmd_top_cat_shortcut(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return
    raw = message.text.lower()
    cat_map = {
        "мора": "mora", "алмазы": "diamonds", "питомцев": "pets",
        "достижений": "achievements", "сообщений": "msgs",
        "стрик": "streaks", "аукцион": "auction",
    }
    cat = next((v for k, v in cat_map.items() if k in raw), "mora")
    text = await _build_cat_top(db, message.chat.id, cat, "local")
    await message.answer(text, reply_markup=_top_cat_kb(cat, "local"), parse_mode="HTML")
# ==========================================
# КОМАНДА: /inactive
# ==========================================
@router.message(TextCmd(["неактивные", "призраки", "мертвые", "неактив", "неактив чата"]))
async def cmd_inactive(message: types.Message, db):
    if message.chat.type == "private":
        return await message.answer("❌ <b>Ошибка:</b> Команда доступна только в группах.", parse_mode="HTML")

    inactive_users = await stats.get_inactive_users(db, message.chat.id, days_limit=INACTIVE_THRESHOLD_DAYS)

    if not inactive_users:
        return await message.answer(
            f"👻 <b>НЕАКТИВНЫЕ УЧАСТНИКИ</b>\n\n"
            f"<i>Все участники активно общаются! (Нет молчунов более {INACTIVE_THRESHOLD_DAYS} дней)</i>",
            parse_mode="HTML"
        )

    text = (
        f"👻 <b>НЕАКТИВНЫЕ УЧАСТНИКИ</b>\n"
        f"<i>Не писали в чат более {INACTIVE_THRESHOLD_DAYS} дней:</i>\n\n"
    )

    for u in inactive_users:
        name = safe_html(u['user_tg_username'] or f"Пользователь {u['user_tg_id']}")
        link = f"""<a href="tg://user?id={u['user_tg_id']}">{name}</a>"""
        text += f"├ {link} — <code>{u['days_offline']} дн. назад</code>\n"

    last_pos = text.rfind("├")
    if last_pos >= 0:
        text = text[:last_pos] + "└" + text[last_pos + 1:]

    text += f"\n\n<i>💡 Всего молчунов: <b>{len(inactive_users)}</b></i>"

    await message.answer(text, parse_mode="HTML")