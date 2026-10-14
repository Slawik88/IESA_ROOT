"""Static contract: the route picker shows odds/cap and the choose handler reports the real outcome."""
from __future__ import annotations

import pathlib

js = (pathlib.Path(__file__).resolve().parent.parent / "FastAPI" / "static" / "app.12.js").read_text(encoding="utf-8")

assert "function petRouteToast" in js
handler = js[js.index("window.petsV1Choose"):]
handler = handler[:handler.index("};")]
assert "petRouteToast(d)" in handler, "the choose handler must report the route outcome"
assert "'Маршрут выбран'" not in handler and "+1 🗝" not in handler, "no hard-coded result text in the handler"
toast = js[js.index("function petRouteToast"):]
toast = toast[:toast.index("window.petsV1Choose")]
for needle in ("r.success", "paid_mora", "amount_keys"):
    assert needle in toast, needle
assert "weekly_remaining_mora" in js and "chance_percent" in js and "scout: 'Разведка'" in js
print("OK: route picker and outcome toast are wired to the server fields")
