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
from core.registry import BATTLE_PASS_SEASONS, BATTLE_PASS_REWARDS, ITEMS_REGISTRY, VIP_TIERS
from core.themes import THEMES
from infrastructure.repositories import theme_templates as theme_tpl_repo
from infrastructure.repositories import theme_meta as theme_meta_repo
from infrastructure.repositories.economy import (
    add_balance, add_item, remove_item, get_item_quantity, get_balance,
)
from infrastructure.repositories import admin_log
from services.battle_pass import get_active_season, refresh_seasons_cache
from services.themes import get_effective_theme
from services.profile_render import (
    build_profile_text,
    get_default_raw_template,
    get_template_variables,
)
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

    # Инвентарь — для визуального инвентаря в карточке игрока (БЛОК 4.1)
    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND quantity > 0 "
        "ORDER BY item_id", (uid,)
    ) as c:
        inv = [dict(r) for r in await c.fetchall()]
    for it in inv:
        it["name"] = ITEMS_REGISTRY.get(it["item_id"], {}).get("name", it["item_id"])
    d["inventory"] = inv

    d["mora"] = float(d["mora"]); d["diamonds"] = float(d["diamonds"])
    d["dark_mora"] = float(d["dark_mora"]); d["zarniki"] = float(d["zarniki"])
    return d


async def _send_admin_gift(db, user_id: int, gifts: list[dict], reason: str = "") -> None:
    """Доставить «подарок от Администрации» (БЛОК 3.4): WS если игрок онлайн, иначе
    сохранить в web_notifications — коробка покажется при входе на сайт.
    gifts: [{"label": str, "amount": number}]. Только положительные начисления."""
    if not gifts:
        return
    payload = {"type": "admin_gift", "reason": (reason or "").strip(), "gifts": gifts}
    try:
        from FastAPI.notifications import notify as _ws_notify
        delivered = await _ws_notify(user_id, payload)
    except Exception:
        delivered = False
    if not delivered:
        try:
            from infrastructure.repositories import web_notifications as _wn
            await _wn.add(db, user_id, payload)
        except Exception:
            pass


# ── 3. Правка баланса ────────────────────────────────────────────────────────────
class BalanceRequest(BaseModel):
    user_id: int
    mora: float = 0
    diamonds: float = 0
    dark_mora: float = 0
    zarniki: float = 0
    reason: Optional[str] = None   # текст для коробки-подарка (БЛОК 3.4)


