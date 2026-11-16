"""Validated personal searches and normalized rental listings."""

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit, urlunsplit

SOURCES = {
    "rentumo": "Rentumo",
    "huusbro": "Huusbro",
    "homegate": "Homegate",
    "realadvisor": "RealAdvisor",
    "immoscout24": "ImmoScout24",
    "homematch": "Homematch",
    "flatfox": "Flatfox",
}
HOSTS = {
    key: ("www." if key in {"homegate", "immoscout24"} else "") + key + ".ch"
    for key in SOURCES
}


def normalized(value: str) -> str:
    value = value.casefold().replace("ß", "ss")
    value = unicodedata.normalize("NFKD", value)
    return re.sub(
        r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))
    ).strip()


def city_name(value: str) -> str:
    return re.sub(r"\s+(?:zh|sg|sz|ag|be|lu|tg|ch)$", "", normalized(value))


def slug(value: str) -> str:
    return normalized(value).replace(" ", "-")


def safe_url(value: str, source: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname
        not in {HOSTS[source], source + ".ch", "www." + source + ".ch"}
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
    ):
        raise ValueError("Нужна HTTPS-ссылка на выбранный сайт.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


@dataclass
class Search:
    cities: list[str] = field(default_factory=lambda: ["Wetzikon ZH"])
    max_price: int = 1500
    min_rooms: float = 1.5
    max_rooms: float = 2.5
    min_area: int = 0
    interval: int = 180
    sources: list[str] = field(default_factory=lambda: list(SOURCES))
    paused: bool = False
    exclude: str = ""
    urls: dict[str, str] = field(default_factory=dict)

    def validate(self):
        if not 100 <= self.max_price <= 50000:
            raise ValueError("Бюджет: целое число от 100 до 50000 CHF в месяц.")
        if not 0 <= self.min_rooms <= self.max_rooms <= 20:
            raise ValueError("Комнаты: от 0 до 20, минимум не больше максимума.")
        if not 0 <= self.min_area <= 1000:
            raise ValueError("Минимальная площадь: от 0 до 1000 м².")
        if not 120 <= self.interval <= 3600:
            raise ValueError("Интервал: от 2 до 60 минут.")
        if not 1 <= len(self.cities) <= 5 or any(
            not re.fullmatch(r"[\w\s().'-]{2,60}", c) for c in self.cities
        ):
            raise ValueError("Введите от 1 до 5 городов латиницей через запятую.")
        if any(
            not re.search(r"[a-z]", normalized(c)) or re.search(r"[А-Яа-я]", c)
            for c in self.cities
        ):
            raise ValueError(
                "Названия городов нужны как на сайтах: Wetzikon ZH, Uster, Zürich."
            )
        if any(s not in SOURCES for s in self.sources) or len(set(self.sources)) != len(
            self.sources
        ):
            raise ValueError("Неизвестный или повторяющийся сайт.")
        if len(self.exclude) > 300:
            raise ValueError("Исключения: до 300 символов.")
        for source, url in self.urls.items():
            if source not in SOURCES:
                raise ValueError("Неизвестный сайт.")
            safe_url(url, source)
        return self

    def to_dict(self):
        return asdict(self)

    def matches(self, listing):
        if listing.source not in self.sources or listing.category not in {
            "apartment",
            "house",
        }:
            return False
        # Unknown prices/rooms never silently satisfy restrictive filters.
        if listing.price is None or listing.price > self.max_price:
            return False
        if (
            listing.rooms is None
            or not self.min_rooms <= listing.rooms <= self.max_rooms
        ):
            return False
        if self.min_area and (listing.area is None or listing.area < self.min_area):
            return False
        haystack = city_name(listing.city)
        if not any(city_name(c) == haystack for c in self.cities):
            return False
        text = normalized(listing.title + " " + listing.address)
        return not any(
            normalized(word) in text
            for word in self.exclude.split(",")
            if normalized(word)
        )


@dataclass
class Listing:
    source: str
    url: str
    title: str
    city: str
    address: str = ""
    price: float | None = None
    rooms: float | None = None
    area: float | None = None
    category: str = "apartment"
    price_note: str = "Цена из объявления; проверьте коммунальные расходы"

    @property
    def key(self):
        return hashlib.sha256(self.url.encode()).hexdigest()

    @property
    def duplicate_key(self):
        # Only merge cross-portal records with a full street + house number.
        street = re.split(r",?\s*\b\d{4}\b", self.address)[0]
        if not re.search(r"\d", street) or not re.search(r"[a-zA-ZäöüÄÖÜ]", street):
            return self.key
        value = (
            city_name(self.city),
            normalized(street),
            self.rooms,
            self.area,
            self.price,
        )
        return hashlib.sha256(repr(value).encode()).hexdigest()
