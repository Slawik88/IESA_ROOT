#!/usr/bin/env python3
"""Подключение бота к чату на настоящем PostgreSQL: путь от «добавили в группу» до «всё готово».

Проверяет весь маршрут нового владельца: сообщение с чек-листом в чате, личку, выдачу прав по шагам, модераторов, админ-чат,
напоминания, воронку для админки; а ещё места, где человек может запутаться (чужие кнопки, закрытая личка, потерянные события).
Запуск: python tools/test_chat_onboarding_pg.py --dsn postgresql://... (пустая тестовая БД!)
Переменная ONB_TRANSCRIPT=путь — записать все тексты бота по порядку, чтобы перечитать их глазами новичка.
"""
import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BOT_ID, BOT_NAME = 999, "predvestnik_bot"
CHAT, CHAT2, CHAT3 = -1001, -1002, -1003
OWNER, MOD, JUNIOR, COSMETIC, STRANGER = 5001, 5002, 5003, 5004, 7777
TRANSCRIPT: list[str] = []


def note(kind: str, where, text: str, kb=None) -> None:
    buttons = ""
    if kb is not None:
        rows = []
        for row in kb.inline_keyboard:
            rows.append(" | ".join(f"[{b.text}→{'URL ' + b.url if b.url else b.callback_data}]" for b in row))
        buttons = "\n    " + "\n    ".join(rows)
    TRANSCRIPT.append(f"── {kind} · {where}\n{re.sub(r'<[^>]+>', '', text)}{buttons}\n")


def tg_error(kind: str, text: str):
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    from aiogram.methods import SendMessage
    method = SendMessage(chat_id=1, text="x")
    return (TelegramForbiddenError if kind == "forbidden" else TelegramBadRequest)(method=method, message=text)


class FakeBot:
    """Telegram в миниатюре: права бота по чатам, администраторы, кто запускал бота (иначе личка закрыта), все сообщения."""

    def __init__(self):
        self.me_user = SimpleNamespace(id=BOT_ID, username=BOT_NAME, can_read_all_group_messages=False)
        self.rights: dict[int, dict] = {}       # чат -> {"status", "can_delete_messages", "can_restrict_members"}
        self.admins: dict[int, list] = {}       # чат -> список администраторов Telegram
        self.titles: dict[int, str] = {}
        self.chat_types: dict[int, str] = {}
        self.started: set[int] = set()          # кто запускал бота: только им можно написать в личку
        self.cannot_write: set[int] = set()     # чаты, где бот писать не может
        self.sent: list[tuple[int, str, dict]] = []
        self.edits: list[tuple[int, int, str]] = []
        self.photos: list[tuple[int, object, str | None, object]] = []   # (кому, фото, подпись, кнопки)
        self.texts: dict[tuple[int, int], str] = {}
        self._next = 100

    async def me(self):
        return self.me_user

    def set_rights(self, chat, status="member", delete=False, restrict=False):
        self.rights[chat] = {"status": status, "can_delete_messages": delete, "can_restrict_members": restrict}

    async def get_chat_member(self, chat_id, user_id):
        if user_id == BOT_ID:
            if chat_id not in self.rights:
                raise tg_error("bad", "Bad Request: chat not found")
            return SimpleNamespace(user=SimpleNamespace(id=BOT_ID), **self.rights[chat_id])
        for a in self.admins.get(chat_id, []):
            if a.user.id == user_id:
                return a
        return SimpleNamespace(status="member", user=SimpleNamespace(id=user_id))

    async def get_chat(self, chat_id):
        if chat_id not in self.titles:
            raise tg_error("bad", "Bad Request: chat not found")
        return SimpleNamespace(title=self.titles[chat_id], type=self.chat_types.get(chat_id, "supergroup"), permissions=None)

    async def get_chat_administrators(self, chat_id):
        return list(self.admins.get(chat_id, []))

    async def send_message(self, chat_id, text, **kw):
        if chat_id > 0 and chat_id not in self.started:
            raise tg_error("forbidden", "Forbidden: bot can't initiate conversation with a user")
        if chat_id < 0 and chat_id in self.cannot_write:
            raise tg_error("forbidden", "Forbidden: bot is not a member of the supergroup chat")
        self._next += 1
        self.sent.append((chat_id, text, kw))
        self.texts[(chat_id, self._next)] = text
        note("отправлено", "личка" if chat_id > 0 else "чат", text, kw.get("reply_markup"))
        return SimpleNamespace(message_id=self._next)

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        self._next += 1
        self.photos.append((chat_id, photo, caption, reply_markup))
        note("картинка", "личка" if chat_id > 0 else "чат", caption or "(без подписи)", reply_markup)
        return SimpleNamespace(message_id=self._next, photo=[SimpleNamespace(file_id=f"photo-{self._next}")])

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kw):
        if self.texts.get((chat_id, message_id)) == text:
            raise tg_error("bad", "Bad Request: message is not modified: specified new message content and reply markup are exactly the same")
        self.texts[(chat_id, message_id)] = text
        self.edits.append((chat_id, message_id, text))
        note("изменено", f"чат {chat_id}", text, kw.get("reply_markup"))

    def last_to(self, chat_id):
        return next((t for c, t, _ in reversed(self.sent) if c == chat_id), None)

    def count_to(self, chat_id):
        return sum(1 for c, _, _ in self.sent if c == chat_id)

    def __getattr__(self, name):
        async def call(*a, **kw):
            return None
        return call


def admin(uid, name, **rights):
    base = dict(can_promote_members=False, can_restrict_members=False, can_delete_messages=False)
    base.update(rights)
    return SimpleNamespace(status="administrator", user=SimpleNamespace(id=uid, is_bot=False, username=name, full_name=name.title()), **base)


def creator(uid, name):
    return SimpleNamespace(status="creator", user=SimpleNamespace(id=uid, is_bot=False, username=name, full_name=name.title()))


def user(uid, name):
    from aiogram.types import User
    return User(id=uid, is_bot=False, first_name=name.title(), username=name)


def bot_user():
    from aiogram.types import User
    return User(id=BOT_ID, is_bot=True, first_name="Предвестник", username=BOT_NAME)


def member_event(chat, who, old, new, delete=False, restrict=False, title="Моя группа", chat_type="supergroup"):
    """Настоящий ChatMemberUpdated: что Telegram присылает, когда бота добавили, повысили или убрали."""
    from aiogram.types import Chat, ChatMemberAdministrator, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated
    me = bot_user()

    def state(status):
        if status == "left":
            return ChatMemberLeft(status="left", user=me)
        if status == "administrator":
            return ChatMemberAdministrator.model_construct(status="administrator", user=me, can_delete_messages=delete,
                                                           can_restrict_members=restrict)
        return ChatMemberMember(status="member", user=me)
    return ChatMemberUpdated(chat=Chat(id=chat, type=chat_type, title=title), from_user=who, date=datetime.now(timezone.utc),
                             old_chat_member=state(old), new_chat_member=state(new))


