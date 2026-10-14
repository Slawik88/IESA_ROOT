"""services/account_deletion.py — admin_audit C1b: удаление аккаунтов.

Конструкция (согласована):
  САМОУДАЛЕНИЕ (анти-взлом/анти-случайность, три независимых барьера):
    1) запрос на сайте → 6-значный код уходит В ЛС БОТА (подтверждение владения
       Telegram-аккаунтом, а не только сессией сайта);
    2) код + контрольная фраза «УДАЛИТЬ АККАУНТ», введённая вручную;
    3) 24 часа «остывания»: удаление происходит не сразу — в ЛС уходит алерт,
       «бот отменить удаление» (или кнопка на сайте) отменяет процесс.
  АВТО-НЕАКТИВ: настройка в профиле (6 мес / 1 год / 2 года, по умолчанию 1 год);
    за 14 дней до срока — ЛС-предупреждение; любое сообщение в чате обнуляет
    отсчёт (активность = MAX(last_message_at) по чатам).
  ВОССТАНОВЛЕНИЕ: 14 дней после удаления данные НЕ трогаются — «бот восстановить
    аккаунт» в ЛС или кнопка на сайте возвращают всё как было.
  ФИНАЛИЗАЦИЯ: по истечении окна — очистка игровых данных (питомцы, инвентарь,
    косметика, балансы, браки, кланы...); аудит-логи (санкции, moderation_logs,
    wallet_log) сознательно ОСТАЮТСЯ.

Отправка в ЛС — raw HTTP (работает из бота и веба одинаково).
"""
import os
import random

import httpx
from loguru import logger
from infrastructure.repositories import chests_v1 as chest_repo

from core.constants import (
    ACCOUNT_DELETE_COOLING_HOURS, ACCOUNT_DELETE_INACTIVITY_CHOICES,
    ACCOUNT_DELETE_PHRASE, ACCOUNT_DELETE_RESTORE_DAYS, ACCOUNT_DELETE_WARN_DAYS,
)


