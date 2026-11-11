"""Whole-bot scenarios (S23e): «Люди» (a transfer in a chat, a marriage proposal, a family invite), holiday looks that are
about to leave, the personal season report, an announcement to the players who turned «События» on, and the heavy bans on
the creator's report card.

Every message here needs the player's own consent (no consent row = no letter), so each scenario also has a player without
consent who must get nothing. The test clock is a parameter (``collect(db, now)``), the season and holiday windows are real."""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_dm_push import consent, database, deliver, player, to_player
from tools.mafia_sim.scn_bot_dm_support import file_report, report_setup, report_status
from tools.mafia_sim.scn_bot_util import last_message, said, say


async def pending(user) -> list[dict]:
    from infrastructure.repositories import dm_push as repo
    async with database() as db:
        return await repo.pending_rows(db, user.id)


# ── «Люди»: a transfer, a proposal, a family invite ─────────────────────────

@bot_scenario
async def dm_social_events_need_consent_and_link_to_the_chat(h: Harness) -> None:
    from bot.chat.notify import message_url
    from infrastructure.repositories import economy as eco
    groom, bride, kid, shy = [await player(h, n) for n in ("Жених", "Невеста", "Малыш", "Скромник")]
    chat = h.new_chat([groom, bride, kid, shy])
    for user in (groom, bride, kid, shy):
        await h.say(user, chat, "привет")
    async with database() as db:
        await consent(db, bride, "social")
        await consent(db, kid, "social")
        await db.commit()
        await eco.add_balance(db, groom.id, mora=100, source="sim", note="scenario funds", idempotency_key=f"sim-social-{h.run_tag}-{groom.id}")

    await say(h, groom, chat, f"бот перевод, @sim{bride.id} 25")
    prompt = last_message(h, chat, "Какую валюту")
    stale = dataclasses.replace(prompt, markup={"inline_keyboard": [list(r) for r in prompt.markup["inline_keyboard"]]})
    first = await h.click(groom, chat, prompt, "Мора")
    ok(first.text == "Готово", f"the transfer goes through: {first}")
    await h.click(groom, chat, stale, "Мора")   # the same tap twice: the money moves once, the letter is queued once
    rows = [r for r in await pending(bride) if r["category"] == "social"]
    ok(len(rows) == 1 and "Перевод от игрока" in rows[0]["text"] and "25" in rows[0]["text"] and "Мора" in rows[0]["text"],
       f"one transfer letter for the consenting receiver: {rows}")
    # the simulator's chat ids are not real supergroup ids (-100…), so the link is checked on the id rule itself
    ok(message_url(SimpleNamespace(id=-1001234567890, username=None), 7) == "https://t.me/c/1234567890/7"
       and message_url(SimpleNamespace(id=-1001234567890, username="club"), 7) == "https://t.me/club/7"
       and message_url(SimpleNamespace(id=-4123, username=None), 7) is None, "links to a public chat, a supergroup, none for a plain group")
    expected = message_url(SimpleNamespace(id=chat, username=None), 1)
    ok(bool(rows[0]["button"]) == bool(expected), f"a button exactly when the chat has message links: {rows[0]}")
    await say(h, groom, chat, f"бот перевод, @sim{shy.id} 5")
    await h.click(groom, chat, last_message(h, chat, "Какую валюту"), "Мора")
    ok(not await pending(shy), "no consent, no letter about the transfer")

    await say(h, groom, chat, f"бот брак, @sim{bride.id}")
    to_bride = last_message(h, chat, "делает предложение")
    proposal = [r for r in await pending(bride) if "предложение" in r["text"]]
    ok(len(proposal) == 1 and "сутки" in proposal[0]["text"] and "Sim" in proposal[0]["text"], f"the proposal letter names the chat: {proposal}")
    await say(h, shy, chat, f"бот брак, @sim{groom.id}")
    ok(not [r for r in await pending(groom) if r["category"] == "social"], "the groom never turned «Люди» on: nothing for him")
    yes = await h.click(bride, chat, to_bride, "Да")
    ok(not yes.alert and last_message(h, chat, "теперь семья"), f"the couple is married: {yes}")

    adopt = await say(h, groom, chat, f"бот усыновить, @sim{kid.id}")
    ok("в свою семью ребёнком" in said(adopt), said(adopt))
    invite = [r for r in await pending(kid) if "семью" in r["text"]]
    ok(len(invite) == 1 and "24 ч" in invite[0]["text"], f"the family invite reaches the child: {invite}")

    async with database() as db:
        start = len(h.world.calls)
        await deliver(h, db, datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=1))
    letters = " ".join(str(p["text"]) for p in to_player(h, bride, start))
    ok("Перевод от игрока" in letters and "предложение" in letters, f"the letters arrive: {letters[:300]!r}")


