"""S16 comparison must catch a real one-channel pixel change and cover every real id/tier."""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.skins_v3_catalog import SKINS
from skin_compare import css_files, pixel_difference

plan = json.loads((ROOT / "docs/roadmap/findings/D2-cosmetics-plan.json").read_text(encoding="utf-8"))
assert set(plan) == set(SKINS) and len(plan) == 42
assert all(len(row["tiers"]) == 7 and all(row["tiers"]) for row in plan.values())
assert all(row["decision"] in ("keep", "refine", "redraw") for row in plan.values())
assert all(row["session"] in ("S17", "S18", "S19", "S20") for row in plan.values())
assert all(set(row["early_scores"]) == {"D", "C"} and row["identity"] for row in plan.values())
before = Image.new("RGB", (2, 2), (10, 20, 30))
after = before.copy()
assert pixel_difference(before, after) == {"changed_percent": 0, "changed_pixels": 0, "size_changed": False}
after.putpixel((1, 0), (10, 20, 31))
assert pixel_difference(before, after)["changed_percent"] == 25, "one blue-channel unit must never be masked as noise"
assert pixel_difference(before, Image.new("RGB", (3, 2)))["size_changed"]
large = Image.new("RGB", (1200, 910))
altered = large.copy()
altered.putpixel((1199, 909), (0, 0, 1))
assert pixel_difference(large, altered)["changed_pixels"] == 1
assert pixel_difference(large, altered)["changed_percent"] > 0
css = css_files(ROOT)
assert css[0] == "app.css" and css.index("monolith-player-v3.css") > css.index("shell-v3-home.css")
assert css[-1] == "desktop-v3.css"
print("PASS exact RGB difference, dimension change, production CSS order and 42×7 complete concepts")
