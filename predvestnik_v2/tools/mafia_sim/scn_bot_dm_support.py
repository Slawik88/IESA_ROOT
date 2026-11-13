"""Whole-bot scenarios (S23b): solo word game in the DM, tickets to the administration with an answer in the DM,
report-card buttons for the staff, the morning plan notification.

Rights are checked through the same code as the admin panel, so the scenarios also prove the buttons do not open more doors:
a helper below the needed role is refused, a stranger is refused, a second tap on a closed report does nothing."""
from __future__ import annotations

import re
from datetime import timedelta

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_dm_push import at, consent, database, deliver, player, to_player
from tools.mafia_sim.scn_bot_util import last_message, said, say


async def set_rank(user, rank: int) -> None:
    async with database() as db:
        await db.execute("UPDATE users SET bot_rank = ? WHERE user_tg_id = ?", (rank, user.id))
        await db.commit()


# ── words: one player against the bot, in the DM ────────────────────────────

def next_letter(text: str) -> str:
    found = re.search(r"Теперь тебе на (\S)", text)
    ok(found, f"the prompt names the next letter: {text[:200]!r}")
    return found.group(1).lower()


def word_for(letter: str, used: set[str]) -> str:
    from core import word_chain as rules
    for word in rules.COMMON_WORDS:
        if word.startswith(letter) and word not in used:
            return word
    raise AssertionError(f"no common word on {letter!r}")


async def let_time_pass(user, *, seconds: int = 60, round_age_minutes: int = 0) -> None:
    """The player's earlier moves are older (the 3-second pause between own moves has passed)."""
    async with database() as db:
        await db.execute("UPDATE word_chain_moves SET created_at = created_at - make_interval(secs => ?) WHERE user_id = ?", (seconds, user.id))
        if round_age_minutes:
            await db.execute("UPDATE word_chain_rounds SET updated_at = updated_at - make_interval(mins => ?) WHERE chat_id = ? AND status = 'active'",
                             (round_age_minutes, user.id))
        await db.commit()


@bot_scenario(volatile=True)
async def dm_words_one_player_against_the_bot(h: Harness) -> None:
    user = await player(h, "Игрок слов", write=False)
    start = await say(h, user, user.id, "слова")
    text = said(start)
    ok("Просто напиши слово" in text and "бот слово, СЛОВО" not in text, f"in the DM the move is just a word: {text[:240]!r}")
    letter, used = next_letter(text), set()
    first = word_for(letter, used)
    reply = said(await say(h, user, user.id, first))                 # a plain word, no command
    ok("Твоё" in reply and first in reply, f"a plain word is a move: {reply[:200]!r}")
    letter = next_letter(reply)
    used |= {first}
    await let_time_pass(user)
    prompt = last_message(h, user.id, "Теперь тебе на")
    second = word_for(letter, used)
    reply = said(await say(h, user, user.id, second, reply_to=prompt))   # an answer to the bot's message works too
    ok("Твоё" in reply and second in reply, f"a reply to the game message is a move: {reply[:200]!r}")
    letter = next_letter(reply)
    used |= {second}
    await let_time_pass(user)
    wrong = "арбуз" if letter != "а" else "бабочка"
    reply = said(await say(h, user, user.id, wrong))
    ok("Сейчас нужно слово на" in reply, f"a word on the wrong letter is refused with the right letter: {reply[:200]!r}")
    balance = said(await say(h, user, user.id, "баланс"))
    ok("🔤" not in balance and balance, f"a command name is a command, not a move, while the game runs: {balance[:120]!r}")
    chatter = said(await say(h, user, user.id, "привет, как дела?"))
    ok("Сейчас нужно слово" not in chatter and "Твоё" not in chatter, f"a phrase is not a move: {chatter[:120]!r}")
    help_text = said(await say(h, user, user.id, "бот слова правила"))
    ok("Слова один на один" in help_text and "<code>" not in help_text, f"the DM has its own help: {help_text[:120]!r}")
    score = said(await say(h, user, user.id, "бот слова счёт"))
    ok("Счёт этой партии" in score and "Игрок слов" in score, f"the score shows the one player: {score[:200]!r}")
    await let_time_pass(user, round_age_minutes=11)
    stale = said(await say(h, user, user.id, word_for(letter, used)))
    ok("Твоё" not in stale and "Сейчас нужно слово" not in stale, f"after 10 minutes of silence a bare word is only a word: {stale[:120]!r}")
    prompt = last_message(h, user.id, "Теперь тебе на")
    reply = said(await say(h, user, user.id, word_for(letter, used), reply_to=prompt))
    ok("Твоё" in reply, f"but an answer to the game message still works within the day: {reply[:120]!r}")
    stop = said(await say(h, user, user.id, "бот слова стоп"))
    ok("Партия завершена" in stop, f"the player ends his own game: {stop[:120]!r}")
    after = said(await say(h, user, user.id, "арбуз"))
    ok("Твоё" not in after, f"with no game running a word does nothing special: {after[:120]!r}")
    other = await player(h, "Другой игрок", write=False)
    ok("Игра сейчас не идёт" in said(await say(h, other, other.id, "бот слова счёт")), "another player's DM is another game")
    group_user = await player(h, "Из группы слов", write=False)
    group = h.new_chat([group_user])
    started = said(await say(h, group_user, group, "бот слова"))
    ok("бот слово, СЛОВО" in started, f"the group game still teaches the group way: {started[:200]!r}")


