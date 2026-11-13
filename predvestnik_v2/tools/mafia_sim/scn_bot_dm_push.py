"""Whole-bot scenarios: notifications to the DM (S23) — consent, DM gate, quiet hours, daily cap, digest, blocked bot,
flood limit, pause without reaction, topics, event collectors with the button, the plan of the day, a reward that cannot be
taken twice, slash commands, deleted accounts and a queue that sleeping players cannot block.

The test clock: ``deliver_due(now=...)`` takes the moment as a parameter, so night and days are checked without waiting.
Time only moves forward inside a scenario (a player who must wait gets a ``next_check_at`` mark)."""
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
        for table in ("dm_push_outbox", "dm_push_settings", "dm_push_topics"):
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user.id,))
        await db.execute("DELETE FROM user_notification_prefs WHERE user_id = ?", (user.id,))
        await db.execute("DELETE FROM vip_v2_preferences WHERE user_id = ?", (user.id,))
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) VALUES (?, ?, ?) ON CONFLICT (user_tg_id) DO NOTHING",
                         (user.id, f"sim{user.id}", name))
        await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (user.id,))
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


async def push_at(db, user, cat: str, key: str, when: datetime, text: str = "🐾 Событие") -> bool:
    """Queue an event that, for the test clock, was born at ``when``."""
    queued = await push(db, user, cat, key, text)
    await db.execute("UPDATE dm_push_outbox SET created_at = ? WHERE user_id = ? AND dedup_key = ?", (when, user.id, key))
    return queued


async def deliver(h: Harness, db, now: datetime, **kw) -> dict:
    """One delivery pass at the test moment ``now``; what it sends is stamped with ``now`` (the daily cap reads sent_at)."""
    from bot.chat.notify import markup_for
    from services import dm_push
    async with db.execute("SELECT id FROM dm_push_outbox WHERE sent_at IS NOT NULL") as c:
        before = [int(r[0]) for r in await c.fetchall()]
    stats = await dm_push.deliver_due(h.bot, db, now=now, markup=markup_for, **kw)
    await db.execute("UPDATE dm_push_outbox SET sent_at = ? WHERE sent_at IS NOT NULL AND NOT (id = ANY(?::bigint[]))", (now, before))
    await db.commit()
    return stats


@bot_scenario
async def dm_push_settings_screen_and_consent(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    user = await player(h, "Игрок", write=False)
    sent = await say(h, user, user.id, "уведомления")
    screen = last_message(h, user.id, "Уведомления в личку")
    ok("ничего" in said(sent), f"nothing is on by default: {said(sent)[:160]!r}")
    ok(all(not b["text"].startswith("✅") for b in screen.buttons() if b.get("callback_data", "").startswith("dn:t:")), "no category is switched on")
    await h.click(user, user.id, screen, "Питомцы")
    async with database() as db:
        ok("pets" in await repo.consented(db, user.id), "tapping a category gives the consent")
        ok((await repo.get_settings(db, user.id))["dm_confirmed_at"] is not None, "the tap also confirms the DM")
    screen = last_message(h, user.id, "Уведомления в личку")
    ok(any(b["text"].startswith("✅") and "Питомцы" in b["text"] for b in screen.buttons()), "the screen shows the category as on")
    await h.click(user, user.id, screen, "Питомцы")
    async with database() as db:
        ok("pets" not in await repo.consented(db, user.id), "a second tap takes the consent back")
    group_user = await player(h, "Из группы")
    group = h.new_chat([group_user])
    ok("в личке" in said(await say(h, group_user, group, "бот уведомления")), "in a group the player is sent to the DM")
    ok("в личке" in said(await say(h, group_user, group, "бот план")), "and the plan is not shown in a group either")
    await say(h, user, user.id, "бот уведомления пояс +5")
    async with database() as db:
        ok((await repo.get_settings(db, user.id))["tz_offset"] == 5, "the time zone is set by the command")
    ok("Не понял пояс" in said(await say(h, user, user.id, "бот уведомления пояс +99")), "an impossible zone is refused")
    hint = await say(h, user, user.id, "бот уведомления тихие")
    async with database() as db:
        ok((await repo.get_settings(db, user.id))["quiet_enabled"] is True, "an unclear «тихие» does not switch the quiet hours off")
    ok("тихие вкл" in said(hint), "and the player is shown how to write it")
    await say(h, user, user.id, "бот уведомления тихие выкл")
    async with database() as db:
        ok((await repo.get_settings(db, user.id))["quiet_enabled"] is False, "«тихие выкл» switches them off")


@bot_scenario
async def dm_push_slash_commands_from_the_menu(h: Harness) -> None:
    user = await player(h, "Из меню", write=False)
    plan = await say(h, user, user.id, "/plan")
    ok("План дня" in said(plan), f"/plan from the «/» menu works: {said(plan)[:100]!r}")
    notify = await say(h, user, user.id, "/notify")
    ok("Уведомления в личку" in said(notify), f"/notify from the «/» menu works: {said(notify)[:100]!r}")
    async with database() as db:
        from infrastructure.repositories import dm_push as repo
        ok((await repo.get_settings(db, user.id))["dm_confirmed_at"] is not None, "and it confirms the DM")


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
        async with db.execute("SELECT dm_confirmed_at FROM vip_v2_preferences WHERE user_id = ?", (quiet.id,)) as c:
            vip = await c.fetchone()
        ok(vip and vip[0] is not None, "the VIP reminder condition dm_confirmed_at is set by a private message (it was never set before)")
        await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (quiet.id,))
        await db.commit()
        ok(not await push(db, quiet, "quests", "q2"), "an account that is being deleted gets nothing")
        stats = await deliver(h, db, at(8, 1))
        ok(stats["sent"] == 0 and not await repo.pending_rows(db, quiet.id), f"and its queue is cleared, nothing is sent: {stats}")
        await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (quiet.id,))
        await db.commit()


