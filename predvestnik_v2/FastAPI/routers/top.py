"""FastAPI/routers/top.py — топы активности."""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db
from infrastructure.repositories.stats import get_top_messages, get_top_messages_global

router = APIRouter(prefix="/top", tags=["top"])


def _fmt(rows: list[dict], count_key: str = "msg_count") -> list[dict]:
    return [
        {
            "position": i + 1,
            "user_id":  r["user_tg_id"],
            "username": r.get("user_tg_username") or f"ID{r['user_tg_id']}",
            "count":    r[count_key],
            "is_vip":   bool(r.get("is_vip", False)),
        }
        for i, r in enumerate(rows)
    ]


@router.get("/local/{chat_id}")
async def local_top(chat_id: int, db=Depends(get_db)):
    """Топ за всё время внутри одного чата."""
    rows = await get_top_messages(db, chat_id, "all_time", limit=50)
    return _fmt(rows)


@router.get("/global")
async def global_top(db=Depends(get_db)):
    """Топ за всё время по всем чатам."""
    rows = await get_top_messages_global(db, limit=50)
    return _fmt(rows, count_key="value")
