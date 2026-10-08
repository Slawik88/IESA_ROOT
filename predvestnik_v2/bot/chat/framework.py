"""Каркас команд чата: «бот [команда], значения».

Примеры: «бот бан, @ник 5д», «бот топ», «обнять» (команды без приставки).
Команда — одно или несколько слов; значения идут после запятой или пробела.
Опечатки и неверная раскладка получают подсказку.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.types import Message

from bot.chat.access import is_developer

_PREFIX_RE = re.compile(r"^\s*(?:бот|bot)(?![\w])[\s,:;.!-]*", re.IGNORECASE)
_TOKEN_RE = re.compile(r"\S+")

_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбю.ё"
_LAYOUT = {ord(e): r for e, r in zip(_EN, _RU)}


def norm(word: str) -> str:
    return word.strip().strip(",;:!?.").lower().replace("ё", "е")


def fix_layout(word: str) -> str:
    """«ngg» -> «топ»: слово набрано в английской раскладке."""
    return word.lower().translate(_LAYOUT)


class UsageError(Exception):
    """Команда вызвана с неверными значениями; текст — подсказка формата."""


@dataclass(frozen=True)
class Command:
    name: str
    handler: Callable[["Ctx"], Awaitable[None]]
    usage: str = ""
    aliases: tuple[str, ...] = ()
    bare: bool = False            # работает и без слова «бот»
    private: bool = True          # доступна в личке с ботом

    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass
class Ctx:
    message: Message
    bot: Bot
    db: object
    command: Command
    args: str
    prefixed: bool

    @property
    def user_id(self) -> int:
        return self.message.from_user.id

    @property
    def is_dev(self) -> bool:
        return is_developer(self.user_id)

    async def reply(self, text: str, **kw):
        kw.setdefault("parse_mode", "HTML")
        kw.setdefault("disable_web_page_preview", True)
        return await self.message.reply(text, **kw)


class Registry:
    def __init__(self) -> None:
        self._by_name: dict[str, Command] = {}

    def register(self, cmd: Command) -> Command:
        for n in cmd.all_names():
            key = " ".join(norm(w) for w in n.split())
            self._by_name[key] = cmd
        return cmd

    def command(self, name: str, **kw):
        def deco(fn):
            self.register(Command(name=name, handler=fn, **kw))
            return fn
        return deco

    @property
    def names(self) -> list[str]:
        return sorted(self._by_name)

    def get(self, key: str) -> Command | None:
        return self._by_name.get(key)

    def max_words(self) -> int:
        return max((k.count(" ") + 1 for k in self._by_name), default=1)


@dataclass(frozen=True)
class Parsed:
    command: Command
    args: str
    prefixed: bool


@dataclass(frozen=True)
class Unknown:
    typed: str
    suggestions: tuple[str, ...]


def _split_prefix(text: str, bot_username: str | None) -> tuple[bool, str]:
    m = _PREFIX_RE.match(text)
    if m:
        return True, text[m.end():]
    if bot_username:
        m2 = re.match(rf"^\s*@{re.escape(bot_username)}\b[\s,:;.!-]*", text, re.IGNORECASE)
        if m2:
            return True, text[m2.end():]
    return False, text


def _consume(rest: str, n: int) -> str:
    """Отрезать n первых слов и разделители после них."""
    pos = 0
    for _ in range(n):
        m = re.match(r"\s*\S+", rest[pos:])
        if not m:
            break
        pos += m.end()
    return re.sub(r"^[\s,;:]+", "", rest[pos:])


def suggest(registry: Registry, typed: str, limit: int = 3) -> tuple[str, ...]:
    """Ближайшие команды к набранному (опечатки, раскладка, лишние буквы)."""
    names = registry.names
    typed_n = " ".join(norm(w) for w in typed.split())
    out: list[str] = []
    candidates = {typed_n, fix_layout(typed_n)}
    for cand in candidates:
        if cand in names and cand not in out:
            out.append(cand)
        for m in difflib.get_close_matches(cand, names, n=limit, cutoff=0.6):
            if m not in out:
                out.append(m)
        # префикс: «блэклист» ~ «блэк»
        for n in names:
            if len(cand) >= 3 and (n.startswith(cand) or cand.startswith(n)) and n not in out:
                out.append(n)
    return tuple(out[:limit])


def parse(registry: Registry, text: str, bot_username: str | None = None) -> Parsed | Unknown | None:
    """None — это не команда; Unknown — «бот ...», но команда не найдена."""
    if not text:
        return None
    prefixed, rest = _split_prefix(text, bot_username)
    rest = rest.strip()
    if not rest:
        return None
    tokens = [norm(t) for t in _TOKEN_RE.findall(rest)]
    for n in range(min(registry.max_words(), len(tokens)), 0, -1):
        key = " ".join(tokens[:n])
        cmd = registry.get(key)
        if cmd is None:
            fixed = " ".join(fix_layout(t) for t in tokens[:n])
            cmd = registry.get(fixed) if prefixed else None
        if cmd is None:
            continue
        if not prefixed and not cmd.bare:
            continue
        return Parsed(cmd, _consume(rest, n), prefixed)
    if not prefixed:
        return None
    typed = " ".join(tokens[:2]) if len(tokens) > 1 else tokens[0]
    sugg = suggest(registry, tokens[0])
    if len(tokens) > 1:
        for s in suggest(registry, " ".join(tokens[:2])):
            if s not in sugg:
                sugg = (s, *sugg)
    return Unknown(tokens[0], sugg[:3])


async def dispatch(registry: Registry, message: Message, bot: Bot, db) -> bool:
    """Выполнить команду из сообщения. True — сообщение обработано как команда."""
    text = message.text or message.caption or ""
    if not text or not message.from_user:
        return False
    me = await bot.me()
    parsed = parse(registry, text, me.username)
    if parsed is None:
        return False
    if isinstance(parsed, Unknown):
        if parsed.suggestions:
            hint = "\n".join(f"• <code>бот {s}</code>" for s in parsed.suggestions)
            await message.reply(
                f"🤔 Не знаю команду «{_esc(parsed.typed)}». Возможно, вы имели в виду:\n{hint}",
                parse_mode="HTML",
            )
        else:
            await message.reply(
                f"🤔 Не знаю команду «{_esc(parsed.typed)}». Список команд: <code>бот помощь</code>",
                parse_mode="HTML",
            )
        return True
    cmd = parsed.command
    if message.chat.type == "private" and not cmd.private:
        await message.reply("Эта команда работает только в группе.")
        return True
    ctx = Ctx(message, bot, db, cmd, parsed.args, parsed.prefixed)
    try:
        await cmd.handler(ctx)
    except UsageError as e:
        usage = str(e) or cmd.usage
        await message.reply(f"✏️ Формат команды:\n<code>{_esc(usage)}</code>", parse_mode="HTML")
    return True


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


registry = Registry()
