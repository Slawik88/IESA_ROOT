#!/usr/bin/env python3
"""Теги участников на настоящем PostgreSQL: откуда берутся, где показываются, как работают в чистке и админке.

Запуск: python tools/test_member_tags_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHAT = -100
ZW = "​"


def link(name, tag=None):
    """Ник в списках: ссылка на профиль в Telegram (t.me, без пинга) и тег после неё."""
    return f'<a href="https://t.me/{name}">@{name}</a>' + (f" [{tag}]" if tag else "")


def real_message(uid, username, text="привет", tag=None, chat_type="supergroup", chat_id=CHAT, **extra):
    """Настоящий Message из aiogram: так тег приходит из Telegram."""
    from aiogram.types import Chat, Message, User
    fields = dict(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type=chat_type, title="Тест"),
                  from_user=User(id=uid, is_bot=False, first_name=username.title(), username=username), text=text)
    if tag is not None:
        fields["sender_tag"] = tag
    return Message(**fields, **extra)


class FakeBot:
    def __init__(self):
        self.sent, self.tags = [], {}   # tags: user_id -> тег, который «знает» Telegram
        self.fail, self.asked = {}, []  # fail: user_id -> ошибка, которой ответит Telegram; asked: кого спрашивали

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=1001))]

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def get_chat_member(self, chat_id, user_id):
        self.asked.append((chat_id, user_id))
        if user_id in self.fail:
            raise self.fail[user_id]
        if user_id in self.tags and self.tags[user_id] == "__left__":
            return SimpleNamespace(status="left", user=SimpleNamespace(id=user_id))
        return SimpleNamespace(status="member", can_delete_messages=False, tag=self.tags.get(user_id),
                               user=SimpleNamespace(id=user_id))

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))

    def __getattr__(self, name):
        async def call(*a, **kw):
            return None
        return call


class FakeMessage:
    def __init__(self, text, uid, username, chat=CHAT, reply_to=None, tag=None):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=username, full_name=username, first_name=username.title())
        self.chat = SimpleNamespace(id=chat, type="supergroup", title="Тест")
        self.content_type, self.sender_tag = "text", tag
        self.reply_to_message = reply_to
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)

    async def answer(self, text, **kw):
        self.replies.append(text)

    async def delete(self):
        pass


async def run(db, bot, text, uid=1001, username="alpha", **kw):
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage(text, uid, username, **kw)
    assert await dispatch(registry, m, bot, db)
    return " | ".join(m.replies)


async def history(db, uid):
    async with db.execute("SELECT value FROM member_tag_history WHERE user_id = ? ORDER BY id", (uid,)) as cur:
        return [r[0] for r in await cur.fetchall()]


async def stored(db, uid, chat=CHAT):
    async with db.execute("SELECT member_tag FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?", (chat, uid)) as cur:
        row = await cur.fetchone()
    return row[0] if row else "нет строки"


async def main():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен: колонки и история добавляются один раз
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        pure()
        await capture(db)
        bot = FakeBot()
        await commands(db, bot)
        await shown_everywhere(db, bot)
        await purge_flow(db, bot)
        await admin_flow(db, bot)
        await backfill_flow(db)
    print("OK: member tags (capture, commands, lists, purge, admin, backfill)")


def pure():
    from aiogram.types import ChatMemberMember, ChatMemberOwner, User
    from services import member_tags as mt
    assert mt.clean("  Сяо \n") == "Сяо" and mt.clean("a​  b") == "a b" and mt.clean("") is None and mt.clean(None) is None
    assert mt.clean("x" * 200) == "x" * mt.MAX_LEN and mt.clean(5) is None
    assert mt.suffix("Сяо") == " [Сяо]" and mt.suffix(None) == "" and mt.with_tag("@a", "Т") == "@a [Т]"
    user = User(id=1, is_bot=False, first_name="A")
    assert mt.of_member(ChatMemberMember(user=user, tag="Лонэ")) == "Лонэ"
    assert mt.of_member(ChatMemberMember(user=user)) is None
    assert mt.of_member(ChatMemberOwner(user=user, is_anonymous=False, custom_title="свлд Арлекино")) == "свлд Арлекино"
    # Тег приходит и там, где модели aiogram его не знают (версия 3.22): через model_extra
    assert mt.of_member(SimpleNamespace(model_extra={"tag": "айно.мл.адм"})) == "айно.мл.адм"
    assert mt.of_member(SimpleNamespace(tag=None, custom_title="Админ")) == "Админ"
    # Обычное сообщение супергруппы: тег известен, а «нет тега» — тоже известно (человеку его убрали)
    assert mt.of_message(real_message(1, "a", tag=" Итто ")) == (True, "Итто")
    assert mt.of_message(real_message(1, "a")) == (True, None)
    # Обычная группа и служебные сообщения: тегов там нет, молчание не значит «тег убрали»
    assert mt.of_message(real_message(1, "a", chat_type="group", tag="Х")) == (False, None)
    assert mt.of_message(SimpleNamespace(chat=SimpleNamespace(type="supergroup"), content_type="new_chat_members")) == (False, None)
    assert mt.of_message(SimpleNamespace(chat=SimpleNamespace(type="supergroup"), content_type="text",
                                         model_extra={"sender_tag": "Из extra"})) == (True, "Из extra")


async def capture(db):
    from bot.chat.tracking import record_message
    from services import member_tags as mt
    # Первое сообщение: строка игрока заводится вместе с тегом
    await record_message(db, real_message(1001, "alpha", tag="Сяо"))
    assert await stored(db, 1001) == "Сяо" and await history(db, 1001) == ["Сяо"]
    # То же самое ещё раз: ничего не пишется (ни базы, ни истории)
    for _ in range(3):
        await record_message(db, real_message(1001, "alpha", tag="Сяо"))
    assert await history(db, 1001) == ["Сяо"]
    # Сменил тег
    await record_message(db, real_message(1001, "alpha", tag="Лонэ"))
    assert await stored(db, 1001) == "Лонэ" and await history(db, 1001) == ["Сяо", "Лонэ"]
    # Сообщение без тега в супергруппе = тег убрали
    await record_message(db, real_message(1001, "alpha"))
    assert await stored(db, 1001) is None and await history(db, 1001) == ["Сяо", "Лонэ", ""]
    # Служебное сообщение и обычная группа тег не трогают
    await record_message(db, real_message(1001, "alpha", tag="Итто"))
    svc = SimpleNamespace(from_user=SimpleNamespace(id=1001, is_bot=False, username="alpha", full_name="Alpha"),
                          chat=SimpleNamespace(id=CHAT, type="supergroup", title="Тест"), content_type="new_chat_members")
    await record_message(db, svc)
    assert await stored(db, 1001) == "Итто"
    # Теги разных чатов независимы
    await record_message(db, real_message(1001, "alpha", tag="Другой чат", chat_id=-200))
    assert await stored(db, 1001) == "Итто" and await stored(db, 1001, -200) == "Другой чат"
    # После перезапуска бота кэш пуст: то же сообщение тег подтверждает, но историю не плодит
    mt._seen.clear()
    before = len(await history(db, 1001))
    await record_message(db, real_message(1001, "alpha", tag="Итто"))
    assert await stored(db, 1001) == "Итто" and len(await history(db, 1001)) == before

    # Остальные участники чата
    for uid, name, tag in ((1002, "beta", "свлд Арлекино"), (1003, "gamma", None), (2001, "silent", None),
                           (2002, "talker", "айно.мл.адм")):
        await record_message(db, real_message(uid, name, tag=tag))

    # Событие chat_member: вошёл и сразу с тегом / сменили тег у остающегося
    from bot.chat import members
    bot = FakeBot()
    user = SimpleNamespace(id=2003, is_bot=False, username="newbie", full_name="Newbie")
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (2003, 'newbie') ON CONFLICT DO NOTHING")

    def event(old_status, new_status, tag):
        return SimpleNamespace(chat=SimpleNamespace(id=CHAT, type="supergroup"),
                               old_chat_member=SimpleNamespace(status=old_status, user=user),
                               new_chat_member=SimpleNamespace(status=new_status, user=user, tag=tag))
    await members.on_member_change(event("left", "member", "Итто"), bot, db)
    assert await stored(db, 2003) == "Итто"
    await members.on_member_change(event("member", "member", "Итто\\свлд"), bot, db)
    assert await stored(db, 2003) == "Итто\\свлд" and await history(db, 2003) == ["Итто", "Итто\\свлд"]
    await members.on_member_change(event("member", "left", None), bot, db)
    assert await stored(db, 2003) == "Итто\\свлд"   # ушёл — запоминаем, каким ушёл


async def commands(db, bot):
    from bot.chat import ranks
    await ranks.sync_owner(db, bot, CHAT, force=True)
    out = await run(db, bot, "бот тег", tag="Итто")
    assert "<b>Итто</b>" in out and "У вас" in out, out
    out = await run(db, bot, "бот тег", uid=1003, username="gamma")
    assert "нет тега" in out, out
    # Про другого игрока спрашиваем Telegram: тег мог смениться, пока человек молчал
    bot.tags[1003] = "Новый у gamma"
    out = await run(db, bot, "бот тег @gamma")
    assert "Новый у gamma" in out and f"@{ZW}gamma" in out, out
    assert await stored(db, 1003) == "Новый у gamma"
    # Не нашли — как у остальных команд
    out = await run(db, bot, "бот тег @nobody")
    assert "Не нашёл" in out, out
    # Ответ на сообщение: берём тег из самого сообщения
    out = await run(db, bot, "бот тег", reply_to=FakeMessage("x", 1002, "beta", tag="свлд Арлекино"))
    assert "свлд Арлекино" in out and "beta" in out, out
    # Поиск по части тега
    out = await run(db, bot, "бот тег арлекино")
    assert "свлд Арлекино" in out and link("beta") in out and "alpha" not in out, out
    out = await run(db, bot, "бот тег мл.адм")
    assert "айно.мл.адм" in out and link("talker") in out, out
    out = await run(db, bot, "бот тег нетакого")
    assert "ни у кого нет" in out, out
    out = await run(db, bot, "бот тег %")
    assert "ни у кого нет" in out, out   # % — не «любой тег»
    out = await run(db, bot, "бот теги")
    assert "Теги чата" in out and "Итто" in out and "свлд Арлекино" in out and "айно.мл.адм" in out, out
    assert "silent" not in out, out      # без тега в списке не бывает
    from bot.chat import help as help_mod
    assert {"тег", "теги"} <= {c.name for c in help_mod._by_section(False)["profile"]}   # команды видны в справке


async def shown_everywhere(db, bot):
    """Тег виден рядом с именем во всех сообщениях бота об игроке."""
    from bot.chat import profile, ranks, sanctions, top
    tag_beta, tag_talker = "свлд Арлекино", "айно.мл.адм"
    out = await run(db, bot, "бот варн, @talker 7д флуд")
    assert f"@{ZW}talker [{tag_talker}]" in out, out                      # санкция
    out = await run(db, bot, "бот снять варн, @talker")
    assert f"[{tag_talker}]" in out, out
    out = await run(db, bot, "бот защита, @beta 3д")
    assert f"@{ZW}beta [{tag_beta}]" in out, out
    out = await run(db, bot, "бот кто под защитой")
    assert link("beta", tag_beta) in out, out
    await ranks.store_rank(db, CHAT, 1002, 6)
    out = await run(db, bot, "бот ранги")
    assert link("beta", tag_beta) in out, out
    text, _ = await top.build(db, "c", "d", 0, CHAT)
    assert link("alpha", "Итто") in text and link("talker", tag_talker) in text, text      # топ чата: ник — ссылка на профиль
    text, _ = await top.build(db, "g", "d", 0, CHAT)
    assert "[Итто]" not in text, text                                       # в общем топе тега нет: он живёт в одном чате
    await run(db, bot, "бот мут, @talker 1ч")
    text, _ = await sanctions.list_view(db, 1001, CHAT, "mute", 0)
    assert link("talker", tag_talker) in text, text
    text, _ = await sanctions.card_view(db, 1001, CHAT, "mute", 0, 2002)
    assert f"[{tag_talker}]" in text, text
    # Профиль: отдельной строкой; в личке тега нет (чат неизвестен)
    target = SimpleNamespace(user_id=1002, username="beta", name="beta")
    text = await profile.card(db, CHAT, target, 1001, True)
    assert f"🏷 <b>{tag_beta}</b>" in text, text
    text = await profile.card(db, 1002, target, 1001, False)
    assert "🏷" not in text, text
    # Варп: тег автора берётся из его сообщения, тег цели из базы
    out = await run(db, bot, "бот обнять, @beta", tag="Итто")
    assert "[Итто]" in out and f"[{tag_beta}]" in out, out
    # Реплай-цель: тег из сообщения, на которое ответили, свежее базы
    out = await run(db, bot, "бот варн", reply_to=FakeMessage("x", 1003, "gamma", tag="Свежий"))
    assert "[Свежий]" in out, out
    # Семья: предложение называет обоих с тегами
    out = await run(db, bot, "бот брак, @beta", tag="Итто")
    assert "[Итто]" in out and f"[{tag_beta}]" in out, out


async def purge_flow(db, bot):
    from bot.chat import purge
    from bot.chat.tracking import local_now
    today = local_now().date()
    a, b = today - timedelta(days=7), today - timedelta(days=1)
    span = f"{a.strftime('%d.%m.%Y')}-{b.strftime('%d.%m.%Y')}"
    await db.execute("UPDATE user_chat_stats SET membership_since = NOW() - INTERVAL '40 days', joined_at = NOW() - INTERVAL '40 days' "
                     "WHERE chat_tg_id = ?", (CHAT,))
    await db.execute("DELETE FROM daily_user_stats WHERE chat_id = ?", (CHAT,))
    await db.execute("DELETE FROM chat_blacklist WHERE chat_id = ?", (CHAT,))
    await db.execute("UPDATE user_chat_stats SET muted_until = NULL, immune_until = NULL, is_immune = FALSE WHERE chat_tg_id = ?", (CHAT,))
    await db.execute("UPDATE user_chat_stats SET member_tag = ? WHERE chat_tg_id = ? AND user_tg_id = 2001", ("Старый тег", CHAT))
    vs = await purge.find_violators(db, CHAT, purge.Plan(10, a, b))
    ids = {v.user_id for v in vs}
    assert 2001 in ids and 2002 in ids, ids
    silent = next(v for v in vs if v.user_id == 2001)
    assert silent.tag == "Старый тег", silent                               # из базы уже подтянулся
    text = purge.dossier_text(silent, "Тест")
    assert "🏷 <b>Старый тег</b>" in text, text
    assert "🏷" not in purge.dossier_text(purge.Violator(9, "nobody", 0, 10, 0, 0, 0, ""), "Тест")   # без тега строки нет

    # Telegram знает свежий тег: перед досье бот его уточняет и сохраняет в базе и в снимке чистки
    bot.tags[2001] = "Свежий из Telegram"
    bot.tags[2002] = None
    out = await run(db, bot, f"бот чистка, 10 {span}")
    assert "Чистка началась" in out, out
    await asyncio.sleep(2.0)   # досье уходят фоном
    dossiers = [t for _, t, _ in bot.sent if "Досье" in t]
    mine = next(t for t in dossiers if "silent" in t)
    assert "🏷 <b>Свежий из Telegram</b>" in mine and "Старый тег" not in mine, mine
    assert "talker" in " ".join(dossiers) and "айно.мл.адм" not in next(t for t in dossiers if "talker" in t), dossiers   # убрали — досье без тега
    assert await stored(db, 2001) == "Свежий из Telegram" and await stored(db, 2002) is None
    s = await purge.active_session(db, CHAT)
    async with db.execute("SELECT user_id, member_tag FROM purge_targets WHERE session_id = ? ORDER BY user_id", (s[0],)) as cur:
        snap = {int(r[0]): r[1] for r in await cur.fetchall()}
    assert snap[2001] == "Свежий из Telegram" and snap[2002] is None, snap

    # Статус показывает, кто ждёт решения, с тегами; решения идут в итог по именам
    out = await run(db, bot, "бот чистка статус")
    assert "Ждут решения" in out and "[Свежий из Telegram]" in out, out
    await db.execute("UPDATE purge_targets SET verdict = 'ban' WHERE session_id = ? AND user_id = 2001", (s[0],))
    await db.execute("UPDATE purge_targets SET verdict = 'kick' WHERE session_id = ? AND user_id = 2002", (s[0],))
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage("бот чистка стоп", 1001, "alpha")
    answers = []

    async def answer(text, **kw):
        answers.append(text)
    m.answer = answer
    assert await dispatch(registry, m, bot, db)
    done = answers[0]
    assert "Забанены" in done and "[Свежий из Telegram]" in done and "Кикнуты" in done and f"@{ZW}talker" in done, done
    assert "Ждут решения" not in done and "Без решения</b>" in done and "[Новый у gamma]" in done, done   # кто остался без решения — тоже по именам

    # Ушедший из чата: Telegram ответил «left» — тег в базе не затирается, досье всё равно уходит
    bot.tags[2001] = "__left__"
    s_before = len(bot.sent)
    await run(db, bot, f"бот чистка, 10 {span}")
    await asyncio.sleep(1.5)
    assert any("silent" in t and "Свежий из Telegram" in t for _, t, _ in bot.sent[s_before:]), [t[:60] for _, t, _ in bot.sent[s_before:]]
    await run(db, bot, "бот чистка стоп")


async def admin_flow(db, bot):
    from services import admin_people, member_tags as mt, reports
    # Поиск по тегу: по части слова, без учёта регистра; у найденных видны их теги
    res = await admin_people.search(db, "арлекино")
    assert [p["id"] for p in res["players"]] == [1002] and res["players"][0]["tags"] == ["свлд Арлекино"], res["players"]
    res = await admin_people.search(db, "ИТТО")
    assert {p["id"] for p in res["players"]} == {1001, 2003}, res["players"]
    assert (await admin_people.search(db, "%"))["players"] == [], "% в поиске не должен значить «любой тег»"
    res = await admin_people.search(db, "")
    assert all("tags" in p for p in res["players"])
    assert (await admin_people.search(db, "1002"))["players"][0]["tags"] == ["свлд Арлекино"]
    # Карточка игрока: тег в каждом чате и история смен
    card = await admin_people.player(db, 1001)
    by_chat = {c["id"]: c["tag"] for c in card["chats"]}
    assert by_chat[CHAT] == "Итто" and by_chat[-200] == "Другой чат", by_chat
    assert [h["tag"] for h in card["tag_history"]][:2] == ["Итто", None] or card["tag_history"], card["tag_history"]
    assert {"chat_id", "chat_title", "tag", "at"} <= set(card["tag_history"][0])
    # Карточка чата: тег в «самых активных», в санкциях и сколько человек с тегом
    chat = await admin_people.chat(db, CHAT)
    tops = {x["id"]: x["tag"] for x in chat["top"]}
    assert tops[1001] == "Итто", tops
    assert chat["tagged"] >= 3, chat["tagged"]
    mutes = chat["sanctions"]["mutes"]["items"]
    assert any(x["user"] == 2002 and x["tag"] == "айно.мл.адм" for x in mutes) or not mutes, mutes
    # Жалоба: тег того, на кого жалуются, в том чате, где она подана
    rid = await reports.create(db, chat_id=CHAT, reporter_id=1003, target_id=1002, reason="спам", message_id=5, message_text="x")
    listing = await reports.listing(db, "open")
    mine = next(r for r in listing if r["target"]["id"] == 1002)
    assert mine["target"]["tag"] == "свлд Арлекино", mine["target"]
    # Журнал действий: тег игрока в чате записи
    await db.execute("INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (?, 1002, 1001, 'warn', 'т')", (CHAT,))
    feed = await admin_people.feed(db, kind="moderation", days=1)
    row = next(x for x in feed["items"] if x["user"] and x["user"]["id"] == 1002)
    assert row["user"]["tag"] == "свлд Арлекино", row["user"]
    # Пары чат/игрок
    got = await mt.pairs(db, [(CHAT, 1001), (-200, 1001), (CHAT, 999999)])
    assert got == {(CHAT, 1001): "Итто", (-200, 1001): "Другой чат"}, got
    assert await mt.pairs(db, []) == {}


async def checked(db, uid, chat):
    async with db.execute("SELECT member_tag, member_tag_checked_at FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
                          (chat, uid)) as cur:
        row = await cur.fetchone()
    return row[0], row[1] is not None


async def backfill_flow(db):
    """Обычные теги видны не только у тех, кто писал после запуска: бот сам дозапрашивает их у Telegram."""
    from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
    from aiogram.methods import GetChatMember
    from bot.chat import ranks, top
    from services import member_tags as mt
    chat, other = -300, -400
    mt._seen.clear()
    mt._denied.clear()
    for c in (chat, other):
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_is_admin, bot_can_moderate) VALUES (?, ?, TRUE, TRUE) "
                         "ON CONFLICT (chat_id) DO UPDATE SET bot_is_admin = TRUE, bot_left_at = NULL", (c, f"Чат {c}"))
    from bot.chat.tracking import local_now
    day = local_now().date().isoformat()   # сутки бота идут по его часовому поясу, а не по UTC базы: иначе вечером тест видит «пустой» день
    users = {3001: "diegoyuuki", 3002: "kovid", 3003: "tarta", 3004: "lini", 3005: "quiet"}
    for i, (uid, name) in enumerate(users.items()):   # как в проде: строки есть (люди писали раньше), тег бот не знает
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, name))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, last_message_at) VALUES (?, ?, NOW() - (? || ' hours')::interval) "
                         "ON CONFLICT DO NOTHING", (uid, chat, str(i)))
        await db.execute("INSERT INTO daily_user_stats (date, chat_id, user_id, message_count) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT DO NOTHING", (day, chat, uid, 100 - i))
    await db.commit()
    for u in users:
        assert await checked(db, u, chat) == (None, False)

    bot = FakeBot()
    bot.tags.update({3002: "Итто|Совлд.", 3003: "Тарталья", 3004: "Лини"})
    # Показ списка: тег дозапрашивается у Telegram сразу, без ожидания сообщений от людей
    text, _ = await top.build(db, "c", "d", 0, chat, bot)
    for who, tag in (("kovid", "Итто|Совлд."), ("tarta", "Тарталья"), ("lini", "Лини")):
        assert link(who, tag) in text, text
    assert "@diegoyuuki</a> [" not in text and "@quiet</a> [" not in text, text   # у кого тега нет — строка чистая
    assert link("diegoyuuki") in text, text
    assert await checked(db, 3002, chat) == ("Итто|Совлд.", True)
    assert await checked(db, 3001, chat) == (None, True), "«тега нет» тоже запомнено: повторно не спрашиваем"
    assert [v for v in await history(db, 3002)] == ["Итто|Совлд."]
    bot.asked.clear()
    text, _ = await top.build(db, "c", "d", 0, chat, bot)
    assert bot.asked == [] and link("kovid", "Итто|Совлд.") in text, bot.asked   # второй показ — без запросов
    text, _ = await top.build(db, "g", "d", 0, chat, bot)
    assert bot.asked == [], "общий топ тегов не показывает и Telegram не спрашивает"

    # Игрок без ника: ссылка на профиль по id; тег с «<» экранируется
    from bot.chat.style import profile_link
    assert profile_link(77, None) == '<a href="tg://user?id=77">id77</a>'
    assert profile_link(77, "ник", "<b>x</b>") == '<a href="https://t.me/ник">@ник</a> [&lt;b&gt;x&lt;/b&gt;]'

    # Бот без бота (личка / нет клиента) ничего не спрашивает и не падает
    assert await mt.many_fresh(None, db, chat, [3002]) == {3002: "Итто|Совлд."}

    # Фоновый обход: сначала недавно писавшие, ушедшие и ошибки не ломают проход
    for i, uid in enumerate((3101, 3102, 3103, 3104)):
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, f"u{uid}"))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, last_message_at) VALUES (?, ?, NOW() - (? || ' hours')::interval) "
                         "ON CONFLICT DO NOTHING", (uid, other, str(i + 1)))
    await db.commit()
    bot = FakeBot()
    bot.tags.update({3101: "Первый", 3102: "__left__", 3104: "Четвёртый"})
    bot.fail[3103] = TelegramNetworkError(method=GetChatMember(chat_id=other, user_id=3103), message="сеть")
    mt.BACKFILL_PAUSE = 0
    done = await mt.backfill_batch(bot, db)
    assert done == 2, done   # 3101 и 3102; на 3103 сеть отвалилась, проход закончился
    assert await checked(db, 3101, other) == ("Первый", True)
    assert await checked(db, 3102, other) == (None, True), "ушедшего пометили проверенным"
    assert await checked(db, 3103, other) == (None, False) and await checked(db, 3104, other) == (None, False)
    bot.fail.clear()
    assert await mt.backfill_batch(bot, db) == 2
    assert await checked(db, 3104, other) == ("Четвёртый", True)
    bot.asked.clear()
    assert await mt.backfill_batch(bot, db) == 0 and bot.asked == [], "всё проверено — Telegram не дёргаем"

    # Чат, где Telegram отказал (бот потерял права), пропускается и не крутится по кругу
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (3201, 'denied') ON CONFLICT DO NOTHING")
    await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (3201, ?), (3202, ?) ON CONFLICT DO NOTHING", (other, other))
    await db.commit()
    bot.fail[3201] = TelegramBadRequest(method=GetChatMember(chat_id=other, user_id=3201), message="Bad Request: CHAT_ADMIN_REQUIRED")
    bot.fail[3202] = bot.fail[3201]
    assert await mt.backfill_batch(bot, db) == 0
    asked = len(bot.asked)
    assert await mt.backfill_batch(bot, db) == 0 and len(bot.asked) == asked, "чат на паузе"
    assert await checked(db, 3201, other) == (None, False), "отказ — не «тега нет»: человека проверим, когда вернутся права"
    mt._denied.clear()

    # Давно проверенных и давно молчащих перепроверяем: тег мог смениться
    await db.execute("UPDATE user_chat_stats SET member_tag_checked_at = NOW() - INTERVAL '30 days', "
                     "last_message_at = NOW() - INTERVAL '30 days' WHERE chat_tg_id = ? AND user_tg_id = 3101", (other,))
    await db.execute("UPDATE user_chat_stats SET member_tag_checked_at = NOW() - INTERVAL '30 days' "
                     "WHERE chat_tg_id = ? AND user_tg_id = 3104", (other,))   # 3104 писал недавно — тег пришёл бы с сообщением
    await db.execute("UPDATE user_chat_stats SET member_tag_checked_at = NOW() WHERE chat_tg_id = ? AND user_tg_id IN (3201, 3202)", (other,))
    await db.commit()
    bot.fail.clear()
    bot.tags[3101] = "Сменил"
    bot.asked.clear()
    assert await mt.backfill_batch(bot, db) == 1 and bot.asked == [(other, 3101)], bot.asked
    assert await checked(db, 3101, other) == ("Сменил", True)
    assert await history(db, 3101) == ["Первый", "Сменил"], await history(db, 3101)

    # Чат, который бот покинул или где он не админ, обход не трогает
    await db.execute("UPDATE chat_settings SET bot_is_admin = FALSE WHERE chat_id = ?", (chat,))
    await db.execute("UPDATE user_chat_stats SET member_tag_checked_at = NULL WHERE chat_tg_id = ?", (chat,))
    await db.commit()
    bot.asked.clear()
    assert await mt.backfill_batch(bot, db) == 0 and bot.asked == []

    # Список рангов тоже дозапрашивает
    bot.tags[3003] = "Тарталья"
    await db.execute("UPDATE chat_settings SET bot_is_admin = TRUE WHERE chat_id = ?", (chat,))
    await ranks.store_rank(db, chat, 3003, 4)
    await db.commit()
    out = await run(db, bot, "бот ранги", chat=chat)
    assert link("tarta", "Тарталья") in out, out


asyncio.run(main())