# ── tickets to the administration ───────────────────────────────────────────

@bot_scenario
async def dm_ticket_reaches_staff_and_the_answer_reaches_the_player(h: Harness) -> None:
    from infrastructure.repositories import dm_tickets as tickets_repo
    asker = await player(h, "Спрашивающий")
    helper = await player(h, "Хелпер обращений")
    senior = await player(h, "Старший обращений")
    junior = await player(h, "Тестер")
    stranger = await player(h, "Посторонний")
    await set_rank(helper, 2)
    await set_rank(senior, 4)
    await set_rank(junior, 1)
    async with database() as db:
        await db.execute("DELETE FROM dm_tickets WHERE user_id = ?", (asker.id,))
        await db.commit()
    ok("Напиши вопрос" in said(await say(h, asker, asker.id, "бот обращение")), "no text: the player is shown how to write")
    ok("подробнее" in said(await say(h, asker, asker.id, "бот обращение коротко")), "one word is not a ticket")
    in_group = h.new_chat([asker])
    ok("в личке" in said(await say(h, asker, in_group, "бот обращение не пришла награда")), "in a group the player is sent to the DM")
    start = len(h.world.calls)
    accepted = said(await say(h, asker, asker.id, "бот обращение не пришла награда за задание дня"))
    ok("Обращение №" in accepted and "принято" in accepted, f"the ticket is accepted: {accepted[:160]!r}")
    cards = [p for n, p in h.world.calls[start:] if n == "SendMessage" and "Обращение №" in str(p.get("text")) and int(p["chat_id"]) != asker.id]
    owners = {int(p["chat_id"]) for p in cards}
    ok(helper.id in owners and senior.id in owners, f"both staff members get the card: {owners}")
    ok(junior.id not in owners and stranger.id not in owners, "a tester below the role and a stranger get nothing")
    ok("Спрашивающий" in str(cards[0]["text"]) or f"{asker.id}" in str(cards[0]["text"]), "the card says who asks")
    card = last_message(h, helper.id, "Обращение №")
    await set_rank(helper, 0)
    denied = await h.click(helper, helper.id, card, "Ответить")
    ok(denied.alert and "персоналу" in denied.text, f"after losing the role the button is refused: {denied.text!r}")
    await set_rank(helper, 2)
    click = await h.click(helper, helper.id, card, "Ответить")
    prompt = last_message(h, helper.id, "Ответ на обращение №")
    ok(not click.alert and prompt.buttons() == [], "«Ответить» asks for the answer text")
    start = len(h.world.calls)
    await h.say(helper, helper.id, "Награду выдали, проверь профиль.", reply_to=prompt)
    got = to_player(h, asker, start)
    ok(got and "Ответ администрации" in str(got[0]["text"]) and "Награду выдали" in str(got[0]["text"]), f"the player gets the answer: {got[:1]}")
    ok(any("отправлен" in str(p.get("text")) for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == helper.id), "the staff member is told it went")
    await h.say(senior, senior.id, "Я тоже отвечу", reply_to=last_message(h, senior.id, "Обращение №"))   # a reply to the card itself is not an answer
    start = len(h.world.calls)
    late = await h.click(senior, senior.id, last_message(h, senior.id, "Обращение №"), "Закрыть")
    ok(late.alert and "уже закрыто" in late.text, f"a colleague who is late is told so: {late.text!r}")
    again = len(h.world.calls)
    await h.say(senior, senior.id, "Второй ответ", reply_to=prompt)
    ok(not to_player(h, asker, again) and any("уже закрыто" in str(p.get("text")) for n, p in h.world.calls[again:] if n == "SendMessage"), "a second answer to the same ticket goes nowhere")
    async with database() as db:
        async with db.execute("SELECT action FROM bot_admin_actions WHERE user_id = ? AND action LIKE 'ticket_%' ORDER BY id", (asker.id,)) as c:
            actions = [r[0] for r in await c.fetchall()]
        ok(actions == ["ticket_answered"], f"the answer is in the admin journal: {actions}")
    second = said(await say(h, asker, asker.id, "бот обращение и ещё один вопрос про питомцев"))
    ok("принято" in second, "a second ticket is fine")
    third = said(await say(h, asker, asker.id, "бот обращение и третий вопрос про биржу монет"))
    ok("принято" in third, "two waiting tickets are the limit; the answered one does not count")
    fourth = said(await say(h, asker, asker.id, "бот обращение и четвёртый вопрос про магазин"))
    ok("Два твоих обращения уже ждут ответа" in fourth, f"too many waiting at once: {fourth[:120]!r}")
    listing = await say(h, senior, senior.id, "бот обращения")
    ok("Ждут ответа: 2" in said(listing), f"staff sees what waits: {said(listing)[:160]!r}")
    ok("только для персонала" in said(await say(h, stranger, stranger.id, "бот обращения")), "a stranger does not see the list")
    close_card = last_message(h, senior.id, "третий вопрос")
    start = len(h.world.calls)
    closed = await h.click(senior, senior.id, close_card, "Закрыть")
    ok(not closed.alert, f"close without an answer works: {closed.text!r}")
    ok(any("закрыто" in str(p.get("text")) for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == asker.id), "the player is told the ticket was closed")
    after = last_message(h, senior.id, "третий вопрос")
    ok("Закрыто без ответа" in after.text and after.buttons() == [], f"the card shows the result and loses its buttons: {after.text[:160]!r}")
    async with database() as db:
        ok((await tickets_repo.counts_for(db, asker.id))[1] == 1, "one ticket still waits")
        await db.execute("UPDATE dm_tickets SET status = 'closed' WHERE user_id = ?", (asker.id,))
        await db.commit()
    daily = said(await say(h, asker, asker.id, "бот обращение и последний вопрос за сегодня"))
    ok("Не больше 3 обращений в сутки" in daily, f"three a day, answered or not: {daily[:140]!r}")
    lonely = await player(h, "Спрашивающий в пустоту")
    saved = set(h.world.dm_open)
    h.world.dm_open.clear()
    h.world.dm_open.add(lonely.id)                      # no staff member has opened the DM with the bot
    try:
        said_to_lonely = said(await say(h, lonely, lonely.id, "бот обращение и вопрос, когда никого нет на связи"))
    finally:
        h.world.dm_open.update(saved)
    ok("никого из администрации нет на связи" in said_to_lonely, f"the player is told the truth when no card could be delivered: {said_to_lonely[:160]!r}")
    long_ticket = said(await say(h, senior, senior.id, "бот обращения"))
    ok("Ждут ответа" in long_ticket, "and the ticket is kept in the staff list")


