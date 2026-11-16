"""Private chat screens, stable listing pages and idempotent saved-item actions."""

import math
import secrets
import time
from html import escape

from .models import SOURCES
from .scanner import query_key
from .sources import search_url
from .views import (
    buttons,
    listing_keyboard,
    listing_text,
    main_keyboard,
    money,
    settings_screen,
    summary,
    when,
)

PROMPTS = {
    "price": (
        "Бюджет",
        "Максимальная аренда в CHF за месяц. Выберите сумму или напишите свою, например 1500.",
    ),
    "rooms": (
        "Комнаты",
        "Выберите диапазон или напишите два числа: 1.5 2.5. Можно с запятой: 1,5 2,5.",
    ),
    "cities": (
        "Где ищем?",
        "Выберите город или напишите до пяти через запятую: Wetzikon ZH, Uster, Hinwil. Названия — латиницей.",
    ),
    "area": (
        "Площадь",
        "Минимальная площадь в м². Выберите значение или напишите своё; 0 — любая площадь.",
    ),
    "interval": (
        "Частота проверок",
        "Интервал от 2 до 60 минут. Из-за задержек или блокировок сайтов проверка может занять больше времени.",
    ),
    "exclude": (
        "Что не показывать?",
        "Слова из заголовка или адреса через запятую, например: befristet, möbliert. Чтобы очистить список, отправьте 0.",
    ),
}


