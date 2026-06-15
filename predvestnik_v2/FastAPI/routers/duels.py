"""FastAPI/routers/duels.py — дуэли: просмотр и управление."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.zoo import get_user_pets as _get_pets
from services.duel import decline_duel, create_challenge, accept_duel

router = APIRouter(prefix="/duels", tags=["duels"])


@router.get("/active")
async def active_duels(db=Depends(get_db), user=Depends(require_tg_user)):
    """Входящие вызовы на дуэль (где я — challenged) + исходящие."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, d.created_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name, "
        "(vc.user_id IS NOT NULL) AS challenger_is_vip, (vd.user_id IS NOT NULL) AS challenged_is_vip "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "LEFT JOIN vip_subscriptions vc ON vc.user_id = d.challenger_id AND vc.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions vd ON vd.user_id = d.challenged_id AND vd.expires_at > NOW() "
        "WHERE (d.challenger_id = ? OR d.challenged_id = ?) AND d.status = 'pending' "
        "ORDER BY d.created_at DESC",
        (user["id"], user["id"]),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


@router.get("/history")
async def duel_history(db=Depends(get_db), user=Depends(require_tg_user)):
    """История дуэлей: последние 20."""
    async with db.execute(
        "SELECT d.id, d.challenger_id, d.challenged_id, d.stake, d.status, "
        "d.winner_id, d.created_at, d.resolved_at, "
        "uc.user_tg_username AS challenger_name, ud.user_tg_username AS challenged_name, "
        "(vc.user_id IS NOT NULL) AS challenger_is_vip, (vd.user_id IS NOT NULL) AS challenged_is_vip "
        "FROM duels d "
        "LEFT JOIN users uc ON uc.user_tg_id = d.challenger_id "
        "LEFT JOIN users ud ON ud.user_tg_id = d.challenged_id "
        "LEFT JOIN vip_subscriptions vc ON vc.user_id = d.challenger_id AND vc.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions vd ON vd.user_id = d.challenged_id AND vd.expires_at > NOW() "
        "WHERE d.challenger_id = ? OR d.challenged_id = ? "
        "ORDER BY d.created_at DESC LIMIT 20",
        (user["id"], user["id"]),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


class ChallengeRequest(BaseModel):
    username: str
    stake: float
    chat_id: int


@router.post("/challenge")
async def challenge(body: ChallengeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Вызвать игрока на дуэль по username."""
    from infrastructure.repositories.zoo import get_user_pets as _get_pets

    async with db.execute(
        "SELECT user_tg_id FROM users WHERE user_tg_username = ?", (body.username,)
    ) as c:
        target = await c.fetchone()
    if not target:
        raise HTTPException(404, f"Игрок @{body.username} не найден.")
    if target[0] == user["id"]:
        raise HTTPException(400, "Нельзя вызвать самого себя.")

    # Must match the bot's selection (placement="active") — otherwise a duel
    # started from the site could fight with the player's *passive* pet
    # instead of the battle pet shown as "active" on their profile.
    my_pets = await _get_pets(db, user["id"], placement="active")
    if not my_pets:
        raise HTTPException(400, "Нет активного питомца! Назначьте его в Зоопарке.")

    # Fetch challenger's own username for notifications
    async with db.execute(
        "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (user["id"],)
    ) as c:
        challenger_row = await c.fetchone()
    challenger_name = (challenger_row[0] or f"user_{user['id']}") if challenger_row else f"user_{user['id']}"

    pet = my_pets[0]
    ok, result = await create_challenge(
        db, user["id"], target[0], body.chat_id, body.stake, pet
    )
    if not ok:
        raise HTTPException(400, str(result))
    await db.commit()

    # Notify challenged user via WebSocket (if connected)
    try:
        from FastAPI.notifications import notify as _ws_notify
        await _ws_notify(target[0], {
            "type": "duel_challenge",
            "from": challenger_name,
            "stake": body.stake,
            "duel_id": result.get("duel_id"),
            "message": f"⚔️ @{challenger_name} вызывает вас на дуэль! Ставка: {body.stake:.0f} 🪙",
        })
    except Exception:
        pass

    # Notify via Telegram DM (best effort using bot token)
    try:
        import os, httpx
        token = os.getenv("BOT_TOKEN", "")
        if token:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": target[0],
                        "text": (
                            f"⚔️ <b>Вызов на дуэль!</b>\n"
                            f"Игрок <b>@{challenger_name}</b> вызывает вас на дуэль через сайт.\n"
                            f"Ставка: <code>{body.stake:.0f} 🪙</code>\n"
                            f"Ответьте в чате: <code>бот принять</code>"
                        ),
                        "parse_mode": "HTML",
                    },
                    timeout=5.0,
                )
    except Exception:
        pass

    return {"ok": True, "duel_id": result.get("duel_id"),
            "message": f"⚔️ Вызов отправлен @{body.username}! Уведомление в Telegram."}


class DeclineRequest(BaseModel):
    duel_id: int


class AcceptRequest(BaseModel):
    duel_id: int


@router.post("/accept")
async def accept(body: AcceptRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Принять входящий вызов на дуэль. Выбирает первого активного питомца."""
    from infrastructure.repositories.zoo import get_user_pets as _get_pets
    async with db.execute(
        "SELECT id, challenger_id, challenged_id, stake FROM duels WHERE id = ? AND status = 'pending'",
        (body.duel_id,),
    ) as c:
        duel = await c.fetchone()
    if not duel or duel["challenged_id"] != user["id"]:
        raise HTTPException(404, "Вызов не найден или уже недоступен.")

    # Must match the bot's selection (placement="active") — otherwise a duel
    # accepted from the site could fight with the player's *passive* pet
    # instead of the battle pet shown as "active" on their profile.
    my_pets = await _get_pets(db, user["id"], placement="active")
    if not my_pets:
        raise HTTPException(400, "Нет активного питомца! Назначьте его в Зоопарке.")

    challenged_pet = my_pets[0]
    ok, result = await accept_duel(db, body.duel_id, challenged_pet)
    if not ok:
        raise HTTPException(400, str(result))
    await db.commit()

    # Wire achievements (same as bot's cb_duel_accept) — otherwise duels
    # accepted via the site never advance the winner's duel_wins achievement.
    try:
        from services.achievements import increment_metric as _incr_ach
        await _incr_ach(db, result["winner_id"], "duel_wins", delta=1.0)
        await db.commit()
    except Exception:
        pass

    # Notify via bot if possible
    try:
        import os, httpx
        token = os.getenv("BOT_TOKEN", "")
        if token and result.get("chat_id"):
            winner_id = result.get("winner_id")
            text = (
                f"⚔️ <b>ДУЭЛЬ ЗАВЕРШЕНА!</b>\n"
                f"{'🏆 Победитель: ' + str(winner_id) if winner_id else 'Ничья!'}\n"
                f"Ставка: {duel['stake']:.0f} 🪙"
            )
            async with httpx.AsyncClient(timeout=3) as c_:
                await c_.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": result["chat_id"], "text": text, "parse_mode": "HTML"})
    except Exception:
        pass

    return {"ok": True, "winner_id": result.get("winner_id"), "result": result}


@router.post("/decline")
async def decline(body: DeclineRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отклонить входящий вызов на дуэль."""
    async with db.execute(
        "SELECT id, challenged_id FROM duels WHERE id = ? AND status = 'pending'",
        (body.duel_id,),
    ) as c:
        duel = await c.fetchone()
    if not duel or duel["challenged_id"] != user["id"]:
        raise HTTPException(404, "Вызов не найден или уже недоступен.")

    ok = await decline_duel(db, body.duel_id)
    if not ok:
        raise HTTPException(400, "Не удалось отклонить вызов.")
    await db.commit()
    return {"ok": True}
