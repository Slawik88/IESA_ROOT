"""services/purge.py — Чистка 2.0 (admin_audit B4/B5): единый движок для бота и сайта.

Раньше логика дублировалась в bot/handlers/purge.py и FastAPI/routers/admin.py
(два независимых SQL + рассылка), досье летели все разом (50–150 сообщений
потоком), а состояние нигде не хранилось. Теперь:
  - сессия чистки живёт в БД (purge_sessions/purge_targets) — начал в чате →
    продолжай на сайте, и наоборот; чистка с сайта производит в чате РОВНО те же
    сообщения, что и чистка из чата;
  - досье уходят порциями по BATCH_SIZE с кнопкой «Выслать ещё N» (жмёт только
    инициатор);
  - вердикты (Варн/Кик/Бан/Пропустить) фиксируются в сессии и исполняются
    одинаково из любого канала.

Отправка в Telegram — raw HTTP (Bot API), работает идентично из процесса бота
и процесса FastAPI. Без импортов bot.* / FastAPI.* — правило иерархии.
"""
import os
import re
from datetime import datetime, timedelta

import httpx
from loguru import logger

from infrastructure.repositories import moderation as mod_db
from infrastructure.repositories import purge_sessions as ps_repo
from infrastructure.repositories import routing as routing_repo
from services.membership import prune_ghosts
from services.utils import safe_html, parse_dt

# Безопасный размер порции досье: с учётом лимитов Telegram (~1 сообщение/сек
# на чат) порция уходит за ~10 секунд и не приближается к flood control.
BATCH_SIZE = 10

_WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


async def _tg(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def parse_purge_args(args: str | None) -> tuple[str, str, int]:
    """«бот чистка [DD.MM-DD.MM] [норма]» → (start_date, end_date, norm).
    По умолчанию: последние 7 дней, норма 50."""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    norm = 50
    if not args:
        return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), norm

    date_match = re.search(r"(\d{2}\.\d{2}(?:\.\d{4})?)-(\d{2}\.\d{2}(?:\.\d{4})?)", args)
    if date_match:
        try:
            d1, d2 = date_match.group(1), date_match.group(2)
            start_dt = datetime.strptime(d1, "%d.%m.%Y" if len(d1) > 5 else "%d.%m")
            end_dt = datetime.strptime(d2, "%d.%m.%Y" if len(d2) > 5 else "%d.%m")
            if len(d1) <= 5:
                start_dt = start_dt.replace(year=datetime.now().year)
            if len(d2) <= 5:
                end_dt = end_dt.replace(year=datetime.now().year)
            args = args.replace(date_match.group(0), "").strip()
        except ValueError:
            pass
    norm_match = re.search(r"\b\d+\b", args or "")
    if norm_match:
        norm = int(norm_match.group(0))
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"), norm


def _period_display(start_date: str, end_date: str) -> str:
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    days = (e - s).days + 1
    return f"{start_date} — {end_date} ({days} дн., {_WEEKDAYS_RU[s.weekday()]}–{_WEEKDAYS_RU[e.weekday()]})"


