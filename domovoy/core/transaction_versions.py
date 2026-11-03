"""Версия содержимого траты для защиты от перезаписи параллельных правок."""
import hashlib
import json


def expense_version(source) -> str:
    row = dict(source)
    fields = ("id", "house_id", "tg_id", "amount_kop", "category_id", "mode", "description", "reimbursed")
    content = {key: row[key] for key in fields}
    content["spent_on"] = row.get("spent_on", row.get("date"))
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def contribution_version(source) -> str:
    """Версия взноса: решение владельца или правка автора меняют её, поэтому устаревшую форму сервер отклонит."""
    row = dict(source)
    content = {key: row[key] for key in ("id", "house_id", "tg_id", "amount_kop", "month", "status")}
    content["paid_on"] = row.get("paid_on", row.get("date"))
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