async def _tg(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception:
        return {"ok": False}


async def get_state(db, user_id: int) -> dict:
    async with db.execute(
        "SELECT deleted_at, COALESCE(delete_after_days, 365) AS delete_after_days "
        "FROM users WHERE user_tg_id = ?", (user_id,)
    ) as c:
        u = await c.fetchone()
    async with db.execute(
        "SELECT * FROM account_deletions WHERE user_id = ?", (user_id,)
    ) as c:
        d = await c.fetchone()
    return {
        "deleted_at": u[0] if u else None,
        "delete_after_days": int(u[1]) if u else 365,
        "deletion": dict(d) if d else None,
    }


async def _has_active_marriage(db, user_id: int) -> bool:
    """Account deletion must never dissolve a family as a side effect."""
    async with db.execute(
        "SELECT 1 FROM marriage_members mm JOIN marriages m ON m.id = mm.marriage_id "
        "WHERE mm.user_id = ? AND m.ended_at IS NULL LIMIT 1",
        (user_id,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def set_inactivity_days(db, user_id: int, days: int) -> tuple[bool, str]:
    if days not in ACCOUNT_DELETE_INACTIVITY_CHOICES:
        return False, f"Допустимо: {', '.join(map(str, ACCOUNT_DELETE_INACTIVITY_CHOICES))} дней."
    await db.execute(
        "UPDATE users SET delete_after_days = ? WHERE user_tg_id = ?", (days, user_id))
    await db.commit()
    label = {180: "6 месяцев", 365: "1 год", 730: "2 года"}.get(days, f"{days} дн.")
    return True, f"✅ Аккаунт будет удалён после {label} полного неактива (с предупреждением в ЛС)."


async def request_deletion(db, user_id: int) -> tuple[bool, str]:
    """Шаг 1: код в ЛС бота."""
    if await _has_active_marriage(db, user_id):
        return False, (
            "Нельзя удалить аккаунт, пока он состоит в браке: это могло бы удалить "
            "семейное состояние партнёра. Сначала завершите брак безопасно."
        )
    st = await get_state(db, user_id)
    if st["deleted_at"]:
        return False, "Аккаунт уже удалён — доступно восстановление."
    d = st["deletion"]
    if d and d["status"] in ("confirming", "cooling") and d.get("source") == "self":
        return False, "Процесс удаления уже запущен. Отменить: «бот отменить удаление»."
    code = f"{random.randint(0, 999999):06d}"
    await db.execute("DELETE FROM account_deletions WHERE user_id = ?", (user_id,))
    await db.execute(
        "INSERT INTO account_deletions (user_id, source, status, confirm_code) "
        "VALUES (?, 'self', 'confirming', ?)",
        (user_id, code),
    )
    await db.commit()
    r = await _tg("sendMessage", chat_id=user_id, parse_mode="HTML", text=(
        f"🗑 <b>Запрошено удаление аккаунта.</b>\n"
        f"Код подтверждения: <code>{code}</code>\n\n"
        f"Введите его на сайте вместе с фразой «{ACCOUNT_DELETE_PHRASE}».\n"
        f"⚠️ Если это не вы — просто игнорируйте: без кода ничего не произойдёт, "
        f"и смените пароль Telegram."))
    if not r.get("ok"):
        await db.execute("DELETE FROM account_deletions WHERE user_id = ?", (user_id,))
        await db.commit()
        return False, "Не удалось отправить код в ЛС — откройте диалог с ботом и попробуйте снова."
    return True, "📨 Код подтверждения отправлен вам в ЛС бота."


async def confirm_deletion(db, user_id: int, code: str, phrase: str) -> tuple[bool, str]:
    """Шаг 2: код + фраза → 24ч остывания (алерт в ЛС, отмена в любой момент)."""
    st = await get_state(db, user_id)
    d = st["deletion"]
    if not d or d["status"] != "confirming":
        return False, "Сначала запросите удаление (придёт код в ЛС)."
    if (phrase or "").strip().upper() != ACCOUNT_DELETE_PHRASE:
        return False, f"Контрольная фраза не совпала. Введите вручную: {ACCOUNT_DELETE_PHRASE}"
    if (code or "").strip() != (d.get("confirm_code") or ""):
        return False, "Неверный код из ЛС."
    await db.execute(
        "UPDATE account_deletions SET status = 'cooling', "
        "cooling_until = NOW() + make_interval(hours => ?) WHERE user_id = ?",
        (ACCOUNT_DELETE_COOLING_HOURS, user_id),
    )
    await db.commit()
    await _tg("sendMessage", chat_id=user_id, parse_mode="HTML", text=(
        f"⏳ <b>Удаление аккаунта подтверждено.</b>\n"
        f"Оно произойдёт через <b>{ACCOUNT_DELETE_COOLING_HOURS} часа(ов)</b> — "
        f"потом ещё {ACCOUNT_DELETE_RESTORE_DAYS} дней на восстановление.\n\n"
        f"Передумали (или это не вы)? <code>бот отменить удаление</code> — в любой момент."))
    return True, (f"⏳ Удаление через {ACCOUNT_DELETE_COOLING_HOURS} ч. "
                  f"Отменить: «бот отменить удаление» или кнопка в настройках.")


async def cancel_deletion(db, user_id: int) -> tuple[bool, str]:
    st = await get_state(db, user_id)
    d = st["deletion"]
    if not d or d["status"] not in ("confirming", "cooling"):
        return False, "Активного процесса удаления нет."
    await db.execute(
        "UPDATE account_deletions SET status = 'cancelled' WHERE user_id = ?", (user_id,))
    await db.commit()
    return True, "✅ Удаление аккаунта отменено. Ничего не изменилось."


async def restore_account(db, user_id: int) -> tuple[bool, str]:
    # Same per-user lock as _finalize: restore and finalization serialize, and
    # whichever commits first wins (the loser sees the changed status).
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(?)", (user_id,))
        st = await get_state(db, user_id)
        d = st["deletion"]
        if not st["deleted_at"]:
            return False, "Аккаунт не удалён — восстанавливать нечего."
        if not d or d["status"] != "pending_restore":
            return False, ("Окно восстановления истекло — данные очищены. "
                           "Обратитесь к администрации бота.")
        result = await db.execute(
            "UPDATE account_deletions SET status = 'restored' "
            "WHERE user_id = ? AND status = 'pending_restore'", (user_id,))
        if result.rowcount != 1:
            return False, ("Окно восстановления истекло — данные очищены. "
                           "Обратитесь к администрации бота.")
        await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (user_id,))
    return True, "🎉 Аккаунт восстановлен! Всё на месте — с возвращением."


async def _mark_deleted(db, user_id: int) -> bool:
    if await _has_active_marriage(db, user_id):
        await db.execute(
            "UPDATE account_deletions SET status = 'cancelled' WHERE user_id = ?", (user_id,)
        )
        return False
    await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (user_id,))
    await db.execute(
        "UPDATE account_deletions SET status = 'pending_restore', deleted_at = NOW(), "
        "restore_deadline = NOW() + make_interval(days => ?) WHERE user_id = ?",
        (ACCOUNT_DELETE_RESTORE_DAYS, user_id),
    )
    return True


# Created lazily by the global-skin repository; absent table = nothing to delete.
# Every other table must exist: a missing one fails the whole finalization.
_OPTIONAL_FINALIZE_TABLES = frozenset({"global_skin_v1_selection", "global_skin_v1_owned"})

_FINALIZE_STEPS = [
    ("pets", "DELETE FROM pets WHERE owner_id = ?"),
    ("inventory", "DELETE FROM inventory WHERE user_id = ?"),
    ("global_skin_v1_selection", "DELETE FROM global_skin_v1_selection WHERE user_id = ?"),
    ("global_skin_v1_owned", "DELETE FROM global_skin_v1_owned WHERE user_id = ?"),
    ("user_cosmetics", "DELETE FROM user_cosmetics WHERE user_id = ?"),
    ("user_cosmetic_loadout", "DELETE FROM user_cosmetic_loadout WHERE user_id = ?"),
    ("cosmetic_presets", "DELETE FROM cosmetic_presets WHERE user_id = ?"),
    ("user_relics", "DELETE FROM user_relics WHERE user_id = ?"),
    ("user_shadow_relics", "DELETE FROM user_shadow_relics WHERE user_id = ?"),
    ("daily_login", "DELETE FROM daily_login WHERE user_id = ?"),
    ("achievements", "DELETE FROM achievements WHERE user_id = ?"),
    ("daily_quests", "DELETE FROM daily_quests WHERE user_id = ?"),
    ("crypto_holdings", "DELETE FROM crypto_holdings WHERE user_id = ?"),
    ("crypto_watchlist", "DELETE FROM crypto_watchlist WHERE user_id = ?"),
    ("user_nicknames", "DELETE FROM user_nicknames WHERE user_id = ?"),
    ("clan_members", "DELETE FROM clan_members WHERE user_id = ?"),
    ("user_chat_stats", "UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = ?"),
    ("users", "UPDATE users SET user_balance_mora = 0, user_balance_diamonds = 0, "
              "user_balance_zarniki = 0, user_balance_dark_mora = 0, account_xp = 0, "
              "account_level = 1, user_tg_username = NULL, active_theme = NULL "
              "WHERE user_tg_id = ?"),
]


async def _finalize(db, user_id: int) -> bool:
    """Очистка игровых данных одной транзакцией (audit A02): любая ошибка
    откатывает всё, статус остаётся 'pending_restore' и следующий проход
    повторяет финализацию целиком. Аудит-таблицы (wallet_log, moderation_logs,
    global_sanctions, admin_grant_log) намеренно НЕ трогаются.

    Возвращает True, только если аккаунт действительно финализирован."""
    async with db.connection.transaction():
        # A long-held user lock must not stall the whole maintenance loop:
        # time out, roll back and retry on the next tick.
        await db.execute("SET LOCAL lock_timeout = '5s'")
        # Per-user lock shared with restore_account and the chest/quest/pet
        # writers; then the users row, which direct ledger writers lock.
        await db.execute("SELECT pg_advisory_xact_lock(?)", (user_id,))
        async with db.execute(
            "SELECT deleted_at IS NOT NULL FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)
        ) as cursor:
            user_row = await cursor.fetchone()
        async with db.execute(
            "SELECT 1 FROM account_deletions WHERE user_id = ? AND status = 'pending_restore' "
            "AND restore_deadline <= NOW() FOR UPDATE", (user_id,)
        ) as cursor:
            due = await cursor.fetchone()
        if not user_row or not user_row[0] or not due:
            return False   # restored, cancelled or not due any more
        if await _has_active_marriage(db, user_id):
            await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (user_id,))
            await db.execute(
                "UPDATE account_deletions SET status = 'cancelled', deleted_at = NULL, "
                "restore_deadline = NULL WHERE user_id = ?",
                (user_id,),
            )
            logger.warning("account finalization cancelled for {}: active marriage", user_id)
            return False
        # Chest history is append-only audit evidence. Move the account to a fresh
        # epoch and zero its spendable keys so old pending opens can never be
        # revealed by a surviving session or a later re-registration.
        await chest_repo.retire_account(db, user_id)
        for table, sql in _FINALIZE_STEPS:
            if table in _OPTIONAL_FINALIZE_TABLES:
                async with db.execute("SELECT to_regclass(?) IS NOT NULL", (table,)) as cursor:
                    if not (await cursor.fetchone())[0]:
                        continue
            await db.execute(sql, (user_id,))
        await db.execute(
            "UPDATE account_deletions SET status = 'finalized', finalized_at = NOW() "
            "WHERE user_id = ?", (user_id,))
    return True


