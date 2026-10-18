"""Раздел «Игроки и чаты»: поиск, карточки и действия персонала.

Смотреть карточки может любой хелпер; каждое действие — со своей минимальной ролью (ACTIONS).
К разработчику бота и к персоналу не ниже своей роли действия не применяются.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from loguru import logger

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat import moderation
from bot.chat.access import is_developer
from bot.chat.global_ranks import BOT_RANKS, CREATOR, bot_rank_name, get_bot_rank
from core.economy_contract import InsufficientBalance
from infrastructure.repositories import skins_v3 as skins_v3_repo
from infrastructure.repositories.economy_ledger import apply_balance_change
from services import admin_access, admin_people, admin_security, feature_switches, global_moderation, staff_notes, staff_watch
from services import reports as reports_service
from services import marks_v1 as marks_service
from services import vip as vip_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("people")

# Действие -> (подпись, минимальная глобальная роль, к чему применяется).
# Роли: 2 мл. хелпер, 3 хелпер, 4 ст. хелпер, 5 разработчик, 6 создатель.
ACTIONS: dict[str, tuple[str, int, str]] = {
    "warn": ("⚠️ Варн в чате", 3, "member"),
    "mute": ("🔇 Мут в чате", 3, "member"),
    "unmute": ("🔊 Снять мут", 3, "member"),
    "unwarn_all": ("🧽 Снять все варны", 3, "member"),
    "kick": ("👢 Кик из чата", 4, "member"),
    "ban": ("⛔ Бан в чате", 4, "member"),
    "unban": ("✅ Снять бан в чате", 4, "member"),
    "block": ("🙈 Бот не отвечает игроку", 4, "player"),
    "unblock": ("🙉 Бот снова отвечает", 4, "player"),
    "global_ban": ("🚫 Бан во всех чатах", 5, "player"),
    "global_unban": ("♻️ Снять бан во всех чатах", 5, "player"),
    "balance": ("💰 Изменить баланс", 5, "player"),
    "vip": ("👑 Выдать VIP", 5, "player"),
    "rank": ("🎖 Глобальная роль", 5, "player"),
    "mark_grant": ("🏅 Выдать метку", 5, "player"),
    "mark_revoke": ("✖️ Снять метку", 5, "player"),
    "close": ("🔒 Закрыть чат", 3, "chat"),
    "open": ("🔓 Открыть чат", 3, "chat"),
    "warn_limit": ("⚠️ Лимит варнов", 4, "chat"),
    "message": ("📣 Написать от бота", 5, "chat"),
    "leave": ("🚪 Бот выходит из чата", 6, "chat"),
    "revoke_sessions": ("🔒 Завершить сессии админки", 6, "player"),
}
LINKED_MIN_RANK = 4
BULK_MAX = 50
BULK_ACTIONS = {"mark_grant": "player", "mark_revoke": "player", "unwarn_all": "member", "watch": "", "unwatch": ""}
BALANCE_CURRENCIES = {"mora": ("🪙 Мора", 0), "diamonds": ("💎 Алмазы", 2), "essence": ("🔮 Эссенция", 0), "zarniki": ("✨ Зарники", 0)}
CREATOR_ONLY_CURRENCIES = ("zarniki",)   # платная валюта: менять баланс может только создатель

_bot = None


def get_bot():
    """Клиент Bot API для действий из админки (сайт и бот живут в одном процессе, токен общий)."""
    global _bot
    if _bot is None:
        from aiogram import Bot
        _bot = Bot(token=os.environ["BOT_TOKEN"])
    return _bot


def set_bot(bot) -> None:   # для тестов
    global _bot
    _bot = bot


admin_security.use_bot(get_bot)   # тревоги владельцу уходят тем же клиентом


def _min(user: dict, action: str) -> int:
    return admin_access.min_rank(user, f"action:{action}", ACTIONS[action][1])


def _allowed(user: dict, scope: str) -> list[dict]:
    return [{"key": k, "title": t, "min_rank": _min(user, k)} for k, (t, r, s) in ACTIONS.items()
            if s == scope and user["rank"] >= _min(user, k)]


def _check(user: dict, action: str, scope: str) -> None:
    spec = ACTIONS.get(action)
    if not spec or spec[2] != scope:
        raise HTTPException(400, "Неизвестное действие.")
    need = _min(user, action)
    if user["rank"] < need:
        raise HTTPException(403, f"Для «{spec[0]}» нужна роль «{bot_rank_name(need)}» или выше.")


def _int(data: dict, key: str, default: int = 0) -> int:
    try:
        return int(data.get(key) if data.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise HTTPException(400, "Нужно целое число.")


def _reason(data: dict) -> str:
    return str(data.get("reason") or "").strip()[:200]


def _duration(data: dict) -> timedelta | None:
    """Срок в минутах; 0 или пусто — навсегда."""
    try:
        minutes = int(data.get("minutes") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Срок — целое число минут.")
    if minutes < 0 or minutes > 366 * 24 * 60:
        raise HTTPException(400, "Срок — от 1 минуты до года (или 0 — навсегда).")
    return timedelta(minutes=minutes) if minutes else None


async def _guard_target(db, user: dict, target_id: int) -> None:
    if target_id == user["id"] and user["rank"] < CREATOR:
        raise HTTPException(403, "К себе действия из админки не применяются.")
    if is_developer(target_id) and not is_developer(user["id"]):
        raise HTTPException(403, "Разработчик бота неприкосновенен.")
    target_rank = await get_bot_rank(db, target_id)
    if target_rank >= user["rank"] and user["rank"] < CREATOR and target_id != user["id"]:
        raise HTTPException(403, "Роль игрока не ниже вашей.")


async def _known_user(db, uid: int) -> None:
    async with db.execute("SELECT 1 FROM users WHERE user_tg_id = ?", (uid,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Игрок не найден.")


async def _known_chat(db, cid: int) -> None:
    async with db.execute("SELECT 1 FROM chat_settings WHERE chat_id = ?", (cid,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Чат не найден.")


def _tg_error(exc: Exception) -> HTTPException:
    logger.warning(f"bot-admin telegram call failed: {exc}")
    text = str(exc)
    if "not enough rights" in text or "administrator" in text:
        return HTTPException(409, "У бота нет прав администратора в этом чате.")
    if "kicked" in text or "not a member" in text or "chat not found" in text:
        return HTTPException(409, "Бота нет в этом чате.")
    return HTTPException(409, "Telegram отказал: " + text[:150])


# ── Поиск и карточки ─────────────────────────────────────────────────────────

@router.get("/search")
async def search(q: str = "", filter: str = "", offset: int = Query(0, ge=0, le=1_000_000), user=Depends(_user), db=Depends(get_db)):
    return await admin_people.search(db, q, flt=filter, offset=offset)


@router.get("/chats/attention")
async def chats_attention(kind: str = "", user=Depends(_user), db=Depends(get_db)):
    """Чаты, где что-то не так: бот без прав, тихо 30 дней, бота удалили."""
    return await admin_people.chats_attention(db, kind if kind in admin_people.ATTENTION_KINDS else "")


@router.get("/chats/onboarding")
async def chats_onboarding(days: int = 7, user=Depends(_user), db=Depends(get_db)):
    """Как люди подключают бота к чатам: сколько добавили, у скольких есть права и на каком шаге застревают."""
    from services import chat_setup
    return await chat_setup.funnel(db, days)


@router.get("/player/{uid}")
async def player_card(uid: int, user=Depends(_user), db=Depends(get_db)):
    card = await admin_people.player(db, uid)
    if not card:
        raise HTTPException(404, "Игрок не найден.")
    card["actions"] = {"player": _allowed(user, "player"), "member": _allowed(user, "member")}
    card["ranks"] = [{"rank": i, "name": bot_rank_name(i)} for i in range(len(BOT_RANKS))
                     if i < CREATOR and (i < user["rank"] or user["rank"] >= CREATOR)]
    card["currencies"] = [{"code": k, "title": t, "decimals": d} for k, (t, d) in BALANCE_CURRENCIES.items()
                          if k not in CREATOR_ONLY_CURRENCIES or user["rank"] >= CREATOR]
    card["history"] = await admin_people.history(db, user_id=uid)
    # Метки (в профиле игрока — «Регалии»): выданные вручную, заработанные и что можно выдать.
    card["marks"] = await marks_service.admin_view(db, uid)
    card["reports"] = await reports_service.about(db, uid)
    card["notes"] = await staff_notes.listing(db, uid, user["id"], user["rank"])
    card["confirm_rules"] = admin_security.rules()
    # Возможные связи между аккаунтами видят старшие хелперы и выше: это подсказка, а не доказательство.
    card["linked"] = await admin_people.linked(db, uid) if user["rank"] >= LINKED_MIN_RANK else None
    return card


# ── Заметки персонала ────────────────────────────────────────────────────────

@router.get("/player/{uid}/notes")
async def player_notes(uid: int, offset: int = 0, user=Depends(_user), db=Depends(get_db)):
    await _known_user(db, uid)
    return await staff_notes.listing(db, uid, user["id"], user["rank"], offset=offset)


@router.post("/player/{uid}/notes")
async def add_player_note(uid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    await _known_user(db, uid)
    try:
        await staff_notes.add(db, uid, user["id"], str(data.get("text") or ""))
    except staff_notes.NoteError as exc:
        raise HTTPException(400, str(exc))
    await admin_people.audit(db, user["id"], "note_add", user_id=uid)
    return await staff_notes.listing(db, uid, user["id"], user["rank"])


@router.delete("/player/{uid}/notes/{nid}")
async def remove_player_note(uid: int, nid: int, user=Depends(_user), db=Depends(get_db)):
    try:
        done = await staff_notes.remove(db, uid, nid, user["id"], user["rank"])
    except staff_notes.NoteError as exc:
        raise HTTPException(403, str(exc))
    if not done:
        raise HTTPException(404, "Заметка не найдена.")
    await admin_people.audit(db, user["id"], "note_remove", user_id=uid)
    return await staff_notes.listing(db, uid, user["id"], user["rank"])


# ── На контроле ──────────────────────────────────────────────────────────────

@router.post("/player/{uid}/watch")
async def player_watch(uid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    await _known_user(db, uid)
    on = bool(data.get("on"))
    reason = _reason(data)
    if on:
        if await staff_watch.add(db, uid, user["id"], reason):
            await admin_people.audit(db, user["id"], "watch_add", user_id=uid, details={"reason": reason})
    elif await staff_watch.remove(db, uid, user["id"]):
        await admin_people.audit(db, user["id"], "watch_remove", user_id=uid)
    return {"watch": await staff_watch.info(db, uid)}


@router.get("/marks")
async def grantable_marks(user=Depends(_user)):
    """Метки, которые можно выдать вручную (для окна массовой выдачи)."""
    from core.marks_v1 import GRANTABLE, MARKS
    return {"items": [{"id": m, "title": MARKS[m]["title"], "glyph": MARKS[m]["glyph"]} for m in GRANTABLE]}


# ── Массовые действия ────────────────────────────────────────────────────────

@router.post("/players/bulk")
async def players_bulk(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    """Одно действие для нескольких игроков (до 50): метка, снять варны везде, на контроль. Каждый игрок проверяется отдельно."""
    admin_access.require_staff(user)   # массовые операции затрагивают игроков всей платформы: владельцам чатов закрыты
    action = str(data.get("action") or "")
    if action not in BULK_ACTIONS:
        raise HTTPException(400, "Это действие для нескольких игроков недоступно.")
    if BULK_ACTIONS[action]:
        _check(user, action, BULK_ACTIONS[action])
    raw = data.get("ids")
    if not isinstance(raw, list):
        raise HTTPException(400, "Выберите игроков.")
    try:
        ids = list(dict.fromkeys(int(i) for i in raw))
    except (TypeError, ValueError):
        raise HTTPException(400, "ID игроков — числа.")
    if not ids:
        raise HTTPException(400, "Выберите игроков.")
    if len(ids) > BULK_MAX:
        raise HTTPException(400, f"За один раз — не больше {BULK_MAX} игроков.")
    actor, reason, mark = user["id"], _reason(data), str(data.get("mark") or "")
    if action in ("mark_grant", "mark_revoke") and not reason:
        raise HTTPException(400, "Укажите причину — она попадёт в журнал.")
    admin_security.rate_limit(user, action, len(ids))
    done, warns, failed = 0, 0, []
    names = await admin_people._names(db, ids)

    for uid in ids:
        try:
            await _known_user(db, uid)
            if action in ("mark_grant", "mark_revoke", "unwarn_all"):
                await _guard_target(db, user, uid)
            if action == "mark_grant":
                title = await marks_service.grant(db, uid, mark, actor, reason)
                await admin_people.audit(db, actor, action, user_id=uid, details={"mark": title, "reason": reason})
            elif action == "mark_revoke":
                title = await marks_service.revoke(db, uid, mark, actor, reason)
                await admin_people.audit(db, actor, action, user_id=uid, details={"mark": title, "reason": reason})
            elif action == "unwarn_all":
                async with db.execute(
                    "SELECT DISTINCT chat_id FROM user_warnings WHERE user_id = ? AND revoked_at IS NULL "
                    "AND (expires_at IS NULL OR expires_at > NOW())", (uid,)) as cur:
                    chats = [int(r[0]) for r in await cur.fetchall()]
                for cid in chats:
                    warns += await moderation.revoke_all_warns(db, cid, uid, actor)
            elif action == "watch":
                if await staff_watch.add(db, uid, actor, reason):
                    await admin_people.audit(db, actor, "watch_add", user_id=uid, details={"reason": reason})
            else:
                if await staff_watch.remove(db, uid, actor):
                    await admin_people.audit(db, actor, "watch_remove", user_id=uid)
            done += 1
        except HTTPException as exc:
            failed.append({"id": uid, "username": names.get(uid), "reason": str(exc.detail)})
        except marks_service.MarkConflict as exc:
            failed.append({"id": uid, "username": names.get(uid), "reason": str(exc)})
    if done and action in ("mark_grant", "mark_revoke"):
        await admin_security.after_action(db, user, action)
    message = f"Готово: {done} из {len(ids)}." + (f" Снято варнов: {warns}." if action == "unwarn_all" else "")
    return {"ok": True, "done": done, "failed": failed, "message": message}


@router.get("/chat/{cid}")
async def chat_card(cid: int, user=Depends(_user), db=Depends(get_db)):
    admin_access.require_chat(user, cid)
    card = await admin_people.chat(db, cid)
    if not card:
        raise HTTPException(404, "Чат не найден.")
    titles = {i["key"]: i["title"] for g in feature_switches.catalog() for i in g["items"]}
    titles |= {x["key"]: x["title"] for g in feature_switches.catalog() for i in g["items"] for x in i.get("items", [])}
    for item in card["switched_off"]:
        item["title"] = titles.get(item["key"], item["key"])
    card["actions"] = {"chat": _allowed(user, "chat"), "member": _allowed(user, "member")}
    card["history"] = await admin_people.history(db, chat_id=cid)
    return card


@router.get("/chat/{cid}/sanctions")
async def chat_sanctions(cid: int, kind: str = "bans", offset: int = 0, user=Depends(_user), db=Depends(get_db)):
    """Следующая страница банов, мутов или варнов чата («Показать ещё»)."""
    if kind not in admin_people.SANCTION_KINDS:
        raise HTTPException(400, "Нет такого списка.")
    admin_access.require_chat(user, cid)
    await _known_chat(db, cid)
    return await admin_people.chat_sanctions(db, cid, kind, offset)


# ── Действия с игроком ───────────────────────────────────────────────────────

@router.post("/player/{uid}/action")
async def player_action(uid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    spec = ACTIONS.get(action)
    scope = spec[2] if spec and spec[2] in ("player", "member") else "player"
    _check(user, action, scope)
    await _known_user(db, uid)
    await _guard_target(db, user, uid)
    admin_security.rate_limit(user, action)
    if admin_security.needs_confirm(action, data) and not admin_security.confirmed(
            uid, (await admin_people._names(db, [uid])).get(uid), data):
        raise HTTPException(400, "Для этого действия введите ID игрока (или его @ник) в поле подтверждения.")
    actor, reason = user["id"], _reason(data)

    if scope == "member":
        chat_id = int(data.get("chat_id") or 0)
        admin_access.require_chat(user, chat_id)
        await _known_chat(db, chat_id)
        bot = get_bot()
        try:
            if action == "mute":
                await moderation.do_mute(bot, db, chat_id, uid, actor, _duration(data), reason)
            elif action == "unmute":
                await moderation.do_unmute(bot, db, chat_id, uid, actor)
            elif action == "kick":
                await moderation.do_kick(bot, db, chat_id, uid, actor, reason)
            elif action == "ban":
                await moderation.do_ban(bot, db, chat_id, uid, actor, _duration(data), reason)
            elif action == "unban":
                await moderation.do_unban(bot, db, chat_id, uid, actor)
            elif action == "warn":
                count, limit = await moderation.do_warn(db, chat_id, uid, actor, _duration(data), reason)
                if count >= limit:
                    async with db.execute("SELECT chat_title FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
                        row = await cur.fetchone()
                    label = (await admin_people._names(db, [uid])).get(uid)
                    await moderation.warn_limit_alert(bot, db, chat_id, row[0] if row else None, uid,
                                                      f"@{label}" if label else f"id{uid}", count, limit)
                return {"ok": True, "message": f"Варн выдан ({count}/{limit})."}
            elif action == "unwarn_all":
                n = await moderation.revoke_all_warns(db, chat_id, uid, actor)
                return {"ok": True, "message": f"Снято варнов: {n}."}
        except HTTPException:
            raise
        except Exception as exc:
            raise _tg_error(exc)
        return {"ok": True, "message": "Готово."}

    if action in ("mark_grant", "mark_revoke"):
        mark = str(data.get("mark") or "")
        try:
            if action == "mark_grant":
                title = await marks_service.grant(db, uid, mark, actor, reason)
            else:
                title = await marks_service.revoke(db, uid, mark, actor, reason)
        except marks_service.MarkConflict as exc:
            raise HTTPException(400, str(exc))
        await admin_people.audit(db, actor, action, user_id=uid, details={"mark": title, "reason": reason})
        await admin_security.after_action(db, user, action, uid)
        return {"ok": True, "message": ("Метка выдана: " if action == "mark_grant" else "Метка снята: ") + title}

    if action == "rank":
        new = _int(data, "rank", -1)
        if not 0 <= new < CREATOR:
            raise HTTPException(400, "Нет такой роли.")
        if new >= user["rank"] and user["rank"] < CREATOR:
            raise HTTPException(403, "Можно выдать только роль ниже своей.")
        old = await get_bot_rank(db, uid)
        await db.execute("UPDATE users SET bot_rank = ? WHERE user_tg_id = ?", (new, uid))
        info = {"from": bot_rank_name(old), "to": bot_rank_name(new), "reason": reason}
        await admin_people.audit(db, actor, "rank", user_id=uid, details=info)
        await admin_security.after_action(db, user, "rank", uid, details=info)
        return {"ok": True, "message": f"Роль: {bot_rank_name(new)}."}

    if action == "balance":
        currency = str(data.get("currency") or "")
        if currency not in BALANCE_CURRENCIES:
            raise HTTPException(400, "Эту валюту из админки менять нельзя.")
        title, decimals = BALANCE_CURRENCIES[currency]
        if currency in CREATOR_ONLY_CURRENCIES and user["rank"] < CREATOR:
            raise HTTPException(403, f"{title}: баланс меняет только создатель.")
        try:
            amount = Decimal(str(data.get("amount")))
        except (InvalidOperation, ValueError):
            raise HTTPException(400, "Сумма — число, со знаком минус для списания.")
        if not amount.is_finite():
            raise HTTPException(400, "Сумма — число, со знаком минус для списания.")
        if amount == 0 or amount != amount.quantize(Decimal(1).scaleb(-decimals)):
            raise HTTPException(400, "Сумма не ноль" + (", целое число." if decimals == 0 else f", до {decimals} знаков."))
        if abs(amount) > Decimal(10_000_000):
            raise HTTPException(400, "Слишком большая сумма.")
        if not reason:
            raise HTTPException(400, "Укажите причину — она попадёт в журнал.")
        key = f"bot_admin:{actor}:{str(data.get('request_id') or uuid.uuid4())[:64]}"
        try:
            async with db.connection.transaction():
                if currency == "essence":
                    applied, _ = await skins_v3_repo.essence_apply(db, uid, int(amount), reason="bot_admin",
                                                                   reference=str(actor), idempotency_key=key)
                else:
                    applied = (await apply_balance_change(
                        db, uid, {currency: amount},
                        reason_code="bot_admin_zarniki_grant" if currency == "zarniki" and amount > 0 else "bot_admin_adjustment",
                        idempotency_key=key,
                        source_type="admin", reference_type="bot_admin", reference_id=str(actor),
                        metadata={"reason": reason})).applied
                if applied:   # повтор того же запроса (двойное нажатие) в журнал не пишется
                    await admin_people.audit(db, actor, "balance", user_id=uid,
                                             details={"currency": title, "code": currency, "amount": str(amount), "reason": reason})
        except (InsufficientBalance, ValueError):
            raise HTTPException(400, "У игрока не хватает для списания.")
        if applied:
            await admin_security.after_action(db, user, "balance", uid, details={"currency": title, "code": currency, "amount": str(amount)})
        return {"ok": True, "message": f"{title}: {'+' if amount > 0 else ''}{amount}."}

    if action == "vip":
        days = _int(data, "days")
        if not 1 <= days <= 3650:
            raise HTTPException(400, "Срок VIP — от 1 до 3650 дней.")
        request_id = str(data.get("request_id") or "")[:64]
        async with db.connection.transaction():
            if request_id:   # повтор того же запроса (ответ потерялся, нажали ещё раз) дни не добавляет
                await db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"bot_admin_vip:{actor}:{request_id}",))
                async with db.execute(
                    "SELECT 1 FROM bot_admin_actions WHERE actor_id = ? AND action = 'vip' "
                    "AND details->>'request_id' = ?", (actor, request_id)) as cur:
                    if await cur.fetchone():
                        return {"ok": True, "message": f"VIP продлён на {days} дн."}
            await vip_service.grant_vip_days(db, uid, "vip", days)
            await admin_people.audit(db, actor, "vip", user_id=uid,
                                     details={"days": days, "reason": reason, "request_id": request_id})
        await admin_security.after_action(db, user, "vip", uid)
        return {"ok": True, "message": f"VIP продлён на {days} дн."}

    if action == "block":
        days = _int(data, "days")
        if not 0 <= days <= 3650:
            raise HTTPException(400, "Срок — от 1 до 3650 дней или 0 — пока не снимут.")
        await global_moderation.block(db, uid, actor, reason, days)
        await admin_people.audit(db, actor, "block", user_id=uid, details={"days": days, "reason": reason})
        await admin_security.after_action(db, user, "block", uid)
        return {"ok": True, "message": "Бот больше не отвечает игроку."}
    if action == "unblock":
        await global_moderation.unblock(db, uid)
        await admin_people.audit(db, actor, "unblock", user_id=uid, details={"reason": reason} if reason else None)
        return {"ok": True, "message": "Бот снова отвечает игроку."}
    if action == "global_ban":
        done, failed = await global_moderation.global_ban(get_bot(), db, uid, actor, reason)
        await admin_security.after_action(db, user, "global_ban", uid)
        return {"ok": True, "message": f"Забанен в чатах: {done}" + (f", не вышло: {failed}." if failed else ".")}
    if action == "global_unban":
        done, failed = await global_moderation.global_unban(get_bot(), db, uid, actor)
        return {"ok": True, "message": f"Бан снят в чатах: {done}" + (f", не вышло: {failed}." if failed else ".")}
    if action == "revoke_sessions":
        await admin_security.revoke(db, uid)
        await admin_people.audit(db, actor, "sessions_revoke", user_id=uid)
        return {"ok": True, "message": "Сессии админки у этого сотрудника завершены: ему нужно открыть её заново."}
    raise HTTPException(400, "Неизвестное действие.")


# ── Действия с чатом ─────────────────────────────────────────────────────────

@router.post("/chat/{cid}/action")
async def chat_action(cid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    _check(user, action, "chat")
    admin_access.require_chat(user, cid)
    await _known_chat(db, cid)
    admin_security.rate_limit(user, action)
    actor, reason = user["id"], _reason(data)

    if action in ("close", "open"):
        await db.execute("UPDATE chat_settings SET is_closed = ? WHERE chat_id = ?", (action == "close", cid))
        await admin_people.audit(db, actor, action, chat_id=cid, details={"reason": reason} if reason else None)
        return {"ok": True, "message": "Чат закрыт: пишут только ранги с правом." if action == "close" else "Чат открыт."}
    if action == "warn_limit":
        limit = _int(data, "value")
        if not 1 <= limit <= 20:
            raise HTTPException(400, "Лимит варнов — от 1 до 20.")
        await db.execute("UPDATE chat_settings SET max_warnings = ? WHERE chat_id = ?", (limit, cid))
        await admin_people.audit(db, actor, "warn_limit", chat_id=cid, details={"value": limit})
        return {"ok": True, "message": f"Лимит варнов: {limit}."}
    if action == "message":
        text = str(data.get("text") or "").strip()
        if not 1 <= len(text) <= 3500:
            raise HTTPException(400, "Текст — от 1 до 3500 символов.")
        try:
            await get_bot().send_message(cid, text)
        except Exception as exc:
            raise _tg_error(exc)
        await admin_people.audit(db, actor, "message", chat_id=cid, details={"text": text[:500]})
        return {"ok": True, "message": "Отправлено."}
    if action == "leave":
        try:
            await get_bot().leave_chat(cid)
        except Exception as exc:
            raise _tg_error(exc)
        await admin_people.audit(db, actor, "leave", chat_id=cid, details={"reason": reason} if reason else None)
        return {"ok": True, "message": "Бот вышел из чата."}
    raise HTTPException(400, "Неизвестное действие.")
