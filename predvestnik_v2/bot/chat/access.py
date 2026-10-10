"""Правила доступа, общие для всех команд чата.

Разработчик бота стоит над всеми ограничениями: к нему нельзя применить
никакую санкцию, и он может применять их к любому независимо от рангов.
"""
from __future__ import annotations

from bot.config import config


def is_developer(user_id: int | None) -> bool:
    return bool(user_id) and bool(config.developer_id) and int(user_id) == config.developer_id


def may_sanction(actor_id: int, target_id: int, *, actor_has_right: bool) -> bool:
    """Можно ли применить санкцию `actor` -> `target`.

    `actor_has_right` — есть ли у исполнителя право на это действие по рангу
    (для разработчика оно не требуется).
    """
    if is_developer(target_id):
        return False
    if is_developer(actor_id):
        return True
    return actor_has_right
