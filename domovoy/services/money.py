"""
services/money.py — Баланс Квартиры: взносы, траты, фото-чеки, отчёты.

Деньги — целые копейки. Баланс котла = подтверждённые взносы − траты из котла
− возвращённые из котла личные траты. Личная трата («за свои») ждёт возврата.
"""

from core.constants import (
    KOPECKS_IN_RUBLE, MAX_AMOUNT_RUBLES, MAX_CATEGORY_NAME_LEN,
    MAX_DESCRIPTION_LEN, MAX_PHOTOS_PER_EXPENSE,
)
from infrastructure import repositories as repo
from services.households import DomainError, can, require, require_member
from services.transaction_dates import parse_date, parse_month
from core.transaction_versions import contribution_version, expense_version

MODE_HOUSE = "house"        # трата из котла
MODE_PERSONAL = "personal"  # заплатил за всех своими — ждёт возврата из котла

STATUS_DECLARED = "declared"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"


def _validate_amount(amount_kop: int) -> None:
    if type(amount_kop) is not int or not 0 < amount_kop <= MAX_AMOUNT_RUBLES * KOPECKS_IN_RUBLE:
        raise DomainError("Сумма должна быть положительной и не превышать допустимый предел")


def month_of(iso_date: str) -> str:
    return iso_date[:7]


def shift_month(month: str, delta: int) -> str:
    """'2026-10' −1 → '2026-09'. Арифметика месяцев без календаря."""
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


# ── Взносы ───────────────────────────────────────────────────────────────────

async def declare_contribution(
    house_id: int, tg_id: int, amount_kop: int, today: str, *, month: str | None = None,
):
    """Жилец заявил взнос за текущий месяц; ждёт подтверждения."""
    from services.settings import house_setting, house_settings, house_today

    await require_member(house_id, tg_id)
    _validate_amount(amount_kop)
    paid_on = parse_date(today, house_today(await house_settings(house_id)))
    month = parse_month(month or month_of(paid_on))
    confirmation_required = await house_setting(house_id, "confirm_contributions")
    contribution_id = await repo.money.declare_contribution(
        house_id, tg_id, amount_kop, month, confirmation_required, paid_on,
    )
    return await repo.money.get_contribution(contribution_id)


async def resolve_contribution(
    contribution_id: int, confirm: bool, resolved_by: int, *, house_id: int | None = None,
):
    """Подтвердить/отклонить. Повторное решение не проходит (идемпотентный переход)."""
    contribution = await repo.money.get_contribution(contribution_id)
    if contribution is None or (house_id is not None and contribution["house_id"] != house_id):
        raise DomainError("Взнос не найден")
    await require(contribution["house_id"], resolved_by, "confirm_contributions")
    if contribution["status"] != STATUS_DECLARED:
        raise DomainError("Этот взнос уже решён")
    status = STATUS_CONFIRMED if confirm else STATUS_REJECTED
    if not await repo.money.set_contribution_status(contribution_id, status, resolved_by):
        raise DomainError("Этот взнос уже решён")
    return await repo.money.get_contribution(contribution_id)


async def pending_contributions(house_id: int) -> list:
    return await repo.money.pending_contributions(house_id)


def can_modify_contribution(contribution, actor: int, approver: bool, confirmation_required: bool) -> bool:
    """Автор правит своё, пока взнос не подтверждён (или подтверждение в доме не нужно); подтверждающий — любой."""
    if approver:
        return True
    return contribution["tg_id"] == actor and (contribution["status"] != STATUS_CONFIRMED or not confirmation_required)


async def _modifiable_contribution(house_id: int, contribution_id: int, actor: int, version: str):
    from services.settings import house_setting

    await require_member(house_id, actor)
    contribution = await repo.money.get_contribution(contribution_id)
    if contribution is None or contribution["house_id"] != house_id:
        raise DomainError("Взнос не найден")
    approver = await can(house_id, actor, "confirm_contributions")
    confirmation_required = await house_setting(house_id, "confirm_contributions")
    if not can_modify_contribution(contribution, actor, approver, confirmation_required):
        raise DomainError("Этот взнос может изменить автор, пока он не подтверждён, или жилец с правом «Взносы»")
    if contribution_version(contribution) != version:
        raise DomainError("Взнос уже изменили. Обновите историю и откройте его заново.")
    return contribution


