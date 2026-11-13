"""
tests/test_cleaning.py — график: версии, перераскладка, отметки, статистика.
"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import cleaning, households, scheduler, settings
from services.households import DomainError
from infrastructure.repositories import houses, schedule
from infrastructure.db import _SqliteConn

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


async def test_old_ensure_cannot_restore_days_after_schedule_replacement(database, monkeypatch):
    house = await _house_with_two(database)
    house_id, monday = house["id"], "2026-11-02"
    await cleaning.save_weekday_map(house_id, {OWNER: 0}, monday)
    original = schedule.add_days_if_current

    async def replace_before_ensure(target_house, version_id, planned):
        await cleaning.save_weekday_map(target_house, {ALLY: 1}, monday)
        return await original(target_house, version_id, planned)

    monkeypatch.setattr(schedule, "add_days_if_current", replace_before_ensure)
    assert await cleaning.ensure_days(house_id, monday) == 0
    assert await cleaning.weekday_map(house_id) == {ALLY: 1}
    assert await cleaning.days_on(house_id, monday) == []
    tuesday = await cleaning.days_on(house_id, "2026-11-03")
    assert len(tuesday) == 1 and tuesday[0]["tg_id"] == ALLY


async def test_ensure_skips_member_who_left_after_schedule_was_read(database, monkeypatch):
    house = await _house_with_two(database)
    house_id, monday = house["id"], "2026-11-02"
    await cleaning.save_weekday_map(house_id, {ALLY: 0}, monday)
    original = schedule.add_days_if_current

    async def leave_before_ensure(target_house, version_id, planned):
        await households.leave_house(target_house, ALLY)
        return await original(target_house, version_id, planned)

    monkeypatch.setattr(schedule, "add_days_if_current", leave_before_ensure)
    assert await cleaning.ensure_days(house_id, "2026-11-16") == 0
    assert await cleaning.days_on(house_id, "2026-11-16") == []


async def test_leaving_clears_future_open_days_and_reminders_but_preserves_history(database, monkeypatch):
    house = await _house_with_two(database)
    house_id, today = house["id"], "2026-11-02"
    monkeypatch.setattr(settings, "house_today", lambda values: today)
    await cleaning.save_weekday_map(house_id, {ALLY: 0}, today)
    await households.set_grant(house_id, ALLY, "manage_categories", True)
    for day in ("2026-10-31", "2026-11-01", "2026-11-03", "2026-11-05"):
        await schedule.add_day(house_id, ALLY, day)
    done = (await schedule.days_on(house_id, "2026-10-31"))[0]
    canceled = (await schedule.days_on(house_id, "2026-11-05"))[0]
    await schedule.close_day(done["id"], "2026-10-31", ALLY)
    await schedule.cancel_day(canceled["id"], OWNER)

    await households.leave_house(house_id, ALLY)

    assert (await households.membership(house_id, ALLY))["status"] == "left"
    assert await households.grants_of(house_id, ALLY) == frozenset()
    assert (await schedule.get_day(done["id"]))["status"] == "done"
    assert (await schedule.get_day(canceled["id"]))["status"] == "canceled"
    assert await schedule.days_on(house_id, "2026-11-01")
    assert await schedule.days_on(house_id, today)
    assert await schedule.days_on(house_id, "2026-11-03") == []
    assert await schedule.days_on(house_id, "2026-11-09") == []
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler._morning_job(bot, house, today)
    await scheduler._evening_job(bot, house, today)
    bot.send_message.assert_not_awaited()


async def test_leave_rolls_back_membership_and_grants_if_day_cleanup_fails(database, monkeypatch):
    house = await _house_with_two(database)
    house_id = house["id"]
    await households.set_grant(house_id, ALLY, "manage_categories", True)
    original = _SqliteConn.execute

    async def fail_cleanup(connection, sql, *args):
        if sql.startswith("DELETE FROM cleaning_days"):
            raise RuntimeError("cleanup unavailable")
        return await original(connection, sql, *args)

    monkeypatch.setattr(_SqliteConn, "execute", fail_cleanup)
    with pytest.raises(RuntimeError, match="cleanup unavailable"):
        await households.leave_house(house_id, ALLY)
    assert (await households.membership(house_id, ALLY))["status"] == "active"
    assert await households.can(house_id, ALLY, "manage_categories")


async def test_schedule_validated_before_leave_cannot_restore_departed_future_days(database, monkeypatch):
    house = await _house_with_two(database)
    house_id, today = house["id"], "2026-11-02"
    original = schedule.replace_open_days

    async def leave_before_replace(*args, **kwargs):
        await households.leave_house(house_id, ALLY)
        return await original(*args, **kwargs)

    monkeypatch.setattr(schedule, "replace_open_days", leave_before_replace)
    await cleaning.save_weekday_map(house_id, {ALLY: 1}, today)
    assert await schedule.days_on(house_id, "2026-11-03") == []
    assert await schedule.days_on(house_id, "2026-11-10") == []


async def test_grant_checked_before_leave_cannot_restore_departed_permissions(database, monkeypatch):
    house = await _house_with_two(database)
    house_id = house["id"]
    original = houses.grant

    async def leave_before_grant(*args):
        await households.leave_house(house_id, ALLY)
        return await original(*args)

    monkeypatch.setattr(houses, "grant", leave_before_grant)
    with pytest.raises(DomainError, match="уже вышел"):
        await households.set_grant(house_id, ALLY, "manage_categories", True)
    assert await households.grants_of(house_id, ALLY) == frozenset()
