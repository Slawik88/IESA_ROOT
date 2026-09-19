#!/usr/bin/env python3
"""Release boundary: the Telegram bot exposes only approved public systems."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
handlers = (ROOT / "bot/handlers/__init__.py").read_text(encoding="utf-8")
startup = (ROOT / "bot/__main__.py").read_text(encoding="utf-8")
scheduler = (ROOT / "services/scheduler.py").read_text(encoding="utf-8")
profile = (ROOT / "bot/handlers/release_profile.py").read_text(encoding="utf-8")
quests = (ROOT / "bot/handlers/quests_v1.py").read_text(encoding="utf-8")
pets = (ROOT / "bot/handlers/pets_v1.py").read_text(encoding="utf-8")

for approved in (
    "release_profile_router",
    "quests_v1_router",
    "pets_v1_router",
    "payments_router",
    "marriage_router",
    "mafia_v1_router",
    "rhythm_router",
    "chat_settings_router",
    "admin_router",
    "mod_router",
):
    assert approved in handlers, approved

for retired in (
    "eco_router",
    "identity_router",
    "product_surfaces_router",
    "themes_router",
    "promo_router",
    "dark_mora_router",
    "events_info_router",
    "vip_router",
    "web_redirect_router",
):
    assert retired not in handlers, retired

assert "pet_bonuses_middleware" not in startup
assert "streak_middleware" not in startup
for retired_job in (
    "expedition_background_task",
    "daily_deal_task",
    "duel_and_auction_task",
    "smart_pulse_task",
    "crypto_alerts_task",
    "chest_spawn_task",
    "shadow_merchant_task",
):
    assert retired_job not in scheduler, retired_job
for retained_job in ("maintenance_task", "mafia_phase_task"):
    assert retained_job in scheduler, retained_job
for forbidden in ("ПИТОМЦ", "Мора", "Алмаз", "Ритм дня", "Небосвод"):
    assert forbidden not in profile, forbidden
assert "Центр активностей" in profile
assert "startapp=quests" in quests
assert "reward_parts" in quests and "Награды доступны в Mini App" in quests
assert "record_metric" not in quests
assert "startapp=pets" in pets
assert "select_active_pet" not in pets

print("OK: Telegram public routes match the approved release scope")
