"""
Сервис валидации PIN и идемпотентности визитов (Block 4a).

Извлечён из log_visit() для соблюдения SRP и упрощения тестирования.
"""
from __future__ import annotations

from django.db.models import F
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from users.constants import (
    PIN_MAX_ATTEMPTS,
    PIN_LOCKOUT_MINUTES,
    IDEMPOTENCY_WINDOW,
)


def check_pin_lockout(member, now) -> tuple[bool, int]:
    """Проверяет заблокирован ли PIN у участника.

    Returns:
        (locked, remaining_minutes) — locked=True если ещё в окне блокировки.
    """
    if member.pin_lockout_until and member.pin_lockout_until > now:
        remaining = int((member.pin_lockout_until - now).total_seconds() // 60) + 1
        return True, remaining
    return False, 0


def process_pin_attempt(member, provided_pin, now) -> tuple[bool, str | None]:
    """Проверяет PIN и обновляет счётчики попыток атомарно.

    Args:
        member: объект User участника
        provided_pin: введённый PIN (строка)
        now: текущее datetime (timezone-aware)

    Returns:
        (ok, error_message)
        - ok=True: PIN верный, счётчик сброшен
        - ok=False, error_message: текст ошибки для формы
    """
    from users.models import User

    if member.verify_pin(provided_pin):
        # Сброс счётчика попыток атомарно (B1-03)
        if member.failed_pin_attempts:
            User.objects.filter(pk=member.pk).update(
                failed_pin_attempts=0,
                pin_lockout_until=None,
            )
            member.failed_pin_attempts = 0
            member.pin_lockout_until = None
        return True, None

    # Неверный PIN — атомарный инкремент (B1-02)
    with transaction.atomic():
        User.objects.filter(pk=member.pk).update(
            failed_pin_attempts=F('failed_pin_attempts') + 1
        )
        member.refresh_from_db(fields=['failed_pin_attempts'])

    if member.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
        User.objects.filter(pk=member.pk).update(
            pin_lockout_until=now + timezone.timedelta(minutes=PIN_LOCKOUT_MINUTES),
            failed_pin_attempts=0,
        )
        member.failed_pin_attempts = 0
        return False, _(
            '🔒 Too many wrong PINs. PIN locked for %(minutes)d minutes.'
        ) % {'minutes': PIN_LOCKOUT_MINUTES}

    attempts_left = PIN_MAX_ATTEMPTS - member.failed_pin_attempts
    return False, _(
        '❌ Invalid PIN. %(left)d attempt(s) remaining before lockout.'
    ) % {'left': attempts_left}


def check_idempotent_visit(partner, member, service_type, cost, window=IDEMPOTENCY_WINDOW):
    """Проверяет идемпотентность: не был ли такой же визит уже создан недавно.

    Returns:
        Visit | None — существующий визит если найден дубль, иначе None.
    """
    from users.models import Visit

    cutoff = timezone.now() - timezone.timedelta(seconds=window)
    return Visit.objects.filter(
        partner=partner,
        member=member,
        service_type=service_type,
        cost=cost,
        timestamp__gte=cutoff,
    ).first()
