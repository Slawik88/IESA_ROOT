"""Transactional application service for the player-created exchange."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from core.player_exchange_v1 import (
    AUCTION_HOURS, CREATION_FEE_ZARNIKI, FEATURE_FLAG_KEY, GENESIS_UNITS,
    MAX_PRICE_MICROMORA, MIN_AUCTION_RAISED_MORA, MIN_AUCTION_SOLD_UNITS, PRICE_SCALE, RULES_VERSION,
    AuctionBid, PlayerExchangePolicyError, allocation_units, clear_uniform_auction,
    validate_coin_draft,
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


async def place_auction_bid(
    db, *, bidder_id: int, coin_id: str, max_price_mora: str, escrow_mora: int,
    action_id: str,
) -> dict:
    await require_enabled(db)
    try:
        price = Decimal(str(max_price_mora))
        price_micro = int((price * PRICE_SCALE).to_integral_exact())
        escrow = int(escrow_mora)
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise PlayerExchangePolicyError("Некорректная цена или сумма заявки.") from exc
    if (not price.is_finite() or price <= 0 or price_micro <= 0
            or price_micro > MAX_PRICE_MICROMORA
            or Decimal(price_micro) / PRICE_SCALE != price):
        raise PlayerExchangePolicyError("Цена должна быть положительной, точность — до 6 знаков.")
    if escrow <= 0 or escrow != escrow_mora:
        raise PlayerExchangePolicyError("Сумма заявки должна быть целым положительным числом Моры.")
    if not str(action_id).strip() or len(str(action_id)) > 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")

    async with db.connection.transaction():
        await repo.lock_owner(db, int(bidder_id))
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_bid_replay(db, bidder_id=int(bidder_id), action_id=str(action_id))
        if replay:
            identity = (str(replay["coin_id"]), int(replay["max_price_micromora"]), int(replay["escrow_mora"]))
            if identity != (str(coin_id), price_micro, escrow):
                raise IdempotencyConflict("Action id is bound to another auction bid.")
            replay["replayed"] = True
            return replay
        coin = await repo.get_coin(db, str(coin_id), for_update=True)
        if not coin or coin["status"] != "auction":
            raise PlayerExchangePolicyError("Стартовый аукцион недоступен.")
        async with db.execute("SELECT NOW() < ?", (coin["auction_ends_at"],)) as cursor:
            still_open = await cursor.fetchone()
        if not still_open or not still_open[0]:
            raise PlayerExchangePolicyError("Приём заявок уже завершён.")
        if int(coin["owner_id"]) == int(bidder_id):
            raise PlayerExchangePolicyError("Владелец не участвует в аукционе своей монеты.")
        if await repo.bidder_has_shared_owner_signal(
            db, bidder_id=int(bidder_id), owner_id=int(coin["owner_id"]),
        ):
            raise PlayerExchangePolicyError("Связанный с владельцем аккаунт не участвует в аукционе.")
        if await repo.get_coin_bid_for_bidder(
            db, coin_id=str(coin_id), bidder_id=int(bidder_id),
        ):
            raise PlayerExchangePolicyError("На этом аукционе уже есть ваша заявка.")
        mutation = await economy_ledger.apply_balance_change(
            db, int(bidder_id), {"mora": -escrow}, reason_code="player_coin_auction_bid",
            idempotency_key=f"player-coin:bid:{action_id}", source_type="player_exchange",
            reference_type="auction_bid", reference_id=str(action_id),
            metadata={"coin_id": str(coin_id), "max_price_micromora": price_micro,
                      "escrow_mora": escrow, "rules_version": RULES_VERSION},
            note=f"Заявка на {coin['ticker']}",
        )
        result = await repo.insert_bid(
            db, coin_id=str(coin_id), bidder_id=int(bidder_id), action_id=str(action_id),
            max_price_micromora=price_micro, escrow_mora=escrow,
            economy_operation_id=str(mutation.operation_id),
        )
        result["replayed"] = False
        return result


async def settle_auction(db, *, coin_id: str) -> dict:
    """Close one expired auction exactly once; safe for scheduler retries."""
    async with db.connection.transaction():
        coin = await repo.get_coin(db, str(coin_id), for_update=True)
        if not coin:
            raise PlayerExchangePolicyError("Монета не найдена.")
        previous = await repo.get_settlement(db, str(coin_id))
        if previous:
            previous["replayed"] = True
            return previous
        if coin["status"] != "auction":
            raise PlayerExchangePolicyError("Аукцион уже закрыт.")
        async with db.execute("SELECT NOW() >= ?", (coin["auction_ends_at"],)) as cursor:
            expired = await cursor.fetchone()
        if not expired or not expired[0]:
            raise PlayerExchangePolicyError("Аукцион ещё не завершён.")
        rows = await repo.list_open_bids(db, str(coin_id))
        clearing = clear_uniform_auction([
            AuctionBid(str(row["id"]), int(row["max_price_micromora"]), int(row["escrow_mora"]))
            for row in rows
        ], allocation_units()["auction"])
        success = (
            clearing.sold_units >= MIN_AUCTION_SOLD_UNITS
            and clearing.raised_mora >= Decimal(MIN_AUCTION_RAISED_MORA)
        )
        for row in rows:
            allocated = clearing.allocations.get(str(row["id"]), 0) if success else 0
            cost = clearing.costs_mora.get(str(row["id"]), Decimal("0")) if success else Decimal("0")
            refund = Decimal(int(row["escrow_mora"])) - cost
            refund_op = None
            if refund > 0:
                mutation = await economy_ledger.apply_balance_change(
                    db, int(row["bidder_id"]), {"mora": refund},
                    reason_code="player_coin_auction_refund",
                    idempotency_key=f"player-coin:auction-refund:{row['id']}",
                    source_type="player_exchange", reference_type="auction_bid",
                    reference_id=str(row["id"]),
                    metadata={"coin_id": str(coin_id), "escrow_mora": int(row["escrow_mora"]),
                              "cost_mora": str(cost), "success": success},
                    note=f"Возврат аукциона {coin['ticker']}",
                )
                refund_op = str(mutation.operation_id)
            if allocated:
                await repo.credit_bid_tokens(
                    db, coin_id=str(coin_id), bidder_id=int(row["bidder_id"]), units=allocated,
                )
            await repo.finish_bid(
                db, bid_id=str(row["id"]), allocated_units=allocated,
                cost_mora=cost, refund_operation_id=refund_op,
            )
        if not success:
            owner_refund = await economy_ledger.apply_balance_change(
                db, int(coin["owner_id"]), {"mora": int(coin["initial_mora"])},
                reason_code="player_coin_launch_failed_refund",
                idempotency_key=f"player-coin:owner-refund:{coin_id}",
                source_type="player_exchange", reference_type="coin_creation",
                reference_id=str(coin_id), metadata={"rules_version": RULES_VERSION},
                note=f"Возврат ликвидности {coin['ticker']}",
            )
            await repo.release_failed_initial_liquidity(
                db, coin_id=str(coin_id), amount=int(coin["initial_mora"]),
                economy_operation_id=str(owner_refund.operation_id),
            )
        result = await repo.finish_auction(
            db, coin=coin, success=success,
            clearing_price=clearing.clearing_price_micromora if success else 0,
            sold_units=clearing.sold_units if success else 0,
            raised_mora=clearing.raised_mora if success else Decimal("0"),
            action_id=f"auction-settle:{coin_id}",
        )
        result["replayed"] = False
        return result


async def settle_due_auctions(db, *, limit: int = 20) -> list[dict]:
    results = []
    for coin_id in await repo.due_auction_ids(db, limit=limit):
        try:
            results.append(await settle_auction(db, coin_id=coin_id))
        except Exception as exc:
            results.append({"coin_id": coin_id, "error": f"{type(exc).__name__}: {exc}"})
    return results
