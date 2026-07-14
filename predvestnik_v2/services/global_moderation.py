# services/global_moderation.py
# Глобальная модерация экосистемы бота (Implementation Block 6.3).
# Без bot.* / FastAPI.* импортов — bot передаётся параметром (aiogram.Bot) для отправки уведомлений.

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from infrastructure.repositories import global_moderation as repo
from infrastructure.repositories import users as users_repo
from services import global_permissions as gperm

SANCTION_LABELS: dict[str, str] = {
    "warn": "предупреждение",
    "restrict": "ограничение",
    "ban": "бан",
}


async def is_user_banned(db, user_id: int) -> bool:
    restriction = await repo.get_active_restriction(db, "user", user_id)
    return bool(restriction and restriction["sanction_type"] == "ban")


async def is_chat_banned(db, chat_id: int) -> bool:
    restriction = await repo.get_active_restriction(db, "chat", chat_id)
    return bool(restriction and restriction["sanction_type"] == "ban")


async def get_user_restriction(db, user_id: int) -> dict | None:
    """Активная restrict для юзера (не ban — ban проверяется отдельно/раньше)."""
    restriction = await repo.get_active_restriction(db, "user", user_id)
    if restriction and restriction["sanction_type"] == "restrict":
        return restriction
    return None


async def get_chat_restriction(db, chat_id: int) -> dict | None:
    """Активная restrict для чата (не ban — ban проверяется отдельно/раньше)."""
    restriction = await repo.get_active_restriction(db, "chat", chat_id)
    if restriction and restriction["sanction_type"] == "restrict":
        return restriction
    return None


def restriction_message(restriction: dict) -> str:
    expires_at = restriction.get("expires_at")
    until = "навсегда" if not expires_at else f"до {expires_at:%d.%m.%Y}"
    reason = restriction.get("reason") or "без указания причины"
    return (
        f"🚫 Экономические команды недоступны ({reason}) — {until}.\n"
        f"Оспорить: «бот апелляция <текст>»"
    )