def labels(message) -> list[str]:
    return [b["text"] for b in message.buttons()]


@bot_scenario
async def dm_ticket_flood_limits_cards_and_the_list_has_pages(h: Harness) -> None:
    """S23d: a flood of tickets does not bury a staff member in cards (CARDS_PER_HOUR an hour, the last one says so), nothing is lost,
    and «бот обращения» pages through everything that waits, oldest first."""
    from core import dm_tickets as rules
    from infrastructure.repositories import dm_tickets as tickets_repo
    from services import dm_tickets as tickets_service
    staff = await player(h, "Дежурный по обращениям")
    asker = await player(h, "Спрашивающий в час пик")
    late = await player(h, "Опоздавший в час пик")
    await set_rank(staff, 2)
    flood: list[int] = []
    try:
        async with database() as db:
            await db.execute("UPDATE dm_tickets SET status = 'closed' WHERE status = 'new'")   # other scenarios' leftovers do not shift the pages
            everyone = await tickets_service.recipients(db)
            ok(staff.id in everyone, f"the new staff member is a recipient: {everyone}")
            for n in range(rules.CARDS_PER_HOUR - 1):        # an hour of cards already behind every recipient but one slot
                flood.append(await tickets_repo.add(db, 9_000_000 + n, f"обращение из потока номер {n:02d}"))
                for staff_id in everyone:
                    await db.execute("INSERT INTO dm_ticket_cards (ticket_id, staff_id) VALUES (?, ?)", (flood[-1], staff_id))
            await db.commit()
        start = len(h.world.calls)
        accepted = said(await say(h, asker, asker.id, "бот обращение награда за сундук не пришла"))
        ok("принято" in accepted and "Ответ придёт сюда" in accepted and "очереди" not in accepted, f"the last free card still goes out: {accepted[:160]!r}")
        cards = [p for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == staff.id and "Обращение №" in str(p.get("text"))]
        ok(len(cards) == 1 and "восьмая карточка за последний час" in str(cards[0]["text"]), f"the card says it is the last one this hour: {cards[:1]}")
        start = len(h.world.calls)
        queued = said(await say(h, late, late.id, "бот обращение и вопрос, когда у всех полно карточек"))
        ok("принято" in queued and "в очереди" in queued and "нет на связи" not in queued, f"over the limit the player hears it is queued: {queued[:160]!r}")
        ok(not [p for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) in everyone and int(p["chat_id"]) in h.world.dm_open],
           "no staff member gets a card over the limit")
        async with database() as db:
            await db.execute("UPDATE dm_ticket_cards SET sent_at = sent_at - INTERVAL '61 minutes' WHERE staff_id = ?", (staff.id,))
            await db.commit()
        start = len(h.world.calls)
        said(await say(h, late, late.id, "бот обращение второй вопрос через час"))
        ok([p for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == staff.id], "an hour later the cards come again")

        async with database() as db:
            for n in range(3):
                flood.append(await tickets_repo.add(db, 9_100_000 + n, f"обращение из потока номер {rules.CARDS_PER_HOUR + n:02d}"))
            await db.commit()
            total = (await tickets_repo.open_total(db))
        pages = rules.page_count(total)
        ok(pages == 2, f"{total} waiting tickets make two pages")
        start = len(h.world.calls)
        first = said(await say(h, staff, staff.id, "бот обращения"))
        ok(f"Ждут ответа: {total}. Страница 1 из 2, старые первыми." in first, f"the header names the page: {first[:200]!r}")
        shown = [p for n, p in h.world.calls[start:] if n == "SendMessage" and "Обращение №" in str(p.get("text"))]
        ok(len(shown) == rules.LIST_LIMIT and "номер 00" in str(shown[0]["text"]), f"a full page, oldest first: {len(shown)}")
        nav = last_message(h, staff.id, "Это страница 1 из 2")
        ok(labels(nav) == ["Страница 2 ›"], f"page one offers only the next page: {labels(nav)}")
        start = len(h.world.calls)
        await h.click(staff, staff.id, nav, "Страница 2")
        rest = [p for n, p in h.world.calls[start:] if n == "SendMessage" and "Обращение №" in str(p.get("text"))]
        ok(len(rest) == total - rules.LIST_LIMIT, f"page two shows the rest: {len(rest)} of {total}")
        ok(last_message(h, staff.id, "Это страница 1 из 2").buttons() == [], "the old page buttons are gone")
        ok(labels(last_message(h, staff.id, "Это страница 2 из 2")) == ["‹ Страница 1"], "the last page offers the way back")
        typed = said(await say(h, staff, staff.id, "бот обращения 9"))
        ok("Страница 2 из 2" in typed, f"a page past the end shows the last one: {typed[:120]!r}")
        ok("Страница 1 из 2" in said(await say(h, staff, staff.id, "бот обращения ²")), "a non-ASCII digit is page one, not a crash")

        async def broken(*_args, **_kwargs):
            raise RuntimeError("relation dm_ticket_cards does not exist")
        real, tickets_service.reserve_card = tickets_service.reserve_card, broken   # the card table failed to appear on start
        try:
            start = len(h.world.calls)
            fallback = said(await say(h, asker, asker.id, "бот обращение когда учёт карточек сломан"))
        finally:
            tickets_service.reserve_card = real
        ok("принято" in fallback and "очереди" not in fallback, f"without the card table the ticket is still accepted: {fallback[:120]!r}")
        ok([p for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == staff.id], "and the card still reaches the staff")
    finally:
        async with database() as db:
            await db.execute("UPDATE dm_tickets SET status = 'closed' WHERE status = 'new'")
            await db.execute("DELETE FROM dm_tickets WHERE id = ANY(?)", (flood,))
            await db.commit()