async def edit_contribution(
    house_id: int, contribution_id: int, actor: int, *, amount_kop: int, paid_on: str, month: str, version: str,
) -> bool:
    """True — изменён, False — значения те же. Сумма и месяц подтверждённого взноса меняют остаток котла."""
    before = await _modifiable_contribution(house_id, contribution_id, actor, version)
    _validate_amount(amount_kop)
    after = {"amount_kop": amount_kop, "month": month, "paid_on": paid_on}
    if all(before[key] == value for key, value in after.items()):
        return False
    snapshot = {key: before[key] for key in ("id", "amount_kop", "month", "paid_on", "status")}
    if not await repo.money.edit_contribution(house_id, actor, snapshot, after):
        raise DomainError("Запись изменилась во время сохранения. Обновите историю и проверьте её.")
    return True


async def delete_contribution(house_id: int, contribution_id: int, actor: int, version: str) -> None:
    before = await _modifiable_contribution(house_id, contribution_id, actor, version)
    snapshot = {key: before[key] for key in ("id", "amount_kop", "month", "paid_on", "status")}
    if not await repo.money.delete_contribution_if_unchanged(house_id, snapshot):
        raise DomainError("Взнос изменился. Обновите историю перед удалением.")


# ── Траты и чеки ─────────────────────────────────────────────────────────────

async def add_expense(
    house_id: int, tg_id: int, amount_kop: int, category_id: int | None,
    spent_on: str, mode: str, description: str, photo_file_ids: list[str],
) -> int:
    from services.settings import house_settings, house_today

    await require_member(house_id, tg_id)
    _validate_amount(amount_kop)
    spent_on = parse_date(spent_on, house_today(await house_settings(house_id)))
    if mode not in (MODE_HOUSE, MODE_PERSONAL):
        raise DomainError("Неизвестный тип траты")
    if category_id is not None:
        category = await repo.money.get_category(category_id)
        if category is None or category["house_id"] != house_id:
            raise DomainError("Категория не найдена в этом доме")
    if len(description) > MAX_DESCRIPTION_LEN:
        raise DomainError(f"Описание — до {MAX_DESCRIPTION_LEN} символов")
    if len(photo_file_ids) > MAX_PHOTOS_PER_EXPENSE:
        raise DomainError(f"Чеков — не больше {MAX_PHOTOS_PER_EXPENSE}")
    return await repo.money.add_expense(
        house_id, tg_id, amount_kop, category_id, spent_on, mode, description.strip(),
        photo_file_ids,
    )


async def get_expense(expense_id: int):
    return await repo.money.get_expense(expense_id)


async def expense_photos(house_id: int, expense_id: int) -> list:
    expense = await repo.money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house_id:
        raise DomainError("Трата не найдена")
    return await repo.money.expense_photos(expense_id)


async def photos_count(expense_id: int) -> int:
    return await repo.money.photos_count(expense_id)


async def recent_expenses(house_id: int, limit: int) -> list:
    return await repo.money.recent_expenses(house_id, limit)


async def delete_expense(house_id: int, expense_id: int) -> None:
    expense = await repo.money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house_id:
        raise DomainError("Трата не найдена")
    await repo.money.delete_expense(expense_id)


async def reimburse_expense(
    house_id: int, expense_id: int, resolved_by: int, *, expected_version: str | None = None, idempotent: bool = False,
) -> None:
    """Вернуть «за свои» из котла — однократно."""
    await require(house_id, resolved_by, "confirm_contributions")
    expense = await repo.money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house_id:
        raise DomainError("Трата не найдена")
    if expense["mode"] != MODE_PERSONAL:
        raise DomainError("Эта трата и так из котла")
    if idempotent and expense["reimbursed"]:
        return
    if expected_version and expense_version(expense) != expected_version:
        raise DomainError("Трату уже изменили. Обновите историю и проверьте сумму возврата.")
    expected = dict(expense) if expected_version else None
    if not await repo.money.reimburse_expense(expense_id, resolved_by, expected=expected):
        current = await repo.money.get_expense(expense_id)
        if idempotent and current and current["reimbursed"]:
            return
        if expected_version:
            raise DomainError("Трата изменилась. Обновите историю и проверьте возврат.")
        raise DomainError("Эта трата уже возвращена")


