"""Whole-bot scenarios: notifications to the DM (S23) — consent, DM gate, quiet hours, daily cap, digest, blocked bot,
flood limit, pause without reaction, event collectors, the plan of the day and a reward that cannot be taken twice."""
from __future__ import annotations

import copy
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import last_message, said, say
from tools.mafia_sim.world import TgError


@asynccontextmanager
async def database():
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


async def player(h: Harness, name: str, *, write: bool = True):
    """A fresh player with a clean notification state; ``write`` — he has already written to the bot in the DM."""
    user = h.user(name)
    async with database() as db:
        for table in ("dm_push_outbox", "dm_push_settings"):
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user.id,))
        await db.execute("DELETE FROM user_notification_prefs WHERE user_id = ?", (user.id,))
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) VALUES (?, ?, ?) ON CONFLICT (user_tg_id) DO NOTHING",
                         (user.id, f"sim{user.id}", name))
        await db.execute("DELETE FROM vip_v2_preferences WHERE user_id = ?", (user.id,))
        await db.commit()
    if write:
        await say(h, user, user.id, "баланс")
    return user


def at(hour_utc: int, day_shift: int = 0) -> datetime:
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return base.replace(hour=hour_utc) + timedelta(days=day_shift)


def to_player(h: Harness, user, since: int = 0) -> list[dict]:
    return [p for n, p in h.world.calls[since:] if n == "SendMessage" and int(p["chat_id"]) == user.id]


async def consent(db, user, *cats: str) -> None:
    from infrastructure.repositories import dm_push as repo
    for cat in cats:
        await repo.set_consent(db, user.id, cat, True)


async def push(db, user, cat: str, key: str, text: str = "🐾 Событие") -> bool:
    from services import dm_push
    return await dm_push.enqueue(db, user_id=user.id, category=cat, dedup_key=key, text=text)


async def push_at(db, user, cat: str, key: str, when: datetime) -> bool:
    """Queue an event that, for the test clock, was born at ``when``."""
    queued = await push(db, user, cat, key)
    await db.execute("UPDATE dm_push_outbox SET created_at = ? WHERE user_id = ? AND dedup_key = ?", (when, user.id, key))
    return queued


async def deliver(h: Harness, db, now: datetime) -> dict:
    from bot.chat.notify import markup_for
    from services import dm_push
    return await dm_push.deliver_due(h.bot, db, now=now, markup=markup_for)


@bot_scenario
async def dm_push_settings_screen_and_consent(h: Harness) -> None:
    user = await player(h, "Игрок", write=False)
    sent = await say(h, user, user.id, "уведомления")
    screen = last_message(h, user.id, "Уведомления в личку")
    ok("ничего" in said(sent), f"nothing is on by default: {said(sent)[:160]!r}")
    ok(all(not b["text"].startswith("✅") for b in screen.buttons() if b.get("callback_data", "").startswith("dn:t:")), "no category is switched on")
    await h.click(user, user.id, screen, "Питомцы")
    async with database() as db:
        from infrastructure.repositories import dm_push as repo
        ok("pets" in await repo.consented(db, user.id), "tapping a category gives the consent")
        ok((await repo.get_settings(db, user.id))["dm_confirmed_at"] is not None, "the tap also confirms the DM")
    screen = last_message(h, user.id, "Уведомления в личку")
    ok(any(b["text"].startswith("✅") and "Питомцы" in b["text"] for b in screen.buttons()), "the screen shows the category as on")
    await h.click(user, user.id, screen, "Питомцы")
    async with database() as db:
        ok("pets" not in await repo.consented(db, user.id), "a second tap takes the consent back")
    group_user = await player(h, "Из группы")
    group = h.new_chat([group_user])
    sent = await say(h, group_user, group, "бот уведомления")
    ok("в личке" in said(sent), f"in a group the player is sent to the DM: {said(sent)[:120]!r}")
    await say(h, user, user.id, "бот уведомления пояс +5")
    async with database() as db:
        ok((await repo.get_settings(db, user.id))["tz_offset"] == 5, "the time zone is set by the command")
    bad = await say(h, user, user.id, "бот уведомления пояс +99")
    ok("Не понял пояс" in said(bad), "an impossible zone is refused")


