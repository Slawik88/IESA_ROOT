"""Уведомления в личку: очередь с согласием, лимитом, тихими часами, дайджестом и затуханием.

Правила (все проверяются здесь, а не в местах, где рождается событие):
 - без согласия игрока по категории событие не попадает в очередь, а если согласие снято — выбрасывается из очереди;
 - личка должна быть подтверждена (игрок писал боту) и не заблокирована; удалённому, заблокированному в боте игроку
   и при выключенном боте не пишем;
 - не больше core.dm_push.DAILY_CAP сообщений за сутки, в тихие часы не пишем, несколько событий — один дайджест;
 - после UNANSWERED_LIMIT сообщений без отклика пауза до первого ответа игрока;
 - Forbidden/«чат не найден» — личка недоступна, очередь снимается; 429 — ждём, ничего не повторяем сразу;
 - игрок, которому сейчас нельзя писать (ночь, лимит, пауза, сбой), получает отметку next_check_at и не занимает
   место в проходах доставки, пока она не наступит.
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from loguru import logger

from core import dm_push as rules
from infrastructure.repositories import dm_push as repo

MAX_ATTEMPTS = 3
CAP_RECHECK = timedelta(minutes=30)   # упёрся в суточный лимит: проверить снова через полчаса
FAIL_RECHECK = timedelta(minutes=5)   # сбой доставки: не мучить игрока каждую минуту
PAUSE_RECHECK = timedelta(days=1)     # пауза без отклика снимается ответом игрока (он сбрасывает отметку сам)
MarkupBuilder = Callable[[dict | None, object], Awaitable[object | None]]


def esc(value) -> str:
    return html.escape(str(value), quote=False)


async def confirm_contact(db, user_id: int) -> None:
    """Игрок написал боту или нажал кнопку в личке. Это подтверждает личку и снимает паузу «без отклика».
    Заодно чинит условие VIP-напоминания (vip_v2_preferences.dm_confirmed_at): раньше его не ставил никто, кроме тестов."""
    changed = await repo.touch_contact(db, user_id)
    if changed:
        from infrastructure.repositories import vip_v2
        try:
            await vip_v2.mark_private_contact(db, user_id=user_id)
        except Exception as exc:   # VIP-таблицы появляются отдельно; личку это не должно ломать
            logger.debug(f"vip private contact not marked: {exc}")


async def player_reachable(db, user_id: int) -> bool:
    """Можно ли вообще писать этому игроку: аккаунт не удалён и не заблокирован в боте."""
    from services import global_moderation
    return await repo.account_alive(db, user_id) and not await global_moderation.is_blocked(db, user_id)


async def bot_is_off(db) -> bool:
    """Весь бот выключен в админке («Функции» → all): тогда он молчит и в личке тоже."""
    from services import feature_switches
    try:
        return await feature_switches.disabled(db, ["all"], None) is not None
    except Exception as exc:   # выключатели недоступны — не блокируем доставку
        logger.warning(f"feature switches unavailable for dm push: {exc}")
        return False


async def enqueue(db, *, user_id: int, category: str, dedup_key: str, text: str, button: dict | None = None) -> bool:
    """Поставить уведомление в очередь. True — поставлено; False — нельзя (нет согласия, личка недоступна) или уже было."""
    cat = rules.BY_KEY.get(category)
    if cat is None or not cat.live:
        return False
    if not await repo.has_consent(db, user_id, category):
        return False
    state = await repo.get_settings(db, user_id)
    if state["dm_confirmed_at"] is None or state["dm_disabled_at"] is not None or state["paused_at"] is not None:
        return False
    if not await player_reachable(db, user_id):
        return False
    return await repo.add(db, user_id, category, dedup_key, text, button) is not None


async def deliver_due(bot, db, *, now: datetime | None = None, markup: MarkupBuilder | None = None,
                      limit: int = rules.SEND_BATCH) -> dict:
    """Один проход доставки. Возвращает счётчики для лога и тестов; 'retry_after' — сколько секунд ждать (429)."""
    now = now or datetime.now(timezone.utc)
    stats = {"sent": 0, "digests": 0, "dropped": 0, "waiting": 0, "unreachable": 0, "failed": 0, "retry_after": 0}
    if await bot_is_off(db):
        return stats
    for user_id in await repo.pending_user_ids(db, now, limit):
        try:
            outcome = await _deliver_user(bot, db, user_id, now, markup, stats)
        except TelegramRetryAfter as exc:
            stats["retry_after"] = max(stats["retry_after"], int(getattr(exc, "retry_after", 5) or 5))
            await db.commit()
            break   # Telegram просит притормозить: остальным игрокам — на следующем проходе, без лавины повторов
        except Exception as exc:   # один игрок не должен остановить остальных
            logger.warning(f"dm push for {user_id} failed: {type(exc).__name__}: {exc}")
            stats["failed"] += 1
            await repo.defer(db, user_id, now + FAIL_RECHECK)
            await db.commit()
            continue
        await db.commit()
        if outcome == "waiting":
            stats["waiting"] += 1
    return stats


async def _deliver_user(bot, db, user_id: int, now: datetime, markup: MarkupBuilder | None, stats: dict) -> str:
    rows = await repo.pending_rows(db, user_id)
    consent = await repo.consented(db, user_id)
    alive, dead = [], []
    for row in rows:
        if now - row["created_at"] > rules.EVENT_TTL:
            dead.append((row["id"], "expired"))
        elif row["category"] not in consent:
            dead.append((row["id"], "revoked"))
        else:
            alive.append(row)
    for reason in {r for _, r in dead}:
        await repo.drop(db, [i for i, r in dead if r == reason], reason)
    stats["dropped"] += len(dead)
    if not alive:
        return "empty"
    state = await repo.get_settings(db, user_id)
    if state["dm_disabled_at"] is not None or state["dm_confirmed_at"] is None or not await player_reachable(db, user_id):
        await repo.drop(db, [r["id"] for r in alive], "unreachable")
        stats["dropped"] += len(alive)
        return "unreachable"
    if state["paused_at"] is not None:
        await repo.defer(db, user_id, now + PAUSE_RECHECK)   # ждём первого ответа игрока; события живут до срока годности
        return "waiting"
    if rules.in_quiet_hours(now, state["tz_offset"], state["quiet_enabled"]):
        await repo.defer(db, user_id, rules.next_quiet_end(now, state["tz_offset"]))
        return "waiting"
    if await repo.sent_batches_since(db, user_id, now - timedelta(days=1)) >= rules.DAILY_CAP:
        await repo.defer(db, user_id, now + CAP_RECHECK)
        return "waiting"
    ids = [r["id"] for r in alive]
    if len(alive) == 1:
        text, button = alive[0]["text"], alive[0]["button"]
    else:
        text, button = rules.merge_digest(alive), {"kind": "cb", "data": "dn:plan", "label": "📋 План дня"}
    thread_id = None
    if len(alive) == 1:   # дайджест смешивает темы — он идёт в общий поток
        thread_id = await _thread_for(bot, db, user_id, rules.BY_KEY[alive[0]["category"]].topic, now)
    await _free(db)   # соединение не держим, пока ждём ответ Telegram
    reply_markup = None
    if markup:
        try:
            reply_markup = await markup(button, bot)
        except Exception as exc:   # кнопка не получилась — лучше сообщение без неё, чем никакого
            logger.warning(f"dm push button failed for {user_id}: {type(exc).__name__}: {exc}")
    revoked = await _revoked_since(db, user_id, {r["category"] for r in alive})
    if revoked:
        logger.debug(f"dm push for {user_id}: consent for {revoked} was taken back before sending")
        return "waiting"   # следующий проход выбросит снятые категории
    try:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup,
                                   **({"message_thread_id": thread_id} if thread_id else {}))
        except TelegramBadRequest as exc:
            if not thread_id or "thread" not in str(exc).lower():
                raise
            await repo.fail_topic(db, user_id, rules.BY_KEY[alive[0]["category"]].topic)   # тему удалили: пишем в общий поток
            await _free(db)
            await bot.send_message(user_id, text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)
    except TelegramForbiddenError:
        await _unreachable(db, user_id, stats)
        return "unreachable"
    except TelegramRetryAfter:
        raise
    except TelegramBadRequest as exc:
        if "chat not found" in str(exc).lower() or "user is deactivated" in str(exc).lower():
            await _unreachable(db, user_id, stats)
            return "unreachable"
        return await _failed(db, user_id, ids, now, stats)
    except TelegramAPIError as exc:   # сеть, 5xx: считаем попытку, чтобы событие не крутилось вечно
        logger.warning(f"dm push to {user_id}: {type(exc).__name__}: {exc}")
        return await _failed(db, user_id, ids, now, stats)
    await repo.mark_sent(db, ids)
    await repo.record_sent_to_player(db, user_id)
    stats["sent"] += len(ids)
    if len(alive) > 1:
        stats["digests"] += 1
    return "sent"


async def _failed(db, user_id: int, ids: list[int], now: datetime, stats: dict) -> str:
    await repo.mark_failed(db, ids, MAX_ATTEMPTS)
    await repo.defer(db, user_id, now + FAIL_RECHECK)
    stats["failed"] += 1
    return "failed"


async def _free(db) -> None:
    """Отдать соединение пула перед вызовом Telegram (на тестовом соединении без пула ничего не делает)."""
    release = getattr(db, "release_if_idle", None)
    if release:
        await db.commit()
        await release()


async def _revoked_since(db, user_id: int, categories: set[str]) -> set[str]:
    """Категории, согласие на которые сняли за то время, пока шла подготовка к отправке."""
    return categories - await repo.consented(db, user_id)


async def _thread_for(bot, db, user_id: int, topic_key: str, now: datetime) -> int | None:
    """Тема лички (Bot API 9.3+) для этого вида сообщений: «Задания», «Питомцы», «Биржа», «Новости».
    Создаётся при первой доставке и запоминается. Нет тем у бота или у игрока — None: сообщение идёт в общий поток."""
    try:
        if getattr(await bot.me(), "has_topics_enabled", None) is False:
            return None
        topic = await repo.get_topic(db, user_id, topic_key)
        if topic["thread_id"]:
            return topic["thread_id"]
        if topic["failed_at"] is not None and now - topic["failed_at"] < rules.TOPIC_RETRY:
            return None
        title, icon = rules.TOPICS[topic_key]
        await _free(db)
        created = await bot.create_forum_topic(user_id, f"{icon} {title}")
        await repo.save_topic(db, user_id, topic_key, created.message_thread_id)
        return int(created.message_thread_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        await repo.fail_topic(db, user_id, topic_key)   # тем в этой личке нет: не пробуем каждый раз
        return None
    except TelegramRetryAfter:
        raise
    except Exception as exc:
        logger.debug(f"dm topic {topic_key} for {user_id} unavailable: {type(exc).__name__}: {exc}")
        return None


async def vip_unreachable(db, user_id: int) -> None:
    """Личка недоступна: то же отключение для VIP-напоминания (его условие читает vip_v2_preferences)."""
    try:
        from infrastructure.repositories import vip_v2
        await vip_v2.mark_private_contact_unreachable(db, user_id=user_id)
    except Exception as exc:
        logger.debug(f"vip private contact not marked unreachable: {exc}")


async def _unreachable(db, user_id: int, stats: dict) -> None:
    await repo.mark_unreachable(db, user_id)
    await db.execute("UPDATE users SET dm_blocked_at = COALESCE(dm_blocked_at, NOW()) WHERE user_tg_id = ?", (int(user_id),))
    await vip_unreachable(db, user_id)
    stats["unreachable"] += 1
