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

# «бот», «bot» и они же в чужой раскладке («ище», «,jn»). После «,jn» запятая — это буква «б».
_PREFIX_RE = re.compile(r"^\s*(?:(?:бот|bot|ище)(?![\w])[\s,:;.!-]*|,jn(?![\w])\s*)", re.IGNORECASE)
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
    section: str = ""             # блок в «бот помощь»; пусто — не показывать
    summary: str = ""             # одна строка: что делает
    example: str = ""             # пример вызова
    group: str = ""               # общий выключатель для набора команд (например, все варпы)
    always_on: bool = False       # выключателями не выключается (вход в админку)

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
        # Проверка выключателей перед командой: None — можно, "" — молча нет, текст — ответить им.
        self.gate: Callable[["Ctx"], Awaitable[str | None]] | None = None
        # Учёт выполненной команды (метрики админки); ошибки учёта команду не ломают.
        self.on_used: Callable[["Ctx"], Awaitable[None]] | None = None

    def register(self, cmd: Command) -> Command:
        for n in cmd.all_names():
            key = " ".join(norm(w) for w in n.split())
            old = self._by_name.get(key)
            if old is not None and old.name != cmd.name:
                raise ValueError(f"команда «{key}» уже занята: {old.name}")
            self._by_name[key] = cmd
        return cmd

    def command(self, name: str, **kw):
        def deco(fn):
            self.register(Command(name=name, handler=fn, **kw))
            return fn
        return deco

    def commands(self) -> list[Command]:
        seen: dict[str, Command] = {}
        for c in self._by_name.values():
            seen.setdefault(c.name, c)
        return list(seen.values())

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


_TRANSLIT = (("sch", "щ"), ("zh", "ж"), ("ch", "ч"), ("sh", "ш"), ("ts", "ц"), ("yu", "ю"), ("ya", "я"),
             ("yo", "е"), ("a", "а"), ("b", "б"), ("v", "в"), ("w", "в"), ("g", "г"), ("d", "д"), ("e", "е"),
             ("z", "з"), ("i", "и"), ("y", "ы"), ("j", "й"), ("k", "к"), ("c", "к"), ("q", "к"), ("l", "л"),
             ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
             ("f", "ф"), ("h", "х"), ("x", "кс"))

# Слова «по смыслу», которых нет среди названий команд: что человек, скорее всего, хотел.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "помоги": ("помощь",), "команды": ("помощь",), "хелп": ("помощь",), "help": ("помощь",), "меню": ("помощь",),
    "умеешь": ("помощь",), "деньги": ("баланс",), "валюта": ("баланс",), "монеты": ("баланс",),
    "мора": ("баланс", "перевод"), "алмазы": ("баланс",), "отправить": ("перевод",), "передать": ("перевод",),
    "скинуть": ("перевод",), "кинуть": ("перевод",), "жениться": ("брак",), "свадьба": ("брак",),
    "пожениться": ("брак",), "рейтинг": ("топ",), "лидеры": ("топ",), "статистика": ("я", "топ"),
    "профиль": ("я",), "ачивки": ("достижения",), "задания": ("квесты",), "ссылка": ("сайт",),
    "приложение": ("сайт",), "апп": ("сайт",), "предупреждение": ("варн",), "заткнуть": ("мут",),
    "выгнать": ("кик",), "забанить": ("бан",), "разбанить": ("снять бан",), "размутить": ("снять мут",),
}


def translit(word: str) -> str:
    """«ban» -> «бан»: русское слово латиницей."""
    out = word.lower()
    for lat, cyr in _TRANSLIT:
        out = out.replace(lat, cyr)
    return out


def _stem(word: str) -> str:
    return word[:5] if len(word) > 5 else word


def suggest(registry: Registry, *typed: str, limit: int = 3) -> tuple[str, ...]:
    """Ближайшие команды к набранному: опечатка, раскладка, латиница, начало слова, смысл.

    Можно передать несколько вариантов (первое слово, первые два) — берётся лучший счёт.
    Возвращает основные названия команд (без дублей через синонимы), лучшие первыми.
    """
    scores: dict[str, float] = {}
    for t in typed:
        for name, score in _scores(registry, t).items():
            scores[name] = max(score, scores.get(name, 0))
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return ()
    floor = max(0.6, ranked[0][1] - 0.2)   # при явном попадании слабые варианты не показываем
    return tuple(name for name, score in ranked if score >= floor)[:limit]


