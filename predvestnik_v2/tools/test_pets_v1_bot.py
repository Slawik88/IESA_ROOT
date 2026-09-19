#!/usr/bin/env python3
"""Contract proof for the chat-facing pet renderer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.handlers.pets_v1 import parse_activity_hours, parse_expedition_route, render_pet_overview

empty = render_pet_overview({"pets": []})
assert "пока нет питомцев" in empty and "одному ключу" in empty
text = render_pet_overview({"pets": [{
    "name": "<Лис>", "level": 4, "endurance": 95, "active": True,
    "effects": {"visual_stage": "Развитый облик"},
}]})
assert "&lt;Лис&gt;" in text
assert "4" in text and "95/100" in text and "активный" in text
assert "select_active_pet" not in text
active_text = render_pet_overview({"pets": [], "activity": {"kind": "trek", "status": "active", "ends_at": "2026-09-05T18:00:00+00:00"}})
assert "Поход идёт" in active_text and "2026-09-05 18:00" in active_text
ready_text = render_pet_overview({"pets": [], "activity": {"kind": "expedition", "status": "ready"}})
assert "Экспедиция: таймер завершён" in ready_text and "бот маршрут, осторожный" in ready_text
chosen_text = render_pet_overview({"pets": [], "activity": {"kind": "expedition", "status": "ready", "decision": "bold"}})
assert "выбран рискованный маршрут" in chosen_text
assert "Ключ уже зачислен" in chosen_text
assert parse_activity_hours("3") == 3 and parse_activity_hours(" 9 ") == 9
for invalid in ("", "4", "03", "три"):
    try: parse_activity_hours(invalid)
    except ValueError: pass
    else: raise AssertionError(f"invalid chat duration accepted: {invalid!r}")
assert parse_expedition_route(" осторожный ") == "careful"
assert parse_expedition_route("ровный") == "steady"
assert parse_expedition_route("рискованный") == "bold"
for invalid in ("", "смелый", "careful", "осторожный маршрут"):
    try: parse_expedition_route(invalid)
    except ValueError: pass
    else: raise AssertionError(f"invalid chat route accepted: {invalid!r}")
print("OK: chat pet renderer is escaped; duration/route input and key messaging are strict")
