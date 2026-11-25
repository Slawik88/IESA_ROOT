"""More Bot API methods for the fake Telegram: Stars payments, media, forum topics, Business, chat management.

Mixed into :class:`tools.mafia_sim.world.World`.  Like the base methods, these reject what the real Bot API
rejects (invoice limits, topics in a private chat that has them switched off, a closed Business connection),
so a bot that survives them is checked against Telegram's rules, not against a lenient mock.
"""
from __future__ import annotations

import random
import time
import zlib
from typing import Any

from tools.mafia_sim.errors import BOT_ID, TgError

STARS = "XTR"
BUSINESS_RIGHTS = ("can_reply", "can_read_messages", "can_delete_sent_messages", "can_delete_all_messages")


class BotApiMixin:
    """Methods are looked up by ``World.handle`` as ``_m_<ApiMethodName>``."""

    # state lives in World's dataclass fields: invoices, precheckout_answers, star_transactions,
    # business_connections, topics_enabled, forum_topics, next_topic_id, widgets, widget_answers

    def _pre(self, name: str, params: dict) -> None:
        """Checks that apply to every method before it runs (Business connection, topics in private chats)."""
        connection_id = params.get("business_connection_id")
        if connection_id is not None:
            connection = self.business_connections.get(str(connection_id))
            if connection is None or not connection["is_enabled"]:
                raise TgError(400, "Bad Request: BUSINESS_CONNECTION_INVALID")
            if name.startswith("Send") and not connection["rights"].get("can_reply"):
                raise TgError(400, "Bad Request: BUSINESS_PEER_USAGE_MISSING")
        thread = params.get("message_thread_id")
        chat = params.get("chat_id")
        if thread and chat is not None and (int(chat), int(thread)) in self.deleted_topics:
            raise TgError(400, "Bad Request: message thread not found")
        if thread and chat is not None and int(chat) > 0 and int(chat) not in self.topics_enabled:
            raise TgError(400, "Bad Request: message thread not found")

    # ── Stars payments ──────────────────────────────────────────────────────
    def _m_SendInvoice(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        self._require_dm(chat_id)
        prices = params.get("prices") or []
        amount = sum(int(p.amount if hasattr(p, "amount") else p["amount"]) for p in prices)
        if params.get("currency") != STARS:
            raise TgError(400, "Bad Request: only Telegram Stars (XTR) invoices are accepted by this bot")
        if params.get("provider_token") not in ("", None):
            raise TgError(400, "Bad Request: PROVIDER_TOKEN must be empty for Stars")
        if len(prices) != 1 or not 1 <= amount <= 100_000:
            raise TgError(400, "Bad Request: Stars invoice needs exactly one price of 1..100000")
        if not 1 <= len(params.get("title", "")) <= 32 or not 1 <= len(params.get("description", "")) <= 255:
            raise TgError(400, "Bad Request: invoice title (1-32) or description (1-255) has a wrong length")
        if not 1 <= len(str(params.get("payload", "")).encode()) <= 128:
            raise TgError(400, "Bad Request: invoice payload must be 1-128 bytes")
        self.next_id += 1
        record = {"chat_id": chat_id, "message_id": self.next_id, "payload": params["payload"], "stars": amount,
                  "title": params["title"], "currency": params["currency"]}
        self.invoices.append(record)
        return {"message_id": self.next_id, "date": int(time.time()), "chat": self._chat(chat_id), "from": self._user(BOT_ID),
                "invoice": {"title": params["title"], "description": params["description"], "start_parameter": "",
                            "currency": params["currency"], "total_amount": amount}}

    def _m_AnswerPreCheckoutQuery(self, params: dict) -> bool:
        if not params.get("ok") and not params.get("error_message"):
            raise TgError(400, "Bad Request: error_message is required when ok is false")
        self.precheckout_answers.append({"id": params["pre_checkout_query_id"], "ok": bool(params.get("ok")),
                                         "error": params.get("error_message")})
        return True

    def _m_GetStarTransactions(self, params: dict) -> dict:
        return {"transactions": list(self.star_transactions)}

    def _m_RefundStarPayment(self, params: dict) -> bool:
        return True

    # ── HTML widgets (Bot API 10.4): production allows them only in the private chat with the bot ──
    @staticmethod
    def _widget_state(params: dict, key: str) -> str | None:
        value = params.get(key)
        if value is not None and len(str(value).encode()) > 1024:
            raise TgError(400, "Bad Request: INPUT_MEDIA_WIDGET_DATA_TOO_LARGE")
        return value

    def _m_SendWidget(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        if chat_id < 0 or params.get("business_connection_id") is not None:
            raise TgError(400, "Bad Request: widgets can be sent only to private chats")
        self._require_dm(chat_id)
        source = str(params.get("html") or "")
        raw = source.encode()
        if "\x00" in source or not raw:
            raise TgError(400, "Bad Request: INPUT_MEDIA_WIDGET_HTML_INVALID")
        if len(raw) > 32768 or len(zlib.compress(raw, 9)) > 4096:
            raise TgError(400, "Bad Request: INPUT_MEDIA_WIDGET_TOO_LARGE")
        caption = params.get("caption") or ""
        if len(caption) > 1024:
            raise TgError(400, "Bad Request: message caption is too long")
        chat_data, public_data = self._widget_state(params, "chat_data"), self._widget_state(params, "public_data")
        data = self._m_SendMessage({**params, "text": caption}) if caption else self._store_captionless(params)
        widget = {"html": source, **({"chat_data": chat_data} if chat_data else {}), **({"public_data": public_data} if public_data else {})}
        self.widgets[(chat_id, data["message_id"])] = {**widget, "allow_queries": bool(params.get("allow_queries"))}
        data.pop("text", None)
        data.pop("entities", None)
        return {**data, "widget": widget, **({"caption": caption} if caption else {})}

    def _m_EditMessageWidgetData(self, params: dict) -> bool:
        key = (int(params["chat_id"]), int(params["message_id"]))
        widget = self.widgets.get(key)
        stored = self.messages.get(key)
        if widget is None or stored is None or stored.deleted:
            raise TgError(400, "Bad Request: message to edit not found")
        changes = {k: self._widget_state(params, k) for k in ("chat_data", "public_data") if params.get(k) is not None}
        if all(widget.get(k) == v for k, v in changes.items()):
            raise TgError(400, "Bad Request: message is not modified")
        widget.update(changes)
        stored.edits += 1
        return True

    def _m_AnswerWidgetQuery(self, params: dict) -> bool:
        data = params.get("data")
        if data is not None and len(str(data).encode()) > 1024:
            raise TgError(400, "Bad Request: WIDGET_RESULT_TOO_LARGE")
        self.widget_answers.append({"id": params["widget_query_id"], "data": data})
        return True

    # ── media and message management ────────────────────────────────────────
    def _media(self, params: dict, key: str) -> dict:
        data = self._m_SendPhoto({**params, "caption": params.get("caption") or "·"})
        data.pop("photo", None)
        data[key] = {"file_id": f"sim-{key}-{data['message_id']}", "file_unique_id": f"u{data['message_id']}"}
        return data

    def _m_SendAnimation(self, params: dict) -> dict:
        data = self._media(params, "animation")
        data["animation"].update(width=320, height=320, duration=3)
        return data

    def _m_SendDocument(self, params: dict) -> dict:
        return self._media(params, "document")

    def _m_SendMediaGroup(self, params: dict) -> list[dict]:
        return [self._m_SendPhoto({**params, "caption": getattr(item, "caption", None) or "·"}) for item in params["media"]]

    def _m_EditMessageCaption(self, params: dict) -> dict:
        return self._m_EditMessageText({**params, "text": params.get("caption")})

    def _m_DeleteMessages(self, params: dict) -> bool:
        for message_id in params["message_ids"]:
            self._m_DeleteMessage({"chat_id": params["chat_id"], "message_id": message_id})
        return True

    # ── chats and members ───────────────────────────────────────────────────
    def _m_GetChat(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        info = {**self._chat(chat_id), "accent_color_id": 0, "max_reaction_count": 11,
                "accepted_gift_types": {"unlimited_gifts": False, "limited_gifts": False, "unique_gifts": False,
                                        "premium_subscription": False, "gifts_from_channels": False}}
        if chat_id > 0:
            info["first_name"] = f"U{chat_id}"
        return info

    def _m_GetChatMember(self, params: dict) -> dict:
        status = self.statuses.get((int(params["chat_id"]), int(params["user_id"])))
        if status is None:
            return {"status": "left", "user": self._user(int(params["user_id"]))}
        user, kind = self._user(int(params["user_id"])), status["status"]
        if kind in {"administrator", "creator"}:
            full = {key: False for key in (
                "can_be_edited", "is_anonymous", "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
                "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users", "can_post_stories",
                "can_edit_stories", "can_delete_stories", "can_send_welcome_messages")}
            full.update({k: v for k, v in status.items() if k != "status"})
            return {"status": kind, "user": user, **({"is_anonymous": False} if kind == "creator" else full)}
        if kind == "restricted":
            perms = {k: False for k in (
                "can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos",
                "can_send_video_notes", "can_send_voice_notes", "can_send_polls", "can_send_other_messages",
                "can_add_web_page_previews", "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics",
                "can_react_to_messages", "can_edit_tag")}
            perms.update({k: v for k, v in status.items() if k != "status"})
            return {"status": "restricted", "user": user, "is_member": True, "until_date": 0, **perms}
        if kind == "kicked":
            return {"status": kind, "user": user, "until_date": 0}   # Telegram always says until when
        return {"status": kind, "user": user}

    def _m_GetChatAdministrators(self, params: dict) -> list[dict]:
        chat_id = int(params["chat_id"])
        found = [self._m_GetChatMember({"chat_id": chat_id, "user_id": uid}) for (cid, uid), s in sorted(self.statuses.items())
                 if cid == chat_id and s["status"] in {"administrator", "creator"}]
        return found

    def _m_BanChatMember(self, params: dict) -> bool:
        self.statuses[(int(params["chat_id"]), int(params["user_id"]))] = {"status": "kicked", "until_date": 0}
        return True

    def _m_UnbanChatMember(self, params: dict) -> bool:
        key = (int(params["chat_id"]), int(params["user_id"]))
        if self.statuses.get(key, {}).get("status") == "kicked":
            self.statuses[key] = {"status": "left"}
        return True

    def _m_RestrictChatMember(self, params: dict) -> bool:
        key = (int(params["chat_id"]), int(params["user_id"]))
        permissions = params["permissions"].model_dump(exclude_none=True) if hasattr(params["permissions"], "model_dump") else {}
        self.statuses[key] = {"status": "restricted", **permissions}
        return True

    # ── forum topics (supergroups and private chats with topics) ────────────
    def _m_CreateForumTopic(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        if chat_id > 0 and chat_id not in self.topics_enabled:
            raise TgError(400, "Bad Request: the chat has no topics enabled")
        if not 1 <= len(params.get("name", "")) <= 128:
            raise TgError(400, "Bad Request: topic name must be 1-128 characters")
        self.next_topic_id += 1
        topic = {"chat_id": chat_id, "message_thread_id": self.next_topic_id, "name": params["name"], "closed": False}
        self.forum_topics[(chat_id, self.next_topic_id)] = topic
        return {"message_thread_id": self.next_topic_id, "name": params["name"], "icon_color": 7322096}

    def _topic(self, params: dict) -> dict:
        topic = self.forum_topics.get((int(params["chat_id"]), int(params["message_thread_id"])))
        if topic is None:
            raise TgError(400, "Bad Request: message thread not found")
        return topic

    def _m_EditForumTopic(self, params: dict) -> bool:
        self._topic(params)["name"] = params.get("name") or self._topic(params)["name"]
        return True

    def _m_CloseForumTopic(self, params: dict) -> bool:
        self._topic(params)["closed"] = True
        return True

    def _m_DeleteForumTopic(self, params: dict) -> bool:
        self._topic(params)
        key = (int(params["chat_id"]), int(params["message_thread_id"]))
        del self.forum_topics[key]
        self.deleted_topics.add(key)
        return True

    def _m_SendDice(self, params: dict) -> dict:
        """A dice: stored like a captionless message; the value is random, like Telegram's."""
        data = self._store_captionless(params)
        data["dice"] = {"emoji": params.get("emoji") or "🎲", "value": random.randint(1, 6)}
        return data

    # ── Telegram Business ───────────────────────────────────────────────────
    def _m_GetBusinessConnection(self, params: dict) -> dict:
        connection = self.business_connections.get(str(params["business_connection_id"]))
        if connection is None:
            raise TgError(400, "Bad Request: BUSINESS_CONNECTION_NOT_FOUND")
        return connection

    def add_business_connection(self, connection_id: str, owner: dict, *, enabled: bool = True, **rights: Any) -> dict:
        rights = {key: rights.get(key, key == "can_reply") for key in BUSINESS_RIGHTS}
        connection = {"id": connection_id, "user": owner, "user_chat_id": owner["id"], "date": int(time.time()),
                      "is_enabled": enabled, "rights": rights, "can_reply": rights["can_reply"]}
        self.business_connections[connection_id] = connection
        return connection
