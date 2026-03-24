"""
Custom exceptions for the service layer.

Handlers and API routes catch these to give friendly error messages without
leaking internal DB details.
"""


class ServiceError(Exception):
    """Base class for all service-layer errors."""


class NotEnoughMoraError(ServiceError):
    """Raised when a payment cannot be completed due to insufficient balance."""

    def __init__(self, have: int, need: int) -> None:
        self.have = have
        self.need = need
        super().__init__(f"Недостаточно Моры: есть {have}, нужно {need}")


class PetAlreadyWalkingError(ServiceError):
    """Raised when a pet walk is requested but the pet is already on a walk."""

    def __init__(self, mins_left: int) -> None:
        self.mins_left = mins_left
        super().__init__(f"Питомец уже гуляет, осталось {mins_left} мин.")


class PetNotFoundError(ServiceError):
    """Raised when the user has no pet."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or "Питомец не найден")


class ItemNotFoundError(ServiceError):
    """Raised when the requested item doesn't exist or doesn't belong to the user."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or "Предмет не найден")


class BossLimitError(ServiceError):
    """Raised when the user has reached the daily boss damage limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"Дневной лимит урона по боссу достигнут ({limit})")


class NotMarriedError(ServiceError):
    """Raised when a family-wallet operation is requested but the user is not in a couple."""

    def __init__(self) -> None:
        super().__init__("Семейный кошелёк доступен только состоящим в узах")