@bot_scenario
async def dm_push_needs_consent_and_a_confirmed_dm(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    quiet = await player(h, "Молчун", write=False)
    async with database() as db:
        ok(not await push(db, quiet, "pets", "a"), "no consent, no message")
        await consent(db, quiet, "pets")
        ok(not await push(db, quiet, "pets", "a"), "consent alone is not enough: the player never wrote to the bot")
    await say(h, quiet, quiet.id, "баланс")                      # any message to the bot confirms the DM
    async with database() as db:
        ok(await push(db, quiet, "pets", "a"), "consent and a confirmed DM: queued")
        ok(not await push(db, quiet, "pets", "a"), "the same event is queued once")
        ok(not await push(db, quiet, "chests", "b"), "a reserved category is not accepted")
        await consent(db, quiet, "quests")
        ok(await push(db, quiet, "quests", "q"), "another category with consent")
        await repo.set_consent(db, quiet.id, "pets", False)
        rows = [r["category"] for r in await repo.pending_rows(db, quiet.id)]
        ok(rows == ["quests"], f"taking the consent back removes the queued message of that category: {rows}")
        row = await db.execute("SELECT dm_confirmed_at FROM vip_v2_preferences WHERE user_id = ?", (quiet.id,))
        async with row as c:
            vip = await c.fetchone()
        ok(vip and vip[0] is not None, "the VIP reminder condition dm_confirmed_at is set by a private message (it was never set before)")


@bot_scenario
async def dm_push_quiet_hours_digest_and_daily_cap(h: Harness) -> None:
    user = await player(h, "Сова")
    async with database() as db:
        await consent(db, user, "pets", "quests", "market", "season")
        for n, cat in enumerate(("pets", "quests", "market")):
            await push(db, user, cat, f"e{n}", f"🔔 Событие {n}\nПодробности")
        start = len(h.world.calls)
        night = await deliver(h, db, at(20))                       # 23:00 по Москве
        ok(night["sent"] == 0 and not to_player(h, user, start), f"nothing is sent in the quiet hours: {night}")
        morning = await deliver(h, db, at(8))                      # 11:00 по Москве
        sent = to_player(h, user, start)
        ok(len(sent) == 1 and morning["digests"] == 1, f"three events are one digest: {len(sent)} message(s)")
        ok(all(f"Событие {n}" in sent[0]["text"] for n in range(3)) and "Подробности" not in sent[0]["text"], "the digest lists each event on one line")
        ok(sent[0]["reply_markup"] and "dn:plan" in str(sent[0]["reply_markup"]), "the digest carries the «План дня» button")
        for n in range(3, 5):                                       # ещё два одиночных: всего 3 сообщения за сутки
            await push(db, user, "pets", f"s{n}")
            await deliver(h, db, at(9))
        ok(len(to_player(h, user, start)) == 3, "three messages in a day are the limit so far")
        await push(db, user, "pets", "over")
        await deliver(h, db, at(10))
        ok(len(to_player(h, user, start)) == 3, "the fourth waits: the daily limit")
        await deliver(h, db, datetime.now(timezone.utc) + timedelta(hours=25) - timedelta(hours=datetime.now(timezone.utc).hour - 8))
        ok(len(to_player(h, user, start)) == 4, "and goes out when the day has passed")
        await push(db, user, "pets", "old")
        await db.execute("UPDATE dm_push_outbox SET created_at = NOW() - INTERVAL '40 hours' WHERE user_id = ? AND dedup_key = 'old'", (user.id,))
        before = len(to_player(h, user, start))
        stats = await deliver(h, db, datetime.now(timezone.utc) + timedelta(days=3))
        ok(len(to_player(h, user, start)) == before and stats["dropped"] >= 1, f"an event nobody could deliver in time is dropped: {stats}")


@bot_scenario
async def dm_push_blocked_bot_and_flood_do_not_avalanche(h: Harness) -> None:
    user = await player(h, "Занятой")
    async with database() as db:
        await consent(db, user, "pets")
        await push(db, user, "pets", "x")
        h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == user.id, TgError(429, "Too Many Requests: retry after 7", 7), times=1)
        stats = await deliver(h, db, at(8))
        ok(stats["retry_after"] == 7 and stats["sent"] == 0, f"Telegram asked to wait: {stats}")
        from infrastructure.repositories import dm_push as repo
        ok(len(await repo.pending_rows(db, user.id)) == 1, "the event stays queued, no immediate retry")
        stats = await deliver(h, db, at(8))
        ok(stats["sent"] == 1, "and goes out on the next pass")
        await push(db, user, "pets", "y")
        h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == user.id,
                     TgError(403, "Forbidden: bot was blocked by the user"), times=5)
        stats = await deliver(h, db, at(9))
        ok(stats["unreachable"] == 1, f"a blocked bot is noticed from the failed send: {stats}")
        ok(not await repo.pending_rows(db, user.id), "the queue of that player is cleared")
        ok(not await push(db, user, "pets", "z"), "nothing new is queued for an unreachable DM")
        calls = len([1 for n, p in h.world.calls if n == "SendMessage" and int(p["chat_id"]) == user.id])
        await deliver(h, db, at(10))
        ok(len([1 for n, p in h.world.calls if n == "SendMessage" and int(p["chat_id"]) == user.id]) == calls, "no more attempts after the block")
    h.world.failures.clear()
    second = await player(h, "Ушёл")
    async with database() as db:
        await consent(db, second, "pets")
        await push(db, second, "pets", "w")
        await h.blocked_by(second)                                  # Telegram tells the bot at once
        ok(not await repo.pending_rows(db, second.id), "blocking the bot clears the queue without sending anything")
    await say(h, user, user.id, "баланс")                           # the player came back
    async with database() as db:
        await consent(db, user, "pets")
        ok(await push(db, user, "pets", "back"), "writing to the bot again reopens the DM")


