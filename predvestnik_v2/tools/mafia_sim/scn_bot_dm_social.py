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
    outsider = await player(h, "Не из этого чата")
    chat = h.new_chat([groom, bride, kid, shy])
    for user in (groom, bride, kid, shy):
        await h.say(user, chat, "привет")
    async with database() as db:
        await consent(db, bride, "social")
        await consent(db, kid, "social")
        await consent(db, outsider, "social")
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
    # Also cover ordinary groups, which do not have private message links.
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
    await say(h, groom, chat, f"бот брак, @sim{outsider.id}")   # @ник ищется по всем игрокам, но письма чужому нет
    ok(not await pending(outsider), "someone who is not in the chat gets no letter and learns no chat title")
    await say(h, shy, chat, f"бот брак, @sim{groom.id}")
    ok(not [r for r in await pending(groom) if r["category"] == "social"], "the groom never turned «Люди» on: nothing for him")
    yes = await h.click(bride, chat, to_bride, "Да")
    ok(not yes.alert and last_message(h, chat, "теперь семья"), f"the couple is married: {yes}")

    adopt = await say(h, groom, chat, f"бот усыновить, @sim{kid.id}")
    ok("в свою семью ребёнком" in said(adopt), said(adopt))
    invite = [r for r in await pending(kid) if "семью" in r["text"]]
    ok(len(invite) == 1 and "24 ч" in invite[0]["text"], f"the family invite reaches the child: {invite}")
    await say(h, groom, chat, f"бот усыновить, @sim{kid.id}")
    ok(len([r for r in await pending(kid) if "семью" in r["text"]]) == 1, "the same invite again today: no second letter")
    await h.click(kid, chat, last_message(h, chat, "в свою семью ребёнком"), "Нет")
    ok(not await pending(kid), "a declined family invitation is withdrawn before delivery")

    async with database() as db:
        start = len(h.world.calls)
        await deliver(h, db, datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=1))
    letters = " ".join(str(p["text"]) for p in to_player(h, bride, start))
    ok("Перевод от игрока" in letters and "переводит тебе" in letters and "зовёт тебя в брак" not in letters,
       f"the transfer arrives, the already accepted proposal is withdrawn: {letters[:400]!r}")


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

    from infrastructure.repositories import dm_push as push_repo
    async with database() as db:
        for skin in looks:
            await skins_repo.grant(db, half.id, skin)
        # Test timestamps are inside the holiday window, independently of the real execution date.
        await db.execute("UPDATE dm_push_outbox SET created_at = (?::timestamp AT TIME ZONE 'UTC') WHERE user_id = ANY(?::bigint[])",
                         (near, [newcomer.id, half.id]))
        await db.commit()
        start = len(h.world.calls)
        await deliver(h, db, near + timedelta(days=1))
        ok(not to_player(h, half, start), "a completed collection cancels the queued reminder")
        letters = to_player(h, newcomer, start)
        ok(letters and "ещё 1 день" in letters[0]["text"], "the remaining time is recomputed at delivery")
        # A new consenting player queued in the last hours must get no letter after the shop window closes.
        late = await player(h, "Опоздавший")
        await consent(db, late, "events")
        ending = datetime(2027, 1, 10, 23, tzinfo=timezone.utc)
        await dm_push_events.collect(db, ending)
        await db.execute("UPDATE dm_push_outbox SET created_at = (?::timestamp AT TIME ZONE 'UTC') WHERE user_id = ?", (ending, late.id))
        await db.commit()
        start = len(h.world.calls)
        await deliver(h, db, ending + timedelta(hours=14))
        ok(not to_player(h, late, start) and not await push_repo.pending_rows(db, late.id), "closed holiday window drops its queued letter")


# ── the personal season report ──────────────────────────────────────────────

