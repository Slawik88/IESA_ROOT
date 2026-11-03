"""Telegram updates beyond plain messages and button presses, for the simulator's :class:`Harness`.

Payments (pre-checkout and the paid-message), the bot being added to or removed from a chat, other members
joining and leaving, and Telegram Business (connection, incoming/edited/deleted business messages).
Each feeder builds the update the way Telegram sends it, so aiogram parses it exactly as in production.
"""
from __future__ import annotations

import time
from typing import Any

from tools.mafia_sim.errors import BOT_ID, BOT_USERNAME
from tools.mafia_sim.world import StoredMessage

BOT_JSON = {"id": BOT_ID, "is_bot": True, "first_name": "Sim", "username": BOT_USERNAME}


class UpdateFeeds:
    """Mixed into Harness; relies on ``self.world``, ``self._feed``, ``self._ids`` and ``self._chat_json``."""

    # ── Stars payments ──────────────────────────────────────────────────────
    async def pre_checkout(self, user, payload: str, stars: int, *, currency: str = "XTR") -> dict:
        """The player confirms an invoice; returns the bot's answer to Telegram (``ok`` and ``error``)."""
        before = len(self.world.precheckout_answers)
        query_id = str(next(self._ids))
        await self._feed({"pre_checkout_query": {"id": query_id, "from": user.json(), "currency": currency,
                                                 "total_amount": stars, "invoice_payload": payload}})
        got = self.world.precheckout_answers[before:]
        assert got and got[-1]["id"] == query_id, "the bot must answer every pre-checkout query"
        return got[-1]

    async def paid(self, user, payload: str, stars: int, charge_id: str, *, currency: str = "XTR") -> int:
        """Telegram reports a completed payment (a service message in the player's DM)."""
        message_id = self.world.next_id = self.world.next_id + 1
        await self._feed({"message": {
            "message_id": message_id, "date": int(time.time()), "chat": self._chat_json(user.id, user), "from": user.json(),
            "successful_payment": {"currency": currency, "total_amount": stars, "invoice_payload": payload,
                                   "telegram_payment_charge_id": charge_id, "provider_payment_charge_id": f"prov-{charge_id}"}}})
        return message_id

    # ── the bot and other members in a chat ─────────────────────────────────
    def _member_json(self, chat_id: int, user_id: int, status: str, **flags: Any) -> dict:
        self.world.set_member(chat_id, user_id, status, **flags)
        member = self.world._m_GetChatMember({"chat_id": chat_id, "user_id": user_id})
        if user_id == BOT_ID:
            member["user"] = BOT_JSON
        return member

    async def bot_membership(self, chat_id: int, actor, old: str, new: str, **flags: Any) -> None:
        """``my_chat_member``: the bot was added (``left`` → ``administrator``), removed (→ ``kicked``/``left``) or blocked."""
        old_member = self._member_json(chat_id, BOT_ID, old, **({"can_delete_messages": True} if old == "administrator" else {}))
        new_member = self._member_json(chat_id, BOT_ID, new, **flags)
        await self._feed({"my_chat_member": {"chat": self._chat_json(chat_id, actor), "from": actor.json(),
                                             "date": int(time.time()), "old_chat_member": old_member,
                                             "new_chat_member": new_member}})

    async def blocked_by(self, user) -> None:
        """The player blocks the bot in the DM (Telegram: ``my_chat_member`` member → kicked in a private chat)."""
        member = {"status": "kicked", "user": BOT_JSON, "until_date": 0}
        await self._feed({"my_chat_member": {"chat": self._chat_json(user.id, user), "from": user.json(), "date": int(time.time()),
                                             "old_chat_member": {"status": "member", "user": BOT_JSON}, "new_chat_member": member}})
        self.world.dm_open.discard(user.id)

    async def member_change(self, chat_id: int, user, actor, old: str, new: str) -> None:
        """``chat_member``: ``user`` joined (``left`` → ``member``), left or was removed by ``actor``."""
        old_member = self._member_json(chat_id, user.id, old)
        new_member = self._member_json(chat_id, user.id, new)
        old_member["user"] = new_member["user"] = user.json()
        await self._feed({"chat_member": {"chat": self._chat_json(chat_id, actor), "from": actor.json(), "date": int(time.time()),
                                          "old_chat_member": old_member, "new_chat_member": new_member}})

    # ── Telegram Business ───────────────────────────────────────────────────
    async def business_connect(self, owner, connection_id: str, *, enabled: bool = True, **rights: Any) -> dict:
        """``business_connection``: a player connects (or disconnects) the bot to their account."""
        connection = self.world.add_business_connection(connection_id, owner.json(), enabled=enabled, **rights)
        await self._feed({"business_connection": connection})
        return connection

    def _business_message(self, connection_id: str, sender, partner, text: str, message_id: int | None = None) -> dict:
        if message_id is None:
            message_id = self.world.next_id = self.world.next_id + 1
        return {"message_id": message_id, "date": int(time.time()), "chat": self._chat_json(partner.id, partner),
                "from": sender.json(), "text": text, "business_connection_id": connection_id}

    async def business_say(self, connection_id: str, sender, partner, text: str) -> int:
        """A message in a private chat of the account owner: ``sender`` is the owner or ``partner``."""
        message = self._business_message(connection_id, sender, partner, text)
        self.world.messages[(partner.id, message["message_id"])] = StoredMessage(partner.id, message["message_id"], text, None, html=text)
        await self._feed({"business_message": message})
        return message["message_id"]

    async def business_edit(self, connection_id: str, sender, partner, message_id: int, text: str) -> None:
        message = self._business_message(connection_id, sender, partner, text, message_id)
        message["edit_date"] = message["date"]
        await self._feed({"edited_business_message": message})

    async def business_delete(self, connection_id: str, partner, message_ids: list[int]) -> None:
        await self._feed({"deleted_business_messages": {"business_connection_id": connection_id,
                                                        "chat": self._chat_json(partner.id, partner), "message_ids": message_ids}})