@bot_scenario
async def dm_push_pauses_without_reaction(h: Harness) -> None:
    from core import dm_push as rules
    user = await player(h, "Читатель")
    async with database() as db:
        await consent(db, user, "pets")
        for day in range(rules.UNANSWERED_LIMIT):
            ok(await push_at(db, user, "pets", f"d{day}", at(8, day + 1)), f"queued on day {day}")
            await deliver(h, db, at(8, day + 1))
        ok(not await push(db, user, "pets", "after"), "after the limit of unanswered messages nothing is queued")
    await say(h, user, user.id, "привет")
    async with database() as db:
        ok(await push(db, user, "pets", "after"), "the player answered: messages continue")


@bot_scenario
async def dm_push_collectors_find_events_once(h: Harness) -> None:
    from services import dm_push_events
    user = await player(h, "Хозяин питомца")
    async with database() as db:
        await consent(db, user, "pets", "quests", "season", "vip_expiry", "market", "pass")
        await db.execute("INSERT INTO system_flags (key, enabled, label) VALUES ('pets_v2', 1, 'pets') ON CONFLICT (key) DO UPDATE SET enabled = 1")
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id = ?", (user.id,))
        await db.execute(
            "INSERT INTO pet_v2_runs (id, user_id, pet_id, kind, hours, route, status, starts_at, ends_at) "
            "VALUES (?, ?, 1, 'trek', 3, 'forest', 'active', NOW() - INTERVAL '4 hours', NOW() - INTERVAL '1 hour')",
            (f"sim-run-{user.id}", user.id))
        await db.execute("DELETE FROM vip_subscriptions WHERE user_id = ?", (user.id,))
        await db.execute("INSERT INTO vip_subscriptions (user_id, tier, expires_at, total_days) VALUES (?, 'vip', NOW() + INTERVAL '2 days', 30)", (user.id,))
        await db.commit()
        now = datetime.now(timezone.utc)
        first = await dm_push_events.collect(db, now)
        ok(first["pets"] >= 1 and first["quests"] >= 1 and first["vip_expiry"] >= 1, f"events found: {first}")
        second = await dm_push_events.collect(db, now)
        ok(second["pets"] == 0 and second["quests"] == 0 and second["vip_expiry"] == 0, f"and not found twice: {second}")
        from infrastructure.repositories import dm_push as repo
        keys = {r["dedup_key"].split(":")[0] for r in await repo.pending_rows(db, user.id)}
        ok({"pet_run", "quests", "vip_end"} <= keys, f"queued keys: {keys}")
        from core import seasons
        end = seasons.season_bounds(seasons.season_number(now))[1]
        near = await dm_push_events.collect(db, end - timedelta(days=2))
        ok(near["season"] >= 1, f"two days before the season ends it is announced: {near}")
        stranger = await player(h, "Без согласия")
        far = await dm_push_events.collect(db, now)
        ok(not await repo.pending_rows(db, stranger.id), "a player without consent gets nothing")
        for name in ("market", "pass"):
            ok(name in far, f"collector {name} runs on this database without errors")
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id = ?", (user.id,))
        await db.execute("DELETE FROM vip_subscriptions WHERE user_id = ?", (user.id,))
        await db.commit()


