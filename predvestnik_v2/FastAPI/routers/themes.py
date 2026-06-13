"""FastAPI/routers/themes.py — темы профиля: просмотр, покупка, применение."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.themes import THEMES, THEME_RARITY_META, RARITY_ORDER
from infrastructure.repositories.themes import (
    list_owned, grant_theme, set_active_theme, get_active_theme, owns_theme,
)
from infrastructure.repositories.economy import get_balance
from infrastructure.repositories import economy as eco_repo

router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("/")
async def all_themes(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все темы с флагом владения и активной темой."""
    owned = await list_owned(db, user["id"])
    active = await get_active_theme(db, user["id"])

    result = []
    for theme_id, t in THEMES.items():
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
async def buy_theme(body: BuyThemeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    theme = THEMES.get(body.theme_id)
    if not theme:
        raise HTTPException(404, "Тема не найдена.")

    if await owns_theme(db, user["id"], body.theme_id):
        raise HTTPException(400, "Тема уже есть в коллекции.")

    source = theme.get("source", "")
    price_mora     = theme.get("price_mora")
    price_diamonds = theme.get("price_diamonds")
    price_zarniki  = theme.get("price_zarniki")

    # Покупаемые в вебе: магазинные (🪙/💎) и донатные (✨). Зарники замыкают
    # донат-петлю: купил Зарники за Stars → тратишь их на премиум-тему здесь же.
    bal = await get_balance(db, user["id"])

    if source in ("shop_mora", "shop_diamond") and (price_mora or price_diamonds):
        if price_mora:
            if bal["user_balance_mora"] < price_mora:
                raise HTTPException(400, f"Нужно {price_mora} 🪙, есть {bal['user_balance_mora']:.0f}.")
            await eco_repo.add_balance(db, user["id"], mora=-price_mora, commit=False,
                                       source="theme_shop", note=body.theme_id)
        else:
            if bal["user_balance_diamonds"] < price_diamonds:
                raise HTTPException(400, f"Нужно {price_diamonds} 💎, есть {bal['user_balance_diamonds']:.1f}.")
            await eco_repo.add_balance(db, user["id"], diamonds=-price_diamonds, commit=False,
                                       source="theme_shop", note=body.theme_id)
    elif source == "zarniki" and price_zarniki:
        if bal.get("user_balance_zarniki", 0) < price_zarniki:
            raise HTTPException(400, f"Нужно {int(price_zarniki)} ✨, есть {bal.get('user_balance_zarniki', 0):.0f}. "
                                     "Пополни Зарники в разделе ✨ Премиум.")
        await eco_repo.add_balance(db, user["id"], zarniki=-price_zarniki, commit=False,
                                   source="theme_shop", note=body.theme_id)
    else:
        raise HTTPException(400, "Эта тема не продаётся напрямую. Получите её через гачу, ивент или Тёмный рынок.")

    await grant_theme(db, user["id"], body.theme_id)
    await db.commit()
    return {"ok": True, "theme_name": theme["name"]}


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
