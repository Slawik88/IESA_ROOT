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
    st = await get_state(db, user_id)
    d = st["deletion"]
    if not st["deleted_at"]:
        return False, "Аккаунт не удалён — восстанавливать нечего."
    if not d or d["status"] != "pending_restore":
        return False, ("Окно восстановления истекло — данные очищены. "
                       "Обратитесь к администрации бота.")
    await db.execute("UPDATE users SET deleted_at = NULL WHERE user_tg_id = ?", (user_id,))
    await db.execute(
        "UPDATE account_deletions SET status = 'restored' WHERE user_id = ?", (user_id,))
    await db.commit()
    return True, "🎉 Аккаунт восстановлен! Всё на месте — с возвращением."


async def _mark_deleted(db, user_id: int) -> None:
    await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (user_id,))
    await db.execute(
        "UPDATE account_deletions SET status = 'pending_restore', deleted_at = NOW(), "
        "restore_deadline = NOW() + make_interval(days => ?) WHERE user_id = ?",
        (ACCOUNT_DELETE_RESTORE_DAYS, user_id),
    )


async def _finalize(db, user_id: int) -> None:
    """Очистка игровых данных. Аудит-таблицы (wallet_log, moderation_logs,
    global_sanctions, admin_grant_log) намеренно НЕ трогаются."""
    for sql, args in [
        ("DELETE FROM pets WHERE owner_id = ?", (user_id,)),
        ("DELETE FROM inventory WHERE user_id = ?", (user_id,)),
        ("DELETE FROM user_cosmetics WHERE user_id = ?", (user_id,)),
        ("DELETE FROM user_cosmetic_loadout WHERE user_id = ?", (user_id,)),
        ("DELETE FROM cosmetic_presets WHERE user_id = ?", (user_id,)),
        ("DELETE FROM user_relics WHERE user_id = ?", (user_id,)),
        ("DELETE FROM user_shadow_relics WHERE user_id = ?", (user_id,)),
        ("DELETE FROM daily_login WHERE user_id = ?", (user_id,)),
        ("DELETE FROM achievements WHERE user_id = ?", (user_id,)),
        ("DELETE FROM daily_quests WHERE user_id = ?", (user_id,)),
        ("DELETE FROM crypto_holdings WHERE user_id = ?", (user_id,)),
        ("DELETE FROM crypto_watchlist WHERE user_id = ?", (user_id,)),
        ("DELETE FROM user_nicknames WHERE user_tg_id = ?", (user_id,)),
        ("DELETE FROM clan_members WHERE user_id = ?", (user_id,)),
        ("DELETE FROM marriages WHERE user1_id = ? OR user2_id = ?", (user_id, user_id)),
        ("UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = ?", (user_id,)),
        ("UPDATE users SET user_balance_mora = 0, user_balance_diamonds = 0, "
         "user_balance_zarniki = 0, user_balance_dark_mora = 0, account_xp = 0, "
         "account_level = 1, user_tg_username = NULL, active_theme = NULL "
         "WHERE user_tg_id = ?", (user_id,)),
    ]:
        try:
            await db.execute(sql, args)
        except Exception as e:
            logger.warning(f"finalize {user_id}: {sql.split()[2]}: {e}")
    await db.execute(
        "UPDATE account_deletions SET status = 'finalized', finalized_at = NOW() "
        "WHERE user_id = ?", (user_id,))


async def daily_tick(db) -> None:
    """Ежедневный проход (шедулер): остывание → удаление; неактив-предупреждение;
    неактив-удаление; финализация просроченных."""
    # 1) остывание истекло → пометить удалённым
    async with db.execute(
        "SELECT user_id FROM account_deletions "
        "WHERE status = 'cooling' AND cooling_until <= NOW()"
    ) as c:
        for r in [dict(x) for x in await c.fetchall()]:
            await _mark_deleted(db, r["user_id"])
            await _tg("sendMessage", chat_id=r["user_id"], parse_mode="HTML", text=(
                f"🗑 <b>Аккаунт удалён.</b> Восстановление доступно "
                f"{ACCOUNT_DELETE_RESTORE_DAYS} дней: <code>бот восстановить аккаунт</code>."))

    # 2) авто-неактив: предупреждение за N дней
    async with db.execute(
        "SELECT u.user_tg_id, COALESCE(u.delete_after_days, 365) AS dd "
        "FROM users u "
        "WHERE u.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM account_deletions ad WHERE ad.user_id = u.user_tg_id "
        "                AND ad.status IN ('confirming','cooling','pending_restore')) "
        "AND (SELECT MAX(s.last_message_at) FROM user_chat_stats s "
        "     WHERE s.user_tg_id = u.user_tg_id) "
        "    < NOW() - make_interval(days => COALESCE(u.delete_after_days, 365) - ?) "
        "LIMIT 50",
        (ACCOUNT_DELETE_WARN_DAYS,),
    ) as c:
        warn_candidates = [dict(x) for x in await c.fetchall()]
    for u in warn_candidates:
        uid = u["user_tg_id"]
        async with db.execute(
            "SELECT 1 FROM account_deletions WHERE user_id = ? AND source = 'inactivity' "
            "AND warned_at IS NOT NULL AND warned_at > NOW() - make_interval(days => ?)",
            (uid, int(u["dd"])),
        ) as c2:
            if await c2.fetchone():
                continue  # уже предупреждали в этом цикле неактива
        # активность после старого warned_at сбрасывает процесс — просто перезаписываем
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
        "AND (SELECT MAX(s.last_message_at) FROM user_chat_stats s "
        "     WHERE s.user_tg_id = u.user_tg_id) "
        "    < NOW() - make_interval(days => COALESCE(u.delete_after_days, 365)) "
        "LIMIT 50"
    ) as c:
        for r in [dict(x) for x in await c.fetchall()]:
            await _mark_deleted(db, r["user_tg_id"])
            await _tg("sendMessage", chat_id=r["user_tg_id"], parse_mode="HTML", text=(
                f"🗑 <b>Аккаунт удалён за неактив.</b> Восстановление доступно "
                f"{ACCOUNT_DELETE_RESTORE_DAYS} дней: <code>бот восстановить аккаунт</code>."))

    # 4) окно восстановления истекло → финализация
    async with db.execute(
        "SELECT user_id FROM account_deletions "
        "WHERE status = 'pending_restore' AND restore_deadline <= NOW() LIMIT 20"
    ) as c:
        for r in [dict(x) for x in await c.fetchall()]:
            await _finalize(db, r["user_id"])
            logger.info(f"Аккаунт {r['user_id']} финализирован (очистка игровых данных)")

    await db.commit()
