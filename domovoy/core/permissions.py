"""
core/permissions.py
Реестр прав «Домового».

Владелец дома имеет всё по умолчанию; прочим участникам права выдаёт владелец
(или носитель manage_members). Добавление новой механики = новая строка в
PERMISSIONS ниже — бот и сервисы подхватят её без правки интерфейсов.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    code: str
    label: str          # короткое имя в меню прав
    hint: str           # что даёт, одной фразой


PERMISSIONS: tuple[Permission, ...] = (
    Permission("manage_schedule", "График уборки", "менять график и переносить дни"),
    Permission("close_others_days", "Чужие дни", "закрывать дни уборки за других"),
    Permission("confirm_contributions", "Взносы", "подтверждать взносы жильцов"),
    Permission("manage_all_expenses", "Чужие траты", "править и удалять чужие траты"),
    Permission("manage_categories", "Категории", "добавлять и убирать категории трат"),
    Permission("manage_house_settings", "Настройки дома", "менять настройки дома"),
    Permission("manage_members", "Участники", "приглашать и назначать права другим"),
    Permission("import_transactions", "Импорт денег", "загружать историю взносов и трат из файлов"),
)

PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)

PERMISSION_BY_CODE: dict[str, Permission] = {p.code: p for p in PERMISSIONS}

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"


def has_permission(role: str, granted: frozenset[str] | set[str], code: str) -> bool:
    """Владелец — всё; остальные — только явно выданное."""
    if code not in PERMISSION_CODES:
        raise ValueError(f"Неизвестное право: {code}")
    if role == ROLE_OWNER:
        return True
    return code in granted
