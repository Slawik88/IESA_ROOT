"""Static contract for the ECO-04 PR-B shop screen (app.44.js, .shop-* in app.css): flag-gated entry, data-driven cards, honest confirm, mobile-first."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
index = (STATIC / "index.html").read_text(encoding="utf-8")
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
js = (STATIC / "app.44.js").read_text(encoding="utf-8")
shell = (STATIC / "app.01.js").read_text(encoding="utf-8")
wallet_js = (STATIC / "app.02.js").read_text(encoding="utf-8")
home_js = (STATIC / "app.15.js").read_text(encoding="utf-8")
enter_js = (STATIC / "app.31.js").read_text(encoding="utf-8")
css = (STATIC / "app.css").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/shop_v1.py").read_text(encoding="utf-8")
startup = (ROOT / "bot/startup_schema.py").read_text(encoding="utf-8")

# Wiring: the page exists, the part is served, the router and the receipt table are registered on both start-up paths.
assert 'id="pg-shop"' in index
parts = [int(n) for n in re.findall(r"\d+", re.search(r"_APP_JS_PARTS = \[[^\]]*for i in \(([^)]*)\)", main_py).group(1))]
assert 44 in parts and parts.index(12) < parts.index(44), parts
assert "shop_v1_router.router" in main_py and '(ensure_shop_v1,' in main_py and '("shop_v1", shop_v1_repo.ensure_tables)' in startup
assert 'prefix="/shop-v1"' in router and "HTTPException(404" in router and "HTTPException(409" in router
assert re.search(r"suppressBrowserBack=\[[^\]]*'shop'[^\]]*\]", shell) and "'pg-shop'" in enter_js

# Entry only while /shop-v1/me answers: the profile row and the wallet button start hidden, 404 «Магазин пока закрыт» keeps them hidden.
assert "shopEntryRow()" in home_js and "data-shop-entry" in wallet_js and "shopProbe()" in wallet_js
assert "_shopOn === true ? '' : 'hidden" in wallet_js and "node.hidden = _shopOn !== true" in js
assert "api('/shop-v1/me')" in js and "Магазин пока закрыт" in js and "openShop()" in wallet_js

# Tabs and words from the brief; gifts (PR-C) live in app.45.js and join only through the _shopExtra hook.
for word in ("'Ключи'", "'Эссенция'", "'Обменник'", "'Купить'", "'Скрафтить'", "'Обменять'"):
    assert word in js, word
code = re.sub(r"//[^\n]*", "", js)
assert "Подарки" not in code and "gift" not in code.lower() and "const _shopExtra = {};" in js
assert "Осталось ${left} из ${max} на этой неделе" in js and "до сброса ${_shopHours(l.resets_in_seconds)} ч" in js
assert "Не хватает: " in js and "is-miss" in js and "item.missing" in js and "item.available" in js
assert "_SHOP_SWITCH = { key_t4:" in js and "'Крафт'" in js and "'За ✨'" in js, "Silver: one tile with a method switch"
assert "🗝" in js and "b.keys" in js, "the balance strip shows keys per tier"
assert "key_odds" in js and "остальное выше" in js and "o.percent" in js, "odds come from data"
assert "Лимит ${fmt(x.daily_cap || 0)}✨ в сутки, осталось ${fmt(x.left || 0)}. Обмен необратим." in js
assert 'inputmode="numeric"' in js and "body.amount = amount" in js

# Confirm before every debit: pay, get, balance before → after; irreversible lines.
assert js.count("v3Confirm(") == 1 and "'Отдаёшь'" in js and "'Получаешь'" in js and "→" in js
assert "'Покупка необратима: ключ не возвращается.'" in js and "'Это необратимо.'" in js
assert "'Это необратимо. Покупка необратима: ключ не возвращается.'" in js  # keys for ✨ or 💎
assert "if (e.includes('уже использован')) _shopPending.delete(key)" in js  # a stale id is dropped, not retried forever
assert "'zarniki' in cost || 'diamonds' in cost" in js

# States: loading, error with retry, success toast and in-place refresh; one action id per item until success.
assert "Загрузка магазина…" in js and "Повторить" in js and "shopRetry(" in js and "aria-busy" in js
assert "_shopPending.get(key) ||" in js and js.count("_shopPending.delete(key)") == 2
success = js[js.index(".then(res =>"):js.index(".catch(e => {\n    _shop.busy = null;")]
assert "_shopPending.delete(key)" in success and "Object.assign(_shop.me.balances, res.balances)" in success and "toast(" in success
assert "catalog_digest: d.catalog_digest" in js and len(re.findall(r"method: 'POST'", js)) == 1

# Links to existing screens; a missing screen hides its tile.
assert "openSeasonPass" in js and "openVipModal" in js and "openLooksModal" in js and "typeof window[_SHOP_LINK_FN[l.target]] === 'function'" in js

# Data-driven: no copied prices or limits; calm copy; retired currencies never appear.
assert not re.search(r"(?<![\d.])(600|800|120|300|3000|200)(?![\d])", code), "prices come from /shop-v1/me"
for banned in ("выгодн", "успей", "только сегодня", "скидк", "эконом", "Тёмн", "Осколк", "dark_mora", "echo"):
    assert banned.lower() not in js.lower(), banned

# Mobile-first: 360px, no horizontal scroll, tap targets.
shop_css = css[css.index("/* ECO-04 PR-B: shop"):]
shop_css = shop_css[:shop_css.index(".pet-release-card")]
assert "overflow-x: hidden" in shop_css and "@media (max-width: 360px)" in shop_css and "minmax(0," in shop_css
assert "min-height: 48px" in shop_css and "min-height: 44px" in shop_css and ".shop-price .is-miss" in shop_css
assert css.index(".chest-buy-confirm") < css.index("/* ECO-04 PR-B: shop"), "styles live next to the chest styles"

done = subprocess.run(["node", "--check", str(STATIC / "app.44.js")], capture_output=True, text=True)
assert done.returncode == 0, done.stderr
print("OK: shop UI is flag-gated, data-driven, confirms every debit with before→after, keeps one action id until success, fits 360px")