@bot_scenario
async def dm_season_report_is_detailed_and_sent_once(h: Harness) -> None:
    from core import seasons
    from infrastructure.repositories import league_pass as pass_repo
    from infrastructure.repositories import minesweeper_v2 as sapper_repo
    from infrastructure.repositories import rhythm_v2 as rhythm_repo
    from infrastructure.repositories import skins_v3 as skins_repo
    from services import dm_push_events, season_report
    star, idle, quiet, old_consent = [await player(h, n) for n in ("Звезда сезона", "Ничего не делал", "Итог без согласия", "Только старое согласие")]
    start, end = seasons.season_bounds(2)
    played = start + timedelta(days=10)
    runs = []
    async with database() as db:
        await rhythm_repo.ensure_tables(db)
        await sapper_repo.ensure_tables(db)
        await skins_repo.ensure_tables(db)
        await pass_repo.ensure_tables(db)
        await consent(db, old_consent, "season")
        for user in (star, idle):
            await consent(db, user, "season_report")
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
            dm_push_events._report_seen.clear()
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
    ok(not await pending(quiet) and not await pending(old_consent), "neither absent nor old season consent permits a report")
    async with database() as db:
        from tools.mafia_sim.scn_bot_dm_push import push
        await consent(db, star, "quests")
        await push(db, star, "quests", f"q:solo:{star.id}", "📋 <b>Новые задания дня</b>\nВыполни их.")
        delivery_time = end + timedelta(hours=9)
        await db.execute("UPDATE dm_push_outbox SET created_at = (?::timestamp AT TIME ZONE 'UTC') WHERE user_id = ?", (delivery_time, star.id))
        start = len(h.world.calls)
        await deliver(h, db, delivery_time)
    first = to_player(h, star, start)
    ok(len(first) == 1 and "Итоги сезона 2" in first[0]["text"] and "Сыграно" in first[0]["text"] and "Новые задания" not in first[0]["text"],
       f"the report goes alone and whole, not squeezed into a digest: {first}")


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
    ok(any("навсегда" in t for t in labels(mine)) and not any("Во всех чатах" in t for t in labels(mine)), f"the creator's card: {labels(mine)}")
    ok(not any("навсегда" in t or "Во всех" in t for t in labels(theirs)), f"a senior's card has no heavy bans: {labels(theirs)}")
    rid = int(re.search(r"№(\d+)", mine.text).group(1))
    forged = dataclasses.replace(theirs, markup={"inline_keyboard": [[{"text": "⛔ Бан навсегда", "callback_data": f"rp:P:{rid}"}]]})
    start = len(h.world.calls)
    refused = await h.click(senior, senior.id, forged, "навсегда")
    ok(refused.alert and "создатель" in refused.text and not any(n == "BanChatMember" for n, _ in h.world.calls[start:]),
       f"a forged button from a senior is refused: {refused}")

    direct = dataclasses.replace(mine, markup=forged.markup)
    refused = await h.click(creator, creator.id, direct, "навсегда")
    ok(refused.alert and "заново" in refused.text, "a direct permanent ban without confirmation is refused")
    refused = await h.click(creator, chat, direct, "навсегда")
    ok(refused.alert and "личке" in refused.text, "even the creator cannot use a heavy callback in a group")
    global_button = dataclasses.replace(mine, markup={"inline_keyboard": [[{"text": "global", "callback_data": f"rp:G:{rid}"}]]})
    refused = await h.click(creator, creator.id, global_button, "global")
    ok(refused.alert and "устарела" in refused.text, "global actions belong to the admin panel, never DM callbacks")

    ask = await h.click(creator, creator.id, mine, "навсегда")
    asked = last_message(h, creator.id, "Жалоба №")
    ok(not ask.alert and labels(asked)[0].startswith("✅ Да, бан навсегда"), f"the permanent ban asks first: {labels(asked)}")
    await h.click(creator, creator.id, asked, "Отмена")
    ok(any("навсегда" in t for t in labels(last_message(h, creator.id, "Жалоба №"))), "«Отмена» brings the creator's buttons back")
    refused = await h.click(creator, creator.id, direct, "навсегда")
    ok(refused.alert and "заново" in refused.text, "cancel revokes the server-side confirmation")
    await h.click(creator, creator.id, last_message(h, creator.id, "Жалоба №"), "навсегда")
    start = len(h.world.calls)
    done = await h.click(creator, creator.id, last_message(h, creator.id, "Жалоба №"), "Да")
    bans = [p for n, p in h.world.calls[start:] if n == "BanChatMember" and int(p["user_id"]) == target.id]
    ok(not done.alert and bans and not bans[0].get("until_date"), f"banned in the chat with no end date: {bans}")
    ok("Бан навсегда" in last_message(h, creator.id, "Жалоба №").text and await report_status(mine.text) == "resolved", "report closed")


