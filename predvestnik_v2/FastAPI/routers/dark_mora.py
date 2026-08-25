"""Read-only compatibility surface for the retired Dark Mora earn loop.

The owner-v3 economy has three active wallets. Existing Dark Mora can still
settle already-issued archive purchases, but no endpoint here can mint it or
consume Mora to create it.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS,
    DARK_MORA_SHADOW_MERCHANT_REWARD_MAX,
    DARK_MORA_SHADOW_MERCHANT_REWARD_MIN,
    DARK_MORA_SHADOW_MERCHANT_WINNERS,
)
from core.registry import SHADOW_RELICS
from FastAPI.deps import get_db, require_module, require_tg_user
from infrastructure.repositories import shadow_merchant as sm_repo


router = APIRouter(
    prefix="/dark-mora",
    tags=["dark-mora"],
    dependencies=[Depends(require_module("module_warps"))],
)


class ContrabandaRequest(BaseModel):
    stake: float


@router.post("/contrabanda")
async def contrabanda(
    body: ContrabandaRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    del body, db, user
    raise HTTPException(
        410,
        "Контрабанда закрыта: она превращала ставку в отдельную валюту без связи с основной прогрессией.",
    )


@router.post("/ritual")
async def ritual(db=Depends(get_db), user=Depends(require_tg_user)):
    del db, user
    raise HTTPException(
        410,
        "Ритуал закрыт: старые стрик и уровень больше не создают Тёмную Мору.",
    )


@router.get("/merchant-status")
async def merchant_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Return archived merchant rights without advertising a live event."""
    now = datetime.now(timezone.utc)
    last_event = None
    next_event = None
    try:
        async with db.execute(
            "SELECT posted_at FROM shadow_merchant_events ORDER BY posted_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            last_event = row[0]
            if isinstance(last_event, str):
                last_event = datetime.fromisoformat(last_event.replace(" ", "T"))
            if last_event.tzinfo is None:
                last_event = last_event.replace(tzinfo=timezone.utc)
            next_event = last_event + timedelta(days=DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS)
    except Exception:
        last_event = None
        next_event = None

    vouchers = await sm_repo.voucher_count(db, user["id"])
    owned = set(await sm_repo.owned_shadow_relics(db, user["id"]))
    return {
        "active": False,
        "retired": True,
        "checked_at": now.isoformat(),
        "last_event": last_event.isoformat() if last_event else None,
        "next_expected": next_event.isoformat() if next_event else None,
        "cooldown_days": DARK_MORA_SHADOW_MERCHANT_COOLDOWN_DAYS,
        "winners": DARK_MORA_SHADOW_MERCHANT_WINNERS,
        "reward_min": DARK_MORA_SHADOW_MERCHANT_REWARD_MIN,
        "reward_max": DARK_MORA_SHADOW_MERCHANT_REWARD_MAX,
        "vouchers": vouchers,
        "shadow_relics": [
            {
                "id": relic_id,
                "name": relic["name"],
                "price_dark": relic["price_dark"],
                "gates_dark_pct": relic["gates_dark_pct"],
                "desc": relic["desc"],
                "owned": relic_id in owned,
            }
            for relic_id, relic in SHADOW_RELICS.items()
        ],
        "how_it_works": (
            "Новые загадки закрыты. Старый баланс и уже полученные права покупки сохранены."
        ),
    }
