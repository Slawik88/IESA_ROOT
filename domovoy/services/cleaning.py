"""
services/cleaning.py — график уборки и дни.

График хранится версиями: правка создаёт новую версию и переложить будущие
открытые дни — одна транзакция. Прошлое не трогается никогда — история честная.
"""
import json
from datetime import date, timedelta

from loguru import logger

from core.constants import DATE_FMT, SCHEDULE_HORIZON_DAYS, WEEKDAY_SHORT
from infrastructure import repositories as repo
from services.households import DomainError, require, require_member

_ANY_SCHEDULE_VERSION = object()


# ── График ───────────────────────────────────────────────────────────────────

async def weekday_map(house_id: int) -> dict[int, int | None]:
    """Активный график: {tg_id: 0..6}. Пусто — график ещё не настроен."""
    version = await repo.schedule.get_latest_version(house_id)
    if version is None:
        return {}
    raw = json.loads(version["weekday_map"])
    return {int(tg_id): weekday for tg_id, weekday in raw.items()}


def planned_days(weekday_map: dict[int, int | None], today: str) -> list[tuple[int, str]]:
    """Даты дней уборки на горизонт планирования по графику. Чистая функция."""
    start = date.fromisoformat(today)
    result: list[tuple[int, str]] = []
    for offset in range(SCHEDULE_HORIZON_DAYS):
        day = start + timedelta(days=offset)
        for tg_id, assigned in weekday_map.items():
            if assigned == day.weekday():
                result.append((tg_id, day.strftime(DATE_FMT)))
    return result


async def save_weekday_map(
    house_id: int, weekday_map: dict[int, int | None], today: str,
    *, expected_version: int | None | object = _ANY_SCHEDULE_VERSION,
) -> int:
    """Новая версия графика + переложить будущие открытые дни — атомарно."""
    if not weekday_map:
        raise DomainError("График не может быть пустым: у кого-то должен быть день")
    for tg_id, weekday in weekday_map.items():
        if weekday is not None and weekday not in range(7):
            raise DomainError("День недели должен быть от Пн до Вс")
    active_members = {member["tg_id"] for member in await repo.houses.list_active_members(house_id)}
    if not set(weekday_map).issubset(active_members):
        raise DomainError("В графике есть участник, который больше не живёт в доме")
    options = {} if expected_version is _ANY_SCHEDULE_VERSION else {"expected_version": expected_version}
    try:
        version_id = await repo.schedule.replace_open_days(
            house_id, json.dumps(weekday_map), today, planned_days(weekday_map, today), **options,
        )
    except repo.schedule.ScheduleConflict as exc:
        raise DomainError("График уже изменили. Обновите его перед сохранением; ваши изменения не записаны.") from exc
    logger.info(f"📅 Дом {house_id}: новая версия графика id={version_id}")
    return version_id


def describe_weekday_map(weekday_map: dict[int, int | None], members: list) -> str:
    """Человекочитаемый график: строки «Пн — Аня»."""
    name_by_tg = {m["tg_id"]: m["display_name"] for m in members}
    by_weekday: dict[int, list[str]] = {}
    for tg_id, weekday in weekday_map.items():
        if weekday is not None:
            by_weekday.setdefault(weekday, []).append(name_by_tg.get(tg_id, f"id{tg_id}"))
    if not by_weekday:
        return "График ещё не настроен."
    return "\n".join(
        f"{WEEKDAY_SHORT[weekday]} — {', '.join(names)}"
        for weekday, names in sorted(by_weekday.items())
    )


# ── Планирование дней ────────────────────────────────────────────────────────

async def ensure_days(house_id: int, today: str) -> int:
    """Разложить дни на горизонт планирования (идемпотентно). Число новых дней."""
    version = await repo.schedule.get_latest_version(house_id)
    if version is None:
        return 0
    active_map = {int(tg_id): weekday for tg_id, weekday in json.loads(version["weekday_map"]).items()}
    return await repo.schedule.add_days_if_current(house_id, version["id"], planned_days(active_map, today))


async def days_on(house_id: int, planned_date: str) -> list:
    return await repo.schedule.days_on(house_id, planned_date)


async def open_days_up_to(house_id: int, today: str) -> list:
    return await repo.schedule.open_days_between(house_id, date.min.isoformat(), today)


# ── Факты ────────────────────────────────────────────────────────────────────

async def close_own_day(house_id: int, tg_id: int, actual_date: str):
    """«Убрался» за конкретную дату: закрывает свой план этой даты, а если его нет —
    самый старый ПРОСРОЧЕННЫЙ день (убрался позже, чем должен был). Будущие дни
    не закрываются никогда."""
    await require_member(house_id, tg_id)
    days = await repo.schedule.days_on(house_id, actual_date)
    own = next(
        (d for d in days if d["tg_id"] == tg_id and d["status"] == "open"),
        await repo.schedule.oldest_open_up_to(house_id, tg_id, actual_date),
    )
    if own is None:
        raise DomainError("У вас нет незакрытых дней уборки — всё чисто!")
    if not await repo.schedule.close_day(own["id"], actual_date, tg_id):
        raise DomainError("Этот день уже закрыт или отменён")
    return own


async def close_day_for(house_id: int, day_id: int, closed_by: int, actual_date: str):
    """Закрыть день за другого с проверкой права close_others_days."""
    day = await repo.schedule.get_day(day_id)
    if day is None or day["house_id"] != house_id or day["status"] != "open":
        raise DomainError("Этот день уже закрыт или отменён")
    if day["planned_date"] > actual_date:
        raise DomainError("Нельзя отметить будущий день уборки")
    if day["tg_id"] == closed_by:
        await require_member(house_id, closed_by)
    else:
        await require(house_id, closed_by, "close_others_days")
    if not await repo.schedule.close_day(day_id, actual_date, closed_by):
        raise DomainError("Этот день уже закрыт или отменён")
    return day


async def cancel_day(house_id: int, day_id: int, closed_by: int):
    """Отменить день (пропуск): остаётся в истории как отменённый."""
    await require(house_id, closed_by, "close_others_days")
    day = await repo.schedule.get_day(day_id)
    if day is None or day["house_id"] != house_id or day["status"] != "open":
        raise DomainError("Этот день уже закрыт или отменён")
    if not await repo.schedule.cancel_day(day_id, closed_by):
        raise DomainError("Этот день уже закрыт или отменён")
    return day


async def month_history(house_id: int, month: str) -> list:
    return await repo.schedule.month_history(house_id, month)


def member_stats(history_rows: list) -> dict[int, dict]:
    """Счётчики по жильцу за месяц: сделано / открыто (пропущено) / отменено."""
    stats: dict[int, dict] = {}
    for row in history_rows:
        entry = stats.setdefault(
            row["tg_id"],
            {"name": row["display_name"], "done": 0, "open": 0, "canceled": 0},
        )
        entry[row["status"]] += 1
    return stats