class FakeCbMessage:
    def __init__(self, chat_id, chat_type, message_id=500):
        self.chat = SimpleNamespace(id=chat_id, type=chat_type)
        self.message_id = message_id
        self.text = ""
        self.edited: list[tuple[str, object]] = []
        self.answers: list[tuple[str, object]] = []
        self.photo = None

    async def answer(self, text, **kw):   # новое сообщение в тот же чат
        self.answers.append((text, kw.get("reply_markup")))
        note("ответ", f"{'личка' if self.chat.type == 'private' else 'чат'}", text, kw.get("reply_markup"))

    async def edit_text(self, text, **kw):
        if text == self.text:
            raise tg_error("bad", "Bad Request: message is not modified")
        self.text = text
        self.edited.append((text, kw.get("reply_markup")))
        note("экран", f"{'личка' if self.chat.type == 'private' else 'чат'}", text, kw.get("reply_markup"))


class FakeCall:
    def __init__(self, uid, name, message):
        self.from_user = SimpleNamespace(id=uid, username=name, is_bot=False)
        self.message = message
        self.toasts: list[tuple[str | None, bool]] = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.toasts.append((text, show_alert))


class FakeMessage:
    def __init__(self, text, uid, name, chat_id, chat_type, message_id=1):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=name, full_name=name.title(), first_name=name.title())
        self.chat = SimpleNamespace(id=chat_id, type=chat_type, title="Моя группа")
        self.message_id = message_id
        self.content_type, self.sender_tag, self.reply_to_message, self.sticker = "text", None, None, None
        self.replies: list[tuple[str, object]] = []

    async def answer(self, text, **kw):
        self.replies.append((text, kw.get("reply_markup")))
        note("ответ", "личка" if self.chat.type == "private" else "чат", text, kw.get("reply_markup"))

    reply = answer

    async def delete(self):
        pass


def buttons(kb):
    return [b for row in kb.inline_keyboard for b in row]


def find(kb, text_part):
    return next((b for b in buttons(kb) if text_part in b.text), None)


async def press(bot, db, uid, name, message, action, chat=0):
    from bot.chat import onboarding
    call = FakeCall(uid, name, message)
    await onboarding.on_onboarding(call, onboarding.OnbCB(a=action, c=chat), bot, db)
    return call


async def events(db, chat=None):
    async with db.execute("SELECT event, detail, user_id FROM chat_onboarding_events WHERE (?::bigint IS NULL OR chat_id = ?) ORDER BY id",
                          (chat, chat)) as cur:
        return [(r[0], r[1], r[2]) for r in await cur.fetchall()]


async def main():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        bot = FakeBot()
        await pure(bot)
        await journey_new_owner(db, bot)
        await journey_ready_at_once(db, bot)
        await journey_edge_cases(db, bot)
        await reminders(db, bot)
        await funnel_and_migration(db, bot)
        await entry_points(db, bot)
        await newbie_traps(db, bot)
    path = os.environ.get("ONB_TRANSCRIPT")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(TRANSCRIPT))
    print("OK: chat onboarding (journey, rights, staff, admin chat, reminders, funnel, entry points)")


async def pure(bot):
    from bot.chat import onboarding as ob
    from bot.chat.framework import Parsed, parse, registry
    from bot.keyboards import cta
    from services import chat_setup as cs

    assert cs.add_url("bot") == "https://t.me/bot?startgroup=setup&admin=delete_messages+restrict_members"
    assert "admin=delete_messages+restrict_members" in cta.ADD_TO_GROUP_URL and "startgroup=" in cta.ADD_TO_GROUP_URL
    assert ob.setup_link("bot", -1001) == "https://t.me/bot?start=setup_-1001"
    assert len(ob.setup_link("a" * 32, -1001234567890).split("start=")[1]) <= 64   # Telegram: параметр start не длиннее 64 символов
    # Права администратора Telegram -> ранг в боте
    assert cs.rank_for_admin(SimpleNamespace(can_promote_members=True, can_restrict_members=True)) == 6
    assert cs.rank_for_admin(SimpleNamespace(can_restrict_members=True, can_delete_messages=True)) == 4
    assert cs.rank_for_admin(SimpleNamespace(can_delete_messages=True)) == 3
    assert cs.rank_for_admin(SimpleNamespace(can_pin_messages=True)) is None   # косметические права ранга не дают

    # Все экраны: кнопки укладываются в лимиты Telegram, а каждая команда в тексте — настоящая
    s = cs.Setup(chat_id=-1001, title="Группа <b>&", present=True, admin=True, can_delete=True, can_restrict=False, live=True)
    ready = cs.Setup(chat_id=-1001, title="Группа", present=True, admin=True, can_delete=True, can_restrict=True, live=True, staff=2,
                     admin_chat={"id": -5, "title": "Админы"})
    gone = cs.Setup(chat_id=-1001, title="Группа")
    waiting = cs.Setup(chat_id=-1001, title="Группа", present=True, admin=True, can_delete=True, can_restrict=True, live=True, verified=False)
    proposals = [cs.Proposal(1, "alpha", "Alpha", 4, 0), cs.Proposal(2, None, "Без ника", 3, 0)]
    screens = [ob.group_screen(s, BOT_NAME), ob.group_screen(ready, BOT_NAME), ob.chat_screen(s, BOT_NAME), ob.chat_screen(ready, BOT_NAME, "intro"),
               ob.chat_screen(gone, BOT_NAME), ob.chat_screen(waiting, BOT_NAME), ob.group_screen(waiting, BOT_NAME), ob.rights_screen(s, BOT_NAME), ob.trouble_screen(s), ob.staff_screen(ready, proposals, legend=ob.rank_legend({"warn": 3, "mute": 4, "kick": 5, "ban": 6, "close_chat": 6}, [4, 3])),
               ob.staff_screen(ready, []), ob.staff_screen(ready, None), ob.admin_screen(ready), ob.admin_screen(s), ob.admin_screen(s, "abcd1234"),
               ob.guide_screen(0), ob.guide_screen(-1001), ob.home_screen(BOT_NAME, "https://example.org/app"), ob.add_screen(BOT_NAME),
               ob.home_screen(BOT_NAME), ob.guide_screen(0, "https://example.org/app"), ob.play_screen(BOT_NAME, "https://example.org/app"),
               ob.play_screen(BOT_NAME), ob.add_photo_screen(BOT_NAME), ob.play_photo_screen(BOT_NAME, "https://example.org/app"),
               ob.my_screen([], BOT_NAME), ob.my_screen([{"id": -1, "title": "T" * 80, "ready": True}], BOT_NAME), ob.denied_screen()]
    examples = set()
    for text, kb in screens:
        assert len(text) < 3900, len(text)
        assert text.count("<b>") == text.count("</b>") and text.count("<code>") == text.count("</code>"), text
        for b in buttons(kb):
            assert (b.callback_data is None) != (b.url is None and b.web_app is None) or b.web_app, b
            if b.callback_data:
                assert len(b.callback_data.encode()) <= 64, b.callback_data
        examples.update(re.findall(r"<code>(бот [^<]+)</code>", text))
    assert len(examples) >= 12, examples
    for example in sorted(examples):
        example = example.replace("CODE", "abcd1234")
        parsed = parse(registry, example, BOT_NAME, False)
        assert isinstance(parsed, Parsed), f"в подсказке команда, которой нет: «{example}» -> {parsed}"
    # Подписи под картинками укладываются в лимит Telegram (1024 видимых знака)
    for text, _ in (ob.add_photo_screen(BOT_NAME), ob.play_photo_screen(BOT_NAME, "https://example.org/app")):
        assert len(re.sub(r"<[^>]+>", "", text)) < 1000, len(text)
    # Картинки знакомства рисуются, имя без эмодзи и экзотики (их нет в шрифте)
    from services import welcome_images as wi
    for pic in (wi.welcome("Слава"), wi.welcome(""), wi.connect_steps(), wi.site_tour()):
        assert pic[:2] == b"\xff\xd8" and 20_000 < len(pic) < 2_000_000, len(pic)
    assert wi.clean_name("Слава 🔥") == "Слава" and wi.clean_name("🔥🔥") == "" and wi.clean_name(None) == ""
    assert wi.clean_name("Alexander Very Long Name").endswith("…") and wi.clean_name("<b>Иван</b>") == "bИванb"
    # Название чата с HTML не ломает разметку
    assert "&lt;b&gt;&amp;" in ob.chat_screen(s, BOT_NAME)[0]
    # Чек-лист: чего не хватает, названо словами Telegram
    assert cs.Setup(chat_id=-1, present=True, admin=True, can_delete=True).missing == ["ограничивать участников"]
    assert cs.Setup(chat_id=-1).missing == ["быть в чате"]
    assert ob.missing_rights(cs.Setup(chat_id=-1, present=True)) == [ob.RIGHT_DELETE, ob.RIGHT_RESTRICT]


