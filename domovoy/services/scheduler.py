"""
services/scheduler.py — напоминания: утро, вечер, месячный отчёт.

Цикл (раз в минуту) живёт в боте; логика тика — здесь, чтобы её можно было
проверить тестами. Каждая сработка отмечается в scheduler_log — после рестарта
ничего не уходит дважды (идемпотентность).
"""
from datetime import date as date_cls

from loguru import logger

from core.constants import DEFAULT_MONTHLY_REPORT_HOUR, DATE_FMT
from infrastructure import repositories as repo
from services import cleaning, money as money_service, notify, reports
from services import settings as settings_service

EVENT_MORNING = "morning"
EVENT_EVENING = "evening"
EVENT_REPORT = "monthly_report"


async def tick(bot) -> None:
    """Один проход по всем домам: сработавшие события отправляются один раз в день."""
    for house in await repo.houses.list_all():
        try:
            await _tick_house(bot, house)
        except Exception as exc:
            # Один дом не должен ронять напоминания остальным.
            logger.exception(f"⏰ Тик по дому {house['id']} упал: {exc}")


async def _tick_house(bot, house) -> None:
    settings = await settings_service.house_settings(house["id"])
    now = settings_service.house_now(settings)
    today = now.strftime(DATE_FMT)

    if now.day == 1 and now.hour >= DEFAULT_MONTHLY_REPORT_HOUR and settings["monthly_report"]:
        await _send_once(bot, house, EVENT_REPORT, today, _monthly_report_job)

    if now.hour >= int(settings["morning_hour"]):
        await _send_once(bot, house, EVENT_MORNING, today, _morning_job)

    if settings["evening_repeat"] and now.hour >= int(settings["evening_hour"]):
        await _send_once(bot, house, EVENT_EVENING, today, _evening_job)


async def _send_once(bot, house, event_key: str, day: str, job) -> None:
    if await repo.settings.scheduler_already_sent(house["id"], event_key, day):
        return
    await job(bot, house, day)
    await repo.settings.scheduler_mark_sent(house["id"], event_key, day)


async def _morning_job(bot, house, today: str) -> None:
    await cleaning.ensure_days(house["id"], today)
    open_days = [d for d in await cleaning.days_on(house["id"], today) if d["status"] == "open"]
    if not open_days:
        return
    texts = {}
    for day in open_days:
        texts[day["tg_id"]] = (
            f"🧹 Сегодня ваш день уборки в «{house['name']}».\n"
            f"Как уберётесь — нажмите «Убрался» в меню."
        )
    await notify.deliver(bot, house, "morning_reminder", texts)


async def _evening_job(bot, house, today: str) -> None:
    earliest = date_cls(2000, 1, 1).strftime(DATE_FMT)
    open_days = await repo.schedule.open_days_between(house["id"], earliest, today)
    if not open_days:
        return
    texts = {}
    for day in open_days:
        texts[day["tg_id"]] = (
            f"🌙 День уборки {day['planned_date']} в «{house['name']}» ещё не закрыт.\n"
            f"Если убрались — нажмите «Убрался», если день пропущен — владелец отменит его."
        )
    await notify.deliver(bot, house, "evening_reminder", texts)


async def _monthly_report_job(bot, house, today: str) -> None:
    month = money_service.shift_month(today[:7], -1)
    text = await reports.month_report_text(house, month)
    await notify.broadcast(bot, house, "monthly_report", text)
