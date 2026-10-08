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

CSS_FILES = ("appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "looks-v3.css", "public-card-v3.css", "collect-v3.css", "toast-v3.css")
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
        if re.search(r"animation(?:-name)?\s*:\s*+(?!none)", rules):
            assert ".ap-anim" in selector, f"{name}: ungated animation in {selector.strip()[:80]}"
    assert "prefers-reduced-motion" in css[name], name
for name, text in css.items():
    assert text.count("\n") <= 300, f"{name} is over 300 lines"

# No visible rectangles: the glow of a nickname is a filter (a name box with overflow:hidden and every list row clip text-shadow along their
# straight edges), the title pill has no light band, and the rows of the top list leave room for a glow inside the ellipsis box.
names_css = css["appearance-v3.css"]
for selector, rules in re.findall(r"([^{}]+)\{([^{}]*)\}", strip_blocks(names_css, "@keyframes")):
    if ".ap-name" in selector:
        assert not re.search(r"text-shadow\s*:\s*(?!none)", rules), f"text-shadow is clipped by the name box: {selector.strip()[:80]}"
assert ".ap-nm-glow::before" not in names_css, "the blurred copy of a glowing name is cut by the name box"
assert not re.search(r"\.ap-title[^{}]*\{[^{}]*apglint", names_css), "a title is never lit through background-position"
sheen = re.search(r"\.ap-title::after \{[^}]*gradient\(([^;]*)\); \}", names_css)
assert sheen and sheen.group(1).count("rgba(") >= 7, "the title sheen needs a smooth many-step profile, a two-step ramp shows its edges"
assert re.search(r"@keyframes aptsheen \{[^}]*opacity[^}]*transform", names_css) and ".ap-anim .ap-title:is(.ap-t4, .ap-t5, .ap-t6, .ap-t7)::after" in names_css
# Long nicknames never break a layout: one line with an ellipsis in lists, two lines at most in heroes.
assert re.search(r"\.v3-who \.ap-name \{[^}]*white-space: nowrap; text-overflow: ellipsis", names_css) and ".ap-plain {" in names_css
assert re.search(r"\.v3-name \.ap-name, \.pp-name \.ap-name, \.lk-name \.ap-name \{[^}]*-webkit-line-clamp: 2[^}]*overflow-wrap: anywhere", names_css)
assert "white-space: nowrap" not in css["looks-v3.css"].split(".lk-name {", 1)[1].split("}", 1)[0], "the looks hero name may wrap"
home_css = (STATIC / "shell-v3-home.css").read_text(encoding="utf-8")
assert re.search(r"\.v3-top-list \.v3-rowbtn > span \{[^}]*padding: 14px 24px; margin: -14px -24px", home_css), "top list rows clip the glow of a look"

# The renderer never trusts the payload: palette and kinds are validated before they reach a class or a style.
assert "_AP_HEX.test" in renderer and "_AP_WORD" in renderer and "look.tier === look.ceiling" in renderer
assert "_v3SafeValue" in decor and "url\\(" in decor
# Readability: the nickname is large text (3:1 needed), the title is small (4.5:1). Letters take the dark end of the palette through --ap-nb (b pulled toward a),
# measured against the skin's own background; the real stage is a little brighter than that, hence the margin over the minimum.
from core.skins_v3 import contrast, mix  # noqa: E402
assert "--ap-nb: color-mix(in srgb, var(--ap-b) 62%, var(--ap-a))" in css["appearance-v3.css"] and "var(--ap-nb)" in css["appearance-v3.css"]
assert not re.search(r"\.ap-name[^{}]*\{[^{}]*background-image: [^;]*var\(--ap-b\)", css["appearance-v3.css"]), "name gradients use --ap-nb, not the dark end of the palette"
for skin_id, skin in SKINS.items():
    bg, (a, b, c) = skin["tokens"]["--v3-bg"], skin["pal"]
    assert contrast(mix(b, a, .38), bg) >= 3.8, f"{skin_id}: the darkest letters of the nickname must stay readable on {bg}"
    assert contrast(a, bg) >= 5.0, f"{skin_id}: title text colour must clear 4.5:1 with margin"
# Placeholder avatar (no photo): a personal constellation, not a glyph; one twinkle class, only under .ap-anim.
assert "function _v3Constellation(" in renderer and "_cnRand" in renderer and "Math.min(9, 4 +" in renderer, "the star count grows with the level up to nine"
shell_css = (STATIC / "shell-v3.css").read_text(encoding="utf-8")
assert ".ap-anim .cn-tw" in shell_css and not re.search(r"(?<!\.ap-anim )\.cn-tw[^{]*\{[^}]*animation", shell_css), "the constellation twinkles only under .ap-anim"
assert "_v3Constellation(" in (STATIC / "app.15.js").read_text(encoding="utf-8") and "seed: d.ref" in (STATIC / "app.21.js").read_text(encoding="utf-8")
print("OK: skins v3 visuals: kinds, signatures, sets, gated motion")
