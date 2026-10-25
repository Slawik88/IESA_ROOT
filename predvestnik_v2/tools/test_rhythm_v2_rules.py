"""Fast contract checks for the dependency-free Rune Rhythm rules."""
from core import rhythm_v2 as rules

seed = bytes.fromhex("9d" * 32)
fresh = rules.new_perks()
take = lambda perk_id, health=5, perks=fresh: rules.apply_perk(perk_id, health=health, perks=perks)
score = lambda p, elapsed=10, window=500, combo=0: rules.score_for_correct(
    elapsed_ms=elapsed, allowed_window_ms=window, combo_before=combo, perks=p)

assert rules.expected_rune(seed, 1) == rules.expected_rune(seed, 1) in rules.RUNES
assert rules.CHUNK_SIZE == 20
assert rules.chunk_for_signal(1) == 0 and rules.chunk_for_signal(20) == 0 and rules.chunk_for_signal(21) == 1
assert rules.initial_health() == 5

# The pace is compounding and every run has a hard end: the window floor sinks
# below any human reaction, so nobody can play forever.
assert rules.window_ms(1) == rules.window_ms(15) == rules.BASE_WINDOW_MS == 2_200
assert rules.speed_percent(21) == 108 and rules.speed_percent(41) == 116
windows = [rules.window_ms(1 + 20 * chunk) for chunk in range(60)]
assert all(a >= b for a, b in zip(windows, windows[1:])), "the window never widens with progress"
assert windows[-1] == rules.HARD_FLOOR_MS < rules.MIN_WINDOW_MS
assert rules.min_window_ms(1) == rules.MIN_WINDOW_MS and rules.min_window_ms(10**6) == rules.HARD_FLOOR_MS

# A gift is owed once per finished chunk and the clock waits for it.
assert not rules.draft_pending(next_signal_no=20, picks=0)
assert rules.draft_pending(next_signal_no=21, picks=0)
assert not rules.draft_pending(next_signal_no=21, picks=1)
assert rules.draft_pending(next_signal_no=61, picks=1)

# Offers: three distinct, repeatable, with a safe gift, nothing ineligible; the pool is wide.
seen = set()
for draft_no in range(1, 60):
    for health in (1, 2, 3, 5, 7):
        offers = rules.perk_offers(seed, draft_no, health=health, perks=fresh)
        assert len(offers) == len(set(offers)) == 3
        assert offers == rules.perk_offers(seed, draft_no, health=health, perks=fresh)
        assert any(rules.perk(item).kind == "safe" for item in offers), offers
        assert "breather" not in offers, "the filler is not part of the normal pool"
        if health < 3:
            assert "blood_price" not in offers
        if health <= 2:
            assert "glass_cannon" not in offers
        if health >= rules.MAX_HEALTH:
            assert "iron_heart" not in offers
        seen.update(offers)
assert len(seen) >= 12, "offers must vary across the whole pool"

# Every gift carries a bonus AND a price, both written down and both real.
assert len(rules.PERKS) == 22
for item in rules.PERKS:
    assert item.bonus and item.cost, item.id
good_fields = ("heal", "shield", "ebb", "bloody", "regen_every", "combo_step", "timeout_free", "sharp_eye", "cadence_every", "low_health_bonus_pct", "recovery_signals",
               "streak_bonus_pct", "combo_keep_pct", "shield_every", "revive")
for item in rules.PERKS:
    pluses = item.window_pct > 0 or item.score_pct > 0 or any(getattr(item, f) for f in good_fields)
    minuses = (item.window_pct < 0 or item.score_pct < 0 or item.pace_pct > 0 or item.damage_extra
               or item.wrong_extra or item.cap_health or item.sacrifice or item.sharp_eye or item.id == "blood_price")
    assert pluses and minuses, f"{item.id} must have both a bonus and a cost"

# Effects.
health, perks = take("iron_heart"); assert health == 7 and rules.window_ms(5, perks) < rules.window_ms(5)
base = score(fresh)
assert score(take("gold_vein")[1]) > base and take("gold_vein")[1]["owned"] == {"gold_vein": 1}
assert score(take("tailwind")[1]) < base and rules.window_ms(5, take("tailwind")[1]) > rules.window_ms(5)
assert score(take("sprint")[1]) > base and rules.speed_percent(5, take("sprint")[1]) == 112
assert rules.window_ms(5, take("gambit")[1]) < rules.window_ms(5) and score(take("gambit")[1]) > base
assert score(take("blood_price")[1]) > base * 2 and take("blood_price")[0] == 4
assert take("glass_cannon")[0] == 2 and score(take("glass_cannon")[1]) > base
assert score(take("echo_chain")[1], combo=10) > score(fresh, combo=10)
sharp = take("sharp_eye")[1]
assert score(sharp, elapsed=10) > base and score(sharp, elapsed=480) < score(fresh, elapsed=480)
ebb = take("ebb_tide")[1]
assert rules.window_ms(5, ebb) > rules.window_ms(5) and rules.speed_percent(5, ebb) == 108
for _ in range(12):
    _, ebb = rules.after_correct(ebb, health=5, streak_after=1)
assert ebb["ebb"] == 0

# Stacking limits and fatal gifts are refused.
stacked = take("stone_shield")[1]; stacked = take("stone_shield", perks=stacked)[1]
for bad, kwargs in (("stone_shield", {"perks": stacked}), ("blood_price", {"health": 2}),
                    ("glass_cannon", {"health": 2}), ("iron_heart", {"health": 7}), ("foreign", {})):
    try:
        take(bad, **kwargs)
    except rules.RhythmRuleError:
        pass
    else:
        raise AssertionError(f"{bad} must fail closed")

