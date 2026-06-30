"""FastAPI/routers/cosmetics.py — Конструктор внешнего вида профиля.

Каталог косметики, покупка (мульти/альт-валюта), экипировка слотов. Только
косметика, без игрового преимущества. Логика — в services/cosmetics.py.
"""
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.cosmetics import COSMETICS
from services.cosmetics import (
    buy, equip, get_catalog, set_welcome, unequip,
    chest_catalog, open_chest, craft_catalog, craft_cosmetic,
    giftable_cosmetics, gift_cosmetic, buy_chest, _RARITY_STARS,
)

router = APIRouter(prefix="/cosmetics", tags=["cosmetics"])


async def _tg_dm(user_id: int, text: str) -> None:
    """Тихий DM получателю подарка через Bot API. Ошибки глушим (мог не /start-нуть бота)."""
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": user_id, "text": text, "parse_mode": "HTML"})
    except Exception:
        pass


@router.get("/")
async def cosmetics_catalog(db=Depends(get_db), user=Depends(require_tg_user)):
    return await get_catalog(db, user["id"])


class BuyRequest(BaseModel):
    cosmetic_id: str
    option_index: int = 0


@router.post("/buy")
async def cosmetics_buy(body: BuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await buy(db, user["id"], body.cosmetic_id, body.option_index)
    if not ok:
        raise HTTPException(400, msg)
    await db.commit()
    return {"ok": True, "message": msg}


class EquipRequest(BaseModel):
    cosmetic_id: str


@router.post("/equip")
async def cosmetics_equip(body: EquipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await equip(db, user["id"], body.cosmetic_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class UnequipRequest(BaseModel):
    slot: str


@router.post("/unequip")
async def cosmetics_unequip(body: UnequipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await unequip(db, user["id"], body.slot)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class WelcomeRequest(BaseModel):
    animation_id: str


@router.post("/welcome")
async def cosmetics_welcome(body: WelcomeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await set_welcome(db, user["id"], body.animation_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ── БЛОК21 #3: сундуки-сюрпризы + крафт косметики из осколков ────────────────────

@router.get("/chests")
async def cosmetics_chests(db=Depends(get_db), user=Depends(require_tg_user)):
    return {"chests": await chest_catalog(db, user["id"])}


class ChestOpenRequest(BaseModel):
    chest_id: str


@router.post("/chest/open")
async def cosmetics_chest_open(body: ChestOpenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg, drop = await open_chest(db, user["id"], body.chest_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "drop": drop}


@router.get("/craft")
async def cosmetics_craft_catalog(db=Depends(get_db), user=Depends(require_tg_user)):
    return await craft_catalog(db, user["id"])


class CraftRequest(BaseModel):
    cosmetic_id: str


@router.post("/craft")
async def cosmetics_craft(body: CraftRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await craft_cosmetic(db, user["id"], body.cosmetic_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ── БЛОК21: подарки и сундуки за ✨ Зарники (Stars покупают ТОЛЬКО зарники) ───────

@router.get("/gift/catalog")
async def cosmetics_gift_catalog(recipient_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    return {"recipient_id": recipient_id, "items": await giftable_cosmetics(db, recipient_id)}


class GiftRequest(BaseModel):
    recipient_id: int
    cosmetic_id: str
    chat_id: int = 0   # чат, откуда открыт мини-апп — для публичного «X подарил Y» (виральность)


@router.post("/gift")
async def cosmetics_gift(body: GiftRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg, cname = await gift_cosmetic(db, user["id"], body.recipient_id, body.cosmetic_id)
    if not ok:
        raise HTTPException(400, msg)
    from infrastructure.repositories import users as users_repo
    sn = await users_repo.get_user_name(db, user["id"])
    sender = f"@{sn}" if sn and sn != str(user["id"]) else "Друг"
    # DM получателю.
    await _tg_dm(body.recipient_id,
                 f"🎁 <b>{sender}</b> подарил тебе <b>{cname}</b>! Надень в мини-аппе → 🎨 Внешний вид.")
    # Публичное признание в чате (БЛОК21 #3.2: виральность) — только в текущий чат, не спам.
    if body.chat_id:
        rn = await users_repo.get_user_name(db, body.recipient_id)
        rdisp = f"@{rn}" if rn and rn != str(body.recipient_id) else "другу"
        await _tg_dm(body.chat_id,
                     f"🎁 <b>{sender}</b> подарил {rdisp} <b>{cname}</b>! Щедрость 💜")
    return {"ok": True, "message": msg}


class ChestBuyRequest(BaseModel):
    chest_id: str


@router.post("/chest/buy")
async def cosmetics_chest_buy(body: ChestBuyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await buy_chest(db, user["id"], body.chest_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ── Прямая покупка косметики за Telegram Stars (XTR) ─────────────────────────

class StarsInvoiceRequest(BaseModel):
    cosmetic_id: str


@router.post("/stars-invoice")
async def cosmetics_stars_invoice(
    body: StarsInvoiceRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Создаёт Stars-invoice (XTR) для прямой покупки конкретной косметики."""
    cos = COSMETICS.get(body.cosmetic_id)
    if not cos:
        raise HTTPException(404, "Косметика не найдена.")
    if cos.get("source") != "shop" or not cos.get("price"):
        raise HTTPException(400, "Этот предмет не продаётся за Stars.")
    stars_price = _RARITY_STARS.get(cos["rarity"])
    if not stars_price:
        raise HTTPException(400, "Нет Stars-цены для этой редкости.")

    async with db.execute(
        "SELECT 1 FROM user_cosmetics WHERE user_id = ? AND cosmetic_id = ?",
        (user["id"], body.cosmetic_id),
    ) as c:
        if await c.fetchone():
            raise HTTPException(400, "Этот предмет уже у вас есть.")

    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise HTTPException(503, "Платежи временно недоступны.")
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/createInvoiceLink",
                json={
                    "title": cos["name"],
                    "description": cos.get("desc", "Косметика профиля — Предвестник"),
                    "payload": f"cosmetic:{body.cosmetic_id}",
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [{"label": cos["name"], "amount": stars_price}],
                },
            )
            res = r.json()
    except Exception:
        raise HTTPException(502, "Ошибка соединения с Telegram.")

    if not res.get("ok") or not res.get("result"):
        raise HTTPException(502, "Не удалось создать счёт. Попробуйте позже.")
    return {"link": res["result"], "stars": stars_price, "cosmetic_id": body.cosmetic_id}
