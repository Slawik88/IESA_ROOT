"""Кого касается команда: ответ на сообщение, упоминание или @ник в значениях."""
from __future__ import annotations

import re
from dataclasses import dataclass

from aiogram.types import Message

_USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})\b")
_ID_RE = re.compile(r"(?<!\w)(?:id)?(\d{5,15})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Target:
    user_id: int
    username: str | None
    name: str

    def label(self) -> str:
        """Имя без пинга: «@» + нулевой пробел."""
        return f"@​{self.username}" if self.username else self.name


def _strip(args: str, span: tuple[int, int]) -> str:
    return re.sub(r"^[\s,;:]+|[\s,;:]+$", "", (args[:span[0]] + " " + args[span[1]:])).strip()


async def resolve_target(db, message: Message, args: str, *, allow_id: bool = False) -> tuple[Target | None, str]:
    """Вернуть (цель, оставшиеся значения). Цель None — не найдена."""
    m = _USERNAME_RE.search(args)
    if m:
        async with db.execute(
            "SELECT user_tg_id, user_tg_username FROM users WHERE LOWER(user_tg_username) = LOWER(?) LIMIT 1",
            (m.group(1),),
        ) as cur:
            row = await cur.fetchone()
        rest = _strip(args, m.span())
        if row:
            return Target(int(row[0]), row[1], row[1]), rest
        return None, rest
    for ent in message.entities or []:
        if ent.type == "text_mention" and ent.user:
            u = ent.user
            text = message.text or ""
            mention = text[ent.offset: ent.offset + ent.length]
            return Target(u.id, u.username, u.full_name), args.replace(mention, "", 1).strip(" ,")
    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        u = reply.from_user
        return Target(u.id, u.username, u.full_name), args
    if allow_id:
        m = _ID_RE.search(args)
        if m:
            uid = int(m.group(1))
            async with db.execute(
                "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (uid,)
            ) as cur:
                row = await cur.fetchone()
            uname = row[0] if row else None
            return Target(uid, uname, uname or f"id{uid}"), _strip(args, m.span())
    return None, args
