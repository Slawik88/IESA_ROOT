"""
Репозитории «Домового»: только SQL, логика — в services/.

Субмодули импортированы явно, чтобы `repo.houses`, `repo.money` и т.д. работали
из любого слоя без дополнительных импортов.
"""
from infrastructure.repositories import (  # noqa: F401
    houses,
    money,
    schedule,
    settings,
    users,
)
