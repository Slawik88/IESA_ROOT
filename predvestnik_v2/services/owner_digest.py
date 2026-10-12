"""Ежедневный отчёт владельцу бота в личку: что было вчера, что требует внимания.

Настройка `owner_digest` в bot_settings: {"enabled": true, "hour": 9}. Час — по местному времени бота (TIMEZONE_OFFSET).
Отправляется раз в сутки, повторно в тот же день не уходит (даже после перезапуска): дата последней отправки в `owner_digest_state`.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from loguru import logger

from bot.chat import settings
from bot.chat.style import quote

KEY, STATE_KEY = "owner_digest", "owner_digest_state"
DEFAULT = {"enabled": True, "hour": 9}


async def get_settings(db) -> dict:
    saved = await settings.get_json(db, KEY, {})
    return {"enabled": bool(saved.get("enabled", DEFAULT["enabled"])), "hour": int(saved.get("hour", DEFAULT["hour"]))}


async def save_settings(db, actor_id: int, enabled: bool, hour: int) -> dict:
    if not 0 <= hour <= 23:
        raise ValueError("Час отправки — от 0 до 23.")
    await settings.set_json(db, KEY, {"enabled": bool(enabled), "hour": int(hour)}, actor_id)
    return await get_settings(db)


def _n(value) -> str:
    return f"{int(value):,}".replace(",", " ")


async def build(db) -> str:
    """Текст отчёта за вчерашние местные сутки."""
    from services import bot_health, bot_metrics
    day = bot_metrics.today() - timedelta(days=1)
    staff = await bot_metrics.staff_ids(db)   # итоги дня считаются так же, как «Метрики»: без аккаунтов команды
    chats = await bot_metrics._chats(db, day, day, staff)
    bot = await bot_metrics._bot(db, day, day, staff)
    site = await bot_metrics._site(db, day, day, staff)
    start, end = bot_metrics._utc_start(day), bot_metrics._utc_start(day + timedelta(days=1))
    new_players = int((await bot_metrics._one(
        db, f"SELECT COUNT(*) FROM (SELECT user_tg_id FROM user_chat_stats WHERE TRUE{staff.sql('user_tg_id')} GROUP BY user_tg_id "
            "HAVING MIN(joined_at) >= ? AND MIN(joined_at) < ?) x", (*staff.args, start, end)))[0])
    health = await bot_health.counters(db)
    errors, _ = bot_health.recent_errors()
    try:
        reports = int((await bot_metrics._one(db, "SELECT COUNT(*) FROM bot_reports WHERE status IN ('new', 'in_work')", ()))[0])
    except Exception:
        reports = 0
    day_lines = [
        f"👥 Новых игроков: <b>{_n(new_players)}</b>",
        f"💬 Сообщений в чатах: <b>{_n(chats['messages'])}</b> · чатов {_n(chats['chats'])} · людей {_n(chats['users'])}",
        f"⌨️ Команд боту: <b>{_n(bot['commands'])}</b> (группы {_n(bot['commands_group'])}, личка {_n(bot['commands_private'])})",
        f"📱 Мини-приложение: <b>{_n(site['visitors'])}</b> посетителей",
    ]
    attention = [f"⚑ Открытых жалоб: <b>{_n(reports)}</b>", f"⚠️ Ошибок в логе за сутки: <b>{_n(errors)}</b>"]
    if health["chats"]["left"]:
        attention.append(f"🚪 Бота удалили из чатов: {_n(health['chats']['left'])}")
    if health["chats"]["no_rights"]:
        attention.append(f"🛡 Без прав модерации: {_n(health['chats']['no_rights'])} чатов")
    return (f"🌅 <b>Итоги дня</b> · {day.strftime('%d.%m.%Y')}\n" + quote(day_lines) + "\n" + quote(attention)
            + "\nПодробнее: админка → Метрики и Состояние.")


async def send_now(bot, db, user_id: int | None = None) -> str:
    """Отправить отчёт сейчас (владельцу или указанному человеку). Возвращает текст."""
    from bot.config import config
    text = await build(db)
    await bot.send_message(user_id or config.developer_id, text, parse_mode="HTML", disable_web_page_preview=True)
    return text


async def send_if_due(bot, pool_db) -> bool:
    """Отправить, если включено, наступил час и за сегодня ещё не отправляли. Возвращает, отправлено ли."""
    from bot.config import config
    from services import bot_metrics
    if not config.developer_id:
        return False
    async with pool_db() as db:
        cfg = await get_settings(db)
        now = bot_metrics.local_now()
        if not cfg["enabled"] or now.hour < cfg["hour"]:
            return False
        state = await settings.get_json(db, STATE_KEY, {})
        today = now.date().isoformat()
        if state.get("last") == today:
            return False
        await settings.set_json(db, STATE_KEY, {"last": today}, config.developer_id)   # отметка до отправки: сбой не даст спам каждую минуту
        try:
            await send_now(bot, db)
        except Exception as exc:
            logger.warning(f"owner digest not sent: {exc}")
            return False
    return True


async def scheduler(bot, pool_db, interval: float = 60.0) -> None:
    while True:
        try:
            await send_if_due(bot, pool_db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"owner digest scheduler: {exc}")
        await asyncio.sleep(interval)
