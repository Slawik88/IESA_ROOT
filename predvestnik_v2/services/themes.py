"""
services/themes.py
Эффективные метаданные темы = core/themes.py THEMES + DB-оверрайд (если есть).
Поле оверрайда перекрывает значение из THEMES только когда оно НЕ NULL —
это единый источник правды для каталога/цены и в боте, и на сайте.
No bot.*/FastAPI.* imports.
"""
from core.themes import THEMES
from infrastructure.repositories import theme_meta as meta_repo

_PRICE_FIELDS = ("name", "rarity", "source", "price_mora", "price_diamonds",
                 "price_zarniki", "price_dark")


def _merge(base: dict, override: dict | None) -> dict:
    if not override:
        return base
    merged = dict(base)
    for f in _PRICE_FIELDS:
        if override.get(f) is not None:
            merged[f] = override[f]
    if override.get("obtainable_bp") is not None:
        merged["obtainable_bp"] = bool(override["obtainable_bp"])
    if override.get("description"):
        merged["desc"] = override["description"]
    return merged


async def get_effective_theme(db, theme_id: str) -> dict | None:
    """THEMES[theme_id] с ценой/редкостью/описанием, перекрытыми DB-оверрайдом (если есть)."""
    base = THEMES.get(theme_id)
    if not base:
        return None
    override = await meta_repo.get_override(db, theme_id)
    return _merge(base, override)


async def get_all_effective_themes(db) -> dict[str, dict]:
    """Все темы из THEMES с применёнными DB-оверрайдами — для каталога/витрины."""
    overrides = await meta_repo.get_all_overrides(db)
    return {tid: _merge(t, overrides.get(tid)) for tid, t in THEMES.items()}
