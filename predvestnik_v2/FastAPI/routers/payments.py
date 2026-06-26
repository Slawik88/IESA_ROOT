"""FastAPI/routers/payments.py — нативная покупка ✨ Зарников за Telegram Stars.

Mini App создаёт invoice-ссылку через Bot API createInvoiceLink (currency=XTR)
и открывает её прямо в Telegram через tg.openInvoice(). Списание звёзд и
начисление Зарников выполняет бот (bot/handlers/payments.py): pre_checkout_query
подтверждает платёж, а successful_payment начисляет ровно столько Зарников,
сколько закодировано в payload "zarniki:{amount}". Тот же payload — тот же
обработчик, что и при покупке через чат: деньги/начисление гарантированы ботом.
"""
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import require_tg_user
from core.constants import ZARNIKI_PER_STAR, STARS_PACKAGES, STARS_MOST_POPULAR

router = APIRouter(prefix="/payments", tags=["payments"])

_MAX_STARS = 100_000


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
        "custom_max": _MAX_STARS,
    }


class InvoiceRequest(BaseModel):
    stars: int


@router.post("/zarniki/invoice")
async def zarniki_invoice(body: InvoiceRequest, user=Depends(require_tg_user)):
    """Создаёт Stars-invoice (XTR) и возвращает ссылку для tg.openInvoice()."""
    stars = int(body.stars)
    if not (1 <= stars <= _MAX_STARS):
        raise HTTPException(400, f"Количество звёзд: от 1 до {_MAX_STARS}.")

    # Пакетные покупки получают бонус; кастомная сумма — по тарифу без бонуса
    pkg = next((p for p in STARS_PACKAGES if p[0] == stars), None)
    zarniki = (pkg[1] + pkg[2]) if pkg else (stars * ZARNIKI_PER_STAR)
    res = await _tg_call(
        "createInvoiceLink",
        title="Зарники ✨",
        description=f"{zarniki}✨ Зарников для Предвестника",
        payload=f"zarniki:{zarniki}",
        provider_token="",          # пусто для оплаты Telegram Stars
        currency="XTR",
        prices=[{"label": f"{zarniki}✨ Зарников", "amount": stars}],
    )
    if not res.get("ok") or not res.get("result"):
        raise HTTPException(502, "Не удалось создать счёт. Попробуйте позже.")
    return {"link": res["result"], "stars": stars, "zarniki": zarniki}
