from datetime import datetime, timezone, timedelta

from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from infrastructure.repositories import stats
from infrastructure.repositories import moderation as moderation_repo
from infrastructure.repositories.streak import get_chat_timezone
from services.utils import safe_html, format_currency, check_callback_owner
from services.profile_render import format_display_name
from services.membership import bot_tg_id, prune_ghosts
from services.admin_titles import get_admin_titles, suffix_of, suffixes_for
from bot.filters.text_commands import TextCmd, TopCmd
from core.constants import INACTIVE_THRESHOLD_DAYS
from bot.keyboards.cta import answer_group_only

_TOP_PAGE_SIZE = 30

# Реальные TG-юзернеймы (до 32 симв.) + админ-тайтл/серый тег (до 16 симв.,
# suffixes_for) давали строки топа от ~5 до ~50+ видимых символов подряд без
# всякого предела — на узком экране одни переносились на второй ряд, другие
# нет, без системы («хаос»). Обрезка юзернейма держит длину ряда предсказуемой.
_TOP_NAME_MAX = 14


def _trunc_name(s: str) -> str:
    return s if len(s) <= _TOP_NAME_MAX else s[:_TOP_NAME_MAX - 1] + "…"


router = Router(name="stats_router")


class MessageTopV2(CallbackData, prefix="msgtop"):
    scope: str = "local"   # local | global | chats
    period: str = "week"   # day | week | month | all_time
    user_id: int = 0
    page: int = 0


_V2_PERIOD_NAMES = {
    "day": "Сегодня", "week": "Неделя", "month": "Месяц", "all_time": "Всё время",
}
_V2_SCOPE_NAMES = {
    "local": "Этот чат", "global": "Все игроки", "chats": "Топ чатов",
}


def _period_dates(now: datetime, period: str) -> tuple[str, str] | None:
    if period == "all_time":
        return None
    if period == "day":
        start = end = now.date()
    elif period == "week":
        start, end = now.date() - timedelta(days=now.weekday()), now.date()
    elif period == "month":
        start = now.date().replace(day=1)
        end = now.date()
    else:
        raise ValueError("unsupported top period")
    return start.isoformat(), end.isoformat()


def _previous_dates(dates: tuple[str, str] | None) -> tuple[str, str] | None:
    if dates is None:
        return None
    start = datetime.fromisoformat(dates[0]).date()
    end = datetime.fromisoformat(dates[1]).date()
    span = end - start
    previous_end = start - timedelta(days=1)
    return (previous_end - span).isoformat(), previous_end.isoformat()


async def _top_v2_rows(db, chat_id: int, scope: str, period: str) -> list[dict]:
    # Local periods follow the chat's configured day boundary. Global player
    # and chat rankings use UTC so the same board cannot change by caller chat.
    tz_offset = await get_chat_timezone(db, chat_id) if scope == "local" else 0
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    dates = _period_dates(now, period)
    if scope == "local":
        return (await stats.get_top_messages(db, chat_id, "all_time") if dates is None
                else await stats.get_top_messages_for_dates(db, chat_id, *dates))
    if scope == "global":
        return (await stats.get_top_messages_global_all_time(db) if dates is None
                else await stats.get_top_messages_global_for_dates(db, *dates))
    if scope == "chats":
        return (await stats.get_top_chats_all_time(db) if dates is None
                else await stats.get_top_chats_for_dates(db, *dates))
    raise ValueError("unsupported top scope")


def _top_v2_keyboard(scope: str, period: str, user_id: int, page: int, pages: int):
    b = InlineKeyboardBuilder()
    for value, label in _V2_SCOPE_NAMES.items():
        b.button(text=("✓ " if value == scope else "") + label,
                 callback_data=MessageTopV2(scope=value, period=period, user_id=user_id, page=0))
    for value, label in _V2_PERIOD_NAMES.items():
        b.button(text=("✓ " if value == period else "") + label,
                 callback_data=MessageTopV2(scope=scope, period=value, user_id=user_id, page=0))
    b.adjust(3, 2, 2)
    if pages > 1:
        if page > 0:
            b.button(text="◀", callback_data=MessageTopV2(scope=scope, period=period, user_id=user_id, page=page - 1))
        b.button(text=f"{page + 1}/{pages}", callback_data=MessageTopV2(scope=scope, period=period, user_id=user_id, page=page))
        if page + 1 < pages:
            b.button(text="▶", callback_data=MessageTopV2(scope=scope, period=period, user_id=user_id, page=page + 1))
        b.adjust(3, 2, 2, 3)
    return b.as_markup()


