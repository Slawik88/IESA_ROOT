"""Small Telegram screens with predictable navigation and explicit state."""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .models import SOURCES

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
        datetime.fromtimestamp(timestamp, TZ).strftime("%d.%m · %H:%M")
        if timestamp
        else "ещё не было"
    )


def money(value):
    if value is None:
        return "не указана"
    return f"{value:,.0f}".replace(",", " ")


def room_range(search):
    return f"{search.min_rooms:g}–{search.max_rooms:g}"


def summary(search):
    extras = []
    if search.min_area:
        extras.append(f"от {search.min_area} м²")
    if search.exclude:
        extras.append("Без: " + escape(search.exclude))
    state = (
        "На паузе"
        if search.paused
        else ("Все сайты выключены" if not search.sources else "Поиск включён")
    )
    return (
        "<b>Ваш дом — где-то рядом</b>\n"
        + state
        + "\n\n"
        + escape(", ".join(search.cities))
        + "\n"
        + f"<b>До {money(search.max_price)} CHF/мес.</b> · {room_range(search)} комн.\n"
        + (" · ".join(extras) + "\n" if extras else "")
        + f"Проверки примерно раз в {search.interval // 60} мин.\n"
    )


def main_keyboard(search, count=0, favorites=0):
    return buttons(
        [
            [(f"Объявления · {count}", "current")],
            [
                ("Настроить поиск", "settings"),
                (f"Избранное · {favorites}", "favorites"),
            ],
            [("Состояние сайтов", "status")],
            [
                (
                    "Продолжить поиск" if search.paused else "Приостановить",
                    "resume" if search.paused else "pause",
                ),
                ("Помощь", "help"),
            ],
        ]
    )


def settings_screen(search):
    text = (
        "<b>Настроим ваш поиск</b>\n\n"
        + escape(", ".join(search.cities))
        + f"\nДо {money(search.max_price)} CHF · {room_range(search)} комн.\n\n"
        + "Выберите, что изменить. Все изменения сохраняются сразу и относятся только к вам."
    )
    rows = [
        [(f"Бюджет · {money(search.max_price)} CHF", "edit:price")],
        [
            (f"Комнаты · {room_range(search)}", "edit:rooms"),
            (
                f"Площадь · {'от ' + str(search.min_area) + ' м²' if search.min_area else 'любая'}",
                "edit:area",
            ),
        ],
        [("Города", "edit:cities"), (f"Сайты · {len(search.sources)} из 7", "sources")],
        [
            (f"Частота · {search.interval // 60} мин.", "edit:interval"),
            ("Исключения", "edit:exclude"),
        ],
        [("К объявлениям", "current"), ("На главную", "home")],
    ]
    return text, buttons(rows)


def listing_text(listing, *, detected=None, current=False):
    details = (
        f"{listing.rooms:g} комн."
        if listing.rooms is not None
        else "Комнаты не указаны"
    )
    details += (
        f" · {listing.area:g} м²"
        if listing.area is not None
        else " · площадь не указана"
    )
    price = (
        f"{money(listing.price)} CHF/мес."
        if listing.price is not None
        else "Цена по запросу"
    )
    text = (
        "<b>"
        + ("Подходит под ваш поиск" if current else "Новое совпадение")
        + "</b>\n\n"
        + f"<b>{price}</b> · {details}\n"
        + escape(listing.address or listing.city)
        + "\n\n"
        + escape(listing.title[:240])
        + "\n"
        + escape(listing.price_note)
        + "\n\n"
        + SOURCES[listing.source]
    )
    if detected:
        text += " · проверено " + when(detected) + " (Цюрих)"
    return text


def listing_keyboard(listing, saved=False):
    keyboard = buttons(
        [
            [
                (
                    "Убрать из избранного" if saved else "В избранное",
                    f"fav:{'remove' if saved else 'add'}:{listing.key[:24]}",
                )
            ],
            [("Все объявления", "current"), ("На главную", "home")],
        ]
    )
    keyboard["inline_keyboard"].insert(
        0, [{"text": "Открыть объявление ↗", "url": listing.url}]
    )
    return keyboard