# Mistakes: a shield eats a whole mistake; gifts decide how deep it cuts.
assert rules.after_error(health=5, perks=fresh, timed_out=False)[0] == 4
health, perks = rules.after_error(health=5, perks=take("stone_shield")[1], timed_out=False)
assert health == 5 and perks["shield"] == 0
assert rules.after_error(health=5, perks=take("gold_vein")[1], timed_out=False)[0] == 3
steady = take("steady_hand")[1]
assert rules.after_error(health=5, perks=steady, timed_out=False)[0] == 3          # wrong rune: +1 heart
free_health, steady = rules.after_error(health=5, perks=steady, timed_out=True)    # first miss free
assert free_health == 5
assert rules.after_error(health=5, perks=steady, timed_out=True)[0] == 4           # every second miss costs
assert rules.after_error(health=1, perks=fresh, timed_out=False)[0] == 0
# Vampire: +1 heart every 15 correct in a row, never past the cap.
vampire = take("vampire")[1]
assert rules.after_correct(vampire, health=5, streak_after=15)[0] == 6
assert rules.after_correct(vampire, health=5, streak_after=14)[0] == 5
assert rules.after_correct(vampire, health=7, streak_after=30)[0] == 7
# The filler keeps a late draft from running dry.
late = {**fresh, "owned": {item.id: item.max_stack for item in rules.PERKS if not item.filler}}
assert rules.perk_offers(seed, 40, health=5, perks=late) == ("breather",)
# Stale or unknown stored state is tolerated.
assert rules.normalize_perks({"owned": {"golden_streak": 2, "shield": 1}, "golden": 5})["owned"] == {}
assert rules.normalize_perks(None) == fresh

# Series gifts: Hot streak counts from the 10th correct tap in a row, the Anchor keeps half of the series, the Recharge
# builds one shield per 20, the Phoenix saves the run once, the Trade pays one heart for +30%.
hot = take("hot_streak")[1]
assert score(hot, combo=9) < score(fresh, combo=9) and score(hot, combo=10) > score(fresh, combo=10)
assert rules.combo_after_error(21, fresh) == 0 and rules.combo_after_error(21, take("anchor")[1]) == 10
assert rules.combo_after_error(21, {**fresh, "owned": {"anchor": 99}}) == 21 * rules.MAX_COMBO_KEEP_PCT // 100, "no stack makes the series unbreakable"
recharge = take("recharge")[1]
assert rules.after_correct(recharge, health=5, streak_after=19)[1]["shield"] == 0
assert rules.after_correct(recharge, health=5, streak_after=20)[1]["shield"] == 1
assert rules.after_correct({**recharge, "shield": 1}, health=5, streak_after=40)[1]["shield"] == 1, "one spare shield at most"
assert rules.after_correct(take("stone_shield")[1], health=5, streak_after=20)[1]["shield"] == 1, "no Recharge, no charging"
health, phoenix = take("phoenix")
assert phoenix["revive"] == 2
health, effects = rules.after_error(health=1, perks=phoenix, timed_out=False)
assert health == 2 and effects["revive"] == 0, "the last mistake leaves two hearts, once"
assert rules.after_error(health=1, perks=effects, timed_out=False)[0] == 0, "and then the run really ends"
assert rules.after_error(health=3, perks=phoenix, timed_out=False)[0] == 2 and phoenix["revive"] == 2, "an ordinary mistake does not spend it"
assert rules.after_error(health=1, perks={**phoenix, "shield": 1}, timed_out=False) == (1, {**phoenix, "shield": 0}), "a shield is spent before the Phoenix"
assert rules.normalize_perks({"revive": 99})["revive"] == rules.BASE_HEALTH and rules.normalize_perks({"revive": -3})["revive"] == 0
assert take("trade")[0] == 4 and score(take("trade")[1]) > base
try:
    take("trade", health=1)
except rules.RhythmRuleError:
    pass
else:
    raise AssertionError("the Trade must not kill")
# A run keeps the gift pool of its ruleset: nothing new appears in a run that is already going.
old_pool = {item.id for item in rules.PERKS if rules.in_pool(item, "rhythm-v2-rules-7")}
assert len(old_pool) == 17 and not {"hot_streak", "anchor", "recharge", "phoenix", "trade"} & old_pool
assert {item.id for item in rules.PERKS if rules.in_pool(item, "rhythm-v2-rules-5")} == old_pool - {"metronome", "last_spark", "second_wind"}
assert len({item.id for item in rules.PERKS if rules.in_pool(item, None)}) == 22 and rules.RULESET_VERSION in rules.SUPPORTED_RULESETS
for draft_no in range(1, 200):
    for version, forbidden in (("rhythm-v2-rules-7", {"hot_streak", "anchor", "recharge", "phoenix", "trade"}), ("rhythm-v2-rules-5", {"metronome", "last_spark", "second_wind", "hot_streak", "anchor", "recharge", "phoenix", "trade"})):
        assert not forbidden & set(rules.perk_offers(seed, draft_no, health=5, perks=fresh, ruleset_version=version)), (version, draft_no)
assert {gift for draft_no in range(1, 300) for gift in rules.perk_offers(seed, draft_no, health=5, perks=fresh)} >= {"hot_streak", "anchor", "recharge", "phoenix", "trade"}

try:
    rules.expected_rune(seed, 0)
except rules.RhythmRuleError:
    pass
else:
    raise AssertionError("non-positive signal number must fail")

print("rhythm_v2_rules: rune gifts with bonus and cost, finite pace and negative cases OK")
