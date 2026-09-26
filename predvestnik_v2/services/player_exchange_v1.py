"""Transactional application service for the player-created exchange."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import uuid4

from core.player_exchange_v1 import (
    AUCTION_HOURS, CREATION_FEE_ZARNIKI, FEATURE_FLAG_KEY, GENESIS_UNITS,
    MAX_PRICE_MICROMORA, MIN_AUCTION_RAISED_MORA, MIN_AUCTION_SOLD_UNITS, PRICE_SCALE, RULES_VERSION,
    AuctionBid, PlayerExchangePolicyError, allocation_units, clear_uniform_auction,
    buy_reserve, parse_token_amount, protected_limit_price, trade_fee, trade_notional, validate_coin_draft,
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


async def place_limit_order(db, *, user_id: int, coin_id: str, side: str,
                            amount: str, limit_price_mora: str, time_in_force: str,
                            action_id: str) -> dict:
    await require_enabled(db)
    side = str(side).lower()
    tif = str(time_in_force).lower()
    if side not in {"buy", "sell"} or tif != "gtc":
        raise PlayerExchangePolicyError("Некорректный тип заявки.")
    units = parse_token_amount(amount)
    try:
        price = Decimal(str(limit_price_mora))
        price_micro = int((price * PRICE_SCALE).to_integral_exact())
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise PlayerExchangePolicyError("Некорректная цена заявки.") from exc
    if (not price.is_finite() or price_micro <= 0 or price_micro > MAX_PRICE_MICROMORA
            or Decimal(price_micro) / PRICE_SCALE != price):
        raise PlayerExchangePolicyError("Цена должна быть положительной, точность — до 6 знаков.")
    if trade_notional(units, price_micro) < Decimal("10"):
        raise PlayerExchangePolicyError("Минимальная сумма заявки — 10 Моры.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_order_replay(db, user_id=int(user_id), action_id=action_id)
        if replay:
            identity = (str(replay["coin_id"]), replay["side"], replay["time_in_force"],
                        int(replay["limit_price_micromora"]), int(replay["original_units"]))
            if identity != (coin_id, side, tif, price_micro, units):
                raise IdempotencyConflict("Action id is bound to another order.")
            replay["replayed"] = True
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Торги этой монетой недоступны.")
        reserved = Decimal("0")
        reserve_op = None
        if side == "buy":
            reserved = buy_reserve(units, price_micro)
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": -reserved}, reason_code="player_coin_order_reserve",
                idempotency_key=f"player-coin:order:{action_id}", source_type="player_exchange",
                reference_type="spot_order", reference_id=action_id,
                metadata={"coin_id": coin_id, "side": side, "units": units,
                          "price_micromora": price_micro, "time_in_force": tif},
                note=f"Заявка на покупку {coin['ticker']}",
            )
            reserve_op = str(mutation.operation_id)
        else:
            try:
                await repo.reserve_sell_units(db, coin_id=coin_id, user_id=int(user_id), units=units)
            except ValueError as exc:
                raise PlayerExchangePolicyError("Недостаточно монет для продажи.") from exc
        result = await repo.insert_order(
            db, coin_id=coin_id, user_id=int(user_id), action_id=action_id, side=side,
            time_in_force=tif, price=price_micro, units=units, reserved_mora=reserved,
            reserve_operation_id=reserve_op,
        )
        result["replayed"] = False
    return result


async def _release_order(db, order: dict, *, reason: str) -> None:
    release_op = None
    if order["side"] == "buy" and Decimal(order["reserved_mora"]) > 0:
        mutation = await economy_ledger.apply_balance_change(
            db, int(order["user_id"]), {"mora": Decimal(order["reserved_mora"])},
            reason_code="player_coin_order_release",
            idempotency_key=f"player-coin:order-release:{order['id']}", source_type="player_exchange",
            reference_type="spot_order", reference_id=str(order["id"]),
            metadata={"reason": reason, "coin_id": str(order["coin_id"])},
            note="Возврат резерва биржевой заявки",
        )
        release_op = str(mutation.operation_id)
    elif order["side"] == "sell" and int(order["remaining_units"]) > 0:
        await repo.release_sell_units(
            db, coin_id=str(order["coin_id"]), user_id=int(order["user_id"]),
            units=int(order["remaining_units"]),
        )
    await repo.close_order(db, order_id=str(order["id"]), release_operation_id=release_op)
    await repo.append_event(
        db, coin_id=str(order["coin_id"]), actor_id=int(order["user_id"]),
        event_type="order_closed", action_id=f"order-closed:{order['id']}",
        payload={"order_id": str(order["id"]), "reason": reason,
                 "released_mora": str(order["reserved_mora"]),
                 "released_units": int(order["remaining_units"]) if order["side"] == "sell" else 0},
    )


async def cancel_order(db, *, user_id: int, order_id: str) -> dict:
    async with db.connection.transaction():
        await repo.lock_spot(db)
        order = await repo.get_order(db, order_id, for_update=True)
        if not order or int(order["user_id"]) != int(user_id):
            raise PlayerExchangePolicyError("Заявка не найдена.")
        if order["status"] != "open":
            return order
        await _release_order(db, order, reason="user_cancelled")
        return await repo.get_order(db, order_id)


async def match_market(db, *, coin_id: str, max_trades: int = 100) -> list[dict]:
    completed = []
    for _ in range(max(1, min(int(max_trades), 500))):
        async with db.connection.transaction():
            await repo.lock_spot(db)
            coin = await repo.get_coin(db, coin_id, for_update=True)
            if not coin or coin["status"] != "active":
                return completed
            if (await repo.market_halt(db, coin_id))["active"]:
                return completed
            pair = await repo.best_cross(db, coin_id)
            if not pair:
                break
            buy = await repo.get_order(db, pair[0], for_update=True)
            sell = await repo.get_order(db, pair[1], for_update=True)
            if int(buy["user_id"]) == int(sell["user_id"]):
                newer = buy if (buy["created_at"], buy["id"]) > (sell["created_at"], sell["id"]) else sell
                await _release_order(db, newer, reason="self_trade_prevented")
                continue
            buy_is_maker = (buy["created_at"], buy["id"]) < (sell["created_at"], sell["id"])
            maker = buy if buy_is_maker else sell
            units = min(int(buy["remaining_units"]), int(sell["remaining_units"]))
            price = int(maker["limit_price_micromora"])
            gross = trade_notional(units, price)
            if gross <= 0:
                newer = buy if (buy["created_at"], buy["id"]) > (sell["created_at"], sell["id"]) else sell
                await _release_order(db, newer, reason="unexecutable_dust_cross")
                continue
            buyer_fee = trade_fee(gross, maker=buy_is_maker)
            seller_fee = trade_fee(gross, maker=not buy_is_maker)
            buyer_charge = gross + buyer_fee
            trade_id = uuid4().hex
            buy_after = await repo.update_order_fill(
                db, order_id=str(buy["id"]), units=units, mora_charge=buyer_charge,
            )
            sell_after = await repo.update_order_fill(
                db, order_id=str(sell["id"]), units=units, mora_charge=Decimal("0"),
            )
            await repo.transfer_trade_tokens(
                db, coin_id=coin_id, seller_id=int(sell["user_id"]),
                buyer_id=int(buy["user_id"]), units=units,
            )
            await economy_ledger.apply_balance_change(
                db, int(sell["user_id"]), {"mora": gross - seller_fee},
                reason_code="player_coin_trade_proceeds",
                idempotency_key=f"player-coin:trade:{trade_id}", source_type="player_exchange",
                reference_type="spot_trade", reference_id=trade_id,
                metadata={"coin_id": coin_id, "units": units, "price_micromora": price,
                          "gross_mora": str(gross), "seller_fee_mora": str(seller_fee)},
                note=f"Продажа {coin['ticker']}",
            )
            await repo.record_trade(
                db, trade_id=trade_id, coin_id=coin_id, buy_order=buy, sell_order=sell,
                units=units, price=price, gross=gross, buyer_fee=buyer_fee, seller_fee=seller_fee,
            )
            current_5m = await repo.vwap_window(db, coin_id=coin_id, minutes=5)
            baseline_5m = await repo.vwap_window(db, coin_id=coin_id, minutes=5, offset_minutes=5)
            current_1h = await repo.vwap_window(db, coin_id=coin_id, minutes=60)
            baseline_1h = await repo.vwap_window(db, coin_id=coin_id, minutes=60, offset_minutes=60)
            meaningful = Decimal("100")
            if (current_1h["volume_mora"] >= meaningful and baseline_1h["volume_mora"] >= meaningful
                    and abs(current_1h["vwap_price_micromora"] - baseline_1h["vwap_price_micromora"]) * 100
                    >= baseline_1h["vwap_price_micromora"] * 40):
                await repo.set_market_halt(
                    db, coin_id=coin_id, minutes=30, reason="price_move_40pct_1h",
                    reference_price=baseline_1h["vwap_price_micromora"],
                )
            elif (current_5m["volume_mora"] >= meaningful and baseline_5m["volume_mora"] >= meaningful
                    and abs(current_5m["vwap_price_micromora"] - baseline_5m["vwap_price_micromora"]) * 100
                    >= baseline_5m["vwap_price_micromora"] * 20):
                await repo.set_market_halt(
                    db, coin_id=coin_id, minutes=5, reason="price_move_20pct_5m",
                    reference_price=baseline_5m["vwap_price_micromora"],
                )
            if buy_after["status"] == "filled" and Decimal(buy_after["reserved_mora"]) > 0:
                mutation = await economy_ledger.apply_balance_change(
                    db, int(buy_after["user_id"]), {"mora": Decimal(buy_after["reserved_mora"])},
                    reason_code="player_coin_order_release",
                    idempotency_key=f"player-coin:order-release:{buy_after['id']}",
                    source_type="player_exchange", reference_type="spot_order",
                    reference_id=str(buy_after["id"]),
                    metadata={"reason": "filled_price_improvement", "coin_id": coin_id},
                    note="Возврат остатка резерва биржевой заявки",
                )
                await repo.release_filled_buy_remainder(
                    db, order_id=str(buy_after["id"]),
                    release_operation_id=str(mutation.operation_id),
                )
                await repo.append_event(
                    db, coin_id=coin_id, actor_id=int(buy_after["user_id"]),
                    event_type="order_closed", action_id=f"order-closed:{buy_after['id']}",
                    payload={"order_id": str(buy_after["id"]), "reason": "filled",
                             "released_mora": str(buy_after["reserved_mora"]), "released_units": 0},
                )
            if sell_after["status"] == "filled":
                # No remaining token reserve; status is already final.
                pass
            completed.append({"trade_id": trade_id, "units": units, "price_micromora": price})
    return completed


async def public_market(db, *, coin_id: str, levels: int = 20, trades: int = 50) -> dict:
    await require_enabled(db)
    coin = await repo.get_coin(db, coin_id)
    if not coin or coin["status"] not in {"active", "halted"}:
        raise PlayerExchangePolicyError("Рынок не найден.")
    return {
        "coin": {key: coin[key] for key in (
            "id", "name", "ticker", "status", "genesis_units", "circulating_units"
        )},
        "order_book": await repo.public_order_book(db, coin_id, levels),
        "recent_trades": await repo.public_recent_trades(db, coin_id, trades),
        "stats_24h": await repo.public_market_stats(db, coin_id),
        "notice": "Игровой актив без вывода в деньги.",
    }


async def manually_halt_market(
    db, *, actor_id: int, coin_id: str, minutes: int, public_reason: str, action_id: str,
) -> dict:
    """Stop trading without granting any power over prices, balances or history."""
    await require_enabled(db)
    reason = " ".join(str(public_reason).strip().split())
    if not 5 <= int(minutes) <= 1_440:
        raise PlayerExchangePolicyError("Остановка рынка — от 5 минут до 24 часов.")
    if not 10 <= len(reason) <= 160:
        raise PlayerExchangePolicyError("Публичная причина должна содержать от 10 до 160 символов.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or coin["status"] not in {"active", "halted"}:
            raise PlayerExchangePolicyError("Рынок не найден.")
        replay = await repo.get_event_by_action(db, actor_id=int(actor_id), action_id=str(action_id))
        if replay:
            payload = replay["payload_json"]
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            if (str(replay["coin_id"]), int(payload.get("minutes", -1)), payload.get("public_reason")) != (
                str(coin_id), int(minutes), reason,
            ):
                raise IdempotencyConflict("Action id is bound to another market halt.")
            result = await repo.market_halt(db, coin_id)
            result["replayed"] = True
            return result
        result = await repo.set_manual_market_halt(
            db, coin_id=coin_id, actor_id=int(actor_id), minutes=int(minutes),
            public_reason=reason, action_id=str(action_id),
        )
        result["replayed"] = False
        return result


async def place_protected_market_order(
    db, *, user_id: int, coin_id: str, side: str, amount: str,
    slippage_percent: int, action_id: str,
) -> dict:
    """Place, match and close an IOC order inside one outer transaction."""
    await require_enabled(db)
    side = str(side).lower()
    if side not in {"buy", "sell"} or int(slippage_percent) not in {1, 3, 5}:
        raise PlayerExchangePolicyError("Выберите направление и предел цены 1%, 3% или 5%.")
    units = parse_token_amount(amount)
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_order_replay(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if (str(replay["coin_id"]), replay["side"], int(replay["original_units"])) != (
                coin_id, side, units,
            ) or replay["time_in_force"] != "ioc" or int(replay["slippage_percent"] or 0) != int(slippage_percent):
                raise IdempotencyConflict("Action id is bound to another order.")
            replay["replayed"] = True
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Торги этой монетой недоступны.")
        if (await repo.market_halt(db, coin_id))["active"]:
            raise PlayerExchangePolicyError("Рынок временно остановлен. Отменять заявки по-прежнему можно.")
        quote = await repo.best_quote(db, coin_id=coin_id, side=side)
        if not quote:
            raise PlayerExchangePolicyError("В стакане пока нет встречных заявок.")
        slip = int(slippage_percent)
        price_micro = protected_limit_price(
            side=side, quote_micromora=quote["price_micromora"], slippage_percent=slip,
        )
        if trade_notional(units, price_micro) < Decimal("10"):
            raise PlayerExchangePolicyError("Минимальная сумма заявки — 10 Моры.")
        reserved = Decimal("0")
        reserve_op = None
        if side == "buy":
            reserved = buy_reserve(units, price_micro)
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": -reserved}, reason_code="player_coin_order_reserve",
                idempotency_key=f"player-coin:order:{action_id}", source_type="player_exchange",
                reference_type="spot_order", reference_id=action_id,
                metadata={"coin_id": coin_id, "side": side, "units": units,
                          "protected_price_micromora": price_micro, "slippage_percent": slip},
                note=f"Рыночная заявка {coin['ticker']}",
            )
            reserve_op = str(mutation.operation_id)
        else:
            try:
                await repo.reserve_sell_units(db, coin_id=coin_id, user_id=int(user_id), units=units)
            except ValueError as exc:
                raise PlayerExchangePolicyError("Недостаточно монет для продажи.") from exc
        order = await repo.insert_order(
            db, coin_id=coin_id, user_id=int(user_id), action_id=action_id, side=side,
            time_in_force="ioc", price=price_micro, units=units, reserved_mora=reserved,
            reserve_operation_id=reserve_op, slippage_percent=slip,
        )
        await match_market(db, coin_id=coin_id, max_trades=100)
        current = await repo.get_order(db, str(order["id"]), for_update=True)
        if current and current["status"] == "open":
            await _release_order(db, current, reason="ioc_unfilled_remainder")
        result = await repo.get_order(db, str(order["id"]))
        result["replayed"] = False
        return result
