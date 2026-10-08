#!/usr/bin/env python3
"""Admin gift card contract (no database): the card is the toast design made larger and longer, it follows the worn skin, and every gift the console can give reaches it."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STATIC = ROOT / "FastAPI/static"

from core.skins_v3_catalog import SKINS  # noqa: E402

toast_js = (STATIC / "app.28.js").read_text(encoding="utf-8")
boot_js = (STATIC / "app.01.js").read_text(encoding="utf-8")
css = (STATIC / "toast-gift-v3.css").read_text(encoding="utf-8")
toast_css = (STATIC / "toast-v3.css").read_text(encoding="utf-8")
console = {name: (ROOT / "FastAPI/routers/dev_console" / f"{name}.py").read_text(encoding="utf-8") for name in ("skins", "marks", "vip", "player")}


def check(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


# One card for everything the console gives; both entry points (live socket, gifts that waited offline) use it, and the next window waits until it is gone.
check("function v3GiftToast(" in toast_js and "function v3GiftClose(" in toast_js, "the gift card exists")
check(re.search(r"function showGiftBox\(payloads\) \{ v3GiftToast\(payloads, \(\) => _nextModal\(\)\); \}", boot_js), "showGiftBox is the card, and the modal queue continues after it")
check("event.type === 'admin_gift'" in boot_js and "gifts.length) queue.push(() => showGiftBox(gifts))" in boot_js, "live and offline gifts both reach the card")
check("OM('🎁 Награда от Администрации" not in boot_js, "the old modal is gone")

# It is the toast design: the same look (apFromLook of the worn skin), the same classes for shape, particles and signature, the same text safety (nothing injected raw).
body = toast_js.split("function v3GiftToast(", 1)[1].split("el('toast')?.addEventListener", 1)[0]
check("_tvLook()" in body and "tv-fr-${ap.k.frame} tv-pt-${ap.k.pt}" in body and "tv-sig" in body and "ap.vars" in body, "the card takes frame, particles, signature and palette of the worn skin")
check("textContent" not in toast_js, "no raw text assignment in the toast module")
for field in ("label", "reason"):
    check(re.search(rf"_profileEsc\([^)]*{field}", body) or "_tgSplit(g.label)" in body, f"{field} is escaped")
check("/^[a-z_]{2,24}$/.test(String(g.skin_id" in body, "a skin id is validated before it is used")
check("pointerdown" in body and "is-held" in body and "Math.min(15000" in body, "longer than any toast (up to 15 s) and paused while held")
check(re.search(r"const ms = Math\.min\(6500", toast_js), "a normal toast stays under 6.5 s: the gift card is clearly the longer one")

# Shape: every frame a skin can ask for is drawn (default or explicit) and every particle kind has a glyph for the burst.
frames = {"ring", "double", "dash", "seg", "drip"}
check({s["kinds"]["frame"] for s in SKINS.values()} <= frames, "a new frame kind needs a card shape in toast-gift-v3.css (and toast-v3.css)")
for kind in frames - {"ring", "double"}:
    check(f".tv-gift.tv-fr-{kind}" in css, f"card shape for {kind}")
for kind in {s["kinds"]["pt"] for s in SKINS.values()}:
    check(re.search(rf"\b{kind}: '", toast_js.split("function _tvGlyph", 1)[1].split("}", 1)[0]), f"particle glyph for {kind}")
check(all(f".tv-t{n}" in toast_css or n < 3 for n in range(1, 8)) and ".tv-gift:is(.tv-t3" in css and ".tv-gift.tv-sig::after" in css, "tier saturation and the signature thread")

# Motion: every animation under .ap-anim (reduced motion kills all), only transform/opacity in keyframes, light phones lose half the particles and the sheen.
for selector, rules in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"@keyframes[^{]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)):
    if re.search(r"animation(?:-name)?\s*:\s*+(?!none)", rules):
        check(".ap-anim" in selector, f"ungated animation in {selector.strip()[:70]}")
for name, frames_body in re.findall(r"@keyframes (tg\w+) \{(.*?)\n", css):
    check(not re.search(r"(?<![a-z-])(left|top|width|height|margin|box-shadow|filter)\s*:", frames_body), f"{name} animates layout or paint")
check("prefers-reduced-motion" in css and ".ap-lite .tv-gift" in css, "reduced motion and the light-phone budget are handled")
check(css.count("\n") <= 300, "css file under 300 lines")

# Everything the console can give arrives as a gift: balances and items (already), VIP, regalia, personal skins; taking away never gifts.
check("_send_admin_gift" in console["player"], "balances and items still gift")
check('"kind": "vip"' in console["vip"] and console["vip"].count("_send_admin_gift(") == 2, "VIP grant and extension gift, shortening and revoking do not")
check('"kind": "mark"' in console["marks"] and 'if action == "grant"' in console["marks"], "regalia grants gift, taking back does not")
check('"kind": "skin"' in console["skins"] and console["skins"].count("_send_admin_gift(") == 1, "a personal skin gifts, taking it back does not")
print("OK: admin gift card contract")
