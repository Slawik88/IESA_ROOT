"""Constants and the error type shared by the fake Telegram (``world.py``) and its API mixin (``world_api.py``)."""
from __future__ import annotations

BOT_ID = 123456
BOT_USERNAME = "predvestnik_test_bot"
NETWORK_FAULT = 599  # TgError code that surfaces as aiogram's TelegramNetworkError


class TgError(Exception):
    def __init__(self, code: int, description: str, retry_after: int | None = None) -> None:
        super().__init__(description)
        self.code, self.description, self.retry_after = code, description, retry_after
