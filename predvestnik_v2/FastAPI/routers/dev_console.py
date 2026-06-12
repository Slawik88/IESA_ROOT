"""FastAPI/routers/dev_console.py — Консоль разработчика (только DEVELOPER_ID).

Всё, что может понадобиться разработчику: обзор системы, досье на любого
игрока, правка балансов/предметов, выдача VIP, управление сезонами Боевого
пропуска, начисление BP XP, рассылка по чатам и сырой SQL.

Гейт строже, чем global_rank=3: проверяется именно совпадение Telegram-ID
с DEVELOPER_ID из ENV.
"""
import asyncio
import os
import re
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import BATTLE_PASS_MAX_LEVEL, BATTLE_PASS_XP_PER_LEVEL
from core.registry import BATTLE_PASS_SEASONS, ITEMS_REGISTRY, VIP_TIERS
from infrastructure.repositories.economy import add_balance, add_item, remove_item
from services.battle_pass import get_active_season, refresh_seasons_cache
from services.roles import GLOBAL_RANKS_MAP, LOCAL_RANKS_MAP

router = APIRouter(prefix="/admin/dev", tags=["dev_console"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)

_SEASON_ID_RE = re.compile(r"^[a-z0-9_]{1,32}$")


def _require_dev(user: dict) -> None:
    if not DEVELOPER_ID or user["id"] != DEVELOPER_ID:
        raise HTTPException(403, "Консоль разработчика доступна только Разработчику.")


async def _tg_call(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 1. Обзор системы ─────────────────────────────────────────────────────────────
@router.get("/overview")
async def dev_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)

    async def _one(sql: str, args: tuple = ()) -> float:
        async with db.execute(sql, args) as c:
            row = await c.fetchone()
        return row[0] if row and row[0] is not None else 0

    users_total = await _one("SELECT COUNT(*) FROM users")
    chats_total = await _one("SELECT COUNT(*) FROM chat_settings")
    msgs_today = await _one(
        "SELECT COALESCE(SUM(message_count),0) FROM daily_user_stats "
        "WHERE date = TO_CHAR(NOW() + INTERVAL '3 hours', 'YYYY-MM-DD')")
    vips_active = await _one("SELECT COUNT(*) FROM vip_subscriptions WHERE expires_at > NOW()")
    appeals_pending = await _one("SELECT COUNT(*) FROM sanction_appeals WHERE status = 'pending'")
    sanctions_active = await _one(
        "SELECT COUNT(*) FROM global_sanctions WHERE revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW())")
    mora_total = await _one("SELECT COALESCE(SUM(user_balance_mora),0) FROM users")
    diamonds_total = await _one("SELECT COALESCE(SUM(user_balance_diamonds),0) FROM users")
    zarniki_total = await _one("SELECT COALESCE(SUM(user_balance_zarniki),0) FROM users")

    await refresh_seasons_cache(db)
    season = get_active_season()

    return {
        "users_total": int(users_total),
        "chats_total": int(chats_total),
        "messages_today": int(msgs_today),
        "vips_active": int(vips_active),
        "appeals_pending": int(appeals_pending),
        "sanctions_active": int(sanctions_active),
        "mora_total": float(mora_total),
        "diamonds_total": float(diamonds_total),
        "zarniki_total": float(zarniki_total),
        "bp_season": {"id": season["id"], "label": season["label"],
                      "ends_at": season["ends_at"]} if season else None,
    }


# ── 2. Досье на игрока ───────────────────────────────────────────────────────────
@router.get("/user")
async def dev_user_lookup(q: str = Query(..., max_length=64),
                          db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    q = q.strip().lstrip("@")
    if q.isdigit():
        where, arg = "u.user_tg_id = ?", int(q)
    else:
        where, arg = "LOWER(u.user_tg_username) = LOWER(?)", q

    async with db.execute(
        f"SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.global_rank,0) AS global_rank, "
        f"COALESCE(u.user_balance_mora,0) AS mora, COALESCE(u.user_balance_diamonds,0) AS diamonds, "
        f"COALESCE(u.user_balance_dark_mora,0) AS dark_mora, COALESCE(u.user_balance_zarniki,0) AS zarniki, "
        f"u.active_theme FROM users u WHERE {where}", (arg,)
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Пользователь не найден.")
    d = dict(row)
    uid = d["user_tg_id"]
    d["global_rank_name"] = GLOBAL_RANKS_MAP.get(d["global_rank"], "?")

    # VIP
    async with db.execute(
        "SELECT tier, expires_at, COALESCE(total_days,0) AS total_days, "
        "(expires_at > NOW()) AS active FROM vip_subscriptions WHERE user_id = ?", (uid,)
    ) as c:
        vrow = await c.fetchone()
    d["vip"] = ({"tier": vrow["tier"], "active": bool(vrow["active"]),
                 "expires_at": str(vrow["expires_at"]), "total_days": vrow["total_days"]}
                if vrow else None)

    # Battle Pass (активный сезон)
    await refresh_seasons_cache(db)
    season = get_active_season()
    d["battle_pass"] = None
    if season:
        async with db.execute(
            "SELECT xp, level FROM battle_pass_progress WHERE user_id = ? AND season_id = ?",
            (uid, season["id"]),
        ) as c:
            bp = await c.fetchone()
        if bp:
            d["battle_pass"] = {"season": season["id"], "xp": bp["xp"], "level": bp["level"]}

    # Чаты
    async with db.execute(
        "SELECT ucs.chat_tg_id, COALESCE(cs.chat_title, CAST(ucs.chat_tg_id AS TEXT)) AS chat_title, "
        "ucs.local_rank, ucs.user_level, ucs.user_messages_count_all_time, ucs.warnings, ucs.is_left "
        "FROM user_chat_stats ucs LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? ORDER BY ucs.user_messages_count_all_time DESC", (uid,)
    ) as c:
        chats = [dict(r) for r in await c.fetchall()]
    for ch in chats:
        ch["rank_name"] = LOCAL_RANKS_MAP.get(ch["local_rank"] or 0, "?")
    d["chats"] = chats

    # Активные глобальные санкции
    async with db.execute(
        "SELECT id, sanction_type, reason, expires_at FROM global_sanctions "
        "WHERE target_type = 'user' AND target_id = ? AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW())", (uid,)
    ) as c:
        sanctions = [dict(r) for r in await c.fetchall()]
    for s in sanctions:
        s["expires_at"] = str(s["expires_at"]) if s["expires_at"] else None
    d["sanctions"] = sanctions

    d["mora"] = float(d["mora"]); d["diamonds"] = float(d["diamonds"])
    d["dark_mora"] = float(d["dark_mora"]); d["zarniki"] = float(d["zarniki"])
    return d


# ── 3. Правка баланса ────────────────────────────────────────────────────────────
class BalanceRequest(BaseModel):
    user_id: int
    mora: float = 0
    diamonds: float = 0
    dark_mora: float = 0
    zarniki: float = 0


@router.post("/balance")
async def dev_balance(body: BalanceRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if not any((body.mora, body.diamonds, body.dark_mora, body.zarniki)):
        raise HTTPException(400, "Все суммы нулевые.")
    if body.mora or body.diamonds or body.zarniki:
        await add_balance(db, body.user_id, mora=body.mora, diamonds=body.diamonds,
                          zarniki=body.zarniki, source="dev_console", note=f"by_{user['id']}")
    if body.dark_mora:
        # add_balance не умеет тёмную мору — прямой UPDATE (как dark_mora-роутер)
        await db.execute(
            "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
        await db.execute(
            "UPDATE users SET user_balance_dark_mora = COALESCE(user_balance_dark_mora,0) + ? "
            "WHERE user_tg_id = ?", (body.dark_mora, body.user_id))
    await db.commit()
    return {"ok": True}


# ── 4. Выдать/забрать предмет ────────────────────────────────────────────────────
class GiveItemRequest(BaseModel):
    user_id: int
    item_id: str
    qty: int = 1


@router.post("/give-item")
async def dev_give_item(body: GiveItemRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if body.item_id not in ITEMS_REGISTRY:
        raise HTTPException(400, f"Неизвестный item_id: {body.item_id}")
    if body.qty == 0:
        raise HTTPException(400, "qty не может быть 0.")
    if body.qty > 0:
        await add_item(db, body.user_id, body.item_id, body.qty)
    else:
        ok = await remove_item(db, body.user_id, body.item_id, -body.qty, commit=False)
        if not ok:
            raise HTTPException(400, "У игрока меньше предметов, чем вы забираете.")
    await db.commit()
    name = ITEMS_REGISTRY[body.item_id].get("name", body.item_id)
    return {"ok": True, "item_name": name}


@router.get("/items")
async def dev_items(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    return {"items": [{"item_id": iid, "name": info.get("name", iid)}
                      for iid, info in ITEMS_REGISTRY.items()]}


# ── 5. Выдать VIP (бесплатно, без списания зарников) ─────────────────────────────
class GiveVipRequest(BaseModel):
    user_id: int
    tier: str
    days: int


@router.post("/give-vip")
async def dev_give_vip(body: GiveVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if body.tier not in VIP_TIERS:
        raise HTTPException(400, "Неизвестный тариф.")
    if not 1 <= body.days <= 3650:
        raise HTTPException(400, "days: 1..3650.")
    await db.execute(
        "INSERT INTO vip_subscriptions (user_id, tier, started_at, expires_at, expiry_notified, total_days) "
        "VALUES (?, ?, NOW(), NOW() + make_interval(days => ?), FALSE, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "tier = EXCLUDED.tier, "
        "started_at = CASE WHEN vip_subscriptions.expires_at > NOW() "
        "THEN vip_subscriptions.started_at ELSE NOW() END, "
        "expires_at = CASE WHEN vip_subscriptions.expires_at > NOW() "
        "THEN vip_subscriptions.expires_at + make_interval(days => ?) "
        "ELSE NOW() + make_interval(days => ?) END, "
        "expiry_notified = FALSE, "
        "total_days = COALESCE(vip_subscriptions.total_days, 0) + ?",
        (body.user_id, body.tier, body.days, body.days, body.days, body.days, body.days),
    )
    await db.commit()
    label = VIP_TIERS[body.tier]["label"]
    await _tg_call("sendMessage", chat_id=body.user_id, parse_mode="HTML",
                   text=f"🎁 Вам выдан <b>{label}</b> на {body.days} дн.! Загляни: «бот вип».")
    return {"ok": True, "label": label}


# ── 6. Battle Pass: XP и сезоны ──────────────────────────────────────────────────
class BpXpRequest(BaseModel):
    user_id: int
    xp: int


@router.post("/bp/xp")
async def dev_bp_xp(body: BpXpRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    await refresh_seasons_cache(db)
    season = get_active_season()
    if not season:
        raise HTTPException(400, "Нет активного сезона.")
    if body.xp == 0:
        raise HTTPException(400, "xp не может быть 0.")

    await db.execute(
        "INSERT INTO battle_pass_progress (user_id, season_id) VALUES (?, ?) "
        "ON CONFLICT (user_id, season_id) DO NOTHING",
        (body.user_id, season["id"]),
    )
    await db.execute(
        "UPDATE battle_pass_progress SET xp = GREATEST(0, xp + ?) "
        "WHERE user_id = ? AND season_id = ?",
        (body.xp, body.user_id, season["id"]),
    )
    async with db.execute(
        "SELECT xp FROM battle_pass_progress WHERE user_id = ? AND season_id = ?",
        (body.user_id, season["id"]),
    ) as c:
        row = await c.fetchone()
    new_xp = row["xp"] if row else 0
    new_level = min(BATTLE_PASS_MAX_LEVEL, 1 + new_xp // BATTLE_PASS_XP_PER_LEVEL)
    await db.execute(
        "UPDATE battle_pass_progress SET level = ? WHERE user_id = ? AND season_id = ?",
        (new_level, body.user_id, season["id"]),
    )
    await db.commit()
    return {"ok": True, "xp": new_xp, "level": new_level}


@router.get("/bp/seasons")
async def dev_bp_seasons(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    async with db.execute(
        "SELECT id, label, starts_at, ends_at, COALESCE(max_level,50) AS max_level "
        "FROM battle_pass_seasons ORDER BY starts_at"
    ) as c:
        db_rows = {r["id"]: dict(r) for r in await c.fetchall()}

    await refresh_seasons_cache(db)
    active = get_active_season()
    active_id = active["id"] if active else None

    out = []
    for sid, s in BATTLE_PASS_SEASONS.items():
        if sid in db_rows:
            continue  # перекрыт БД-версией
        out.append({"id": sid, "label": s["label"], "starts_at": s["starts_at"],
                    "ends_at": s["ends_at"], "max_level": s.get("max_level", 50),
                    "source": "registry", "active": sid == active_id})
    for sid, s in db_rows.items():
        out.append({**s, "source": "db", "active": sid == active_id})
    out.sort(key=lambda x: x["starts_at"])
    return {"seasons": out}


class SeasonRequest(BaseModel):
    id: str
    label: str
    starts_at: str   # YYYY-MM-DD
    ends_at: str
    max_level: int = 50


@router.post("/bp/seasons")
async def dev_bp_season_upsert(body: SeasonRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if not _SEASON_ID_RE.match(body.id):
        raise HTTPException(400, "id: латиница/цифры/_, до 32 символов.")
    try:
        s = datetime.strptime(body.starts_at, "%Y-%m-%d")
        e = datetime.strptime(body.ends_at, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Даты — в формате YYYY-MM-DD.")
    if e <= s:
        raise HTTPException(400, "ends_at должен быть позже starts_at.")
    if not body.label.strip():
        raise HTTPException(400, "label пустой.")
    if not 1 <= body.max_level <= BATTLE_PASS_MAX_LEVEL:
        raise HTTPException(400, f"max_level: 1..{BATTLE_PASS_MAX_LEVEL}.")

    await db.execute(
        "INSERT INTO battle_pass_seasons (id, label, starts_at, ends_at, max_level) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label, "
        "starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, "
        "max_level = EXCLUDED.max_level",
        (body.id, body.label.strip(), body.starts_at, body.ends_at, body.max_level),
    )
    await db.commit()
    await refresh_seasons_cache(db)
    return {"ok": True}


@router.delete("/bp/seasons/{season_id}")
async def dev_bp_season_delete(season_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    async with db.execute(
        "DELETE FROM battle_pass_seasons WHERE id = ? RETURNING id", (season_id,)
    ) as c:
        row = await c.fetchone()
    await db.commit()
    await refresh_seasons_cache(db)
    if not row:
        raise HTTPException(404, "Сезон не найден в БД (registry-сезоны удалить нельзя — только перекрыть).")
    return {"ok": True}


# ── 7. Рассылка по всем чатам ────────────────────────────────────────────────────
class BroadcastRequest(BaseModel):
    text: str


@router.post("/broadcast")
async def dev_broadcast(body: BroadcastRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустой текст.")
    async with db.execute("SELECT chat_id FROM chat_settings") as c:
        chat_ids = [r[0] for r in await c.fetchall()]
    sent = failed = 0
    for cid in chat_ids:
        r = await _tg_call("sendMessage", chat_id=cid, text=text, parse_mode="HTML")
        if r.get("ok"):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return {"ok": True, "sent": sent, "failed": failed, "total": len(chat_ids)}


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
