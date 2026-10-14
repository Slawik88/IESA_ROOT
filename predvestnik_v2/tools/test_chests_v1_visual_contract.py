"""Static contract for the mobile mixed-loot chest store."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
profile_js = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
release_js = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/chests_v1.py").read_text(encoding="utf-8")
legacy_router = (ROOT / "FastAPI/routers/cosmetics.py").read_text(encoding="utf-8")

assert 'id="pg-chests"' in index
home_js = (ROOT / "FastAPI/static/app.15.js").read_text(encoding="utf-8")
assert "_sysFlags.content_chests_v1" in home_js and "openChestsV1()" in home_js
assert "Награда уже сохранена сервером" in release_js
assert "Точные шансы и размеры наград" in release_js
assert "Купить ключ" in release_js and "chestsV1Buy" in release_js
assert "chestsV1AskBuy" in release_js and "Неиспользованный купленный ключ" in release_js
assert "Ключ уровня N поднимает звёзды ниже N до N" in release_js
assert "Покупка необратима" in release_js and "chestTierBalance(d,_chestsV1Tier)<1))_chestsV1Tier=" in release_js
# ECO-04 PR-A: tier picker, per-tier odds, offers with limits and an irreversible-spend note.
assert "chestsV1PickTier" in release_js and "key_tier:tier" in release_js and "prepare:${tier}" in release_js
assert "chestsV1AskOffer" in release_js and "/chests-v1/offers/" in release_js and "Покупка необратима" in release_js
assert "Осталось ${o.remaining} из ${o.limit}" in release_js and ".chest-tier-chip" in css
assert "pending_open" in release_js and "last_result" in release_js
assert "catalog_digest:_chestsV1Data.catalog_digest" in release_js
assert "min-height: 48px" in css and "@media (max-width: 360px)" in css
assert "position: sticky" in css and ".chest-inventory" in css
assert '@router.post("/prepare")' in router and '@router.post("/{open_id}/reveal")' in router
assert '@router.post("/purchase")' in router
assert "Архивные косметические сундуки закрыты" in legacy_router

print("OK: mixed chest UI is flag-gated, recoverable, transparent and mobile-first")
