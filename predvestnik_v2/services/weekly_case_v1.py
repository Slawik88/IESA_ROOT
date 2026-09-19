"""Application service for the sequential, catch-up friendly case catalog."""
from __future__ import annotations

from core.reconstruction import BALANCE_VERSION, GAME_VERSION
from core.retention_v3 import DAILY_CONTRACTS
from core.weekly_case_v1 import CASE_CATALOG, POLICY_VERSION, case_for_policy, case_view, definition_digest, finale_id, next_case
from infrastructure.repositories import gameplay_events as event_repo
from infrastructure.repositories import reconstruction as reconstruction_repo
from infrastructure.repositories import weekly_case_v1 as repo

class WeeklyCaseError(ValueError): pass
class WeeklyCaseConflict(WeeklyCaseError): pass

async def _ensure_user(db, user_id: int) -> None:
    if not await repo.has_catalog(db, user_id):
        first = CASE_CATALOG[0]
        legacy = await repo.legacy_case(db, user_id, POLICY_VERSION)
        legacy_days = await repo.legacy_days(db, user_id, POLICY_VERSION) if legacy else []
        path_id = legacy.get("path_id") if legacy else None
        progress = min(int(first["target_days"]), int((legacy or {}).get("progress_days") or 0))
        complete = bool(path_id and progress >= int(first["target_days"]))
        categories = {DAILY_CONTRACTS.get(str(item["contract_id"]), {}).get("category") for item in legacy_days}
        categories.discard(None)
        candidate_finale = (legacy or {}).get("finale_id")
        if candidate_finale and candidate_finale not in first["finales"]:
            raise RuntimeError("Legacy Weekly Case has an unknown frozen finale")
        frozen_finale = (candidate_finale or finale_id(categories)) if complete else None
        completed_at = ((legacy or {}).get("completed_at") or (legacy or {}).get("assigned_at")) if complete else None
        await repo.create_case(db, user_id=user_id, case_id=first["case_id"], case_order=1,
            policy_version=first["policy_version"], definition_digest=definition_digest(first),
            target_days=first["target_days"], path_id=path_id, progress_days=progress,
            finale_id=frozen_finale, assigned_at=(legacy or {}).get("assigned_at"),
            chosen_at=(legacy or {}).get("chosen_at"), completed_at=completed_at)
        for item in legacy_days:
            contract_id = str(item["contract_id"])
            category = str(DAILY_CONTRACTS.get(contract_id, {}).get("category") or "legacy")
            await repo.import_day(db, user_id=user_id, day_key=item["day_key"], case_id=first["case_id"], contract_id=contract_id, category=category)

    rows = await repo.all_cases(db, user_id)
    by_id = {str(item["case_id"]): item for item in rows}
    for order, case in enumerate(CASE_CATALOG, 1):
        row = by_id.get(str(case["case_id"]))
        if not row:
            continue
        if (int(row["case_order"]) != order or str(row["policy_version"]) != case["policy_version"]
                or int(row["target_days"]) != int(case["target_days"])):
            raise RuntimeError("Weekly Case immutable catalog prefix conflict")
        if row.get("path_id") and str(row["path_id"]) not in case["paths"]:
            raise RuntimeError("Weekly Case contains an unknown frozen path")
        if row.get("finale_id") and str(row["finale_id"]) not in case["finales"]:
            raise RuntimeError("Weekly Case contains an unknown frozen finale")
        if row.get("completed_at") and (not row.get("path_id") or int(row["progress_days"]) != int(row["target_days"])):
            raise RuntimeError("Weekly Case completed row violates terminal invariants")
        await repo.bind_definition(db, user_id=user_id, case_id=case["case_id"], digest=definition_digest(case))

    rows = await repo.all_cases(db, user_id)
    if any(not row.get("completed_at") for row in rows):
        return
    next_order = len(rows) + 1
    if next_order <= len(CASE_CATALOG):
        following = CASE_CATALOG[next_order - 1]
        await repo.create_case(db, user_id=user_id, case_id=following["case_id"],
            case_order=next_order, policy_version=following["policy_version"],
            definition_digest=definition_digest(following), target_days=following["target_days"])

async def _row_view(db, user_id: int, row: dict) -> dict:
    case = case_for_policy(str(row["policy_version"]))
    if not case or case["case_id"] != row["case_id"]:
        raise RuntimeError("Weekly Case catalog definition mismatch")
    return case_view(row, await repo.categories_for_case(db, user_id, row["case_id"]), case)

async def _catalog_view(db, user_id: int) -> dict:
    rows = await repo.all_cases(db, user_id)
    active_row = next((row for row in rows if not row.get("completed_at")), None)
    completed_rows = [row for row in rows if row.get("completed_at")]
    archive = [await _row_view(db, user_id, row) for row in completed_rows]
    if active_row:
        result = await _row_view(db, user_id, active_row)
    else:
        result = {"policy_version":"weekly-catalog-v2-2026-08-28","case_id":None,
            "title":"Каталог дел завершён","intro":"Все текущие дела раскрыты. Финалы сохранены в Архиве.",
            "path_id":None,"paths":[],"progress_days":0,"target_days":0,"reveals":[],
            "completed":True,"finale":None,"next_case_available":False,
            "catalog_position":len(CASE_CATALOG),"catalog_total":len(CASE_CATALOG),
            "expires":False,"stars_can_buy_progress":False,"economic_reward":None}
    result["catalog_version"] = repo.CATALOG_VERSION
    result["catalog_completed"] = active_row is None
    result["archive"] = {"completed_count":len(archive),"total":len(CASE_CATALOG),"cases":archive}
    result["latest_completed"] = archive[-1] if archive else None
    return result

