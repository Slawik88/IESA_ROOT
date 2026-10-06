"""Authenticated, fail-closed API for the player-created exchange."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.player_exchange_v1 import PlayerExchangePolicyError
from infrastructure.repositories import player_exchange_v1 as repo
from services import player_exchange_v1 as service
from FastAPI.routers.dev_console._common import _require_dev


router = APIRouter(prefix="/player-exchange/v1", tags=["player-exchange-v1"])


class CoinCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ticker: str = Field(min_length=1, max_length=12)
    initial_mora: int
    action_id: str = Field(min_length=8, max_length=128)


class AuctionBidRequest(BaseModel):
    max_price_mora: str = Field(min_length=1, max_length=32)
    escrow_mora: int
    action_id: str = Field(min_length=8, max_length=128)


class LimitOrderRequest(BaseModel):
    side: str
    amount: str
    limit_price_mora: str
    time_in_force: str = "gtc"
    action_id: str = Field(min_length=8, max_length=128)


class ProtectedMarketOrderRequest(BaseModel):
    side: str
    amount: str
    slippage_percent: int = 3
    action_id: str = Field(min_length=8, max_length=128)


class ManualMarketHaltRequest(BaseModel):
    minutes: int = Field(ge=5, le=1_440)
    public_reason: str = Field(min_length=10, max_length=160)
    action_id: str = Field(min_length=8, max_length=128)


class EmissionRequest(BaseModel):
    amount: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=10, max_length=160)
    action_id: str = Field(min_length=8, max_length=128)


class EmissionCancelRequest(BaseModel):
    action_id: str = Field(min_length=8, max_length=128)


class OwnerVestingClaimRequest(BaseModel):
    action_id: str = Field(min_length=8, max_length=128)
    units: int = Field(gt=0)


class TreasuryOrderRequest(BaseModel):
    side: str
    amount: str = Field(min_length=1, max_length=32)
    limit_price_mora: str = Field(min_length=1, max_length=32)
    action_id: str = Field(min_length=8, max_length=128)


class TreasuryBurnRequest(BaseModel):
    amount: str = Field(min_length=1, max_length=32)
    action_id: str = Field(min_length=8, max_length=128)


class LiquidityAmountRequest(BaseModel):
    amount_mora: str = Field(min_length=1, max_length=32)
    action_id: str = Field(min_length=8, max_length=128)


class ShortCollateralRequest(BaseModel):
    amount_mora: str = Field(min_length=1, max_length=32)
    action_id: str = Field(min_length=8, max_length=128)


class ShortUnitsRequest(BaseModel):
    amount: str = Field(min_length=1, max_length=32)
    action_id: str = Field(min_length=8, max_length=128)


class ShortOpenRequest(ShortUnitsRequest):
    max_collateral_mora: str = Field(min_length=1, max_length=32)
    min_sale_price_micromora: int = Field(gt=0)
    max_apr_bps: int = Field(ge=0)


class ShortActionRequest(BaseModel):
    action_id: str = Field(min_length=8, max_length=128)


class ShortCloseRequest(ShortActionRequest):
    max_buyback_price_micromora: int = Field(gt=0)
    max_escrow_debit_mora: str = Field(min_length=1, max_length=32)


class ShortReduceRequest(ShortCloseRequest):
    amount: str = Field(min_length=1, max_length=32)


class ShortLiquidationRequest(ShortActionRequest):
    pass


@router.get("/me")
async def my_exchange_state(limit: int = 50, holdings_cursor: str | None = None,
                            orders_cursor: str | None = None, bids_cursor: str | None = None,
                            coins_cursor: str | None = None,
                            db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        state = await service.player_recovery_state(
            db, user_id=int(user["id"]), limit=limit, holdings_cursor=holdings_cursor,
            orders_cursor=orders_cursor, bids_cursor=bids_cursor,
            coins_cursor=coins_cursor,
        )
        return {
            **state,
            "notice": "Игровые активы без вывода в деньги.",
        }
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/shorts/me")
async def my_short_state(limit: int = 50, lending_cursor: str | None = None,
                         positions_cursor: str | None = None,
                         principal_cursor: str | None = None,
                         interest_cursor: str | None = None,
                         db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.short_recovery_state(
            db, user_id=int(user["id"]), limit=limit, lending_cursor=lending_cursor,
            positions_cursor=positions_cursor, principal_cursor=principal_cursor,
            interest_cursor=interest_cursor,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/shorts/coins/{coin_id}/liquidations")
async def short_liquidation_candidates(coin_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"items": await service.short_liquidation_candidates(db, coin_id=coin_id)}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/shorts/positions/{position_id}/liquidate")
async def execute_short_liquidation(position_id: str, payload: ShortLiquidationRequest,
                                    db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.liquidate_short(
            db, executor_id=int(user["id"]), position_id=position_id, action_id=payload.action_id,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/shorts/positions/{position_id}/collateral")
async def top_up_short_collateral(position_id: str, payload: ShortCollateralRequest,
                                  db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.add_short_collateral(
            db, user_id=int(user["id"]), position_id=position_id,
            amount_mora=payload.amount_mora, action_id=payload.action_id,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/shorts/coins/{coin_id}/lending/deposit")
async def deposit_short_lending(coin_id: str, payload: ShortUnitsRequest,
                                db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.deposit_lending_units(
            db, user_id=int(user["id"]), coin_id=coin_id,
            amount=payload.amount, action_id=payload.action_id,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/shorts/coins/{coin_id}/lending/withdraw")
async def withdraw_short_lending(coin_id: str, payload: ShortUnitsRequest,
                                 db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.withdraw_lending_units(
            db, user_id=int(user["id"]), coin_id=coin_id,
            amount=payload.amount, action_id=payload.action_id,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/shorts/coins/{coin_id}/positions")
async def open_short_position(coin_id: str, payload: ShortOpenRequest,
                              db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.open_short(
            db, user_id=int(user["id"]), coin_id=coin_id,
            amount=payload.amount, action_id=payload.action_id,
            max_collateral_mora=payload.max_collateral_mora,
            min_sale_price_micromora=payload.min_sale_price_micromora,
            max_apr_bps=payload.max_apr_bps,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.get("/shorts/coins/{coin_id}/open-quote")
async def quote_short_open(coin_id: str, amount: str,
                           db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.short_open_quote(
            db, user_id=int(user["id"]), coin_id=coin_id, amount=amount,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/shorts/positions/{position_id}/reduce")
async def reduce_short_position(position_id: str, payload: ShortReduceRequest,
                                db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.reduce_short(
            db, user_id=int(user["id"]), position_id=position_id,
            amount=payload.amount, action_id=payload.action_id,
            max_buyback_price_micromora=payload.max_buyback_price_micromora,
            max_escrow_debit_mora=payload.max_escrow_debit_mora,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.get("/shorts/positions/{position_id}/close-quote")
async def quote_short_close(position_id: str, amount: str | None = None,
                            db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.short_close_quote(
            db, user_id=int(user["id"]), position_id=position_id, amount=amount,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/shorts/positions/{position_id}/close")
async def close_short_position(position_id: str, payload: ShortCloseRequest,
                               db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.close_short(
            db, user_id=int(user["id"]), position_id=position_id, action_id=payload.action_id,
            max_buyback_price_micromora=payload.max_buyback_price_micromora,
            max_escrow_debit_mora=payload.max_escrow_debit_mora,
        )
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.get("/coins")
async def coins(db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await service.require_enabled(db)
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"items": await repo.list_coins(db), "notice": "Игровые активы без вывода в деньги."}


@router.post("/coins")
async def create_coin(payload: CoinCreateRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        coin = await service.create_coin(
            db, owner_id=int(user["id"]), name=payload.name, ticker=payload.ticker,
            initial_mora=payload.initial_mora, action_id=payload.action_id,
        )
        return {"coin": coin, "notice": "Игровой актив без вывода в деньги."}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/auction-bids")
async def auction_bid(coin_id: str, payload: AuctionBidRequest,
                      db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        bid = await service.place_auction_bid(
            db, bidder_id=int(user["id"]), coin_id=coin_id,
            max_price_mora=payload.max_price_mora, escrow_mora=payload.escrow_mora,
            action_id=payload.action_id,
        )
        return {"bid": bid, "notice": "Мора зарезервирована до закрытия аукциона."}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/orders")
async def place_order(coin_id: str, payload: LimitOrderRequest,
                      db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        order = await service.place_limit_order(
            db, user_id=int(user["id"]), coin_id=coin_id, side=payload.side,
            amount=payload.amount, limit_price_mora=payload.limit_price_mora,
            time_in_force=payload.time_in_force, action_id=payload.action_id,
        )
        return {"order": order}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"order": await service.cancel_order(db, user_id=int(user["id"]), order_id=order_id)}
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/coins/{coin_id}/market")
async def market(coin_id: str, levels: int = 20, trades: int = 50,
                 db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return await service.public_market(db, coin_id=coin_id, levels=levels, trades=trades)
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/coins/{coin_id}/market-orders")
async def market_order(coin_id: str, payload: ProtectedMarketOrderRequest,
                       db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        order = await service.place_protected_market_order(
            db, user_id=int(user["id"]), coin_id=coin_id, side=payload.side,
            amount=payload.amount, slippage_percent=payload.slippage_percent,
            action_id=payload.action_id,
        )
        return {"order": order}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/admin/coins/{coin_id}/halt")
async def halt_market(coin_id: str, payload: ManualMarketHaltRequest,
                      db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    try:
        return {"halt": await service.manually_halt_market(
            db, actor_id=int(user["id"]), coin_id=coin_id, minutes=payload.minutes,
            public_reason=payload.public_reason, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/emissions")
async def request_emission(coin_id: str, payload: EmissionRequest,
                           db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"emission": await service.request_emission(
            db, owner_id=int(user["id"]), coin_id=coin_id, amount=payload.amount,
            reason=payload.reason, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/emissions/{emission_id}/cancel")
async def cancel_emission(emission_id: str, payload: EmissionCancelRequest,
                          db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"emission": await service.cancel_emission(
            db, owner_id=int(user["id"]), emission_id=emission_id, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/owner-vesting/claim")
async def claim_owner_vesting(coin_id: str, payload: OwnerVestingClaimRequest,
                              db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"vesting": await service.claim_owner_vesting(
            db, owner_id=int(user["id"]), coin_id=coin_id, units=payload.units,
            action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/treasury/orders")
async def place_treasury_order(coin_id: str, payload: TreasuryOrderRequest,
                               db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"order": await service.place_treasury_order(
            db, owner_id=int(user["id"]), coin_id=coin_id, side=payload.side,
            amount=payload.amount, limit_price_mora=payload.limit_price_mora,
            action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/treasury/orders/{order_id}/cancel")
async def cancel_treasury_order(order_id: str, payload: EmissionCancelRequest,
                                db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"order": await service.cancel_treasury_order(
            db, owner_id=int(user["id"]), order_id=order_id, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/treasury/burn")
async def burn_treasury(coin_id: str, payload: TreasuryBurnRequest,
                        db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"burn": await service.burn_treasury(
            db, owner_id=int(user["id"]), coin_id=coin_id,
            amount=payload.amount, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/liquidity/add")
async def add_liquidity(coin_id: str, payload: LiquidityAmountRequest,
                        db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"liquidity": await service.add_treasury_liquidity(
            db, owner_id=int(user["id"]), coin_id=coin_id,
            amount_mora=payload.amount_mora, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except (PlayerExchangePolicyError, InsufficientBalance) as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/coins/{coin_id}/liquidity/withdrawals")
async def request_liquidity_withdrawal(coin_id: str, payload: LiquidityAmountRequest,
                                       db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"withdrawal": await service.request_liquidity_withdrawal(
            db, owner_id=int(user["id"]), coin_id=coin_id,
            amount_mora=payload.amount_mora, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc


@router.post("/liquidity/withdrawals/{withdrawal_id}/cancel")
async def cancel_liquidity_withdrawal(withdrawal_id: str, payload: EmissionCancelRequest,
                                      db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        return {"withdrawal": await service.cancel_liquidity_withdrawal(
            db, owner_id=int(user["id"]), withdrawal_id=withdrawal_id, action_id=payload.action_id,
        )}
    except service.PlayerExchangeUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except PlayerExchangePolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, "Этот идентификатор уже использован для другой операции.") from exc