def _scores(registry: Registry, typed: str) -> dict[str, float]:
    typed_n = " ".join(norm(w) for w in typed.split())
    if not typed_n:
        return {}
    variants = {typed_n, fix_layout(typed_n)}
    if re.fullmatch(r"[a-z ]+", typed_n):
        variants.add(translit(typed_n))
    scores: dict[str, float] = {}

    def give(cmd: Command, score: float) -> None:
        if score > scores.get(cmd.name, 0):
            scores[cmd.name] = score

    for key in registry.names:
        cmd = registry.get(key)
        for v in variants:
            if v == key:
                give(cmd, 1.0 if v == typed_n else 0.98)
                continue
            ratio = difflib.SequenceMatcher(None, v, key).ratio()
            first = key.split()[0]
            if " " in key and " " not in v:
                ratio = max(ratio, difflib.SequenceMatcher(None, v, first).ratio() * 0.78)   # только первое слово
            if ratio >= 0.6:
                give(cmd, ratio)
            # начало слова: «дост» -> «достижения», «санкц» -> «санкции»
            if len(v) >= 3 and (key.startswith(v) or v.startswith(key) and len(key) >= 3):
                give(cmd, 0.7 + min(len(v), len(key)) / max(len(v), len(key)) * 0.2)
    # По смыслу: словарь и слова из описаний команд.
    words = typed_n.split()
    for w in words:
        for name in SYNONYMS.get(w, ()):
            cmd = registry.get(name)
            if cmd:
                give(cmd, 0.85)
    stems = {_stem(w) for w in words[:1] if len(w) >= 5}   # дальше обычно значения, а не команда
    if stems:
        for cmd in registry.commands():
            text = f"{cmd.summary} {cmd.name}".lower().replace("ё", "е")
            hits = stems & {_stem(t) for t in re.findall(r"[а-яa-z]+", text) if len(t) >= 4}
            if hits:
                give(cmd, 0.55 + 0.05 * len(hits))
    return scores


def parse(registry: Registry, text: str, bot_username: str | None = None) -> Parsed | Unknown | None:
    """None — это не команда; Unknown — «бот ...», но команда не найдена."""
    if not text:
        return None
    prefixed, rest = _split_prefix(text, bot_username)
    rest = rest.strip()
    if not rest:
        return None
    raw = _TOKEN_RE.findall(rest)
    tokens = [norm(t) for t in raw]
    for n in range(min(registry.max_words(), len(tokens)), 0, -1):
        key = " ".join(tokens[:n])
        cmd = registry.get(key)
        if cmd is None:
            fixed = " ".join(norm(fix_layout(t)) for t in raw[:n])   # «,fkfyc»: запятая — это «б»
            cmd = registry.get(fixed) if prefixed else None
        if cmd is None:
            continue
        if not prefixed and not cmd.bare:
            continue
        return Parsed(cmd, _consume(rest, n), prefixed)
    if not prefixed:
        return None
    typed = " ".join(tokens[:2]) if len(tokens) > 1 else tokens[0]
    sugg = suggest(registry, *([tokens[0], " ".join(tokens[:2])] if len(tokens) > 1 else [tokens[0]]))
    return Unknown(tokens[0], sugg)


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
            def line(name: str) -> str:
                cmd = registry.get(name)
                about = f" — {_esc(cmd.summary)}" if cmd and cmd.summary else ""
                return f"• <code>бот {_esc(name)}</code>{about}"
            hint = "\n".join(line(s) for s in parsed.suggestions)
            await message.reply(
                f"🤔 Не знаю команду «{_esc(parsed.typed)}». Возможно, вы имели в виду:\n<blockquote>{hint}</blockquote>",
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
    if registry.gate is not None and not cmd.always_on:
        blocked = await registry.gate(ctx)
        if blocked is not None:
            if blocked and parsed.prefixed:
                await message.reply(blocked, parse_mode="HTML")
            return True
    if registry.on_used is not None:
        try:
            await registry.on_used(ctx)
        except Exception:
            pass
    try:
        await cmd.handler(ctx)
    except UsageError as e:
        usage = str(e) or cmd.usage
        await message.reply(f"✏️ Формат команды:\n<code>{_esc(usage)}</code>", parse_mode="HTML")
    return True


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


registry = Registry()
