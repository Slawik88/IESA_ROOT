"""Player rollout: real private menus, read-only pages, recovery and retained snapshot limits."""

from __future__ import annotations

import json

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_dm_push import player


def newest(h, user):
    return next(key for key in reversed(h.world.widgets) if key[0] == user.id)


@bot_scenario
async def player_cards_cover_personal_menus_and_native_navigation(h: Harness):
    user = await player(h, "Карточки", write=False)
    await h.say(user, user.id, "/start")
    for command in (
        "план",
        "уведомления",
        "квесты",
        "пропуск",
        "питомцы",
        "баланс",
        "достижения",
        "помощь",
        "бизнес",
        "я",
    ):
        before = len(h.world.widgets)
        await h.say(user, user.id, "бот " + command)
        ok(
            len(h.world.widgets) > before,
            f"{command}: a player receives a widget by default",
        )
        key = newest(h, user)
        stored = h.world.messages[key]
        ok(
            stored.text and "Меню Предвестника" not in stored.text,
            "actual pages, not just a caption",
        )
        rows = await h.sql(
            "SELECT ready,seen_revision,revision FROM predvestnik.widget_card_views WHERE bot_id=$1 AND chat_id=$2 AND message_id=$3",
            h.bot.id,
            *key,
        )
        ok(
            rows[0]["ready"] and rows[0]["seen_revision"] == rows[0]["revision"],
            "rendered version is acknowledged",
        )
    await h.say(user, user.id, "бот уведомления")
    key = newest(h, user)
    settings = h.world.messages[key]
    action = next(
        button
        for button in settings.buttons()
        if button.get("callback_data", "").startswith("dn:t:")
    )
    old_revision = json.loads(h.world.widgets[key]["chat_data"])["r"]
    result = await h.click(user, user.id, settings, contains=action["text"])
    ok(result.answered, "native settings callback still answers")
    ok(
        json.loads(h.world.widgets[key]["chat_data"])["r"] > old_revision,
        "existing edit_text updates widget state",
    )


@bot_scenario
async def player_cards_old_clients_require_text_before_actions(h: Harness):
    user = await player(h, "Без карточек", write=False)
    await h.say(user, user.id, "/start")
    h.auto_render_cards = False
    try:
        await h.say(user, user.id, "бот уведомления")
        key = newest(h, user)
        card = h.world.messages[key]
        action = next(
            button
            for button in card.buttons()
            if button.get("callback_data", "").startswith("dn:t:")
        )
        before = await h.sql(
            "SELECT revision FROM predvestnik.widget_card_views WHERE message_id=$1 AND chat_id=$2",
            key[1],
            key[0],
        )
        answer = await h.click(user, user.id, card, contains=action["text"])
        ok("Текстовый режим" in answer.text, "old clients cannot use opaque actions")
        after = await h.sql(
            "SELECT revision FROM predvestnik.widget_card_views WHERE message_id=$1 AND chat_id=$2",
            key[1],
            key[0],
        )
        ok(before == after, "denied action does not edit the card")
        await h.click(user, user.id, card, contains="Текстовый режим")
        ok(
            "Уведомления" in h.world.last(user.id).text,
            "full native readable text is delivered",
        )
        copied = h.world.last(user.id)
        ok(
            not copied.markup,
            "signed domain buttons aren't copied to another message id",
        )
        count = len(h.world.widgets)
        await h.say(user, user.id, "бот план")
        ok(len(h.world.widgets) == count, "text preference applies to future menus")
        await h.say(user, user.id, "бот виджеты вкл")
        await h.say(user, user.id, "бот план")
        ok(len(h.world.widgets) > count, "player can enable cards again")
    finally:
        h.auto_render_cards = True


@bot_scenario
async def player_cards_bind_private_pages_and_expire_deleted_accounts(h: Harness):
    from services import widget_cards as service
    from infrastructure.telegram_widgets import WidgetQuery
    from tools.mafia_sim.scn_bot_widgets import database

    user = await player(h, "Приватность", write=False)
    stranger = h.user("Другой")
    await h.say(user, user.id, "/start")
    await h.say(user, user.id, "бот план")
    key = newest(h, user)
    state = json.loads(h.world.widgets[key]["chat_data"])
    request = f"card:p:{state['k']}:0:{state['r']}"
    foreign = await h.widget_query(stranger, key[1], request, chat_id=user.id)
    ok("e" in json.loads(foreign["data"]), "another player cannot read a private menu")
    raw = dict(
        id="q",
        **{"from": {"id": user.id}},
        chat={"id": user.id, "type": "private"},
        message_id=key[1],
        data=request,
    )
    async with database() as db:
        wrong = await service.answer(db, WidgetQuery.model_validate(raw), h.bot.id + 1)
        ok(
            "e" in json.loads(wrong),
            "same message id on a different bot cannot read the snapshot",
        )
    await h.sql(
        "UPDATE predvestnik.users SET deleted_at=NOW() WHERE user_tg_id=$1", user.id
    )
    denied = await h.widget_query(user, key[1], request)
    ok(
        "e" in json.loads(denied["data"]),
        "pending account deletion blocks saved content",
    )
    await h.sql(
        "UPDATE predvestnik.users SET deleted_at=NULL WHERE user_tg_id=$1", user.id
    )
    await h.sql(
        "UPDATE predvestnik.widget_card_views SET expires_at=NOW()-INTERVAL '1 second' WHERE owner_id=$1",
        user.id,
    )
    expired = await h.widget_query(user, key[1], request)
    ok("e" in json.loads(expired["data"]), "old snapshots expire")


@bot_scenario
async def player_cards_retention_is_bounded_and_cleanup_is_idempotent(h: Harness):
    from infrastructure.repositories import widget_cards as repo
    from core import widget_cards as rules
    from tools.mafia_sim.scn_bot_widgets import database

    user = await player(h, "Лимит", write=False)
    await h.say(user, user.id, "/start")
    async with database() as db:
        for _ in range(rules.MAX_USER_CARDS + 3):
            last = await repo.create(db, h.bot.id, user.id, "plan", "План", "HTML")
        rows = await h.sql(
            "SELECT token FROM predvestnik.widget_card_views WHERE owner_id=$1", user.id
        )
        ok(
            len(rows) == rules.MAX_USER_CARDS
            and last["token"] in [row["token"] for row in rows],
            "bounded snapshots keep newest even with same transaction timestamps",
        )
        await h.sql(
            "UPDATE predvestnik.widget_card_views SET created_at=NOW()-INTERVAL '6 minutes' WHERE owner_id=$1",
            user.id,
        )
        await repo.cleanup(db)
        await repo.cleanup(db)
    rows = await h.sql(
        "SELECT token FROM predvestnik.widget_card_views WHERE owner_id=$1", user.id
    )
    ok(not rows, "unbound deliveries are cleaned without a new scheduler loop")
