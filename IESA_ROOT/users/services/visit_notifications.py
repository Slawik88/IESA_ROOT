"""
Сервис уведомлений о визитах партнёра.

Единое место для логики создания in-site уведомлений и отправки TG-сообщений
при трёх событиях: логирование (logged), редактирование (edited), отмена (cancelled).

Избавляет от дублирования ~90 строк кода в log_visit(), edit_visit(), cancel_visit().
"""
from __future__ import annotations

import logging
import threading

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

# Ссылка на профиль с закреплённым PIN-разделом (Block 1: /cabinet/ → /profile/#pin-section)
_PROFILE_PIN_LINK = '/auth/profile/#pin-section'


def notify_visit_logged(visit, partner, member) -> None:
    """
    Уведомление при логировании нового визита:
      - всегда создаёт in-site notification
      - если TG привязан — шлёт TG-уведомление в фоне
      - если TG НЕ привязан — создаёт дополнительный in-site с приглашением привязать
    """
    from notifications.models import Notification as _Notif

    _cost_txt = f' — {visit.cost} CHF' if visit.cost else ''
    _pin_txt  = ' ✓ (PIN verified)' if visit.pin_verified else ''

    _Notif.objects.create(
        recipient=member,
        notification_type='system',
        title=f'✅ {partner.company_name} — {visit.get_service_type_display()}',
        message=_(
            'Partner %(company)s has recorded your visit.\n'
            'Service: %(service)s%(cost)s%(pin)s.\n'
            'Date: %(date)s.'
        ) % {
            'company': partner.company_name,
            'service': visit.get_service_type_display(),
            'cost':    _cost_txt,
            'pin':     _pin_txt,
            'date':    visit.timestamp.strftime('%d %b %Y, %H:%M'),
        },
        link=_PROFILE_PIN_LINK,
    )

    if getattr(member, 'telegram_chat_id', None):
        _visit_id = visit.pk

        def _notify_tg():
            try:
                from users.models import Visit as _Visit
                from users.telegram.notify import notify_visit_confirmed as _notify
                _v = _Visit.objects.select_related('member', 'partner').get(pk=_visit_id)
                _notify(_v)
            except Exception as exc:
                logger.error("bg notify_visit_confirmed failed: %s", exc)

        threading.Thread(target=_notify_tg, daemon=True).start()
    else:
        _Notif.objects.create(
            recipient=member,
            notification_type='system',
            title='📱 Connect Telegram for instant notifications',
            message=_(
                "You don't have Telegram connected yet. "
                'Connect @IESA_Administrator_bot to receive instant notifications about '
                'your visits at %(company)s and other partners!'
            ) % {'company': partner.company_name},
            link='/auth/connect-telegram/',
        )


def notify_visit_edited(visit, audit, partner) -> None:
    """
    Уведомление при редактировании визита (in-site + TG).
    """
    from notifications.models import Notification as _Notif
    from users.telegram import notify_visit_edited as _tg_notify

    _cost_txt = f' — {visit.cost} CHF' if visit.cost else ''

    _Notif.objects.create(
        recipient=visit.member,
        notification_type='system',
        title=f'✏️ Visit updated — {partner.company_name}',
        message=_(
            'Partner %(company)s has updated your visit record.\n'
            'Service: %(service)s%(cost)s.\n'
            'Reason: %(reason)s'
        ) % {
            'company': partner.company_name,
            'service': visit.get_service_type_display(),
            'cost':    _cost_txt,
            'reason':  audit.reason or _('No reason specified'),
        },
        link=_PROFILE_PIN_LINK,
    )

    try:
        _tg_notify(visit, audit)
    except Exception as exc:
        logger.error("notify_visit_edited (TG) failed: %s", exc)


def notify_visit_cancelled(visit, audit, partner) -> None:
    """
    Уведомление при отмене визита (in-site + TG).
    """
    from notifications.models import Notification as _Notif
    from users.telegram import notify_visit_cancelled as _tg_notify

    _Notif.objects.create(
        recipient=visit.member,
        notification_type='system',
        title=f'❌ Visit cancelled — {partner.company_name}',
        message=_(
            'Partner %(company)s has cancelled your visit record.\n'
            'Service that was logged: %(service)s.\n'
            'Reason: %(reason)s'
        ) % {
            'company': partner.company_name,
            'service': visit.get_service_type_display(),
            'reason':  audit.reason or _('No reason specified'),
        },
        link=_PROFILE_PIN_LINK,
    )

    try:
        _tg_notify(visit, audit)
    except Exception as exc:
        logger.error("notify_visit_cancelled (TG) failed: %s", exc)
