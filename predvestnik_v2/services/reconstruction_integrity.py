"""Shadow-only integrity evidence for Reconstruction runs.

The module never bans a user and never settles a reward.  It records bounded
server-derived evidence so a future terminal processor can quarantine a result
for review instead of trusting client claims or making an irreversible decision.
"""
from __future__ import annotations

from typing import Any, Final, Mapping


INTEGRITY_STATE_KEY: Final = "_integrity"
MIN_PLAUSIBLE_REACTION_MS: Final = 70
REVIEW_MIN_SAMPLES: Final = 5
REVIEW_MIN_FAST_SAMPLES: Final = 3


def record_strike(state: dict[str, Any], strike: Mapping[str, Any] | None) -> None:
    """Record only accepted, server-timed tap evidence."""
    if not isinstance(strike, Mapping) or not strike.get("accepted"):
        return
    reaction = strike.get("reaction_ms")
    if isinstance(reaction, bool) or not isinstance(reaction, int) or reaction < 0:
        return
    evidence = state.setdefault(INTEGRITY_STATE_KEY, {
        "reaction_samples": 0,
        "reaction_total_ms": 0,
        "fastest_reaction_ms": None,
        "implausibly_fast_samples": 0,
    })
    evidence["reaction_samples"] = int(evidence.get("reaction_samples", 0)) + 1
    evidence["reaction_total_ms"] = int(evidence.get("reaction_total_ms", 0)) + reaction
    fastest = evidence.get("fastest_reaction_ms")
    evidence["fastest_reaction_ms"] = reaction if fastest is None else min(int(fastest), reaction)
    if reaction < MIN_PLAUSIBLE_REACTION_MS:
        evidence["implausibly_fast_samples"] = int(
            evidence.get("implausibly_fast_samples", 0)
        ) + 1


def verdict(state: Mapping[str, Any]) -> dict[str, Any]:
    evidence = state.get(INTEGRITY_STATE_KEY)
    if not isinstance(evidence, Mapping):
        evidence = {}
    samples = max(0, int(evidence.get("reaction_samples", 0)))
    fast = max(0, int(evidence.get("implausibly_fast_samples", 0)))
    total = max(0, int(evidence.get("reaction_total_ms", 0)))
    fastest = evidence.get("fastest_reaction_ms")
    review_required = samples >= REVIEW_MIN_SAMPLES and fast >= REVIEW_MIN_FAST_SAMPLES
    return {
        "status": "review_required" if review_required else "clear",
        "review_required": review_required,
        "reaction_samples": samples,
        "implausibly_fast_samples": fast,
        "fastest_reaction_ms": int(fastest) if isinstance(fastest, int) else None,
        "average_reaction_ms": round(total / samples) if samples else None,
        "automatic_ban": False,
    }


def terminal_result(
    *,
    run_id: int,
    revision: int,
    outcome: str,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    if outcome not in {"won", "lost", "cancelled"}:
        raise ValueError("Terminal outcome must be won, lost or cancelled.")
    if run_id < 1 or revision < 0:
        raise ValueError("Terminal run id and revision are invalid.")
    return {
        "id": f"reconstruction:{run_id}:terminal",
        "outcome": outcome,
        "server_revision": revision,
        "integrity": verdict(state),
    }


def public_integrity_manifest() -> dict[str, Any]:
    return {
        "mode": "shadow_review",
        "minimum_plausible_reaction_ms": MIN_PLAUSIBLE_REACTION_MS,
        "review_min_samples": REVIEW_MIN_SAMPLES,
        "review_min_fast_samples": REVIEW_MIN_FAST_SAMPLES,
        "automatic_ban": False,
        "real_rewards_enabled": False,
    }
