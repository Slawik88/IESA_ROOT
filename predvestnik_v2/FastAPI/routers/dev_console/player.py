"""dev_console/player.py — Игроки: обзор, досье, баланс, выдача предметов, чаты."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import (
    add_balance,
    add_item,
    remove_item,
    get_item_quantity,
    get_balance,
)
from infrastructure.repositories import admin_log
from services.battle_pass import get_active_season, refresh_seasons_cache
from services.roles import GLOBAL_RANKS_MAP, LOCAL_RANKS_MAP
from ._common import _classify_chat_links, _require_dev, _send_admin_gift

router = APIRouter()


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

    # VIP — со сроком: сколько дней осталось (days_left) и на сколько в целом текущая
    # подписка (span_days = started_at→expires_at), плюс накопленный стаж (total_days).
    async with db.execute(
        "SELECT tier, started_at, expires_at, COALESCE(total_days,0) AS total_days, "
        "(expires_at > NOW()) AS active, "
        "GREATEST(0, CEIL(EXTRACT(EPOCH FROM (expires_at - NOW())) / 86400.0))::int AS days_left, "
        "GREATEST(0, CEIL(EXTRACT(EPOCH FROM (expires_at - started_at)) / 86400.0))::int AS span_days "
        "FROM vip_subscriptions WHERE user_id = ?", (uid,)
    ) as c:
        vrow = await c.fetchone()
    d["vip"] = ({"tier": vrow["tier"], "active": bool(vrow["active"]),
                 "expires_at": str(vrow["expires_at"]),
                 "started_at": str(vrow["started_at"]) if vrow["started_at"] else None,
                 "days_left": vrow["days_left"], "span_days": vrow["span_days"],
                 "total_days": vrow["total_days"]}
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

    # Чаты — только реальные группы (chat_tg_id < 0, без ЛС с ботом). Размечаем
    # связь Основная↔Админ (chat_links) и переупорядочиваем, чтобы чаты одной
    # группы (основной + его админ-чат) шли рядом.
    async with db.execute(
        "SELECT ucs.chat_tg_id, COALESCE(cs.chat_title, CAST(ucs.chat_tg_id AS TEXT)) AS chat_title, "
        "ucs.local_rank, ucs.user_level, ucs.user_messages_count_all_time, ucs.warnings, ucs.is_left, "
        "lk.admin_chat_id "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "LEFT JOIN chat_links lk ON lk.main_chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? AND ucs.chat_tg_id < 0 "
        "ORDER BY ucs.user_messages_count_all_time DESC", (uid,)
    ) as c:
        chats = [dict(r) for r in await c.fetchall()]
    for ch in chats:
        ch["rank_name"] = LOCAL_RANKS_MAP.get(ch["local_rank"] or 0, "?")
    await _classify_chat_links(db, chats, "chat_tg_id")
    # Порядок: группы рядом, активные группы выше; внутри группы main → admin.
    gmax: dict = {}
    for ch in chats:
        gk = ch["group_key"]; m = ch.get("user_messages_count_all_time") or 0
        gmax[gk] = max(gmax.get(gk, 0), m)
    _role_ord = {"main": 0, "admin": 1, "plain": 0}
    chats.sort(key=lambda c: (-gmax[c["group_key"]], c["group_key"], _role_ord.get(c["role"], 0)))
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
    """Полный список предметов (ITEMS_REGISTRY) для каталога-пикера в дев-консоли."""
    _require_dev(user)
    items = [{"item_id": iid, "name": info.get("name", iid),
              "category": info.get("category", "—"),
              "description": info.get("description", "")}
             for iid, info in ITEMS_REGISTRY.items()]
    items.sort(key=lambda x: (x["category"], x["name"]))
    return {"items": items}


@router.get("/admin-log")
async def dev_admin_log(db=Depends(get_db), user=Depends(require_tg_user)):
    """Журнал выдач/изъятий дев-консоли (БЛОК 4.2): кто, кому, что, причина, до/после."""
    _require_dev(user)
    return {"log": await admin_log.recent(db, 50)}


@router.get("/chats")
async def dev_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    """Список чатов для дропдауна «чат → юзер» в карточке игрока (БЛОК 4.1).
    Только реальные группы (chat_id < 0, без ЛС с ботом), с разметкой Основная↔Админ
    и упорядочиванием так, чтобы админ-чат шёл сразу за своей основной группой."""
    _require_dev(user)
    async with db.execute(
        "SELECT cs.chat_id, COALESCE(cs.chat_title, CAST(cs.chat_id AS TEXT)) AS title, "
        "lk.admin_chat_id "
        "FROM chat_settings cs LEFT JOIN chat_links lk ON lk.main_chat_id = cs.chat_id "
        "WHERE cs.chat_id < 0 ORDER BY cs.chat_title LIMIT 300"
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    await _classify_chat_links(db, rows, "chat_id")
    _role_ord = {"main": 0, "admin": 1, "plain": 2}

    def _grp(r: dict) -> str:
        base = r["linked_title"] if r["role"] == "admin" else r["title"]
        return (base or "").lower()

    rows.sort(key=lambda r: (_grp(r), _role_ord.get(r["role"], 2), (r["title"] or "").lower()))
    return {"chats": rows}


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