@router.post("/balance")
async def dev_balance(body: BalanceRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if not any((body.mora, body.diamonds, body.dark_mora, body.zarniki)):
        raise HTTPException(400, "Все суммы нулевые.")

    # Баланс «до» — для журнала (БЛОК 4.2)
    bal = await get_balance(db, body.user_id)
    before = {
        "mora":     float(bal["user_balance_mora"] or 0),
        "diamonds": float(bal["user_balance_diamonds"] or 0),
        "zarniki":  float(bal["user_balance_zarniki"] or 0),
    }
    async with db.execute(
        "SELECT COALESCE(user_balance_dark_mora, 0) FROM users WHERE user_tg_id = ?",
        (body.user_id,),
    ) as c:
        _dk = await c.fetchone()
    before["dark_mora"] = float(_dk[0]) if _dk else 0.0

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

    # Журнал: по записи на каждую затронутую валюту (баланс до/после)
    _labels = {"mora": "🪙 Мора", "diamonds": "💎 Алмазы",
               "dark_mora": "🌑 Тёмная Мора", "zarniki": "✨ Зарники"}
    for cur in ("mora", "diamonds", "dark_mora", "zarniki"):
        delta = getattr(body, cur)
        if delta:
            await admin_log.add(db, user["id"], body.user_id, "balance", _labels[cur],
                                float(delta), body.reason or "",
                                before[cur], before[cur] + float(delta))

    # Коробка-подарок только за положительные начисления (списание не «дарим»).
    gifts = []
    if body.mora > 0:      gifts.append({"label": "🪙 Мора",        "amount": body.mora})
    if body.diamonds > 0:  gifts.append({"label": "💎 Алмазы",      "amount": body.diamonds})
    if body.dark_mora > 0: gifts.append({"label": "🌑 Тёмная Мора", "amount": body.dark_mora})
    if body.zarniki > 0:   gifts.append({"label": "✨ Зарники",      "amount": body.zarniki})
    if gifts:
        await _send_admin_gift(db, body.user_id, gifts, body.reason or "")
    await db.commit()
    return {"ok": True}


# ── 4. Выдать/забрать предмет ────────────────────────────────────────────────────
class GiveItemRequest(BaseModel):
    user_id: int
    item_id: str
    qty: int = 1
    reason: Optional[str] = None   # текст для коробки-подарка (БЛОК 3.4)


@router.post("/give-item")
async def dev_give_item(body: GiveItemRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    if body.item_id not in ITEMS_REGISTRY:
        raise HTTPException(400, f"Неизвестный item_id: {body.item_id}")
    if body.qty == 0:
        raise HTTPException(400, "qty не может быть 0.")
    name = ITEMS_REGISTRY[body.item_id].get("name", body.item_id)
    qty_before = await get_item_quantity(db, body.user_id, body.item_id)
    if body.qty > 0:
        await add_item(db, body.user_id, body.item_id, body.qty)
        await _send_admin_gift(db, body.user_id,
                               [{"label": f"📦 {name}", "amount": body.qty}], body.reason or "")
    else:
        ok = await remove_item(db, body.user_id, body.item_id, -body.qty, commit=False)
        if not ok:
            raise HTTPException(400, "У игрока меньше предметов, чем вы забираете.")
    # Журнал (БЛОК 4.2): что выдал/забрал, причина, кол-во до/после
    await admin_log.add(db, user["id"], body.user_id, "item", name, float(body.qty),
                        body.reason or "", float(qty_before), float(qty_before + body.qty))
    await db.commit()
    return {"ok": True, "item_name": name}


@router.get("/items")
async def dev_items(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
    return {"items": [{"item_id": iid, "name": info.get("name", iid)}
                      for iid, info in ITEMS_REGISTRY.items()]}


@router.get("/admin-log")
async def dev_admin_log(db=Depends(get_db), user=Depends(require_tg_user)):
    """Журнал выдач/изъятий дев-консоли (БЛОК 4.2): кто, кому, что, причина, до/после."""
    _require_dev(user)
    return {"log": await admin_log.recent(db, 50)}


@router.get("/chats")
async def dev_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    """Список чатов для дропдауна «чат → юзер» в карточке игрока (БЛОК 4.1)."""
    _require_dev(user)
    async with db.execute(
        "SELECT chat_id, COALESCE(chat_title, CAST(chat_id AS TEXT)) AS title "
        "FROM chat_settings ORDER BY chat_title LIMIT 200"
    ) as c:
        return {"chats": [dict(r) for r in await c.fetchall()]}


@router.get("/chat-members")
async def dev_chat_members(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Участники чата (для дропдауна «чат → юзер»), активные первыми."""
    _require_dev(user)
    async with db.execute(
        "SELECT ucs.user_tg_id, "
        "COALESCE(u.user_tg_username, CAST(ucs.user_tg_id AS TEXT)) AS username, "
        "ucs.user_level, ucs.user_messages_count_all_time AS msgs "
        "FROM user_chat_stats ucs LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
        "WHERE ucs.chat_tg_id = ? AND COALESCE(ucs.is_left, 0) = 0 "
        "ORDER BY ucs.user_messages_count_all_time DESC LIMIT 200",
        (chat_id,),
    ) as c:
        return {"members": [dict(r) for r in await c.fetchall()]}


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
    # vip_subscriptions.user_id REFERENCES users(user_tg_id) — гарантируем строку,
    # иначе FK-violation на юзере, который ещё не писал боту (как в dev_balance).
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
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


@router.post("/revoke-vip")
async def dev_revoke_vip(body: dict, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отозвать VIP у пользователя (expires_at = NOW(), он сразу теряет статус)."""
    _require_dev(user)
    uid = int(body.get("user_id", 0))
    if not uid:
        raise HTTPException(400, "user_id обязателен.")
    async with db.execute(
        "UPDATE vip_subscriptions SET expires_at = NOW(), expiry_notified = TRUE "
        "WHERE user_id = ? AND expires_at > NOW() RETURNING tier",
        (uid,),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(400, "Активного VIP не найдено.")
    await db.commit()
    await _tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                   text="⚠️ Ваш VIP-статус был отозван администратором.")
    return {"ok": True, "revoked_tier": row[0]}


class SetVipRequest(BaseModel):
    user_id: int
    tier: str
    days: int


@router.post("/set-vip")
async def dev_set_vip(body: SetVipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Принудительно заменить текущий VIP на новый тариф и срок.
    Предыдущий VIP (бонусы, срок) сгорают; начисляется gift нового тарифа."""
    _require_dev(user)
    if body.tier not in VIP_TIERS:
        raise HTTPException(400, "Неизвестный тариф.")
    if not 1 <= body.days <= 3650:
        raise HTTPException(400, "days: 1..3650.")

    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
    # Полностью заменяем — сбрасываем started_at и expires_at
    await db.execute(
        "INSERT INTO vip_subscriptions (user_id, tier, started_at, expires_at, expiry_notified, total_days) "
        "VALUES (?, ?, NOW(), NOW() + make_interval(days => ?), FALSE, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "tier = EXCLUDED.tier, "
        "started_at = NOW(), "
        "expires_at = NOW() + make_interval(days => ?), "
        "expiry_notified = FALSE, "
        "total_days = COALESCE(vip_subscriptions.total_days, 0) + ?",
        (body.user_id, body.tier, body.days, body.days, body.days, body.days),
    )
    # Начисляем gift нового тарифа
    info = VIP_TIERS[body.tier]
    gift = info["gift"]
    if gift.get("mora"):
        await db.execute(
            "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
            (gift["mora"], body.user_id),
        )
    if gift.get("diamonds"):
        await db.execute(
            "UPDATE users SET user_balance_diamonds = user_balance_diamonds + ? WHERE user_tg_id = ?",
            (gift["diamonds"], body.user_id),
        )
    for item_id, qty in gift.get("items", ()):
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (body.user_id, item_id, qty, qty),
        )
    await db.commit()
    label = info["label"]
    await _tg_call("sendMessage", chat_id=body.user_id, parse_mode="HTML",
                   text=f"🔄 Ваш VIP переключён на <b>{label}</b> на {body.days} дн. + бонус пакета!")
    return {"ok": True, "label": label}


# ── 5б. Системные ресурсы (исключая девелопера) ─────────────────────────────────
@router.get("/system-resources")
async def dev_system_resources(db=Depends(get_db), user=Depends(require_tg_user)):
    """Суммарное количество ресурсов в игре, без учёта аккаунта разработчика."""
    _require_dev(user)
    dev_id = user["id"]

    async def _sum(col: str) -> float:
        async with db.execute(
            f"SELECT COALESCE(SUM({col}), 0) FROM users WHERE user_tg_id != ?", (dev_id,)
        ) as c:
            return float((await c.fetchone())[0])

    async def _inv_sum(item_id: str) -> int:
        async with db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM inventory "
            "WHERE item_id = ? AND user_id != ?", (item_id, dev_id)
        ) as c:
            return int((await c.fetchone())[0])

    mora = await _sum("user_balance_mora")
    diamonds = await _sum("user_balance_diamonds")
    dark_mora = await _sum("COALESCE(user_balance_dark_mora, 0)")
    zarniki = await _sum("COALESCE(user_balance_zarniki, 0)")

    # Топ предметов по количеству
    async with db.execute(
        "SELECT item_id, SUM(quantity) AS total FROM inventory WHERE user_id != ? "
        "GROUP BY item_id ORDER BY total DESC LIMIT 20", (dev_id,)
    ) as c:
        top_items = [{"item_id": r[0], "total": r[1]} for r in await c.fetchall()]

    async with db.execute(
        "SELECT COUNT(*) FROM users WHERE user_tg_id != ?", (dev_id,)
    ) as c:
        player_count = (await c.fetchone())[0]

    return {
        "player_count": player_count,
        "mora": mora,
        "diamonds": diamonds,
        "dark_mora": dark_mora,
        "zarniki": zarniki,
        "top_items": top_items,
    }


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

    # battle_pass_progress.user_id REFERENCES users(user_tg_id) — гарантируем строку,
    # иначе FK-violation на юзере, который ещё не писал боту (как в dev_balance).
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
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


# ── 6б. Управление наградами Боевого пропуска ────────────────────────────────────

@router.get("/bp/rewards")
async def dev_bp_rewards(db=Depends(get_db), user=Depends(require_tg_user)):
    """Все награды БП (registry + DB-переопределения). DB побеждает при совпадении."""
    import json as _json
    _require_dev(user)
    await refresh_seasons_cache(db)
    season = get_active_season()
    season_id = season["id"] if season else None

    # DB overrides for active season
    db_overrides: dict[tuple, dict] = {}
    if season_id:
        async with db.execute(
            "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
            "FROM battle_pass_reward_overrides WHERE season_id = ?",
            (season_id,),
        ) as c:
            for row in await c.fetchall():
                entry = {
                    "mora": row[2] or 0,
                    "diamonds": row[3] or 0,
                    "items": _json.loads(row[4] or "[]"),
                    "theme": row[5],
                }
                if row[6]:
                    try:
                        opts = _json.loads(row[6])
                        if isinstance(opts, list) and len(opts) >= 2:
                            entry["options"] = opts
                    except Exception:
                        pass
                db_overrides[(row[0], row[1])] = entry

    rewards = []
    for lv in range(1, BATTLE_PASS_MAX_LEVEL + 1):
        reg = BATTLE_PASS_REWARDS.get(lv, {})
        for track in ("free", "paid"):
            key = (lv, track)
            if key in db_overrides:
                r = {**db_overrides[key], "source": "db"}
            else:
                r = {**reg.get(track, {}), "source": "registry"}
                if "items" in r:
                    r["items"] = list(list(x) for x in r["items"])
            rewards.append({"level": lv, "track": track, **r})

    return {"season_id": season_id, "rewards": rewards, "items_registry": list(ITEMS_REGISTRY.keys())}


class BpRewardRequest(BaseModel):
    season_id: str
    level: int
    track: str
    mora: int = 0
    diamonds: int = 0
    items: list = []   # [[item_id, qty], ...]
    theme_id: str | None = None
    # Если задан массив из ≥2 вариантов — уровень становится ВЫБОРОМ игрока.
    # Каждый вариант: {"mora":N,"diamonds":N,"items":[[id,qty]],"theme":id|null}
    reward_options: list | None = None


@router.post("/bp/rewards")
async def dev_bp_reward_set(body: BpRewardRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Установить награду уровня+трека. Перезаписывает registry. Если задан
    reward_options (≥2 варианта) — уровень становится выбором игрока."""
    import json as _json
    _require_dev(user)
    if body.track not in ("free", "paid"):
        raise HTTPException(400, "track: 'free' или 'paid'.")
    if not 1 <= body.level <= BATTLE_PASS_MAX_LEVEL:
        raise HTTPException(400, f"level: 1..{BATTLE_PASS_MAX_LEVEL}.")

    opts_json = None
    if body.reward_options:
        if not isinstance(body.reward_options, list) or len(body.reward_options) < 2:
            raise HTTPException(400, "reward_options: нужно ≥2 вариантов (или null).")
        opts_json = _json.dumps(body.reward_options)

    items_json = _json.dumps(body.items)
    await db.execute(
        "INSERT INTO battle_pass_reward_overrides "
        "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (season_id, level, track) DO UPDATE SET "
        "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items=EXCLUDED.items, "
        "theme_id=EXCLUDED.theme_id, reward_options=EXCLUDED.reward_options",
        (body.season_id, body.level, body.track, body.mora, body.diamonds,
         items_json, body.theme_id, opts_json),
    )
    await db.commit()
    return {"ok": True}


class BpBulkRequest(BaseModel):
    season_id: str
    track: str
    level_from: int
    level_to: int
    mora_base: int = 0
    mora_step: int = 0      # +mora_step за каждый уровень выше level_from
    diamonds_base: int = 0
    diamonds_step: int = 0


@router.post("/bp/rewards/bulk")
async def dev_bp_reward_bulk(body: BpBulkRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Массовое автозаполнение диапазона уровней по формуле base+step×(lv-from)."""
    _require_dev(user)
    if body.track not in ("free", "paid"):
        raise HTTPException(400, "track: 'free' или 'paid'.")
    lo, hi = body.level_from, body.level_to
    if not (1 <= lo <= hi <= BATTLE_PASS_MAX_LEVEL):
        raise HTTPException(400, f"Диапазон 1..{BATTLE_PASS_MAX_LEVEL}, from ≤ to.")
    count = 0
    for lv in range(lo, hi + 1):
        mora = body.mora_base + body.mora_step * (lv - lo)
        dia = body.diamonds_base + body.diamonds_step * (lv - lo)
        await db.execute(
            "INSERT INTO battle_pass_reward_overrides "
            "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
            "VALUES (?, ?, ?, ?, ?, '[]', NULL, NULL) "
            "ON CONFLICT (season_id, level, track) DO UPDATE SET "
            "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items='[]', "
            "theme_id=NULL, reward_options=NULL",
            (body.season_id, lv, body.track, mora, dia),
        )
        count += 1
    await db.commit()
    return {"ok": True, "updated": count}


class BpCopyRequest(BaseModel):
    from_season: str
    to_season: str


@router.post("/bp/rewards/copy")
async def dev_bp_reward_copy(body: BpCopyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Скопировать ВСЕ переопределения наград из одного сезона в другой
    (стартовый шаблон для нового сезона). Существующие в to_season перезаписываются."""
    _require_dev(user)
    if body.from_season == body.to_season:
        raise HTTPException(400, "Сезоны должны различаться.")
    async with db.execute(
        "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
        "FROM battle_pass_reward_overrides WHERE season_id = ?",
        (body.from_season,),
    ) as c:
        rows = await c.fetchall()
    for r in rows:
        await db.execute(
            "INSERT INTO battle_pass_reward_overrides "
            "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (season_id, level, track) DO UPDATE SET "
            "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items=EXCLUDED.items, "
            "theme_id=EXCLUDED.theme_id, reward_options=EXCLUDED.reward_options",
            (body.to_season, r[0], r[1], r[2], r[3], r[4], r[5], r[6]),
        )
    await db.commit()
    return {"ok": True, "copied": len(rows)}


@router.get("/bp/season-summary")
async def dev_bp_season_summary(db=Depends(get_db), user=Depends(require_tg_user)):
    """Сводная «ценность сезона»: сумма мора/алмазов/предметов по трекам
    (registry + DB-переопределения, DB побеждает). Плюс список пустых уровней."""
    import json as _json
    _require_dev(user)
    await refresh_seasons_cache(db)
    season = get_active_season()
    season_id = season["id"] if season else None

    overrides: dict[tuple, dict] = {}
    if season_id:
        async with db.execute(
            "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
            "FROM battle_pass_reward_overrides WHERE season_id = ?",
            (season_id,),
        ) as c:
            for row in await c.fetchall():
                overrides[(row[0], row[1])] = row

    summary = {"free": {"mora": 0, "diamonds": 0, "items": 0},
               "paid": {"mora": 0, "diamonds": 0, "items": 0}}
    empty_levels = []
    for lv in range(1, BATTLE_PASS_MAX_LEVEL + 1):
        lv_has_any = False
        for track in ("free", "paid"):
            if (lv, track) in overrides:
                row = overrides[(lv, track)]
                if row[6]:  # reward_options — берём максимум по варианту как «потолок ценности»
                    try:
                        opts = _json.loads(row[6])
                        best = max(opts, key=lambda o: (o.get("mora", 0) + o.get("diamonds", 0) * 60))
                        summary[track]["mora"] += best.get("mora", 0)
                        summary[track]["diamonds"] += best.get("diamonds", 0)
                        summary[track]["items"] += len(best.get("items", []))
                        lv_has_any = True
                        continue
                    except Exception:
                        pass
                summary[track]["mora"] += row[2] or 0
                summary[track]["diamonds"] += row[3] or 0
                summary[track]["items"] += len(_json.loads(row[4] or "[]"))
                if (row[2] or row[3] or row[4] not in (None, "[]") or row[5]):
                    lv_has_any = True
            else:
                reg = BATTLE_PASS_REWARDS.get(lv, {}).get(track, {})
                summary[track]["mora"] += reg.get("mora", 0)
                summary[track]["diamonds"] += reg.get("diamonds", 0)
                summary[track]["items"] += len(reg.get("items", ()))
                if reg.get("mora") or reg.get("diamonds") or reg.get("items") or reg.get("theme"):
                    lv_has_any = True
        if not lv_has_any:
            empty_levels.append(lv)

    return {"season_id": season_id, "summary": summary, "empty_levels": empty_levels,
            "max_level": BATTLE_PASS_MAX_LEVEL}


@router.delete("/bp/rewards/{season_id}/{level}/{track}")
async def dev_bp_reward_reset(
    season_id: str, level: int, track: str,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    """Сбросить награду к значению из registry (удалить DB-переопределение)."""
    _require_dev(user)
    async with db.execute(
        "DELETE FROM battle_pass_reward_overrides WHERE season_id=? AND level=? AND track=? RETURNING level",
        (season_id, level, track),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    if not row:
        raise HTTPException(404, "Переопределения не было.")
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


# ── 9. Theme Lab — кастомные raw-шаблоны премиум-тем (правки без деплоя) ──────────
def _premium_template_list() -> list[dict]:
    out = []
    for theme_id, t in THEMES.items():
        tpl = t.get("premium_template")
        if tpl:
            out.append({"template_id": tpl, "theme_id": theme_id, "name": t.get("name", tpl), "kind": "premium"})
        else:
            out.append({"template_id": theme_id, "theme_id": theme_id, "name": t.get("name", theme_id), "kind": "basic"})
    return out


@router.get("/theme-templates")
async def dev_theme_templates(db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
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
    _require_dev(user)
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
    }


class ThemeTemplateRequest(BaseModel):
    raw_text: str


def _theme_id_for_template(template_id: str) -> str | None:
    theme_id = next((tid for tid, t in THEMES.items() if t.get("premium_template") == template_id), None)
    if theme_id:
        return theme_id
    return template_id if template_id in THEMES else None


async def _render_theme_preview(db, user_id: int, theme_id: str, raw_text: str) -> str:
    async with db.execute(
        "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
        "ORDER BY user_messages_count_all_time DESC LIMIT 1",
        (user_id,),
    ) as c:
        _cr = await c.fetchone()
    chat_id = _cr[0] if _cr else 0
    return await build_profile_text(db, user_id, chat_id, theme_id_override=theme_id,
                                     raw_template_override=raw_text)


@router.post("/theme-templates/{template_id}/preview")
async def dev_theme_template_preview(template_id: str, body: ThemeTemplateRequest,
                                      db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
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
    _require_dev(user)
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
    _require_dev(user)
    if get_default_raw_template(template_id) is None:
        raise HTTPException(404, "Неизвестный шаблон.")
    if not body.raw_text.strip():
        raise HTTPException(400, "Пустой шаблон.")
    await theme_tpl_repo.set_override(db, template_id, body.raw_text, user["id"])
    return {"ok": True}


@router.delete("/theme-templates/{template_id}")
async def dev_theme_template_reset(template_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    _require_dev(user)
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
    _require_dev(user)
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
    _require_dev(user)
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
    _require_dev(user)
    await theme_meta_repo.delete_override(db, theme_id)
    return {"ok": True}
