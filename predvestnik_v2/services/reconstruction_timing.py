"""Server-authoritative timing for Reconstruction actions.

The browser may keep sending ``delta_ms`` for protocol compatibility, but this
module replaces it with elapsed server wall time before the combat engine sees
the action.  Persisted wall time survives process restarts; long gaps are treated
as a pause instead of silently killing a mobile player in a background tab.
"""
from __future__ import annotations

import time
from typing import Any, Final, Mapping


CLOCK_STATE_KEY: Final = "_server_clock"
CLOCK_VERSION: Final = 1
MAX_SERVER_STEP_MS: Final = 500
IDLE_PAUSE_AFTER_MS: Final = 3_000


class ReconstructionTimingError(ValueError):
    pass


def server_now_ms() -> int:
    """UTC wall time works across requests and process restarts."""
    return time.time_ns() // 1_000_000


def _timestamp(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReconstructionTimingError(f"{label} must be a non-negative integer.")
    return value


def _valid_clock(clock: object) -> bool:
    if not isinstance(clock, dict) or clock.get("version") != CLOCK_VERSION:
        return False
    last_server_ms = clock.get("last_server_ms")
    return (
        isinstance(last_server_ms, int)
        and not isinstance(last_server_ms, bool)
        and last_server_ms >= 0
    )


def attach_server_clock(state: dict[str, Any], *, now_ms: int | None = None) -> None:
    """Start or intentionally rebase a persisted run clock."""
    if not isinstance(state, dict):
        raise ReconstructionTimingError("state must be a dictionary.")
    now = _timestamp(server_now_ms() if now_ms is None else now_ms, "now_ms")
    state[CLOCK_STATE_KEY] = {
        "version": CLOCK_VERSION,
        "last_server_ms": now,
        "paused_gap_ms": 0,
        "discarded_step_ms": 0,
    }


def server_timed_action(
    state: dict[str, Any],
    action: Mapping[str, Any],
    *,
    now_ms: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an action whose delta comes only from the server clock.

    The state clock is advanced here and is persisted only if the surrounding
    service transaction accepts and saves the combat action.
    """
    if not isinstance(state, dict):
        raise ReconstructionTimingError("state must be a dictionary.")
    if not isinstance(action, Mapping):
        raise ReconstructionTimingError("action must be a mapping.")
    now = _timestamp(server_now_ms() if now_ms is None else now_ms, "now_ms")
    clock = state.get(CLOCK_STATE_KEY)
    initialized = not _valid_clock(clock)
    if initialized:
        attach_server_clock(state, now_ms=now)
        clock = state[CLOCK_STATE_KEY]

    previous = _timestamp(clock["last_server_ms"], "last_server_ms")
    clock_rebased = now < previous
    raw_interval = 0 if clock_rebased else now - previous
    # A backwards NTP/host-clock correction must not create time, but keeping the
    # old future value would freeze a run until wall time caught up.
    clock["last_server_ms"] = now

    action_type = str(action.get("type") or "")
    applied = 0
    discarded = 0
    resumed_after_idle = False
    reason = "non_frame"
    if action_type in {"frame", "strike"}:
        if initialized:
            reason = "clock_initialized"
        elif clock_rebased:
            reason = "clock_rebased_backward"
        elif raw_interval > IDLE_PAUSE_AFTER_MS:
            resumed_after_idle = True
            discarded = raw_interval
            clock["paused_gap_ms"] = int(clock.get("paused_gap_ms", 0)) + raw_interval
            reason = "resume_after_idle"
        else:
            applied = min(raw_interval, MAX_SERVER_STEP_MS)
            discarded = max(0, raw_interval - applied)
            clock["discarded_step_ms"] = int(clock.get("discarded_step_ms", 0)) + discarded
            reason = "server_elapsed"

    sanitized = dict(action)
    sanitized["delta_ms"] = applied
    timing = {
        "mode": "server_wall_clock",
        "clock_version": CLOCK_VERSION,
        "client_delta_ms_ignored": True,
        "client_delta_was_supplied": "delta_ms" in action,
        "raw_interval_ms": raw_interval,
        "applied_ms": applied,
        "discarded_ms": discarded,
        "resumed_after_idle": resumed_after_idle,
        "clock_rebased": clock_rebased,
        "reason": reason,
    }
    return sanitized, timing


def public_timing_manifest() -> dict[str, Any]:
    return {
        "mode": "server_wall_clock",
        "clock_version": CLOCK_VERSION,
        "client_delta_ms_ignored": True,
        "max_server_step_ms": MAX_SERVER_STEP_MS,
        "idle_pause_after_ms": IDLE_PAUSE_AFTER_MS,
    }
