"""dev_console/system.py — Системные ресурсы и глобальные флаги фич."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from ._common import require_console_perm
from infrastructure.repositories import system_flags as _flags_repo
from infrastructure.repositories import dev_settings as _num_repo
from infrastructure.repositories import chat_module_audit as _module_repo
from core.chat_modules import CHAT_MODULES, CHAT_MODULE_KEYS, chat_module_default

router = APIRouter()

class FlagBody(BaseModel):
    enabled: bool


class _ModuleBody(BaseModel):
    module_key: str
    enabled: bool


@router.get("/flags")
async def dev_get_flags(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "flags_manage")
    flags = await _flags_repo.get_all(db)
    return {"flags": flags}


@router.post("/flags/{key}")
async def dev_set_flag(key: str, body: FlagBody, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "flags_manage")
    ok = await _flags_repo.set_flag(db, key, body.enabled)
    if not ok:
        raise HTTPException(404, f"Флаг '{key}' не найден.")
    return {"ok": True, "key": key, "enabled": body.enabled}


# ── Числовые дев-настройки (Growth-полиш 2026-07-13) ────────────────────────────
class NumericSettingBody(BaseModel):
    value: float


@router.get("/numeric-settings")
async def dev_get_numeric_settings(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "flags_manage")
    return {"settings": await _num_repo.get_all(db)}


@router.post("/numeric-settings/{key}")
async def dev_set_numeric_setting(
    key: str, body: NumericSettingBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    await require_console_perm(db, user, "flags_manage")
    ok = await _num_repo.set_value(db, key, body.value)
    if not ok:
        raise HTTPException(404, f"Настройка '{key}' не найдена.")
    return {"ok": True, "key": key, "value": body.value}


@router.get("/chat-modules/{chat_id}")
async def dev_get_chat_modules(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "modules_manage")
    keys = list(CHAT_MODULES)
    cols = ", ".join(
        f"COALESCE({key}, {int(chat_module_default(key))}) AS {key}" for key in keys
    )
    async with db.execute(
        f"SELECT {cols} FROM chat_settings WHERE chat_id = ?", (chat_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        modules = {key: int(chat_module_default(key)) for key in keys}
    else:
        modules = {key: int(row[key]) for key in keys}
    return {"modules": modules, "catalog": _module_repo.catalog(),
            "audit": await _module_repo.recent(db, scope="chat", chat_id=chat_id, limit=12)}


@router.post("/chat-modules/{chat_id}")
async def dev_set_chat_module(
    chat_id: int, body: _ModuleBody, db=Depends(get_db), user=Depends(require_tg_user)
):
    await require_console_perm(db, user, "modules_manage")
    if body.module_key not in CHAT_MODULE_KEYS:
        raise HTTPException(400, "Неизвестный модуль")
    result = await _module_repo.set_chat_module(
        db, chat_id=chat_id, module_key=body.module_key, enabled=body.enabled,
        actor_id=int(user["id"]), source="miniapp_console",
    )
    return {"ok": True, **result}


@router.get("/global-modules")
async def dev_get_global_modules(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "flags_manage")
    modules = {}
    for key in CHAT_MODULES:
        async with db.execute(
            "SELECT enabled,disabled_reason FROM global_module_toggles WHERE module_key=?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        modules[key] = {"enabled": bool(row["enabled"]) if row else chat_module_default(key),
                        "reason": row["disabled_reason"] if row else None}
    return {"catalog": _module_repo.catalog(), "modules": modules,
            "audit": await _module_repo.recent(db, scope="global", limit=12)}


class _GlobalModuleBody(BaseModel):
    enabled: bool
    reason: str | None = None


@router.post("/global-modules/{module_key}")
async def dev_set_global_module(
    module_key: str, body: _GlobalModuleBody,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    await require_console_perm(db, user, "flags_manage")
    if module_key not in CHAT_MODULE_KEYS:
        raise HTTPException(400, "Неизвестный модуль")
    result = await _module_repo.set_global_module(
        db, module_key=module_key, enabled=body.enabled, actor_id=int(user["id"]),
        reason=body.reason, source="miniapp_console",
    )
    return {"ok": True, **result}


# ── 5б. Системные ресурсы (исключая девелопера) ─────────────────────────────────
@router.get("/system-resources")
async def dev_system_resources(db=Depends(get_db), user=Depends(require_tg_user)):
    """Суммарное количество ресурсов в игре, без учёта аккаунта разработчика."""
    await require_console_perm(db, user, "metrics_view")
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