async def journey_new_owner(db, bot):
    """Новичок: добавил бота участником → видит чек-лист → выдаёт права → настраивает модераторов и админ-чат."""
    from bot.chat import members, onboarding as ob, ranks
    from services import chat_setup as cs

    bot.titles[CHAT] = "Моя группа"
    bot.admins[CHAT] = [creator(OWNER, "owner"), admin(MOD, "mod", can_restrict_members=True, can_delete_messages=True),
                        admin(JUNIOR, "junior", can_delete_messages=True), admin(COSMETIC, "cosmetic")]
    bot.set_rights(CHAT, "member")

    # 1. Бота добавили без прав. Владелец ещё не запускал бота: личка закрыта, но в чате есть чек-лист и кнопка в личку.
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "left", "member"), bot, db)
    assert bot.count_to(CHAT) == 1 and bot.count_to(OWNER) == 0
    text = bot.last_to(CHAT)
    assert "❌ Я администратор" in text and "✅ Я в чате" in text and "Добавить администратора" in text, text
    assert RIGHT_ALL(text), text
    kb = [kw["reply_markup"] for c, _, kw in bot.sent if c == CHAT][-1]
    assert find(kb, "Проверить").callback_data == f"onb:chk:{CHAT}"
    assert find(kb, "в личке").url == f"https://t.me/{BOT_NAME}?start=setup_{CHAT}"
    rec = await cs.get(db, CHAT)
    assert rec["inviter_id"] == OWNER and rec["message_id"] and rec["rights_ok_at"] is None and rec["reminders"] == 0
    kinds = [e[0] for e in await events(db, CHAT)]
    assert kinds == ["added", "dm_failed"], kinds
    assert await ranks.get_owner(db, CHAT) == OWNER   # владелец узнан сразу

    # 2. Сразу за входом Telegram присылает в чат /start от того же человека: второго приветствия быть не должно
    from bot.chat.payments import cmd_start
    start = FakeMessage("/start setup", OWNER, "owner", CHAT, "supergroup")
    await cmd_start(start, SimpleNamespace(args="setup"), db, bot)
    assert bot.count_to(CHAT) == 1 and not start.replies

    # 3. Владелец переходит по кнопке «Подробно в личке»: бот открывается сразу на нужном чате
    bot.started.add(OWNER)
    dm = FakeMessage(f"/start setup_{CHAT}", OWNER, "owner", OWNER, "private")
    await cmd_start(dm, SimpleNamespace(args=f"setup_{CHAT}"), db, bot)
    text, kb = dm.replies[-1]
    assert "Моя группа" in text and "Путь настройки" in text and "👉 2. Права администратора" in text and "▫️ 3. Проверка" in text, text
    assert "✅ 1. Бот в чате" in text and "Сделайте меня администратором" in text and "Как выдать права" in text, text
    assert find(kb, "Как выдать права").callback_data == f"onb:rights:{CHAT}"
    screen = FakeCbMessage(OWNER, "private")
    screen.text = text

    # 4. Инструкция по выдаче прав и «Не получается»
    call = await press(bot, db, OWNER, "owner", screen, "rights", CHAT)
    assert "Добавить администратора" in screen.text and ob.RIGHT_DELETE in screen.text and ob.RIGHT_RESTRICT in screen.text
    assert "Delete messages" in screen.text and "Ban users" in screen.text, screen.text   # те же пункты в английском Telegram
    assert find(screen.edited[-1][1], "одним нажатием").url == cs.add_url(BOT_NAME)          # быстрый способ: ссылка с готовыми правами
    await press(bot, db, OWNER, "owner", screen, "trouble", CHAT)
    assert "Анонимность" in screen.text and "Нет кнопки" in screen.text
    # «Проверить», пока ничего не поменялось: экран тот же — человеку говорят об этом, а не молчат
    await press(bot, db, OWNER, "owner", screen, "chat", CHAT)
    call = await press(bot, db, OWNER, "owner", screen, "chk", CHAT)
    assert call.toasts and call.toasts[-1][0] and "оба права" in call.toasts[-1][0], call.toasts

    # 5. Выдал только «администратор + удаление»: чек-лист в чате обновился сам, личка молчит (рано)
    bot.set_rights(CHAT, "administrator", delete=True)
    dms = bot.count_to(OWNER)
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "member", "administrator", delete=True), bot, db)
    edited = [t for c, _, t in bot.edits if c == CHAT][-1]
    assert "✅ Я администратор" in edited and "✅ Удаление сообщений" in edited and "❌ Блокировка пользователей" in edited, edited
    assert "включите пункт <b>«Блокировка пользователей»</b>" in edited and "Добавить администратора" not in edited, edited
    assert bot.count_to(OWNER) == dms and bot.count_to(CHAT) == 1

    # 6. Выдал всё: сообщение в чате превращается в «готово», владельцу приходит личное сообщение
    bot.set_rights(CHAT, "administrator", delete=True, restrict=True)
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "administrator", "administrator", delete=True, restrict=True), bot, db)
    edited = [t for c, _, t in bot.edits if c == CHAT][-1]
    assert "Права получены" in edited and "Последний шаг" in edited and "бот помощь" in edited and "⏳ Жду первую команду" in edited, edited
    assert "Бот подключён" not in edited, "пока бот не ответил на команду, подключение не завершено"
    assert bot.count_to(OWNER) == dms + 1 and "Права получены" in bot.last_to(OWNER)
    assert "👉 3. Проверка: напишите в чате «бот помощь»" in bot.last_to(OWNER) and "Откройте чат и напишите" in bot.last_to(OWNER), bot.last_to(OWNER)
    assert (await cs.get(db, CHAT))["rights_ok_at"] is not None
    # то же событие второй раз (Telegram повторяет) ничего не шлёт
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "administrator", "administrator", delete=True, restrict=True), bot, db)
    assert bot.count_to(OWNER) == dms + 1
    # кнопка «Проверить» в чате, когда всё готово
    group_msg = FakeCbMessage(CHAT, "supergroup", message_id=(await cs.get(db, CHAT))["message_id"])
    call = await press(bot, db, STRANGER, "stranger", group_msg, "chk", CHAT)
    assert "Осталось написать «бот помощь»" in call.toasts[-1][0], call.toasts
    # Пока «Проверить» нажимали подряд, бот отвечает отказом подождать, а не гоняет Telegram каждый раз
    call = await press(bot, db, STRANGER, "stranger", group_msg, "chk", CHAT)
    assert "Подождите" in call.toasts[-1][0], call.toasts
    ob._chk_cooldown.clear()
    # кнопка из чужого чата в этом чате не действует
    call = await press(bot, db, STRANGER, "stranger", group_msg, "chk", CHAT2)
    assert not call.toasts[-1][0]

    # Первая команда в чате: бот ответил, значит видит сообщения, и подключение завершено
    s0 = await cs.inspect(bot, db, CHAT)
    assert s0.ready and not s0.verified
    edits_before = len([e for e in bot.edits if e[0] == CHAT])
    await ob.on_command_used(bot, db, CHAT)
    edited = [t for c, _, t in bot.edits if c == CHAT][-1]
    assert len([e for e in bot.edits if e[0] == CHAT]) == edits_before + 1
    assert "Бот подключён и отвечает" in edited and "✅ Отвечаю на команды" in edited and "Последний шаг" not in edited, edited
    assert (await cs.inspect(bot, db, CHAT)).verified
    await ob.on_command_used(bot, db, CHAT)                                   # вторая команда ничего не меняет
    assert len([e for e in bot.edits if e[0] == CHAT]) == edits_before + 1
    assert [e[0] for e in await events(db, CHAT)].count("first_command") == 1

    # 7. Модераторы из администраторов Telegram
    screen = FakeCbMessage(OWNER, "private")
    await press(bot, db, OWNER, "owner", screen, "chat", CHAT)
    assert "✅ 3. Проверка: бот отвечает на команды" in screen.text and "👉 4. Модераторы (по желанию)" in screen.text, screen.text
    assert "<b>Сейчас:</b> Назначьте модераторов" in screen.text, screen.text
    await press(bot, db, OWNER, "owner", screen, "staff", CHAT)
    assert "@mod → 🛡 Модератор" in screen.text and "@junior → 🔰 Младший модератор" in screen.text, screen.text
    assert "Что это даст в вашем чате" in screen.text and "Модератор — варны, муты" in screen.text, screen.text   # пороги чата, не выдуманные
    assert "Младший модератор — варны" in screen.text and "кики" not in screen.text.split("Что это даст")[1].split("Ранг можно")[0], screen.text
    assert "cosmetic" not in screen.text and "owner" not in screen.text      # без реальных прав и владельца ранг не предлагаем
    # Telegram-админ без ранга в боте (MOD) не может раздавать ранги, даже если бы нашёл кнопку
    mod_screen = FakeCbMessage(MOD, "private")
    call = await press(bot, db, MOD, "mod", mod_screen, "staffok", CHAT)
    assert call.toasts[-1][1] and "7" in call.toasts[-1][0] and await ranks.get_rank(db, CHAT, JUNIOR) == 0
    call = await press(bot, db, OWNER, "owner", screen, "staffok", CHAT)
    assert "Назначено: 2" in screen.text and await ranks.get_rank(db, CHAT, MOD) == 4 and await ranks.get_rank(db, CHAT, JUNIOR) == 3
    assert "Предлагать больше некого" in screen.text   # после назначения предлагать больше некого
    # Повышать некого, понижать нельзя: у MOD уже 4, Telegram-права дают 4 — ранг не трогаем
    await ranks.store_rank(db, CHAT, JUNIOR, 5)
    await press(bot, db, OWNER, "owner", screen, "staff", CHAT)
    assert "junior" not in screen.text

    # 8. Админ-чат
    await press(bot, db, OWNER, "owner", screen, "adm", CHAT)
    assert "по желанию" in screen.text or "не привязан" in screen.text
    call = await press(bot, db, MOD, "mod", mod_screen, "admcode", CHAT)
    assert call.toasts[-1][1], "код админ-чата выдаётся только владельцу"
    await press(bot, db, OWNER, "owner", screen, "admcode", CHAT)
    code = re.search(r"бот админ чат ([0-9a-f]{8})", screen.text).group(1)
    async with db.execute("SELECT main_chat_id FROM chat_bind_tokens WHERE token = ?", (code,)) as cur:
        assert (await cur.fetchone())[0] == CHAT
    await press(bot, db, OWNER, "owner", screen, "admcode", CHAT)   # новый код заменяет прежний
    code2 = re.search(r"бот админ чат ([0-9a-f]{8})", screen.text).group(1)
    async with db.execute("SELECT COUNT(*) FROM chat_bind_tokens WHERE main_chat_id = ?", (CHAT,)) as cur:
        assert (await cur.fetchone())[0] == 1 and code != code2
    # Код действительно привязывает админ-чат (тот же путь, что и «бот привязать админ чат»)
    from bot.chat.admin_chat import cmd_bind_start
    from bot.chat.framework import Ctx, registry
    bot.titles[-2001] = "Админы"
    bot.admins[-2001] = [creator(OWNER, "owner")]
    await ranks.sync_owner(db, bot, -2001, force=True)
    admin_msg = FakeMessage(f"бот админ чат {code2}", OWNER, "owner", -2001, "supergroup")
    await cmd_bind_start(Ctx(admin_msg, bot, db, registry.get("привязать админ чат"), code2, True))
    assert "стал админ-чатом" in admin_msg.replies[-1][0], admin_msg.replies
    await press(bot, db, OWNER, "owner", screen, "chat", CHAT)
    assert "✅ 5. Админ-чат «Админы»" in screen.text and "✅ 4. Модераторы: назначены 2" in screen.text and "Всё настроено" in screen.text, screen.text

    # 9. Чужой человек и кнопки
    stranger = FakeMessage(f"/start setup_{CHAT}", STRANGER, "stranger", STRANGER, "private")
    bot.started.add(STRANGER)
    await cmd_start(stranger, SimpleNamespace(args=f"setup_{CHAT}"), db, bot)
    assert "Настраивать чат могут" in stranger.replies[-1][0]
    other = FakeCbMessage(STRANGER, "private")
    await press(bot, db, STRANGER, "stranger", other, "staffok", CHAT)
    assert "Настраивать чат могут" in other.text and await ranks.get_rank(db, CHAT, COSMETIC) == 0
    # Telegram-администратор без ранга и не добавлявший бота может открыть настройку (но не раздавать ранги)
    cos = FakeMessage(f"/start setup_{CHAT}", COSMETIC, "cosmetic", COSMETIC, "private")
    await cmd_start(cos, SimpleNamespace(args=f"setup_{CHAT}"), db, bot)
    assert "Моя группа" in cos.replies[-1][0]
    # Кривая ссылка: главный экран, а не ошибка
    bad = FakeMessage("/start setup_abc", OWNER, "owner", OWNER, "private")
    await cmd_start(bad, SimpleNamespace(args="setup_abc"), db, bot)
    assert "Подключение занимает" in bad.replies[-1][0]

    # 10. «бот настройка» и /setup
    group_cmd = FakeMessage("бот настройка", OWNER, "owner", CHAT, "supergroup")
    await ob.cmd_setup(Ctx(group_cmd, bot, db, registry.get("настройка"), "", True))
    assert "Бот подключён и отвечает" in group_cmd.replies[-1][0]
    dm_cmd = FakeMessage("/setup", OWNER, "owner", OWNER, "private")
    await ob.slash_setup(dm_cmd, bot, db)
    text, kb = dm_cmd.replies[-1]
    assert "Мои чаты" in text and find(kb, "Моя группа").text.startswith("✅") and find(kb, "Моя группа").callback_data == f"onb:chat:{CHAT}"
    assert len([b for b in buttons(kb) if b.callback_data and b.callback_data.startswith("onb:chat:")]) == 1, \
        "админ-чат в списке настраиваемых чатов не показываем"
    empty = FakeMessage("/setup", STRANGER, "stranger", STRANGER, "private")
    await ob.slash_setup(empty, bot, db)
    assert "Пока не вижу чатов" in empty.replies[-1][0] and find(empty.replies[-1][1], "Добавить").url.startswith("https://t.me/")

    # 11. Права сняли: сообщение в чате снова просит их выдать, воронка запоминает
    bot.set_rights(CHAT, "administrator", delete=True, restrict=False)
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "administrator", "administrator", delete=True, restrict=False), bot, db)
    edited = [t for c, _, t in bot.edits if c == CHAT][-1]
    assert "❌ Блокировка пользователей" in edited and "Бот подключён" not in edited and "Права получены" not in edited
    assert (await cs.get(db, CHAT))["rights_ok_at"] is None
    kinds = [e[0] for e in await events(db, CHAT)]
    assert "rights_lost" in kinds and kinds.count("rights_ok") == 1 and "staff_applied" in kinds and "admin_chat_code" in kinds
    assert "denied" in kinds and "rights_help" in kinds and "trouble" in kinds
    # вернули — и снова сообщили владельцу
    bot.set_rights(CHAT, "administrator", delete=True, restrict=True)
    dms = bot.count_to(OWNER)
    await members.on_bot_membership(member_event(CHAT, user(OWNER, "owner"), "administrator", "administrator", delete=True, restrict=True), bot, db)
    assert bot.count_to(OWNER) == dms + 1


