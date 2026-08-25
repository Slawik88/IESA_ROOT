"""Regression contract for immutable difficulty plans and earned-loss shadow rewards."""
from __future__ import annotations

from decimal import Decimal
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.economy_v3 import evaluate_reconstruction_reward_shadow
from core.reconstruction_difficulty import (
    ReconstructionDifficultyError,
    build_wave_plan,
    state_difficulty_snapshot,
)
from services import reconstruction, reconstruction_combat as combat, reconstruction_integrity
from tools.reconstruction_preview_api import Handler


base = copy.deepcopy(combat.ENCOUNTER_WAVES["e01_two_bells"])
standard_id, standard = build_wave_plan("e01_two_bells", "standard", base)
support_id, support = build_wave_plan("e01_two_bells", "support", base)
challenge_id, challenge = build_wave_plan("e01_two_bells", "challenge", base)
assert standard_id == "standard" and support_id == "support" and challenge_id == "challenge"
assert standard == list(base)
assert [wave["hp"] for wave in support] == [741.0, 1092.0, 1482.0]
assert [wave["duration_ms"] for wave in support] == [26000, 31200, 37700]
assert [wave["signal_ms"] for wave in support] == [1420, 1270, 1170]
assert [wave["hp"] for wave in challenge] == [1121.0, 1652.0, 2242.0]
assert base == combat.ENCOUNTER_WAVES["e01_two_bells"], "profile build mutated global waves"

try:
    build_wave_plan("e02_shattered_causeway", "support", combat.ENCOUNTER_WAVES["e02_shattered_causeway"])
    raise AssertionError("un-authored support profile was accepted outside e01")
except ReconstructionDifficultyError:
    pass

support_state = combat.new_encounter(seed=11, difficulty_id="support")
challenge_state = combat.new_encounter(seed=12, difficulty_id="challenge")
standard_state = combat.new_encounter(seed=13, difficulty_id="standard")
assert support_state["difficulty"]["id"] == "support"
assert challenge_state["difficulty"]["id"] == "challenge"
assert standard_state["difficulty"]["id"] == "standard"
assert support_state["wave"]["hp_max"] == 741.0
assert challenge_state["wave"]["hp_max"] == 1121.0
assert standard_state["wave"]["hp_max"] == 950.0
assert combat.ENCOUNTER_WAVES["e01_two_bells"] == base, "runs leaked profile changes into content"
round_trip = combat.loads(combat.dumps(support_state))
assert round_trip["difficulty"] == support_state["difficulty"]
assert combat.public_state(round_trip)["difficulty"]["id"] == "support"

snapshot = state_difficulty_snapshot("e01_two_bells", "standard", base)
first_ratio = Decimal(str(snapshot["wave_plan"][0]["hp"] / sum(item["hp"] for item in snapshot["wave_plan"])))

def loss(progress: Decimal, accepted_before: int = 0):
    return evaluate_reconstruction_reward_shadow(
        outcome="lost", run_kind="campaign", accepted_results_last_7_days=accepted_before,
        server_terminal_confirmed=True, first_branch_reached=True,
        correct_signals=4, wrong_signals=3, missed_signals=3,
        reward_progress_ratio=progress, first_rewardable_progress_ratio=first_ratio,
    )

first_wave = loss(first_ratio)
near_win = loss(Decimal("1"))
assert (first_wave.mora, first_wave.lead_unit_xp, first_wave.support_unit_xp_each) == (35, 45, 27)
assert (near_win.mora, near_win.lead_unit_xp, near_win.support_unit_xp_each) == (60, 60, 36)
assert first_wave.loss_reward_factor == Decimal("0.35")
assert near_win.loss_reward_factor == Decimal("0.60")
assert loss(first_ratio, accepted_before=35).mora == 26
assert loss(Decimal("1"), accepted_before=35).mora == 45
assert loss(first_ratio, accepted_before=105).mora == 18
assert loss(Decimal("1"), accepted_before=105).mora == 30

not_earned = evaluate_reconstruction_reward_shadow(
    outcome="lost", run_kind="campaign", accepted_results_last_7_days=0,
    server_terminal_confirmed=True, first_branch_reached=False,
    correct_signals=10, wrong_signals=0, missed_signals=0,
    reward_progress_ratio=first_ratio, first_rewardable_progress_ratio=first_ratio,
)
assert not not_earned.eligible and not_earned.mora == 0

# Every public adapter must return a JSON-native shadow decision.  The preview
# bridge uses Python's strict json encoder, while FastAPI serializes Decimals
# implicitly; neither response may leak a Decimal from the progress snapshot.
won_state = copy.deepcopy(standard_state)
won_state["status"] = "won"
won_state["round"] = len(won_state["difficulty"]["wave_plan"])
won_state["mastery"].update({"correct_taps": 10, "mistakes": 0, "missed_signals": 0})
terminal = reconstruction_integrity.terminal_result(
    run_id=1, revision=0, outcome="won", state=won_state,
)
preview_shadow = Handler._preview_shadow_reward(won_state, terminal)
assert preview_shadow["eligible"] is True
assert preview_shadow["projected"]["mora"] == 100
assert isinstance(preview_shadow["progress"]["first_rewardable_ratio"], float)
json.dumps(preview_shadow)
print("reconstruction_difficulty: immutable profiles + earned-loss boundaries  OK")
