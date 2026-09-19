#!/usr/bin/env python3
"""Static contract for product-wide Mini App / Telegram chat parity."""
from __future__ import annotations

import os
import pathlib
import sys


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from bot.handlers.product_surfaces import NotificationCB  # noqa: E402
from bot.handlers.web_redirect import _REDIRECTS  # noqa: E402
from core.constants import NOTIFICATION_CATEGORIES  # noqa: E402
from core.gameplay_events import canonical_event_payload  # noqa: E402
from core.surface_parity import SURFACES, surfaces_for_redirect  # noqa: E402

surface_handler_source = (pathlib.Path(__file__).resolve().parents[1] / "bot/handlers/product_surfaces.py").read_text(encoding="utf-8")
app_source = (pathlib.Path(__file__).resolve().parents[1] / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
assert "callback_data.enabled not in (0, 1)" in surface_handler_source
assert "from infrastructure.repositories import zoo" not in surface_handler_source
assert "Новая система питомцев ещё проектируется" in surface_handler_source
assert "Старый уход за питомцами закрыт" in surface_handler_source


surface_ids = [spec.surface_id for spec in SURFACES]
assert len(surface_ids) == len(set(surface_ids)), "duplicate surface_id"

all_aliases: dict[str, str] = {}
for spec in SURFACES:
    assert spec.aliases and spec.start_param
    for alias in spec.aliases:
        assert alias not in all_aliases, f"alias {alias!r} belongs to two surfaces"
        all_aliases[alias] = spec.surface_id

redirect_ids = {spec.surface_id for spec in surfaces_for_redirect()}
chat_ids = {spec.surface_id for spec in SURFACES if spec.chat_mode in {"shared_action", "chat_summary"}}
assert redirect_ids.isdisjoint(chat_ids)
assert len(_REDIRECTS) == len(redirect_ids)

expected_chat = {"inventory", "achievements", "rhythm", "notifications", "clans", "themes"}
assert expected_chat <= chat_ids
assert next(spec for spec in SURFACES if spec.surface_id == "rhythm").start_param == "games"
assert "zoo:['zoo']" not in app_source

callbacks = [
    NotificationCB(category=category, enabled=0, user_id=9_999_999_999).pack()
    for category in NOTIFICATION_CATEGORIES
]
assert callbacks and all(len(value.encode("utf-8")) <= 64 for value in callbacks)
assert NotificationCB(category="vip_expiry", enabled=0, user_id=7).pack() != NotificationCB(
    category="vip_expiry", enabled=1, user_id=7
).pack()

_, opened = canonical_event_payload("product_surface_opened", {"surface_id": "inventory"})
_, changed = canonical_event_payload(
    "player_preference_changed", {"preference": "vip_expiry", "enabled": False}
)
assert '"surface_id":"inventory"' in opened
assert '"enabled":false' in changed

print("OK: product surfaces have one owner, valid callbacks and disjoint chat/redirect routes")