async def start_purge(db, chat_id: int, initiator_id: int,
                      start_date: str, end_date: str, norm: int) -> tuple[bool, str, dict]:
    """Полный запуск чистки: сбор кандидатов → сессия в БД → сводка в чат/админ-чат
    → первый батч досье. Возвращает (ok, сообщение, инфо-словарь)."""
    existing = await ps_repo.get_active(db, chat_id)
    if existing:
        c = await ps_repo.counts(db, existing["id"])
        return False, (
            f"⚠️ Чистка уже идёт (сессия #{existing['id']}): вердиктов "
            f"{c['decided']}/{c['total']}. Завершить: «бот конец чистки» или на сайте."
        ), {"session_id": existing["id"]}

    settings = await mod_db.get_chat_settings(db, chat_id)
    purge_min_rank = settings.get("purge_min_rank", 4)
    admin_chat_id = await routing_repo.get_admin_chat(db, chat_id)
    dest = admin_chat_id or chat_id

    # Сбор статистики (та же SQL-логика, что жила в боте и на сайте дублями)
    async with db.execute(
        """SELECT u.user_tg_id as id, u.user_tg_username as username,
               s.local_rank, s.joined_at, s.is_immune, s.immune_until, s.warnings,
               COALESCE(SUM(d.message_count), 0) as msg_sum
           FROM user_chat_stats s
           LEFT JOIN users u ON s.user_tg_id = u.user_tg_id
           LEFT JOIN daily_user_stats d ON s.user_tg_id = d.user_id
                AND d.chat_id = s.chat_tg_id AND d.date BETWEEN ? AND ?
           WHERE s.chat_tg_id = ? AND s.is_left = FALSE
           GROUP BY u.user_tg_id, s.local_rank, s.joined_at, s.is_immune,
                    s.immune_until, s.warnings""",
        (start_date, end_date, chat_id),
    ) as cursor:
        candidates = [dict(r) for r in await cursor.fetchall()]

    if candidates:
        left_ids = await prune_ghosts(db, chat_id, [c["id"] for c in candidates])
        if left_ids:
            candidates = [c for c in candidates if c["id"] not in left_ids]

    passed, failed, protected, admins = [], [], [], []
    now = datetime.now()
    for u in candidates:
        uname = u["username"] or f'ID {u["id"]}'
        link = f'<a href="tg://user?id={u["id"]}">{safe_html(uname)}</a>'
        shielded = False
        if u["immune_until"]:
            try:
                dt = parse_dt(u["immune_until"])
                shielded = bool(dt and dt > now)
            except Exception:
                pass
        if (u["local_rank"] or 0) >= purge_min_rank:
            admins.append(f"├ 👑 {link} ({u['msg_sum']} msg)")
        elif u["is_immune"]:
            protected.append(f"├ 🛡 {link} ({u['msg_sum']} msg) [иммунитет ∞]")
        elif shielded:
            dt = parse_dt(u["immune_until"])
            protected.append(f"├ 🕐 {link} ({u['msg_sum']} msg) [рест до {dt.strftime('%d.%m') if dt else '?'}]")
        elif u["msg_sum"] >= norm:
            passed.append(f"├ ✅ {link} ({u['msg_sum']} msg)")
        else:
            failed.append(u)

    session_id = await ps_repo.create(db, chat_id, initiator_id, norm,
                                      start_date, end_date, dest)
    for u in failed:
        joined = parse_dt(u["joined_at"]) if u["joined_at"] else now
        days = max(1, (now - (joined or now)).days)
        await ps_repo.add_target(db, session_id, u["id"], u["username"],
                                 int(u["msg_sum"]), days, int(u["warnings"] or 0))
    # admin_audit B5: включаем режим чистки (см. purge_gate middleware —
    # ограничение письма по purge_write_rank, если владелец его настроил)
    await mod_db.update_chat_settings(db, chat_id, is_purging=True)
    await db.commit()

    period = _period_display(start_date, end_date)
    report = (
        f"📊 <b>ИТОГИ ЧИСТКИ АКТИВНОСТИ</b> · сессия #{session_id}\n"
        f"📅 Период: <code>{period}</code>\n"
        f"🎯 Норма: <code>{norm} сообщений</code>\n\n"
    )
    if admins:
        admins[-1] = admins[-1].replace("├", "└")
        report += f"<b>👑 Освобождены от чистки (ранг ≥ {purge_min_rank}):</b>\n" + "\n".join(admins) + "\n\n"
    if passed:
        passed[-1] = passed[-1].replace("├", "└")
        report += f"<b>Прошли норму ({len(passed)}):</b>\n" + "\n".join(passed) + "\n\n"
    if protected:
        protected[-1] = protected[-1].replace("├", "└")
        report += f"<b>Под защитой ({len(protected)}):</b>\n" + "\n".join(protected) + "\n\n"
    if failed:
        lines = [f'├ <a href="tg://user?id={u["id"]}">{safe_html(u["username"] or str(u["id"]))}</a> ({u["msg_sum"]} msg)'
                 for u in failed]
        lines[-1] = lines[-1].replace("├", "└")
        report += f"<b>❌ НЕ ПРОШЛИ ({len(failed)}):</b>\n" + "\n".join(lines)
    else:
        report += "<b>❌ НЕ ПРОШЛИ:</b>\n└ <i>Таких нет, все молодцы!</i>"
    if len(report) > 4000:
        report = report[:4000] + "\n… <i>[список обрезан — полный на сайте: Админ → Чистка]</i>"

    r = await _tg("sendMessage", chat_id=dest, text=report, parse_mode="HTML")
    if not r.get("ok") and dest != chat_id:
        dest = chat_id
        await _tg("sendMessage", chat_id=dest, text=report, parse_mode="HTML")

    sent, remaining = 0, len(failed)
    if failed:
        sent, remaining = await send_next_batch(db, session_id)
    else:
        await finish_purge(db, session_id, initiator_id, auto=True)

    return True, "ok", {"session_id": session_id, "failed": len(failed),
                        "passed": len(passed), "protected": len(protected),
                        "admins": len(admins), "sent": sent, "remaining": remaining}


