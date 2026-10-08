"""Раздел «Игроки и чаты»: поиск, карточки и действия персонала.

Смотреть карточки может любой хелпер; каждое действие — со своей минимальной ролью (ACTIONS).
К разработчику бота и к персоналу не ниже своей роли действия не применяются.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException
from loguru import logger

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from bot.chat import moderation
from bot.chat.access import is_developer
from bot.chat.global_ranks import BOT_RANKS, CREATOR, bot_rank_name, get_bot_rank
from core.economy_contract import InsufficientBalance
from infrastructure.repositories import skins_v3 as skins_v3_repo
from infrastructure.repositories.economy_ledger import apply_balance_change
from services import admin_people, feature_switches, global_moderation
from services import vip as vip_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
_user = section("people")

# Действие -> (подпись, минимальная глобальная роль, к чему применяется).
# Роли: 2 мл. хелпер, 3 хелпер, 4 ст. хелпер, 5 разработчик, 6 создатель.
ACTIONS: dict[str, tuple[str, int, str]] = {
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
    "close": ("🔒 Закрыть чат", 3, "chat"),
    "open": ("🔓 Открыть чат", 3, "chat"),
    "warn_limit": ("⚠️ Лимит варнов", 4, "chat"),
    "message": ("📣 Написать от бота", 5, "chat"),
    "leave": ("🚪 Бот выходит из чата", 6, "chat"),
}
BALANCE_CURRENCIES = {"mora": ("🪙 Мора", 0), "diamonds": ("💎 Алмазы", 2), "essence": ("🔮 Эссенция", 0)}

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


def _allowed(rank: int, scope: str) -> list[dict]:
    return [{"key": k, "title": t, "min_rank": r} for k, (t, r, s) in ACTIONS.items() if s == scope and rank >= r]


def _check(user: dict, action: str, scope: str) -> None:
    spec = ACTIONS.get(action)
    if not spec or spec[2] != scope:
        raise HTTPException(400, "Неизвестное действие.")
    if user["rank"] < spec[1]:
        raise HTTPException(403, f"Для «{spec[0]}» нужна роль «{bot_rank_name(spec[1])}» или выше.")


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
async def search(q: str = "", user=Depends(_user), db=Depends(get_db)):
    return await admin_people.search(db, q)


@router.get("/player/{uid}")
async def player_card(uid: int, user=Depends(_user), db=Depends(get_db)):
    card = await admin_people.player(db, uid)
    if not card:
        raise HTTPException(404, "Игрок не найден.")
    card["actions"] = {"player": _allowed(user["rank"], "player"), "member": _allowed(user["rank"], "member")}
    card["ranks"] = [{"rank": i, "name": bot_rank_name(i)} for i in range(len(BOT_RANKS))
                     if i < CREATOR and (i < user["rank"] or user["rank"] >= CREATOR)]
    card["currencies"] = [{"code": k, "title": t, "decimals": d} for k, (t, d) in BALANCE_CURRENCIES.items()]
    card["history"] = await admin_people.history(db, user_id=uid)
    return card


@router.get("/chat/{cid}")
async def chat_card(cid: int, user=Depends(_user), db=Depends(get_db)):
    card = await admin_people.chat(db, cid)
    if not card:
        raise HTTPException(404, "Чат не найден.")
    titles = {i["key"]: i["title"] for g in feature_switches.catalog() for i in g["items"]}
    titles |= {x["key"]: x["title"] for g in feature_switches.catalog() for i in g["items"] for x in i.get("items", [])}
    for item in card["switched_off"]:
        item["title"] = titles.get(item["key"], item["key"])
    card["actions"] = {"chat": _allowed(user["rank"], "chat"), "member": _allowed(user["rank"], "member")}
    card["history"] = await admin_people.history(db, chat_id=cid)
    return card


# ── Действия с игроком ───────────────────────────────────────────────────────

@router.post("/player/{uid}/action")
async def player_action(uid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    spec = ACTIONS.get(action)
    scope = spec[2] if spec and spec[2] in ("player", "member") else "player"
    _check(user, action, scope)
    await _known_user(db, uid)
    await _guard_target(db, user, uid)
    actor, reason = user["id"], _reason(data)

    if scope == "member":
        chat_id = int(data.get("chat_id") or 0)
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
            elif action == "unwarn_all":
                n = await moderation.revoke_all_warns(db, chat_id, uid, actor)
                return {"ok": True, "message": f"Снято варнов: {n}."}
        except HTTPException:
            raise
        except Exception as exc:
            raise _tg_error(exc)
        return {"ok": True, "message": "Готово."}

    if action == "rank":
        new = int(data.get("rank") if data.get("rank") is not None else -1)
        if not 0 <= new < CREATOR:
            raise HTTPException(400, "Нет такой роли.")
        if new >= user["rank"] and user["rank"] < CREATOR:
            raise HTTPException(403, "Можно выдать только роль ниже своей.")
        old = await get_bot_rank(db, uid)
        await db.execute("UPDATE users SET bot_rank = ? WHERE user_tg_id = ?", (new, uid))
        await admin_people.audit(db, actor, "rank", user_id=uid,
                                 details={"from": bot_rank_name(old), "to": bot_rank_name(new), "reason": reason})
        return {"ok": True, "message": f"Роль: {bot_rank_name(new)}."}

    if action == "balance":
        currency = str(data.get("currency") or "")
        if currency not in BALANCE_CURRENCIES:
            raise HTTPException(400, "Эту валюту из админки менять нельзя.")
        title, decimals = BALANCE_CURRENCIES[currency]
        try:
            amount = Decimal(str(data.get("amount")))
        except (InvalidOperation, ValueError):
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
                        db, uid, {currency: amount}, reason_code="bot_admin_adjustment", idempotency_key=key,
                        source_type="admin", reference_type="bot_admin", reference_id=str(actor),
                        metadata={"reason": reason})).applied
                if applied:   # повтор того же запроса (двойное нажатие) в журнал не пишется
                    await admin_people.audit(db, actor, "balance", user_id=uid,
                                             details={"currency": title, "amount": str(amount), "reason": reason})
        except (InsufficientBalance, ValueError):
            raise HTTPException(400, "У игрока не хватает для списания.")
        return {"ok": True, "message": f"{title}: {'+' if amount > 0 else ''}{amount}."}

    if action == "vip":
        days = int(data.get("days") or 0)
        if not 1 <= days <= 3650:
            raise HTTPException(400, "Срок VIP — от 1 до 3650 дней.")
        async with db.connection.transaction():
            await vip_service.grant_vip_days(db, uid, "vip", days)
            await admin_people.audit(db, actor, "vip", user_id=uid, details={"days": days, "reason": reason})
        return {"ok": True, "message": f"VIP продлён на {days} дн."}

    if action == "block":
        days = int(data.get("days") or 0)
        await global_moderation.block(db, uid, actor, reason, max(0, days))
        await admin_people.audit(db, actor, "block", user_id=uid, details={"days": days, "reason": reason})
        return {"ok": True, "message": "Бот больше не отвечает игроку."}
    if action == "unblock":
        await global_moderation.unblock(db, uid)
        await admin_people.audit(db, actor, "unblock", user_id=uid, details={"reason": reason} if reason else None)
        return {"ok": True, "message": "Бот снова отвечает игроку."}
    if action == "global_ban":
        done, failed = await global_moderation.global_ban(get_bot(), db, uid, actor, reason)
        return {"ok": True, "message": f"Забанен в чатах: {done}" + (f", не вышло: {failed}." if failed else ".")}
    if action == "global_unban":
        done, failed = await global_moderation.global_unban(get_bot(), db, uid, actor)
        return {"ok": True, "message": f"Бан снят в чатах: {done}" + (f", не вышло: {failed}." if failed else ".")}
    raise HTTPException(400, "Неизвестное действие.")


# ── Действия с чатом ─────────────────────────────────────────────────────────

@router.post("/chat/{cid}/action")
async def chat_action(cid: int, data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    _check(user, action, "chat")
    await _known_chat(db, cid)
    actor, reason = user["id"], _reason(data)

    if action in ("close", "open"):
        await db.execute("UPDATE chat_settings SET is_closed = ? WHERE chat_id = ?", (action == "close", cid))
        await admin_people.audit(db, actor, action, chat_id=cid, details={"reason": reason} if reason else None)
        return {"ok": True, "message": "Чат закрыт: пишут только ранги с правом." if action == "close" else "Чат открыт."}
    if action == "warn_limit":
        limit = int(data.get("value") or 0)
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