# ── holiday looks are about to leave ────────────────────────────────────────

@bot_scenario
async def dm_holiday_looks_reminder_lists_only_missing_looks(h: Harness) -> None:
    from core.skins_v3_catalog import SKINS
    from infrastructure.repositories import skins_v3 as skins_repo
    from services import dm_push_events
    looks = [k for k, s in SKINS.items() if s.get("season") == "new_year" and not s.get("exclusive")]
    ok(len(looks) >= 2, f"the New Year has looks to remind about: {looks}")
    newcomer, collector, half, quiet = [await player(h, n) for n in ("Без образов", "Собрал всё", "Половина", "Без согласия")]
    async with database() as db:
        await skins_repo.ensure_tables(db)
        for user in (newcomer, collector, half):
            await consent(db, user, "events")
        for skin in looks:
            await skins_repo.grant(db, collector.id, skin)
        await skins_repo.grant(db, half.id, looks[0])
        await db.commit()
        early = await dm_push_events.collect(db, datetime(2027, 1, 2, 12, tzinfo=timezone.utc))   # nine days before the end
        ok(early["events"] == 0, f"too early: nothing yet {early}")
        near = datetime(2027, 1, 9, 12, tzinfo=timezone.utc)                                       # the window closes on 11.01
        found = await dm_push_events.collect(db, near)
        again = await dm_push_events.collect(db, near + timedelta(hours=1))
    ok(found["events"] >= 2 and again["events"] == 0, f"queued once per window: {found} then {again}")
    rows = await pending(newcomer)
    ok(len(rows) == 1 and "Новогодняя Ночь" in rows[0]["text"] and "ещё 2 дня" in rows[0]["text"]
       and all(SKINS[k]["name"] in rows[0]["text"] for k in looks), f"the letter names the window, the days and the looks: {rows}")
    ok(rows[0]["button"]["section"] == "looks", "the button opens the looks")
    half_rows = await pending(half)
    ok(len(half_rows) == 1 and SKINS[looks[0]]["name"] not in half_rows[0]["text"], "an owned look is not offered again")
    ok(not await pending(collector) and not await pending(quiet), "a full collection or no consent: no letter")


# ── the personal season report ──────────────────────────────────────────────

