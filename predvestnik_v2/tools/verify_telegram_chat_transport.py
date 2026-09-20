#!/usr/bin/env python3
"""Non-destructive smoke test for a real Telegram test chat.

The probe never acts on chat members.  It creates one clearly labelled bot
message, verifies edit and inline-keyboard transport, and removes the message
even when a later assertion fails.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def telegram_call(token: str, method: str, **data: object) -> object:
    payload = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=payload
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Telegram {method} failed: {detail}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {result}")
    return result["result"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", required=True, type=int)
    parser.add_argument("--token-env", default="BOT_TOKEN")
    parser.add_argument("--expected-username")
    parser.add_argument("--cleanup-delay", type=float, default=0.5)
    args = parser.parse_args()

    token = os.getenv(args.token_env, "").strip()
    if not token:
        parser.error(f"environment variable {args.token_env} is empty")

    me = telegram_call(token, "getMe")
    if args.expected_username and me.get("username", "").lower() != args.expected_username.lower().lstrip("@"):
        raise RuntimeError(
            f"unexpected bot @{me.get('username')}; expected @{args.expected_username.lstrip('@')}"
        )
    chat = telegram_call(token, "getChat", chat_id=args.chat_id)
    member = telegram_call(
        token, "getChatMember", chat_id=args.chat_id, user_id=me["id"]
    )
    required_permissions = (
        "can_manage_chat",
        "can_delete_messages",
        "can_restrict_members",
        "can_invite_users",
        "can_pin_messages",
    )
    missing = [name for name in required_permissions if not member.get(name)]
    if member.get("status") not in {"administrator", "creator"} or missing:
        raise RuntimeError(
            f"bot is not a fully usable chat admin; status={member.get('status')}, missing={missing}"
        )

    message_id: int | None = None
    checks: dict[str, object] = {
        "bot": f"@{me.get('username')}",
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "admin_permissions": "ok",
    }
    try:
        keyboard = {
            "inline_keyboard": [
                [{"text": "Callback transport", "callback_data": "qa:transport"}],
                [{"text": "HTTPS transport", "url": "https://telegram.org/"}],
            ]
        }
        sent = telegram_call(
            token,
            "sendMessage",
            chat_id=args.chat_id,
            text="🧪 Telegram transport smoke test. This message will be removed automatically.",
            reply_markup=json.dumps(keyboard),
        )
        message_id = int(sent["message_id"])
        accepted = sent.get("reply_markup", {}).get("inline_keyboard", [])
        if len(accepted) != 2:
            raise RuntimeError("Telegram did not retain both keyboard rows")
        checks["send"] = "ok"
        checks["callback_keyboard"] = "ok"
        checks["url_keyboard"] = "ok"

        telegram_call(
            token,
            "editMessageText",
            chat_id=args.chat_id,
            message_id=message_id,
            text="✅ Telegram transport smoke test passed. Cleaning up.",
        )
        checks["edit"] = "ok"
    finally:
        if message_id is not None:
            time.sleep(max(0.0, args.cleanup_delay))
            telegram_call(
                token, "deleteMessage", chat_id=args.chat_id, message_id=message_id
            )
            checks["cleanup"] = "ok"

    print(json.dumps(checks, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
