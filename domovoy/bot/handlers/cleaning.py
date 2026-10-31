"""
bot/handlers/cleaning.py — «Сегодня», график, отметки уборки, история месяца.
"""
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

from bot import cb, keyboards as kb
from bot.util import fmt_date, guard, resolve_house, safe_edit
from core.constants import DATE_FMT, WEEKDAY_NAMES
from services import cleaning, households, notify
from services import settings as settings_service
from services.money import shift_month

router = Router(name="cleaning")


class ScheduleEdit(StatesGroup):
    editing = State()


async def _context(tg_id: int):
    """(house, settings, today, yesterday); house=None — дом не выбран."""
    house = await resolve_house(tg_id)
    if house is None:
        return None, None, None, None
    settings = await settings_service.house_settings(house["id"])
    today = settings_service.house_today(settings)
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).strftime(DATE_FMT)
    return house, settings, today, yesterday


STATUS_MARK = {"done": "✅", "open": "⏳", "canceled": "⛔"}


# ── Сегодня ──────────────────────────────────────────────────────────────────

async def render_today(cbq: CallbackQuery, state: FSMContext) -> None:
    house, settings, today, yesterday = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return

    days = await cleaning.days_on(house["id"], today)
    if not await cleaning.weekday_map(house["id"]):
        text = "График ещё не настроен. Задать его можно здесь: «График» → «Изменить график»."
    elif not days:
        text = f"На {fmt_date(today)} уборка не запланирована."
    else:
        lines = [f"🧹 Уборка на {fmt_date(today)} "
                 f"({WEEKDAY_NAMES[date.fromisoformat(today).weekday()]})"]
        for day in days:
            mark = STATUS_MARK[day["status"]]
            suffix = "" if day["status"] == "open" else " — день закрыт"
            lines.append(f"{mark} {day['display_name']}{suffix}")
        text = "\n".join(lines)

    my_open_dates = [d["planned_date"] for d in days
                     if d["tg_id"] == cbq.from_user.id and d["status"] == "open"]
    owner_days: list[tuple[int, str]] = []
    if await households.can(house["id"], cbq.from_user.id, "close_others_days"):
        owner_days = [(d["id"], d["display_name"] or "?") for d in days
                      if d["status"] == "open" and d["tg_id"] != cbq.from_user.id]
    await safe_edit(cbq, text, kb.today_keyboard(my_open_dates, today, yesterday, owner_days))


