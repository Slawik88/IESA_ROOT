"""FastAPI/routers/top.py — топы активности."""
from fastapi import APIRouter, Depends
from FastAPI.deps import get_db
from infrastructure.repositories.stats import get_top_messages, get_top_messages_global
from services.cosmetics import get_flex_cosmetics_batch
from services.membership import bot_tg_id, prune_ghosts

router = APIRouter(prefix="/top", tags=["top"])


async def _fmt(db, rows: list[dict], count_key: str = "msg_count") -> list[dict]:
    out = [
        {
            "position": i + 1,
            "user_id":  r["user_tg_id"],
            "username": r.get("user_tg_username") or f"ID{r['user_tg_id']}",
            "count":    r[count_key],
            "is_vip":   bool(r.get("is_vip", False)),
        }
        for i, r in enumerate(rows)
    ]
    # БЛОК21: «видимый статус» — подмешиваем ник-глоу + титул, чтобы косметика
    # светилась прямо в топе (зрители → зависть → конверсия). Один батч-запрос.
    flex = await get_flex_cosmetics_batch(db, [r["user_id"] for r in out])
    for r in out:
        f = flex.get(r["user_id"], {})
        r["glow"] = f.get("glow")
        r["title"] = f.get("title")
    return out


@router.get("/local/{chat_id}")
async def local_top(chat_id: int, db=Depends(get_db)):
    """Топ за всё время внутри одного чата."""
    rows = await get_top_messages(db, chat_id, "all_time", limit=50)
    # Бот сам — строка в user_chat_stats, Telegram видит его обычным участником
    # чата (см. bot_tg_id() в services/membership.py) — без исключения он мог
    # попасть в собственный топ активности.
    _self_id = bot_tg_id()
    if _self_id is not None:
        rows = [r for r in rows if r["user_tg_id"] != _self_id]
    # Сверка is_left с реальным членством (см. services/membership.py) —
    # тот же ghost-баг, что и в боте: без push-апдейта (бот не админ чата)
    # is_left не обновляется, и ушедший игрок годами висит в топе.
    if rows:
        left_ids = await prune_ghosts(db, chat_id, [r["user_tg_id"] for r in rows])
        if left_ids:
            rows = [r for r in rows if r["user_tg_id"] not in left_ids]
    return await _fmt(db, rows)


@router.get("/global")
async def global_top(db=Depends(get_db)):
    """Топ за всё время по всем чатам."""
    rows = await get_top_messages_global(db, limit=50)
    _self_id = bot_tg_id()
    if _self_id is not None:
        rows = [r for r in rows if r["user_tg_id"] != _self_id]
    return await _fmt(db, rows, count_key="value")
