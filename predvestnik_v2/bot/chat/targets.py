"""Кого касается команда: ответ на сообщение, упоминание или @ник в значениях."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from aiogram.types import Message

from services import member_tags

_USERNAME_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})\b")
_ID_RE = re.compile(r"(?<!\w)(?:id)?(\d{5,15})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Target:
    user_id: int
    username: str | None
    name: str
    tag: str | None = None   # тег в чате, где пришла команда (подпись справа от имени в Telegram)

    def label(self) -> str:
        """Имя без пинга («@» + нулевой пробел) и тег в этом чате: «@ник [Сяо]»."""
        return member_tags.with_tag(f"@​{self.username}" if self.username else self.name, self.tag)

    @property
    def plain_name(self) -> str:
        """Имя без тега: для пинга ссылкой и текста, который копируют в команду."""
        return f"@​{self.username}" if self.username else self.name


NOT_FOUND = "🤔 Не нашёл такого игрока. Он должен хотя бы раз написать в чат с ботом."
TELEGRAM_SERVICE_ID = 777000   # сюда Telegram подписывает пересланные из канала посты


def names_someone(args: str) -> bool:
    """В значениях есть @ник: если цель не нашлась, это ошибка, а не «покажи мне самого себя»."""
    return bool(_USERNAME_RE.search(args))


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Telegram считает смещения упоминаний в UTF-16: эмодзи в имени занимает два места, а не одно."""
    data = text.encode("utf-16-le")
    return data[offset * 2:(offset + length) * 2].decode("utf-16-le", "ignore")


def _replied_user(message: Message):
    """Автор сообщения, на которое ответили. В темах форума «ответом» Telegram считает служебное сообщение
    о создании темы, а у пересланных из канала постов автор — служебный аккаунт Telegram: ни то, ни другое — не цель."""
    reply = message.reply_to_message
    if not reply or not reply.from_user or reply.from_user.is_bot:
        return None
    if getattr(reply, "forum_topic_created", None) or getattr(reply, "is_automatic_forward", False):
        return None
    if reply.from_user.id == TELEGRAM_SERVICE_ID:
        return None
    return reply.from_user


def _strip(args: str, span: tuple[int, int]) -> str:
    return re.sub(r"^[\s,;:]+|[\s,;:]+$", "", (args[:span[0]] + " " + args[span[1]:])).strip()


async def _tagged(db, message: Message, target: Target, source: Message | None = None) -> Target:
    """Цель с тегом в этом чате. Если цель взята из ответа на сообщение, берём тег из самого сообщения: он свежее базы."""
    if message.chat.type not in ("group", "supergroup"):
        return target
    tag = None
    if source is not None:
        known, tag = member_tags.of_message(source)
        if not known:
            tag = await member_tags.get(db, message.chat.id, target.user_id)
    else:
        tag = await member_tags.get(db, message.chat.id, target.user_id)
    return replace(target, tag=tag) if tag else target


async def resolve_target(db, message: Message, args: str, *, allow_id: bool = False) -> tuple[Target | None, str]:
    """Вернуть (цель, оставшиеся значения). Цель None — не найдена. У цели уже есть тег в этом чате."""
    target, rest, source = await _resolve(db, message, args, allow_id=allow_id)
    return (await _tagged(db, message, target, source) if target else None), rest


async def _resolve(db, message: Message, args: str, *, allow_id: bool = False) -> tuple[Target | None, str, Message | None]:
    m = _USERNAME_RE.search(args)
    if m:
        # Ник в Telegram один на весь мир, но у людей, сменивших его, в базе мог остаться старый: берём того,
        # кто писал последним.
        async with db.execute(
            "SELECT u.user_tg_id, u.user_tg_username FROM users u WHERE LOWER(u.user_tg_username) = LOWER(?) "
            "ORDER BY (SELECT MAX(s.last_message_at) FROM user_chat_stats s WHERE s.user_tg_id = u.user_tg_id) "
            "DESC NULLS LAST, u.user_tg_id LIMIT 1",
            (m.group(1),),
        ) as cur:
            row = await cur.fetchone()
        rest = _strip(args, m.span())
        if row:
            return Target(int(row[0]), row[1], row[1]), rest, None
        return None, rest, None
    for ent in message.entities or []:
        if ent.type == "text_mention" and ent.user:
            u = ent.user
            mention = _utf16_slice(message.text or message.caption or "", ent.offset, ent.length)
            return Target(u.id, u.username, u.full_name), args.replace(mention, "", 1).strip(" ,"), None
    u = _replied_user(message)
    if u:
        return Target(u.id, u.username, u.full_name), args, message.reply_to_message
    if allow_id:
        m = _ID_RE.search(args)
        if m:
            uid = int(m.group(1))
            async with db.execute(
                "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (uid,)
            ) as cur:
                row = await cur.fetchone()
            uname = row[0] if row else None
            return Target(uid, uname, uname or f"id{uid}"), _strip(args, m.span()), None
    return None, args, None