@bot_scenario
async def dm_plan_and_reward_taken_once(h: Harness) -> None:
    user = await player(h, "Исполнитель")
    sent = await say(h, user, user.id, "план")
    ok("План дня" in said(sent), f"the plan opens: {said(sent)[:120]!r}")
    async with database() as db:
        await db.execute("UPDATE quest_v1_assignments SET completed_at = NOW(), progress = target WHERE user_id = ? AND period = 'daily'", (user.id,))
        await db.commit()
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (user.id,)) as c:
            before = float((await c.fetchone())[0])
    await say(h, user, user.id, "план")
    plan = last_message(h, user.id, "План дня")
    ok("Награда за задания дня готова" in plan.text, f"the finished set is offered: {plan.text[:200]!r}")
    stale = copy.copy(plan)                                          # the message as the player saw it before the first tap
    async def balance() -> float:
        async with database() as db:
            async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (user.id,)) as c:
                return float((await c.fetchone())[0])

    first = await h.click(user, user.id, plan, "Забрать: дня")
    ok(first.answered and "Забрано" in first.text, f"the first tap pays: {first.text!r}")
    paid = await balance()
    ok(paid - before >= 20, f"the reward arrived: {before} -> {paid}")
    second = await h.click(user, user.id, stale, "Забрать: дня")      # an impatient second tap on the same old button
    ok(second.answered and "уже забрал" in second.text, f"the second tap is told it is done: {second.text!r}")
    ok(await balance() == paid, "and nothing is paid the second time")
    ok("Награда за задания дня готова" not in last_message(h, user.id, "План дня").text, "the plan no longer offers it")


@bot_scenario
async def dm_push_goes_to_the_topic_or_the_main_chat(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    with_topics = await player(h, "С темами")
    h.world.topics_enabled.add(with_topics.id)
    without = await player(h, "Без тем")
    async with database() as db:
        for user in (with_topics, without):
            await consent(db, user, "pets", "quests")
        await db.execute("DELETE FROM dm_push_topics WHERE user_id = ANY(?::bigint[])", ([with_topics.id, without.id],))
        await push(db, with_topics, "pets", "p1")
        await push(db, without, "pets", "p1")
        await deliver(h, db, at(8))
        sent = to_player(h, with_topics)[-1]
        ok(sent.get("message_thread_id"), f"with topics the message lands in a topic: {sent}")
        topic = await repo.get_topic(db, with_topics.id, "pets")
        ok(topic["thread_id"] == sent["message_thread_id"], "and the topic is remembered")
        plain = to_player(h, without)[-1]
        ok(not plain.get("message_thread_id"), "without topics it is the main chat, no error")
        await push_at(db, with_topics, "pets", "p2", at(8, 1))
        await deliver(h, db, at(8, 1))
        ok(to_player(h, with_topics)[-1].get("message_thread_id") == topic["thread_id"], "the next message reuses the same topic")
        await h.bot.delete_forum_topic(with_topics.id, topic["thread_id"])      # the player deleted the topic
        await push_at(db, with_topics, "pets", "p3", at(8, 2))
        await deliver(h, db, at(8, 2))
        ok(not to_player(h, with_topics)[-1].get("message_thread_id"), "a deleted topic falls back to the main chat")
        await push_at(db, with_topics, "quests", "q1", at(8, 3))
        await deliver(h, db, at(8, 3))
        ok(to_player(h, with_topics)[-1].get("message_thread_id"), "another kind of message gets its own topic")