def RIGHT_ALL(text: str) -> bool:
    return "Удаление сообщений" in text and "Блокировка пользователей" in text


async def journey_ready_at_once(db, bot):
    """Добавили сразу администратором с нужными правами (кнопка «Добавить» просит их сама): лишних шагов нет."""
    from bot.chat import members
    from services import chat_setup as cs
    bot.titles[CHAT2] = "Сразу готовая"
    bot.admins[CHAT2] = [creator(OWNER, "owner")]
    bot.set_rights(CHAT2, "administrator", delete=True, restrict=True)
    await members.on_bot_membership(member_event(CHAT2, user(OWNER, "owner"), "left", "administrator", True, True, "Сразу готовая"), bot, db)
    text = bot.last_to(CHAT2)
    assert "Права получены" in text and "Последний шаг" in text and "Добавить администратора" not in text, text
    assert (await cs.get(db, CHAT2))["rights_ok_at"] is not None
    assert [e[0] for e in await events(db, CHAT2)] == ["added", "rights_ok", "dm_sent"], await events(db, CHAT2)
    # Вышел из чата — и снова добавили: приветствие отправляется заново
    await members.on_bot_membership(member_event(CHAT2, user(OWNER, "owner"), "administrator", "left", title="Сразу готовая"), bot, db)
    assert (await cs.get(db, CHAT2))["left_at"] is not None
    n = bot.count_to(CHAT2)
    bot.set_rights(CHAT2, "member")
    await members.on_bot_membership(member_event(CHAT2, user(OWNER, "owner"), "left", "member", title="Сразу готовая"), bot, db)
    assert bot.count_to(CHAT2) == n + 1 and "❌ Я администратор" in bot.last_to(CHAT2)
    rec = await cs.get(db, CHAT2)
    assert rec["left_at"] is None and rec["rights_ok_at"] is None and rec["reminders"] == 0
    # Дубль события входа в ту же минуту приветствие не повторяет
    await members.on_bot_membership(member_event(CHAT2, user(OWNER, "owner"), "left", "member", title="Сразу готовая"), bot, db)
    assert bot.count_to(CHAT2) == n + 1


