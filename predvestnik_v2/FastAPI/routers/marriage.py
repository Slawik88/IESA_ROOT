"""FastAPI/routers/marriage.py — брак и семейный банк."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.marriages import (
    get_user_marriage, family_bank_transaction, delete_marriage,
)
from infrastructure.repositories.zoo import get_user_pets
from services.achievements import increment_metric as ach_incr

router = APIRouter(prefix="/marriage", tags=["marriage"])


async def _get_any_marriage(db, user_id: int) -> dict | None:
    """Find marriage in any chat for this user."""
    async with db.execute(
        "SELECT id, chat_id, user1_id, user1_name, user2_id, user2_name, "
        "marriage_date, family_balance FROM marriages "
        "WHERE user1_id = ? OR user2_id = ?",
        (user_id, user_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


@router.get("/")
async def my_marriage(db=Depends(get_db), user=Depends(require_tg_user)):
    """Брак текущего пользователя + питомцы семьи + стаж."""
    m = await _get_any_marriage(db, user["id"])
    if not m:
        return {"married": False}

    partner_id = m["user2_id"] if m["user1_id"] == user["id"] else m["user1_id"]
    partner_name = m["user2_name"] if m["user1_id"] == user["id"] else m["user1_name"]

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

    # Backfill vow_keeper achievement if days > 0 and progress is 0
    try:
        from infrastructure.repositories.achievements import get_achievement, upsert_achievement
        rec = await get_achievement(db, user["id"], "vow_keeper")
        if (rec is None or rec["progress"] == 0) and days > 0:
            grants = await ach_incr(db, user["id"], "marriage_days_total", delta=float(days))
            if grants:
                await db.commit()
    except Exception:
        pass

    return {
        "married": True,
        "marriage_id": m["id"],
        "partner_id": partner_id,
        "partner_name": partner_name,
        "family_balance": float(m["family_balance"] or 0),
        "days": days,
        "family_pets": family_pets,
    }


class BankRequest(BaseModel):
    marriage_id: int
    amount: float
    action: str   # "deposit" | "withdraw"


@router.post("/bank")
async def family_bank(body: BankRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Депозит или вывод из семейного банка."""
    if body.action not in ("deposit", "withdraw"):
        raise HTTPException(400, "action: 'deposit' или 'withdraw'")
    ok, msg = await family_bank_transaction(db, body.marriage_id, user["id"],
                                            body.amount, body.action)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.post("/divorce")
async def divorce(db=Depends(get_db), user=Depends(require_tg_user)):
    """Развод — удаляет брак текущего пользователя."""
    m = await _get_any_marriage(db, user["id"])
    if not m:
        raise HTTPException(404, "Вы не состоите в браке.")
    await delete_marriage(db, m["chat_id"], user["id"])
    return {"ok": True}


@router.get("/proposals")
async def get_proposals(db=Depends(get_db), user=Depends(require_tg_user)):
    """Входящие предложения о браке для текущего пользователя."""
    async with db.execute(
        "SELECT mp.id, mp.chat_id, mp.proposer_id, mp.proposed_at, mp.expires_at, "
        "u.user_tg_username AS proposer_name "
        "FROM marriage_proposals mp "
        "LEFT JOIN users u ON mp.proposer_id = u.user_tg_id "
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

    existing = await _get_any_marriage(db, user["id"])
    if existing:
        raise HTTPException(400, "Вы уже состоите в браке.")

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

    await db.execute(
        "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) VALUES (?,?,?,?,?)",
        (prop["chat_id"], prop["proposer_id"], proposer_name, user["id"], my_name),
    )
    await db.execute(
        "UPDATE marriage_proposals SET status = 'accepted' WHERE id = ?", (body.proposal_id,)
    )
    await db.commit()
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
