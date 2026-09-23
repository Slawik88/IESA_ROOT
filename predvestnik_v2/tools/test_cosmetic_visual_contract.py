#!/usr/bin/env python3
"""Static half of the 134-item visual audit; browser evidence covers layout."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cosmetics import COSMETICS, COSMETIC_SLOTS, LINEUPS


EXPECTED_COUNTS = {
    "name_glow": 25,
    "avatar_frame": 23,
    "title": 19,
    "avatar_halo": 21,
    "profile_bg": 23,
    "card_fx": 23,
}
TOKEN_PREFIX = {
    "name_glow": "glow-",
    "avatar_frame": "frame-",
    "title": "title-",
    "avatar_halo": "halo-",
    "profile_bg": "pbg-",
    "card_fx": "cfx-",
}

css = (ROOT / "FastAPI" / "static" / "app.css").read_text(encoding="utf-8")
release_js = (ROOT / "FastAPI" / "static" / "app.12.js").read_text(encoding="utf-8")
store_js = (ROOT / "FastAPI" / "static" / "app.13.js").read_text(encoding="utf-8")

assert len(COSMETICS) == 134
assert Counter(item["slot"] for item in COSMETICS.values()) == EXPECTED_COUNTS
assert set(EXPECTED_COUNTS) == set(COSMETIC_SLOTS)

for cosmetic_id, item in COSMETICS.items():
    slot = item["slot"]
    token = item.get("css")
    assert isinstance(token, str) and re.fullmatch(r"[a-z0-9-]{1,80}", token), cosmetic_id
    assert token.startswith(TOKEN_PREFIX[slot]), f"{cosmetic_id}: {token} does not match {slot}"
    assert re.search(rf"\.{re.escape(token)}(?![\w-])", css), (
        f"{cosmetic_id}: missing .{token} visual definition"
    )
    assert item.get("lineup") in LINEUPS, f"{cosmetic_id}: unknown lineup"
    assert str(item.get("name") or "").strip(), f"{cosmetic_id}: empty player-facing name"
    if slot == "title":
        assert str(item.get("text") or "").strip(), f"{cosmetic_id}: empty title text"

# One generic switch must suppress motion for every cosmetic slot, including
# pseudo-element-heavy effects whose individual definitions evolve over time.
for selector in (
    '.no-fx .pname[class*="glow-"]',
    '.no-fx .ava[class*="frame-"]',
    '.no-fx .ava[class*="halo-"]',
    '.no-fx .hero[class*="pbg-"]',
    '.no-fx .card-fx[class*="cfx-"]',
    '.no-fx .ptitle[class*="title-"]',
):
    assert selector in css, f"missing reduced-motion selector: {selector}"

for selector in (
    '.no-fx .ava[class*="frame-"]::before',
    '.no-fx .ava[class*="halo-"]::after',
    '.no-fx .hero[class*="pbg-"]::after',
    '.no-fx .card-fx[class*="cfx-"]::before',
    '.ava[class*="frame-"]::before',
    '.ava[class*="halo-"]::after',
    '.hero[class*="pbg-"]::after',
    '.card-fx[class*="cfx-"]::before',
):
    assert selector in css, f"missing pseudo-element motion freeze: {selector}"

# The release wardrobe iterates the complete server projection and uses the
# same sanitiser/renderer as the public and personal profile card.
assert "Object.entries(wardrobe.slots||{}).map" in release_js
assert "typeof _profileCss==='function'?_profileCss(item.css)" in release_js
assert "renderProfileShowcase(d,look,{caption,compact:true})" in release_js

profile_renderer = (ROOT / "FastAPI" / "static" / "app.02.js").read_text(encoding="utf-8")
assert "[frame?.css,halo?.css].map(_profileCss).filter(Boolean).join(' ')" in profile_renderer
assert "const current=_profileData?.cosmetics||{}" in store_js
assert "const look={...current}" in store_js
assert "look[selected.slot]=projectedItem(selected)" in store_js
assert 'data-store-topup aria-label="Пополнить Зарники' in store_js
assert "window.openZarnikiTopup=async function()" in store_js
assert "В продакшене пополнение работает" in store_js
for selector in (".hdr-news", ".hdr-refresh", ".looks-back", ".profile-looks-link"):
    assert selector in css
assert ".looks-back {\n  width: 44px; height: 44px" in css
assert ".profile-looks-link {\n  min-height: 44px" in css
assert ".hdr-user { display: flex; align-items: center; gap: 8px; flex: 1 1 auto; overflow: hidden;" in css
assert ".hdr-id { flex: 1 1 auto; min-width: 0; overflow: hidden; }" in css
assert ".hdr-name { width: 100%; max-width: 100%;" in css
selected_look = store_js.split("function selectedLook(){", 1)[1].split("function previewHtml", 1)[0]
assert "cosmeticLook(selected.lineup)" not in selected_look
assert '${identityCss}' in profile_renderer

print("Cosmetic visual contract: 134/134 tokens, slots, lineups and motion fallback OK")
