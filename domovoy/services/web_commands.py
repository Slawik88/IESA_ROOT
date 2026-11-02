"""Команды сайта с проверкой дома и устойчивым ключом повторной отправки."""
from infrastructure import repositories as repo
from infrastructure.repositories import transactions
from services import households, money, settings, transfers, notify
from core.money import AmountError, format_amount
from core.transaction_versions import expense_version
from services.households import DomainError


async def create_transaction(house_id: int, actor: int, data: dict, *, bot=None) -> dict:
    await households.require_member(house_id, actor)
    values = await settings.house_settings(house_id)
    kind = data["kind"]
    category_name = ""
    if data.get("category_id"):
        categories = {row["id"]: row["name"] for row in await money.categories(house_id)}
        if data["category_id"] not in categories:
            raise DomainError("Категория не найдена в этом доме")
        category_name = categories[data["category_id"]]
    status = "declared" if kind == "contribution" and values["confirm_contributions"] else "confirmed"
    try:
        row = transfers.normalize_row({
            **data, "source_key": f"web:{actor}:{data['request_id']}", "member_tg_id": actor,
            "category": category_name, "status": status, "currency": values["currency"], "reimbursed": "0",
        }, settings.house_today(values), values["currency"], {actor})
    except AmountError as exc:
        raise DomainError(str(exc)) from exc
    try:
        added, skipped = await transactions.apply_import(house_id, actor, [row])
    except ValueError as exc:
        raise DomainError("Эта отправка уже сохранена с другими данными. Начните новую запись.") from exc
    if added and bot is not None:
        house = await households.get_house(house_id)
        if kind == "contribution" and status == "declared":
            await notify.contribution_declared(bot, house, {
                "tg_id": actor, "amount_kop": row["amount_kop"], "month": row["month"],
            }, values["currency"])
        elif kind == "expense":
            member = await households.membership(house_id, actor)
            formatted = format_amount(row["amount_kop"], values["currency"])
            await notify.broadcast(bot, house, "expense_added",
                                   f"🧾 {member['display_name']}: {formatted} "
                                   f"— {category_name or 'Без категории'} · {row['date']}", exclude_tg_ids={actor})
    target_id = await transactions.imported_target_id(house_id, row["source_key"])
    return {"added": added, "duplicate": bool(skipped), "status": status,
            "id": target_id}


async def edit_expense(house_id: int, actor: int, expense_id: int, data: dict, version: str) -> dict:
    await households.require_member(house_id, actor)
    original = await money.get_expense(expense_id)
    if original is None or original["house_id"] != house_id:
        raise DomainError("Трата не найдена в этом доме")
    if original["tg_id"] != actor:
        await households.require(house_id, actor, "manage_all_expenses")
    values = await settings.house_settings(house_id)
    categories = {row["id"]: row["name"] for row in await money.categories(house_id)}
    category_id = data.get("category_id")
    if category_id is not None and category_id not in categories:
        raise DomainError("Категория не найдена в этом доме")
    try:
        normalized = transfers.normalize_row({
            **data, "kind": "expense", "member_tg_id": original["tg_id"],
            "category": categories.get(category_id, ""), "currency": values["currency"],
            "status": "confirmed", "reimbursed": "0",
        }, settings.house_today(values), values["currency"], {original["tg_id"]})
    except AmountError as exc:
        raise DomainError(str(exc)) from exc
    after = {"amount_kop": normalized["amount_kop"], "category_id": category_id,
             "spent_on": normalized["date"], "mode": normalized["mode"], "description": normalized["description"]}
    if all(original[key] == value for key, value in after.items()):
        return {"ok": True, "unchanged": True}
    if original["reimbursed"]:
        raise DomainError("Эта трата уже возвращена. Проведённый возврат не редактируется.")
    if expense_version(original) != version:
        raise DomainError("Трату уже изменили. Обновите историю и откройте её заново; ваш текст оставлен в форме.")
    if not await repo.money.edit_expense(house_id, actor, dict(original), after):
        raise DomainError("Запись изменилась во время сохранения. Обновите историю и проверьте её.")
    return {"ok": True, "unchanged": False}