def _dossier_keyboard(session_id: int, user_id: int) -> dict:
    return {"inline_keyboard": [
        [{"text": "⚠️ Варн", "callback_data": f"pv:{session_id}:{user_id}:warn"},
         {"text": "👢 Кик", "callback_data": f"pv:{session_id}:{user_id}:kick"}],
        [{"text": "🔨 Бан", "callback_data": f"pv:{session_id}:{user_id}:ban"},
         {"text": "🕊 Пропустить", "callback_data": f"pv:{session_id}:{user_id}:skip"}],
    ]}


async def send_next_batch(db, session_id: int, requester_id: int | None = None) -> tuple[int, int]:
    """Шлёт следующую порцию досье (BATCH_SIZE). requester_id — если задан,
    проверяется, что это инициатор сессии. Возвращает (отправлено, осталось)."""
    session = await ps_repo.get_by_id(db, session_id)
    if not session or session["status"] != "active":
        return 0, 0
    if requester_id is not None and requester_id != session["initiator_id"]:
        return -1, -1  # маркер «не инициатор» для вызывающего

    dest = session["dest_chat_id"] or session["chat_id"]
    batch = await ps_repo.unsent_targets(db, session_id, BATCH_SIZE)
    sent = 0
    for t in batch:
        uname = safe_html(t["username"] or f"ID {t['user_id']}")
        dossier = (
            f'🗂 <b>ДОСЬЕ НАРУШИТЕЛЯ:</b> <a href="tg://user?id={t["user_id"]}">{uname}</a>\n'
            f"├ Сообщений за период: <b>{t['msg_count']}</b> из {session['norm']}\n"
            f"├ Дней в чате: <b>{t['days_in_chat']}</b>\n"
            f"└ Текущие варны: <b>{t['warns']}</b>\n\n"
            f"<i>Вердикт выносит инициатор чистки:</i>"
        )
        r = await _tg("sendMessage", chat_id=dest, text=dossier, parse_mode="HTML",
                      reply_markup=_dossier_keyboard(session_id, t["user_id"]))
        if r.get("ok"):
            await ps_repo.mark_sent(db, session_id, t["user_id"])
            sent += 1
        else:
            logger.warning(f"purge dossier send fail: {r}")
    await db.commit()

    c = await ps_repo.counts(db, session_id)
    remaining = c["total"] - c["sent"]
    if remaining > 0:
        n = min(BATCH_SIZE, remaining)
        await _tg("sendMessage", chat_id=dest, parse_mode="HTML",
                  text=(f"📨 Выдано досье: <b>{c['sent']}/{c['total']}</b>. "
                        f"Осталось {remaining}."),
                  reply_markup={"inline_keyboard": [[
                      {"text": f"📨 Выслать ещё {n}", "callback_data": f"pm:{session_id}"}]]})
    else:
        await _tg("sendMessage", chat_id=dest, parse_mode="HTML",
                  text=(f"✅ Все досье выданы (<b>{c['total']}</b>). "
                        f"Вердиктов: {c['decided']}/{c['total']}.\n"
                        f"<i>Завершить: «бот конец чистки» (или на сайте: Админ → Чистка). "
                        f"Статус: «бот чистка статус»</i>"))
    return sent, remaining


_VERDICT_LABEL = {"warn": "⚠️ ВАРН", "kick": "👢 ИСКЛЮЧЕНИЕ", "ban": "🔨 БАН", "skip": "🕊 ПРОЩЕНО"}


