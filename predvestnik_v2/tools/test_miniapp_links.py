#!/usr/bin/env python3
"""Mini App buttons must never emit Telegram's invalid bare startapp link."""

from __future__ import annotations

import os

from core.miniapp_links import miniapp_url


os.environ["BOT_USERNAME"] = "IIIPredvestnikIIIBot"
os.environ["MINIAPP_URL"] = "https://example.test/predvestnik"
os.environ.pop("MINIAPP_SHORT_NAME", None)
assert miniapp_url() == "https://example.test/predvestnik"
assert miniapp_url("home") == "https://example.test/predvestnik?startapp=home"
assert "t.me" not in miniapp_url("home")

os.environ["MINIAPP_URL"] = "https://example.test/predvestnik?source=bot"
assert miniapp_url("quests") == "https://example.test/predvestnik?source=bot&startapp=quests"

os.environ["MINIAPP_SHORT_NAME"] = "predvestnik"
assert miniapp_url("game") == "https://t.me/IIIPredvestnikIIIBot/predvestnik?startapp=game"

print("Mini App link fallback and native short-name contract: OK")