@bot_scenario
async def dm_season_report_is_detailed_and_sent_once(h: Harness) -> None:
    from core import seasons
    from infrastructure.repositories import league_pass as pass_repo
    from infrastructure.repositories import minesweeper_v2 as sapper_repo
    from infrastructure.repositories import rhythm_v2 as rhythm_repo
    from infrastructure.repositories import skins_v3 as skins_repo
    from services import dm_push_events, season_report
    star, idle, quiet = [await player(h, n) for n in ("Звезда сезона", "Ничего не делал", "Итог без согласия")]
    start, end = seasons.season_bounds(2)
    played = start + timedelta(days=10)
    runs = []
    async with database() as db:
        await rhythm_repo.ensure_tables(db)
        await sapper_repo.ensure_tables(db)
        await skins_repo.ensure_tables(db)
        await pass_repo.ensure_tables(db)
        for user in (star, idle):
            await consent(db, user, "season")
        for score in (900_000_000, 10):   # the best clear run counts; a huge score puts the star first
            run_id = f"s23e-{uuid4()}"
            runs.append(run_id)
            await db.execute("INSERT INTO rhythm_v2_runs (run_id, user_id, mode, ruleset_version, seed, offers_json, status, health, score, "
                             "integrity_status, created_at, finished_at) VALUES (?, ?, 'normal', 'test', ?, '[]'::jsonb, 'finished', 0, ?, 'clear', ?, ?)",
                             (run_id, star.id, b"x" * 32, score, played, played))
        sapper_run = f"s23e-{uuid4()}"
        await db.execute("INSERT INTO minesweeper_v2_runs (run_id, user_id, difficulty, ruleset_version, seed, status, opened_actions, "
                         "elapsed_ms, finished_at) VALUES (?, ?, 'hard', 'minesweeper-v2', ?, 'won', 5, 1, ?)",
                         (sapper_run, star.id, b"\x00" * 32, played))
        await db.execute("INSERT INTO league_pass_progress (user_id, season, xp) VALUES (?, 2, 3700) "
                         "ON CONFLICT (user_id, season) DO UPDATE SET xp = EXCLUDED.xp", (star.id,))
        await skins_repo.grant(db, star.id, "sakura_bud")
        await db.execute("UPDATE skins_v3_owned SET acquired_at = ? WHERE user_id = ? AND skin_id = 'sakura_bud'", (played, star.id))
        await db.commit()
        try:
            season_report._cache.clear()
            dm_push_events._report_cursor.clear()
            ok((await dm_push_events.collect(db, end + timedelta(minutes=30)))["season_report"] == 0, "not before the last results settle")
            found = await dm_push_events.collect(db, end + timedelta(hours=2))
            again = await dm_push_events.collect(db, end + timedelta(hours=3))
            ok(found["season_report"] >= 1 and again["season_report"] == 0, f"one report per player: {found} then {again}")
            ok(season_report.due_season(end + timedelta(days=3)) is None, "two days later the report is no longer news")
        finally:
            await db.execute("DELETE FROM rhythm_v2_runs WHERE run_id = ANY(?)", (runs,))
            await db.execute("DELETE FROM minesweeper_v2_runs WHERE run_id = ?", (sapper_run,))
            await db.commit()
            season_report._cache.clear()
    rows = await pending(star)
    text = rows[0]["text"] if rows else ""
    ok(len(rows) == 1 and "Итоги сезона 2" in text, f"the star gets the report: {rows}")
    for piece in ("Пропуск: 12-й уровень из 40", "Ритм: 1-е место из", "Сапёр: ", "поле «Сложный»",
                  "Сыграно: 2 партии в Ритм и 1 партия в Сапёр", "Новые образы: "):
        ok(piece in text, f"the report has «{piece}»: {text!r}")
    ok(rows[0]["button"]["section"] == "pass", "the button opens the new Pass")
    ok(not await pending(idle), "an empty season gives no letter")
    ok(not await pending(quiet), "no consent, no report")


# ── an announcement to the players who wait for events ──────────────────────

@bot_scenario
async def broadcast_to_event_subscribers_only_with_the_way_out(h: Harness) -> None:
    from services import broadcasts
    fan, other, closed = await player(h, "Ждёт события"), await player(h, "Не подписан"), await player(h, "Не открыл личку", write=False)
    async with database() as db:
        await broadcasts.ensure_schema(db)
        await consent(db, fan, "events")
        await consent(db, closed, "events")
        await db.commit()
        seg = broadcasts.normalize_segment({"kind": "events", "players": [fan.id, other.id, closed.id]})
        ok(await broadcasts.recipients(db, seg) == [fan.id], "only a consenting player with an open DM")
        ok(broadcasts.describe_segment(seg).startswith("События в личку"), broadcasts.describe_segment(seg))
        long_text = "а" * (broadcasts.MAX_TEXT - 20)
        broadcasts.check_text(long_text, False, None, "players")
        try:
            broadcasts.check_text(long_text, False, None, "events")
            refused = False
        except broadcasts.BroadcastError as exc:
            refused = "выключить" in str(exc)
        ok(refused, "the event text leaves room for the line about turning it off")
        created = await broadcasts.create(db, 101, "events", "🎉 Сегодня двойной опыт в Ритме!", f"s23e-{uuid4()}",
                                          segment={"kind": "events", "players": [fan.id, other.id, closed.id]})
        await db.commit()
        start = len(h.world.calls)
        await db.execute("UPDATE bot_broadcasts SET status = 'running' WHERE id = ? AND status <> 'running'", (created.id,))
        await db.commit()
    await broadcasts.run(h.bot, broadcasts.pool_db_factory(), created.id, "events", "🎉 Сегодня двойной опыт в Ритме!")
    sent = [p for n, p in h.world.calls[start:] if n == "SendMessage"]
    ok([int(p["chat_id"]) for p in sent] == [fan.id], f"one letter, to the subscriber: {[p['chat_id'] for p in sent]}")
    ok("двойной опыт" in sent[0]["text"] and "«уведомления»" in sent[0]["text"], f"with the way out at the end: {sent[0]['text']!r}")


