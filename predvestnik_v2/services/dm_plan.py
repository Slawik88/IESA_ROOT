"""Сводка «что ждёт игрока сегодня» для плана дня в личке и утреннего дайджеста: задания, питомцы, Пропуск.

Данные берутся теми же сервисами, что в Mini App. Здесь только сбор состояния и текст утреннего письма;
экран «План дня» с кнопками рисует bot/chat/notify.py.
"""
from __future__ import annotations

from datetime import datetime

from loguru import logger

QUEST_KINDS = {"daily": "дня", "weekly": "недели", "combined": "за день и неделю вместе"}


async def quests_state(db, user_id: int) -> dict | None:
    from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger
    from infrastructure.repositories.quests_v1 import ensure_tables
    from services import quests_v1 as quests
    from services.vip import is_vip_active
    try:
        await ensure_tables(db)
        await ensure_ledger(db)
        sources = await quests.available_sources(db, user_id=user_id)
        return await quests.overview(db, user_id=user_id, vip_active=await is_vip_active(db, user_id), sources=sources)
    except Exception as exc:
        logger.warning(f"plan: quests unavailable: {type(exc).__name__}: {exc}")
        return None


async def pets_state(db, user_id: int) -> tuple[int, int] | None:
    """(вернулись и ждут, ещё в пути)."""
    from infrastructure.repositories import system_flags
    try:
        if not await system_flags.is_enabled(db, "pets_v2"):
            return None
        async with db.execute(
            "SELECT COUNT(*) FILTER (WHERE ends_at <= NOW()), COUNT(*) FILTER (WHERE ends_at > NOW()) "
            "FROM pet_v2_runs WHERE user_id = ? AND status = 'active'", (int(user_id),),
        ) as c:
            row = await c.fetchone()
        return int(row[0] or 0), int(row[1] or 0)
    except Exception as exc:
        logger.warning(f"plan: pets unavailable: {type(exc).__name__}: {exc}")
        return None


async def pass_ready(db, user_id: int, now: datetime) -> bool:
    from services import dm_push_events
    try:
        return bool(await dm_push_events.ready_pass_seasons(db, user_id, now))
    except Exception as exc:
        logger.warning(f"plan: pass unavailable: {type(exc).__name__}: {exc}")
        return False


async def morning_text(db, user_id: int, now: datetime) -> str | None:
    """Утреннее письмо: что сегодня можно забрать или сделать. None — сегодня нечего сказать, письмо не нужно."""
    lines = []
    quests = await quests_state(db, user_id)
    if quests is not None and quests["daily"]["quests"]:
        total = len(quests["daily"]["quests"])
        done = sum(1 for q in quests["daily"]["quests"] if q["completed"])
        ready = [k for k, v in quests["rewards"]["items"].items() if v["claimable"]]
        if ready:
            lines.append("🎁 Награда за задания " + ", ".join(QUEST_KINDS[k] for k in ready if k in QUEST_KINDS) + " ждёт тебя.")
        if done < total:
            lines.append(f"📋 Задания дня: сделано {done} из {total}.")
    pets = await pets_state(db, user_id)
    if pets is not None and pets[0]:
        lines.append(f"🐾 Питомцы вернулись: {pets[0]} — добыча ждёт.")
    if await pass_ready(db, user_id, now):
        lines.append("🏆 В Пропуске есть награда, которую можно забрать.")
    if not lines:
        return None
    return "☀️ <b>План на сегодня</b>\n" + "\n".join(lines)