@bot_scenario
async def dm_invitation_letters_expire_and_follow_the_players_answer(h: Harness) -> None:
    from services import dm_push
    proposer, cancelled, declined, expired, app_reply = [await player(h, n) for n in ("Зовущий", "Отзыв", "Отказ", "Поздно", "Ответ в приложении")]
    chat = h.new_chat([proposer, cancelled, declined, expired, app_reply])
    for user in (proposer, cancelled, declined, expired, app_reply):
        await h.say(user, chat, "привет")
    async with database() as db:
        for user in (cancelled, declined, expired, app_reply):
            await consent(db, user, "social")
    for target, actor, button in ((cancelled, proposer, "Отозвать"), (declined, declined, "Нет")):
        await say(h, proposer, chat, f"бот брак, @sim{target.id}")
        ok(bool(await pending(target)), "the unanswered proposal has a queued letter")
        await h.click(actor, chat, last_message(h, chat, "делает предложение"), button)
        ok(not await pending(target), "the withdrawn or declined proposal has no letter left")
    await say(h, proposer, chat, f"бот брак, @sim{expired.id}")
    await say(h, proposer, chat, f"бот брак, @sim{app_reply.id}")
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    async with database() as db:
        # The Mini App changes the authoritative proposal, without touching the bot outbox.
        await db.execute("UPDATE marriage_proposals SET status='declined' WHERE proposer_id=? AND target_id=?", (proposer.id, app_reply.id))
        await db.execute("UPDATE dm_push_outbox SET created_at=(?::timestamp AT TIME ZONE 'UTC') WHERE user_id=?", (now - dm_push.INVITATION_TTL, expired.id))
        await db.commit()
        before = len(h.world.calls)
        await deliver(h, db, now)
    ok(not await pending(expired) and not to_player(h, expired, before), "the letter expires with the invitation at 24 hours")
    ok(not await pending(app_reply) and not to_player(h, app_reply, before), "an answer through the Mini App also cancels delivery")


@bot_scenario
async def dm_season_report_uses_exact_utc_boundaries(h: Harness) -> None:
    from core import seasons
    from infrastructure.repositories import league_pass as pass_repo, minesweeper_v2 as mines_repo, rhythm_v2 as rhythm_repo, skins_v3 as skins_repo
    from services import season_report
    user = await player(h, "На границе сезона")
    start, end = seasons.season_bounds(2)
    moments = (start - timedelta(microseconds=1), start, end - timedelta(microseconds=1), end)
    run_ids = []
    async with database() as db:
        for repo in (pass_repo, mines_repo, rhythm_repo, skins_repo):
            await repo.ensure_tables(db)
        try:
            for moment in moments:
                run_id = f"s23e-edge-{uuid4()}"
                run_ids.append(run_id)
                # Raw asyncpg inserts UTC instants without PGAdapter's naive-datetime compatibility path.
                await db.connection.execute(
                    "INSERT INTO rhythm_v2_runs (run_id,user_id,mode,ruleset_version,seed,offers_json,status,health,score,integrity_status,created_at,finished_at) "
                    "VALUES ($1,$2,'normal','test',$3,'[]'::jsonb,'finished',0,10,'clear',$4,$4)",
                    run_id, user.id, b"x" * 32, moment)
                await db.connection.execute(
                    "INSERT INTO minesweeper_v2_runs (run_id,user_id,difficulty,ruleset_version,seed,status,opened_actions,elapsed_ms,finished_at) "
                    "VALUES ($1,$2,'hard','minesweeper-v2',$3,'lost',1,100,$4)", run_id, user.id, b"x" * 32, moment)
            for skin, moment in zip(("sakura_bud", "forest", "dune"), (moments[0], moments[1], moments[-1])):
                await skins_repo.grant(db, user.id, skin)
                await db.connection.execute("UPDATE skins_v3_owned SET acquired_at=$1 WHERE user_id=$2 AND skin_id=$3", moment, user.id, skin)
            season_report._cache.clear()
            result = await season_report.report(db, user.id, 2)
            from core.skins_v3_catalog import SKINS
            ok(result["rhythm_games"] == 2 and result["sapper_games"] == 2, f"only [start,end) UTC games count: {result}")
            ok(result["looks"] == [SKINS["forest"]["name"]], f"only the look acquired inside the UTC season counts: {result}")
            next_result = await season_report.report(db, user.id, 3)
            ok(next_result["rhythm_games"] == 1 and next_result["sapper_games"] == 1, "the exact closing instant belongs to the next season")
        finally:
            await db.execute("DELETE FROM rhythm_v2_runs WHERE run_id = ANY(?)", (run_ids,))
            await db.execute("DELETE FROM minesweeper_v2_runs WHERE run_id = ANY(?)", (run_ids,))
            await db.commit()
            season_report._cache.clear()
