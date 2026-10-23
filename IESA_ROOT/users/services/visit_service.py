"""
Сервис валидации PIN и идемпотентности визитов (Block 4a).

Извлечён из log_visit() для соблюдения SRP и упрощения тестирования.
"""
from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _

from users.constants import (
    EDIT_WINDOW,
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


@transaction.atomic
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

    # A caller's instance can predate a concurrent failed attempt or lockout.
    current = User.objects.select_for_update().get(pk=member.pk)
    locked, remaining = check_pin_lockout(current, now)
    if locked:
        member.failed_pin_attempts = current.failed_pin_attempts
        member.pin_lockout_until = current.pin_lockout_until
        return False, _(
            'PIN entry is temporarily locked for this member. Please wait %(remaining)d minute(s).'
        ) % {'remaining': remaining}

    ok = current.verify_pin(provided_pin)
    error = None
    if ok:
        current.failed_pin_attempts = 0
        current.pin_lockout_until = None
    else:
        current.failed_pin_attempts += 1
        if current.failed_pin_attempts >= PIN_MAX_ATTEMPTS:
            current.failed_pin_attempts = 0
            current.pin_lockout_until = now + timezone.timedelta(minutes=PIN_LOCKOUT_MINUTES)
            error = _('🔒 Too many wrong PINs. PIN locked for %(minutes)d minutes.') % {
                'minutes': PIN_LOCKOUT_MINUTES,
            }
        else:
            error = _('❌ Invalid PIN. %(left)d attempt(s) remaining before lockout.') % {
                'left': PIN_MAX_ATTEMPTS - current.failed_pin_attempts,
            }
    # Avoid unrelated User.save signals (QR storage, etc.).
    User.objects.filter(pk=current.pk).update(
        failed_pin_attempts=current.failed_pin_attempts,
        pin_lockout_until=current.pin_lockout_until,
    )
    member.failed_pin_attempts = current.failed_pin_attempts
    member.pin_lockout_until = current.pin_lockout_until
    return ok, error


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
    ).order_by('-timestamp', '-pk').first()


@transaction.atomic
def log_verified_visit(*, partner, member, data):
    """Serialize duplicate checks and creation; PIN must be checked by caller."""
    from users.models import User, Visit
    from .visit_notifications import notify_visit_logged

    User.objects.select_for_update().get(pk=member.pk)
    existing = check_idempotent_visit(partner, member, data['service_type'], data.get('cost'))
    if existing:
        return existing, False
    visit = Visit.objects.create(
        partner=partner, member=member, pin_verified=True, status='ACTIVE',
        **{field: data[field] for field in ('service_type', 'service_description', 'cost', 'comments')},
    )
    transaction.on_commit(lambda: notify_visit_logged(visit, partner, member), robust=True)
    return visit, True


class VisitChangeError(ValueError):
    """The locked record can no longer be changed (expired or cancelled)."""


@transaction.atomic
def change_visit(*, visit_id, partner, actor, data, cancel=False):
    """Persist a visit and its previous values together, under a row lock.

    Reload after validation: ModelForm.is_valid() mutates its instance.
    Concurrent edits/cancellation must observe the latest committed record.
    """
    from users.models import Visit, VisitAudit
    from .visit_notifications import notify_visit_cancelled, notify_visit_edited

    visit = get_object_or_404(Visit.objects.select_for_update(), pk=visit_id, partner=partner)
    if (timezone.now() - visit.timestamp).total_seconds() > EDIT_WINDOW:
        raise VisitChangeError(_('The edit window has expired. Visits can only be edited within 20 minutes of logging.'))
    if visit.status == 'CANCELLED':
        raise VisitChangeError(_('Cancelled visits cannot be edited.'))

    audit = VisitAudit.objects.create(
        visit=visit, action=VisitAudit.ACTION_CANCEL if cancel else VisitAudit.ACTION_EDIT,
        previous_service_type=visit.get_service_type_display(),
        previous_service_description=visit.service_description,
        previous_cost=visit.cost, previous_comments=visit.comments,
        reason=data['reason'], changed_by=actor,
    )
    fields = ['status']
    if not cancel:
        fields += ['service_type', 'service_description', 'cost', 'comments']
        for field in fields[1:]:
            setattr(visit, field, data[field])
    visit.status = 'CANCELLED' if cancel else 'EDITED'
    visit.save(update_fields=fields)
    notify = notify_visit_cancelled if cancel else notify_visit_edited
    transaction.on_commit(lambda: notify(visit, audit, partner), robust=True)
    return visit, audit
