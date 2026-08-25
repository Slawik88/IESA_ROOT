"""FastAPI/routers/dev_overlay.py — БЛОК 25: dev-mod оверлей (плавающая отладочная
панель поверх обычного мини-аппа). Доступ: DEVELOPER_ID + DEVELOPER_HELPER_IDS.

Фронт: static/app.devmode.js — грузится всем как отдельный <script>, но активируется
только после 200 от /check; все данные — за гейтом require_dev_user.
"""
import os

from fastapi import APIRouter, Depends, HTTPException

from core.constants import DEVELOPER_HELPER_IDS
from FastAPI.deps import get_db, require_tg_user

router = APIRouter(prefix="/admin/dev-overlay", tags=["dev-overlay"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)


def _is_dev_user(uid: int) -> bool:
    return (DEVELOPER_ID and uid == DEVELOPER_ID) or uid in set(DEVELOPER_HELPER_IDS)


async def require_dev_user(user=Depends(require_tg_user)) -> dict:
    if not _is_dev_user(int(user["id"])):
        raise HTTPException(403, "Dev-режим доступен только разработчику и хелперам.")
    return user


@router.get("/check")
async def check(user=Depends(require_dev_user)):
    """Лёгкий пинг: 200 = показать панель, 403 = фронт молча остаётся выключенным."""
    return {"ok": True, "id": user["id"]}


@router.get("/user/{target_id}")
async def raw_user_snapshot(target_id: int, db=Depends(get_db),
                            user=Depends(require_dev_user)):
    """Сырой слепок игрока прямо из БД — без сервисной обработки/форматирования.
    Именно то, что лежит в таблицах (для поиска расхождений UI ↔ данные)."""
    out: dict = {"target_id": target_id}

    async with db.execute("SELECT * FROM users WHERE user_tg_id = ?", (target_id,)) as c:
        r = await c.fetchone()
    out["users"] = dict(r) if r else None

    async with db.execute(
        "SELECT * FROM user_chat_stats WHERE user_tg_id = ? ORDER BY chat_tg_id",
        (target_id,),
    ) as c:
        out["user_chat_stats"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM pets WHERE owner_id = ? ORDER BY id", (target_id,)
    ) as c:
        out["pets"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM inventory WHERE user_id = ? AND quantity > 0 ORDER BY item_id",
        (target_id,),
    ) as c:
        out["inventory"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM wallet_log WHERE user_id = ? ORDER BY id DESC LIMIT 15",
        (target_id,),
    ) as c:
        out["wallet_log_recent"] = [dict(x) for x in await c.fetchall()]

    async with db.execute(
        "SELECT * FROM achievements WHERE user_id = ? ORDER BY achievement_id",
        (target_id,),
    ) as c:
        out["achievements"] = [dict(x) for x in await c.fetchall()]

    # Глобальный стрик — sentinel chat_id = 0 (см. infrastructure/repositories/streak.py)
    async with db.execute(
        "SELECT * FROM daily_login WHERE user_id = ? AND chat_id = 0", (target_id,)
    ) as c:
        r = await c.fetchone()
    out["daily_login_global"] = dict(r) if r else None

    async with db.execute(
        "SELECT * FROM global_sanctions WHERE target_type = 'user' AND target_id = ? "
        "ORDER BY id DESC LIMIT 5",
        (target_id,),
    ) as c:
        out["global_sanctions_recent"] = [dict(x) for x in await c.fetchall()]

    return out


@router.get("/registry")
async def full_registry(user=Depends(require_dev_user)):
    """Справочник всех игровых сущностей с ID для быстрого
    поиска айдишников (конструктор БП, промокоды, выдача предметов, SQL и т.д.).
    Плоский список {id, name, cat, extra} — фронт группирует и ищет в реальном времени."""
    from core.registry import (ITEMS_REGISTRY, PET_SPECIES, RELICS, SHADOW_RELICS,
                               PARTNER_GIFTS, CRAFT_RECIPES)
    from core.cosmetics import COSMETICS, WELCOME_ANIMATIONS
    from core.constants import COSMETIC_CHESTS
    from core.themes import THEMES

    out: list[dict] = []

    _CAT_RU = {"material": "материал", "chest": "сундук-токен", "spin_token": "жетон",
               "food": "еда", "booster": "бустер", "utility": "утилита", "donate": "донат"}
    for iid, it in ITEMS_REGISTRY.items():
        out.append({"id": iid, "name": it.get("name", iid), "cat": "🎒 Предметы",
                    "extra": _CAT_RU.get(it.get("category", ""), it.get("category", ""))})

    for pid, p in PET_SPECIES.items():
        out.append({"id": pid, "name": p.get("name", pid), "cat": "🐾 Питомцы",
                    "extra": p.get("rarity", "")})

    for rid, r in RELICS.items():
        price = " + ".join(f"{v:g} {k}" for k, v in (r.get("price") or {}).items())
        out.append({"id": rid, "name": r.get("name", rid), "cat": "🗿 Реликвии",
                    "extra": f"{r.get('rarity','')} · {price} · +{r.get('exp_mora_pct',0)*100:g}% походы"})

    for rid, r in SHADOW_RELICS.items():
        out.append({"id": rid, "name": r.get("name", rid), "cat": "🕴 Теневые реликвии",
                    "extra": f"{r.get('price_dark',0):g} 🌑 · +{r.get('gates_dark_pct',0)*100:g}% Врата"})

    for cid, c in COSMETICS.items():
        price = (c.get("price") or [{}])[0].get("zarniki", 0)
        out.append({"id": cid, "name": c.get("name", cid), "cat": "🎨 Косметика",
                    "extra": f"{c.get('slot','')} · {c.get('rarity','')} · {price}✨"})

    for wid, w in WELCOME_ANIMATIONS.items():
        out.append({"id": wid, "name": w.get("name", wid) if isinstance(w, dict) else str(w),
                    "cat": "🎬 Приветствия", "extra": "VIP-прелоадер"})

    for tid, t in THEMES.items():
        price = (f"{t.get('price_mora'):g}🪙" if t.get("price_mora") else
                 f"{t.get('price_diamonds'):g}💎" if t.get("price_diamonds") else
                 f"{t.get('price_zarniki'):g}✨" if t.get("price_zarniki") else
                 f"{t.get('price_dark'):g}🌑" if t.get("price_dark") else "—")
        out.append({"id": tid, "name": t.get("name", tid), "cat": "🖼 Темы профиля",
                    "extra": f"{t.get('rarity','')} · {t.get('source','')} · {price}"})

    for gid, g in PARTNER_GIFTS.items():
        price = (f"{g.get('price_mora'):g}🪙" if g.get("price_mora") else
                 f"{g.get('price_diamonds'):g}💎" if g.get("price_diamonds") else
                 f"{g.get('price_zarniki'):g}✨" if g.get("price_zarniki") else "—")
        out.append({"id": gid, "name": g.get("name", gid), "cat": "💝 Подарки партнёру",
                    "extra": f"{g.get('kind','')} · {price}"})

    for chid, ch in COSMETIC_CHESTS.items():
        out.append({"id": chid, "name": ch.get("name", chid), "cat": "🎁 Сундуки",
                    "extra": f"{ch.get('zarniki',0)}✨"})

    for rid, r in CRAFT_RECIPES.items():
        out.append({"id": rid, "name": r.get("name", rid), "cat": "⚗️ Крафт-рецепты",
                    "extra": f"→ {r.get('result_item','')} ×{r.get('result_qty',1)}"})

    for cur_id, cur_name, col in (
        ("mora", "🪙 Мора", "users.user_balance_mora"),
        ("diamonds", "💎 Алмазы", "users.user_balance_diamonds"),
        ("zarniki", "✨ Зарники", "users.user_balance_zarniki"),
        ("dark_mora", "🌑 Тёмная Мора", "users.user_balance_dark_mora"),
        ("clan_coins", "🎖 Клан-монеты (легаси)", "clan_members.clan_coins"),
        ("treasury_shards", "🔷 Казна клана", "clans.treasury_shards"),
    ):
        out.append({"id": cur_id, "name": cur_name, "cat": "💰 Валюты", "extra": col})

    return {"entries": out, "total": len(out)}