# ── buttons under a report card ─────────────────────────────────────────────

async def report_setup(h: Harness, label: str):
    from FastAPI.routers.bot_admin import people
    people.set_bot(h.bot)
    reporter, target = await player(h, f"Жалобщик {label}"), await player(h, f"Нарушитель {label}")
    helper, senior, other = await player(h, f"Хелпер {label}"), await player(h, f"Старший {label}"), await player(h, f"Второй старший {label}")
    for user, rank in ((helper, 2), (senior, 4), (other, 4)):
        await set_rank(user, rank)
    chat = h.new_chat([reporter, target])
    async with database() as db:
        from services import reports
        await reports.ensure_schema(db)
        await reports.save_settings(db, {"dm_staff_rank": 2, "to_admin_chat": False}, senior.id)
        await db.commit()
    return reporter, target, helper, senior, other, chat


async def file_report(h: Harness, reporter, target, chat: int, reason: str):
    await h.say(target, chat, "купите дёшево, переходите по ссылке")   # the offender is known to the chat
    await h.say(reporter, chat, f"бот жалоба, @sim{target.id} {reason}")


async def report_status(rid_text: str) -> str:
    rid = int(re.search(r"№(\d+)", rid_text).group(1))
    async with database() as db:
        async with db.execute("SELECT status FROM bot_reports WHERE id = ?", (rid,)) as c:
            return (await c.fetchone())[0]


