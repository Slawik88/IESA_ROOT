"""Bounded presentation of existing private bot menus; domain actions stay native callbacks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar

MAX_SOURCE_BYTES = 32768
PAGE_BYTES = 570
PAGE_LINES = 9
PAGE_CHARS = 220
LINE_CHARS = 70
KEEP_DAYS = 7
MAX_USER_CARDS = 40
PLAIN_CALLBACK = "vw:plain"
CAPTION_FEATURES = frozenset({"pets", "wallet", "transfer", "vip", "dust", "family", "business"})


def caption_fits(source: str, parse_mode: str | None) -> bool:
    return len(text_view(source, parse_mode).text.encode("utf-16-le")) // 2 <= 1024

FEATURES = {
    "home": "Предвестник",
    "plan": "План дня",
    "notify": "Уведомления",
    "quests": "Задания",
    "pass": "Пропуск",
    "pets": "Питомцы",
    "profile": "Профиль",
    "activity": "Активность",
    "achievements": "Достижения",
    "wallet": "Кошелёк",
    "transfer": "Перевод",
    "vip": "VIP",
    "dust": "Звёздная пыль",
    "family": "Семья",
    "top": "Топ",
    "help": "Помощь",
    "business": "Пульт переписки",
    "games": "Игры",
    "chests": "Сундук",
    "digest": "События",
}
COMMANDS = {
    "план": "plan",
    "уведомления": "notify",
    "квесты": "quests",
    "пропуск": "pass",
    "питомцы": "pets",
    "отправить питомца": "pets",
    "покормить питомца": "pets",
    "лагерь": "pets",
    "вылазка": "pets",
    "выслеживание": "pets",
    "испытание питомцев": "pets",
    "бестиарий": "pets",
    "я": "profile",
    "кто": "profile",
    "баланс": "wallet",
    "стрик": "activity",
    "достижения": "achievements",
    "перевод": "transfer",
    "обменять зарники": "transfer",
    "подарок фортуны": "wallet",
    "вип": "vip",
    "vip": "vip",
    "пыль": "dust",
    "вип за пыль": "dust",
    "семья": "family",
    "родословная": "family",
    "топ": "top",
    "помощь": "help",
    "бизнес": "business",
    "игры": "games",
    "ритм": "games",
}


@dataclass(frozen=True)
class TextView:
    text: str
    entities: tuple[dict, ...] = ()


class _TelegramHTML(HTMLParser):
    """Keep Telegram UTF-16 entities consistent when hydrating a real callback Message."""

    TYPES: ClassVar[dict[str, str]] = {
        "b": "bold",
        "strong": "bold",
        "i": "italic",
        "em": "italic",
        "u": "underline",
        "ins": "underline",
        "s": "strikethrough",
        "strike": "strikethrough",
        "del": "strikethrough",
        "code": "code",
        "pre": "pre",
        "blockquote": "blockquote",
        "tg-spoiler": "spoiler",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.utf16_offset = 0
        self.open: list[tuple[str, int, dict]] = []
        self.entities: list[dict] = []

    def handle_data(self, value):
        self.parts.append(value)
        self.utf16_offset += len(value.encode("utf-16-le")) // 2

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "br":
            self.handle_data("\n")
            return
        kind = self.TYPES.get(tag)
        extra = {}
        if tag == "a" and attrs.get("href"):
            kind, extra = "text_link", {"url": attrs["href"]}
        elif tag == "tg-emoji" and attrs.get("emoji-id"):
            kind, extra = "custom_emoji", {"custom_emoji_id": attrs["emoji-id"]}
        elif tag == "span" and attrs.get("class") == "tg-spoiler":
            kind = "spoiler"
        elif tag == "blockquote" and "expandable" in attrs:
            kind = "expandable_blockquote"
        if kind:
            self.open.append((tag, self.utf16_offset, {"type": kind, **extra}))

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            name, start, entity = self.open[index]
            if name == tag:
                self.open.pop(index)
                if self.utf16_offset > start:
                    self.entities.append(
                        {**entity, "offset": start, "length": self.utf16_offset - start}
                    )
                break


def text_view(source: str, parse_mode: str | None = "HTML") -> TextView:
    if parse_mode != "HTML":
        return TextView(source)
    parser = _TelegramHTML()
    parser.feed(source)
    parser.close()
    return TextView(
        "".join(parser.parts),
        tuple(sorted(parser.entities, key=lambda item: item["offset"])),
    )


def pages(text: str) -> list[list[str]]:
    """Split on UTF-8 bytes and line count; no clipped suffixes, including long emoji strings."""
    result: list[list[str]] = []
    page: list[str] = []
    size = 0
    chars = 0
    lines = text.split("\n")
    for index, line in enumerate(lines):
        pieces, chunk, chunk_size = [], "", 0
        for char in line:
            char_size = len(json.dumps(char, ensure_ascii=False).encode("utf-8")) - 2
            if chunk_size + char_size > PAGE_BYTES or len(chunk) >= LINE_CHARS:
                pieces.append(chunk)
                chunk, chunk_size = "", 0
            chunk += char
            chunk_size += char_size
        pieces.append(chunk)
        if index < len(lines) - 1:
            pieces[-1] += "\n"
        for piece in pieces:
            cost = len(json.dumps(piece, ensure_ascii=False).encode("utf-8")) + 1
            if page and (
                size + cost > PAGE_BYTES
                or len(page) >= PAGE_LINES
                or chars + len(piece) > PAGE_CHARS
            ):
                result.append(page)
                page, size, chars = [], 0, 0
            page.append(piece)
            size += cost
            chars += len(piece)
    if page:
        result.append(page)
    return result or [["Пока здесь ничего нет."]]


def snapshot(row: dict, page: int = 0) -> dict:
    text = text_view(row["source"], row["parse_mode"]).text.replace("\t", " ")
    content = pages(text)
    page = max(0, min(page, len(content) - 1))
    return {
        "k": row["token"],
        "t": FEATURES[row["feature"]],
        "l": content[page],
        "p": page,
        "n": len(content),
        "r": int(row["revision"]),
    }
