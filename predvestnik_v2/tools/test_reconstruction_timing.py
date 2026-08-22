#!/usr/bin/env python3
"""Pure contract tests for server-authoritative Reconstruction time."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.reconstruction_timing import (  # noqa: E402
    CLOCK_STATE_KEY,
    IDLE_PAUSE_AFTER_MS,
    MAX_SERVER_STEP_MS,
    ReconstructionTimingError,
    attach_server_clock,
    public_timing_manifest,
    server_timed_action,
)


state = {}
attach_server_clock(state, now_ms=1_000)
assert state[CLOCK_STATE_KEY]["last_server_ms"] == 1_000

# A forged 500ms client delta cannot advance a clock that did not move.
forged, forged_meta = server_timed_action(
    state,
    {"type": "frame", "delta_ms": 500},
    now_ms=1_000,
)
assert forged["delta_ms"] == 0
assert forged_meta["client_delta_ms_ignored"] is True
assert forged_meta["client_delta_was_supplied"] is True

honest, honest_meta = server_timed_action(
    state,
    {"type": "frame", "delta_ms": 1},
    now_ms=1_120,
)
assert honest["delta_ms"] == 120
assert honest_meta["applied_ms"] == 120

# Slow requests cannot jump more than one bounded server step.
bounded, bounded_meta = server_timed_action(
    state,
    {"type": "frame", "delta_ms": 0},
    now_ms=2_020,
)
assert bounded["delta_ms"] == MAX_SERVER_STEP_MS
assert bounded_meta["discarded_ms"] == 400

# A background-tab gap becomes a pause, not a hidden defeat.
resumed, resumed_meta = server_timed_action(
    state,
    {"type": "frame", "delta_ms": 500},
    now_ms=2_020 + IDLE_PAUSE_AFTER_MS + 1,
)
assert resumed["delta_ms"] == 0
assert resumed_meta["resumed_after_idle"] is True
assert resumed_meta["reason"] == "resume_after_idle"

# Non-frame actions never move combat time but rebase the next frame.
choice, choice_meta = server_timed_action(
    state,
    {"type": "choose_upgrade", "upgrade_id": "heavy_echo", "delta_ms": 500},
    now_ms=6_000,
)
assert choice["delta_ms"] == 0 and choice_meta["reason"] == "non_frame"

# Standalone strike is also a timed combat action; otherwise repeated empty
# strikes could keep rebasing the clock without advancing the round.
strike_state = {}
attach_server_clock(strike_state, now_ms=7_000)
strike, strike_meta = server_timed_action(
    strike_state,
    {"type": "strike", "challenge_id": 1, "target_slot": "left"},
    now_ms=7_140,
)
assert strike["delta_ms"] == 140
assert strike_meta["reason"] == "server_elapsed"

# Повторяемые кнопки ветвей не могут бесплатно замораживать бой. Только
# модальное решение Клятвы действительно является паузой.
branch_clock = {}
attach_server_clock(branch_clock, now_ms=8_000)
toggle, toggle_meta = server_timed_action(
    branch_clock,
    {"type": "branch_action", "command": "forbidden_toggle", "enabled": True},
    now_ms=8_220,
)
assert toggle["delta_ms"] == 220 and toggle_meta["reason"] == "server_elapsed"
vow, vow_meta = server_timed_action(
    branch_clock,
    {"type": "branch_action", "command": "vow_keep"},
    now_ms=8_440,
)
assert vow["delta_ms"] == 0 and vow_meta["reason"] == "non_frame"

# A legacy active run without a clock freezes its first action and initializes.
legacy = {}
legacy_action, legacy_meta = server_timed_action(
    legacy,
    {"type": "frame", "delta_ms": 500},
    now_ms=9_000,
)
assert legacy_action["delta_ms"] == 0
assert legacy_meta["reason"] == "clock_initialized"
assert CLOCK_STATE_KEY in legacy

# A backwards wall-clock correction can never rewind or create time.
backwards, backwards_meta = server_timed_action(
    legacy,
    {"type": "frame", "delta_ms": 500},
    now_ms=8_000,
)
assert backwards["delta_ms"] == 0 and backwards_meta["raw_interval_ms"] == 0
assert backwards_meta["clock_rebased"] is True
assert backwards_meta["reason"] == "clock_rebased_backward"
assert legacy[CLOCK_STATE_KEY]["last_server_ms"] == 8_000

# Corrupt/partial persisted clock metadata is safely replaced instead of
# crashing an otherwise recoverable legacy run.
corrupt = {CLOCK_STATE_KEY: {"version": 1, "last_server_ms": "not-a-timestamp"}}
recovered, recovered_meta = server_timed_action(
    corrupt,
    {"type": "frame"},
    now_ms=12_000,
)
assert recovered["delta_ms"] == 0
assert recovered_meta["reason"] == "clock_initialized"
assert corrupt[CLOCK_STATE_KEY]["last_server_ms"] == 12_000

manifest = public_timing_manifest()
assert manifest == {
    "mode": "server_wall_clock",
    "clock_version": 1,
    "client_delta_ms_ignored": True,
    "max_server_step_ms": 500,
    "idle_pause_after_ms": 3_000,
}

for invalid in (-1, True, 1.5, "100"):
    try:
        attach_server_clock({}, now_ms=invalid)
    except ReconstructionTimingError:
        pass
    else:
        raise AssertionError(f"Invalid server timestamp accepted: {invalid!r}")

print("reconstruction_timing: server clock+pause+forged delta guard  OK")