@bot_scenario
async def report_card_buttons_use_the_admin_rules(h: Harness) -> None:
    reporter, target, helper, senior, other, chat = await report_setup(h, "А")
    stranger = await player(h, "Любопытный А")
    start = len(h.world.calls)
    await file_report(h, reporter, target, chat, "спам")
    cards = {int(p["chat_id"]): p for n, p in h.world.calls[start:] if n == "SendMessage" and "Жалоба №" in str(p.get("text")) and int(p["chat_id"]) > 0}
    ok(helper.id in cards and senior.id in cards and other.id in cards, f"the staff get the card: {sorted(cards)}")
    ok(reporter.id not in cards, "the author of the report does not")
    card = last_message(h, senior.id, "Жалоба №")
    labels = [b["text"] for b in card.buttons()]
    ok(any("Мут" in t for t in labels) and any("Бан" in t for t in labels) and any("Отклонить" in t for t in labels), f"the card has the buttons: {labels}")
    refused = await h.click(stranger, senior.id, card, "Мут")
    ok(refused.alert and "для персонала" in refused.text, f"a stranger is refused: {refused.text!r}")
    weak = await h.click(helper, helper.id, last_message(h, helper.id, "Жалоба №"), "Мут")
    ok(weak.alert and "нужна роль" in weak.text, f"a helper below the role for mute is refused with the admin's words: {weak.text!r}")
    ok(await report_status(card.text) == "new", "and the report is untouched")
    take = await h.click(senior, senior.id, card, "В работу")
    ok(not take.alert, f"«В работу» works: {take.text!r}")
    taken = last_message(h, senior.id, "Жалоба №")
    ok("В работе" in taken.text and not any("В работу" in b["text"] for b in taken.buttons()), "the card shows who took it and drops the button")
    ok(await report_status(card.text) == "in_work", "the status moved")
    already = await h.click(other, other.id, last_message(h, other.id, "Жалоба №"), "В работу")
    ok(already.alert and "уже в работе" in already.text, f"a second «В работу» is told so: {already.text!r}")
    ok(any("Мут" in b["text"] for b in last_message(h, other.id, "Жалоба №").buttons()), "and his card keeps its buttons: the report is still open")
    start = len(h.world.calls)
    muted = await h.click(senior, senior.id, taken, "Мут")
    ok(not muted.alert, f"mute works: {muted.text!r}")
    closed = last_message(h, senior.id, "Жалоба №")
    ok("Мут на 1 час" in closed.text and closed.buttons() == [], f"the card shows the result: {closed.text[-160:]!r}")
    ok(await report_status(card.text) == "resolved", "the report is closed as confirmed")
    ok(any(n == "RestrictChatMember" and int(p["user_id"]) == target.id for n, p in h.world.calls[start:]), "the offender is muted in the chat of the report")
    ok(any("рассмотрена" in str(p.get("text")) for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == reporter.id), "the author is told how it ended")
    late = await h.click(other, other.id, last_message(h, other.id, "Жалоба №"), "Мут")
    ok(late.alert and "закрыта" in late.text, f"a colleague's second tap does not punish twice: {late.text!r}")
    ok("уже закрыта" in last_message(h, other.id, "Жалоба №").text, "and his card loses the buttons")
    async with database() as db:
        async with db.execute("SELECT action FROM bot_admin_actions WHERE user_id = ? AND action LIKE 'report_%' ORDER BY id", (target.id,)) as c:
            ok(len(await c.fetchall()) >= 2, "the journal has the taking and the closing")


