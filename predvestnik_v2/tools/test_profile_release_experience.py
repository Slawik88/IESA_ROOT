#!/usr/bin/env python3
"""Static release contract for the profile, compensation and pet collection UX."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
profile = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
shell = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
pets = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
admin = (ROOT / "FastAPI/static/app.07.js").read_text(encoding="utf-8")
wallet = (ROOT / "FastAPI/routers/wallet.py").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
skin = (ROOT / "FastAPI/static/global-skins-v1.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/profile.py").read_text(encoding="utf-8")
service = (ROOT / "services/pets_v1.py").read_text(encoding="utf-8")
constants = (ROOT / "core/constants.py").read_text(encoding="utf-8")
updates = (ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8")
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")

assert "_profileVipCard(d.vip)" in profile
assert "expires_at" in router and "_compensation_receipt" in router
assert "retirement_compensation_receipts_v2" in router
assert "to_regclass('retirement_compensation_receipts_v2')" in router
assert "json.loads(raw_compensation)" in router
assert "localStorage" in profile and "replayCompensationAnimation" in profile
assert "old.mora" in profile and "old.diamonds" in profile
assert "vip_preserved_days" in profile and "vip_bonus_days" in profile
assert "+${fmt(c.mora_compensation" not in profile
assert "по снимку переноса" in profile
assert "overflow-x:auto" not in css[css.index(".migration-card"):css.index("/* Pets are a collection first")]
assert "prefers-reduced-motion:reduce" in css
assert "bestiary_owned" in service and "PET_SPECIES" in service
assert "showPetPanel('bestiary'" in pets and "Неизвестный питомец" in pets
assert "background-size:auto 100svh" in skin and "backdrop-filter:blur" in skin
assert "2026-09-20-profile-compensation-and-bestiary" in updates
assert "2026-09-20-clearer-interface" in updates
assert "help-hero" in index and "help-card" in index and "more-hero" in index
assert "settings-panel" in profile and "settings-toggle" in profile
assert ".help-card" in css and ".settings-panel" in css
assert profile.index("if (data?.username !== undefined)") < profile.index("if (!bar) return")
assert 'aria-label="Основные разделы"' in index
assert index.count('type="button" class="nb') == 4
assert "setAttribute('aria-current','page')" in shell
assert "2026-09-20-navigation-and-player-hub" in updates
assert "2026-09-20-profile-stories-and-admin-repair" in updates
for profile_chapter in ("profile-zone--games", "profile-zone--progress", "profile-zone--social", "profile-zone--safety"):
    assert profile_chapter in profile and profile_chapter in css
assert "profile-paths" in profile and "--path:" in profile
assert "openAchievementsV1()" in profile and "openPetsV1()" in profile
cached_admin = admin[admin.index("function loadAdmin()") : admin.index("function renderAdminChatSel()")]
assert "_adminChats.some" in cached_admin
assert "swAdmin(_adminTab" in cached_admin
assert "renderAdminChatSel(); return;" not in cached_admin
assert '"chest_key_purchase": "🗝 Ключ от сундука"' in wallet
assert "_WN_ARCHIVE_BOUNDARY" in profile and "all.slice(0,archiveAt)" in profile
for action in ("openSettingsModal()", "openZarnikiTopup()", "openWhatsNew()", "openChatTracker()"):
    assert action in index
notification_block = constants[constants.index("NOTIFICATION_CATEGORIES:"):constants.index("# ── ИИ-помощник")]
assert '"vip_expiry"' in notification_block
assert '"bp_reminder"' not in notification_block and '"bid_outbid_final"' not in notification_block

print("OK: mobile skin, visible VIP, immutable compensation story and pet bestiary are wired")
