"""dev_console/system.py — Системные ресурсы и глобальные флаги фич."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from ._common import _require_dev
from infrastructure.repositories import system_flags as _flags_repo

router = APIRouter()

_CHAT_MODULES = [
    "module_shop", "module_gacha", "module_expeditions", "module_auction",
    "module_games", "module_exchange", "module_quests", "module_zoo",
    "module_warps", "module_daily_deal",
]


class FlagBody(BaseModel):
    enabled: bool


class _ModuleBody(BaseModel):
    module_key: str
    enabled: bool


@router.get("/flags")
async def dev_get_flags(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    flags = await _flags_repo.get_all(db)
    return {"flags": flags}


@router.post("/flags/{key}")
async def dev_set_flag(key: str, body: FlagBody, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    ok = await _flags_repo.set_flag(db, key, body.enabled)
    if not ok:
        raise HTTPException(404, f"Флаг '{key}' не найден.")
    return {"ok": True, "key": key, "enabled": body.enabled}


@router.get("/chat-modules/{chat_id}")
async def dev_get_chat_modules(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    cols = ", ".join(f"COALESCE({m}, 1)" for m in _CHAT_MODULES)
    async with db.execute(
        f"SELECT {cols} FROM chat_settings WHERE chat_id = ?", (chat_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return {"modules": {m: 1 for m in _CHAT_MODULES}}
    return {"modules": {m: row[i] for i, m in enumerate(_CHAT_MODULES)}}


@router.post("/chat-modules/{chat_id}")
async def dev_set_chat_module(
    chat_id: int, body: _ModuleBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    _require_dev(user)
    if body.module_key not in _CHAT_MODULES:
        raise HTTPException(400, "Неизвестный модуль")
    val = 1 if body.enabled else 0
    await db.execute(
        "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING",
        (chat_id,),
    )
    await db.execute(
        f"UPDATE chat_settings SET {body.module_key} = ? WHERE chat_id = ?",
        (val, chat_id),
    )
    await db.commit()
    return {"ok": True}


# ── 5б. Системные ресурсы (исключая девелопера) ─────────────────────────────────
@router.get("/system-resources")
async def dev_system_resources(db=Depends(get_db), user=Depends(require_tg_user)):
    """Суммарное количество ресурсов в игре, без учёта аккаунта разработчика."""
    _require_dev(user)
    dev_id = user["id"]

    async def _sum(col: str) -> float:
        async with db.execute(
            f"SELECT COALESCE(SUM({col}), 0) FROM users WHERE user_tg_id != ?", (dev_id,)
        ) as c:
            return float((await c.fetchone())[0])

    async def _inv_sum(item_id: str) -> int:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM inventory "
            "WHERE item_id = ? AND user_id != ?", (item_id, dev_id)
        ) as c:
            return int((await c.fetchone())[0])

    mora = await _sum("user_balance_mora")
    diamonds = await _sum("user_balance_diamonds")
    dark_mora = await _sum("COALESCE(user_balance_dark_mora, 0)")
    zarniki = await _sum("COALESCE(user_balance_zarniki, 0)")

    # Топ предметов по количеству
    async with db.execute(
        "SELECT item_id, SUM(quantity) AS total FROM inventory WHERE user_id != ? "
        "GROUP BY item_id ORDER BY total DESC LIMIT 20", (dev_id,)
    ) as c:
        top_items = [{"item_id": r[0], "total": r[1]} for r in await c.fetchall()]

    async with db.execute(
        "SELECT COUNT(*) FROM users WHERE user_tg_id != ?", (dev_id,)
    ) as c:
        player_count = (await c.fetchone())[0]

    return {
        "player_count": player_count,
        "mora": mora,
        "diamonds": diamonds,
        "dark_mora": dark_mora,
        "zarniki": zarniki,
        "top_items": top_items,
    }
