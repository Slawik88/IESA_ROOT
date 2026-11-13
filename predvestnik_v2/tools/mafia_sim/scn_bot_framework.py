"""Whole-bot scenarios: the dispatcher as a whole (which updates it asks Telegram for, the identity of the bot)."""
from __future__ import annotations

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok

# Telegram only sends the update types a bot asks for; aiogram derives them from the registered handlers.
# A new handler type (S23: topics, S24: business_*) must show up here on purpose, never by accident.
# S24: business_connection and business_message — the bot in the player's own private chats (Telegram Business)
EXPECTED_UPDATE_TYPES = ["business_connection", "business_message", "callback_query", "chat_member", "edited_message", "message",
                         "my_chat_member", "pre_checkout_query"]


@bot_scenario
async def dispatcher_asks_for_the_expected_updates(h: Harness) -> None:
    used = sorted(h.dp.resolve_used_update_types())
    ok(used == EXPECTED_UPDATE_TYPES, f"update types requested from Telegram changed: {used}")
    h.world.calls.append(("NOTE", {"used_update_types": used}))     # also part of the before/after fingerprint


@bot_scenario
async def bot_identity_and_session(h: Harness) -> None:
    me = await h.bot.me()
    ok(me.is_bot and me.username and me.id, f"the bot identifies itself: {me}")
    ok(h.bot.session.__class__.__name__ == "FakeSession", "the simulator really replaced the HTTP session")


@bot_scenario(volatile=True)
async def library_has_what_topics_and_business_need(h: Harness) -> None:
    """What S23 (topics in a DM) and S24 (Business) need from the installed aiogram.  The old 3.22 library is only reported."""
    import aiogram
    from aiogram.types import User

    version = tuple(int(part) for part in aiogram.__version__.split(".")[:3])
    if version < (3, 24, 0):
        return                      # topics in private chats arrived in aiogram 3.24.0 (Bot API 9.3)
    ok("has_topics_enabled" in User.model_fields, "User.has_topics_enabled is known to the library")
    player = User.model_validate({"id": 1, "is_bot": False, "first_name": "Игрок", "has_topics_enabled": True})
    ok(player.has_topics_enabled is True, "a player with topics switched on is recognised from the update")
    for observer in ("business_connection", "business_message", "edited_business_message", "deleted_business_messages"):
        ok(hasattr(h.dp, observer), f"the dispatcher can route {observer}")


@bot_scenario(volatile=True)
async def member_objects_without_new_fields_are_a_known_gap(h: Harness) -> None:
    """aiogram 3.26+ refuses chat-member objects without fields Telegram's newest Bot API made mandatory (can_edit_tag,
    can_react_to_messages in restricted members, can_send_welcome_messages in administrators since 3.31).  The error is a
    ClientDecodeError, NOT a TelegramAPIError: code written as ``except TelegramAPIError`` around get_chat_member does not catch it.
    This documents that gap (S23/S24 must handle both) and notices when a library version changes it."""
    import aiogram
    from aiogram.exceptions import ClientDecodeError, TelegramAPIError

    version = tuple(int(part) for part in aiogram.__version__.split(".")[:3])
    owner, guest = h.user("Владелец"), h.user("Гость")
    chat = h.new_chat([owner, guest], admins=[owner])
    h.world.set_member(chat, guest.id, "restricted", can_send_messages=False)
    complete = h.world._m_GetChatMember
    newest = {"can_send_welcome_messages", "can_edit_tag", "can_react_to_messages"}
    h.world._m_GetChatMember = lambda params: {k: v for k, v in complete(params).items() if k not in newest}
    try:
        outcomes = {}
        for label, user in (("administrator", owner), ("restricted", guest)):
            try:
                await h.bot.get_chat_member(chat, user.id)
                outcomes[label] = True
            except ClientDecodeError:
                outcomes[label] = False
    finally:
        del h.world._m_GetChatMember
    ok(not issubclass(ClientDecodeError, TelegramAPIError), "a decode error is not a Telegram API error")
    ok(outcomes == {"administrator": version < (3, 31, 0), "restricted": version < (3, 26, 0)},
       f"which incomplete member objects the installed aiogram {aiogram.__version__} still accepts changed: {outcomes}")
