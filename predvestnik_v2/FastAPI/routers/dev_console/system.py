"""dev_console/system.py — Системные ресурсы сервера."""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db, require_tg_user
from ._common import _require_dev

router = APIRouter()


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
