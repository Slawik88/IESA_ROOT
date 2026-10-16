import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from core.quests_v1 import *

validate()
assert VIP_WEEKLY_REROLLS > STANDARD_WEEKLY_REROLLS
for period, count in (("daily", DAILY_COUNT), ("weekly", WEEKLY_COUNT)):
    solo = definitions(period, {"rhythm", "minesweeper"})
    assert len({quest["lane"] for quest in solo}) > count
    assert len({quest["metric"] for quest in solo}) >= count
assert all(q["source"] in {"any_game", "rhythm", "minesweeper", "mafia", "chests", "pets", "pet_care", "pets_v2", "pets_v2_daily", "pets_v2_trek_daily", "pets_v2_expedition_daily", "pets_v2_watch_daily"} for q in QUESTS)
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

# No paywall, RNG outcome or late-day 12-hour watch is needed for a daily set.
from datetime import datetime, timezone, timedelta
pet = {'id':1,'species_id':'moss_cat','energy':100}
morning = datetime(2026,10,18,8,tzinfo=timezone.utc)
assert 'pets_v2_watch_daily' in pet_daily_sources([pet],[],now=morning)
late = morning.replace(hour=23)
assert not pet_daily_sources([pet],[],now=late)
ready_watch = {'pet_id':1,'kind':'watch','ends_at':late-timedelta(minutes=1)}
assert 'pets_v2_watch_daily' in pet_daily_sources([pet],[ready_watch],now=late)
assert not pet_daily_sources([pet],[{**ready_watch,'ends_at':late+timedelta(hours=2)}],now=late)
assert not pet_daily_sources([{**pet,'energy':0}],[],now=morning)
assert not pet_daily_sources([pet],[{'pet_id':2,'companion_id':1,'kind':'watch','ends_at':morning+timedelta(days=2)}],now=morning)
assert not pet_daily_sources([],[],now=morning)
for period in ('daily','weekly'):
    old = definitions(period,{'rhythm','minesweeper','pets'})
    assert not any(q['metric'] in {'pet_trek_completed','pet_expedition_completed','pet_watch_completed'} for q in old)
print('OK: pet daily eligibility respects UTC reset, occupied companions and stored energy')
