"""Internal-only Echo Shard compensation writer.

There is deliberately no router, bot command, checkout, exchange or item spend
adapter for this service.  A future source writer calls it in the same outer
transaction that persists its terminal duplicate event.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from core.echo_shards_v1 import (
    POLICY_VERSION, EchoShardPolicyError, MaxDuplicateCompensation,
    canonical_snapshot_fingerprint, validate_max_duplicate,
)
from infrastructure.repositories import echo_shards_v1 as repo


class EchoShardConflict(EchoShardPolicyError):
    """A terminal source identity was reused with different facts."""


@dataclass(frozen=True, slots=True)
class EchoShardReceipt:
    compensation_id: str
    applied: bool
    amount: int
    balance_before: int
    balance_after: int


def _same_facts(row: dict, event: MaxDuplicateCompensation, user_id: int, snapshot_hash: str) -> bool:
    return (
        int(row["user_id"]) == int(user_id)
        and str(row["collectible_kind"]) == event.collectible_kind
        and str(row["collectible_id"]) == event.collectible_id
        and int(row["observed_level"]) == event.observed_level
        and int(row["observed_cap"]) == event.observed_cap
        and int(row["amount"]) == event.amount
        and str(row["policy_version"]) == POLICY_VERSION
        and str(row.get("source_snapshot_hash") or "") == snapshot_hash
    )


async def compensate_max_duplicate(db, *, user_id: int, event: MaxDuplicateCompensation) -> EchoShardReceipt:
    """Append exactly one internal compensation for one immutable source line."""
    event = validate_max_duplicate(event)
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        return await compensate_max_duplicate_in_transaction(db, user_id=int(user_id), event=event)


async def compensate_max_duplicate_in_transaction(
    db, *, user_id: int, event: MaxDuplicateCompensation,
) -> EchoShardReceipt:
    """Internal variant for a source writer that owns the outer atomic transaction.

    The caller must already hold the per-user advisory lock.  Keeping the source
    receipt, pet level transition and compensation in one transaction prevents
    a level-16 duplicate from becoming either a free level change or a free shard.
    """
    event = validate_max_duplicate(event)
    snapshot_hash = canonical_snapshot_fingerprint(event.source_snapshot)
    replay = await repo.find_by_source(
        db, user_id=int(user_id), source_kind=event.source_kind, source_event_id=event.source_event_id,
        source_line_id=event.source_line_id,
    )
    if replay:
        if not _same_facts(replay, event, int(user_id), snapshot_hash):
            raise EchoShardConflict("Source duplicate identity is already bound to different compensation facts.")
        return EchoShardReceipt(
            compensation_id=str(replay["id"]), applied=False, amount=int(replay["amount"]),
            balance_before=int(replay["balance_before"]), balance_after=int(replay["balance_after"]),
        )
    before = await repo.lock_account(db, int(user_id))
    compensation_id = uuid4().hex
    after = await repo.apply_compensation(
        db, compensation_id=compensation_id, user_id=int(user_id),
        source_kind=event.source_kind, source_event_id=event.source_event_id,
        source_line_id=event.source_line_id, collectible_kind=event.collectible_kind,
        collectible_id=event.collectible_id, observed_level=event.observed_level,
        observed_cap=event.observed_cap, amount=event.amount,
        policy_version=POLICY_VERSION, source_snapshot=dict(event.source_snapshot),
        source_snapshot_hash=snapshot_hash, balance_before=before,
    )
    return EchoShardReceipt(compensation_id=compensation_id, applied=True, amount=event.amount, balance_before=before, balance_after=after)
