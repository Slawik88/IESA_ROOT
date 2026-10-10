"""Pure parsing of Mafia chat commands: «бот мафия …», «бот, мафия стоп», «/mafia@bot 8».

The legacy ``TextCmd`` filter only understood «бот мафия» or «бот мафия, args» (comma
required), so a natural «бот мафия стоп» was silently ignored.  This parser accepts
both spellings and is shared by the aiogram filter and by the message gate, which
must let control commands through during a protected phase.
"""
from __future__ import annotations

import re
from typing import Final, NamedTuple

# kind -> accepted words (lower case).  Anything else after «мафия» is lobby settings.
_CONTROL: Final = {
    "stop": ("стоп", "stop", "отмена", "отменить", "cancel", "остановить", "завершить"),
    "resume": ("продолжить", "resume", "дальше"),
    "rules": ("правила", "помощь", "help", "rules", "как играть", "обучение", "инструкция"),
    "status": ("статус", "status", "состояние"),
    "ready": ("готов", "ready", "готова"),
}
_WORD_TO_KIND: Final = {word: kind for kind, words in _CONTROL.items() for word in words}
# Control commands that are harmless to show in a quiet phase and must never be eaten.
GATE_BYPASS_KINDS: Final = frozenset({"stop", "resume", "rules", "status"})

_HEAD = re.compile(r"^(?:бот(?:\s+|\s*[,.:]\s*)|/)(?:мафия|mafia)(?:@\w+)?(?=$|[\s,.:!?])", re.IGNORECASE)


class MafiaCommand(NamedTuple):
    kind: str  # create | stop | resume | rules | status | ready
    args: str  # normalised remainder, e.g. "8 доктор открытое"


def parse(text: str | None) -> MafiaCommand | None:
    """Return the command a chat message means, or None when it is not about Mafia."""
    if not text:
        return None
    clean = re.sub(r"\s+", " ", text.strip().lower())
    head = _HEAD.match(clean)
    if not head:
        return None
    rest = clean[head.end():].strip(" ,.:!?")
    rest = re.sub(r"\s*,\s*", " ", rest).strip()
    kind = _WORD_TO_KIND.get(rest)
    if kind:
        return MafiaCommand(kind, "")
    return MafiaCommand("create", rest)


def invite_hint(args_error: str = "") -> str:
    """Examples shown when the settings words after «бот мафия» are not understood."""
    lead = f"{args_error}\n\n" if args_error else ""
    return (
        f"{lead}Просто напиши <code>бот мафия</code> — лобби создастся само, настройки меняются кнопками.\n"
        "Быстрый вариант: <code>бот мафия 8 доктор детектив</code> "
        "(число — места; слова — доп. роли; «открытое» — голосование на виду)."
    )
