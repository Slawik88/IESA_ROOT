"""Backwards-compatibility shim — all logic moved to users/telegram/ package.

Import from users.telegram directly for new code.
"""
from users.telegram import (  # noqa: F401
    bot_name,
    consume_link_code,
    generate_link_code,
    get_webhook_info,
    is_configured,
    notify_membership_activated,
    notify_visit_cancelled,
    notify_visit_confirmed,
    notify_visit_edited,
    process_incoming_update,
    send_message,
    send_message_async,
    set_webhook,
    token,
    verify_telegram_auth,
    webhook_secret,
)

# Legacy aliases
_token          = token
_webhook_secret = webhook_secret
