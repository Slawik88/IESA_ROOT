"""Transactional application service for the player-created exchange."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from core.player_exchange_v1 import (
    AUCTION_HOURS, CREATION_FEE_ZARNIKI, EMISSION_WAIT_HOURS, FEATURE_FLAG_KEY, GENESIS_UNITS,
    MAX_PRICE_MICROMORA, MIN_AUCTION_RAISED_MORA, MIN_AUCTION_SOLD_UNITS,
    LIQUIDITY_WITHDRAWAL_COOLDOWN_DAYS, LIQUIDITY_WITHDRAWAL_LOCK_DAYS,
    LIQUIDITY_WITHDRAWAL_MAX_BPS, LIQUIDITY_WITHDRAWAL_WAIT_HOURS,
    OWNER_VESTING_CLIFF_DAYS, OWNER_VESTING_LINEAR_DAYS, PRICE_SCALE, RULES_VERSION,
    AuctionBid, PlayerExchangePolicyError, allocation_units, clear_uniform_auction,
    buy_reserve, parse_token_amount, protected_limit_price, trade_fee, trade_notional,
    treasury_ladder_prices, validate_coin_draft, validate_emission,
)
from core.player_exchange_shorts_v1 import (
    SHORTS_FEATURE_FLAG_KEY, conservative_mark_price_micromora,
    executable_buyback_limit_price, executable_sell_limit_price,
    borrow_apr_bps, frozen_claim_buyback_mark_micromora, frozen_claim_units_for_budget, is_short_eligible, pool_utilisation_bps,
    equity_mora, liquidation_penalty_split, liquidation_state, margin_ratio_bps,
    minimum_partial_liquidation_units, required_initial_collateral_mora, short_limits_units,
    validate_short_open,
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


async def require_shorts_enabled(db) -> None:
    await require_enabled(db)
    if not await system_flags.is_enabled(db, SHORTS_FEATURE_FLAG_KEY):
        raise PlayerExchangeUnavailable("Шорты пока закрыты для игроков.")


async def short_eligibility(db, *, coin_id: str) -> dict:
    """One server-owned verdict; later writers re-read it under the Spot lock."""
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    metrics = await repo.short_eligibility_metrics(db, coin_id=str(coin_id))
    return {
        **metrics,
        "eligible": is_short_eligible(**metrics),
        "shorts_enabled": bool(await system_flags.is_enabled(db, SHORTS_FEATURE_FLAG_KEY)),
    }


def _decode_recovery_cursor(value: str | None, *, kind: str):
    if not value:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        expected_keys = {"k", "t", "i"} if kind in {"holdings", "coins"} else {"k", "r", "t", "i"}
        if not isinstance(payload, dict) or set(payload) != expected_keys or payload.get("k") != kind:
            raise ValueError
        row_id = payload.get("i")
        if not isinstance(row_id, str) or not row_id or len(row_id) > 128:
            raise ValueError
        raw_time = payload.get("t")
        if not isinstance(raw_time, str):
            raise ValueError
        timestamp = datetime.fromisoformat(raw_time)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError
        if kind in {"holdings", "coins"}:
            return timestamp.isoformat(), row_id
        rank = payload.get("r")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank not in {0, 1}:
            raise ValueError
        return rank, timestamp.isoformat(), row_id
    except Exception as exc:
        raise PlayerExchangePolicyError("Некорректный курсор списка.") from exc


def _encode_recovery_cursor(*, kind: str, row: dict) -> str:
    payload = {"k": kind, "t": row["created_at"].isoformat(),
               "i": str(row.get("id") or row["coin_id"])}
    if kind not in {"holdings", "coins"}:
        payload["r"] = 1 if row["status"] == "open" else 0
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def _recovery_page(rows: list[dict], *, limit: int, kind: str) -> dict:
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        _encode_recovery_cursor(kind=kind, row=items[-1]) if has_more and items else None
    )
    if kind == "bids":
        items = [{key: value for key, value in row.items() if key != "id"} for row in items]
    return {"items": items, "next_cursor": next_cursor}


async def player_recovery_state(
    db, *, user_id: int, limit: int = 50, holdings_cursor: str | None = None,
    orders_cursor: str | None = None, bids_cursor: str | None = None,
    coins_cursor: str | None = None,
) -> dict:
    """Return only the actor's recoverable exchange state, even during a kill switch."""
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    page_limit = max(1, min(int(limit), 100))
    state = await repo.player_recovery_state(
        db, user_id=int(user_id), limit=page_limit,
        holdings_cursor=_decode_recovery_cursor(holdings_cursor, kind="holdings"),
        orders_cursor=_decode_recovery_cursor(orders_cursor, kind="orders"),
        bids_cursor=_decode_recovery_cursor(bids_cursor, kind="bids"),
        coins_cursor=_decode_recovery_cursor(coins_cursor, kind="coins"),
    )
    enabled = await system_flags.is_enabled(db, FEATURE_FLAG_KEY)
    if not enabled and not any(state.values()):
        raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
    return {
        "holdings": _recovery_page(state["holdings"], limit=page_limit, kind="holdings"),
        "orders": _recovery_page(state["orders"], limit=page_limit, kind="orders"),
        "auction_bids": _recovery_page(state["auction_bids"], limit=page_limit, kind="bids"),
        "owned_coins": _recovery_page(state["owned_coins"], limit=page_limit, kind="coins"),
        "trading_enabled": bool(enabled),
        "can_cancel_open_orders": True,
    }


async def _lending_replay(db, *, user_id: int, coin_id: str, action_id: str,
                          event_type: str, units: int) -> dict | None:
    event = await repo.get_short_event_by_action(db, action_id=str(action_id))
    if not event:
        return None
    payload = event["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if (event["event_type"] != event_type or int(event["actor_id"] or 0) != int(user_id)
            or str(event["coin_id"]) != str(coin_id) or int(payload.get("units", -1)) != int(units)):
        raise IdempotencyConflict("Action id is bound to another Shorts operation.")
    position = await repo.get_lending_position(db, coin_id=coin_id, lender_id=user_id)
    return {"position": position, "replayed": True}


async def deposit_lending_units(db, *, user_id: int, coin_id: str, amount: str, action_id: str) -> dict:
    """Move owned units into the disabled-by-default voluntary lending pool."""
    await require_shorts_enabled(db)
    units = parse_token_amount(amount)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY) or not await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Шорты пока закрыты для игроков.")
        replay = await _lending_replay(
            db, user_id=user_id, coin_id=coin_id, action_id=action_id, event_type="lending_deposited", units=units,
        )
        if replay:
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Пул этой монеты пока недоступен.")
        try:
            position = await repo.move_player_units_to_lending(
                db, coin_id=coin_id, lender_id=int(user_id), units=units,
            )
        except ValueError as exc:
            raise PlayerExchangePolicyError("Недостаточно свободных монет для пула.") from exc
        await repo.append_short_event(
            db, coin_id=coin_id, actor_id=int(user_id), event_type="lending_deposited", action_id=str(action_id),
            payload={"units": units},
        )
        return {"position": position, "replayed": False}


async def withdraw_lending_units(db, *, user_id: int, coin_id: str, amount: str, action_id: str) -> dict:
    """Withdraw only free lender units; loaned and frozen units cannot be withdrawn."""
    await require_shorts_enabled(db)
    units = parse_token_amount(amount)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY) or not await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Шорты пока закрыты для игроков.")
        replay = await _lending_replay(
            db, user_id=user_id, coin_id=coin_id, action_id=action_id, event_type="lending_withdrawn", units=units,
        )
        if replay:
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Пул этой монеты пока недоступен.")
        try:
            position = await repo.move_lending_units_to_player(
                db, coin_id=coin_id, lender_id=int(user_id), units=units,
            )
        except ValueError as exc:
            raise PlayerExchangePolicyError("Можно забрать только свободные, не выданные в заём монеты.") from exc
        await repo.append_short_event(
            db, coin_id=coin_id, actor_id=int(user_id), event_type="lending_withdrawn", action_id=str(action_id),
            payload={"units": units},
        )
        return {"position": position, "replayed": False}


async def _short_open_replay(db, *, user_id: int, coin_id: str, action_id: str,
                             units: int) -> dict | None:
    event = await repo.get_short_event_by_action(db, action_id=str(action_id))
    if not event:
        return None
    payload = event["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if (event["event_type"] != "short_opened" or int(event["actor_id"] or 0) != int(user_id)
            or str(event["coin_id"]) != str(coin_id) or int(payload.get("units", -1)) != int(units)):
        raise IdempotencyConflict("Action id is bound to another Shorts operation.")
    position = await repo.get_short_position_by_action(
        db, borrower_id=int(user_id), action_id=str(action_id), for_update=True,
    )
    if not position:
        raise RuntimeError("Short replay receipt has no position.")
    return {"position": position, "order_id": payload.get("order_id"), "replayed": True}