@bot_scenario
async def dm_push_quiet_hours_digest_and_daily_cap(h: Harness) -> None:
    user = await player(h, "Сова")
    async with database() as db:
        await consent(db, user, "pets", "quests", "market", "season")
        for n, cat in enumerate(("pets", "quests", "market")):
            await push_at(db, user, cat, f"e{n}", at(18), f"🔔 Событие {n}\nПодробности")
        start = len(h.world.calls)
        night = await deliver(h, db, at(20))                       # 23:00 по Москве
        ok(night["sent"] == 0 and not to_player(h, user, start), f"nothing is sent in the quiet hours: {night}")
        again = await deliver(h, db, at(21))
        ok(again["waiting"] == 0, f"and the sleeping player is not looked at again until morning: {again}")
        morning = await deliver(h, db, at(8, 1))                   # 11:00 по Москве следующего дня
        sent = to_player(h, user, start)
        ok(len(sent) == 1 and morning["digests"] == 1, f"three events are one digest: {len(sent)} message(s)")
        ok(all(f"Событие {n}" in sent[0]["text"] for n in range(3)) and "Подробности" not in sent[0]["text"], "the digest lists each event on one line")
        ok(sent[0]["reply_markup"] and "dn:plan" in str(sent[0]["reply_markup"]), "the digest carries the «План дня» button")
        for n in range(3, 5):                                       # ещё два одиночных: всего 3 сообщения за сутки
            await push_at(db, user, "pets", f"s{n}", at(8, 1))
            await deliver(h, db, at(9 + n, 1))
        ok(len(to_player(h, user, start)) == 3, "three messages in a day are the limit so far")
        await push_at(db, user, "pets", "over", at(8, 1))
        await deliver(h, db, at(15, 1))
        ok(len(to_player(h, user, start)) == 3, "the fourth waits: the daily limit")
        await deliver(h, db, at(12, 2))
        ok(len(to_player(h, user, start)) == 4, "and goes out when the day has passed")
        await push(db, user, "pets", "old")
        await db.execute("UPDATE dm_push_outbox SET created_at = ? WHERE user_id = ? AND dedup_key = 'old'", (at(8, 2) - timedelta(hours=40), user.id))
        before = len(to_player(h, user, start))
        stats = await deliver(h, db, at(12, 5))
        ok(len(to_player(h, user, start)) == before and stats["dropped"] >= 1, f"an event nobody could deliver in time is dropped: {stats}")