class Screens:
    async def show(self, user_id, text, keyboard):
        result = await self.telegram.panel(
            user_id, text, keyboard, self.panels.get(user_id)
        )
        if isinstance(result, dict) and isinstance(result.get("message_id"), int):
            self.panels[user_id] = result["message_id"]
            self.store.put("panel:" + str(user_id), result["message_id"])

    def query_rows(self, user_id, source):
        search = self.store.search(user_id)
        cities = search.cities[:1] if source in search.urls else search.cities
        keys = [
            query_key(source, city, search.urls.get(source) or search_url(source, city))
            for city in cities
        ]
        return [
            row
            for key in keys
            if (
                row := self.store.db.execute(
                    "SELECT * FROM queries WHERE key=?", (key,)
                ).fetchone()
            )
        ]

    def source_state(self, user_id, source):
        search = self.store.search(user_id)
        rows = self.query_rows(user_id, source)
        if source not in search.sources:
            return "выключен"
        expected = 1 if source in search.urls else len(search.cities)
        if len(rows) < expected or any(not r["checked"] for r in rows):
            return "ожидает проверки"
        if any(r["error"] for r in rows):
            return "недоступен"
        if any(
            not r["success"]
            or time.time() - r["success"] > max(600, 3 * search.interval)
            for r in rows
        ):
            return "давно не обновлялся"
        if any(r["partial"] for r in rows):
            return "часть выдачи"
        return "есть данные"

    async def menu(self, user_id, prefix=""):
        search = self.store.search(user_id)
        count = len(self.store.recent(search, limit=100))
        saved = len(self.store.favorites(user_id))
        states = [self.source_state(user_id, s) for s in search.sources]
        checked = sum(s in {"есть данные", "часть выдачи"} for s in states)
        text = prefix + summary(search)
        text += f"\nСайты с актуальными данными: {checked} из {len(search.sources)}."
        if count:
            text += f"\nПод ваш фильтр: {count}{'+' if count == 100 else ''}. Откройте объявления ниже."
        elif not search.sources:
            text += "\nВключите хотя бы один сайт в настройках."
        elif search.paused:
            text += "\nПродолжите поиск, когда снова захотите получать новые варианты."
        elif not checked:
            text += (
                "\nЖду первые данные. В «Состоянии сайтов» видно, что уже проверено."
            )
        else:
            text += (
                "\nСовпадений пока нет. Как только замечу подходящий вариант — напишу."
            )
        await self.show(user_id, text, main_keyboard(search, count, saved))

    async def settings(self, user_id, prefix=""):
        text, keyboard = settings_screen(self.store.search(user_id))
        await self.show(user_id, prefix + text, keyboard)

    async def prompt(self, user_id, field, error=""):
        if field not in PROMPTS:
            return
        self.store.set_user(user_id, pending=field)
        search = self.store.search(user_id)
        title, hint = PROMPTS[field]
        current = {
            "price": f"до {money(search.max_price)} CHF/мес.",
            "rooms": f"{search.min_rooms:g}–{search.max_rooms:g}",
            "cities": ", ".join(search.cities),
            "area": f"от {search.min_area} м²" if search.min_area else "любая",
            "interval": f"{search.interval // 60} мин.",
            "exclude": search.exclude or "ничего не исключено",
        }[field]
        presets = {
            "price": [
                [("1 350 CHF", "1350"), ("1 500 CHF", "1500"), ("1 800 CHF", "1800")]
            ],
            "rooms": [[("1–2.5", "1 2.5"), ("1.5–2.5", "1.5 2.5"), ("2–3.5", "2 3.5")]],
            "cities": [
                [
                    ("Wetzikon ZH", "Wetzikon ZH"),
                    ("Uster", "Uster"),
                    ("Hinwil", "Hinwil"),
                ],
                [("Wetzikon + Uster", "Wetzikon ZH, Uster")],
            ],
            "area": [[("Любая", "0"), ("От 30 м²", "30"), ("От 50 м²", "50")]],
            "interval": [
                [("2 мин.", "2"), ("3 мин.", "3"), ("5 мин.", "5"), ("10 мин.", "10")]
            ],
            "exclude": [
                [("Без временной аренды", "befristet, temporär"), ("Очистить", "0")]
            ],
        }
        rows = [
            [(label, "set:" + field + ":" + value) for label, value in row]
            for row in presets[field]
        ]
        if field == "price":
            rows.insert(
                0,
                [
                    ("−100 CHF", f"set:price:{max(100, search.max_price - 100)}"),
                    ("+100 CHF", f"set:price:{min(50000, search.max_price + 100)}"),
                ],
            )
        rows.append([("Отмена · к настройкам", "settings")])
        text = "<b>" + title + "</b>\nСейчас: " + escape(current) + "\n\n" + hint
        if field == "cities" and search.urls:
            text += (
                "\n\nПри смене городов ваши собственные ссылки поиска будут сброшены."
            )
        if error:
            text = "Не удалось сохранить: " + escape(error) + "\n\n" + text
        await self.show(user_id, text, buttons(rows))

    async def sources(self, user_id):
        search = self.store.search(user_id)
        rows = [
            [
                (
                    ("✓ " if s in search.sources else "○ ")
                    + name
                    + " · "
                    + self.source_state(user_id, s),
                    "toggle:" + s,
                )
            ]
            for s, name in SOURCES.items()
        ]
        rows += [
            [("Включить все", "sources:all"), ("Выключить все", "sources:none")],
            [("К настройкам", "settings"), ("На главную", "home")],
        ]
        await self.show(
            user_id,
            "<b>Где искать</b>\n\n✓ — включён в ваш поиск. Нажмите на сайт, чтобы изменить.\nБлокировки сайтов не означают, что объявлений нет. Подробности — в «Состоянии сайтов».",
            buttons(rows),
        )

    async def status(self, user_id, source=None):
        search = self.store.search(user_id)
        if source not in SOURCES:
            rows = [
                [(name + " · " + self.source_state(user_id, s), "source:" + s)]
                for s, name in SOURCES.items()
            ]
            rows += [[("Обновить статус", "status"), ("На главную", "home")]]
            await self.show(
                user_id,
                "<b>Состояние сайтов</b>\n\nВыберите сайт для подробностей.\n«Часть выдачи» — проверены не все объявления. «Недоступен» — сайт отклонил запрос или данные не удалось прочитать.\n\nОбновление этого экрана не отправляет дополнительные запросы на сайты.",
                buttons(rows),
            )
            return
        text = (
            "<b>"
            + SOURCES[source]
            + "</b> · "
            + self.source_state(user_id, source)
            + "\n"
        )
        rows = self.query_rows(user_id, source)
        if not rows:
            text += "\nПервая проверка ещё не завершена."
        for row in rows:
            text += "\n<b>" + escape(row["city"]) + "</b>\n"
            if row["error"]:
                text += escape(row["error"]) + "\n"
                minutes = max(1, math.ceil((row["next_run"] - time.time()) / 60))
                text += (
                    f"Повтор — не раньше чем через {minutes} мин.\n"
                    if row["next_run"] > time.time()
                    else "Повтор в очереди.\n"
                )
            text += "Успешная проверка: " + when(row["success"]) + "\n"
            if row["success"]:
                text += f"Объявлений до ваших фильтров: {row['count']}.\n"
            if row["partial"]:
                text += "Охват ограничен: показана часть выдачи.\n"
        text += "\nВремя — Цюрих. Доступность может меняться; проверка не гарантирует, что объявление ещё активно."
        keyboard = buttons(
            [
                [("Обновить", "source:" + source)],
                [("Все сайты", "status"), ("На главную", "home")],
            ]
        )
        keyboard["inline_keyboard"].insert(
            0,
            [
                {
                    "text": "Открыть поиск на сайте ↗",
                    "url": search.urls.get(source)
                    or search_url(source, search.cities[0]),
                }
            ],
        )
        await self.show(user_id, text, keyboard)

    async def current(self, user_id, mode="current", order=None, index=0):
        order = order or self.store.get("sort:" + str(user_id), "price")
        matches = (
            self.store.favorites(user_id)
            if mode == "favorites"
            else self.store.recent(self.store.search(user_id), limit=100)
        )
        matches.sort(
            key=(
                lambda pair: (
                    pair[0].price if pair[0].price is not None else float("inf"),
                    -pair[1],
                )
            )
            if order == "price"
            else (lambda pair: -pair[1])
        )
        snapshot = {
            "token": secrets.token_hex(4),
            "mode": mode,
            "order": order,
            "items": [
                {"key": item.key[:24], "checked": checked}
                for item, checked in matches[:100]
            ],
        }
        self.store.put("browser:" + str(user_id), snapshot)
        await self.browse(
            user_id, snapshot["token"], min(index, max(0, len(snapshot["items"]) - 1))
        )

    async def browse(self, user_id, token, index, notice=""):
        snapshot = self.store.get("browser:" + str(user_id))
        if not snapshot or snapshot["token"] != token:
            await self.show(
                user_id,
                "Этот список уже обновился. Откройте свежую подборку.",
                buttons(
                    [
                        [("Объявления", "current"), ("Избранное", "favorites")],
                        [("На главную", "home")],
                    ]
                ),
            )
            return
        items, mode = snapshot["items"], snapshot["mode"]
        if not items:
            text = (
                "<b>В избранном пока пусто</b>\n\nСохраните понравившийся вариант кнопкой под объявлением. Он останется здесь после перезапуска и изменения фильтров."
                if mode == "favorites"
                else "<b>Подходящих вариантов пока нет</b>\n\nИщу в выбранных городах по вашему бюджету и комнатам. Можно изменить фильтры или проверить состояние сайтов."
            )
            if mode == "current" and self.store.search(user_id).paused:
                text += "\n\nВаш поиск сейчас на паузе."
            await self.show(
                user_id,
                text,
                buttons(
                    [
                        [
                            ("Настроить поиск", "settings"),
                            ("Состояние сайтов", "status"),
                        ],
                        [("Обновить список", mode), ("На главную", "home")],
                    ]
                ),
            )
            return
        if not 0 <= index < len(items):
            return
        item = self.store.find_listing(items[index]["key"], user_id)
        if item is None or (
            mode == "current" and not self.store.search(user_id).matches(item[0])
        ):
            await self.current(user_id, mode)
            return
        listing, checked = item
        saved = self.store.is_favorite(user_id, listing.key)
        keyboard = listing_keyboard(listing, saved)
        keyboard["inline_keyboard"][1][0]["callback_data"] += f":{token}:{index}"
        navigation = []
        if index:
            navigation.append(("← Предыдущее", f"browse:{token}:{index - 1}"))
        if index + 1 < len(items):
            navigation.append(("Следующее →", f"browse:{token}:{index + 1}"))
        if navigation:
            keyboard["inline_keyboard"].insert(
                2, buttons([navigation])["inline_keyboard"][0]
            )
        sort_label = (
            "По времени проверки" if snapshot["order"] == "price" else "Сначала дешевле"
        )
        keyboard["inline_keyboard"].insert(
            -1,
            buttons(
                [
                    [
                        (
                            sort_label,
                            "sort:"
                            + mode
                            + ":"
                            + ("recent" if snapshot["order"] == "price" else "price"),
                        ),
                        ("Обновить", mode),
                    ]
                ]
            )["inline_keyboard"][0],
        )
        title = "Избранное" if mode == "favorites" else "Объявления"
        text = (
            notice
            + f"<b>{title} · {index + 1} из {len(items)}{'+' if len(items) == 100 else ''}</b>\n\n"
            + listing_text(listing, detected=checked, current=True)
        )
        if mode == "favorites":
            text += "\n\nСохранённый вариант. Он может больше не подходить под фильтры или быть снят с публикации."
        else:
            text += (
                "\n\nИз проверок за последние сутки. Актуальность уточняйте на сайте."
            )
        await self.show(user_id, text, keyboard)

    async def favorite_action(self, user_id, action):
        parts = action.split(":")
        if len(parts) not in {3, 5} or parts[1] not in {"add", "remove"}:
            return
        item = self.store.find_listing(parts[2], user_id)
        if not item:
            await self.show(
                user_id,
                "Эта карточка больше не хранится. Откройте свежую подборку.",
                buttons([[("Объявления", "current"), ("На главную", "home")]]),
            )
            return
        listing, checked = item
        if len(parts) == 5:
            snapshot = self.store.get("browser:" + str(user_id))
            if not snapshot or snapshot["token"] != parts[3] or not parts[4].isdigit():
                return await self.browse(user_id, "expired", 0)
            index = int(parts[4])
            if (
                not 0 <= index < len(snapshot["items"])
                or snapshot["items"][index]["key"] != parts[2]
            ):
                return
        if parts[1] == "add":
            self.store.save_favorite(user_id, listing, checked)
        else:
            self.store.remove_favorite(user_id, listing.key)
        if len(parts) == 5:
            if snapshot["mode"] == "favorites" and parts[1] == "remove":
                return await self.current(user_id, "favorites", index=index)
            return await self.browse(
                user_id,
                parts[3],
                index,
                "Сохранено в избранное.\n\n"
                if parts[1] == "add"
                else "Убрано из избранного.\n\n",
            )
        await self.show(
            user_id,
            (
                "Сохранено в избранное.\n\n"
                if parts[1] == "add"
                else "Убрано из избранного.\n\n"
            )
            + listing_text(listing, detected=checked, current=True),
            listing_keyboard(listing, self.store.is_favorite(user_id, listing.key)),
        )
