"""Static contract for the chest screen: keys, one primary action, star keys and loot as rows, exact odds collapsed."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
release_js = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
css = (ROOT / "FastAPI/static/chests-v3.css").read_text(encoding="utf-8")
main = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/chests_v1.py").read_text(encoding="utf-8")
legacy_router = (ROOT / "FastAPI/routers/cosmetics.py").read_text(encoding="utf-8")

assert 'id="pg-chests"' in index and "chests-v3.css" in index and '"chests-v3.css"' in main
home_js = (ROOT / "FastAPI/static/app.15.js").read_text(encoding="utf-8")
assert "_sysFlags.content_chests_v1" in home_js and "openChestsV1()" in home_js
assert "v3Head('Сундуки'" in release_js and "Награда уже сохранена сервером" in release_js
assert "Точные шансы и размеры наград" in release_js and "Карты не пропадут" in release_js
# One primary action: reveal a prepared chest, else open with a key, else buy one, else go earn one.
assert "if(_chestsV1Prepared)action=" in release_js and "else if(tierBal>0)action=" in release_js
assert "else if(canBuy&&remaining>0)action=" in release_js and "onclick=\"openQuestsV1()\">К заданиям" in release_js
assert "Купить ключ" in release_js and "chestsV1Buy" in release_js
assert "chestsV1AskBuy" in release_js and "Неиспользованный купленный ключ" in release_js
assert "Ключ уровня N поднимает звёзды ниже N до N" in release_js
# The draw order moved from the collapsed odds into the guide's «Открытие» tile: one line, same honesty.
guides_js = (ROOT / "FastAPI/static/app.47.js").read_text(encoding="utf-8")
assert "guideDefine('chests'" in guides_js and "награда выбрана заранее" in guides_js
assert "Покупка необратима" in release_js and "chestTierBalance(d,_chestsV1Tier)<1)_chestsV1Tier=" in release_js
# ECO-04 PR-A: tier picker, per-tier odds, offers with limits and an irreversible-spend note.
assert "chestsV1PickTier" in release_js and "key_tier:tier" in release_js and "prepare:${tier}" in release_js
assert "chestsV1AskOffer" in release_js and "/chests-v1/offers/" in release_js
assert "осталось ${o.remaining} из ${o.limit}" in release_js and ".chest-tier-chip" in css
assert "pending_open" in release_js and "last_result" in release_js
assert "catalog_digest:_chestsV1Data.catalog_digest" in release_js
assert "min-height: 52px" in css and "min-height: 44px" in css
assert '@router.post("/prepare")' in router and '@router.post("/{open_id}/reveal")' in router
assert '@router.post("/purchase")' in router
assert "Архивные косметические сундуки закрыты" in legacy_router

print("OK: chest screen has one primary action, transparent odds, recoverable opens and v3 styling")