@bot_scenario
async def dm_push_sleeping_players_do_not_block_the_queue(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    night_a, night_b, awake = await player(h, "Ночь А"), await player(h, "Ночь Б"), await player(h, "Днём")
    async with database() as db:
        for user in (night_a, night_b, awake):
            await consent(db, user, "pets")
        await repo.set_tz(db, awake.id, -8)                          # 20:00 UTC — у него день
        await push_at(db, night_a, "pets", "k", at(10))
        await push_at(db, night_b, "pets", "k", at(11))
        await push_at(db, awake, "pets", "k", at(12))                # самое новое событие
        first = await deliver(h, db, at(20), limit=2)
        ok(first["waiting"] == 2 and first["sent"] == 0, f"the two oldest are night sleepers: {first}")
        second = await deliver(h, db, at(20), limit=2)
        ok(second["sent"] == 1 and len(to_player(h, awake)) >= 1, f"so they do not take the place of the one who is awake: {second}")


@bot_scenario
async def dm_push_blocked_bot_and_flood_do_not_avalanche(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    user = await player(h, "Занятой")
    async with database() as db:
        await consent(db, user, "pets")
        await push_at(db, user, "pets", "x", at(7))
        h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == user.id, TgError(429, "Too Many Requests: retry after 7", 7), times=1)
        stats = await deliver(h, db, at(8))
        ok(stats["retry_after"] == 7 and stats["sent"] == 0, f"Telegram asked to wait: {stats}")
        ok(len(await repo.pending_rows(db, user.id)) == 1, "the event stays queued, no immediate retry")
        stats = await deliver(h, db, at(8))
        ok(stats["sent"] == 1, "and goes out on the next pass")
        await push_at(db, user, "pets", "y", at(8))
        h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == user.id,
                     TgError(403, "Forbidden: bot was blocked by the user"), times=5)
        stats = await deliver(h, db, at(9))
        ok(stats["unreachable"] == 1, f"a blocked bot is noticed from the failed send: {stats}")
        ok(not await repo.pending_rows(db, user.id), "the queue of that player is cleared")
        ok(not await push(db, user, "pets", "z"), "nothing new is queued for an unreachable DM")
        calls = len(to_player(h, user))
        await deliver(h, db, at(10))
        ok(len(to_player(h, user)) == calls, "no more attempts after the block")
    h.world.failures.clear()
    second = await player(h, "Ушёл")
    async with database() as db:
        await consent(db, second, "pets")
        await push(db, second, "pets", "w")
        await h.blocked_by(second)                                  # Telegram tells the bot at once
        ok(not await repo.pending_rows(db, second.id), "blocking the bot clears the queue without sending anything")
    flaky = await player(h, "Сеть")
    async with database() as db:
        await consent(db, flaky, "pets")
        await push_at(db, flaky, "pets", "n", at(7, 3))
        h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == flaky.id, TgError(502, "Bad Gateway"), times=9)
        for minutes in (0, 6, 12, 18):                              # the network keeps failing: three attempts, then the event is dropped
            await deliver(h, db, at(8, 3) + timedelta(minutes=minutes))
        ok(not await repo.pending_rows(db, flaky.id), "an event that fails again and again is dropped after three attempts")
    h.world.failures.clear()
    await say(h, user, user.id, "баланс")                           # the first player came back
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
async def dm_push_collectors_find_events_and_the_button_arrives(h: Harness) -> None:
    from services import dm_push_events
    from infrastructure.repositories import dm_push as repo
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
        rows = await repo.pending_rows(db, user.id)
        keys = {r["dedup_key"].split(":")[0] for r in rows}
        ok({"pet_run", "quests", "vip_end"} <= keys, f"queued keys: {keys}")
        ok(all(isinstance(r["button"], dict) for r in rows if r["button"]), "the button comes back from the database as a dict, not a string")
        await db.execute("DELETE FROM dm_push_outbox WHERE user_id = ? AND dedup_key NOT LIKE 'pet_run:%'", (user.id,))   # one message, one button
        await db.execute("UPDATE dm_push_outbox SET created_at = ? WHERE user_id = ?", (at(7, 1), user.id))
        await db.commit()
        start = len(h.world.calls)
        sent = await deliver(h, db, at(8, 1))
        message = to_player(h, user, start)
        ok(len(message) == 1, f"the pet message is delivered, once: {sent}")
        ok(message[0]["reply_markup"] and "miniapp.example" in str(message[0]["reply_markup"]),
           f"with its «К питомцам» button that opens the app: {message[0].get('reply_markup')}")
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
    async with database() as db:
        await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (user.id,))
        await db.commit()
    refused = await h.click(user, user.id, stale, "Забрать: дня")
    ok(refused.answered and "недоступно" in refused.text, f"an account that is being deleted takes nothing here: {refused.text!r}")
    async with database() as db:
        await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (user.id,))
        await db.commit()


