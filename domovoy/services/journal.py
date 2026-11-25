"""Поиск, фильтры и итоги по одному набору денежных операций."""
from dataclasses import dataclass

from core.constants import JOURNAL_SEARCH_LIMIT, QUICK_TRANSACTION_LIMIT, WEB_HOME_RECENT_LIMIT, WEB_JOURNAL_PAGE_SIZE
from core.transaction_versions import expense_version, contribution_version
from core.transaction_permissions import can_change_contribution
from infrastructure.repositories import transactions
from services import households
from services.households import DomainError
from services.transaction_dates import parse_month


@dataclass(frozen=True)
class JournalQuery:
    month: str | None = None
    q: str = ""
    kind: str = "all"
    member: int | None = None
    category: int | None = None
    mode: str = "all"
    sort: str = "newest"


def filter_rows(rows: list, query: JournalQuery) -> list:
    month = parse_month(query.month) if query.month else None
    if len(query.q) > JOURNAL_SEARCH_LIMIT:
        raise DomainError(f"Поисковый запрос — до {JOURNAL_SEARCH_LIMIT} символов")
    if (query.kind not in ("all", "expense", "contribution") or
            query.mode not in ("all", "house", "personal", "waiting_return") or
            query.sort not in ("newest", "oldest", "largest", "smallest")):
        raise DomainError("Неизвестный фильтр журнала")
    words = query.q.casefold().split()
    result = []
    for row in rows:
        if month and row["month"] != month:
            continue
        if query.kind != "all" and row["kind"] != query.kind:
            continue
        if query.member is not None and row["tg_id"] != query.member:
            continue
        if query.category is not None and row["category_id"] != query.category:
            continue
        if query.mode == "waiting_return":
            if row["kind"] != "expense" or row["mode"] != "personal" or row["reimbursed"]:
                continue
        elif query.mode != "all" and row["mode"] != query.mode:
            continue
        text = " ".join(str(row[key] or "") for key in ("display_name", "category", "description", "date"))
        text += " " + ".".join(str(row["date"]).split("-")[::-1])
        if any(word not in text.casefold() for word in words):
            continue
        result.append(row)
    if query.sort == "newest":
        result.sort(key=lambda row: (row["date"], row["kind"], row["id"]), reverse=True)
    elif query.sort == "oldest":
        result.sort(key=lambda row: (row["date"], row["kind"], row["id"]))
    elif query.sort in ("largest", "smallest"):
        result.sort(key=lambda row: (row["amount_kop"], row["date"], row["id"]), reverse=query.sort == "largest")
    return result


async def decorate_rows(house_id: int, actor: int, source_rows: list) -> list[dict]:
    await households.require_member(house_id, actor)
    rows = [dict(row) for row in source_rows]
    manage_all = await households.can(house_id, actor, "manage_all_expenses")
    can_confirm = await households.can(house_id, actor, "confirm_contributions")
    for row in rows:
        row["house_id"] = house_id
        if row["kind"] == "expense":
            row["can_edit"] = not row["reimbursed"] and (row["tg_id"] == actor or manage_all)
            row["version"] = expense_version(row)
            reason = "reimbursed_expense" if row["reimbursed"] else "other_author"
        else:
            row["can_edit"] = can_change_contribution(row["tg_id"], row["status"], actor, can_confirm)
            row["version"] = contribution_version(row)
            reason = "resolved_contribution" if row["status"] != "declared" else "other_author"
        row["can_delete"] = row["can_edit"]
        row["read_only_reason"] = None if row["can_edit"] else reason
    return rows


async def transaction(house_id: int, actor: int, kind: str, transaction_id: int) -> dict:
    await households.require_member(house_id, actor)
    row = await transactions.get_row(house_id, kind, transaction_id)
    if row is None:
        raise DomainError("Операция не найдена в этом доме")
    return (await decorate_rows(house_id, actor, [row]))[0]


async def view(house_id: int, actor: int, query: JournalQuery, page: int = 0) -> dict:
    await households.require_member(house_id, actor)
    all_rows = await decorate_rows(house_id, actor, await transactions.all_rows(house_id))
    selected = filter_rows(all_rows, query)
    page = max(0, min(page, max(0, (len(selected) - 1) // WEB_JOURNAL_PAGE_SIZE)))
    summary = {"expenses": 0, "contributions": 0, "pending": 0, "waiting_return": 0}
    for row in selected:
        if row["kind"] == "expense":
            summary["expenses"] += row["amount_kop"]
            if row["mode"] == "personal" and not row["reimbursed"]:
                summary["waiting_return"] += row["amount_kop"]
        elif row["status"] == "confirmed":
            summary["contributions"] += row["amount_kop"]
        elif row["status"] == "declared":
            summary["pending"] += row["amount_kop"]
    recent_rows = sorted(all_rows, key=lambda row: (row["created_at"], row["id"], row["kind"]), reverse=True)
    templates, seen = [], set()
    for row in recent_rows:
        if row["tg_id"] != actor:
            continue
        identity = (row["kind"], row["amount_kop"], row["category_id"], row["mode"], row["description"])
        if identity not in seen:
            templates.append(row)
            seen.add(identity)
        if len(templates) == QUICK_TRANSACTION_LIMIT:
            break
    return {"recent": recent_rows[:WEB_HOME_RECENT_LIMIT],
            "rows": selected[page * WEB_JOURNAL_PAGE_SIZE:(page + 1) * WEB_JOURNAL_PAGE_SIZE],
            "page": page, "total": len(selected), "summary": summary, "analytics": expense_breakdown(selected),
            "templates": templates,
            "page_size": WEB_JOURNAL_PAGE_SIZE,
            "filter_members": [{"id": actor_id, "name": name} for actor_id, name in
                               {row["tg_id"]: row["display_name"] or "Жилец" for row in all_rows}.items()]}


def expense_breakdown(rows: list[dict]) -> dict:
    """Расходы из полной выборки; возврат не является второй покупкой."""
    categories, members = {}, {}
    for row in rows:
        member = members.setdefault(row["tg_id"], {
            "id": row["tg_id"], "name": row["display_name"] or "Жилец",
            "expenses": 0, "contributions": 0, "waiting_return": 0,
        })
        kop = row["amount_kop"]
        if row["kind"] == "contribution":
            if row["status"] == "confirmed":
                member["contributions"] += kop
            continue
        member["expenses"] += kop
        if row["mode"] == "personal" and not row["reimbursed"]:
            member["waiting_return"] += kop
        category = categories.setdefault(row["category_id"], {
            "id": row["category_id"], "name": row["category"] or "Без категории", "amount_kop": 0, "count": 0,
        })
        category["amount_kop"] += kop
        category["count"] += 1
    return {
        "categories": sorted(categories.values(), key=lambda item: (-item["amount_kop"], item["name"])),
        "members": sorted(members.values(), key=lambda item: (-item["expenses"], item["id"])),
    }