async def journey_edge_cases(db, bot):
    from bot.chat import members, onboarding as ob
    from bot.chat.payments import cmd_start
    from services import chat_setup as cs
    # Бот не может писать в чат: приветствие не дошло, но владелец получает всё в личке
    bot.titles[CHAT3] = "Тихая группа"
    bot.admins[CHAT3] = [creator(OWNER, "owner")]
    bot.set_rights(CHAT3, "member")
    bot.cannot_write.add(CHAT3)
    n = bot.count_to(OWNER)
    await members.on_bot_membership(member_event(CHAT3, user(OWNER, "owner"), "left", "member", title="Тихая группа"), bot, db)
    kinds = [e[0] for e in await events(db, CHAT3)]
    assert kinds == ["added", "welcome_failed", "dm_sent"], kinds
    assert bot.count_to(OWNER) == n + 1 and "Тихая группа" in bot.last_to(OWNER)
    bot.cannot_write.discard(CHAT3)
    # Telegram не отвечает про чат: берём запомненное и честно предупреждаем
    s = await cs.inspect(FakeBot(), db, CHAT3)
    assert not s.live and s.present and "Telegram сейчас не ответил" in ob.chat_screen(s, BOT_NAME)[0]
    # Обычная группа (не супергруппа): подсказка про теги
    bot.chat_types[CHAT3] = "group"
    s = await cs.inspect(bot, db, CHAT3)
    assert not s.supergroup and "обычная группа" in ob.group_screen(s, BOT_NAME)[0]
    bot.chat_types[CHAT3] = "supergroup"
    # /start в группе у давно подключённого чата: приветствие заново не отправляется, а случайный участник хозяином не становится
    await db.execute("UPDATE chat_onboarding SET added_at = NOW() - INTERVAL '2 hours', left_at = NULL WHERE chat_id = ?", (CHAT3,))
    await db.commit()
    n = bot.count_to(CHAT3)
    start = FakeMessage("/start", STRANGER, "stranger", CHAT3, "supergroup")
    await cmd_start(start, SimpleNamespace(args=None), db, bot)
    assert start.replies and "Я Предвестник" in start.replies[-1][0] and bot.count_to(CHAT3) == n
    assert (await cs.get(db, CHAT3))["inviter_id"] == OWNER
    await db.execute("UPDATE chat_onboarding SET added_at = NOW() WHERE chat_id = ?", (CHAT3,))   # дальше проверяются напоминания
    await db.commit()
    # Чат без записи (подключён до обновления) + /start от случайного участника: общий чек-лист в чате, личку никто не получает
    fresh = -4001
    bot.titles[fresh] = "Давний чат"
    bot.admins[fresh] = [creator(OWNER, "owner")]
    bot.set_rights(fresh, "member")
    dms = bot.count_to(STRANGER)
    start = FakeMessage("/start", STRANGER, "stranger", fresh, "supergroup")
    await cmd_start(start, SimpleNamespace(args=None), db, bot)
    assert bot.count_to(fresh) == 1 and bot.count_to(STRANGER) == dms and (await cs.get(db, fresh))["inviter_id"] is None
    # А если /start написал администратор, он становится хозяином подключения и получает личное сообщение
    bot.admins[-4002] = [creator(OWNER, "owner")]
    bot.titles[-4002] = "Другой чат"
    bot.set_rights(-4002, "member")
    start = FakeMessage("/start", OWNER, "owner", -4002, "supergroup")
    await cmd_start(start, SimpleNamespace(args=None), db, bot)
    assert (await cs.get(db, -4002))["inviter_id"] == OWNER and "Другой чат" in bot.last_to(OWNER)
    # Чат, о котором бот ничего не знает (подключён до обновления): «бот настройка» работает и не заводит записей
    old = -1999
    bot.titles[old] = "Старый чат"
    bot.set_rights(old, "administrator", delete=True, restrict=True)
    msg = FakeMessage("/setup", OWNER, "owner", old, "supergroup")
    await ob.slash_setup(msg, bot, db)
    assert "Бот подключён и отвечает" in msg.replies[-1][0] and await cs.get(db, old) is None   # подключён до мастера: проверять нечего
    # Событие по чату без записи (права поменяли у старого чата): тихо, без сообщений
    n = bot.count_to(old)
    await members.on_bot_membership(member_event(old, user(OWNER, "owner"), "member", "administrator", True, True, "Старый чат"), bot, db)
    assert bot.count_to(old) == n and await cs.get(db, old) is None
    # Бот в канале или личке этим не занимается
    await ob.on_bot_change(SimpleNamespace(chat=SimpleNamespace(id=-3, type="channel"), old_chat_member=SimpleNamespace(status="left"),
                                           new_chat_member=SimpleNamespace(status="restricted"), from_user=None), bot, db)


