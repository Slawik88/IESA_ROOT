#!/usr/bin/env python3
"""The UI smoke suite (tools/ui_smoke.py) may only open screens that exist: a screen opener that was renamed or deleted must fail here, without a browser."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke_checks import DOCK_TABS, SCREENS  # noqa: E402

STATIC = ROOT / "FastAPI/static"
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
parts = re.search(r"_APP_JS_PARTS = \[\"app.load-scheduler.js\"\] \+ \[f\"app\.\{i:02d\}\.js\" for i in \(([^)]*)\)\]", main_py)
assert parts, "the part list of the app script changed: update this test"
js = (STATIC / 'app.load-scheduler.js').read_text(encoding='utf-8') + "\n" + "\n".join((STATIC / f"app.{int(n):02d}.js").read_text(encoding="utf-8") for n in parts.group(1).split(","))
html = (STATIC / "index.html").read_text(encoding="utf-8")

defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js)) | set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=", js)) | set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()", js))
for name, opener in SCREENS:
    for call in re.findall(r"(?<![\w.$'\"])([A-Za-z_$][\w$]*)\(", opener):
        if call in {"setTimeout", "typeof"} or call.startswith("lkView"):
            continue
        assert call in defined or call in {"querySelector"}, f"screen {name!r}: {call}() is not defined in the app script"

for tab in DOCK_TABS:
    assert f'data-page="{tab}"' in html or f"data-page='{tab}'" in html or f"data-page=\\\"{tab}\\\"" in html or tab in js, f"dock tab {tab!r} is gone"

# Admin screens stay out of the suite: they are being rewritten elsewhere.
assert not any(name.startswith(("admin", "global", "console")) for name, _ in SCREENS)
print(f"OK: the UI smoke suite opens {len(SCREENS)} screens and {len(DOCK_TABS)} dock tabs, all of which exist")