async def _release_filled_buy_remainder(db, *, order: dict, coin_id: str) -> None:
    """Return only unused buy reserve after a terminal fill, in the same transaction."""
    remainder = Decimal(order["reserved_mora"])
    if remainder <= 0:
        return
    if order.get("actor_kind") == "treasury":
        await repo.release_treasury_order(db, order=order, reason="filled_price_improvement", filled=True)
        return
    mutation = await economy_ledger.apply_balance_change(
        db, int(order["user_id"]), {"mora": remainder},
        reason_code="player_coin_order_release",
        idempotency_key=f"player-coin:order-release:{order['id']}",
        source_type="player_exchange", reference_type="spot_order", reference_id=str(order["id"]),
        metadata={"reason": "filled_price_improvement", "coin_id": coin_id},
        note="Возврат остатка резерва биржевой заявки",
    )
    await repo.release_filled_buy_remainder(
        db, order_id=str(order["id"]), release_operation_id=str(mutation.operation_id),
    )
    await repo.append_event(
        db, coin_id=coin_id, actor_id=int(order["user_id"]),
        event_type="order_closed", action_id=f"order-closed:{order['id']}",
        payload={"order_id": str(order["id"]), "reason": "filled",
                 "released_mora": str(remainder), "released_units": 0},
    )


async def open_short(db, *, user_id: int, coin_id: str, amount: str, action_id: str) -> dict:
    """Open a fully-filled, position-bound Short or roll every write back.

    This writer deliberately has no HTTP or Mini App route yet.  Its only valid
    sale route is the locked, exact bid set below; it never delegates to the
    ordinary matcher, which commits one fill per transaction.
    """
    await require_shorts_enabled(db)
    units = parse_token_amount(amount)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if (not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY)
                or not await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY)):
            raise PlayerExchangeUnavailable("Шорты пока закрыты для игроков.")
        replay = await _short_open_replay(
            db, user_id=int(user_id), coin_id=str(coin_id), action_id=str(action_id), units=units,
        )
        if replay:
            return replay
        coin = await repo.get_coin(db, coin_id=str(coin_id), for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Шорт этой монеты сейчас недоступен.")
        reserve = await repo.get_short_reserve(db, coin_id=str(coin_id), for_update=True)
        if not reserve or reserve["shorts_paused"]:
            raise PlayerExchangePolicyError("Шорты этой монеты временно остановлены до расчёта прежних требований.")
        if (int(coin["owner_id"]) == int(user_id)
                or await repo.bidder_has_shared_owner_signal(
                    db, bidder_id=int(user_id), owner_id=int(coin["owner_id"]),
                )):
            raise PlayerExchangePolicyError("Владелец монеты и связанные с ним аккаунты не могут открывать шорт.")
        if (await repo.market_halt(db, str(coin_id)))["active"]:
            raise PlayerExchangePolicyError("Рынок временно остановлен: шорты не открываются.")
        metrics = await repo.short_eligibility_metrics(db, coin_id=str(coin_id))
        if not is_short_eligible(**metrics):
            raise PlayerExchangePolicyError("Монета ещё не набрала безопасную историю для шортов.")
        pool = await repo.short_pool_state(db, coin_id=str(coin_id), borrower_id=int(user_id))
        try:
            validate_short_open(
                requested_units=units, circulating_units=int(coin["circulating_units"]),
                lending_pool_units=pool["lending_pool_units"],
                already_borrowed_units=pool["already_borrowed_units"], actor_is_owner_or_linked=False,
            )
            per_player, aggregate_remaining = short_limits_units(
                circulating_units=int(coin["circulating_units"]),
                lending_pool_units=pool["lending_pool_units"],
                already_borrowed_units=pool["already_borrowed_units"],
            )
        except ValueError as exc:
            raise PlayerExchangePolicyError("Размер шорта не соответствует лимитам рынка.") from exc
        if (pool["borrower_debt_units"] + units > per_player or units > aggregate_remaining
                or units > pool["available_units"]):
            raise PlayerExchangePolicyError("Недостаточно свободного пула или лимита для этого шорта.")
        bids = await repo.eligible_short_sell_bids(
            db, coin_id=str(coin_id), borrower_id=int(user_id), owner_id=int(coin["owner_id"]), limit_price=1,
        )
        sale_limit = executable_sell_limit_price(
            units=units,
            bids=[(int(row["limit_price_micromora"]), int(row["remaining_units"])) for row in bids],
        )
        if sale_limit is None or trade_notional(units, sale_limit) < Decimal("10"):
            raise PlayerExchangePolicyError("В стакане нет полного защищённого спроса для этого шорта.")
        asks = await repo.eligible_short_buyback_asks(
            db, coin_id=str(coin_id), borrower_id=int(user_id), owner_id=int(coin["owner_id"]),
        )
        buyback_limit = executable_buyback_limit_price(
            units=units,
            asks=[(int(row["limit_price_micromora"]), int(row["remaining_units"])) for row in asks],
        )
        vwap = await repo.vwap_window(db, coin_id=str(coin_id), minutes=5)
        mark = conservative_mark_price_micromora(
            vwap_5m_micromora=vwap["vwap_price_micromora"],
            vwap_5m_volume_mora=vwap["volume_mora"], executable_buyback_micromora=buyback_limit,
        )
        if mark is None:
            raise PlayerExchangePolicyError("Рынку не хватает свежей ликвидности для безопасной оценки шорта.")
        collateral = required_initial_collateral_mora(
            debt_units=units, conservative_price_micromora=mark,
        )
        opening_apr_bps = borrow_apr_bps(
            utilisation_bps=pool_utilisation_bps(
                lending_pool_units=pool["lending_pool_units"],
                borrowed_units=pool["already_borrowed_units"] + units,
            )
        )
        collateral_mutation = await economy_ledger.apply_balance_change(
            db, int(user_id), {"mora": -collateral}, reason_code="player_coin_short_collateral",
            idempotency_key=f"player-coin:short-collateral:{action_id}", source_type="player_exchange",
            reference_type="short_position", reference_id=str(action_id),
            metadata={"coin_id": str(coin_id), "units": units, "mark_price_micromora": mark,
                      "collateral_mora": str(collateral)},
            note=f"Залог по шорту {coin['ticker']}",
        )
        position_id = uuid4().hex
        await repo.create_short_position(
            db, position_id=position_id, coin_id=str(coin_id), borrower_id=int(user_id),
            action_id=str(action_id), units=units, collateral_mora=collateral,
            collateral_operation_id=str(collateral_mutation.operation_id), open_apr_bps=opening_apr_bps,
            interest_mark_price_micromora=int(mark),
        )
        await repo.change_short_cash_escrow(
            db, position_id=position_id, amount=collateral, source_type="collateral",
            source_id=str(collateral_mutation.operation_id),
        )
        await repo.allocate_lending_units(db, coin_id=str(coin_id), position_id=position_id, units=units)
        order = await repo.insert_order(
            db, coin_id=str(coin_id), user_id=int(user_id), action_id=f"short-sale:{action_id}",
            side="sell", time_in_force="ioc", price=int(sale_limit), units=units,
            reserved_mora=Decimal("0"), reserve_operation_id=None, actor_kind="short",
            short_position_id=position_id,
        )
        remaining = units
        gross_total = Decimal("0")
        proceeds_total = Decimal("0")
        shorts_reserve_enabled = await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY)
        for buy in bids:
            if remaining <= 0:
                break
            fill_units = min(remaining, int(buy["remaining_units"]))
            price = int(buy["limit_price_micromora"])
            gross = trade_notional(fill_units, price)
            buyer_fee = trade_fee(gross, maker=True)
            seller_fee = trade_fee(gross, maker=False)
            trade_id = uuid4().hex
            buy_after = await repo.update_order_fill(
                db, order_id=str(buy["id"]), units=fill_units, mora_charge=gross + buyer_fee,
            )
            await repo.update_order_fill(db, order_id=str(order["id"]), units=fill_units, mora_charge=Decimal("0"))
            await repo.transfer_trade_tokens(
                db, coin_id=str(coin_id), sell_order=order, buy_order=buy, units=fill_units,
            )
            net_proceeds = gross - seller_fee
            await repo.credit_short_sale_proceeds(
                db, position_id=position_id, amount=net_proceeds, source_id=f"short-sale:{trade_id}",
            )
            await repo.record_trade(
                db, trade_id=trade_id, coin_id=str(coin_id), buy_order=buy, sell_order=order,
                units=fill_units, price=price, gross=gross, buyer_fee=buyer_fee, seller_fee=seller_fee,
                shorts_reserve_enabled=shorts_reserve_enabled,
            )
            if buy_after["status"] == "filled":
                await _release_filled_buy_remainder(db, order=buy_after, coin_id=str(coin_id))
            remaining -= fill_units
            gross_total += gross
            proceeds_total += net_proceeds
        if remaining != 0:
            raise RuntimeError("Protected Short sale depth changed after its locked preflight.")
        final_order = await repo.get_order(db, str(order["id"]), for_update=True)
        if not final_order or final_order["status"] != "filled":
            raise RuntimeError("Protected Short sale did not reach terminal fill.")
        position = await repo.get_short_position_by_action(
            db, borrower_id=int(user_id), action_id=str(action_id), for_update=True,
        )
        await repo.append_short_event(
            db, coin_id=str(coin_id), actor_id=int(user_id), event_type="short_opened", action_id=str(action_id),
            payload={"position_id": position_id, "order_id": str(order["id"]), "units": units,
                     "sale_limit_price_micromora": int(sale_limit), "mark_price_micromora": int(mark),
                     "collateral_mora": str(collateral), "gross_sale_mora": str(gross_total),
                     "locked_sale_proceeds_mora": str(proceeds_total)},
        )
        return {"position": position, "order_id": str(order["id"]), "replayed": False}


