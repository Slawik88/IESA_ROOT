"""FastAPI/routers/dev_overlay.py — БЛОК 25: dev-mod оверлей (плавающая отладочная
панель поверх обычного мини-аппа). Доступ: DEVELOPER_ID + DEVELOPER_HELPER_IDS.

Фронт: static/app.devmode.js — грузится всем как отдельный <script>, но активируется
только после 200 от /check; все данные — за гейтом require_dev_user.
"""
import os

from fastapi import APIRouter, Depends, HTTPException

from core.constants import DEVELOPER_HELPER_IDS
from FastAPI.deps import get_db, require_tg_user

router = APIRouter(prefix="/admin/dev-overlay", tags=["dev-overlay"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)


def _is_dev_user(uid: int) -> bool:
    return (DEVELOPER_ID and uid == DEVELOPER_ID) or uid in set(DEVELOPER_HELPER_IDS)


async def require_dev_user(user=Depends(require_tg_user)) -> dict:
    if not _is_dev_user(int(user["id"])):
        raise HTTPException(403, "Dev-режим доступен только разработчику и хелперам.")
    return user


@router.get("/check")
async def check(user=Depends(require_dev_user)):
    """Лёгкий пинг: 200 = показать панель, 403 = фронт молча остаётся выключенным."""
    return {"ok": True, "id": user["id"]}


@router.get("/user/{target_id}")
async def raw_user_snapshot(target_id: int, db=Depends(get_db),
                            user=Depends(require_dev_user)):
    """Сырой слепок игрока прямо из БД — без сервисной обработки/форматирования.
    Именно то, что лежит в таблицах (для поиска расхождений UI ↔ данные)."""
    out: dict = {"target_id": target_id}

    async with db.execute("SELECT * FROM users WHERE user_tg_id = ?", (target_id,)) as c:
        r = await c.fetchone()
    out["users"] = dict(r) if r else None

    async with db.execute(
        "SELECT * FROM user_chat_stats WHERE user_tg_id = ? ORDER BY chat_tg_id",
        (target_id,),
    ) as c:
        out["user_chat_stats"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM pets WHERE owner_id = ? ORDER BY id", (target_id,)
    ) as c:
        out["pets"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY item_id",
        (target_id,),
    ) as c:
        out["inventory"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM wallet_log WHERE user_id = ? ORDER BY id DESC LIMIT 15",
        (target_id,),
    ) as c:
        out["wallet_log_recent"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM achievements WHERE user_id = ? ORDER BY achievement_id",
        (target_id,),
    ) as c:
        out["achievements"] = [dict(x) for x in await c.fetchall()]

    # Глобальный стрик — sentinel chat_id = 0 (см. infrastructure/repositories/streak.py)
    async with db.execute(
        "SELECT * FROM daily_login WHERE user_id = ? AND chat_id = 0", (target_id,)
    ) as c:
        r = await c.fetchone()
    out["daily_login_global"] = dict(r) if r else None

    async with db.execute(
        "SELECT * FROM global_sanctions WHERE target_type = 'user' AND target_id = ? "
        "ORDER BY id DESC LIMIT 5",
        (target_id,),
    ) as c:
        out["global_sanctions_recent"] = [dict(x) for x in await c.fetchall()]

    return out
