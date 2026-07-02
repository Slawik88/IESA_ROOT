"""FastAPI/routers/marriage.py — брак и семейный банк."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.marriages import (
    get_user_marriage, family_bank_transaction, delete_marriage, FAMILY_CURRENCIES,
    get_received_gifts, purchase_partner_gift,
)
from core.registry import PARTNER_GIFTS
from services.achievements import backfill_metric
from services.vip import is_vip_active

router = APIRouter(prefix="/marriage", tags=["marriage"])


@router.get("/")
async def my_marriage(db=Depends(get_db), user=Depends(require_tg_user)):
    """Брак текущего пользователя + питомцы семьи + стаж."""
    m = await get_user_marriage(db, user["id"])
    if not m:
        return {"married": False}

    partner_id = m["user2_id"] if m["user1_id"] == user["id"] else m["user1_id"]
    partner_name = m["user2_name"] if m["user1_id"] == user["id"] else m["user1_name"]
    partner_is_vip = await is_vip_active(db, partner_id)

    # Family pets (marriage_id set on pets)
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level,1) AS pet_level "
        "FROM pets WHERE marriage_id = ?",
        (m["id"],),
    ) as c:
        family_pets = [dict(r) for r in await c.fetchall()]

    # Marriage duration in days
    from datetime import datetime, timezone
    try:
        since = datetime.fromisoformat(str(m["marriage_date"]).replace(" ", "T"))
        since = since.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - since).days
    except Exception:
        days = 0

    # Backfill vow_keeper achievement from marriage duration (catch-up if days > progress)
    try:
        await backfill_metric(db, user["id"], "marriage_days_total", float(days))
        await db.commit()
    except Exception:
        pass

    return {
        "married": True,
        "marriage_id": m["id"],
        "partner_id": partner_id,
        "partner_name": partner_name,
        "partner_is_vip": partner_is_vip,
        "family_balance": float(m["family_balance"] or 0),
        "family_balance_diamonds": float(m.get("family_balance_diamonds", 0) or 0),
        "family_balance_dark_mora": float(m.get("family_balance_dark_mora", 0) or 0),
        "family_balance_zarniki": float(m.get("family_balance_zarniki", 0) or 0),
        "days": days,
        "family_pets": family_pets,
        "received_gifts": [
            {"name": PARTNER_GIFTS.get(g["gift_id"], {}).get("name", g["gift_id"]),
             "sent_at": str(g["sent_at"])}
            for g in await get_received_gifts(db, user["id"], 5)
        ],
    }


class BankRequest(BaseModel):
    marriage_id: int
    amount: float
    action: str            # "deposit" | "withdraw"
    currency: str = "mora"  # mora | diamonds | dark_mora | zarniki


@router.post("/bank")
async def family_bank(body: BankRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Депозит или вывод любой из 4 валют семейного кошелька."""
    if body.action not in ("deposit", "withdraw"):
        raise HTTPException(400, "action: 'deposit' или 'withdraw'")
    if body.currency not in FAMILY_CURRENCIES:
        raise HTTPException(400, "Неизвестная валюта.")
    ok, msg = await family_bank_transaction(db, body.marriage_id, user["id"],
                                            body.amount, body.action, body.currency)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class FundRequest(BaseModel):
    currency: str = "mora"
    amount: float


