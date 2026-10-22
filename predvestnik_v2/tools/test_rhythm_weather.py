"""Chunk weather of the endless Rhythm: schedule, effects, version gate and the season-2 switch."""
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import rhythm_v2 as r, rhythm_weather as w, seasons
from services import rhythm_v2 as service

assert r.CHUNK_SIZE == 20, "rhythm_weather assumes chunks of 20 signals"
assert [w.event_for_chunk(c) for c in range(12)] == [None, "calm", None, "gold", None, "storm", None, "spring", None, "calm", None, "gold"]
assert w.has_weather("rhythm-v2-rules-7") and w.has_weather(r.RULESET_VERSION)
assert not w.has_weather(r.PREVIOUS_RULESET_VERSION) and not w.has_weather("rhythm-v2-rules-5") and not w.has_weather(None)

on = {**r.new_perks(), "weather": 1}
off = r.new_perks()
plain, calm, gold, storm, spring = 1, 21, 61, 101, 141
assert r.window_ms(plain, on) == r.window_ms(plain, off)
assert r.window_ms(calm, on) > r.window_ms(calm, off) and r.window_ms(storm, on) < r.window_ms(storm, off)
score = lambda sig, perks: r.score_for_correct(elapsed_ms=0, allowed_window_ms=1000, combo_before=0, perks=perks, signal_no=sig)
assert score(gold, on) == score(gold, off) * 3 // 2 and score(calm, on) < score(calm, off)
assert score(plain, on) == score(plain, off)
assert r.after_error(health=5, perks=on, timed_out=True, signal_no=gold)[0] == 3, "a golden beat costs one heart more"
assert r.after_error(health=5, perks=off, timed_out=True, signal_no=gold)[0] == 4
assert r.after_correct(on, health=3, streak_after=8, signal_no=spring)[0] == 4, "spring heals every 8 in a row"
assert r.after_correct(on, health=3, streak_after=8, signal_no=calm)[0] == 3
assert r.after_correct(off, health=3, streak_after=8, signal_no=spring)[0] == 3
# clamps still hold under the harshest stack: Storm on top of every narrowing gift
narrow = {**on, "owned": {"iron_heart": 2, "gambit": 2, "echo_chain": 2}}
assert r.window_ms(storm, narrow) >= r.min_window_ms(storm)
# The season that is running keeps its rules; weather starts with season 2.
assert service.ruleset_for_new_run(datetime(2026, 10, 24, 23, 59, tzinfo=timezone.utc)) == r.PREVIOUS_RULESET_VERSION
assert service.ruleset_for_new_run(seasons.SEASON_TWO_START) == r.RULESET_VERSION
assert all(len(e["effect"]) <= 60 for e in w.EVENTS.values())
print("OK: rhythm weather — odd chunks in a fixed cycle, effects, clamps, ruleset gate, season-2 switch")
