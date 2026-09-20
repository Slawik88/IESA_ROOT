#!/usr/bin/env python3
"""Static release contract for the profile, compensation and pet collection UX."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
profile = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
pets = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
skin = (ROOT / "FastAPI/static/global-skins-v1.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/profile.py").read_text(encoding="utf-8")
service = (ROOT / "services/pets_v1.py").read_text(encoding="utf-8")
updates = (ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8")
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")

assert "_profileVipCard(d.vip)" in profile
assert "expires_at" in router and "_compensation_receipt" in router
assert "retirement_compensation_receipts_v2" in router
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

print("OK: mobile skin, visible VIP, immutable compensation story and pet bestiary are wired")
