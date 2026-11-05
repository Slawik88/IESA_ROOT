"""Обращения игроков к администрации из лички: создание, кому показывать, ответ и закрытие.

Правила здесь, а не в боте: бот только принимает текст и нажатия. Ответить или закрыть может только персонал с доступом к
«Жалобам» (роль берётся из тех же настроек прав, что в админке); любое действие пишется в журнал админки.
"""
from __future__ import annotations

from core import dm_tickets as rules
from infrastructure.repositories import dm_tickets as repo
from services import admin_access, admin_people


class TicketError(Exception):
    """Понятная игроку или сотруднику причина отказа."""


async def ensure_schema(db) -> None:
    await repo.ensure_schema(db)


async def create(db, *, user_id: int, text: str) -> dict:
    """Принять обращение. Один игрок: не больше DAILY_LIMIT новых за сутки и OPEN_LIMIT неотвеченных одновременно."""
    clean = rules.clean_text(text, rules.MAX_TEXT)
    if len(clean) < rules.MIN_TEXT:
        raise TicketError("Опиши вопрос подробнее: хотя бы одним предложением.")
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (f"dm_ticket:{int(user_id)}",))
        today, waiting = await repo.counts_for(db, user_id)
        if waiting >= rules.OPEN_LIMIT:
            raise TicketError("Два твоих обращения уже ждут ответа. Дождись его — я напишу сюда.")
        if today >= rules.DAILY_LIMIT:
            raise TicketError(f"Не больше {rules.DAILY_LIMIT} обращений в сутки. Попробуй завтра.")
        ticket_id = await repo.add(db, user_id, clean)
    return {"id": ticket_id, "text": clean}


async def staff_rank_needed(db, principal_rank: int, user_id: int) -> int:
    """Нужная роль для обращений (как для раздела «Жалобы»; создатель может поднять порог в «Правах»)."""
    grants = await admin_access.load_grants(db)
    principal = admin_access.staff_principal(user_id, principal_rank, grants)
    return admin_access.min_rank(principal, rules.STAFF_SECTION, rules.STAFF_DEFAULT_RANK)


async def is_staff(db, user_id: int) -> bool:
    from bot.chat.global_ranks import get_bot_rank
    rank = await get_bot_rank(db, user_id)
    return rank > 0 and rank >= await staff_rank_needed(db, rank, user_id)


async def recipients(db, exclude: int | None = None) -> list[int]:
    """Кому показать новое обращение: персонал с нужной ролью (создатель бота — всегда), не больше MAX_RECIPIENTS."""
    from bot.config import config
    grants = await admin_access.load_grants(db)
    need = admin_access.min_rank(admin_access.staff_principal(0, 0, grants), rules.STAFF_SECTION, rules.STAFF_DEFAULT_RANK)
    found = set(await repo.staff_ids(db, max(1, need)))
    if config.developer_id:
        found.add(int(config.developer_id))
    found.discard(int(exclude or 0))
    return sorted(found)[:rules.MAX_RECIPIENTS]


async def get(db, ticket_id: int) -> dict | None:
    return await repo.get(db, ticket_id)


async def open_list(db) -> tuple[list[dict], int]:
    return await repo.open_list(db, rules.LIST_LIMIT), await repo.open_total(db)


async def answer(db, *, ticket_id: int, staff_id: int, text: str) -> dict:
    """Ответить игроку. Второй ответ на то же обращение не пройдёт (кто-то из коллег успел раньше)."""
    if len(str(text or "").strip()) > rules.MAX_ANSWER:
        raise TicketError(f"Ответ длиннее {rules.MAX_ANSWER} знаков: сократи и отправь заново.")
    return await _settle(db, ticket_id, staff_id, "answered", rules.clean_text(text, rules.MAX_ANSWER))


async def close(db, *, ticket_id: int, staff_id: int) -> dict:
    return await _settle(db, ticket_id, staff_id, "closed", None)


async def _settle(db, ticket_id: int, staff_id: int, status: str, text: str | None) -> dict:
    if not await is_staff(db, staff_id):
        raise TicketError("Обращения доступны только персоналу бота.")
    if status == "answered" and not text:
        raise TicketError("Ответ пустой. Напиши текст ответа.")
    async with db.connection.transaction():
        ticket = await repo.get(db, ticket_id)
        if ticket is None:
            raise TicketError("Такого обращения нет.")
        if not await repo.settle(db, ticket_id, status, staff_id, text):
            raise TicketError("Обращение уже закрыто: коллега ответил раньше.")
        await admin_people.audit(db, staff_id, f"ticket_{status}", user_id=ticket["user_id"], details={"ticket": int(ticket_id)})
    return {**ticket, "status": status, "answer": text}