async def apply_verdict(db, session_id: int, target_id: int, action: str,
                        actor_id: int, developer_id: int = 0) -> tuple[bool, str]:
    """Вердикт по цели: только инициатор сессии; «Бан»/«Кик» дополнительно
    требуют порогов rank_ban/rank_kick (согласовано с admin_audit B1).
    Исполняется одинаково из чата (кнопка) и с сайта."""
    session = await ps_repo.get_by_id(db, session_id)
    if not session or session["status"] != "active":
        return False, "Сессия чистки уже завершена."
    if actor_id != session["initiator_id"] and actor_id != developer_id:
        return False, "Вердикт выносит только инициатор чистки."
    if action not in _VERDICT_LABEL:
        return False, "Неизвестный вердикт."

    settings = await mod_db.get_chat_settings(db, session["chat_id"])
    async with db.execute(
        "SELECT COALESCE(local_rank, 0) FROM user_chat_stats "
        "WHERE user_tg_id = ? AND chat_tg_id = ?",
        (actor_id, session["chat_id"]),
    ) as c:
        row = await c.fetchone()
    actor_rank = int(row[0]) if row else 0
    if actor_id == developer_id:
        actor_rank = 6
    need = {"ban": settings.get("rank_ban", 2), "kick": settings.get("rank_kick", 1)}.get(action, 0)
    if actor_rank < need:
        return False, f"Для этого вердикта нужен ранг {need}+ (у вас {actor_rank})."

    if not await ps_repo.set_verdict(db, session_id, target_id, action, actor_id):
        t = await ps_repo.get_target(db, session_id, target_id)
        return False, f"Вердикт уже вынесен: {_VERDICT_LABEL.get((t or {}).get('verdict', ''), '?')}."

    chat_id = session["chat_id"]
    ok_exec = True
    if action == "ban":
        r = await _tg("banChatMember", chat_id=chat_id, user_id=target_id)
        ok_exec = bool(r.get("ok"))
        if ok_exec:
            await mod_db.log_moderation_action(db, chat_id, target_id, actor_id, "ban")
            await mod_db.clear_warns(db, chat_id, target_id)
    elif action == "kick":
        r = await _tg("banChatMember", chat_id=chat_id, user_id=target_id)
        await _tg("unbanChatMember", chat_id=chat_id, user_id=target_id)
        ok_exec = bool(r.get("ok"))
        if ok_exec:
            await mod_db.log_moderation_action(db, chat_id, target_id, actor_id, "kick")
            await mod_db.clear_warns(db, chat_id, target_id)
    elif action == "warn":
        await mod_db.add_warn(db, chat_id, target_id, actor_id, "Чистка активности")
    await db.commit()

    label = _VERDICT_LABEL[action]
    text = (f'{label} для <a href="tg://user?id={target_id}">нарушителя</a> '
            f'(чистка #{session_id}).')
    if not ok_exec:
        text += " ⚠️ <i>Telegram-действие не удалось (нет прав у бота?), вердикт записан.</i>"
    # Объявление в основной чат (даже если досье в админ-чате) — как раньше
    await _tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")
    return True, text


async def finish_purge(db, session_id: int, actor_id: int, auto: bool = False) -> str:
    """Завершение: снять режим чистки, закрыть сессию, итоговая сводка.
    ВАЖНО (admin_audit B5): права чата больше НЕ трогаются — старая версия
    «бот конец чистки» молча сносила ручные ограничения владельца."""
    session = await ps_repo.get_by_id(db, session_id)
    if not session:
        return "Сессия не найдена."
    await ps_repo.finish(db, session_id, "done")
    await mod_db.update_chat_settings(db, session["chat_id"], is_purging=False)
    await db.commit()
    c = await ps_repo.counts(db, session_id)
    summary = (
        f"✅ <b>Чистка #{session_id} завершена.</b>\n"
        f"Вердикты: ⚠️ {c['warned']} · 👢 {c['kicked']} · 🔨 {c['banned']} · 🕊 {c['skipped']}"
        + (f" · без вердикта: {c['total'] - c['decided']}" if c['total'] > c['decided'] else "")
    )
    if not auto:
        dest = session["dest_chat_id"] or session["chat_id"]
        await _tg("sendMessage", chat_id=dest, text=summary, parse_mode="HTML")
    return summary


async def get_status(db, chat_id: int) -> dict | None:
    """Статус активной сессии (для «бот чистка статус» и сайта)."""
    session = await ps_repo.get_active(db, chat_id)
    if not session:
        return None
    c = await ps_repo.counts(db, session["id"])
    targets = await ps_repo.list_targets(db, session["id"])
    return {"session": session, "counts": c, "targets": targets}
