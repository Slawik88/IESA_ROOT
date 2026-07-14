"""dev_console/themes.py — Theme Lab: шаблоны премиум-тем и мета тем."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from core.themes import THEMES
from infrastructure.repositories import theme_templates as theme_tpl_repo
from infrastructure.repositories import theme_meta as theme_meta_repo
from services.themes import get_effective_theme
from services.profile_render import (
    get_default_raw_template,
    get_template_variables,
    get_template_var_help,
)
from ._common import _premium_template_list, _render_theme_preview, require_console_perm, _tg_call, _theme_id_for_template

router = APIRouter()


@router.get("/theme-templates")
async def dev_theme_templates(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "themes_manage")
    overrides = await theme_tpl_repo.get_all_overrides(db)
    out = []
    for t in _premium_template_list():
        ov = overrides.get(t["template_id"])
        out.append({
            **t,
            "has_override": ov is not None,
            "updated_at": str(ov["updated_at"]) if ov else None,
        })
    return {"templates": out}


@router.get("/theme-templates/{template_id}")
async def dev_theme_template_get(template_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "themes_manage")
    default_text = get_default_raw_template(template_id)
    if default_text is None:
        raise HTTPException(404, "Неизвестный шаблон.")
    override = await theme_tpl_repo.get_override(db, template_id)
    return {
        "template_id": template_id,
        "raw_text": override if override is not None else default_text,
        "default_text": default_text,
        "has_override": override is not None,
        "variables": get_template_variables(template_id),
        "var_help": get_template_var_help(template_id),
    }


class ThemeTemplateRequest(BaseModel):
    raw_text: str


@router.post("/theme-templates/{template_id}/preview")
async def dev_theme_template_preview(template_id: str, body: ThemeTemplateRequest,
                                      db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "themes_manage")
    if get_default_raw_template(template_id) is None:
        raise HTTPException(404, "Неизвестный шаблон.")
    theme_id = _theme_id_for_template(template_id)
    if not theme_id:
        raise HTTPException(404, "Тема не найдена.")
    text = await _render_theme_preview(db, user["id"], theme_id, body.raw_text)
    return {"text": text}


@router.post("/theme-templates/{template_id}/send-test")
async def dev_theme_template_send_test(template_id: str, body: ThemeTemplateRequest,
                                        db=Depends(get_db), user=Depends(require_tg_user)):
    """Шлёт разработчику в личку с ботом РЕАЛЬНОЕ сообщение с этим шаблоном —
    100% то же, что увидит игрок (рендер Telegram-клиента, не браузера)."""
    await require_console_perm(db, user, "themes_manage")
    if get_default_raw_template(template_id) is None:
        raise HTTPException(404, "Неизвестный шаблон.")
    theme_id = _theme_id_for_template(template_id)
    if not theme_id:
        raise HTTPException(404, "Тема не найдена.")
    text = await _render_theme_preview(db, user["id"], theme_id, body.raw_text)
    r = await _tg_call("sendMessage", chat_id=user["id"], text=text, parse_mode="HTML")
    if not r.get("ok"):
        raise HTTPException(400, f"Telegram отклонил сообщение: {r.get('description') or r.get('error') or '?'}")
    return {"ok": True}


@router.post("/theme-templates/{template_id}")
async def dev_theme_template_save(template_id: str, body: ThemeTemplateRequest,
                                   db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "themes_manage")
    if get_default_raw_template(template_id) is None:
        raise HTTPException(404, "Неизвестный шаблон.")
    if not body.raw_text.strip():
        raise HTTPException(400, "Пустой шаблон.")
    await theme_tpl_repo.set_override(db, template_id, body.raw_text, user["id"])
    return {"ok": True}


@router.delete("/theme-templates/{template_id}")
async def dev_theme_template_reset(template_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "themes_manage")
    await theme_tpl_repo.delete_override(db, template_id)
    return {"ok": True}


# ── Theme metadata editor — реально применяется к покупке через services/themes.py ──
class ThemeMetaRequest(BaseModel):
    name: str | None = None
    rarity: str | None = None
    source: str | None = None
    price_mora: int | None = None
    price_diamonds: float | None = None
    price_zarniki: int | None = None
    price_dark: int | None = None
    obtainable_bp: bool | None = None
    desc: str | None = None


_VALID_RARITIES = {"common", "uncommon", "rare", "epic", "legendary", "mythic", "shadow", "zarniki", "seasonal"}


_VALID_SOURCES  = {"start", "shop_mora", "shop_diamond", "gacha_mora", "gacha_novice",
                   "gacha_standard", "gacha_premium", "gacha_diamond", "dark", "zarniki",
                   "event", "auction", "bp"}


@router.get("/theme-meta/{theme_id}")
async def dev_theme_meta_get(theme_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """Вернуть текущие метаданные темы (база из themes.py + DB-оверрайды) —
    те же значения, что реально применяются при покупке (services/themes.get_effective_theme)."""
    await require_console_perm(db, user, "themes_manage")
    if theme_id not in THEMES:
        raise HTTPException(404, "Тема не найдена.")
    effective = await get_effective_theme(db, theme_id)
    override = await theme_meta_repo.get_override(db, theme_id)
    return {
        "theme_id": theme_id,
        "name": effective.get("name", theme_id),
        "rarity": effective.get("rarity", "common"),
        "source": effective.get("source", ""),
        "price_mora": effective.get("price_mora"),
        "price_diamonds": effective.get("price_diamonds"),
        "price_zarniki": effective.get("price_zarniki"),
        "price_dark": effective.get("price_dark"),
        "obtainable_bp": effective.get("obtainable_bp", False),
        "desc": effective.get("desc", ""),
        "has_override": override is not None,
    }


@router.post("/theme-meta/{theme_id}")
async def dev_theme_meta_save(theme_id: str, body: ThemeMetaRequest,
                               db=Depends(get_db), user=Depends(require_tg_user)):
    """Сохранить метаданные темы (цены, редкость, описание) в DB — сразу применяется
    к реальной покупке в боте и на сайте (services/themes.get_effective_theme)."""
    await require_console_perm(db, user, "themes_manage")
    if theme_id not in THEMES:
        raise HTTPException(404, "Тема не найдена.")
    if body.rarity and body.rarity not in _VALID_RARITIES:
        raise HTTPException(400, f"Неверная редкость. Допустимо: {', '.join(_VALID_RARITIES)}")
    if body.source and body.source not in _VALID_SOURCES:
        raise HTTPException(400, f"Неверный источник. Допустимо: {', '.join(_VALID_SOURCES)}")
    await theme_meta_repo.set_override(
        db, theme_id,
        name=body.name, rarity=body.rarity, source=body.source,
        price_mora=body.price_mora, price_diamonds=body.price_diamonds,
        price_zarniki=body.price_zarniki, price_dark=body.price_dark,
        obtainable_bp=body.obtainable_bp, description=body.desc,
    )
    return {"ok": True}


@router.delete("/theme-meta/{theme_id}")
async def dev_theme_meta_delete(theme_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """Удалить DB-оверрайд метаданных (вернуть к значениям из themes.py)."""
    await require_console_perm(db, user, "themes_manage")
    await theme_meta_repo.delete_override(db, theme_id)
    return {"ok": True}
