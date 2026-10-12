"""Static contract for the Inventory screen: looks (the personal ones too), marks, pets, keys, food, cards, jokers and the items kept from the previous game in one place. Read-only."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
index = (STATIC / "index.html").read_text(encoding="utf-8")
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
js = (STATIC / "app.39.js").read_text(encoding="utf-8")
css = (STATIC / "inventory-v3.css").read_text(encoding="utf-8")
service = (ROOT / "services/inventory_v1.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/inventory_v1.py").read_text(encoding="utf-8")
home = (STATIC / "app.15.js").read_text(encoding="utf-8")
links = (STATIC / "app.02.js").read_text(encoding="utf-8")
shell = (STATIC / "app.01.js").read_text(encoding="utf-8")
motion = (STATIC / "app.31.js").read_text(encoding="utf-8")

# The screen is wired in: its page, script part, style sheet and API router.
assert 'id="pg-inventory"' in index and 'inventory-v3.css' in index
assert re.search(r"_APP_JS_PARTS = \[[^\]]*\b39\b", main_py) and "inventory-v3.css" in main_py, "the script part and the style sheet are served"
assert "inventory_v1 as inventory_v1_router" in main_py and "inventory_v1_router.router" in main_py, "the API router is registered"
assert "'pg-inventory'" in motion, "the cascade of sections plays on this page like on the others"
assert "'inventory'" in shell and "suppressBrowserBack" in shell, "no second back arrow on the screen that has its own"

# Ways in: the profile list, the deep link, the help page. The old deep link opened the looks screen; it now opens the inventory.
assert "openInventory()" in home and "_v3Row('bag', 'Инвентарь'" in home and "bag:" in home
assert "inventory:openInventory" in links and "inv:openInventory" in links and "inventory:openLooksModal" not in links
assert "openInventory()" in index, "help card"

# Second way in: the bag button in the top bar leads to the same screen; the dock is not touched.
bar = re.search(r'<header class="v3-bar".*?</header>', index, re.S).group(0)
assert 'id="v3-bag"' in bar and 'onclick="openInventory()"' in bar and 'aria-label="Инвентарь"' in bar

# Eight tabs in the dock: pets stand between chests and top and open the pets screen.
nav = re.search(r'<nav class="nav".*?</nav>', index, re.S)
assert nav and "--nav-n:8" in nav.group(0) and nav.group(0).count('class="nb') == 8
tabs = re.findall(r'data-page="([a-z]+)"', nav.group(0))
assert tabs == ["profile", "arena", "looks", "questlog", "chests", "pets", "top", "more"], tabs
assert 'data-page="pets" onclick="openPetsV1()"' in nav.group(0)

# The screen only reads: two GET requests, no writes, and a failed request does not hide the part that arrived.
assert "api('/skins-v3/me')" in js and "api('/inventory-v1/me')" in js
assert not re.search(r"method\s*:", js), "the inventory screen never writes"
assert "invItem(" in js and "CM();${go[1]}" in js and "'openChestsV1()'" in js and "'openPetsV1()'" in js, "the item sheet only leads to the screen where the item is used"
assert "_invSettle(" in js and "Повторить" in js
assert "i.owned" in js and "i.exclusive" in js and "личный" in js, "personal looks are listed among the owned ones and named"
assert "_lkMini(" in js and "openLooksModal()" in js, "the same tile as in the looks screen; a tile leads to where the look is worn and grown"
assert "_profileEsc(" in js and js.count("_profileEsc(") >= 20, "every server text is escaped"
assert not re.search(r"@keyframes|animation\s*:", css), "a screen that is read, not played on, has no motion of its own"

# Every inv-* class the script writes is styled.
used = set(re.findall(r'class="(?:[^"$]*\s)?(inv-[a-z-]+)', js))
styled = set(re.findall(r"\.(inv-[a-z-]+)", css))
assert used and used <= styled, f"classes without a rule: {sorted(used - styled)}"

# The view is read-only on the server too, and the router offers one GET.
assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", service), "the inventory service never writes"
assert router.count("@router.") == 1 and '@router.get("/me")' in router

print("OK: the inventory shows looks, pets, stock and old items in one read-only screen, with eight tabs in the dock")
