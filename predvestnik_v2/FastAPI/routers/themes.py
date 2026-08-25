"""FastAPI/routers/themes.py — темы профиля: просмотр, покупка, применение."""
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.themes import THEMES, THEME_RARITY_META, RARITY_ORDER
from infrastructure.repositories.themes import list_owned, set_active_theme, get_active_theme, owns_theme
from services.themes import (
    WEB_DIRECT_THEME_SOURCES,
    ThemePurchaseError,
    get_all_effective_themes,
    get_effective_theme,
    purchase_direct_theme,
)

router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("/")
async def all_themes(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все темы с флагом владения и активной темой."""
    owned = await list_owned(db, user["id"])
    active = await get_active_theme(db, user["id"])
    effective = await get_all_effective_themes(db)

    result = []
    for theme_id, t in effective.items():
        rarity = t.get("rarity", "common")
        meta = THEME_RARITY_META.get(rarity, {})
        result.append({
            "theme_id":  theme_id,
            "name":      t["name"],
            "rarity":    rarity,
            "badge":     meta.get("badge", "⬜"),
            "rarity_label": meta.get("name", rarity),
            "source":    t.get("source", ""),
            "desc":      t.get("desc", ""),
            "top":       t.get("top", ""),
            "bot_line":  t.get("bot", ""),
            "accent":    t.get("accent", ""),
            "price_mora":     t.get("price_mora"),
            "price_diamonds": t.get("price_diamonds"),
            "price_dark":     t.get("price_dark"),
            "price_zarniki":  t.get("price_zarniki"),
            "owned":   theme_id in owned,
            "active":  theme_id == active,
            "gacha":   t.get("gacha"),
            "it":      t.get("it", False),       # IT-стиль (подкатегория в Зарниковой)
            "premium": rarity == "zarniki",      # донат-тема за ✨
        })

    order = {r: i for i, r in enumerate(RARITY_ORDER)}
    result.sort(key=lambda x: order.get(x["rarity"], 9))
    return result


class BuyThemeRequest(BaseModel):
    theme_id: str


@router.post("/buy")
async def buy_theme(
    body: BuyThemeRequest,
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Purchase a current direct theme once, even across retries or double taps."""
    if request_key is None or not request_key.strip() or len(request_key.strip()) > 180:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–180 символов.")
    try:
        result = await purchase_direct_theme(
            db,
            user["id"],
            body.theme_id,
            idempotency_key=request_key.strip(),
            allowed_sources=WEB_DIRECT_THEME_SOURCES,
        )
    except ThemePurchaseError as exc:
        detail = str(exc)
        status = 404 if detail == "Тема не найдена." else 400
        if "каталог закрыт" in detail:
            status = 410
        raise HTTPException(status, detail) from exc
    return {
        "ok": True,
        "theme_name": result.theme_name,
        "applied": result.applied,
        "replayed": result.replayed,
        "already_owned": result.already_owned,
    }


class EquipThemeRequest(BaseModel):
    theme_id: str


@router.post("/equip")
async def equip_theme(body: EquipThemeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    if not await owns_theme(db, user["id"], body.theme_id):
        raise HTTPException(403, "Этой темы нет в вашей коллекции.")
    await set_active_theme(db, user["id"], body.theme_id)
    return {"ok": True}



@router.get("/preview/{theme_id}")
async def theme_preview_text(theme_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """
    Return the raw profile HTML string rendered with the given theme.
    The string is identical to what the bot sends to Telegram.
    Frontend should display it with white-space: pre-wrap and innerHTML.
    """
    if theme_id not in THEMES:
        raise HTTPException(404, "Тема не найдена.")

    # Find the user's primary chat for stats context
    async with db.execute(
        "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
        "ORDER BY user_messages_count_all_time DESC LIMIT 1",
        (user["id"],),
    ) as c:
        _cr = await c.fetchone()
    chat_id = _cr[0] if _cr else 0

    from services.profile_render import build_profile_text
    text = await build_profile_text(db, user["id"], chat_id, theme_id_override=theme_id)
    return {"text": text, "theme_id": theme_id}
