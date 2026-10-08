"""
Email Service for IESA Sport
============================
Delivers all transactional emails (visit confirmation/edit/cancel,
password reset notifications, etc.).

Delivery priority
-----------------
1. CleverReach REST API  — used when CLEVERREACH_CLIENT_ID is set in env
2. Django SMTP backend  — fallback (Resend SMTP or console in local dev)

This means: set CLEVERREACH_* Heroku config vars to switch to CleverReach;
remove / unset them to fall back to Django's EMAIL_BACKEND automatically.
"""
import logging
from django.core.mail import get_connection, send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

ADMIN_EMAIL = 'makssmart29@gmail.com'


def _get_from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'IESA Sport <noreply@iesasport.ch>')


def _site_domain():
    return getattr(settings, 'SITE_DOMAIN', 'iesasport.ch')


def _render_email(template, **context):
    """Render users/email/<template>.html on the shared dark layout (see _layout.html)."""
    context.setdefault('domain', _site_domain())
    context.setdefault('support_email', 'iesa@iesasport.ch')
    return render_to_string(f'users/email/{template}.html', context)


def _chf(amount):
    return f'{amount} CHF' if amount else 'N/A'


def send_visit_confirmed(visit):
    """Send confirmation email to member when a visit is logged."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = _('Visit confirmed at %(company)s') % {'company': partner.company_name}
    service_display = visit.get_service_type_display()
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')
    html = _render_email(
        'visit_confirmed',
        accent='#22c55e',
        name=member.get_full_name() or member.username,
        partner=partner.company_name,
        service=service_display,
        cost=_chf(visit.cost),
        when=ts,
        description=visit.service_description or '',
    )
    plain = (
        f"Visit confirmed at {partner.company_name}\n"
        f"Service: {service_display}\nCost: {_chf(visit.cost)}\nDate: {ts}\n"
    )
    _send(subject, plain, html, [member.email])


def send_visit_edited(visit, audit):
    """Send notification to member when their visit record is edited."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = _('Visit record updated — %(company)s') % {'company': partner.company_name}
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')
    html = _render_email(
        'visit_edited',
        accent='#f59e0b',
        name=member.get_full_name() or member.username,
        partner=partner.company_name,
        when=ts,
        old_service=audit.previous_service_type,
        service=visit.get_service_type_display(),
        old_cost=_chf(audit.previous_cost),
        cost=_chf(visit.cost),
        reason=audit.reason,
    )
    plain = (
        f"Your visit at {partner.company_name} has been edited.\n"
        f"Reason: {audit.reason}\n"
        f"New service: {visit.get_service_type_display()}, Cost: {visit.cost or 'N/A'} CHF\n"
    )
    _send(subject, plain, html, [member.email])


def send_visit_cancelled(visit, audit):
    """Send notification to member when their visit is cancelled."""
    member = visit.member
    partner = visit.partner
    if not member.email:
        return

    subject = _('Visit cancelled — %(company)s') % {'company': partner.company_name}
    ts = visit.timestamp.strftime('%d.%m.%Y %H:%M')
    html = _render_email(
        'visit_cancelled',
        accent='#ef4444',
        name=member.get_full_name() or member.username,
        partner=partner.company_name,
        when=ts,
        service=audit.previous_service_type,
        cost=_chf(audit.previous_cost),
        reason=audit.reason,
    )
    plain = (
        f"Your visit at {partner.company_name} has been cancelled.\n"
        f"Reason: {audit.reason}\n"
    )
    _send(subject, plain, html, [member.email])


def send_test_email(recipient=ADMIN_EMAIL):
    """Send a simple test email to verify SMTP configuration."""
    subject = _('IESA Sport — Test Email')
    plain = 'This is a test email from IESA Sport visit notification system.'
    html = _render_email('test_email', accent='#22c55e')
    return _send(subject, plain, html, [recipient])


def _send(subject, plain_text, html_content, recipients):
    """Internal dispatcher.

    Tries CleverReach first (if configured), then falls back to Django SMTP.
    Each recipient gets an individual CleverReach mailing so that CR analytics
    are per-person.
    """
    from .cleverreach_client import is_configured as cr_is_configured
    from .cleverreach_client import send_cleverreach_email as cr_send

    if getattr(settings, 'EMAIL_PREFER_SMTP', False):
        # Real SMTP is configured (e.g. Google Workspace): use it first, CleverReach only as backup.
        delivered_count = 0
        for email_addr in recipients:
            if _smtp_send(subject, plain_text, html_content, [email_addr]):
                delivered_count += 1
            elif cr_is_configured():
                logger.warning('SMTP delivery failed for %s — trying CleverReach', email_addr)
                if cr_send(to_email=email_addr, to_name=email_addr, subject=subject,
                           html=html_content, text=plain_text):
                    delivered_count += 1
        return delivered_count

    if cr_is_configured():
        delivered_count = 0
        for email_addr in recipients:
            ok = cr_send(
                to_email=email_addr,
                to_name=email_addr,  # real name not always available at this level
                subject=subject,
                html=html_content,
                text=plain_text,
            )
            if ok:
                delivered_count += 1
            else:
                logger.warning(
                    'CleverReach delivery failed for %s — falling back to SMTP', email_addr
                )
                smtp_ok = _smtp_send(subject, plain_text, html_content, [email_addr])
                if smtp_ok:
                    delivered_count += 1
        return delivered_count

    return _smtp_send(subject, plain_text, html_content, recipients)


def _smtp_send(subject, plain_text, html_content, recipients):
    """Direct SMTP send wrapper (bypasses custom CleverReach backend).

    Always uses real SMTP (Resend or configured host).  If RESEND_API_KEY is
    available we use it directly so this fallback works even when settings did
    not set EMAIL_HOST (e.g. console backend for local dev).
    """
    import os as _os
    resend_key = _os.environ.get('RESEND_API_KEY', '').strip()

    # Prefer env-level Resend SMTP credentials; fall back to Django settings.
    host     = 'smtp.resend.com'      if resend_key else getattr(settings, 'EMAIL_HOST', 'localhost')
    port     = 465                     if resend_key else getattr(settings, 'EMAIL_PORT', 25)
    user     = 'resend'               if resend_key else getattr(settings, 'EMAIL_HOST_USER', '')
    password = resend_key              if resend_key else getattr(settings, 'EMAIL_HOST_PASSWORD', '')
    use_ssl  = True                    if resend_key else getattr(settings, 'EMAIL_USE_SSL', False)
    use_tls  = False                   if resend_key else getattr(settings, 'EMAIL_USE_TLS', False)

    try:
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=host,
            port=port,
            username=user,
            password=password,
            use_tls=use_tls,
            use_ssl=use_ssl,
            fail_silently=False,
        )
        result = send_mail(
            subject=subject,
            message=plain_text,
            from_email=_get_from_email(),
            recipient_list=recipients,
            html_message=html_content,
            fail_silently=False,
            connection=connection,
        )
        logger.info('SMTP email sent: "%s" → %s', subject, recipients)
        return result
    except Exception as exc:
        logger.error('SMTP email failed: "%s" → %s: %s', subject, recipients, exc)
        return 0
