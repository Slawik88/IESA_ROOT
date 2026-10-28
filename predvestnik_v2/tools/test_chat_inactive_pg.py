"""Inactivity command on loopback PostgreSQL; real dispatch and callbacks, no Telegram sends.

Run: python tools/test_chat_inactive_pg.py --dsn postgresql://...localhost/...
Fixtures live in a transaction which always rolls back.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

os.environ.setdefault("BOT_TOKEN", "1:offline-test")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot.chat
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import EditMessageText
from bot.chat import help as help_view, inactive
from bot.chat.durations import MAX_DAYS as MODERATION_DAYS, TooLong, split_duration
from bot.chat.framework import Ctx, Parsed, dispatch, parse, registry
from core.chat_inactivity import DAY_SECONDS as DAY, PAGE_SIZE
from infrastructure.pg_adapter import PGAdapter
from infrastructure.lazy_db import lazy_connection, release_current
from services import chat_inactivity, feature_switches


class Message:
    def __init__(self, text, uid, chat, kind="supergroup"):
        self.text, self.caption, self.sender_chat = text, None, None
        self.from_user = SimpleNamespace(id=uid, username="qa", is_bot=False)
        self.chat = SimpleNamespace(id=chat, type=kind)
        self.replies = []
        self.edit_text = AsyncMock()

    async def reply(self, text, **kwargs):
        self.replies.append((text, kwargs))


async def run(dsn: str, output: Path | None) -> None:
    connection = await asyncpg.connect(dsn)
    await connection.execute("SET search_path TO predvestnik,public")
    db = PGAdapter(connection)
    transaction = connection.transaction()
    await transaction.start()
    original_used = registry.on_used
    registry.on_used = None
    base = int(uuid4().int % 100_000_000) + 8_500_000_000
    chat, owner = -base, base
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(id=base+999, username="qa_bot")))

    async def seed(offset, *, age=10, count=1, joined=90, back=None, left=False,
                   is_bot=False, cid=chat, no_dates=False, name="Участник", username=None):
        uid = base + offset
        await db.execute("INSERT INTO users(user_tg_id,user_tg_username,user_tg_name) VALUES (?,?,?) "
                         "ON CONFLICT(user_tg_id) DO NOTHING", (uid, username, name))
        await db.execute(
            "INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,user_messages_count_all_time,is_left,is_bot,"
            "last_message_at,joined_at,membership_since,rejoined_at) VALUES (?,?,?,?,?,"
            "CASE WHEN ? THEN NULL ELSE (NOW()-make_interval(secs => ?::double precision)) AT TIME ZONE 'UTC' END,"
            "CASE WHEN ? THEN NULL ELSE (NOW()-make_interval(secs => ?::double precision)) AT TIME ZONE 'UTC' END,"
            "CASE WHEN ? THEN NULL ELSE NOW()-make_interval(secs => ?::double precision) END,"
            "CASE WHEN ?::double precision IS NULL THEN NULL ELSE NOW()-make_interval(secs => ?::double precision) END)",
            (uid, cid, count, left, is_bot, no_dates, age*DAY, no_dates, joined*DAY,
             no_dates, joined*DAY, back*DAY if back is not None else None, back*DAY if back is not None else None))
        return uid

    async def listing(seconds=DAY, page=0):
        return await chat_inactivity.list_inactive(db, chat, seconds, page, bot_id=base+999, timezone_seconds=10800)

    async def invoke(text, kind="supergroup"):
        message = Message(text, owner, chat if kind == "supergroup" else owner, kind)
        assert await dispatch(registry, message, bot, db)
        assert message.replies
        return message.replies[-1]

    def callback(message, **kwargs):
        values = dict(uid=owner, chat=chat, seconds=DAY, page=0)
        values.update(kwargs)
        call = SimpleNamespace(from_user=SimpleNamespace(id=owner), message=message, answer=AsyncMock())
        return call, inactive.InactiveCB(**values)

    try:
        for text, seconds in (("", DAY), ("1д", DAY), ("5д", 5*DAY), ("7д", 7*DAY),
                              ("1н", 7*DAY), ("1г", 365*DAY), ("29д", 29*DAY), ("2 года", 730*DAY),
                              ("1мес", 30*DAY), ("1д12ч", DAY+43200), ("100лет", 36500*DAY)):
            assert inactive.parse_period(text) == seconds, text
        for text in ("0д", "-1д", "1.5д", "1,5д", "7д мусор", "7д0х", "навсегда", "23ч", "1", "36600д", "9"*5000+"д"):
            try:
                inactive.parse_period(text)
                raise AssertionError(text)
            except ValueError:
                pass
        assert split_duration("1г")[0].days == 365
        for text in (f"{MODERATION_DAYS+1}д", "2г"):
            try:
                split_duration(text)
                raise AssertionError("moderation limit weakened")
            except TooLong:
                pass
        for name in ("кто неактив", "неактивы", "призраки"):
            for suffix in ("", " 5д", ", 1г"):
                result = parse(registry, f"бот {name}{suffix}")
                assert isinstance(result, Parsed) and result.command.name == "неактивы"
            assert "1 день" in help_view.command_text(registry.get(name))
        help_text = help_view.section_text("stats")
        assert all(word in help_text for word in ("неактивы", "кто неактив", "призраки", "7д", "365"))
        assert "неактивы" not in help_view.section_text("stats", private=True)
        assert (await invoke("бот неактивы", "private"))[0].startswith("Эта команда работает только в группе")
        assert "Укажи срок" in (await invoke("бот неактивы 7д мусор"))[0]
        print("PASS: all aliases/help, 1-day default, custom periods, invalid input, moderation limits, group-only")

        boundary = await seed(1, age=1)
        await seed(2, age=(DAY-1)/DAY)
        await seed(3, age=400, left=True)
        await seed(4, age=400, is_bot=True)
        global_bot = await seed(5, age=400)
        await seed(5, age=1, cid=chat-1, is_bot=True)
        await seed(6, age=400, cid=chat-1)
        await seed(999, age=400)
        await seed(777000-base, age=400)
        returning = await seed(7, age=400, back=0.5)
        returned = await seed(8, age=400, back=3)
        silent = await seed(9, age=0, count=0, joined=10)
        unknown = await seed(10, no_dates=True)
        oldest_day = await seed(11, age=0, count=0, joined=0)
        await db.execute("INSERT INTO daily_user_stats(user_id,chat_id,date,message_count) VALUES (?,?,"
                         "((NOW() AT TIME ZONE 'UTC')::date-50)::text,1)", (oldest_day, chat))
        recent_day = await seed(12, age=0, count=0, joined=100)
        await db.execute("INSERT INTO daily_user_stats(user_id,chat_id,date,message_count) VALUES (?,?,"
                         "((NOW() AT TIME ZONE 'UTC')::date)::text,1)", (recent_day, chat))
        missing_timestamp = await seed(13, no_dates=True)
        await db.execute("INSERT INTO daily_user_stats(user_id,chat_id,date,message_count) VALUES (?,?,"
                         "((NOW() AT TIME ZONE 'UTC')::date)::text,1)", (missing_timestamp, chat))
        sample = await listing()
        ids = {m.user_id for m in sample.items}
        assert ids == {boundary, returned, silent, oldest_day}, ids
        assert sample.total == 4 and sample.unknown == 1
        assert next(m for m in sample.items if m.user_id == returned).seconds == 3*DAY
        assert next(m for m in sample.items if m.user_id == silent).never_spoke
        assert not next(m for m in sample.items if m.user_id == oldest_day).never_spoke
        assert recent_day not in ids, "daily activity must override a broken all-time counter"
        assert missing_timestamp not in ids, "daily activity also recovers a missing last-message timestamp"
        assert returning not in ids and unknown not in ids and global_bot not in ids
        await connection.execute("SET LOCAL TIME ZONE 'Pacific/Honolulu'")
        assert await listing() == sample, "timestamp comparisons must not depend on session timezone"
        await connection.execute("SET LOCAL TIME ZONE 'UTC'")
        assert (await listing(365*DAY)).total == 0
        print("PASS: exact 24h boundary, left/bots/service/other chat excluded, rejoin reset, never-speakers, unknown dates, timezone")

        for offset in range(20, 20+PAGE_SIZE+3):
            await seed(offset, age=5, name='<Участник & "имя">' * 20)
        first, last = await listing(), await listing(page=9999)
        assert len(first.items) == PAGE_SIZE and len(last.items) == 7 and last.page == 1 and last.total == 22
        assert not {m.user_id for m in first.items} & {m.user_id for m in last.items}
        assert await listing(page=-100) == first
        text, kwargs = await invoke("бот призраки")
        assert "от <b>1 дн.</b>" in text and "&lt;" in text and "&amp;" in text and '<Участник' not in text
        assert len(text) < 4096 and "Страница 1 из 2" in text
        assert "после возвращения" in inactive.render(sample, DAY) and "не писал при боте" in text
        for row in kwargs["reply_markup"].inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64
        if output:
            output.mkdir(parents=True, exist_ok=True)
            import json
            (output/"example.json").write_text(json.dumps({"text": text,
                "keyboard": kwargs["reply_markup"].model_dump()}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS: stable pages, clamps, safe long names, payload/message limits, readable result and keyboard")

        message = Message("", owner, chat)
        call, data = callback(message)
        call.from_user.id = owner+1
        await inactive.on_inactive(call, data, db, bot)
        assert call.answer.call_args.kwargs["show_alert"] and not message.edit_text.called
        for change in ({"chat": chat-1}, {"seconds": 0}, {"page": -1}):
            call, data = callback(message, **change)
            await inactive.on_inactive(call, data, db, bot)
            assert not message.edit_text.called
        call, data = callback(None)
        await inactive.on_inactive(call, data, db, bot)
        call, data = callback(SimpleNamespace(chat=SimpleNamespace(id=chat,type="supergroup")))
        await inactive.on_inactive(call, data, db, bot)
        assert "устарела" in call.answer.call_args.args[0]
        for key in ("all", "section:stats", "cmd:неактивы"):
            await db.execute("INSERT INTO bot_feature_switches(chat_id,feature) VALUES (?,?) ON CONFLICT DO NOTHING", (chat,key))
            feature_switches.invalidate()
            call, data = callback(message)
            await inactive.on_inactive(call, data, db, bot)
            assert not message.edit_text.called and "недоступна" in call.answer.call_args.args[0]
            if key == "all":
                quiet = Message("бот неактивы", owner, chat)
                assert await dispatch(registry, quiet, bot, db) and not quiet.replies
            else:
                assert "недоступно" in (await invoke("бот неактивы"))[0]
            await db.execute("DELETE FROM bot_feature_switches WHERE chat_id=? AND feature=?", (chat,key))
        feature_switches.invalidate()
        with patch("bot.chat.inactive.global_moderation.is_blocked", AsyncMock(return_value=True)):
            call, data = callback(message)
            await inactive.on_inactive(call, data, db, bot)
            assert not message.edit_text.called
        call, data = callback(message, page=1)
        await inactive.on_inactive(call, data, db, bot)
        assert message.edit_text.called and "Страница 2 из 2" in message.edit_text.call_args.args[0]
        await db.execute("UPDATE user_chat_stats SET is_left=TRUE WHERE chat_tg_id=? AND user_tg_id>=?", (chat,base+20))
        call, data = callback(message, page=1)
        await inactive.on_inactive(call, data, db, bot)
        assert "Страница 1 из 1" in message.edit_text.call_args.args[0]
        method = EditMessageText(chat_id=chat,message_id=1,text="x")
        for exc, expect in ((TelegramBadRequest(method=method,message="message is not modified"), "актуален"),
                            (TelegramBadRequest(method=method,message="message can't be edited"), "нельзя обновить"),
                            (TelegramNetworkError(method=method,message="timeout"), "Не удалось")):
            message.edit_text.side_effect = exc
            call, data = callback(message)
            await inactive.on_inactive(call, data, db, bot)
            assert expect in call.answer.call_args.args[0]
        with patch("bot.chat.inactive.build", AsyncMock(side_effect=ConnectionError("offline"))):
            call, data = callback(message)
            await inactive.on_inactive(call, data, db, bot)
            assert "Не удалось" in call.answer.call_args.args[0]
            failed = Message("", owner, chat)
            await inactive.cmd_inactive(Ctx(failed,bot,db,registry.get("неактивы"),"",True))
            assert "Не удалось" in failed.replies[-1][0]
        async def stalled(*args, **kwargs):
            await asyncio.sleep(1)
        with patch("bot.chat.inactive.QUERY_TIMEOUT_SECONDS", 0.01), patch(
                "bot.chat.inactive.chat_inactivity.list_inactive", stalled):
            failed = Message("", owner, chat)
            await inactive.cmd_inactive(Ctx(failed,bot,db,registry.get("неактивы"),"",True))
            assert "Не удалось" in failed.replies[-1][0]
        assert await connection.fetchval("SELECT user_messages_count_all_time FROM user_chat_stats WHERE chat_tg_id=$1 AND user_tg_id=$2", chat,boundary) == 1
        print("PASS: callback ownership/chat/invalid payload, all feature gates, blocked player, stale page, edit/network/DB failures, no sanctions")
    finally:
        registry.on_used = original_used
        await transaction.rollback()
        feature_switches.invalidate()
        await connection.close()
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2,
                                     server_settings={"search_path": "predvestnik,public"})
    try:
        async with lazy_connection(pool, source="bot") as lazy:
            result = await inactive.build(lazy, bot, chat, DAY)
            assert result.total == 0, "fixtures must have rolled back"
            assert lazy.holds_connection
            assert await release_current() and not lazy.holds_connection
            assert (await inactive.build(lazy, bot, chat, DAY)).total == 0
        assert pool.get_idle_size() == pool.get_size()
        print("PASS: production LazyPGAdapter, release before Telegram, reacquire, fixture rollback and no leaked slots")
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("loopback database required")
    asyncio.run(run(args.dsn, args.output))
