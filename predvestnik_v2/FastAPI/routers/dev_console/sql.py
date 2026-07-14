"""dev_console/sql.py — Сырой SQL (только разработчик).

admin_audit A1: запросы, меняющие данные (не-SELECT), требуют подтверждения
(confirm=true вторым запросом) и журналируются в admin_grant_log — раньше опечатка
в WHERE молча портила данные без следа.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.admin_log import add_sys
from ._common import require_console_perm

router = APIRouter()


# ── 8. Сырой SQL (escape hatch) ──────────────────────────────────────────────────
class SqlRequest(BaseModel):
    query: str
    confirm: bool = False


# Только эти первые слова считаются read-only. WITH намеренно НЕ в списке:
# CTE может оканчиваться INSERT/UPDATE/DELETE — перестраховка в сторону confirm.
_READONLY_HEADS = {"select", "show", "explain", "table", "values"}


@router.post("/sql")
async def dev_sql(body: SqlRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "sql_run")
    q = body.query.strip().rstrip(";")
    if not q:
        raise HTTPException(400, "Пустой запрос.")

    head = q.split(None, 1)[0].lower()
    is_readonly = head in _READONLY_HEADS

    if not is_readonly and not body.confirm:
        # Двухшаговое подтверждение мутаций: фронт показывает предупреждение
        # и повторяет запрос с confirm=true.
        return {
            "ok": False, "needs_confirm": True,
            "notice": ("Запрос ИЗМЕНЯЕТ данные и будет записан в журнал "
                       "admin-действий. Подсказка: добавьте RETURNING *, чтобы "
                       "увидеть затронутые строки."),
        }

    try:
        async with db.execute(q) as c:
            try:
                rows = await c.fetchall()
            except Exception:
                rows = None
        if not is_readonly:
            # Журнал ДО commit — мутация и её след фиксируются вместе
            await add_sys(db, user["id"], "sql_write", q[:500])
        await db.commit()
    except Exception as e:
        raise HTTPException(400, f"SQL error: {e}")

    if rows is None:
        return {"ok": True, "rows": None, "count": 0, "logged": not is_readonly}
    out = []
    for r in rows[:200]:
        out.append({k: (str(v) if v is not None else None) for k, v in dict(r).items()})
    return {"ok": True, "rows": out, "count": len(rows),
            "truncated": len(rows) > 200, "logged": not is_readonly}
