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
pets_ui = "".join(
    (ROOT / f"bot/handlers/{name}").read_text(encoding="utf-8")
    for name in ("_pets_ui.py", "_pets_ui_base.py", "_pets_ui_pets.py", "_pets_ui_activity.py")
)
pets_chat = (ROOT / "bot/handlers/pets_v1_callbacks.py").read_text(encoding="utf-8")
account = (ROOT / "bot/handlers/account.py").read_text(encoding="utf-8")

for approved in (
    "release_profile_router",
    "quests_v1_router",
    "pets_v1_router",
    "payments_router",
    "account_router",
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

for retired_file in ("profile.py", "identity.py", "vip.py"):
    assert not (ROOT / "bot" / "handlers" / retired_file).exists(), retired_file

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
assert 'miniapp_url("quests")' in quests
assert "reward_parts" in quests and "Награды доступны в Mini App" in quests
assert "record_metric" not in quests
# Pets are fully manageable from chat now: owner-locked callbacks may call the
# approved service writers, while the Mini App link stays as the secondary entry.
assert 'miniapp_url("pets")' in pets_ui
assert "check_callback_owner" in pets_chat
for chat_call in ("select_active_pet", "feed_pet", "start_activity", "choose_expedition"):
    assert chat_call in pets_chat or chat_call in pets, chat_call
assert 'TextCmd(["отменить удаление", "отмена удаления"])' in account
assert 'TextCmd(["восстановить аккаунт", "восстановление аккаунта"])' in account
assert "account_deletion.cancel_deletion" in account
assert "account_deletion.restore_account" in account

print("OK: Telegram public routes match the approved release scope")
