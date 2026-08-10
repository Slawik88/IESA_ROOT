"""Signed, expiring e-mail ownership verification for IESA accounts."""

from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from users.email_service import _send
from users.models import User


TOKEN_SALT = 'users.email-verification.v1'
DEFAULT_MAX_AGE = 48 * 60 * 60


class EmailVerificationError(Exception):
    """Base class for safe, user-facing token failures."""


class EmailVerificationExpired(EmailVerificationError):
    pass


class EmailVerificationInvalid(EmailVerificationError):
    pass


class EmailVerificationConflict(EmailVerificationError):
    """Another account has already verified the requested address."""


@dataclass(frozen=True)
class VerificationResult:
    user: User
    already_verified: bool


def _normalized_email(value):
    return (value or '').strip().lower()


def make_email_verification_token(user):
    """Create a tamper-proof token bound to both the account and current e-mail."""
    return signing.dumps(
        {'uid': user.pk, 'email': _normalized_email(user.email)},
        salt=TOKEN_SALT,
        compress=True,
    )


def verify_email_token(token):
    max_age = getattr(settings, 'EMAIL_VERIFICATION_MAX_AGE', DEFAULT_MAX_AGE)
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=max_age)
    except signing.SignatureExpired as exc:
        raise EmailVerificationExpired from exc
    except (signing.BadSignature, TypeError, ValueError) as exc:
        raise EmailVerificationInvalid from exc

    try:
        user = User.objects.get(pk=payload.get('uid'))
    except (User.DoesNotExist, TypeError, ValueError) as exc:
        raise EmailVerificationInvalid from exc

    token_email = _normalized_email(payload.get('email'))
    if not token_email or token_email != _normalized_email(user.email):
        # Changing the address immediately invalidates every old link.
        raise EmailVerificationInvalid

    already_verified = user.is_email_verified
    if not already_verified:
        if User.objects.filter(
            email__iexact=token_email,
            email_verified_at__isnull=False,
        ).exclude(pk=user.pk).exists():
            raise EmailVerificationConflict
        try:
            with transaction.atomic():
                user.email_verified_at = timezone.now()
                user.save(update_fields=['email_verified_at'])
        except IntegrityError as exc:
            # The database constraint closes the small race between the
            # conflict lookup and saving two simultaneous confirmations.
            raise EmailVerificationConflict from exc
    return VerificationResult(user=user, already_verified=already_verified)


def send_email_verification(user, request=None):
    """Send the verification link and record a successful delivery attempt."""
    if not user.email:
        return False

    token = make_email_verification_token(user)
    path = reverse('users:verify_email', kwargs={'token': token})
    if request is not None:
        verification_url = request.build_absolute_uri(path)
    else:
        domain = getattr(settings, 'SITE_DOMAIN', 'iesasport.ch')
        verification_url = f'https://{domain}{path}'

    context = {
        'user': user,
        'verification_url': verification_url,
        'expires_hours': getattr(settings, 'EMAIL_VERIFICATION_MAX_AGE', DEFAULT_MAX_AGE) // 3600,
        'support_email': 'iesa@iesasport.ch',
    }
    subject = render_to_string('users/email/verify_email_subject.txt', context).strip()
    plain = render_to_string('users/email/verify_email.txt', context)
    html = render_to_string('users/email/verify_email.html', context)
    delivered = bool(_send(subject, plain, html, [user.email]))
    if delivered:
        user.email_verification_sent_at = timezone.now()
        user.save(update_fields=['email_verification_sent_at'])
    return delivered
