"""Private chat menus, validated personal preferences and delivery worker."""

import asyncio
import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .models import SOURCES, Listing, safe_url
from .scanner import query_key
from .sources import search_url
from .telegram import TelegramError

log = logging.getLogger(__name__)
TZ = ZoneInfo("Europe/Zurich")


def buttons(rows):
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": action} for label, action in row]
            for row in rows
        ]
    }


def when(timestamp):
    return (
        datetime.fromtimestamp(timestamp, TZ).strftime("%d.%m %H:%M")
        if timestamp
        else "ещё не было"
    )


def summary(search):
    return (
        "<b>Мой поиск жилья</b>\n\n"
        + "Города: "
        + escape(", ".join(search.cities))
        + "\n"
        + f"Бюджет: до {search.max_price} CHF/месяц\n"
        + f"Комнаты: {search.min_rooms:g}–{search.max_rooms:g}\n"
        + f"Площадь: от {search.min_area} м²\n"
        + f"Проверки: раз в {search.interval // 60} мин. + время ответа сайтов\n"
        + "Сайты: "
        + (", ".join(SOURCES[s] for s in search.sources) or "все выключены")
        + "\n"
        + "Не показывать: "
        + escape(search.exclude or "без исключений")
        + "\n\n"
        + ("Уведомления на паузе." if search.paused else "Уведомления включены.")
        + "\nНастройки относятся только к вашему поиску. Квартиры и дома; без WG, парковок и обмена."
    )


def main_keyboard(search):
    return buttons(
        [
            [("Бюджет", "edit:price"), ("Комнаты", "edit:rooms")],
            [("Города", "edit:cities"), ("Площадь", "edit:area")],
            [("Сайты", "sources"), ("Частота", "edit:interval")],
            [("Исключения", "edit:exclude")],
            [("Подходящие сейчас", "current"), ("Статус сайтов", "status")],
            [
                (
                    "Возобновить" if search.paused else "Пауза",
                    "resume" if search.paused else "pause",
                )
            ],
        ]
    )


def listing_text(listing, *, detected=None, current=False):
    title = "Подходит под ваш поиск" if current else "Найдено новое совпадение"
    text = f"<b>{title}</b> · {SOURCES[listing.source]}\n\n<b>{escape(listing.title[:240])}</b>\n"
    text += escape(listing.address or listing.city) + "\n"
    text += f"{listing.price:g} CHF/месяц · {listing.rooms:g} комн."
    if listing.area is not None:
        text += f" · {listing.area:g} м²"
    text += "\n" + escape(listing.price_note) + "\n"
    if detected:
        text += "Проверено: " + when(detected) + " (Цюрих)\n"
    return (
        text
        + '\n<a href="'
        + escape(listing.url, quote=True)
        + '">Открыть объявление</a>'
    )


PROMPTS = {
    "price": "Введите максимальный бюджет в CHF/месяц, например 1500.",
    "rooms": "Введите минимум и максимум комнат через пробел, например 1.5 2.5.",
    "cities": "Введите города латиницей через запятую (до 5). Например: Wetzikon ZH, Uster, Hinwil. Для неоднозначных названий укажите кантон.",
    "area": "Введите минимальную площадь в м². Например 40; 0 — без ограничения.",
    "interval": "Введите интервал от 2 до 60 минут. Фактическая задержка зависит от сайта; при блокировках бот увеличит паузу.",
    "exclude": "Какие слова исключить из заголовка и адреса? Через запятую, например: befristet, möbliert. Отправьте 0, чтобы убрать исключения.",
}


def updated_search(search, field, text):
    candidate = replace(search)
    if field == "price":
        candidate.max_price = int(text.replace("'", "").replace(" ", ""))
    elif field == "rooms":
        match = re.fullmatch(
            r"\s*(\d+(?:[.,]\d+)?)\s*(?:[;–-]|\s)\s*(\d+(?:[.,]\d+)?)\s*", text
        )
        if not match:
            raise ValueError("Нужны два числа, например: 1.5 2.5.")
        candidate.min_rooms, candidate.max_rooms = (
            float(x.replace(",", ".")) for x in match.groups()
        )
    elif field == "cities":
        candidate.cities = list(
            dict.fromkeys(x.strip() for x in text.split(",") if x.strip())
        )
        # A previous city-specific URL must not override a newly selected town.
        candidate.urls = {}
    elif field == "area":
        candidate.min_area = int(text)
    elif field == "interval":
        candidate.interval = int(text) * 60
    elif field == "exclude":
        candidate.exclude = "" if text.strip() == "0" else text.strip()
    else:
        raise ValueError("Неизвестная настройка. Откройте /settings.")
    return candidate.validate()