async def reminders(db, bot):
    from bot.chat import members, onboarding as ob
    from services import chat_setup as cs
    chat, quiet = -3001, -3002
    for c, title in ((chat, "Забывчивые"), (quiet, "Молчаливые")):
        bot.titles[c] = title
        bot.admins[c] = [creator(6001 if c == chat else 6002, "o" + str(abs(c)))]
        bot.set_rights(c, "member")
    bot.started.add(6001)
    await members.on_bot_membership(member_event(chat, user(6001, "o3001"), "left", "member", title="Забывчивые"), bot, db)
    await members.on_bot_membership(member_event(quiet, user(6002, "o3002"), "left", "member", title="Молчаливые"), bot, db)
    assert await ob.send_reminders(bot, db) == 0   # час ещё не прошёл
    for c in (chat, quiet):
        await db.execute("UPDATE chat_onboarding SET added_at = NOW() - INTERVAL '2 hours' WHERE chat_id = ?", (c,))
    await db.commit()
    n_chat = bot.count_to(quiet)
    assert await ob.send_reminders(bot, db) == 2
    assert "⏰" in bot.last_to(6001) and "Забывчивые" in bot.last_to(6001) and "Как выдать права" in str([kw for c, _, kw in bot.sent if c == 6001][-1]["reply_markup"])
    assert bot.count_to(quiet) == n_chat + 1 and bot.last_to(quiet).startswith("⏰ "), "личка закрыта: один раз напоминаем прямо в чате"
    assert "Мне всё ещё не хватает прав" in bot.last_to(quiet) and "Я Предвестник" not in bot.last_to(quiet)
    assert await ob.send_reminders(bot, db) == 0   # второй раз то же самое не шлётся
    # Через сутки последнее напоминание; в чат, если личка закрыта, больше не пишем
    for c in (chat, quiet):
        await db.execute("UPDATE chat_onboarding SET added_at = NOW() - INTERVAL '26 hours' WHERE chat_id = ?", (c,))
    await db.commit()
    n_chat = bot.count_to(quiet)
    assert await ob.send_reminders(bot, db) == 2
    assert "Последнее напоминание" in bot.last_to(6001) and bot.count_to(quiet) == n_chat
    assert await ob.send_reminders(bot, db) == 0   # больше двух напоминаний не бывает
    async with db.execute("SELECT reminders FROM chat_onboarding WHERE chat_id IN (?, ?)", (chat, quiet)) as cur:
        assert [r[0] for r in await cur.fetchall()] == [2, 2]
    # Права выдали, а событие потерялось: напоминания не будет, статус догоняется сам
    third = -3003
    bot.titles[third] = "Потерянное событие"
    bot.admins[third] = [creator(6001, "o3001")]
    bot.set_rights(third, "member")
    await members.on_bot_membership(member_event(third, user(6001, "o3001"), "left", "member", title="Потерянное событие"), bot, db)
    bot.set_rights(third, "administrator", delete=True, restrict=True)   # события нет
    await db.execute("UPDATE chat_onboarding SET added_at = NOW() - INTERVAL '2 hours' WHERE chat_id = ?", (third,))
    await db.commit()
    n = bot.count_to(6001)
    await ob.send_reminders(bot, db)
    assert (await cs.get(db, third))["rights_ok_at"] is not None and "⏰" not in (bot.last_to(6001) or "")
    assert bot.count_to(6001) == n + 1 and "Права получены" in bot.last_to(6001)   # владельцу сказали, что всё в порядке
    # Бота убрали тихо: напоминать нечего
    gone = -3004
    bot.titles[gone] = "Убрали"
    bot.admins[gone] = [creator(6001, "o3001")]
    bot.set_rights(gone, "member")
    await members.on_bot_membership(member_event(gone, user(6001, "o3001"), "left", "member", title="Убрали"), bot, db)
    del bot.rights[gone]
    await db.execute("UPDATE chat_settings SET bot_left_at = NOW() WHERE chat_id = ?", (gone,))
    await db.execute("UPDATE chat_onboarding SET added_at = NOW() - INTERVAL '2 hours' WHERE chat_id = ?", (gone,))
    await db.commit()
    n = bot.count_to(6001)
    await ob.send_reminders(bot, db)
    assert bot.count_to(6001) == n and (await cs.get(db, gone))["left_at"] is not None


