"""dev_console/sql.py — Сырой SQL (только разработчик)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from ._common import _require_dev

router = APIRouter()


# ── 8. Сырой SQL (escape hatch) ──────────────────────────────────────────────────
class SqlRequest(BaseModel):
    query: str


@router.post("/sql")
async def dev_sql(body: SqlRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    q = body.query.strip().rstrip(";")
    if not q:
        raise HTTPException(400, "Пустой запрос.")
    try:
        async with db.execute(q) as c:
            try:
                rows = await c.fetchall()
            except Exception:
                rows = None
        await db.commit()
    except Exception as e:
        raise HTTPException(400, f"SQL error: {e}")

    if rows is None:
        return {"ok": True, "rows": None, "count": 0}
    out = []
    for r in rows[:200]:
        out.append({k: (str(v) if v is not None else None) for k, v in dict(r).items()})
    return {"ok": True, "rows": out, "count": len(rows), "truncated": len(rows) > 200}
