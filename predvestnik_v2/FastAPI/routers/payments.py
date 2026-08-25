"""FastAPI/routers/payments.py — нативная покупка ✨ Зарников за Telegram Stars.

Mini App создаёт invoice-ссылку через Bot API createInvoiceLink (currency=XTR)
и открывает её прямо в Telegram через tg.openInvoice(). Списание звёзд и
начисление Зарников выполняет бот (bot/handlers/payments.py): pre_checkout_query
подтверждает платёж, а successful_payment валидирует общий versioned invoice
contract. Новый счёт никогда не использует legacy payload.
"""
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictInt

from FastAPI.deps import require_tg_user
from infrastructure.preprod import stars_invoice_issuance_allowed
from core.constants import ZARNIKI_PER_STAR, STARS_PACKAGES, STARS_MOST_POPULAR
from core.payment_contract import (
    MAX_STARS,
    STARS_CURRENCY,
    custom_quote,
    invoice_payload,
    is_issuable_v1_quote,
    is_stars_amount,
    package_quote,
)

router = APIRouter(prefix="/payments", tags=["payments"])

async def _tg_call(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/zarniki/packages")
async def zarniki_packages(user=Depends(require_tg_user)):
    """Пакеты Stars→Зарники + параметры произвольной суммы (для донат-витрины)."""
    return {
        "per_star": ZARNIKI_PER_STAR,
        "packages": [
            {
                "stars": s,
                "zarniki": base,
                "bonus": bonus,
                "total": base + bonus,
                "popular": s == STARS_MOST_POPULAR,
            }
            for s, base, bonus in STARS_PACKAGES
        ],
        "custom_min": 1,
        "custom_max": MAX_STARS,
    }


class InvoiceRequest(BaseModel):
    stars: StrictInt


@router.post("/zarniki/invoice")
async def zarniki_invoice(body: InvoiceRequest, user=Depends(require_tg_user)):
    """Создаёт Stars-invoice (XTR) и возвращает ссылку для tg.openInvoice()."""
    if not stars_invoice_issuance_allowed():
        raise HTTPException(
            403,
            "Покупки Stars отключены на изолированном тестовом стенде.",
        )
    stars = body.stars
    if not is_stars_amount(stars):
        raise HTTPException(400, f"Количество звёзд: от 1 до {MAX_STARS}.")

    quote = package_quote(stars) or custom_quote(stars)
    if not quote or not is_issuable_v1_quote(quote):
        # A tariff revision must introduce a new frozen payload version before
        # selling anything.  Do not create an invoice the bot will reject.
        raise HTTPException(503, "Покупка временно обновляется. Попробуйте чуть позже.")
    res = await _tg_call(
        "createInvoiceLink",
        title="Зарники ✨",
        description=f"{quote.zarniki}✨ Зарников для Предвестника",
        payload=invoice_payload(quote),
        provider_token="",          # пусто для оплаты Telegram Stars
        currency=STARS_CURRENCY,
        prices=[{"label": f"{quote.zarniki}✨ Зарников", "amount": quote.stars}],
    )
    if not res.get("ok") or not res.get("result"):
        raise HTTPException(502, "Не удалось создать счёт. Попробуйте позже.")
    return {"link": res["result"], "stars": quote.stars, "zarniki": quote.zarniki}
