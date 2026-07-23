"""FastAPI/routers/admin.py — панель модератора."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.moderation import (
    get_chat_settings, update_chat_settings, add_warn, remove_warn,
    log_moderation_action, get_left_users, expire_due_warns,
)
from infrastructure.repositories.blacklist import get_chat_blacklist
from infrastructure.repositories.chat import set_local_rank
from infrastructure.repositories.routing import get_admin_chat
from services import moderation as mod_service
from services import roles
from services.utils import resolve_display_name

router = APIRouter(prefix="/admin", tags=["admin"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)

_LOCAL_RANK_NAMES = {
    0: "👤 Пользователь", 1: "👁 Модератор", 2: "👮 Мл.Админ",
    3: "👮 Админ", 4: "🕵️ Ст.Админ", 5: "👑 Совладелец", 6: "👑 Владелец",
}


async def _get_actor_rank(db, user_id: int, chat_id: int) -> int:
    # 8.0: Developer bypass — панель работает в ЛЮБОМ чате даже без строки user_chat_stats
    if DEVELOPER_ID and user_id == DEVELOPER_ID:
        return 6  # Владелец в любом чате
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    # row[0] может быть NULL у старых строк (как и ucs.local_rank in admin_users) —
    # без `or 0` `_require_admin` сравнивает None < 1 → TypeError → 500.
    local = (row[0] or 0) if row else 0
    # БЛОК 21.2 W1.4: глобальный ранг 3 = Владелец в любом чате бота; хелпер с
    # правом local_actions_any_chat = Ст.Адм (4) — варн/мут/кик по порогам чата,
    # но не выше владельцев. Все действия пишутся в журнал чата как обычно.
    if local < 6:
        from infrastructure.repositories.users import get_global_rank
        grank = await get_global_rank(db, user_id) or 0
        if grank >= 3:
            return 6
        if grank >= 1:
            from services import global_permissions as _gperm
            if await _gperm.has_perm(db, grank, "local_actions_any_chat"):
                return max(local, 4)
    return local


async def _require_admin(db, user_id: int, chat_id: int) -> int:
    rank = await _get_actor_rank(db, user_id, chat_id)
    if rank < 1:
        raise HTTPException(403, "Нет прав модератора в этом чате.")
    return rank


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


class _TgBotShim:
    """services.moderation ждёт интерфейс aiogram.Bot; у FastAPI нет live-бота —
    те же методы через raw HTTP (как _BotShim в global_admin.py). Ошибка TG
    → исключение, как у aiogram: сервис тогда НЕ меняет состояние в БД."""

    @staticmethod
    def _ok(res: dict) -> None:
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or res.get("description") or "tg error")

    async def ban_chat_member(self, chat_id: int, user_id: int) -> None:
        self._ok(await _tg_call("banChatMember", chat_id=chat_id, user_id=user_id))

    async def unban_chat_member(self, chat_id: int, user_id: int,
                                only_if_banned: bool = False) -> None:
        self._ok(await _tg_call("unbanChatMember", chat_id=chat_id, user_id=user_id,
                                only_if_banned=only_if_banned))

    async def restrict_chat_member(self, chat_id: int, user_id: int,
                                   permissions=None, until_date=None) -> None:
        kwargs = {"chat_id": chat_id, "user_id": user_id,
                  "permissions": permissions.model_dump(exclude_none=True)}
        if until_date is not None:
            kwargs["until_date"] = until_date
        self._ok(await _tg_call("restrictChatMember", **kwargs))


_tg_bot = _TgBotShim()


@router.get("/my-chats")
async def my_admin_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    """Только РЕАЛЬНЫЕ группы (chat_id < 0, есть название), где пользователь
    состоит (is_left=FALSE). Обычному пользователю нужен явный ранг модератора
    (local_rank >= 1). Разработчик (DEVELOPER_ID) — Владелец (ранг 6) в ЛЮБОМ
    чате по _get_actor_rank, даже без явной строки local_rank в этом чате
    (просто состоит как обычный участник) — без байпаса свитчер не показывал
    его собственный чат вообще, хотя действия там уже работали.
    Без «фантомных чатов-цифр» и без показа всех чатов бота.
    Размечает связь Основная↔Админская группа (chat_links)."""
    is_developer = bool(DEVELOPER_ID) and user["id"] == DEVELOPER_ID
    rank_filter = "1=1" if is_developer else "ucs.local_rank >= 1"
    async with db.execute(
        "SELECT ucs.chat_tg_id, COALESCE(cs.chat_title, CAST(ucs.chat_tg_id AS TEXT)) AS chat_title, "
        "ucs.local_rank, lk.admin_chat_id "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "LEFT JOIN chat_links lk ON lk.main_chat_id = ucs.chat_tg_id "
        f"WHERE ucs.user_tg_id = ? AND {rank_filter} AND ucs.is_left = FALSE "
        "AND ucs.chat_tg_id < 0 AND cs.chat_title IS NOT NULL "
        "ORDER BY ucs.local_rank DESC",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    if is_developer:
        for r in rows:
            r["local_rank"] = 6  # фактический ранг в любом чате, см. _get_actor_rank

    chat_ids = [r["chat_tg_id"] for r in rows]
    # Какие из этих чатов сами являются админ-чатами для какой-то основной группы
    serves: dict = {}
    if chat_ids:
        ph = ",".join("?" * len(chat_ids))
        async with db.execute(
            f"SELECT main_chat_id, admin_chat_id FROM chat_links WHERE admin_chat_id IN ({ph})",
            tuple(chat_ids),
        ) as c:
            for lk in await c.fetchall():
                serves[lk["admin_chat_id"]] = lk["main_chat_id"]

    # Заголовки связанных чатов (основных и админских)
    linked_ids = {r["admin_chat_id"] for r in rows if r["admin_chat_id"]} | set(serves.values())
    titles: dict = {}
    if linked_ids:
        ph = ",".join("?" * len(linked_ids))
        async with db.execute(
            f"SELECT chat_id, chat_title FROM chat_settings WHERE chat_id IN ({ph})",
            tuple(linked_ids),
        ) as c:
            titles = {x["chat_id"]: (x["chat_title"] or str(x["chat_id"])) for x in await c.fetchall()}

    for r in rows:
        r["rank_name"] = _LOCAL_RANK_NAMES.get(r["local_rank"], "?")
        if r["chat_tg_id"] in serves:               # это админ-чат для основной группы
            r["role"] = "admin"
            r["linked_title"] = titles.get(serves[r["chat_tg_id"]])
        elif r["admin_chat_id"]:                     # это основная группа с привязанным админ-чатом
            r["role"] = "main"
            r["linked_title"] = titles.get(r["admin_chat_id"])
        else:
            r["role"] = "plain"
            r["linked_title"] = None
    return {"chats": rows}


@router.get("/{chat_id}/dashboard")
async def admin_dashboard(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE", (chat_id,)
    ) as c:
        member_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND warnings > 0 AND is_left = FALSE",
        (chat_id,),
    ) as c:
        warned_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM moderation_logs WHERE chat_id = ? AND action = 'ban'", (chat_id,)
    ) as c:
        ban_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats "
        "WHERE chat_tg_id = ? AND last_message_at > NOW() - INTERVAL '24 hours' AND is_left = FALSE",
        (chat_id,),
    ) as c:
        active_today = (await c.fetchone())[0]

    return {
        "my_rank": actor_rank,
        "my_rank_name": _LOCAL_RANK_NAMES.get(actor_rank, "?"),
        "member_count": member_count,
        "warned_count": warned_count,
        "ban_count": ban_count,
        "active_today": active_today,
        "can_warn": actor_rank >= settings.get("rank_warn", 2),
        "can_mute": actor_rank >= settings.get("rank_mute", 1),
        "can_kick": actor_rank >= settings.get("rank_kick", 1),
        "can_ban":  actor_rank >= settings.get("rank_ban",  2),
    }


@router.get("/{chat_id}/users")
async def admin_users(
    chat_id: int,
    page: int = Query(1, ge=1),
    search: str = Query("", max_length=64),
    sort: str = Query("messages"),
    flt: str = Query("", max_length=16, alias="filter"),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    page_size = 20
    offset = (page - 1) * page_size

    sort_col = {
        "messages": "ucs.user_messages_count_all_time DESC",
        "level": "ucs.user_level DESC",
        "rank": "ucs.local_rank DESC",
        "warns": "ucs.warnings DESC",
    }.get(sort, "ucs.user_messages_count_all_time DESC")

    search_clause = ""
    params: list = [chat_id]
    if search:
        search_clause = " AND (LOWER(u.user_tg_username) LIKE LOWER(?) OR CAST(ucs.user_tg_id AS TEXT) LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    # Фильтр «только забаненные/кикнутые» (block 7.2): бан/кик/ЧС/глоб.бан живут НЕ в
    # user_chat_stats, а в moderation_logs / chat_blacklist / global_sanctions (те же
    # источники, что chat_sanctions_map рисует бейджами) — поэтому сужаем серверно;
    # постранично клиент отфильтровал бы лишь текущую страницу (20 из N).
    ban_clause = ""
    if flt == "banned":
        ban_clause = (
            " AND ucs.user_tg_id IN ("
            "SELECT user_id FROM moderation_logs WHERE chat_id = ? AND action IN ('ban','kick') "
            "UNION SELECT user_id FROM chat_blacklist WHERE chat_id = ? "
            "UNION SELECT target_id FROM global_sanctions WHERE target_type = 'user' "
            "AND sanction_type = 'ban' AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > NOW()))"
        )
        params += [chat_id, chat_id]

    query = (
        f"SELECT ucs.user_tg_id, u.user_tg_username, ucs.user_level, ucs.user_xp, "
        f"ucs.local_rank, ucs.warnings, ucs.is_immune, ucs.immune_until, ucs.is_left, "
        f"ucs.user_messages_count_all_time, ucs.last_message_at, ucs.muted_until, ucs.joined_at, "
        f"(v.user_id IS NOT NULL) AS is_vip "
        f"FROM user_chat_stats ucs "
        f"LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
        f"LEFT JOIN vip_subscriptions v ON v.user_id = ucs.user_tg_id AND v.expires_at > NOW() "
        f"WHERE ucs.chat_tg_id = ? {search_clause}{ban_clause} "
        f"ORDER BY {sort_col} LIMIT {page_size} OFFSET {offset}"
    )
    async with db.execute(query, params) as c:
        rows = [dict(r) for r in await c.fetchall()]

    count_query = (
        f"SELECT COUNT(*) FROM user_chat_stats ucs "
        f"LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
        f"WHERE ucs.chat_tg_id = ?{search_clause}{ban_clause}"
    )
    async with db.execute(count_query, params) as c:
        total = (await c.fetchone())[0]

    # UX: статусы модерации у каждого участника (бан/кик/глоб.ЧС) — админ видит
    # полную картину прямо в списке, как и dev-консоль (один сервис на обоих).
    from services.moderation import chat_sanctions_map
    sanctions = await chat_sanctions_map(db, chat_id, [r["user_tg_id"] for r in rows])

    for r in rows:
        s = sanctions.get(int(r["user_tg_id"])) or {}
        r["is_banned"] = s.get("banned", False)
        r["was_kicked"] = s.get("kicked", False)
        r["global_ban"] = s.get("global_ban", False)
        r["rank_name"] = _LOCAL_RANK_NAMES.get(r["local_rank"] or 0, "?")
        r["can_act"] = actor_rank > (r["local_rank"] or 0)
        r["can_warn"] = r["can_act"] and actor_rank >= settings.get("rank_warn", 2)
        r["can_mute"] = r["can_act"] and actor_rank >= settings.get("rank_mute", 1)
        r["can_kick"] = r["can_act"] and actor_rank >= settings.get("rank_kick", 1)
        r["can_ban"]  = r["can_act"] and actor_rank >= settings.get("rank_ban",  2)
        # 8.4: щит/иммунитет — отдельные пороги
        r["can_shield"] = r["can_act"] and actor_rank >= settings.get("rank_shield", 4)
        r["can_immune"] = r["can_act"] and actor_rank >= settings.get("rank_immune", 5)
        # 8.2: смена ранга
        r["can_set_rank"] = r["can_act"]
        r["muted_until"] = str(r["muted_until"]) if r.get("muted_until") else None
        r["immune_until"] = str(r["immune_until"]) if r.get("immune_until") else None
        r["last_message_at"] = str(r["last_message_at"]) if r.get("last_message_at") else None
        r["joined_at"] = str(r["joined_at"]) if r.get("joined_at") else None

    return {"users": rows, "total": total, "page": page, "page_size": page_size,
            "max_assignable_rank": actor_rank - 1}


@router.get("/{chat_id}/settings")
async def admin_get_settings(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_admin(db, user["id"], chat_id)
    return await get_chat_settings(db, chat_id)


class SettingsUpdateRequest(BaseModel):
    shield_duration_days: Optional[int] = None
    max_warnings: Optional[int] = None
    rank_warn: Optional[int] = None
    rank_mute: Optional[int] = None
    rank_kick: Optional[int] = None
    rank_ban: Optional[int] = None
    # 8.3: недостающие пороги рангов (бот их уже читает/пишет в той же chat_settings)
    rank_shield: Optional[int] = None
    rank_immune: Optional[int] = None
    rank_marriage: Optional[int] = None
    rank_give: Optional[int] = None
    purge_min_rank: Optional[int] = None
    purge_action_rank: Optional[int] = None
    purge_write_rank: Optional[int] = None   # admin_audit B5: 0 = пишут все
    rank_chat_lock: Optional[int] = None
    events_enabled: Optional[int] = None
    module_shop: Optional[int] = None
    module_gacha: Optional[int] = None
    module_expeditions: Optional[int] = None
    module_auction: Optional[int] = None
    module_games: Optional[int] = None
    module_exchange: Optional[int] = None
    module_quests: Optional[int] = None
    module_zoo: Optional[int] = None
    module_warps: Optional[int] = None
    module_daily_deal: Optional[int] = None
    nsfw_warps_allowed: Optional[int] = None
    # Категорийные тумблеры игровых уведомлений чата (2026-07-12)
    notif_auction: Optional[int] = None
    notif_gacha: Optional[int] = None
    notif_expeditions: Optional[int] = None
    notif_quests: Optional[int] = None


@router.post("/{chat_id}/settings")
async def admin_update_settings(
    chat_id: int, body: SettingsUpdateRequest,
    db=Depends(get_db), user=Depends(require_tg_user)
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    # Выравнивание с ботом (БЛОК 36.2): вход в «бот настройки чата» требует ранг 5 —
    # сайт разрешал сохранение с 4, игрок с рангом 4 менял настройки, не видя их в боте.
    if actor_rank < 5:
        raise HTTPException(403, "Требуется ранг Совладелец (5) для изменения настроек.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    await update_chat_settings(db, chat_id, **updates)
    return {"ok": True}


class ActionRequest(BaseModel):
    user_id: int
    action: str   # warn / unwarn / mute / unmute / kick / ban / unban / immune
    duration_minutes: Optional[int] = None
    reason: Optional[str] = None


@router.post("/{chat_id}/action")
async def admin_action(
    chat_id: int, body: ActionRequest,
    db=Depends(get_db), user=Depends(require_tg_user)
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)

    # Get target rank for anti-peer check
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (body.user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    # `or 0`: local_rank может быть NULL у старых строк (как в admin_set_rank) —
    # иначе actor_rank <= target_rank ниже кидает TypeError на int <= None.
    target_rank = (trow[0] or 0) if trow else 0

    if actor_rank <= target_rank:
        raise HTTPException(403, "Нельзя применить действие к пользователю с таким же или более высоким рангом.")

    action = body.action
    if action == "immune":
        action = "shield"  # 8.4: старое имя action — алиас щита (так фронт не ломается)
    _required = {"warn": "rank_warn", "unwarn": "rank_warn",
                 "mute": "rank_mute", "unmute": "rank_mute",
                 "kick": "rank_kick", "ban": "rank_ban", "unban": "rank_ban",
                 # 8.4: щит (временный) и иммунитет (постоянный) — разные пороги
                 "shield": "rank_shield", "unshield": "rank_shield",
                 "set_immune": "rank_immune", "unset_immune": "rank_immune"}
    req_key = _required.get(action)
    if req_key and actor_rank < settings.get(req_key, 99):
        raise HTTPException(403, f"Недостаточно прав для действия '{action}'.")

    tg_result = None

    if action == "warn":
        # ленивая уборка истёкших срочных варнов — как бот-команда «варн» (admin_audit B3)
        try:
            await expire_due_warns(db, chat_id)
        except Exception:
            pass
        new_warnings = await add_warn(db, chat_id, body.user_id, user["id"], body.reason)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "warn", body.reason)
        # Суд Присяжных при лимите — как бот-команда «варн» («сайт == бот»)
        max_warns = settings.get("max_warnings") or 3
        if new_warnings >= max_warns:
            target_name = await resolve_display_name(
                db, body.user_id, chat_id, f"ID{body.user_id}")
            await mod_service.start_warn_court(
                db, chat_id, body.user_id, target_name, new_warnings, max_warns)
        return {"ok": True, "new_warnings": new_warnings}

    elif action == "unwarn":
        new_warnings = await remove_warn(db, chat_id, body.user_id)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unwarn", body.reason)
        return {"ok": True, "new_warnings": new_warnings}

    # mute/unmute/kick/ban/unban — единый сервис («сайт == бот»): TG-вызов + все
    # DB-состояния (журнал, muted_until, ЧС) меняются одинаково с бот-командами;
    # при ошибке TG состояние не трогается (раньше сайт логировал даже фейл).
    elif action == "mute":
        duration = body.duration_minutes or 60
        tg_ok = await mod_service.mute_user(
            db, _tg_bot, chat_id, body.user_id, user["id"],
            duration_minutes=duration, reason=body.reason)
        return {"ok": True, "telegram_ok": tg_ok}

    elif action == "unmute":
        tg_ok = await mod_service.unmute_user(
            db, _tg_bot, chat_id, body.user_id, user["id"], reason=body.reason)
        return {"ok": True, "telegram_ok": tg_ok}

    elif action == "kick":
        tg_ok = await mod_service.kick_user(
            db, _tg_bot, chat_id, body.user_id, user["id"], reason=body.reason)
        return {"ok": True, "telegram_ok": tg_ok}

    elif action == "ban":
        tg_ok = await mod_service.ban_user(
            db, _tg_bot, chat_id, body.user_id, user["id"], reason=body.reason)
        return {"ok": True, "telegram_ok": tg_ok}

    elif action == "unban":
        tg_ok = await mod_service.unban_user(
            db, _tg_bot, chat_id, body.user_id, user["id"], reason=body.reason)
        return {"ok": True, "telegram_ok": tg_ok}

    elif action == "shield":
        duration = body.duration_minutes or 1440
        await mod_service.shield_user(
            db, chat_id, body.user_id, user["id"], duration, reason=body.reason)

    elif action == "unshield":
        await mod_service.unshield_user(db, chat_id, body.user_id, user["id"], reason=body.reason)

    elif action == "set_immune":
        await mod_service.set_immune_user(
            db, chat_id, body.user_id, user["id"], True, reason=body.reason)

    elif action == "unset_immune":
        await mod_service.set_immune_user(
            db, chat_id, body.user_id, user["id"], False, reason=body.reason)

    else:
        raise HTTPException(400, f"Неизвестное действие: {action}")

    return {"ok": True, "telegram_ok": (tg_result or {}).get("ok", False)}


@router.get("/{chat_id}/logs")
async def admin_logs(
    chat_id: int,
    page: int = Query(1, ge=1),
    action: str = Query("", max_length=16),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    await _require_admin(db, user["id"], chat_id)
    page_size = 25
    offset = (page - 1) * page_size

    # 8.6: фильтр ?action=ban / ?action=kick — те же данные, что бот-команды «баны»/«кики»
    action_clause = ""
    params: list = [chat_id]
    if action:
        if action not in ("ban", "kick", "warn", "unwarn", "unban", "mute", "unmute"):
            raise HTTPException(400, "Недопустимый фильтр action.")
        if action == "mute":
            # старые бот-записи — просто 'mute', новые (единый сервис) — 'mute_60m'/'mute_perm'
            action_clause = " AND (ml.action = 'mute' OR ml.action LIKE 'mute_%')"
        else:
            action_clause = " AND ml.action = ?"
            params.append(action)

    async with db.execute(
        "SELECT ml.id, ml.user_id, ml.admin_id, ml.action, ml.reason, ml.created_at, "
        "u.user_tg_username AS target_name, a.user_tg_username AS admin_name, "
        "(vu.user_id IS NOT NULL) AS target_is_vip, (va.user_id IS NOT NULL) AS admin_is_vip "
        "FROM moderation_logs ml "
        "LEFT JOIN users u ON ml.user_id = u.user_tg_id "
        "LEFT JOIN users a ON ml.admin_id = a.user_tg_id "
        "LEFT JOIN vip_subscriptions vu ON vu.user_id = ml.user_id AND vu.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions va ON va.user_id = ml.admin_id AND va.expires_at > NOW() "
        f"WHERE ml.chat_id = ?{action_clause} "
        "ORDER BY ml.created_at DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    async with db.execute(
        f"SELECT COUNT(*) FROM moderation_logs ml WHERE ml.chat_id = ?{action_clause}", params
    ) as c:
        total = (await c.fetchone())[0]

    for r in rows:
        r["created_at"] = str(r["created_at"])

    return {"logs": rows, "total": total, "page": page, "page_size": page_size}


# ── Открыть / закрыть чат целиком (с сайта) ─────────────────────────────────────
_OPEN_PERMS_WEB = {"can_send_messages": True, "can_send_audios": True,
                   "can_send_documents": True, "can_send_photos": True,
                   "can_send_videos": True, "can_send_video_notes": True,
                   "can_send_voice_notes": True, "can_send_polls": True,
                   "can_send_other_messages": True, "can_add_web_page_previews": True}


class ChatLockRequest(BaseModel):
    open: bool


@router.post("/{chat_id}/chat-lock")
async def admin_chat_lock(chat_id: int, body: ChatLockRequest,
                          db=Depends(get_db), user=Depends(require_tg_user)):
    """Открыть/закрыть чат целиком. Порог — rank_chat_lock (как у бот +чат/-чат)."""
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    if actor_rank < settings.get("rank_chat_lock", 4):
        raise HTTPException(403, "Недостаточно прав для открытия/закрытия чата.")
    perms = _OPEN_PERMS_WEB if body.open else {"can_send_messages": False}
    res = await _tg_call("setChatPermissions", chat_id=chat_id, permissions=perms)
    if not res.get("ok"):
        raise HTTPException(502, "Не удалось изменить права чата (бот не админ?).")
    return {"ok": True, "open": body.open}


# ── 8.6: Вышедшие из чата ───────────────────────────────────────────────────────
@router.get("/{chat_id}/left")
async def admin_left_users(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_admin(db, user["id"], chat_id)
    rows = await get_left_users(db, chat_id)
    return {"left": rows}


# ── 8.1: Чёрный список чата ─────────────────────────────────────────────────────
class BlacklistAddRequest(BaseModel):
    user_id: int
    reason: Optional[str] = None


async def _require_blacklist_rank(db, user_id: int, chat_id: int) -> int:
    """ЧС по тяжести близок к бану — порог rank_ban."""
    actor_rank = await _require_admin(db, user_id, chat_id)
    settings = await get_chat_settings(db, chat_id)
    if actor_rank < settings.get("rank_ban", 2):
        raise HTTPException(403, "Требуется ранг для бана (rank_ban), чтобы управлять ЧС.")
    return actor_rank


@router.get("/{chat_id}/blacklist")
async def admin_blacklist(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_blacklist_rank(db, user["id"], chat_id)
    entries = await get_chat_blacklist(db, chat_id)
    # Обогащаем юзернеймами одним запросом
    ids = {e["user_id"] for e in entries} | {e["added_by"] for e in entries if e["added_by"]}
    names: dict = {}
    if ids:
        ph = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({ph})",
            tuple(ids),
        ) as c:
            names = {r["user_tg_id"]: r["user_tg_username"] for r in await c.fetchall()}
    for e in entries:
        e["username"] = names.get(e["user_id"])
        e["added_by_name"] = names.get(e["added_by"])
        e["added_at"] = str(e["added_at"]) if e.get("added_at") else None
    return {"blacklist": entries}


@router.post("/{chat_id}/blacklist")
async def admin_blacklist_add(
    chat_id: int, body: BlacklistAddRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_blacklist_rank(db, user["id"], chat_id)
    # anti-peer как в /action
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (body.user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    # `or 0`: local_rank может быть NULL у старых строк (как в admin_set_rank) —
    # иначе actor_rank <= target_rank ниже кидает TypeError на int <= None.
    target_rank = (trow[0] or 0) if trow else 0
    if actor_rank <= target_rank:
        raise HTTPException(403, "Нельзя внести в ЧС пользователя с таким же или более высоким рангом.")

    await mod_service.blacklist_user(db, chat_id, body.user_id, user["id"], body.reason)
    return {"ok": True}


@router.delete("/{chat_id}/blacklist/{user_id}")
async def admin_blacklist_remove(
    chat_id: int, user_id: int,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    await _require_blacklist_rank(db, user["id"], chat_id)
    removed = await mod_service.unblacklist_user(db, chat_id, user_id, user["id"])
    return {"ok": True, "removed": removed}


# ── 8.2: Управление рангами ─────────────────────────────────────────────────────
class SetRankRequest(BaseModel):
    new_rank: int


@router.post("/{chat_id}/users/{user_id}/rank")
async def admin_set_rank(
    chat_id: int, user_id: int, body: SetRankRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    if body.new_rank not in roles.LOCAL_RANKS_MAP:
        raise HTTPException(400, "Недопустимый ранг.")

    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    if not trow:
        raise HTTPException(404, "Пользователь не найден в этом чате.")
    target_rank = trow[0] or 0

    ok, err = roles.can_assign_local_rank(
        user["id"], actor_rank, target_rank, body.new_rank, DEVELOPER_ID)
    if not ok:
        raise HTTPException(403, err)

    await set_local_rank(db, user_id, chat_id, body.new_rank)
    await log_moderation_action(db, chat_id, user_id, user["id"], f"rank_{body.new_rank}", None)
    await db.commit()
    return {"ok": True, "new_rank": body.new_rank,
            "rank_name": _LOCAL_RANK_NAMES.get(body.new_rank, "?")}


# ── 8.5: Чистка 2.0 (admin_audit B4) — единый движок services/purge.py ──────────
# Полный паритет с чатом: сессия в БД, батчевая выдача досье в чат, вердикты и
# завершение — с сайта производятся РОВНО те же сообщения в чате, что и из чата.
from services import purge as purge_svc  # noqa: E402


class PurgeStartRequest(BaseModel):
    start_date: Optional[str] = None   # YYYY-MM-DD
    end_date: Optional[str] = None
    norm: Optional[int] = None


@router.get("/{chat_id}/purge/status")
async def admin_purge_status(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    admin_chat_id = await get_admin_chat(db, chat_id)
    st = await purge_svc.get_status(db, chat_id)
    out = {"purge_min_rank": settings.get("purge_min_rank", 4),
           "purge_action_rank": settings.get("purge_action_rank", 2),
           "purge_write_rank": settings.get("purge_write_rank", 0),
           "has_admin_chat": bool(admin_chat_id),
           "active": bool(st)}
    if st:
        # Кто может жать кнопки вердикта (то же правило, что в apply_verdict):
        # инициатор / разработчик / ранг ≥ purge_action_rank — сайт == бот.
        out["can_verdict"] = (
            user["id"] == st["session"]["initiator_id"]
            or user["id"] == DEVELOPER_ID
            or actor_rank >= settings.get("purge_action_rank", 2))
        out["session"] = {
            "id": st["session"]["id"],
            "initiator_id": st["session"]["initiator_id"],
            "norm": st["session"]["norm"],
            "date_from": st["session"]["date_from"],
            "date_to": st["session"]["date_to"],
        }
        out["counts"] = st["counts"]
        out["targets"] = [
            {"user_id": t["user_id"], "username": t["username"],
             "msg_count": t["msg_count"], "days_in_chat": t["days_in_chat"],
             "warns": t["warns"], "dossier_sent": bool(t["dossier_sent"]),
             "verdict": t["verdict"]}
            for t in st["targets"]
        ]
    return out


@router.post("/{chat_id}/purge/start")
async def admin_purge_start(
    chat_id: int, body: PurgeStartRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    if actor_rank < 4:
        raise HTTPException(403, "Чистка требует ранг Ст. Админ (4) — как и в чате.")
    now = datetime.now(timezone.utc)
    try:
        end_d = datetime.strptime(body.end_date, "%Y-%m-%d") if body.end_date else now
        start_d = datetime.strptime(body.start_date, "%Y-%m-%d") if body.start_date \
            else end_d - timedelta(days=7)
    except ValueError:
        raise HTTPException(400, "Даты — в формате YYYY-MM-DD.")
    norm = body.norm if body.norm and body.norm > 0 else 50
    ok, msg, info = await purge_svc.start_purge(
        db, chat_id, user["id"],
        start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"), norm)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, **info}


@router.post("/{chat_id}/purge/dossiers")
async def admin_purge_dossiers(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Выслать в чат следующую порцию досье (аналог кнопки «Выслать ещё N»)."""
    await _require_admin(db, user["id"], chat_id)
    st = await purge_svc.get_status(db, chat_id)
    if not st:
        raise HTTPException(400, "Активной чистки нет.")
    sent, remaining = await purge_svc.send_next_batch(db, st["session"]["id"], user["id"])
    if sent == -1:
        raise HTTPException(403, "Досье высылает только инициатор чистки.")
    return {"ok": True, "sent": sent, "remaining": remaining}


class PurgeVerdictRequest(BaseModel):
    user_id: int
    action: str   # warn | kick | ban | skip


@router.post("/{chat_id}/purge/verdict")
async def admin_purge_verdict(
    chat_id: int, body: PurgeVerdictRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    await _require_admin(db, user["id"], chat_id)
    st = await purge_svc.get_status(db, chat_id)
    if not st:
        raise HTTPException(400, "Активной чистки нет.")
    ok, text = await purge_svc.apply_verdict(
        db, st["session"]["id"], body.user_id, body.action, user["id"],
        developer_id=DEVELOPER_ID)
    if not ok:
        raise HTTPException(403, text)
    return {"ok": True, "message": text}


@router.post("/{chat_id}/purge/finish")
async def admin_purge_finish(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    if actor_rank < 4:
        raise HTTPException(403, "Завершение чистки — ранг 4+.")
    st = await purge_svc.get_status(db, chat_id)
    if not st:
        raise HTTPException(400, "Активной чистки нет.")
    summary = await purge_svc.finish_purge(db, st["session"]["id"], user["id"])
    return {"ok": True, "summary": summary}
