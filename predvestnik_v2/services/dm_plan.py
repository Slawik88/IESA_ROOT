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


async def evening_text(db, user_id: int, now: datetime) -> str | None:
    lines = []
    quests = await quests_state(db, user_id)
    if quests is not None and (daily := quests["daily"]["quests"]):
        done = sum(q["completed"] for q in daily)
        if done:
            lines.append(f"📋 Задания дня: сделано {done} из {len(daily)}.")
        if any(reward["claimable"] for reward in quests["rewards"]["items"].values()):
            lines.append("🎁 Награды за задания ещё ждут тебя.")
    pets = await pets_state(db, user_id)
    if pets is not None and pets[0]:
        lines.append(f"🐾 Питомцы вернулись: {pets[0]} — добыча ждёт.")
    if await pass_ready(db, user_id, now):
        lines.append("🏆 В Пропуске есть награда, которую можно забрать.")
    return "🌙 <b>Итоги дня</b>\n" + "\n".join(lines) if lines else None


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


# ── «забрать»: одни и те же правила для кнопок плана в личке и для «Табло» (services/widgets/hub.py) ──────────

async def claim_quest(db, user_id: int, kind: str) -> str:
    """Награда за задания дня, недели или за всё вместе. Повтор не выдаёт второй раз: квитанция по периоду."""
    from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger
    from infrastructure.repositories.quests_v1 import ensure_tables
    from services import quests_v1 as quests
    from services.vip import is_vip_active
    await ensure_tables(db)
    await ensure_ledger(db)
    sources = await quests.available_sources(db, user_id=user_id)
    state = await quests.claim_reward(db, user_id=user_id, vip_active=await is_vip_active(db, user_id), kind=kind, sources=sources)
    result = state["reward_result"]
    if result["already_claimed"]:
        return "Эту награду ты уже забрал."
    parts = [f"Мора +{result['amount_mora']}"]
    if result.get("amount_keys"):
        parts.append(f"ключей +{result['amount_keys']}")
    if result.get("amount_essence"):
        parts.append(f"Эссенции +{result['amount_essence']}")
    return "✅ Забрано: " + ", ".join(parts) + "."


async def claim_pass(db, user_id: int) -> str:
    """Все готовые награды Пропуска во всех сезонах, где их можно забрать."""
    from datetime import timezone
    from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger
    from services import dm_push_events, league_pass
    await ensure_ledger(db)
    seasons = await dm_push_events.ready_pass_seasons(db, user_id, datetime.now(timezone.utc))
    if not seasons:
        return "Сейчас в Пропуске нечего забирать."
    texts = []
    for season in seasons:
        try:
            result = await league_pass.claim(db, user_id=user_id, season=season)
        except league_pass.PassError as exc:
            if texts:
                break
            return str(exc)
        texts += [g["text"] for g in result["granted"]]
    return "✅ Забрано из Пропуска: " + ", ".join(texts[:8]) + ("…" if len(texts) > 8 else "") + "."


async def claim_casino_gift(db, user_id: int, day) -> str:
    """Ежедневные фишки Зала Фортуны за день `day` (день из кнопки: вчерашняя кнопка сегодня не сработает)."""
    from infrastructure.repositories import system_flags
    from services import casino_v1
    if not await system_flags.is_enabled(db, "game_casino_v1"):
        return "Зал Фортуны сейчас закрыт."
    result = await casino_v1.claim_gift(db, user_id, expected_day=day)
    return f"✅ Получено фишек: {result['gift']}."


async def next_pet_return(db, user_id: int) -> tuple[datetime, datetime] | None:
    """(начало, конец) занятия питомца, которое закончится раньше всех; None — все дома или уже вернулись."""
    async with db.execute(
        "SELECT ends_at, hours FROM pet_v2_runs WHERE user_id = ? AND status = 'active' AND ends_at > NOW() "
        "ORDER BY ends_at LIMIT 1", (int(user_id),),
    ) as c:
        row = await c.fetchone()
    if row is None:
        return None
    from datetime import timedelta
    return row[0] - timedelta(hours=int(row[1])), row[0]