async def funnel_and_migration(db, bot):
    from bot.chat.migration import migrate_chat
    from services import chat_setup as cs
    f = await cs.funnel(db, 7)
    assert f["added"] >= 6 and 0 < f["ready"] < f["added"] and f["waiting"] >= 1, f
    by_event = {e["event"]: e for e in f["events"]}
    for key in ("added", "dm_sent", "dm_failed", "rights_help", "trouble", "check", "rights_ok", "rights_lost", "staff_preview",
                "staff_applied", "admin_chat_code", "reminder", "left"):
        assert key in by_event and by_event[key]["count"] >= 1 and by_event[key]["title"], (key, by_event.keys())
    assert all(item["title"] and item["id"] < 0 for item in f["stuck"]) and f["stuck"], f["stuck"]
    assert all(item["inviter"] is None or item["inviter"]["id"] for item in f["stuck"])
    assert (await cs.funnel(db, -5))["days"] == 1 and (await cs.funnel(db, 9999))["days"] == 90 and (await cs.funnel(db, 0))["days"] == 7
    # Группа стала супергруппой: запись подключения переезжает на новый ID
    await migrate_chat(db, CHAT3, -100999)
    assert await cs.get(db, CHAT3) is None and (await cs.get(db, -100999)) is not None


async def entry_points(db, bot):
    """Что видит человек, который просто написал боту, и как это совпадает с остальными подсказками."""
    from bot.chat.payments import cmd_start
    dm = FakeMessage("/start", 8001, "newbie", 8001, "private")
    await cmd_start(dm, SimpleNamespace(args=None), db, bot)
    text, kb = dm.replies[-1]
    assert "Предвестник" in text and "Подключение занимает" in text, text
    add = find(kb, "Добавить бота в чат")
    assert add.url == f"https://t.me/{BOT_NAME}?startgroup=setup&admin=delete_messages+restrict_members"
    assert buttons(kb)[0] is add   # главное действие — первой кнопкой
    assert find(kb, "Мой чат").callback_data == "onb:my:0" and find(kb, "Что умеет бот").callback_data == "onb:guide:0"
    assert find(kb, "Как подключить").callback_data == "onb:add:0" and find(kb, "Я просто играю").callback_data == "onb:play:0"
    # Приветствие картинкой — один раз, повторный /start не засыпает картинками
    bot.photos = [p for p in bot.photos if p[0] == 8001]
    assert len(bot.photos) == 1 and bot.photos[0][2] is None, bot.photos
    await cmd_start(FakeMessage("/start", 8001, "newbie", 8001, "private"), SimpleNamespace(args=None), db, bot)
    assert len(bot.photos) == 1
    # «Как подключить»: первый раз — картинка «3 шага» с подписью и кнопками, второй — обычный экран
    screen = FakeCbMessage(8001, "private")
    await press(bot, db, 8001, "newbie", screen, "add")
    _, photo, caption, pkb = bot.photos[-1]
    assert len(bot.photos) == 2 and "Как подключить" in caption and find(pkb, "Выбрать чат").url == add.url
    assert find(pkb, "Я уже добавил").callback_data == "onb:my:0" and not screen.edited
    from bot.chat import onboarding as ob
    assert ob._photo_ids["steps"] == "photo-" + str(bot._next)   # второй показ уйдёт по file_id, без новой загрузки
    photo_msg = FakeCbMessage(8001, "private")
    photo_msg.photo = [SimpleNamespace(file_id="x")]
    call = await press(bot, db, 8001, "newbie", photo_msg, "my")   # кнопка под картинкой: следующий экран новым сообщением
    assert not photo_msg.edited and call.toasts and "Мои чаты" in photo_msg.answers[-1][0]
    await press(bot, db, 8001, "newbie", screen, "add")
    assert "Выбрать чат" in screen.text and "Удаление сообщений" in screen.text and len(bot.photos) == 2
    # «Я просто играю»: тур по сайту картинкой, потом текстом; кнопка сайта и путь в свой чат
    await press(bot, db, 8001, "newbie", screen, "play")
    assert len(bot.photos) == 3 and "Как играть" in bot.photos[-1][2] and find(bot.photos[-1][3], "Добавить бота")
    await press(bot, db, 8001, "newbie", screen, "play")
    assert "Как играть" in screen.text and find(screen.edited[-1][1], "Назад").callback_data == "onb:home:0"
    # Написал в личку «привет»: команды нет, бот не молчит, но и не повторяет меню каждые пять секунд
    from bot.chat import registry as reg
    from bot.chat.framework import Parsed, dispatch as disp, parse
    hello = FakeMessage("привет", 8002, "hello", 8002, "private")
    assert not await disp(reg, hello, bot, db)
    await ob.dm_hint(hello, bot, db)
    text, kb = hello.replies[-1]
    assert "Привет" in text and find(kb, "Добавить бота в чат") and find(kb, "Как подключить")
    for example in re.findall(r"<code>(бот [^<]+)</code>", text):   # пример в подсказке — настоящая команда
        assert isinstance(parse(reg, example, BOT_NAME, True), Parsed), example
    await ob.dm_hint(hello, bot, db)
    assert len(hello.replies) == 1
    photo_only = FakeMessage(None, 8003, "pic", 8003, "private")
    await ob.dm_hint(photo_only, bot, db)
    assert not photo_only.replies   # фото, оплаты и служебные сообщения подсказку не вызывают
    await press(bot, db, 8001, "newbie", screen, "guide")
    assert "Что я умею" in screen.text and find(screen.edited[-1][1], "Назад").callback_data == "onb:home:0"
    await press(bot, db, 8001, "newbie", screen, "home")
    assert "Подключение занимает" in screen.text
    # Справка бота знает про «бот настройка»
    from bot.chat import help as help_mod
    assert "настройка" in {c.name for c in help_mod._by_section(True)["basic"]}   # и в личке, и в чате справка её показывает
    assert "настройка" in {c.name for c in help_mod._by_section(False)["basic"]}
    # Команда для чата, набранная в личке: не тупик, а кнопка «добавить бота»
    from bot.chat import registry
    from bot.chat.framework import dispatch
    dm = FakeMessage("бот мут @x", 8001, "newbie", 8001, "private")
    assert await dispatch(registry, dm, bot, db)
    text, kb = dm.replies[-1]
    assert "только в группе" in text and find(kb, "Добавить бота").url.endswith("admin=delete_messages+restrict_members")




