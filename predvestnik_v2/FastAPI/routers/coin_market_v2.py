"""Authenticated, closed-by-default v2 HTTP adapter."""

from typing import Annotated, Any

from asyncpg import UniqueViolationError
from core.coin_market_v2 import MarketError
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from fastapi import APIRouter, Depends, HTTPException
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import coin_market_v2 as repo
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from services import coin_market_v2 as service

router = APIRouter(prefix="/coin-market/v2", tags=["coin-market-v2"])
DB = Annotated[Any, Depends(get_db)]
User = Annotated[dict, Depends(require_tg_user)]


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coin_id: StrictStr = Field(min_length=1, max_length=64)
    side: StrictStr = Field(pattern=r"^(buy|sell|short|close_short)$")
    amount: StrictStr = "0"
    units: StrictInt = Field(default=0, ge=0, le=1_000_000_000)
    position_id: StrictStr | None = Field(default=None, max_length=64)


class Trade(Quote):
    action_id: StrictStr = Field(min_length=8, max_length=96)
    tick: StrictInt = Field(ge=0)
    price: StrictStr


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr = Field(min_length=3, max_length=100)
    zarniki: StrictInt = Field(ge=1000, le=5000)
    deposit: StrictStr
    diamonds: StrictBool = False
    action_id: StrictStr = Field(min_length=8, max_length=96)
    icon: StrictStr=Field(default='coin',pattern=r'^(coin|star|wave|leaf)$')
    description: StrictStr = Field(default="", max_length=160)


class Metadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    icon: StrictStr=Field(pattern=r'^(coin|star|wave|leaf)$')
    description: StrictStr=Field(max_length=160)


class Favorite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


async def call(coro):
    try:
        return await coro
    except service.Requote as exc:
        raise HTTPException(409, {"code": "requote", "message": str(exc)}) from exc
    except service.Unavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except InsufficientBalance as exc:
        raise HTTPException(400, "Недостаточно средств.") from exc
    except MarketError as exc:
        raise HTTPException(400, str(exc)) from exc
    except UniqueViolationError as exc:
        raise HTTPException(
            409, "Название или позиция уже заняты. Обновите биржу."
        ) from exc


def arguments(body):
    return {
        "coin_id": body.coin_id,
        "side": body.side,
        "amount": service.money(body.amount) if body.side in ("buy", "short") else 0,
        "units": body.units,
        "position_id": body.position_id,
    }


@router.get("/me")
async def me(db: DB, user: User, visit: bool = False):
    return await call(service.market(db, int(user["id"]), visit=visit))


@router.get("/availability")
async def availability(db: DB, user: User):
    return await service.availability(db, int(user["id"]))


@router.get("/coins/{coin_id}/history")
async def history(coin_id: str, db: DB, user: User, hours: int = 24):
    if hours not in (1, 24, 168):
        raise HTTPException(400, "Неверный период.")
    await call(service.require(db, new=False))
    if not (await service.availability(db, int(user["id"])))["visible"]:
        raise HTTPException(503, "Биржа ещё не открыта.")
    if not await repo.load(db, coin_id):
        raise HTTPException(404, "Монета не найдена.")
    return await service.history_view(db, int(user["id"]), coin_id, hours)


@router.post("/quote")
async def quote(body: Quote, db: DB, user: User):
    async def run():
        return await service.quote(db, int(user["id"]), **arguments(body))

    return await call(run())


@router.post("/trade")
async def trade(body: Trade, db: DB, user: User):
    async def run():
        return await service.trade(
            db,
            int(user["id"]),
            **arguments(body),
            action_id=body.action_id,
            tick=body.tick,
            price=service.money(body.price),
        )

    return await call(run())


@router.post("/create-quote")
async def create_quote(body: Create, db: DB, user: User):
    async def run():
        return await service.creation_quote(db,int(user['id']),name=body.name,zarniki=body.zarniki,
                                            deposit=service.money(body.deposit),diamonds=body.diamonds)

    return await call(run())


@router.post("/create")
async def create(body: Create, db: DB, user: User):
    async def run():
        return await service.create_coin(
            db,
            int(user["id"]),
            name=body.name,
            zarniki=body.zarniki,
            deposit=service.money(body.deposit),
            diamonds=body.diamonds,
            action_id=body.action_id,
            icon=body.icon,
            description=body.description,
        )

    return await call(run())


@router.put('/coins/{coin_id}/metadata')
async def metadata(coin_id:str,body:Metadata,db:DB,user:User):
    return await call(service.edit_metadata(db,int(user['id']),coin_id,body.icon,body.description))


@router.put("/coins/{coin_id}/favorite")
async def favorite(coin_id: str, body: Favorite, db: DB, user: User):
    await call(service.require(db, new=False))
    if not await repo.load(db, coin_id):
        raise HTTPException(404, "Монета не найдена.")
    async with db.connection.transaction():
        await repo.favorite(db, int(user["id"]), coin_id, body.enabled)
    return {"ok": True}


@router.get("/receipt/{action_id}")
async def receipt(action_id: str, db: DB, user: User):
    await call(service.require(db, new=False))
    row = await repo.replay(db, int(user["id"]), action_id)
    if not row:
        raise HTTPException(404, "Результат операции пока не найден.")
    return {**repo.decode(row["response"]), "replayed": True}