@bot_scenario
async def report_card_ban_asks_twice_and_reject_closes(h: Harness) -> None:
    reporter, target, helper, senior, other, chat = await report_setup(h, "Б")
    await file_report(h, reporter, target, chat, "оскорбления")
    card = last_message(h, senior.id, "Жалоба №")
    start = len(h.world.calls)
    ask = await h.click(senior, senior.id, card, "Бан")
    asked = last_message(h, senior.id, "Жалоба №")
    ok(not ask.alert and [b["text"] for b in asked.buttons()][0].startswith("✅ Да") and not any(n == "BanChatMember" for n, _ in h.world.calls[start:]),
       "«Бан» only asks for confirmation")
    await h.click(senior, senior.id, asked, "Отмена")
    ok(any("Мут" in b["text"] for b in last_message(h, senior.id, "Жалоба №").buttons()), "«Отмена» brings the buttons back")
    await h.click(senior, senior.id, last_message(h, senior.id, "Жалоба №"), "Бан")
    done = await h.click(senior, senior.id, last_message(h, senior.id, "Жалоба №"), "Да")
    ok(not done.alert, f"the confirmed ban is done: {done.text!r}")
    ok(any(n == "BanChatMember" and int(p["user_id"]) == target.id for n, p in h.world.calls[start:]), "the offender is banned in that chat")
    ok("Бан на 7 дней" in last_message(h, senior.id, "Жалоба №").text and await report_status(card.text) == "resolved", "7 days, report closed")
    await file_report(h, reporter, target, chat, "и снова")
    start = len(h.world.calls)
    rejected = await h.click(senior, senior.id, last_message(h, senior.id, "Жалоба №"), "Отклонить")
    ok(not rejected.alert and "Отклонена" in last_message(h, senior.id, "Жалоба №").text, f"reject: {rejected.text!r}")
    ok(not any(n in ("RestrictChatMember", "BanChatMember") for n, _ in h.world.calls[start:]), "reject punishes nobody")
    ok(any("нарушения не нашли" in str(p.get("text")) for n, p in h.world.calls[start:] if n == "SendMessage" and int(p["chat_id"]) == reporter.id), "the author is told")


