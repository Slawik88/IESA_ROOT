"""Validated typed preference changes shared by commands and buttons."""

import re
from dataclasses import replace


def updated_search(search, field, text):
    candidate = replace(search)
    if field == "price":
        match = re.fullmatch(
            r"\s*(?:CHF\s*)?(\d+(?:[ '’.]\d{3})*)(?:\s*(?:CHF|fr\.?))?\s*",
            text,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError("Введите бюджет числом, например 1500 или 1 500 CHF.")
        candidate.max_price = int(re.sub(r"[ '’.]", "", match[1]))
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