async def newbie_traps(db, bot):
    """Места, где новичок молча застревал: админ пишет анонимно, бота добавили в канал, админ чата не видит свой чат."""
    from bot.chat import members, onboarding as ob, registry
    from bot.chat.framework import ANON_HINT, dispatch
    from services import chat_setup as cs

    # Администратор пишет «от имени чата»: вместо «нет права» ему объясняют про «Анонимность» (один раз в час в журнал)
    async def say(text, uid=OWNER, name="owner", sender_chat=None):
        m = FakeMessage(text, uid, name, CHAT, "supergroup")
        m.sender_chat = sender_chat
        assert await dispatch(registry, m, bot, db)
        return " | ".join(t for t, _ in m.replies)
    anon = await say("бот ранги", uid=1087968824, name="GroupAnonymousBot")
    assert "Вы пишете анонимно" in anon and "Анонимность" in anon and "Состав чата" not in anon, anon
    anon = await say("бот чистка, 10", sender_chat=SimpleNamespace(id=CHAT))
    assert "Вы пишете анонимно" in anon, anon
    assert [e[0] for e in await events(db, CHAT)].count("anon_hint") == 1
    assert "Состав чата" in await say("бот ранги")                                  # обычный администратор — без подсказки
    assert ANON_HINT.split("\n")[0] not in await say("бот помощь", uid=1087968824, name="GroupAnonymousBot")   # справке имя не нужно

    # Бота добавили в канал: каналы он не ведёт, человек узнаёт об этом сразу, записи о подключении нет
    n = bot.count_to(OWNER)
    await members.on_bot_membership(member_event(-5000, user(OWNER, "owner"), "left", "administrator", title="Мой канал", chat_type="channel"), bot, db)
    text = bot.last_to(OWNER)
    assert bot.count_to(OWNER) == n + 1 and "Мой канал" in text and "Каналы я не веду" in text, text
    assert await cs.get(db, -5000) is None and bot.count_to(-5000) == 0
    assert "channel_added" in [e[0] for e in await events(db, -5000)]
    # Не запускал бота: написать нельзя, это не ошибка
    await members.on_bot_membership(member_event(-5001, user(8888, "newbie"), "left", "administrator", title="Другой канал", chat_type="channel"), bot, db)
    assert "dm_failed" in [e[0] for e in await events(db, -5001)]

    # Telegram-администратор чата, которого бота добавлял не он: свой чат видит в «Мои чаты» (ранга в боте у него нет)
    for uid in (COSMETIC, STRANGER):
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, FALSE) ON CONFLICT DO NOTHING", (uid, CHAT))
    await db.commit()
    assert not [c for c in await cs.my_chats(db, COSMETIC) if c["id"] == CHAT]
    mine = [c for c in await cs.my_chats(db, COSMETIC, bot=bot) if c["id"] == CHAT]
    assert mine and mine[0]["title"] == "Моя группа", mine
    assert not [c for c in await cs.my_chats(db, STRANGER, bot=bot) if c["id"] == CHAT]   # обычный участник не видит чужую настройку
    text, kb = ob.my_screen([{"id": CHAT, "title": "Чат", "admin": True, "ready": False}], BOT_NAME)
    assert find(kb, "Чат").text == "⚠️ Чат · нужны права", find(kb, "Чат").text

    # Воронка называет новые шаги по-человечески
    funnel = await cs.funnel(db, 7)
    titles = {e["event"]: e["title"] for e in funnel["events"]}
    for key in ("first_command", "anon_hint", "channel_added", "denied"):
        assert titles.get(key) and titles[key] != key, (key, titles)


asyncio.run(main())