@router.callback_query(F.data == cb.today())
@guard
async def show_today(cbq: CallbackQuery, state: FSMContext):
    await state.clear()
    await render_today(cbq)
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^done:(\d{4}-\d{2}-\d{2})$"))
@guard
async def mark_done(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    actual_date = cb.parse(cbq.data)[1]
    day = await cleaning.close_own_day(house["id"], cbq.from_user.id, actual_date)
    await state.clear()
    await cbq.answer(f"Готово! День {fmt_date(day['planned_date'])} закрыт.", show_alert=True)

    members = await households.members(house["id"])
    name = next((m["display_name"] for m in members if m["tg_id"] == cbq.from_user.id), "Жилец")
    late = "" if day["planned_date"] == actual_date else f" (факт: {fmt_date(actual_date)})"
    await notify.broadcast(
        cbq.bot, house, "cleaning_marked",
        f"✅ {name} закрыл день уборки {fmt_date(day['planned_date'])}{late}",
        exclude_tg_ids={cbq.from_user.id},
    )
    await render_today(cbq)


# ── Чужие дни (право close_others_days) ──────────────────────────────────────

@router.callback_query(F.data.regexp(r"^day_close:(\d+)$"))
@guard
async def close_for_someone(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    day_id = int(cb.parse(cbq.data)[1])
    await households.require(house["id"], cbq.from_user.id, "close_others_days")
    day = await cleaning.close_day_for(house["id"], day_id, cbq.from_user.id, today)
    await state.clear()
    closer = next((m["display_name"] for m in await households.members(house["id"])
                   if m["tg_id"] == cbq.from_user.id), "Владелец")
    await notify.broadcast(
        cbq.bot, house, "cleaning_marked",
        f"✅ {closer} закрыл день уборки {fmt_date(day['planned_date'])} "
        f"за «{day['display_name'] or '?'}»",
        exclude_tg_ids={cbq.from_user.id},
    )
    await cbq.answer("День закрыт")
    await render_today(cbq)


@router.callback_query(F.data.regexp(r"^day_cancel:(\d+)$"))
@guard
async def cancel_day(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    day_id = int(cb.parse(cbq.data)[1])
    await households.require(house["id"], cbq.from_user.id, "close_others_days")
    day = await cleaning.cancel_day(house["id"], day_id, cbq.from_user.id)
    await state.clear()
    await notify.broadcast(
        cbq.bot, house, "cleaning_marked",
        f"⛔ День уборки {fmt_date(day['planned_date'])} («{day['display_name'] or '?'}») отменён",
    )
    await cbq.answer("День отменён")
    await render_today(cbq)


# ── График ───────────────────────────────────────────────────────────────────

async def render_schedule(cbq: CallbackQuery, house) -> None:
    members = await households.members(house["id"])
    text = (f"📅 График уборки — «{house['name']}»\n\n"
            + cleaning.describe_weekday_map(await cleaning.weekday_map(house["id"]), members))
    can_edit = await households.can(house["id"], cbq.from_user.id, "manage_schedule")
    await safe_edit(cbq, text, kb.schedule_keyboard(can_edit))


@router.callback_query(F.data == cb.schedule_view())
@guard
async def show_schedule(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await state.clear()
    await render_schedule(cbq, house)
    await cbq.answer()


@router.callback_query(F.data == cb.schedule_edit())
@guard
async def edit_schedule(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "manage_schedule")
    members = await households.members(house["id"])
    current = await cleaning.weekday_map(house["id"])
    draft = {m["tg_id"]: current.get(m["tg_id"]) for m in members}
    await state.set_state(ScheduleEdit.editing)
    await state.update_data(house_id=house["id"], draft=draft, picked=None)
    await safe_edit(cbq, "Выберите жильца и его день недели.\n«—» — в этот день жилец не убирает.",
                    kb.schedule_editor_keyboard(members, draft))
    await cbq.answer()


async def _redraw_editor(cbq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    members = await households.members(data["house_id"])
    await cbq.message.edit_reply_markup(
        reply_markup=kb.schedule_editor_keyboard(members, data["draft"],
                                                 picked_tg=data.get("picked")))


@router.callback_query(ScheduleEdit.editing, F.data.regexp(r"^sched_m:(\d+)$"))
@guard
async def pick_member(cbq: CallbackQuery, state: FSMContext):
    await state.update_data(picked=int(cb.parse(cbq.data)[1]))
    await _redraw_editor(cbq, state)
    await cbq.answer()


@router.callback_query(ScheduleEdit.editing, F.data.regexp(r"^sched_pick:(\d+):(x|\d)$"))
@guard
async def pick_weekday(cbq: CallbackQuery, state: FSMContext):
    parts = cb.parse(cbq.data)
    tg_id, raw_weekday = int(parts[1]), parts[2]
    data = await state.get_data()
    draft = dict(data["draft"])
    draft[tg_id] = None if raw_weekday == "x" else int(raw_weekday)
    await state.update_data(draft=draft, picked=tg_id)
    await _redraw_editor(cbq, state)
    await cbq.answer()


@router.callback_query(ScheduleEdit.editing, F.data == cb.schedule_save())
@guard
async def save_schedule(cbq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    house = await households.get_house(data["house_id"])
    settings = await settings_service.house_settings(house["id"])
    today = settings_service.house_today(settings)
    await cleaning.save_weekday_map(house["id"], data["draft"], today)
    await state.clear()
    await notify.broadcast(cbq.bot, house, "cleaning_marked",
                           "📅 График уборки обновлён")
    await cbq.message.edit_text(
        f"📅 График сохранён — «{house['name']}»\n\n"
        + cleaning.describe_weekday_map(await cleaning.weekday_map(house["id"]),
                                        await households.members(house["id"])),
        reply_markup=kb.schedule_keyboard(can_edit=True),
    )
    await cbq.answer("Сохранено")


@router.callback_query(ScheduleEdit.editing, F.data == cb.schedule_cancel())
@guard
async def cancel_schedule_edit(cbq: CallbackQuery, state: FSMContext):
    house = await resolve_house(cbq.from_user.id)
    await state.clear()
    if house is not None:
        await render_schedule(cbq, house)
    await cbq.answer()


# ── История месяца ───────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^hist:(current|\d{4}-\d{2})$"))
@guard
async def show_history(cbq: CallbackQuery, state: FSMContext):
    house, settings, today, _ = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await state.clear()
    month = cb.parse(cbq.data)[1]
    if month == "current":
        month = today[:7]
    rows = await cleaning.month_history(house["id"], month)
    lines = [f"🗓 Уборка за {month} — «{house['name']}»", ""]
    if not rows:
        lines.append("Дней не запланировано.")
    for row in rows:
        mark = STATUS_MARK[row["status"]]
        line = f"{mark} {fmt_date(row['planned_date'])} — {row['display_name'] or '?'}"
        if row["status"] == "done" and row["actual_date"] != row["planned_date"]:
            line += f" (факт {fmt_date(row['actual_date'])})"
        lines.append(line)
    stats = cleaning.member_stats(rows)
    if stats:
        lines.append("")
        lines.append("Итоги месяца:")
        for entry in stats.values():
            lines.append(f"  {entry['name']}: убрался {entry['done']}, "
                         f"не закрыто {entry['open']}, отменено {entry['canceled']}")
    year, mon = int(month[:4]), int(month[5:7])
    prev = shift_month(month, -1)
    nxt = shift_month(month, 1)
    can_next = year < int(today[:4]) or (year == int(today[:4]) and mon < int(today[5:7]))
    await safe_edit(cbq, "\n".join(lines), kb.history_keyboard(month, prev, nxt, can_nav_next=can_next))
    await cbq.answer()
