"""
tests/test_cleaning.py — график: версии, перераскладка, отметки, статистика.
"""
from datetime import date, timedelta

import pytest

from services import cleaning, households
from services.households import DomainError

OWNER = 100
ALLY = 200


async def _house_with_two(database):
    house_id = await households.create_house(OWNER, "Владелец", "Тест-дом")
    house = await households.get_house(house_id)
    await households.join_house(house, ALLY, "Напарник")
    return house


def _next_monday(from_date: str) -> str:
    day = date.fromisoformat(from_date)
    while day.weekday() != 0:
        day += timedelta(days=1)
    return day.strftime("%Y-%m-%d")


async def test_planned_days_pure(today):
    monday = _next_monday(today)
    planned = cleaning.planned_days({OWNER: 0, ALLY: None}, monday)
    assert planned[0] == (OWNER, monday)
    assert len(planned) == 2, "в горизонте 14 дней понедельник встречается дважды"
    # Никто не назначен — пусто.
    assert cleaning.planned_days({}, monday) == []


async def test_schedule_save_and_close(database, today):
    house = await _house_with_two(database)
    hid = house["id"]

    # Понедельник — владелец, вторник — напарник.
    await cleaning.save_weekday_map(hid, {OWNER: 0, ALLY: 1}, today)

    monday = _next_monday(today)
    days = await cleaning.days_on(hid, monday)
    assert len(days) == 1 and days[0]["tg_id"] == OWNER and days[0]["status"] == "open"

    # Повторный ensure не плодит дни.
    created = await cleaning.ensure_days(hid, today)
    assert created == 0

    # «Убрался» за эту дату.
    closed = await cleaning.close_own_day(hid, OWNER, monday)
    assert closed["planned_date"] == monday
    with pytest.raises(DomainError):
        await cleaning.close_own_day(hid, OWNER, monday)  # второй раз — нечего закрывать


async def test_close_late_day(database, today):
    """Должен был 22-го, убрался 23-го: план 22-го закрыт фактом 23-го."""
    house = await _house_with_two(database)
    hid = house["id"]
    some_monday = _next_monday(today)
    await cleaning.save_weekday_map(hid, {OWNER: 0}, today)

    closed = await cleaning.close_own_day(hid, OWNER, some_monday)
    assert closed["planned_date"] == some_monday
    rows = await cleaning.month_history(hid, some_monday[:7])
    done = [r for r in rows if r["status"] == "done"]
    assert done and done[0]["actual_date"] == some_monday


async def test_schedule_change_keeps_past(database, today):
    house = await _house_with_two(database)
    hid = house["id"]
    await cleaning.save_weekday_map(hid, {OWNER: 0}, today)
    monday = _next_monday(today)

    # Закрыли день, потом сменили график.
    await cleaning.close_own_day(hid, OWNER, monday)
    await cleaning.save_weekday_map(hid, {ALLY: 0}, today)

    rows = await cleaning.month_history(hid, monday[:7])
    done = [r for r in rows if r["status"] == "done" and r["tg_id"] == OWNER]
    assert done, "закрытый день должен пережить смену графика"
    future_owner = [d for d in await cleaning.days_on(hid, monday) if d["tg_id"] == OWNER]
    assert future_owner and future_owner[0]["status"] == "done", "закрытый день не переложился"


async def test_cancel_and_stats(database, today):
    house = await _house_with_two(database)
    hid = house["id"]
    monday = _next_monday(today)
    await cleaning.save_weekday_map(hid, {OWNER: 0, ALLY: 1}, today)

    days = await cleaning.days_on(hid, monday)
    await cleaning.cancel_day(hid, days[0]["id"], OWNER)

    history = await cleaning.month_history(hid, monday[:7])
    stats = cleaning.member_stats(history)
    assert stats[OWNER]["canceled"] == 1

    with pytest.raises(DomainError):
        await cleaning.cancel_day(hid, days[0]["id"], OWNER)  # повторная отмена


async def test_member_stats_counts(database, today):
    house = await _house_with_two(database)
    hid = house["id"]
    monday = _next_monday(today)
    tuesday = (date.fromisoformat(monday) + timedelta(days=1)).strftime("%Y-%m-%d")
    await cleaning.save_weekday_map(hid, {OWNER: 0, ALLY: 1}, today)

    await cleaning.close_own_day(hid, OWNER, monday)
    history = [row for row in await cleaning.month_history(hid, monday[:7])
               if row["planned_date"] in (monday, tuesday)]
    stats = cleaning.member_stats(history)
    assert stats[OWNER]["done"] == 1
    assert stats[ALLY]["open"] == 1