async def notify_sanction(db, bot, target_type: str, target_id: int, sanction_type: str,
                           reason: str | None, action: str) -> None:
    """action: 'issued' | 'revoked'."""
    label = SANCTION_LABELS.get(sanction_type, sanction_type)
    # Имя цели — чтобы в групповом чате было видно, КОМУ санкция (а не безличное «вам»).
    who = ""
    if target_type == "user":
        uname = await users_repo.get_user_name(db, target_id)  # username ИЛИ строка-id (фолбэк)
        who = f"@{uname}" if uname and uname != str(target_id) else f"ID{target_id}"
    if action == "issued":
        reason_part = f"\nПричина: {reason}" if reason else ""
        if target_type == "user":
            text = f"⚠️ Глобальная модерация: игроку {who} выдана санкция «{label}».{reason_part}"
        else:
            text = f"⚠️ Глобальная модерация: этому чату выдана санкция «{label}».{reason_part}"
    else:
        if target_type == "user":
            text = f"✅ Глобальная модерация: с игрока {who} снята санкция «{label}»."
        else:
            text = f"✅ Глобальная модерация: с этого чата снята санкция «{label}»."

    if target_type == "user":
        for chat_id in await repo.get_user_chat_ids(db, target_id):
            try:
                await bot.send_message(chat_id, text)
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
    else:
        try:
            await bot.send_message(target_id, text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass


async def issue_global_sanction(db, bot, actor_id: int, actor_rank: int, target_type: str, target_id: int,
                                 sanction_type: str, reason: str | None, expires_at=None,
                                 target_global_rank: int = 0,
                                 photos_json: str = "[]") -> tuple[bool, str, int]:
    """can_issue_global_sanction → repo.issue_sanction.

    admin_audit B1: для target_type='user' уведомления по чатам БОЛЬШЕ НЕ шлются
    автоматически — модератор выбирает каналы (панель в боте / чекбоксы на сайте),
    затем send_sanction_notices(). Нарушителю ВСЕГДА сразу уходит ЛС-инструкция
    по апелляции (send_appeal_instruction). Для 'chat' — как раньше, немедленно.
    Возвращает (ok, message, sanction_id)."""
    # БЛОК 21.2: права настраиваются по-функционно (global_rank_permissions),
    # антипир внутри can_sanction. Единая проверка для бота и сайта.
    if not await gperm.can_sanction(db, actor_rank, target_type, sanction_type, target_global_rank):
        return False, "❌ Недостаточно прав для этой санкции.", 0

    if reason:
        reason = reason[:9999]   # admin_audit B1: лимит причины 9999 символов

    sanction_id = await repo.issue_sanction(db, target_type, target_id, sanction_type, reason, actor_id, expires_at)
    if photos_json and photos_json != "[]":
        await repo.set_sanction_photos(db, sanction_id, photos_json)

    if target_type == "chat":
        await notify_sanction(db, bot, target_type, target_id, sanction_type, reason, "issued")

    label = SANCTION_LABELS.get(sanction_type, sanction_type)
    return True, f"✅ Глобальная санкция «{label}» выдана (#{sanction_id}).", sanction_id


# ── admin_audit B1 «Апелляции 2.0» ────────────────────────────────────────────
# Отправка через raw HTTP (Bot API): одинаково работает из процесса бота и из
# FastAPI-роутеров (у веба нет живого aiogram.Bot).

async def _tg(method: str, **kwargs) -> dict:
    import os
    import httpx
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception:
        return {"ok": False}


def _webapp_url() -> str:
    import os
    return f"https://t.me/{os.getenv('BOT_USERNAME', 'IIIPredvestnikIIIBot')}?startapp=appeal"


async def send_appeal_instruction(db, user_id: int, sanction: dict) -> bool:
    """ЛС нарушителю сразу после санкции: что случилось и КАК оспорить.
    admin_audit B1: «юзер должен сразу понять, как действовать»."""
    label = SANCTION_LABELS.get(sanction["sanction_type"], sanction["sanction_type"])
    until = "бессрочно"
    if sanction.get("expires_at"):
        try:
            until = f"до {sanction['expires_at']:%d.%m.%Y %H:%M}"
        except Exception:
            until = str(sanction.get("expires_at"))
    reason = sanction.get("reason") or "не указана"
    text = (
        f"⚠️ <b>Вам выдана глобальная санкция: {label}</b> ({until})\n"
        f"📝 Причина: {reason[:1000]}\n\n"
        f"<b>Как оспорить (в любой момент):</b>\n"
        f"1️⃣ Прямо здесь, в ЛС: <code>бот апелляция, ваш текст</code>\n"
        f"   Можно приложить фото: отправьте фото с подписью-текстом.\n"
        f"2️⃣ Или на сайте — кнопка ниже.\n\n"
        f"Модерация ответит здесь же — диалог останется открыт, пока дело не закроют."
    )
    r = await _tg("sendMessage", chat_id=user_id, text=text, parse_mode="HTML",
                  reply_markup={"inline_keyboard": [[
                      {"text": "🌐 Подать апелляцию на сайте", "url": _webapp_url()}]]})
    return bool(r.get("ok"))


async def send_sanction_notices(db, sanction_id: int, chat_ids) -> int:
    """Рассылка уведомления о санкции по ВЫБРАННЫМ каналам (admin_audit B1:
    все чаты / конкретный чат / несколько). chat_ids: list[int] | 'all'."""
    sanction = await repo.get_sanction_by_id(db, sanction_id)
    if not sanction:
        return 0
    label = SANCTION_LABELS.get(sanction["sanction_type"], sanction["sanction_type"])
    uname = await users_repo.get_user_name(db, sanction["target_id"])
    who = f"@{uname}" if uname and uname != str(sanction["target_id"]) else f"ID{sanction['target_id']}"
    reason_part = f"\nПричина: {(sanction.get('reason') or '')[:500]}" if sanction.get("reason") else ""
    text = (f"⚠️ Глобальная модерация: игроку {who} выдана санкция «{label}».{reason_part}\n"
            f"📨 Инструкция по апелляции выслана нарушителю в ЛС.")
    if chat_ids == "all":
        chat_ids = await repo.get_user_chat_ids(db, sanction["target_id"])
    sent = 0
    for cid in chat_ids:
        r = await _tg("sendMessage", chat_id=cid, text=text)
        if r.get("ok"):
            sent += 1
    return sent


async def appeal_add_message(db, user_id: int, text: str,
                             photo_ids: list[str] | None = None) -> tuple[bool, str, int]:
    """Сообщение игрока в нить апелляции: продолжает открытую или создаёт новую
    (нужна активная санкция). Возвращает (ok, msg, appeal_id)."""
    import json as _json
    text = (text or "").strip()[:9999]
    photos = _json.dumps(photo_ids or [])
    appeal = await repo.get_open_appeal(db, user_id)
    if appeal:
        await repo.add_appeal_message(db, appeal["id"], user_id, False, text, photos)
        return True, "✉️ Сообщение добавлено в вашу апелляцию.", appeal["id"]
    sanction = await repo.get_active_sanction_for_user(db, user_id)
    if not sanction:
        return False, "У вас нет активных глобальных санкций — оспаривать нечего.", 0
    if not text and not photo_ids:
        return False, "Опишите, почему санкция несправедлива.", 0
    appeal_id = await repo.create_appeal(db, user_id, sanction["id"], text or "(фото)")
    await repo.add_appeal_message(db, appeal_id, user_id, False, text, photos)
    return True, f"✅ Апелляция #{appeal_id} подана. Ответ придёт сюда, в ЛС.", appeal_id


async def notify_staff_about_appeal(db, appeal_id: int, user_id: int, text: str,
                                    developer_id: int) -> None:
    """Уведомить модерацию о новом сообщении в апелляции: разработчику + автору санкции."""
    appeal = await repo.get_appeal_by_id(db, appeal_id)
    staff_ids = {developer_id} if developer_id else set()
    if appeal:
        s = await repo.get_sanction_by_id(db, appeal["sanction_id"])
        if s and s.get("issued_by"):
            staff_ids.add(int(s["issued_by"]))
    note = (f"📨 <b>Апелляция #{appeal_id}</b> — новое сообщение от <code>{user_id}</code>:\n"
            f"{(text or '(фото)')[:800]}\n\n"
            f"<i>Ответить: <code>бот апелляция ответ, {appeal_id}, текст</code> · "
            f"Закрыть: <code>бот апелляция закрыть, {appeal_id}, решение</code> · или на сайте</i>")
    for sid in staff_ids:
        await _tg("sendMessage", chat_id=sid, text=note, parse_mode="HTML")


async def staff_reply_appeal(db, appeal_id: int, staff_id: int, text: str,
                             photo_ids: list[str] | None = None) -> tuple[bool, str]:
    """Ответ модерации в нить: записывается и доставляется игроку в ЛС."""
    import json as _json
    appeal = await repo.get_appeal_by_id(db, appeal_id)
    if not appeal:
        return False, "Апелляция не найдена."
    if appeal["status"] not in ("pending",):
        return False, f"Апелляция уже закрыта (статус: {appeal['status']})."
    text = (text or "").strip()[:9999]
    await repo.add_appeal_message(db, appeal_id, staff_id, True, text,
                                  _json.dumps(photo_ids or []))
    body = (f"💬 <b>Ответ модерации по апелляции #{appeal_id}:</b>\n{text}\n\n"
            f"<i>Ответить: <code>бот апелляция, текст</code> (или фото с подписью)</i>")
    r = await _tg("sendMessage", chat_id=appeal["user_id"], text=body, parse_mode="HTML")
    if photo_ids:
        for pid in photo_ids:
            await _tg("sendPhoto", chat_id=appeal["user_id"], photo=pid)
    return True, ("✅ Ответ отправлен игроку." if r.get("ok")
                  else "⚠️ Записано, но ЛС игрока закрыта — он увидит на сайте.")


async def close_appeal(db, appeal_id: int, staff_id: int, resolution: str | None,
                       status: str = "closed") -> tuple[bool, str]:
    """Закрыть дело (status: closed/accepted/rejected) + финальное слово игроку."""
    appeal = await repo.get_appeal_by_id(db, appeal_id)
    if not appeal:
        return False, "Апелляция не найдена."
    if appeal["status"] != "pending":
        return False, f"Уже закрыта (статус: {appeal['status']})."
    resolution = (resolution or "").strip()[:9999]
    if resolution:
        import json as _json
        await repo.add_appeal_message(db, appeal_id, staff_id, True,
                                      f"[Закрытие дела] {resolution}", _json.dumps([]))
    await repo.resolve_appeal(db, appeal_id, status, staff_id)
    label = {"closed": "закрыта", "accepted": "принята ✅", "rejected": "отклонена ❌"}.get(status, status)
    await _tg("sendMessage", chat_id=appeal["user_id"], parse_mode="HTML",
              text=(f"📪 <b>Апелляция #{appeal_id} {label}.</b>"
                    + (f"\n💬 {resolution}" if resolution else "")
                    + "\n<i>Диалог по этому делу закрыт. Новая санкция — новая апелляция.</i>"))
    return True, f"✅ Апелляция #{appeal_id} {label}."


async def revoke_global_sanction(db, bot, actor_id: int, actor_rank: int, sanction_id: int) -> tuple[bool, str]:
    """проверка прав по sanction.sanction_type/target → repo.revoke_sanction → notify(action='revoked')."""
    sanction = await repo.get_sanction_by_id(db, sanction_id)
    if not sanction:
        return False, "❌ Санкция с таким ID не найдена."
    if sanction["revoked_at"] is not None:
        return False, "⚠️ Санкция уже снята."

    target_global_rank = 0
    if sanction["target_type"] == "user":
        target_global_rank = await users_repo.get_global_rank(db, sanction["target_id"])

    # Снятие требует того же права, что выдача этого типа санкции (симметрия).
    if not await gperm.can_sanction(db, actor_rank, sanction["target_type"], sanction["sanction_type"], target_global_rank):
        return False, "❌ Недостаточно прав для снятия этой санкции."

    if not await repo.revoke_sanction(db, sanction_id, actor_id):
        return False, "⚠️ Санкция уже снята."

    await notify_sanction(db, bot, sanction["target_type"], sanction["target_id"],
                           sanction["sanction_type"], sanction["reason"], "revoked")

    label = SANCTION_LABELS.get(sanction["sanction_type"], sanction["sanction_type"])
    return True, f"✅ Глобальная санкция «{label}» (#{sanction_id}) снята."