@router.post("/fund")
async def fund_from_family(body: FundRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Block 5.2 (авто-перевод): перенести сумму из семейного кошелька на личный
    счёт перед покупкой. marriage_id резолвится сервером. Излишек (если была
    скидка) просто останется на личном — деньги не теряются."""
    if body.currency not in FAMILY_CURRENCIES:
        raise HTTPException(400, "Неизвестная валюта.")
    if body.amount <= 0:
        raise HTTPException(400, "Сумма должна быть больше нуля.")
    m = await get_user_marriage(db, user["id"])
    if not m:
        raise HTTPException(400, "Вы не состоите в браке.")
    ok, msg = await family_bank_transaction(db, m["id"], user["id"],
                                            body.amount, "withdraw", body.currency)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ── Подарки партнёру (Block 5.4 — паритет с ботом `бот подарки`) ──────────────
def _gift_currency(g: dict) -> tuple[str | None, float]:
    """(currency, price) из полей реестра подарка."""
    if g.get("price_mora"):     return "mora", float(g["price_mora"])
    if g.get("price_diamonds"): return "diamonds", float(g["price_diamonds"])
    if g.get("price_zarniki"):  return "zarniki", float(g["price_zarniki"])
    return None, 0.0


async def _notify_partner_gift(db, sender_id: int, partner_id: int, gift: dict) -> None:
    """Коробка «подарок от супруга»: WS если партнёр онлайн, иначе web_notifications
    (покажется при следующем входе). Тот же паттерн, что админ-подарки."""
    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (sender_id,)
    ) as c:
        row = await c.fetchone()
    from_name = row[0] if row and row[0] else f"ID{sender_id}"
    payload = {
        "type": "partner_gift",
        "from": from_name,
        "gift_name": gift.get("name", "подарок"),
        "msg": gift.get("msg", ""),
    }
    try:
        from FastAPI.notifications import notify as _ws_notify
        delivered = await _ws_notify(partner_id, payload)
    except Exception:
        delivered = False
    if not delivered:
        try:
            from infrastructure.repositories import web_notifications as _wn
            await _wn.add(db, partner_id, payload)
            await db.commit()
        except Exception:
            pass


@router.get("/gifts")
async def gift_catalog(user=Depends(require_tg_user)):
    """Каталог подарков партнёру — тот же PARTNER_GIFTS, что в боте."""
    out = []
    for gid, g in PARTNER_GIFTS.items():
        cur, price = _gift_currency(g)
        out.append({
            "id": gid, "name": g["name"], "kind": g["kind"],
            "currency": cur, "price": price,
            "buff_value": g.get("buff_value"), "buff_hours": g.get("buff_hours"),
        })
    return {"gifts": out}


class GiftRequest(BaseModel):
    gift_id: str


@router.post("/gift")
async def send_partner_gift(body: GiftRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить и вручить подарок супругу. Списывает с личного баланса дарителя,
    бафф-подарки дают +XP партнёру, лог в partner_gifts_log (см. бот `бот подарки`)."""
    if body.gift_id not in PARTNER_GIFTS:
        raise HTTPException(400, "Неизвестный подарок.")
    m = await get_user_marriage(db, user["id"])
    if not m:
        raise HTTPException(400, "Вы не состоите в браке.")
    partner_id = m["user2_id"] if m["user1_id"] == user["id"] else m["user1_id"]
    ok, msg, gift = await purchase_partner_gift(db, user["id"], partner_id, body.gift_id)
    if not ok:
        raise HTTPException(400, msg)
    # purchase_partner_gift коммитит сам (db.connection.transaction()).
    await _notify_partner_gift(db, user["id"], partner_id, gift)
    return {"ok": True, "message": msg, "gift_name": gift.get("name")}


@router.post("/divorce")
async def divorce(db=Depends(get_db), user=Depends(require_tg_user)):
    """Развод — удаляет брак текущего пользователя."""
    m = await get_user_marriage(db, user["id"])
    if not m:
        raise HTTPException(404, "Вы не состоите в браке.")
    await delete_marriage(db, user["id"])
    return {"ok": True}


@router.get("/proposals")
async def get_proposals(db=Depends(get_db), user=Depends(require_tg_user)):
    """Входящие предложения о браке для текущего пользователя."""
    async with db.execute(
        "SELECT mp.id, mp.chat_id, mp.proposer_id, mp.proposed_at, mp.expires_at, "
        "u.user_tg_username AS proposer_name, "
        "(v.user_id IS NOT NULL) AS proposer_is_vip "
        "FROM marriage_proposals mp "
        "LEFT JOIN users u ON mp.proposer_id = u.user_tg_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = mp.proposer_id AND v.expires_at > NOW() "
        "WHERE mp.target_id = ? AND mp.status = 'pending' AND mp.expires_at > NOW() "
        "ORDER BY mp.proposed_at DESC",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    return {"proposals": rows}


class ProposalActionRequest(BaseModel):
    proposal_id: int


@router.post("/proposals/accept")
async def accept_proposal(body: ProposalActionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Принять предложение о браке."""
    async with db.execute(
        "SELECT * FROM marriage_proposals WHERE id = ? AND target_id = ? AND status = 'pending' AND expires_at > NOW()",
        (body.proposal_id, user["id"]),
    ) as c:
        prop = await c.fetchone()
    if not prop:
        raise HTTPException(404, "Предложение не найдено или уже истекло.")
    prop = dict(prop)

    existing = await get_user_marriage(db, user["id"])
    if existing:
        raise HTTPException(400, "Вы уже состоите в браке.")

    # The bot's flow re-checks BOTH parties via check_marriage_proposal before
    # creating the marriage — mirror that here. Without it, accepting a stale
    # proposal whose proposer got married in the meantime would create a
    # second marriage row for an already-married user.
    proposer_existing = await get_user_marriage(db, prop["proposer_id"])
    if proposer_existing:
        raise HTTPException(400, "Этот пользователь уже состоит в браке.")

    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (user["id"],)
    ) as c:
        my_row = await c.fetchone()
    my_name = my_row[0] if my_row and my_row[0] else f"ID{user['id']}"

    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (prop["proposer_id"],)
    ) as c:
        pr_row = await c.fetchone()
    proposer_name = pr_row[0] if pr_row and pr_row[0] else f"ID{prop['proposer_id']}"

    # Wrap creation + proposal-status update atomically — otherwise a failure
    # after INSERT could leave the proposal "pending" and acceptable again,
    # producing a duplicate marriage row.
    async with db.connection.transaction():
        await db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) VALUES (?,?,?,?,?)",
            (prop["chat_id"], prop["proposer_id"], proposer_name, user["id"], my_name),
        )
        await db.execute(
            "UPDATE marriage_proposals SET status = 'accepted' WHERE id = ?", (body.proposal_id,)
        )
    return {"ok": True}


@router.post("/proposals/decline")
async def decline_proposal(body: ProposalActionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отклонить предложение о браке."""
    async with db.execute(
        "SELECT id FROM marriage_proposals WHERE id = ? AND target_id = ? AND status = 'pending'",
        (body.proposal_id, user["id"]),
    ) as c:
        prop = await c.fetchone()
    if not prop:
        raise HTTPException(404, "Предложение не найдено.")
    await db.execute(
        "UPDATE marriage_proposals SET status = 'declined' WHERE id = ?", (body.proposal_id,)
    )
    await db.commit()
    return {"ok": True}
