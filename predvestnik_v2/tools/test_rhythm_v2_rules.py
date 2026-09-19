"""Fast contract checks for the dependency-free Rune Rhythm rules."""
from core import rhythm_v2 as rules

seed = bytes.fromhex("9d" * 32)
offers = rules.offers_for_seed(seed)
assert len(offers["positive"]) == len(set(offers["positive"])) == 3
assert len(offers["negative"]) == len(set(offers["negative"])) == 3

selected = rules.validate_selection(
    offers, positive=offers["positive"][:2], negative=offers["negative"][:2]
)
assert len(selected) == 4
assert rules.expected_rune(seed, 1) in rules.RUNES
assert rules.expected_rune(seed, 1) == rules.expected_rune(seed, 1)
assert rules.chunk_for_signal(1) == 0
assert rules.chunk_for_signal(31) == 1
assert rules.speed_percent(31) > rules.speed_percent(1)
assert rules.window_ms(31) < rules.window_ms(1)
assert rules.window_ms(1) == rules.window_ms(12) == rules.BASE_WINDOW_MS
assert rules.window_ms(1) == 2_000
assert rules.initial_health() == 5
assert rules.initial_health(selected) >= 1
assert rules.score_for_correct(elapsed_ms=10, allowed_window_ms=500, combo_before=0, selected_ids=selected) > 0

for bad_positive, bad_negative in ((offers["positive"][:1], offers["negative"][:2]), (("foreign", "also_foreign"), offers["negative"][:2])):
    try:
        rules.validate_selection(offers, positive=bad_positive, negative=bad_negative)
    except rules.RhythmRuleError:
        pass
    else:
        raise AssertionError("invalid augmentation choice must fail closed")

try:
    rules.expected_rune(seed, 0)
except rules.RhythmRuleError:
    pass
else:
    raise AssertionError("non-positive signal number must fail")

print("rhythm_v2_rules: catalogue+offers+progression+negative cases OK")
