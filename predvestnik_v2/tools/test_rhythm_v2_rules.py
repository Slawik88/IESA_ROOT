"""Fast contract checks for the dependency-free Rune Rhythm rules."""
from core import rhythm_v2 as rules

seed = bytes.fromhex("9d" * 32)
fresh = rules.new_perks()
assert rules.expected_rune(seed, 1) in rules.RUNES
assert rules.expected_rune(seed, 1) == rules.expected_rune(seed, 1)
assert rules.chunk_for_signal(1) == 0 and rules.chunk_for_signal(30) == 0 and rules.chunk_for_signal(31) == 1
assert rules.speed_percent(31) > rules.speed_percent(1)
assert rules.window_ms(31) < rules.window_ms(1)
assert rules.window_ms(1) == rules.window_ms(12) == rules.BASE_WINDOW_MS == 2_000
assert rules.initial_health() == 5

# A gift is owed once per finished chunk and the clock waits for it.
assert not rules.draft_pending(next_signal_no=30, picks=0)
assert rules.draft_pending(next_signal_no=31, picks=0)
assert not rules.draft_pending(next_signal_no=31, picks=1)
assert rules.draft_pending(next_signal_no=91, picks=1)

# Offers: three distinct, repeatable, never without a safe gift, never ineligible.
for draft_no in range(1, 40):
    for health in (1, 2, 3, 5, 7):
        for perks in (fresh, {**fresh, "shield": 2, "echo": 1, "gambit": 1}):
            offers = rules.perk_offers(seed, draft_no, health=health, perks=perks)
            assert len(offers) == len(set(offers)) == 3
            assert offers == rules.perk_offers(seed, draft_no, health=health, perks=perks)
            assert any(rules.perk(item).kind == "safe" for item in offers), offers
            if health < 3:
                assert "blood_price" not in offers
            if health >= rules.MAX_HEALTH:
                assert "second_wind" not in offers
            if perks["gambit"]:
                assert "gambit" not in offers
            if perks["shield"] >= rules.MAX_SHIELDS:
                assert "shield" not in offers
assert len({rules.perk_offers(seed, n, health=5, perks=fresh) for n in range(1, 40)}) > 3, "offers must vary"

# Every gift changes an authoritative field.
health, perks = rules.apply_perk("second_wind", health=5, perks=fresh)
assert health == 6 and perks == fresh
assert rules.apply_perk("second_wind", health=6, perks=fresh)[0] == 7
health, perks = rules.apply_perk("shield", health=5, perks=fresh)
assert perks["shield"] == 1
health, perks = rules.apply_perk("blood_price", health=5, perks=fresh)
assert health == 4 and perks["bloody"] == rules.BLOODY_TAPS
base = rules.score_for_correct(elapsed_ms=10, allowed_window_ms=500, combo_before=0, perks=fresh)
golden = rules.apply_perk("golden_streak", health=5, perks=fresh)[1]
bloody = rules.apply_perk("blood_price", health=5, perks=fresh)[1]
gambit = rules.apply_perk("gambit", health=5, perks=fresh)[1]
slow = rules.apply_perk("slow_tide", health=5, perks=fresh)[1]
score = lambda p: rules.score_for_correct(elapsed_ms=10, allowed_window_ms=500, combo_before=0, perks=p)
assert score(golden) == base * 2 and score(bloody) == base * 3 and score(gambit) > base
assert rules.window_ms(5, slow) > rules.window_ms(5) > rules.window_ms(5, gambit)
for bad in ("foreign", ""):
    try:
        rules.perk(bad)
    except rules.RhythmRuleError:
        pass
    else:
        raise AssertionError("unknown gift must fail closed")
try:
    rules.apply_perk("blood_price", health=2, perks=fresh)
except rules.RhythmRuleError:
    pass
else:
    raise AssertionError("a gift that would be fatal must be refused")

# Counters run down, shield eats damage, echo keeps the combo, each only once.
perks = golden
for _ in range(rules.GOLDEN_TAPS):
    assert score(perks) == base * 2
    perks = rules.after_correct(perks)
assert score(perks) == base and perks["golden"] == 0
health, combo, perks = rules.after_error(health=5, combo=9, perks=fresh)
assert (health, combo) == (4, 0)
shielded = rules.apply_perk("shield", health=5, perks=fresh)[1]
health, combo, after = rules.after_error(health=5, combo=9, perks=shielded)
assert (health, combo, after["shield"]) == (5, 0, 0)
echoed = rules.apply_perk("echo", health=5, perks=fresh)[1]
health, combo, after = rules.after_error(health=5, combo=9, perks=echoed)
assert (health, combo, after["echo"]) == (4, 9, 0)
assert rules.after_error(health=1, combo=0, perks=fresh)[0] == 0

try:
    rules.expected_rune(seed, 0)
except rules.RhythmRuleError:
    pass
else:
    raise AssertionError("non-positive signal number must fail")

print("rhythm_v2_rules: rune gifts, offers, counters and negative cases OK")
