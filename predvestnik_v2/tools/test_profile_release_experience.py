#!/usr/bin/env python3
"""Static release contract for the profile, compensation and pet collection UX."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
profile = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
shell = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
pets = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
wallet = (ROOT / "FastAPI/routers/wallet.py").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
skin = (ROOT / "FastAPI/static/skin-runtime-v3.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/profile.py").read_text(encoding="utf-8")
service = (ROOT / "services/pets_v1.py").read_text(encoding="utf-8")
constants = (ROOT / "core/constants.py").read_text(encoding="utf-8")
updates = (ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8")
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")

assert "renderProfileHome(d)" in profile
assert "v3-admin-entry" in index and "openBotAdmin()" in profile
assert "adminEntry.hidden=!d.is_developer" in profile
assert "event?.type === 'balance_changed'" in shell and "queueLiveBalance(event)" in shell
assert "setInterval(refreshCurrBar" not in profile
assert "cm-bal-essence" in profile and "cm-bal-zarniki" in profile
assert "Подробнее о профиле" not in profile
assert "_profileVipCard" not in profile and "renderProfileDetails" not in profile
assert "_profileCompensationCard" not in profile and "replayCompensationAnimation" not in profile
assert "expires_at" in router and "_compensation_receipt" in router
assert "retirement_compensation_receipts_v2" in router
assert "to_regclass('retirement_compensation_receipts_v2')" in router
assert "json.loads(raw_compensation)" in router
assert "overflow-x:auto" not in css[css.index(".migration-card"):css.index("/* Pets are a collection first")]
assert "prefers-reduced-motion:reduce" in css
assert "bestiary_owned" in service and "PET_SPECIES" in service
assert "showPetPanel('bestiary'" in pets and "Неизвестный питомец" in pets
assert "body.skin-v3" in skin and "var(--v3-wash)" in skin, "game pages take the equipped skin palette"
assert "2026-09-20-profile-compensation-and-bestiary" in updates
assert "2026-09-20-clearer-interface" in updates
assert "help-hero" in index and "help-card" in index and "v3-title" in index
settings = (ROOT / "FastAPI/static/app.26.js").read_text(encoding="utf-8")
assert "st-switch" in settings and "st-sec" in settings and "_accDeleteStart()" in settings
assert ".help-card" in css
assert profile.index("if (data?.username !== undefined)") < profile.index("if (!bar) return")
assert 'aria-label="Основные разделы"' in index
assert index.count('type="button" class="nb') == 7
assert "setAttribute('aria-current','page')" in shell
assert "2026-09-20-navigation-and-player-hub" in updates
assert "2026-09-20-profile-stories-and-admin-repair" in updates
for retired in ("profile-zone--games", "profile-zone--progress", "profile-zone--social", "profile-zone--safety"):
    assert retired not in profile
home = (ROOT / "FastAPI/static/app.15.js").read_text(encoding="utf-8")
assert "openAchievementsV1()" in home and "openPetsV1()" in home
assert '"chest_key_purchase": "🗝 Ключ от сундука"' in wallet
assert "_WN_ARCHIVE_BOUNDARY" in profile and "all.slice(0,archiveAt)" in profile
for action in ("openSettingsModal()", "openWhatsNew()", "openChatTracker()"):
    assert action in index
notification_block = constants[constants.index("NOTIFICATION_CATEGORIES:"):constants.index("# ── ИИ-помощник")]
assert '"vip_expiry"' in notification_block
assert '"bp_reminder"' not in notification_block and '"bid_outbid_final"' not in notification_block

print("OK: current profile, preserved compensation data and accessible pet bestiary are wired")
