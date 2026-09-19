"""FastAPI/routers/payments.py — нативная покупка ✨ Зарников за Telegram Stars.

Mini App создаёт invoice-ссылку через Bot API createInvoiceLink (currency=XTR)
и открывает её прямо в Telegram через tg.openInvoice(). Списание звёзд и
начисление Зарников выполняет бот (bot/handlers/payments.py): pre_checkout_query
подтверждает платёж, а successful_payment валидирует общий versioned invoice
contract. Новый счёт никогда не использует legacy payload.
"""
import os
import json

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, StrictInt

from FastAPI.deps import get_db, require_tg_user
from infrastructure.preprod import direct_stars_cosmetics_allowed, stars_invoice_issuance_allowed
from services import supporter_cosmetics_v1
from infrastructure.repositories import supporter_cosmetics_v1 as supporter_repo
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
        "purchase_enabled": stars_invoice_issuance_allowed(),
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


class CosmeticInvoiceRequest(BaseModel):
    offer_id: str


class CosmeticSelectRequest(BaseModel):
    cosmetic_id: str | None = None
    expected_revision: StrictInt


@router.get("/cosmetics/offers")
async def cosmetic_offers(db=Depends(get_db),
                          user=Depends(require_tg_user)):
    view = await supporter_cosmetics_v1.overview(db, int(user["id"]))
    view["purchase_enabled"] = direct_stars_cosmetics_allowed() and await supporter_repo.schema_ready(db)
    return view


@router.post("/cosmetics/invoice")
async def cosmetic_invoice(
    body: CosmeticInvoiceRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_id: str = Header(alias="Idempotency-Key"),
):
    if not direct_stars_cosmetics_allowed() or not await supporter_repo.schema_ready(db):
        raise HTTPException(403, "Прямая Stars-косметика закрыта до завершения refund rail.")
    try:
        order, _ = await supporter_cosmetics_v1.create_order(
            db, payer_user_id=int(user["id"]), beneficiary_user_id=int(user["id"]),
            offer_id=body.offer_id, request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    stored_link = order.get("invoice_link")
    if stored_link:
        return {"link": stored_link, "order_id": order["order_id"],
                "offer_id": order["offer_id"], "stars": int(order["stars_amount"])}
    snapshot = order["offer_snapshot_json"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    if not isinstance(snapshot, dict):
        raise HTTPException(409, "У заказа нет неизменяемого описания предложения.")
    res = await _tg_call(
        "createInvoiceLink", title=snapshot["name"], description=snapshot["description"],
        payload=order["invoice_payload"], provider_token="", currency="XTR",
        prices=[{"label": snapshot["name"], "amount": int(order["stars_amount"])}],
    )
    if not res.get("ok") or not res.get("result"):
        raise HTTPException(502, "Не удалось создать счёт. Повторите с тем же запросом позже.")
    try:
        saved = await supporter_repo.store_invoice_link(db, order["order_id"], res["result"])
    except RuntimeError as exc:
        raise HTTPException(409, "Заказ уже изменился; откройте витрину заново.") from exc
    return {"link": saved["invoice_link"], "order_id": saved["order_id"],
            "offer_id": saved["offer_id"], "stars": int(saved["stars_amount"])}


@router.post("/cosmetics/select")
async def cosmetic_select(body: CosmeticSelectRequest, db=Depends(get_db),
                          user=Depends(require_tg_user)):
    try:
        return await supporter_cosmetics_v1.select(
            db, user_id=int(user["id"]), cosmetic_id=body.cosmetic_id,
            expected_revision=int(body.expected_revision),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/zarniki/invoice")
async def zarniki_invoice(body: InvoiceRequest, user=Depends(require_tg_user)):
    """Создаёт Stars-invoice (XTR) и возвращает ссылку для tg.openInvoice()."""
    if not stars_invoice_issuance_allowed():
        raise HTTPException(
            403,
            "Покупки Stars временно закрыты до завершения безопасного возврата и учёта цифровых прав.",
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