class Bot:
    def __init__(self, store, telegram, allowed_ids):
        self.store, self.telegram, self.allowed_ids = store, telegram, set(allowed_ids)

    async def menu(self, user_id, prefix=""):
        search = self.store.search(user_id)
        await self.telegram.send(
            user_id, prefix + summary(search), main_keyboard(search)
        )

    async def handle(self, update):
        callback = update.get("callback_query")
        message = (callback or {}).get("message") or update.get("message") or {}
        sender = (callback or message).get("from", {})
        user_id = sender.get("id")
        private = (
            message.get("chat", {}).get("type") == "private"
            and message.get("chat", {}).get("id") == user_id
        )
        if user_id not in self.allowed_ids or not private:
            if callback:
                await self.telegram.call(
                    "answerCallbackQuery",
                    callback_query_id=callback["id"],
                    text="Бот доступен только двум приглашённым пользователям.",
                    show_alert=True,
                )
            return
        self.store.ensure_user(user_id)
        self.store.set_user(user_id, active=True)
        if callback:
            await self.telegram.call(
                "answerCallbackQuery", callback_query_id=callback["id"]
            )
            action = callback.get("data", "")
            if action.startswith("edit:"):
                return await self.prompt(user_id, action.split(":", 1)[1])
            if action.startswith("set:"):
                _, field, value = action.split(":", 2)
                return await self.save(user_id, field, value)
            if action.startswith("toggle:"):
                source = action.split(":", 1)[1]
                if source not in SOURCES:
                    return
                search = self.store.search(user_id)
                search.sources = (
                    [s for s in search.sources if s != source]
                    if source in search.sources
                    else search.sources + [source]
                )
                self.store.save_search(user_id, search)
                return await self.sources(user_id)
            self.store.set_user(user_id, pending="")
            return await self.action(user_id, action)
        text = message.get("text", "").strip()
        if not text:
            return
        if text.startswith("/"):
            command, _, args = text.partition(" ")
            command = command.split("@")[0][1:].lower()
            if command in {"price", "rooms", "cities", "area", "interval", "exclude"}:
                return (
                    await self.save(user_id, command, args)
                    if args
                    else await self.prompt(user_id, command)
                )
            if command == "url":
                return await self.custom_url(user_id, args)
            self.store.set_user(user_id, pending="")
            return await self.action(user_id, command)
        pending = self.store.user(user_id)["pending"]
        if pending:
            return await self.save(user_id, pending, text)
        await self.menu(user_id, "Выберите настройку кнопкой ниже.\n\n")

    async def save(self, user_id, field, value):
        try:
            search = updated_search(self.store.search(user_id), field, value)
        except (ValueError, OverflowError) as exc:
            explanation = (
                str(exc)
                if isinstance(exc, ValueError) and "invalid literal" not in str(exc)
                else "Введите целое число."
            )
            await self.telegram.send(
                user_id,
                escape(explanation)
                + "\n\n"
                + PROMPTS.get(field, "Откройте /settings."),
                buttons([[("Отменить", "settings")]]),
            )
            self.store.set_user(user_id, pending=field)
            return
        self.store.save_search(user_id, search)
        self.store.set_user(user_id, pending="")
        await self.menu(
            user_id, "Сохранено. Фильтр применится к следующим уведомлениям.\n\n"
        )

    async def prompt(self, user_id, field):
        if field not in PROMPTS:
            return
        self.store.set_user(user_id, pending=field)
        presets = {
            "price": [("1350 CHF", "1350"), ("1500 CHF", "1500"), ("1800 CHF", "1800")],
            "rooms": [("1–2.5", "1 2.5"), ("1.5–2.5", "1.5 2.5"), ("2–3.5", "2 3.5")],
            "interval": [
                ("2 мин.", "2"),
                ("3 мин.", "3"),
                ("5 мин.", "5"),
                ("10 мин.", "10"),
            ],
        }
        rows = (
            [[(label, "set:" + field + ":" + value) for label, value in presets[field]]]
            if field in presets
            else []
        )
        rows.append([("Отменить", "settings")])
        await self.telegram.send(user_id, PROMPTS[field], buttons(rows))

    async def sources(self, user_id):
        self.store.set_user(user_id, pending="")
        search = self.store.search(user_id)
        rows = [
            [
                (
                    ("Вкл. · " if source in search.sources else "Выкл. · ") + label,
                    "toggle:" + source,
                )
            ]
            for source, label in SOURCES.items()
        ]
        rows.append([("Назад к настройкам", "settings")])
        await self.telegram.send(
            user_id,
            "<b>Сайты для вашего поиска</b>\nНажмите на сайт, чтобы включить или выключить. Блокировки и ошибки видны в «Статус сайтов».\n\nHomegate и ImmoScout24 могут отклонять прямые проверки; часть их объявлений встречается на агрегаторах.",
            buttons(rows),
        )

    async def status(self, user_id):
        search = self.store.search(user_id)
        text = "<b>Статус проверок</b>\nВремя — Europe/Zurich. Интервал — желаемая частота; публикации и блокировки сайтов влияют на задержку.\n"
        if search.paused:
            text += "\nВаш поиск на паузе.\n"
        rows = self.store.db.execute(
            "SELECT * FROM queries ORDER BY checked DESC"
        ).fetchall()
        for source in search.sources:
            keys = {
                query_key(
                    source, city, search.urls.get(source) or search_url(source, city)
                )
                for city in search.cities
            }
            selected = [r for r in rows if r["key"] in keys]
            text += "\n\n<b>" + SOURCES[source] + "</b>\n"
            if not selected:
                text += "Ожидает первой проверки.\n"
            for row in selected[:5]:
                text += escape(row["city"]) + ": "
                if row["error"]:
                    text += (
                        escape(row["error"])
                        + "; повтор не раньше "
                        + when(row["next_run"])
                    )
                    text += "\nПоследняя успешная: " + when(row["success"])
                elif row["success"]:
                    text += f"проверено {when(row['success'])}, найдено {row['count']} до ваших фильтров"
                    if row["partial"]:
                        text += "; охват ограничен, показана часть выдачи"
                else:
                    text += "в очереди"
                text += "\n"
            link = search.urls.get(source) or search_url(source, search.cities[0])
            text += (
                '<a href="'
                + escape(link, quote=True)
                + '">Открыть поиск на сайте</a>\n'
            )
        if not search.sources:
            text += "\nВсе сайты выключены. Включите их в настройках."
        text += "\nПервый успешный проход запоминает текущую выдачу без массовой рассылки. Существующие варианты — «Подходящие сейчас»."
        # At most five towns × seven sources; split only at paragraph boundaries.
        parts, chunk = [], ""
        for section in text.split("\n\n"):
            if len(chunk) + len(section) > 3700:
                parts.append(chunk)
                chunk = ""
            chunk += section + "\n\n"
        parts.append(chunk)
        for part in parts:
            await self.telegram.send(
                user_id, part, buttons([[("Настройки", "settings")]])
            )

    async def current(self, user_id):
        matches = self.store.recent(self.store.search(user_id))
        if not matches:
            await self.telegram.send(
                user_id,
                "В сохранённой выдаче за последние сутки подходящих вариантов пока нет. Если вы только начали поиск, дождитесь первого прохода. Доступность и охват каждого сайта — в статусе.",
                buttons([[("Статус сайтов", "status"), ("Настройки", "settings")]]),
            )
            return
        await self.telegram.send(
            user_id,
            "До 10 подходящих вариантов из последних проверок. Время проверки указано у каждого: доступность объявления уточняйте на сайте.",
        )
        for listing, checked in matches:
            await self.telegram.send(
                user_id, listing_text(listing, detected=checked, current=True)
            )

    async def custom_url(self, user_id, args):
        source, _, value = args.partition(" ")
        if source not in SOURCES or not value or source == "flatfox":
            await self.telegram.send(
                user_id,
                "Своя ссылка поиска: /url huusbro https://huusbro.ch/de/mieten/wetzikon\nУбрать: /url huusbro reset\nДля Flatfox карта строится по выбранным городам. После смены городов свои ссылки сбрасываются.",
            )
            return
        search = self.store.search(user_id)
        try:
            if value == "reset":
                search.urls.pop(source, None)
            else:
                search.urls[source] = safe_url(value.strip(), source)
            self.store.save_search(user_id, search)
        except ValueError as exc:
            await self.telegram.send(user_id, escape(str(exc)))
            return
        await self.menu(
            user_id,
            "Ссылка сохранена. Ваши фильтры проверяются дополнительно по объявлению.\n\n",
        )

    async def action(self, user_id, action):
        if action in {"start", "settings", "cancel"}:
            prefix = (
                "Ищу жильё на семи сайтах и присылаю новые совпадения. Начальные параметры — Wetzikon ZH, до 1500 CHF, 1.5–2.5 комнаты; измените их кнопками. Первую выдачу можно посмотреть в «Подходящие сейчас».\n\n"
                if action == "start"
                else ""
            )
            return await self.menu(user_id, prefix)
        if action in {"pause", "resume"}:
            search = self.store.search(user_id)
            search.paused = action == "pause"
            self.store.save_search(user_id, search)
            return await self.menu(user_id)
        if action == "sources":
            return await self.sources(user_id)
        if action == "current":
            return await self.current(user_id)
        if action == "status":
            return await self.status(user_id)
        await self.telegram.send(
            user_id,
            "Настройте поиск кнопками /settings.\n\nМожно и командами:\n/price 1500\n/rooms 1.5 2.5\n/cities Wetzikon ZH, Uster\n/area 40\n/interval 3\n/exclude befristet, möbliert\n\n/current — текущие варианты\n/status — состояние сайтов\n/pause и /resume — уведомления\n/cancel — отменить ввод\n\nБот работает только в ЛС двух приглашённых пользователей. Не все сайты отдают полную выдачу; статус сообщает о блокировках и ограничениях.",
            buttons([[("Настройки", "settings")]]),
        )

    async def poll(self):
        offset = self.store.get("telegram_offset", 0)
        while True:
            try:
                updates = await self.telegram.call(
                    "getUpdates",
                    offset=offset,
                    timeout=45,
                    allowed_updates=["message", "callback_query"],
                )
                for update in updates:
                    try:
                        await self.handle(update)
                    except TelegramError as exc:
                        if exc.code == 429 or exc.code == 0 or exc.code >= 500:
                            raise
                        log.warning("update response failed code=%s", exc.code)
                    # Only acknowledge updates after handling; transient failures are retried.
                    offset = update["update_id"] + 1
                    self.store.put("telegram_offset", offset)
            except TelegramError as exc:
                if exc.code in {401, 409}:
                    raise RuntimeError(
                        "Telegram authorization or competing polling receiver"
                    ) from None
                log.warning("poll retry code=%s", exc.code)
                await asyncio.sleep(min(300, max(5, exc.retry)))

    async def deliver(self):
        while True:
            for row in self.store.pending():
                user_id = row["user_id"]
                user = self.store.user(user_id)
                listing = Listing(**json.loads(row["data"]))
                if user_id not in self.allowed_ids or not user or not user["active"]:
                    self.store.delivery_result(row, "cancelled")
                    continue
                search = self.store.search(user_id)
                if (
                    search.paused
                    or not search.matches(listing)
                    or row["created"] < time.time() - 86400
                ):
                    self.store.delivery_result(row, "cancelled")
                    continue
                try:
                    await self.telegram.send(
                        user_id, listing_text(listing, detected=row["created"])
                    )
                except TelegramError as exc:
                    if exc.code in {400, 403}:
                        self.store.set_user(user_id, active=False)
                        self.store.delivery_result(row, "cancelled")
                    elif exc.code == 401:
                        raise RuntimeError("Telegram token rejected") from None
                    else:
                        self.store.delivery_result(
                            row,
                            "pending",
                            min(
                                3600, max(exc.retry, 30 * 2 ** min(row["attempts"], 6))
                            ),
                        )
                        if exc.code == 429:
                            await asyncio.sleep(min(300, exc.retry))
                else:
                    self.store.delivery_result(row, "sent")
                await asyncio.sleep(1)
            await asyncio.sleep(3)