async def daily_tick(db) -> None:
    """Ежедневный проход (шедулер): остывание → удаление; неактив-предупреждение;
    неактив-удаление; финализация просроченных."""
    # 1) остывание истекло → пометить удалённым
    async with db.execute(
        "SELECT user_id FROM account_deletions "
        "WHERE status = 'cooling' AND cooling_until <= NOW()"
    ) as c:
        for r in [dict(x) for x in await c.fetchall()]:
            if await _mark_deleted(db, r["user_id"]):
                await _tg("sendMessage", chat_id=r["user_id"], parse_mode="HTML", text=(
                    f"🗑 <b>Аккаунт удалён.</b> Восстановление доступно "
                    f"{ACCOUNT_DELETE_RESTORE_DAYS} дней: <code>бот восстановить аккаунт</code>."))

    # 2) авто-неактив: предупреждение за N дней
    async with db.execute(
        "SELECT u.user_tg_id, COALESCE(u.delete_after_days, 365) AS dd "
        "FROM users u "
        "WHERE u.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM account_deletions ad WHERE ad.user_id = u.user_tg_id "
        "                AND (ad.status IN ('cooling','pending_restore') "
        "                     OR (ad.status = 'confirming' AND (ad.source <> 'inactivity' OR ad.warned_at IS NULL "
        "                          OR ad.warned_at >= (SELECT MAX(s2.last_message_at) FROM user_chat_stats s2 "
        "                                              WHERE s2.user_tg_id = u.user_tg_id))))) "
        "AND (SELECT MAX(s.last_message_at) FROM user_chat_stats s "
        "     WHERE s.user_tg_id = u.user_tg_id) "
        "    < NOW() - make_interval(days => COALESCE(u.delete_after_days, 365) - ?) "
        "LIMIT 50",
        (ACCOUNT_DELETE_WARN_DAYS,),
    ) as c:
        warn_candidates = [dict(x) for x in await c.fetchall()]
    # Старая отметка «предупреждён» после возвращения игрока устарела: предупреждаем заново (ON CONFLICT ниже).
    for u in warn_candidates:
        uid = u["user_tg_id"]
        await db.execute("DELETE FROM account_deletions WHERE user_id = ? AND status IN ('cancelled','restored')", (uid,))
        await db.execute(
            "INSERT INTO account_deletions (user_id, source, status, warned_at) "
            "VALUES (?, 'inactivity', 'confirming', NOW()) "
            "ON CONFLICT (user_id) DO UPDATE SET warned_at = NOW(), source = 'inactivity'",
            (uid,),
        )
        await _tg("sendMessage", chat_id=uid, parse_mode="HTML", text=(
            f"😴 <b>Вы давно не появлялись.</b> По вашей настройке аккаунт будет "
            f"удалён через ~{ACCOUNT_DELETE_WARN_DAYS} дней неактива.\n"
            f"Чтобы отменить — просто напишите любое сообщение в чате с ботом. "
            f"Настройка: сайт → ⚙️ Настройки → Аккаунт."))

    # 3) авто-неактив: срок вышел полностью → удаление
    async with db.execute(
        "SELECT u.user_tg_id FROM users u "
        "JOIN account_deletions ad ON ad.user_id = u.user_tg_id "
        "WHERE u.deleted_at IS NULL AND ad.source = 'inactivity' "
        "AND ad.status = 'confirming' AND ad.warned_at IS NOT NULL "
        # предупреждение должно пройти не меньше ACCOUNT_DELETE_WARN_DAYS и быть позже последней активности
        "AND ad.warned_at <= NOW() - make_interval(days => ?) "
        "AND (SELECT MAX(s.last_message_at) FROM user_chat_stats s "
        "     WHERE s.user_tg_id = u.user_tg_id) < ad.warned_at "
        "AND (SELECT MAX(s.last_message_at) FROM user_chat_stats s "
        "     WHERE s.user_tg_id = u.user_tg_id) "
        "    < NOW() - make_interval(days => COALESCE(u.delete_after_days, 365)) "
        "LIMIT 50",
        (ACCOUNT_DELETE_WARN_DAYS,),
    ) as c:
        for r in [dict(x) for x in await c.fetchall()]:
            if await _mark_deleted(db, r["user_tg_id"]):
                await _tg("sendMessage", chat_id=r["user_tg_id"], parse_mode="HTML", text=(
                    f"🗑 <b>Аккаунт удалён за неактив.</b> Восстановление доступно "
                    f"{ACCOUNT_DELETE_RESTORE_DAYS} дней: <code>бот восстановить аккаунт</code>."))

    # 4) окно восстановления истекло → финализация
    async with db.execute(
        "SELECT user_id FROM account_deletions "
        "WHERE status = 'pending_restore' AND restore_deadline <= NOW() "
        "ORDER BY restore_deadline LIMIT 20"
    ) as c:
        due = [dict(x) for x in await c.fetchall()]
    for r in due:
        # One failing account must not stop the others; it stays
        # 'pending_restore' and is retried on the next pass.
        try:
            if await _finalize(db, r["user_id"]):
                logger.info(f"Аккаунт {r['user_id']} финализирован (очистка игровых данных)")
        except Exception:
            logger.exception(f"Финализация аккаунта {r['user_id']} откатана, повтор в следующий проход")

    await db.commit()