async def _short_close_replay(db, *, user_id: int, position_id: str, action_id: str,
                              requested_units: int) -> dict | None:
    event = await repo.get_short_event_by_action(db, action_id=str(action_id))
    if not event:
        return None
    payload = event["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if (event["event_type"] not in {"short_reduced", "short_closed"}
            or int(event["actor_id"] or 0) != int(user_id)
            or str(payload.get("position_id")) != str(position_id)
            or int(payload.get("units", -1)) != int(requested_units)):
        raise IdempotencyConflict("Action id is bound to another Shorts operation.")
    position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
    if not position:
        raise RuntimeError("Short close replay receipt has no position.")
    return {"position": position, "order_id": payload.get("order_id"), "replayed": True}


async def _buy_back_short(db, *, user_id: int, position_id: str, units: int,
                          action_id: str, liquidation: bool = False) -> dict:
    """Atomically reduce or close a Short against already-locked genuine asks.

    This stays intentionally service-only.  Unlike an ordinary buy, its cash is
    never reserved from a player wallet and the tokens never reach a player
    account: escrow funds the fill and the exact units go straight back to the
    lenders recorded on this position.
    """
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    requested = int(units)
    if requested <= 0 or not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректные параметры закрытия шорта.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
        if not position or int(position["borrower_id"]) != int(user_id):
            raise PlayerExchangePolicyError("Шорт не найден.")
        if not liquidation:
            replay = await _short_close_replay(
                db, user_id=int(user_id), position_id=str(position_id), action_id=str(action_id),
                requested_units=requested,
            )
            if replay:
                return replay
        if position["status"] != "open" or requested > int(position["outstanding_debt_units"]):
            raise PlayerExchangePolicyError("Этот объём уже нельзя выкупить из шорта.")
        coin = await repo.get_coin(db, str(position["coin_id"]), for_update=True)
        if not coin or coin["status"] != "active":
            raise PlayerExchangePolicyError("Рынок этой монеты сейчас недоступен для закрытия шорта.")
        asks = await repo.eligible_short_buyback_asks(
            db, coin_id=str(coin["id"]), borrower_id=int(user_id), owner_id=int(coin["owner_id"]),
        )
        buyback_limit = executable_buyback_limit_price(
            units=requested,
            asks=[(int(row["limit_price_micromora"]), int(row["remaining_units"])) for row in asks],
        )
        if buyback_limit is None:
            raise PlayerExchangePolicyError("В стакане нет полного защищённого предложения для выкупа шорта.")
        remaining = requested
        planned_charge = Decimal("0")
        for sell in asks:
            if remaining <= 0:
                break
            fill_units = min(remaining, int(sell["remaining_units"]))
            gross = trade_notional(fill_units, int(sell["limit_price_micromora"]))
            planned_charge += gross + trade_fee(gross, maker=False)
            remaining -= fill_units
        if remaining:
            raise RuntimeError("Protected Short buyback depth changed after its locked preflight.")
        # Closing stays available during the kill switch and a halt because it
        # only reduces existing risk. Interest itself freezes unless there is a
        # fresh, qualified conservative mark; it is never repriced from a lone
        # close-side ask.
        halt = await repo.market_halt(db, str(coin["id"]))
        vwap = await repo.vwap_window(db, coin_id=str(coin["id"]), minutes=5)
        current_mark = conservative_mark_price_micromora(
            vwap_5m_micromora=vwap["vwap_price_micromora"], vwap_5m_volume_mora=vwap["volume_mora"],
            executable_buyback_micromora=buyback_limit,
        )
        # An active halt is represented by a durable pause interval.  We still
        # charge the active minutes immediately *before* that interval at the
        # prior server mark, but never charge the halted minutes themselves.
        # A missing qualified mark outside a halt freezes the clock entirely.
        await repo.accrue_short_interest(
            db, position_id=str(position_id), mark_price_micromora=current_mark,
            charge_allowed=bool(halt["active"] or current_mark is not None),
        )
        position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
        if not position:
            raise RuntimeError("Short position disappeared during close.")
        closing = requested == int(position["outstanding_debt_units"])
        escrow = Decimal(position["cash_escrow_mora"])
        accrued_interest = Decimal(position["accrued_interest_mora"])
        if planned_charge > escrow:
            raise PlayerExchangePolicyError("Escrow шорта не покрывает защищённый выкуп.")
        if closing and planned_charge + accrued_interest > escrow:
            raise PlayerExchangePolicyError(
                "Полное закрытие пока не покрывает начисленные проценты; сначала уменьшите шорт."
            )
        # Interest receives only escrow that remains after the already locked
        # principal buyback. This makes a partial close an unconditional
        # risk-reducing route even for an underwater position.
        await repo.settle_short_interest(
            db, position_id=str(position_id), action_id=f"short-close-interest:{action_id}",
            max_amount=escrow - planned_charge,
        )
        order = await repo.insert_order(
            db, coin_id=str(coin["id"]), user_id=int(user_id), action_id=f"short-buyback:{action_id}",
            side="buy", time_in_force="ioc", price=int(buyback_limit), units=requested,
            reserved_mora=Decimal("0"), reserve_operation_id=None, actor_kind="short",
            short_position_id=str(position_id),
        )
        remaining = requested
        total_charge = Decimal("0")
        shorts_reserve_enabled = await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY)
        for sell in asks:
            if remaining <= 0:
                break
            fill_units = min(remaining, int(sell["remaining_units"]))
            price = int(sell["limit_price_micromora"])
            gross = trade_notional(fill_units, price)
            buyer_fee = trade_fee(gross, maker=False)
            seller_fee = trade_fee(gross, maker=True)
            buyer_charge = gross + buyer_fee
            trade_id = uuid4().hex
            buy_after = await repo.update_order_fill(
                db, order_id=str(order["id"]), units=fill_units, mora_charge=Decimal("0"),
            )
            sell_after = await repo.update_order_fill(
                db, order_id=str(sell["id"]), units=fill_units, mora_charge=Decimal("0"),
            )
            await repo.transfer_trade_tokens(
                db, coin_id=str(coin["id"]), sell_order=sell, buy_order=order, units=fill_units,
            )
            await repo.change_short_cash_escrow(
                db, position_id=str(position_id), amount=-buyer_charge, source_type="buyback_spend",
                source_id=f"short-buyback:{trade_id}",
            )
            await economy_ledger.apply_balance_change(
                db, int(sell["user_id"]), {"mora": gross - seller_fee},
                reason_code="player_coin_trade_proceeds",
                idempotency_key=f"player-coin:trade:{trade_id}", source_type="player_exchange",
                reference_type="spot_trade", reference_id=trade_id,
                metadata={"coin_id": str(coin["id"]), "units": fill_units,
                          "price_micromora": price, "gross_mora": str(gross),
                          "seller_fee_mora": str(seller_fee), "short_position_id": str(position_id)},
                note=f"Выкуп шорта {coin['ticker']}",
            )
            await repo.record_trade(
                db, trade_id=trade_id, coin_id=str(coin["id"]), buy_order=order, sell_order=sell,
                units=fill_units, price=price, gross=gross, buyer_fee=buyer_fee, seller_fee=seller_fee,
                shorts_reserve_enabled=shorts_reserve_enabled,
            )
            if sell_after["status"] == "filled":
                # A filled sell has no Mora reserve and its token reserve was
                # consumed by transfer_trade_tokens, so there is nothing else
                # to release.
                pass
            if buy_after["status"] not in {"open", "filled"}:
                raise RuntimeError("Protected Short buyback order entered an invalid state.")
            total_charge += buyer_charge
            remaining -= fill_units
        if remaining:
            raise RuntimeError("Protected Short buyback depth changed after its locked preflight.")
        final_order = await repo.get_order(db, str(order["id"]), for_update=True)
        if not final_order or final_order["status"] != "filled":
            raise RuntimeError("Protected Short buyback did not reach terminal fill.")
        repaid = await repo.repay_short_loans(
            db, position_id=str(position_id), units=requested, close_position=closing,
        )
        final_position = repaid["position"]
        liquidation_penalty = Decimal("0")
        if liquidation:
            executor_share, reserve_share = liquidation_penalty_split(
                posted_collateral_mora=Decimal(final_position["posted_collateral_mora"]),
                closed_units=requested, original_debt_units=int(position["outstanding_debt_units"]),
            )
            # Forced reduction never creates a new debt: the penalty is capped
            # by actual post-buyback escrow and goes only to the segregated
            # reserve while the public liquidator programme is still disabled.
            liquidation_penalty = min(executor_share + reserve_share, Decimal(final_position["cash_escrow_mora"]))
            if liquidation_penalty > 0:
                await repo.change_short_cash_escrow(
                    db, position_id=str(position_id), amount=-liquidation_penalty,
                    source_type="liquidation_penalty", source_id=f"short-liquidation-penalty:{action_id}",
                )
                await repo.credit_short_reserve(
                    db, coin_id=str(coin["id"]), amount=liquidation_penalty,
                    source_type="liquidation_penalty", source_id=f"short-liquidation-penalty:{action_id}",
                )
                final_position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
                if not final_position:
                    raise RuntimeError("Short position disappeared during liquidation penalty.")
        borrower_release = Decimal("0")
        if closing:
            borrower_release = Decimal(final_position["cash_escrow_mora"])
            if borrower_release > 0:
                await repo.change_short_cash_escrow(
                    db, position_id=str(position_id), amount=-borrower_release,
                    source_type="borrower_release", source_id=f"short-close-release:{action_id}",
                )
                await economy_ledger.apply_balance_change(
                    db, int(user_id), {"mora": borrower_release},
                    reason_code="player_coin_short_collateral_release",
                    idempotency_key=f"player-coin:short-release:{action_id}", source_type="player_exchange",
                    reference_type="short_position", reference_id=str(position_id),
                    metadata={"coin_id": str(coin["id"]), "position_id": str(position_id),
                              "release_mora": str(borrower_release)},
                    note=f"Возврат остатка залога шорта {coin['ticker']}",
                )
            final_position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
        event_type = "short_liquidated" if liquidation else ("short_closed" if closing else "short_reduced")
        await repo.append_short_event(
            db, coin_id=str(coin["id"]), actor_id=None if liquidation else int(user_id), event_type=event_type,
            action_id=str(action_id), payload={
                "position_id": str(position_id), "order_id": str(order["id"]), "units": requested,
                "buyback_limit_price_micromora": int(buyback_limit), "spent_mora": str(total_charge),
                "borrower_release_mora": str(borrower_release), "liquidation_penalty_mora": str(liquidation_penalty),
            },
        )
        return {"position": final_position, "order_id": str(order["id"]), "replayed": False}