async def unreimburse_expense(house_id: int, expense_id: int, actor: int, expected_version: str) -> None:
    """Отменить ошибочный возврат: сумма снова ждёт возврата, трату можно править."""
    await require(house_id, actor, "confirm_contributions")
    expense = await repo.money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house_id:
        raise DomainError("Трата не найдена")
    if not expense["reimbursed"]:
        raise DomainError("Возврат по этой трате не отмечен")
    if expense_version(expense) != expected_version:
        raise DomainError("Трату уже изменили. Обновите историю и проверьте её.")
    if not await repo.money.unreimburse_expense(house_id, actor, dict(expense)):
        raise DomainError("Трата изменилась. Обновите историю и повторите.")


# ── Категории ────────────────────────────────────────────────────────────────

async def categories(house_id: int) -> list:
    return await repo.money.list_categories(house_id)


async def add_category(house_id: int, name: str, *, reuse_existing: bool = False) -> int:
    name = name.strip()
    if not name:
        raise DomainError("Название категории не может быть пустым")
    if len(name) > MAX_CATEGORY_NAME_LEN:
        raise DomainError(f"Название категории — до {MAX_CATEGORY_NAME_LEN} символов")
    existing = {row["name"].casefold(): row["id"] for row in await repo.money.list_categories(house_id)}
    if name.casefold() in existing:
        if reuse_existing:
            return existing[name.casefold()]
        raise DomainError("Такая категория уже есть")
    return await repo.money.add_category(house_id, name)


async def remove_category(house_id: int, category_id: int) -> None:
    category = await repo.money.get_category(category_id)
    if category is None or category["house_id"] != house_id:
        raise DomainError("Категория не найдена")
    if await repo.money.category_expense_count(category_id):
        raise DomainError("В этой категории уже есть траты — категорию не удалить")
    await repo.money.delete_category(category_id)


async def rename_category(house_id: int, category_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise DomainError("Название категории не может быть пустым")
    if len(name) > MAX_CATEGORY_NAME_LEN:
        raise DomainError(f"Название категории — до {MAX_CATEGORY_NAME_LEN} символов")
    category = await repo.money.get_category(category_id)
    if category is None or category["house_id"] != house_id:
        raise DomainError("Категория не найдена")
    known = {row["name"].casefold(): row["id"] for row in await repo.money.list_categories(house_id)}
    if known.get(name.casefold(), category_id) != category_id:
        raise DomainError("Такая категория уже есть")
    await repo.money.rename_category(house_id, category_id, name)


# ── Баланс и отчёты ──────────────────────────────────────────────────────────

async def pot_balance(house_id: int) -> dict:
    confirmed = await repo.money.confirmed_total(house_id)
    house_spent = await repo.money.sum_expenses(house_id, MODE_HOUSE)
    reimbursed = await repo.money.sum_expenses(house_id, MODE_PERSONAL, only_reimbursed=True)
    return {
        "confirmed_total": confirmed,
        "house_spent": house_spent,
        "reimbursed": reimbursed,
        "balance": confirmed - house_spent - reimbursed,
    }


async def outstanding_personal(house_id: int) -> list:
    """Личные траты, ждущие возврата из котла (за все месяцы)."""
    return await repo.money.personal_unreimbursed(house_id)


async def month_report(house_id: int, month: str) -> dict:
    """Данные месячного отчёта: взносы, траты по категориям, баланс котла."""
    contributions = await repo.money.month_contributions(house_id, month)
    expenses = await repo.money.month_expenses(house_id, month)
    by_category: dict[str, int] = {}
    for row in expenses:
        name = row["category_name"] or "Без категории"
        by_category[name] = by_category.get(name, 0) + int(row["amount_kop"])
    return {
        "month": month,
        "contributions": contributions,
        "expenses": expenses,
        "by_category": by_category,
        "balance": await pot_balance(house_id),
        "outstanding": await outstanding_personal(house_id),
    }