async def overview(db, user_id: int) -> dict:
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db, user_id)
        await _ensure_user(db, user_id)
        return await _catalog_view(db, user_id)

async def _record_completion(db, user_id: int, view: dict, trigger: str, source: str) -> None:
    await event_repo.record_event(db,user_id=user_id,event_name="weekly_case_completed",
        game_version=GAME_VERSION,balance_version=BALANCE_VERSION,source=source,
        payload={"policy_version":view["policy_version"],"case_id":view["case_id"],"path_id":view["path_id"],"finale_id":view["finale"]["id"],"completion_trigger":trigger},
        idempotency_key=f"weekly-case:{repo.CATALOG_VERSION}:{user_id}:{view['case_id']}:completed")

async def _finish_and_assign_next(db, user_id: int, row: dict, source: str, trigger: str) -> bool:
    view = await _row_view(db, user_id, row)
    if not view["completed"]: return False
    frozen = await repo.complete_case(db,user_id=user_id,case_id=row["case_id"],finale_id=view["finale"]["id"])
    if not frozen: return False
    view = await _row_view(db, user_id, frozen)
    await _record_completion(db,user_id,view,trigger,source)
    following = next_case(str(row["policy_version"]))
    if following:
        await repo.create_case(db,user_id=user_id,case_id=following["case_id"],
            case_order=int(view["catalog_position"])+1,policy_version=following["policy_version"],
            definition_digest=definition_digest(following),target_days=following["target_days"])
    return True

async def choose_path(db, user_id: int, case_id: str, path_id: str, *, source: str="mini_app") -> dict:
    case_id,path_id=str(case_id or "").strip(),str(path_id or "").strip()
    async with db.connection.transaction():
        await reconstruction_repo.lock_user(db,user_id); await _ensure_user(db,user_id)
        current=await repo.active_case(db,user_id)
        if not current or current["case_id"] != case_id:
            previous = await repo.case_by_id(db, user_id, case_id)
            if previous and previous.get("path_id") == path_id:
                return await _catalog_view(db,user_id)
            raise WeeklyCaseConflict("Карточка устарела: открой текущее Дело заново.")
        case=case_for_policy(str(current["policy_version"]))
        if not case or path_id not in case["paths"]: raise WeeklyCaseError("Неизвестный путь текущего Дела.")
        if current.get("path_id") == path_id:
            return await _catalog_view(db,user_id)
        if current.get("path_id") not in (None,path_id): raise WeeklyCaseConflict("Путь уже выбран и не меняется.")
        updated=await repo.choose_path(db,user_id,case_id,path_id)
        if not updated: raise WeeklyCaseConflict("Дело уже изменилось в другой вкладке.")
        await event_repo.record_event(db,user_id=user_id,event_name="weekly_case_path_chosen",game_version=GAME_VERSION,balance_version=BALANCE_VERSION,source=source,
            payload={"policy_version":current["policy_version"],"case_id":case_id,"path_id":path_id},idempotency_key=f"weekly-case:{repo.CATALOG_VERSION}:{user_id}:{case_id}:path")
        await _finish_and_assign_next(db,user_id,updated,source,"path_chosen")
        return await _catalog_view(db,user_id)

async def apply_completed_day(db, *, user_id: int, day_key: str, contract_id: str, source: str="mini_app") -> dict | None:
    """Advance at most one catalog case per UTC day; caller owns transaction."""
    await reconstruction_repo.lock_user(db,user_id); await _ensure_user(db,user_id)
    current=await repo.active_case(db,user_id)
    if not current: return None
    category=str(DAILY_CONTRACTS.get(contract_id,{}).get("category") or "unknown")
    updated=await repo.add_completed_day(db,user_id=user_id,case_id=current["case_id"],day_key=day_key,contract_id=contract_id,category=category)
    if not updated: return None
    preview=await _row_view(db,user_id,updated)
    await event_repo.record_event(db,user_id=user_id,event_name="weekly_case_progressed",game_version=GAME_VERSION,balance_version=BALANCE_VERSION,source=source,
        payload={"policy_version":updated["policy_version"],"case_id":updated["case_id"],"path_id":updated.get("path_id"),"day_key":day_key,"progress":int(updated["progress_days"]),"target":int(updated["target_days"]),"completed":bool(preview["completed"])},
        idempotency_key=f"weekly-case:{repo.CATALOG_VERSION}:{user_id}:day:{day_key}")
    await _finish_and_assign_next(db,user_id,updated,source,"meaningful_day")
    return await _catalog_view(db,user_id)