async def _render_top_v2(
    db, chat_id: int, scope: str, period: str, page: int, actor_id: int,
):
    rows = await _top_v2_rows(db, chat_id, scope, period)
    self_id = bot_tg_id()
    if scope != "chats" and self_id is not None:
        rows = [row for row in rows if int(row["user_tg_id"]) != int(self_id)]
    if scope == "local" and rows:
        left = await prune_ghosts(db, chat_id, [int(row["user_tg_id"]) for row in rows])
        rows = [row for row in rows if int(row["user_tg_id"]) not in left]
    pages = max(1, -(-len(rows) // _TOP_PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    visible = rows[page * _TOP_PAGE_SIZE:(page + 1) * _TOP_PAGE_SIZE]
    lines = ["🏆 <b>ТОП ПО СООБЩЕНИЯМ</b>",
             f"{_V2_SCOPE_NAMES[scope]} · {_V2_PERIOD_NAMES[period]}", ""]
    if not visible:
        lines.append("<i>За этот период сообщений пока нет.</i>")
    for offset, row in enumerate(visible, start=page * _TOP_PAGE_SIZE + 1):
        medal = "🥇" if offset == 1 else "🥈" if offset == 2 else "🥉" if offset == 3 else f"{offset}."
        if scope == "chats":
            raw_title = str(row.get("chat_title") or "Чат")
            title = safe_html(raw_title if len(raw_title) <= 32 else raw_title[:31] + "…")
            lines.append(f"{medal} <code>{int(row['msg_count'])}</code> · <b>{title}</b> · {int(row['active_users'])} уч.")
        else:
            uid = int(row["user_tg_id"])
            name = safe_html(_trunc_name(str(row.get("user_tg_username") or f"Игрок {uid}")))
            lines.append(f'{medal} <code>{int(row["msg_count"])}</code> · <a href="tg://user?id={uid}">{name}</a>')
    tz_offset = await get_chat_timezone(db, chat_id) if scope == "local" else 0
    dates = _period_dates(datetime.now(timezone.utc) + timedelta(hours=tz_offset), period)
    entity_id = chat_id if scope == "chats" else actor_id
    position = await stats.get_message_top_position(
        db, scope=scope, entity_id=entity_id, chat_id=chat_id,
        date_start=dates[0] if dates else None, date_end=dates[1] if dates else None,
        excluded_user_id=self_id,
    )
    lines.append("")
    if scope == "chats" and not bool((await moderation_repo.get_chat_settings(db, chat_id)).get("include_in_global_top", 1)):
        lines.append("<i>Этот чат не участвует в глобальном топе по настройке администрации.</i>")
    elif position:
        subject = "Этот чат" if scope == "chats" else "Ваш результат"
        summary = (
            f"{subject}: <b>#{int(position['place'])}</b> из {int(position['total_count'])} · "
            f"<code>{int(position['msg_count'])}</code> сообщ."
        )
        previous = _previous_dates(dates)
        if previous:
            previous_position = await stats.get_message_top_position(
                db, scope=scope, entity_id=entity_id, chat_id=chat_id,
                date_start=previous[0], date_end=previous[1], excluded_user_id=self_id,
            )
            previous_count = int(previous_position["msg_count"]) if previous_position else 0
            delta = int(position["msg_count"]) - previous_count
            summary += f" · к прошлому периоду: <b>{delta:+d}</b>"
        lines.append(summary)
    else:
        lines.append("<i>У вас пока нет сообщений за выбранный период.</i>" if scope != "chats" else
                     "<i>У этого чата пока нет сообщений за выбранный период.</i>")
    return "\n".join(lines), page, pages


@router.message(TopCmd(["топ", "лидеры"], [
    "день", "сегодня", "неделя", "месяц", "все время", "всё время",
    "глобальный", "глобально", "все игроки", "топ чатов", "чатов",
]))
async def cmd_message_top_v2(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)
    raw = str(message.text or "").lower()
    scope = "chats" if "чатов" in raw else "global" if "глоб" in raw or "все игрок" in raw else "local"
    period = "month" if "месяц" in raw else "day" if "сегодня" in raw or "день" in raw else "all_time" if "всё время" in raw or "все время" in raw else "week"
    text, page, pages = await _render_top_v2(db, message.chat.id, scope, period, 0, message.from_user.id)
    await message.answer(text, reply_markup=_top_v2_keyboard(scope, period, message.from_user.id, page, pages), parse_mode="HTML")


@router.callback_query(MessageTopV2.filter())
async def cb_message_top_v2(query: types.CallbackQuery, callback_data: MessageTopV2, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    text, page, pages = await _render_top_v2(
        db, query.message.chat.id, callback_data.scope, callback_data.period,
        callback_data.page, callback_data.user_id,
    )
    try:
        await query.message.edit_text(text, reply_markup=_top_v2_keyboard(callback_data.scope, callback_data.period, callback_data.user_id, page, pages), parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await query.answer()

# Фабрика кнопок для переключения периодов в ТОПе
class TopPeriodData(CallbackData, prefix="top"):
    period: str
    user_id: int = 0
    page: int = 0

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

def generate_top_keyboard(
    current_period: str,
    user_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> types.InlineKeyboardMarkup:
    """Генерирует кнопки периодов + пагинацию."""
    builder = InlineKeyboardBuilder()

    periods = ["day", "week", "all_time", "last_day", "last_week"]
    for p in periods:
        label = f"✅ {PERIOD_NAMES[p]}" if p == current_period else PERIOD_NAMES[p]
        builder.button(text=label, callback_data=TopPeriodData(period=p, user_id=user_id, page=0))

    builder.adjust(2, 2, 1)

    if total_pages > 1:
        nav = InlineKeyboardBuilder()
        prev_page = max(0, page - 1)
        next_page = min(total_pages - 1, page + 1)
        if page > 0:
            nav.button(text="◀️ Назад", callback_data=TopPeriodData(period=current_period, user_id=user_id, page=prev_page))
        nav.button(text=f"📄 {page + 1}/{total_pages}", callback_data=TopPeriodData(period=current_period, user_id=user_id, page=page))
        if page < total_pages - 1:
            nav.button(text="Вперёд ▶️", callback_data=TopPeriodData(period=current_period, user_id=user_id, page=next_page))
        nav.adjust(3)
        builder.attach(nav)

    return builder.as_markup()


async def _get_period_users(db, chat_id: int, period: str) -> list[dict]:
    """Route to the correct query based on period type."""
    if period == "all_time":
        return await stats.get_top_messages(db, chat_id, period)

    tz_offset = await get_chat_timezone(db, chat_id)
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    today = now.strftime("%Y-%m-%d")

    if period == "day":
        return await stats.get_top_messages_for_dates(db, chat_id, today, today)
    elif period == "last_day":
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return await stats.get_top_messages_for_dates(db, chat_id, yesterday, yesterday)
    elif period == "week":
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        return await stats.get_top_messages_for_dates(db, chat_id, week_start, today)
    elif period == "last_week":
        last_week_start = now - timedelta(days=now.weekday() + 7)
        last_week_end = last_week_start + timedelta(days=6)
        return await stats.get_top_messages_for_dates(
            db, chat_id,
            last_week_start.strftime("%Y-%m-%d"),
            last_week_end.strftime("%Y-%m-%d"),
        )
    return await stats.get_top_messages(db, chat_id, "all_time")


async def build_top_text(db, chat_id: int, period: str, page: int = 0) -> tuple[str, int]:
    """Возвращает (текст страницы, total_pages).
    Данные за периоды берутся из daily_user_stats — точный учёт без lazy-reset бага."""
    all_users = await _get_period_users(db, chat_id, period)
    # Бот сам — строка в user_chat_stats, Telegram видит его обычным участником
    # чата (см. bot_tg_id() в services/membership.py) — без исключения он мог
    # попасть в собственный топ активности.
    _self_id = bot_tg_id()
    if _self_id is not None:
        all_users = [u for u in all_users if u["user_tg_id"] != _self_id]
    # Сверка с реальным членством в чате — is_left не всегда успевает обновиться
    # пушем от Telegram (см. services/membership.py), топ не должен показывать
    # тех, кто фактически уже не в чате.
    if all_users:
        left_ids = await prune_ghosts(db, chat_id, [u["user_tg_id"] for u in all_users])
        if left_ids:
            all_users = [u for u in all_users if u["user_tg_id"] not in left_ids]
    period_name = PERIOD_NAMES.get(period, "За всё время")

    if not all_users:
        return f"🏆 <b>ТОП АКТИВНОСТИ</b>\n└ <i>{period_name}: сообщений нет.</i>", 1

    total_pages = max(1, -(-len(all_users) // _TOP_PAGE_SIZE))  # ceiling div
    page = max(0, min(page, total_pages - 1))

    slice_start = page * _TOP_PAGE_SIZE
    slice_end = slice_start + _TOP_PAGE_SIZE
    page_users = all_users[slice_start:slice_end]

    _suffixes = await suffixes_for(chat_id, [u["user_tg_id"] for u in page_users])
    lines = [f"🏆 <b>ТОП АКТИВНОСТИ</b>\n📅 <b>Период:</b> {period_name}\n"]
    for local_idx, user in enumerate(page_users, 1):
        global_idx = slice_start + local_idx
        medal = "🥇" if global_idx == 1 else "🥈" if global_idx == 2 else "🥉" if global_idx == 3 else "🏅" if global_idx <= 10 else f"{global_idx}."
        uname = user["user_tg_username"]
        name = format_display_name(
            safe_html(_trunc_name(uname) if uname else f"Пользователь {user['user_tg_id']}"),
            user["is_vip"],
        )
        name += _suffixes.get(user["user_tg_id"], "")
        link = f'<a href="tg://user?id={user["user_tg_id"]}">{name}</a>'
        # Число — сразу после медали, до имени: если длинное имя уедет переносом
        # на новую строку, число уже видно, а не «повисает» без контекста.
        lines.append(f"{medal} <code>{user['msg_count']}</code>  {link}")

    return "\n".join(lines), total_pages

# ==========================================
# КОМАНДА: /top
# ==========================================
async def cmd_top(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)

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

    text, total_pages = await build_top_text(db, message.chat.id, period, page=0)
    keyboard = generate_top_keyboard(period, user_id=message.from_user.id, page=0, total_pages=total_pages)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# Обработчик кнопок ТОПа
async def process_top_period(callback: types.CallbackQuery, callback_data: TopPeriodData, db):
    if not await check_callback_owner(callback, callback_data.user_id):
        return
    text, total_pages = await build_top_text(db, callback.message.chat.id, callback_data.period, callback_data.page)
    keyboard = generate_top_keyboard(
        callback_data.period,
        user_id=callback_data.user_id,
        page=callback_data.page,
        total_pages=total_pages,
    )
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
    user_id: int = 0


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

    _self_id = bot_tg_id()
    if _self_id is not None and rows:
        rows = [r for r in rows if r.get("user_tg_id", 0) != _self_id]

    # Локальный топ — сверяем с реальным членством чата (см. build_top_text).
    # Глобальный режим (cid=None) охватывает много чатов сразу — членство одного
    # чата тут не определяет попадание в топ, сверять нечего.
    if is_local and rows:
        left_ids = await prune_ghosts(db, chat_id, [r.get("user_tg_id", 0) for r in rows])
        if left_ids:
            rows = [r for r in rows if r.get("user_tg_id", 0) not in left_ids]

    if not rows:
        return f"{label} ({mode_label})\n\n<i>Данных пока нет.</i>"

    _suffixes = await suffixes_for(chat_id, [r.get("user_tg_id", 0) for r in rows[:10]])
    text = f"{label} — {mode_label}\n\n"
    for idx, row in enumerate(rows[:10], 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else "🏅" if idx <= 10 else f"{idx}."
        uid = row.get("user_tg_id", 0)
        uname = row.get("user_tg_username")
        name = safe_html(_trunc_name(uname) if uname else f"ID{uid}") + _suffixes.get(uid, "")
        link = f'<a href="tg://user?id={uid}">{name}</a>'
        val = row.get("value", row.get("msg_count", 0))
        if cat in ("mora", "diamonds"):
            val_str = format_currency(float(val))
        else:
            val_str = str(int(val))
        # Число — сразу после медали, до имени: см. build_top_text() выше — та же
        # причина (длинное имя не должно оставлять число «висеть» без контекста).
        text += f"{medal} <code>{val_str} {unit}</code>  {link}\n"

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
    scope = "global" if callback_data.mode == "global" else "local"
    text, page, pages = await _render_top_v2(
        db, query.message.chat.id, scope, "week", 0, query.from_user.id,
    )
    kb = _top_v2_keyboard(scope, "week", query.from_user.id, page, pages)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await query.answer()


@router.message(TextCmd(["топ мора", "топ алмазы", "топ питомцев", "топ достижений",
                          "топ стрик", "топ аукцион", "топ сообщений"]))
async def cmd_top_cat_shortcut(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return await answer_group_only(message)
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
        return await answer_group_only(message)

    inactive_users = await stats.get_inactive_users(db, message.chat.id, days_limit=INACTIVE_THRESHOLD_DAYS)
    _self_id = bot_tg_id()
    if _self_id is not None:
        inactive_users = [u for u in inactive_users if u["user_tg_id"] != _self_id]
    if inactive_users:
        left_ids = await prune_ghosts(db, message.chat.id, [u["user_tg_id"] for u in inactive_users])
        if left_ids:
            inactive_users = [u for u in inactive_users if u["user_tg_id"] not in left_ids]

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

    _titles = await get_admin_titles(message.chat.id)
    for u in inactive_users:
        name = safe_html(u['user_tg_username'] or f"Пользователь {u['user_tg_id']}")
        name += suffix_of(_titles, u['user_tg_id'])
        link = f"""<a href="tg://user?id={u['user_tg_id']}">{name}</a>"""
        text += f"├ {link} — <code>{u['days_offline']} дн. назад</code>\n"

    last_pos = text.rfind("├")
    if last_pos >= 0:
        text = text[:last_pos] + "└" + text[last_pos + 1:]

    text += f"\n\n<i>💡 Всего молчунов: <b>{len(inactive_users)}</b></i>"

    await message.answer(text, parse_mode="HTML")