async def reduce_short(db, *, user_id: int, position_id: str, amount: str, action_id: str) -> dict:
    """Buy back a strict part of an open Short; no collateral is released yet."""
    return await _buy_back_short(
        db, user_id=int(user_id), position_id=str(position_id), units=parse_token_amount(amount), action_id=str(action_id),
    )


async def close_short(db, *, user_id: int, position_id: str, action_id: str) -> dict:
    """Buy back every remaining unit and return only the verified escrow surplus."""
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    event = await repo.get_short_event_by_action(db, action_id=str(action_id))
    if event:
        payload = event["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        position = await repo.get_short_position(db, position_id=str(position_id))
        if (event["event_type"] != "short_closed" or int(event["actor_id"] or 0) != int(user_id)
                or str(payload.get("position_id")) != str(position_id) or not position):
            raise IdempotencyConflict("Action id is bound to another Shorts operation.")
        return {"position": position, "order_id": payload.get("order_id"), "replayed": True}
    position = await repo.get_short_position(db, position_id=str(position_id))
    if not position or int(position["borrower_id"]) != int(user_id):
        raise PlayerExchangePolicyError("Шорт не найден.")
    # A replay is resolved inside _buy_back_short after the shared transaction
    # guard.  A new close always binds to the debt observed immediately before
    # it enters that transaction.
    return await _buy_back_short(
        db, user_id=int(user_id), position_id=str(position_id),
        units=int(position["outstanding_debt_units"]), action_id=str(action_id),
    )


async def liquidate_short(db, *, position_id: str, action_id: str) -> dict:
    """Run one server-owned, reduce-only liquidation decision.

    It is intentionally not a player endpoint.  A halted market or an
    unqualified mark performs no forced operation.  When a qualified market
    exists but escrow cannot fund even the required protected reduction, lender
    principal becomes an immutable frozen claim only after every accrued
    interest claim has been settled; otherwise the position remains untouched.
    """
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор ликвидации.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        prior = await repo.get_short_event_by_action(db, action_id=str(action_id))
        if prior:
            if prior["event_type"] not in {"short_liquidated", "short_frozen"}:
                raise IdempotencyConflict("Action id is bound to another Shorts operation.")
            position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
            if not position:
                raise RuntimeError("Short liquidation replay has no position.")
            return {"position": position, "decision": prior["event_type"], "replayed": True}
        position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
        if not position:
            raise PlayerExchangePolicyError("Шорт не найден.")
        if position["status"] != "open":
            return {"position": position, "decision": "not_open", "replayed": False}
        coin = await repo.get_coin(db, str(position["coin_id"]), for_update=True)
        if not coin:
            raise RuntimeError("Short coin disappeared.")
        halt = await repo.market_halt(db, str(coin["id"]))
        asks = await repo.eligible_short_buyback_asks(
            db, coin_id=str(coin["id"]), borrower_id=int(position["borrower_id"]), owner_id=int(coin["owner_id"]),
        )
        full_buyback = executable_buyback_limit_price(
            units=int(position["outstanding_debt_units"]),
            asks=[(int(row["limit_price_micromora"]), int(row["remaining_units"])) for row in asks],
        )
        vwap = await repo.vwap_window(db, coin_id=str(coin["id"]), minutes=5)
        mark = conservative_mark_price_micromora(
            vwap_5m_micromora=vwap["vwap_price_micromora"], vwap_5m_volume_mora=vwap["volume_mora"],
            executable_buyback_micromora=full_buyback,
        )
        # A meaningful trade mark may prove full insolvency even after the
        # protected ask depth has vanished.  It never triggers a forced trade;
        # it only permits the documented claim-freeze default path below.
        no_depth_mark = (int(vwap["vwap_price_micromora"]) if vwap["vwap_price_micromora"]
                         and Decimal(vwap["volume_mora"]) >= Decimal("100") else None)
        mark = mark or no_depth_mark
        if liquidation_state(margin_bps=0, market_halted=bool(halt["active"]), mark_available=mark is not None) == "frozen":
            return {"position": position, "decision": "market_frozen", "replayed": False}
        if position["open_apr_bps"] is None or position["interest_mark_price_micromora"] is None:
            # A pre-interest migration row has no immutable terms.  It must be
            # reconciled explicitly, never liquidated under guessed economics.
            return {"position": position, "decision": "legacy_terms_missing", "replayed": False}
        await repo.accrue_short_interest(db, position_id=str(position_id), mark_price_micromora=mark)
        position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
        if not position:
            raise RuntimeError("Short position disappeared during liquidation accrual.")
        margin = margin_ratio_bps(
            posted_collateral_mora=Decimal(position["posted_collateral_mora"]),
            locked_sale_proceeds_mora=Decimal(position["locked_sale_proceeds_mora"]),
            cash_escrow_mora=Decimal(position["cash_escrow_mora"]),
            debt_units=int(position["outstanding_debt_units"]), mark_price_micromora=mark,
            accrued_interest_mora=Decimal(position["accrued_interest_mora"]),
        )
        decision = liquidation_state(margin_bps=margin, market_halted=False, mark_available=True)
        if decision == "healthy":
            return {"position": position, "decision": "healthy", "margin_bps": margin, "replayed": False}
        units = int(position["outstanding_debt_units"])
        debt_units = int(position["outstanding_debt_units"])
        cash = Decimal(position["cash_escrow_mora"])
        accrued = Decimal(position["accrued_interest_mora"])

        def planned_buyback_charge(candidate_units: int) -> Decimal:
            remaining_units, charge = int(candidate_units), Decimal("0")
            for ask in asks:
                if remaining_units <= 0:
                    break
                fill = min(remaining_units, int(ask["remaining_units"]))
                gross = trade_notional(fill, int(ask["limit_price_micromora"]))
                charge += gross + trade_fee(gross, maker=False)
                remaining_units -= fill
            if remaining_units:
                raise RuntimeError("Liquidation depth changed after lock.")
            return charge

        def projected_margin_bps(candidate_units: int) -> int:
            if candidate_units >= debt_units:
                return 10**9
            charge = planned_buyback_charge(candidate_units)
            cash_after_interest_and_buyback = cash - accrued - charge
            requested_executor, requested_reserve = liquidation_penalty_split(
                posted_collateral_mora=Decimal(position["posted_collateral_mora"]),
                closed_units=candidate_units, original_debt_units=debt_units,
            )
            penalty = min(requested_executor + requested_reserve, max(Decimal("0"), cash_after_interest_and_buyback))
            equity_after = cash_after_interest_and_buyback - penalty
            debt_after = trade_notional(debt_units - candidate_units, mark)
            return int((equity_after * Decimal(10_000) / debt_after).to_integral_value(rounding="ROUND_DOWN"))

        if decision == "partial":
            equity = equity_mora(
                posted_collateral_mora=Decimal(position["posted_collateral_mora"]),
                locked_sale_proceeds_mora=Decimal(position["locked_sale_proceeds_mora"]),
                cash_escrow_mora=Decimal(position["cash_escrow_mora"]),
                debt_units=units, mark_price_micromora=mark,
                accrued_interest_mora=Decimal(position["accrued_interest_mora"]),
            )
            units = minimum_partial_liquidation_units(
                debt_units=units, mark_price_micromora=mark, current_equity_mora=equity,
                posted_collateral_mora=Decimal(position["posted_collateral_mora"]),
            )
            # The pure lower bound intentionally knows nothing about book fees.
            # Reprice against the locked real asks and expand it until the live
            # post-trade escrow is actually back at 200%, or close in full.
            if units < debt_units and projected_margin_bps(units) < 20_000:
                low, high, chosen = units + 1, debt_units - 1, debt_units
                while low <= high:
                    candidate = (low + high) // 2
                    if projected_margin_bps(candidate) >= 20_000:
                        chosen = candidate
                        high = candidate - 1
                    else:
                        low = candidate + 1
                units = chosen
        protected_price = executable_buyback_limit_price(
            units=units, asks=[(int(row["limit_price_micromora"]), int(row["remaining_units"])) for row in asks],
        )
        if protected_price is None:
            if decision == "full":
                await repo.settle_short_interest(
                    db, position_id=str(position_id), action_id=f"short-no-depth-interest:{action_id}",
                )
                frozen = await repo.freeze_short_position(db, position_id=str(position_id), action_id=str(action_id))
                await repo.append_short_event(
                    db, coin_id=str(coin["id"]), actor_id=None, event_type="short_frozen", action_id=str(action_id),
                    payload={"position_id": str(position_id), "margin_bps": margin,
                             "mark_price_micromora": mark, "reason": "qualified_mark_no_depth"},
                )
                return {"position": frozen, "decision": "short_frozen", "margin_bps": margin, "replayed": False}
            return {"position": position, "decision": "market_frozen", "margin_bps": margin, "replayed": False}
        planned_charge = planned_buyback_charge(units)
        if planned_charge > Decimal(position["cash_escrow_mora"]):
            await repo.settle_short_interest(
                db, position_id=str(position_id), action_id=f"short-freeze-interest:{action_id}",
            )
            position = await repo.get_short_position(db, position_id=str(position_id), for_update=True)
            if not position:
                raise RuntimeError("Short position disappeared before frozen recovery.")
            frozen = await repo.freeze_short_position(db, position_id=str(position_id), action_id=str(action_id))
            await repo.append_short_event(
                db, coin_id=str(coin["id"]), actor_id=None, event_type="short_frozen", action_id=str(action_id),
                payload={"position_id": str(position_id), "margin_bps": margin,
                         "mark_price_micromora": mark, "planned_charge_mora": str(planned_charge)},
            )
            return {"position": frozen, "decision": "short_frozen", "margin_bps": margin, "replayed": False}
        result = await _buy_back_short(
            db, user_id=int(position["borrower_id"]), position_id=str(position_id), units=units,
            action_id=str(action_id), liquidation=True,
        )
        return {**result, "decision": "short_liquidated", "margin_bps": margin}


async def settle_frozen_short_claims(db, *, coin_id: str, max_claims: int = 25) -> dict:
    """Server-only hourly, FIFO recovery for lender claims after an unrecoverable Short.

    This deliberately does not require either public exchange flag: turning off a
    market must never stop already-frozen lenders from receiving reserve-funded
    recovery.  A halt or absent qualified mark simply performs no forced action.
    """
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    limit = max(1, min(int(max_claims), 100))
    async with db.connection.transaction():
        await repo.lock_spot(db)
        coin = await repo.get_coin(db, str(coin_id), for_update=True)
        if not coin:
            raise PlayerExchangePolicyError("Монета не найдена.")
        halt = await repo.market_halt(db, str(coin_id))
        if halt["active"]:
            return {"coin_id": str(coin_id), "status": "market_halted", "settled": []}
        cycle = await repo.begin_frozen_claim_buyback_cycle(db, coin_id=str(coin_id))
        frozen_interest = await repo.list_open_frozen_interest_claims(db, coin_id=str(coin_id))
        claims = await repo.list_open_frozen_claims(db, coin_id=str(coin_id))
        vwap = await repo.vwap_window(db, coin_id=str(coin_id), minutes=5)
        settled: list[dict] = []
        for claim in frozen_interest[:limit]:
            remaining_budget = Decimal(cycle["budget_mora"]) - Decimal(cycle["spent_mora"])
            payout = min(Decimal(claim["remaining_mora"]), remaining_budget)
            if payout <= 0:
                break
            source_id = f"short-frozen-interest:{coin_id}:{cycle['action_id']}:{claim['id']}:{claim['remaining_mora']}"
            await economy_ledger.apply_balance_change(
                db, int(claim["lender_id"]), {"mora": payout},
                reason_code="player_coin_short_frozen_interest_buyback",
                idempotency_key=f"player-coin:{source_id}", source_type="player_exchange",
                reference_type="short_frozen_interest_claim", reference_id=str(claim["id"]),
                metadata={"coin_id": str(coin_id), "claim_id": str(claim["id"]), "cycle": str(cycle["action_id"])},
                note=f"Возврат процентов по шорту {coin['ticker']}",
            )
            updated = await repo.settle_frozen_interest_claim_buyback(
                db, claim_id=str(claim["id"]), cycle=cycle, payout_mora=payout, source_id=source_id,
            )
            cycle["spent_mora"] = Decimal(cycle["spent_mora"]) + payout
            await repo.append_short_event(
                db, coin_id=str(coin_id), actor_id=None, event_type="frozen_interest_buyback", action_id=source_id,
                payload={"claim_id": str(claim["id"]), "payout_mora": str(payout), "cycle": str(cycle["action_id"])},
            )
            settled.append({"claim_id": str(claim["id"]), "kind": "interest", "payout_mora": payout,
                            "remaining_mora": Decimal(updated["remaining_mora"])})
        for claim in claims[:limit]:
            remaining_budget = Decimal(cycle["budget_mora"]) - Decimal(cycle["spent_mora"])
            if remaining_budget <= 0:
                break
            mark = frozen_claim_buyback_mark_micromora(
                vwap_5m_micromora=vwap["vwap_price_micromora"], vwap_5m_volume_mora=vwap["volume_mora"],
            )
            # Strict FIFO: a younger lender never receives a preferred recovery
            # price while the oldest open claim has no qualified historical mark.
            if mark is None:
                break
            units = frozen_claim_units_for_budget(
                remaining_units=int(claim["remaining_units"]), mark_price_micromora=mark,
                budget_mora=remaining_budget,
            )
            if units <= 0:
                break
            payout = trade_notional(units, mark)
            cycle_key = str(cycle["action_id"])
            # The pre-settlement remaining amount is an immutable slice key.
            # A partially paid claim may receive a second, independently
            # journalled tranche in the same hour if the mark later improves.
            source_id = f"short-frozen-buyback:{coin_id}:{cycle_key}:{claim['id']}:{claim['remaining_units']}"
            await economy_ledger.apply_balance_change(
                db, int(claim["lender_id"]), {"mora": payout},
                reason_code="player_coin_short_frozen_claim_buyback",
                idempotency_key=f"player-coin:{source_id}", source_type="player_exchange",
                reference_type="short_frozen_claim", reference_id=str(claim["id"]),
                metadata={"coin_id": str(coin_id), "claim_id": str(claim["id"]), "units": units,
                          "mark_price_micromora": mark, "cycle_hour": cycle_key},
                note=f"Выкуп замороженного требования {coin['ticker']}",
            )
            updated = await repo.settle_frozen_claim_buyback(
                db, claim_id=str(claim["id"]), cycle=cycle, units=units, payout_mora=payout,
                source_id=source_id,
            )
            cycle["spent_mora"] = Decimal(cycle["spent_mora"]) + payout
            await repo.append_short_event(
                db, coin_id=str(coin_id), actor_id=None, event_type="frozen_claim_buyback",
                action_id=source_id,
                payload={"claim_id": str(claim["id"]), "lender_id": int(claim["lender_id"]), "units": units,
                         "payout_mora": str(payout), "mark_price_micromora": mark, "cycle_hour": cycle_key},
            )
            settled.append({"claim_id": str(claim["id"]), "units": units, "payout_mora": payout,
                            "remaining_units": int(updated["remaining_units"])})
        return {"coin_id": str(coin_id), "status": "ok", "cycle_hour": cycle["cycle_hour"],
                "budget_mora": Decimal(cycle["budget_mora"]), "spent_mora": Decimal(cycle["spent_mora"]),
                "settled": settled}


async def run_short_risk_maintenance(db, *, limit: int = 50) -> list[dict]:
    """Bounded recovery worker; it remains active even if new Shorts are disabled."""
    if not await repo.schema_ready(db):
        return []
    results: list[dict] = []
    for position_id in await repo.next_open_short_position_ids(db, limit=limit):
        action_id = f"short-liquidation:{position_id}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        try:
            results.append(await liquidate_short(db, position_id=position_id, action_id=action_id))
        except Exception as exc:
            results.append({"position_id": position_id, "error": str(exc)})
    for coin_id in await repo.frozen_claim_coin_ids(db, limit=limit):
        try:
            results.append(await settle_frozen_short_claims(db, coin_id=coin_id))
        except Exception as exc:
            results.append({"coin_id": coin_id, "error": str(exc)})
    return results


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
        if success:
            prices = treasury_ladder_prices(clearing.clearing_price_micromora)
            buy_budget = (Decimal(int(coin["initial_mora"])) * Decimal("0.18")).quantize(Decimal("0.000001"))
            buy_levels = []
            sell_prices = [price for side, price in prices if side == "sell"]
            sell_total = allocation_units()["market_reserve"]
            base_sell = sell_total // len(sell_prices)
            sell_levels = []
            for index, price in enumerate(sell_prices):
                sell_levels.append((price, base_sell + (sell_total % len(sell_prices) if index == 0 else 0)))
            for side, price in prices:
                if side != "buy":
                    continue
                units = int((buy_budget * PRICE_SCALE * 10 * 9 * 1000 / (Decimal(price) * 100)).to_integral_value())
                while units > 0 and buy_reserve(units, price) > buy_budget:
                    units -= 1
                if units <= 0:
                    raise RuntimeError("Launch ladder buy level is too small.")
                buy_levels.append((price, units, buy_reserve(units, price)))
            await repo.create_treasury_ladder(
                db, coin=coin, clearing_price=clearing.clearing_price_micromora,
                buy_levels=buy_levels, sell_levels=sell_levels,
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
        if side == "sell" and int(coin["owner_id"]) == int(user_id) and await repo.pending_emission(db, coin_id):
            raise PlayerExchangePolicyError("Владелец не может продавать монету, пока эмиссия ожидает исполнения.")
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
    if order.get("actor_kind") == "short":
        raise RuntimeError("A position-bound Short order can only be resolved by the Shorts executor.")
    if order.get("actor_kind") == "treasury":
        await repo.release_treasury_order(db, order=order, reason=reason)
    elif order["side"] == "buy" and Decimal(order["reserved_mora"]) > 0:
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
        if order.get("actor_kind") != "player":
            raise PlayerExchangePolicyError("Заявки казны управляются только отдельной публичной операцией.")
        if order["status"] != "open":
            return order
        await _release_order(db, order, reason="user_cancelled")
        return await repo.get_order(db, order_id)


async def match_market(db, *, coin_id: str, max_trades: int = 100) -> list[dict]:
    completed = []
    for _ in range(max(1, min(int(max_trades), 500))):
        async with db.connection.transaction():
            await repo.lock_spot(db)
            if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
                return completed
            shorts_reserve_enabled = await repo.lock_enabled_flag(db, SHORTS_FEATURE_FLAG_KEY)
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
            if buy.get("actor_kind") == "short" or sell.get("actor_kind") == "short":
                raise RuntimeError("Position-bound Short orders require the atomic Shorts executor.")
            if ((buy.get("actor_kind") == "treasury") != (sell.get("actor_kind") == "treasury")
                    and int(buy["user_id"]) == int(sell["user_id"])):
                player_order = sell if buy.get("actor_kind") == "treasury" else buy
                await _release_order(db, player_order, reason="owner_treasury_cross_prevented")
                continue
            if (buy.get("actor_kind") == "player" and sell.get("actor_kind") == "player"
                    and int(buy["user_id"]) == int(sell["user_id"])):
                newer = buy if (buy["created_at"], buy["id"]) > (sell["created_at"], sell["id"]) else sell
                await _release_order(db, newer, reason="self_trade_prevented")
                continue
            if (buy.get("actor_kind") == "treasury" and sell.get("actor_kind") == "treasury"
                    and int(buy["user_id"]) == int(sell["user_id"])):
                # Old data may predate the placement guard.  Never try to write a
                # treasury-to-itself trade: the immutable trade ledger forbids it.
                newer = buy if (buy["created_at"], buy["id"]) > (sell["created_at"], sell["id"]) else sell
                await _release_order(db, newer, reason="treasury_self_trade_prevented")
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
            await repo.transfer_trade_tokens(db, coin_id=coin_id, sell_order=sell, buy_order=buy, units=units)
            if sell.get("actor_kind") == "treasury":
                await repo.credit_treasury_mora(
                    db, coin_id=coin_id, amount=gross - seller_fee, reason="treasury_spot_sale",
                )
            else:
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
                shorts_reserve_enabled=shorts_reserve_enabled,
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
            if (buy_after["status"] == "filled" and Decimal(buy_after["reserved_mora"]) > 0
                    and buy_after.get("actor_kind") == "treasury"):
                await repo.release_treasury_order(
                    db, order=buy_after, reason="filled_price_improvement", filled=True,
                )
            elif buy_after["status"] == "filled" and Decimal(buy_after["reserved_mora"]) > 0:
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
    vesting = _project_owner_vesting(await repo.owner_vesting_state(db, coin_id))
    return {
        "coin": {key: coin[key] for key in (
            "id", "name", "ticker", "status", "genesis_units", "total_supply_units", "circulating_units"
        )},
        "order_book": await repo.public_order_book(db, coin_id, levels),
        "recent_trades": await repo.public_recent_trades(db, coin_id, trades),
        "stats_24h": await repo.public_market_stats(db, coin_id),
        "emissions": await repo.public_emissions(db, coin_id),
        "owner_vesting": vesting,
        "treasury": await repo.public_treasury_state(db, coin_id),
        "treasury_orders": await repo.public_treasury_orders(db, coin_id),
        "liquidity_withdrawals": await repo.public_liquidity_withdrawals(db, coin_id),
        "journal": _public_journal(await repo.public_owner_journal(db, coin_id)),
        "notice": "Игровой актив без вывода в деньги.",
    }


def _project_owner_vesting(state: dict | None) -> dict | None:
    if not state or state.get("launched_at") is None:
        return None
    allocation = allocation_units()["owner_locked"]
    age_seconds = max(0, int(Decimal(str(state.get("age_seconds") or 0))))
    cliff_seconds = OWNER_VESTING_CLIFF_DAYS * 86_400
    linear_seconds = OWNER_VESTING_LINEAR_DAYS * 86_400
    vested = 0 if age_seconds < cliff_seconds else min(
        allocation, allocation * (age_seconds - cliff_seconds) // linear_seconds,
    )
    locked = int(state["locked_units"])
    claimed = allocation - locked
    return {
        "allocation_units": allocation,
        "locked_units": locked,
        "vested_units": vested,
        "claimed_units": claimed,
        "claimable_units": max(0, vested - claimed),
        "cliff_days": OWNER_VESTING_CLIFF_DAYS,
        "linear_days": OWNER_VESTING_LINEAR_DAYS,
        "launched_at": state["launched_at"],
        "server_now": state["server_now"],
    }


_PUBLIC_JOURNAL_KEYS = {
    "coin_created": {"name", "ticker", "initial_mora", "genesis_units", "allocations", "rules_version"},
    "auction_settled": {"success", "clearing_price_micromora", "sold_units", "raised_mora"},
    "treasury_ladder_created": {"clearing_price_micromora", "buy_levels", "sell_levels", "reserved_mora", "reserved_units"},
    "market_halted": {"minutes", "reason", "reference_price_micromora"},
    "market_halted_manual": {"minutes", "public_reason"},
    "emission_requested": {"units", "circulation_snapshot_units", "projected_total_supply_units", "reason", "executes_at"},
    "emission_cancelled": {"units"},
    "emission_executed": {"units", "destination"},
    "owner_vesting_claimed": {"units", "vested_units", "claimed_units"},
    "treasury_order_placed": {"side", "units", "limit_price_micromora", "reserved_mora"},
    "treasury_order_cancelled": {"side", "remaining_units"},
    "treasury_burned": {"units", "total_supply_units"},
    "liquidity_added": {"amount_mora"},
    "liquidity_withdrawal_requested": {"amount_mora", "treasury_snapshot_mora", "max_amount_mora", "executes_at"},
    "liquidity_withdrawal_cancelled": {"amount_mora"},
    "liquidity_withdrawal_executed": {"amount_mora"},
}


def _public_journal(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        payload = row.get("payload_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        allowed = _PUBLIC_JOURNAL_KEYS.get(str(row["event_type"]), set())
        result.append({
            "id": str(row["id"]), "event_type": str(row["event_type"]),
            "created_at": row["created_at"],
            "details": {key: payload[key] for key in allowed if key in payload},
        })
    return result


async def claim_owner_vesting(db, *, owner_id: int, coin_id: str, units: int, action_id: str) -> dict:
    await require_enabled(db)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    requested_units = int(units)
    if requested_units <= 0:
        raise PlayerExchangePolicyError("Количество должно быть положительным.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_event_by_action(db, actor_id=int(owner_id), action_id=str(action_id))
        if replay:
            if replay["event_type"] != "owner_vesting_claimed" or str(replay["coin_id"]) != str(coin_id):
                raise IdempotencyConflict("Action id is bound to another owner operation.")
            payload = replay["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if int(payload.get("units", 0)) != requested_units:
                raise IdempotencyConflict("Action id is bound to another vesting amount.")
            return {**payload, "replayed": True}
        state = await repo.owner_vesting_state(db, coin_id, for_update=True)
        if (not state or int(state["owner_id"]) != int(owner_id)
                or state["status"] not in {"active", "halted"}):
            raise PlayerExchangePolicyError("Получить долю может только владелец активной монеты.")
        projection = _project_owner_vesting(state)
        claimable_units = int(projection["claimable_units"])
        if requested_units > claimable_units:
            raise PlayerExchangePolicyError("Подтверждённая сумма больше доступной доли. Обновите экран.")
        await repo.transfer_vested_owner_units(
            db, coin_id=str(coin_id), owner_id=int(owner_id), units=requested_units,
        )
        payload = {
            "units": requested_units, "vested_units": int(projection["vested_units"]),
            "claimed_units": int(projection["claimed_units"]) + requested_units,
        }
        await repo.append_event(
            db, coin_id=str(coin_id), actor_id=int(owner_id), event_type="owner_vesting_claimed",
            action_id=str(action_id), payload=payload,
        )
        return {**payload, "replayed": False}


async def place_treasury_order(
    db, *, owner_id: int, coin_id: str, side: str, amount: str,
    limit_price_mora: str, action_id: str,
) -> dict:
    await require_enabled(db)
    side = str(side).lower()
    if side not in {"buy", "sell"}:
        raise PlayerExchangePolicyError("Направление должно быть buy или sell.")
    units = parse_token_amount(amount)
    try:
        price_value = Decimal(str(limit_price_mora))
        price = int((price_value * PRICE_SCALE).to_integral_exact())
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise PlayerExchangePolicyError("Некорректная цена заявки.") from exc
    if (not price_value.is_finite() or price <= 0 or price > MAX_PRICE_MICROMORA
            or Decimal(price) / PRICE_SCALE != price_value):
        raise PlayerExchangePolicyError("Цена должна быть положительной, точность — до 6 знаков.")
    if trade_notional(units, price) < Decimal("10"):
        raise PlayerExchangePolicyError("Минимальная сумма заявки — 10 Моры.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_order_replay(db, user_id=int(owner_id), action_id=str(action_id))
        if replay:
            identity = (str(replay["coin_id"]), replay["side"], int(replay["original_units"]),
                        int(replay["limit_price_micromora"]), replay.get("actor_kind"))
            if identity != (str(coin_id), side, units, price, "treasury"):
                raise IdempotencyConflict("Action id is bound to another treasury order.")
            replay["replayed"] = True
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if (not coin or int(coin["owner_id"]) != int(owner_id)
                or coin["status"] not in {"active", "halted"}):
            raise PlayerExchangePolicyError("Управлять казной может только владелец активной монеты.")
        if side == "sell" and await repo.pending_emission(db, coin_id):
            raise PlayerExchangePolicyError("Продажа из казны недоступна, пока эмиссия ожидает исполнения.")
        if await repo.treasury_has_crossing_opposite_order(db, coin_id=coin_id, side=side, price=price):
            raise PlayerExchangePolicyError("Заявка казны пересечётся с другой заявкой этой же казны.")
        reserved_mora = Decimal("0")
        token_bucket = None
        if side == "buy":
            reserved_mora = buy_reserve(units, price)
            try:
                await repo.reserve_treasury_mora(
                    db, coin_id=coin_id, amount=reserved_mora, reason="owner_treasury_buy_reserve",
                )
            except ValueError as exc:
                raise PlayerExchangePolicyError("В казне недостаточно Моры.") from exc
        else:
            token_bucket = "treasury"
            try:
                await repo.reserve_treasury_tokens(db, coin_id=coin_id, units=units, bucket=token_bucket)
            except ValueError as exc:
                raise PlayerExchangePolicyError("В казне недостаточно монет.") from exc
        order = await repo.insert_order(
            db, coin_id=coin_id, user_id=int(owner_id), action_id=str(action_id), side=side,
            time_in_force="gtc", price=price, units=units, reserved_mora=reserved_mora,
            reserve_operation_id=None, actor_kind="treasury", treasury_token_bucket=token_bucket,
        )
        await repo.append_event(
            db, coin_id=coin_id, actor_id=int(owner_id), event_type="treasury_order_placed",
            action_id=f"treasury-public:{action_id}", payload={
                "order_id": order["id"], "side": side, "units": units,
                "limit_price_micromora": price, "reserved_mora": str(reserved_mora),
            },
        )
        order["replayed"] = False
        return order


async def cancel_treasury_order(
    db, *, owner_id: int, order_id: str, action_id: str,
) -> dict:
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        replay = await repo.get_event_by_action(db, actor_id=int(owner_id), action_id=str(action_id))
        if replay:
            payload = replay["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if replay["event_type"] != "treasury_order_cancelled" or payload.get("order_id") != str(order_id):
                raise IdempotencyConflict("Action id is bound to another treasury cancellation.")
            order = await repo.get_order(db, order_id)
            return {**order, "replayed": True}
        order = await repo.get_order(db, order_id, for_update=True)
        if (not order or int(order["user_id"]) != int(owner_id)
                or order.get("actor_kind") != "treasury"):
            raise PlayerExchangePolicyError("Заявка казны не найдена.")
        coin = await repo.get_coin(db, str(order["coin_id"]), for_update=True)
        if not coin or int(coin["owner_id"]) != int(owner_id):
            raise PlayerExchangePolicyError("Заявка казны не найдена.")
        if order["status"] != "open":
            raise PlayerExchangePolicyError("Заявка казны уже закрыта.")
        if order["side"] == "buy" and await repo.pending_emission(db, str(order["coin_id"])):
            raise PlayerExchangePolicyError("Поддерживающую покупку нельзя отменить, пока эмиссия ожидает исполнения.")
        await _release_order(db, order, reason="owner_treasury_cancelled")
        await repo.append_event(
            db, coin_id=str(order["coin_id"]), actor_id=int(owner_id),
            event_type="treasury_order_cancelled", action_id=str(action_id),
            payload={"order_id": str(order_id), "side": order["side"],
                     "remaining_units": int(order["remaining_units"])},
        )
        result = await repo.get_order(db, order_id)
        result["replayed"] = False
        return result


async def burn_treasury(db, *, owner_id: int, coin_id: str, amount: str, action_id: str) -> dict:
    await require_enabled(db)
    units = parse_token_amount(amount)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_event_by_action(db, actor_id=int(owner_id), action_id=str(action_id))
        if replay:
            payload = replay["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if (replay["event_type"] != "treasury_burned" or str(replay["coin_id"]) != str(coin_id)
                    or int(payload.get("units", 0)) != units):
                raise IdempotencyConflict("Action id is bound to another treasury burn.")
            return {**payload, "replayed": True}
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if (not coin or int(coin["owner_id"]) != int(owner_id)
                or coin["status"] not in {"active", "halted"}):
            raise PlayerExchangePolicyError("Управлять казной может только владелец активной монеты.")
        try:
            await repo.burn_treasury_tokens(db, coin_id=coin_id, units=units)
        except ValueError as exc:
            raise PlayerExchangePolicyError("В казне недостаточно свободных монет для сжигания.") from exc
        payload = {"units": units, "total_supply_units": int(coin["total_supply_units"]) - units}
        await repo.append_event(
            db, coin_id=coin_id, actor_id=int(owner_id), event_type="treasury_burned",
            action_id=str(action_id), payload=payload,
        )
        return {**payload, "replayed": False}


def _parse_mora_amount(value: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PlayerExchangePolicyError("Некорректная сумма Моры.") from exc
    normalized = amount.quantize(Decimal("0.000001"))
    if not amount.is_finite() or amount < Decimal("1") or normalized != amount:
        raise PlayerExchangePolicyError("Сумма должна быть не меньше 1 Моры, точность — до 6 знаков.")
    return normalized


async def add_treasury_liquidity(
    db, *, owner_id: int, coin_id: str, amount_mora: str, action_id: str,
) -> dict:
    await require_enabled(db)
    amount = _parse_mora_amount(amount_mora)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_event_by_action(db, actor_id=int(owner_id), action_id=str(action_id))
        if replay:
            payload = replay["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if (replay["event_type"] != "liquidity_added" or str(replay["coin_id"]) != str(coin_id)
                    or Decimal(str(payload.get("amount_mora"))) != amount):
                raise IdempotencyConflict("Action id is bound to another liquidity operation.")
            return {**payload, "replayed": True}
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if (not coin or int(coin["owner_id"]) != int(owner_id)
                or coin["status"] not in {"active", "halted"}):
            raise PlayerExchangePolicyError("Добавить ликвидность может только владелец активной монеты.")
        mutation = await economy_ledger.apply_balance_change(
            db, int(owner_id), {"mora": -amount}, reason_code="player_coin_liquidity_add",
            idempotency_key=f"player-coin:liquidity-add:{action_id}", source_type="player_exchange",
            reference_type="coin_liquidity", reference_id=str(coin_id),
            metadata={"coin_id": str(coin_id), "amount_mora": str(amount)},
            note=f"Ликвидность казны {coin['ticker']}",
        )
        await repo.credit_treasury_mora(
            db, coin_id=coin_id, amount=amount, reason="owner_liquidity_add",
            economy_operation_id=str(mutation.operation_id),
        )
        payload = {"amount_mora": str(amount)}
        await repo.append_event(
            db, coin_id=coin_id, actor_id=int(owner_id), event_type="liquidity_added",
            action_id=str(action_id), payload=payload,
        )
        return {**payload, "replayed": False}


async def request_liquidity_withdrawal(
    db, *, owner_id: int, coin_id: str, amount_mora: str, action_id: str,
) -> dict:
    await require_enabled(db)
    amount = _parse_mora_amount(amount_mora)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_liquidity_withdrawal_by_action(
            db, owner_id=int(owner_id), action_id=str(action_id),
        )
        if replay:
            if (str(replay["coin_id"]), Decimal(str(replay["amount_mora"])), replay["action_id"]) != (
                str(coin_id), amount, str(action_id),
            ):
                raise IdempotencyConflict("Action id is bound to another liquidity withdrawal.")
            return {**replay, "replayed": True}
        state = await repo.owner_vesting_state(db, coin_id, for_update=True)
        if (not state or int(state["owner_id"]) != int(owner_id)
                or state["status"] not in {"active", "halted"}):
            raise PlayerExchangePolicyError("Выводить ликвидность может только владелец активной монеты.")
        if int(Decimal(str(state["age_seconds"]))) < LIQUIDITY_WITHDRAWAL_LOCK_DAYS * 86_400:
            raise PlayerExchangePolicyError("Стартовую ликвидность нельзя выводить первые 30 дней.")
        if await repo.pending_liquidity_withdrawal(db, coin_id):
            raise PlayerExchangePolicyError("У монеты уже есть ожидающий вывод ликвидности.")
        if await repo.liquidity_withdrawal_cooldown_active(
            db, coin_id, days=LIQUIDITY_WITHDRAWAL_COOLDOWN_DAYS,
        ):
            raise PlayerExchangePolicyError("Следующий вывод доступен через 7 дней после предыдущего.")
        treasury = await repo.public_treasury_state(db, coin_id)
        snapshot = Decimal(str(treasury.get("treasury_mora") or 0))
        maximum = (snapshot * Decimal(LIQUIDITY_WITHDRAWAL_MAX_BPS) / Decimal(10_000)).quantize(Decimal("0.000001"))
        if amount > maximum:
            raise PlayerExchangePolicyError("За 7 дней можно запросить не больше 10% текущей Моры казны.")
        result = await repo.create_liquidity_withdrawal(
            db, coin_id=coin_id, owner_id=int(owner_id), amount_mora=amount,
            treasury_snapshot_mora=snapshot, max_amount_mora=maximum, action_id=str(action_id),
            wait_hours=LIQUIDITY_WITHDRAWAL_WAIT_HOURS,
        )
        await repo.append_event(
            db, coin_id=coin_id, actor_id=int(owner_id), event_type="liquidity_withdrawal_requested",
            action_id=str(action_id), payload={
                "amount_mora": str(amount), "treasury_snapshot_mora": str(snapshot),
                "max_amount_mora": str(maximum), "executes_at": result["executes_at"].isoformat(),
            },
        )
        return {**result, "replayed": False}


async def cancel_liquidity_withdrawal(
    db, *, owner_id: int, withdrawal_id: str, action_id: str,
) -> dict:
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        replay = await repo.get_liquidity_withdrawal_by_action(
            db, owner_id=int(owner_id), action_id=str(action_id),
        )
        if replay:
            if str(replay["id"]) != str(withdrawal_id) or replay.get("cancel_action_id") != str(action_id):
                raise IdempotencyConflict("Action id is bound to another withdrawal cancellation.")
            return {**replay, "replayed": True}
        withdrawal = await repo.get_liquidity_withdrawal(db, withdrawal_id, for_update=True)
        if not withdrawal or int(withdrawal["owner_id"]) != int(owner_id):
            raise PlayerExchangePolicyError("Запрос вывода не найден.")
        try:
            result = await repo.cancel_liquidity_withdrawal(
                db, withdrawal_id=str(withdrawal_id), owner_id=int(owner_id), action_id=str(action_id),
            )
        except ValueError as exc:
            raise PlayerExchangePolicyError("Запрос вывода уже нельзя отменить.") from exc
        await repo.append_event(
            db, coin_id=str(result["coin_id"]), actor_id=int(owner_id),
            event_type="liquidity_withdrawal_cancelled", action_id=str(action_id),
            payload={"amount_mora": str(result["amount_mora"])},
        )
        return {**result, "replayed": False}


async def execute_due_liquidity_withdrawals(db, *, limit: int = 20) -> list[dict]:
    if not await system_flags.is_enabled(db, FEATURE_FLAG_KEY):
        return []
    results = []
    for withdrawal_id in await repo.due_liquidity_withdrawal_ids(db, limit=limit):
        try:
            async with db.connection.transaction():
                await repo.lock_spot(db)
                if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
                    return results
                withdrawal = await repo.get_liquidity_withdrawal(db, withdrawal_id, for_update=True)
                if not withdrawal or withdrawal["status"] != "pending":
                    continue
                amount = Decimal(str(withdrawal["amount_mora"]))
                mutation = await economy_ledger.apply_balance_change(
                    db, int(withdrawal["owner_id"]), {"mora": amount},
                    reason_code="player_coin_liquidity_withdrawal",
                    idempotency_key=f"player-coin:liquidity-withdraw:{withdrawal_id}",
                    source_type="player_exchange", reference_type="coin_liquidity_withdrawal",
                    reference_id=str(withdrawal_id), metadata={
                        "coin_id": str(withdrawal["coin_id"]), "amount_mora": str(amount),
                    }, note="Вывод ликвидности казны",
                )
                await repo.withdraw_treasury_mora(
                    db, coin_id=str(withdrawal["coin_id"]), amount=amount,
                    reason="owner_liquidity_withdrawal", economy_operation_id=str(mutation.operation_id),
                )
                result = await repo.mark_liquidity_withdrawal_executed(
                    db, withdrawal_id=str(withdrawal_id), economy_operation_id=str(mutation.operation_id),
                )
                await repo.append_event(
                    db, coin_id=str(result["coin_id"]), actor_id=int(result["owner_id"]),
                    event_type="liquidity_withdrawal_executed",
                    action_id=f"liquidity-withdraw-execute:{withdrawal_id}",
                    payload={"amount_mora": str(amount)},
                )
                results.append(result)
        except Exception as exc:
            results.append({"withdrawal_id": withdrawal_id, "error": f"{type(exc).__name__}: {exc}"})
    return results


async def request_emission(db, *, owner_id: int, coin_id: str, amount: str,
                           reason: str, action_id: str) -> dict:
    await require_enabled(db)
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
            raise PlayerExchangeUnavailable("Биржа монет пока закрыта для игроков.")
        replay = await repo.get_emission_by_action(db, owner_id=int(owner_id), action_id=str(action_id))
        if replay:
            units, clean_reason = validate_emission(
                amount=amount, circulating_units=max(int(replay["requested_units"]) * 10, 1), reason=reason,
            )
            if (str(replay["coin_id"]), int(replay["requested_units"]), replay["reason"]) != (
                str(coin_id), units, clean_reason,
            ):
                raise IdempotencyConflict("Action id is bound to another emission request.")
            replay["replayed"] = True
            return replay
        coin = await repo.get_coin(db, coin_id, for_update=True)
        if not coin or int(coin["owner_id"]) != int(owner_id) or coin["status"] not in {"active", "halted"}:
            raise PlayerExchangePolicyError("Управлять эмиссией может только владелец активной монеты.")
        units, clean_reason = validate_emission(
            amount=amount, circulating_units=int(coin["circulating_units"]), reason=reason,
        )
        if await repo.pending_emission(db, coin_id):
            raise PlayerExchangePolicyError("У монеты уже есть ожидающая эмиссия.")
        if await repo.owner_has_open_sell(db, coin_id=coin_id, owner_id=int(owner_id)):
            raise PlayerExchangePolicyError("Перед эмиссией владелец должен отменить все свои заявки на продажу этой монеты.")
        if await repo.emission_cooldown_active(db, coin_id):
            raise PlayerExchangePolicyError("Между эмиссиями должно пройти 7 дней.")
        result = await repo.create_emission(
            db, coin_id=coin_id, owner_id=int(owner_id), units=units, reason=clean_reason,
            circulation_snapshot_units=int(coin["circulating_units"]),
            projected_total_supply_units=int(coin["total_supply_units"]) + units,
            action_id=str(action_id), wait_hours=EMISSION_WAIT_HOURS,
        )
        result["replayed"] = False
        return result


async def cancel_emission(db, *, owner_id: int, emission_id: str, action_id: str) -> dict:
    if not await repo.schema_ready(db):
        raise PlayerExchangeUnavailable("Биржа временно недоступна: хранилище не готово.")
    if not 8 <= len(str(action_id)) <= 128:
        raise PlayerExchangePolicyError("Некорректный идентификатор запроса.")
    async with db.connection.transaction():
        await repo.lock_spot(db)
        replay = await repo.get_emission_by_action(db, owner_id=int(owner_id), action_id=str(action_id))
        if replay:
            if str(replay["id"]) != str(emission_id) or replay.get("cancel_action_id") != str(action_id):
                raise IdempotencyConflict("Action id is bound to another emission operation.")
            replay["replayed"] = True
            return replay
        emission = await repo.get_emission(db, emission_id, for_update=True)
        if not emission or int(emission["owner_id"]) != int(owner_id):
            raise PlayerExchangePolicyError("Запрос эмиссии не найден.")
        try:
            result = await repo.cancel_emission(
                db, emission_id=str(emission_id), owner_id=int(owner_id), action_id=str(action_id),
            )
        except ValueError as exc:
            raise PlayerExchangePolicyError("Эмиссию нельзя отменить в последний час или после исполнения.") from exc
        result["replayed"] = False
        return result


async def execute_due_emissions(db, *, limit: int = 20) -> list[dict]:
    if not await system_flags.is_enabled(db, FEATURE_FLAG_KEY):
        return []
    results = []
    for emission_id in await repo.due_emission_ids(db, limit=limit):
        try:
            async with db.connection.transaction():
                await repo.lock_spot(db)
                if not await repo.lock_enabled_flag(db, FEATURE_FLAG_KEY):
                    return results
                results.append(await repo.execute_emission(db, emission_id=emission_id))
        except Exception as exc:
            results.append({"emission_id": emission_id, "error": f"{type(exc).__name__}: {exc}"})
    return results


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
        if side == "sell" and int(coin["owner_id"]) == int(user_id) and await repo.pending_emission(db, coin_id):
            raise PlayerExchangePolicyError("Владелец не может продавать монету, пока эмиссия ожидает исполнения.")
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
