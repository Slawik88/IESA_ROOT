"""
Custom Django email backend for CleverReach.

When CLEVERREACH_CLIENT_ID is set, replace Django's default email backend
with this one in settings_addon.py so that ALL outgoing emails
(password reset, auth, custom) go through CleverReach REST API.

Falls back transparently to SMTP if CleverReach send fails.
"""

import logging

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

logger = logging.getLogger(__name__)


class CleverReachEmailBackend(BaseEmailBackend):
    """
    Django email backend that delivers via CleverReach REST API.

    Each ``EmailMessage`` sent through Django's ``send_mail()``,
    ``send_mass_mail()``, or the admin email system is routed through
    ``users.cleverreach_client.send_cleverreach_email()``.

    If the CleverReach API call fails the message is automatically
    re-delivered via Django's configured SMTP backend so no email is lost.
    """

    def send_messages(self, email_messages):
        """Send each message via CleverReach, falling back to SMTP per-message."""
        from users.cleverreach_client import send_cleverreach_email

        sent = 0
        for message in email_messages:
            subject = message.subject
            text_body = message.body
            html_body = ""

            # Extract HTML alternative if present
            if hasattr(message, "alternatives"):
                for content, mimetype in message.alternatives:
                    if mimetype == "text/html":
                        html_body = content
                        break
            if not html_body:
                # Minimal fallback: wrap plain text in simple HTML
                html_body = f"<html><body><pre>{text_body}</pre></body></html>"

            all_ok = True
            for recipient in message.to:
                ok = send_cleverreach_email(
                    to_email=recipient,
                    to_name=recipient,
                    subject=subject,
                    html=html_body,
                    text=text_body,
                )
                if not ok:
                    all_ok = False
                    logger.warning(
                        "CleverReach backend: delivery failed for %s — using SMTP fallback",
                        recipient,
                    )
                    self._smtp_fallback(message, [recipient])

            if all_ok:
                sent += 1

        return sent

    def _smtp_fallback(self, message, override_recipients=None):
        """Resend one message via SMTP backend as a fallback."""
        original_to = message.to
        try:
            from django.conf import settings as _settings
            # Temporarily re-address if needed
            if override_recipients is not None:
                message.to = override_recipients
            smtp = SMTPBackend(
                host=getattr(_settings, 'EMAIL_HOST', None),
                port=getattr(_settings, 'EMAIL_PORT', None),
                username=getattr(_settings, 'EMAIL_HOST_USER', None),
                password=getattr(_settings, 'EMAIL_HOST_PASSWORD', None),
                use_tls=getattr(_settings, 'EMAIL_USE_TLS', False),
                use_ssl=getattr(_settings, 'EMAIL_USE_SSL', False),
                fail_silently=False,
            )
            smtp.send_messages([message])
        except Exception as exc:
            logger.error("CleverReach SMTP fallback also failed: %s", exc)
        finally:
            message.to = original_to
