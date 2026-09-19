import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from core.quests_v1 import *

validate()
assert VIP_WEEKLY_REROLLS > STANDARD_WEEKLY_REROLLS
for period, count in (("daily", DAILY_COUNT), ("weekly", WEEKLY_COUNT)):
    solo = definitions(period, {"rhythm", "minesweeper"})
    assert len({quest["lane"] for quest in solo}) > count
    assert len({quest["metric"] for quest in solo}) >= count
assert all(q["source"] in {"any_game", "rhythm", "minesweeper", "mafia", "chests", "pets", "pet_care"} for q in QUESTS)
assert all("редк" not in q["title"].lower() for q in QUESTS)
assert any(q["metric"] == "minesweeper_win" for q in QUESTS)
assert any(q["metric"] == "minesweeper_hard_win" for q in QUESTS)
assert any(q["metric"] == "rhythm_augments_completed" for q in QUESTS)
assert any(q["metric"] == "mafia_win" for q in QUESTS)
assert any(q["metric"] == "chest_revealed" for q in QUESTS)
assert any(q["metric"] == "pet_activity_completed" for q in QUESTS)
assert any(q["metric"] == "pet_fed" for q in QUESTS)
assert not any(q["metric"] == "pet_card_found" for q in QUESTS), "random loot must not gate set completion"
print("OK: varied, source-aware quests v1 rules")
