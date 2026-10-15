"""Static contract for ECO-04 PR-C gifts UI (app.45.js, .gift-* in app.css): flag-gated tab and shelf, honest confirm, escaped notes, 360px."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
js = (STATIC / "app.45.js").read_text(encoding="utf-8")
shop_js = (STATIC / "app.44.js").read_text(encoding="utf-8")
home_js = (STATIC / "app.15.js").read_text(encoding="utf-8")
card_js = (STATIC / "app.21.js").read_text(encoding="utf-8")
css = (STATIC / "app.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/gifts_v2.py").read_text(encoding="utf-8")
startup = (ROOT / "bot/startup_schema.py").read_text(encoding="utf-8")
wallet = (ROOT / "FastAPI/routers/wallet.py").read_text(encoding="utf-8")
public = (ROOT / "FastAPI/routers/public_profile_v3.py").read_text(encoding="utf-8")

# Wiring: the part is served after the shop part, the router and both tables are created on both start-up paths.
parts = [int(n) for n in re.findall(r"\d+", re.search(r"_APP_JS_PARTS = \[[^\]]*for i in \(([^)]*)\)", main_py).group(1))]
assert 45 in parts and parts.index(44) < parts.index(45), parts
assert "gifts_v2_router.router" in main_py and "(ensure_gifts_v2," in main_py and '("gifts_v2", gifts_v2_repo.ensure_tables)' in startup
assert 'prefix="/gifts-v2"' in router and "HTTPException(404" in router and "HTTPException(409" in router
assert '"gift_send_v2": "🎁 Подарок"' in wallet and "gifts_v2.public_view(" in public

# Flag-gated tab: registered through the shop hook, shown only while /gifts-v2/me answered; 404 «Подарки пока закрыты» hides tab and shelf.
assert "_shopExtra.gifts = { name: 'Подарки', on: () => _giftsOn === true && !!_gifts.me" in js
assert "api('/gifts-v2/me')" in js and "e === 'Подарки пока закрыты'" in js and "_giftsOn = false" in js
assert "Object.values(_shopExtra).forEach(x => { try { x.load(); }" in shop_js and "_shopExtra[tab] ? _shopExtra[tab].html()" in shop_js
assert "x.on()" in shop_js, "an extra tab is listed only while its own flag answered"
assert "host.hidden = !(_giftsOn === true && s)" in js and "${_giftsOn === true ? '' : 'hidden'}" in js
assert "giftsShelfShell()" in home_js and "ppGiftsHtml(d)" in card_js and "giftBadgeHtml(d.gifts?.top_badge)" in card_js
assert "const g = d && d.gifts; if (!g) return '';" in js, "the public card shows nothing while the flag is off"

# Send flow: recipient = partner → gift → optional note ≤60 → confirm with price, before → after, irreversible for ✨/💎.
assert "Кому: " in js and "'Записка к подарку'" in js and "giftNoteNext()" in js
assert js.count("v3Confirm(") == 1 and "['Кому'," in js and "['Отдаёшь'," in js and "→" in js
assert "note: g.irreversible ? 'Это необратимо.' : ''" in js and "`Подарить за ${_giftCost(g.cost)}`" in js
assert "_giftLen(note) > max" in js and "[...String(s || '')].length" in js, "note length counted in characters, as on the server"
assert "_giftPending.get(key) ||" in js and js.count("_giftPending.delete(key)") == 2 and "if (e.includes('уже использован')) _giftPending.delete(key)" in js
assert "catalog_digest: d.catalog_digest" in js and "giftRetry(" in js and "aria-busy" in js
assert "v3Reward(" in js, "success: a short animation"

# Notes come from another player: every place that prints one escapes it; no raw interpolation of server strings.
html_js = "\n".join(line for line in js.splitlines() if "toast(" not in line)   # toast() escapes its text itself (app.28.js)
assert "_profileEsc(text)" in (STATIC / "app.28.js").read_text(encoding="utf-8")
for name in ("h.note", "note", "p.name", "g.name", "x.name", "who?.name", "d.recipient.name", "b.name", "h.name", "t.name"):
    raw = re.escape("${" + name + "}")
    assert not re.search(r"[>\"' ]" + raw, html_js), f"{name} is printed without _profileEsc"
assert "<q>${_profileEsc(h.note)}</q>" in js and "_profileEsc(_gifts.draft.note)" in js

# Shelf: four tiers, slots with silhouettes, counters, pin up to 3, history with tier filter, empty text.
assert "is-empty" in js and "'Получено'" in js and "'Отправлено'" in js and "Получено <b>" in js and "Отправлено <b>" in js
assert "/gifts-v2/pin" in js and "aria-pressed=\"${!!h.pinned}\"" in js and "openGiftHistory()" in js and "&tier=" in js
assert js.count("Пока нет подарков") >= 2 and "'Подарить'" not in shop_js
assert "!d.is_self && g.can_send" in js, "«Подарить» only on someone else's card"
assert ".slice(0, 3)" in js

# Data-driven and calm: no copied prices, no pressure words, retired currencies never appear.
code = re.sub(r"//[^\n]*", "", js)
assert not re.search(r"(?<![\d.])(150|300|450|800|1500|2000|3000)(?![\d])", code), "prices come from /gifts-v2/me"
for banned in ("выгодн", "успей", "только сегодня", "скидк", "эконом", "Тёмн", "Осколк", "dark_mora", "echo"):
    assert banned.lower() not in js.lower(), banned

# Tiers richer each step from existing tokens; 360px without horizontal scroll; tap targets.
gift_css = css[css.index("/* ECO-04 PR-C: gifts"):css.index(".pet-release-card")]
assert all(f".gt{n}" in gift_css for n in (2, 3, 4)) and "var(--violet)" in gift_css and "var(--glow-gold)" in gift_css
assert "prefers-reduced-motion" in gift_css and "@media (max-width: 360px)" in gift_css and "minmax(0,1fr)" in gift_css
assert "min-height: 44px" in gift_css and "min-height: 48px" in gift_css and "overflow-wrap: anywhere" in gift_css
assert not re.search(r"#[0-9a-fA-F]{3,6}\b", gift_css), "tier colors come from tokens"
assert "grid-auto-flow: column; grid-auto-columns: minmax(0,1fr)" in css, "the shop tab bar fits three or four tabs"

for part in ("app.44.js", "app.45.js", "app.15.js", "app.21.js"):
    done = subprocess.run(["node", "--check", str(STATIC / part)], capture_output=True, text=True)
    assert done.returncode == 0, (part, done.stderr)
print("OK: gifts UI is flag-gated (tab, shelf, card), confirms with before→after and «Это необратимо» for ✨/💎, escapes notes, fits 360px")
