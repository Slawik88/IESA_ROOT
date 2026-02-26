"""IESA Sport Telegram bot package.

Public API — import from here for maximum stability:

    from users.telegram import send_message, send_message_async
    from users.telegram import notify_visit_confirmed
    from users.telegram import process_incoming_update
    from users.telegram import set_webhook, get_webhook_info
    from users.telegram import is_configured
"""
from .client import (
    get_webhook_info,
    send_message,
    send_message_async,
    set_webhook,
)
from .config import (
    bot_name,
    is_configured,
    token,
    webhook_secret,
)
from .dispatcher import process_incoming_update
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
    # client
    "send_message",
    "send_message_async",
    "set_webhook",
    "get_webhook_info",
    # config
    "is_configured",
    "token",
    "webhook_secret",
    "bot_name",
    # link
    "generate_link_code",
    "consume_link_code",
    "verify_telegram_auth",
    # dispatcher
    "process_incoming_update",
    # notify
    "notify_visit_confirmed",
    "notify_visit_edited",
    "notify_visit_cancelled",
    "notify_membership_activated",
    "send_test_notification",
]
