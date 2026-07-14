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
from ._common import _classify_chat_links, require_console_perm, _send_admin_gift, _tg_call

router = APIRouter()


# ── 1. Обзор системы ─────────────────────────────────────────────────────────────
@router.get("/overview")
async def dev_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "console_overview")

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
    await require_console_perm(db, user, "dossier_view")
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
        "ucs.last_message_at, ucs.muted_until, "
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
        ch["last_message_at"] = str(ch["last_message_at"]) if ch.get("last_message_at") else None
        ch["muted_until"] = str(ch["muted_until"]) if ch.get("muted_until") else None
    await _classify_chat_links(db, chats, "chat_tg_id")
    # Порядок: группы рядом, активные группы выше; внутри группы main → admin.
    gmax: dict = {}
    for ch in chats:
        gk = ch["group_key"]; m = ch.get("user_messages_count_all_time") or 0
        gmax[gk] = max(gmax.get(gk, 0), m)
    _role_ord = {"main": 0, "admin": 1, "plain": 0}
    chats.sort(key=lambda c: (-gmax[c["group_key"]], c["group_key"], _role_ord.get(c["role"], 0)))
    d["chats"] = chats

    # Досье v2 (БЛОК 21.2 W1.3): ВСЕ санкции (вкл. снятые/истёкшие) с автором,
    # d["sanctions"] остаётся активным срезом (обратная совместимость фронта).
    async with db.execute(
        "SELECT g.id, g.sanction_type, g.reason, g.expires_at, g.created_at, g.revoked_at, "
        "g.issued_by, ui.user_tg_username AS issued_by_name, "
        "(g.revoked_at IS NULL AND (g.expires_at IS NULL OR g.expires_at > NOW())) AS active "
        "FROM global_sanctions g LEFT JOIN users ui ON ui.user_tg_id = g.issued_by "
        "WHERE g.target_type = 'user' AND g.target_id = ? ORDER BY g.id DESC LIMIT 30", (uid,)
    ) as c:
        sanctions_all = [dict(r) for r in await c.fetchall()]
    for s in sanctions_all:
        s["active"] = bool(s["active"])
        for k in ("expires_at", "created_at", "revoked_at"):
            s[k] = str(s[k]) if s[k] else None
    d["sanctions_all"] = sanctions_all
    d["sanctions"] = [s for s in sanctions_all if s["active"]]

    # Апелляции игрока (все статусы) — переход в диалог из Центра игрока
    async with db.execute(
        "SELECT id, sanction_id, status, created_at FROM sanction_appeals "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 15", (uid,)
    ) as c:
        appeals = [dict(r) for r in await c.fetchall()]
    for a in appeals:
        a["created_at"] = str(a["created_at"]) if a["created_at"] else None
    d["appeals"] = appeals

    # Действия консоли по игроку (журнал выдач) — последние 15
    async with db.execute(
        "SELECT l.action, l.detail, l.amount, l.reason, l.created_at, "
        "ua.user_tg_username AS admin_name "
        "FROM admin_grant_log l LEFT JOIN users ua ON ua.user_tg_id = l.admin_id "
        "WHERE l.target_id = ? ORDER BY l.id DESC LIMIT 15", (uid,)
    ) as c:
        grant_log = [dict(r) for r in await c.fetchall()]
    for g in grant_log:
        g["created_at"] = str(g["created_at"]) if g["created_at"] else None
    d["grant_log"] = grant_log

    # Локальная модерация по чатам (варны/муты/кики/баны) — последние 15
    async with db.execute(
        "SELECT ml.chat_id, ml.action, ml.reason, ml.created_at, "
        "COALESCE(cs.chat_title, CAST(ml.chat_id AS TEXT)) AS chat_title, "
        "ua.user_tg_username AS admin_name "
        "FROM moderation_logs ml "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ml.chat_id "
        "LEFT JOIN users ua ON ua.user_tg_id = ml.admin_id "
        "WHERE ml.user_id = ? ORDER BY ml.id DESC LIMIT 15", (uid,)
    ) as c:
        mod_log = [dict(r) for r in await c.fetchall()]
    for m in mod_log:
        m["created_at"] = str(m["created_at"]) if m["created_at"] else None
    d["mod_log"] = mod_log

    # Последняя активность: где и когда писал в последний раз
    last = max((c2 for c2 in chats if c2.get("last_message_at")),
               key=lambda c2: c2["last_message_at"], default=None)
    d["last_seen"] = ({"at": last["last_message_at"], "chat_title": last["chat_title"]}
                      if last else None)

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
    await require_console_perm(db, user, "economy_balance")
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
    await require_console_perm(db, user, "economy_items")
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
    await require_console_perm(db, user, "economy_items")
    items = [{"item_id": iid, "name": info.get("name", iid),
              "category": info.get("category", "—"),
              "description": info.get("description", "")}
             for iid, info in ITEMS_REGISTRY.items()]
    items.sort(key=lambda x: (x["category"], x["name"]))
    return {"items": items}


