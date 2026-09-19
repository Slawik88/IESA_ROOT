#!/usr/bin/env python3
"""Small contract proof for the chat-facing, read-only quest renderer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.handlers.quests_v1 import render_quest_overview

view = {
    "daily": {"quests": [{"title": "Сыграй <тег>", "progress": 1, "target": 3, "completed": False}]},
    "weekly": {"quests": [{"title": "Заверши матч", "progress": 5, "target": 5, "completed": True}]},
    "rerolls": {"remaining": 2, "limit": 2},
    "rewards": {"items": {
        "daily": {"amount_mora": 20, "amount_keys": 1},
        "weekly": {"amount_mora": 100, "amount_keys": 1},
        "combined": {"amount_mora": 75, "amount_keys": 0},
    }},
}
text = render_quest_overview(view)
assert "Сыграй &lt;тег&gt;" in text
assert "1/3" in text and "5/5" in text and "✅" in text
assert "2/2" in text
assert "Награды: день: 20 Моры + 1 ключ; неделя: 100 Моры + 1 ключ; всё вместе: 75 Моры." in text
print("OK: chat quest renderer is escaped and shows the authoritative reward snapshot")
