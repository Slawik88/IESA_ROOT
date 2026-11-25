"""Общие правила изменения взноса для журнала и команд сайта."""


def can_change_contribution(author: int, status: str, actor: int, can_confirm: bool) -> bool:
    return status in ("declared", "confirmed", "rejected") and (
        can_confirm or (author == actor and status == "declared")
    )