@router.get("/admin-log")
async def dev_admin_log(q: str = Query("", max_length=64), offset: int = Query(0, ge=0),
                        db=Depends(get_db), user=Depends(require_tg_user)):
    """Журнал выдач/изъятий дев-консоли (БЛОК 4.2): кто, кому, что, причина, до/после.
    W5.1: фильтр q (ник/ID цели или админа, подстрока) + офсет для кнопки «Ещё»."""
    await require_console_perm(db, user, "log_admin_view")
    q = q.strip().lstrip("@")
    where, params = "", []
    if q:
        where = ("WHERE (ua.user_tg_username ILIKE ? OR ut.user_tg_username ILIKE ? "
                 "OR CAST(l.target_id AS TEXT) = ? OR CAST(l.admin_id AS TEXT) = ?)")
        params = [f"%{q}%", f"%{q}%", q, q]
    async with db.execute(
        "SELECT l.id, l.admin_id, l.target_id, l.action, l.detail, l.amount, "
        "l.reason, l.before_val, l.after_val, l.created_at, "
        "ua.user_tg_username AS admin_name, ut.user_tg_username AS target_name "
        "FROM admin_grant_log l "
        "LEFT JOIN users ua ON ua.user_tg_id = l.admin_id "
        "LEFT JOIN users ut ON ut.user_tg_id = l.target_id "
        f"{where} ORDER BY l.id DESC LIMIT 50 OFFSET ?",
        (*params, offset),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        r["created_at"] = str(r["created_at"]) if r.get("created_at") else None
    return {"log": rows, "offset": offset, "has_more": len(rows) == 50}


@router.get("/pulse")
async def dev_pulse(db=Depends(get_db), user=Depends(require_tg_user)):
    """W4.2: «пульт дежурного» — сводка-инбокс первой вкладкой консоли:
    счётчики-ссылки + свежие апелляции/санкции/действия штата одним запросом."""
    await require_console_perm(db, user, "console_overview")

    async def _one(sql: str, args: tuple = ()):
        async with db.execute(sql, args) as c:
            row = await c.fetchone()
        return row[0] if row and row[0] is not None else 0

    counts = {
        "appeals_pending": int(await _one(
            "SELECT COUNT(*) FROM sanction_appeals WHERE status = 'pending'")),
        "sanctions_active": int(await _one(
            "SELECT COUNT(*) FROM global_sanctions WHERE revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > NOW())")),
        "users_total": int(await _one("SELECT COUNT(*) FROM users")),
        "chats_total": int(await _one(
            "SELECT COUNT(*) FROM chat_settings WHERE chat_id < 0 AND chat_title IS NOT NULL")),
        "messages_today": int(await _one(
            "SELECT COALESCE(SUM(message_count),0) FROM daily_user_stats "
            "WHERE date = TO_CHAR(NOW() + INTERVAL '3 hours', 'YYYY-MM-DD')")),
    }

    async with db.execute(
        "SELECT a.id, a.user_id, a.status, a.created_at, u.user_tg_username "
        "FROM sanction_appeals a LEFT JOIN users u ON u.user_tg_id = a.user_id "
        "WHERE a.status = 'pending' ORDER BY a.id DESC LIMIT 5") as c:
        appeals = [dict(r) for r in await c.fetchall()]
    async with db.execute(
        "SELECT g.id, g.sanction_type, g.target_type, g.target_id, g.reason, g.created_at, "
        "ut.user_tg_username AS target_name, ui.user_tg_username AS issued_by_name "
        "FROM global_sanctions g "
        "LEFT JOIN users ut ON ut.user_tg_id = g.target_id AND g.target_type = 'user' "
        "LEFT JOIN users ui ON ui.user_tg_id = g.issued_by "
        "ORDER BY g.id DESC LIMIT 5") as c:
        sanctions = [dict(r) for r in await c.fetchall()]
    async with db.execute(
        "SELECT l.action, l.detail, l.amount, l.created_at, l.target_id, "
        "ua.user_tg_username AS admin_name, ut.user_tg_username AS target_name "
        "FROM admin_grant_log l "
        "LEFT JOIN users ua ON ua.user_tg_id = l.admin_id "
        "LEFT JOIN users ut ON ut.user_tg_id = l.target_id "
        "ORDER BY l.id DESC LIMIT 5") as c:
        admin_actions = [dict(r) for r in await c.fetchall()]
    for coll in (appeals, sanctions, admin_actions):
        for r in coll:
            r["created_at"] = str(r["created_at"]) if r.get("created_at") else None
    return {"counts": counts, "appeals": appeals, "sanctions": sanctions,
            "admin_actions": admin_actions}


@router.get("/chats")
async def dev_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    """Список чатов для дропдауна «чат → юзер» в карточке игрока (БЛОК 4.1).
    Только реальные группы (chat_id < 0, без ЛС с ботом), с разметкой Основная↔Админ
    и упорядочиванием так, чтобы админ-чат шёл сразу за своей основной группой."""
    await require_console_perm(db, user, "dossier_view", "modules_manage")
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
    await require_console_perm(db, user, "dossier_view")
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


# ── БЛОК 21.2 W1.2: глобальный поиск игрока (подстрока, топ-10) ──────────────────
@router.get("/user-search")
async def dev_user_search(q: str = Query(..., max_length=64),
                          db=Depends(get_db), user=Depends(require_tg_user)):
    """Живой поиск: подстрока username/ника (ILIKE) или точный ID. Возвращает
    топ-10 с ключевой инфой (ранг/VIP/активные санкции/балансы кратко)."""
    await require_console_perm(db, user, "user_search")
    q = q.strip().lstrip("@")
    if not q or (len(q) < 2 and not q.isdigit()):
        return {"results": []}

    base_select = (
        "SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.global_rank,0) AS global_rank, "
        "COALESCE(u.user_balance_mora,0) AS mora, COALESCE(u.user_balance_zarniki,0) AS zarniki, "
        "(v.user_id IS NOT NULL) AS is_vip, "
        "EXISTS(SELECT 1 FROM global_sanctions g WHERE g.target_type='user' AND g.target_id=u.user_tg_id "
        "  AND g.revoked_at IS NULL AND (g.expires_at IS NULL OR g.expires_at > NOW())) AS has_sanction, "
        "(SELECT n.nickname FROM user_nicknames n WHERE n.user_id = u.user_tg_id LIMIT 1) AS nickname "
        "FROM users u "
        "LEFT JOIN vip_subscriptions v ON v.user_id = u.user_tg_id AND v.expires_at > NOW() "
    )
    if q.isdigit():
        sql = base_select + "WHERE u.user_tg_id = ? OR CAST(u.user_tg_id AS TEXT) LIKE ? LIMIT 10"
        args: tuple = (int(q), f"{q}%")
    else:
        sql = base_select + (
            "WHERE u.user_tg_username ILIKE ? "
            "OR EXISTS(SELECT 1 FROM user_nicknames n2 WHERE n2.user_id = u.user_tg_id "
            "          AND n2.nickname ILIKE ?) "
            "ORDER BY (LOWER(u.user_tg_username) = LOWER(?)) DESC, u.user_tg_username LIMIT 10"
        )
        args = (f"%{q}%", f"%{q}%", q)
    async with db.execute(sql, args) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        r["global_rank_name"] = GLOBAL_RANKS_MAP.get(r["global_rank"] or 0, "?")
        r["mora"] = float(r["mora"]); r["zarniki"] = float(r["zarniki"])
        r["is_vip"] = bool(r["is_vip"]); r["has_sanction"] = bool(r["has_sanction"])
    return {"results": rows}


# ── БЛОК 21.2 W1.3: проверка доступности ЛС (по кнопке, не на каждое досье) ──────
@router.get("/dm-check")
async def dev_dm_check(user_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """sendChatAction — самый лёгкий пробник: ok=ЛС открыты, 403=бот заблокирован.
    Ничего видимого игроку не отправляет (краткий индикатор набора текста)."""
    await require_console_perm(db, user, "dossier_view")
    r = await _tg_call("sendChatAction", chat_id=user_id, action="typing")
    return {"dm_ok": bool(r.get("ok")),
            "hint": None if r.get("ok") else (r.get("description") or "ЛС закрыты/бот не запущен")}
