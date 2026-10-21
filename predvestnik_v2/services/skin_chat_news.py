"""Chat news about skins: a purchase or a raise to SSS goes to every main chat where the player wrote within 30 days.

Main chat is the same as the broadcast segment «основные чаты»: the bot is in it and it is not linked as someone's admin
chat. The queue is written by the purchase transaction (services.skins_chat.news); this loop only reads it.
A run of purchases is one message: a player's news wait until QUIET_SEC passed since the latest one. News older than
STALE_SEC (the bot was down) are dropped: an old purchase is not news. Each (news, chat) is claimed before sending.
"""
from __future__ import annotations

import asyncio
import os
from html import escape

from loguru import logger

from core.skins_v3_catalog import SKINS
from core import skins_v3_chat_layout as layout
from core.skins_v3_chat import chat_look, glyph_of, title_of
from infrastructure.repositories import skin_chat_v1 as repo

ACTIVE_DAYS = 30
QUIET_SEC = 90
STALE_SEC = 24 * 3600
INTERVAL_SEC = 30
PAUSE_SEC = 0.4         # between chats: a player may be in a dozen of them
USERS_PER_TICK = 20


def _who(user_id: int, username: str | None) -> str:
    """The same name link as bot.chat.style.profile_link: t.me/<nick> opens the profile and pings nobody."""
    if username:
        shown = escape(layout.cut(f"@{username}", layout.LINE_EM - 4))   # длинный ник не рвётся посередине; ссылка ведёт на полный
        return f'<a href="https://t.me/{escape(username, quote=True)}">{shown}</a>'
    return f'<a href="tg://user?id={int(user_id)}">id{int(user_id)}</a>'


def _look(skin_id: str, kind: str):
    """Новость всегда в полном оформлении скина: покупка — как тир B, SSS — как SSS."""
    return chat_look(skin_id, "SSS" if kind == "sss" else "B")


def _one(user_id: int, username: str | None, item: dict) -> str:
    sid, kind = item["skin_id"], item["kind"]
    skin, look = SKINS[sid], _look(sid, kind)
    who = f"{look.glyph} {_who(user_id, username)}"
    if kind == "sss":
        rows = [layout.row(look) + who, *layout.wrap(look, f"<b>{escape(skin['name'])}</b> теперь <b>SSS</b>", nested=True)]
        return layout.message(look, [layout.section(look, "👑", "SSS", rows)])
    rows = [layout.row(look) + who, layout.sub(look) + "новый образ", *layout.wrap(look, f"<b>{escape(skin['name'])}</b>"),
            *layout.wrap(look, f"<i>{escape(title_of(sid))}</i> · редкость {skin['tier']}", nested=True)]
    return layout.section(look, "✨", "Образ", rows)


def text(user_id: int, username: str | None, items: list[dict]) -> str:
    """One message for all of a player's news in this chat."""
    if len(items) == 1:
        return _one(user_id, username, items[0])
    look = _look(items[-1]["skin_id"], items[-1]["kind"])
    rows = [layout.row(look) + f"✨ {_who(user_id, username)}", layout.sub(look) + "пополняет коллекцию"]
    for i in items:
        rows += layout.wrap(look, f"{glyph_of(i['skin_id'])} <b>{escape(SKINS[i['skin_id']]['name'])}</b> · {'SSS' if i['kind'] == 'sss' else 'новый'}")
    return layout.section(look, "🎨", "Коллекция", rows)


def markup():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    bot_name = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎨 Образы", url=f"https://t.me/{bot_name}?startapp=looks")]])


async def _send(bot, chat_id: int, body: str) -> tuple[str, str | None]:
    from aiogram.exceptions import TelegramRetryAfter
    from services.broadcasts import reason_of
    for attempt in range(2):
        try:
            await bot.send_message(chat_id, body, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup())
            return "sent", None
        except TelegramRetryAfter as exc:
            if attempt:
                return "failed", "other: Telegram просит подождать"
            await asyncio.sleep(min(float(exc.retry_after), 60) + 1)
        except Exception as exc:   # бота выгнали, нет права писать и т.п.
            return "failed", reason_of(exc)
    return "failed", "other"


async def _prepare(db, user_id: int) -> tuple[list[dict], list[int], str | None]:
    """Fresh news, target chats and the username; stale news are closed here without sending."""
    items = await repo.pending(db, user_id)
    stale = [i["id"] for i in items if i["age"] > STALE_SEC or i["skin_id"] not in SKINS]
    await repo.finish(db, stale)
    fresh = [i for i in items if i["id"] not in stale]
    if not fresh or not await repo.cosmetics_enabled(db, 0):   # chat 0: only the global switch
        await repo.finish(db, [i["id"] for i in fresh])
        return [], [], None
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (int(user_id),)) as cur:
        row = await cur.fetchone()
    return fresh, await repo.main_active_chats(db, user_id, ACTIVE_DAYS), (row[0] if row else None)


async def deliver_user(bot, pool_db, user_id: int) -> int:
    """Send one player's pending news to their chats. Returns how many messages went out."""
    async with pool_db() as db:
        items, chats, username = await _prepare(db, user_id)
    by_id = {i["id"]: i for i in items}
    sent = 0
    for chat_id in chats:
        async with pool_db() as db:
            claimed = await repo.claim(db, list(by_id), chat_id)
        if not claimed:
            continue
        status, error = await _send(bot, chat_id, text(user_id, username, [by_id[i] for i in sorted(claimed)]))
        sent += status == "sent"
        async with pool_db() as db:
            await repo.mark(db, claimed, chat_id, status, error)
        await asyncio.sleep(PAUSE_SEC)
    if by_id:
        async with pool_db() as db:
            await repo.finish(db, list(by_id))
    return sent


async def tick(bot, pool_db) -> int:
    async with pool_db() as db:
        users = await repo.ready_users(db, QUIET_SEC, USERS_PER_TICK)
    total = 0
    for user_id in users:
        total += await deliver_user(bot, pool_db, user_id)
    return total


async def task(bot, pool_db) -> None:
    """Background loop (bot/__main__.py). It never ends by itself: one bad round is logged and the next one runs."""
    while True:
        try:
            await tick(bot, pool_db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(f"skin chat news: {exc}")
        await asyncio.sleep(INTERVAL_SEC)
