#!/usr/bin/env python3
"""Skins V3 visual contract: every catalog skin has CSS for each of its kinds and signature, motion is gated and cheap."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATIC = ROOT / "FastAPI/static"

from core.skins_v3 import TIERS  # noqa: E402
from core.skins_v3_catalog import SETS, SKINS  # noqa: E402

CSS_FILES = ("appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "looks-v3.css", "public-card-v3.css")
css = {name: (STATIC / name).read_text(encoding="utf-8") for name in CSS_FILES}
every = "".join(css.values())
decor = (STATIC / "app.22.js").read_text(encoding="utf-8")
renderer = (STATIC / "app.20.js").read_text(encoding="utf-8")

# Shape of the catalog: three or more skins on every ceiling tier, each with a palette that reads on its background.
per_tier = {tier: [s for s in SKINS.values() if s["tier"] == tier] for tier in TIERS}
assert all(len(items) >= 3 for items in per_tier.values()), {t: len(v) for t, v in per_tier.items()}
assert len(SKINS) >= 25 and len({s["name"] for s in SKINS.values()}) == len(SKINS)
for sid, skin in SKINS.items():
    assert re.fullmatch(r"#[0-9a-f]{6}", skin["pal"][0]) and len(skin["pal"]) == 3, sid
    assert set(skin["kinds"]) == {"frame", "halo", "pt", "name", "bg"}, sid
    assert set(skin["items"]) == {"name_glow", "title", "avatar_frame", "avatar_halo", "profile_bg", "card_fx"}, sid
    assert skin["tier"] in ("S", "SS", "SSS") if skin["sig"] else True, f"{sid}: only S and above carry a signature"
    if skin["tier"] in ("S", "SS", "SSS"):
        assert skin["sig"], f"{sid}: S, SS and SSS skins need a hand-made signature"

# Every kind a skin asks for exists in CSS, every signature has CSS and decor markup.
prefix = {"frame": "ap-fr-", "halo": "ap-ha-", "pt": "ap-pt-", "name": "ap-nm-", "bg": "ap-bg-"}
for sid, skin in SKINS.items():
    for kind, value in skin["kinds"].items():
        assert f".{prefix[kind]}{value}" in every, f"{sid}: no CSS for {kind}={value}"
    if skin["sig"]:
        assert f".ap-sig-{skin['sig']}" in every, f"{sid}: no CSS for signature {skin['sig']}"
        assert re.search(rf"\b{skin['sig']}:", decor), f"{sid}: no decor markup for {skin['sig']}"
for level in range(1, 8):
    assert f".ap-t{level}" in every

# Sets reference real skins of mixed rarity.
for set_id, spec in SETS.items():
    assert len(spec["members"]) == 3 and all(SKINS[m]["set"] == set_id for m in spec["members"]), set_id
    assert len({SKINS[m]["tier"] for m in spec["members"]}) == 3, f"{set_id}: members should span three rarities"

# Motion: any animation inside the appearance layers lives under .ap-anim (or the reduced-motion reset), and files stay small.
def strip_blocks(text: str, head: str) -> str:
    out, pos = [], 0
    while (start := text.find(head, pos)) != -1:
        out.append(text[pos:start])
        i = text.index("{", start); depth = 0
        for j in range(i, len(text)):
            depth += text[j] == "{"; depth -= text[j] == "}"
            if depth == 0:
                break
        pos = j + 1
    out.append(text[pos:])
    return "".join(out)

for name in ("appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css"):
    body = strip_blocks(strip_blocks(css[name], "@keyframes"), "@media")
    for selector, rules in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
        if re.search(r"animation(?:-name)?\s*:\s*(?!none)", rules):
            assert ".ap-anim" in selector, f"{name}: ungated animation in {selector.strip()[:80]}"
    assert "prefers-reduced-motion" in css[name], name
for name, text in css.items():
    assert text.count("\n") <= 300, f"{name} is over 300 lines"

# The renderer never trusts the payload: palette and kinds are validated before they reach a class or a style.
assert "_AP_HEX.test" in renderer and "_AP_WORD" in renderer and "look.tier === look.ceiling" in renderer
assert "_v3SafeValue" in decor and "url\\(" in decor
print("OK: skins v3 visuals: kinds, signatures, sets, gated motion")
