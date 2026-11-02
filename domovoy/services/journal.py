"""Поиск, фильтры и итоги по одному набору денежных операций."""
from dataclasses import dataclass

from core.constants import JOURNAL_SEARCH_LIMIT, QUICK_TRANSACTION_LIMIT, WEB_HOME_RECENT_LIMIT, WEB_JOURNAL_PAGE_SIZE
from core.transaction_versions import expense_version
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


async def view(house_id: int, actor: int, query: JournalQuery, page: int = 0) -> dict:
    await households.require_member(house_id, actor)
    all_rows = [dict(row) for row in await transactions.all_rows(house_id)]
    manage_all = await households.can(house_id, actor, "manage_all_expenses")
    for row in all_rows:
        row["house_id"] = house_id
        row["can_edit"] = (row["kind"] == "expense" and not row["reimbursed"]
                           and (row["tg_id"] == actor or manage_all))
        row["version"] = expense_version(row) if row["kind"] == "expense" else None
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
            "page": page, "total": len(selected), "summary": summary, "templates": templates,
            "page_size": WEB_JOURNAL_PAGE_SIZE,
            "filter_members": [{"id": actor_id, "name": name} for actor_id, name in
                               {row["tg_id"]: row["display_name"] or "Жилец" for row in all_rows}.items()]}
