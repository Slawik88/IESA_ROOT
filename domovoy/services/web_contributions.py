"""Правка взносов сайта: автор неподтверждённого или носитель права подтверждения."""
import json

from core.money import AmountError
from core.transaction_permissions import can_change_contribution
from core.transaction_versions import contribution_version
from infrastructure.repositories import money as money_repo, contribution_changes
from services import households, settings, transfers
from services.households import DomainError


async def _require(house_id: int, actor: int, row) -> None:
    await households.require_member(house_id, actor)
    can_confirm = await households.can(house_id, actor, "confirm_contributions")
    if not can_change_contribution(row["tg_id"], row["status"], actor, can_confirm):
        raise DomainError("Свой ожидающий взнос можно изменить самостоятельно. "
                          "Для остальных взносов нужно право подтверждения.")


async def _normalize(house_id: int, row, data: dict) -> dict:
    values = await settings.house_settings(house_id)
    try:
        return transfers.normalize_row({
            "kind": "contribution", "member_tg_id": row["tg_id"], "status": row["status"],
            "amount": data["amount"], "date": data["date"], "month": data.get("month"),
            "source_key": f"domovoy:{house_id}:contribution:{row['id']}", "currency": values["currency"],
        }, settings.house_today(values), values["currency"], {row["tg_id"]})
    except AmountError as exc:
        raise DomainError(str(exc)) from exc


async def edit(house_id: int, actor: int, contribution_id: int, data: dict, version: str) -> dict:
    await households.require_member(house_id, actor)
    original = await money_repo.get_contribution(contribution_id)
    if original is None or original["house_id"] != house_id:
        raise DomainError("Взнос не найден в этом доме")
    await _require(house_id, actor, original)
    normalized = await _normalize(house_id, original, data)
    after = {"amount_kop": normalized["amount_kop"], "paid_on": normalized["date"], "month": normalized["month"]}
    current = dict(original)
    if contribution_version(original) != version:
        # Повтор нашей уже записанной правки безопасен, пока состояние/статус совпадают
        # с её аудитом. Чужое решение по взносу этот путь не пропускает.
        if (all(current[key] == value for key, value in after.items())
                and await contribution_changes.matching_edit(house_id, contribution_id, actor, version, current)):
            return {"ok": True, "unchanged": True, "id": contribution_id,
                    "version": contribution_version(current)}
        raise DomainError("Взнос уже изменили или подтвердили. Обновите историю и откройте его заново.")
    if all(current[key] == value for key, value in after.items()):
        return {"ok": True, "unchanged": True, "id": contribution_id, "version": version}
    if not await contribution_changes.edit(house_id, actor, current, after, version):
        raise DomainError("Взнос или ваши права изменились во время сохранения. Обновите историю.")
    return {"ok": True, "unchanged": False, "id": contribution_id,
            "version": contribution_version({**current, **after})}


async def remove(house_id: int, actor: int, contribution_id: int, version: str) -> dict:
    await households.require_member(house_id, actor)
    original = await money_repo.get_contribution(contribution_id)
    if original is None:
        tombstone = await contribution_changes.deleted(house_id, contribution_id, version)
        if tombstone is None:
            raise DomainError("Взнос не найден в этом доме")
        await _require(house_id, actor, json.loads(tombstone["before_json"]))
        return {"ok": True, "duplicate": True}
    if original["house_id"] != house_id:
        raise DomainError("Взнос не найден в этом доме")
    await _require(house_id, actor, original)
    if contribution_version(original) != version:
        raise DomainError("Взнос уже изменили или подтвердили. Обновите историю перед удалением.")
    kop = original["amount_kop"]
    canonical = await _normalize(house_id, original, {
        "amount": f"{kop // 100}.{kop % 100:02d}", "date": original["paid_on"], "month": original["month"],
    })
    if not await contribution_changes.remove(house_id, actor, dict(original), version, canonical):
        tombstone = await contribution_changes.deleted(house_id, contribution_id, version)
        if tombstone:
            await _require(house_id, actor, json.loads(tombstone["before_json"]))
            return {"ok": True, "duplicate": True}
        raise DomainError("Взнос или ваши права изменились во время удаления. Обновите историю.")
    return {"ok": True, "duplicate": False}