# ── the creator's report card: a permanent ban and a ban everywhere ─────────

@bot_scenario
async def report_card_heavy_bans_only_for_the_creator(h: Harness) -> None:
    reporter, target, _helper, senior, _other, chat = await report_setup(h, "В")
    from bot.config import config
    from tools.mafia_sim.harness import SimUser
    creator = SimUser(int(config.developer_id), "Создатель В")   # «только я»: создатель бота — DEVELOPER_ID, роль в базе не выше 5
    h.world.dm_open.add(creator.id)
    async with database() as db:
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) VALUES (?, ?, ?) ON CONFLICT (user_tg_id) DO NOTHING",
                         (creator.id, creator.username, creator.name))
        await db.commit()
    await say(h, creator, creator.id, "баланс")
    await file_report(h, reporter, target, chat, "угрозы")
    mine, theirs = last_message(h, creator.id, "Жалоба №"), last_message(h, senior.id, "Жалоба №")
    labels = lambda m: [b["text"] for b in m.buttons()]
    ok(any("навсегда" in t for t in labels(mine)) and any("Во всех чатах" in t for t in labels(mine)), f"the creator's card: {labels(mine)}")
    ok(not any("навсегда" in t or "Во всех" in t for t in labels(theirs)), f"a senior's card has no heavy bans: {labels(theirs)}")
    rid = int(re.search(r"№(\d+)", mine.text).group(1))
    forged = dataclasses.replace(theirs, markup={"inline_keyboard": [[{"text": "⛔ Бан навсегда", "callback_data": f"rp:P:{rid}"}]]})
    start = len(h.world.calls)
    refused = await h.click(senior, senior.id, forged, "навсегда")
    ok(refused.alert and "создатель" in refused.text and not any(n == "BanChatMember" for n, _ in h.world.calls[start:]),
       f"a forged button from a senior is refused: {refused}")

    ask = await h.click(creator, creator.id, mine, "навсегда")
    asked = last_message(h, creator.id, "Жалоба №")
    ok(not ask.alert and labels(asked)[0].startswith("✅ Да, бан навсегда"), f"the permanent ban asks first: {labels(asked)}")
    await h.click(creator, creator.id, asked, "Отмена")
    ok(any("Во всех чатах" in t for t in labels(last_message(h, creator.id, "Жалоба №"))), "«Отмена» brings the creator's buttons back")
    await h.click(creator, creator.id, last_message(h, creator.id, "Жалоба №"), "навсегда")
    start = len(h.world.calls)
    done = await h.click(creator, creator.id, last_message(h, creator.id, "Жалоба №"), "Да")
    bans = [p for n, p in h.world.calls[start:] if n == "BanChatMember" and int(p["user_id"]) == target.id]
    ok(not done.alert and bans and not bans[0].get("until_date"), f"banned in the chat with no end date: {bans}")
    ok("Бан навсегда" in last_message(h, creator.id, "Жалоба №").text and await report_status(mine.text) == "resolved", "report closed")

    await file_report(h, reporter, target, chat, "снова угрозы")
    card = last_message(h, creator.id, "Жалоба №")
    await h.click(creator, creator.id, card, "Во всех чатах")
    done = await h.click(creator, creator.id, last_message(h, creator.id, "Жалоба №"), "Да, во всех")
    ok(done.alert and "Жалоба закрыта" in done.text, f"the ban everywhere answers with the count: {done}")
    ok("Бан во всех чатах" in last_message(h, creator.id, "Жалоба №").text and await report_status(card.text) == "resolved", "report closed")
    async with database() as db:
        async with db.execute("SELECT 1 FROM chat_blacklist WHERE chat_id = 0 AND user_id = ?", (target.id,)) as c:
            ok(await c.fetchone() is not None, "the offender is on the bot-wide ban list")
        await db.execute("DELETE FROM chat_blacklist WHERE user_id = ?", (target.id,))
        await db.commit()