@bot_scenario
async def dm_push_goes_to_the_topic_or_the_main_chat(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    with_topics = await player(h, "С темами")
    h.world.topics_enabled.add(with_topics.id)
    without = await player(h, "Без тем")
    async with database() as db:
        for user in (with_topics, without):
            await consent(db, user, "pets", "quests")
        await push_at(db, with_topics, "pets", "p1", at(7))
        await push_at(db, without, "pets", "p1", at(7))
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


@bot_scenario
async def dm_push_vip_reminder_uses_the_same_rules(h: Harness) -> None:
    from services import dm_push_events
    from infrastructure.repositories import dm_push as repo
    vip, plain = await player(h, "ВИП"), await player(h, "ВИП без согласия")
    async with database() as db:
        for user in (vip, plain):
            await db.execute("DELETE FROM vip_subscriptions WHERE user_id = ?", (user.id,))
            await db.execute("INSERT INTO vip_subscriptions (user_id, tier, expires_at, total_days) VALUES (?, 'vip', NOW() + INTERVAL '20 days', 30)", (user.id,))
        await consent(db, vip, "vip_expiry")
        await db.commit()
        evening = datetime.now(timezone.utc).replace(hour=19, minute=0, second=0, microsecond=0)
        queued = await dm_push_events.vip_daily_reminders(db, evening)
        ok(queued >= 1, f"a VIP with consent gets the reminder queued: {queued}")
        ok(await repo.pending_rows(db, vip.id) and not await repo.pending_rows(db, plain.id), "and a VIP without consent gets nothing")
        again = await dm_push_events.vip_daily_reminders(db, evening)
        ok(not [r for r in await repo.pending_rows(db, vip.id) if r["dedup_key"].startswith("vip_daily")][1:], f"it is queued once a day: {again}")
        start = len(h.world.calls)
        await deliver(h, db, evening + timedelta(hours=1))           # 22:00 UTC is already night for the player: it waits for the morning
        ok(not to_player(h, vip, start), "in the quiet hours the VIP reminder waits too (it did not before)")
        await repo.touch_contact(db, vip.id)
        await db.execute("UPDATE dm_push_outbox SET created_at = ? WHERE user_id = ?", (evening + timedelta(hours=12), vip.id))
        await deliver(h, db, evening + timedelta(hours=16))
        ok(len(to_player(h, vip, start)) == 1, "and arrives in the morning")
        await db.execute("DELETE FROM vip_subscriptions WHERE user_id = ANY(?::bigint[])", ([vip.id, plain.id],))
        await db.commit()



@bot_scenario(volatile=True)
async def dm_evening_digest_is_opt_in_and_never_arrives_next_morning(h: Harness) -> None:
    from infrastructure.repositories import dm_push as repo
    from services import dm_plan, dm_push_events
    from unittest.mock import patch

    subscribed = await player(h, "Вечерняя сводка")
    morning_only = await player(h, "Только утро")
    delayed = await player(h, "Опоздавшая сводка")
    now = at(16)  # 19:00 at the default +3.
    async with database() as db:
        await consent(db, subscribed, "digest_evening")
        await consent(db, delayed, "digest_evening")
        await consent(db, morning_only, "digest")
        await db.commit()
        with patch.object(dm_plan, "evening_text", return_value="🌙 <b>Итоги дня</b>\nЗадания дня: сделано 2 из 3."):
            ok(await dm_push_events._evening(db, now - timedelta(minutes=1)) == 0, "not before 19:00")
            ok(await dm_push_events._evening(db, now) == 2, "both and only the explicit evening subscribers")
            ok(await dm_push_events._evening(db, now + timedelta(minutes=1)) == 0, "once per local day")
        await repo.defer(db, delayed.id, now + timedelta(hours=14))
        await db.commit()
        start = len(h.world.calls)
        await deliver(h, db, now)
        ok(len(to_player(h, subscribed, start)) == 1, "the evening subscriber receives one message")
        ok(not to_player(h, morning_only, start), "morning consent alone grants no evening messages")
        await deliver(h, db, now + timedelta(hours=14))
        ok(not to_player(h, delayed, start) and not await repo.pending_rows(db, delayed.id),
           "a digest deferred overnight is discarded")


@bot_scenario(volatile=True)
async def dm_chest_button_opens_only_its_own_key_once(h: Harness) -> None:
    from infrastructure.repositories import chests_v1 as repo, dm_push as push_repo, economy_ledger, system_flags
    from services import chests_v1, dm_push_events
    from infrastructure.repositories import quests_v1 as quests_repo
    from tools.test_chests_v1_pg import insert_receipt

    user = await player(h, "Ключ в личке")
    other = await player(h, "Ключ без согласия")
    now = at(10)
    async with database() as db:
        original = await system_flags.is_enabled(db, "content_chests_v1")
        await system_flags.set_flag(db, "content_chests_v1", True)
        await economy_ledger.ensure_tables(db)
        await repo.ensure_tables(db)
        await quests_repo.ensure_tables(db)
        await consent(db, user, "chests")
        try:
            for owner in (user, other):
                await insert_receipt(db, owner.id, "daily", "daily:2026-09-12")
                await chests_v1.grant_quest_completion_key(db, user_id=owner.id, reward_kind="daily", reward_id="daily:2026-09-12")
            await db.commit()
            ok(await dm_push_events._chests(db, now) >= 1, "only new unspent keys are queued")
            ok(not await push_repo.pending_rows(db, other.id), "no opt-in means no chest reminder")
            ok(await dm_push_events._chests(db, now) == 0, "the same keys are not queued twice")
            await db.commit()
            await deliver(h, db, now)
            # More than one grant can merge into a digest. Exercise the exact same callback on its source notification.
            pending = await repo.get_balance(db, user.id)
            ok(pending >= 1, "the user has a key")
            message = last_message(h, user.id, "Ключ от сундука")
            foreign = await h.click(other, other.id, message, "Открыть за 1 ключ")
            ok("недоступен" in foreign.text, "a forwarded callback cannot open somebody else's key")
            first = await h.click(user, user.id, message, "Открыть за 1 ключ")
            second = await h.click(user, user.id, message, "Открыть за 1 ключ")
            ok("Награда" in first.text and first.text == second.text, "one reward receipt on repeat")
            ok(await repo.get_balance(db, user.id) == pending - 1, "a repeated callback does not spend another key")
        finally:
            await system_flags.set_flag(db, "content_chests_v1", original)


@bot_scenario(volatile=True)
async def dm_exchange_confirms_the_quote_and_casino_rejects_an_old_day(h: Harness) -> None:
    from datetime import date
    from unittest.mock import patch
    from infrastructure.repositories import casino_v1 as casino_repo, system_flags
    from services import casino_v1
    from tools.mafia_sim.scn_bot_payments import _balance, _buy

    user = await player(h, "Кошелёк в личке")
    other = await player(h, "Чужая кнопка")
    async with database() as db:
        invoice = await _buy(h, user, "50⭐")
        await h.paid(user, invoice["payload"], invoice["stars"], f"sim-{h.run_tag}-exchange")
        await say(h, user, user.id, "бот обменять зарники 3")
        message = last_message(h, user.id, "30 Моры")
        rejected = await h.click(other, other.id, message, "Подтвердить обмен")
        ok("устарело" in rejected.text, "a quote is signed for its original player")
        await say(h, user, user.id, "бот обменять зарники 4")
        expired_message = last_message(h, user.id, "40 Моры")
        with patch("bot.chat.notify.time.time", return_value=datetime.now(timezone.utc).timestamp() + 301):
            denied = await h.click(user, user.id, expired_message, "Подтвердить обмен")
        ok("устарело" in denied.text, "an expired confirmation cannot spend")
        first = await h.click(user, user.id, message, "Подтвердить обмен")
        repeat = await h.click(user, user.id, message, "Подтвердить обмен")
        ok("30 Моры" in first.text and "Уже обменяно" in repeat.text, "only one confirmed exchange")
        ok("Зарники: 657" in await _balance(h, user), "exactly three Zarniki were spent")

        original = await system_flags.is_enabled(db, "game_casino_v1")
        await system_flags.set_flag(db, "game_casino_v1", True)
        await casino_repo.ensure_tables(db)
        try:
            try:
                await casino_v1.claim_gift(db, user.id, expected_day=date(2000, 1, 1))
            except casino_v1.CasinoError:
                pass
            else:
                raise AssertionError("a stale gift callback cannot claim a new day's gift")
            await say(h, user, user.id, "бот подарок фортуны")
            gift = last_message(h, user.id, "Подарок Зала Фортуны")
            await system_flags.set_flag(db, "game_casino_v1", False)
            closed = await h.click(user, user.id, gift, "Забрать подарок")
            ok("закрыт" in closed.text, "existing gift buttons respect the flag")
            await system_flags.set_flag(db, "game_casino_v1", True)
            first = await h.click(user, user.id, gift, "Забрать подарок")
            repeat = await h.click(user, user.id, gift, "Забрать подарок")
            ok("Получено" in first.text and "уже получен" in repeat.text, "only one gift per day")
        finally:
            await system_flags.set_flag(db, "game_casino_v1", original)