# ── the morning plan ────────────────────────────────────────────────────────

@bot_scenario
async def dm_morning_plan_comes_once_in_the_players_morning(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    from services import dm_plan, dm_push_events
    early, ready, stranger = await player(h, "Жаворонок"), await player(h, "Утренний"), await player(h, "Без согласия утро")
    async with database() as db:
        await consent(db, ready, "digest")
        await consent(db, early, "digest")
        await repo.set_tz(db, early.id, 5)
        await db.commit()
        night = at(3)                                                       # 06:00 for the default zone (+3), 08:00 for +5: both too early
        await dm_push_events.collect(db, night)
        ok(not await repo.pending_rows(db, ready.id) and not await repo.pending_rows(db, early.id), "before 09:00 local time nobody is written to")
        window = at(4).replace(minute=30)                                   # 07:30 (+3) — still early; 09:30 (+5) — the window
        await dm_push_events.collect(db, window)
        ok(not await repo.pending_rows(db, ready.id), "09:00 is the earliest, by the player's own zone")
        ok(await repo.pending_rows(db, early.id), "a player in +5 gets his plan at 09:30 local time")
        morning = at(7)                                                     # 10:00 (+3)
        found = await dm_push_events.collect(db, morning)
        ok(found["digest"] >= 1 and await repo.pending_rows(db, ready.id), f"in the window the plan is queued: {found}")
        ok(not await repo.pending_rows(db, stranger.id), "no consent, no plan")
        rows = await repo.pending_rows(db, ready.id)
        ok("План на сегодня" in rows[0]["text"] and rows[0]["button"]["data"] == "dn:plan", f"the text and the button: {rows[0]['text'][:80]!r}")
        again = await dm_push_events.collect(db, morning + timedelta(minutes=5))
        ok(again["digest"] == 0 and len(await repo.pending_rows(db, ready.id)) == 1, "a second pass in the same morning adds nothing")
        start = len(h.world.calls)
        await deliver(h, db, morning + timedelta(minutes=1))
        sent = to_player(h, ready, start)
        ok(len(sent) == 1 and "План на сегодня" in str(sent[0]["text"]) and "Открыть план" in str(sent[0]["reply_markup"]), "it arrives with the button")
        click = await h.click(ready, ready.id, last_message(h, ready.id, "План на сегодня"), "Открыть план")
        ok(not click.alert and last_message(h, ready.id, "План дня"), "the button opens the full plan")
        tomorrow = await dm_push_events.collect(db, morning + timedelta(days=1))
        ok(tomorrow["digest"] >= 1, "and tomorrow it comes again")
        mixed = await player(h, "Склейка")
        await consent(db, mixed, "digest", "quests")
        from tools.mafia_sim.scn_bot_dm_push import push_at
        await push_at(db, mixed, "quests", "q:mix", at(7, 3), "📋 <b>Новые задания дня</b>\nВыполни их.")
        await push_at(db, mixed, "digest", "digest:mix", at(7, 3), "☀️ <b>План на сегодня</b>\n🐾 Питомцы вернулись: 2 — добыча ждёт.")
        start = len(h.world.calls)
        await deliver(h, db, at(8, 3))
        merged = to_player(h, mixed, start)
        ok(len(merged) == 1 and "Питомцы вернулись: 2" in str(merged[0]["text"]) and "Новые задания дня" in str(merged[0]["text"]),
           f"the morning plan keeps its content inside a shared digest: {merged[:1]}")
        original = dm_plan.quests_state

        async def nothing(db, user_id):
            return None
        dm_plan.quests_state = nothing
        try:
            quiet = await player(h, "Нечего сказать")
            await consent(db, quiet, "digest")
            await dm_push_events.collect(db, morning + timedelta(days=2))
            ok(not await repo.pending_rows(db, quiet.id), "with nothing to do there is no letter")
        finally:
            dm_plan.quests_state = original

