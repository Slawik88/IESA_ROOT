# Service layer for PredvestnikBot.
# Handlers and API routes call service functions — no raw SQL outside db.py.
from .exceptions import (
    ServiceError,
    NotEnoughMoraError,
    PetAlreadyWalkingError,
    PetNotFoundError,
    ItemNotFoundError,
    BossLimitError,
    NotMarriedError,
)

__all__ = [
    "ServiceError",
    "NotEnoughMoraError",
    "PetAlreadyWalkingError",
    "PetNotFoundError",
    "ItemNotFoundError",
    "BossLimitError",
    "NotMarriedError",
]
