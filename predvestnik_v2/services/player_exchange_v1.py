"""Transactional application service for the player-created exchange."""
from __future__ import annotations

from core.player_exchange_v1 import (
    AUCTION_HOURS, CREATION_FEE_ZARNIKI, FEATURE_FLAG_KEY, GENESIS_UNITS,
    RULES_VERSION, PlayerExchangePolicyError, allocation_units, validate_coin_draft,
)
from core.economy_contract import IdempotencyConflict
from infrastructure.repositories import economy_ledger, player_exchange_v1 as repo, system_flags


class PlayerExchangeUnavailable(RuntimeError):
    pass


async def require_enabled(db) -> None:
    if not await system_flags.is_enabled(db, FEATURE_FLAG_KEY):
        raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")


async def create_coin(
    db, *, owner_id: int, name: str, ticker: str, initial_mora: int, action_id: str,
) -> dict:
    await require_enabled(db)
    draft = validate_coin_draft(name=name, ticker=ticker, initial_mora=initial_mora)
    if not str(action_id).strip() or len(str(action_id)) > 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")

    async with db.connection.transaction():
        await repo.lock_owner(db, int(owner_id))
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_creation_replay(db, owner_id=int(owner_id), action_id=str(action_id))
        if replay:
            payload = replay.pop("payload_json", {})
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            request_identity = (draft.name, draft.ticker, draft.initial_mora)
            stored_identity = (
                payload.get("name"), payload.get("ticker"), int(payload.get("initial_mora", -1)),
            )
            if stored_identity != request_identity:
                raise IdempotencyConflict("Action id is bound to another coin creation request.")
            replay["replayed"] = True
            return replay
        conflict = await repo.creation_conflict(
            db, owner_id=int(owner_id), name=draft.name, ticker=draft.ticker,
        )
        if conflict == "owner":
            raise PlayerExchangePolicyError("У игрока уже есть активная монета.")
        if conflict == "ticker":
            raise PlayerExchangePolicyError("Этот тикер уже занят.")
        if conflict == "name":
            raise PlayerExchangePolicyError("Это название уже занято.")
        mutation = await economy_ledger.apply_balance_change(
            db, int(owner_id),
            {"zarniki": -CREATION_FEE_ZARNIKI, "mora": -draft.initial_mora},
            reason_code="player_coin_creation",
            idempotency_key=f"player-coin:create:{action_id}",
            source_type="player_exchange",
            reference_type="coin_creation",
            reference_id=str(action_id),
            metadata={"name": draft.name, "ticker": draft.ticker,
                      "initial_mora": draft.initial_mora, "rules_version": RULES_VERSION},
            note=f"Создание монеты {draft.ticker}",
        )
        result = await repo.create_coin_rows(
            db, owner_id=int(owner_id), name=draft.name, ticker=draft.ticker,
            initial_mora=draft.initial_mora, rules_version=RULES_VERSION,
            genesis_units=GENESIS_UNITS, allocations=allocation_units(),
            economy_operation_id=str(mutation.operation_id), action_id=str(action_id),
            auction_hours=AUCTION_HOURS,
        )
        result["replayed"] = False
        return result
