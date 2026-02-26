"""IESA Sport Telegram bot package."""
from .client import (
    answer_callback_query,
    edit_message_reply_markup,
    edit_message_text,
    get_webhook_info,
    send_message,
    send_message_async,
    set_bot_commands,
    set_webhook,
)
from .config import (
    bot_name,
    is_configured,
    token,
    webhook_secret,
)
from .dispatcher import init_bot_commands, process_incoming_update
from .link import (
    consume_link_code,
    generate_link_code,
    verify_telegram_auth,
)
from .notify import (
    notify_membership_activated,
    notify_visit_cancelled,
    notify_visit_confirmed,
    notify_visit_edited,
    send_test_notification,
)

__all__ = [
    "send_message", "send_message_async", "set_webhook", "get_webhook_info",
    "answer_callback_query", "edit_message_text", "edit_message_reply_markup",
    "set_bot_commands",
    "is_configured", "token", "webhook_secret", "bot_name",
    "generate_link_code", "consume_link_code", "verify_telegram_auth",
    "process_incoming_update", "init_bot_commands",
    "notify_visit_confirmed", "notify_visit_edited", "notify_visit_cancelled",
    "notify_membership_activated", "send_test_notification",
]
