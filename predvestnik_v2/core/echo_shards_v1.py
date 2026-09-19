"""Pure contract for the future Echo Shards compensation subsystem.

Echo Shards are deliberately not a wallet currency.  They have no Stars price,
exchange route, transfer, shop item or public balance endpoint in this version.
Only a future server-authoritative duplicate writer may call the internal
service after it has recorded a terminal source event.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Final, Mapping


POLICY_VERSION: Final = "echo-shards-v1-2026-09-07"
CURRENCY_CODE: Final = "echo_shards"
DISPLAY_NAME: Final = "Осколки Эха"
DISPLAY_ICON: Final = "◈"
SUPPORTED_SOURCE_KINDS: Final = (
    "pet_v1_max_duplicate",
)
FIXED_SOURCE_AMOUNTS: Final = {
    "pet_v1_max_duplicate": 1,
}


class EchoShardPolicyError(ValueError):
    """The proposed internal compensation does not satisfy the policy."""


@dataclass(frozen=True, slots=True)
class MaxDuplicateCompensation:
    """Trusted facts captured by a terminal source writer, never by a client."""

    source_kind: str
    source_event_id: str
    source_line_id: int
    collectible_kind: str
    collectible_id: str
    observed_level: int
    observed_cap: int
    amount: int
    source_snapshot: Mapping[str, object]


def _identifier(value: object, field: str, *, max_length: int = 160) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_length or any(ord(char) < 32 for char in normalized):
        raise EchoShardPolicyError(f"{field} must contain 1..{max_length} printable characters.")
    return normalized


def _strict_int(value: object, field: str, *, minimum: int) -> int:
    """Reject coercion: ``1.9`` must never become a valid reward amount."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "non-negative" if minimum == 0 else "positive"
        raise EchoShardPolicyError(f"{field} must be a {qualifier} integer.")
    return value


def canonical_snapshot_fingerprint(snapshot: Mapping[str, object]) -> str:
    """Hash the exact source facts so a replay cannot silently change them."""
    try:
        encoded = json.dumps(
            dict(snapshot), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EchoShardPolicyError("source_snapshot must contain canonical JSON values.") from exc
    return sha256(encoded.encode("utf-8")).hexdigest()


def validate_max_duplicate(event: MaxDuplicateCompensation) -> MaxDuplicateCompensation:
    """Fail closed unless a source proves that this exact collectible is capped."""
    source_kind = _identifier(event.source_kind, "source_kind", max_length=64)
    if source_kind not in SUPPORTED_SOURCE_KINDS:
        raise EchoShardPolicyError("Unsupported Echo Shard source.")
    source_event_id = _identifier(event.source_event_id, "source_event_id")
    collectible_kind = _identifier(event.collectible_kind, "collectible_kind", max_length=64)
    collectible_id = _identifier(event.collectible_id, "collectible_id")
    source_line_id = _strict_int(event.source_line_id, "source_line_id", minimum=0)
    level = _strict_int(event.observed_level, "observed_level", minimum=1)
    cap = _strict_int(event.observed_cap, "observed_cap", minimum=1)
    if level < 1 or cap < 1 or level != cap:
        raise EchoShardPolicyError("Echo Shards require a collectible already at its current cap.")
    amount = _strict_int(event.amount, "amount", minimum=1)
    if amount != FIXED_SOURCE_AMOUNTS[source_kind]:
        raise EchoShardPolicyError("This duplicate source has a fixed Echo Shard compensation amount.")
    if not isinstance(event.source_snapshot, Mapping):
        raise EchoShardPolicyError("source_snapshot must be a mapping.")
    snapshot = dict(event.source_snapshot)
    canonical_snapshot_fingerprint(snapshot)
    return MaxDuplicateCompensation(
        source_kind=source_kind,
        source_event_id=source_event_id,
        source_line_id=source_line_id,
        collectible_kind=collectible_kind,
        collectible_id=collectible_id,
        observed_level=level,
        observed_cap=cap,
        amount=amount,
        source_snapshot=snapshot,
    )
