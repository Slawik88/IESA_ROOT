"""Whole-bot scenarios: forum topics (groups and DMs) and the failures that hit real bots (blocked DM, flood limit)."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import said, say, sim_friends
from tools.mafia_sim.world import TgError


@bot_scenario
async def group_topic_reply_stays_in_topic(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    sent = await say(h, player, group, "бот баланс", topic=77)
    ok(sent and all(p.get("message_thread_id") == 77 for _, p in sent), f"the answer goes to the topic it was asked in: {sent!r}")
    plain_group = await say(h, player, group, "бот баланс")
    ok(plain_group and all(not p.get("message_thread_id") for _, p in plain_group), "and a general-chat question stays in the general chat")
    reply_thread = await say(h, player, group, "бот баланс", topic=88, forum=False)   # reply chain in a plain supergroup
    ok(reply_thread and said(reply_thread), "a plain reply thread (not a forum) is answered too")


@bot_scenario
async def dm_topic_reply_stays_in_topic(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    h.world.topics_enabled.add(player.id)                    # the player switched topics on in the DM with the bot
    sent = await say(h, player, player.id, "баланс", topic=9)
    ok(sent and all(p.get("message_thread_id") == 9 for _, p in sent), f"a DM topic is answered inside the topic: {sent!r}")
    plain_dm = await say(h, player, player.id, "баланс")
    ok(plain_dm and all(not p.get("message_thread_id") for _, p in plain_dm), "the main DM stays the main DM")


@bot_scenario
async def private_topics_api_rules(h: Harness) -> None:
    """What S23 will rely on: topics can be created in a DM only when the player has them switched on."""
    on, off = h.user("С темами"), h.user("Без тем")
    h.world.topics_enabled.add(on.id)
    topic = await h.bot.create_forum_topic(on.id, "Задания")
    ok(topic.name == "Задания" and topic.message_thread_id, f"a DM topic is created: {topic}")
    note = await h.bot.send_message(on.id, "В теме", message_thread_id=topic.message_thread_id)
    ok(note.message_thread_id == topic.message_thread_id, "and a message can be posted into it")
    try:
        await h.bot.create_forum_topic(off.id, "Задания")
        raise AssertionError("a DM without topics must refuse topic creation")
    except TelegramBadRequest:
        pass
    try:
        await h.bot.send_message(off.id, "x", message_thread_id=topic.message_thread_id)
        raise AssertionError("posting into a thread of a DM without topics must fail")
    except TelegramBadRequest:
        pass
    await h.bot.delete_forum_topic(on.id, topic.message_thread_id)
    try:
        await h.bot.send_message(on.id, "x", message_thread_id=topic.message_thread_id)
        raise AssertionError("a deleted topic cannot be written to")
    except TelegramBadRequest:
        pass


@bot_scenario
async def blocked_player_does_not_break_the_bot(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == player.id,
                 TgError(403, "Forbidden: bot was blocked by the user"), times=2)
    for _ in range(2):
        try:
            await say(h, player, player.id, "баланс")
            raise AssertionError("the blocked-bot error must surface to the dispatcher (it is counted and logged there)")
        except TelegramForbiddenError:
            pass
    ok("Баланс" in said(await say(h, player, group, "бот баланс")), "the same player is still served in the group")
    ok("Баланс" in said(await say(h, player, player.id, "баланс")), "and in the DM once the block is lifted")


@bot_scenario
async def flood_limit_surfaces_as_retry_after(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    h.world.fail(lambda n, p: n == "SendMessage" and int(p["chat_id"]) == group,
                 TgError(429, "Too Many Requests: retry after 3", 3), times=1)
    try:
        await say(h, player, group, "бот баланс")
        raise AssertionError("a flood answer must surface as TelegramRetryAfter")
    except TelegramRetryAfter as flood:
        ok(flood.retry_after == 3, f"the wait Telegram asked for is kept: {flood.retry_after}")
    ok("Баланс" in said(await say(h, player, group, "бот баланс")), "the next command works once the flood is over")
