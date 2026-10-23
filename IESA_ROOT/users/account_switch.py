"""Quick switching between several IESA accounts on one device.

A person who runs, say, a personal account and a partner/business account can
sign in to both once ("Add another account" in the menu) and then flip between
them with one tap, without typing passwords again.

How it stays safe
-----------------
* The list lives in a signed, HttpOnly, SameSite=Lax cookie. Each entry carries
  a fingerprint derived from that account's current password hash, so changing
  the password (or deactivating the account) instantly revokes the link.
* An account is added only after the person has actually signed in to it
  through the normal login form while already signed in to another one.
* The list is wiped on logout and on any ordinary login. On a shared computer
  the next person can therefore never inherit someone else's linked accounts.
* Switching is a POST (CSRF-protected) and requires an active session.
"""
import hmac

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core import signing
from django.dispatch import receiver
from django.utils.crypto import salted_hmac

COOKIE_NAME = 'iesa_accounts'
SALT = 'users.account-switch.v1'
MAX_ACCOUNTS = 5
MAX_AGE = 30 * 24 * 60 * 60

KEEP_FLAG = '_keep_linked_accounts'      # set by flows that legitimately maintain the list
FORGET_FLAG = '_forget_linked_accounts'  # set by the signals below, honoured by the middleware


def fingerprint(user):
    return salted_hmac(SALT, f'{user.pk}:{user.password}').hexdigest()[:24]


def _load(request):
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return {}
    try:
        data = signing.loads(raw, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        return {int(pk): str(fp) for pk, fp in data.items()}
    except (TypeError, ValueError):
        return {}


def linked_accounts(request, exclude=None):
    """Active accounts whose link is still valid, optionally without the current one."""
    entries = _load(request)
    if not entries:
        return []
    from .models import User
    accounts = []
    for user in User.objects.filter(pk__in=list(entries), is_active=True).order_by('username'):
        if exclude is not None and user.pk == exclude.pk:
            continue
        if hmac.compare_digest(entries[user.pk], fingerprint(user)):
            accounts.append(user)
    return accounts


def remember(response, request, *users):
    """Add `users` to the signed cookie on `response` (keeps the newest MAX_ACCOUNTS)."""
    entries = _load(request)
    for user in users:
        entries.pop(user.pk, None)          # re-insert so it counts as most recent
        entries[user.pk] = fingerprint(user)
    while len(entries) > MAX_ACCOUNTS:
        entries.pop(next(iter(entries)))
    response.set_cookie(
        COOKIE_NAME,
        signing.dumps({str(pk): fp for pk, fp in entries.items()}, salt=SALT, compress=True),
        max_age=MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
    )


def forget_all(response):
    response.delete_cookie(COOKIE_NAME, samesite='Lax')


@receiver(user_logged_in)
def _flag_forget_on_login(sender, request, user, **kwargs):
    if request is not None and not getattr(request, KEEP_FLAG, False):
        setattr(request, FORGET_FLAG, True)


@receiver(user_logged_out)
def _flag_forget_on_logout(sender, request, user, **kwargs):
    if request is not None:
        setattr(request, FORGET_FLAG, True)


class LinkedAccountsMiddleware:
    """Deletes the cookie on responses where a login/logout flagged it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, FORGET_FLAG, False):
            forget_all(response)
        return response


def context_processor(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or COOKIE_NAME not in request.COOKIES:
        return {}
    return {'linked_accounts': linked_accounts(request, exclude=user)}
