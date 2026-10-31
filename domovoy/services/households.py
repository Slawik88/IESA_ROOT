"""
services/households.py — дома, участники, права.

Единственное место, где решается «можно ли этому человеку это». Бот и будущий
веб спрашивают здесь, а не решают сами (CLEAN_CODE 2.2).
"""

from loguru import logger

from core import permissions as perms
from core.constants import DEFAULT_CATEGORIES, MAX_HOUSE_NAME_LEN, MAX_MEMBER_NAME_LEN
from infrastructure import repositories as repo


class DomainError(Exception):
    """Понятный отказ пользователю: бот показывает message, ничего не падает."""


# ── Дома ─────────────────────────────────────────────────────────────────────

async def create_house(owner_tg_id: int, owner_name: str, house_name: str) -> int:
    name = house_name.strip()
    if not name:
        raise DomainError("Название дома не может быть пустым")
    if len(name) > MAX_HOUSE_NAME_LEN:
        raise DomainError(f"Название дома — до {MAX_HOUSE_NAME_LEN} символов")
    house_id = await repo.houses.create_house(name, owner_tg_id, owner_name.strip() or "Жилец")
    await repo.money.seed_default_categories(house_id, DEFAULT_CATEGORIES)
    logger.info(f"🏠 Создан дом id={house_id} «{name}» (владелец {owner_tg_id})")
    return house_id


async def get_house(house_id: int):
    return await repo.houses.get_house(house_id)


async def get_house_by_invite(token: str):
    return await repo.houses.get_house_by_invite(token)


async def houses_of_user(tg_id: int) -> list:
    return await repo.houses.list_houses_of_user(tg_id)


async def new_invite_token(house_id: int) -> str:
    return await repo.houses.refresh_invite_token(house_id)


def invite_link(house, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start=join_{house['invite_token']}"


async def set_chat_id(house_id: int, chat_id: int | None) -> None:
    await repo.houses.set_chat(house_id, chat_id)


# ── Участники ────────────────────────────────────────────────────────────────

async def join_house(house, tg_id: int, display_name: str) -> bool:
    """Вступить по приглашению. False — уже участник (это не ошибка)."""
    return await repo.houses.add_member(house["id"], tg_id, display_name.strip() or "Жилец")


async def members(house_id: int) -> list:
    return await repo.houses.list_active_members(house_id)


async def membership(house_id: int, tg_id: int):
    return await repo.houses.get_membership(house_id, tg_id)


async def leave_house(house_id: int, tg_id: int) -> None:
    m = await repo.houses.get_membership(house_id, tg_id)
    if m and m["role"] == perms.ROLE_OWNER:
        raise DomainError("Владелец не может выйти из дома. Сначала передайте дом другому — "
                          "или напишите разработчику.")
    await repo.houses.set_member_status(house_id, tg_id, "left")
    await repo.houses.clear_member_grants(house_id, tg_id)


def member_label(member_row) -> str:
    """Имя участника для сообщений (username, если задан, — в скобках)."""
    name = member_row["display_name"]
    username = member_row["username"] if "username" in member_row.keys() else None
    return f"{name} (@{username})" if username else name


# ── Права ────────────────────────────────────────────────────────────────────

async def can(house_id: int, tg_id: int, code: str) -> bool:
    perms.has_permission(perms.ROLE_MEMBER, set(), code)  # валидация кода права — всегда
    m = await repo.houses.get_membership(house_id, tg_id)
    if m is None or m["status"] != "active":
        return False
    if m["role"] == perms.ROLE_OWNER:
        return True
    grants = await repo.houses.member_grants(house_id, tg_id)
    return perms.has_permission(m["role"], grants, code)


async def require(house_id: int, tg_id: int, code: str) -> None:
    """Хранитель правила: отказ — DomainError с текстом для человека."""
    if not await can(house_id, tg_id, code):
        raise DomainError("Это может делать только владелец дома или тот, кому он выдал право.")


async def grants_of(house_id: int, tg_id: int) -> frozenset[str]:
    return await repo.houses.member_grants(house_id, tg_id)


async def set_grant(house_id: int, tg_id: int, code: str, granted: bool) -> None:
    if code not in perms.PERMISSION_CODES:
        raise DomainError("Неизвестное право")
    if granted:
        await repo.houses.grant(house_id, tg_id, code)
    else:
        await repo.houses.revoke(house_id, tg_id, code)


async def grantor_candidates(house_id: int, acting_tg_id: int) -> list:
    """Кому можно выдавать права: все активные, кроме владельца и самого себя."""
    return [
        m for m in await repo.houses.list_active_members(house_id)
        if m["role"] != perms.ROLE_OWNER and m["tg_id"] != acting_tg_id
    ]


# ── Имя внутри дома ──────────────────────────────────────────────────────────

async def rename_member(house_id: int, tg_id: int, new_name: str) -> None:
    name = new_name.strip()
    if not name or len(name) > MAX_MEMBER_NAME_LEN:
        raise DomainError("Имя не может быть пустым или слишком длинным")
    await repo.houses.set_display_name(house_id, tg_id, name)
